# SPDX-License-Identifier: Apache-2.0
"""Standing approvals (contract §12.17, docs/architecture/AUTOMATION.md §3.2, CORE-AUTO-3).

A standing approval is the owner's "yes, in advance" for a narrow set of requests:

    {"allow": {"types": ["app.remove"], "requested_by": ["automation:update-policy"],
               "params": {"app_id": {"enum": ["whoami"]}}},
     "limits": {"per_day": 3}, "window_id": "win_nightly", "expires_at": "..."}

Hard limits, checked when it is created and again on every match:
- it covers only `read` and `write` requests (§12.3); a request whose parameters make it
  `sensitive` or `destructive` (e.g. `app.remove` with `delete_data`) is never covered, nor is
  `automation.rule.*` (registry.NEVER_BY_POLICY); actions.py checks the same again;
- it expires at most 180 days ahead (30, 90 or 180 on the sheet), or it is a *forever* rule: only for
  read and write types, never a floor item, never with accept_injection_risk (F-10, D-028);
- by default it ends itself after 14 days without a use (`lapse_unused_days`), and it may end after
  `max_uses` uses, or cap the bytes and items it writes per day;
- it can be narrowed at once and widened only with a fresh passkey; every edit is a new revision;
  a one-tap revoke needs no step-up;
- it is suspended (not deleted) when its agent's token is rotated, revoked or re-minted, the agent's
  identity changes or it becomes exposed, the owning person's role changes, or a request it names
  turns out riskier than the type's own class; one tap at L1 re-confirms it;
- it covers an agent or a plugin only when it names it exactly (`agent:*` is refused), and only the
  identity it was bound to when it was made: its permanent principal id (principals.py, PR 7). An
  agent whose token was revoked, an app reinstalled, or another holder of the same display id is
  not covered;
- `per_day` is counted in the database over the last 24 hours, so a restart keeps the count;
- with a window, it approves only while the window is open;
- `app.update` (F-6) needs a window and matches only a patch update of a `verified` app whose
  scan passes, and that the owner's update policy does not hold back (updatepolicy.py, #132).

Evaluation order is deterministic: kill switch, risk, then every live policy that matches, most
specific first (most constrained parameters, then oldest), and the first with room left wins.
An approval is recorded as `approved_by: policy:<id>@<revision>`, with the owner who created it.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
import posixpath
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from ..actions import StandingGrant
from ..audit import AuditLog
from ..auth import Principal
from ..catalog import Catalog
from ..errors import ApiError
from ..jsonbody import JsonBody
from ..ledger import Action, iso, utc
from ..principals import bound_kind
from ..scan import scan_problem
from . import registry
from .cron import parse_ranges, resolve_tz, window_open
from .store import AutomationRepository, new_id

MAX_POLICY_DAYS = 180  # D-028 / F-10: 30, 90 or 180 days, or forever (was 90)
FOREVER = datetime(9999, 12, 31, tzinfo=UTC)  # expires_at of a forever rule
DEFAULT_LAPSE_DAYS = 14  # "end if unused for 14 days", on by default (F-10)
REVIEW_EVERY = timedelta(days=90)  # "still want these rules that never end?" (design §3.6.2 item 5)
NOTIFY = ("each", "digest", "silent")
ENDED_STATES = ("deleted", "revoked", "lapsed", "ended")
# No new wildcard rule is accepted (gateway permissions PR 5, gap 18). Rules made before that keep a
# narrow reading: `person:*` covers only an owner or an adult, and `automation:*` only an automation
# an owner or adult wrote by hand (never one an agent proposed); legacy `automation:*` rules were
# also paused by migration until the owner confirms them.
WILDCARD_KINDS: tuple[str, ...] = ()
LEGACY_WILDCARD_KINDS = ("automation", "person")
WILDCARD_PERSON_ROLES = frozenset({"owner", "adult"})
SYSTEM_AUTOMATIONS = frozenset({"automation:update-policy"})
REQUESTER_RE = re.compile(r"^(automation|person|agent|plugin):([A-Za-z0-9][A-Za-z0-9_.:-]{0,79}|\*)$")
PARAM_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")


class Allow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    types: list[str] = Field(min_length=1, max_length=20)
    requested_by: list[str] = Field(min_length=1, max_length=20)
    params: dict[str, dict] = Field(default_factory=dict)


class Limits(JsonBody):
    model_config = ConfigDict(extra="forbid")
    per_day: int = Field(ge=1, le=1000)
    max_uses: int | None = Field(default=None, ge=1, le=100_000, description="total uses, then the rule ends itself; 1 = once more")
    bytes_per_day: int | None = Field(default=None, ge=1, le=1 << 34, description="bytes its uses may write in 24 hours")
    items_per_day: int | None = Field(default=None, ge=1, le=100_000, description="items its uses may write in 24 hours")


class LimitsPatch(JsonBody):
    """Limits to change; the ones left out keep their value (null clears an optional one)."""

    model_config = ConfigDict(extra="forbid")
    per_day: int | None = Field(default=None, ge=1, le=1000)
    max_uses: int | None = Field(default=None, ge=1, le=100_000)
    bytes_per_day: int | None = Field(default=None, ge=1, le=1 << 34)
    items_per_day: int | None = Field(default=None, ge=1, le=100_000)


class Target(BaseModel):
    """RFC 9396-shaped resource pattern: what the request's target must be (e.g. a Notes folder)."""

    model_config = ConfigDict(extra="forbid")
    type: str = Field(min_length=1, max_length=40)
    locations: list[str] = Field(min_length=1, max_length=20)


class PolicyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, max_length=120)
    allow: Allow
    limits: Limits
    window_id: str | None = Field(default=None, max_length=40)
    expires_at: AwareDatetime | None = Field(default=None, description="required unless forever is true; at most 180 days ahead")
    forever: bool = Field(default=False, description="no end date (read and write types only; never a floor item)")
    notify_after: Literal["each", "digest", "silent"] = "digest"
    lapse_unused_days: int | None = Field(default=DEFAULT_LAPSE_DAYS, ge=1, le=90,
                                          description="end after this many days without a use; null keeps it")
    target: Target | None = None
    accept_injection_risk: bool = Field(default=False, description="needs a proven key (L2, design PR 11): refused for now")


class PolicyPatch(BaseModel):
    """A new revision. Fields left out keep their value. Narrowing applies at once; widening needs a
    fresh passkey (the route asks); either way the revision goes up."""

    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, max_length=120)
    allow: Allow | None = None
    limits: LimitsPatch | None = None
    window_id: str | None = Field(default=None, max_length=40)
    expires_at: AwareDatetime | None = None
    forever: bool | None = None
    notify_after: Literal["each", "digest", "silent"] | None = None
    lapse_unused_days: int | None = Field(default=None, ge=1, le=90)
    target: Target | None = None
    revision: int | None = Field(default=None, ge=1, description="the revision you read; a newer one answers 409")


def requester_key(requested_by: dict) -> str:
    """`kind:id` for a requester; v0 file tokens carry a bare id (`owner`, `hermes`)."""
    kind, pid = str(requested_by.get("kind", "")), str(requested_by.get("id", ""))
    return pid if pid.startswith(kind + ":") else f"{kind}:{pid}"


def _check_constraint(name: str, c: dict) -> None:
    if not PARAM_NAME_RE.match(name):
        raise ValueError(f"allow.params: bad parameter name {name!r}")
    if not isinstance(c, dict) or not c or set(c) - {"const", "enum", "pattern", "min", "max"}:
        raise ValueError(f"allow.params.{name} takes const, enum, pattern, min or max")
    if "const" in c and not isinstance(c["const"], (str, int, float, bool)):
        raise ValueError(f"allow.params.{name}.const must be a scalar")
    if "enum" in c and (not isinstance(c["enum"], list) or not 1 <= len(c["enum"]) <= 100
                        or not all(isinstance(v, (str, int, float, bool)) for v in c["enum"])):
        raise ValueError(f"allow.params.{name}.enum must be 1 to 100 scalars")
    if "pattern" in c:
        if not isinstance(c["pattern"], str) or len(c["pattern"]) > 200:
            raise ValueError(f"allow.params.{name}.pattern must be a string of at most 200 characters")
        try:
            re.compile(c["pattern"])
        except re.error as exc:
            raise ValueError(f"allow.params.{name}.pattern: {exc}") from None
    for k in ("min", "max"):
        if k in c and (isinstance(c[k], bool) or not isinstance(c[k], (int, float))):
            raise ValueError(f"allow.params.{name}.{k} must be a number")


def _param_ok(value: object, c: dict) -> bool:
    if value is None:
        return False
    if "const" in c and value != c["const"]:
        return False
    if "enum" in c and value not in c["enum"]:
        return False
    if "pattern" in c and not (isinstance(value, str) and re.fullmatch(c["pattern"], value)):
        return False
    for k, ok in (("min", lambda v, b: v >= b), ("max", lambda v, b: v <= b)):
        if k in c and not (isinstance(value, (int, float)) and not isinstance(value, bool) and ok(value, c[k])):
            return False
    return True


def canonical_location(loc: str) -> str | None:
    """A target location normalised for matching, or None when it climbs out (`..`) or is empty."""
    if not isinstance(loc, str) or not loc or "\x00" in loc or "\\" in loc:
        return None
    head, sep, rest = loc.partition(":")
    path = rest if sep else loc
    norm = posixpath.normpath("/" + path)
    if ".." in path.split("/") or norm in ("/", ""):
        return None
    return (head + ":" if sep else "") + norm.lstrip("/")


def location_matches(pattern: str, loc: str) -> bool:
    """Glob match: `*` stays inside one folder, `**` crosses folders. Both sides canonical."""
    p, value = canonical_location(pattern), canonical_location(loc)
    if p is None or value is None:
        return False
    rx = "".join(".*" if part == "**" else "[^/]*" if part == "*" else re.escape(part)
                 for part in re.split(r"(\*\*|\*)", p))
    return re.fullmatch(rx, value) is not None


def update_kind(installed: object, target: object) -> str | None:
    """`patch`, `minor` or `major` between two release versions; None when either is unknown.

    A pre-release (`1.10.2-rc1`) on either side is never a patch update (F-6 covers releases only).
    """
    if not isinstance(installed, str) or not isinstance(target, str) or "-" in installed + target:
        return None
    a, b = SEMVER_RE.match(installed), SEMVER_RE.match(target)
    if not a or not b:
        return None
    x, y = tuple(map(int, a.groups())), tuple(map(int, b.groups()))
    if y <= x:
        return None
    return "patch" if x[:2] == y[:2] else "minor" if x[0] == y[0] else "major"


@dataclass
class Verdict:
    outcome: str  # auto_approved | needs_approval
    reason: str | None = None
    policy: dict | None = None
    uses: str | None = None  # "n/limit"
    extra: dict = field(default_factory=dict)

    @property
    def approver(self) -> str | None:
        return f"policy:{self.policy['id']}@{self.policy['revision']}" if self.policy else None

    def to_json(self) -> dict:
        out: dict = {"verdict": self.outcome}
        if self.reason:
            out["reason"] = self.reason
        if self.policy:
            out["policy"] = self.approver
        if self.uses:
            out["uses"] = self.uses
        return out


class PolicyService:
    def __init__(
        self,
        repo: AutomationRepository,
        audit: AuditLog,
        catalog: Catalog,
        clock: Callable[[], datetime],
        box_tz: str = "UTC",
        installed_version: Callable[[str], str | None] | None = None,
    ):
        self.repo = repo
        self.audit = audit
        self.catalog = catalog
        self.clock = clock
        self.box_tz = box_tz
        # F-6 needs the version an app runs now (app_runtime, recorded by app.install and
        # app.update). Unknown means app.update always waits for a person.
        self.installed_version = installed_version or (lambda _app_id: None)
        # NMD-07 (#132): the owner's update policy (cool-off, same major, back-off) may hold an
        # update back; fn(params, at) -> reason or None. It never approves anything.
        self.update_gate: Callable[[dict, datetime], str | None] = lambda _params, _at: None
        # Whether the gateway files requests of a type (ActionService.can_file); a rule that names
        # a type nothing files could never fire, so it is refused when made.
        self.can_file: Callable[[str], bool] = lambda _type: True
        # Who a legacy wildcard may cover: person id -> role (identity), unknown means not covered.
        self.person_role: Callable[[str], str | None] = lambda _pid: None
        # PR 7: the permanent ids of agents and plugins (principals.PrincipalRegistry), and the ids of
        # static-file principals. Without a registry no agent or plugin is ever covered (fails closed).
        self.principals = None
        self.file_ids: Callable[[], set[str]] = lambda: set()
        # PR 9: (type, params | None) -> the request's target ("notes", "vault:u/Agent Inbox/x.md"), or None
        # when the type names none; params None asks only whether the type can name one. And
        # (type, params) -> (bytes, items) one request writes, for the size caps. Set by the router.
        self.target_of: Callable[[str, dict | None], tuple[str, str] | None] = lambda _t, _p: None
        self.size_of: Callable[[str, dict], tuple[int, int]] = lambda _t, _p: (0, 1)
        # PR 10 (F-8): why nothing may be loosened yet (no owner passkey), or None. Creating, widening or
        # re-confirming a rule loosens.
        self.loosen_guard: Callable[[], str | None] = lambda: None

    def _check_loosen(self) -> None:
        why = self.loosen_guard()
        if why:
            raise ApiError(409, "conflict", "add a passkey first: no standing approval is made or widened before the "
                                            "owner has one (F-8)", reason=why)

    def _bindings(self, requested_by: list[str]) -> dict:
        """The permanent id each agent or plugin entry binds to; 422 when one names nobody yet."""
        out = {}
        for who in requested_by:
            if not bound_kind(who):
                continue
            found = self.principals.resolve(who, self.file_ids()) if self.principals is not None else None
            if found is None:
                raise ApiError(422, "conflict", f"{who!r} is not a principal this gateway knows: mint its token or "
                                                "install its app first, so the rule binds to that identity", reason="unknown_principal")
            out[who] = {"uid": found["uid"], "owner_user_id": found["owner_user_id"]}
        return out

    def _bound_ok(self, p: dict, who: str) -> bool:
        """Is the live identity of `who` the one this rule was bound to? Persons and automations need no binding."""
        if not bound_kind(who):
            return True
        want = (p.get("principals") or {}).get(who)
        live = self.principals.live(who) if self.principals is not None else None
        return bool(want and live and want.get("uid") == live["uid"])

    def adopt_unbound(self) -> int:
        """At start: bind rules made before PR 7 to the identity that holds each id now, so live rules
        keep working after the upgrade. An entry nobody holds stays unbound and never matches."""
        n = 0
        for p in self.repo.list_policies(with_paused=True):
            have = dict(p.get("principals") or {})
            missing = [w for w in p["allow"]["requested_by"] if bound_kind(w) and w not in have]
            if not missing or self.principals is None:
                continue
            for who in missing:
                found = self.principals.resolve(who, self.file_ids())
                if found is not None:
                    have[who] = {"uid": found["uid"], "owner_user_id": found["owner_user_id"]}
            if have != (p.get("principals") or {}):
                self.repo.bind_principals(p["id"], have)
                self.audit.append("approval.policy.bound", None, None,
                                  {"policy_id": p["id"], "principals": have, "reason": "upgrade"})
                n += 1
        return n

    def _wildcard_covers(self, kind: str, who: str) -> bool:
        """May a legacy `person:*` / `automation:*` entry cover this requester? Fails closed."""
        if kind == "person":
            return self.person_role(who.split(":", 1)[1]) in WILDCARD_PERSON_ROLES
        if kind == "automation":
            if who in SYSTEM_AUTOMATIONS:
                return True
            rule = self.repo.get_rule(who.split(":", 1)[1])
            if rule is None or rule.proposed_by:
                return False
            return rule.created_by.get("kind") == "person" and rule.created_by.get("role") in WILDCARD_PERSON_ROLES
        return False

    # ---- windows -------------------------------------------------------------------------------
    def window_is_open(self, window_id: str | None, at: datetime) -> bool:
        if window_id is None:
            return True
        w = self.repo.get_window(window_id)
        if w is None:
            return False
        return window_open(parse_ranges(w["ranges"]), resolve_tz(w["tz"], self.box_tz), at)

    # ---- create / list / delete ----------------------------------------------------------------
    def to_json(self, p: dict) -> dict:
        now = self.clock()
        forever = bool(p.get("forever"))
        expired = not forever and utc(p["expires_at"]) <= now
        state = "expired" if p["state"] == "active" and expired else p["state"]
        if state == "active" and p.get("suspended_at"):
            state = "suspended"
        return {
            "id": p["id"], "revision": p["revision"], "name": p["name"], "allow": p["allow"],
            "limits": {"per_day": p["per_day"], "max_uses": p.get("max_uses"), "bytes_per_day": p.get("bytes_per_day"),
                       "items_per_day": p.get("items_per_day")},
            "window_id": p["window_id"], "principals": p.get("principals") or {},
            "expires_at": None if forever else iso(p["expires_at"]), "forever": forever,
            "notify_after": p.get("notify_after") or "digest", "lapse_unused_days": p.get("lapse_unused_days"),
            "target": p.get("target"), "accept_injection_risk": bool(p.get("accept_injection_risk")),
            "created_from": p.get("created_from"),
            "created_by": p["created_by"], "created_at": iso(p["created_at"]),
            "state": state, "suspended_reason": p.get("suspended_reason") if state == "suspended" else None,
            "revoked_at": iso(p["revoked_at"]) if p.get("revoked_at") else None, "revoked_by": p.get("revoked_by"),
            "uses": p.get("uses") or 0, "last_used_at": iso(p["last_used_at"]) if p.get("last_used_at") else None,
            "uses_24h": self.repo.count_uses(p["id"], now - timedelta(days=1)),
            "review_due": forever and state == "active" and self._review_base(p) + REVIEW_EVERY <= now,
        }

    @staticmethod
    def _review_base(p: dict) -> datetime:
        return max(utc(p["created_at"]), utc(p["reviewed_at"]) if p.get("reviewed_at") else utc(p["created_at"]))

    def _floor_type(self, t: str) -> str | None:
        from ..permissions.floor import GRANTS_ACCESS, SMB_TYPES, radio_transmit

        if t in GRANTS_ACCESS or t in SMB_TYPES or radio_transmit(t):
            return f"{t} is a hard-floor item: a person approves it at the time, so no rule may name it"
        return None

    def validate(self, body: PolicyBody) -> None:
        now = self.clock()
        try:
            for t in body.allow.types:
                problem = registry.policy_may_cover(t) or self._floor_type(t)
                if problem:
                    raise ValueError(problem)
                if not self.can_file(t):
                    raise ValueError(f"{t} is not a request type this gateway files, so a standing approval could never fire")
            if len(set(body.allow.types)) != len(body.allow.types):
                raise ValueError("allow.types lists a type twice")
            for r in body.allow.requested_by:
                m = REQUESTER_RE.match(r)
                if not m:
                    raise ValueError(f"requested_by entry {r!r} must be <kind>:<id> or automation:* / person:*")
                if m.group(2) == "*":
                    raise ValueError(f"{r!r}: a standing approval covers an {m.group(1)} only when it names it exactly"
                                     " (wildcards are no longer accepted)")
            for name, c in body.allow.params.items():
                _check_constraint(name, c)
            if "app.update" in body.allow.types and body.window_id is None:
                raise ValueError("app.update needs a window_id (F-6: patch updates inside the window)")
            if body.accept_injection_risk:
                raise ValueError("accept_injection_risk needs a proven key (L2), which arrives with gateway "
                                 "permissions PR 11; it is refused until then")
            if body.notify_after == "silent" and any(registry.risk_of(t) != "read" for t in body.allow.types):
                raise ValueError("notify_after silent is for read-only (T0) rules only")
            if body.target is not None:
                if any(canonical_location(x) is None for x in body.target.locations):
                    raise ValueError("target.locations: every location must be a plain path (no '..')")
                missing = [t for t in body.allow.types if self.target_of(t, None) is None]
                if missing:
                    raise ValueError(f"{', '.join(missing)} cannot name a target, so a rule with a target would never fire")
        except ValueError as exc:
            raise ApiError(422, "conflict", str(exc)) from None
        if body.forever:
            if body.expires_at is not None:
                raise ApiError(422, "conflict", "a forever rule has no expires_at")
        else:
            if body.expires_at is None:
                raise ApiError(422, "conflict", "expires_at is required unless forever is true")
            expires = utc(body.expires_at)
            if expires <= now:
                raise ApiError(422, "conflict", "expires_at must be in the future")
            if expires > now + timedelta(days=MAX_POLICY_DAYS):
                raise ApiError(422, "conflict", f"a standing approval expires at most {MAX_POLICY_DAYS} days ahead, or is forever")
        if body.window_id is not None and self.repo.get_window(body.window_id) is None:
            raise ApiError(404, "not_found", f"no window {body.window_id!r}")

    def _owner_only(self, principal: Principal, what: str) -> None:
        if not principal.is_owner:
            self.audit.append("authz.denied", principal.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", f"{principal.kind}/{principal.role} may not {what}")

    def confirm(self, principal: Principal, policy_id: str) -> dict:
        """The owner re-enables a legacy rule that migration paused (it keeps its narrow reading)."""
        self._owner_only(principal, "confirm standing approvals")
        if not self.repo.confirm_policy(policy_id):
            raise ApiError(404, "not_found", "no paused standing approval with that id")
        self.audit.append("automation.policy.confirmed", principal.as_dict(), None, {"policy_id": policy_id})
        return self.to_json(self.repo.get_policy(policy_id))  # type: ignore[arg-type]

    @staticmethod
    def _columns(body: PolicyBody) -> dict:
        return {"name": body.name, "allow": body.allow.model_dump(), "per_day": body.limits.per_day,
                "max_uses": body.limits.max_uses, "bytes_per_day": body.limits.bytes_per_day,
                "items_per_day": body.limits.items_per_day, "window_id": body.window_id,
                "expires_at": FOREVER if body.forever else utc(body.expires_at), "forever": body.forever,
                "notify_after": body.notify_after, "lapse_unused_days": body.lapse_unused_days,
                "target": body.target.model_dump() if body.target else None,
                "accept_injection_risk": body.accept_injection_risk}

    def create(self, principal: Principal, body: PolicyBody, approval: str = "token", *,
               created_from: str | None = None) -> dict:
        self._owner_only(principal, "create standing approvals")
        self._check_loosen()
        self.validate(body)
        bindings = self._bindings(body.allow.requested_by)
        now = self.clock()
        p = self.repo.add_policy(id=new_id("pol_"), created_by=principal.as_dict(), created_at=now, principals=bindings,
                                 created_from=created_from, **self._columns(body))
        # F-2: the route has already required identity step-up (a fresh passkey once passkeys are
        # active); `approval` records how the owner proved presence. Only an owner reaches here.
        out = self.to_json(p)
        self.audit.append("automation.policy.created", principal.as_dict(), None,
                          {"policy_id": p["id"], "revision": 1, "allow": p["allow"], "per_day": p["per_day"],
                           "window_id": p["window_id"], "expires_at": out["expires_at"], "forever": out["forever"],
                           "limits": out["limits"], "notify_after": out["notify_after"],
                           "lapse_unused_days": out["lapse_unused_days"], "target": out["target"],
                           "approval": approval, "principals": bindings,
                           **({"created_from": created_from} if created_from else {})})
        return out

    def delete(self, principal: Principal, policy_id: str) -> None:
        self._owner_only(principal, "delete standing approvals")
        if not self.repo.delete_policy(policy_id):
            raise ApiError(404, "not_found", "no such standing approval")
        self.audit.append("automation.policy.deleted", principal.as_dict(), None, {"policy_id": policy_id})

    # ---- revisions, revoke, suspension (gateway permissions PR 9) ------------------------------
    def _get(self, policy_id: str) -> dict:
        p = self.repo.get_policy(policy_id)
        if p is None or p["state"] in ENDED_STATES:
            raise ApiError(404, "not_found", "no such standing approval")
        return p

    def _body_of(self, p: dict) -> PolicyBody:
        forever = bool(p.get("forever"))
        return PolicyBody(name=p["name"], allow=Allow(**p["allow"]),
                          limits=Limits(per_day=p["per_day"], max_uses=p.get("max_uses"), bytes_per_day=p.get("bytes_per_day"),
                                        items_per_day=p.get("items_per_day")),
                          window_id=p["window_id"], expires_at=None if forever else utc(p["expires_at"]), forever=forever,
                          notify_after=p.get("notify_after") or "digest", lapse_unused_days=p.get("lapse_unused_days"),
                          target=Target(**p["target"]) if p.get("target") else None)

    def _merged(self, p: dict, patch: PolicyPatch) -> PolicyBody:
        old = self._body_of(p).model_dump()
        sent = patch.model_dump(exclude_unset=True)
        sent.pop("revision", None)
        if "limits" in sent:
            sent["limits"] = {**old["limits"], **(sent["limits"] or {})}
            if sent["limits"].get("per_day") is None:
                raise ApiError(422, "conflict", "limits.per_day cannot be cleared")
        if sent.get("forever") is False and "expires_at" not in sent:
            raise ApiError(422, "conflict", "ending a forever rule's forever needs an expires_at")
        if sent.get("forever"):
            sent["expires_at"] = None
        elif sent.get("expires_at") is not None:
            sent["forever"] = False
        return PolicyBody.model_validate({**old, **sent})

    @staticmethod
    def classify(old: PolicyBody, new: PolicyBody) -> tuple[str, list[str]]:
        """("narrow" | "widen", changed fields). Anything that could approve more is a widening."""
        changed, wider = [], False

        def note(field: str, widens: bool) -> None:
            nonlocal wider
            changed.append(field)
            wider = wider or widens

        if new.name != old.name:
            note("name", False)
        if new.allow.types != old.allow.types:
            note("allow.types", not set(new.allow.types) <= set(old.allow.types))
        if new.allow.requested_by != old.allow.requested_by:
            note("allow.requested_by", not set(new.allow.requested_by) <= set(old.allow.requested_by))
        if new.allow.params != old.allow.params:
            kept = all(new.allow.params.get(k) == c for k, c in old.allow.params.items())
            note("allow.params", not kept)
        for k in ("per_day", "max_uses", "bytes_per_day", "items_per_day"):
            a, b = getattr(old.limits, k), getattr(new.limits, k)
            if a != b:
                note(f"limits.{k}", b is None or (a is not None and b > a))
        if new.window_id != old.window_id:
            note("window_id", old.window_id is not None)
        if (new.forever, new.expires_at) != (old.forever, old.expires_at):
            longer = new.forever or (not old.forever and utc(new.expires_at) > utc(old.expires_at))
            note("expires_at", longer)
        if new.notify_after != old.notify_after:
            note("notify_after", NOTIFY.index(new.notify_after) > NOTIFY.index(old.notify_after))
        if new.lapse_unused_days != old.lapse_unused_days:
            a, b = old.lapse_unused_days, new.lapse_unused_days
            note("lapse_unused_days", b is None or (a is not None and b > a))
        if new.target != old.target:
            if old.target is None:
                widens = False  # adding a target narrows
            elif new.target is None:
                widens = True
            else:
                widens = new.target.type != old.target.type or not set(new.target.locations) <= set(old.target.locations)
            note("target", widens)
        return ("widen" if wider else "narrow"), changed

    def plan_revision(self, policy_id: str, patch: PolicyPatch) -> tuple[str, list[str]]:
        p = self._get(policy_id)
        return self.classify(self._body_of(p), self._merged(p, patch))

    def revise(self, principal: Principal, policy_id: str, patch: PolicyPatch, approval: str | None) -> dict:
        """PATCH: a new revision. The route has asked for a passkey when this widens."""
        self._owner_only(principal, "edit standing approvals")
        p = self._get(policy_id)
        if patch.revision is not None and patch.revision != p["revision"]:
            raise ApiError(409, "conflict", f"the rule is at revision {p['revision']} now; read it again")
        old, new = self._body_of(p), self._merged(p, patch)
        direction, changed = self.classify(old, new)
        if not changed:
            return self.to_json(p)
        if direction == "widen":
            self._check_loosen()
        if direction == "widen" and approval is None:
            raise ApiError(401, "unauthenticated", "widening a standing approval needs a fresh passkey", reason="step_up_required")
        self.validate(new)
        cols = self._columns(new)
        cols["principals"] = {**(p.get("principals") or {}), **self._bindings(
            [w for w in new.allow.requested_by if w not in (p.get("principals") or {})])}
        cols["principals"] = {k: v for k, v in cols["principals"].items() if k in new.allow.requested_by}
        if not self.repo.set_policy(policy_id, expect_revision=p["revision"], **cols):
            raise ApiError(409, "conflict", "the rule changed meanwhile; read it again")
        out = self.to_json(self.repo.get_policy(policy_id))  # type: ignore[arg-type]
        self.audit.append("approval.policy.revised", principal.as_dict(), None,
                          {"policy_id": policy_id, "revision": out["revision"], "direction": direction,
                           "changed": changed, "approval": approval or "none (narrowing)"})
        return out

    def may_revoke(self, principal: Principal, p: dict, owned: set[str]) -> bool:
        """Revoking only narrows: the owner, or the person who owns every agent the rule names."""
        if principal.is_owner:
            return True
        names = set(p["allow"]["requested_by"])
        return principal.kind == "person" and bool(names) and names <= owned

    def revoke(self, principal: Principal, policy_id: str, owned: set[str] = frozenset()) -> dict:
        p = self._get(policy_id)
        if not self.may_revoke(principal, p, set(owned)):
            self._owner_only(principal, "revoke this standing approval")
        now = self.clock()
        # One UPDATE sets the state and bumps the revision, so reserve_use can never take a use after it.
        if not self.repo.set_policy(policy_id, states=("active", "paused"), state="revoked", revoked_at=now,
                                    revoked_by=principal.as_dict()):
            raise ApiError(404, "not_found", "no such standing approval")
        self.audit.append("approval.policy.revoked", principal.as_dict(), None, {"policy_id": policy_id})
        return self.to_json(self.repo.get_policy(policy_id))  # type: ignore[arg-type]

    def revoke_all(self, principal: Principal, name: str | None, owned: set[str] = frozenset()) -> list[str]:
        if name is None:
            self._owner_only(principal, "revoke every standing approval")
        done = []
        for p in self.repo.list_policies(with_paused=True):
            if name is None or name in p["allow"]["requested_by"]:
                if self.may_revoke(principal, p, set(owned)) or (name is not None and principal.is_owner):
                    self.revoke(principal, p["id"], owned)
                    done.append(p["id"])
        return done

    def suspend_for(self, name: str, reason: str) -> list[str]:
        """Suspend every live rule that names `name` (its identity or credential changed). Not a revoke:
        the rule keeps its id, history and use count, and one tap re-confirms it."""
        hit = []
        for p in self.repo.list_policies():
            if name in p["allow"]["requested_by"] and not p.get("suspended_at"):
                if self.repo.set_policy(p["id"], states=("active",), suspended_at=self.clock(), suspended_reason=reason[:80]):
                    hit.append(p["id"])
                    self.audit.append("approval.policy.suspended", None, None,
                                      {"policy_id": p["id"], "principal": name, "reason": reason[:80]})
        return hit

    def reconfirm(self, principal: Principal, policy_id: str, approval: str) -> dict:
        """One tap (L1): the approver accepts what changed; the rule binds to the identity live now."""
        self._owner_only(principal, "re-confirm standing approvals")
        self._check_loosen()
        p = self._get(policy_id)
        if not p.get("suspended_at"):
            raise ApiError(409, "conflict", "this rule is not suspended")
        bindings = self._bindings(p["allow"]["requested_by"])
        if not self.repo.set_policy(policy_id, states=("active",), suspended_at=None, suspended_reason=None,
                                    principals=bindings, reviewed_at=self.clock()):
            raise ApiError(409, "conflict", "the rule changed meanwhile; read it again")
        self.audit.append("approval.policy.reconfirmed", principal.as_dict(), None,
                          {"policy_id": policy_id, "was": p.get("suspended_reason"), "principals": bindings,
                           "approval": approval})
        return self.to_json(self.repo.get_policy(policy_id))  # type: ignore[arg-type]

    def keep(self, principal: Principal, policy_id: str) -> dict:
        """The 90-day review of a forever rule: keep it (End is revoke)."""
        self._owner_only(principal, "review standing approvals")
        p = self._get(policy_id)
        self.repo.set_policy(policy_id, bump=False, states=("active",), reviewed_at=self.clock(), review_notified_at=None)
        self.audit.append("approval.policy.kept", principal.as_dict(), None, {"policy_id": policy_id, "forever": bool(p.get("forever"))})
        return self.to_json(self.repo.get_policy(policy_id))  # type: ignore[arg-type]

    def _lapse_due(self, p: dict, at: datetime) -> bool:
        days = p.get("lapse_unused_days")
        if not days:
            return False
        base = max(t for t in (utc(p["created_at"]), utc(p["last_used_at"]) if p.get("last_used_at") else None,
                               utc(p["reviewed_at"]) if p.get("reviewed_at") else None) if t is not None)
        return at - base >= timedelta(days=days)

    def lapse_due(self, at: datetime) -> list[str]:
        """End every rule unused for its lapse period (audited once, as approval.policy.lapsed)."""
        out = []
        for p in self.repo.list_policies(with_paused=True):
            if self._lapse_due(p, at) and self.repo.set_policy(p["id"], states=("active", "paused"), state="lapsed"):
                out.append(p["id"])
                self.audit.append("approval.policy.lapsed", None, None,
                                  {"policy_id": p["id"], "unused_days": p["lapse_unused_days"]})
        return out

    def review_tick(self, at: datetime) -> list[str]:
        """Every 90 days, remind the owner of each forever rule (approval.policy.review_due). Ignoring the
        reminder ends nothing: that is what forever means; the rule shows review_due until kept or revoked."""
        self.lapse_due(at)
        due = []
        for p in self.repo.list_policies():
            if not p.get("forever") or self._review_base(p) + REVIEW_EVERY > at:
                continue
            if p.get("review_notified_at") and utc(p["review_notified_at"]) >= self._review_base(p) + REVIEW_EVERY:
                continue
            self.repo.set_policy(p["id"], bump=False, states=("active",), review_notified_at=at)
            due.append(p["id"])
        if due:
            self.audit.append("approval.policy.review_due", None, None, {"policy_ids": due, "count": len(due)})
        return due

    # ---- evaluation ----------------------------------------------------------------------------
    def _f6_problem(self, params: dict, at: datetime) -> str | None:
        app_id = params.get("app_id")
        app = self.catalog.get(app_id) if isinstance(app_id, str) else None
        if app is None:
            return "app_unknown"
        if app.manifest_tier != "verified":
            return "app_not_verified"
        if scan_problem(app.id, app.scan, at):
            return "scan_not_passing"
        if update_kind(self.installed_version(app.id), params.get("to_version")) != "patch":
            return "not_a_patch_update"
        return self.update_gate(params, at)

    def candidates(self, action_type: str, params: dict, requested_by: dict, at: datetime,
                   paused: bool, stored_risk: object = registry._UNSET) -> tuple[list[dict], str]:
        """Live policies that cover this request, most specific first, and why there are none."""
        if paused:
            return [], "automation_paused"
        if not registry.known(action_type):
            return [], "no_policy"
        who = requester_key(requested_by)
        if registry.policy_may_cover(action_type, params, stored_risk):
            if stored_risk is not registry._UNSET and registry.policy_may_cover(action_type) is None:
                # PR 9: this request is riskier than its type's own class (fix 2 refuses it); make that
                # visible by suspending the rules that name this requester and type.
                self._suspend_risk_raised(who, action_type)
            return [], "never_by_policy"
        kind = who.split(":", 1)[0]
        matched, reason = [], "no_policy"
        target = None
        for p in self.repo.list_policies():
            if utc(p["expires_at"]) <= at or action_type not in p["allow"]["types"]:
                continue
            if p.get("suspended_at"):
                reason = "rule_suspended"
                continue
            if self._lapse_due(p, at):
                reason = "rule_lapsed"
                continue
            if p.get("target"):
                target = target or self.target_of(action_type, params) or ("", "")
                t = p["target"]
                if target[0] != t["type"] or not any(location_matches(x, target[1]) for x in t["locations"]):
                    reason = "outside_target"
                    continue
            req = p["allow"]["requested_by"]
            if who not in req and not (kind in LEGACY_WILDCARD_KINDS and f"{kind}:*" in req
                                       and self._wildcard_covers(kind, who)):
                continue
            if not self._bound_ok(p, who):
                reason = "principal_changed"
                continue
            if not all(_param_ok(params.get(k), c) for k, c in p["allow"]["params"].items()):
                continue
            if action_type == "app.update":
                problem = self._f6_problem(params, at)
                if problem:
                    reason = problem
                    continue
            if not self.window_is_open(p["window_id"], at):
                reason = "outside_window"
                continue
            matched.append(p)
        matched.sort(key=lambda p: (-len(p["allow"]["params"]), utc(p["created_at"]), p["id"]))
        return matched, reason

    def _suspend_risk_raised(self, who: str, action_type: str) -> None:
        for p in self.repo.list_policies():
            if who in p["allow"]["requested_by"] and action_type in p["allow"]["types"] and not p.get("suspended_at"):
                if self.repo.set_policy(p["id"], states=("active",), suspended_at=self.clock(), suspended_reason="risk_raised"):
                    self.audit.append("approval.policy.suspended", None, None,
                                      {"policy_id": p["id"], "principal": who, "reason": "risk_raised", "type": action_type})

    def evaluate(self, action_type: str, params: dict, requested_by: dict, at: datetime, *,
                 paused: bool, extra_uses: dict[str, list[datetime]] | None = None) -> Verdict:
        """What would happen to this request at `at`, without taking a use (dry runs, POST /v1/plans)."""
        matched, reason = self.candidates(action_type, params, requested_by, at, paused)
        over = None
        for p in matched:
            n = self.repo.count_uses(p["id"], at - timedelta(days=1))
            n += sum(1 for t in (extra_uses or {}).get(p["id"], []) if t > at - timedelta(days=1))
            if n < p["per_day"]:
                return Verdict("auto_approved", policy=p, uses=f"{n + 1}/{p['per_day']}")
            over = over or (p, n)
        if over:
            return Verdict("needs_approval", "limit_reached", policy=None, uses=f"{over[1]}/{over[0]['per_day']}",
                           extra={"policy_id": over[0]["id"]})
        return Verdict("needs_approval", reason)

    def decide(self, action: Action, paused: bool) -> StandingGrant | None:
        """The ActionService hook: reserve a use of the first matching policy with room left."""
        now = self.clock()
        matched, reason = self.candidates(action.type, action.params, action.requested_by, now, paused, action.risk)
        over = None
        for p in matched:
            size, items = self.size_of(action.type, action.params)
            status, n = self.repo.reserve_use(p["id"], p["revision"], p["per_day"], action.id, now,
                                              max_uses=p.get("max_uses"), size=size, items=items,
                                              bytes_per_day=p.get("bytes_per_day"), items_per_day=p.get("items_per_day"))
            if status == "ok":
                approver = f"policy:{p['id']}@{p['revision']}"
                return StandingGrant(
                    principal=Principal(id=approver, kind="policy", role="policy"),
                    audit={"approved_via": "policy", "approval": "policy", "policy_id": p["id"],
                           "policy_revision": p["revision"], "policy_created_by": p["created_by"].get("id"),
                           "uses": f"{n}/{p['per_day']}", "notify_after": p.get("notify_after") or "digest",
                           **({"forever": True} if p.get("forever") else {})},
                    release=lambda aid=action.id: self.repo.release_use(aid),
                )
            if status == "limit":
                over = over or (p, n)
            elif status == "cap":
                self.audit.append("automation.policy.limit_reached", None, action.id,
                                  {"policy_id": p["id"], "reason": "cap_reached", "max_uses": p.get("max_uses"),
                                   "bytes_per_day": p.get("bytes_per_day"), "items_per_day": p.get("items_per_day")})
        if over:
            self.audit.append("automation.policy.limit_reached", None, action.id,
                              {"policy_id": over[0]["id"], "uses": f"{over[1]}/{over[0]['per_day']}",
                               "reason": "limit_reached"})
        elif matched == [] and reason in ("outside_window", "automation_paused") and action.requested_by.get("kind") == "automation":
            self.audit.append("automation.policy.not_applied", None, action.id, {"reason": reason})
        return None
