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

from fastapi import Depends, FastAPI, Request

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope
from ..osupdate import ROLLBACK, OsUpdateService

ORDER = 335

# Registered once, at import (#323): the same facts /v1/nodes shows (version, slots), so the same scope reads them.
register_route_scope("GET,HEAD", r"/v1/os/updates", ("nodes:read",))
register_route_scope("GET,HEAD", r"/v1/os/updates/history", ("nodes:read",))


def rollback_step_up(gw: Gateway):
    """Approval guard: `os.rollback` is approved only with a passkey assertion the identity guard verified
    (signed over this action, by an active owner), whatever `require_passkey_approval` says: it discards the
    running system for the other slot and reboots. Same rule as destructive storage (routers/storage.py).
    With no passkey registered the answer is the same 401, so the owner registers one first (D-028/D-029)."""

    def guard(p: Principal, action_id: str, body: dict, request: Request) -> None:
        if not p.is_owner:
            return  # actions.approve refuses and audits non-owners itself
        try:
            action = gw.actions.get(action_id)
        except ApiError:
            return  # unknown id: the approve route answers 404
        if action.get("type") != ROLLBACK:
            return
        identity_present = any(getattr(g, "__name__", "") == "approval_guard" for g in gw.approval_guards)
        if not (body.get("webauthn") or body.get("password_totp")) or not identity_present:
            gw.events.publish_event(
                "auth", "step_up.required",
                {"attempted": "approve", "action_id": action_id, "type": ROLLBACK, "reason": "os_rollback_needs_passkey"},
                principal=p.as_dict(), severity="warning", action_id=action_id)
            raise ApiError(401, "unauthenticated", "rolling back the OS needs a proven passkey or a sign-in check "
                           "with the code from the box's screen",
                           reason="step_up_required")

    return guard


def register(app: FastAPI, gw: Gateway) -> None:
    svc = OsUpdateService(gw, app.state.hostlink)
    svc.register()
    gw.approval_guards.append(rollback_step_up(gw))
    app.state.osupdate = svc

    @app.get("/v1/os/updates", tags=["os"], operation_id="os.updates.status", responses=error_responses(401))
    def os_updates(_: Principal = Depends(gw.principal)):
        """Per node: running version, booted A/B slot, the update on offer, and whether installing can run."""
        return svc.status()

    @app.get("/v1/os/updates/history", tags=["os"], operation_id="os.updates.history", responses=error_responses(401))
    def os_updates_history(_: Principal = Depends(gw.principal)):
        """Commits and rollbacks the nodes reported, newest first, and the install requests filed."""
        return svc.history()
