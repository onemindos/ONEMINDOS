# SPDX-License-Identifier: Apache-2.0
"""Network shares (FILES-SHARE-01, #235): `GET /v1/shares/smb`, `POST /v1/shares/smb/{id}/stop` and `POST /v1/shares/smb/password`.

Turning a share on is the `files.share.create` action, requested through `POST /v1/actions` and
approved by an owner (smbshares.py). Until the box has a file-sharing service the list says
`service.available: false` with the reason, and a request is refused instead of filed.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..files.access import HOME_ROLES
from ..identity import ctx_of
from ..identity.scopes import register_route_scope
from ..smbshares import ShareService

ORDER = 337
# Rows ask for every scope (#323): a scoped token is refused, like the Files routes. People reach these
# as themselves; the handlers check who may see and do what.
register_route_scope("GET,HEAD", r"/v1/shares/smb", ("*",))
register_route_scope("POST", r"/v1/shares/smb/password", ("*",))
register_route_scope("POST", r"/v1/shares/smb/[^/]+/stop", ("*",))


def register(app: FastAPI, gw: Gateway) -> None:
    svc = ShareService(gw)
    svc.register()
    app.state.shares = svc

    def person(p: Principal) -> Principal:
        if p.kind != "person" or p.role not in HOME_ROLES:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "file sharing", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "file sharing is for household members who have files of their own")
        return p

    @app.get("/v1/shares/smb", tags=["files"], operation_id="shares.smb.list", responses=error_responses(401, 403))
    def shares_list(p: Principal = Depends(gw.principal)):
        """Whether the box can share over SMB, who could be shared, and the shares that exist.

        An owner sees everyone's shares; anyone else sees their own."""
        return svc.view(person(p))

    @app.post("/v1/shares/smb/{share_id}/stop", tags=["files"], operation_id="shares.smb.stop",
                responses=error_responses(401, 403, 404, 409))
    def shares_stop(share_id: str, p: Principal = Depends(gw.principal)):
        """Stop sharing. Owner only; taking exposure away needs no approval, and is audited."""
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "remove a share", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "only an owner may remove a share")
        return svc.remove(share_id, p)

    @app.post("/v1/shares/smb/password", tags=["files"], operation_id="shares.smb.password",
              responses=error_responses(401, 403, 409))
    def shares_password(request: Request, p: Principal = Depends(gw.principal)):
        """A new SMB password for you, shown once. Replaces the old one; only people with a share of their own.

        Once passkeys are active this needs a recent passkey sign-in (step-up), like other credential changes:
        the password opens the person's whole Files home and Time Machine folder from the LAN or mesh."""
        person(p)
        identity = getattr(request.app.state, "identity", None)
        if identity is not None:
            identity.require_step_up(ctx_of(request), p, "set an SMB password")
        out = svc.new_password(p)
        return JSONResponse(out, headers={"Cache-Control": "no-store"})
