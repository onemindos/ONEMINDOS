# SPDX-License-Identifier: Apache-2.0
"""Photos backup routes: /v1/photos/... (docs/leap/core/PHOTOS.md §2, interim contract §12-p).

Uploads follow the IETF resumable-upload draft: POST creates, HEAD reports the offset, PATCH
appends. PATCH streams the body to disk (never whole into memory) and is cut off when it stalls.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from ..auth import Principal
from ..context import Gateway
from ..errors import error_response, error_responses
from ..photos import MAX_CHECK, PhotosError, PhotosRepository, PhotosService, PhotosSettings
from ..photos.files import LibraryEscape

FLUSH_BYTES = 1024 * 1024
HEX64 = r"^[0-9a-f]{64}$"
UPLOAD_HEADERS = {
    "Upload-Offset": {"description": "Bytes the box holds", "schema": {"type": "integer"}},
    "Upload-Complete": {"description": "?1 when the upload is finished", "schema": {"type": "string"}},
    "Upload-Length": {"description": "Declared length", "schema": {"type": "integer"}},
    "Upload-Limit": {"description": "max-size=<bytes>", "schema": {"type": "string"}},
}


class SourceIn(BaseModel):
    client_id: str = Field(pattern=r"^[\x21-\x7e]{1,128}$", description="Random id made once per app install")
    name: str = Field(min_length=1, max_length=200)
    platform: Literal["ios", "android", "other"]


class SourceOut(BaseModel):
    id: str
    client_id: str
    name: str
    platform: str


class CheckItem(BaseModel):
    client_key: str = Field(pattern=HEX64)
    size: int = Field(ge=0)
    hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class CheckIn(BaseModel):
    items: list[CheckItem] = Field(max_length=MAX_CHECK)


class CheckAnswer(BaseModel):
    client_key: str
    status: Literal["have", "need"]


class CheckOut(BaseModel):
    items: list[CheckAnswer]


class Receipt(BaseModel):
    client_key: str
    hash: str
    deduped: bool = Field(description="True when this person already held these bytes; no new copy was kept")


class Coverage(BaseModel):
    total: int
    on_box: int
    backed_up: int = Field(description="In a box backup snapshot")
    verified: int = Field(description="In a snapshot that passed a restore check: the only ones safe to free")
    as_of: str


class ReceiptLevel(BaseModel):
    client_key: str
    hash: str
    received_at: str
    level: Literal["on_box", "in_backup", "in_verified_backup"]


class ReceiptPage(BaseModel):
    items: list[ReceiptLevel]
    next_cursor: str | None


def _photos_error(_: Request, exc: PhotosError):
    res = error_response(exc.status, exc.error, exc.message)
    for k, v in exc.headers.items():
        res.headers[k] = v
    return res


def _library_escape(_: Request, exc: LibraryEscape):
    return error_response(403, "permission_denied", "the photo library refused a path outside itself")


def register(app: FastAPI, gw: Gateway) -> None:
    settings = gw.settings.section(PhotosSettings)
    svc = PhotosService(settings, PhotosRepository(gw.db), gw.clock, gw.events, gw.audit)
    principal = gw.principal
    app.add_exception_handler(PhotosError, _photos_error)
    app.add_exception_handler(LibraryEscape, _library_escape)
    gw.events.subscribe("backup.run.finished", svc.on_backup_run)
    gw.events.subscribe("backup.verify.finished", svc.on_backup_verify)
    gw.events.subscribe("backup.snapshot.removed", svc.on_snapshot_removed)
    gw.on_startup(lambda: run_in_threadpool(svc.sweep))
    app.state.photos = svc

    @app.post(
        "/v1/photos/sources", tags=["photos"], operation_id="photos.register_source", status_code=201, response_model=SourceOut,
        responses={200: {"description": "This phone was registered before: its source"}, **error_responses(401, 403, 404, 422)},
    )
    def register_source(req: SourceIn, p: Principal = Depends(principal)):
        body, created = svc.register_source(p, req.client_id, req.name, req.platform)
        return JSONResponse(status_code=201 if created else 200, content=body)

    @app.post(
        "/v1/photos/sources/{source_id}/check", tags=["photos"], operation_id="photos.check", response_model=CheckOut,
        responses=error_responses(401, 403, 404, 422),
    )
    def check(source_id: str, req: CheckIn, p: Principal = Depends(principal)):
        return {"items": svc.check(p, source_id, [(i.client_key, i.size, i.hash) for i in req.items])}

    @app.get(
        "/v1/photos/sources/{source_id}/coverage", tags=["photos"], operation_id="photos.coverage", response_model=Coverage,
        responses=error_responses(401, 403, 404),
    )
    def coverage(source_id: str, p: Principal = Depends(principal)):
        return svc.coverage(p, source_id)

    @app.get(
        "/v1/photos/sources/{source_id}/receipts", tags=["photos"], operation_id="photos.receipts", response_model=ReceiptPage,
        responses=error_responses(401, 403, 404, 422),
    )
    def receipts(
        source_id: str,
        cursor: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=500),
        p: Principal = Depends(principal),
    ):
        return svc.receipts(p, source_id, cursor, limit)

    @app.post(
        "/v1/photos/uploads", tags=["photos"], operation_id="photos.create_upload", status_code=201,
        responses={201: {"description": "Upload created; Location names it", "headers": UPLOAD_HEADERS},
                   **error_responses(401, 403, 404, 409, 422)},
    )
    def create_upload(
        p: Principal = Depends(principal),
        upload_length: int = Header(alias="Upload-Length"),
        upload_complete: Literal["?0", "?1"] = Header(default="?0", alias="Upload-Complete"),
        source_id: str = Header(alias="OneMind-Source-Id", max_length=40),
        client_key: str = Header(alias="OneMind-Client-Key", max_length=64),
        content_hash: str = Header(alias="OneMind-Content-Hash", max_length=71),
        file_name: str | None = Header(default=None, alias="OneMind-File-Name", max_length=2048),
        created_at: str | None = Header(default=None, alias="OneMind-Created-At", max_length=64),
    ):
        upload_id, offset = svc.create_upload(
            p, source_id=source_id, client_key=client_key, content_hash=content_hash, length=upload_length,
            file_name=file_name, created_at=created_at, complete=upload_complete == "?1",
        )
        return Response(status_code=201, headers={
            "Location": f"/v1/photos/uploads/{upload_id}",
            "Upload-Offset": str(offset),
            "Upload-Complete": "?0",
            "Upload-Limit": f"max-size={settings.max_upload_bytes}",
        })

    @app.head(
        "/v1/photos/uploads/{upload_id}", tags=["photos"], operation_id="photos.upload_offset", status_code=204,
        responses={204: {"description": "What the box holds", "headers": UPLOAD_HEADERS},
                   **error_responses(401, 403, 404)},
    )
    def upload_offset(upload_id: str, p: Principal = Depends(principal)):
        return Response(status_code=204, headers=svc.upload_status(p, upload_id))

    @app.patch(
        "/v1/photos/uploads/{upload_id}", tags=["photos"], operation_id="photos.append", status_code=204,
        responses={
            200: {"model": Receipt, "description": "Last part: verified, stored and fsynced"},
            204: {"description": "Part stored and fsynced", "headers": UPLOAD_HEADERS},
            **error_responses(401, 403, 404, 409, 422),
        },
    )
    async def append(
        upload_id: str,
        request: Request,
        p: Principal = Depends(principal),
        upload_offset: int = Header(alias="Upload-Offset", ge=0),
        upload_complete: Literal["?0", "?1"] = Header(alias="Upload-Complete"),
    ):
        complete = upload_complete == "?1"
        started = await run_in_threadpool(svc.begin_append, p, upload_id, upload_offset, complete)
        if isinstance(started, dict):  # the last part of a finished upload, sent again
            return JSONResponse(started["receipt"], headers=started["headers"])
        session = started
        interrupted = stalled = False
        buf = bytearray()
        stream = request.stream().__aiter__()
        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(stream.__anext__(), settings.read_timeout_s)
                except StopAsyncIteration:
                    break
                except ClientDisconnect:
                    interrupted = True
                    break
                except TimeoutError:
                    stalled = True
                    break
                buf += chunk
                if len(buf) >= FLUSH_BYTES:
                    ok = await run_in_threadpool(session.write, bytes(buf))
                    buf.clear()
                    if not ok:
                        break
            if buf:
                await run_in_threadpool(session.write, bytes(buf))
        finally:
            result = await run_in_threadpool(session.finish, complete and not interrupted, stalled)
        if "receipt" in result:
            return JSONResponse(result["receipt"], headers=svc.offset_headers(session.up, result["offset"], True))
        return Response(status_code=204, headers=svc.offset_headers(session.up, result["offset"], False))
