# SPDX-License-Identifier: Apache-2.0
"""Household identity (contract §12.6): accounts, sign-in, sessions, passkeys, API tokens, sharing.

Every decision is audited through gw.events (auth.*, authz.denied, user.*, app.access.*). Secrets
(passwords, tokens, session cookies, refresh tokens, enrolment codes) are stored only as hashes and
never appear in the audit; a response carries them once under `one_time`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from fastapi import Request
from sqlalchemy import or_, select

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError
from . import passkeys as pk
from . import scopes as sc
from .crypto import (
    PASSWORD_MAX,
    PASSWORD_MIN,
    TOKEN_KINDS,
    b64url,
    hash_password,
    new_id,
    new_secret,
    new_totp_secret,
    otpauth_uri,
    sha256_hex,
    totp_match,
    verify_password,
)
from .models import (
    AppAccessRow,
    ChallengeRow,
    IdentityRepository,
    PasskeyRow,
    SessionRow,
    TokenRow,
    UserRow,
    iso,
    utc,
)
from .settings import IdentitySettings

log = logging.getLogger("onemind.identity")

PERSON_ROLES = ("owner", "adult", "guest", "child")
USERNAME_RE = re.compile(r"[a-z][a-z0-9._-]{1,31}")
AGENT_ID_RE = re.compile(r"agent:[a-z0-9][a-z0-9._-]{0,62}")
CSRF_HEADER = "onemind-csrf"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
TOUCH_EVERY = timedelta(seconds=60)  # last_seen / last_used are written at most once a minute
CHALLENGE_TTL = timedelta(seconds=120)
ENROL_TTL = timedelta(hours=24)
PAT_DEFAULT_DAYS, PAT_MAX_DAYS = 90, 365
AGENT_DEFAULT_DAYS = AGENT_MAX_DAYS = 90  # F-15: personal agent tokens, renewable
MAX_GRACE_S = 3600


@dataclass
class AuthContext:
    """How an identity principal authenticated; request.state.identity. Absent for static-file tokens."""

    principal: Principal
    scopes: frozenset[str]
    user: UserRow | None = None
    session: SessionRow | None = None
    token: TokenRow | None = None


def ctx_of(request: Request) -> AuthContext | None:
    return getattr(request.state, "identity", None)


def source_of(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@dataclass
class FailureLimiter:
    """§12.1: wrong logins, tokens and codes: N per minute per source, then a back-off."""

    per_min: int
    lockout: timedelta
    _fails: dict[str, deque] = field(default_factory=dict)
    _locked: dict[str, datetime] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def check(self, key: str, now: datetime) -> None:
        with self._lock:
            until = self._locked.get(key)
            if until is not None and until > now:
                wait = int((until - now).total_seconds()) + 1
                raise ApiError(429, "rate_limited", "too many failed attempts; try again later",
                               reason="too_many_failures", retry_after_s=wait)
            self._locked.pop(key, None)

    def fail(self, key: str, now: datetime) -> None:
        with self._lock:
            q = self._fails.setdefault(key, deque())
            q.append(now)
            while q and (now - q[0]).total_seconds() > 60:
                q.popleft()
            if len(q) >= self.per_min:
                self._locked[key] = now + self.lockout
                q.clear()
            if len(self._fails) > 10_000:  # bounded memory under a spray of sources
                self._fails.pop(next(iter(self._fails)))


class IdentityService:
    def __init__(self, gw: Gateway):
        self.gw = gw
        self.cfg = gw.settings.section(IdentitySettings)
        self.repo = IdentityRepository(gw.db)
        self.limiter = FailureLimiter(self.cfg.login_failures_per_min, timedelta(minutes=self.cfg.lockout_minutes))
        secure = self.cfg.cookie_secure
        # __Host- cookies must be Secure, path=/ and host-only: they cannot be set by a sibling name.
        self.cookie = "__Host-onemind_session" if secure else "onemind_session"
        self.csrf_cookie = "__Host-onemind_csrf" if secure else "onemind_csrf"

    # ---- helpers ---------------------------------------------------------------------------------
    def now(self) -> datetime:
        return self.gw.clock()

    def emit(self, domain: str, name: str, payload: dict, p: Principal | None = None, severity: str = "info") -> None:
        self.gw.events.publish_event(domain, name, payload, principal=p.as_dict() if p else None, severity=severity)

    def deny(self, p: Principal | None, what: str, **extra) -> ApiError:
        self.emit("authz", "denied", {"attempted": what, **extra}, p, severity="warning")
        return ApiError(403, "permission_denied", f"not allowed to {what}")

    @staticmethod
    def principal_for(user: UserRow) -> Principal:
        return Principal(id=user.id, kind="person", role=user.role)

    def user(self, user_id: str) -> UserRow | None:
        return self.repo.get(UserRow, user_id)

    def active_owner_ids(self) -> list[str]:
        return list(self.repo.all(select(UserRow.id).where(UserRow.role == "owner", UserRow.disabled.is_(False))))

    def passkeys_active(self) -> bool:
        """F-2: once any active owner has a passkey, owner approvals and administration need one."""
        owners = self.active_owner_ids()
        return bool(owners) and self.repo.count(PasskeyRow, PasskeyRow.user_id.in_(owners)) > 0

    def rp(self, request: Request) -> tuple[str, list[str]]:
        host = request.headers.get("host") or (request.url.hostname or "localhost")
        rp_id = self.cfg.rp_id or host.rsplit(":", 1)[0].strip("[]")
        if self.cfg.origins:
            return rp_id, list(self.cfg.origins)
        origins = {f"https://{rp_id}", f"https://{host}"}
        if rp_id in ("localhost", "127.0.0.1"):
            origins |= {f"http://{rp_id}", f"http://{host}"}
        return rp_id, sorted(origins)

    @staticmethod
    def _check_password(password: str) -> None:
        if not isinstance(password, str) or not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
            raise ApiError(422, "conflict", f"password must be {PASSWORD_MIN} to {PASSWORD_MAX} characters",
                           reason="weak_password")

    # ---- authentication: the gateway's Authenticator hook --------------------------------------
    def authenticate(self, request: Request, token: str | None) -> Principal | None:
        now = self.now()
        if token is None:
            raw = request.cookies.get(self.cookie)
            if not raw:
                return None
            ctx = self._cookie_session(request, raw, now)
        elif token.startswith("om_ses_"):
            ctx = self._bearer_session(token, now)
        elif token.startswith("om_"):
            ctx = self._api_token(token, now)
        else:
            return None
        if ctx is None:
            return None
        required = sc.required_scopes(request.method, request.url.path)
        if required is not None and not sc.has_any(ctx.scopes, required):
            raise self.deny(ctx.principal, f"{request.method} {request.url.path}",
                            required=list(required), reason="scope")
        request.state.identity = ctx
        return ctx.principal

    def _session_scopes(self, user: UserRow) -> frozenset[str]:
        return sc.role_scopes(user.role) if self.cfg.enforce_role_scopes else frozenset({sc.ALL})

    def _live_user(self, user_id: str | None) -> UserRow | None:
        u = self.user(user_id) if user_id else None
        return u if u is not None and not u.disabled else None

    def _touch_session(self, s: SessionRow, user: UserRow, now: datetime) -> None:
        if now - utc(s.last_seen_at) >= TOUCH_EVERY:
            self.repo.update(SessionRow, [SessionRow.id == s.id], {"last_seen_at": now})
            self.repo.update(UserRow, [UserRow.id == user.id], {"last_seen_at": now})

    def _cookie_session(self, request: Request, raw: str, now: datetime) -> AuthContext | None:
        s = self.repo.one(select(SessionRow).where(SessionRow.secret_hash == sha256_hex(raw)))
        if s is None or s.transport != "cookie" or not self._session_live(s, now):
            return None
        user = self._live_user(s.user_id)
        if user is None:
            return None
        # H-16: a cookie rides along with cross-site requests, so every unsafe method must also
        # carry the session's CSRF token in a header a cross-site form or image cannot set.
        if request.method not in SAFE_METHODS:
            sent = request.headers.get(CSRF_HEADER, "")
            if not (sent and s.csrf_hash and hmac.compare_digest(sha256_hex(sent), s.csrf_hash)):
                self.emit("authz", "denied", {"attempted": f"{request.method} {request.url.path}", "reason": "csrf"},
                          self.principal_for(user), severity="warning")
                raise ApiError(403, "permission_denied", "missing or wrong OneMind-CSRF header", reason="csrf")
        self._touch_session(s, user, now)
        return AuthContext(self.principal_for(user), self._session_scopes(user), user=user, session=s)

    def _session_live(self, s: SessionRow, now: datetime) -> bool:
        if s.revoked_at is not None or utc(s.expires_at) <= now:
            return False
        if s.transport == "cookie":
            return now - utc(s.last_seen_at) < timedelta(hours=self.cfg.session_idle_hours)
        return True

    def _bearer_session(self, token: str, now: datetime) -> AuthContext | None:
        s = self.repo.one(select(SessionRow).where(SessionRow.secret_hash == sha256_hex(token)))
        if s is None or s.transport != "bearer" or not self._session_live(s, now):
            return None
        if s.access_expires_at is None or utc(s.access_expires_at) <= now:
            return None
        user = self._live_user(s.user_id)
        if user is None:
            return None
        self._touch_session(s, user, now)
        return AuthContext(self.principal_for(user), self._session_scopes(user), user=user, session=s)

    def _api_token(self, token: str, now: datetime) -> AuthContext | None:
        h = sha256_hex(token)
        t = self.repo.one(select(TokenRow).where(TokenRow.hash == h))
        if t is None:  # the previous secret of a rotated token, inside its grace period
            t = self.repo.one(select(TokenRow).where(TokenRow.prev_hash == h))
            if t is None or t.prev_valid_until is None or utc(t.prev_valid_until) <= now:
                return None
        if t.revoked_at is not None or (t.expires_at is not None and utc(t.expires_at) <= now):
            return None
        owner = None
        if t.owner_user_id is not None:
            owner = self._live_user(t.owner_user_id)
            if owner is None:  # a disabled or deleted person's tokens die with them
                return None
        if t.kind == "person":
            if owner is None:
                return None
            principal = self.principal_for(owner)
        else:
            principal = Principal(id=t.principal_id, kind=t.kind, role=t.kind)
        granted = frozenset(s for s in t.scopes if sc.allowed_for_kind(s, t.kind))
        if owner is not None and self.cfg.enforce_role_scopes:  # never beyond the owning person today
            cap = sc.role_scopes(owner.role)
            granted = frozenset(s for s in granted if sc.within(s, cap) or (s == sc.ALL and sc.ALL in cap))
        if t.last_used_at is None or now - utc(t.last_used_at) >= TOUCH_EVERY:
            self.repo.update(TokenRow, [TokenRow.id == t.id], {"last_used_at": now})
        return AuthContext(principal, granted, user=owner if t.kind == "person" else None, token=t)

    # ---- sessions --------------------------------------------------------------------------------
    def _client_label(self, request: Request, client: str | None) -> str:
        label = client or request.headers.get("user-agent") or "unknown"
        return label[:200]

    def start_session(self, request: Request, user: UserRow, method: str, client: str | None,
                      bearer: bool, passkey: bool) -> dict:
        """Create a session; returns the body, with secrets, and `_cookies` for the router to set."""
        now = self.now()
        sid = new_id("ses")
        out: dict = {}
        common = dict(id=sid, user_id=user.id, client=self._client_label(request, client), auth_method=method,
                      passkey_at=now if passkey else None, created_at=now, last_seen_at=now)
        if bearer:
            access, refresh = new_secret("ses"), new_secret("ref")
            access_exp = now + timedelta(minutes=self.cfg.access_token_minutes)
            exp = now + timedelta(days=self.cfg.refresh_days)
            row = SessionRow(transport="bearer", secret_hash=sha256_hex(access), refresh_hash=sha256_hex(refresh),
                             access_expires_at=access_exp, expires_at=exp, **common)
            out.update(access_token=access, expires_at=iso(access_exp), refresh_token=refresh,
                       refresh_expires_at=iso(exp))
        else:
            cookie, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            exp = now + timedelta(days=self.cfg.session_max_days)
            row = SessionRow(transport="cookie", secret_hash=sha256_hex(cookie), csrf_hash=sha256_hex(csrf),
                             expires_at=exp, **common)
            out.update(csrf_token=csrf, _cookies={"session": cookie, "csrf": csrf, "max_age": int((exp - now).total_seconds())})
        self.repo.add(row)
        self.repo.update(UserRow, [UserRow.id == user.id], {"last_seen_at": now})
        p = self.principal_for(user)
        self.emit("auth", "login.succeeded", {"user_id": user.id, "method": method, "session_id": sid,
                                              "transport": row.transport, "source": source_of(request)}, p)
        out.update(session={"id": sid, "expires_at": iso(exp)},
                   principal={**p.as_dict(), "display_name": user.display_name})
        return out

    def session_json(self, s: SessionRow, current: SessionRow | None) -> dict:
        return {"id": s.id, "principal_id": s.user_id, "client": s.client, "transport": s.transport,
                "auth_method": s.auth_method, "created_at": iso(s.created_at), "last_seen_at": iso(s.last_seen_at),
                "expires_at": iso(s.expires_at), "current": current is not None and current.id == s.id}

    def list_sessions(self, ctx: AuthContext | None, p: Principal) -> list[dict]:
        now = self.now()
        q = select(SessionRow).where(SessionRow.revoked_at.is_(None)).order_by(SessionRow.created_at)
        if not p.is_owner:
            if ctx is None or ctx.user is None:
                return []
            q = q.where(SessionRow.user_id == ctx.user.id)
        current = ctx.session if ctx else None
        return [self.session_json(s, current) for s in self.repo.all(q) if self._session_live(s, now)]

    def revoke_session(self, ctx: AuthContext | None, p: Principal, session_id: str) -> None:
        s = self.repo.get(SessionRow, session_id)
        mine = s is not None and ctx is not None and ctx.user is not None and s.user_id == ctx.user.id
        if s is None or not (mine or p.is_owner):
            raise ApiError(404, "not_found", "no such session")
        self.repo.update(SessionRow, [SessionRow.id == s.id, SessionRow.revoked_at.is_(None)], {"revoked_at": self.now()})
        self.emit("auth", "session.revoked", {"session_id": s.id, "user_id": s.user_id}, p)

    def logout(self, ctx: AuthContext | None) -> None:
        if ctx is None or ctx.session is None:
            raise ApiError(409, "conflict", "this credential is not a session", reason="not_a_session")
        self.repo.update(SessionRow, [SessionRow.id == ctx.session.id], {"revoked_at": self.now()})
        self.emit("auth", "logout", {"session_id": ctx.session.id}, ctx.principal)

    def refresh(self, request: Request, refresh_token: str) -> dict:
        now, src = self.now(), source_of(request)
        self.limiter.check(src, now)
        s = self.repo.one(select(SessionRow).where(SessionRow.refresh_hash == sha256_hex(refresh_token or "")))
        user = self._live_user(s.user_id) if s is not None else None
        if s is None or s.transport != "bearer" or not self._session_live(s, now) or user is None:
            self.limiter.fail(src, now)
            self.emit("auth", "refresh.failed", {"source": src}, severity="warning")
            raise ApiError(401, "unauthenticated", "unknown or expired refresh token")
        access, refresh = new_secret("ses"), new_secret("ref")
        access_exp = now + timedelta(minutes=self.cfg.access_token_minutes)
        done = self.repo.update(
            SessionRow, [SessionRow.id == s.id, SessionRow.refresh_hash == s.refresh_hash],
            {"secret_hash": sha256_hex(access), "refresh_hash": sha256_hex(refresh),
             "access_expires_at": access_exp, "last_seen_at": now},
        )
        if not done:  # a concurrent refresh won
            raise ApiError(401, "unauthenticated", "refresh token already used")
        self.emit("auth", "session.refreshed", {"session_id": s.id}, self.principal_for(user))
        return {"access_token": access, "expires_at": iso(access_exp), "refresh_token": refresh,
                "refresh_expires_at": iso(utc(s.expires_at)), "session": {"id": s.id, "expires_at": iso(s.expires_at)}}

    # ---- sign-in -----------------------------------------------------------------------------------
    def login_password(self, request: Request, username: str, password: str, totp: str | None) -> UserRow:
        now, src = self.now(), source_of(request)
        self.limiter.check(src, now)
        u = self.repo.one(select(UserRow).where(UserRow.username == (username or "").strip().lower()))
        ok = verify_password(password or "", u.password_hash if u is not None else None)
        if not ok or u is None or u.disabled:
            self.limiter.fail(src, now)
            self.emit("auth", "login.failed", {"username": (username or "")[:64], "method": "password",
                                               "source": src, "reason": "bad_credentials"}, severity="warning")
            raise ApiError(401, "unauthenticated", "wrong username or password", reason="bad_credentials")
        if u.totp_secret:
            if not totp:
                raise ApiError(401, "unauthenticated", "this account needs its authenticator code",
                               reason="totp_required")
            step = totp_match(u.totp_secret, totp, now.timestamp(), u.totp_last_step)
            if step is None:
                self.limiter.fail(src, now)
                self.emit("auth", "login.failed", {"username": u.username, "method": "password+totp",
                                                   "source": src, "reason": "totp_invalid"}, severity="warning")
                raise ApiError(401, "unauthenticated", "wrong or reused authenticator code", reason="totp_invalid")
            self.repo.update(UserRow, [UserRow.id == u.id], {"totp_last_step": step})
        return u

    def _new_challenge(self, purpose: str, user_id: str | None = None, action_id: str | None = None,
                       data: dict | None = None, raw: bytes | None = None) -> tuple[ChallengeRow, bytes]:
        now = self.now()
        raw = raw or os.urandom(32)
        row = ChallengeRow(id=new_id("chl"), purpose=purpose, challenge=b64url(raw), user_id=user_id,
                           action_id=action_id, data=data or {}, expires_at=now + CHALLENGE_TTL)
        self.repo.add(row)
        # Expired challenges are garbage: drop them whenever a new one is made.
        self.repo.delete(ChallengeRow, ChallengeRow.expires_at < now - CHALLENGE_TTL)
        return row, raw

    def _consume_challenge(self, credential: dict, purpose: str) -> ChallengeRow:
        """Single use: the first verifier claims it, verified or not."""
        value = pk.client_challenge(credential)
        row = self.repo.one(select(ChallengeRow).where(ChallengeRow.challenge == value))
        now = self.now()
        if row is None or row.purpose != purpose:
            raise ApiError(401, "unauthenticated", "unknown challenge", reason="assertion_invalid")
        claimed = self.repo.update(ChallengeRow, [ChallengeRow.id == row.id, ChallengeRow.used_at.is_(None),
                                                  ChallengeRow.expires_at > now], {"used_at": now})
        if not claimed:
            raise ApiError(401, "unauthenticated", "challenge expired or already used", reason="assertion_invalid")
        return row

    def login_options(self, request: Request) -> dict:
        rp_id, _ = self.rp(request)
        row, raw = self._new_challenge("login")
        return {"challenge_id": row.id, "expires_at": iso(row.expires_at),
                "publicKey": pk.authentication_options(rp_id=rp_id, challenge=raw, allow=[])}

    def _assert(self, request: Request, credential: dict, row: ChallengeRow) -> PasskeyRow:
        """Verify an assertion against a claimed challenge; bumps the sign count. Raises 401."""
        rp_id, origins = self.rp(request)
        cred = self.repo.get(PasskeyRow, credential["id"])
        if cred is None:
            raise ApiError(401, "unauthenticated", "unknown passkey", reason="assertion_invalid")
        try:
            count = pk.verify_assertion(credential=credential, challenge=pk.unb64url(row.challenge), rp_id=rp_id,
                                        origins=origins, public_key=cred.public_key, sign_count=cred.sign_count)
        except pk.PasskeyError as exc:
            raise ApiError(401, "unauthenticated", str(exc)[:300], reason="assertion_invalid") from None
        self.repo.update(PasskeyRow, [PasskeyRow.id == cred.id], {"sign_count": count, "last_used_at": self.now()})
        return cred

    def login_passkey(self, request: Request, credential: dict) -> UserRow:
        now, src = self.now(), source_of(request)
        self.limiter.check(src, now)
        try:
            credential = pk.normalize(credential)
            row = self._consume_challenge(credential, "login")
            cred = self._assert(request, credential, row)
            u = self._live_user(cred.user_id)
            if u is None:
                raise ApiError(401, "unauthenticated", "account disabled", reason="bad_credentials")
        except (ApiError, pk.PasskeyError) as exc:
            self.limiter.fail(src, now)
            self.emit("auth", "login.failed", {"method": "passkey", "source": src,
                                               "reason": getattr(exc, "reason", None) or "assertion_invalid"},
                      severity="warning")
            if isinstance(exc, ApiError):
                raise
            raise ApiError(401, "unauthenticated", str(exc)[:300], reason="assertion_invalid") from None
        return u

    # ---- first owner (bootstrap) and enrolment -----------------------------------------------------
    def _setup_token_ok(self, token: str) -> bool:
        p = self.gw.tokens.lookup(token) if token else None
        if p is not None and p.is_owner:
            return True
        path = self.cfg.setup_token_file
        if token and path is not None:
            try:
                expected = path.read_text().strip()
            except OSError:
                return False
            return bool(expected) and hmac.compare_digest(sha256_hex(expected), sha256_hex(token))
        return False

    def _new_username(self, username: str) -> str:
        name = (username or "").strip().lower()
        if not USERNAME_RE.fullmatch(name):
            raise ApiError(422, "conflict", "username must be 2-32 characters: a-z, 0-9, '.', '_', '-', starting with a letter")
        if self.repo.one(select(UserRow.id).where(UserRow.username == name)) is not None:
            raise ApiError(409, "conflict", "that username is taken", reason="username_taken")
        return name

    def setup(self, request: Request, token: str, username: str, display_name: str, password: str) -> UserRow:
        now, src = self.now(), source_of(request)
        self.limiter.check(src, now)
        if not self._setup_token_ok(token):
            self.limiter.fail(src, now)
            self.emit("auth", "setup.rejected", {"source": src, "reason": "bad_setup_token"}, severity="warning")
            raise ApiError(401, "unauthenticated", "setup needs the install owner token or the first-boot token")
        if self.repo.count(UserRow) > 0:
            raise ApiError(409, "conflict", "this box already has accounts; sign in instead", reason="already_set_up")
        self._check_password(password)
        u = UserRow(id=new_id("usr"), username=self._new_username(username),
                    display_name=(display_name or username).strip()[:100], role="owner",
                    password_hash=hash_password(password), created_at=now, updated_at=now, created_by="setup")
        self.repo.add(u)
        self.emit("auth", "setup.completed", {"user_id": u.id, "username": u.username, "source": src},
                  self.principal_for(u))
        return u

    def enrol(self, request: Request, code: str, username: str, password: str) -> UserRow:
        now, src = self.now(), source_of(request)
        self.limiter.check(src, now)
        u = self.repo.one(select(UserRow).where(UserRow.enrol_hash == sha256_hex(code or "")))
        if u is None or u.disabled or u.enrol_expires_at is None or utc(u.enrol_expires_at) <= now:
            self.limiter.fail(src, now)
            self.emit("auth", "enrol.failed", {"source": src, "reason": "code_unknown"}, severity="warning")
            raise ApiError(401, "unauthenticated", "unknown or expired enrolment code", reason="code_unknown")
        self._check_password(password)
        name = u.username or self._new_username(username)
        claimed = self.repo.update(UserRow, [UserRow.id == u.id, UserRow.enrol_hash == u.enrol_hash], {
            "username": name, "password_hash": hash_password(password), "enrol_hash": None,
            "enrol_expires_at": None, "updated_at": now})
        if not claimed:
            raise ApiError(401, "unauthenticated", "enrolment code already used", reason="code_used")
        self.emit("auth", "enrol.completed", {"user_id": u.id, "username": name}, self.principal_for(u))
        return self.user(u.id)

    # ---- step-up ---------------------------------------------------------------------------------
    def require_step_up(self, ctx: AuthContext | None, p: Principal, what: str) -> str:
        """Administration that adds power: once passkeys are active, a passkey sign-in in the last
        step_up_s seconds. Returns how the caller proved presence (audited by the caller)."""
        if not self.passkeys_active():
            return "token" if ctx is None or ctx.session is None else ctx.session.auth_method
        s = ctx.session if ctx else None
        if s is not None and s.passkey_at is not None and \
                (self.now() - utc(s.passkey_at)).total_seconds() <= self.cfg.step_up_s:
            return "passkey"
        self.emit("auth", "step_up.required", {"attempted": what}, p, severity="warning")
        raise ApiError(401, "unauthenticated", "sign in again with your passkey to do this", reason="step_up_required")

    # ---- passkeys --------------------------------------------------------------------------------
    def _person(self, ctx: AuthContext | None) -> UserRow:
        if ctx is None or ctx.user is None:
            raise ApiError(403, "permission_denied", "sign in with a household account (not a static token) to do this")
        return ctx.user

    def passkey_register_options(self, request: Request, ctx: AuthContext | None) -> dict:
        user = self._person(ctx)
        existing = list(self.repo.all(select(PasskeyRow.id).where(PasskeyRow.user_id == user.id)))
        if existing:  # adding a second key is adding power: prove you hold the first
            self.require_step_up(ctx, ctx.principal, "register a passkey")
        rp_id, _ = self.rp(request)
        row, raw = self._new_challenge("register", user_id=user.id)
        opts = pk.registration_options(rp_id=rp_id, rp_name=self.cfg.rp_name, user_id=user.id,
                                       user_name=user.username or user.id, display_name=user.display_name,
                                       challenge=raw, exclude=existing)
        return {"challenge_id": row.id, "expires_at": iso(row.expires_at), "publicKey": opts}

    def passkey_register(self, request: Request, ctx: AuthContext | None, credential: dict, label: str | None) -> dict:
        user = self._person(ctx)
        try:
            credential = pk.normalize(credential)
            row = self._consume_challenge(credential, "register")
        except pk.PasskeyError as exc:
            raise ApiError(422, "conflict", str(exc)[:300], reason="assertion_invalid") from None
        if row.user_id != user.id:
            raise ApiError(401, "unauthenticated", "challenge belongs to another account", reason="assertion_invalid")
        rp_id, origins = self.rp(request)
        try:
            v = pk.verify_registration(credential=credential, challenge=pk.unb64url(row.challenge), rp_id=rp_id,
                                       origins=origins)
        except pk.PasskeyError as exc:
            self.emit("auth", "passkey.rejected", {"user_id": user.id, "reason": "registration_invalid"},
                      ctx.principal, severity="warning")
            raise ApiError(422, "conflict", str(exc)[:300], reason="assertion_invalid") from None
        if self.repo.get(PasskeyRow, v["id"]) is not None:
            raise ApiError(409, "conflict", "this passkey is already registered")
        now = self.now()
        label = (label or "passkey").strip()[:100] or "passkey"
        self.repo.add(PasskeyRow(id=v["id"], user_id=user.id, label=label, public_key=v["public_key"],
                                 sign_count=v["sign_count"], transports=v["transports"], created_at=now))
        if ctx.session is not None:  # registering just proved presence on this device
            self.repo.update(SessionRow, [SessionRow.id == ctx.session.id], {"passkey_at": now})
        self.emit("auth", "passkey.registered", {"user_id": user.id, "credential_id": v["id"], "label": label},
                  ctx.principal)
        return {"credential_id": v["id"], "label": label, "created_at": iso(now)}

    def list_passkeys(self, ctx: AuthContext | None) -> list[dict]:
        user = self._person(ctx)
        rows = self.repo.all(select(PasskeyRow).where(PasskeyRow.user_id == user.id).order_by(PasskeyRow.created_at))
        return [{"credential_id": r.id, "label": r.label, "created_at": iso(r.created_at),
                 "last_used_at": iso(r.last_used_at)} for r in rows]

    def delete_passkey(self, ctx: AuthContext | None, credential_id: str) -> None:
        user = self._person(ctx)
        row = self.repo.get(PasskeyRow, credential_id)
        if row is None or row.user_id != user.id:
            raise ApiError(404, "not_found", "no such passkey")
        self.require_step_up(ctx, ctx.principal, "remove a passkey")
        if user.role == "owner":
            owners = self.active_owner_ids()
            if self.repo.count(PasskeyRow, PasskeyRow.user_id.in_(owners)) <= 1:
                raise ApiError(409, "conflict", "this is the last owner passkey on the box", reason="last_owner")
        self.repo.delete(PasskeyRow, PasskeyRow.id == row.id)
        self.emit("auth", "passkey.removed", {"user_id": user.id, "credential_id": row.id}, ctx.principal)

    # ---- password and TOTP -------------------------------------------------------------------------
    def change_password(self, request: Request, ctx: AuthContext | None, current: str, new: str) -> None:
        user = self._person(ctx)
        now, src = self.now(), source_of(request)
        self.limiter.check(src, now)
        if not verify_password(current or "", user.password_hash):
            self.limiter.fail(src, now)
            self.emit("auth", "password.change_failed", {"user_id": user.id}, ctx.principal, severity="warning")
            raise ApiError(401, "unauthenticated", "current password is wrong", reason="bad_credentials")
        self._check_password(new)
        self.repo.update(UserRow, [UserRow.id == user.id], {"password_hash": hash_password(new), "updated_at": now})
        keep = ctx.session.id if ctx.session else ""
        self.repo.update(SessionRow, [SessionRow.user_id == user.id, SessionRow.id != keep,
                                      SessionRow.revoked_at.is_(None)], {"revoked_at": now})
        self.emit("auth", "password.changed", {"user_id": user.id, "other_sessions_revoked": True}, ctx.principal)

    def totp_setup(self, ctx: AuthContext | None) -> dict:
        user = self._person(ctx)
        if user.totp_secret:
            raise ApiError(409, "conflict", "an authenticator is already set up; turn it off first")
        secret = new_totp_secret()
        self.repo.update(UserRow, [UserRow.id == user.id], {"totp_pending": secret})
        return {"one_time": {"secret": secret,
                             "otpauth_uri": otpauth_uri(secret, user.username or user.id, self.cfg.rp_name)}}

    def totp_confirm(self, ctx: AuthContext | None, code: str) -> None:
        user = self._person(ctx)
        fresh = self.user(user.id)
        if not fresh.totp_pending:
            raise ApiError(409, "conflict", "start authenticator setup first")
        step = totp_match(fresh.totp_pending, code, self.now().timestamp())
        if step is None:
            raise ApiError(422, "conflict", "that code does not match", reason="totp_invalid")
        self.repo.update(UserRow, [UserRow.id == user.id], {"totp_secret": fresh.totp_pending, "totp_pending": None,
                                                            "totp_last_step": step, "updated_at": self.now()})
        self.emit("auth", "totp.enabled", {"user_id": user.id}, ctx.principal)

    def totp_disable(self, request: Request, ctx: AuthContext | None, password: str) -> None:
        user = self._person(ctx)
        now, src = self.now(), source_of(request)
        self.limiter.check(src, now)
        if not verify_password(password or "", user.password_hash):
            self.limiter.fail(src, now)
            raise ApiError(401, "unauthenticated", "password is wrong", reason="bad_credentials")
        self.repo.update(UserRow, [UserRow.id == user.id], {"totp_secret": None, "totp_pending": None,
                                                            "totp_last_step": None, "updated_at": now})
        self.emit("auth", "totp.disabled", {"user_id": user.id}, ctx.principal, severity="warning")

    # ---- users -------------------------------------------------------------------------------------
    def user_json(self, u: UserRow) -> dict:
        return {"id": u.id, "username": u.username, "display_name": u.display_name, "role": u.role,
                "created_at": iso(u.created_at), "last_seen_at": iso(u.last_seen_at), "disabled": u.disabled,
                "enrolled": u.password_hash is not None,
                "passkeys": self.repo.count(PasskeyRow, PasskeyRow.user_id == u.id),
                "totp": u.totp_secret is not None}

    def _owner_only(self, p: Principal, what: str) -> None:
        if not p.is_owner:
            raise self.deny(p, what)

    def list_users(self, p: Principal) -> list[dict]:
        self._owner_only(p, "list users")
        return [self.user_json(u) for u in self.repo.all(select(UserRow).order_by(UserRow.created_at))]

    @staticmethod
    def _role(role: str) -> str:
        if role not in PERSON_ROLES:
            raise ApiError(422, "conflict", f"role must be one of {', '.join(PERSON_ROLES)}")
        return role

    def create_user(self, request: Request, ctx: AuthContext | None, p: Principal, display_name: str, role: str,
                    username: str | None) -> dict:
        self._owner_only(p, "create users")
        via = self.require_step_up(ctx, p, "create users")
        now = self.now()
        code = secrets.token_urlsafe(24)
        u = UserRow(id=new_id("usr"), username=self._new_username(username) if username else None,
                    display_name=(display_name or "").strip()[:100] or "member", role=self._role(role),
                    enrol_hash=sha256_hex(code), enrol_expires_at=now + ENROL_TTL,
                    created_at=now, updated_at=now, created_by=p.id)
        self.repo.add(u)
        self.emit("user", "created", {"user_id": u.id, "role": u.role, "step_up": via}, p)
        base = (self.gw.settings.public_url or str(request.base_url)).rstrip("/")
        return {**self.user_json(u), "one_time": {"enrolment_code": code, "enrolment_url": f"{base}/signin#enrol={code}",
                                                  "expires_at": iso(now + ENROL_TTL)}}

    def _last_owner_guard(self, u: UserRow, becomes_non_owner: bool) -> None:
        if u.role == "owner" and not u.disabled and becomes_non_owner and self.active_owner_ids() == [u.id]:
            raise ApiError(409, "conflict", "the last owner cannot be demoted or disabled", reason="last_owner")

    def update_user(self, ctx: AuthContext | None, p: Principal, user_id: str, display_name: str | None,
                    role: str | None) -> dict:
        self._owner_only(p, "change users")
        u = self.user(user_id)
        if u is None:
            raise ApiError(404, "not_found", "no such user")
        via = self.require_step_up(ctx, p, "change users")
        values: dict = {"updated_at": self.now()}
        if display_name is not None:
            values["display_name"] = display_name.strip()[:100] or u.display_name
        if role is not None and role != u.role:
            self._last_owner_guard(u, self._role(role) != "owner")
            values["role"] = role
        self.repo.update(UserRow, [UserRow.id == u.id], values)
        changed = sorted(k for k in values if k != "updated_at")
        self.emit("user", "updated", {"user_id": u.id, "changed": changed, "role": values.get("role", u.role),
                                      "step_up": via}, p)
        return self.user_json(self.user(u.id))

    def disable_user(self, p: Principal, user_id: str) -> dict:
        self._owner_only(p, "disable users")
        u = self.user(user_id)
        if u is None:
            raise ApiError(404, "not_found", "no such user")
        self._last_owner_guard(u, True)
        now = self.now()  # removing power is a direct write: no step-up (§12.1)
        self.repo.update(UserRow, [UserRow.id == u.id], {"disabled": True, "updated_at": now})
        sessions = self.repo.update(SessionRow, [SessionRow.user_id == u.id, SessionRow.revoked_at.is_(None)],
                                    {"revoked_at": now})
        tokens = self.repo.update(TokenRow, [or_(TokenRow.owner_user_id == u.id, TokenRow.principal_id == u.id),
                                             TokenRow.revoked_at.is_(None)], {"revoked_at": now})
        self.emit("user", "disabled", {"user_id": u.id, "sessions_revoked": len(sessions),
                                       "tokens_revoked": len(tokens)}, p, severity="warning")
        return self.user_json(self.user(u.id))

    # ---- API tokens (H-09) ---------------------------------------------------------------------------
    def token_json(self, t: TokenRow) -> dict:
        return {"id": t.id, "prefix": t.prefix, "name": t.name, "principal_id": t.principal_id, "kind": t.kind,
                "scopes": list(t.scopes), "created_at": iso(t.created_at), "expires_at": iso(t.expires_at),
                "last_used_at": iso(t.last_used_at), "revoked_at": iso(t.revoked_at), "source": t.source,
                "owner_user_id": t.owner_user_id}

    def _actor_scopes(self, ctx: AuthContext | None, p: Principal) -> frozenset[str]:
        if ctx is not None:
            return ctx.scopes
        return frozenset({sc.ALL}) if p.is_owner else sc.role_scopes(p.role)  # static file principal

    def list_tokens(self, ctx: AuthContext | None, p: Principal) -> list[dict]:
        rows = self.repo.all(select(TokenRow).where(TokenRow.revoked_at.is_(None)).order_by(TokenRow.created_at))
        if p.is_owner:
            out = [self.token_json(t) for t in rows]
            out += [{"id": f"file:{h[:12]}", "prefix": None, "name": fp.id, "principal_id": fp.id, "kind": fp.kind,
                     "scopes": ["v0"], "created_at": None, "expires_at": None, "last_used_at": None,
                     "revoked_at": None, "source": "file", "owner_user_id": None}
                    for h, fp in self.gw.tokens.entries()]
            return out
        uid = ctx.user.id if ctx and ctx.user else None
        return [self.token_json(t) for t in rows if uid and (t.owner_user_id == uid or t.principal_id == uid)]

    def create_token(self, ctx: AuthContext | None, p: Principal, name: str, principal: object,
                     scopes: list[str] | None, expires_in_days: int | None) -> dict:
        if p.kind != "person":
            raise self.deny(p, "mint tokens", reason="kind")
        actor_scopes = self._actor_scopes(ctx, p)
        if not sc.has_any(actor_scopes, ("tokens:self", "tokens:admin")):
            raise self.deny(p, "mint tokens", reason="scope")
        user = ctx.user if ctx else None
        if principal == "self":
            if user is None:
                raise ApiError(403, "permission_denied", "a static-file principal cannot hold API tokens; "
                                                         "set up a household account first")
            kind, principal_id, default_days, max_days = "person", user.id, PAT_DEFAULT_DAYS, PAT_MAX_DAYS
            default_scopes = sorted(actor_scopes)
        elif isinstance(principal, dict) and principal.get("kind") == "agent":
            principal_id = str(principal.get("id") or "")
            if not AGENT_ID_RE.fullmatch(principal_id):
                raise ApiError(422, "conflict", "agent id must look like agent:<name> (a-z, 0-9, '.', '_', '-')")
            kind, default_days, max_days = "agent", AGENT_DEFAULT_DAYS, AGENT_MAX_DAYS
            default_scopes = list(sc.BUNDLES["reader"])  # F-15
        else:
            raise ApiError(422, "conflict", 'principal must be "self" or {"kind": "agent", "id": "agent:<name>"}')
        try:
            wanted = sc.expand(scopes if scopes else default_scopes)
        except ValueError as exc:
            raise ApiError(422, "conflict", str(exc)) from None
        for s in wanted:
            if not sc.allowed_for_kind(s, kind):  # §12.6: never minted for non-person kinds
                raise self.deny(p, f"mint scope {s} for a {kind}", reason="never_minted")
            if not (sc.within(s, actor_scopes) or (s == sc.ALL and sc.ALL in actor_scopes)):
                raise self.deny(p, f"grant {s}, which you do not hold", reason="exceeds_grantor")
        days = default_days if expires_in_days is None else expires_in_days
        if not 1 <= days <= max_days:
            raise ApiError(422, "conflict", f"expires_in_days must be 1 to {max_days} for a {kind} token")
        now = self.now()
        secret = new_secret(TOKEN_KINDS[kind])
        t = TokenRow(id=new_id("tok"), prefix=secret[:11], name=(name or "token").strip()[:100] or "token",
                     hash=sha256_hex(secret), kind=kind, principal_id=principal_id,
                     owner_user_id=user.id if user else None, scopes=wanted, source="api", created_by=p.id,
                     created_at=now, expires_at=now + timedelta(days=days))
        self.repo.add(t)
        self.emit("auth", "token.created", {"token_id": t.id, "kind": kind, "principal_id": principal_id,
                                            "scopes": wanted, "expires_at": iso(t.expires_at)}, p)
        return {**self.token_json(t), "one_time": {"token": secret}}

    def _token_for_write(self, ctx: AuthContext | None, p: Principal, token_id: str, what: str) -> TokenRow:
        t = self.repo.get(TokenRow, token_id)
        if t is None or t.revoked_at is not None:
            raise ApiError(404, "not_found", "no such token")
        uid = ctx.user.id if ctx and ctx.user else None
        if not (p.is_owner or (uid and (t.owner_user_id == uid or t.principal_id == uid))):
            raise ApiError(404, "not_found", "no such token")
        return t

    def rotate_token(self, ctx: AuthContext | None, p: Principal, token_id: str, grace_s: int) -> dict:
        t = self._token_for_write(ctx, p, token_id, "rotate tokens")
        if not 0 <= grace_s <= MAX_GRACE_S:
            raise ApiError(422, "conflict", f"grace_s must be 0 to {MAX_GRACE_S}")
        now = self.now()
        secret = new_secret(TOKEN_KINDS[t.kind])
        done = self.repo.update(TokenRow, [TokenRow.id == t.id, TokenRow.hash == t.hash], {
            "hash": sha256_hex(secret), "prefix": secret[:11], "prev_hash": t.hash if grace_s else None,
            "prev_valid_until": now + timedelta(seconds=grace_s) if grace_s else None})
        if not done:
            raise ApiError(409, "conflict", "token was rotated concurrently")
        self.emit("auth", "token.rotated", {"token_id": t.id, "grace_s": grace_s}, p)
        return {**self.token_json(self.repo.get(TokenRow, t.id)), "one_time": {"token": secret}}

    def revoke_token(self, ctx: AuthContext | None, p: Principal, token_id: str) -> None:
        t = self._token_for_write(ctx, p, token_id, "revoke tokens")
        self.repo.update(TokenRow, [TokenRow.id == t.id], {"revoked_at": self.now(), "prev_hash": None})
        self.emit("auth", "token.revoked", {"token_id": t.id, "principal_id": t.principal_id}, p)

    # ---- per-app sharing ---------------------------------------------------------------------------
    DEFAULT_ROLES = ("owner", "adult")

    def _access(self, app_id: str) -> dict:
        row = self.repo.get(AppAccessRow, app_id)
        if row is None:
            return {"app_id": app_id, "roles": list(self.DEFAULT_ROLES), "people": [], "auth": "onemind"}
        return {"app_id": app_id, "roles": list(row.roles), "people": list(row.people), "auth": row.auth}

    def _people(self, ids: list[str]) -> list[dict]:
        out = []
        for uid in ids:
            u = self.user(uid)
            if u is not None:
                out.append({"id": u.id, "display_name": u.display_name})
        return out

    def get_access(self, p: Principal, app_id: str) -> dict:
        if app_id not in self.gw.catalog.load():
            raise ApiError(404, "not_found", f"no app {app_id!r}")
        a = self._access(app_id)
        if p.is_owner:
            return {**a, "people": self._people(a["people"])}
        mine = [uid for uid in a["people"] if uid == p.id]
        return {"app_id": app_id, "roles": [r for r in a["roles"] if r == p.role], "people": self._people(mine),
                "auth": a["auth"], "allowed": self.can_open(p, app_id)}

    def put_access(self, ctx: AuthContext | None, p: Principal, app_id: str, roles: list[str], people: list[str],
                   auth: str | None) -> dict:
        self._owner_only(p, "change app access")
        if app_id not in self.gw.catalog.load():
            raise ApiError(404, "not_found", f"no app {app_id!r}")
        roles = sorted({self._role(r) for r in roles} | {"owner"}, key=PERSON_ROLES.index)
        people = sorted(set(people))
        for uid in people:
            if self.user(uid) is None:
                raise ApiError(422, "conflict", f"no user {uid!r}")
        auth = auth or "onemind"
        if auth not in ("onemind", "app"):
            raise ApiError(422, "conflict", 'auth must be "onemind" or "app"')
        before = self._access(app_id)
        widens = bool(set(roles) - set(before["roles"]) or set(people) - set(before["people"]))
        via = self.require_step_up(ctx, p, "share an app") if widens else "not_needed"
        now = self.now()
        with self.repo.db.session.begin() as s:
            row = s.get(AppAccessRow, app_id)
            if row is None:
                s.add(AppAccessRow(app_id=app_id, roles=roles, people=people, auth=auth, updated_at=now, updated_by=p.id))
            else:
                row.roles, row.people, row.auth, row.updated_at, row.updated_by = roles, people, auth, now, p.id
        self.emit("app", "access.updated", {"app_id": app_id, "roles": roles, "people": people, "auth": auth,
                                            "step_up": via}, p)
        return {**self._access(app_id), "people": self._people(people)}

    def can_open(self, p: Principal, app_id: str) -> bool:
        """§12.6: owners and adults see every app; guests and children only apps shared with them.
        Agents and plugins are governed by their scopes, not by sharing."""
        if p.kind != "person" or p.role in ("owner", "adult"):
            return True
        a = self._access(app_id)
        return p.role in a["roles"] or p.id in a["people"]

    def app_filter(self, request: Request, p: Principal, app_id: str) -> bool:
        # Static-file principals keep v0 behaviour (everyone sees the catalog), F-14.
        return ctx_of(request) is None or self.can_open(p, app_id)

    # ---- approvals with step-up (F-2, §12.3, §12.4) -----------------------------------------------
    @staticmethod
    def action_sha256(action: dict) -> str:
        bound = {k: action.get(k) for k in ("id", "type", "params", "requested_by", "expires_at")}
        canon = json.dumps(bound, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return "sha256:" + hashlib.sha256(canon.encode()).hexdigest()

    def approve_options(self, request: Request, p: Principal, action_id: str) -> dict:
        if not p.is_owner:
            raise self.deny(p, "approve actions", action_id=action_id)
        action = self.gw.actions.get(action_id)  # 404 when unknown
        if action.get("state") != "awaiting_approval":
            raise ApiError(409, "conflict", f"action is {action.get('state')}, not awaiting_approval")
        ctx = ctx_of(request)
        a_sha = self.action_sha256(action)
        p_sha = action.get("plan_sha256") or ""
        nonce = os.urandom(32)
        raw = hashlib.sha256(action_id.encode() + a_sha.encode() + p_sha.encode() + nonce).digest()
        user_id = ctx.user.id if ctx and ctx.user else None
        allow_users = [user_id] if user_id else self.active_owner_ids()
        allow = list(self.repo.all(select(PasskeyRow.id).where(PasskeyRow.user_id.in_(allow_users))))
        row, _ = self._new_challenge("approve", user_id=user_id, action_id=action_id,
                                     data={"action_sha256": a_sha, "plan_sha256": p_sha or None}, raw=raw)
        rp_id, _ = self.rp(request)
        return {"challenge": row.challenge, "action_sha256": a_sha, "plan_sha256": p_sha or None,
                "expires_at": iso(row.expires_at),
                "publicKey": pk.authentication_options(rp_id=rp_id, challenge=raw, allow=allow)}

    def approval_guard(self, p: Principal, action_id: str, body: dict, request: Request) -> None:
        if not p.is_owner:
            return  # actions.approve refuses and audits non-owners itself
        ctx = ctx_of(request)
        assertion = body.get("webauthn")
        if assertion is None:
            if self.cfg.require_passkey_approval and self.passkeys_active():
                self.emit("auth", "step_up.required", {"attempted": "approve", "action_id": action_id}, p,
                          severity="warning")
                raise ApiError(401, "unauthenticated", "approvals need a passkey on this box", reason="step_up_required")
            if ctx is not None:  # F-12: shown as "approved without passkey"
                self.emit("auth", "approval.token", {"action_id": action_id, "via": ctx.session.auth_method
                                                     if ctx.session else "token"}, p)
            return
        try:
            credential = pk.normalize(assertion)
            row = self._consume_challenge(credential, "approve")
        except pk.PasskeyError as exc:
            raise self._step_up_failed(p, action_id, str(exc)) from None
        except ApiError as exc:
            raise self._step_up_failed(p, action_id, exc.message) from None
        if row.action_id != action_id:
            raise self._step_up_failed(p, action_id, "challenge was issued for another action")
        if row.data.get("action_sha256") != self.action_sha256(self.gw.actions.get(action_id)):
            raise self._step_up_failed(p, action_id, "the action changed since the challenge", reason="plan_changed")
        try:
            cred = self._assert(request, credential, row)
        except ApiError as exc:
            raise self._step_up_failed(p, action_id, exc.message) from None
        owner = self._live_user(cred.user_id)
        if owner is None or owner.role != "owner":
            raise self._step_up_failed(p, action_id, "passkey does not belong to an active owner")
        if ctx is not None and ctx.user is not None and ctx.user.id != owner.id:
            raise self._step_up_failed(p, action_id, "passkey belongs to another account")
        if ctx is not None and ctx.session is not None:
            self.repo.update(SessionRow, [SessionRow.id == ctx.session.id], {"passkey_at": self.now()})
        self.emit("auth", "step_up.succeeded", {"action_id": action_id, "credential_id": cred.id,
                                                "passkey_user_id": owner.id, "approval": "passkey"}, p)

    def _step_up_failed(self, p: Principal, action_id: str, why: str, reason: str = "assertion_invalid") -> ApiError:
        self.emit("auth", "step_up.failed", {"action_id": action_id, "reason": reason, "detail": why[:200]}, p,
                  severity="warning")
        if reason == "plan_changed":
            return ApiError(409, "stale_precondition", why, reason=reason)
        return ApiError(401, "unauthenticated", f"passkey check failed: {why}"[:300], reason="step_up_required")

    # ---- /v1/me ------------------------------------------------------------------------------------
    def me(self, request: Request, p: Principal) -> dict:
        ctx = ctx_of(request)
        principal = p.as_dict()
        token = session = None
        n_passkeys = 0
        if ctx is None:  # static-file token, or an app agent token of §11.2
            header = request.headers.get("authorization", "")
            raw = header.partition(" ")[2].strip()
            token = {"id": f"file:{sha256_hex(raw)[:12]}", "scopes": ["v0"], "expires_at": None, "source": "file"}
            scopes = [sc.ALL]
        else:
            scopes = sorted(ctx.scopes)
            if ctx.user is not None:
                principal["display_name"] = ctx.user.display_name
                principal["username"] = ctx.user.username
                n_passkeys = self.repo.count(PasskeyRow, PasskeyRow.user_id == ctx.user.id)
            if ctx.token is not None:
                token = {"id": ctx.token.id, "scopes": list(ctx.token.scopes), "expires_at": iso(ctx.token.expires_at),
                         "source": ctx.token.source}
            if ctx.session is not None:
                session = {"id": ctx.session.id, "expires_at": iso(ctx.session.expires_at),
                           "auth_method": ctx.session.auth_method,
                           "passkey_at": iso(ctx.session.passkey_at)}
        caps = []
        if p.is_owner and sc.has_any(scopes, ("actions:approve",)):
            caps.append("can_approve")
        if p.can_request_actions or (p.kind == "person" and sc.has_any(scopes, ("actions:request",))):
            caps.append("can_request")
        if p.is_owner:
            caps += ["can_manage_users", "can_share_apps"]
        if p.kind == "person" and sc.has_any(scopes, ("tokens:self", "tokens:admin")):
            caps.append("can_create_tokens")
        return {"principal": principal, "token": token, "session": session, "passkeys": n_passkeys,
                "scopes": scopes, "capabilities": caps,
                "step_up": {"passkeys_active": self.passkeys_active(),
                            "require_passkey_approval": self.cfg.require_passkey_approval}}
