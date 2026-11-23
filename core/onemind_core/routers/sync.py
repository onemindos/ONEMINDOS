# SPDX-License-Identifier: Apache-2.0
"""Hub sync contract: the per-root change feed (#698) and chunked, conditional uploads (#699).

A sync client (the Rust sync core, the Mac File Provider, the Android documents provider) keeps
one cursor per root and asks "what changed since?". The first call (no cursor) lists every live
entry; later calls return each entry that changed once, at its latest state, deletions included.
A 410 means the cursor is older than the deletions the hub still remembers: list again with no
cursor. `sync.root_changed` on /v1/events says when to ask; it carries the root and its revision
only, never the changes themselves. The index behind it is files/index.py.

Sending a file (#699, files/transfer.py): ask which chunks are missing, PUT those, then commit the
manifest with the file's base revision. A stale base is 412 with the current revision; an
interrupted upload resumes by asking for the missing chunks again.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, Path, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from ..auth import Principal
from ..context import Gateway
from ..files import errors as ferrors
from ..files.errors import FilesError
from ..files.index import CHANGES_MAX
from ..files.service import FilesService
from ..files.transfer import CHUNK_LIMIT, MANIFEST_MAX_CHUNKS, Transfer
from ..guard import reads_body
from ..identity.scopes import ALL, register_route_scope
from ..jsonbody import JsonBody
from .files import CURSOR_RE, MAX_QUOTA_BYTES, Root, RootQ, errs

# Like /v1/files/*: no narrower scope covers files yet, so a scoped token needs every scope ("*");
# the handler then checks read access to the whole root (a person's role, or an agent's grant on "/").
register_route_scope("GET,HEAD", r"/v1/sync/changes", (ALL,))
register_route_scope("GET,HEAD", r"/v1/sync/versions", (ALL,))
register_route_scope("POST", r"/v1/sync/(chunks/missing|commit)", (ALL,))
register_route_scope("PUT", r"/v1/sync/chunks/[^/]+", (ALL,))

TAG = ["sync"]
ORDER = 305  # after files (300)
HEX_RE = r"^[0-9a-f]{64}$"
Hex = Annotated[str, Field(max_length=64, json_schema_extra={"pattern": HEX_RE})]
MISSING_MAX = 3000  # hashes in one question: the body stays under the gateway's body cap
_412 = {412: {"description": "stale_precondition (stale_base): the file is not at base_revision; "
                             "details[0] carries current_revision and current_hash, ETag the revision"}}


class SyncChange(BaseModel):
    """One entry of the feed: a file, folder or symlink as it is now (or its deletion)."""
    id: str                       # fil_...: survives renames and moves inside the root
    parent_id: str | None         # the folder it is in; null at the top of the root
    path: str                     # inside the root, from "/"; never a path on the hub's disk
    name: str
    type: Literal["file", "dir", "symlink"]
    size: int | None              # files only
    mtime: str
    hash: str | None              # "sha256:<hex>" for a file once hashed; null for folders
    revision: int                 # the root's revision at this entry's last change
    deleted: bool                 # true: the entry is gone (kept until pruned)


class SyncChanges(BaseModel):
    root: str
    revision: int                 # the root's current revision
    changes: list[SyncChange]
    next_cursor: str              # pass back as ?cursor=; bound to this root and this caller
    has_more: bool                # true: ask again at once with next_cursor


class _Body(JsonBody):
    """Request bodies: unknown keys refused, numbers must arrive as JSON numbers (not "12" or true)."""
    model_config = ConfigDict(extra="forbid")


class MissingQuestion(_Body):
    root: Root
    hashes: list[Hex] = Field(max_length=MISSING_MAX)


class MissingChunks(BaseModel):
    missing: list[str]            # the hashes the hub does not hold, in the order asked


class ChunkStored(BaseModel):
    hash: str
    size: int
    stored: bool                  # false: the hub held it already


class ChunkRef(_Body):
    hash: Hex                     # sha256 of the chunk, lowercase hex
    size: int = Field(ge=1, le=CHUNK_LIMIT)


class CommitBody(_Body):
    root: Root
    path: str = Field(min_length=1, max_length=4096)
    size: int = Field(ge=0, le=MAX_QUOTA_BYTES)
    sha256: Hex                   # of the whole file
    chunks: list[ChunkRef] | None = Field(None, max_length=MANIFEST_MAX_CHUNKS)
    manifest_chunks: list[Hex] | None = Field(None, max_length=MISSING_MAX)
    # The file's revision the client last saw (from /v1/sync/changes or a commit); null or absent:
    # the file must not exist yet. An If-Match header says the same and wins when both are sent.
    base_revision: int | None = Field(None, ge=0)


class SyncCommitted(BaseModel):
    root: str
    path: str
    id: str
    revision: int                 # the file's revision now: the next commit's base
    size: int
    hash: str
    version_id: str


class SyncVersion(BaseModel):
    id: str
    revision: int
    size: int
    sha256: str
    chunks: int
    origin: Literal["sync", "hub"]  # hub: changed outside sync, cut into chunks by the hub
    created_by: str | None
    created_at: str
    current: bool


class SyncVersions(BaseModel):
    root: str
    path: str
    id: str
    revision: int
    versions: list[SyncVersion]   # newest first; the last few are kept and share chunks


def _if_match(value: str | None) -> int | None:
    """If-Match: "<revision>" (quotes optional). Anything else is 422."""
    raw = value.strip().removeprefix("W/").strip('"') if value else ""
    if not raw.isdigit() or len(raw) > 18:
        raise FilesError(422, "conflict", 'If-Match is "<revision>"', reason="invalid_precondition")
    return int(raw)


def register(app: FastAPI, gw: Gateway) -> None:
    svc = FilesService(gw)
    transfer = Transfer(svc)
    app.state.sync_transfer = transfer
    principal = gw.principal
    app.add_exception_handler(FilesError, ferrors.handle)

    @app.get("/v1/sync/changes", operation_id="sync.changes.list", tags=TAG, response_model=SyncChanges,
             summary="What changed in a root since a cursor",
             description=("Entries with a revision after the cursor, oldest first, each once at its latest state. "
                          "No cursor: every live entry. 410 (cursor_expired): list again with no cursor. "
                          "422 (invalid_cursor): the cursor was issued for another root or caller."),
             responses={410: {"description": "expired: the cursor is older than the remembered deletions"},
                        **errs(401, 403, 422, 503)})
    def changes(root: RootQ, cursor: str | None = Query(None, max_length=64, json_schema_extra={"pattern": CURSOR_RE}),
                limit: int = Query(500, ge=1, le=CHANGES_MAX), p: Principal = Depends(principal)):
        return svc.sync_changes(p, root, cursor, limit)

    @app.post("/v1/sync/chunks/missing", operation_id="sync.chunks.missing", tags=TAG, response_model=MissingChunks,
              summary="Which chunks the root does not hold yet",
              description=("Ask before sending, and again after an interruption: only the missing chunks need sending. "
                           "Needs write access to the whole root (an agent: a read-write grant on \"/\"). "
                           "Chunks named here stay on the hub for a day even if no version uses them yet."),
              responses=errs(401, 403, 422, 503))
    def chunks_missing(body: MissingQuestion, p: Principal = Depends(principal)):
        return {"missing": transfer.missing(p, body.root, body.hashes)}

    @app.put("/v1/sync/chunks/{chunk_hash}", operation_id="sync.chunks.put", tags=TAG, response_model=ChunkStored,
             summary="Send one chunk",
             description=(f"The raw bytes (1 to {CHUNK_LIMIT}). 422 (hash_mismatch): they do not hash to the name. "
                          "Sending a chunk the root already holds is harmless."),
             responses=errs(401, 403, 413, 422, 503))
    @reads_body
    async def chunk_put(request: Request, root: RootQ,
                        chunk_hash: Annotated[str, Path(max_length=64, json_schema_extra={"pattern": HEX_RE})],
                        p: Principal = Depends(principal)):
        data = bytearray()
        async for piece in request.stream():
            data += piece
            if len(data) > CHUNK_LIMIT:
                raise FilesError(413, "payload_too_large", f"a chunk is at most {CHUNK_LIMIT} bytes",
                                 reason="chunk_too_large")
        return await run_in_threadpool(transfer.put_chunk, p, root, chunk_hash, bytes(data))

    @app.post("/v1/sync/commit", operation_id="sync.commit", tags=TAG, response_model=SyncCommitted,
              summary="Make a file from chunks, if it is still at the base revision",
              description=("409 (chunks_missing): details list the chunks to send first. 412 (stale_base): another "
                           "device changed the file; details carry its revision. 413 (quota_exceeded). "
                           "The replaced content stays as a version."),
              responses={**errs(401, 403, 404, 409, 413, 422, 503), **_412})
    def commit(body: CommitBody, if_match: Annotated[str | None, Header(max_length=40)] = None,
               p: Principal = Depends(principal)):
        base = _if_match(if_match) if if_match is not None else body.base_revision
        chunks = [c.model_dump() for c in body.chunks] if body.chunks is not None else None
        return transfer.commit(p, body.root, body.path, body.size, body.sha256, chunks, base, body.manifest_chunks)

    @app.get("/v1/sync/versions", operation_id="sync.versions.list", tags=TAG, response_model=SyncVersions,
             summary="The kept versions of a file", responses=errs(401, 403, 404, 422, 503))
    def versions(root: RootQ, path: str = Query(..., max_length=4096), p: Principal = Depends(principal)):
        return transfer.versions(p, root, path)
