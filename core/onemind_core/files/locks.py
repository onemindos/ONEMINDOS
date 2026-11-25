# SPDX-License-Identifier: Apache-2.0
"""Advisory locks with a time limit (#699), the shape WebDAV class 2 needs (RFC 4918 section 6).

macOS mounts a WebDAV share read-write only when the server offers locks, and office apps take one
while a document is open. A lock here is advisory: it tells other clients "someone is editing
this", it does not stop a write. The sync engine only warns when it commits over someone's lock.

A lock covers its path and, for a folder, everything inside it (depth infinity). Taking a lock
where a live lock of someone else covers the path, or inside a path they hold, is 423 Locked.
Every lock expires at `expires_at` unless its holder refreshes it; an expired lock counts as gone.
The lock id is the lock token: only its holder (or an owner, to clear a stale one) removes it.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta

from sqlalchemy import DateTime, Index, String, delete, select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, mapped_column

from ..auth import Principal
from ..ledger import Base, iso
from . import paths
from .errors import FilesError, not_found
from .store import SCHEMA, aware, new_id

TTL_DEFAULT_S = 300
TTL_MAX_S = 3600
_LOCK = threading.Lock()


class LockRow(Base):
    __tablename__ = "files_sync_locks"
    __table_args__ = (Index("ix_files_sync_locks_root", "root", "path"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)        # lck_...: the lock token
    root: Mapped[str] = mapped_column(String(220))
    path: Mapped[str] = mapped_column(String(4200))
    holder_id: Mapped[str] = mapped_column(String(200))
    holder_kind: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)  # e.g. the app that holds it
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


@SCHEMA.step(4, "sync locks: files_sync_locks (#699)")
def _files_v4(conn: Connection) -> None:
    LockRow.__table__.create(conn, checkfirst=True)


def _overlaps(a: str, b: str) -> bool:
    """True when one path is the other or inside it."""
    pa, pb = paths.split_path(a), paths.split_path(b)
    return paths.is_within(pa, pb) or paths.is_within(pb, pa)


class Locks:
    def __init__(self, files):
        self.files = files
        self.db = files.repo.db

    def _json(self, row: LockRow) -> dict:
        return {"id": row.id, "root": row.root, "path": row.path,
                "holder": {"kind": row.holder_kind, "id": row.holder_id}, "note": row.note,
                "created_at": iso(aware(row.created_at)), "expires_at": iso(aware(row.expires_at))}

    def _ttl(self, ttl_s: int | None) -> timedelta:
        return timedelta(seconds=min(max(ttl_s or TTL_DEFAULT_S, 1), TTL_MAX_S))

    def _live(self, s, root: str) -> list[LockRow]:
        now = self.files.clock()
        s.execute(delete(LockRow).where(LockRow.root == root, LockRow.expires_at <= now))
        return list(s.scalars(select(LockRow).where(LockRow.root == root)))

    def take(self, p: Principal, root: str | None, path: str | None, ttl_s: int | None, note: str | None) -> dict:
        t = self.files.target(p, root, path, "entry")  # locking is a write intent: read-only callers are refused
        if not t.parts:
            raise FilesError(422, "conflict", "lock a file or folder, not the root", reason="invalid_path")
        with self.files._space(t.root) as space, paths.dir_at(space, t.parts[:-1]) as d:
            paths.lstat_at(d, t.parts[-1])  # 404 when nothing is there
        now = self.files.clock()
        with _LOCK, self.db.session.begin() as s:
            for other in self._live(s, t.root.id):
                if _overlaps(other.path, t.path) and other.holder_id != p.id:
                    raise FilesError(423, "conflict", f"{other.path} is locked by {other.holder_kind} {other.holder_id} "
                                     f"until {iso(aware(other.expires_at))}", reason="locked")
            row = LockRow(id=new_id("lck"), root=t.root.id, path=t.path, holder_id=p.id, holder_kind=p.kind,
                          note=note, created_at=now, expires_at=now + self._ttl(ttl_s))
            s.add(row)
            s.flush()
            out = self._json(row)
        self.files.event("lock.taken", p, {"root": t.root.id, "path": t.path, "lock_id": out["id"],
                                           "expires_at": out["expires_at"]})
        return out

    def _mine(self, s, p: Principal, lock_id: str, *, owner_may: bool = False) -> LockRow:
        row = s.get(LockRow, lock_id)
        if row is None or aware(row.expires_at) <= self.files.clock():
            raise not_found("no such lock (it may have expired)")
        if row.holder_id != p.id and not (owner_may and p.is_owner):
            raise not_found("no such lock of yours")
        return row

    def refresh(self, p: Principal, lock_id: str, ttl_s: int | None) -> dict:
        with _LOCK, self.db.session.begin() as s:
            row = self._mine(s, p, lock_id)
            row.expires_at = self.files.clock() + self._ttl(ttl_s)
            s.flush()
            return self._json(row)

    def release(self, p: Principal, lock_id: str) -> None:
        with _LOCK, self.db.session.begin() as s:
            row = self._mine(s, p, lock_id, owner_may=True)
            root, path = row.root, row.path
            s.delete(row)
        self.files.event("lock.released", p, {"root": root, "path": path, "lock_id": lock_id})

    def list(self, p: Principal, root: str | None, path: str | None) -> list[dict]:
        t = self.files.target(p, root, path, "read")
        with _LOCK, self.db.session.begin() as s:
            return [self._json(r) for r in self._live(s, t.root.id) if _overlaps(r.path, t.path)]

    def held_by_others(self, p: Principal, root: str, path: str) -> list[dict]:
        """Live locks of someone else that cover `path`: what a sync commit warns about."""
        now = self.files.clock()
        with self.db.session() as s:
            rows = s.scalars(select(LockRow).where(LockRow.root == root, LockRow.expires_at > now))
            return [self._json(r) for r in rows if r.holder_id != p.id and _overlaps(r.path, path)]


__all__ = ["LockRow", "Locks", "TTL_DEFAULT_S", "TTL_MAX_S"]
