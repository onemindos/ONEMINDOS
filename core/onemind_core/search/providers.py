# SPDX-License-Identifier: Apache-2.0
"""The first two search providers: Files and Settings (#611).

files     every file and folder in the Files sync index (files/index.py), followed by its per-root
          revision so a refresh reads only what changed. A hit is shown to a person by role (their own
          Home, the Shared folder) and to an agent only under a folder grant the owner approved:
          exactly who may list that folder through GET /v1/files/list.
settings  every Settings page a built-in declares (descriptor spec.settingsPages). A page is shown to
          a person whose scopes allow the route the page reads; agents and apps do not browse Settings.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from urllib.parse import quote

from sqlalchemy import select

from ..builtins import Descriptor
from ..files import paths
from ..files.access import is_person, parse_root, person_access
from ..files.errors import FilesError
from ..files.index import IndexRootRow, IndexRow
from ..identity import scopes as sc
from .index import Item, Writer
from .service import Asker, Provider, register_provider

FILE_TYPES = {"file": "file", "dir": "folder"}  # files_index type -> search type; symlinks are not searched
FILES_READ = "GET /v1/files/list"


def files_link(root: str, path: str) -> str:
    return f"onemind://app/files/open?root={quote(root, safe='')}&path={quote(path, safe='')}"


def settings_link(app_id: str, page_id: str) -> str:
    return f"onemind://app/settings/{app_id}/{page_id}"


class FilesProvider(Provider):
    def __init__(self, descriptor: Descriptor, files):
        super().__init__(descriptor)
        self.files = files  # files.service.FilesService

    def _item(self, row: IndexRow) -> Item:
        parent = row.path.rsplit("/", 1)[0] or "/"
        where = "Shared" if row.root == "shared" else "Home"
        return Item(id=row.file_id, type=FILE_TYPES[row.type], app_id=self.app_id, scope=row.root, key=row.path,
                    title=row.name, subtitle=f"{where} {parent}", body=row.path.replace("/", " "),
                    link=files_link(row.root, row.path))

    def refresh(self, w: Writer) -> None:
        db = self.files.index.db
        with db.session() as s:
            roots = {r.root: (r.revision, r.floor) for r in s.scalars(select(IndexRootRow))}
        for gone in w.scopes() - set(roots):
            w.delete_scope(gone)
            w.set_cursor(gone, None)
        for root, (revision, floor) in sorted(roots.items()):
            cur = w.cursor(root)
            after = int(cur) if cur is not None else None
            if after == revision:
                continue
            q = select(IndexRow).where(IndexRow.root == root)
            # No cursor, or one the feed can no longer answer from (tombstones pruned): read the live tree again.
            full = after is None or after < floor or after > revision
            if full:
                w.delete_scope(root)
                q = q.where(IndexRow.deleted.is_(False))
            else:
                q = q.where(IndexRow.revision > after)
            with db.session() as s:
                for row in s.scalars(q.execution_options(yield_per=1000)):
                    if row.deleted or row.type not in FILE_TYPES:
                        w.delete(row.file_id)
                    else:
                        w.put(self._item(row))
            w.set_cursor(root, str(revision))

    def visible(self, asker: Asker) -> Callable[[Item], bool]:
        p = asker.principal
        if not asker.may_call(FILES_READ):
            return lambda item: False
        if is_person(p):
            seen: dict[str, bool] = {}

            def by_role(item: Item) -> bool:
                if item.scope not in seen:
                    try:
                        seen[item.scope] = person_access(p, parse_root(item.scope)).read
                    except FilesError:
                        seen[item.scope] = False
                return seen[item.scope]
            return by_role
        grants = [(g.root, paths.split_path(g.path)) for g in self.files.grants_for(p)]  # agents only; else none

        def by_grant(item: Item) -> bool:
            try:
                parts = paths.split_path(item.key)
            except FilesError:
                return False
            return any(root == item.scope and paths.is_within(parts, prefix) for root, prefix in grants)
        return by_grant


class SettingsProvider(Provider):
    def __init__(self, descriptor: Descriptor, builtins):
        super().__init__(descriptor)
        self.builtins = builtins  # builtins.Builtins: every descriptor, switched on or off

    def refresh(self, w: Writer) -> None:
        pages = [(d.id, d.name, p) for _, d in sorted(self.builtins.descriptors.items())
                 for p in d.spec.get("settingsPages", [])]
        digest = hashlib.sha256(json.dumps(pages, sort_keys=True).encode()).hexdigest()
        if w.cursor("pages") == digest:
            return
        w.clear()
        for app_id, name, page in pages:
            w.put(Item(id=f"{app_id}.{page['id']}", type="page", app_id=app_id, scope=app_id, key=page["source"],
                       title=page["title"], subtitle=f"{name} settings",
                       body=f"{name} settings {page['id'].replace('-', ' ')}",
                       link=settings_link(app_id, page["id"])))
        w.set_cursor("pages", digest)

    def visible(self, asker: Asker) -> Callable[[Item], bool]:
        p = asker.principal
        if not is_person(p):
            return lambda item: False
        # A tokens-file person has no identity scopes: judge the page by the scopes of their role.
        who = asker if asker.scopes is not None else Asker(p, sc.role_scopes(p.role), asker.app_visible)
        return lambda item: who.may_call(item.key)


def _files(descriptor: Descriptor, app) -> Provider | None:
    svc = getattr(app.state, "files_service", None)
    return FilesProvider(descriptor, svc) if svc is not None else None


def _settings(descriptor: Descriptor, app) -> Provider | None:
    reg = getattr(app.state, "builtins", None)
    return SettingsProvider(descriptor, reg) if reg is not None else None


register_provider("files", _files)
register_provider("settings", _settings)
