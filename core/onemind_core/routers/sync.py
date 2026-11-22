# SPDX-License-Identifier: Apache-2.0
"""Hub sync contract, part 1 (#698): GET /v1/sync/changes, the per-root change feed.

A sync client (the Rust sync core, the Mac File Provider, the Android documents provider) keeps
one cursor per root and asks "what changed since?". The first call (no cursor) lists every live
entry; later calls return each entry that changed once, at its latest state, deletions included.
A 410 means the cursor is older than the deletions the hub still remembers: list again with no
cursor. `sync.root_changed` on /v1/events says when to ask; it carries the root and its revision
only, never the changes themselves. The index behind it is files/index.py.
"""

from __future__ import annotations

from typing import Literal

from fastapi import Depends, FastAPI, Query
from pydantic import BaseModel

from ..auth import Principal
from ..context import Gateway
from ..files import errors as ferrors
from ..files.errors import FilesError
from ..files.index import CHANGES_MAX
from ..files.service import FilesService
from ..identity.scopes import ALL, register_route_scope
from .files import CURSOR_RE, RootQ, errs

# Like /v1/files/*: no narrower scope covers files yet, so a scoped token needs every scope ("*");
# the handler then checks read access to the whole root (a person's role, or an agent's grant on "/").
register_route_scope("GET,HEAD", r"/v1/sync/changes", (ALL,))

TAG = ["sync"]
ORDER = 305  # after files (300)


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


def register(app: FastAPI, gw: Gateway) -> None:
    svc = FilesService(gw)
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
