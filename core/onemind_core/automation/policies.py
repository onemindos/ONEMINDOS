# SPDX-License-Identifier: Apache-2.0
"""Standing approvals (contract §12.17, docs/architecture/AUTOMATION.md §3.2, CORE-AUTO-3).

A standing approval is the owner's "yes, in advance" for a narrow set of requests:

    {"allow": {"types": ["app.remove"], "requested_by": ["automation:*"],
               "params": {"app_id": {"enum": ["whoami"]}}},
     "limits": {"per_day": 3}, "window_id": "win_nightly", "expires_at": "..."}

Hard limits, checked when it is created and again on every match:
- it covers only `read` and `write` requests (§12.3); a request whose parameters make it
  `sensitive` or `destructive` (e.g. `app.remove` with `delete_data`) is never covered, nor is
  `automation.rule.*` (registry.NEVER_BY_POLICY); actions.py checks the same again;
- it always expires, at most 90 days ahead;
- it covers an agent or a plugin only when it names it exactly (`agent:*` is refused);
- `per_day` is counted in the database over the last 24 hours, so a restart keeps the count;
- with a window, it approves only while the window is open;
- `app.update` (F-6) needs a window and matches only a patch update of a `verified` app whose
  scan passes.

Evaluation order is deterministic: kill switch, risk, then every live policy that matches, most
specific first (most constrained parameters, then oldest), and the first with room left wins.
An approval is recorded as `approved_by: policy:<id>@<revision>`, with the owner who created it.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from ..actions import StandingGrant
from ..audit import AuditLog
from ..auth import Principal
from ..catalog import Catalog
from ..errors import ApiError
from ..ledger import Action, iso, utc
from ..scan import scan_problem
from . import registry
from .cron import parse_ranges, resolve_tz, window_open
from .store import AutomationRepository, new_id

MAX_POLICY_DAYS = 90
WILDCARD_KINDS = ("automation", "person")
REQUESTER_RE = re.compile(r"^(automation|person|agent|plugin):([A-Za-z0-9][A-Za-z0-9_.:-]{0,79}|\*)$")
PARAM_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")


class Allow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    types: list[str] = Field(min_length=1, max_length=20)
    requested_by: list[str] = Field(min_length=1, max_length=20)
    params: dict[str, dict] = Field(default_factory=dict)


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    per_day: int = Field(ge=1, le=1000)


class PolicyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, max_length=120)
    allow: Allow
    limits: Limits
    window_id: str | None = Field(default=None, max_length=40)
    expires_at: AwareDatetime


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
        # F-6 needs the version an app runs now. Until the deployments stream reports it
        # (CORE-DEPLOY-3 revisions), nothing is known and app.update always waits for a person.
        self.installed_version = installed_version or (lambda _app_id: None)

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
        expired = utc(p["expires_at"]) <= now
        return {
            "id": p["id"], "revision": p["revision"], "name": p["name"], "allow": p["allow"],
            "limits": {"per_day": p["per_day"]}, "window_id": p["window_id"],
            "expires_at": iso(p["expires_at"]), "created_by": p["created_by"], "created_at": iso(p["created_at"]),
            "state": "expired" if p["state"] == "active" and expired else p["state"],
            "uses_24h": self.repo.count_uses(p["id"], now - timedelta(days=1)),
        }

    def validate(self, body: PolicyBody) -> None:
        now = self.clock()
        try:
            for t in body.allow.types:
                problem = registry.policy_may_cover(t)
                if problem:
                    raise ValueError(problem)
            if len(set(body.allow.types)) != len(body.allow.types):
                raise ValueError("allow.types lists a type twice")
            for r in body.allow.requested_by:
                m = REQUESTER_RE.match(r)
                if not m:
                    raise ValueError(f"requested_by entry {r!r} must be <kind>:<id> or automation:* / person:*")
                if m.group(2) == "*" and m.group(1) not in WILDCARD_KINDS:
                    raise ValueError(f"{r!r}: a standing approval covers an {m.group(1)} only when it names it exactly")
            for name, c in body.allow.params.items():
                _check_constraint(name, c)
            if "app.update" in body.allow.types and body.window_id is None:
                raise ValueError("app.update needs a window_id (F-6: patch updates inside the window)")
        except ValueError as exc:
            raise ApiError(422, "conflict", str(exc)) from None
        expires = utc(body.expires_at)
        if expires <= now:
            raise ApiError(422, "conflict", "expires_at must be in the future")
        if expires > now + timedelta(days=MAX_POLICY_DAYS):
            raise ApiError(422, "conflict", f"a standing approval expires at most {MAX_POLICY_DAYS} days ahead")
        if body.window_id is not None and self.repo.get_window(body.window_id) is None:
            raise ApiError(404, "not_found", f"no window {body.window_id!r}")

    def create(self, principal: Principal, body: PolicyBody) -> dict:
        if not principal.is_owner:
            self.audit.append("authz.denied", principal.as_dict(), None,
                              {"attempted": "create standing approval", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", f"{principal.kind}/{principal.role} may not create standing approvals")
        self.validate(body)
        now = self.clock()
        p = self.repo.add_policy(
            id=new_id("pol_"), name=body.name, allow=body.allow.model_dump(), per_day=body.limits.per_day,
            window_id=body.window_id, expires_at=utc(body.expires_at), created_by=principal.as_dict(),
            created_at=now,
        )
        # F-2 (passkey on owner approvals) is enforced by the identity stream's approval guard once
        # it lands; until then this is a token-authenticated owner write, recorded as such.
        self.audit.append("automation.policy.created", principal.as_dict(), None,
                          {"policy_id": p["id"], "revision": 1, "allow": p["allow"], "per_day": p["per_day"],
                           "window_id": p["window_id"], "expires_at": iso(p["expires_at"]), "approval": "token"})
        return self.to_json(p)

    def delete(self, principal: Principal, policy_id: str) -> None:
        if not principal.is_owner:
            self.audit.append("authz.denied", principal.as_dict(), None,
                              {"attempted": "delete standing approval", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", f"{principal.kind}/{principal.role} may not delete standing approvals")
        if not self.repo.delete_policy(policy_id):
            raise ApiError(404, "not_found", "no such standing approval")
        self.audit.append("automation.policy.deleted", principal.as_dict(), None, {"policy_id": policy_id})

    # ---- evaluation ----------------------------------------------------------------------------
    def _f6_problem(self, params: dict, at: datetime) -> str | None:
        app_id = params.get("app_id")
        app = self.catalog.get(app_id) if isinstance(app_id, str) else None
        if app is None:
            return "app_unknown"
        if (app.manifest.get("metadata") or {}).get("tier") != "verified":
            return "app_not_verified"
        if scan_problem(app.id, app.scan, at):
            return "scan_not_passing"
        if update_kind(self.installed_version(app.id), params.get("to_version")) != "patch":
            return "not_a_patch_update"
        return None

    def candidates(self, action_type: str, params: dict, requested_by: dict, at: datetime,
                   paused: bool) -> tuple[list[dict], str]:
        """Live policies that cover this request, most specific first, and why there are none."""
        if paused:
            return [], "automation_paused"
        if not registry.known(action_type):
            return [], "no_policy"
        if registry.policy_may_cover(action_type, params):
            return [], "never_by_policy"
        who = requester_key(requested_by)
        kind = who.split(":", 1)[0]
        matched, reason = [], "no_policy"
        for p in self.repo.list_policies():
            if utc(p["expires_at"]) <= at or action_type not in p["allow"]["types"]:
                continue
            req = p["allow"]["requested_by"]
            if who not in req and not (kind in WILDCARD_KINDS and f"{kind}:*" in req):
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
        matched, reason = self.candidates(action.type, action.params, action.requested_by, now, paused)
        over = None
        for p in matched:
            status, n = self.repo.reserve_use(p["id"], p["revision"], p["per_day"], action.id, now)
            if status == "ok":
                approver = f"policy:{p['id']}@{p['revision']}"
                return StandingGrant(
                    principal=Principal(id=approver, kind="policy", role="policy"),
                    audit={"approved_via": "policy", "approval": "policy", "policy_id": p["id"],
                           "policy_revision": p["revision"], "policy_created_by": p["created_by"].get("id"),
                           "uses": f"{n}/{p['per_day']}"},
                    release=lambda aid=action.id: self.repo.release_use(aid),
                )
            if status == "limit":
                over = over or (p, n)
        if over:
            self.audit.append("automation.policy.limit_reached", None, action.id,
                              {"policy_id": over[0]["id"], "uses": f"{over[1]}/{over[0]['per_day']}",
                               "reason": "limit_reached"})
        elif matched == [] and reason in ("outside_window", "automation_paused") and action.requested_by.get("kind") == "automation":
            self.audit.append("automation.policy.not_applied", None, action.id, {"reason": reason})
        return None
