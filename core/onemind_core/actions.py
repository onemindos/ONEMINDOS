"""Action service: request -> owner approval -> dispatch, with every decision audited.

This is where "AI never actuates without human approval" is enforced:
- owners and agents may *request* an action (it lands in awaiting_approval);
- only a person with role owner may approve or deny; an agent always gets 403 permission_denied;
- nothing reaches the executor until an approval has moved the action to accepted;
- a standing approval the owner set in advance (§12.17, automation/policies.py) may accept a
  matching read or write request; it is recorded as approved_by policy:<id>@<revision>;
- an app.install is approved only for an app with a passing scan newer than 7 days (§10.3);
- an agent that read third-party text (over MCP or REST) is tainted (taint.py, AIG-04): its requests,
  app and feature types alike, carry a note on the plan, are never accepted by a standing approval,
  need the owner's approval to name the plan fingerprint, and may only name apps visible to AI;
- an app that declares spec.agent gets its own agent principal at install, revoked at removal
  (§11.2), so the AI inside it can request actions but, like every agent, never approve them;
- an app's declared secrets are entered by the owner with the approval itself (or filed as an
  app.configure the owner approves) and reach the executor only after acceptance (appsecrets/);
- an owner may approve an install whose scan failed only through the F-7 owner override, which
  is off unless ONEMIND_ALLOW_OWNER_OVERRIDE=1 and leaves a red audit mark (override.py);
- a feature module may own further action types of contract §12.5 (FeatureAction, for example
  backup.run and backup.restore): they go through the same ledger, the same owner-only approval
  and the same audit lines; only what runs after approval is the feature's;
- a feature may prepare an app install before the executor runs (install_hooks, for example the
  app's database and its Secret); a hook that fails fails the install before anything is applied;
- action types that are not about an app and have no executor step (node.join, later mesh.*) plug in a
  handler with register_handler(type, handler): the same ledger, approval rule and audit trail apply,
  and the handler owns the precondition re-check and the effect (docs/leap/core/PLUMBING.md §2);
- a feature type registered with physical=True (it moves or switches something in the world) is
  fixed as physical at registration and, whatever its risk class: is approved only by an owner with a
  passkey assertion and a hold of at least HOLD_MIN_MS, bound to its plan_sha256; is never accepted by a
  standing approval nor filed by an automation; and is refused while the owner's motion lockout is on.
  It is separate from risk "actuate", which also covers an OS install reboot and node.wake (#723).
"""

from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, Protocol

from pydantic import (
    AwareDatetime, BaseModel, ConfigDict, Discriminator, Field, Tag, ValidationError, field_validator, model_validator,
)

from . import ai_policy
from .audit import AuditLog
from .auth import Principal, new_agent_token, token_hash
from .catalog import APP_ID_RE, GREEN_LICENCE_CLASSES, AppEntry, Catalog
from .errors import ApiError, SemanticValueError
from .executors import AgentSecret, ExecResult, Executor
from . import lifecycle as lc
from . import streams
from .scan import scan_problem
from .approvalcard import APPROVAL_LIMIT_VALUE, HOLD_MIN_MS, approval_card, hold_required  # noqa: F401 (re-exported)
from .ledger import Action, ActionRepository, iso, new_action_id, utc
from .taint import PLAN_KEY, TaintLedger, plan_taint
from .taint_store import NODE_JOIN_REQUESTER

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


# Handler action types whose module reconciles them itself when it registers (reconcile_interrupted
# runs before the routers register, so self.handlers is still empty then). Other FeatureAction types
# are not in this set: they are marked outcome_unknown here, as before. The host actions are: a restart,
# shutdown or OS install reboots the box and so restarts the gateway while the host executor is still
# finishing them; hostlink.py reads the verdict from the host's journal at startup (HOST-ACTIONS.md).
SELF_RECONCILED_TYPES = frozenset({
    "node.join", "os.update.install", "os.rollback", "system.restart", "system.shutdown", "system.factory_reset",
    "service.restart",  # #636: restarting the gateway's own unit restarts the gateway mid-action
})


class ActionHandler(Protocol):
    """The effect of a non-app action type, run only after an owner approved it.

    recheck(action) -> a message when the world changed since the request (the approval answers 409
    stale_precondition and the action stays awaiting_approval), else None.
    dispatch(action) -> an ExecResult to finish the action now, or None to leave it dispatched; the
    handler then calls ActionService.finish() when the effect is complete (a node joining).
    reconcile_interrupted() leaves the type's accepted/dispatched actions alone: the handler's module
    picks them up when it registers.
    """

    def recheck(self, action: Action) -> str | None: ...

    def dispatch(self, action: Action) -> ExecResult | None: ...


@dataclass(frozen=True)
class ApprovalInput:
    """What the owner sends with an approval besides the action id.

    sealed: the app's secrets form, sealed in the browser (app.install only; appsecrets/).
    override: the F-7 owner override {reason, confirm} for an install whose scan failed.
    webauthn: whether a passkey assertion came with the approval. The identity feature's approval
      guard verifies it before the action service runs; the override only checks it was there.
    """

    sealed: dict | None = None
    override: dict | None = None
    # #173: the app id the owner typed to accept a licence class that is not green.
    accept_licence: str | None = None
    webauthn: bool = False
    # How long the owner held the approve control, in ms (hold-to-approve). A physical action needs
    # at least HOLD_MIN_MS; the passkey assertion, not this number, is the proof of presence.
    hold_ms: int | None = None


def _fingerprinted(plan: dict) -> tuple[dict, str]:
    body = json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return plan, "sha256:" + hashlib.sha256(body.encode()).hexdigest()


def physical_plan(action_type: str, params: dict, card: dict) -> tuple[dict, str]:
    """(plan, plan_sha256) of a physical request: the fingerprint covers type, params and card, so any
    changed parameter or limit needs a new approval (contract §12.4)."""
    return _fingerprinted({"type": action_type, "params": params, "approval": card})


def feature_plan(action_type: str, params: dict) -> tuple[dict, str]:
    """(plan, plan_sha256) of a tainted agent's feature request (AIG-04): type and params, so the
    owner approves exactly the parameters the card showed."""
    return _fingerprinted({"type": action_type, "params": params})


class ActionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_id: str = Field(min_length=1, max_length=59, pattern=APP_ID_RE.pattern)
    # app.configure: plain settings, never secrets (those go through the sealed path).
    # §12.22: a setting an app declares in spec.settings is a string, integer, number or boolean;
    # the manifest's field says which, and it is checked there when the app declares any.
    settings: dict[str, str | int | float | bool] | None = Field(default=None, max_length=50)
    # app.delete_data: the app id typed again by the owner. Deleting data is never one click.
    confirm: str | None = Field(default=None, max_length=59)


def check_params_fit(action_type: str, p: ActionParams) -> None:
    if action_type == "app.configure":
        if not p.settings:
            raise ValueError("app.configure needs params.settings")
        problem = lc.settings_problem(p.settings)
        if problem:
            raise SemanticValueError(problem, "invalid_settings")
    elif p.settings is not None:
        raise ValueError(f"params.settings is only for app.configure, not {action_type}")
    if action_type == "app.delete_data":
        if p.confirm != p.app_id:
            raise SemanticValueError("app.delete_data needs params.confirm equal to the app id, typed by the owner",
                                     "confirm_mismatch")
    elif p.confirm is not None:
        raise ValueError("params.confirm is only for app.delete_data")


# Gateway permissions design PR 3 (gap 9, review item 15): a request nobody decides must not wait for ever.
# Software that asks (agents, automations, nodes, plugins) gets 72 hours; a person gets 7 days.
PENDING_MAX_AGENT = timedelta(hours=72)
PENDING_MAX_PERSON = timedelta(days=7)


def check_pending_lifetime(requester_kind: str | None, expires_at: datetime, now: datetime) -> None:
    """Refuse an expires_at further ahead than the requester kind may wait (422 conflict)."""
    person = requester_kind == "person"
    limit = PENDING_MAX_PERSON if person else PENDING_MAX_AGENT
    if utc(expires_at) > now + limit:
        raise ApiError(
            422, "conflict",
            f"a request from {'a person' if person else 'an agent, automation or node'} expires at most "
            f"{'7 days' if person else '72 hours'} ahead")


TYPE_RE = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,3}$"

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
    # A lifecycle type (ActionType) or a type a feature registered (contract §12.5, §12.22:
    # source.add|move|remove, exposure.private|mesh|public). Unknown types are refused at request.
    type: str = Field(min_length=1, max_length=64, pattern=TYPE_RE)
    params: ActionParams | dict[str, Any]
    idempotency_key: str = Field(min_length=1, max_length=200)
    expires_at: AwareDatetime
    # Contract §12.4: the fingerprint of the plan the requester looked at. If the plan the gateway
    # renders now differs, the request is refused (409 stale_precondition, reason plan_changed).
    plan_sha256: str | None = Field(default=None, max_length=80)

    @field_validator("params", mode="before")
    @classmethod
    def _lifecycle_params(cls, value: Any, info):
        # A lifecycle type takes exactly ActionParams (extra keys refused); a feature type's params
        # are checked against its own model when the request is filed.
        if info.data.get("type") in APP_CLAIMS:
            return ActionParams.model_validate(value)
        return value

    @field_validator("expires_at")
    @classmethod
    def _expires_in_range(cls, v: datetime) -> datetime:
        return _expiry_in_range(v)

    @model_validator(mode="after")
    def _params_fit_type(self):
        if isinstance(self.params, ActionParams):
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
    # plain settings, never secrets (those go through the sealed path). Typed settings (D21, §12.22):
    # a value is a string, integer, number or boolean; the app's spec.settings says which.
    settings: dict[str, str | int | float | bool] = Field(min_length=1, max_length=50)


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


class FeatureActionRequest(_ActionRequestFields):
    # A type a feature registered at runtime (contract §12.5, §12.22: source.add|move|remove,
    # exposure.private|mesh|public, ...). The service checks params against the model the feature
    # registered and refuses a type nobody registered, so this variant cannot widen what is accepted.
    type: str = Field(min_length=1, max_length=64, pattern=TYPE_RE)
    params: dict[str, Any]


_LIFECYCLE_TAGS = {**{t: "plain" for t in _PLAIN_TYPES.__args__}, "app.configure": "configure",
                   "app.delete_data": "delete_data"}


def _action_variant(body: Any) -> str:
    t = body.get("type") if isinstance(body, dict) else getattr(body, "type", None)
    return _LIFECYCLE_TAGS.get(t, "feature") if isinstance(t, str) else "plain"


ActionRequestBody = Annotated[
    Annotated[PlainActionRequest, Tag("plain")] | Annotated[ConfigureActionRequest, Tag("configure")]
    | Annotated[DeleteDataActionRequest, Tag("delete_data")] | Annotated[FeatureActionRequest, Tag("feature")],
    Discriminator(_action_variant),
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

    # The class stored on the request counts, not only the table's: a feature's risk_for may have
    # raised it, and a request with no stored class is never covered.
    return registry.policy_may_cover(a.type, a.params, a.risk) is not None


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
    # Requested through POST /v1/actions (contract §12.22): the pydantic model its params must fit,
    # and an optional request-time check that raises ApiError. Types filed by their own routes
    # (backup.run ...) leave both unset.
    params_model: type[BaseModel] | None = None
    check_request: Callable[[dict, Principal], None] | None = None
    claim: Callable[["Action"], str | None] | None = None
    release: Callable[["Action"], None] | None = None
    background: bool = False
    # A feature may derive risk from its immutable request; approval must match it.
    risk_for: Callable[[dict], str] | None = None
    # A security-setting approval needs the requester's own session and a fresh, bound passkey.
    owner_passkey: bool = False
    # #723: it moves or switches something physical. Fixed at registration, independent of risk:
    # passkey and hold-to-approve, plan-bound, never a standing approval or automation, lockout applies.
    physical: bool = False
    # Physical types: the limits with units and the optional preview drawn on the approval card,
    # derived from the request's params (part of plan_sha256).
    limits_for: Callable[[dict], list[dict]] | None = None
    preview_for: Callable[[dict], dict | None] | None = None


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
    # Security cleanup must precede removal, including a failed executor.
    removing: Callable[[AppEntry, "Action"], None] | None = field(default=None)


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
        # H-05: the box CA (PEM) to hand agent pods as ONEMIND_GATEWAY_CA; net.py sets it when HTTPS is on.
        self.gateway_ca: Callable[[], str | None] = lambda: None
        self.require_scan = require_scan
        self.repo = repo
        self.catalog = catalog
        self.executor = executor
        self.audit = audit
        self.clock = clock
        # Set by feature routers at registration (routers/secrets.py, routers/override.py).
        self.app_secrets: Any = None  # appsecrets.service.AppSecretsService
        self.owner_override: Any = None  # override.OwnerOverride
        self.feature_types: dict[str, FeatureAction] = {}
        self.install_hooks: list[InstallHook] = []
        # A feature-owned workload identity, handed only to the executor after preparation.
        self.workload_credential: Callable[[Action, AppEntry], AgentSecret | None] | None = None
        self._finish_lock = threading.Lock()
        # Contract §12.1 / H-14: most actions one non-owner requester may have awaiting approval.
        # 0 = no cap. Set from the limits settings section (guard.py).
        self.max_pending_per_requester = 10
        # AIG-03 (#167): fn(principal) raises ApiError to refuse a fresh request (agent budget, cancel).
        self.requester_checks: list[Callable[[Principal], None]] = []
        # AIG-04: who read third-party text lately. Fed by the MCP layer; read when a request is filed.
        self.taint = TaintLedger(clock)
        # fn(principal_id): an agent identity ended (app removed, failed install); what the owner
        # declared about it (agents_inputs) must not carry over to a new agent with the same id.
        self.agent_forgotten: Callable[[str], None] | None = None
        self.handlers: dict[str, ActionHandler] = {}
        # How a background feature action's run() is started after approval; tests make it synchronous.
        self.spawn: Callable[[Callable[[], None]], None] = _worker
        # Contract §12.17: checked right after a request is filed; the first grant accepts it.
        self.standing_approvals: list[Callable[[Action], StandingGrant | None]] = []
        # Extra preconditions for lifecycle types: fn(type, params, app, phase) raises ApiError;
        # phase is "request" or "approve" (§12.22 dependencies, host ports, settings values).
        self.app_checks: list[Callable[[str, dict, AppEntry, str], None]] = []
        # Checks on the app id alone, before the catalog is asked: fn(type, app_id) raises ApiError.
        # A native built-in has no catalog entry, and removing it must still be 409, not 404 (#603).
        self.id_checks: list[Callable[[str, str], None]] = []
        # Feature-owned actor/type policies. Side-effect-free checks must return
        # True explicitly; evaluate before filing or replaying any request.
        self.request_checks: list[Callable[[Principal, str], bool]] = []
        # Run after every lifecycle dispatch with (action, outcome); a failing hook is logged and skipped.
        self.after_dispatch: list[Callable[[Action, str], None]] = []
        # §12.22: (app, merged settings by name, changed names) -> (ConfigMap data keyed by env name,
        # whether the workloads restart). Set when an app declares spec.settings.
        self.settings_transform: Callable[[AppEntry, dict, dict], tuple[dict, bool]] | None = None
        # §12.22 dependency network paths: app -> ([{from, to, provider, port, protocol, requirement}],
        # plan warnings). Set by the app store.
        self.dependency_paths: Callable[[AppEntry], tuple[list[dict], list[str]]] | None = None
        # CORE-FABRIC-4 (#171): app -> placement.schedule (the machine to pin to, the GPU request) or None.
        # Set by the app store; hashed into the plan so an approval covers exactly that machine.
        self.placement: Callable[[AppEntry], dict | None] | None = None
        # #723: the owner's motion lockout (physical.py). True refuses every physical request and
        # approval; a failing read counts as locked.
        self.motion_lockout: Callable[[], bool] = lambda: False

    def register_type(self, action_type: str, spec: FeatureAction) -> None:
        if action_type in APP_CLAIMS or action_type in self.feature_types or action_type in self.handlers:
            raise ValueError(f"action type {action_type} is already registered")
        if spec.risk not in ("read", "write", "sensitive", "destructive", "actuate"):
            raise ValueError(f"{action_type}: unknown risk class {spec.risk!r}")
        from .automation import registry  # imported late: the registry imports ActionType from here

        if spec.physical:
            if spec.requesters & {"automation", "policy"}:
                raise ValueError(f"{action_type}: a physical type is never requested by an automation or policy")
            registry.mark_physical(action_type)
        registry.register_feature(action_type, spec.risk, automation="automation" in spec.requesters)
        self.feature_types[action_type] = spec

    def can_file(self, action_type: str) -> bool:
        """True when a request of this type can be filed here (so a standing approval can fire on it)."""
        return action_type in APP_CLAIMS or action_type in self.handlers or action_type in self.feature_types

    def is_physical(self, action_type: str) -> bool:
        spec = self.feature_types.get(action_type)
        return spec is not None and spec.physical

    def _locked(self) -> bool:
        try:
            return bool(self.motion_lockout())
        except Exception:  # fail closed: a lockout that cannot be read is on
            log.exception("motion lockout read failed")
            return True

    def _refuse_if_locked(self) -> None:
        if self._locked():
            raise ApiError(409, "conflict", "the owner's motion lockout is on: no physical action is filed or approved",
                           reason="motion_lockout")

    def _physical_plan(self, action_type: str, spec: FeatureAction, params: dict, risk: str) -> tuple[dict, str]:
        try:
            card = approval_card(risk, True, spec.limits_for(params) if spec.limits_for else None,
                                 spec.preview_for(params) if spec.preview_for else None)
        except ValueError as exc:
            raise ApiError(422, "conflict", f"{action_type}: {exc}"[:500]) from None
        return physical_plan(action_type, params, card)

    def _check_physical_approval(self, principal: Principal, a: Action, spec: FeatureAction,
                                 plan_sha256: str | None, extra: ApprovalInput, standing: dict | None) -> None:
        """The extra rules of a physical action (#723), checked before anything is claimed."""
        if standing is not None or not principal.is_owner:
            raise self._deny(principal, f"approve physical action {a.type} (only a person, never a standing approval)", a.id)
        self._refuse_if_locked()
        if not extra.webauthn:
            raise ApiError(401, "unauthenticated", f"{a.type} moves something physical: approve it with your passkey",
                           reason="step_up_required")
        if extra.hold_ms is None or extra.hold_ms < HOLD_MIN_MS:
            raise ApiError(409, "conflict", f"{a.type} moves something physical: hold to approve ({HOLD_MIN_MS} ms)",
                           reason="hold_required")
        if plan_sha256 is None:
            raise ApiError(409, "stale_precondition", "send plan_sha256 so the approval is bound to the plan you read",
                           reason="plan_unchecked")
        _, fresh = self._physical_plan(a.type, spec, a.params, a.risk or spec.risk)
        if a.plan_sha256 is None or plan_sha256 != a.plan_sha256 or fresh != a.plan_sha256:
            raise ApiError(409, "stale_precondition", "the parameters or limits changed since the request; ask again",
                           reason="plan_changed")

    # ---- handlers for non-app action types ---------------------------------------------
    def register_handler(self, action_type: str, handler: ActionHandler) -> None:
        if action_type in APP_CLAIMS or action_type in self.handlers or action_type in self.feature_types:
            raise ValueError(f"action type {action_type!r} already has a handler")
        self.handlers[action_type] = handler

    def file(self, action_type: str, params: dict, requested_by: dict, *, expires_at: datetime,
             idempotency_key: str, audit_principal: dict | None = None) -> Action:
        """File an action of a registered handler type straight into awaiting_approval.

        For requests that do not come through POST /v1/actions (a joining node, §12.11). The
        caller has already checked who may ask; approval still needs an owner.
        """
        if action_type not in self.handlers:
            raise ValueError(f"no handler for action type {action_type!r}")
        from .automation import registry  # imported late: the registry imports ActionType from here

        now = self.clock()
        check_pending_lifetime(requested_by.get("kind"), expires_at, now)
        risk = registry.risk_of(action_type, params) if registry.known(action_type) else None
        # A requester that read third-party text is tainted here as on every other path, and a request
        # a standing approval could cover carries a plan, so an approval is bound to these parameters.
        # Only the fabric's node.join request skips a node's default exposure; any other request a
        # node files counts as exposed, as on every other path (#1133 fails closed).
        kind = requested_by.get("kind")
        if kind == "node" and action_type == "node.join":
            kind = NODE_JOIN_REQUESTER
        taint = self.taint.get(str(requested_by.get("id") or ""), kind)
        plan, plan_sha = None, None
        if taint is not None or registry.policy_may_cover(action_type, params, risk) is None:
            plan, plan_sha = feature_plan(action_type, params)
            if taint is not None:
                plan = {**plan, PLAN_KEY: taint.note()}
        action = Action(
            id=new_action_id(), type=action_type, params=params, state="requested",
            requested_by=requested_by, idempotency_key=idempotency_key,
            created_at=now, updated_at=now, expires_at=utc(expires_at),
            # #723: the §12.5 risk class, so the approval card asks for hold on a destructive type.
            risk=risk, plan=plan, plan_sha256=plan_sha,
        )
        stored, created = self.repo.create(action)
        if not created:
            raise ApiError(409, "conflict", "this request was already filed")
        self.audit.append("action.requested", audit_principal, stored.id, {
            "type": stored.type, "params": stored.params, "expires_at": iso(stored.expires_at),
            "requested_by": requested_by.get("id"), **({"tainted_by": list(taint.sources)} if taint else {}),
        })
        moved = self.repo.transition(stored.id, {"requested"}, "awaiting_approval", self.clock())
        self.audit.append("action.awaiting_approval", None, stored.id, {})
        filed = moved or stored
        if self._standing_approve(filed) is not None:  # an owner-set rule accepted it: return the decided row
            return self.repo.get(stored.id) or filed
        return filed

    def finish(self, action_id: str, outcome: str, message: str, result: dict | None = None, *,
               from_states: frozenset[str] = frozenset({"dispatched"})) -> Action | None:
        """Complete a dispatched handler action (succeeded | failed | outcome_unknown). Idempotent.

        A handler that reconciles at startup passes from_states={"accepted", "dispatched"} to close
        an approval a crash interrupted (as outcome_unknown, never a retry).
        """
        body = {"outcome": outcome, "message": message, **(result or {})}
        final = self.repo.transition(action_id, set(from_states), outcome, self.clock(), result=body)
        if final is not None:
            self.audit.append(f"action.{outcome}", None, action_id, {"message": message})
        return final

    # ---- helpers -------------------------------------------------------------------------
    def _deny(self, principal: Principal, what: str, action_id: str | None = None) -> ApiError:
        self.audit.append(
            "authz.denied", principal.as_dict(), action_id, {"attempted": what, "reason": "permission_denied"}
        )
        return ApiError(403, "permission_denied", f"{principal.kind}/{principal.role} may not {what}")

    def _check_request(self, principal: Principal, action_type: str) -> None:
        if not principal.may_request_action(action_type) or any(
            check(principal, action_type) is not True for check in self.request_checks
        ):
            raise self._deny(principal, f"request {action_type}")

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
        data = {"type": req.type, "params": _params_of(req), "idempotency_key": req.idempotency_key}
        return self._audited(
            principal, "request action", None, data, lambda: self._create(principal, req, reason)
        )

    def deny(self, principal: Principal, action_id: str) -> dict:
        out = self._audited(principal, "deny action", action_id, {}, lambda: self._cancel(principal, action_id))
        if self.app_secrets is not None:  # values entered for a denied change are not kept
            self.app_secrets.discard(action_id)
        return out

    def approve(
        self, principal: Principal, action_id: str, plan_sha256: str | None = None, strict: bool = False,
        extra: ApprovalInput | None = None,
    ) -> dict:
        """strict=True (the client sent OneMind-API-Version: 1) refuses an approval without plan_sha256."""
        return self._audited(
            principal, "approve action", action_id, {},
            lambda: self._approve(principal, action_id, plan_sha256, strict, extra=extra or ApprovalInput()),
        )

    def request_configure(
        self, principal: Principal, params: dict, idempotency_key: str, expires_at: datetime,
        reason: str | None = None,
    ) -> tuple[dict, bool]:
        """File an app.configure whose params list secret changes (routers/secrets.py, owner only).

        POST /v1/actions and the MCP tool cannot carry these params (ActionParams forbids them),
        and this path is never offered to a standing approval: only a person approves it.
        """
        data = {"type": "app.configure", "params": params, "idempotency_key": idempotency_key}
        return self._audited(
            principal, "request action", None, data,
            lambda: self._create_configure(principal, params, idempotency_key, expires_at, reason),
        )

    def _create_configure(
        self, principal: Principal, params: dict, idempotency_key: str, expires_at: datetime, reason: str | None
    ) -> tuple[dict, bool]:
        if not principal.is_owner:
            raise self._deny(principal, "request app.configure with secrets")
        existing = self.repo.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            same = (
                existing.type == "app.configure" and existing.params == params
                and existing.requested_by.get("id") == principal.id and existing.expires_at == utc(expires_at)
            )
            if not same:
                raise ApiError(409, "conflict", "idempotency_key was already used for a different request")
            return self.expire_if_due(existing).to_json(), False
        now = self.clock()
        expires = utc(expires_at)
        if expires <= now:
            raise ApiError(409, "expired", "expires_at is already in the past")
        check_pending_lifetime(principal.kind, expires, now)
        app, problem = self._precondition("app.configure", params["app_id"])
        if app is None:
            raise ApiError(404, "not_found", problem or "unknown app")
        if problem:
            raise ApiError(409, "stale_precondition", problem)
        action = Action(
            id=new_action_id(), type="app.configure", params=params, state="requested",
            requested_by={"id": principal.id, "kind": principal.kind}, idempotency_key=idempotency_key,
            created_at=now, updated_at=now, expires_at=expires, risk=lc.TYPES["app.configure"].risk,
        )
        stored, created = self.repo.create(action)
        if not created:  # lost an insert race on the same idempotency key
            return self.expire_if_due(stored).to_json(), False
        self.audit.append(
            "action.requested", principal.as_dict(), stored.id,
            {"type": stored.type, "params": stored.params, "expires_at": iso(stored.expires_at),
             "requested_by": principal.id, "risk": lc.TYPES["app.configure"].risk,
             **({"reason": reason} if reason else {})},
        )
        moved = self.repo.transition(stored.id, {"requested"}, "awaiting_approval", self.clock())
        self.audit.append("action.awaiting_approval", None, stored.id, {})
        return (moved or stored).to_json(), True

    # ---- plans (contract §12.4) -----------------------------------------------------------
    def render(self, action_type: str, params: dict) -> tuple[AppEntry | None, dict | None, str | None]:
        """(app, rendered plan with plan_sha256, problem). Pure: nothing is filed or run."""
        app = self.catalog.get(params["app_id"])
        if app is None:
            return None, None, f"app {params['app_id']!r} is not in the catalog"
        state = self.repo.get_app_state(app.id)
        status = state.status if state else None
        network = None
        if self.dependency_paths is not None:
            network = self.dependency_paths(app)
        sched = self.placement(app) if self.placement is not None and action_type in ("app.install", "app.update") else None
        rendered = lc.render_plan(action_type, params, app, self.repo.get_runtime(app.id), status, network,
                                  streams.plan_entries(app.id, app.manifest), sched=sched)
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
        self._check_request(principal, req.type)
        if req.type not in APP_CLAIMS:
            return self._create_feature(principal, req, reason)
        if not principal.can_request_actions:
            raise self._deny(principal, "request actions")
        if not lc.TYPES[req.type].agent_may_request and not principal.is_owner:
            # Deleting data is the owner's own act: an agent can propose a removal, never this.
            raise self._deny(principal, f"request {req.type}")
        params = _params_of(req)
        existing = self.repo.get_by_idempotency_key(req.idempotency_key)
        if existing is not None:
            return self._replay(principal, req, params, existing)
        now = self.clock()
        expires_at = utc(req.expires_at)
        if expires_at <= now:
            raise ApiError(409, "expired", "expires_at is already in the past")
        check_pending_lifetime(principal.kind, expires_at, now)
        self._check_pending_cap(principal)
        for check in self.id_checks:
            check(req.type, params["app_id"])
        app, problem = self._precondition(req.type, params["app_id"])
        if app is None:
            raise ApiError(404, "not_found", problem or "unknown app")
        if problem:
            raise ApiError(409, "stale_precondition", problem)
        for hook in self.app_checks:
            hook(req.type, params, app, "request")
        _, rendered, _ = self.render(req.type, params)
        if req.plan_sha256 is not None and req.plan_sha256 != rendered["plan_sha256"]:
            raise ApiError(
                409, "stale_precondition", "the plan changed since you read it; read it again",
                reason="plan_changed",
            )
        taint = self.taint.get(principal.id, principal.kind)
        if taint is not None:
            self._tainted_target_check(principal, app)
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
            # The taint note sits beside the plan, not inside the fingerprint: the fingerprint says
            # what would change; the note says where the requester's context came from.
            plan={**rendered["plan"], PLAN_KEY: taint.note()} if taint else rendered["plan"],
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
                **({"tainted_by": list(taint.sources)} if taint else {}),
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
        if plan_taint(a.plan):  # AIG-04: a requester that read third-party text always waits for a person
            return None
        if (a.plan or {}).get("network_paths"):  # §12.22: opening a path between apps needs a person
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

    @staticmethod
    def _check_tainted_approval(a: Action, plan_sha256: str | None, standing: dict | None,
                                fresh: str | None = None) -> None:
        """AIG-04: the requester read third-party text. Only a person, approving this exact plan.

        fresh: the fingerprint rendered again now, when the caller has one; it must still match.
        """
        if standing is not None:
            raise ApiError(409, "stale_precondition", "a request from a tainted agent needs a person",
                           reason="tainted")
        if plan_sha256 is None:
            raise ApiError(
                409, "stale_precondition",
                "this agent read third-party text before asking: send plan_sha256 to approve exactly this plan",
                reason="plan_unchecked",
            )
        if a.plan_sha256 is None or plan_sha256 != a.plan_sha256 or (fresh is not None and fresh != a.plan_sha256):
            raise ApiError(409, "stale_precondition", "the approval names a different plan than the one requested",
                           reason="plan_changed")

    def _tainted_target_check(self, principal: Principal, app: AppEntry) -> None:
        """A tainted agent may only ask about apps the app's own aiPolicy shows to AI (#165, deny by default)."""
        try:
            ai_policy.require(app.manifest, ai_policy.CATALOG)
        except ai_policy.AIPolicyDenied as exc:
            raise self._deny(
                principal, f"request an action on {app.id!r} after reading third-party text: {exc.decision.reason}")

    def _check_pending_cap(self, principal: Principal) -> None:
        for check in self.requester_checks:
            check(principal)
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
        standing: dict | None = None, extra: ApprovalInput | None = None,
    ) -> dict:
        extra = extra or ApprovalInput()
        if standing is None and not principal.is_owner:
            raise self._deny(principal, "approve actions", action_id)
        a = self.expire_if_due(self._get(action_id))
        if a.state == "expired":
            raise ApiError(409, "expired", "action expired before approval")
        if a.state != "awaiting_approval":
            raise ApiError(409, "conflict", f"action is {a.state}, not awaiting_approval")
        if a.type in self.feature_types:
            spec = self.feature_types[a.type]
            if spec.owner_passkey:
                if standing is not None or a.requested_by.get("id") != principal.id:
                    raise self._deny(principal, "approve this owner's security setting", a.id)
                if not extra.webauthn:
                    raise ApiError(401, "unauthenticated", "approve with your passkey", reason="step_up_required")
            facts = None
            if spec.physical:
                self._check_physical_approval(principal, a, spec, plan_sha256, extra, standing)
                facts = {"physical": True, "hold_ms": extra.hold_ms, "approval": "passkey", "plan_sha256": a.plan_sha256}
            if plan_taint(a.plan):
                fresh = None if spec.physical else feature_plan(a.type, a.params)[1]
                self._check_tainted_approval(a, plan_sha256, standing, fresh)
                facts = {**(facts or {}), "tainted": True, "plan_sha256": a.plan_sha256}
            return self._approve_feature(principal, a, spec, standing, facts)
        handler = self.handlers.get(a.type)
        if handler is not None:
            if plan_taint(a.plan):
                self._check_tainted_approval(a, plan_sha256, standing, feature_plan(a.type, a.params)[1])
            return self._approve_handled(principal, a, handler, standing)
        if a.type not in APP_CLAIMS:
            raise ApiError(409, "conflict", f"no handler for action type {a.type!r} is running")

        # Check current conditions again: the world may have changed since the request. The claim
        # on the app is made atomically with "accepted", so two actions for one app cannot both
        # pass. A stale action stays in awaiting_approval (the owner may deny it or let it expire).
        app_id = a.params["app_id"]
        app = self.catalog.get(app_id)
        claim, allowed, allow_absent = APP_CLAIMS[a.type]
        now = self.clock()
        if app is not None:
            for hook in self.app_checks:  # the world may have changed since the request
                hook(a.type, a.params, app, "approve")
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
        if plan_taint(a.plan):
            self._check_tainted_approval(a, plan_sha256, standing)
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
        if a.type == "app.install" and app is not None:
            self._check_licence_class(principal, a, app, standing, extra)
        override = None
        if extra.override is not None and a.type != "app.install":
            raise ApiError(422, "conflict", "an owner override applies only to app.install")
        if a.type in ("app.install", "app.update") and app is not None and self.require_scan:
            # Contract 9.4: a malware hit or a human review sets metadata.tier to blocked, and
            # nothing lifts it but a human. The scan record alone must not override it, and
            # neither does the F-7 owner override: it never applies to a blocked tier.
            if (app.manifest.get("metadata") or {}).get("tier") == "blocked":
                raise ApiError(
                    409, "stale_precondition", f"app {app_id!r} is tier blocked; a human has to review it first"
                )
            problem = scan_problem(app_id, app.scan, now)
            if problem and extra.override is None:  # §10.3: nothing unscanned runs; stays awaiting_approval
                raise ApiError(409, "stale_precondition", problem)
            if problem:  # F-7: refuses (and audits) unless the box allows it and every check passes
                if self.owner_override is None:
                    raise self._deny(principal, "override a failed scan (no owner override on this gateway)", a.id)
                override = self.owner_override.check(principal, a, app, problem, extra)
        prepared = None
        if app is not None and self.app_secrets is not None:
            prepared = self.app_secrets.prepare(a, app, extra.sealed)  # refuses before anything is claimed
        elif extra.sealed is not None:
            raise ApiError(422, "conflict", "this gateway has no secret store")
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
        unchecked = {"plan_unchecked": True} if plan_sha256 is None and a.plan_sha256 is not None else {}
        self.audit.append(
            "action.approved", principal.as_dict(), a.id,
            {"type": a.type, "params": a.params, **ids, **unchecked, **({"owner_override": True} if override else {})},
        )
        if override is not None:
            self.owner_override.record(principal, a, override)

        try:
            out = self._dispatch(a, app, ids, prior, principal, prepared, override)
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

    def _check_licence_class(self, principal: Principal, a: Action, app: AppEntry, standing: dict | None,
                             extra: ApprovalInput) -> None:
        """#173: only a green licence class (L1 permissive, L2 copyleft) installs on an ordinary approval.
        blocked and unknown need the owner, in person, to type the app id as accept_licence. A standing
        approval never covers it, and nothing lifts it for an agent. Refusals are audited."""
        cls = app.licence_class
        if cls in GREEN_LICENCE_CLASSES:
            return
        if standing is not None or not principal.is_owner:
            raise self._deny(principal, f"approve app.install for {a.params['app_id']!r} (licence class {cls}: only the owner, in person)", a.id)
        if extra.accept_licence != app.id:
            self.audit.append("authz.denied", principal.as_dict(), a.id,
                              {"attempted": "approve app.install", "app_id": app.id, "licence_class": cls,
                               "reason": "licence_unconfirmed"})
            raise ApiError(
                409, "stale_precondition",
                f"app {app.id!r} has licence class {cls}, which is not green: send accept_licence with the app id "
                "to confirm you accept its licence", reason="licence_unconfirmed",
            )
        self.audit.append("app.licence_accepted", principal.as_dict(), a.id, {"app_id": app.id, "licence_class": cls})

    def _approve_handled(self, principal: Principal, a: Action, handler: ActionHandler,
                         standing: dict | None = None) -> dict:
        problem = handler.recheck(a)
        if problem:
            raise ApiError(409, "stale_precondition", problem)
        now = self.clock()
        accepted = self.repo.transition(
            a.id, {"awaiting_approval"}, "accepted", now, decided_by=principal.as_dict(), decided_at=now
        )
        if accepted is None:
            raise ApiError(409, "conflict", "action was decided concurrently")
        ids = {"requested_by": a.requested_by.get("id"), "approved_by": principal.id, **(standing or {})}
        self.audit.append("action.approved", principal.as_dict(), a.id, {"type": a.type, "params": a.params, **ids})
        dispatched = self.repo.transition(a.id, {"accepted"}, "dispatched", self.clock())
        if dispatched is None:
            self._mark_outcome_unknown(accepted, "accepted action could not move to dispatched")
            return self._get(a.id).to_json()
        self.audit.append("action.dispatched", None, a.id, {"executor": f"handler:{a.type}", **ids})
        try:
            result = handler.dispatch(dispatched)
        except Exception as exc:  # unknown effect: never retry automatically
            log.exception("action handler crashed")
            result = ExecResult("outcome_unknown", f"handler error: {exc.__class__.__name__}")
        if result is not None:
            self.finish(a.id, result.outcome, result.message)
        return self._get(a.id).to_json()

    def _dispatch(
        self, a: Action, app: AppEntry, ids: dict, prior: str | None = None, approver: Principal | None = None,
        prepared=None, override: dict | None = None,
    ) -> dict:
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
            if a.type == "app.remove":
                for hook in self.install_hooks:
                    if hook.removing is not None:
                        hook.removing(app, a)
            if a.type == "app.install":
                for hook in self.install_hooks:
                    hook_steps += [{"hook": hook.name, **st} for st in hook.prepare(app, a)]
        except Exception as exc:  # nothing was applied yet: the install fails cleanly
            log.exception("install hook failed")
            result = ExecResult("failed", f"install preparation failed: {exc}"[:500], hook_steps)
        else:
            # The approved values become current only now, after acceptance (appsecrets/service.py).
            secrets = self.app_secrets.commit(a, app, prepared, approver) if prepared is not None else []
            ctx = self._exec_context(a, app, ids)
            ctx = dataclasses.replace(ctx, secrets=tuple(secrets))
            token = lc.set_progress_callback(self._progress_reporter(a))
            try:
                if self.workload_credential is not None:
                    credential = self.workload_credential(a, app)
                    if credential is not None:
                        if agent is not None:
                            raise ValueError("a workload cannot have two principal kinds")
                        agent = credential
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
        stored_result = result.to_json()
        if override is not None:  # shown on the action itself, not only in the audit log
            stored_result["owner_override"] = {"mark": override["mark"], "approved_by": ids["approved_by"]}
        final = self.repo.transition(a.id, {"dispatched"}, result.outcome, self.clock(), result=stored_result)
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
        self._after(a, result.outcome)
        return (final or self._get(a.id)).to_json()

    def _after(self, a: Action, outcome: str) -> None:
        for hook in self.after_dispatch:
            try:
                hook(a, outcome)
            except Exception:  # a follow-up must never change the recorded outcome
                log.exception("after-dispatch hook %r failed for %s", hook, a.id)

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
        restart = True
        if a.type == "app.configure" and self.settings_transform is not None:
            settings, restart = self.settings_transform(app, settings, a.params.get("settings") or {})
        grant = None
        if a.type == "app.install" and self.credentials is not None:
            grant, generated = self.credentials.ensure(app, self.clock())
            if generated:  # the value is never logged, only the fact
                self.audit.append("app.credentials.generated", None, a.id, {"app_id": app.id, **ids})
        paths: tuple[tuple[str, int], ...] = ()
        sync = False
        if self.dependency_paths is not None and a.type in ("app.install", "app.update", "app.configure", "app.remove"):
            # Exactly the paths of the plan the owner approved (re-rendered and hash-checked just
            # before dispatch). app.remove opens nothing and closes all.
            if a.type != "app.remove":
                paths = tuple((p["provider"], p["port"]) for p in (a.plan or {}).get("network_paths") or ())
            sync = a.type != "app.install" or bool(paths)  # a fresh install has nothing to close
        sched = self.placement(app) if self.placement is not None and a.type in ("app.install", "app.update") else None
        return lc.ExecContext(params=dict(a.params), settings=settings, credentials=grant, restart=restart,
                              dependency_paths=paths, dependency_sync=sync, placement=sched)

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
            if a.type == "app.update":
                # A version published without spec.agent must not leave the old credential alive.
                self._revoke_agent(a, "agent no longer declared")
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
        return AgentSecret(spec.secret, spec.principal_id, gateway_url=self.gateway_url, token=token,
                           ca_pem=self.gateway_ca())

    def _revoke_agent(self, a: Action, reason: str) -> None:
        principal_id = f"agent:{a.params['app_id']}"
        if self.agent_forgotten is not None:
            try:
                self.agent_forgotten(principal_id)
            except Exception:  # best effort: the token is revoked either way
                log.exception("forgetting the declared inputs of %s failed", principal_id)
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
            if a.type in SELF_RECONCILED_TYPES:
                # Handler types (node.join) finish on their own schedule: their module reconciles
                # them when it registers (create_app runs this before the routers register).
                continue
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
        elif a.type == "app.configure" and a.params.get("settings"):  # a secrets-only change has none
            self.repo.set_runtime(app_id, now, settings={**(runtime.settings if runtime else {}), **a.params["settings"]})


    # ---- feature-owned action types (contract §12.5) -------------------------------------------
    def request_feature(
        self, principal: Principal, action_type: str, params: dict, *, idempotency_key: str,
        expires_at: datetime, reason: str | None = None, audit_extra: dict | None = None,
        pending_cap: bool = False,
    ) -> tuple[dict, bool]:
        """File a feature action: same ledger, idempotency and audit as POST /v1/actions.

        pending_cap applies the per-requester limit on requests awaiting approval that POST /v1/actions
        enforces (_check_pending_cap), for routes an agent can call in a loop.

        params are the feature's already-validated parameters (never secrets: they are stored and
        audited). audit_extra adds facts to the action.requested line, e.g. credentials: provided.
        """
        spec = self.feature_types[action_type]
        data = {"type": action_type, "params": params, "idempotency_key": idempotency_key}

        def create() -> tuple[dict, bool]:
            return self._file_feature(
                principal, action_type, spec, params, idempotency_key, expires_at, reason, audit_extra,
                pending_cap=pending_cap)

        return self._audited(principal, f"request {action_type}", None, data, create)

    def _create_feature(self, principal: Principal, req: ActionRequest, reason: str | None) -> tuple[dict, bool]:
        """POST /v1/actions for a type a feature registered with params_model (contract §12.22)."""
        spec = self.feature_types.get(req.type)
        if spec is None or spec.params_model is None:
            raise ApiError(422, "conflict", f"request failed validation: type: unknown action type {req.type!r}")
        if not principal.can_request_actions or (not principal.is_owner and principal.kind not in spec.requesters):
            raise self._deny(principal, f"request {req.type}")  # before anything is validated or filed
        raw = req.params if isinstance(req.params, dict) else req.params.model_dump(exclude_none=True)
        try:
            params = spec.params_model.model_validate(raw).model_dump(exclude_none=True)
        except ValidationError as exc:
            problems = "; ".join(
                f"params.{'.'.join(str(x) for x in e.get('loc', []))}: {e.get('msg', '')}" for e in exc.errors())
            raise ApiError(422, "conflict", f"request failed validation: {problems}"[:1000]) from exc
        existing = self.repo.get_by_idempotency_key(req.idempotency_key)
        if existing is None:
            self._check_pending_cap(principal)
            if spec.check_request is not None:
                spec.check_request(params, principal)
        return self._file_feature(
            principal, req.type, spec, params, req.idempotency_key, req.expires_at, reason, None)

    def _file_feature(
        self, principal: Principal, action_type: str, spec: FeatureAction, params: dict,
        idempotency_key: str, expires_at: datetime, reason: str | None, audit_extra: dict | None,
        pending_cap: bool = False,
    ) -> tuple[dict, bool]:
        self._check_request(principal, action_type)
        if not principal.can_request_actions or (not principal.is_owner and principal.kind not in spec.requesters):
            raise self._deny(principal, f"request {action_type}")
        if spec.physical and principal.kind not in ("person", "agent"):  # never an automation or plugin
            raise self._deny(principal, f"request physical action {action_type}")
        existing = self.repo.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            if existing.type != action_type or existing.params != params or existing.requested_by.get("id") != principal.id:
                raise ApiError(409, "conflict", "idempotency_key was already used for a different request")
            return self.expire_if_due(existing).to_json(), False
        if pending_cap:
            self._check_pending_cap(principal)  # the per-requester cap, plus the requester checks below
        else:
            for check in self.requester_checks:  # cancel/budget hold for every filing route, not only POST /v1/actions
                check(principal)
        now = self.clock()
        exp = utc(expires_at)
        if exp <= now:
            raise ApiError(409, "expired", "expires_at is already in the past")
        check_pending_lifetime(principal.kind, exp, now)
        risk = spec.risk_for(params) if spec.risk_for else spec.risk
        if risk not in {"read", "write", "sensitive", "destructive", "actuate"}:
            raise ApiError(422, "conflict", "feature returned an invalid risk class")
        plan, plan_sha = None, None
        if spec.physical:
            self._refuse_if_locked()
            plan, plan_sha = self._physical_plan(action_type, spec, params, risk)
        taint = self.taint.get(principal.id, principal.kind)
        if taint is not None:
            # AIG-04: the same rules as an app action. The app it names must be visible to AI, the
            # card carries the note (beside the plan, outside the fingerprint), and the plan is
            # fingerprinted so the owner's approval is bound to exactly these parameters.
            target = self.catalog.get(params["app_id"]) if isinstance(params.get("app_id"), str) else None
            if target is not None:
                self._tainted_target_check(principal, target)
            if plan is None:
                plan, plan_sha = feature_plan(action_type, params)
            plan = {**plan, PLAN_KEY: taint.note()}
        if plan is None and self._rule_could_cover(action_type, params, risk):
            plan, plan_sha = feature_plan(action_type, params)  # an approval by rule is bound to these params
        action = Action(
            id=new_action_id(), type=action_type, params=params, state="requested",
            requested_by={"id": principal.id, "kind": principal.kind}, idempotency_key=idempotency_key,
            created_at=now, updated_at=now, expires_at=exp,
            risk=risk, plan=plan, plan_sha256=plan_sha,  # #723: stored so the approval card can say hold
        )
        stored, created = self.repo.create(action)
        if not created:
            return self.expire_if_due(stored).to_json(), False
        self.audit.append("action.requested", principal.as_dict(), stored.id, {
            "type": action_type, "params": params, "risk": risk, "expires_at": iso(exp),
            "requested_by": principal.id, **({"reason": reason} if reason else {}), **(audit_extra or {}),
            **({"tainted_by": list(taint.sources)} if taint else {}),
            **({"physical": True, "plan_sha256": plan_sha} if spec.physical else {}),
        })
        moved = self.repo.transition(stored.id, {"requested"}, "awaiting_approval", self.clock())
        self.audit.append("action.awaiting_approval", None, stored.id, {})
        return self._standing_approve(moved or stored) or (moved or stored).to_json(), True

    @staticmethod
    def _rule_could_cover(action_type: str, params: dict, risk: str) -> bool:
        from .automation import registry  # imported late: the registry imports ActionType from here

        return registry.policy_may_cover(action_type, params, risk) is None

    def _approve_feature(
        self, principal: Principal, a: Action, spec: FeatureAction, standing: dict | None = None,
        facts: dict | None = None,
    ) -> dict:
        if spec.risk_for and a.risk != spec.risk_for(a.params):
            raise ApiError(409, "stale_precondition", "the action risk changed after the request")
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
                          {"type": a.type, "params": a.params, "risk": a.risk or spec.risk, **ids, **(facts or {})})
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


def _params_of(req: ActionRequest) -> dict:
    return dict(req.params) if isinstance(req.params, dict) else req.params.model_dump(exclude_none=True)


def _detail(v: dict) -> dict:
    where = f"{v.get('kind')}/{v.get('name')}" + (f" {v['path']}" if v.get("path") else "")
    return {"field": where, "problem": f"{v.get('rule')}: {v.get('message')}", "rule": v.get("rule")}
