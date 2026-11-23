# SPDX-License-Identifier: Apache-2.0
"""In-process fan-out behind GET /v1/events (issue #606): one reader per source, one queue per stream.

Before this, every open stream read the audit file on its own every half second. Now each source
has ONE ordered reader for the whole gateway, and each open stream (a *subscriber*) gets its own
small queue that the reader fills:

- **Facts** (the audit log, contract §3): `AuditPump` reads new lines right after `AuditLog.append`
  writes them (the log calls `kick`), in file order, so they reach every stream in seq order. A
  stream never reads the file again except for a replay on connect. Facts are never dropped or
  merged: when a stream's fact queue is full the stream gets `stream.reset` (reason slow_client) and
  ends; the client reconnects with Last-Event-ID and replays from the file.
- **Asset values** (the `asset` kind of the subject tree, #600): `AssetState` is one NATS JetStream
  *ordered consumer* on the hub's `asset-state` KV bucket (#601). It starts with the last value of
  every key, so it always holds the current state of every asset: that is the snapshot a stream gets
  on connect. Values are merged latest-wins per key in each queue, so a plugin sending 1,000 values
  a second costs a slow stream one entry per key, never a growing backlog, and never delays a fact.

The KV key of an asset subject `onemind.asset.<asset_class>.<asset_id>.<field>` is the subject
without `onemind.asset.` (`asset_key`). The gateway is the only writer of that bucket; this module
only reads it. Browsers and phones never get NATS credentials: they read this through the gateway.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import math
import re
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from . import audit as auditlog
from . import subjects
from .auditread import iter_records

log = logging.getLogger("onemind.fanout")

ASSET_BUCKET = "asset-state"          # jetstream.KV_BUCKETS["ONEMIND_ASSET_STATE"]
ASSET_PREFIX = "onemind.asset."
DATAPOINT = "onemind.datapoint/v1"
QUALITIES = ("live", "stale", "unknown", "simulated")
FACT_QUEUE_MAX = 1024                 # facts waiting for one stream before it gets stream.reset
VALUE_KEYS_MAX = 10_000               # distinct asset keys waiting for one stream before stream.reset
PUMP_POLL_S = 1.0                     # also look at the audit file this often (a write by another process)
RETRY_S = 5.0
MAX_KINDS = 32
_KIND = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


# ---------------------------------------------------------------- one stream's queue
class Subscriber:
    """One open stream. Readers push from any thread; the stream drains it in its own event loop."""

    def __init__(self, loop: asyncio.AbstractEventLoop, *, assets: bool = False,
                 kinds: frozenset[str] | None = None):
        self.loop = loop
        self.assets = assets          # this stream asked for asset.* events
        self.kinds = kinds            # ?kind= asset classes, None = all
        self.reset: str | None = None
        self.coalesced = 0            # values replaced by a newer one before the stream sent them
        self._facts: deque[dict] = deque()
        self._values: dict[str, tuple[str, AssetValue]] = {}
        self._event = asyncio.Event()
        self._lock = threading.Lock()

    def wants(self, v: AssetValue) -> bool:
        return self.assets and (self.kinds is None or v.asset_class in self.kinds)

    def push_fact(self, rec: dict) -> None:
        with self._lock:
            if self.reset:
                return
            if len(self._facts) >= FACT_QUEUE_MAX:
                self._overflow()
            else:
                self._facts.append(rec)
        self._wake()

    def push_value(self, op: str, v: AssetValue) -> None:
        """op is value or removed. Latest wins: a newer value for a waiting key replaces it."""
        with self._lock:
            if self.reset:
                return
            if self._values.pop(v.key, None) is not None:
                self.coalesced += 1
            elif len(self._values) >= VALUE_KEYS_MAX:
                self._overflow()
            if not self.reset:
                self._values[v.key] = (op, v)
        self._wake()

    def _overflow(self) -> None:
        self.reset = "slow_client"
        self._facts.clear()
        self._values.clear()

    def next(self) -> tuple[str, object] | None:
        """The next item: every waiting fact first, then the oldest waiting value."""
        with self._lock:
            if self._facts:
                return "fact", self._facts.popleft()
            if self._values:
                key = next(iter(self._values))
                return self._values.pop(key)
        return None

    def waiting(self) -> bool:
        with self._lock:
            return bool(self._facts or self._values or self.reset)

    async def wait(self, timeout: float) -> None:
        try:
            await asyncio.wait_for(self._event.wait(), timeout)
        except asyncio.TimeoutError:
            pass
        self._event.clear()

    def _wake(self) -> None:
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self.loop:
            self._event.set()
            return
        try:
            self.loop.call_soon_threadsafe(self._event.set)
        except RuntimeError:  # that stream's loop is closed: it is going away
            pass


# ---------------------------------------------------------------- facts: the audit log
def _records(fh: IO[bytes], start: int) -> Iterator[tuple[int, dict]]:
    """(offset after the line, record) from byte `start` of an open file, as auditread.iter_records."""
    pos = 0
    while pos < start:
        chunk = fh.read(min(1 << 20, start - pos))
        if not chunk:
            return
        pos += len(chunk)
    for raw in fh:
        if not raw.endswith(b"\n"):
            break
        pos += len(raw)
        try:
            rec = json.loads(raw) if raw.strip() else None
        except ValueError:
            continue
        if isinstance(rec, dict) and isinstance(rec.get("seq"), int):
            yield pos, rec


def _end_of_lines(path: Path) -> int:
    """The offset just after the last complete line (a line still being written is read later)."""
    try:
        with path.open("rb") as fh:
            size = fh.seek(0, 2)
            tail_at = max(0, size - 65536)
            fh.seek(tail_at)
            tail = fh.read()
    except OSError:
        return 0
    cut = tail.rfind(b"\n")
    if cut >= 0:
        return tail_at + cut + 1
    end = 0
    for end, _rec in iter_records(path):  # a last line over 64 KiB: rare, walk the file
        pass
    return end


class AuditPump:
    """The one ordered reader of the audit log for every open stream.

    `kick()` (called by AuditLog after each append, from whichever thread wrote) reads the new lines
    and hands each to every subscriber, in file order. Nothing reads while no stream is open."""

    def __init__(self, path: Path):
        self.path = path
        self.reads = 0                # how often the file was read (idle streams cost none)
        self._subs: set[Subscriber] = set()
        self._offset = 0
        self._last_poll = 0.0
        self._lock = threading.Lock()

    def attach(self, sub: Subscriber) -> None:
        with self._lock:
            if not self._subs:  # nobody was listening: start at the end of what is written now
                self._offset = _end_of_lines(self.path)
            self._subs.add(sub)

    def detach(self, sub: Subscriber) -> None:
        with self._lock:
            self._subs.discard(sub)

    def subscribers(self) -> list[Subscriber]:
        with self._lock:
            return list(self._subs)

    def kick(self) -> None:
        with self._lock:
            if self._subs:
                self._read_locked()

    def poll(self) -> None:
        """Catch a write made outside this process: at most one look per PUMP_POLL_S for all streams."""
        now = time.monotonic()
        if now - self._last_poll >= PUMP_POLL_S:
            self._last_poll = now
            self.kick()

    def _read_locked(self) -> None:
        try:
            size = self.path.stat().st_size
        except OSError:
            return
        if size == self._offset:
            return
        self.reads += 1
        recs: list[dict] = []
        if size < self._offset:  # rotated: the rest of the old file is the newest segment
            segs = auditlog.segments(self.path)
            if segs:
                try:
                    with gzip.open(segs[-1][2], "rb") as fh:
                        recs += [r for _p, r in _records(fh, self._offset)]
                except (OSError, EOFError):
                    log.warning("audit segment %s could not be read for live events", segs[-1][2].name)
            self._offset = 0
        for pos, rec in iter_records(self.path, self._offset):
            self._offset = pos
            recs.append(rec)
        for rec in recs:
            for sub in self._subs:
                sub.push_fact(rec)


# ---------------------------------------------------------------- asset values: the asset-state KV bucket
@dataclass(frozen=True)
class AssetValue:
    key: str                  # <asset_class>.<asset_id>.<field>, the KV key
    asset_class: str
    asset_id: str
    field: str
    revision: int             # the KV revision (stream sequence): newer is larger
    datapoint: dict           # onemind.datapoint/v1


def asset_key(subject: str) -> str:
    """The asset-state KV key of an asset subject (the subject without `onemind.asset.`)."""
    v = subjects.load().check(subject, "gateway")
    if not v.ok or v.kind != "asset":
        raise ValueError(f"{subject!r} is not an asset subject: {v.reason}")
    return subject[len(ASSET_PREFIX):]


def parse_asset_key(key: str) -> tuple[str, str, str]:
    """(asset_class, asset_id, field) of a KV key; ValueError when it is not a registered asset subject."""
    asset_key(ASSET_PREFIX + key)
    cls, aid, fld = key.split(".")
    return cls, aid, fld


def datapoint_problems(dp: object, subject: str) -> list[str]:
    """Cheap checks of a stored datapoint (the intake runs the full schema before it writes)."""
    if not isinstance(dp, dict):
        return ["the value is not a JSON object"]
    out = []
    if dp.get("schema") != DATAPOINT:
        out.append(f"schema is not {DATAPOINT}")
    if dp.get("nats_subject") != subject:
        out.append("nats_subject does not match the key")
    if not isinstance(dp.get("time"), str):
        out.append("time is missing")
    if dp.get("quality") not in QUALITIES:
        out.append("quality is not live, stale, unknown or simulated")
    if not isinstance(dp.get("source"), dict):
        out.append("source is missing")
    if "position" in dp:
        out += subjects.position_problems(dp["position"])
    return out


class AssetState:
    """The current value of every asset key, kept by one ordered consumer of the asset-state bucket.

    `state`: off (no JetStream on this hub), pending (waiting for NATS or the bucket), ready, error."""

    def __init__(self) -> None:
        self.state = "off"
        self.reason = "JetStream is off on this hub, so there is no asset state"
        self.rejected = 0
        self.listeners: list[Callable[[str, AssetValue], None]] = []
        self._latest: dict[str, AssetValue] = {}
        # The current values of each asset that carry a position, by key. A stream picks its own
        # position from these, so a value it may not see never places an asset on its map.
        self._pos: dict[tuple[str, str], dict[str, AssetValue]] = {}
        self._lock = threading.Lock()

    def snapshot(self) -> list[AssetValue]:
        with self._lock:
            return list(self._latest.values())

    def position(self, asset_class: str, asset_id: str,
                 allowed: Callable[[AssetValue], bool] | None = None) -> tuple[float, float] | None:
        """The (lat, lon) of an asset from the newest of its current values that carries a position,
        counting only values `allowed` passes (the caller's asset filters, design rule 8). A value the
        caller may not see never gives away where the asset is, not even through a ?bbox= test."""
        with self._lock:
            held = list(self._pos.get((asset_class, asset_id), {}).values())
        for v in sorted(held, key=lambda x: x.revision, reverse=True):
            if allowed is None or allowed(v):
                return float(v.datapoint["position"]["lat"]), float(v.datapoint["position"]["lon"])
        return None

    def _keep_pos_locked(self, v: AssetValue | None, key: str, asset: tuple[str, str]) -> None:
        held = self._pos.get(asset)
        if v is not None and "position" in v.datapoint:
            self._pos.setdefault(asset, {})[key] = v
        elif held is not None:
            held.pop(key, None)  # this key no longer carries a position (a new value, or removed)
            if not held:
                del self._pos[asset]

    def ingest(self, key: str, revision: int, raw: bytes | dict) -> AssetValue | None:
        """Keep a value read from the bucket and hand it on. An invalid one is counted and dropped."""
        try:
            cls, aid, fld = parse_asset_key(key)
            dp = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
        except (ValueError, subjects.RegistryError):
            self.rejected += 1
            return None
        problems = datapoint_problems(dp, ASSET_PREFIX + key)
        if problems:
            self.rejected += 1
            log.warning("asset-state %s dropped: %s", key, "; ".join(problems))
            return None
        v = AssetValue(key, cls, aid, fld, revision, dp)
        with self._lock:
            old = self._latest.get(key)
            if old is not None and old.revision >= revision:
                return None  # already have this or a newer one
            self._latest[key] = v
            self._keep_pos_locked(v, key, (cls, aid))
        self._emit("value", v)
        return v

    def remove(self, key: str, revision: int) -> AssetValue | None:
        with self._lock:
            old = self._latest.pop(key, None)
            if old is not None:
                self._keep_pos_locked(None, key, (old.asset_class, old.asset_id))
        if old is None:
            return None
        gone = AssetValue(key, old.asset_class, old.asset_id, old.field, revision, old.datapoint)
        self._emit("removed", gone)
        return gone

    def _emit(self, op: str, v: AssetValue) -> None:
        for fn in self.listeners:
            try:
                fn(op, v)
            except Exception:  # one listener failing must not stop the feed
                log.exception("asset listener failed")

    async def on_kv_message(self, msg) -> None:
        """The ordered consumer's callback: a put, or a delete or purge marker (KV-Operation header)."""
        key = msg.subject[len(f"$KV.{ASSET_BUCKET}."):]
        revision = int(msg.metadata.sequence.stream)
        if (msg.headers or {}).get("KV-Operation") in ("DEL", "PURGE"):
            self.remove(key, revision)
        else:
            self.ingest(key, revision, msg.data)

    async def run(self, bus, bucket_ready: Callable[[], bool], interval_s: float = RETRY_S) -> None:
        """Keep one ordered consumer on the bucket while NATS is up; subscribe again on a new connection
        and after each reconnect.

        A connection is (id(nc), reconnects), as JetStreamCore.run tracks it: nats-py keeps the same
        `nc` object when it reconnects (allow_reconnect), so the object alone would leave the state at
        pending for good after the first NATS drop. After a reconnect the old subscription is dropped
        and a fresh one starts from the last value per key (the server may have restarted and lost the
        ephemeral consumer); `ingest` skips revisions it already holds, so nothing is sent twice."""
        from nats.js.api import DeliverPolicy

        self.state, self.reason = "pending", "waiting for NATS and the asset-state bucket"
        seen = None
        sub = None
        try:
            while True:
                nc = bus.nc if bus.connected else None
                if nc is None:
                    if self.state == "ready":
                        self.state, self.reason = "pending", "NATS is down; the last values are kept"
                else:
                    key = (id(nc), (getattr(nc, "stats", None) or {}).get("reconnects", 0))
                    if key != seen and bucket_ready():
                        if sub is not None:
                            await _unsubscribe(sub)
                            sub = None
                        try:
                            # Last value per key first (the snapshot), then every change, in order. The
                            # ordered consumer is ephemeral and re-creates itself after a sequence gap.
                            sub = await nc.jetstream().subscribe(
                                f"$KV.{ASSET_BUCKET}.>", stream=f"KV_{ASSET_BUCKET}", cb=self.on_kv_message,
                                ordered_consumer=True, deliver_policy=DeliverPolicy.LAST_PER_SUBJECT)
                        except Exception as exc:  # NATS answered but refused: keep serving, retry
                            self.state, self.reason = "error", f"{exc.__class__.__name__}: {exc}"[:300]
                        else:
                            seen, self.state, self.reason = key, "ready", ""
                await asyncio.sleep(interval_s)
        finally:
            if sub is not None:
                await _unsubscribe(sub)


async def _unsubscribe(sub) -> None:
    try:
        await sub.unsubscribe()
    except Exception:  # the old connection is gone or closed: nothing left to stop
        log.debug("asset-state: the old subscription could not be stopped", exc_info=True)


# ---------------------------------------------------------------- ?kind= and ?bbox=
def parse_kinds(raw: str | None) -> frozenset[str] | None:
    if raw is None or not raw.strip():
        return None
    kinds = [k.strip() for k in raw.split(",") if k.strip()]
    if len(kinds) > MAX_KINDS:
        raise ValueError(f"kind names at most {MAX_KINDS} asset classes")
    bad = [k for k in kinds if not _KIND.match(k)]
    if bad:
        raise ValueError(f"kind {bad[0]!r} is not an asset class (lowercase letters, digits, '_' and '-')")
    return frozenset(kinds)


def parse_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    """min_lon,min_lat,max_lon,max_lat in WGS-84 degrees (GeoJSON order). min_lon > max_lon crosses 180."""
    if raw is None or not raw.strip():
        return None
    parts = raw.split(",")
    try:
        nums = [float(x) for x in parts]
    except ValueError:
        nums = []
    if len(nums) != 4 or not all(math.isfinite(n) for n in nums):
        raise ValueError("bbox is min_lon,min_lat,max_lon,max_lat: four numbers")
    w, s, e, n = nums
    if not (-180 <= w <= 180 and -180 <= e <= 180 and -90 <= s <= 90 and -90 <= n <= 90):
        raise ValueError("bbox is outside WGS-84 (lon -180 to 180, lat -90 to 90)")
    if s > n:
        raise ValueError("bbox min_lat is above max_lat")
    return w, s, e, n


def in_bbox(pos: tuple[float, float], bbox: tuple[float, float, float, float]) -> bool:
    lat, lon = pos
    w, s, e, n = bbox
    if not s <= lat <= n:
        return False
    return w <= lon <= e if w <= e else (lon >= w or lon <= e)


class AssetView:
    """One stream's ?kind= and ?bbox= filter. An asset that leaves the box is sent once more (its new
    position), so the map can take its marker away; after that it is quiet until it comes back."""

    def __init__(self, kinds: frozenset[str] | None, bbox, position: Callable[[str, str], tuple | None]):
        self.kinds, self.bbox, self.position = kinds, bbox, position
        self._inside: set[tuple[str, str]] = set()

    def passes(self, v: AssetValue, removed: bool = False) -> bool:
        if self.kinds is not None and v.asset_class not in self.kinds:
            return False
        if self.bbox is None:
            return True
        asset = (v.asset_class, v.asset_id)
        if removed:
            return asset in self._inside
        pos = self.position(*asset)
        if pos is not None and in_bbox(pos, self.bbox):
            self._inside.add(asset)
            return True
        if asset in self._inside:
            self._inside.discard(asset)
            return True
        return False
