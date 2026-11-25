# SPDX-License-Identifier: Apache-2.0
"""Rename the box (P-05): PUT /v1/instance/name.

The box name is one lower-case DNS label (the same rule as the first-run setting). It is the name on the sign-in
page and the box's host name, so after the change `<name>.local` answers over mDNS (avahi). The request files an
`instance.rename` action; nothing changes until an owner approves it (D-027: every write is an owner action). An
agent or the `onemind` CLI may ask, only an owner approves. The host service (`onemindd host serve`, kind
`set-hostname`) saves the name on the data partition, because the root image is read-only, and asks
systemd-hostnamed to switch the running name; at every boot `onemindd host apply-hostname` puts it back.
The display name (GET /v1/instance/name) changes when the owner approves and is put back if the host cannot do it:
the host restarts the gateway a few seconds after a rename (its certificate and join QR carry the name), so the
name is saved before the request goes out, not after the answer comes back.
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
from ..identity.scopes import register_route_scope
from ..onboarding import OnboardingService

# After instance (100) and hostlink (20), whose link to the host it uses.
ORDER = 101
ACTION = "instance.rename"
REQUESTERS = frozenset({"agent"})  # besides the owner; an agent asks, only an owner approves
REQUEST_TTL = timedelta(hours=24)
NAME_PATTERN = r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"

register_route_scope("PUT", r"/v1/instance/name", ("actions:request",))


class RenameRequest(BaseModel):
    """PUT /v1/instance/name."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=63, pattern=NAME_PATTERN,
                      description="One lower-case DNS label: a-z, 0-9 and -, not starting or ending with -. The box answers as <name>.local.")
    reason: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


def register(app: FastAPI, gw: Gateway) -> None:
    svc = OnboardingService(gw.db)

    def deny(p: Principal, msg: str) -> ApiError:
        gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": f"request {ACTION}", "reason": "permission_denied"})
        return ApiError(403, "permission_denied", msg)

    def run(a, finish) -> None:
        link = app.state.hostlink
        why = link.problem(ACTION)
        if why is not None:
            finish(ExecResult("failed", why[1], steps=[{"step": "host", "result": why[0]}]))
            return
        name = (a.params or {}).get("name", "")
        before = svc.read()
        if before["saved"]:
            svc.save({k: before[k] for k in ("time_zone", "backup_choice", "backup_destination_id")} | {"box_name": name})

        def done(result: ExecResult) -> None:
            # Put back only the name: a time zone or backup choice saved while the host worked stays.
            now = svc.read()
            if result.outcome == "failed" and before["saved"] and now["box_name"] == name:
                svc.save({k: now[k] for k in ("time_zone", "backup_choice", "backup_destination_id")} | {"box_name": before["box_name"]})
            finish(result)

        link.run(a, done)

    gw.actions.register_type(ACTION, FeatureAction("actuate", run, REQUESTERS))

    @app.put("/v1/instance/name", tags=["instance"], operation_id="instance.rename", status_code=202, response_model=Action,
             openapi_extra={"security": [{"bearer": ["actions:request"]}]},
             responses={200: {"model": Action, "description": "Idempotent replay"}, **error_responses(401, 403, 409, 422, 429)})
    def rename(req: RenameRequest, p: Principal = Depends(gw.principal),
               idem: Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=200)] = None):
        """Ask to rename the box. It waits for the owner to approve; the response is the action, whose id is
        the approval to look for. An agent may ask, never approve. When the host has done it, the box answers as
        `<name>.local` (the gateway restarts a few seconds later to pick the name up) and GET /v1/instance/name says the new name.

        409 `setup_needed` before the first-run settings are saved; 409 `host_unavailable` while the host service
        cannot rename the box (nothing is filed). The `Idempotency-Key` header (or the body's `idempotency_key`)
        makes a retry replay the same action."""
        if not p.can_request_actions or not (p.is_owner or p.kind in REQUESTERS):
            raise deny(p, "only an owner or an agent may ask to rename the box")
        if not svc.read()["saved"]:
            raise ApiError(409, "conflict", "finish the first-run setup before renaming the box", reason="setup_needed")
        why = app.state.hostlink.problem(ACTION)
        if why is not None:
            raise ApiError(409, "conflict", why[1], reason="host_unavailable")
        body, created = gw.actions.request_feature(
            p, ACTION, {"name": req.name}, idempotency_key=idem or req.idempotency_key or f"rename:{uuid.uuid4()}",
            expires_at=gw.clock() + REQUEST_TTL, reason=req.reason, pending_cap=True)
        return JSONResponse(status_code=202 if created else 200, content=body, headers={"Location": f"/v1/actions/{body['id']}"})
