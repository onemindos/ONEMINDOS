# SPDX-License-Identifier: Apache-2.0
"""The signed stop and revoke snapshot every machine keeps (D-029; design step N7).

In plain words: a machine cut off from the hub cannot ask whether the owner pressed a stop or revoked a
key. So the gateway sends each joined machine one small signed note, `onemind.policy/v1`, every time
that answer changes, and the machine keeps the newest one on its own disk and checks every job against
it before running it, also after a power cut or a long time offline. The note can only ever add a "no":

- `stop`: the motion lockout (physical.py) and the agent kill switch (agent_stop.py). While either is
  on, a machine refuses every job whose kind actuates something (ACTUATE_PREFIXES);
- `revoked_kids`: job keys the machine must no longer trust (the fabric root key's rotations fill it);
- `allowed_kinds`: when set, the only job kinds this machine may run;
- `epoch`: raised on every change. Jobs carry the epoch they were signed under (onemind.job/v2
  `policy_epoch`), and a machine refuses a job older than the newest note, so a job signed before
  "Stop" can never run after it, even if it was already queued.

Transport: the hub keeps the newest note per machine in ONEMIND_POLICY (last message per subject,
direct get on). Each machine's account may read only its own note (natsconf.py policy_services), and
the machine reads it before every job pull and again right before a job that actuates something, so
the newest note always wins over a queued job.

When a stop switch changes, the switch call itself pushes the new notes to the hub before it returns
(`push_now`, a listener on the lockout and the kill switch), and, while a stop is on, purges every
actuating job still queued in ONEMIND_JOBS. So once the owner's "Stop" call has returned, a job queued
before it cannot actuate anything: it is gone from the queue, or the machine reads the stop note right
before running it. At dispatch, an actuating job additionally needs a signed answer to a fresh
challenge from the gateway, so a retained note cannot authorize dispatch during a failed push.
A successful Stop waits for previously issued dispatch windows to expire. If the push fails, the
switch stays on locally, the API reports incomplete enforcement, and the background loop retries.

The epoch file is the one thing that must never go back: a corrupt file is an error (EpochError),
never a silent reset to 1, which would make every machine ignore the next note and refuse every new
job as stale. Job signing and publishing then stop loudly until the file is restored.
Signed with the gateway's job key today (the key machines already pin at join; the fabric root key
moves it to a key of its own). Nothing on NATS approves anything: the note only refuses.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .backups.jobs import _iso, canonical, job_kid
from .natsconf import JOBS_STREAM, NODE_ID_RE, POLICY_STREAM

log = logging.getLogger("onemind.policy")

POLICY_SCHEMA = "onemind.policy/v1"
POLICY_MAX_BYTES = 1 << 20
# Job kinds that move or switch something in the world: refused on a machine while a stop is on.
# internal/jobs/policy.go ActuatePrefixes is the same list.
ACTUATE_PREFIXES = ("physical", "robot", "actuator", "relay", "motion")
RETRY_S = 5.0
PUSH_TIMEOUT_S = 3.0  # how long a stop switch call waits for the hub to hold the new notes
DISPATCH_TIMEOUT_S = 1.0  # same duration as internal/jobs/intake.go dispatchTimeout
_CHALLENGE = re.compile(rb"[0-9a-f]{32}")


class EpochError(RuntimeError):
    """The epoch file exists but cannot be read: never guessed, never reset (fails loudly)."""


def actuating_job_subjects() -> list[str]:
    """ONEMIND_JOBS subjects of every job kind that actuates something, on every machine (purged on stop)."""
    return [f"onemind.node.*.job.{p}{tail}" for p in ACTUATE_PREFIXES for tail in ("", ".>")]


def policy_subject(node_id: str) -> str:
    return f"onemind.node.{node_id}.policy"


@dataclass(frozen=True)
class PolicyState:
    """What the snapshot says, before the epoch and the signature."""
    motion_lockout: bool = False
    agents_stopped: bool = False
    revoked_kids: tuple[str, ...] = ()
    allowed_kinds: tuple[str, ...] | None = None

    def body(self) -> dict:
        return {"stop": {"motion_lockout": self.motion_lockout, "agents": self.agents_stopped},
                "revoked_kids": sorted(set(self.revoked_kids)),
                "allowed_kinds": sorted(set(self.allowed_kinds)) if self.allowed_kinds is not None else None}

    def digest(self) -> str:
        return hashlib.sha256(canonical(self.body())).hexdigest()


def sign_snapshot(key: Ed25519PrivateKey, node_id: str, epoch: int, state: PolicyState, now: datetime,
                  *, challenge: str | None = None) -> dict:
    """One machine's signed snapshot. internal/jobs/policy.go verifies it (shared vector)."""
    if not isinstance(node_id, str) or not NODE_ID_RE.match(node_id):
        raise ValueError("node_id is not a lowercase node id")
    if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 1:
        raise ValueError("epoch must be a positive integer")
    env = {"schema": POLICY_SCHEMA, "aud": f"node:{node_id}", "kid": job_kid(key.public_key()), "epoch": epoch,
           "issued_at": _iso(now), **state.body()}
    if challenge is not None:
        env["challenge"] = challenge
    env["sig"] = base64.b64encode(key.sign(canonical(env))).decode("ascii")
    return env


def stream_json() -> dict:
    """ONEMIND_POLICY in the NATS API's JSON shape (internal/leaf/testdata/policy-stream.golden.json)."""
    return {"name": POLICY_STREAM, "subjects": ["onemind.node.*.policy"], "retention": "limits", "storage": "file",
            "discard": "old", "max_bytes": POLICY_MAX_BYTES, "max_msgs_per_subject": 1, "allow_direct": True,
            "num_replicas": 1}


def stream_config():
    from nats.js.api import DiscardPolicy, RetentionPolicy, StorageType, StreamConfig

    return StreamConfig(name=POLICY_STREAM, subjects=["onemind.node.*.policy"], retention=RetentionPolicy.LIMITS,
                        storage=StorageType.FILE, discard=DiscardPolicy.OLD, max_bytes=POLICY_MAX_BYTES,
                        max_msgs_per_subject=1, allow_direct=True, num_replicas=1,
                        description="OneMind stop and revoke snapshot per machine (fabric_policy.py)")


async def ensure_stream(js) -> str:
    """Create ONEMIND_POLICY, or bring it to its config."""
    from nats.js.errors import NotFoundError

    try:
        await js.stream_info(POLICY_STREAM)
    except NotFoundError:
        await js.add_stream(stream_config())
        return "created"
    await js.update_stream(stream_config())
    return "updated"


async def purge_actuating_jobs(js) -> None:
    """Drop every queued job that actuates something, on every machine (ONEMIND_JOBS). A hub without
    the job stream has nothing to drop."""
    from nats.js.errors import NotFoundError

    for subject in actuating_job_subjects():
        try:
            await js.purge_stream(JOBS_STREAM, subject=subject)
        except NotFoundError:
            return


class EpochStore:
    """The gateway's policy epoch and the digest it was raised for, in one small file (durable write).
    Starts at 1, the epoch every job before this step was signed under (backups/jobs.py POLICY_EPOCH)."""

    def __init__(self, path: Path):
        self.path = path

    def read(self) -> tuple[int, str]:
        """(epoch, digest). No file yet: epoch 1 for the calm answer (no stop, nothing revoked), the one
        every job signed before this step carries, so the first stop ever is epoch 2 and refuses them.
        A file that cannot be read raises EpochError: guessing 1 would make every machine ignore the next
        note and refuse every new job, fabric-wide and silently."""
        try:
            raw = self.path.read_text()
        except FileNotFoundError:
            return 1, PolicyState().digest()
        except OSError as exc:
            raise EpochError(f"{self.path}: cannot be read ({exc.__class__.__name__})") from exc
        try:
            d = json.loads(raw)
            epoch, digest = d["epoch"], d["digest"]
            if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 1 or not isinstance(digest, str):
                raise ValueError("epoch must be a positive integer and digest a string")
            return epoch, digest
        except (ValueError, KeyError, TypeError) as exc:
            raise EpochError(f"{self.path} is corrupt ({exc}); restore it, or write an epoch above every "
                             "machine's (onemind fabric policy shows the last one each machine got)") from exc

    def peek(self, digest: str) -> int:
        """The epoch `advance(digest)` would return, without writing anything (for reads)."""
        epoch, stored = self.read()
        return epoch if digest == stored or not stored else epoch + 1  # "" only in a pre-release file

    def advance(self, digest: str) -> int:
        """The epoch for `digest`: unchanged when it is the stored one, else one more (kept on disk first)."""
        epoch, stored = self.read()
        if digest == stored:
            return epoch
        if stored:
            epoch += 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, json.dumps({"epoch": epoch, "digest": digest}).encode())
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, self.path)
        dfd = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
        return epoch


@dataclass
class PolicyPublisher:
    """Keeps every joined machine's snapshot current on the hub. `state()` reads the stop switches and
    revocations; a change raises the epoch and republishes every machine's note."""

    key: Callable[[], Ed25519PrivateKey]
    store: EpochStore
    state: Callable[[], PolicyState]
    node_ids: Callable[[], list[str]]
    clock: Callable[[], datetime]
    published: dict[str, int] = field(default_factory=dict)  # node id -> epoch of its note on the hub
    error: str = ""
    _seen: tuple = ()
    _purged: int = 0  # the epoch whose stop already purged ONEMIND_JOBS of actuating jobs
    _publish_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _epoch_lock: threading.Lock = field(default_factory=threading.Lock)
    # A previous gateway process could have answered just before restarting.
    _dispatch_until: float = field(default_factory=lambda: time.monotonic() + DISPATCH_TIMEOUT_S)

    def _current(self) -> tuple[PolicyState, int]:
        with self._epoch_lock:
            state = self.state()
            return state, self.store.advance(state.digest())

    def epoch(self) -> int:
        """The epoch a job signed now must carry. A switch that cannot be read counts as on (state()
        does that); an epoch file that cannot be read raises EpochError, so nothing is signed with a
        guessed epoch."""
        with self._epoch_lock:
            try:
                digest = self.state().digest()
            except Exception:  # noqa: BLE001 - read-only jobs can still use the stored epoch
                return self.store.read()[0]
            return self.store.advance(digest)

    def view(self) -> dict:
        """What GET /v1/fabric/policy shows. Read-only: it never writes the epoch file. `epoch` is the one
        a job signed now carries; 0 with `error` set when the epoch file cannot be read."""
        error = self.error or None
        try:
            state = self.state()
            body = state.body()
            epoch = self.store.peek(state.digest())
        except EpochError as exc:
            body, epoch, error = PolicyState(True, True).body(), 0, f"EpochError: {exc}"[:300]
        except Exception as exc:  # noqa: BLE001
            body, epoch, error = PolicyState(True, True).body(), 0, f"{exc.__class__.__name__}: {exc}"[:300]
        return {"schema": POLICY_SCHEMA, "epoch": epoch, **body, "published": dict(sorted(self.published.items())),
                "error": error}

    async def publish_on(self, nc, *, every: bool = False, confirm_stop: bool = False) -> bool:
        """Bring the hub's notes to the current epoch: the stream first, then each machine whose note is
        older (or all of them after a new connection); while a stop is on, purge actuating jobs from
        ONEMIND_JOBS once per epoch. Never raises: an error is kept and retried."""
        async with self._publish_lock:
            connection = (id(nc), (getattr(nc, "stats", None) or {}).get("reconnects", 0))
            published = await self._publish(nc, every=every or connection != self._seen, confirm_stop=confirm_stop)
            if published:
                self._seen = connection
            return published

    async def _publish(self, nc, *, every: bool, confirm_stop: bool) -> bool:
        try:
            js = nc.jetstream()
            if every:
                await ensure_stream(js)
            state, epoch = self._current()
            for node_id in self.node_ids():
                if not every and self.published.get(node_id) == epoch:
                    continue
                env = sign_snapshot(self.key(), node_id, epoch, state, self.clock())
                await js.publish(policy_subject(node_id), json.dumps(env).encode(),
                                 headers={"Nats-Msg-Id": f"policy-{node_id}-{epoch}"})
                self.published[node_id] = epoch
            if (state.motion_lockout or state.agents_stopped) and self._purged != epoch:
                await purge_actuating_jobs(js)
                self._purged = epoch
            if confirm_stop:
                # A node starts its monotonic window before sending its challenge. Waiting one
                # window after we signed the last permissive answer also covers answers in flight.
                await asyncio.sleep(max(0.0, self._dispatch_until - time.monotonic()))
            self.error = ""
            return True
        except EpochError as exc:
            self.error = f"EpochError: {exc}"[:300]
            log.error("policy snapshots not published: %s", exc)
        except Exception as exc:  # noqa: BLE001 - NATS refused or dropped: keep serving, retry
            self.error = f"{exc.__class__.__name__}: {exc}"[:300]
            log.warning("policy snapshots not published (%s); retrying", self.error)
        return False

    async def confirm_dispatch(self, msg) -> None:
        """Prove the current gateway policy to a node at its dispatch boundary."""
        if not _CHALLENGE.fullmatch(msg.data) or not msg.reply:
            return
        try:
            node_id = msg.subject.split(".")[2]
            if node_id not in self.node_ids():
                return
            state, epoch = self._current()
            env = sign_snapshot(self.key(), node_id, epoch, state, self.clock(), challenge=msg.data.decode("ascii"))
            if not (state.motion_lockout or state.agents_stopped):
                self._dispatch_until = time.monotonic() + DISPATCH_TIMEOUT_S
            await msg.respond(json.dumps(env).encode())
        except Exception as exc:  # noqa: BLE001 - without a signed answer the node refuses dispatch
            log.warning("policy dispatch check failed (%s)", exc.__class__.__name__)

    def push_now(self, bus, timeout_s: float = PUSH_TIMEOUT_S, *, confirm_stop: bool = False) -> bool:
        """Called by a stop switch, from the request's worker thread, before the switch call returns:
        put the new notes on the hub (and purge actuating jobs while a stop is on) now, not at the next
        5 s tick. True when every machine's note on the hub is current."""
        try:
            # Persist the transition even if the broker cannot be reached, so Stop followed
            # by Resume during an outage still invalidates every pre-Stop job.
            self._current()
            if not bus.connected:
                self.error = "NATS is not connected"
                return False
            return bus.run_threadsafe(lambda nc: self.publish_on(nc, confirm_stop=confirm_stop), timeout_s)
        except Exception as exc:  # noqa: BLE001 - a timeout or a closed loop: the background loop retries
            self.error = f"{exc.__class__.__name__}: {exc}"[:300] or "push timed out"
            return False

    async def run(self, bus, interval_s: float = RETRY_S) -> None:
        while True:
            nc = bus.nc if bus.connected else None
            if nc is not None:
                await self.publish_on(nc)
            await asyncio.sleep(interval_s)
