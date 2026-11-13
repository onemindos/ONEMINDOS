"""Action service: request -> owner approval -> dispatch, with every decision audited.

This is where "AI never actuates without human approval" is enforced:
- owners and agents may *request* an action (it lands in awaiting_approval);
- only a person with role owner may approve or deny; an agent always gets 403 permission_denied;
- nothing reaches the executor until an approval has moved the action to accepted;
- a standing approval the owner set in advance (§12.17, automation/policies.py) may accept a
  matching read or write request; it is recorded as approved_by policy:<id>@<revision>;
- an app.install is approved only for an app with a passing scan newer than 7 days (§10.3);
- an app that declares spec.agent gets its own agent principal at install, revoked at removal
  (§11.2), so the AI inside it can request actions but, like every agent, never approve them;
- a feature module may own further action types of contract §12.5 (FeatureAction, for example
  backup.run and backup.restore): they go through the same ledger, the same owner-only approval
  and the same audit lines; only what runs after approval is the feature's;
- a feature may prepare an app install before the executor runs (install_hooks, for example the
  app's database and its Secret); a hook that fails fails the install before anything is applied.
"""

from __future__ import annotations

import inspect
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from .audit import AuditLog
from .auth import Principal, new_agent_token, token_hash
from .catalog import APP_ID_RE, AppEntry, Catalog
from .errors import ApiError
from .executors import AgentSecret, ExecResult, Executor
from . import lifecycle as lc
from .scan import scan_problem
from .ledger import Action, ActionRepository, iso, new_action_id, utc

log = logging.getLogger("onemind.actions")

ActionType = Literal[
    "app.install", "app.remove", "app.start", "app.stop", "app.restart", "app.update", "app.configure",
    "app.delete_data",
]

# Per action type: (app status while it runs, app statuses it may start from, may the app have no
# state row at all). The same table drives the request-time check and the atomic claim at approval.
# It is derived from lifecycle.TYPES, which also holds the end state and the risk class.
APP_CLAIMS: dict[str, tuple[str, frozenset[str], bool]] = {
    t: (spec.claim, spec.allowed, spec.allow_absent) for t, spec in lc.TYPES.items()
}


class ActionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_id: str = Field(min_length=1, max_length=59, pattern=APP_ID_RE.pattern)
    # app.configure: plain settings, never secrets (those go through the sealed path).
    settings: dict[str, str] | None = Field(default=None, max_length=50)
    # app.delete_data: the app id typed again by the owner. Deleting data is never one click.
    confirm: str | None = Field(default=None, max_length=59)


def check_params_fit(action_type: str, p: ActionParams) -> None:
    if action_type == "app.configure":
        if not p.settings:
            raise ValueError("app.configure needs params.settings")
        problem = lc.settings_problem(p.settings)
        if problem:
            raise ValueError(problem)
    elif p.settings is not None:
        raise ValueError(f"params.settings is only for app.configure, not {action_type}")
    if action_type == "app.delete_data":
        if p.confirm != p.app_id:
            raise ValueError("app.delete_data needs params.confirm equal to the app id, typed by the owner")
    elif p.confirm is not None:
        raise ValueError("params.confirm is only for app.delete_data")


def _expiry_in_range(v: datetime) -> datetime:
    # 9999-12-31T23:59:59-23:59 is a valid RFC 3339 time whose UTC instant is past year 9999:
    # converting it raised OverflowError, an unaudited 500 (finding F-API-1). Refuse it here.
    try:
        v.astimezone(UTC)
    except OverflowError:
        raise ValueError("expires_at is outside the supported date range") from None
    return v


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: ActionType
    params: ActionParams
    idempotency_key: str = Field(min_length=1, max_length=200)
    expires_at: AwareDatetime
    # Contract §12.4: the fingerprint of the plan the requester looked at. If the plan the gateway
    # renders now differs, the request is refused (409 stale_precondition, reason plan_changed).
    plan_sha256: str | None = Field(default=None, max_length=80)

    @field_validator("expires_at")
    @classmethod
    def _expires_in_range(cls, v: datetime) -> datetime:
        return _expiry_in_range(v)

    @model_validator(mode="after")
    def _params_fit_type(self):
        check_params_fit(self.type, self.params)
        return self


class PlanRequest(BaseModel):
    """POST /v1/plans (contract §12.4): the same type and params as a request, nothing is filed."""

    model_config = ConfigDict(extra="forbid")
    type: ActionType
    params: ActionParams

    @model_validator(mode="after")
    def _params_fit_type(self):
        check_params_fit(self.type, self.params)
        return self


# ---- what the API publishes -------------------------------------------------------------------
# ActionRequest / PlanRequest above are what the service works with. The published schema is
# stricter: it is one variant per kind of params, tied to `type`, so a client generated from
# /openapi.json cannot build a request the server refuses (settings only on app.configure,
# confirm only on app.delete_data). The routers accept these and hand the service the plain model.
class PlainActionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_id: str = Field(min_length=1, max_length=59, pattern=APP_ID_RE.pattern)


class ConfigureActionParams(PlainActionParams):
    # plain settings, never secrets (those go through the sealed path)
    settings: dict[str, str] = Field(min_length=1, max_length=50)


class DeleteDataActionParams(PlainActionParams):
    # the app id typed again by the owner (check_params_fit enforces the equality)
    confirm: str = Field(min_length=1, max_length=59)


def _fits(model) -> None:
    """The same checks as ActionRequest, run while the request body is validated (so a failure is a 422)."""
    check_params_fit(model.type, ActionParams.model_validate(model.params.model_dump()))


_PLAIN_TYPES = Literal["app.install", "app.remove", "app.start", "app.stop", "app.restart", "app.update"]


class _ActionRequestFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=200)
    expires_at: AwareDatetime
    plan_sha256: str | None = Field(default=None, max_length=80)

    @field_validator("expires_at")
    @classmethod
    def _expires_in_range(cls, v: datetime) -> datetime:
        return _expiry_in_range(v)


class PlainActionRequest(_ActionRequestFields):
    type: _PLAIN_TYPES
    params: PlainActionParams

    @model_validator(mode="after")
    def _params_fit_type(self):
        _fits(self)
        return self


class ConfigureActionRequest(_ActionRequestFields):
    type: Literal["app.configure"]
    params: ConfigureActionParams

    @model_validator(mode="after")
    def _params_fit_type(self):
        _fits(self)
        return self


class DeleteDataActionRequest(_ActionRequestFields):
    type: Literal["app.delete_data"]
    params: DeleteDataActionParams

    @model_validator(mode="after")
    def _params_fit_type(self):
        _fits(self)
        return self


ActionRequestBody = Annotated[
    PlainActionRequest | ConfigureActionRequest | DeleteDataActionRequest, Field(discriminator="type")
]


class PlainPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: _PLAIN_TYPES
    params: PlainActionParams

    @model_validator(mode="after")
    def _params_fit_type(self):
        _fits(self)
        return self


class ConfigurePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["app.configure"]
    params: ConfigureActionParams

    @model_validator(mode="after")
    def _params_fit_type(self):
        _fits(self)
        return self


class DeleteDataPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["app.delete_data"]
    params: DeleteDataActionParams

    @model_validator(mode="after")
    def _params_fit_type(self):
        _fits(self)
        return self


PlanRequestBody = Annotated[PlainPlanRequest | ConfigurePlanRequest | DeleteDataPlanRequest, Field(discriminator="type")]


def _never_by_policy(a: Action) -> bool:
    """True unless the §12.3 risk class of this request lets a standing approval accept it."""
    from .automation import registry  # imported late: the registry imports ActionType from here

    return registry.policy_may_cover(a.type, a.params) is not None


@dataclass(frozen=True)
class StandingGrant:
    """A standing approval (contract §12.17) covering one request; built by the automation module."""

    principal: Principal  # kind "policy", id "policy:<id>@<revision>"
    audit: dict  # added to the approval's audit lines (approved_via, policy, uses, created_by)
    release: Callable[[], None]  # gives the reserved use back when the approval does not go through


@dataclass(frozen=True)
class FeatureAction:
    """An action type owned by a feature module (contract §12.5), registered with register_type.

    risk:        the §12.3 risk class (recorded in the audit; v0 has no standing approvals, so
                 every class waits for an owner).
    requesters:  principal kinds that may request it; owners always may, agents only if listed.
    check:       called again at approval with the stored action; a returned problem keeps the
                 action awaiting_approval and answers 409 stale_precondition.
    run:         the work after approval. It gets the action and a finish(ExecResult) callback and
                 may call finish later from another thread; until then the action is dispatched.
    claim:       reserves what the action changes (a compare-and-swap in the feature's own tables)
                 at approval, before the action is accepted, so two approved actions never run on
                 the same thing. A returned problem answers 409 stale_precondition.
    release:     gives the claim (and anything else held for the action, e.g. in-memory
                 credentials) back when the action ends or is denied, expires or is not accepted
                 after all. Runs at most once per ending and never fails the caller.
    background:  run() is started on a worker thread (a copy may take hours) instead of inline;
                 a crash there becomes outcome_unknown.
    """

    risk: str
    run: Callable[["Action", Callable[[ExecResult], None]], None]
    requesters: frozenset[str] = frozenset({"person"})
    check: Callable[["Action"], str | None] | None = None
    claim: Callable[["Action"], str | None] | None = None
    release: Callable[["Action"], None] | None = None
    background: bool = False


FEATURE_OUTCOMES = ("succeeded", "failed", "outcome_unknown")


def _worker(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="onemind-feature-action", daemon=True).start()


@dataclass
class InstallHook:
    """Runs before the executor for app.install (prepare) and after a removal (cleanup).

    prepare returns step records for the action result; raising fails the install before the
    executor applies anything.
    """

    name: str
    prepare: Callable[[AppEntry, "Action"], list[dict]]
    removed: Callable[[AppEntry, "Action"], None] | None = field(default=None)


class ActionService:
    def __init__(
        self,
        repo: ActionRepository,
        catalog: Catalog,
        executor: Executor,
        audit: AuditLog,
        clock: Callable[[], datetime],
        *,
        gateway_url: str = "http://localhost:8080",
        require_scan: bool = True,
        credentials: lc.CredentialStore | None = None,
    ):
        self.credentials = credentials
        # Called as fn(action_dict_fields) while an executor reports progress; failures are ignored.
        self.progress_listeners: list[Callable[[str, dict], None]] = []
        self.gateway_url = gateway_url
        self.require_scan = require_scan
        self.repo = repo
        self.catalog = catalog
        self.executor = executor
        self.audit = audit
        self.clock = clock
        self.feature_types: dict[str, FeatureAction] = {}
        self.install_hooks: list[InstallHook] = []
        self._finish_lock = threading.Lock()
        # Contract §12.1 / H-14: most actions one non-owner requester may have awaiting approval.
        # 0 = no cap. Set from the limits settings section (guard.py).
        self.max_pending_per_requester = 10
        # How a background feature action's run() is started after approval; tests make it synchronous.
        self.spawn: Callable[[Callable[[], None]], None] = _worker
        # Contract §12.17: checked right after a request is filed; the first grant accepts it.
        self.standing_approvals: list[Callable[[Action], StandingGrant | None]] = []

    def register_type(self, action_type: str, spec: FeatureAction) -> None:
        if action_type in APP_CLAIMS or action_type in self.feature_types:
            raise ValueError(f"action type {action_type} is already registered")
        if spec.risk not in ("read", "write", "sensitive", "destructive", "actuate"):
            raise ValueError(f"{action_type}: unknown risk class {spec.risk!r}")
        self.feature_types[action_type] = spec

    # ---- helpers -------------------------------------------------------------------------
    def _deny(self, principal: Principal, what: str, action_id: str | None = None) -> ApiError:
        self.audit.append(
            "authz.denied", principal.as_dict(), action_id, {"attempted": what, "reason": "permission_denied"}
        )
        return ApiError(403, "permission_denied", f"{principal.kind}/{principal.role} may not {what}")

    def _get(self, action_id: str) -> Action:
        a = self.repo.get(action_id)
        if a is None:
            raise ApiError(404, "not_found", "no such action")
        return a

    def expire_if_due(self, a: Action) -> Action:
        """Lazy expiry: an undecided action past expires_at becomes expired when next touched."""
        now = self.clock()
        if a.state in ("requested", "awaiting_approval") and now >= a.expires_at:
            moved = self.repo.transition(a.id, {a.state}, "expired", now)
            if moved is not None:
                self.audit.append("action.expired", None, a.id, {"expires_at": iso(a.expires_at)})
                self._release_feature(a)
                return moved
            return self.repo.get(a.id) or a
        return a

    def _precondition(self, action_type: str, app_id: str) -> tuple[AppEntry | None, str | None]:
        app = self.catalog.get(app_id)
        if app is None:
            return None, f"app {app_id!r} is not in the catalog"
        state = self.repo.get_app_state(app_id)
        status = state.status if state else None
        _, allowed, allow_absent = APP_CLAIMS[action_type]
        if status in allowed or (status is None and allow_absent):
            return app, None
        return app, f"app {app_id!r} is {self.shown_status(status)}"

    # ---- API operations ------------------------------------------------------------------
    def list(self) -> list[dict]:
        return [self.expire_if_due(a).to_json() for a in self.repo.list()]

    def get(self, action_id: str) -> dict:
        return self.expire_if_due(self._get(action_id)).to_json()

    def _audited(self, principal: Principal, attempted: str, action_id: str | None, data: dict, fn):
        """Run one decision; any refusal (4xx ApiError) is written to the audit log, then re-raised.

        403s are already audited as authz.denied by _deny, so they are not written twice.
        """
        try:
            return fn()
        except ApiError as e:
            # 403s are audited as authz.denied, policy refusals as policy.refused.
            if e.status != 403 and e.error != "policy_refused":
                self.audit.append(
                    "action.rejected", principal.as_dict(), action_id,
                    {"attempted": attempted, "status": e.status, "error": e.error, "message": e.message, **data},
                )
            raise

    def create(self, principal: Principal, req: ActionRequest, reason: str | None = None) -> tuple[dict, bool]:
        """Returns (action, created). created=False means an idempotent replay (HTTP 200).

        reason (from the MCP request_action tool) is written to the audit log only; the §3 action
        shape has no field for it.
        """
        data = {"type": req.type, "params": req.params.model_dump(exclude_none=True), "idempotency_key": req.idempotency_key}
        return self._audited(
            principal, "request action", None, data, lambda: self._create(principal, req, reason)
        )

    def deny(self, principal: Principal, action_id: str) -> dict:
        return self._audited(principal, "deny action", action_id, {}, lambda: self._cancel(principal, action_id))

    def approve(
        self, principal: Principal, action_id: str, plan_sha256: str | None = None, strict: bool = False
    ) -> dict:
        """strict=True (the client sent OneMind-API-Version: 1) refuses an approval without plan_sha256."""
        return self._audited(
            principal, "approve action", action_id, {},
            lambda: self._approve(principal, action_id, plan_sha256, strict),
        )

    # ---- plans (contract §12.4) -----------------------------------------------------------
    def render(self, action_type: str, params: dict) -> tuple[AppEntry | None, dict | None, str | None]:
        """(app, rendered plan with plan_sha256, problem). Pure: nothing is filed or run."""
        app = self.catalog.get(params["app_id"])
        if app is None:
            return None, None, f"app {params['app_id']!r} is not in the catalog"
        state = self.repo.get_app_state(app.id)
        status = state.status if state else None
        rendered = lc.render_plan(action_type, params, app, self.repo.get_runtime(app.id), status)
        _, allowed, allow_absent = APP_CLAIMS[action_type]
        problem = None if (status in allowed or (status is None and allow_absent)) else (
            f"app {app.id!r} is {self.shown_status(status)}"
        )
        return app, rendered, problem

    @staticmethod
    def shown_status(status: str | None) -> str:
        return "not installed" if status in (None, "removed") else status

    def preview(self, principal: Principal, action_type: str, params: dict) -> dict:
        """POST /v1/plans and GET /v1/apps/{id}/plan: what would happen, and its fingerprint."""
        if not lc.TYPES[action_type].agent_may_request and not principal.is_owner:
            raise self._deny(principal, f"plan {action_type}")
        app, rendered, problem = self.render(action_type, params)
        if app is None:
            raise ApiError(404, "not_found", problem or "unknown app")
        return {
            "type": action_type, "app_id": app.id, "risk": lc.TYPES[action_type].risk,
            "policy_verdict": "refused" if problem else "needs_approval", "reason": problem,
            "plan": rendered["plan"], "plan_sha256": rendered["plan_sha256"],
        }

    def _create(self, principal: Principal, req: ActionRequest, reason: str | None = None) -> tuple[dict, bool]:
        if not principal.can_request_actions:
            raise self._deny(principal, "request actions")
        if not lc.TYPES[req.type].agent_may_request and not principal.is_owner:
            # Deleting data is the owner's own act: an agent can propose a removal, never this.
            raise self._deny(principal, f"request {req.type}")
        params = req.params.model_dump(exclude_none=True)
        existing = self.repo.get_by_idempotency_key(req.idempotency_key)
        if existing is not None:
            return self._replay(principal, req, params, existing)
        now = self.clock()
        expires_at = utc(req.expires_at)
        if expires_at <= now:
            raise ApiError(409, "expired", "expires_at is already in the past")
        self._check_pending_cap(principal)
        app, problem = self._precondition(req.type, params["app_id"])
        if app is None:
            raise ApiError(404, "not_found", problem or "unknown app")
        if problem:
            raise ApiError(409, "stale_precondition", problem)
        _, rendered, _ = self.render(req.type, params)
        if req.plan_sha256 is not None and req.plan_sha256 != rendered["plan_sha256"]:
            raise ApiError(
                409, "stale_precondition", "the plan changed since you read it; read it again",
                reason="plan_changed",
            )
        action = Action(
            id=new_action_id(),
            type=req.type,
            params=params,
            state="requested",
            requested_by={"id": principal.id, "kind": principal.kind},
            idempotency_key=req.idempotency_key,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
            plan=rendered["plan"],
            plan_sha256=rendered["plan_sha256"],
            risk=lc.TYPES[req.type].risk,
        )
        stored, created = self.repo.create(action)
        if not created:  # lost an insert race on the same idempotency key
            return self._replay(principal, req, params, stored)
        self.audit.append(
            "action.requested",
            principal.as_dict(),
            stored.id,
            {
                "type": stored.type, "params": stored.params, "expires_at": iso(stored.expires_at),
                "requested_by": principal.id, "risk": lc.TYPES[req.type].risk,
                "plan_sha256": stored.plan_sha256,
                **({"reason": reason} if reason else {}),
            },
        )
        moved = self.repo.transition(stored.id, {"requested"}, "awaiting_approval", self.clock())
        self.audit.append("action.awaiting_approval", None, stored.id, {})
        action = moved or stored
        return self._standing_approve(action) or action.to_json(), True

    def _standing_approve(self, a: Action) -> dict | None:
        """Accept a fresh request under an owner-set standing approval, or leave it for a person.

        The risk ceiling is checked here as well as in the policy module, so no hook can make a
        policy accept a sensitive, destructive or actuate request (docs/leap/core/AUTOMATION.md §4).
        """
        if not self.standing_approvals or _never_by_policy(a):
            return None
        for decide in self.standing_approvals:
            try:
                grant = decide(a)
            except Exception:  # a broken policy store must not approve, nor fail the filed request
                log.exception("standing approval check failed")
                continue
            if grant is None:
                continue
            try:
                return self._audited(
                    grant.principal, "approve action", a.id, {},
                    lambda: self._approve(grant.principal, a.id, standing=grant.audit),
                )
            except ApiError:  # e.g. a stale precondition: the action stays awaiting_approval
                grant.release()
                return None
            except Exception:  # the request is filed: never fail it; give the use back unless accepted
                log.exception("standing approval failed")
                try:
                    now = self._get(a.id)
                except Exception:
                    return None
                if now.state == "awaiting_approval":
                    grant.release()
                    return None
                return now.to_json()
        return None

    def _check_pending_cap(self, principal: Principal) -> None:
        cap = self.max_pending_per_requester
        if principal.is_owner or cap <= 0:
            return
        pending = sum(
            1 for x in self.repo.list(states={"awaiting_approval"})
            if x.requested_by.get("id") == principal.id and self.expire_if_due(x).state == "awaiting_approval"
        )
        if pending >= cap:
            raise ApiError(
                429, "rate_limited", f"{pending} requests are already awaiting approval (limit {cap})",
                reason="too_many_pending", retry_after_s=60,
            )

    def _replay(self, principal: Principal, req: ActionRequest, params: dict, existing: Action) -> tuple[dict, bool]:
        same = (
            existing.type == req.type
            and existing.params == params
            and existing.requested_by.get("id") == principal.id
            and existing.expires_at == utc(req.expires_at)
        )
        if not same:
            raise ApiError(409, "conflict", "idempotency_key was already used for a different request")
        return self.expire_if_due(existing).to_json(), False

    def _cancel(self, principal: Principal, action_id: str) -> dict:
        if not principal.is_owner:
            raise self._deny(principal, "deny actions", action_id)
        a = self.expire_if_due(self._get(action_id))
        if a.state == "expired":
            raise ApiError(409, "expired", "action expired before a decision")
        now = self.clock()
        moved = self.repo.transition(
            a.id, {"awaiting_approval"}, "cancelled", now, decided_by=principal.as_dict(), decided_at=now
        )
        if moved is None:
            raise ApiError(409, "conflict", f"action is {self._get(action_id).state}, not awaiting_approval")
        self.audit.append("action.denied", principal.as_dict(), a.id, {"params": a.params})
        self._release_feature(a)
        return moved.to_json()

    def _release_feature(self, a: Action) -> None:
        """A feature action that ended or never started: let its module drop what it holds for it
        (e.g. migrate's in-memory kubeconfig). A failing release never fails the caller."""
        spec = self.feature_types.get(a.type)
        if spec is None or spec.release is None:
            return
        try:
            spec.release(a)
        except Exception:
            log.exception("release of %s %s failed", a.type, a.id)

    def _approve(
        self, principal: Principal, action_id: str, plan_sha256: str | None = None, strict: bool = False,
        standing: dict | None = None,
    ) -> dict:
        if standing is None and not principal.is_owner:
            raise self._deny(principal, "approve actions", action_id)
        a = self.expire_if_due(self._get(action_id))
        if a.state == "expired":
            raise ApiError(409, "expired", "action expired before approval")
        if a.state != "awaiting_approval":
            raise ApiError(409, "conflict", f"action is {a.state}, not awaiting_approval")
        if a.type in self.feature_types:
            return self._approve_feature(principal, a, self.feature_types[a.type], standing)

        # Check current conditions again: the world may have changed since the request. The claim
        # on the app is made atomically with "accepted", so two actions for one app cannot both
        # pass. A stale action stays in awaiting_approval (the owner may deny it or let it expire).
        app_id = a.params["app_id"]
        app = self.catalog.get(app_id)
        claim, allowed, allow_absent = APP_CLAIMS[a.type]
        now = self.clock()
        # Plan binding (contract §12.4): the owner approves a fingerprint, and only the thing that
        # fingerprint describes may run. A different fingerprint from the card, or a fresh render
        # that no longer matches what was requested, leaves the action awaiting_approval.
        if plan_sha256 is not None and a.plan_sha256 is not None and plan_sha256 != a.plan_sha256:
            raise ApiError(
                409, "stale_precondition", "the approval names a different plan than the one requested",
                reason="plan_changed",
            )
        if plan_sha256 is None and strict:
            raise ApiError(
                409, "stale_precondition", "send plan_sha256 so the approval is bound to the plan you read",
                reason="plan_unchecked",
            )
        if a.plan_sha256 is not None and app is not None:
            _, fresh, _ = self.render(a.type, a.params)
            if fresh["plan_sha256"] != a.plan_sha256:
                raise ApiError(
                    409, "stale_precondition",
                    f"the plan for {a.type} changed since it was requested (the app or its state is different now)",
                    reason="plan_changed",
                )
        prior_state = self.repo.get_app_state(app_id)
        prior = prior_state.status if prior_state else None
        if a.type in ("app.install", "app.update") and app is not None and self.require_scan:
            # Contract 9.4: a malware hit or a human review sets metadata.tier to blocked, and
            # nothing lifts it but a human. The scan record alone must not override it.
            problem = f"app {app_id!r} is tier blocked; a human has to review it first" if (app.manifest.get("metadata") or {}).get("tier") == "blocked" else None
            problem = problem or scan_problem(app_id, app.scan, now)
            if problem:  # §10.3: nothing unscanned runs; the action stays awaiting_approval
                raise ApiError(409, "stale_precondition", problem)
        outcome = "stale" if app is None else self.repo.accept_and_claim(
            a.id, now, principal.as_dict(), app_id, claim, set(allowed), allow_absent
        )
        if outcome == "conflict":  # someone else decided first (compare-and-swap lost)
            raise ApiError(409, "conflict", "action was decided concurrently")
        if outcome == "stale":
            problem = self._precondition(a.type, app_id)[1] or f"app {app_id!r} changed state concurrently"
            raise ApiError(409, "stale_precondition", problem)
        ids = {"requested_by": a.requested_by.get("id"), "approved_by": principal.id, **(standing or {})}
        # Contract §12.4: an approval that named no plan fingerprint is allowed for old clients, but recorded.
        extra = {"plan_unchecked": True} if plan_sha256 is None and a.plan_sha256 is not None else {}
        self.audit.append("action.approved", principal.as_dict(), a.id, {"type": a.type, "params": a.params, **ids, **extra})

        try:
            out = self._dispatch(a, app, ids, prior)
        except Exception as exc:  # anything after accepted: the effect is unknown, never retry
            log.exception("dispatch interrupted")
            self._mark_outcome_unknown(a, f"dispatch error: {exc.__class__.__name__}")
            return self._get(a.id).to_json()
        violations = (out.get("result") or {}).get("violations")
        if out.get("state") == "failed" and violations:
            # Contract §12.2: the install sandbox refused the rendered plan. The action is failed
            # (with the violations in its result) and the approval call says why.
            raise ApiError(
                409, "policy_refused", (out.get("result") or {}).get("message") or "install sandbox refused",
                details=[_detail(v) for v in violations],
            )
        return out

    def _dispatch(self, a: Action, app: AppEntry, ids: dict, prior: str | None = None) -> dict:
        dispatched = self.repo.transition(a.id, {"accepted"}, "dispatched", self.clock())
        if dispatched is None:
            raise RuntimeError("accepted action could not move to dispatched")
        self.audit.append("action.dispatched", None, a.id, {"executor": self.executor.name, **ids})

        # Last look before anything runs: what is about to execute must still be what was approved.
        if a.plan_sha256 is not None:
            _, fresh, _ = self.render(a.type, {**a.params})
            if fresh is None or fresh["plan_sha256"] != a.plan_sha256:
                return self._refuse_dispatch(a, ids, prior)

        agent = self._agent_grant(a, app)
        hook_steps: list[dict] = []
        try:
            if a.type == "app.install":
                for hook in self.install_hooks:
                    hook_steps += [{"hook": hook.name, **st} for st in hook.prepare(app, a)]
        except Exception as exc:  # nothing was applied yet: the install fails cleanly
            log.exception("install hook failed")
            result = ExecResult("failed", f"install preparation failed: {exc}"[:500], hook_steps)
        else:
            ctx = self._exec_context(a, app, ids)
            token = lc.set_progress_callback(self._progress_reporter(a))
            try:
                result = self._run_executor(a, app, agent, ctx)
            except Exception as exc:  # unknown effect: never retry automatically
                log.exception("executor crashed")
                result = ExecResult("outcome_unknown", f"executor error: {exc.__class__.__name__}")
            finally:
                lc.reset_progress_callback(token)
            result.steps = hook_steps + result.steps
            if a.type == "app.remove" and result.outcome == "succeeded":
                for hook in self.install_hooks:
                    if hook.removed is not None:
                        try:
                            hook.removed(app, a)
                        except Exception:  # cleanup is best effort; the app is already gone
                            log.exception("removal hook %s failed", hook.name)
        if a.type == "app.install" and agent is not None and result.outcome != "succeeded":
            # A failed or unknown install must not leave a live credential behind; a new install
            # issues a fresh one.
            self._revoke_agent(a, f"install {result.outcome}")

        if result.violations:
            self.audit.append(
                "policy.refused", None, a.id,
                {"app_id": app.id, "violations": result.violations,
                 "policy_version": (result.plan or {}).get("policy_version"), **ids},
            )
        final = self.repo.transition(a.id, {"dispatched"}, result.outcome, self.clock(), result=result.to_json())
        self._record_app_state(a, result, prior)
        self.audit.append(
            f"action.{result.outcome}", None, a.id,
            {"executor": self.executor.name, "message": result.message, **ids},
        )
        state = self.repo.get_app_state(app.id)
        status = state.status if state else None
        self.audit.append("app.status", None, a.id, {
            "app_id": app.id, "status": "not_installed" if status in (None, "removed") else status,
            "data_kept": status == "removed",
        })
        if a.type == "app.restart" and result.outcome == "succeeded":
            self.audit.append("app.restarted", None, a.id, {"app_id": app.id})
        if a.type == "app.update" and result.reverted:
            self.audit.append(
                "app.update_reverted", None, a.id,
                {"app_id": app.id, "reason": "the new version failed its health check", **ids},
            )
        return (final or self._get(a.id)).to_json()

    def _run_executor(self, a: Action, app: AppEntry, agent: AgentSecret | None, ctx: lc.ExecContext) -> ExecResult:
        # Executors written before the lifecycle (tests, plugins) take no ctx; give it only to those that do.
        if "ctx" in inspect.signature(self.executor.run).parameters:
            return self.executor.run(a.type, app, agent=agent, ctx=ctx)
        return self.executor.run(a.type, app, agent=agent)

    def _refuse_dispatch(self, a: Action, ids: dict, prior: str | None) -> dict:
        """The plan changed between approval and execution: nothing runs, the app goes back as it was."""
        result = {"outcome": "failed", "message": "the plan changed after approval; nothing was run",
                  "reason": "plan_changed", "steps": []}
        final = self.repo.transition(a.id, {"dispatched"}, "failed", self.clock(), result=result)
        self._restore_state(a.params["app_id"], prior, a.id)
        self.audit.append("action.failed", None, a.id, {"message": result["message"], "reason": "plan_changed", **ids})
        return (final or self._get(a.id)).to_json()

    def _restore_state(self, app_id: str, prior: str | None, action_id: str) -> None:
        self.repo.set_app_state(app_id, prior, self.clock(), action_id)

    def _exec_context(self, a: Action, app: AppEntry, ids: dict) -> lc.ExecContext:
        runtime = self.repo.get_runtime(app.id)
        stored = dict(runtime.settings) if runtime else {}
        settings = {**stored, **(a.params.get("settings") or {})}
        grant = None
        if a.type == "app.install" and self.credentials is not None:
            grant, generated = self.credentials.ensure(app, self.clock())
            if generated:  # the value is never logged, only the fact
                self.audit.append("app.credentials.generated", None, a.id, {"app_id": app.id, **ids})
        return lc.ExecContext(params=dict(a.params), settings=settings, credentials=grant)

    def _progress_reporter(self, a: Action):
        def report(step: str, pct: int) -> None:
            progress = {"step": step[:200], "pct": pct}
            try:
                self.repo.set_progress(a.id, progress, self.clock())
            except Exception:  # progress is a courtesy: it must never fail the action
                log.exception("could not record progress")
            for fn in self.progress_listeners:
                try:
                    fn(a.id, {"type": a.type, "app_id": a.params["app_id"], **progress})
                except Exception:
                    log.exception("progress listener failed")

        return report

    # ---- §11.2 agent principals ------------------------------------------------------------
    def _agent_grant(self, a: Action, app: AppEntry) -> AgentSecret | None:
        """Issue (install) or revoke (remove) the app's agent principal, before the executor runs.

        On removal the principal is revoked first and whatever the executor then manages to do,
        so a removed app's credential is dead even when deleting its resources fails. Removal
        revokes agent:<app-id> even if the manifest no longer declares spec.agent.
        """
        spec = app.agent
        if a.type == "app.remove":
            self._revoke_agent(a, "app.remove")
            return AgentSecret(name=spec.secret, principal_id=spec.principal_id) if spec else None
        if spec is None:
            return None
        if a.type != "app.install":
            # Only an install issues a credential. Other actions must not rotate it: the app's
            # Secret would go stale. An update still needs the gateway address for its egress rule.
            return AgentSecret(spec.secret, spec.principal_id, gateway_url=self.gateway_url) if a.type == "app.update" else None
        token = new_agent_token()
        self.repo.issue_agent_token(spec.principal_id, app.id, token_hash(token), self.clock())
        self.audit.append(
            "agent.principal.issued", None, a.id,
            {"principal": {"id": spec.principal_id, "kind": "agent", "role": "agent"},
             "app_id": app.id, "secret": spec.secret, "namespace": f"app-{app.id}"},
        )
        return AgentSecret(spec.secret, spec.principal_id, gateway_url=self.gateway_url, token=token)

    def _revoke_agent(self, a: Action, reason: str) -> None:
        principal_id = f"agent:{a.params['app_id']}"
        if self.repo.revoke_agent_token(principal_id, self.clock()):
            self.audit.append(
                "agent.principal.revoked", None, a.id, {"principal_id": principal_id, "reason": reason}
            )

    def _mark_outcome_unknown(self, a: Action, message: str) -> None:
        result = {"outcome": "outcome_unknown", "message": message}
        moved = self.repo.transition(a.id, {"accepted", "dispatched"}, "outcome_unknown", self.clock(), result=result)
        if a.type in self.feature_types:  # a feature action: its module reconciles its own state
            self._release_feature(a)
        if a.type in APP_CLAIMS:
            self.repo.set_app_state(a.params["app_id"], "unknown", self.clock(), a.id)
        if a.type == "app.install":
            self._revoke_agent(a, "install outcome unknown")
        if moved is not None:
            self.audit.append("action.outcome_unknown", None, a.id, {"message": message})

    def reconcile_interrupted(self) -> None:
        """Startup: whatever a previous gateway process left mid-dispatch has an unknown effect.

        Actions still accepted/dispatched become outcome_unknown and apps still installing/removing
        become unknown, each with an audit entry, so later installs or removals are not refused
        forever. (v0 runs one gateway per ledger; several would need leases first.)
        """
        for a in self.repo.list(states={"accepted", "dispatched"}):
            self._mark_outcome_unknown(a, f"gateway restarted while the action was {a.state}")
        now = self.clock()
        for app_id, st in self.repo.list_app_states().items():
            if st.status in lc.TRANSIENT:
                self.repo.set_app_state(app_id, "unknown", now, st.action_id)
                self.audit.append(
                    "app.reconciled", None, st.action_id,
                    {"app_id": app_id, "from": st.status, "to": "unknown", "reason": "gateway restarted"},
                )

    def _record_app_state(self, a: Action, result: ExecResult, prior: str | None) -> None:
        app_id, now = a.params["app_id"], self.clock()
        spec = lc.TYPES[a.type]
        outcome = result.outcome
        if outcome == "succeeded":
            self.repo.set_app_state(app_id, spec.final, now, a.id)
            self._record_runtime(a, now)
        elif outcome == "failed":
            # A failure that left the running app untouched keeps it as it was: the install sandbox
            # refused the update, or the new version was unhealthy and the old one is back.
            untouched = prior is not None and a.type != "app.install" and (result.reverted or result.violations)
            self.repo.set_app_state(app_id, prior if untouched else "failed", now, a.id)
        else:
            self.repo.set_app_state(app_id, "unknown", now, a.id)

    def _record_runtime(self, a: Action, now: datetime) -> None:
        app_id = a.params["app_id"]
        if a.type == "app.delete_data":
            self.repo.delete_runtime(app_id)
            if self.credentials is not None and self.credentials.delete(app_id):
                self.audit.append("app.credentials.deleted", None, a.id, {"app_id": app_id})
            return
        app = self.catalog.get(app_id)
        runtime = self.repo.get_runtime(app_id)
        if a.type in ("app.install", "app.update") and app is not None:
            md = app.manifest.get("metadata") or {}
            version = str(md.get("version")) if md.get("version") is not None else None
            self.repo.set_runtime(
                app_id, now, version=version, bundle_sha256=lc.bundle_sha256(app),
                previous_version=runtime.version if runtime and runtime.version != version else (
                    runtime.previous_version if runtime else None),
            )
        elif a.type == "app.configure":
            self.repo.set_runtime(app_id, now, settings={**(runtime.settings if runtime else {}), **a.params["settings"]})


    # ---- feature-owned action types (contract §12.5) -------------------------------------------
    def request_feature(
        self, principal: Principal, action_type: str, params: dict, *, idempotency_key: str,
        expires_at: datetime, reason: str | None = None, audit_extra: dict | None = None,
    ) -> tuple[dict, bool]:
        """File a feature action: same ledger, idempotency and audit as POST /v1/actions.

        params are the feature's already-validated parameters (never secrets: they are stored and
        audited). audit_extra adds facts to the action.requested line, e.g. credentials: provided.
        """
        spec = self.feature_types[action_type]
        data = {"type": action_type, "params": params, "idempotency_key": idempotency_key}

        def create() -> tuple[dict, bool]:
            if not principal.can_request_actions or (not principal.is_owner and principal.kind not in spec.requesters):
                raise self._deny(principal, f"request {action_type}")
            existing = self.repo.get_by_idempotency_key(idempotency_key)
            if existing is not None:
                if existing.type != action_type or existing.params != params or existing.requested_by.get("id") != principal.id:
                    raise ApiError(409, "conflict", "idempotency_key was already used for a different request")
                return self.expire_if_due(existing).to_json(), False
            now = self.clock()
            exp = utc(expires_at)
            if exp <= now:
                raise ApiError(409, "expired", "expires_at is already in the past")
            action = Action(
                id=new_action_id(), type=action_type, params=params, state="requested",
                requested_by={"id": principal.id, "kind": principal.kind}, idempotency_key=idempotency_key,
                created_at=now, updated_at=now, expires_at=exp,
            )
            stored, created = self.repo.create(action)
            if not created:
                return self.expire_if_due(stored).to_json(), False
            self.audit.append("action.requested", principal.as_dict(), stored.id, {
                "type": action_type, "params": params, "risk": spec.risk, "expires_at": iso(exp),
                "requested_by": principal.id, **({"reason": reason} if reason else {}), **(audit_extra or {}),
            })
            moved = self.repo.transition(stored.id, {"requested"}, "awaiting_approval", self.clock())
            self.audit.append("action.awaiting_approval", None, stored.id, {})
            return (moved or stored).to_json(), True

        return self._audited(principal, f"request {action_type}", None, data, create)

    def _approve_feature(
        self, principal: Principal, a: Action, spec: FeatureAction, standing: dict | None = None
    ) -> dict:
        problem = spec.check(a) if spec.check else None
        if problem:
            raise ApiError(409, "stale_precondition", problem)
        problem = spec.claim(a) if spec.claim else None
        if problem:  # the action stays awaiting_approval; the owner may deny it or let it expire
            raise ApiError(409, "stale_precondition", problem)
        now = self.clock()
        accepted = self.repo.transition(
            a.id, {"awaiting_approval"}, "accepted", now, decided_by=principal.as_dict(), decided_at=now,
            approved_by=principal.id,
        )
        if accepted is None:
            self._release_feature(a)
            raise ApiError(409, "conflict", "action was decided concurrently")
        ids = {"requested_by": a.requested_by.get("id"), "approved_by": principal.id, **(standing or {})}
        self.audit.append("action.approved", principal.as_dict(), a.id,
                          {"type": a.type, "params": a.params, "risk": spec.risk, **ids})
        if self.repo.transition(a.id, {"accepted"}, "dispatched", self.clock()) is None:
            self._mark_outcome_unknown(a, "accepted action could not move to dispatched")
            return self._get(a.id).to_json()
        self.audit.append("action.dispatched", None, a.id, {"executor": f"feature:{a.type}", **ids})

        def finish(result: ExecResult) -> None:
            if result.outcome not in FEATURE_OUTCOMES:
                result = ExecResult("outcome_unknown", f"{a.type} returned outcome {result.outcome!r}")
            with self._finish_lock:
                final = self.repo.transition(
                    a.id, {"dispatched"}, result.outcome, self.clock(), result=result.to_json()
                )
                if final is not None:
                    self.audit.append(f"action.{result.outcome}", None, a.id,
                                      {"executor": f"feature:{a.type}", "message": result.message, **ids})
                    self._release_feature(a)

        def start() -> None:
            try:
                spec.run(a, finish)
            except Exception as exc:  # the feature could not even start: the effect is unknown
                log.exception("feature action %s crashed", a.type)
                finish(ExecResult("outcome_unknown", f"feature error: {exc.__class__.__name__}"))

        if spec.background:
            self.spawn(start)
        else:
            start()
        return self._get(a.id).to_json()


def _detail(v: dict) -> dict:
    where = f"{v.get('kind')}/{v.get('name')}" + (f" {v['path']}" if v.get("path") else "")
    return {"field": where, "problem": f"{v.get('rule')}: {v.get('message')}", "rule": v.get("rule")}
