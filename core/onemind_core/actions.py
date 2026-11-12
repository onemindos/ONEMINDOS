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

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Literal, Protocol

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


class ActionTypeHandler(Protocol):
    """A feature-owned action type (contract §12.5; the registry DEV-API-7 generalises).

    The feature files requests through `ActionService.file` from its own request endpoint and
    the owner approves them through POST /v1/actions/{id}/approve like any other action.
    """

    def recheck(self, action: Action) -> str | None:
        """At approval: None when the action may run, else why it is stale (409, stays pending)."""

    def dispatch(self, action: Action) -> ExecResult | None:
        """After approval: the outcome, or None while it keeps running (state dispatched; the
        feature closes it later with `ActionService.finish`)."""


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
        # Feature-owned action types (one register_type call per type, from the feature's router).
        self.type_handlers: dict[str, ActionTypeHandler] = {}

    def register_type(self, action_type: str, handler: ActionTypeHandler) -> None:
        if action_type in APP_CLAIMS or action_type in self.type_handlers:
            raise ValueError(f"action type {action_type} is already registered")
        self.type_handlers[action_type] = handler

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

    # ---- feature-owned types --------------------------------------------------------------
    def file(
        self, principal: Principal, action_type: str, params: dict, idempotency_key: str,
        expires_at: datetime, reason: str | None = None,
    ) -> tuple[dict, bool]:
        """File a request of a registered feature type (the feature checked its own preconditions).

        Returns (action, created); created=False is an idempotent replay. Same rules as POST
        /v1/actions: only principals that may request, audited, lands in awaiting_approval.
        """
        if action_type not in self.type_handlers:
            raise ValueError(f"unregistered action type {action_type}")
        data = {"type": action_type, "params": params, "idempotency_key": idempotency_key}
        return self._audited(
            principal, "request action", None, data,
            lambda: self._file(principal, action_type, params, idempotency_key, expires_at, reason),
        )

    def _file(self, principal, action_type, params, idempotency_key, expires_at, reason) -> tuple[dict, bool]:
        if not principal.can_request_actions:
            raise self._deny(principal, "request actions")
        expires_at = utc(expires_at)

        def replay(existing: Action) -> tuple[dict, bool]:
            same = (
                existing.type == action_type and existing.params == params
                and existing.requested_by.get("id") == principal.id and existing.expires_at == expires_at
            )
            if not same:
                raise ApiError(409, "conflict", "idempotency_key was already used for a different request")
            return self.expire_if_due(existing).to_json(), False

        existing = self.repo.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            return replay(existing)
        now = self.clock()
        if expires_at <= now:
            raise ApiError(409, "expired", "expires_at is already in the past")
        action = Action(
            id=new_action_id(), type=action_type, params=params, state="requested",
            requested_by={"id": principal.id, "kind": principal.kind}, idempotency_key=idempotency_key,
            created_at=now, updated_at=now, expires_at=expires_at,
        )
        stored, created = self.repo.create(action)
        if not created:
            return replay(stored)
        self.audit.append(
            "action.requested", principal.as_dict(), stored.id,
            {"type": stored.type, "params": stored.params, "expires_at": iso(stored.expires_at),
             "requested_by": principal.id, **({"reason": reason} if reason else {})},
        )
        moved = self.repo.transition(stored.id, {"requested"}, "awaiting_approval", self.clock())
        self.audit.append("action.awaiting_approval", None, stored.id, {})
        return (moved or stored).to_json(), True

    def _approve_typed(self, principal: Principal, a: Action, handler: ActionTypeHandler) -> dict:
        problem = handler.recheck(a)
        if problem:  # the world changed since the request: stays awaiting_approval
            raise ApiError(409, "stale_precondition", problem)
        now = self.clock()
        moved = self.repo.transition(
            a.id, {"awaiting_approval"}, "accepted", now, decided_by=principal.as_dict(), decided_at=now
        )
        if moved is None:
            raise ApiError(409, "conflict", "action was decided concurrently")
        ids = {"requested_by": a.requested_by.get("id"), "approved_by": principal.id}
        self.audit.append("action.approved", principal.as_dict(), a.id, {"type": a.type, "params": a.params, **ids})
        dispatched = self.repo.transition(a.id, {"accepted"}, "dispatched", self.clock())
        executor = a.type.split(".", 1)[0]
        self.audit.append("action.dispatched", None, a.id, {"executor": executor, **ids})
        try:
            result = handler.dispatch(dispatched or moved)
        except Exception as exc:  # unknown effect: never retry automatically
            log.exception("%s dispatch crashed", a.type)
            result = ExecResult("outcome_unknown", f"dispatch error: {exc.__class__.__name__}")
        if result is None:  # still running; the feature finishes it
            return self._get(a.id).to_json()
        return self.finish(a.id, result.outcome, result.message, result.to_json()) or self._get(a.id).to_json()

    def finish(
        self, action_id: str, outcome: str, message: str, result: dict | None = None,
        from_states: frozenset[str] = frozenset({"dispatched"}),
    ) -> dict | None:
        """Close a feature-owned action (succeeded, failed, outcome_unknown) and audit it once."""
        result = result or {"outcome": outcome, "message": message}
        moved = self.repo.transition(action_id, set(from_states), outcome, self.clock(), result=result)
        if moved is None:
            return None
        self.audit.append(f"action.{outcome}", None, action_id, {"executor": moved.type.split(".", 1)[0], "message": message})
        return moved.to_json()

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
        handler = self.type_handlers.get(a.type)
        if handler is not None:
            return self._approve_typed(principal, a, handler)

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
        try:
            result = self.executor.run(a.type, app, agent=agent)
        except Exception as exc:  # unknown effect: never retry automatically
            log.exception("executor crashed")
            result = ExecResult("outcome_unknown", f"executor error: {exc.__class__.__name__}")
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
            if a.type not in APP_CLAIMS:
                continue  # a feature-owned type may still be running on a node: the feature reconciles it
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
