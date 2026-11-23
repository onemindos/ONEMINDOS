# SPDX-License-Identifier: Apache-2.0
"""WebDAV and its app passwords (files-webdav, #722).

Routes (bearer token or session, like the rest of the API):
- `GET /v1/files/app-passwords`: your app passwords (an owner sees everyone's), never the secret, and
  where to connect.
- `POST /v1/files/app-passwords`: make one for yourself, shown once. Owner or adult only.
- `POST /v1/files/app-passwords/{password_id}/revoke`: revoke yours (an owner may revoke anyone's).

The WebDAV tree itself (`/dav/...`, files/webdav.py) is answered by a middleware outside the guard:
it streams whole files, which the guard's 256 KiB body cap would refuse, and it takes only app
passwords (HTTP Basic), never a bearer token. It is LAN and mesh only and has its own rate limit and
wrong-password back-off. ORDER sits before net (270), so the app proxy stays outside this middleware
and an app's own `/dav` on its app host name still reaches the app.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Request, Security
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..files.apppasswords import CreateBody
from ..files.webdav import WebDav, WebDavMiddleware
from ..identity import ctx_of
from ..identity.scopes import register_route_scope

ORDER = 268  # after identity (260, step-up); before net (270), whose app proxy must wrap the /dav middleware
# Minting a credential for yourself is tokens:self, as for API tokens: a narrowly scoped token cannot make one.
register_route_scope("GET,HEAD", r"/v1/files/app-passwords", ("tokens:read", "tokens:self", "tokens:admin"))
register_route_scope("POST", r"/v1/files/app-passwords", ("tokens:self", "tokens:admin"))
register_route_scope("POST", r"/v1/files/app-passwords/[^/]+/revoke", ("tokens:self", "tokens:admin"))
# Names the bearer scheme and these scopes in /openapi.json (contract lint rules `security` and `scopes`).
# It never refuses by itself: gw.principal decides, and a session cookie works as on every other route.
_BEARER = HTTPBearer(scheme_name="bearer", auto_error=False, description="A gateway token or a signed-in session (contract §3)")
READ = [Security(_BEARER, scopes=["tokens:read", "tokens:self", "tokens:admin"])]
WRITE = [Security(_BEARER, scopes=["tokens:self", "tokens:admin"])]


def register(app: FastAPI, gw: Gateway) -> None:
    dav = WebDav(gw)
    passwords = dav.passwords
    app.state.webdav = dav
    app.state.app_passwords = passwords
    app.add_middleware(WebDavMiddleware, dav=dav)

    def holder(p: Principal, attempted: str) -> Principal:
        if not passwords.may_hold(p):
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": attempted, "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "app passwords are for the owner and adults, for their own files")
        return p

    @app.get("/v1/files/app-passwords", tags=["files"], operation_id="files.app_passwords.list", dependencies=READ,
             responses=error_responses(401, 403))
    def app_passwords_list(p: Principal = Depends(gw.principal)):
        """Your WebDAV app passwords (an owner sees everyone's), and where to connect. The secret is never shown again."""
        holder(p, "list app passwords")
        return {"app_passwords": passwords.list(p), "webdav": {
            "enabled": dav.settings.enabled, "path": "/dav/", "reach": ["lan", "mesh"],
            "spaces": {"home": "Home", "shared": "Shared"}, "windows": "smb"}}

    @app.post("/v1/files/app-passwords", tags=["files"], operation_id="files.app_passwords.create", status_code=201, dependencies=WRITE,
              responses=error_responses(401, 403, 409, 422))
    def app_passwords_create(body: CreateBody, request: Request, p: Principal = Depends(gw.principal)):
        """Make an app password for a WebDAV client (Finder, GNOME Files), shown once.

        The user name is your person id. Once passkeys are active this needs a recent passkey sign-in (step-up):
        the password opens your files from the LAN or mesh."""
        holder(p, "create an app password")
        identity = getattr(request.app.state, "identity", None)
        if identity is not None:
            identity.require_step_up(ctx_of(request), p, "create an app password")
        return JSONResponse(passwords.create(p, body), status_code=201, headers={"Cache-Control": "no-store"})

    @app.post("/v1/files/app-passwords/{password_id}/revoke", tags=["files"], operation_id="files.app_passwords.revoke", dependencies=WRITE,
                responses=error_responses(401, 403, 404))
    def app_passwords_revoke(password_id: str, p: Principal = Depends(gw.principal)):
        """Revoke an app password. The next WebDAV request with it fails."""
        holder(p, "revoke an app password")
        return passwords.revoke(p, password_id)
