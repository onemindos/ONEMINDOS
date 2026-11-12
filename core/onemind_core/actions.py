"""Action service: request -> owner approval -> dispatch, with every decision audited.

This is where "AI never actuates without human approval" is enforced:
- owners and agents may *request* an action (it lands in awaiting_approval);
- only a person with role owner may approve or deny; an agent always gets 403 permission_denied;
- nothing reaches the executor until an approval has moved the action to accepted;
- an app.install is approved only for an app with a passing scan newer than 7 days (§10.3);
- an app that declares spec.agent gets its own agent principal at install, revoked at removal
  (§11.2), so the AI inside it can request actions but, like every agent, never approve them.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

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


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: ActionType
    params: ActionParams
    idempotency_key: str = Field(min_length=1, max_length=200)
    expires_at: AwareDatetime
    # Contract §12.4: the fingerprint of the plan the requester looked at. If the plan the gateway
    # renders now differs, the request is refused (409 stale_precondition, reason plan_changed).
    plan_sha256: str | None = Field(default=None, max_length=80)

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
        # Contract §12.1 / H-14: most actions one non-owner requester may have awaiting approval.
        # 0 = no cap. Set from the limits settings section (guard.py).
        self.max_pending_per_requester = 10

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
        return (moved or stored).to_json(), True

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
        return moved.to_json()

    def _approve(
        self, principal: Principal, action_id: str, plan_sha256: str | None = None, strict: bool = False
    ) -> dict:
        if not principal.is_owner:
            raise self._deny(principal, "approve actions", action_id)
        a = self.expire_if_due(self._get(action_id))
        if a.state == "expired":
            raise ApiError(409, "expired", "action expired before approval")
        if a.state != "awaiting_approval":
            raise ApiError(409, "conflict", f"action is {a.state}, not awaiting_approval")

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
            problem = scan_problem(app_id, app.scan, now)
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
        ids = {"requested_by": a.requested_by.get("id"), "approved_by": principal.id}
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
        ctx = self._exec_context(a, app, ids)
        token = lc.set_progress_callback(self._progress_reporter(a))
        try:
            result = self._run_executor(a, app, agent, ctx)
        except Exception as exc:  # unknown effect: never retry automatically
            log.exception("executor crashed")
            result = ExecResult("outcome_unknown", f"executor error: {exc.__class__.__name__}")
        finally:
            lc.reset_progress_callback(token)
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


def _detail(v: dict) -> dict:
    where = f"{v.get('kind')}/{v.get('name')}" + (f" {v['path']}" if v.get("path") else "")
    return {"field": where, "problem": f"{v.get('rule')}: {v.get('message')}", "rule": v.get("rule")}
