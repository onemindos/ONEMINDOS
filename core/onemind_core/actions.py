"""Action service: request -> owner approval -> dispatch, with every decision audited.

This is where "AI never actuates without human approval" is enforced:
- owners and agents may *request* an action (it lands in awaiting_approval);
- only a person with role owner may approve or deny; an agent always gets 403 permission_denied;
- nothing reaches the executor until an approval has moved the action to accepted;
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

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from .audit import AuditLog
from .auth import Principal, new_agent_token, token_hash
from .catalog import APP_ID_RE, AppEntry, Catalog
from .errors import ApiError
from .executors import AgentSecret, ExecResult, Executor
from .scan import scan_problem
from .ledger import Action, ActionRepository, iso, new_action_id, utc

log = logging.getLogger("onemind.actions")

ActionType = Literal["app.install", "app.remove"]

# Per action type: (app status while it runs, app statuses it may start from, may the app have no
# state row at all). The same table drives the request-time check and the atomic claim at approval.
APP_CLAIMS: dict[str, tuple[str, frozenset[str], bool]] = {
    "app.install": ("installing", frozenset({"failed", "unknown"}), True),
    "app.remove": ("removing", frozenset({"installed", "failed", "unknown"}), False),
}


class ActionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_id: str = Field(min_length=1, max_length=59, pattern=APP_ID_RE.pattern)


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: ActionType
    params: ActionParams
    idempotency_key: str = Field(min_length=1, max_length=200)
    expires_at: AwareDatetime


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
    """

    risk: str
    run: Callable[["Action", Callable[[ExecResult], None]], None]
    requesters: frozenset[str] = frozenset({"person"})
    check: Callable[["Action"], str | None] | None = None


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
    ):
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

    def register_type(self, action_type: str, spec: FeatureAction) -> None:
        if action_type in APP_CLAIMS or action_type in self.feature_types:
            raise ValueError(f"action type {action_type} is already registered")
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
        return app, f"app {app_id!r} is {status or 'not installed'}"

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
            if e.status != 403:
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
        data = {"type": req.type, "params": req.params.model_dump(), "idempotency_key": req.idempotency_key}
        return self._audited(
            principal, "request action", None, data, lambda: self._create(principal, req, reason)
        )

    def deny(self, principal: Principal, action_id: str) -> dict:
        return self._audited(principal, "deny action", action_id, {}, lambda: self._cancel(principal, action_id))

    def approve(self, principal: Principal, action_id: str) -> dict:
        return self._audited(principal, "approve action", action_id, {}, lambda: self._approve(principal, action_id))

    def _create(self, principal: Principal, req: ActionRequest, reason: str | None = None) -> tuple[dict, bool]:
        if not principal.can_request_actions:
            raise self._deny(principal, "request actions")
        params = req.params.model_dump()
        existing = self.repo.get_by_idempotency_key(req.idempotency_key)
        if existing is not None:
            return self._replay(principal, req, params, existing)
        now = self.clock()
        expires_at = utc(req.expires_at)
        if expires_at <= now:
            raise ApiError(409, "expired", "expires_at is already in the past")
        app, problem = self._precondition(req.type, params["app_id"])
        if app is None:
            raise ApiError(404, "not_found", problem or "unknown app")
        if problem:
            raise ApiError(409, "stale_precondition", problem)
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
                "requested_by": principal.id,
                **({"reason": reason} if reason else {}),
            },
        )
        moved = self.repo.transition(stored.id, {"requested"}, "awaiting_approval", self.clock())
        self.audit.append("action.awaiting_approval", None, stored.id, {})
        return (moved or stored).to_json(), True

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

    def _approve(self, principal: Principal, action_id: str) -> dict:
        if not principal.is_owner:
            raise self._deny(principal, "approve actions", action_id)
        a = self.expire_if_due(self._get(action_id))
        if a.state == "expired":
            raise ApiError(409, "expired", "action expired before approval")
        if a.state != "awaiting_approval":
            raise ApiError(409, "conflict", f"action is {a.state}, not awaiting_approval")
        if a.type in self.feature_types:
            return self._approve_feature(principal, a, self.feature_types[a.type])

        # Check current conditions again: the world may have changed since the request. The claim
        # on the app is made atomically with "accepted", so two actions for one app cannot both
        # pass. A stale action stays in awaiting_approval (the owner may deny it or let it expire).
        app_id = a.params["app_id"]
        app = self.catalog.get(app_id)
        claim, allowed, allow_absent = APP_CLAIMS[a.type]
        now = self.clock()
        if a.type == "app.install" and app is not None and self.require_scan:
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
        self.audit.append("action.approved", principal.as_dict(), a.id, {"type": a.type, "params": a.params, **ids})

        try:
            return self._dispatch(a, app, ids)
        except Exception as exc:  # anything after accepted: the effect is unknown, never retry
            log.exception("dispatch interrupted")
            self._mark_outcome_unknown(a, f"dispatch error: {exc.__class__.__name__}")
            return self._get(a.id).to_json()

    def _dispatch(self, a: Action, app: AppEntry, ids: dict) -> dict:
        dispatched = self.repo.transition(a.id, {"accepted"}, "dispatched", self.clock())
        if dispatched is None:
            raise RuntimeError("accepted action could not move to dispatched")
        self.audit.append("action.dispatched", None, a.id, {"executor": self.executor.name, **ids})

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
            try:
                result = self.executor.run(a.type, app, agent=agent)
            except Exception as exc:  # unknown effect: never retry automatically
                log.exception("executor crashed")
                result = ExecResult("outcome_unknown", f"executor error: {exc.__class__.__name__}")
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

        final = self.repo.transition(a.id, {"dispatched"}, result.outcome, self.clock(), result=result.to_json())
        self._record_app_state(a, result.outcome)
        self.audit.append(
            f"action.{result.outcome}", None, a.id,
            {"executor": self.executor.name, "message": result.message, **ids},
        )
        return (final or self._get(a.id)).to_json()

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
            if st.status in ("installing", "removing"):
                self.repo.set_app_state(app_id, "unknown", now, st.action_id)
                self.audit.append(
                    "app.reconciled", None, st.action_id,
                    {"app_id": app_id, "from": st.status, "to": "unknown", "reason": "gateway restarted"},
                )

    def _record_app_state(self, a: Action, outcome: str) -> None:
        app_id, now = a.params["app_id"], self.clock()
        if outcome == "succeeded":
            self.repo.set_app_state(app_id, "installed" if a.type == "app.install" else None, now, a.id)
        elif outcome == "failed":
            self.repo.set_app_state(app_id, "failed", now, a.id)
        else:
            self.repo.set_app_state(app_id, "unknown", now, a.id)


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

    def _approve_feature(self, principal: Principal, a: Action, spec: FeatureAction) -> dict:
        problem = spec.check(a) if spec.check else None
        if problem:
            raise ApiError(409, "stale_precondition", problem)
        now = self.clock()
        accepted = self.repo.transition(
            a.id, {"awaiting_approval"}, "accepted", now, decided_by=principal.as_dict(), decided_at=now
        )
        if accepted is None:
            raise ApiError(409, "conflict", "action was decided concurrently")
        ids = {"requested_by": a.requested_by.get("id"), "approved_by": principal.id}
        self.audit.append("action.approved", principal.as_dict(), a.id,
                          {"type": a.type, "params": a.params, "risk": spec.risk, **ids})
        if self.repo.transition(a.id, {"accepted"}, "dispatched", self.clock()) is None:
            self._mark_outcome_unknown(a, "accepted action could not move to dispatched")
            return self._get(a.id).to_json()
        self.audit.append("action.dispatched", None, a.id, {"executor": f"feature:{a.type}", **ids})

        def finish(result: ExecResult) -> None:
            with self._finish_lock:
                final = self.repo.transition(
                    a.id, {"dispatched"}, result.outcome, self.clock(), result=result.to_json()
                )
                if final is not None:
                    self.audit.append(f"action.{result.outcome}", None, a.id,
                                      {"executor": f"feature:{a.type}", "message": result.message, **ids})

        try:
            spec.run(a, finish)
        except Exception as exc:  # the feature could not even start: the effect is unknown
            log.exception("feature action %s crashed", a.type)
            finish(ExecResult("outcome_unknown", f"feature error: {exc.__class__.__name__}"))
        return self._get(a.id).to_json()
