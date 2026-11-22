# SPDX-License-Identifier: Apache-2.0
"""The hub file index for sync (#698): stable ids, revisions, content hashes and a per-root change feed.

files_index        one row per file, folder or symlink in a space. `file_id` (fil_ ULID) survives a
                   rename or a move inside the same root; `revision` is the root's revision at the
                   row's last change; `hash` is `sha256:<hex>` of a file (null until hashed);
                   `deleted` marks a tombstone, kept so the feed can report the deletion.
files_index_roots  per root: `revision` (monotonic, only goes up), `floor` (tombstones at or below it
                   were pruned, so an older cursor gets 410) and `key` (signs that root's cursors).

The feed is the index itself: rows with revision > cursor. A file changed five times since a
cursor appears once, at its latest state, and renaming a folder gives one change per entry inside
it, each with its old id. Everything here names a root id and a path inside the space, never a
host path.

Who fills it: every FILES write calls `reconcile` on what it touched; a scanner and an inotify
watcher (watch.py) call it for a whole space, so writes made over SMB or WebDAV land here too.
A rename seen by the scanner is matched by device and inode, so it keeps its id as well.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import BigInteger, Boolean, DateTime, Index, String, delete, func, or_, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..auth import Principal
from ..ledger import Base, iso
from . import paths
from .errors import FilesError
from .store import SCHEMA, new_id

INDEXED_KINDS = ("file", "dir", "symlink")
INLINE_HASH_BYTES = 16 * 1024 * 1024   # stat hashes a file up to this size (list hashes none); the scanner hashes the rest
READ_CHUNK = 1024 * 1024
CHANGES_MAX = 1000                     # most entries in one page of the feed

# One writer at a time per process: the API threads, the scanner and the watcher share it.
_LOCK = threading.RLock()


class IndexRow(Base):
    __tablename__ = "files_index"
    __table_args__ = (
        Index("ix_files_index_live_path", "root", "path", unique=True,
              sqlite_where=text("NOT deleted"), postgresql_where=text("NOT deleted")),
        Index("ix_files_index_feed", "root", "revision"),
        Index("ix_files_index_parent", "parent_id"),
    )
    file_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    root: Mapped[str] = mapped_column(String(220))
    parent_id: Mapped[str | None] = mapped_column(String(40), nullable=True)  # None: at the top of the space
    path: Mapped[str] = mapped_column(String(4200))
    name: Mapped[str] = mapped_column(String(1024))
    type: Mapped[str] = mapped_column(String(8))                    # file | dir | symlink
    size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mtime_ns: Mapped[int] = mapped_column(BigInteger)
    ino: Mapped[str | None] = mapped_column(String(48), nullable=True)  # "<dev>:<inode>", to follow renames
    hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    revision: Mapped[int] = mapped_column(BigInteger)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IndexRootRow(Base):
    __tablename__ = "files_index_roots"
    root: Mapped[str] = mapped_column(String(220), primary_key=True)
    revision: Mapped[int] = mapped_column(BigInteger)
    floor: Mapped[int] = mapped_column(BigInteger)
    key: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


@SCHEMA.step(2, "sync index: files_index and files_index_roots (#698)")
def _files_v2(conn: Connection) -> None:
    IndexRow.__table__.create(conn, checkfirst=True)
    IndexRootRow.__table__.create(conn, checkfirst=True)


def hash_at(dir_fd: int, name: str, limit: int | None) -> str | None:
    """`sha256:<hex>` of a regular file, or None when it is larger than `limit` or went away."""
    try:
        fd = os.open(name, paths.O_FILE_READ, dir_fd=dir_fd)
    except OSError:
        return None
    try:
        if limit is not None and os.fstat(fd).st_size > limit:
            return None
        h = hashlib.sha256()
        while chunk := os.read(fd, READ_CHUNK):
            h.update(chunk)
        return "sha256:" + h.hexdigest()
    except OSError:
        return None
    finally:
        os.close(fd)


def _ino(st: os.stat_result) -> str:
    return f"{st.st_dev}:{st.st_ino}"


def _under(path: str) -> str:
    return "/" if path == "/" else path + "/"


Seen = dict[str, tuple[tuple[str, ...], os.stat_result, str | None]]  # path -> (parts, stat, hash)


class FileIndex:
    def __init__(self, db, clock: Callable[[], datetime]):
        self.db = db
        self.clock = clock

    # ---- walking the disk (no lock held) --------------------------------------------------
    def _walk(self, space_fd: int, parts: tuple[str, ...], depth: int | None, snapshot: dict[str, IndexRow],
              hash_max: int | None, on_dir: Callable[[int], None] | None) -> Seen:
        """Stat everything at and under `parts` (to `depth` levels) and hash files that changed."""
        seen: Seen = {}

        def note(d: int, name: str, entry_parts: tuple[str, ...], st: os.stat_result) -> bool:
            kind = paths.kind_of(st)
            if kind not in INDEXED_KINDS:
                return False
            path = paths.join(entry_parts)
            old = snapshot.get(path)
            digest = None
            if kind == "file":
                same = old is not None and (old.size, old.mtime_ns, old.ino) == (st.st_size, st.st_mtime_ns, _ino(st))
                digest = old.hash if same and old.hash else (hash_at(d, name, hash_max) if hash_max != 0 else None)
            seen[path] = (entry_parts, st, digest)
            return kind == "dir"

        def children(d: int, prefix: tuple[str, ...], left: int | None) -> None:
            if on_dir is not None:
                on_dir(d)
            if left == 0:
                return
            try:
                with os.scandir(d) as it:
                    entries = sorted((e.name for e in it), key=lambda n: n.encode("utf-8", "surrogateescape"))
            except OSError:
                return
            for name in entries:
                if not paths.is_utf8(name):
                    continue
                try:
                    st = os.lstat(name, dir_fd=d)
                except OSError:
                    continue
                if note(d, name, prefix + (name,), st):
                    try:
                        sub = os.open(name, paths.O_DIR, dir_fd=d)
                    except OSError:
                        continue
                    try:
                        children(sub, prefix + (name,), None if left is None else left - 1)
                    finally:
                        os.close(sub)

        if not parts:
            children(space_fd, (), depth)
            return seen
        try:
            parent = paths.open_dir(space_fd, parts[:-1])
        except FilesError:
            return seen
        try:
            try:
                st = os.lstat(parts[-1], dir_fd=parent)
            except OSError:
                return seen
            if note(parent, parts[-1], parts, st) and depth != 0:
                try:
                    sub = os.open(parts[-1], paths.O_DIR, dir_fd=parent)
                except OSError:
                    return seen
                try:
                    children(sub, parts, depth)  # depth 1: the folder and what is directly in it
                finally:
                    os.close(sub)
        finally:
            os.close(parent)
        return seen

    # ---- loading rows ---------------------------------------------------------------------
    @staticmethod
    def _live(s: Session, root: str, path: str) -> IndexRow | None:
        return s.scalars(select(IndexRow).where(IndexRow.root == root, IndexRow.path == path,
                                                IndexRow.deleted.is_(False))).first()

    def _scope(self, s: Session, root: str, parts: tuple[str, ...], depth: int | None) -> dict[str, IndexRow]:
        """Live rows at and under `parts` that a walk to `depth` would see (depth None: all of them)."""
        path = paths.join(parts)
        live = (IndexRow.root == root) & IndexRow.deleted.is_(False)
        if depth is None:
            q = select(IndexRow).where(live)
            if parts:
                q = q.where(or_(IndexRow.path == path, IndexRow.path.startswith(_under(path), autoescape=True)))
            return {r.path: r for r in s.scalars(q)}
        out: dict[str, IndexRow] = {}
        top = self._live(s, root, path) if parts else None
        if top is not None:
            out[top.path] = top
        if depth != 0 and (top is not None or not parts):
            parent = IndexRow.parent_id.is_(None) if not parts else IndexRow.parent_id == top.file_id
            out.update({r.path: r for r in s.scalars(select(IndexRow).where(live, parent))})
        return out

    # ---- writing --------------------------------------------------------------------------
    def _root_row(self, s: Session, root: str) -> IndexRootRow:
        row = s.get(IndexRootRow, root, with_for_update=True)
        if row is None:
            row = IndexRootRow(root=root, revision=0, floor=0, key=secrets.token_hex(32), updated_at=self.clock())
            s.add(row)
            s.flush()
        return row

    def _bump(self, s: Session, root: str) -> int:
        row = self._root_row(s, root)
        row.revision += 1
        row.updated_at = self.clock()
        return row.revision

    def _tombstone(self, s: Session, row: IndexRow) -> None:
        row.deleted = True
        row.revision = self._bump(s, row.root)
        row.changed_at = self.clock()
        s.flush()

    def _place(self, s: Session, root: str, row: IndexRow | None, parts: tuple[str, ...], st: os.stat_result,
               parent_id: str | None, digest: str | None) -> IndexRow:
        """Bring one row in line with the disk; bumps the revision only when something changed."""
        path, kind = paths.join(parts), paths.kind_of(st)
        size = st.st_size if kind == "file" else None
        want = (path, parts[-1], parent_id, kind, size, st.st_mtime_ns, _ino(st))
        if row is not None:
            have = (row.path, row.name, row.parent_id, row.type, row.size, row.mtime_ns, row.ino)
            if have == want and (digest is None or digest == row.hash):
                return row
            if kind == "dir" and have[:4] == want[:4]:
                # A folder's mtime and inode change with what is inside it or when it is restored:
                # its entries report their own changes, so the folder itself has not changed.
                row.mtime_ns, row.ino = want[5], want[6]
                return row
        if row is None or row.path != path:
            other = self._live(s, root, path)  # a stale row left at the destination: it is gone now
            if other is not None and (row is None or other.file_id != row.file_id):
                self._tombstone(s, other)
        revision = self._bump(s, root)  # before the row changes: the query here must not flush a half-made row
        new = row is None
        if new:
            row = IndexRow(file_id=new_id("fil"), root=root, deleted=False)
        elif kind != "file" or (row.size, row.mtime_ns) != (size, st.st_mtime_ns):
            row.hash = None
        row.path, row.name, row.parent_id, row.type, row.size, row.mtime_ns, row.ino = want
        if digest is not None:
            row.hash = digest
        row.revision, row.changed_at = revision, self.clock()
        if new:
            s.add(row)
        s.flush()
        return row

    def reconcile(self, space_fd: int, root: str, parts: tuple[str, ...] = (), *, depth: int | None = None,
                  also: tuple[str, ...] | None = None, known_hash: str | None = None,
                  hash_max: int | None = INLINE_HASH_BYTES, on_dir: Callable[[int], None] | None = None) -> int:
        """Make the index match the disk at and under `parts`. `also`: a path that no longer exists
        (the source of a move) whose rows may be matched by inode, so they keep their ids.
        `known_hash`: the hash of the file at `parts` (an upload already computed it).
        Returns how many rows changed."""
        with self.db.session() as s:
            snapshot = self._scope(s, root, parts, depth)
        seen = self._walk(space_fd, parts, depth, snapshot, hash_max, on_dir)
        if known_hash is not None and parts and paths.join(parts) in seen:
            entry = seen[paths.join(parts)]
            seen[paths.join(parts)] = (entry[0], entry[1], known_hash)
        changed = 0
        with _LOCK, self.db.session.begin() as s:
            start = self._root_row(s, root).revision
            ids: dict[str, str] = {}
            for i in range(1, len(parts)):  # the folders above the entry, so it has a parent id
                anc = parts[:i]
                try:
                    with paths.dir_at(space_fd, anc[:-1]) as d:
                        st = paths.lstat_at(d, anc[-1])
                except FilesError:
                    break
                row = self._place(s, root, self._live(s, root, paths.join(anc)), anc, st, ids.get(paths.join(anc[:-1])), None)
                ids[row.path] = row.file_id
            rows = self._scope(s, root, parts, depth)
            if also is not None:
                rows.update(self._scope(s, root, also, None))
            if parts and len(parts) > 1 and paths.join(parts[:-1]) not in ids:
                parent = self._live(s, root, paths.join(parts[:-1]))
                if parent is not None:
                    ids[parent.path] = parent.file_id
            by_ino = {r.ino: r for r in rows.values() if r.ino and r.path not in seen}
            claimed: set[str] = set()
            for path, (entry_parts, st, digest) in seen.items():
                kind = paths.kind_of(st)
                row = rows.get(path)
                if row is not None and row.type != kind:
                    self._tombstone(s, row)
                    claimed.add(row.file_id)
                    row = None
                if row is None:
                    moved = by_ino.pop(_ino(st), None)
                    if moved is not None and moved.type == kind and moved.file_id not in claimed:
                        row = moved
                if row is not None:
                    claimed.add(row.file_id)
                parent_id = ids.get(paths.join(entry_parts[:-1])) if len(entry_parts) > 1 else None
                row = self._place(s, root, row, entry_parts, st, parent_id, digest)
                ids[path] = row.file_id
            for row in rows.values():
                if row.file_id not in claimed and row.path not in seen and not row.deleted:
                    self._tombstone(s, row)
            changed = self._root_row(s, root).revision - start
        return changed

    # ---- reading --------------------------------------------------------------------------
    def rows(self, root: str, paths_: list[str]) -> dict[str, IndexRow]:
        if not paths_:
            return {}
        with self.db.session() as s:
            q = select(IndexRow).where(IndexRow.root == root, IndexRow.deleted.is_(False), IndexRow.path.in_(paths_))
            return {r.path: r for r in s.scalars(q)}

    def revision(self, root: str) -> int:
        with self.db.session() as s:
            row = s.get(IndexRootRow, root)
            return row.revision if row is not None else 0

    def revisions(self, roots: list[str]) -> dict[str, int]:
        with self.db.session() as s:
            have = {r.root: r.revision for r in s.scalars(select(IndexRootRow).where(IndexRootRow.root.in_(roots)))}
        return {r: have.get(r, 0) for r in roots}

    @staticmethod
    def change_json(row: IndexRow) -> dict:
        return {
            "id": row.file_id, "parent_id": row.parent_id, "path": row.path, "name": row.name, "type": row.type,
            "size": row.size, "mtime": iso(datetime.fromtimestamp(row.mtime_ns / 1e9, tz=UTC)),
            "hash": row.hash, "revision": row.revision, "deleted": row.deleted,
        }

    # ---- cursors: bound to one root and one principal --------------------------------------
    @staticmethod
    def _mac(key: str, p: Principal, root: str, revision: int) -> bytes:
        msg = f"{p.kind}:{p.id}\n{root}\n{revision}".encode()
        return hmac.new(bytes.fromhex(key), msg, hashlib.sha256).digest()[:16]

    def _key(self, root: str) -> IndexRootRow:
        with _LOCK, self.db.session.begin() as s:
            row = self._root_row(s, root)
            return IndexRootRow(root=row.root, revision=row.revision, floor=row.floor, key=row.key, updated_at=row.updated_at)

    def encode_cursor(self, key: str, p: Principal, root: str, revision: int) -> str:
        raw = revision.to_bytes(8, "big") + self._mac(key, p, root, revision)
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    def changes(self, p: Principal, root: str, cursor: str | None, limit: int) -> dict:
        """One page of the feed. A cursor made for another root or principal is refused (422); one
        older than the pruned floor, or newer than the root, gets 410: walk the tree again."""
        info = self._key(root)
        after = 0
        if cursor:
            try:
                raw = base64.urlsafe_b64decode(cursor.encode() + b"=" * (-len(cursor) % 4))
            except ValueError:
                raw = b""
            if len(raw) != 24:
                raise FilesError(422, "conflict", "invalid cursor", reason="invalid_cursor")
            after = int.from_bytes(raw[:8], "big")
            if not hmac.compare_digest(raw[8:], self._mac(info.key, p, root, after)):
                raise FilesError(422, "conflict", "this cursor was not issued for this root and caller",
                                 reason="invalid_cursor")
            if after < info.floor or after > info.revision:
                raise FilesError(410, "expired", "the cursor is too old; list the root again from the start",
                                 reason="cursor_expired")
        limit = max(1, min(limit, CHANGES_MAX))
        with self.db.session() as s:
            q = select(IndexRow).where(IndexRow.root == root, IndexRow.revision > after,
                                       IndexRow.revision <= info.revision)
            if not cursor:
                q = q.where(IndexRow.deleted.is_(False))
            page = list(s.scalars(q.order_by(IndexRow.revision).limit(limit + 1)))
        more = len(page) > limit
        page = page[:limit]
        upto = page[-1].revision if more else info.revision
        return {"root": root, "revision": info.revision, "changes": [self.change_json(r) for r in page],
                "next_cursor": self.encode_cursor(info.key, p, root, upto), "has_more": more}

    # ---- pruning --------------------------------------------------------------------------
    def prune(self, root: str, keep: timedelta) -> int:
        """Drop tombstones older than `keep` and raise the root's floor past them."""
        cutoff = self.clock() - keep
        with _LOCK, self.db.session.begin() as s:
            tomb = (IndexRow.root == root) & IndexRow.deleted.is_(True)
            top = s.execute(select(func.max(IndexRow.revision)).where(tomb, IndexRow.changed_at <= cutoff)).scalar()
            if top is None:
                return 0
            res = s.execute(delete(IndexRow).where(tomb, IndexRow.revision <= top))
            row = self._root_row(s, root)
            row.floor = max(row.floor, int(top))
            return max(0, res.rowcount or 0)


__all__ = ["CHANGES_MAX", "FileIndex", "INLINE_HASH_BYTES", "IndexRootRow", "IndexRow", "hash_at"]
