# SPDX-License-Identifier: Apache-2.0
"""Household identity (contract §12.6): accounts, sign-in, sessions, passkeys, API tokens, sharing.

Every decision is audited through gw.events (auth.*, authz.denied, user.*, app.access.*). Secrets
(passwords, tokens, session cookies, refresh tokens, enrolment codes) are stored only as hashes and
never appear in the audit; a response carries them once under `one_time`.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import secrets
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from fastapi import Request
from sqlalchemy import case, delete, or_, select, update
from sqlalchemy.orm import Session

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError
from ..netconf import NetSettings
from ..netpath import SCOPE_PATH_KEY, PathClassifier, parse_networks
from . import approver_keys as ak
from . import levels as lv
from . import passkeys as pk
from . import remote_recovery
from . import scopes as sc
from .crypto import (
    COMMON_PASSWORDS,
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
    OWNER_PASSKEY_SEEN,
    AppAccessRow,
    ApproverKeyRow,
    ChallengeRow,
    HouseholdFlagRow,
    IdentityRepository,
    PasskeyRow,
    SessionRow,
    TokenRow,
    UserRow,
    iso,
    utc,
)
from .onboarding import SETUP_PATHS, AccountSetup
from .presence import BoxPresence
from .settings import IdentitySettings
from .verification import Verification

log = logging.getLogger("onemind.identity")

PERSON_ROLES = ("owner", "adult", "guest", "child", "teen")
USERNAME_RE = re.compile(r"[a-z][a-z0-9._-]{1,31}")
AGENT_ID_RE = re.compile(r"agent:[a-z0-9][a-z0-9._-]{0,62}")
CSRF_HEADER = "onemind-csrf"
STEP_UP_HEADER = "onemind-step-up"
# A version 3 onion address: 56 base32 characters, then ".onion" (lower case, as Tor Browser sends it).
ONION_V3 = re.compile(r"[a-z2-7]{56}\.onion")
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
TOUCH_EVERY = timedelta(seconds=60)  # session and token display timestamps are throttled
CHALLENGE_TTL = timedelta(seconds=120)
ENROL_TTL = timedelta(hours=24)
PAT_DEFAULT_DAYS, PAT_MAX_DAYS = 90, 365
AGENT_DEFAULT_DAYS = AGENT_MAX_DAYS = 90  # F-15: personal agent tokens, renewable
MAX_GRACE_S = 3600
MAX_OPEN_RESCUE_CHALLENGES = 20  # an owner credential is needed, so far fewer than for login
MAX_OPEN_LOGIN_CHALLENGES = 1000  # unauthenticated: bound the rows an anonymous caller can create
MAX_CREDENTIAL_ID = 512  # PasskeyRow.id width; WebAuthn allows longer ids, which we refuse with a 422


@dataclass
class AuthContext:
    """How an identity principal authenticated; request.state.identity. Absent for static-file tokens."""

    principal: Principal
    scopes: frozenset[str]
    user: UserRow | None = None
    session: SessionRow | None = None
    token: TokenRow | None = None
    step_up_grant: str | None = None  # the OneMind-Step-Up header: a body-bound L2+ step-up (design 3.11)
    home: bool = False
    redeemed_step_up: ChallengeRow | None = None  # the grant require_step_up just used (proven-key vouch)


PROFILE_NAME_MAX = 60


def clean_profile_name(raw: str) -> str:
    """1 to 60 characters after trimming; no control or format characters, no markup brackets."""
    import unicodedata

    name = raw.strip()
    if not 1 <= len(name) <= PROFILE_NAME_MAX:
        raise ApiError(422, "conflict", f"display name must be 1 to {PROFILE_NAME_MAX} characters",
                       reason="display_name_length")
    if any(unicodedata.category(ch)[0] == "C" or ch in "<>" for ch in name):
        raise ApiError(422, "conflict", "display name cannot contain control characters or markup",
                       reason="display_name_characters")
    return name


def ctx_of(request: Request) -> AuthContext | None:
    return getattr(request.state, "identity", None)


def source_of(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def clean_email(raw: str | None) -> str | None:
    email = (raw or "").strip()
    if email and not re.fullmatch(r"[^@\s<>\x00-\x1f\x7f]+@[^@\s<>\x00-\x1f\x7f]+", email):
        raise ApiError(422, "conflict", "enter an email address", reason="email_invalid")
    return email or None


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
        # SECURITY.md §3.2: the first-boot owner token stops working on the API once an owner exists.
        gw.tokens.retire_when = lambda: self.repo.count(UserRow) > 0
        # Features that give a new or re-roled person starting data (FAM-01 age presets): (user_id, role, actor).
        self.role_hooks: list[Callable[[str, str, Principal], None]] = []
        self.limiter = FailureLimiter(self.cfg.login_failures_per_min, timedelta(minutes=self.cfg.lockout_minutes))
        secure = self.cfg.cookie_secure
        # __Host- cookies must be Secure, path=/ and host-only: they cannot be set by a sibling name.
        self.cookie = "__Host-onemind_session" if secure else "onemind_session"
        self.csrf_cookie = "__Host-onemind_csrf" if secure else "onemind_csrf"
        self.levels = Verification(self)
        self.presence = BoxPresence(self.cfg.box_code_file, self.now,
                                    lambda name, payload, sev: self.emit("auth", name, payload, severity=sev))
        self.onboarding = AccountSetup(self)
        self.classify_path = PathClassifier(parse_networks(gw.settings.section(NetSettings).trusted_proxies))

    # ---- helpers ---------------------------------------------------------------------------------
    def now(self) -> datetime:
        return self.gw.clock()

    def emit(self, domain: str, name: str, payload: dict, p: Principal | None = None, severity: str = "info") -> None:
        self.gw.events.publish_event(domain, name, payload, principal=p.as_dict() if p else None, severity=severity)

    def deny(self, p: Principal | None, what: str, *, tell: bool = False, **extra) -> ApiError:
        """Audit a refusal and build its 403. `reason` always goes to the audit event; with tell=True it is also
        sent to the caller, for refusals the person can fix themselves (session_required: sign in, not a token)."""
        self.emit("authz", "denied", {"attempted": what, **extra}, p, severity="warning")
        return ApiError(403, "permission_denied", f"not allowed to {what}", reason=extra.get("reason") if tell else None)

    @staticmethod
    def principal_for(user: UserRow) -> Principal:
        return Principal(id=user.id, kind="person", role=user.role)

    def user(self, user_id: str) -> UserRow | None:
        return self.repo.get(UserRow, user_id)

    def active_owner_ids(self) -> list[str]:
        return list(self.repo.all(select(UserRow.id).where(UserRow.role == "owner", UserRow.disabled.is_(False))))

    def people(self) -> dict[str, str]:
        """Every active household account (user id -> role), for features that address people."""
        return {u.id: u.role for u in self.repo.all(select(UserRow).where(UserRow.disabled.is_(False)))}

    def passkeys_active(self, session: Session | None = None) -> bool:
        """Whether any active owner currently holds a passkey."""
        owner_key = select(PasskeyRow.id).join(UserRow, UserRow.id == PasskeyRow.user_id).where(
            UserRow.role == "owner", UserRow.disabled.is_(False)).limit(1)
        return (session.scalar(owner_key) if session is not None else self.repo.one(owner_key)) is not None

    def _owner_verification_active(self, session: Session | None = None) -> bool:
        """Owner verification stays on once the household has completed passkey setup."""
        active = self.passkeys_active() if session is None else self.passkeys_active(session)
        store = session if session is not None else self.repo
        return active or store.get(HouseholdFlagRow, OWNER_PASSKEY_SEEN) is not None or self.levels.latched(session)

    def rp(self, request: Request) -> tuple[str, list[str]]:
        host = request.headers.get("host") or (request.url.hostname or "localhost")
        rp_id = self.cfg.rp_id or host.rsplit(":", 1)[0].strip("[]")
        if self.cfg.origins:
            return rp_id, list(self.cfg.origins)
        origins = {f"https://{rp_id}", f"https://{host}"}
        if rp_id in ("localhost", "127.0.0.1"):
            origins |= {f"http://{rp_id}", f"http://{host}"}
        elif ONION_V3.fullmatch(rp_id):
            # Tor onion service (NET-TOR-01, #284): the .onion link is already end-to-end encrypted
            # and authenticated by the address itself, and Tor Browser treats it as a secure
            # context, so it is served over http://. The relying party stays the exact address;
            # a lookalike or another onion gets a different rp_id and never matches.
            origins |= {f"http://{rp_id}", f"http://{host}"}
        return rp_id, sorted(origins)

    @staticmethod
    def _check_password(password: str) -> None:
        if not isinstance(password, str) or not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
            raise ApiError(422, "conflict", f"password must be {PASSWORD_MIN} to {PASSWORD_MAX} characters",
                           reason="weak_password")
        if password.strip().casefold() in COMMON_PASSWORDS:
            raise ApiError(422, "conflict", "choose a password that is less common", reason="weak_password")

    def is_home(self, request: Request) -> bool:
        peer = source_of(request)
        fixed = request.scope.get(SCOPE_PATH_KEY)
        if fixed is not None:
            return fixed == "lan"
        if ONION_V3.fullmatch(request.url.hostname or ""):
            return False
        return self.classify_path(peer, request.headers) == "lan"

    def _require_session_path(self, request: Request, session: SessionRow) -> None:
        if session.auth_method not in ("passkey", "password+totp") and not self.is_home(request):
            raise ApiError(401, "unauthenticated", "outside your home network, sign in with an authenticator or a passkey",
                           reason="remote_factor_required")

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
        ctx.home = self.is_home(request)
        if ctx.session is not None:
            self._require_session_path(request, ctx.session)
        if ctx.user and ctx.user.setup_pending and (request.method, request.url.path) not in SETUP_PATHS:
            self.emit("authz", "denied", {"attempted": request.url.path, "reason": "recovery_kit_required"},
                      ctx.principal, severity="warning")
            raise ApiError(403, "permission_denied", "download or print your recovery kit to finish setup",
                           reason="recovery_kit_required")
        if ctx.principal.kind == "plugin":
            # Installation-owned plugins never inherit static-v0 access, self-service
            # exceptions or the generic scope table's broad route trees.
            from ..plugins.auth import allows_read, allows_request, plugin_app_id, request_types
            from ..plugins.auth import allows_own_action_read
            from ..plugins.principal import PluginPrincipal

            app_id = plugin_app_id(ctx.principal.id)
            state = self.gw.repo.get_app_state(app_id) if app_id else None
            row = ctx.token
            policy = dict(method=request.method, path=request.url.path, principal_id=ctx.principal.id,
                          source=row.source if row else "", scopes=row.scopes if row else None,
                          app_status=state.status if state else None,
                          operation_id=getattr(request.scope.get("route"), "operation_id", None))
            if allows_request(**policy):
                # Preserve the owning person's effective cap without ever adding the
                # broad actions:request scope. The service checks the body type before
                # either filing or returning an idempotent replay.
                exact = request_types(list(ctx.scopes))
                if not exact:
                    raise self.deny(ctx.principal, "request actions", reason="plugin_policy")
                ctx.principal = PluginPrincipal(ctx.principal.id, "plugin", "plugin", exact)
                request.state.identity = ctx
                return ctx.principal
            if allows_own_action_read(**policy):
                if "actions:read:own" not in ctx.scopes:
                    raise self.deny(ctx.principal, "read own actions", reason="plugin_policy")
                request.state.identity = ctx
                return ctx.principal
            from ..plugins.auth import EVENTS_WRITE_OWN, allows_bridge_intake

            if allows_bridge_intake(**policy):
                if EVENTS_WRITE_OWN not in ctx.scopes:
                    raise self.deny(ctx.principal, "post bridge events", reason="plugin_policy")
                request.state.identity = ctx
                return ctx.principal
            if not allows_read(**policy):
                raise self.deny(ctx.principal, f"{request.method} {request.url.path}", reason="plugin_policy")
        required = sc.required_scopes(request.method, request.url.path)
        if (required is not None and not sc.has_any(ctx.scopes, required)
                and not sc.narrowed_mcp_access(request.method, request.url.path, ctx.scopes)):
            raise self.deny(ctx.principal, f"{request.method} {request.url.path}",
                            required=list(required), reason="scope")
        ctx.step_up_grant = (request.headers.get(STEP_UP_HEADER) or "")[:128] or None
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
            if user.role != "owner":
                self.repo.update(UserRow, [UserRow.id == user.id], {"last_seen_at": now})
        self._touch_owner(user, now)

    def _touch_owner(self, user: UserRow, now: datetime) -> None:
        # Legacy recovery consumes this watermark. A request within the display throttle can
        # still be the first activity after a claim opens. Keep concurrent writes monotonic.
        if user.role == "owner":
            self.repo.update(UserRow, [UserRow.id == user.id,
                                       UserRow.last_seen_at.is_(None) | (UserRow.last_seen_at < now)],
                             {"last_seen_at": now})

    def _cookie_session(self, request: Request, raw: str, now: datetime) -> AuthContext | None:
        s = self.repo.one(select(SessionRow).where(SessionRow.secret_hash == sha256_hex(raw)))
        if s is None or s.transport != "cookie" or not self._session_live(s, now):
            return None
        user = self._live_user(s.user_id)
        if user is None or s.credential_revision != user.credential_revision:
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
        if user is None or s.credential_revision != user.credential_revision:
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
            self._touch_owner(owner, now)
            principal = self.principal_for(owner)
        else:
            principal = Principal(id=t.principal_id, kind=t.kind, role=t.kind)
        if t.kind == "plugin":
            # The plugin policy checks the original snapshot and rejects malformed
            # JSON. Do not let generic scope parsing fail before that denial.
            raw = t.scopes if isinstance(t.scopes, list) else []
            granted = frozenset(s for s in raw if isinstance(s, str))
        else:
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
                      bearer: bool, passkey: bool, install_id: str | None = None) -> dict:
        """Create a session; returns the body, with secrets, and `_cookies` for the router to set."""
        now = self.now()
        sid = new_id("ses")
        out: dict = {}
        cred_id = getattr(request.state, "onemind_passkey_id", None) if passkey else None
        common = dict(id=sid, user_id=user.id, client=self._client_label(request, client), auth_method=method,
                      passkey_at=now if passkey else None, totp_at=now if method == "password+totp" else None,
                      credential_revision=user.credential_revision, step_up_credential_id=cred_id, created_at=now,
                      last_seen_at=now, install_id=install_id)
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
        with self.repo.db.session.begin() as db:
            current = db.execute(update(UserRow).where(
                UserRow.id == user.id, UserRow.credential_revision == user.credential_revision,
                UserRow.disabled.is_(False),
            ).values(last_seen_at=case(  # monotonic: legacy recovery reads an owner's watermark
                (UserRow.last_seen_at.is_(None) | (UserRow.last_seen_at < now), now),
                else_=UserRow.last_seen_at,
            )).returning(UserRow.id)).scalar_one_or_none()
            if current is None:
                raise ApiError(401, "unauthenticated", "credentials changed; sign in again",
                               reason="credentials_changed")
            db.add(row)
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

    @staticmethod
    def _owner_wide(ctx: AuthContext | None, p: Principal) -> bool:
        """Owner-wide session control: a static owner token or a full owner session/token, never a
        narrowed owner PAT (scopes are the token's ceiling, also on self-service routes)."""
        return p.is_owner and (ctx is None or sc.ALL in ctx.scopes)

    def list_sessions(self, ctx: AuthContext | None, p: Principal) -> list[dict]:
        now = self.now()
        q = select(SessionRow).where(SessionRow.revoked_at.is_(None)).order_by(SessionRow.created_at)
        if not self._owner_wide(ctx, p):
            if ctx is None or ctx.user is None:
                return []
            q = q.where(SessionRow.user_id == ctx.user.id)
        current = ctx.session if ctx else None
        return [self.session_json(s, current) for s in self.repo.all(q) if self._session_live(s, now)]

    def revoke_session(self, ctx: AuthContext | None, p: Principal, session_id: str) -> None:
        s = self.repo.get(SessionRow, session_id)
        mine = s is not None and ctx is not None and ctx.user is not None and s.user_id == ctx.user.id
        if s is None or not (mine or self._owner_wide(ctx, p)):
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
        if (s is None or s.transport != "bearer" or not self._session_live(s, now) or user is None
                or s.credential_revision != user.credential_revision):
            self.limiter.fail(src, now)
            self.emit("auth", "refresh.failed", {"source": src}, severity="warning")
            raise ApiError(401, "unauthenticated", "unknown or expired refresh token")
        self._require_session_path(request, s)
        access, refresh = new_secret("ses"), new_secret("ref")
        access_exp = now + timedelta(minutes=self.cfg.access_token_minutes)
        done = self.repo.update(
            SessionRow, [SessionRow.id == s.id, SessionRow.refresh_hash == s.refresh_hash, SessionRow.revoked_at.is_(None)],
            {"secret_hash": sha256_hex(access), "refresh_hash": sha256_hex(refresh),
             "access_expires_at": access_exp, "last_seen_at": now},
        )
        if not done:  # a concurrent refresh won
            raise ApiError(401, "unauthenticated", "refresh token already used")
        self._touch_owner(user, now)
        self.emit("auth", "session.refreshed", {"session_id": s.id}, self.principal_for(user))
        return {"access_token": access, "expires_at": iso(access_exp), "refresh_token": refresh,
                "refresh_expires_at": iso(utc(s.expires_at)), "session": {"id": s.id, "expires_at": iso(s.expires_at)}}

    # ---- sign-in -----------------------------------------------------------------------------------
    def _check_login_password(self, request: Request, username: str, password: str, u: UserRow | None) -> UserRow:
        now, src, account = self.now(), source_of(request), f"account:{username}"
        for key in (src, account):
            self.limiter.check(key, now)
        ok = verify_password(password or "", u.password_hash if u is not None else None)
        if not ok or u is None or u.disabled:
            for key in (src, account):
                self.limiter.fail(key, now)
            self.emit("auth", "login.failed", {"username": (username or "")[:64], "method": "password",
                                               "source": src, "reason": "bad_credentials"}, severity="warning")
            raise ApiError(401, "unauthenticated", "wrong username or password", reason="bad_credentials")
        return u

    def _consume_totp(self, request: Request, user: UserRow, totp: str | None) -> None:
        if not totp or not user.totp_secret:
            raise ApiError(401, "unauthenticated", "sign in with an authenticator code",
                           reason="totp_required")
        now, src = self.now(), source_of(request)
        step = totp_match(user.totp_secret, totp, now.timestamp(), user.totp_last_step)
        if step is not None and self.repo.update(UserRow, [
            UserRow.id == user.id, UserRow.disabled.is_(False), UserRow.totp_secret == user.totp_secret,
            UserRow.credential_revision == user.credential_revision,
            or_(UserRow.totp_last_step.is_(None), UserRow.totp_last_step < step),
        ], {"totp_last_step": step}):
            return
        for key in (src, f"account:{user.username}"):
            self.limiter.fail(key, now)
        self.emit("auth", "login.failed", {"user_id": user.id, "method": "password+totp",
                                           "source": src, "reason": "totp_invalid"}, severity="warning")
        raise ApiError(401, "unauthenticated", "wrong or reused authenticator code", reason="totp_invalid")

    def verify_password_totp(self, request: Request, user: UserRow, password: str, totp: str | None) -> None:
        self._check_login_password(request, user.username or user.id, password, user)
        self._consume_totp(request, user, totp)

    def login_password(self, request: Request, username: str, password: str, totp: str | None) -> UserRow:
        name = (username or "").strip().lower()
        user = self._check_login_password(request, name, password,
                                          self.repo.one(select(UserRow).where(UserRow.username == name)))
        if user.totp_secret:
            self._consume_totp(request, user, totp)
        elif not self.is_home(request):
            self.emit("auth", "login.failed", {"user_id": user.id, "reason": "remote_factor_required"},
                      severity="warning")
            raise ApiError(401, "unauthenticated", "outside your home network, sign in with an authenticator or a passkey",
                           reason="remote_factor_required")
        return user

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
        return self._claim_challenge(pk.client_challenge(credential), purpose)

    def _claim_challenge(self, value: str, purpose: str) -> ChallengeRow:
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
        now = self.now()
        open_ = self.repo.count(ChallengeRow, ChallengeRow.purpose == "login", ChallengeRow.used_at.is_(None),
                                ChallengeRow.expires_at > now)
        if open_ >= MAX_OPEN_LOGIN_CHALLENGES:
            raise ApiError(429, "rate_limited", "too many sign-in attempts in progress; try again shortly",
                           reason="too_many_pending", retry_after_s=int(CHALLENGE_TTL.total_seconds()))
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
        now = self.now()
        if (user := self._live_user(cred.user_id)) is not None:
            self._touch_owner(user, now)
        self.repo.update(PasskeyRow, [PasskeyRow.id == cred.id], {"sign_count": count, "last_used_at": now})
        return cred

    def login_passkey(self, request: Request, credential: dict) -> UserRow:
        now, src = self.now(), source_of(request)
        self.limiter.check(src, now)
        try:
            credential = pk.normalize(credential)
            row = self._consume_challenge(credential, "login")
            # Capture the owner's revision while the credential is still registered.
            u = self.repo.one(select(UserRow).join(PasskeyRow, PasskeyRow.user_id == UserRow.id).where(
                PasskeyRow.id == credential["id"], UserRow.disabled.is_(False)))
            if u is None:
                raise ApiError(401, "unauthenticated", "unknown passkey or disabled account", reason="assertion_invalid")
            cred = self._assert(request, credential, row)
            request.state.onemind_passkey_id = cred.id  # start_session records which key signed in
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
        p = self.gw.tokens.lookup(token, include_retired=True) if token else None
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

    def enrol(self, request: Request, code: str, username: str, password: str) -> UserRow:
        if not self.is_home(request):
            raise ApiError(403, "permission_denied", "accept the invitation on the box's home network",
                           reason="home_network_required")
        now, src = self.now(), source_of(request)
        self.limiter.check(src, now)
        u = self.repo.one(select(UserRow).where(UserRow.enrol_hash == sha256_hex(code or "")))
        if u is None or u.disabled or u.enrol_expires_at is None or utc(u.enrol_expires_at) <= now:
            self.limiter.fail(src, now)
            self.emit("auth", "enrol.failed", {"source": src, "reason": "code_unknown"}, severity="warning")
            raise ApiError(401, "unauthenticated", "unknown or expired enrolment code", reason="code_unknown")
        self._check_password(password)
        name = u.username or self._new_username(username)
        digest = hash_password(password)
        claimed = self.repo.update(UserRow, [UserRow.id == u.id, UserRow.enrol_hash == u.enrol_hash,
                                            UserRow.credential_revision == u.credential_revision,
                                            UserRow.disabled.is_(False)], {
            "username": name, "password_hash": digest, "enrol_hash": None,
            "enrol_expires_at": None, "updated_at": now})
        if not claimed:
            raise ApiError(401, "unauthenticated", "enrolment code already used", reason="code_used")
        self.emit("auth", "enrol.completed", {"user_id": u.id, "username": name}, self.principal_for(u))
        u.username, u.password_hash = name, digest
        return u

    # ---- step-up ---------------------------------------------------------------------------------
    def require_step_up(self, ctx: AuthContext | None, p: Principal, what: str, op: str | None = None,
                        target: str = "", body: dict | None = None) -> str:
        """Require fresh L1 or an operation-bound grant at the level this change needs (D-034).

        op names the owner route (levels.STEP_UP_ROWS, levels.FRESH_OPS or a guarded removal). When its
        rule asks for L2 or more, or for a confirmation at the box (_op_rule), the 5-minute window is not
        enough: the request must carry a step-up made for this exact change (op, target and body) at that
        level (design 3.11, gap 20). Below L2 a step-up grant also stands in for signing in again. Either way
        the 401 names the step-up in `details`, so a client can make it in place and repeat the request with
        the OneMind-Step-Up header (SDK `completeStepUp`). Returns how the caller proved presence."""
        if not self.account_setup_exists():
            return "token"  # installation and test fixtures before the household claims the box
        need, box, inplace = 1, "", op is not None and (p.is_owner or op in lv.FRESH_OPS)
        if inplace:
            need, box = self._op_rule(op, target, body, home=bool(ctx and ctx.home))
            if need >= 2 or box or (ctx is not None and ctx.step_up_grant):
                return self._use_step_up_grant(ctx, p, what, op, target, body or {}, need, box)
        if fresh := self._fresh_l1(ctx):
            return fresh
        self.emit("auth", "step_up.required", {"attempted": what}, p, severity="warning")
        details = self._step_up_details(op, target, body or {}, need, box) if inplace else None
        raise ApiError(401, "unauthenticated", "confirm with your password and authenticator code, or with your "
                       "passkey", reason="step_up_required", details=details)

    def require_fresh_passkey(self, ctx: AuthContext | None, p: Principal, what: str) -> str:
        """Require recent passkey verification even during password-only setup."""
        s = ctx.session if ctx else None
        if s is not None and s.passkey_at is not None and \
                (self.now() - utc(s.passkey_at)).total_seconds() <= self.cfg.step_up_s:
            return "passkey"
        self.emit("auth", "step_up.required", {"attempted": what}, p, severity="warning")
        raise ApiError(401, "unauthenticated", "sign in again with your passkey to do this", reason="step_up_required")

    def _fresh_l1(self, ctx: AuthContext | None) -> str | None:
        s = ctx.session if ctx else None
        if s is None:
            return None
        now = self.now()
        cutoff = now - timedelta(seconds=self.cfg.step_up_s)
        if s.passkey_at is not None and cutoff <= utc(s.passkey_at) <= now:
            cred = self.repo.get(PasskeyRow, s.step_up_credential_id) if s.step_up_credential_id else None
            if cred is not None and cred.user_id == s.user_id:
                return "passkey"
        if s.totp_at is not None and cutoff <= utc(s.totp_at) <= now and ctx.user.totp_secret:
            return "password+totp"
        return None

    def account_setup_exists(self) -> bool:
        return bool(self.repo.count(UserRow))

    # The confirmation an owner change needs (design 3.11, N-1 = b):
    #   box ""         a key at `need`;
    #   box "required" an L1 key plus the code on the box's own screen (the grace, or the interim recovery);
    #   box "alt"      a key at `need`, or an L1 key plus the box code when that key is lost.
    #   Away from the box (not home) there is no box code: "alt" and "required" are never offered (D-034).
    def _op_rule(self, op: str, target: str = "", body: dict | None = None, *,
                 home: bool = False) -> tuple[int, str]:
        if op == "auth.passkeys.delete":
            # Revoking the household's last proven key would leave L2 actions without a key: it takes that
            # key, or an owner at the box (a lost or stolen key must always be stoppable, design 3.11).
            return (2, "alt" if home else "") if self._last_proven(target) else (1, "")
        if op == "auth.trusted_models.remove":  # only asked for when it holds the last proven key
            return 2, "alt" if home else ""
        if op == "me.devices.remove":  # only asked for when the group contains the last proven key(s)
            return 2, "alt" if home else ""
        if op in lv.FRESH_OPS:
            return 1, ""
        row = lv.STEP_UP_ROWS[op]
        if op == "auth.passkeys.register":
            # Design 3.11: adding a second key needs L1 until a proven key exists, and the admin.high_risk row
            # afterwards (L2 unless the owner lowered it), or an owner at the box: with no proven key left that
            # is the only way (the interim recovery path), and an owner whose keys are all L1 can add one there
            # too. Whether the new key may be a *proven* one is a separate rule with its own floor
            # (lv.PROVEN_KEY_VOUCH, passkey_register_options): this row never lowers it.
            if not self.levels.note_proven("household_level"):
                return 1, ""
            need = self.levels.row_level(row)
            if home and need == 2 and self.levels.recovery_needed():
                return 1, "required"
            return need, "alt" if home and need >= 2 else ""
        if op == "users.create":
            # Direct and queued invitations follow the same policy, including owner overrides.
            need, strict, _ = self.levels.for_action({"type": "users.invite", "risk": lv.FAMILY_INVITE_RISK})
        else:
            need, strict = self.levels.for_row(row)
        if home and self.levels.grace(need, strict):
            return 1, "required"
        if (op == "users.update" and (body or {}).get("role") == "owner" and need < lv.PROVEN_KEY_VOUCH
                and self.repo.one(self._member_proven_key(target)) is not None):
            # Making this person an owner would turn their proven key (a member enrols one without the box)
            # into an owner's, which nobody vouched for: the same floor as adding an owner's proven key, so a
            # lowered admin.high_risk row can't hand an L1 key that power by a promotion. Before the first
            # proven key it is the box (it would end the grace); after it, a proven key or an owner at the box.
            # Away from the box only a proven key does (D-034: remote L2 needs a proven key).
            if self.levels.note_proven("household_level"):
                return lv.PROVEN_KEY_VOUCH, "alt" if home else ""
            return (1, "required") if home else (lv.PROVEN_KEY_VOUCH, "")
        return need, "alt" if home and need == 2 and not strict else ""

    @staticmethod
    def _member_proven_key(user_id: str):
        """Find a member's key that enrolled as proven, even if its model is currently untrusted."""
        return select(PasskeyRow.id).join(UserRow, UserRow.id == PasskeyRow.user_id).where(
            UserRow.id == user_id, UserRow.role != "owner",
            PasskeyRow.level.in_(lv.LEVELS[lv.PROVEN_KEY_VOUCH:])).limit(1)

    @staticmethod
    def _vouch(via: str) -> str:
        """How a step-up (require_step_up's answer, "<method>:<level>[+box]") vouches for an owner's new proven
        key or a promotion: "proven_key" when it was made with a passkey at lv.PROVEN_KEY_VOUCH or more, "box"
        when the box's code was typed with it at home (an L1 passkey, or a password and authenticator code:
        D-034's local L2), else "" (a fresh sign-in or a plain L1 grant: a phone can add a key, never vouch for
        a proven one)."""
        method, _, proof = via.partition(":")
        level, _, extra = proof.partition("+")
        if level not in lv.LEVELS:
            return ""
        if method == "passkey" and lv.rank(level) >= lv.PROVEN_KEY_VOUCH:
            return "proven_key"
        return "box" if extra == "box" and lv.rank(level) >= 1 else ""

    def _last_proven(self, credential_id: str) -> bool:
        return self.removes_last_proven({credential_id})

    def removes_last_proven(self, credential_ids: set[str]) -> bool:
        """Removing the selected credentials leaves no proven key held by an active owner."""
        owners = self.active_owner_ids()
        models = self.levels.models()
        proven = {r.id for r in self.repo.all(select(PasskeyRow).where(PasskeyRow.user_id.in_(owners)))
                  if self.levels.cred_level(r, models) >= 2}
        return bool(proven) and proven <= credential_ids

    @staticmethod
    def _canon(v):
        """The JSON value a step-up binds: what a client gets back from the error's details and sends to
        step-up/options after a JSON round trip. 2.0 and 2 are the same JSON number, so they hash alike."""
        if isinstance(v, dict):
            return {str(k): IdentityService._canon(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [IdentityService._canon(x) for x in v]
        if isinstance(v, float) and v.is_integer():
            return int(v)
        return v

    @staticmethod
    def step_up_sha256(op: str, target: str, body: dict) -> str:
        canon = json.dumps({"op": op, "target": target, "body": IdentityService._canon(body)}, sort_keys=True,
                           separators=(",", ":"), ensure_ascii=False)
        return "sha256:" + hashlib.sha256(canon.encode()).hexdigest()

    @staticmethod
    def _step_up_details(op: str, target: str, body: dict, need: int, box: str = "") -> list[dict]:
        return [{"step_up": {"op": op, "target": target, "body": IdentityService._canon(body),
                             "required_level": lv.name(max(need, 1)), "box": box or None}}]

    def step_up_options(self, request: Request, ctx: AuthContext | None, op: str, target: str, body: dict,
                        at_box: bool = False, method: str = "passkey") -> dict:
        """Begin a proof for the exact operation in this session."""
        user = self._account(ctx, "step up")  # a session, never an API token: a grant is bound to it
        ops = set(lv.STEP_UP_ROWS) | lv.FRESH_OPS | {"auth.trusted_models.remove"}
        if op not in ops:
            raise ApiError(422, "conflict", f"op must be one of {', '.join(sorted(ops))}", reason="invalid_op")
        need, box = self._op_rule(op, target, body, home=ctx.home)
        use_box = box == "required" or (box == "alt" and at_box)
        factor_need = 1 if use_box else max(need, 1)
        allow = self._keys_meeting(user.id, factor_need) if method == "passkey" else []
        if method == "password+totp":
            self._require_totp_available(user, ctx.principal, op, factor_need)
        elif not allow:
            raise self._level_unmet(ctx.principal, op, need)
        data = {"op": op, "sha256": self.step_up_sha256(op, target, body), "need": factor_need,
                "method": method, "session_id": ctx.session.id, "credential_revision": user.credential_revision}
        if use_box:
            data["box_sha256"] = self.presence.issue(f"confirm {op}", self.now() + CHALLENGE_TTL)
        row, raw = self._new_challenge("stepup", user_id=user.id, data=data)
        public_key = self._assertion_options(request, raw, allow) if method == "passkey" else {}
        return {"challenge_id": row.id, "challenge": row.challenge, "expires_at": iso(row.expires_at),
                "required_level": lv.name(factor_need),
                "grace": use_box and not self.levels.latched(), "box_code_required": use_box,
                "publicKey": public_key}

    def _assertion_options(self, request: Request, raw: bytes, allow: list[str]) -> dict:
        rp_id, _ = self.rp(request)
        return pk.authentication_options(rp_id=rp_id, challenge=raw, allow=allow)

    def _require_totp_available(self, user: UserRow, p: Principal, what: str, need: int) -> None:
        if need >= 2:
            raise self._level_unmet(p, what, need)
        if not (user.password_hash and user.totp_secret):
            raise ApiError(409, "conflict", "add an authenticator app or a passkey to confirm this",
                           reason="authenticator_required")

    def step_up_verify(self, request: Request, ctx: AuthContext | None, credential: dict | None,
                       box_code: str | None = None, password_totp: dict | None = None) -> dict:
        """Check one proof and issue a single-use grant bound to the original operation and session."""
        user = self._account(ctx, "step up")
        session = ctx.session
        if (credential is None) == (password_totp is None):
            raise ApiError(422, "conflict", "send one passkey or password and authenticator proof")
        if password_totp is not None:
            row = self._claim_challenge(password_totp["challenge"], "stepup")
            method = "password+totp"
        else:
            try:
                credential = pk.normalize(credential)
                row = self._consume_challenge(credential, "stepup")
            except pk.PasskeyError as exc:
                raise ApiError(401, "unauthenticated", str(exc)[:300], reason="assertion_invalid") from None
            method = "passkey"
        if (row.user_id != user.id or row.data.get("session_id") != session.id
                or row.data.get("credential_revision") != user.credential_revision
                or row.data.get("method") != method):
            raise ApiError(401, "unauthenticated", "challenge belongs to another session or sign-in method",
                           reason="assertion_invalid")
        need = int(row.data["need"])
        cred = None
        if password_totp is not None:
            self._require_totp_available(user, ctx.principal, row.data["op"], need)
            self.verify_password_totp(request, user, password_totp["password"], password_totp["totp"])
            level = 1
        else:
            cred = self._assert(request, credential, row)
            level = self.levels.cred_level(cred)
            if cred.user_id != user.id or level < need:
                self.emit("auth", "step_up.failed", {"attempted": row.data["op"], "reason": "level_unmet",
                                                     "credential_id": cred.id}, ctx.principal, severity="warning")
                raise ApiError(401, "unauthenticated", "this key doesn't meet the level this change needs",
                               reason="step_up_required")
        at_box = bool(row.data.get("box_sha256"))
        if at_box:
            self._check_local_box(request, row.data["box_sha256"], box_code, f"confirm {row.data['op']}")
        if cred is not None:
            self.repo.update(SessionRow, [SessionRow.id == session.id],
                             {"passkey_at": self.now(), "step_up_credential_id": cred.id})
        data = {k: v for k, v in row.data.items() if k != "box_sha256"}
        if cred is not None:
            data["credential_id"] = cred.id
        grant, _ = self._new_challenge("stepup-grant", user_id=user.id, data={
            **data, "level": lv.name(level), "box": at_box})
        return {"step_up": grant.challenge, "expires_at": iso(grant.expires_at),
                "level": lv.name(max(level, 2) if at_box else level)}

    def _check_local_box(self, request: Request, digest: str, code: str | None, what: str) -> None:
        if not self.is_home(request):
            raise ApiError(401, "unauthenticated", "use the home network to confirm with the box's screen",
                           reason="box_code_required")
        self.presence.check(digest, code, what)

    def _use_step_up_grant(self, ctx: AuthContext | None, p: Principal, what: str, op: str, target: str,
                           body: dict, need: int, box: str = "") -> str:
        grant = ctx.step_up_grant if ctx else None
        details = self._step_up_details(op, target, body, need, box)
        if not grant:
            self.emit("auth", "step_up.required", {"attempted": what, "required_level": lv.name(need)}, p,
                      severity="warning")
            ask = "fresh sign-in proof and the code on the box's own screen" if box == "required" else \
                f"verification level {lv.name(need)}" if need >= 2 else "your authenticator code or passkey"
            raise ApiError(401, "unauthenticated", f"this change needs {ask}: POST /v1/auth/step-up/options "
                           f"with op {op!r}, then send the grant as OneMind-Step-Up", reason="step_up_required",
                           details=details)
        try:
            row = self._claim_challenge(grant, "stepup-grant")
        except ApiError:
            raise ApiError(401, "unauthenticated", "step-up expired or already used", reason="step_up_required",
                           details=details) from None
        d = row.data
        have, at_box = lv.rank(d.get("level") or "L0"), bool(d.get("box"))
        if d.get("credential_id"):
            cred = self.repo.get(PasskeyRow, d["credential_id"])
            have = min(have, self.levels.cred_level(cred)) if cred is not None else 0
        elif not (ctx.user and ctx.user.totp_secret):
            have = 0
        at_box = at_box and ctx.home
        level_ok = (have >= 1 and at_box) if box == "required" else \
            (have >= need or (have >= 1 and at_box)) if box == "alt" else have >= need
        if (d.get("op") != op or d.get("sha256") != self.step_up_sha256(op, target, body)
                or ctx.session is None or d.get("session_id") != ctx.session.id or not level_ok
                or ctx.user is None or d.get("credential_revision") != ctx.user.credential_revision):
            self.emit("auth", "step_up.failed", {"attempted": what, "reason": "grant_mismatch"}, p, severity="warning")
            raise ApiError(401, "unauthenticated", "this step-up was made for a different change",
                           reason="step_up_required", details=details)
        ctx.redeemed_step_up = row
        return f"{d.get('method', 'passkey')}:{d.get('level')}{'+box' if at_box else ''}"

    def _keys_meeting(self, user_ids: str | list[str], need: int) -> list[str]:
        ids = [user_ids] if isinstance(user_ids, str) else user_ids
        rows = self.repo.all(select(PasskeyRow).where(PasskeyRow.user_id.in_(ids))) if ids else []
        models = self.levels.models()
        return [r.id for r in rows if self.levels.cred_level(r, models) >= need]

    def _level_unmet(self, p: Principal | None, what: str, need: int, *, details: list[dict] | None = None) -> ApiError:
        self.emit("auth", "step_up.required", {"attempted": what, "required_level": lv.name(need),
                                               "reason": "level_unmet"}, p, severity="warning")
        message = (f"this needs your proven key ({lv.name(need)}); add one under Settings > Security > Sign-in keys"
                   if need >= 2 else "this needs a passkey or a password with your authenticator code (L1)")
        return ApiError(409, "conflict", message, reason="verification_level_unmet", details=details)

    # ---- passkeys --------------------------------------------------------------------------------
    def _person(self, ctx: AuthContext | None) -> UserRow:
        if ctx is None or ctx.user is None:
            raise ApiError(403, "permission_denied", "sign in with a household account (not a static token) to do this")
        return ctx.user

    def _account(self, ctx: AuthContext | None, what: str) -> UserRow:
        """Changing a person's own sign-in credentials needs a signed-in session, never an API token:
        a narrowly scoped PAT must not be able to add a passkey or TOTP, or change the password."""
        user = self._person(ctx)
        if ctx.session is None:
            raise self.deny(ctx.principal, what, reason="session_required", tell=True)
        return user

    def _refuse_onion_enrolment(self, request: Request, ctx: AuthContext | None) -> None:
        """#284: an onion-bound passkey cannot assert on the LAN origin, yet its existence turns
        passkeys_active() on for the whole box and would lock LAN approvals. Until the owner-approved
        enrolment design lands, passkeys are not registered over an onion address. An authenticator
        code with the password can sign in there."""
        rp_id, _ = self.rp(request)
        if ONION_V3.fullmatch(rp_id):
            self.emit("authz", "denied", {"attempted": "register a passkey", "reason": "onion_origin"},
                      ctx.principal if ctx else None, severity="warning")
            raise ApiError(403, "permission_denied",
                           "passkeys cannot be added over a .onion address yet; add it on your home network "
                           "(use your password and authenticator over Tor)", reason="passkey_enrolment_unavailable_on_onion")

    def passkey_register_options(self, request: Request, ctx: AuthContext | None, recovering: bool = False) -> dict:
        user = self._account(ctx, "register a passkey")
        self._refuse_onion_enrolment(request, ctx)
        existing = list(self.repo.all(select(PasskeyRow.id).where(PasskeyRow.user_id == user.id)))
        recovery_id = remote_recovery.registration_id(self, ctx) if recovering else None
        vouched = ""
        if existing and not recovery_id:  # adding a second key is adding power: prove you hold the first
            via = self.require_step_up(ctx, ctx.principal, "register a passkey", op="auth.passkeys.register")
            vouched = self._vouch(via)
        proof = ctx.redeemed_step_up.data if vouched and ctx.redeemed_step_up is not None else {}
        if not proof.get("credential_id"):
            vouched = ""  # a password and authenticator grant: the registration asks for the box code itself
        rp_id, _ = self.rp(request)
        # An owner's key that would enrol at L2 or more (a proven key) needs one of three things, before and after
        # the grace and whatever keys the owner already has (N-1 = b; final review of #1184; D-034):
        #   - a step-up grant for this registration made with the owner's own proven key (lv.PROVEN_KEY_VOUCH),
        #     which the admin.high_risk row can't lower, or with an L1 passkey plus the box's code at home;
        #   - the code on the box's own screen, typed at home with the registration; or
        #   - a completed remote recovery (D-034: fresh L1, the recovery-kit code and a 72-hour wait).
        # Otherwise an L1 key (a synced phone passkey somewhere else) or a password could enrol a key of its own
        # that is L2, for instance after deleting its owner's only key, or with admin.high_risk lowered to L1.
        # An L1 key (a phone or computer passkey) still enrols without any of them. Only an owner's key counts
        # for approvals, so only an owner's enrolment needs this; a member's proven key meets the same floor when
        # they are made an owner (_op_rule, users.update). There is no first-key exemption: the household's
        # first proven owner key is also added at the box (D-034 first run) or through remote recovery.
        box = user.role == "owner" and not vouched
        data = {"session_id": ctx.session.id, "credential_revision": user.credential_revision,
                "role": user.role, "box_for_proven": box, "vouched": vouched or None}
        if vouched:
            data.update(vouch_session_id=proof["session_id"], vouch_credential_id=proof["credential_id"])
        shown = False
        if recovery_id:
            data["remote_recovery_id"] = recovery_id
        elif box and ctx.home and self.presence.available:
            try:
                data["box_sha256"] = self.presence.issue("add a proven key", self.now() + CHALLENGE_TTL)
                shown = True
            except ApiError as exc:  # paused after wrong codes: an L1 key still enrols, a proven one waits
                data["box_refused"] = {"status": exc.status, "reason": exc.reason, "message": exc.message}
        row, raw = self._new_challenge("register", user_id=user.id, data=data)
        opts = pk.registration_options(rp_id=rp_id, rp_name=self.cfg.rp_name, user_id=user.id,
                                       user_name=user.username or user.id, display_name=user.display_name,
                                       challenge=raw, exclude=existing)
        return {"challenge_id": row.id, "expires_at": iso(row.expires_at), "publicKey": opts,
                "box_code_if_proven": shown}

    def passkey_register(self, request: Request, ctx: AuthContext | None, credential: dict, label: str | None,
                         install_id: str | None = None, box_code: str | None = None) -> dict:
        user = self._account(ctx, "register a passkey")
        self._refuse_onion_enrolment(request, ctx)
        try:
            credential = pk.normalize(credential)
            row = self._consume_challenge(credential, "register")
        except pk.PasskeyError as exc:
            raise ApiError(422, "conflict", str(exc)[:300], reason="assertion_invalid") from None
        if (row.user_id != user.id or row.data.get("session_id") != ctx.session.id
                or row.data.get("credential_revision") != user.credential_revision):
            raise ApiError(401, "unauthenticated", "registration belongs to another session or credential revision",
                           reason="assertion_invalid")
        rp_id, origins = self.rp(request)
        try:
            v = pk.verify_registration(credential=credential, challenge=pk.unb64url(row.challenge), rp_id=rp_id,
                                       origins=origins, roots_for=self.levels.roots_for)
        except pk.PasskeyError as exc:
            self.emit("auth", "passkey.rejected", {"user_id": user.id, "reason": "registration_invalid"},
                      ctx.principal, severity="warning")
            raise ApiError(422, "conflict", str(exc)[:300], reason="assertion_invalid") from None
        if len(v["id"]) > MAX_CREDENTIAL_ID:
            raise ApiError(422, "conflict", "credential id is too long", reason="assertion_invalid")
        if self.repo.get(PasskeyRow, v["id"]) is not None:
            raise ApiError(409, "conflict", "this passkey is already registered")
        now = self.now()
        label = (label or "passkey").strip()[:100] or "passkey"
        model = self.levels.models().get(v["aaguid"])
        level, why = lv.credential_level(fmt=v["fmt"], has_chain=v["has_chain"], backup_eligible=v["backup_eligible"],
                                         model=model, chain_ok=v["chain_ok"])
        proven = lv.rank(level) >= lv.PROVEN_KEY_VOUCH
        why_grace_ended = f"passkey {v['id'][:32]}"
        grace_ended = False
        recovery_id = row.data.get("remote_recovery_id")
        vouched = row.data.get("vouched")
        needs_code = bool(row.data.get("box_for_proven")) and not recovery_id
        if recovery_id and not proven:
            raise ApiError(409, "conflict", "remote approval recovery needs a proven key on this session",
                           reason="remote_recovery_proven_key_required")
        if proven and needs_code:
            if not ctx.home:
                raise ApiError(409, "conflict", "use remote approval recovery to add a proven key away from the box",
                               reason="remote_recovery_required")
            if (refused := row.data.get("box_refused")) is not None:
                raise ApiError(refused["status"], "rate_limited" if refused["status"] == 429 else "unavailable",
                               refused["message"], reason=refused["reason"])
            if not row.data.get("box_sha256"):
                raise ApiError(409, "conflict", "this is a proven key: add it with your proven key's confirmation, "
                               "or at the box, which this install has no screen for; nothing was saved",
                               reason="box_presence_unavailable")
            self._check_local_box(request, row.data["box_sha256"], box_code, "add a proven key")
        with self.repo.lock_user(user.id) as (db, current):
            if current is None or current.disabled:
                raise ApiError(401, "unauthenticated", "account disabled", reason="bad_credentials")
            # Serialize on the same user row that password resets and replacement invites update.
            unchanged = db.execute(update(UserRow).where(
                UserRow.id == user.id, UserRow.role == user.role, UserRow.disabled.is_(False),
                UserRow.credential_revision == user.credential_revision,
            ).values(credential_revision=UserRow.credential_revision).returning(UserRow.id),
                execution_options={"synchronize_session": False}).scalar_one_or_none()
            if unchanged is None:
                raise ApiError(409, "conflict", "the account credentials changed; sign in and try again",
                               reason="credentials_changed")
            if vouched:
                session_id, credential_id = row.data.get("vouch_session_id"), row.data.get("vouch_credential_id")
                vouch_session = (db.get(SessionRow, session_id, with_for_update=True)
                                 if session_id == ctx.session.id else None)
                key = db.get(PasskeyRow, credential_id) if credential_id else None
                need = lv.PROVEN_KEY_VOUCH if vouched == "proven_key" else 1
                if (vouch_session is None or not self._session_live(vouch_session, self.now())
                        or key is None or key.user_id != user.id
                        or self.levels.cred_level(key, self.levels.models(db)) < need):
                    raise ApiError(409, "conflict", "passkey confirmation is no longer valid for this session; "
                                   "request new passkey registration options", reason="registration_options_stale")
            # A promotion may land while registration is pending: options made for a member never let the new
            # owner finish a proven registration without a vouch, the box code or a remote recovery.
            if (proven and current.role == "owner" and not (needs_code or vouched or recovery_id)
                    and (row.data.get("role") != "owner" or self._owner_verification_active(db))):
                raise ApiError(409, "conflict", "verification requirements changed; request new passkey "
                               "registration options", reason="registration_options_stale")
            session = ctx.session
            now = self.now()
            transport_live = (SessionRow.last_seen_at > now - timedelta(hours=self.cfg.session_idle_hours)
                              if session.transport == "cookie" else SessionRow.access_expires_at > now)
            updated = db.execute(update(SessionRow).where(
                SessionRow.id == session.id, SessionRow.user_id == user.id,
                SessionRow.credential_revision == user.credential_revision, SessionRow.revoked_at.is_(None),
                SessionRow.expires_at > now, transport_live,
            ).values(passkey_at=now, step_up_credential_id=v["id"]).returning(SessionRow.id),
                # the vouch check may have loaded this row: SQLite's naive times can't be compared in Python
                execution_options={"synchronize_session": False}).scalar_one_or_none()
            if updated is None:
                raise ApiError(401, "unauthenticated", "the session ended; sign in and try again", reason="session_required")
            if recovery_id:
                remote_recovery.consume(self, db, ctx, recovery_id)
            db.add(PasskeyRow(id=v["id"], user_id=user.id, label=label, public_key=v["public_key"],
                              sign_count=v["sign_count"], transports=v["transports"], created_at=now,
                              install_id=install_id, aaguid=v["aaguid"], att_fmt=v["fmt"][:24],
                              att_chain_sha256=v["chain_sha256"], backup_eligible=v["backup_eligible"],
                              backed_up=v["backed_up"], level=level, level_reason=why,
                              model=model.name if model and level != "L1" else None))
            if current.role == "owner":
                db.flush()  # record_proven counts this key
                self.repo.set_household_flag(db, OWNER_PASSKEY_SEEN, now, "owner passkey registered")
                if proven:
                    grace_ended = self.levels.record_proven(db, why_grace_ended)
        if recovery_id:
            self.emit("auth", "remote_recovery.completed", {"user_id": user.id}, ctx.principal, severity="warning")
        # How a proven key was vouched for: "proven_key", "box", "remote_recovery", or None (an L1 or member key).
        confirmed = (vouched or ("remote_recovery" if recovery_id else "box" if needs_code else None)) if proven else None
        self.emit("auth", "passkey.registered", {"user_id": user.id, "credential_id": v["id"], "label": label,
                                                 "level": level, "level_reason": why, "aaguid": v["aaguid"],
                                                 "attestation": v["fmt"], "confirmed": confirmed}, ctx.principal)
        if grace_ended:
            self.levels.emit_grace_ended(why_grace_ended)
        return {"credential_id": v["id"], "label": label, "created_at": iso(now), "level": level,
                "level_reason": why, "explanation": lv.REASON_TEXT[why]}

    def list_passkeys(self, ctx: AuthContext | None) -> list[dict]:
        user = self._person(ctx)
        rows = self.repo.all(select(PasskeyRow).where(PasskeyRow.user_id == user.id).order_by(PasskeyRow.created_at))
        models = self.levels.models()
        out = []
        for r in rows:
            level = self.levels.cred_level(r, models)
            why = r.level_reason or "legacy"
            if r.level == "L2" and level < 2:
                why = "model_not_trusted"  # its model has left the allow-list since
            out.append({"credential_id": r.id, "label": r.label, "created_at": iso(r.created_at),
                        "last_used_at": iso(r.last_used_at), "level": lv.name(level), "level_reason": why,
                        "explanation": lv.REASON_TEXT.get(why, ""), "model": r.model if level >= 2 else None,
                        "aaguid": r.aaguid, "attestation": r.att_fmt,
                        "device_bound": None if r.backup_eligible is None else not r.backup_eligible,
                        "synced": r.backed_up})
        return out

    def delete_passkey(self, ctx: AuthContext | None, credential_id: str) -> None:
        user = self._account(ctx, "remove a passkey")
        row = self.repo.get(PasskeyRow, credential_id)
        if row is None or row.user_id != user.id:
            raise ApiError(404, "not_found", "no such passkey")
        if self._last_proven(credential_id):
            self.require_step_up(ctx, ctx.principal, "remove the last proven key", op="auth.passkeys.delete",
                                 target=credential_id)
        self.remove_passkeys(ctx, {row.id})
        self.emit("auth", "passkey.removed", {"user_id": user.id, "credential_id": row.id}, ctx.principal)

    def remove_passkeys(self, ctx: AuthContext, credential_ids: set[str]) -> set[str]:
        user = ctx.user
        if not user.password_hash and not self.repo.count(PasskeyRow, PasskeyRow.user_id == user.id,
                                                          PasskeyRow.id.not_in(credential_ids)):
            raise ApiError(409, "conflict", "this is your only way to sign in", reason="last_sign_in_method")
        auth_method = "password" if ctx.session.auth_method == "passkey" else None
        return self._change_credentials(ctx, {}, user.credential_revision, auth_method=auth_method,
                                        remove_passkey_ids=credential_ids)

    # ---- password and TOTP -------------------------------------------------------------------------
    # ---- device-bound approver keys (#702) ------------------------------------------------------
    @staticmethod
    def approver_key_json(k: ApproverKeyRow) -> dict:
        return {"key_id": k.id, "label": k.label, "key_kind": k.key_kind, "fingerprint": k.fingerprint,
                "created_at": iso(k.created_at), "last_used_at": iso(k.last_used_at), "revoked_at": iso(k.revoked_at)}

    def register_approver_key(self, ctx: AuthContext | None, public_key: str, label: str, key_kind: str) -> dict:
        user = self._account(ctx, "register an approver key")
        if user.role != "owner":
            raise self.deny(ctx.principal, "register an approver key", reason="owner_only")
        self.require_step_up(ctx, ctx.principal, "register an approver key", op="auth.approver_keys.register",
                             body={"public_key": public_key, "label": label, "key_kind": key_kind})
        if key_kind not in ak.KEY_KINDS:
            raise ApiError(422, "conflict", f"key_kind must be one of {', '.join(ak.KEY_KINDS)}")
        if key_kind == "hardware-attested":  # nothing verifies an attestation chain yet: never claim it
            raise ApiError(422, "conflict", "hardware attestation is not verified yet; register as hardware-reported",
                           reason="attestation_unverified")
        label = " ".join((label or "").split())[:100]
        if not label:
            raise ApiError(422, "conflict", "name the phone this key lives on")
        try:
            der, fingerprint = ak.parse_public_key(public_key)
        except ak.ApproverKeyError as exc:
            raise ApiError(422, "conflict", str(exc)) from None
        if self.repo.one(select(ApproverKeyRow.id).where(ApproverKeyRow.fingerprint == fingerprint)) is not None:
            raise ApiError(409, "conflict", "this key is already registered (or was revoked); make a new one")
        active = self.repo.all(select(ApproverKeyRow).where(ApproverKeyRow.user_id == user.id,
                                                             ApproverKeyRow.revoked_at.is_(None)))
        if any(k.label == label for k in active):
            raise ApiError(409, "conflict", f"{label} already has an approver key; revoke it first", reason="label_taken")
        if len(active) >= ak.MAX_ACTIVE_PER_USER:
            raise ApiError(409, "conflict", "too many approver keys; revoke one first")
        row = ApproverKeyRow(id=new_id("apk"), user_id=user.id, label=label, key_kind=key_kind, public_key=der,
                             fingerprint=fingerprint, created_at=self.now())
        self.repo.add(row)
        self.emit("auth", "approver_key.registered", {"user_id": user.id, "key_id": row.id, "label": label,
                                                      "key_kind": key_kind, "fingerprint": fingerprint}, ctx.principal)
        return self.approver_key_json(row)

    def list_approver_keys(self, ctx: AuthContext | None) -> list[dict]:
        user = self._person(ctx)
        rows = self.repo.all(select(ApproverKeyRow).where(ApproverKeyRow.user_id == user.id)
                             .order_by(ApproverKeyRow.created_at))
        return [self.approver_key_json(r) for r in rows]

    def revoke_approver_key(self, ctx: AuthContext | None, key_id: str) -> None:
        """Revoking takes power away, so no step-up: a lost phone is cut off from any signed-in device."""
        user = self._person(ctx)
        row = self.repo.get(ApproverKeyRow, key_id)
        if row is None or row.user_id != user.id:
            raise ApiError(404, "not_found", "no such approver key")
        if row.revoked_at is not None:
            return
        self.repo.update(ApproverKeyRow, [ApproverKeyRow.id == row.id], {"revoked_at": self.now()})
        self.emit("auth", "approver_key.revoked", {"user_id": user.id, "key_id": row.id, "label": row.label,
                                                   "key_kind": row.key_kind}, ctx.principal)

    def change_password(self, request: Request, ctx: AuthContext | None, current: str, new: str) -> None:
        user = self._account(ctx, "change the password")
        now, src = self.now(), source_of(request)
        self.limiter.check(src, now)
        if not verify_password(current or "", user.password_hash):
            self.limiter.fail(src, now)
            self.emit("auth", "password.change_failed", {"user_id": user.id}, ctx.principal, severity="warning")
            raise ApiError(401, "unauthenticated", "current password is wrong", reason="bad_credentials")
        self._check_password(new)
        self._change_credentials(ctx, {"password_hash": hash_password(new)}, user.credential_revision)
        self.emit("auth", "password.changed", {"user_id": user.id, "other_sessions_revoked": True}, ctx.principal)

    @staticmethod
    def revoke_sessions(db, user_id: str, now: datetime, keep: str = ""):
        return db.execute(update(SessionRow).where(SessionRow.user_id == user_id, SessionRow.id != keep,
                                                    SessionRow.revoked_at.is_(None)).values(revoked_at=now)
                          .returning(SessionRow.id)).scalars()

    def _change_credentials(self, ctx: AuthContext, changes: dict, revision: int | None, *conditions,
                            auth_method: str | None = None, remove_passkey_ids: set[str] | None = None) -> set[str]:
        now, user_id, session_id = self.now(), ctx.user.id, ctx.session.id
        revised = (revision or 0) + 1
        with self.repo.db.session.begin() as db:
            changed = db.execute(update(UserRow).where(
                UserRow.id == user_id, UserRow.credential_revision == revision, UserRow.disabled.is_(False), *conditions
            ).values(**changes, credential_revision=revised, updated_at=now).returning(UserRow.id)).scalar_one_or_none()
            if changed is None:
                raise ApiError(409, "conflict", "the account credentials changed; sign in and try again",
                               reason="credentials_changed")
            if remove_passkey_ids:
                db.execute(delete(PasskeyRow).where(PasskeyRow.id.in_(remove_passkey_ids), PasskeyRow.user_id == user_id))
            db.execute(update(SessionRow).where(SessionRow.id == session_id).values(
                credential_revision=revised, passkey_at=None, step_up_credential_id=None, totp_at=None,
                auth_method=auth_method or ctx.session.auth_method))
            return set(self.revoke_sessions(db, user_id, now, keep=session_id))

    def sign_in_methods(self, ctx: AuthContext | None) -> dict:
        """GET /v1/auth/methods: what the person's own sign-in looks like. Reading needs no session (a
        person's token may read it); changing any of it does (_account)."""
        person = self._person(ctx)
        user = self.user(person.id) or person  # re-read: a change in this request's session is seen at once
        return {"password": user.password_hash is not None, "totp": user.totp_secret is not None,
                "passkeys": self.repo.count(PasskeyRow, PasskeyRow.user_id == user.id),
                "passkeys_active": self.passkeys_active()}

    def totp_setup(self, ctx: AuthContext | None) -> dict:
        user = self._account(ctx, "set up an authenticator")
        if user.totp_secret:
            raise ApiError(409, "conflict", "an authenticator is already set up; turn it off first")
        secret = new_totp_secret()
        if not self.repo.update(UserRow, [UserRow.id == user.id, UserRow.credential_revision == user.credential_revision,
                                          UserRow.totp_secret.is_(None)], {"totp_pending": secret}):
            raise ApiError(409, "conflict", "the account credentials changed; sign in and try again")
        return {"one_time": {"secret": secret,
                             "otpauth_uri": otpauth_uri(secret, user.username or user.id, self.cfg.rp_name)}}

    def totp_confirm(self, ctx: AuthContext | None, code: str) -> None:
        user = self._account(ctx, "set up an authenticator")
        fresh = self.user(user.id)
        if not fresh.totp_pending:
            raise ApiError(409, "conflict", "start authenticator setup first")
        step = totp_match(fresh.totp_pending, code, self.now().timestamp())
        if step is None:
            raise ApiError(422, "conflict", "that code does not match", reason="totp_invalid")
        self._change_credentials(ctx, {"totp_secret": fresh.totp_pending, "totp_pending": None,
                                       "totp_last_step": step}, user.credential_revision,
                                 UserRow.totp_pending == fresh.totp_pending, UserRow.totp_secret.is_(None))
        self.emit("auth", "totp.enabled", {"user_id": user.id}, ctx.principal)

    def totp_disable(self, request: Request, ctx: AuthContext | None, password: str) -> None:
        user = self._account(ctx, "turn off the authenticator")
        if not self.is_home(request):
            raise self.deny(ctx.principal, "turn off the authenticator away from the box", reason="home_network_required")
        self._check_login_password(request, user.username or user.id, password, user)
        self._change_credentials(ctx, {"totp_secret": None, "totp_pending": None, "totp_last_step": None},
                                 user.credential_revision,
                                 auth_method="password" if ctx.session.auth_method == "password+totp" else None)
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
        if ctx is None or ctx.session is None or ctx.user is None:
            raise self.deny(p, "create users without a signed-in household session", reason="session_required")
        via = self.require_step_up(ctx, p, "create users", op="users.create",
                                   body={"display_name": display_name, "role": role, "username": username})
        u, code = self._create_invited_user(p, display_name, role, username, via)
        return self._invite_response(request, u, code, "/signin")

    def _create_invited_user(self, p: Principal, display_name: str, role: str, username: str | None,
                             via: str) -> tuple[UserRow, str]:
        now = self.now()
        code = secrets.token_urlsafe(24)
        u = UserRow(id=new_id("usr"), username=self._new_username(username) if username else None,
                    display_name=(display_name or "").strip()[:100] or "member", role=self._role(role),
                    enrol_hash=sha256_hex(code), enrol_expires_at=now + ENROL_TTL,
                    created_at=now, updated_at=now, created_by=p.id)
        self.repo.add(u)
        self.emit("user", "created", {"user_id": u.id, "role": u.role, "step_up": via}, p)
        for hook in self.role_hooks:
            hook(u.id, u.role, p)
        return u, code

    def _invite_response(self, request: Request, u: UserRow, code: str, path: str) -> dict:
        base = (self.gw.settings.public_url or str(request.base_url)).rstrip("/")
        return {**self.user_json(u), "one_time": {"enrolment_code": code, "enrolment_url": f"{base}{path}#enrol={code}",
                                                  "expires_at": iso(u.enrol_expires_at)}}

    def _replace_invite(self, p: Principal, user_id: str, revision: int | None) -> str:
        now, code = self.now(), secrets.token_urlsafe(24)
        with self.repo.db.session.begin() as db:
            changed = db.execute(update(UserRow).where(
                UserRow.id == user_id, UserRow.role != "owner", UserRow.disabled.is_(False),
                UserRow.credential_revision == revision,
            ).values(enrol_hash=sha256_hex(code), enrol_expires_at=now + ENROL_TTL, password_hash=None,
                     totp_secret=None, totp_pending=None, totp_last_step=None, recovery_hash=None, email=None,
                     email_verified_at=None,
                     credential_revision=(revision or 0) + 1, updated_at=now
                     ).returning(UserRow.id)).scalar_one_or_none()
            if changed is None:
                raise ApiError(409, "conflict", "the account changed; request a new confirmation")
            self.revoke_sessions(db, user_id, now)
            db.execute(delete(PasskeyRow).where(PasskeyRow.user_id == user_id))
            db.execute(update(TokenRow).where(TokenRow.owner_user_id == user_id, TokenRow.revoked_at.is_(None)).values(
                revoked_at=now, prev_hash=None))
        self.emit("user", "invite.replaced", {"user_id": user_id, "step_up": "approval"}, p, severity="warning")
        return code

    def _last_owner_guard(self, u: UserRow, becomes_non_owner: bool) -> None:
        if u.role == "owner" and not u.disabled and becomes_non_owner and self.active_owner_ids() == [u.id]:
            raise ApiError(409, "conflict", "the last owner cannot be demoted or disabled", reason="last_owner")

    def update_user(self, ctx: AuthContext | None, p: Principal, user_id: str, display_name: str | None,
                    role: str | None) -> dict:
        self._owner_only(p, "change users")
        u = self.user(user_id)
        if u is None:
            raise ApiError(404, "not_found", "no such user")
        if role is not None and role != u.role:
            self._last_owner_guard(u, self._role(role) != "owner")
        via = self.require_step_up(ctx, p, "change users", op="users.update", target=user_id,
                                   body={"display_name": display_name, "role": role})
        values: dict = {"updated_at": self.now()}
        if display_name is not None:
            values["display_name"] = display_name.strip()[:100] or u.display_name
        if role is not None and role != u.role:
            values["role"] = role
        why_grace_ended = f"owner promotion {u.id}"
        grace_ended = False
        if values.get("role") == "owner":
            with self.repo.lock_user(u.id) as (s, current):
                # A member may finish enrolling a proven key after the promotion's step-up was checked. With
                # sign-in verification always on once a household account exists (D-034), there is no
                # pre-passkey exemption here either.
                if not self._vouch(via) and s.scalar(self._member_proven_key(u.id)) is not None:
                    raise ApiError(409, "conflict", "this person enrolled a proven key; retry the role change",
                                   reason="promotion_verification_changed")
                s.execute(update(UserRow).where(UserRow.id == u.id).values(**values))
                if current is not None and not current.disabled and s.scalar(
                        select(PasskeyRow.id).where(PasskeyRow.user_id == u.id).limit(1)) is not None:
                    self.repo.set_household_flag(s, OWNER_PASSKEY_SEEN, values["updated_at"], "owner promoted with passkey")
                    grace_ended = self.levels.record_proven(s, why_grace_ended)
        else:
            self.repo.update(UserRow, [UserRow.id == u.id], values)
        changed = sorted(k for k in values if k != "updated_at")
        self.emit("user", "updated", {"user_id": u.id, "changed": changed, "role": values.get("role", u.role),
                                      "step_up": via}, p)
        if grace_ended:
            self.levels.emit_grace_ended(why_grace_ended)
        if "role" in values:
            for hook in self.role_hooks:
                hook(u.id, values["role"], p)
        return self.user_json(self.user(u.id))

    def update_profile(self, request: Request, p: Principal, fields: dict) -> dict:
        """Display and contact fields have no bearing on authentication or access."""
        ctx = ctx_of(request)
        if p.kind != "person" or ctx is None or ctx.user is None:
            raise self.deny(p, "update a profile")
        changes, result = {}, {}
        if "display_name" in fields:
            name = fields["display_name"]
            changes["profile_name"] = result["display_name"] = clean_profile_name(name) if name is not None else None
        if "email" in fields:
            self._account(ctx, "set a contact email")
            changes["email"] = result["email"] = clean_email(fields["email"])
            changes["email_verified_at"] = None
            result["email_verified"] = False
        if changes:
            self.repo.update(UserRow, [UserRow.id == ctx.user.id], {**changes, "updated_at": self.now()})
        if "profile_name" in changes:
            self.emit("user", "profile_name.changed", {"user_id": ctx.user.id, "cleared": changes["profile_name"] is None}, p)
        if "email" in changes:
            self.emit("user", "email.changed", {"user_id": ctx.user.id, "cleared": changes["email"] is None}, p)
        return result

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
            if user is None and not p.is_owner:
                # A static-file adult has no household account, so the token would be owned by no one:
                # it would outlive the adult's removal and the adult could not list or revoke it.
                raise ApiError(403, "permission_denied", "a static-file principal cannot hold API tokens; "
                                                         "set up a household account first")
            principal_id = str(principal.get("id") or "")
            if not AGENT_ID_RE.fullmatch(principal_id):
                raise ApiError(422, "conflict", "agent id must look like agent:<name> (a-z, 0-9, '.', '_', '-')")
            self._check_agent_id(principal_id, user, p)
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
        expires_at = now + timedelta(days=days)
        if ctx is not None and ctx.token is not None and ctx.token.expires_at is not None:
            # A token never mints a token that outlives it (no lifetime laundering with a stolen PAT).
            expires_at = min(expires_at, utc(ctx.token.expires_at))
        secret = new_secret(TOKEN_KINDS[kind])
        t = TokenRow(id=new_id("tok"), prefix=secret[:11], name=(name or "token").strip()[:100] or "token",
                     hash=sha256_hex(secret), kind=kind, principal_id=principal_id,
                     owner_user_id=user.id if user else None, scopes=wanted, source="api", created_by=p.id,
                     created_at=now, expires_at=expires_at)
        self.repo.add(t)
        self.emit("auth", "token.created", {"token_id": t.id, "kind": kind, "principal_id": principal_id,
                                            "scopes": wanted, "expires_at": iso(t.expires_at)}, p)
        return {**self.token_json(t), "one_time": {"token": secret}}

    def _check_agent_id(self, principal_id: str, user: UserRow | None, p: Principal) -> None:
        """A personal agent id must not reuse an app's agent principal (agent:<app-id>, §11.2), a
        static-file principal, or another person's agent: its requests would be shown and audited
        as that principal's."""
        app_id = principal_id.partition(":")[2]
        taken = app_id in self.gw.catalog.load() or any(fp.id == principal_id for _, fp in self.gw.tokens.entries())
        if not taken:
            owner_id = user.id if user else None
            others = self.repo.all(select(TokenRow.owner_user_id).where(TokenRow.kind == "agent",
                                                                         TokenRow.principal_id == principal_id))
            taken = any(o != owner_id for o in others)
        if taken:
            self.emit("authz", "denied", {"attempted": "mint agent token", "principal_id": principal_id,
                                          "reason": "agent_id_taken"}, p, severity="warning")
            raise ApiError(409, "conflict", f"agent id {principal_id!r} belongs to an app or another principal",
                           reason="agent_id_taken")

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
        if t.kind == "plugin" and t.source == "app-install":
            raise self.deny(p, "rotate an installation-managed plugin token", token_id=t.id)
        uid = ctx.user.id if ctx and ctx.user else None
        if t.owner_user_id is not None and t.owner_user_id != uid:
            # Rotation hands out the new secret: an owner may revoke another person's token, but not
            # obtain a working secret for it (that would let them act as that person).
            raise self.deny(p, "rotate another person's token", token_id=t.id)
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

    def shared_roles(self, app_id: str) -> list[str]:
        """Roles an app is shared with (§12.6), for other features to show (GET /v1/apps/{id})."""
        return self._access(app_id)["roles"]

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
        asked = {"roles": list(roles), "people": list(people), "auth": auth}  # what a step-up binds (design 3.11)
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
        # Moving people to the app's own sign-in is a security setting too (design 3.11, D-028): OneMind stops
        # checking who opens it, so it asks for the same step-up as sharing with more people.
        widens = bool(set(roles) - set(before["roles"]) or set(people) - set(before["people"])
                      or (auth == "app" and before["auth"] != "app"))
        via = self.require_step_up(ctx, p, "share an app", op="apps.access.set", target=app_id,
                                   body=asked) if widens else "not_needed"
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

    def _approval_view(self, request: Request, p: Principal, action_id: str) -> dict:
        return self._approval_action(p, action_id)  # a file request (frq_) or an action; 404 when unknown

    def _approval_verification(self, need: int, strict: bool, home: bool, ctx: AuthContext | None) -> dict:
        user = ctx.user if ctx and ctx.session else None
        box_available = need == 2 and not strict and home and self.presence.available
        return {"required_level": lv.name(need), "box_available": box_available,
                "password_totp_available": bool((need <= 1 or box_available) and user
                                                and user.password_hash and user.totp_secret)}

    def approve_options(self, request: Request, p: Principal, action_id: str, *, at_box: bool = False,
                        method: str = "passkey") -> dict:
        if not p.is_owner:
            raise self.deny(p, "approve actions", action_id=action_id)
        action = self._approval_view(request, p, action_id)
        if action.get("state") != "awaiting_approval":
            raise ApiError(409, "conflict", f"action is {action.get('state')}, not awaiting_approval")
        ctx = ctx_of(request)
        if action["type"] in lv.FAMILY_INVITE_ACTIONS:
            self._account(ctx, "approve a family invitation")
        a_sha = self.action_sha256(action)
        p_sha = action.get("plan_sha256") or ""
        nonce = os.urandom(32)
        raw = hashlib.sha256(action_id.encode() + a_sha.encode() + p_sha.encode() + nonce).digest()
        user_id = ctx.user.id if ctx and ctx.user else None
        allow_users = [user_id] if user_id else self.active_owner_ids()
        need, strict, decided_by = self.levels.for_action(action)
        home = self.is_home(request)
        eased = home and self.levels.grace(need, strict)
        box = need == 2 and not strict and home and (at_box or eased)
        factor_need = 1 if box else need
        what = f"approve {action.get('type')}"
        verification = self._approval_verification(need, strict, home, ctx)
        if at_box and strict:
            raise self._level_unmet(p, what, need, details=[{"approval_verification": verification}])
        allow = self._keys_meeting(allow_users, factor_need) if method == "passkey" else []
        if method == "password+totp":
            user = self._account(ctx, "approve with an authenticator")
            self._require_totp_available(user, p, what, factor_need)
        elif (at_box and need == 2 and not home) or (not allow and self.account_setup_exists() and need >= 2):
            if box and not self.presence.available:
                self.presence.issue(what, self.now() + CHALLENGE_TTL)  # raises box_presence_unavailable
            raise self._level_unmet(p, what, need, details=[{"approval_verification": verification}])
        data = {"action_sha256": a_sha, "plan_sha256": p_sha or None, "need": factor_need, "method": method,
                "session_id": ctx.session.id if ctx and ctx.session else None}
        if box:
            data["box_sha256"] = self.presence.issue(what, self.now() + CHALLENGE_TTL)
        row, _ = self._new_challenge("approve", user_id=user_id, action_id=action_id, data=data, raw=raw)
        public_key = self._assertion_options(request, raw, allow) if method == "passkey" else {}
        return {"challenge": row.challenge, "action_sha256": a_sha, "plan_sha256": p_sha or None,
                **verification,
                "expires_at": iso(row.expires_at), "required_level": lv.name(factor_need), "grace": eased,
                "box_code_required": box,
                "decided_by": decided_by,
                "device_payload": ak.signing_payload(row.challenge, action_id, a_sha, p_sha or None).decode(),
                "publicKey": public_key}

    def action_view(self, row: dict) -> dict:
        """required_level on a request waiting for approval (D-028), so a card shows "Needs L2" before the
        owner tries. It is the table's level: during the grace an L1 key plus the box's code stands in for
        L2, and approve-options says so (box_code_required)."""
        if row.get("state") != "awaiting_approval" or not self.account_setup_exists():
            return row
        need = self.levels.for_action(row)[0]
        return {**row, "required_level": lv.name(max(need, 1))}

    def _approval_action(self, p: Principal, action_id: str) -> dict:
        for lookup in self.gw.approval_lookups:
            if (action := lookup(p, action_id)) is not None:
                return action
        return self.gw.actions.get(action_id)

    def approval_guard(self, p: Principal, action_id: str, body: dict, request: Request) -> None:
        if not p.is_owner:
            return  # actions.approve refuses and audits non-owners itself
        ctx = ctx_of(request)
        assertion = body.get("webauthn")
        password_totp = body.get("password_totp")
        if sum(proof is not None for proof in (assertion, password_totp, body.get("device_signature"))) > 1:
            raise ApiError(422, "conflict", "send one approval proof")
        raw_action = None if action_id.startswith("frq_") else self.gw.repo.get(action_id)
        spec = self.gw.actions.feature_types.get(raw_action.type) if raw_action is not None else None
        if spec is not None and spec.owner_passkey:  # an owner's own security setting: only their passkey
            owner = self._account(ctx, "approve an owner security setting")
            if owner.id != raw_action.requested_by.get("id"):
                raise self.deny(p, "approve another owner's security setting", reason="owner_only")
            if assertion is None:
                raise self._step_up_failed(p, action_id, "approve this security setting with your passkey")
        if assertion is None and password_totp is None and body.get("device_signature") is None \
                and not self.account_setup_exists():
            return  # installation owner before the box has a household account
        action = self._approval_view(request, p, action_id)
        family = action["type"] in lv.FAMILY_INVITE_ACTIONS
        if family:
            self._account(ctx, "approve a family invitation")
        if body.get("device_signature") is not None:
            if family:
                raise self._step_up_failed(p, action_id, "approve this family invitation with your passkey or authenticator")
            return self._approve_with_device_key(p, ctx, action_id, body)
        need, strict, decided_by = self.levels.for_action(action)
        if assertion is None and password_totp is None:
            fresh = self._fresh_l1(ctx)
            low_risk = need <= 1 and decided_by in {"tier.T0", "tier.T1"} and not strict
            # D-028 keeps tightening at L0, including ending a public bearer link.
            tightening = bool(body.get("plan_sha256") and action_id.startswith("frq_")
                              and action["type"] == "files.shares.revoke")
            if tightening:
                self.emit("auth", "approval.token", {"action_id": action_id, "via": fresh or (
                    ctx.session.auth_method if ctx and ctx.session else "token")}, p)
                return
            if not family and ((fresh == "password+totp" and need <= 1) or (
                    low_risk and ctx is not None and ctx.session is not None and ctx.home
                    and (not self.cfg.require_passkey_approval or ctx.session.auth_method != "passkey"))):
                self.emit("auth", "approval.token", {"action_id": action_id, "via": fresh or ctx.session.auth_method}, p)
                return
            self.emit("auth", "step_up.required", {"attempted": "approve", "action_id": action_id,
                                                   "required_level": lv.name(need)}, p, severity="warning")
            raise ApiError(401, "unauthenticated", "approve with your authenticator code and password, or with "
                           "your passkey", reason="step_up_required", details=[{"approval_verification":
                               self._approval_verification(need, strict, bool(ctx and ctx.home), ctx)}])
        if password_totp is not None:
            self._approve_with_password_totp(request, ctx, p, action, body, need, strict)
            return
        try:
            credential = pk.normalize(assertion)
            row = self._consume_challenge(credential, "approve")
        except pk.PasskeyError as exc:
            raise self._step_up_failed(p, action_id, str(exc)) from None
        except ApiError as exc:
            raise self._step_up_failed(p, action_id, exc.message) from None
        self._check_bound(p, action_id, row, body, action=action)
        if family and row.data.get("session_id") != ctx.session.id:
            raise self._step_up_failed(p, action_id, "challenge belongs to another session")
        if row.data.get("method", "passkey") != "passkey":
            raise self._step_up_failed(p, action_id, "challenge was made for another sign-in method")
        try:
            cred = self._assert(request, credential, row)
        except ApiError as exc:
            raise self._step_up_failed(p, action_id, exc.message) from None
        owner = self._live_user(cred.user_id)
        if owner is None or owner.role != "owner":
            raise self._step_up_failed(p, action_id, "passkey does not belong to an active owner")
        if ctx is not None and ctx.user is not None and ctx.user.id != owner.id:
            raise self._step_up_failed(p, action_id, "passkey belongs to another account")
        have = self.levels.cred_level(cred)
        at_box = bool(row.data.get("box_sha256"))
        if have < need and not (have >= 1 and need == 2 and at_box and not strict):
            raise self._step_up_failed(p, action_id, f"this approval needs your proven key ({lv.name(need)}); "
                                       f"this key is {lv.name(have)}", reason="level_unmet")
        if at_box:
            self._check_local_box(request, row.data["box_sha256"], body.get("box_code"), f"approve {action_id}")
        request.state.action_bound_proof = True
        if ctx is not None and ctx.session is not None:
            self.repo.update(SessionRow, [SessionRow.id == ctx.session.id], {"passkey_at": self.now(),
                                                                             "step_up_credential_id": cred.id})
        self.emit("auth", "step_up.succeeded", {"action_id": action_id, "credential_id": cred.id,
                                                "passkey_user_id": owner.id, "approval": "passkey",
                                                "level": lv.name(have), "required_level": lv.name(need),
                                                "grace": at_box and not self.levels.latched(), "at_box": at_box}, p)

    def _approve_with_password_totp(self, request: Request, ctx: AuthContext | None, p: Principal,
                                    action: dict, body: dict, need: int, strict: bool) -> None:
        user = self._account(ctx, "approve with an authenticator")
        proof = body["password_totp"]
        row = self._claim_challenge(proof["challenge"], "approve")
        action_id = action["id"]
        self._check_bound(p, action_id, row, body, action=action)
        if row.data.get("method") != "password+totp" or row.user_id != user.id \
                or row.data.get("session_id") != ctx.session.id:
            raise self._step_up_failed(p, action_id, "challenge belongs to another session or sign-in method")
        at_box = bool(row.data.get("box_sha256"))
        self._require_totp_available(user, p, f"approve {action_id}", 1 if need == 2 and at_box and not strict else need)
        self.verify_password_totp(request, user, proof["password"], proof["totp"])
        if at_box:
            self._check_local_box(request, row.data["box_sha256"], body.get("box_code"), f"approve {action_id}")
        request.state.action_bound_proof = True
        self.emit("auth", "step_up.succeeded", {"action_id": action_id, "approval": "password+totp",
                                                "level": "L2" if at_box else "L1", "at_box": at_box}, p)

    def _check_bound(self, p: Principal, action_id: str, row: ChallengeRow, body: dict, *,
                     action: dict | None = None) -> None:
        """The claimed challenge was made for this action, and neither the action nor its plan changed."""
        if row.action_id != action_id:
            raise self._step_up_failed(p, action_id, "challenge was issued for another action")
        current = action if action is not None else self._approval_action(p, action_id)
        if row.data.get("action_sha256") != self.action_sha256(current) or \
                (row.data.get("plan_sha256") or None) != (current.get("plan_sha256") or None):
            raise self._step_up_failed(p, action_id, "the action changed since the challenge", reason="plan_changed")
        if body.get("plan_sha256") and body["plan_sha256"] != (row.data.get("plan_sha256") or None):
            raise self._step_up_failed(p, action_id, "plan_sha256 differs from the one signed", reason="plan_changed")

    def _device_key_refusal(self, action: dict) -> str | None:
        """Why this action cannot be approved with a device key (F-2), or None when it can."""
        action_type = str(action.get("type"))
        if self.gw.actions.is_physical(action_type):
            return "it moves something physical"
        need, eased = self.levels.effective(*self.levels.for_action(action)[:2])
        if need >= 2:  # an approver key is L1 until its attestation is verified (design PR 18b)
            return f"it needs your proven key ({lv.name(need)})"
        if eased:  # the grace's L1 approval also needs the code on the box's own screen, which a phone can't send
            return "it needs your passkey and the code on the box's own screen"
        risk = action.get("risk")
        if risk is None:
            from ..automation import registry  # late, as in actions.py

            risk = registry.risk_of(action_type, action.get("params") or {}) if registry.known(action_type) else None
        if risk in ("read", "write", "sensitive"):
            return None
        if risk in ("destructive", "actuate") and self.cfg.approver_key_high_risk:
            return None
        return f"its risk is {risk or 'unknown'}"

    def _approve_with_device_key(self, p: Principal, ctx: AuthContext | None, action_id: str, body: dict) -> None:
        """#702: an ECDSA signature by the owner's phone key over approve-options' device_payload."""
        sig = body["device_signature"]
        why = self._device_key_refusal(self.gw.actions.get(action_id))
        if why:  # checked before the challenge is claimed, so the phone can fall back to its passkey
            self.emit("auth", "step_up.required", {"attempted": "approve", "action_id": action_id,
                                                   "reason": "device_key_not_allowed", "detail": why}, p,
                      severity="warning")
            raise ApiError(401, "unauthenticated", f"approve this with your passkey: {why}", reason="step_up_required")
        try:
            row = self._claim_challenge(str(sig.get("challenge") or ""), "approve")
        except ApiError as exc:
            raise self._step_up_failed(p, action_id, exc.message) from None
        self._check_bound(p, action_id, row, body)
        if row.data.get("method", "passkey") != "passkey" or row.data.get("box_sha256"):
            raise self._step_up_failed(p, action_id, "challenge requires a passkey or authenticator and box code")
        key = self.repo.get(ApproverKeyRow, str(sig.get("key_id") or ""))
        if key is None or key.revoked_at is not None:
            raise self._step_up_failed(p, action_id, "unknown or revoked approver key")
        owner = self._live_user(key.user_id)
        if owner is None or owner.role != "owner":
            raise self._step_up_failed(p, action_id, "approver key does not belong to an active owner")
        if (ctx is not None and ctx.user is not None and ctx.user.id != owner.id) or \
                (row.user_id is not None and row.user_id != owner.id):
            raise self._step_up_failed(p, action_id, "approver key belongs to another account")
        payload = ak.signing_payload(row.challenge, action_id, row.data.get("action_sha256") or "",
                                     row.data.get("plan_sha256") or None)
        try:
            ak.verify(key.public_key, payload, str(sig.get("signature") or ""))
        except ak.ApproverKeyError as exc:
            raise self._step_up_failed(p, action_id, str(exc)) from None
        now = self.now()
        self._touch_owner(owner, now)
        self.repo.update(ApproverKeyRow, [ApproverKeyRow.id == key.id], {"last_used_at": now})
        self.emit("auth", "step_up.succeeded", {"action_id": action_id, "approval": "device_key", "key_id": key.id,
                                                "key_kind": key.key_kind, "device": key.label,
                                                "approver_user_id": owner.id}, p)

    def _step_up_failed(self, p: Principal, action_id: str, why: str, reason: str = "assertion_invalid") -> ApiError:
        self.emit("auth", "step_up.failed", {"action_id": action_id, "reason": reason, "detail": why[:200]}, p,
                  severity="warning")
        if reason == "plan_changed":
            return ApiError(409, "stale_precondition", why, reason=reason)
        return ApiError(401, "unauthenticated", f"passkey check failed: {why}"[:300], reason="step_up_required")

    # ---- rescue console step-up (SEC-TERM-01, D-014) -----------------------------------------------
    # The rescue console (a separate Go process) opens a root shell only after the owner proves a fresh
    # passkey here. It forwards the owner's own credential; these two calls are not in the OpenAPI, the
    # SDK or the MCP tools, and they open nothing themselves: they only check and audit the assertion.
    def rescue_options(self, request: Request, p: Principal) -> dict:
        if not p.is_owner:
            raise self.deny(p, "start a rescue session")
        kit = self._kit_ready(request)
        if not self.passkeys_active():
            if kit:  # D-028: no dead end. The printed kit, typed at the console, stands in for a passkey.
                return {"methods": ["kit"], "kit": True}
            raise ApiError(409, "conflict", "no owner passkey is registered on this box, and no emergency kit was issued",
                           reason="no_passkey")
        now = self.now()
        if self.repo.count(ChallengeRow, ChallengeRow.purpose == "rescue", ChallengeRow.used_at.is_(None),
                           ChallengeRow.expires_at > now) >= MAX_OPEN_RESCUE_CHALLENGES:
            raise ApiError(429, "rate_limited", "too many rescue sign-ins in progress; try again shortly",
                           reason="too_many_pending", retry_after_s=int(CHALLENGE_TTL.total_seconds()))
        ctx = ctx_of(request)
        user_id = ctx.user.id if ctx and ctx.user else None
        allow_users = [user_id] if user_id else self.active_owner_ids()
        allow = list(self.repo.all(select(PasskeyRow.id).where(PasskeyRow.user_id.in_(allow_users))))
        row, raw = self._new_challenge("rescue", user_id=user_id)
        rp_id, _ = self.rp(request)
        return {"challenge_id": row.id, "expires_at": iso(row.expires_at), "methods": ["passkey"] + (["kit"] if kit else []),
                "kit": kit, "publicKey": pk.authentication_options(rp_id=rp_id, challenge=raw, allow=allow)}

    @staticmethod
    def _backups(request: Request):
        return getattr(request.app.state, "backups", None)

    def _kit_ready(self, request: Request) -> bool:
        b = self._backups(request)
        return b is not None and b.kit_ready()

    _PROXY_HEADERS = ("x-forwarded-for", "x-forwarded-host", "x-real-ip", "forwarded")

    @classmethod
    def _from_this_box(cls, request: Request) -> bool:
        """The TCP peer is loopback and no proxy header says the request came from further away (a reverse proxy
        on the box would also connect from loopback)."""
        host = request.client.host if request.client else ""
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False
        return loopback and not any(h in request.headers for h in cls._PROXY_HEADERS)

    def rescue_kit(self, request: Request, p: Principal, kit_key: str) -> dict:
        """D-028: the owner lost every passkey. The printed kit's owner key, typed at the box's console, proves
        owner access (the console only offers it to a browser on the box itself). Same answer as rescue_verify.
        It opens nothing itself, deletes nothing and never reads or shows a disk or backup key."""
        if not p.is_owner:
            raise self.deny(p, "start a rescue session")
        # Design 3.13 path 2: the kit key is typed at the box itself. The rescue console on the box calls this from
        # loopback; any other source, or a request that came through a proxy, is refused before the key is looked at,
        # so a LAN client with the owner token can neither test kit keys nor use up the shared lockout.
        if not self._from_this_box(request):
            err = self.deny(p, "use the printed kit away from the box", reason="kit_not_at_box")
            raise ApiError(err.status, err.error, "the printed kit is accepted at the box itself only", reason="kit_not_at_box")
        b = self._backups(request)
        if b is None:
            raise ApiError(409, "conflict", "no emergency kit has been issued on this box", reason="no_kit")
        try:
            got = b.verify_console_kit(p, kit_key)
        except ApiError as exc:
            self.emit("auth", "step_up.failed", {"attempted": "rescue session", "detail": exc.message[:200], "approval": "kit"}, p,
                      severity="warning")
            raise
        owners = self.active_owner_ids()
        self.emit("auth", "step_up.succeeded", {"attempted": "rescue session", "credential_id": f"kit:{got['fingerprint']}",
                                                "approval": "kit"}, p)
        return {"credential_id": f"kit:{got['fingerprint']}", "user_id": owners[0] if owners else None,
                "verified_at": iso(self.now())}

    def rescue_verify(self, request: Request, p: Principal, credential: dict) -> dict:
        """Single-use, two minutes: the assertion must answer a challenge made by rescue_options and
        come from an active owner's passkey. Audited either way."""
        if not p.is_owner:
            raise self.deny(p, "start a rescue session")
        ctx = ctx_of(request)
        try:
            credential = pk.normalize(credential)
            row = self._consume_challenge(credential, "rescue")
            cred = self._assert(request, credential, row)
            owner = self._live_user(cred.user_id)
            if owner is None or owner.role != "owner":
                raise ApiError(401, "unauthenticated", "passkey does not belong to an active owner")
            if row.user_id is not None and row.user_id != owner.id:
                raise ApiError(401, "unauthenticated", "passkey belongs to another account")
            if ctx is not None and ctx.user is not None and ctx.user.id != owner.id:
                raise ApiError(401, "unauthenticated", "passkey belongs to another account")
        except (ApiError, pk.PasskeyError) as exc:
            why = exc.message if isinstance(exc, ApiError) else str(exc)
            self.emit("auth", "step_up.failed", {"attempted": "rescue session", "detail": why[:200]}, p,
                      severity="warning")
            raise ApiError(401, "unauthenticated", f"passkey check failed: {why}"[:300], reason="step_up_required") from None
        self.emit("auth", "step_up.succeeded", {"attempted": "rescue session", "credential_id": cred.id,
                                                "passkey_user_id": owner.id, "approval": "passkey"}, p)
        return {"credential_id": cred.id, "user_id": owner.id, "verified_at": iso(self.now())}

    # ---- /v1/me ------------------------------------------------------------------------------------
    def me(self, request: Request, p: Principal) -> dict:
        ctx = ctx_of(request)
        principal = p.as_dict()
        token = session = None
        n_passkeys = 0
        profile_name = None
        email, email_verified, totp, setup_pending = None, False, False, False
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
                profile_name = ctx.user.profile_name
                n_passkeys = self.repo.count(PasskeyRow, PasskeyRow.user_id == ctx.user.id)
                if ctx.session is not None:
                    email, totp, setup_pending = ctx.user.email, bool(ctx.user.totp_secret), bool(ctx.user.setup_pending)
                    email_verified = bool(ctx.user.email_verified_at)
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
        return {"principal": principal, "display_name": profile_name, "token": token, "session": session,
                "email": email, "email_verified": email_verified, "totp": totp, "setup_pending": setup_pending,
                "passkeys": n_passkeys,
                "scopes": scopes, "capabilities": caps,
                "step_up": {"passkeys_active": self.passkeys_active(),
                            "require_passkey_approval": self.cfg.require_passkey_approval}}
