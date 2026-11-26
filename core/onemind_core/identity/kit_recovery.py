# SPDX-License-Identifier: Apache-2.0
"""Recover owner access at the box with the printed emergency kit (gateway permissions design 25c, D-028).

Path 2 of design section 3.13: an owner who lost every passkey stands at the box, types the kit's owner key on the
box's own console, and gets owner access back. The console program is `onemindd recover-owner` (on tty2) or
`onemind recovery kit` run as root on the box; it talks to this gateway on loopback and presents the CONSOLE
KEY, a random secret in a 0600 file next to the gateway's data that only the gateway's user and root can read. A
network client never has it, so these routes refuse every caller that is not the box's own console.

What a kit session (15 minutes) can do: set a new password, turn off the authenticator code, remove lost passkeys,
end sessions, and make a one-time sign-in code that lets a phone or laptop add a new passkey. It cannot approve
anything, change any setting, delete or reset anything, or show any key. Wrong kit keys: 5 tries, then a wait of
15 minutes that doubles after each further lockout up to 24 hours. A lockout never wipes or deletes anything.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Request
from sqlalchemy import DateTime, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column

from ..errors import ApiError
from ..ledger import Base
from .crypto import hash_password
from .models import PasskeyRow, SessionRow, UserRow, utc

CONSOLE_HEADER = "OneMind-Console"
SESSION_HEADER = "OneMind-Kit-Session"
SESSION_TTL = timedelta(minutes=15)
CODE_TTL = timedelta(minutes=15)
TRIES = 5
FIRST_LOCK = timedelta(minutes=15)
MAX_LOCK = timedelta(hours=24)
FORWARDING = ("forwarded", "x-forwarded-for", "x-real-ip", "x-forwarded-host")
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L: read off a screen and typed on a phone


class KitAttemptRow(Base):
    """Wrong kit keys at the console (one row, id "kit"). A new table: create_all adds it to an existing database."""
    __tablename__ = "identity_kit_attempts"
    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    lockouts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


@dataclass
class _Session:
    expires_at: datetime


@dataclass
class _Code:
    user_id: str
    expires_at: datetime


def load_or_create_console_key(path: Path) -> str:
    """The console key: 32 random bytes as hex, 0600. Written durably (temp, fsync, rename, fsync the folder)."""
    try:
        text = path.read_text(encoding="ascii").strip()
        if len(text) == 64:
            return text
    except FileNotFoundError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_hex(32)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, (key + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    dfd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)
    return key


class KitRecovery:
    def __init__(self, identity, backups, key_file: Path):
        self.id = identity
        self.backups = backups
        self.key_file = key_file
        self._key: str | None = None
        self._sessions: dict[str, _Session] = {}  # sha256(token) -> session; memory only, a restart ends them
        self._codes: dict[str, _Code] = {}        # sha256(code) -> one-time sign-in code
        self._lock = threading.Lock()

    def now(self) -> datetime:
        return self.id.now()

    def key(self) -> str:
        if self._key is None:
            self._key = load_or_create_console_key(self.key_file)
        return self._key

    def _refuse(self, request: Request, why: str) -> ApiError:
        self.id.emit("authz", "denied", {"attempted": "owner recovery with the kit", "reason": "console_only",
                                         "detail": why, "source": request.client.host if request.client else "unknown"},
                     severity="warning")
        return ApiError(403, "permission_denied", "owner recovery with the kit works only on the box's own console",
                        reason="console_only")

    def require_console(self, request: Request) -> None:
        """Loopback, no proxy headers, and the console key: only the box's own console gets past this."""
        host = request.client.host if request.client else ""
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = False
        if not loopback or any(h in request.headers for h in FORWARDING):
            raise self._refuse(request, "not_loopback")
        given = request.headers.get(CONSOLE_HEADER, "")
        if not given or not hmac.compare_digest(given.encode(), self.key().encode()):
            raise self._refuse(request, "no_console_key")

    # ---- the kit key, with a doubling lockout that never deletes anything ----------------------------------
    def _attempts(self) -> KitAttemptRow:
        row = self.id.repo.get(KitAttemptRow, "kit")
        if row is None:
            row = KitAttemptRow(id="kit", failures=0, lockouts=0, locked_until=None)
            self.id.repo.add(row)
        return row

    def unlock(self, groups: list[str], check: str) -> dict:
        now = self.now()
        with self._lock:
            row = self._attempts()
            until = utc(row.locked_until)
            if until is not None and until > now:
                raise ApiError(429, "rate_limited", "too many wrong kit keys; wait before trying again",
                               reason="kit_locked", retry_after_s=int((until - now).total_seconds()) + 1)
            if self.backups is None:
                raise ApiError(409, "stale_precondition", "backups are off, so this box has no emergency kit",
                               reason="no_kit")
            state = self.backups.kit_state()["state"]
            if state == "missing":
                raise ApiError(409, "stale_precondition", "no emergency kit was made on this box", reason="no_kit")
            try:
                self.backups.check_kit_key(groups, check)
            except ApiError as exc:
                if exc.status == 422:  # a typo the check group caught: not a guess, not counted
                    raise
                failures, lockouts, locked = row.failures + 1, row.lockouts, None
                if failures >= TRIES:
                    locked = now + min(FIRST_LOCK * (2 ** lockouts), MAX_LOCK)
                    failures, lockouts = 0, lockouts + 1
                self.id.repo.update(KitAttemptRow, [KitAttemptRow.id == "kit"],
                                    {"failures": failures, "lockouts": lockouts, "locked_until": locked})
                self.id.emit("auth", "recovery.kit.failed", {"locked_until": locked.isoformat() if locked else None},
                             severity="warning")
                raise ApiError(401, "unauthenticated", "that is not this box's kit key", reason="kit_wrong") from None
            self.id.repo.update(KitAttemptRow, [KitAttemptRow.id == "kit"],
                                {"failures": 0, "lockouts": 0, "locked_until": None})
            token = secrets.token_urlsafe(32)
            self._sessions = {k: v for k, v in self._sessions.items() if v.expires_at > now}
            self._sessions[hashlib.sha256(token.encode()).hexdigest()] = _Session(now + SESSION_TTL)
        # Every owner device (and, once they exist, every approver and recovery contact) is told.
        self.id.emit("auth", "recovery.kit.unlocked", {"via": "console", "kit_state": state}, severity="critical")
        return {"session": token, "expires_at": (now + SESSION_TTL).isoformat(), "owners": self.owners()}

    def require_session(self, request: Request) -> None:
        self.require_console(request)
        token = request.headers.get(SESSION_HEADER, "")
        s = self._sessions.get(hashlib.sha256(token.encode()).hexdigest()) if token else None
        if s is None or s.expires_at <= self.now():
            raise ApiError(401, "unauthenticated", "the kit session ended; type the kit key again",
                           reason="kit_session_ended")

    # ---- what a kit session may do -----------------------------------------------------------------------
    def owners(self) -> list[dict]:
        out = []
        for uid in self.id.active_owner_ids():
            u = self.id.user(uid)
            keys = self.id.repo.all(select(PasskeyRow).where(PasskeyRow.user_id == uid))
            out.append({"user_id": u.id, "username": u.username, "display_name": u.display_name,
                        "authenticator": bool(u.totp_secret),
                        "passkeys": [{"credential_id": k.id, "label": k.label} for k in keys]})
        return out

    def _owner(self, user_id: str) -> UserRow:
        if user_id not in self.id.active_owner_ids():
            raise ApiError(404, "not_found", "no such owner")
        return self.id.user(user_id)

    def set_password(self, user_id: str, password: str) -> None:
        u = self._owner(user_id)
        self.id._check_password(password)
        now = self.now()
        self.id.repo.update(UserRow, [UserRow.id == u.id], {"password_hash": hash_password(password), "updated_at": now})
        # Whoever held the old password is signed out everywhere.
        self.id.repo.update(SessionRow, [SessionRow.user_id == u.id, SessionRow.revoked_at.is_(None)], {"revoked_at": now})
        self.id.emit("auth", "recovery.kit.password_set", {"user_id": u.id, "sessions_revoked": True}, severity="critical")

    def clear_authenticator(self, user_id: str) -> None:
        u = self._owner(user_id)
        self.id.repo.update(UserRow, [UserRow.id == u.id], {"totp_secret": None, "totp_pending": None,
                                                            "totp_last_step": None, "updated_at": self.now()})
        self.id.emit("auth", "recovery.kit.authenticator_cleared", {"user_id": u.id}, severity="critical")

    def remove_passkey(self, user_id: str, credential_id: str) -> None:
        """A lost key is cut off. Removing a key deletes no data; the owner adds a new one with a sign-in code."""
        u = self._owner(user_id)
        row = self.id.repo.get(PasskeyRow, credential_id)
        if row is None or row.user_id != u.id:
            raise ApiError(404, "not_found", "no such passkey")
        self.id.repo.delete(PasskeyRow, PasskeyRow.id == row.id)
        self.id.emit("auth", "recovery.kit.passkey_removed", {"user_id": u.id, "credential_id": row.id},
                     severity="critical")

    def sign_in_code(self, user_id: str) -> dict:
        """A one-time code (15 minutes) that signs this owner in on a phone or laptop to add a new passkey."""
        u = self._owner(user_id)
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(12))
        now = self.now()
        with self._lock:
            self._codes = {k: v for k, v in self._codes.items() if v.expires_at > now}
            self._codes[hashlib.sha256(code.encode()).hexdigest()] = _Code(u.id, now + CODE_TTL)
        self.id.emit("auth", "recovery.kit.code_issued", {"user_id": u.id}, severity="warning")
        return {"code": f"{code[:4]}-{code[4:8]}-{code[8:]}", "expires_at": (now + CODE_TTL).isoformat()}

    def redeem(self, code: str) -> UserRow:
        """The phone side, from the network: single use, and only with a code made at the console."""
        norm = "".join(c for c in (code or "").upper() if c in CODE_ALPHABET)
        with self._lock:
            c = self._codes.pop(hashlib.sha256(norm.encode()).hexdigest(), None)
        if c is None or c.expires_at <= self.now():
            raise ApiError(401, "unauthenticated", "unknown, used or expired recovery code", reason="code_unknown")
        u = self.id._live_user(c.user_id)
        if u is None or u.role != "owner":
            raise ApiError(401, "unauthenticated", "unknown, used or expired recovery code", reason="code_unknown")
        return u
