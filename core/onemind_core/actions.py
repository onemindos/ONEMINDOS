"""Action service: request -> owner approval -> dispatch, with every decision audited.

This is where "AI never actuates without human approval" is enforced:
- owners and agents may *request* an action (it lands in awaiting_approval);
- only a person with role owner may approve or deny; an agent always gets 403 permission_denied;
- nothing reaches the executor until an approval has moved the action to accepted;
- an app.install is approved only for an app with a passing scan newer than 7 days (§10.3);
- an app that declares spec.agent gets its own agent principal at install, revoked at removal
  (§11.2), so the AI inside it can request actions but, like every agent, never approve them;
- an app's declared secrets are entered by the owner with the approval itself (or filed as an
  app.configure the owner approves) and reach the executor only after acceptance (appsecrets/);
- an owner may approve an install whose scan failed only through the F-7 owner override, which
  is off unless ONEMIND_ALLOW_OWNER_OVERRIDE=1 and leaves a red audit mark (override.py).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from .audit import AuditLog
from .auth import Principal, new_agent_token, token_hash
from .catalog import APP_ID_RE, AppEntry, Catalog
from .errors import ApiError
from .executors import AgentSecret, ExecResult, Executor
from .scan import scan_problem
from .ledger import Action, ActionRepository, iso, new_action_id, utc

log = logging.getLogger("onemind.actions")

# What POST /v1/actions and the MCP request_action tool accept. app.configure is filed only by the
# secrets router (POST /v1/apps/{id}/secrets, owner): its params carry the change list.
ActionType = Literal["app.install", "app.remove"]

# Per action type: (app status while it runs, app statuses it may start from, may the app have no
# state row at all). The same table drives the request-time check and the atomic claim at approval.
APP_CLAIMS: dict[str, tuple[str, frozenset[str], bool]] = {
    "app.install": ("installing", frozenset({"failed", "unknown"}), True),
    "app.remove": ("removing", frozenset({"installed", "failed", "unknown"}), False),
    "app.configure": ("configuring", frozenset({"installed"}), False),
}
# App statuses that only exist while a dispatch runs; a restart finds them interrupted.
IN_FLIGHT = frozenset(claim for claim, _, _ in APP_CLAIMS.values())


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
    webauthn: bool = False


class ActionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_id: str = Field(min_length=1, max_length=59, pattern=APP_ID_RE.pattern)


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: ActionType
    params: ActionParams
    idempotency_key: str = Field(min_length=1, max_length=200)
    expires_at: AwareDatetime


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
        # Set by feature routers at registration (routers/secrets.py, routers/override.py).
        self.app_secrets: Any = None  # appsecrets.service.AppSecretsService
        self.owner_override: Any = None  # override.OwnerOverride

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
        return self.request(principal, req.type, req.params.model_dump(), req.idempotency_key, req.expires_at, reason)

    def request(
        self, principal: Principal, type_: str, params: dict, idempotency_key: str, expires_at: datetime,
        reason: str | None = None,
    ) -> tuple[dict, bool]:
        """create() for feature routers whose action params are more than {app_id} (app.configure)."""
        if type_ not in APP_CLAIMS:
            raise ValueError(f"unknown action type {type_}")
        data = {"type": type_, "params": params, "idempotency_key": idempotency_key}
        return self._audited(
            principal, "request action", None, data,
            lambda: self._create(principal, type_, params, idempotency_key, expires_at, reason),
        )

    def deny(self, principal: Principal, action_id: str) -> dict:
        out = self._audited(principal, "deny action", action_id, {}, lambda: self._cancel(principal, action_id))
        if self.app_secrets is not None:  # values entered for a denied change are not kept
            self.app_secrets.discard(action_id)
        return out

    def approve(self, principal: Principal, action_id: str, extra: ApprovalInput | None = None) -> dict:
        return self._audited(
            principal, "approve action", action_id, {}, lambda: self._approve(principal, action_id, extra or ApprovalInput())
        )

    def _create(
        self, principal: Principal, type_: str, params: dict, idempotency_key: str, expires_at: datetime,
        reason: str | None = None,
    ) -> tuple[dict, bool]:
        if not principal.can_request_actions:
            raise self._deny(principal, "request actions")
        existing = self.repo.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            return self._replay(principal, type_, params, expires_at, existing)
        now = self.clock()
        expires_at = utc(expires_at)
        if expires_at <= now:
            raise ApiError(409, "expired", "expires_at is already in the past")
        app, problem = self._precondition(type_, params["app_id"])
        if app is None:
            raise ApiError(404, "not_found", problem or "unknown app")
        if problem:
            raise ApiError(409, "stale_precondition", problem)
        action = Action(
            id=new_action_id(),
            type=type_,
            params=params,
            state="requested",
            requested_by={"id": principal.id, "kind": principal.kind},
            idempotency_key=idempotency_key,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )
        stored, created = self.repo.create(action)
        if not created:  # lost an insert race on the same idempotency key
            return self._replay(principal, type_, params, expires_at, stored)
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

    def _replay(
        self, principal: Principal, type_: str, params: dict, expires_at: datetime, existing: Action
    ) -> tuple[dict, bool]:
        same = (
            existing.type == type_
            and existing.params == params
            and existing.requested_by.get("id") == principal.id
            and existing.expires_at == utc(expires_at)
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

    def _approve(self, principal: Principal, action_id: str, extra: ApprovalInput) -> dict:
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
        if extra.override is not None and a.type != "app.install":
            raise ApiError(422, "conflict", "an owner override applies only to app.install")
        override = None
        if a.type == "app.install" and app is not None and self.require_scan:
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
        ids = {"requested_by": a.requested_by.get("id"), "approved_by": principal.id}
        self.audit.append(
            "action.approved", principal.as_dict(), a.id,
            {"type": a.type, "params": a.params, **ids, **({"owner_override": True} if override else {})},
        )
        if override is not None:
            self.owner_override.record(principal, a, override)

        try:
            return self._dispatch(a, app, ids, principal, prepared, override)
        except Exception as exc:  # anything after accepted: the effect is unknown, never retry
            log.exception("dispatch interrupted")
            self._mark_outcome_unknown(a, f"dispatch error: {exc.__class__.__name__}")
            return self._get(a.id).to_json()

    def _dispatch(
        self, a: Action, app: AppEntry, ids: dict, approver: Principal, prepared=None, override: dict | None = None
    ) -> dict:
        dispatched = self.repo.transition(a.id, {"accepted"}, "dispatched", self.clock())
        if dispatched is None:
            raise RuntimeError("accepted action could not move to dispatched")
        self.audit.append("action.dispatched", None, a.id, {"executor": self.executor.name, **ids})

        agent = self._agent_grant(a, app)
        # The approved values become current only now, after acceptance (appsecrets/service.py).
        secrets = self.app_secrets.commit(a, app, prepared, approver) if prepared is not None else []
        try:
            result = self.executor.run(a.type, app, agent=agent, **({"secrets": secrets} if secrets else {}))
        except Exception as exc:  # unknown effect: never retry automatically
            log.exception("executor crashed")
            result = ExecResult("outcome_unknown", f"executor error: {exc.__class__.__name__}")
        if a.type == "app.install" and agent is not None and result.outcome != "succeeded":
            # A failed or unknown install must not leave a live credential behind; a new install
            # issues a fresh one.
            self._revoke_agent(a, f"install {result.outcome}")

        stored = result.to_json()
        if override is not None:  # shown on the action itself, not only in the audit log
            stored["owner_override"] = {"mark": override["mark"], "approved_by": ids["approved_by"]}
        final = self.repo.transition(a.id, {"dispatched"}, result.outcome, self.clock(), result=stored)
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
        if spec is None or a.type != "app.install":
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
            self._mark_outcome_unknown(a, f"gateway restarted while the action was {a.state}")
        now = self.clock()
        for app_id, st in self.repo.list_app_states().items():
            if st.status in IN_FLIGHT:
                self.repo.set_app_state(app_id, "unknown", now, st.action_id)
                self.audit.append(
                    "app.reconciled", None, st.action_id,
                    {"app_id": app_id, "from": st.status, "to": "unknown", "reason": "gateway restarted"},
                )

    def _record_app_state(self, a: Action, outcome: str) -> None:
        app_id, now = a.params["app_id"], self.clock()
        if a.type == "app.configure" and outcome in ("succeeded", "failed"):
            # A configure that failed left the app installed (with old or partly new values); the
            # action's result says what happened, and the owner can submit the change again.
            self.repo.set_app_state(app_id, "installed", now, a.id)
        elif outcome == "succeeded":
            self.repo.set_app_state(app_id, "installed" if a.type == "app.install" else None, now, a.id)
        elif outcome == "failed":
            self.repo.set_app_state(app_id, "failed", now, a.id)
        else:
            self.repo.set_app_state(app_id, "unknown", now, a.id)
