# SPDX-License-Identifier: Apache-2.0
"""The broker: a host grant is pending until an owner approves it, active until the owner revokes it.

Flow (contract §12.5 feature action, #186 E2):
1. An owner or an agent files `host.grant` for one app and one thing (kinds.py). The action waits
   in awaiting_approval; nothing is granted yet, and the approval card shows the app, the kind,
   the device node and the reason.
2. Only a person with role owner approves it (actions.py refuses everyone else, and a standing
   approval never covers an unregistered-in-automation type). `activate` checks again that the
   approval came from an owner before it writes the grant.
3. The executor asks `allowance(app_id)` at every render; the sandbox (policy.py) then allows
   exactly the granted node, host network or capability for that app, nothing wider.
4. `revoke` turns the grant off at once; the next install or update of the app is refused again.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..actions import ActionRequest, FeatureAction
from ..catalog import APP_ID_RE
from ..errors import ApiError
from ..executors import ExecResult
from ..identity.models import utc
from . import kinds
from .kinds import HostAllowance
from .models import HostGrantRepository, HostGrantRow, grant_id

ACTION_TYPE = "host.grant"


class GrantParams(BaseModel):
    """What the owner approves: one app, one thing, and why the app needs it."""

    model_config = ConfigDict(extra="forbid")
    app_id: str = Field(pattern=APP_ID_RE.pattern, max_length=59)
    kind: Literal["device", "gpu", "host-network", "realtime"]
    device_class: Literal["usb-serial", "usb", "video"] | None = None
    path: str | None = Field(default=None, min_length=1, max_length=220)
    reason: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def _one_thing(self):
        why = kinds.problem(self.kind, self.device_class, self.path)
        if why:
            raise ValueError(why)
        if not self.reason.strip():
            raise ValueError("reason must not be blank")
        return self


def grant_json(row: HostGrantRow) -> dict:
    return {
        "id": row.id, "app_id": row.app_id, "kind": row.kind, "device_class": row.device_class, "path": row.path,
        "reason": row.reason, "active": row.active, "granted_at": utc(row.granted_at), "approved_by": row.approved_by,
        "action_id": row.action_id, "revoked_at": utc(row.revoked_at) if row.revoked_at else None,
        "revoked_by": row.revoked_by,
    }


class HostGrantBroker:
    def __init__(self, gw):
        self.gw = gw
        self.repo = HostGrantRepository(gw.db)
        gw.actions.register_type(ACTION_TYPE, FeatureAction(
            "sensitive", self.activate, requesters=frozenset({"agent"}), params_model=GrantParams,
            check_request=self.check_request, check=self.check_action, risk_for=lambda _: "sensitive",
        ))
        # The executor asks at every render; an executor without the hook (a test double) ignores it.
        try:
            gw.executor.host_grants = self.allowance
        except AttributeError:
            pass

    # ---- reads ---------------------------------------------------------------------------------
    def owner(self, principal, what: str) -> None:
        if not principal.is_owner:
            self.gw.audit.append("authz.denied", principal.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", f"{principal.kind}/{principal.role} may not {what}")

    def grants(self, principal, app_id: str | None) -> list[dict]:
        self.owner(principal, "read host grants")
        return [grant_json(r) for r in self.repo.list(app_id)]

    def allowance(self, app_id: str) -> HostAllowance:
        return HostAllowance.of((r.kind, r.path) for r in self.repo.list(app_id, active_only=True))

    # ---- request and approval ------------------------------------------------------------------
    def request(self, principal, body) -> dict:
        params = {"app_id": body.app_id, "kind": body.kind, "device_class": body.device_class,
                  "path": body.path, "reason": body.reason.strip()}
        params = {k: v for k, v in params.items() if v is not None}
        return self.gw.actions.create(principal, ActionRequest(
            type=ACTION_TYPE, params=params, idempotency_key=body.idempotency_key, expires_at=body.expires_at))[0]

    def _problem(self, params: dict) -> tuple[int, str, str] | None:
        app = self.gw.catalog.get(params["app_id"])
        if app is None:
            return 404, "not_found", "no such app"
        if app.summary().get("tier") == "community":
            return 409, "conflict", "a community-tier app never gets a host grant (Z-21); it must be Verified"
        row = self.repo.get(self._id(params))
        if row is not None and row.active:
            return 409, "conflict", "this host grant is already active"
        return None

    @staticmethod
    def _id(params: dict) -> str:
        return grant_id(params["app_id"], params["kind"], params.get("device_class"), params.get("path"))

    def check_request(self, params: dict, principal) -> None:
        found = self._problem(params)
        if found:
            raise ApiError(*found)

    def check_action(self, action) -> str | None:
        found = self._problem(action.params)
        if found:
            return found[2]
        return self._revoked_since(action)

    def _revoked_since(self, action) -> str | None:
        """A revocation is final for every request filed before it: the owner files a new one."""
        row = self.repo.get(self._id(action.params))
        if row is not None and row.revoked_at is not None and utc(action.created_at) <= utc(row.revoked_at):
            return "this host grant was revoked after the request was filed; request it again"
        return None

    def activate(self, action, finish) -> None:
        decided = self.gw.repo.get(action.id)
        by = (decided.decided_by or {}) if decided else {}
        if by.get("kind") != "person" or by.get("role") != "owner":  # never an agent, automation or policy
            finish(ExecResult("failed", "a host grant is activated only by an owner's approval"))
            return
        stale = self.check_action(action)
        if stale:
            finish(ExecResult("failed", stale))
            return
        p = action.params
        values = dict(id=self._id(p), app_id=p["app_id"], kind=p["kind"], device_class=p.get("device_class"),
                      path=p.get("path"), reason=p["reason"], active=True, granted_at=self.gw.clock(),
                      approved_by=str(by.get("id")), action_id=action.id, revoked_at=None, revoked_by=None)
        if not self.repo.activate(values):
            finish(ExecResult("failed", "this host grant is already active"))
            return
        self.gw.audit.append("hostgrant.activated", by, action.id, {k: p.get(k) for k in ("app_id", "kind", "device_class", "path")})
        finish(ExecResult("succeeded", f"host grant {p['kind']} active for {p['app_id']}"))

    # ---- revocation ----------------------------------------------------------------------------
    def revoke(self, principal, gid: str) -> dict:
        self.owner(principal, "revoke host grants")
        row = self.repo.get(gid)
        if row is None or not row.active:
            raise ApiError(404, "not_found", "no active host grant with this id")
        if not self.repo.revoke(gid, principal.id, self.gw.clock()):
            raise ApiError(404, "not_found", "no active host grant with this id")
        self.gw.audit.append("hostgrant.revoked", principal.as_dict(), row.action_id,
                             {"id": gid, "app_id": row.app_id, "kind": row.kind, "path": row.path})
        return grant_json(self.repo.get(gid))
