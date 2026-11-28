# SPDX-License-Identifier: Apache-2.0
"""OS updates (UMB-P05, #142; PD-19): what each node runs, a pending update, and the history.

Going back to the previous version is the `os.rollback` action (P-16): the same path, approved only with
the owner's passkey (`rollback_step_up` below), never by a bare token or session.

`GET /v1/os/updates` and `GET /v1/os/updates/history` read what the nodes' heartbeats report about
`internal/update` and RAUC (osupdate.py). Installing is the `os.update.install` action, requested
through `POST /v1/actions` and approved by an owner; the approved version goes to the host service
(hostlink.py), and a box without it reports `engine_unreachable` instead of running.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..apimodels import Action
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope
from ..osupdate import ROLLBACK, SETTINGS, OsUpdateService, SettingsParams

ORDER = 335

# Registered once, at import (#323): the same facts /v1/nodes shows (version, slots), so the same scope reads them.
register_route_scope("GET,HEAD", r"/v1/os/updates", ("nodes:read",))
register_route_scope("GET,HEAD", r"/v1/os/updates/history", ("nodes:read",))
# Contract §12 (poc-v0.md): changing the update settings is the owner's (`updates:admin`), and it only files a request.
register_route_scope("PUT", r"/v1/os/settings", ("updates:admin",))
SETTINGS_TTL = timedelta(hours=24)
# Contract §12.1: a retried request files one action, not two.
IdemHeader = Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=128)]


class OsSettingsBody(BaseModel):
    """PUT /v1/os/settings (REL-02, #154). A field left out keeps the value the node reports now."""

    model_config = ConfigDict(extra="forbid")
    node_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    policy: str | None = Field(default=None, pattern=r"^(auto|notify|off)$",
                               description="notify: tell the owner and wait for approval (the default, Z-02); "
                                           "auto: install by themselves inside the window (opt-in); off: do not check")
    window: str | None = Field(default=None, max_length=11,
                               description='local-time maintenance window "HH:MM-HH:MM" (may wrap past midnight) or "any"')
    reason: str | None = Field(default=None, max_length=500)


def rollback_step_up(gw: Gateway):
    """Approval guard: `os.rollback` is approved only with a passkey assertion the identity guard verified
    (signed over this action, by an active owner), whatever `require_passkey_approval` says: it discards the
    running system for the other slot and reboots. Same rule as destructive storage (routers/storage.py).
    With no passkey registered the answer is the same 401, so the owner registers one first (D-028/D-029).

    `os.update.settings` (REL-02, #154) follows the same rule for every change: the update policy and window are
    a security-related setting (D-028), and since the founder's Z-02 answer (2026-11-28) automatic installs are
    the opt-in, so no direction counts as a plain tightening."""

    def guard(p: Principal, action_id: str, body: dict, request: Request) -> None:
        if not p.is_owner:
            return  # actions.approve refuses and audits non-owners itself
        try:
            action = gw.actions.get(action_id)
        except ApiError:
            return  # unknown id: the approve route answers 404
        kind = action.get("type")
        if kind not in (SETTINGS, ROLLBACK):
            return
        identity_present = any(getattr(g, "__name__", "") == "approval_guard" for g in gw.approval_guards)
        if body.get("webauthn") is None or not identity_present:
            gw.events.publish_event(
                "auth", "step_up.required",
                {"attempted": "approve", "action_id": action_id, "type": kind,
                 "reason": "os_settings_need_passkey" if kind == SETTINGS else "os_rollback_needs_passkey"},
                principal=p.as_dict(), severity="warning", action_id=action_id)
            what = ("changing the OS update settings" if kind == SETTINGS
                    else "going back to the previous OS version")
            raise ApiError(401, "unauthenticated", f"{what} needs your passkey: register one, then approve with it",
                           reason="step_up_required")

    return guard


def register(app: FastAPI, gw: Gateway) -> None:
    svc = OsUpdateService(gw, app.state.hostlink)
    svc.register()
    gw.approval_guards.append(rollback_step_up(gw))
    app.state.osupdate = svc

    @app.put("/v1/os/settings", tags=["os"], operation_id="os.settings.update", status_code=202, response_model=Action,
             responses={200: {"model": Action, "description": "Idempotent replay"}, **error_responses(401, 403, 409, 422)},
             openapi_extra={"security": [{"bearer": ["updates:admin"]}]})
    def os_settings(body: OsSettingsBody, idem: IdemHeader = None, p: Principal = Depends(gw.principal)):
        """Request a new OS update policy or maintenance window for one node (owner only). Nothing changes until
        the owner approves the `os.update.settings` action with a passkey."""
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "request os.update.settings", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "only an owner may change the OS update settings")
        if body.policy is None and body.window is None:
            raise ApiError(422, "conflict", "give policy, window or both")
        current = svc.current_settings(body.node_id) or {}
        params = {"node_id": body.node_id, "policy": body.policy or current.get("policy"),
                  "window": body.window or current.get("window")}
        if params["policy"] is None or params["window"] is None:
            raise ApiError(409, "policy_refused", f"node {body.node_id} does not report its current update settings: give both policy and window",
                           reason="settings_unknown")
        try:
            params = SettingsParams.model_validate(params).model_dump()
        except ValueError as exc:
            raise ApiError(422, "conflict", f"request failed validation: {exc}"[:1000]) from None
        svc.check_settings_request(params)
        action, created = gw.actions.request_feature(
            p, SETTINGS, params, idempotency_key=f"os-settings:{idem}" if idem else f"os-settings:{uuid.uuid4()}",
            expires_at=gw.clock() + SETTINGS_TTL, reason=body.reason)
        return JSONResponse(status_code=202 if created else 200, content=action, headers={"Location": f"/v1/actions/{action['id']}"})

    @app.get("/v1/os/updates", tags=["os"], operation_id="os.updates.status", responses=error_responses(401))
    def os_updates(_: Principal = Depends(gw.principal)):
        """Per node: running version, booted A/B slot, the update on offer, and whether installing can run."""
        return svc.status()

    @app.get("/v1/os/updates/history", tags=["os"], operation_id="os.updates.history", responses=error_responses(401))
    def os_updates_history(_: Principal = Depends(gw.principal)):
        """Commits and rollbacks the nodes reported, newest first, and the install requests filed."""
        return svc.history()
