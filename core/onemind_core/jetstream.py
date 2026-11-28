# SPDX-License-Identifier: Apache-2.0
"""The hub's JetStream budget and its core streams and KV buckets (issue #601, on top of #540, #472, #532).

JetStream is the part of NATS that keeps a copy of messages on disk, so nothing is lost when a link
drops. Every byte it keeps is a byte the owner's data disk does not have, so three rules hold here:

1. **The cap is a share of /data, never a fixed number.** `cap_from_total(total)` is DATA_SHARE of the
   data disk, at least CAP_MIN_BYTES and at most CAP_MAX_BYTES. A disk too small for the minimum is
   refused. onemind-firstboot writes this cap into the hub's nats.conf (`max_file_store`) and into
   gateway.env (`ONEMIND_FABRIC_JETSTREAM_MAX_BYTES`), so NATS and the gateway agree on one number.
2. **No cap, no JetStream.** `require_cap` refuses 0 or less; the gateway then creates no stream at
   all, and the hub's NATS refuses to start with a `jetstream` block that has no `max_file_store` or
   no `max_memory_store: 0` (os/.../onemind-nats-capcheck). Without those two lines nats-server takes
   the free disk and 75 % of RAM (nats-server v2.15.3 server/jetstream.go, dynJetStreamConfig).
3. **File storage only.** Memory storage is lost on a restart, silently; nothing here asks for it.

The core streams and buckets come from the subject tree (sdk/schema/onemind.subjects.json, #600),
which names a stream and a retention for each kind. A kind kept as `latest` (asset, layer) is a KV
bucket (the last value per key); `ONEMIND_NODE_OUTBOX` is kept per node by the hub's source streams
(internal/leaf HubSourceStream), not by one gateway stream; every other named stream is a core stream.
Together they may reserve CORE_SHARE of the cap (NATS reserves a stream's max_bytes when it is
created), scaled down evenly on a small disk; the rest is for app `spec.streams` (streams.py) and the
per-node source streams. Each node's source stream keeps that registry retention too (#747): the
registry's age, and its size or NODE_SHARE / NODE_COPY_SLOTS of the cap, whichever is smaller, so a
handful of nodes fit in NODE_SHARE and one chatty or compromised node only ever fills its own copy.
Because each stream has its own reserved size, a full stream drops only its own oldest messages (or
refuses new ones, for a work queue): the audit stream is never touched by it.

The gateway connects to NATS in the background (bus.py) and `JetStreamCore.run` creates or updates
the streams whenever it has a connection, again after every reconnect; NATS down never stops it serving.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import subjects
from .natsconf import NODE_ID_RE, OUTBOX_STREAM, node_domain, node_js_api, source_deliver_prefix

log = logging.getLogger("onemind.jetstream")

MIB = 1 << 20
GIB = 1 << 30
DATA_SHARE = 0.10                 # the hub's JetStream cap is this share of the data disk
CAP_MIN_BYTES = 256 * MIB         # below this the disk is too small: JetStream is refused
CAP_MAX_BYTES = 64 * GIB          # a large disk still gives the store at most this
CORE_SHARE = 0.5                  # what core streams and buckets may reserve of the cap
DEFAULT_STREAM_MAX_BYTES = 64 * MIB   # a registry stream that names no max_bytes still gets a cap
MIN_STREAM_BYTES = 1 * MIB
NODE_SHARE = 0.25                 # what the per-node hub source streams of NODE_COPY_SLOTS nodes reserve
NODE_COPY_SLOTS = 8               # a household fabric is a handful of machines; more still fit, from the rest

# Registry streams that are kept per node by the hub's source streams, not created by the gateway.
PER_NODE_STREAMS = ("ONEMIND_NODE_OUTBOX",)
# Registry streams with the `latest` policy, and the KV bucket that keeps each (NATS stream KV_<bucket>).
KV_BUCKETS = {"ONEMIND_ASSET_STATE": "asset-state", "ONEMIND_LAYER_META": "layer-meta"}

RETRY_S = 5.0
HUB_SOURCE_DEDUPE_NS = 24 * 3600 * 10**9   # internal/leaf DefaultDedupeWindow
# The registry retention of ONEMIND_NODE_OUTBOX (kinds/node), which internal/leaf HubSourceStream also
# carries (DefaultHubCopyMaxBytes, DefaultOutboxMaxAge); a test checks both against the registry.
HUB_COPY_MAX_BYTES = 256 * MIB
HUB_COPY_MAX_AGE_S = 7 * 24 * 3600


def node_copy_bytes(cap_bytes: int, wanted: int = HUB_COPY_MAX_BYTES) -> int:
    """The size of one node's hub source stream for a JetStream cap: the registry's size, or a
    NODE_COPY_SLOTS-th of NODE_SHARE of the cap on a smaller disk, never under MIN_STREAM_BYTES."""
    return min(int(wanted), max(MIN_STREAM_BYTES, int(require_cap(cap_bytes) * NODE_SHARE / NODE_COPY_SLOTS)))


@dataclass(frozen=True)
class HubSource:
    """The hub's copy of one node's leaf outbox (#747): internal/leaf HubSourceStream for the node's
    domain, plus the node's own delivery prefix, the one delivery subject tree its NATS account
    exports to ONEMIND (natsconf.py). The gateway creates it when the node's join is approved; the
    source reaches the leaf over the leaf link once the node connects, and resumes after every cut.
    internal/leaf/testdata/hub-source-stream.golden.json is `to_json()` for node aaa111, and the Go
    test checks it equals HubSourceStream."""

    node_id: str
    max_bytes: int = HUB_COPY_MAX_BYTES
    max_age_s: int = HUB_COPY_MAX_AGE_S

    def __post_init__(self) -> None:
        if not isinstance(self.node_id, str) or not NODE_ID_RE.match(self.node_id):
            raise ValueError(f"node id {self.node_id!r} is not a lowercase id")
        for what, v, low in (("max_bytes", self.max_bytes, MIN_STREAM_BYTES), ("max_age_s", self.max_age_s, 1)):
            if isinstance(v, bool) or not isinstance(v, int) or v < low:
                raise ValueError(f"hub source {what} {v!r} is under {low}: a node's copy is never unbounded")

    @property
    def name(self) -> str:
        return "NODE_" + node_domain(self.node_id).replace("-", "_") + "_" + OUTBOX_STREAM

    def to_json(self) -> dict:
        """The stream in the NATS API's JSON shape (what the Go side unmarshals). A full copy drops its
        own oldest event (discard old, the registry's limits policy); it never refuses the source."""
        return {"name": self.name, "retention": "limits", "storage": "file", "discard": "old",
                "max_bytes": self.max_bytes, "max_age": self.max_age_s * 10**9,
                "sources": [{"name": OUTBOX_STREAM, "external": {"api": node_js_api(self.node_id),
                                                                  "deliver": source_deliver_prefix(self.node_id)}}],
                "duplicate_window": HUB_SOURCE_DEDUPE_NS}

    def config(self):
        from nats.js.api import DiscardPolicy, ExternalStream, RetentionPolicy, StorageType, StreamConfig, StreamSource

        return StreamConfig(
            name=self.name, retention=RetentionPolicy.LIMITS, storage=StorageType.FILE,
            discard=DiscardPolicy.OLD, max_bytes=self.max_bytes, max_age=float(self.max_age_s),
            sources=[StreamSource(name=OUTBOX_STREAM, external=ExternalStream(
                api=node_js_api(self.node_id), deliver=source_deliver_prefix(self.node_id)))],
            duplicate_window=HUB_SOURCE_DEDUPE_NS / 1e9,
        )


async def ensure_hub_source(js, src: HubSource) -> str:
    """Create a node's hub source stream, or bring an existing one to its config. Returns what happened."""
    from nats.js.errors import NotFoundError

    try:
        await js.stream_info(src.name)
    except NotFoundError:
        await js.add_stream(src.config())
        return "created"
    await js.update_stream(src.config())
    return "updated"


class JetStreamCapError(ValueError):
    """JetStream would run without a cap, or the cap cannot hold the core streams: refused."""


def cap_from_total(total_bytes: int, share: float = DATA_SHARE) -> int:
    """The hub's JetStream cap for a data disk of `total_bytes`: a share of it, clamped, never 0."""
    if not 0 < share <= 0.5:
        raise JetStreamCapError(f"the JetStream share of /data must be above 0 and at most 0.5, got {share}")
    cap = min(int(total_bytes * share), CAP_MAX_BYTES)
    if cap < CAP_MIN_BYTES:
        raise JetStreamCapError(
            f"the data disk ({total_bytes} bytes) is too small for JetStream: {share:.0%} of it is under "
            f"{CAP_MIN_BYTES} bytes")
    return cap


def cap_for_path(path: str | Path, share: float = DATA_SHARE) -> int:
    """`cap_from_total` for the disk that holds `path` (its total size, so the cap never moves as it fills)."""
    try:
        total = shutil.disk_usage(path).total
    except OSError as exc:
        raise JetStreamCapError(f"the data disk at {path} cannot be read: {exc.strerror or exc}") from None
    return cap_from_total(total, share)


def require_cap(max_bytes: int) -> int:
    """`max_bytes` when it is a real cap. 0 or less is refused: JetStream never runs uncapped."""
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise JetStreamCapError("JetStream without a cap is refused (ONEMIND_FABRIC_JETSTREAM_MAX_BYTES is 0)")
    return max_bytes


def _filter(pattern: subjects.Pattern) -> str:
    """The NATS subscription filter for a pattern: each one-token placeholder is `*`; the first
    placeholder that may span several tokens ends the filter with `>`."""
    out = []
    for s in pattern.slots:
        if s.literal is not None:
            out.append(s.literal)
        elif s.hi > 1:
            out.append(">")
            break
        else:
            out.append("*")
    return ".".join(out)


def _covers(a: str, b: str) -> bool:
    """True when filter `a` matches every subject filter `b` matches."""
    at, bt = a.split("."), b.split(".")
    for i, t in enumerate(at):
        if t == ">":
            return len(bt) > i
        if i >= len(bt) or (t != "*" and t != bt[i]) or (t == "*" and bt[i] == ">"):
            return False
    return len(at) == len(bt)


def _minimal(filters: list[str]) -> tuple[str, ...]:
    """Drop duplicates and filters another one already covers (NATS refuses overlap inside a stream)."""
    uniq = sorted(set(filters))
    return tuple(f for f in uniq if not any(g != f and _covers(g, f) for g in uniq))


@dataclass(frozen=True)
class CoreStream:
    name: str
    subjects: tuple[str, ...]
    retention: str            # limits | workqueue
    max_bytes: int
    max_age_s: int | None
    discard: str              # old (drop the oldest) | new (refuse the newest; work queues keep unread work)
    deny_delete: bool = False
    deny_purge: bool = False

    def to_json(self) -> dict:
        return {"name": self.name, "subjects": list(self.subjects), "storage": "file", "replicas": 1,
                "retention": self.retention, "discard": self.discard, "max_bytes": self.max_bytes,
                "max_age_s": self.max_age_s, "deny_delete": self.deny_delete, "deny_purge": self.deny_purge}

    def config(self):
        from nats.js.api import DiscardPolicy, RetentionPolicy, StorageType, StreamConfig

        return StreamConfig(
            name=self.name, description="OneMind core stream (onemind_core/jetstream.py)",
            subjects=list(self.subjects), retention=RetentionPolicy(self.retention), storage=StorageType.FILE,
            num_replicas=1, max_bytes=self.max_bytes, max_age=float(self.max_age_s or 0),
            discard=DiscardPolicy(self.discard), deny_delete=self.deny_delete, deny_purge=self.deny_purge,
            duplicate_window=120.0,
        )


@dataclass(frozen=True)
class CoreBucket:
    bucket: str               # the KV bucket (NATS stream KV_<bucket>)
    stream: str               # the registry stream it stands for
    kinds: tuple[str, ...]
    max_bytes: int

    @property
    def stream_name(self) -> str:
        return f"KV_{self.bucket}"

    def to_json(self) -> dict:
        return {"bucket": self.bucket, "stream": self.stream_name, "registry_stream": self.stream,
                "kinds": list(self.kinds), "storage": "file", "history": 1, "max_bytes": self.max_bytes}

    def config(self):
        from nats.js.api import KeyValueConfig, StorageType

        return KeyValueConfig(bucket=self.bucket, description=f"OneMind {self.stream} (latest value per key)",
                              history=1, max_bytes=self.max_bytes, storage=StorageType.FILE, replicas=1)


@dataclass(frozen=True)
class CorePlan:
    cap_bytes: int
    budget_bytes: int
    streams: tuple[CoreStream, ...]
    buckets: tuple[CoreBucket, ...]
    node_copy_bytes: int = HUB_COPY_MAX_BYTES   # each node's hub source stream (HubSource)
    node_copy_age_s: int = HUB_COPY_MAX_AGE_S

    def hub_source(self, node_id: str) -> HubSource:
        """A node's hub source stream, with the registry retention sized for this cap."""
        return HubSource(node_id, self.node_copy_bytes, self.node_copy_age_s)

    @property
    def reserved_bytes(self) -> int:
        return sum(s.max_bytes for s in self.streams) + sum(b.max_bytes for b in self.buckets)

    def to_json(self) -> dict:
        return {"cap_bytes": self.cap_bytes, "budget_bytes": self.budget_bytes, "reserved_bytes": self.reserved_bytes,
                "streams": [s.to_json() for s in self.streams], "buckets": [b.to_json() for b in self.buckets],
                "node_copy": {"max_bytes": self.node_copy_bytes, "max_age_s": self.node_copy_age_s, "discard": "old"}}


def plan(cap_bytes: int, registry: subjects.Registry | None = None) -> CorePlan:
    """The core streams and buckets for a hub JetStream cap, from the subject tree.

    Each keeps the registry's retention; together they reserve at most CORE_SHARE of the cap, scaled
    down evenly when the registry asks for more. Refused without a cap, or when the cap cannot give
    every stream MIN_STREAM_BYTES."""
    cap = require_cap(cap_bytes)
    reg = registry or subjects.load()
    groups: dict[str, dict] = {}
    node_r: dict = {}
    for p in reg.patterns:
        if p.stream in PER_NODE_STREAMS:
            if p.retention.get("policy") != "limits":
                raise subjects.RegistryError(f"stream {p.stream} is kept per node by limits, not {p.retention!r}")
            node_r = p.retention
            continue
        if not p.stream:
            continue
        g = groups.setdefault(p.stream, {"retention": p.retention, "filters": [], "kinds": []})
        g["filters"].append(_filter(p))
        if p.kind not in g["kinds"]:
            g["kinds"].append(p.kind)
        if g["retention"] != p.retention:
            raise subjects.RegistryError(f"stream {p.stream} is given two retentions in the subject tree")
    wanted = {name: int(g["retention"].get("max_bytes") or DEFAULT_STREAM_MAX_BYTES) for name, g in groups.items()}
    budget = int(cap * CORE_SHARE)
    if MIN_STREAM_BYTES * len(wanted) > budget:
        raise JetStreamCapError(f"a JetStream cap of {cap} bytes cannot hold the {len(wanted)} core streams")
    scale = min(1.0, budget / sum(wanted.values())) if wanted else 1.0
    streams, buckets = [], []
    for name in sorted(groups):
        g, size = groups[name], max(MIN_STREAM_BYTES, int(wanted[name] * scale))
        r = g["retention"]
        if r["policy"] == "latest":
            if name not in KV_BUCKETS:
                raise subjects.RegistryError(f"stream {name} keeps the latest value but has no KV bucket")
            buckets.append(CoreBucket(KV_BUCKETS[name], name, tuple(g["kinds"]), size))
        elif r["policy"] in ("limits", "workqueue"):
            streams.append(CoreStream(
                name, _minimal(g["filters"]), r["policy"], size, r.get("max_age_s"),
                "new" if r["policy"] == "workqueue" else "old",
                bool(r.get("deny_delete")), bool(r.get("deny_purge"))))
        else:
            raise subjects.RegistryError(f"stream {name} has retention policy {r['policy']!r}")
    out = CorePlan(cap, budget, tuple(streams), tuple(buckets),
                   node_copy_bytes(cap, int(node_r.get("max_bytes") or HUB_COPY_MAX_BYTES)),
                   int(node_r.get("max_age_s") or HUB_COPY_MAX_AGE_S))
    if out.reserved_bytes > budget:  # the MIN_STREAM_BYTES floor can push past the budget on a tiny cap
        raise JetStreamCapError(f"the core streams need {out.reserved_bytes} bytes, more than {budget} of the cap")
    return out


async def ensure(js, p: CorePlan) -> dict[str, str]:
    """Create each core stream and bucket, or bring an existing one to the plan. Returns {name: what happened}."""
    from nats.js.errors import NotFoundError

    done: dict[str, str] = {}
    for s in p.streams:
        try:
            await js.stream_info(s.name)
        except NotFoundError:
            await js.add_stream(s.config())
            done[s.name] = "created"
        else:
            await js.update_stream(s.config())
            done[s.name] = "updated"
    for b in p.buckets:
        try:
            info = await js.stream_info(b.stream_name)
        except NotFoundError:
            await js.create_key_value(b.config())
            done[b.stream_name] = "created"
        else:
            if info.config.max_bytes != b.max_bytes:
                await js.update_stream(info.config.evolve(max_bytes=b.max_bytes))
                done[b.stream_name] = "updated"
            else:
                done[b.stream_name] = "unchanged"
    return done


@dataclass
class JetStreamCore:
    """The gateway's side of the hub store: the plan, and its state for the Engine feed (#619).

    `state` is off (no cap: nothing is created), refused (the cap or the subject tree does not allow
    the plan), pending (waiting for NATS), ready, or error (NATS answered but refused a stream)."""

    max_bytes: int
    data_path: Path | None = None
    registry: subjects.Registry | None = None
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    plan: CorePlan | None = None
    state: str = "off"
    reason: str = ""
    ensured_at: datetime | None = None
    results: dict[str, str] = field(default_factory=dict)
    # node id -> its hub source stream's state: pending (wanted, not yet on NATS), created, updated,
    # or error: <why> (retried on the next pass). Filled by want_source on join approval (fabric.py).
    sources: dict[str, str] = field(default_factory=dict)
    _seen: tuple = ()

    def __post_init__(self) -> None:
        if self.max_bytes <= 0:
            self.state, self.reason = "off", "no JetStream cap is set, so the gateway creates no stream"
            return
        try:
            cap = require_cap(self.max_bytes)
            if self.data_path is not None:
                with contextlib.suppress(JetStreamCapError):  # an unreadable path keeps the configured cap
                    cap = min(cap, cap_for_path(self.data_path))
            self.plan = plan(cap, self.registry)
            self.state, self.reason = "pending", "waiting for NATS"
        except (JetStreamCapError, subjects.RegistryError) as exc:
            self.state, self.reason = "refused", str(exc)

    def view(self) -> dict:
        return {"state": self.state, "reason": self.reason,
                "ensured_at": self.ensured_at.isoformat() if self.ensured_at else None,
                "results": dict(self.results), "plan": self.plan.to_json() if self.plan else None,
                "sources": [{"node_id": n, "stream": HubSource(n).name, "state": st}
                            for n, st in sorted(self.sources.items())]}

    def want_source(self, node_id: str) -> None:
        """A node's join was approved (or it is already joined at startup): keep its outbox on the hub.
        The stream is made by `run` on the next pass with a NATS connection; nothing is made without a cap."""
        HubSource(node_id)  # refuses a bad id before it is kept
        if self.plan is not None and not self.sources.get(node_id, "").startswith(("created", "updated")):
            self.sources[node_id] = "pending"

    async def ensure_sources_on(self, nc, *, every: bool = False) -> None:
        """Create the wanted hub source streams on a connected client: the pending ones, or all of them
        after a new connection (`every`). Never raises: a refusal is kept per node and retried."""
        js = nc.jetstream()
        for node_id, st in list(self.sources.items()):
            if not every and st.startswith(("created", "updated")):
                continue
            try:
                self.sources[node_id] = await ensure_hub_source(js, self.plan.hub_source(node_id))
            except Exception as exc:  # NATS refused it or the link dropped: retry on the next pass
                self.sources[node_id] = f"error: {exc.__class__.__name__}: {exc}"[:300]
                log.warning("hub source stream for node %s not ensured (%s); retrying", node_id, self.sources[node_id])

    async def ensure_on(self, nc) -> bool:
        """Ensure the plan on a connected client. Never raises: a failure is kept in `state`."""
        if self.plan is None:
            return False
        try:
            self.results = await ensure(nc.jetstream(), self.plan)
        except Exception as exc:  # NATS answered but refused, or the link dropped: keep serving, retry
            self.state, self.reason = "error", f"{exc.__class__.__name__}: {exc}"[:300]
            log.warning("JetStream core streams not ensured (%s); retrying", self.reason)
            return False
        self.state, self.reason, self.ensured_at = "ready", "", self.clock()
        log.info("JetStream core streams ensured: %s", ", ".join(f"{k} {v}" for k, v in self.results.items()))
        return True

    async def run(self, bus, interval_s: float = RETRY_S) -> None:
        """Watch the bus; ensure the plan on each new connection and after each reconnect."""
        if self.plan is None:
            return
        while True:
            nc = bus.nc if bus.connected else None
            if nc is None:
                if self.state == "ready":
                    self.state, self.reason = "pending", "waiting for NATS"
            else:
                key = (id(nc), (getattr(nc, "stats", None) or {}).get("reconnects", 0))
                fresh = key != self._seen
                if fresh and await self.ensure_on(nc):
                    self._seen = key
                if self._seen == key:
                    await self.ensure_sources_on(nc, every=fresh)
            await asyncio.sleep(interval_s)
