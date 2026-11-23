# SPDX-License-Identifier: Apache-2.0
"""Bridge intake (#610): the one way outside data comes in, POST /v1/bridges/<id>/events.

A *bridge* is an installed app whose approved manifest has `spec.extensions.bridge` (#604,
sdk/contracts/connectors.md). Its workload holds a plugin token (`om_plg_`) minted at the approved
install with the grant `events:write:own`. It posts batches of events here; the gateway:

1. authenticates the plugin principal and checks the path id is its own app id (plugins/auth.py),
   that the approved install snapshot has a bridge block and that the bridge is not paused;
2. takes one token per event from the bridge's bucket (the manifest's eventsPerSecond and burst,
   capped by the hub maximum) and from the hub-wide bucket; short of tokens the whole batch is
   refused with 429 and Retry-After, before any work, so a flood costs almost nothing;
3. checks each event: its kind and name are one of the bridge's emits, at most min(maxEventBytes,
   16 KiB), and the stamped datapoint fits sdk/schema/onemind.datapoint.schema.json;
4. stamps source (always the app id: a bridge cannot speak for another source) and licence (the
   provider's terms record), dedupes by (id, revision) and coalesces latest-wins per entity;
5. keeps the latest value per entity in the table bridges_latest and publishes, best effort
   (NATS down never fails the caller): an onemind.event/v1 envelope on the bridge's own intake
   subject onemind.plugin.<app_id>.in.<kind>.<name>; for kind asset also the datapoint on
   onemind.asset.<name>.<id>.<field> and in the asset-state KV bucket (key <name>.<id>.<field>).

A refused event goes to onemind.plugin.<app_id>.reject. After REJECTS_TO_PAUSE refused events in
REJECT_WINDOW_S the bridge is paused (stored, so a restart keeps it) and one bridge.paused event
opens one owner alert; nothing is taken from it until an owner resumes it. Intake events are not
audit lines: the audit log keeps only pauses, resumes and refusals of the principal.
"""

from __future__ import annotations

import json
import math
import threading
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import JSON, BigInteger, DateTime, String, func, select
from sqlalchemy.orm import Mapped, mapped_column

from . import subjects
from .auth import Principal
from .errors import ApiError
from .ledger import Base, iso, utc
from .sections import config_section
from .store import FeatureSchema, SqlRepository

SCHEMA = FeatureSchema("bridges")

GRANT = "events:write:own"          # the plugin token grant minted for an approved bridge block
HUB_MAX_EVENT_BYTES = 16 * 1024      # the hub cap on one event; a manifest may only lower it
MAX_BATCH = 100                     # events per request
REJECTS_TO_PAUSE = 20
REJECT_WINDOW_S = 300
MAX_ENTITIES = 10_000               # latest-per-entity rows one bridge may keep
ASSET_KV_BUCKET = "asset-state"      # jetstream.KV_BUCKETS
KINDS = ("intel", "article", "alert", "layer", "asset")
_ID = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"   # subject placeholder `id` (onemind.subjects.json)
_TOKEN = r"^[a-z0-9][a-z0-9_-]{0,63}$"        # subject placeholder `token`


@config_section("bridges")
@dataclass(frozen=True)
class BridgeSettings:
    max_events_per_second: int = 50    # ONEMIND_BRIDGES_MAX_EVENTS_PER_SECOND: hub cap on one bridge's rate
    max_burst: int = 200               # ONEMIND_BRIDGES_MAX_BURST: hub cap on one bridge's burst
    hub_events_per_second: int = 500   # ONEMIND_BRIDGES_HUB_EVENTS_PER_SECOND: all bridges together

    def validate(self) -> None:
        if not 1 <= self.max_events_per_second <= 1000 or not 1 <= self.max_burst <= 10_000:
            raise ValueError("ONEMIND_BRIDGES_MAX_EVENTS_PER_SECOND must be 1-1000 and ONEMIND_BRIDGES_MAX_BURST 1-10000")
        if not self.max_events_per_second <= self.hub_events_per_second <= 100_000:
            raise ValueError("ONEMIND_BRIDGES_HUB_EVENTS_PER_SECOND must be at least the per-bridge cap, at most 100000")


class BridgeStateRow(Base):
    """A paused bridge (paused_at set) survives a gateway restart."""

    __tablename__ = "bridges_state"
    app_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)


class BridgeLatestRow(Base):
    """The latest value of one entity of one bridge: key <app_id>/<kind>/<name>/<id>/<field>."""

    __tablename__ = "bridges_latest"
    key: Mapped[str] = mapped_column(String(400), primary_key=True)
    app_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(128))
    field: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(BigInteger)
    event_id: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    datapoint: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # None when the provider's store is none


class BridgeEvent(BaseModel):
    """One event a bridge posts. `value` follows the datapoint envelope (at most 32 keys)."""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=_ID, description="the item's own id at the source; the entity latest-wins keys on")
    revision: int = Field(default=0, ge=0, le=2**53 - 1, description="bump it when the same item changes")
    kind: Literal["intel", "article", "alert", "layer", "asset"]
    name: str = Field(pattern=_TOKEN, description="one of the bridge's spec.extensions.bridge.emits names")
    field: str = Field(default="state", pattern=_TOKEN)
    time: AwareDatetime = Field(description="when the value was observed")
    quality: Literal["live", "stale", "unknown", "simulated"] = "live"
    value: Any = None
    unit: str | None = None
    position: dict | None = None


class IntakeBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    events: list[dict] = Field(min_length=1, max_length=MAX_BATCH)


class IntakeReject(BaseModel):
    index: int
    id: str | None = None
    reason: str


class IntakeResult(BaseModel):
    """What happened to a batch: published, already seen (same or older revision) and refused."""

    accepted: int
    duplicates: int
    rejected: list[IntakeReject]
    paused: bool


class BridgeStatus(BaseModel):
    """One bridge as `onemind bridge list|status` shows it; counters are since the gateway started."""

    id: str
    app_status: str | None
    state: Literal["active", "paused", "inactive"]
    provider: str
    mode: str
    data_class: str
    emits: list[dict]
    events_per_second: int
    burst: int
    max_event_bytes: int
    paused_at: str | None = None
    paused_reason: str | None = None
    accepted: int = 0
    duplicates: int = 0
    rejected: int = 0
    throttled: int = 0
    recent_rejects: int = 0
    last_event_at: str | None = None
    last_reject_reason: str | None = None
    entities: int = 0


class LatestValue(BaseModel):
    kind: str
    name: str
    id: str
    field: str
    revision: int
    received_at: str
    datapoint: dict | None


@dataclass(frozen=True)
class Bridge:
    """A bridge block from the approved install snapshot, with its effective limits."""

    app_id: str
    provider: dict
    block: dict
    rate: int
    burst: int
    max_event_bytes: int

    @property
    def emits(self) -> set[tuple[str, str]]:
        return {(e.get("kind"), e.get("name")) for e in self.block.get("emits") or [] if isinstance(e, dict)}

    @property
    def data_class(self) -> str:
        return str(self.block.get("dataClass") or "private")

    def licence(self) -> dict:
        out = {"id": str(self.provider.get("id") or self.app_id)}
        if self.provider.get("attribution"):
            out["attribution"] = str(self.provider["attribution"])[:256]
        if isinstance(self.provider.get("url"), str) and len(self.provider["url"]) <= 512:
            out["url"] = self.provider["url"]
        return out


@dataclass
class _Bucket:
    rate: float
    burst: float
    tokens: float
    at: float

    def take(self, n: int, now: float) -> float:
        """0 when n tokens were taken, else seconds until they would be there (nothing taken)."""
        self.tokens = min(self.burst, self.tokens + max(0.0, now - self.at) * self.rate)
        self.at = now
        if self.tokens >= n:
            self.tokens -= n
            return 0.0
        return (n - self.tokens) / self.rate


@dataclass
class _Live:
    bucket: _Bucket
    accepted: int = 0
    duplicates: int = 0
    rejected: int = 0
    throttled: int = 0
    rejects: deque = field(default_factory=deque)
    last_event_at: datetime | None = None
    last_reject_reason: str | None = None


def bridge_from(app_id: str, manifest: object, cfg: BridgeSettings) -> Bridge | None:
    """The bridge of an approved manifest snapshot, or None when it declares none."""
    spec = manifest.get("spec") if isinstance(manifest, dict) else None
    block = ((spec or {}).get("extensions") or {}).get("bridge") if isinstance(spec, dict) else None
    if not isinstance(block, dict):
        return None
    providers = ((spec.get("terms") or {}).get("providers") or [])
    provider = next((p for p in providers if isinstance(p, dict) and p.get("id") == block.get("provider")), {})
    limits = block.get("limits") or {}
    rate = max(1, min(int(limits.get("eventsPerSecond") or 1), cfg.max_events_per_second))
    burst = max(1, min(int(limits.get("burst") or rate), cfg.max_burst))
    size = max(1, min(int(limits.get("maxEventBytes") or HUB_MAX_EVENT_BYTES), HUB_MAX_EVENT_BYTES))
    return Bridge(app_id, provider, block, rate, burst, size)


def may_read(p: Principal, data_class: str) -> bool:
    """The subscribe-time check: may this person receive a bridge's values at all?

    Checked once when a reader asks for the snapshot (GET /v1/bridges/<id>/latest; the live
    fan-out will call it on subscribe). Public data: owners and adults. Any other data class
    (owner, private, location, activity): owners only. Agents, plugins and machines: never here."""
    if p.kind != "person":
        return False
    return p.is_owner or (data_class == "public" and p.role == "adult")


class BridgeRepository(SqlRepository):
    def installs(self) -> dict[str, dict]:
        from .plugins.models import PluginInstallRow

        with self.db.session() as s:
            return {r.app_id: r.manifest for r in s.scalars(select(PluginInstallRow))}

    def install(self, app_id: str) -> dict | None:
        from .plugins.models import PluginInstallRow

        with self.db.session() as s:
            row = s.get(PluginInstallRow, app_id)
            return row.manifest if row else None

    def state(self, app_id: str) -> BridgeStateRow | None:
        with self.db.session() as s:
            row = s.get(BridgeStateRow, app_id)
            if row is not None:
                s.expunge(row)
            return row

    def set_paused(self, app_id: str, at: datetime | None, reason: str | None) -> None:
        values = {"paused_at": at, "paused_reason": reason}
        with self.db.session.begin() as s:
            s.execute(self.db.insert()(BridgeStateRow).values(app_id=app_id, **values)
                      .on_conflict_do_update(index_elements=[BridgeStateRow.app_id], set_=values))

    def existing(self, keys: list[str]) -> dict[str, int]:
        with self.db.session() as s:
            return dict(s.execute(select(BridgeLatestRow.key, BridgeLatestRow.revision)
                                  .where(BridgeLatestRow.key.in_(keys))).all())

    def count(self, app_id: str) -> int:
        with self.db.session() as s:
            return s.scalar(select(func.count()).select_from(BridgeLatestRow).where(BridgeLatestRow.app_id == app_id))

    def asset_owner(self, app_id: str, name: str, entity: str) -> str | None:
        """Another bridge that already publishes asset <name>/<entity>, if any."""
        with self.db.session() as s:
            return s.scalar(select(BridgeLatestRow.app_id).where(
                BridgeLatestRow.kind == "asset", BridgeLatestRow.name == name, BridgeLatestRow.entity == entity,
                BridgeLatestRow.app_id != app_id).limit(1))

    def upsert(self, values: dict) -> bool:
        """Latest-wins: write only when the revision is newer than the stored one. True when written."""
        ins = self.db.insert()(BridgeLatestRow).values(**values)
        newer = {k: getattr(ins.excluded, k) for k in values if k not in ("key", "app_id", "kind", "name", "entity", "field")}
        stmt = ins.on_conflict_do_update(index_elements=[BridgeLatestRow.key], set_=newer,
                                         where=BridgeLatestRow.revision < ins.excluded.revision)
        with self.db.session.begin() as s:
            return s.execute(stmt.returning(BridgeLatestRow.key)).first() is not None

    def latest(self, app_id: str, limit: int = 500) -> list[BridgeLatestRow]:
        with self.db.session() as s:
            rows = list(s.scalars(select(BridgeLatestRow).where(BridgeLatestRow.app_id == app_id)
                                  .order_by(BridgeLatestRow.received_at.desc()).limit(limit)))
            for r in rows:
                s.expunge(r)
            return rows


def _problems(err: ValidationError) -> str:
    """Field names and error kinds only: a refusal never repeats a value the bridge sent."""
    return "; ".join(f"{'.'.join(str(x) for x in e['loc']) or 'event'}: {e['type']}" for e in err.errors()[:3])


class BridgeIntake:
    def __init__(self, gw, cfg: BridgeSettings, clock: Callable[[], datetime]):
        self.gw, self.cfg, self.clock = gw, cfg, clock
        self.repo = BridgeRepository(gw.db)
        self._lock = threading.Lock()
        self._live: dict[str, _Live] = {}
        self._hub = _Bucket(cfg.hub_events_per_second, cfg.hub_events_per_second, cfg.hub_events_per_second, self._now())

    def _now(self) -> float:
        return self.clock().timestamp()

    def _live_for(self, b: Bridge) -> _Live:
        live = self._live.get(b.app_id)
        if live is None or (live.bucket.rate, live.bucket.burst) != (b.rate, b.burst):
            bucket = _Bucket(b.rate, b.burst, float(b.burst), self._now())
            live = self._live[b.app_id] = _Live(bucket) if live is None else _Live(
                bucket, live.accepted, live.duplicates, live.rejected, live.throttled, live.rejects,
                live.last_event_at, live.last_reject_reason)
        return live

    def deny(self, p: Principal, what: str, reason: str, status: int = 403) -> ApiError:
        self.gw.events.publish_event("authz", "denied", {"attempted": what, "reason": reason},
                                     principal=p.as_dict(), severity="warning")
        return ApiError(status, "permission_denied", f"not allowed to {what}", reason=reason)

    # ---- reads ------------------------------------------------------------------------------
    def _reader(self, p: Principal, what: str) -> None:
        if p.kind != "person" or p.role not in ("owner", "adult"):
            raise self.deny(p, what, "people_only")

    def _status(self, app_id: str, b: Bridge) -> BridgeStatus:
        st = self.repo.state(app_id)
        app = self.gw.repo.get_app_state(app_id)
        with self._lock:
            live = self._live_for(b)
            cutoff = self._now() - REJECT_WINDOW_S
            recent = sum(1 for t in live.rejects if t > cutoff)
            counts = dict(accepted=live.accepted, duplicates=live.duplicates, rejected=live.rejected,
                          throttled=live.throttled, recent_rejects=recent, last_event_at=iso(live.last_event_at),
                          last_reject_reason=live.last_reject_reason)
        paused = st is not None and st.paused_at is not None
        state = "paused" if paused else ("active" if app and app.status == "installed" else "inactive")
        return BridgeStatus(
            id=app_id, app_status=app.status if app else None, state=state,
            provider=str(b.block.get("provider")), mode=str(b.block.get("mode")), data_class=b.data_class,
            emits=[{"kind": k, "name": n} for k, n in sorted(b.emits, key=str)], events_per_second=b.rate,
            burst=b.burst, max_event_bytes=b.max_event_bytes, paused_at=iso(utc(st.paused_at)) if paused else None,
            paused_reason=st.paused_reason if paused else None, entities=self.repo.count(app_id), **counts)

    def list_bridges(self, p: Principal) -> list[BridgeStatus]:
        self._reader(p, "read bridges")
        out = []
        for app_id, manifest in sorted(self.repo.installs().items()):
            b = bridge_from(app_id, manifest, self.cfg)
            if b is not None:
                out.append(self._status(app_id, b))
        return out

    def _bridge(self, app_id: str) -> Bridge:
        b = bridge_from(app_id, self.repo.install(app_id), self.cfg)
        if b is None:
            raise ApiError(404, "not_found", f"no approved bridge {app_id!r}")
        return b

    def get(self, p: Principal, app_id: str) -> BridgeStatus:
        self._reader(p, "read bridges")
        return self._status(app_id, self._bridge(app_id))

    def latest(self, p: Principal, app_id: str) -> list[LatestValue]:
        self._reader(p, "read bridge values")
        if not may_read(p, self._bridge(app_id).data_class):
            raise self.deny(p, f"read the values of bridge {app_id}", "data_class")
        return [LatestValue(kind=r.kind, name=r.name, id=r.entity, field=r.field, revision=r.revision,
                            received_at=iso(utc(r.received_at)), datapoint=r.datapoint) for r in self.repo.latest(app_id)]

    def resume(self, p: Principal, app_id: str) -> BridgeStatus:
        if not p.is_owner:
            raise self.deny(p, f"resume bridge {app_id}", "owner_only")
        b = self._bridge(app_id)
        self.repo.set_paused(app_id, None, None)
        with self._lock:
            self._live_for(b).rejects.clear()
        self.gw.events.publish_event("bridge", "resumed", {"app_id": app_id}, principal=p.as_dict(),
                                     resource={"kind": "app", "id": app_id})
        return self._status(app_id, b)

    # ---- intake -----------------------------------------------------------------------------
    def intake(self, p: Principal, identity, app_id: str, batch: IntakeBatch) -> IntakeResult:
        row = getattr(identity, "token", None)
        # Only an installation-owned plugin token for this very app (never a static or person token).
        if (p.kind != "plugin" or p.id != f"plugin:{app_id}" or row is None or row.kind != "plugin"
                or row.source != "app-install" or row.principal_id != p.id or GRANT not in (row.scopes or [])):
            raise self.deny(p, f"post events for bridge {app_id}", "not_this_bridge")
        b = bridge_from(app_id, self.repo.install(app_id), self.cfg)
        if b is None:
            raise self.deny(p, f"post events for bridge {app_id}", "no_approved_bridge")
        st = self.repo.state(app_id)
        if st is not None and st.paused_at is not None:
            raise ApiError(409, "conflict", f"bridge {app_id} is paused until an owner resumes it", reason="bridge_paused")
        if len(batch.events) > b.burst:
            raise ApiError(422, "conflict", f"a batch holds at most the bridge's burst ({b.burst}) events",
                           reason="batch_over_burst")
        now, n = self._now(), len(batch.events)
        with self._lock:
            live = self._live_for(b)
            wait = live.bucket.take(n, now)
            if wait == 0.0 and (hub_wait := self._hub.take(n, now)):
                live.bucket.tokens += n  # give the bridge its tokens back: the hub said no
                wait = hub_wait
            if wait:
                live.throttled += n
                raise ApiError(429, "rate_limited", f"bridge {app_id} is over its rate ({b.rate} events/s)",
                               reason="bridge_rate", retry_after_s=max(1, math.ceil(wait)))
        return self._take(b, batch.events)

    def _take(self, b: Bridge, raw_events: list[dict]) -> IntakeResult:
        reg = subjects.load()
        rejects: list[IntakeReject] = []
        chosen: dict[str, tuple[int, BridgeEvent]] = {}
        for i, raw in enumerate(raw_events):
            ev, why = self._check(b, reg, raw)
            if ev is None:
                rejects.append(IntakeReject(index=i, id=raw.get("id") if isinstance(raw.get("id"), str) else None,
                                            reason=why))
                continue
            key = f"{b.app_id}/{ev.kind}/{ev.name}/{ev.id}/{ev.field}"
            if key not in chosen or chosen[key][1].revision <= ev.revision:
                chosen[key] = (i, ev)  # latest-wins inside the batch: the highest revision, the later on a tie
        coalesced = len(raw_events) - len(rejects) - len(chosen)
        stored = self.repo.existing(list(chosen)) if chosen else {}
        room = MAX_ENTITIES - self.repo.count(b.app_id) if any(k not in stored for k in chosen) else MAX_ENTITIES
        accepted = duplicates = 0
        for key, (i, ev) in chosen.items():
            if key in stored and stored[key] >= ev.revision:
                duplicates += 1
                continue
            if key not in stored:
                if room <= 0:
                    rejects.append(IntakeReject(index=i, id=ev.id, reason=f"the bridge keeps at most {MAX_ENTITIES} entities"))
                    continue
                if ev.kind == "asset" and self.repo.asset_owner(b.app_id, ev.name, ev.id):
                    rejects.append(IntakeReject(index=i, id=ev.id, reason=f"asset {ev.name}/{ev.id} belongs to another source"))
                    continue
            if self._publish(b, key, ev):
                accepted += 1
                room -= key not in stored
            else:
                duplicates += 1
        return self._tally(b, accepted, duplicates + coalesced, sorted(rejects, key=lambda r: r.index))

    def _check(self, b: Bridge, reg, raw: object) -> tuple[BridgeEvent | None, str]:
        try:
            size = len(json.dumps(raw, separators=(",", ":"), allow_nan=False).encode())
        except (TypeError, ValueError):
            return None, "the event is not finite JSON"
        if size > b.max_event_bytes:
            return None, f"the event is {size} bytes; this bridge's limit is {b.max_event_bytes}"
        try:
            ev = BridgeEvent.model_validate(raw)
        except ValidationError as exc:
            return None, _problems(exc)
        if (ev.kind, ev.name) not in b.emits:
            return None, f"{ev.kind} {ev.name} is not one of this bridge's emits"
        if ev.kind == "asset" and ev.name == "robot":
            return None, "robot channels are reserved: no bridge publishes them"
        for subject in self._subjects(b, ev):
            verdict = reg.check(subject, "gateway")
            if not verdict.ok:
                return None, verdict.reason[:300]
            problems = reg.envelope_problems("onemind.datapoint/v1", self._datapoint(b, ev, subject))
            if problems:
                return None, "; ".join(problems[:3])[:300]
        return ev, ""

    @staticmethod
    def _subjects(b: Bridge, ev: BridgeEvent) -> list[str]:
        out = [f"onemind.plugin.{b.app_id}.in.{ev.kind}.{ev.name}"]
        if ev.kind == "asset":
            out.append(f"onemind.asset.{ev.name}.{ev.id}.{ev.field}")
        return out

    def _datapoint(self, b: Bridge, ev: BridgeEvent, subject: str) -> dict:
        dp = {"schema": "onemind.datapoint/v1", "nats_subject": subject, "time": iso(ev.time), "seq": ev.revision,
              "value": ev.value, "quality": ev.quality, "source": {"kind": "bridge", "id": b.app_id},
              "licence": b.licence()}
        dp |= {k: v for k, v in (("unit", ev.unit), ("position", ev.position)) if v is not None}
        return dp

    def _publish(self, b: Bridge, key: str, ev: BridgeEvent) -> bool:
        now, event_id = self.clock(), "evt_" + uuid.uuid4().hex
        intake, *core = self._subjects(b, ev)
        keep = b.provider.get("store") != "none"  # show-only terms: nothing is kept
        written = self.repo.upsert({
            "key": key, "app_id": b.app_id, "kind": ev.kind, "name": ev.name, "entity": ev.id, "field": ev.field,
            "revision": ev.revision, "event_id": event_id, "received_at": now,
            "datapoint": self._datapoint(b, ev, core[0] if core else intake) if keep else None})
        if not written:
            return False  # a newer revision landed meanwhile
        envelope = {"schema": "onemind.event/v1", "id": event_id, "type": f"bridge.{ev.kind}", "ts": iso(now),
                    "subject": {"app_id": b.app_id, "entity_id": ev.id, "field": ev.field}, "severity": "info",
                    "source_id": b.app_id, "dedupe_key": f"{key}@{ev.revision}", "observed_at": iso(ev.time),
                    "data": self._datapoint(b, ev, intake)}
        self._send(intake, envelope)
        for subject in core:
            dp = self._datapoint(b, ev, subject)
            self._send(subject, dp)
            if keep:
                self._send(f"$KV.{ASSET_KV_BUCKET}.{ev.name}.{ev.id}.{ev.field}", dp)
        return True

    def _send(self, subject: str, doc: dict) -> None:
        try:  # best effort: the stored latest value is the record; NATS down never fails the caller
            self.gw.bus.publish_threadsafe(subject, json.dumps(doc, separators=(",", ":")).encode())
        except Exception:  # noqa: BLE001
            pass

    def _tally(self, b: Bridge, accepted: int, duplicates: int, rejects: list[IntakeReject]) -> IntakeResult:
        now = self.clock()
        for r in rejects:
            self._send(f"onemind.plugin.{b.app_id}.reject", {
                "schema": "onemind.event/v1", "id": "evt_" + uuid.uuid4().hex, "type": "bridge.rejected",
                "ts": iso(now), "subject": {"app_id": b.app_id}, "severity": "warning", "source_id": b.app_id,
                "data": r.model_dump()})
        pause = None
        with self._lock:
            live = self._live_for(b)
            live.accepted += accepted
            live.duplicates += duplicates
            live.rejected += len(rejects)
            if accepted:
                live.last_event_at = now
            t = now.timestamp()
            while live.rejects and live.rejects[0] <= t - REJECT_WINDOW_S:
                live.rejects.popleft()
            for r in rejects:
                live.last_reject_reason = r.reason
                live.rejects.append(t)
            if len(live.rejects) >= REJECTS_TO_PAUSE:
                pause, live.rejects = live.last_reject_reason, deque()
        if pause is not None:
            self.repo.set_paused(b.app_id, now, pause[:300])
            self.gw.events.publish_event("bridge", "paused", {
                "app_id": b.app_id, "rejects": REJECTS_TO_PAUSE, "window_min": REJECT_WINDOW_S // 60,
                "reason": pause[:300]}, severity="warning", resource={"kind": "app", "id": b.app_id})
        return IntakeResult(accepted=accepted, duplicates=duplicates, rejected=rejects, paused=pause is not None)
