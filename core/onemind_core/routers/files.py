# SPDX-License-Identifier: Apache-2.0
"""FILES routes: /v1/files/* (docs/leap/core/FILES.md is the client guide)."""

from __future__ import annotations

import base64
import email.utils
import os
import re
import urllib.parse
from datetime import datetime
from typing import Annotated, Literal

from fastapi import Body, Depends, FastAPI, Header, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from starlette.requests import ClientDisconnect

from ..auth import Principal
from ..context import Gateway
from ..files import errors as ferrors
from ..files.errors import FilesError
from ..files.preview import INLINE_SAFE, guess_mime
from ..files.service import FilesService
from ..files.store import aware
from ..files.uploads import TUS_EXTENSIONS, TUS_VERSION, Uploads, parse_metadata, parse_repr_digest

TAG = ["files"]
STREAM_CHUNK = 256 * 1024

_ERR = {
    401: {"description": "Missing or unknown bearer token (unauthenticated)"},
    403: {"description": "Not allowed for this principal (permission_denied)"},
    404: {"description": "No such file, folder, request or upload (not_found)"},
    409: {"description": "conflict, stale_precondition or expired; `reason` says which case"},
    412: {"description": "Tus-Resumable version not supported"},
    413: {"description": "payload_too_large: quota_exceeded, insufficient_space, upload_too_large or chunk_too_large"},
    416: {"description": "Range not satisfiable"},
    422: {"description": "Invalid root, path or body (conflict, reason invalid_path / invalid_root ...)"},
    429: {"description": "rate_limited: too many requests awaiting approval"},
    460: {"description": "tus checksum mismatch: the chunk was discarded"},
    503: {"description": "unavailable: the files storage is not usable"},
}


def errs(*codes: int) -> dict:
    return {c: _ERR[c] for c in codes}


# ---- bodies -------------------------------------------------------------------------------
class OpBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["mkdir", "move", "rename", "trash", "restore_trash"]
    root: str | None = Field(default=None, max_length=220)
    path: str | None = Field(default=None, max_length=4096)
    to_root: str | None = Field(default=None, max_length=220)
    to_path: str | None = Field(default=None, max_length=4096)
    name: str | None = Field(default=None, max_length=255)
    trash_id: str | None = Field(default=None, max_length=40)


class Subject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["app", "agent"]
    id: str = Field(min_length=1, max_length=200)


class RequestCommon(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=500)
    expires_at: AwareDatetime | None = None
    approve: bool = False


class GrantBody(RequestCommon):
    subject: Subject
    root: str = Field(max_length=220)
    path: str = Field(max_length=4096)
    access: Literal["r", "rw"]
    slot: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9-]{0,62}$")


class TrashEmptyBody(RequestCommon):
    trash: Literal["home", "shared"] = "home"


class DenyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=500)


class QuotaBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit_bytes: int | None = Field(ge=0)


IdemKey = Annotated[str | None, Header(alias="Idempotency-Key", max_length=200)]


# ---- helpers ------------------------------------------------------------------------------
def paginate(request: Request, items: list, limit: int, cursor: str | None) -> JSONResponse:
    """§12.1 lists: a JSON array, `?limit=&cursor=`, and an RFC 8288 Link rel=next when more remain."""
    start = 0
    if cursor:
        try:
            start = int(base64.urlsafe_b64decode(cursor.encode() + b"==").decode().removeprefix("o:"))
        except (ValueError, UnicodeDecodeError):
            raise FilesError(422, "conflict", "invalid cursor", reason="invalid_cursor") from None
    page = items[start:start + limit]
    headers = {}
    if start + limit < len(items):
        nxt = base64.urlsafe_b64encode(f"o:{start + limit}".encode()).decode().rstrip("=")
        query = dict(request.query_params) | {"cursor": nxt, "limit": str(limit)}
        headers["Link"] = f'<{request.url.path}?{urllib.parse.urlencode(query)}>; rel="next"'
    return JSONResponse(page, headers=headers)


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """One `bytes=` range -> (start, end inclusive). None = send everything (absent or multi-range)."""
    if not header:
        return None
    m = re.fullmatch(r"\s*bytes\s*=\s*(\d*)\s*-\s*(\d*)\s*", header)
    if not m:  # several ranges, or a unit we do not serve: the whole file (RFC 9110 allows it)
        return None
    first, last = m.group(1), m.group(2)
    if first == "" and last == "":
        return None
    if first == "":
        n = int(last)
        if n == 0:
            raise _unsatisfiable(size)
        return max(0, size - n), size - 1
    start = int(first)
    end = min(int(last), size - 1) if last else size - 1
    if start >= size or (last and int(last) < start):
        raise _unsatisfiable(size)
    return start, end


def _unsatisfiable(size: int) -> FilesError:
    return FilesError(416, "conflict", "range not satisfiable", reason="range", headers={"Content-Range": f"bytes */{size}"})


def content_disposition(name: str, inline: bool) -> str:
    ascii_name = re.sub(r'[^A-Za-z0-9._ -]', "_", name) or "download"
    return f"{'inline' if inline else 'attachment'}; filename=\"{ascii_name}\"; filename*=UTF-8''{urllib.parse.quote(name)}"


def tus_headers(**extra: str) -> dict[str, str]:
    return {"Tus-Resumable": TUS_VERSION, "Cache-Control": "no-store", **extra}


def require_tus(tus: str | None) -> None:
    if tus != TUS_VERSION:
        raise FilesError(412, "conflict", f"send Tus-Resumable: {TUS_VERSION}", reason="tus_version",
                         headers={"Tus-Version": TUS_VERSION, "Tus-Resumable": TUS_VERSION})


def http_date(dt: datetime | None) -> str:
    return email.utils.format_datetime(dt, usegmt=True)


# ---- routes -------------------------------------------------------------------------------
def register(app: FastAPI, gw: Gateway) -> None:
    svc = FilesService(gw)
    uploads = Uploads(svc)
    principal = gw.principal
    app.add_exception_handler(FilesError, ferrors.handle)

    def housekeeping() -> None:
        try:
            svc.purge_expired()
            uploads.expire_due()
        except FilesError as exc:  # storage not mounted yet: the routes answer 503 until it is
            svc.gw.audit.append("files.housekeeping.skipped", None, None, {"reason": exc.reason or exc.error})

    gw.on_startup(housekeeping)

    # -- browse --
    @app.get("/v1/files/roots", tags=TAG, responses=errs(401, 503))
    def roots(p: Principal = Depends(principal)):
        return svc.roots(p)

    @app.get("/v1/files/list", tags=TAG, responses=errs(401, 403, 404, 409, 422, 503))
    def list_folder(request: Request, root: str = Query(max_length=220), path: str = Query("/", max_length=4096),
                    limit: int = Query(100, ge=1, le=500), cursor: str | None = Query(None, max_length=64),
                    p: Principal = Depends(principal)):
        return paginate(request, svc.list(p, root, path), limit, cursor)

    @app.get("/v1/files/stat", tags=TAG, responses=errs(401, 403, 404, 409, 422, 503))
    def stat(root: str = Query(max_length=220), path: str = Query("/", max_length=4096), p: Principal = Depends(principal)):
        return svc.stat(p, root, path)

    @app.get("/v1/files/preview", tags=TAG, responses=errs(401, 403, 404, 409, 422, 503))
    def preview(root: str = Query(max_length=220), path: str = Query(max_length=4096), p: Principal = Depends(principal)):
        return svc.preview(p, root, path)

    @app.get("/v1/files/download", tags=TAG, responses={206: {"description": "Partial content (Range)"},
                                                         **errs(401, 403, 404, 409, 416, 422, 503)})
    def download(request: Request, root: str = Query(max_length=220), path: str = Query(max_length=4096),
                 inline: bool = False, p: Principal = Depends(principal)):
        cm = svc.open_file(p, root, path)
        fd, st, name = cm.__enter__()
        try:
            etag = f'"{st.st_size:x}-{st.st_mtime_ns:x}"'
            rng = parse_range(request.headers.get("range"), st.st_size)
            if_range = request.headers.get("if-range")
            if rng is not None and if_range is not None and if_range.strip() != etag:
                rng = None  # the file changed since the client's partial copy: send it whole
            mime = guess_mime(name)
            show_inline = inline and mime in INLINE_SAFE
            headers = {
                "Accept-Ranges": "bytes", "ETag": etag, "Cache-Control": "private, no-cache",
                "Content-Disposition": content_disposition(name, show_inline),
                "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox; default-src 'none'",
            }
            start, end, status = 0, st.st_size - 1, 200
            if rng is not None:
                start, end = rng
                status = 206
                headers["Content-Range"] = f"bytes {start}-{end}/{st.st_size}"
            headers["Content-Length"] = str(max(0, end - start + 1))
        except BaseException:
            cm.__exit__(None, None, None)
            raise

        def body():
            try:
                pos, remaining = start, end - start + 1
                while remaining > 0:
                    chunk = os.pread(fd, min(STREAM_CHUNK, remaining), pos)
                    if not chunk:
                        break
                    pos += len(chunk)
                    remaining -= len(chunk)
                    yield chunk
            finally:
                cm.__exit__(None, None, None)

        media = mime if show_inline else "application/octet-stream"
        return StreamingResponse(body(), status_code=status, media_type=media, headers=headers)

    # -- data-plane writes --
    @app.post("/v1/files/ops", tags=TAG, responses=errs(401, 403, 404, 409, 413, 422, 503))
    def ops(body: OpBody, p: Principal = Depends(principal)):
        if body.op == "mkdir":
            return svc.mkdir(p, body.root, body.path)
        if body.op == "move":
            return svc.move(p, body.root, body.path, body.to_root, body.to_path)
        if body.op == "rename":
            if not body.name:
                raise FilesError(422, "conflict", "rename needs name", reason="invalid_request")
            return svc.rename(p, body.root, body.path, body.name)
        if body.op == "trash":
            return svc.trash(p, body.root, body.path)
        if not body.trash_id:
            raise FilesError(422, "conflict", "restore_trash needs trash_id", reason="invalid_request")
        return svc.restore_trash(p, body.trash_id, body.to_root, body.to_path)

    @app.get("/v1/files/trash", tags=TAG, responses=errs(401, 403, 503))
    def trash(request: Request, trash: Literal["home", "shared"] = "home", limit: int = Query(100, ge=1, le=500),
              cursor: str | None = Query(None, max_length=64), p: Principal = Depends(principal)):
        return paginate(request, svc.list_trash(p, trash), limit, cursor)

    # -- quotas --
    @app.get("/v1/files/quotas", tags=TAG, responses=errs(401, 403, 503))
    def quotas(p: Principal = Depends(principal)):
        return svc.list_quotas(p)

    @app.put("/v1/files/quotas/{person_id}", tags=TAG, responses=errs(401, 403, 422, 503))
    def set_quota(person_id: str, body: QuotaBody, p: Principal = Depends(principal)):
        return svc.set_quota(p, person_id, body.limit_bytes)

    # -- requests that need an owner approval --
    def filed(result: tuple[dict, bool]) -> JSONResponse:
        req, created = result
        headers = {"Location": f"/v1/files/requests/{req['id']}"}
        if not created:
            headers["OneMind-Idempotent-Replay"] = "true"
        return JSONResponse(req, status_code=202, headers=headers)

    @app.post("/v1/files/grants", tags=TAG, status_code=202, responses=errs(401, 403, 404, 409, 422, 429, 503))
    def request_grant(request: Request, body: GrantBody, idem: IdemKey = None, p: Principal = Depends(principal)):
        params = {"subject": body.subject.model_dump(), "root": body.root, "path": body.path,
                  "access": body.access, "slot": body.slot}
        return filed(svc.create_request(p, "files.grant.create", params, reason=body.reason, expires_at=body.expires_at,
                                        approve=body.approve, idempotency_key=idem, http_request=request))

    @app.post("/v1/files/trash/empty", tags=TAG, status_code=202, responses=errs(401, 403, 409, 422, 429, 503))
    def request_trash_empty(request: Request, body: TrashEmptyBody = Body(default_factory=TrashEmptyBody),
                            idem: IdemKey = None, p: Principal = Depends(principal)):
        return filed(svc.create_request(p, "files.trash.empty", {"trash": body.trash}, reason=body.reason,
                                        expires_at=body.expires_at, approve=body.approve, idempotency_key=idem,
                                        http_request=request))

    @app.get("/v1/files/requests", tags=TAG, responses=errs(401))
    def list_requests(request: Request, state: str | None = Query(None, max_length=100),
                      limit: int = Query(100, ge=1, le=500), cursor: str | None = Query(None, max_length=64),
                      p: Principal = Depends(principal)):
        return paginate(request, svc.list_requests(p, state), limit, cursor)

    @app.get("/v1/files/requests/{request_id}", tags=TAG, responses=errs(401, 404))
    def get_request(request_id: str, p: Principal = Depends(principal)):
        return svc.get_request(p, request_id)

    @app.post("/v1/files/requests/{request_id}/approve", tags=TAG, responses=errs(401, 403, 404, 409))
    def approve(request: Request, request_id: str, p: Principal = Depends(principal)):
        return svc.approve(p, request_id, http_request=request)

    @app.post("/v1/files/requests/{request_id}/deny", tags=TAG, responses=errs(401, 403, 404, 409))
    def deny(request_id: str, body: DenyBody = Body(default_factory=DenyBody), p: Principal = Depends(principal)):
        return svc.deny(p, request_id, body.reason)

    @app.post("/v1/files/requests/{request_id}/cancel", tags=TAG, responses=errs(401, 404, 409))
    def cancel(request_id: str, p: Principal = Depends(principal)):
        return svc.cancel(p, request_id)

    @app.get("/v1/files/grants", tags=TAG, responses=errs(401))
    def list_grants(include_revoked: bool = False, p: Principal = Depends(principal)):
        return svc.list_grants(p, include_revoked)

    @app.delete("/v1/files/grants/{grant_id}", tags=TAG, responses=errs(401, 404, 409))
    def revoke_grant(grant_id: str, p: Principal = Depends(principal)):
        return svc.revoke_grant(p, grant_id)

    # -- resumable uploads (tus 1.0.0) --
    @app.options("/v1/files/uploads", tags=TAG)
    def tus_options():
        return Response(status_code=204, headers=tus_headers(**{
            "Tus-Version": TUS_VERSION, "Tus-Extension": TUS_EXTENSIONS, "Tus-Checksum-Algorithm": "sha256",
            "Tus-Max-Size": str(svc.settings.upload_max_bytes),
        }))

    @app.post("/v1/files/uploads", tags=TAG, status_code=201, responses=errs(401, 403, 404, 409, 412, 413, 422, 503))
    def tus_create(upload_length: Annotated[int | None, Header()] = None,
                   upload_metadata: Annotated[str | None, Header(max_length=8192)] = None,
                   repr_digest: Annotated[str | None, Header(max_length=300)] = None,
                   tus_resumable: Annotated[str | None, Header()] = None, p: Principal = Depends(principal)):
        require_tus(tus_resumable)
        row = uploads.create(p, upload_length, parse_metadata(upload_metadata), parse_repr_digest(repr_digest))
        return JSONResponse(uploads.json(row), status_code=201, headers=tus_headers(**{
            "Location": f"/v1/files/uploads/{row.id}", "Upload-Offset": str(row.received),
            "Upload-Expires": http_date(aware(row.expires_at)),
        }))

    @app.head("/v1/files/uploads/{upload_id}", tags=TAG, responses=errs(401, 404, 412))
    def tus_head(upload_id: str, tus_resumable: Annotated[str | None, Header()] = None, p: Principal = Depends(principal)):
        require_tus(tus_resumable)
        row = uploads.get(p, upload_id)
        return Response(status_code=200, headers=tus_headers(**{
            "Upload-Offset": str(row.received), "Upload-Length": str(row.length),
            "Upload-Expires": http_date(aware(row.expires_at)),
        }))

    @app.get("/v1/files/uploads/{upload_id}", tags=TAG, responses=errs(401, 404))
    def upload_status(upload_id: str, p: Principal = Depends(principal)):
        return uploads.json(uploads.get(p, upload_id))

    @app.patch("/v1/files/uploads/{upload_id}", tags=TAG, status_code=204,
               responses=errs(401, 404, 409, 412, 413, 460, 503))
    async def tus_patch(request: Request, upload_id: str, upload_offset: Annotated[int | None, Header()] = None,
                        upload_checksum: Annotated[str | None, Header(max_length=200)] = None,
                        content_type: Annotated[str | None, Header()] = None,
                        tus_resumable: Annotated[str | None, Header()] = None, p: Principal = Depends(principal)):
        require_tus(tus_resumable)
        if (content_type or "").split(";")[0].strip().lower() != "application/offset+octet-stream":
            raise FilesError(415, "conflict", "PATCH needs Content-Type: application/offset+octet-stream",
                             reason="content_type")
        cl = request.headers.get("content-length")
        patch = await run_in_threadpool(uploads.begin_patch, p, upload_id, upload_offset, upload_checksum,
                                        int(cl) if cl and cl.isdigit() else None)
        interrupted = False
        try:
            async for chunk in request.stream():
                if chunk:
                    uploads.write(patch, chunk)
        except ClientDisconnect:
            interrupted = True
        except BaseException:
            uploads.abort(patch)
            raise
        row = await run_in_threadpool(uploads.finish, p, patch, interrupted=interrupted)
        return Response(status_code=204, headers=tus_headers(**{
            "Upload-Offset": str(row.received), "Upload-Expires": http_date(aware(row.expires_at)),
            **({"OneMind-File-Sha256": row.sha256} if row.state == "done" and row.sha256 else {}),
        }))

    @app.delete("/v1/files/uploads/{upload_id}", tags=TAG, status_code=204, responses=errs(401, 404, 409, 412))
    def tus_delete(upload_id: str, tus_resumable: Annotated[str | None, Header()] = None, p: Principal = Depends(principal)):
        require_tus(tus_resumable)
        uploads.terminate(p, upload_id)
        return Response(status_code=204, headers=tus_headers())

