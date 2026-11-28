# SPDX-License-Identifier: Apache-2.0
"""The keyboard layout of the box (P-11): the text console (tty1-tty6, the tty2 login) and the box's own screen.

- GET /v1/system/keyboard: the layout chosen now and every layout the image offers (its xkb-data list), read from the host
  service. Owner only, like the other /v1/system reads.
- POST /v1/system/keyboard: files a system.set_keymap action. An owner or an agent may ask; only an owner approves (an
  agent never does, and `onemind keyboard set` only asks). The host writes the layout to /data, so it survives reboots
  and A/B updates, and loads it into the console and the kiosk (hostlink.py, internal/host/keymap.go). Not a security
  change, so the owner's approval is enough: no passkey step-up (D-028).
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..actions import FeatureAction
from ..apimodels import Action
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..executors import ExecResult
from ..hostkeyboard import LAYOUT_RE, VARIANT_RE, HostKeyboardClient, KeyboardView, offers, read_view
from ..identity.scopes import register_route_scope
from ..netconf import NetSettings

# Route order in the app and in /openapi.json (routers/__init__.py): right after routers/services.py.
ORDER = 342
ACTION = "system.set_keymap"
REQUESTERS = frozenset({"agent"})  # besides the owner; an agent asks, only an owner approves
REQUEST_TTL = timedelta(hours=24)

# Same scope as /v1/system/controls: minted to no one, so only the owner role (every scope) reads it.
register_route_scope("GET,HEAD", r"/v1/system/keyboard", ("system:admin",))
register_route_scope("POST", r"/v1/system/keyboard", ("actions:request",))


class KeyboardRequest(BaseModel):
    """POST /v1/system/keyboard."""

    model_config = ConfigDict(extra="forbid")
    layout: str = Field(pattern=LAYOUT_RE.pattern, description="A layout id from GET /v1/system/keyboard, e.g. de.")
    variant: str | None = Field(default=None, pattern=VARIANT_RE.pattern, description="One of that layout's variant ids.")
    reason: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


def register(app: FastAPI, gw: Gateway) -> None:
    cfg = gw.settings.section(NetSettings)
    client = HostKeyboardClient(str(cfg.host_socket), cfg.host_timeout_s)

    def deny(p: Principal, what: str, msg: str) -> ApiError:
        gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
        return ApiError(403, "permission_denied", msg)

    def problem(params: dict) -> str | None:
        """Why this layout may not be set now (read from the host each time), else None."""
        view = read_view(client)
        if not view.available:
            return view.message or "the host service is not reachable"
        if not offers(view, params.get("layout", ""), params.get("variant")):
            return "this image does not offer that keyboard layout"
        return None

    def recheck(a) -> str | None:
        return problem(a.params or {})

    def run(a, finish) -> None:
        link = app.state.hostlink
        why = link.problem(ACTION)
        if why is not None:
            finish(ExecResult("failed", why[1], steps=[{"step": "host", "result": why[0]}]))
            return
        link.run(a, finish)

    gw.actions.register_type(ACTION, FeatureAction("actuate", run, REQUESTERS, check=recheck))

    @app.get("/v1/system/keyboard", tags=["system"], operation_id="system.keyboard.get", response_model=KeyboardView,
             responses=error_responses(401, 403), openapi_extra={"security": [{"bearer": ["system:admin"]}]})
    def system_keyboard(p: Principal = Depends(gw.principal)) -> KeyboardView:
        """The keyboard layout of the text console and the box's own screen, and every layout this image offers
        with its variants (read only). `seeded` is true while nothing is chosen and the box runs the US layout.
        `available` is false, with a reason, when the host service cannot be reached."""
        if not p.is_owner:
            raise deny(p, "read the keyboard layout", "only an owner may see the keyboard layout settings")
        return read_view(client)

    @app.post("/v1/system/keyboard", tags=["system"], operation_id="system.keyboard.set", status_code=202,
              response_model=Action,
              responses={200: {"model": Action, "description": "Idempotent replay"}, **error_responses(401, 403, 404, 409, 422, 429)},
              openapi_extra={"security": [{"bearer": ["actions:request"]}]})
    def system_keyboard_set(req: KeyboardRequest, p: Principal = Depends(gw.principal),
                            idem: Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=200)] = None):
        """Ask to change the keyboard layout. It waits for the owner, who approves it on the Approvals screen; the
        response is the action, whose id is the approval to look for. An agent may ask, never approve. Once approved
        the layout is saved on the data disk and loaded into the text console and the box's screen.

        404 for a layout or variant this image does not offer; 409 host_unavailable while the host service cannot
        change the layout (nothing is filed). The `Idempotency-Key` header (or the body's `idempotency_key`) makes a
        retry replay the same action."""
        if not p.can_request_actions or not (p.is_owner or p.kind in REQUESTERS):
            raise deny(p, f"request {ACTION}", "only an owner or an agent may ask to change the keyboard layout")
        params = {"layout": req.layout, **({"variant": req.variant} if req.variant else {})}
        view = read_view(client)
        if not view.available:
            raise ApiError(409, "conflict", view.message or "the host service is not reachable", reason="host_unavailable")
        if not offers(view, req.layout, req.variant):
            raise ApiError(404, "not_found", "this image does not offer that keyboard layout")
        why = app.state.hostlink.problem(ACTION)
        if why is not None:
            raise ApiError(409, "conflict", why[1], reason="host_unavailable")
        body, created = gw.actions.request_feature(
            p, ACTION, params, idempotency_key=idem or req.idempotency_key or f"keyboard:{uuid.uuid4()}",
            expires_at=gw.clock() + REQUEST_TTL, reason=req.reason, pending_cap=True)
        return JSONResponse(status_code=202 if created else 200, content=body, headers={"Location": f"/v1/actions/{body['id']}"})
