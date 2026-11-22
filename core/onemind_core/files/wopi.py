# SPDX-License-Identifier: Apache-2.0
"""WOPI host over FILES (issue #675): an office engine opens and saves one file, never anything else.

WOPI is the protocol office engines (Collabora Online, OnlyOffice, Microsoft 365 for the web) use to
read and write a document that lives on someone else's server. The engine never signs in: it holds an
access token the host issued for one file and calls six operations with it. This host is
engine-neutral and ships no engine (the engine's licence is a separate gate).

Who may get a token, and what it reaches:

- Only a person signed in with a session (cookie or bearer `om_ses_`) mints a token. Agents, API and
  SDK tokens, and the static tokens file are refused: an engine acts for a human at a screen, and AI
  never writes a document behind a person's back.
- A token names one person, one file (root + path) and the session it was minted from. It expires
  after TOKEN_TTL (minutes). Every call re-checks that the session is still live, the person is still
  enabled, and the Files role table (access.py) still lets them read, or write, that path. Signing out
  or losing the role ends the token at once.
- Paths go through the same rules as the Files API (paths.py): no `..`, no symlink is ever followed.
- Every token issue, open (GetFile), lock change and save is audited through the Files event stream.

Saves follow WOPI's lock rules: PutFile needs the file's current lock, and the file must still be the
version the lock holder last saw (base_version). A save that would overwrite a change made through
Files, SMB or another engine answers 409 with reason stale_version instead of losing that change.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import stat as stat_mod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import BigInteger, Boolean, DateTime, String, delete, select
from sqlalchemy.orm import Mapped, mapped_column

from ..auth import Principal
from ..ledger import Base, iso, utc
from ..store import FeatureSchema, SqlRepository
from . import paths
from .errors import FilesError, conflict, not_found
from .service import FilesService, Target
from .store import new_id

SCHEMA = FeatureSchema("wopi")

TOKEN_TTL = timedelta(minutes=10)     # "expire within minutes": the editor re-mints to keep going
LOCK_TTL = timedelta(minutes=30)      # WOPI: a lock lasts 30 minutes unless refreshed
MAX_LOCK_LEN = 1024                   # WOPI: lock ids are at most 1024 ASCII characters
TOKEN_PREFIX = "om_wopi_"
READ_CHUNK = 1024 * 1024


class WopiTokenRow(Base):
    __tablename__ = "wopi_tokens"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    secret_hash: Mapped[str] = mapped_column(String(64), unique=True)   # sha256 of the token; the token is never stored
    file_id: Mapped[str] = mapped_column(String(64), index=True)
    person_id: Mapped[str] = mapped_column(String(200))
    session_id: Mapped[str] = mapped_column(String(40), index=True)
    root: Mapped[str] = mapped_column(String(220))
    path: Mapped[str] = mapped_column(String(4200))
    can_write: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WopiLockRow(Base):
    __tablename__ = "wopi_locks"
    file_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    root: Mapped[str] = mapped_column(String(220))
    path: Mapped[str] = mapped_column(String(4200))
    lock_id: Mapped[str] = mapped_column(String(MAX_LOCK_LEN))
    person_id: Mapped[str] = mapped_column(String(200))
    base_version: Mapped[str] = mapped_column(String(64))   # sha256 the lock holder last saw or wrote
    size: Mapped[int] = mapped_column(BigInteger)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def file_id_for(root: str, path: str) -> str:
    """A stable opaque id for (root, path): every token for one file shares its lock."""
    return "wf_" + hashlib.sha256(f"{root}\x00{path}".encode()).hexdigest()[:40]


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def unauthenticated(message: str = "missing, unknown or expired WOPI access token") -> FilesError:
    return FilesError(401, "unauthenticated", message, reason="wopi_token", headers={"WWW-Authenticate": "Bearer"})


def lock_conflict(current: str, message: str, reason: str) -> FilesError:
    """WOPI: a lock mismatch is 409 and names the file's current lock ('' when there is none)."""
    return FilesError(409, "conflict", message, reason=reason, headers={"X-WOPI-Lock": current})


class WopiRepository(SqlRepository):
    def add_token(self, row: WopiTokenRow) -> None:
        with self.db.session.begin() as s:
            s.add(row)

    def token(self, secret_hash: str) -> WopiTokenRow | None:
        with self.db.session() as s:
            return s.scalars(select(WopiTokenRow).where(WopiTokenRow.secret_hash == secret_hash)).first()

    def drop_expired_tokens(self, now: datetime) -> None:
        with self.db.session.begin() as s:
            s.execute(delete(WopiTokenRow).where(WopiTokenRow.expires_at < now))

    def lock(self, file_id: str, now: datetime) -> WopiLockRow | None:
        """The live lock of a file; an expired one is gone (WOPI treats it as unlocked)."""
        with self.db.session() as s:
            row = s.get(WopiLockRow, file_id)
            return row if row is not None and utc(row.expires_at) > now else None

    def put_lock(self, row: WopiLockRow) -> None:
        with self.db.session.begin() as s:
            s.merge(row)

    def drop_lock(self, file_id: str) -> None:
        with self.db.session.begin() as s:
            s.execute(delete(WopiLockRow).where(WopiLockRow.file_id == file_id))


@dataclass
class Grant:
    """A WOPI call that passed every check: who, which file, and what the token allows."""

    principal: Principal
    token: WopiTokenRow
    target: Target

    @property
    def file_id(self) -> str:
        return self.token.file_id


class WopiHost:
    def __init__(self, files: FilesService, repo: WopiRepository | None = None):
        self.files = files
        self.gw = files.gw
        self.repo = repo or WopiRepository(files.repo.db)
        self.clock = files.clock

    # ---- tokens -------------------------------------------------------------------------------
    def issue(self, p: Principal, session_id: str | None, root: str | None, path: str | None) -> dict:
        """Mint a token for one file. `session_id` is the caller's live sign-in session, None otherwise."""
        if p.kind != "person":
            raise self.files._deny(p, "files wopi token", "only a person opens a document in the editor", "not_a_person")
        if not session_id:
            raise self.files._deny(p, "files wopi token", "open documents from a signed-in session, not with an API token",
                                   "not_a_session")
        t = self.files.target(p, root, path, "read")
        if not t.parts:
            raise conflict("a space is a folder, not a file", "not_a_file")
        st = self._stat_file(t)
        can_write = self.files.access(p, t.root, t.parts).write
        now = self.clock()
        secret = TOKEN_PREFIX + secrets.token_urlsafe(32)
        row = WopiTokenRow(id=new_id("wtk"), secret_hash=_hash(secret), file_id=file_id_for(t.root.id, t.path),
                           person_id=p.id, session_id=session_id, root=t.root.id, path=t.path, can_write=can_write,
                           created_at=now, expires_at=now + TOKEN_TTL)
        self.repo.drop_expired_tokens(now - timedelta(days=1))
        self.repo.add_token(row)
        self.files.event("wopi.token.issued", p, {"root": t.root.id, "path": t.path, "file_id": row.file_id,
                                                   "can_write": can_write, "session_id": session_id, "size": st.st_size})
        return {"access_token": secret, "access_token_ttl": int(row.expires_at.timestamp() * 1000),
                "expires_at": iso(row.expires_at), "file_id": row.file_id,
                "wopi_src": f"/v1/files/wopi/files/{row.file_id}", "can_write": can_write}

    def resolve(self, access_token: str | None, file_id: str, need: str = "read") -> Grant:
        """Every WOPI call starts here: token, file, session, person and role are checked again."""
        if not access_token or not access_token.startswith(TOKEN_PREFIX) or len(access_token) > 200:
            raise unauthenticated()
        now = self.clock()
        row = self.repo.token(_hash(access_token))
        if row is None or utc(row.expires_at) <= now or row.file_id != file_id:
            raise unauthenticated()
        p = self._live_person(row, now)
        if p is None:
            raise unauthenticated("the sign-in session behind this WOPI token has ended")
        try:
            t = self.files.target(p, row.root, row.path, "read")
        except FilesError:
            raise unauthenticated("this person can no longer open the file") from None
        if need == "write" and not (row.can_write and self.files.access(p, t.root, t.parts).write):
            raise self.files._deny(p, "files wopi write", "this document is open read-only", "read_only")
        return Grant(p, row, t)

    def _live_person(self, row: WopiTokenRow, now: datetime) -> Principal | None:
        from ..identity.models import SessionRow, UserRow
        from ..identity.settings import IdentitySettings

        with self.repo.db.session() as s:
            ses = s.get(SessionRow, row.session_id)
            user = s.get(UserRow, row.person_id)
        if ses is None or user is None or user.disabled or ses.user_id != user.id:
            return None
        if ses.revoked_at is not None or utc(ses.expires_at) <= now:
            return None
        if ses.transport == "cookie":
            idle = timedelta(hours=self.gw.settings.section(IdentitySettings).session_idle_hours)
            if now - utc(ses.last_seen_at) >= idle:
                return None
        return Principal(id=user.id, kind="person", role=user.role)

    # ---- files --------------------------------------------------------------------------------
    def _stat_file(self, t: Target) -> os.stat_result:
        with self.files._space(t.root) as space, paths.dir_at(space, t.parts[:-1]) as d:
            st = paths.lstat_at(d, t.parts[-1])
        if not stat_mod.S_ISREG(st.st_mode):
            raise conflict("not a regular file", "not_a_file") if paths.kind_of(st) != "symlink" else \
                FilesError(403, "permission_denied", "the path is a symbolic link, which FILES never follows", reason="symlink")
        return st

    def _read(self, t: Target) -> tuple[bytes, os.stat_result]:
        with self.files._space(t.root) as space, paths.dir_at(space, t.parts[:-1]) as d:
            fd, st = paths.open_file_at(d, t.parts[-1])
        try:
            chunks = []
            while chunk := os.read(fd, READ_CHUNK):
                chunks.append(chunk)
        finally:
            os.close(fd)
        return b"".join(chunks), st

    def _version(self, t: Target) -> tuple[str, os.stat_result]:
        data, st = self._read(t)
        return hashlib.sha256(data).hexdigest(), st

    def check_file_info(self, g: Grant) -> dict:
        version, st = self._version(g.target)
        writable = g.token.can_write and self.files.access(g.principal, g.target.root, g.target.parts).write
        return {
            "BaseFileName": g.target.parts[-1],
            "OwnerId": g.target.root.id,
            "Size": st.st_size,
            "UserId": g.principal.id,
            "Version": version,
            "SHA256": base64.b64encode(bytes.fromhex(version)).decode(),
            "LastModifiedTime": iso(datetime.fromtimestamp(st.st_mtime, tz=UTC)),
            "UserCanWrite": writable,
            "ReadOnly": not writable,
            "SupportsLocks": True,
            "SupportsGetLock": True,
            "SupportsUpdate": True,
            "UserCanNotWriteRelative": True,
            "SupportsRename": False,
        }

    def get_file(self, g: Grant) -> tuple[bytes, str]:
        data, st = self._read(g.target)
        version = hashlib.sha256(data).hexdigest()
        self.files.event("wopi.opened", g.principal, {"root": g.target.root.id, "path": g.target.path,
                                                      "file_id": g.file_id, "size": st.st_size, "version": version})
        return data, version

    # ---- locks (WOPI Lock, Unlock, RefreshLock, GetLock, UnlockAndRelock) ---------------------
    @staticmethod
    def _lock_id(value: str | None) -> str:
        if not value or len(value) > MAX_LOCK_LEN or not value.isascii() or not value.isprintable():
            raise FilesError(422, "conflict", "send X-WOPI-Lock: 1 to 1024 printable ASCII characters", reason="wopi_lock")
        return value

    def get_lock(self, g: Grant) -> str:
        row = self.repo.lock(g.file_id, self.clock())
        return row.lock_id if row else ""

    def lock(self, g: Grant, lock_id: str | None, old_lock: str | None = None) -> str:
        lock_id = self._lock_id(lock_id)
        now = self.clock()
        with self.files._lock:
            current = self.repo.lock(g.file_id, now)
            if old_lock is not None:  # UnlockAndRelock
                if current is None or current.lock_id != old_lock:
                    raise lock_conflict(current.lock_id if current else "", "the file's lock is not X-WOPI-OldLock",
                                        "lock_mismatch")
            elif current is not None and current.lock_id != lock_id:
                raise lock_conflict(current.lock_id, "the file is locked by another editing session", "locked")
            if current is None:  # a new lock starts from the bytes on disk now
                version, st = self._version(g.target)
                size = st.st_size
            else:  # the same lock again (a refresh) or a relock: keep the version its holder saw
                version, size = current.base_version, current.size
            self.repo.put_lock(WopiLockRow(file_id=g.file_id, root=g.target.root.id, path=g.target.path, lock_id=lock_id,
                                           person_id=g.principal.id, base_version=version, size=size,
                                           expires_at=now + LOCK_TTL, updated_at=now))
        if current is None or old_lock is not None:  # a refresh by Lock is not a new event
            self.files.event("wopi.locked", g.principal, {"root": g.target.root.id, "path": g.target.path,
                                                          "file_id": g.file_id, "version": version})
        return version

    def refresh_lock(self, g: Grant, lock_id: str | None) -> None:
        lock_id = self._lock_id(lock_id)
        now = self.clock()
        with self.files._lock:
            current = self.repo.lock(g.file_id, now)
            if current is None or current.lock_id != lock_id:
                raise lock_conflict(current.lock_id if current else "", "the file does not hold this lock", "lock_mismatch")
            current.expires_at, current.updated_at = now + LOCK_TTL, now
            self.repo.put_lock(current)

    def unlock(self, g: Grant, lock_id: str | None) -> str:
        lock_id = self._lock_id(lock_id)
        with self.files._lock:
            current = self.repo.lock(g.file_id, self.clock())
            if current is None or current.lock_id != lock_id:
                raise lock_conflict(current.lock_id if current else "", "the file does not hold this lock", "lock_mismatch")
            self.repo.drop_lock(g.file_id)
        version, _ = self._version(g.target)
        self.files.event("wopi.unlocked", g.principal, {"root": g.target.root.id, "path": g.target.path,
                                                        "file_id": g.file_id, "version": version})
        return version

    # ---- PutFile ------------------------------------------------------------------------------
    def put_file(self, g: Grant, lock_id: str | None, data: bytes) -> str:
        """Replace the file's bytes in one rename. Needs the current lock and an unchanged file (409 otherwise)."""
        now = self.clock()
        t = g.target
        with self.files._lock:
            current = self.repo.lock(g.file_id, now)
            if current is None:
                raise lock_conflict("", "lock the file before saving it", "not_locked")
            if lock_id != current.lock_id:
                raise lock_conflict(current.lock_id, "the file is locked by another editing session", "lock_mismatch")
            on_disk, st = self._version(t)
            if on_disk != current.base_version:
                raise FilesError(409, "stale_precondition", "the file changed since it was opened; reopen it to save",
                                 reason="stale_version", headers={"X-WOPI-Lock": current.lock_id})
            self.files.check_space(t.root, len(data) - st.st_size)
            version = hashlib.sha256(data).hexdigest()
            tmp = f"wopi-{secrets.token_hex(8)}.part"
            with self.files._system("wopi") as work:
                fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640, dir_fd=work)
                try:
                    view = memoryview(data)
                    while view:
                        view = view[os.write(fd, view):]
                    os.fsync(fd)
                finally:
                    os.close(fd)
                try:
                    with self.files._space(t.root) as space, paths.dir_at(space, t.parts[:-1]) as d:
                        if not stat_mod.S_ISREG(paths.lstat_at(d, t.parts[-1]).st_mode):
                            raise not_found("the file is gone")
                        os.rename(tmp, t.parts[-1], src_dir_fd=work, dst_dir_fd=d)
                        os.fsync(d)
                except BaseException:
                    try:
                        os.unlink(tmp, dir_fd=work)
                    except FileNotFoundError:
                        pass
                    raise
            current.base_version, current.size, current.updated_at = version, len(data), now
            self.repo.put_lock(current)
        self.files.reindex(t.root, t.parts, depth=0, known_hash="sha256:" + version)
        self.files.event("wopi.saved", g.principal, {"root": t.root.id, "path": t.path, "file_id": g.file_id,
                                                     "size": len(data), "sha256": version, "previous": on_disk})
        return version


__all__ = ["LOCK_TTL", "SCHEMA", "TOKEN_TTL", "WopiHost", "WopiLockRow", "WopiRepository", "WopiTokenRow", "file_id_for"]
