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
the machine reads it before every job pull, so the newest note always wins over a queued job.
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
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .backups.jobs import _iso, canonical, job_kid
from .natsconf import NODE_ID_RE, POLICY_STREAM

log = logging.getLogger("onemind.policy")

POLICY_SCHEMA = "onemind.policy/v1"
POLICY_MAX_BYTES = 1 << 20
# Job kinds that move or switch something in the world: refused on a machine while a stop is on.
# internal/jobs/policy.go ActuatePrefixes is the same list.
ACTUATE_PREFIXES = ("physical", "robot", "actuator", "relay", "motion")
RETRY_S = 5.0


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


def sign_snapshot(key: Ed25519PrivateKey, node_id: str, epoch: int, state: PolicyState, now: datetime) -> dict:
    """One machine's signed snapshot. internal/jobs/policy.go verifies it (shared vector)."""
    if not isinstance(node_id, str) or not NODE_ID_RE.match(node_id):
        raise ValueError("node_id is not a lowercase node id")
    if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 1:
        raise ValueError("epoch must be a positive integer")
    env = {"schema": POLICY_SCHEMA, "aud": f"node:{node_id}", "kid": job_kid(key.public_key()), "epoch": epoch,
           "issued_at": _iso(now), **state.body()}
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


class EpochStore:
    """The gateway's policy epoch and the digest it was raised for, in one small file (durable write).
    Starts at 1, the epoch every job before this step was signed under (backups/jobs.py POLICY_EPOCH)."""

    def __init__(self, path: Path):
        self.path = path

    def read(self) -> tuple[int, str]:
        try:
            d = json.loads(self.path.read_text())
            return int(d["epoch"]), str(d["digest"])
        except (OSError, ValueError, KeyError, TypeError):
            return 1, ""

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

    def epoch(self) -> int:
        """The epoch a job signed now must carry. Fails closed to the stored one if the state is unreadable."""
        try:
            return self.store.advance(self.state().digest())
        except Exception:  # noqa: BLE001 - a switch that cannot be read must not stop job signing
            return self.store.read()[0]

    def view(self) -> dict:
        epoch = self.epoch()  # the same epoch a job signed now carries
        try:
            body = self.state().body()
        except Exception as exc:  # noqa: BLE001
            body = {"error": exc.__class__.__name__}
        return {"schema": POLICY_SCHEMA, "epoch": epoch, **body, "published": dict(sorted(self.published.items())),
                "error": self.error or None}

    async def publish_on(self, nc, *, every: bool = False) -> None:
        """Bring the hub's notes to the current epoch: the stream first, then each machine whose note is
        older (or all of them after a new connection). Never raises: an error is kept and retried."""
        try:
            js = nc.jetstream()
            if every:
                await ensure_stream(js)
            state = self.state()
            epoch = self.store.advance(state.digest())
            for node_id in self.node_ids():
                if not every and self.published.get(node_id) == epoch:
                    continue
                env = sign_snapshot(self.key(), node_id, epoch, state, self.clock())
                await js.publish(policy_subject(node_id), json.dumps(env).encode(),
                                 headers={"Nats-Msg-Id": f"policy-{node_id}-{epoch}"})
                self.published[node_id] = epoch
            self.error = ""
        except Exception as exc:  # noqa: BLE001 - NATS refused or dropped: keep serving, retry
            self.error = f"{exc.__class__.__name__}: {exc}"[:300]
            log.warning("policy snapshots not published (%s); retrying", self.error)

    async def run(self, bus, interval_s: float = RETRY_S) -> None:
        while True:
            nc = bus.nc if bus.connected else None
            if nc is not None:
                key = (id(nc), (getattr(nc, "stats", None) or {}).get("reconnects", 0))
                fresh = key != self._seen
                await self.publish_on(nc, every=fresh)
                if not self.error:
                    self._seen = key
            await asyncio.sleep(interval_s)
