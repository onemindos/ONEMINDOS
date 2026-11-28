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

from fastapi import Depends, FastAPI, Header, Path, Query, Request, Response, Security
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..auth import Principal
from ..context import Gateway
from ..errors import ErrorBody, SemanticValueError
from ..files import errors as ferrors
from ..files.errors import FilesError
from ..files.index import CHANGES_MAX
from ..files.service import FilesService
from ..files.locks import TTL_MAX_S, Locks
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
register_route_scope("GET,HEAD", r"/v1/sync/locks", (ALL,))
register_route_scope("POST", r"/v1/sync/locks(/[^/]+/refresh)?", (ALL,))
register_route_scope("DELETE", r"/v1/sync/locks/[^/]+", (ALL,))

TAG = ["sync"]
ORDER = 305  # after files (300)
HEX_RE = r"^[0-9a-f]{64}$"
Hex = Annotated[str, Field(max_length=64, json_schema_extra={"pattern": HEX_RE})]
MISSING_MAX = 3000  # hashes in one question: the body stays under the gateway's body cap
_412 = {412: {"model": ErrorBody, "description": "stale_precondition (stale_base): the file is not at base_revision; "
                                                 "details[0] carries current_revision and current_hash, ETag the revision"}}
# Names the bearer scheme and the route's scope in /openapi.json (contract lint rules `security` and `scopes`).
# It never refuses by itself: gw.principal decides, and a session cookie works as on every other route.
_BEARER = HTTPBearer(scheme_name="bearer", auto_error=False, description="A gateway token or a signed-in session (contract §3)")
SECURED = [Security(_BEARER, scopes=[ALL])]


def body_errs(*codes: int) -> dict:
    """The files error descriptions, each answered with the one ErrorBody (contract lint rule `error-schema`)."""
    return {c: {"model": ErrorBody, **e} for c, e in errs(*codes).items()}


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


def _commit_schema(schema: dict) -> None:
    schema["oneOf"] = [{"required": ["chunks"]}, {"required": ["manifest_chunks"]}]
    for name in ("chunks", "manifest_chunks"):  # absent, never null: drop the default pydantic prints
        schema["properties"][name].pop("default", None)


class CommitBody(_Body):
    model_config = ConfigDict(extra="forbid", json_schema_extra=_commit_schema)
    root: Root
    path: str = Field(min_length=1, max_length=4096)
    size: int = Field(ge=0, le=MAX_QUOTA_BYTES)
    sha256: Hex                   # of the whole file
    # Exactly one of the two: the schema says so (oneOf on "required"), and so does the model. Neither is
    # nullable: absent means "not sent", and an explicit null would make the two readings differ.
    chunks: list[ChunkRef] = Field(None, max_length=MANIFEST_MAX_CHUNKS)  # type: ignore[assignment]
    manifest_chunks: list[Hex] = Field(None, max_length=MISSING_MAX)  # type: ignore[assignment]
    # The file's revision the client last saw (from /v1/sync/changes or a commit); null or absent:
    # the file must not exist yet. An If-Match header says the same and wins when both are sent.
    base_revision: int | None = Field(None, ge=0)

    @model_validator(mode="after")
    def _exactly_one_manifest(self):
        if len(self.model_fields_set & {"chunks", "manifest_chunks"}) != 1:
            raise SemanticValueError("send exactly one of chunks or manifest_chunks", reason="chunks_or_manifest")
        return self


class LockHolder(BaseModel):
    kind: str
    id: str


class SyncLock(BaseModel):
    id: str                       # lck_...: the lock token; refresh or release it with this id
    root: str
    path: str
    holder: LockHolder
    note: str | None
    created_at: str
    expires_at: str


class SyncLocks(BaseModel):
    locks: list[SyncLock]


class LockBody(_Body):
    root: Root
    path: str = Field(min_length=1, max_length=4096)
    ttl_s: int | None = Field(None, ge=1, le=TTL_MAX_S)
    note: str | None = Field(None, max_length=200)


class LockRefresh(_Body):
    ttl_s: int | None = Field(None, ge=1, le=TTL_MAX_S)


class SyncCommitted(BaseModel):
    root: str
    path: str
    id: str
    revision: int                 # the file's revision now: the next commit's base
    size: int
    hash: str
    version_id: str
    locks: list[SyncLock]         # advisory locks of others on this file: the client warns, nothing is refused


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


# If-Match on a commit: the base revision, as an ETag ("7", W/"7") or bare (7). The schema states it, so a
# client (and the fuzzer) knows anything else is the 422 below rather than a value the server might take.
IF_MATCH_RE = r'^(W/)?"?[0-9]{1,18}"?$'


def _if_match(value: str | None) -> int | None:
    """If-Match: "<revision>" (quotes optional). Anything else is 422."""
    raw = value.strip().removeprefix("W/").strip('"') if value else ""
    # isdigit() alone also takes "²" or Arabic-Indic digits, which int() then refuses (a 500): ASCII only.
    if not (raw.isascii() and raw.isdigit()) or len(raw) > 18:
        raise FilesError(422, "conflict", 'If-Match is "<revision>"', reason="invalid_precondition")
    return int(raw)


def register(app: FastAPI, gw: Gateway) -> None:
    svc = FilesService(gw)
    locks = Locks(svc)
    transfer = Transfer(svc, locks=locks)
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
              dependencies=SECURED, responses=body_errs(401, 403, 422, 503))
    def chunks_missing(body: MissingQuestion, p: Principal = Depends(principal)):
        return {"missing": transfer.missing(p, body.root, body.hashes)}

    @app.put("/v1/sync/chunks/{chunk_hash}", operation_id="sync.chunks.put", tags=TAG, response_model=ChunkStored,
             summary="Send one chunk",
             description=(f"The raw bytes (1 to {CHUNK_LIMIT}). 422 (hash_mismatch): they do not hash to the name. "
                          "Sending a chunk the root already holds is harmless."),
             dependencies=SECURED, responses=body_errs(401, 403, 413, 422, 503))
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
              dependencies=SECURED, responses={**body_errs(401, 403, 404, 409, 413, 422, 503), **_412})
    # `str`, not `str | None`: an optional header is simply absent, and a nullable schema made clients
    # (and the fuzzer) send the text "null", which is no revision.
    def commit(body: CommitBody, if_match: Annotated[str, Header(max_length=40, json_schema_extra={
                   "pattern": IF_MATCH_RE})] = None,  # type: ignore[assignment]
               p: Principal = Depends(principal)):
        base = _if_match(if_match) if if_match is not None else body.base_revision
        chunks = [c.model_dump() for c in body.chunks] if body.chunks is not None else None
        return transfer.commit(p, body.root, body.path, body.size, body.sha256, chunks, base, body.manifest_chunks)

    @app.get("/v1/sync/versions", operation_id="sync.versions.list", tags=TAG, response_model=SyncVersions,
             summary="The kept versions of a file", dependencies=SECURED,
             responses=body_errs(401, 403, 404, 422, 503))
    def versions(root: RootQ, path: str = Query(..., max_length=4096), p: Principal = Depends(principal)):
        return transfer.versions(p, root, path)

    _423 = {423: {"model": ErrorBody, "description": "conflict (locked): someone else holds a lock on this path, or inside it"}}

    @app.post("/v1/sync/locks", operation_id="sync.locks.create", tags=TAG, response_model=SyncLock, status_code=201,
              summary="Take an advisory lock on a file or folder (WebDAV class 2)",
              description=f"The lock lasts ttl_s seconds (default 300, at most {TTL_MAX_S}) unless refreshed. Advisory: "
                          "it warns other clients, it never blocks a write.",
              dependencies=SECURED, responses={**body_errs(401, 403, 404, 422, 503), **_423})
    def lock_take(body: LockBody, p: Principal = Depends(principal)):
        return locks.take(p, body.root, body.path, body.ttl_s, body.note)

    @app.get("/v1/sync/locks", operation_id="sync.locks.list", tags=TAG, response_model=SyncLocks,
             summary="Live locks at or inside a path", dependencies=SECURED, responses=body_errs(401, 403, 422, 503))
    def lock_list(root: RootQ, path: str = Query("/", max_length=4096), p: Principal = Depends(principal)):
        return {"locks": locks.list(p, root, path)}

    @app.post("/v1/sync/locks/{lock_id}/refresh", operation_id="sync.locks.refresh", tags=TAG, response_model=SyncLock,
              summary="Extend your lock", dependencies=SECURED, responses=body_errs(401, 404, 422))
    def lock_refresh(lock_id: Annotated[str, Path(max_length=40)], body: LockRefresh | None = None,
                     p: Principal = Depends(principal)):
        return locks.refresh(p, lock_id, body.ttl_s if body else None)

    @app.delete("/v1/sync/locks/{lock_id}", operation_id="sync.locks.delete", tags=TAG, status_code=204,
                summary="Release your lock (an owner may clear anyone's)", dependencies=SECURED, responses=body_errs(401, 404))
    def lock_release(lock_id: Annotated[str, Path(max_length=40)], p: Principal = Depends(principal)):
        locks.release(p, lock_id)
        return Response(status_code=204)
