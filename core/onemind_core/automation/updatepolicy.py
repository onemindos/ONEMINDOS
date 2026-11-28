# SPDX-License-Identifier: Apache-2.0
"""Update policy knobs for apps (NMD-07, #132; docs/strategy/nomad-parity.md).

The owner's rules for unattended app updates, on top of the maintenance windows (#75) and the
F-6 standing approval (patch updates of verified apps inside a window, policies.py):

- **Cool-off** `cool_off_hours`: a release is not updated to until it has been out this long
  (`metadata.upstream.released_at` in the app's manifest). A release whose date is unknown waits
  for a person while a cool-off is set.
- **Same major only** `same_major_only`: a new major version is never offered for auto-update.
- **Back-off** `backoff_after_failures`: after this many failed (or reverted, or unknown) updates
  of one app in a row, auto-update of that app pauses until the owner resumes it.
- **Dry run** `GET /v1/update-policy/dry-run`: what would update in the next window, and why not.
- **AI schedule** `ai_schedule`: hours in which the box's AI apps (category `ai`) should be off
  to save power. This step stores and evaluates the schedule and lists the apps it covers; the
  stop and start requests at its edges are a follow-up, and they will wait for the owner like any
  other request (AI never actuates without human approval).

The knobs only ever hold an update back. They never approve one: that stays with the owner or a
standing approval they created. Settings are computed defaults until the owner changes them.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import nullcontext
from datetime import datetime, timedelta, tzinfo

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..auth import Principal
from ..errors import ApiError
from ..jsonbody import JsonBody
from ..ledger import Base, iso, utc
from ..store import FeatureSchema, SqlRepository
from .cron import WEEKDAYS, parse_ranges, resolve_tz, window_open
from .policies import update_kind

SCHEMA = FeatureSchema("updatepolicy")  # version 1 = the shape below

FAILED = frozenset({"failed", "outcome_unknown"})
SCAN_LIMIT = timedelta(days=8)  # a window or schedule repeats weekly; look a little past a week
AI_CATEGORY = "ai"


class UpdatePolicyRow(Base):
    """One row, id "global": the owner's knobs and the apps they resumed after a back-off."""

    __tablename__ = "update_policy"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    # JSON null means the policy uses defaults, independently of per-app resume state.
    doc: Mapped[dict | None] = mapped_column(JSON, nullable=False)
    resumed: Mapped[dict] = mapped_column(JSON, default=dict)  # app_id -> ISO time of the resume
    updated_by: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AiSchedule(JsonBody):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    tz: str = Field(default="box", max_length=64)
    off: list[dict] = Field(default_factory=lambda: [{"days": list(WEEKDAYS), "start": "23:00", "end": "07:00"}])

    def validate_timing(self, resolve_zone: Callable[[str], tzinfo] = resolve_tz) -> None:
        parse_ranges(self.off)
        resolve_zone(self.tz)


class UpdatePolicyBody(JsonBody):
    model_config = ConfigDict(extra="forbid")
    window_id: str = Field(default="win_nightly", max_length=40)
    cool_off_hours: int = Field(default=48, ge=0, le=720)
    same_major_only: bool = True
    backoff_after_failures: int = Field(default=3, ge=1, le=10)
    ai_schedule: AiSchedule = Field(default_factory=AiSchedule)


class ResumeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")


class UpdatePolicyRepository(SqlRepository):
    def get(self, *, session: Session | None = None) -> dict | None:
        with (self.db.session() if session is None else nullcontext(session)) as s:
            r = s.get(UpdatePolicyRow, "global")
            return None if r is None else {"doc": r.doc, "resumed": dict(r.resumed or {}),
                                           "updated_by": r.updated_by, "updated_at": utc(r.updated_at)}

    def put(self, *, now: datetime, session: Session | None = None, **values) -> None:
        values = {**values, "updated_at": now}
        with (self.db.session.begin() if session is None else nullcontext(session)) as s:
            s.execute(self.db.insert()(UpdatePolicyRow).values(id="global", **{"resumed": {}, **values})
                      .on_conflict_do_update(index_elements=[UpdatePolicyRow.id], set_=values))


def next_change(ranges: list, tz, after: datetime, want_open: bool) -> datetime | None:
    """The first whole minute after `after` at which the ranges are open (want_open) or closed."""
    parsed = parse_ranges(ranges)
    t = utc(after).replace(second=0, microsecond=0) + timedelta(minutes=1)
    end = t + SCAN_LIMIT
    while t < end:
        if window_open(parsed, tz, t) == want_open:
            return t
        t += timedelta(minutes=1)
    return None


def released_at(manifest: dict, version: object) -> datetime | None:
    """When the catalog's release came out (metadata.upstream.released_at), for that version only."""
    md = manifest.get("metadata") or {}
    upstream = md.get("upstream") if isinstance(md.get("upstream"), dict) else {}
    raw = upstream.get("released_at")
    if version is None or str(md.get("version")) != str(version) or not isinstance(raw, str):
        return None
    try:
        return utc(datetime.fromisoformat(raw.replace("Z", "+00:00")))
    except ValueError:
        return None


class UpdatePolicyService:
    def __init__(self, gw, automation):
        self.gw = gw
        self.automation = automation
        self.repo = UpdatePolicyRepository(gw.db)

    # ---- the stored knobs ----------------------------------------------------------------------
    def policy(self) -> UpdatePolicyBody:
        row = self.repo.get()
        return UpdatePolicyBody.model_validate(row["doc"]) if row and row["doc"] is not None else UpdatePolicyBody()

    def resumed_at(self, app_id: str) -> datetime | None:
        row = self.repo.get()
        raw = (row or {}).get("resumed", {}).get(app_id)
        return utc(datetime.fromisoformat(raw.replace("Z", "+00:00"))) if raw else None

    def to_json(self) -> dict:
        row = self.repo.get()
        body = self.policy()
        return {**body.model_dump(), "customized": row is not None and row["doc"] is not None,
                "updated_at": iso(row["updated_at"]) if row else None,
                "updated_by": row["updated_by"] if row else None,
                "paused_apps": self.paused_apps()}

    def _owner(self, principal: Principal, what: str) -> None:
        if not principal.is_owner:
            self.gw.audit.append("authz.denied", principal.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", f"{principal.kind}/{principal.role} may not {what}")

    def put(self, principal: Principal, body: UpdatePolicyBody) -> dict:
        self._owner(principal, "edit the update policy")
        if self.automation.repo.get_window(body.window_id) is None:
            raise ApiError(422, "conflict", f"no window {body.window_id!r}")
        try:
            body.ai_schedule.validate_timing(self.automation.tz)
        except ValueError as exc:
            raise ApiError(422, "conflict", f"ai_schedule: {exc}") from None
        self.repo.put(now=self.gw.clock(), doc=body.model_dump(), updated_by=principal.as_dict())
        self.gw.audit.append("update_policy.updated", principal.as_dict(), None, body.model_dump())
        return self.to_json()

    def resume(self, principal: Principal, app_id: str) -> dict:
        self._owner(principal, "resume auto-update")
        now = self.gw.clock()
        row = self.repo.get()
        resumed = {**(row["resumed"] if row else {}), app_id: iso(now)}
        doc = row["doc"] if row else UpdatePolicyBody().model_dump()
        self.repo.put(now=now, doc=doc, resumed=resumed, updated_by=principal.as_dict())
        self.gw.audit.append("update_policy.resumed", principal.as_dict(), None,
                             {"app_id": app_id, "failures": self.failures(app_id)})
        return self.to_json()

    # ---- the rules -----------------------------------------------------------------------------
    def failures(self, app_id: str) -> int:
        """Failed app.update requests of this app in a row, newest first, since its last success or resume."""
        since = self.resumed_at(app_id)
        n = 0
        for a in self.gw.repo.list({"succeeded", *FAILED}):  # newest first
            if a.type != "app.update" or a.params.get("app_id") != app_id:
                continue
            if since is not None and utc(a.created_at) <= since:
                break
            if a.state not in FAILED:
                break
            n += 1
        return n

    def paused_apps(self) -> list[dict]:
        limit = self.policy().backoff_after_failures
        out = []
        for app_id in sorted(self.gw.repo.list_app_states()):
            n = self.failures(app_id)
            if n >= limit:
                out.append({"app_id": app_id, "failures": n})
        return out

    def hold(self, app_id: str, from_version: object, to_version: object, at: datetime,
             policy: UpdatePolicyBody | None = None) -> tuple[str, datetime | None] | None:
        """Why the knobs hold this update back at `at` (reason, until), or None when they let it through."""
        p = policy or self.policy()
        if self.failures(app_id) >= p.backoff_after_failures:
            return "paused_after_failures", None
        if p.same_major_only and update_kind(from_version, to_version) == "major":
            return "major_update", None
        if p.cool_off_hours:
            app = self.gw.catalog.get(app_id)
            released = released_at(app.manifest, to_version) if app else None
            if released is None:
                return "release_time_unknown", None
            ready = released + timedelta(hours=p.cool_off_hours)
            if at < ready:
                return "cool_off", ready
        return None

    def gate(self, params: dict, at: datetime) -> str | None:
        """The standing-approval hook (PolicyService.update_gate): a held update waits for a person."""
        app_id = params.get("app_id")
        if not isinstance(app_id, str):
            return None
        held = self.hold(app_id, self.automation.policies.installed_version(app_id), params.get("to_version"), at)
        return held[0] if held else None

    # ---- what the owner sees -------------------------------------------------------------------
    def ai_state(self, at: datetime, p: UpdatePolicyBody | None = None) -> dict:
        s = (p or self.policy()).ai_schedule
        states = self.gw.repo.list_app_states()
        apps = []
        for app_id in sorted(states):
            app = self.gw.catalog.get(app_id)
            if app and (app.manifest.get("metadata") or {}).get("category") == AI_CATEGORY \
                    and states[app_id].status == "installed":
                apps.append(app_id)
        out = {"enabled": s.enabled, "off_now": False, "next_change_at": None, "apps": apps}
        if s.enabled:
            tz = self.automation.tz(s.tz)
            off = window_open(parse_ranges(s.off), tz, at)
            out["off_now"] = off
            out["next_change_at"] = iso(next_change(s.off, tz, at, not off))
        return out

    def dry_run(self) -> dict:
        """What would update in the next window, app by app, and why not. Files nothing."""
        now = self.gw.clock()
        p = self.policy()
        pol = self.automation.policies
        w = self.automation.repo.get_window(p.window_id)
        window = None
        at = now
        if w is not None:
            tz = self.automation.tz(w["tz"])
            open_now = window_open(parse_ranges(w["ranges"]), tz, now)
            nxt = now if open_now else next_change(w["ranges"], tz, now, True)
            at = nxt or now
            window = {"id": w["id"], "name": w["name"], "open_now": open_now, "next_open_at": iso(nxt)}
        paused = self.automation.paused()
        requester = {"id": "automation:update-policy", "kind": "automation"}
        items = []
        for app_id, state in sorted(self.gw.repo.list_app_states().items()):
            app = self.gw.catalog.get(app_id)
            if app is None or state.status != "installed":
                continue
            md = app.manifest.get("metadata") or {}
            target = str(md["version"]) if md.get("version") is not None else None
            current = pol.installed_version(app_id)
            if target is None or target == current:
                continue
            kind = update_kind(current, target)
            item = {"app_id": app_id, "name": md.get("name") or app_id, "from_version": current,
                    "to_version": target, "kind": kind, "released_at": iso(released_at(app.manifest, target)),
                    "outcome": "held", "reason": None, "until": None}
            held = self.hold(app_id, current, target, at, p)
            if kind is None:
                item["reason"] = "version_not_comparable"
            elif held:
                item["reason"], until = held
                item["until"] = iso(until)
            elif window is None:
                item["reason"] = "no_window"
            else:
                v = pol.evaluate("app.update", {"app_id": app_id, "to_version": target}, requester, at, paused=paused)
                item["outcome"] = "would_update" if v.outcome == "auto_approved" else "needs_approval"
                item["reason"] = v.reason
            items.append(item)
        return {"evaluated_at": iso(now), "at": iso(at), "window": window, "automation_paused": paused,
                "apps": items, "ai": self.ai_state(now, p)}
