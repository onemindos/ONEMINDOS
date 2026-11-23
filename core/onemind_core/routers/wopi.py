# SPDX-License-Identifier: Apache-2.0
"""WOPI host routes: /v1/files/wopi/* (issue #675; files/wopi.py holds the rules).

POST /v1/files/wopi/tokens is the only route a signed-in person calls: it mints a short-lived token
for one file. Like every /v1/files/* route it needs the "*" scope (today the owner role). The rest
are the WOPI protocol an office engine calls with that token (`access_token` query parameter), never
with a bearer token:

    GET  /v1/files/wopi/files/{file_id}            CheckFileInfo
    GET  /v1/files/wopi/files/{file_id}/contents   GetFile
    POST /v1/files/wopi/files/{file_id}            X-WOPI-Override: LOCK | GET_LOCK | REFRESH_LOCK | UNLOCK
    POST /v1/files/wopi/files/{file_id}/contents   X-WOPI-Override: PUT (PutFile)

They live under /v1/files, so switching the Files app off switches them off too.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, Header, Path, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ..auth import Principal
from ..context import Gateway
from ..errors import ErrorBody
from ..files.errors import FilesError
from ..files.service import FilesService
from ..files.wopi import TOKEN_ROUTE, WopiHost
from ..guard import reads_body
from ..identity.scopes import ALL, register_route_scope
from ..identity.service import ctx_of
from .files import Root

TAG = ["files"]
# Route order in the app and in /openapi.json (routers/__init__.py): right after files (300), whose service it shares.
ORDER = 305

# Like /v1/files/*: no narrower scope covers files yet, so a session needs every scope ("*", the owner).
# The handler then also needs a person with a live session and access to the path; resolve() re-checks
# the role on every WOPI call (files/wopi.py role_may_edit).
register_route_scope("POST", TOKEN_ROUTE, (ALL,))
# The WOPI operations take only the file token (access_token), never a sign-in credential: no scope applies.
register_route_scope("GET,POST", r"/v1/files/wopi/files/[^/]+(/contents)?", None)

_ERR = {
    401: {"description": "Missing, unknown or expired token, or the session behind it ended (unauthenticated)"},
    403: {"description": "Not a signed-in person, no access to the path, or the document is read-only (permission_denied)"},
    404: {"description": "No such file (not_found)"},
    409: {"description": "Lock mismatch, not locked, stale version or not a file; X-WOPI-Lock names the current lock"},
    413: {"description": "payload_too_large: the save would pass the space's quota or the disk's free space"},
    422: {"description": "Invalid root, path, body or X-WOPI-Lock"},
    501: {"description": "X-WOPI-Override names an operation this host does not support"},
    503: {"description": "unavailable: the files storage is not usable"},
}


def errs(*codes: int) -> dict:
    """Every error answer is the section 3 envelope (ErrorBody), WOPI's X-WOPI-Lock header aside."""
    return {c: {"model": ErrorBody, **_ERR[c]} for c in codes}


class WopiTokenBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root: Root
    path: str = Field(min_length=1, max_length=4096)


AccessToken = Annotated[str | None, Query(max_length=200, description="The WOPI access token from POST /v1/files/wopi/tokens")]
FileId = Annotated[str, Path(max_length=64)]
Override = Annotated[str | None, Header(max_length=40)]
LockHeader = Annotated[str | None, Header(max_length=1024)]


def unsupported(override: str | None) -> FilesError:
    return FilesError(501, "unavailable", f"X-WOPI-Override {str(override)[:40]!r} is not supported here",
                      reason="wopi_override")


def register(app: FastAPI, gw: Gateway) -> None:
    watcher = getattr(app.state, "files_index_watcher", None)
    host = WopiHost(watcher.files if watcher is not None else FilesService(gw))
    principal = gw.principal

    @app.post(TOKEN_ROUTE, operation_id="files.wopi.tokens.create", tags=TAG, status_code=201,
              responses=errs(401, 403, 404, 409, 422, 503))
    def create_token(request: Request, body: WopiTokenBody, p: Principal = Depends(principal)):
        """A token for one file, for the signed-in person's editor. Expires in minutes; agents and API tokens are refused."""
        ctx = ctx_of(request)
        session_id = ctx.session.id if ctx is not None and ctx.session is not None else None
        return host.issue(p, session_id, body.root, body.path)

    @app.get("/v1/files/wopi/files/{file_id}", operation_id="files.wopi.check_file_info", tags=TAG,
             responses=errs(401, 404, 409, 503))
    def check_file_info(file_id: FileId, access_token: AccessToken = None):
        return host.check_file_info(host.resolve(access_token, file_id))

    @app.get("/v1/files/wopi/files/{file_id}/contents", operation_id="files.wopi.get_file", tags=TAG,
             responses={200: {"content": {"application/octet-stream": {}}}, **errs(401, 404, 409, 503)})
    def get_file(file_id: FileId, access_token: AccessToken = None):
        chunks, version, size = host.get_file(host.resolve(access_token, file_id))
        return StreamingResponse(chunks, media_type="application/octet-stream",
                                 headers={"X-WOPI-ItemVersion": version, "Cache-Control": "no-store",
                                          "Content-Length": str(size)})

    @app.post("/v1/files/wopi/files/{file_id}", operation_id="files.wopi.lock", tags=TAG,
              responses=errs(401, 403, 404, 409, 422, 501, 503))
    def lock_ops(file_id: FileId, access_token: AccessToken = None, x_wopi_override: Override = None,
                 x_wopi_lock: LockHeader = None, x_wopi_oldlock: LockHeader = None):
        """Lock, GetLock, RefreshLock, Unlock and UnlockAndRelock (X-WOPI-OldLock), by X-WOPI-Override."""
        op = (x_wopi_override or "").upper()
        if op == "GET_LOCK":
            g = host.resolve(access_token, file_id)
            return Response(status_code=200, headers={"X-WOPI-Lock": host.get_lock(g)})
        g = host.resolve(access_token, file_id, "write")
        if op == "LOCK":
            version = host.lock(g, x_wopi_lock, x_wopi_oldlock)
            return Response(status_code=200, headers={"X-WOPI-ItemVersion": version})
        if op == "REFRESH_LOCK":
            host.refresh_lock(g, x_wopi_lock)
            return Response(status_code=200)
        if op == "UNLOCK":
            version = host.unlock(g, x_wopi_lock)
            return Response(status_code=200, headers={"X-WOPI-ItemVersion": version})
        raise unsupported(x_wopi_override)

    @app.post("/v1/files/wopi/files/{file_id}/contents", operation_id="files.wopi.put_file", tags=TAG,
              responses=errs(401, 403, 404, 409, 413, 422, 501, 503))
    @reads_body
    async def put_file(request: Request, file_id: FileId, access_token: AccessToken = None,
                       x_wopi_override: Override = None, x_wopi_lock: LockHeader = None):
        """PutFile: the whole new file as the body. Needs the file's current lock and an unchanged file."""
        g = await run_in_threadpool(host.resolve, access_token, file_id, "write")
        if (x_wopi_override or "").upper() != "PUT":
            raise unsupported(x_wopi_override)
        data = await request.body()
        version = await run_in_threadpool(host.put_file, g, x_wopi_lock, data)
        return Response(status_code=200, headers={"X-WOPI-ItemVersion": version})
