# SPDX-License-Identifier: Apache-2.0
"""D-034 first-owner setup and on-box password recovery."""

from __future__ import annotations

import hmac
from typing import TYPE_CHECKING

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from ..errors import ApiError
from .crypto import hash_password, new_id, new_secret, sha256_hex
from .models import ChallengeRow, HouseholdFlagRow, UserRow, iso

if TYPE_CHECKING:
    from fastapi import Request

    from .service import AuthContext, IdentityService

SETUP_PATHS = {
    ("GET", "/v1/instance"),
    ("GET", "/v1/me"),
    ("PATCH", "/v1/me"),
    ("GET", "/v1/auth/setup/status"),
    ("POST", "/v1/auth/setup/kit"),
    ("POST", "/v1/auth/setup/finish"),
    ("POST", "/v1/auth/logout"),
    ("POST", "/v1/auth/totp/setup"),
    ("POST", "/v1/auth/totp/confirm"),
    ("POST", "/v1/auth/email/options"),
    ("POST", "/v1/auth/email/verify"),
    ("POST", "/v1/auth/passkeys/register/options"),
    ("POST", "/v1/auth/passkeys/register"),
}
ALREADY_SET_UP = "this box already has accounts; sign in instead"
MAX_PENDING_SCREEN_CODES = 30


class AccountSetup:
    def __init__(self, service: IdentityService):
        self.svc = service
        self.repo = service.repo

    def status(self) -> dict:
        pending = self.repo.count(UserRow, UserRow.setup_pending.is_(True)) > 0
        return {"state": "pending" if pending else "ready" if self.repo.count(UserRow) else "unclaimed",
                "screen": self.svc.presence.available}

    def _require_home(self, request: Request) -> None:
        if not self.svc.is_home(request):
            self.svc.emit("authz", "denied", {"attempted": request.url.path, "reason": "home_network_required"},
                          severity="warning")
            raise ApiError(403, "permission_denied", "open this page on the box's home network",
                           reason="home_network_required")

    def _options(self, request: Request, purpose: str, label: str, user: UserRow | None = None) -> dict:
        from .service import CHALLENGE_TTL, source_of

        now = self.svc.now()
        self.svc.limiter.check(source_of(request), now)
        if self.repo.count(ChallengeRow, ChallengeRow.purpose == purpose, ChallengeRow.expires_at > now,
                           ChallengeRow.used_at.is_(None)) >= MAX_PENDING_SCREEN_CODES:
            raise ApiError(429, "rate_limited", "too many screen codes requested; try again in two minutes",
                           reason="too_many_pending", retry_after_s=int(CHALLENGE_TTL.total_seconds()))
        box_hash = self.svc.presence.issue(label, now + CHALLENGE_TTL)
        row, _ = self.svc._new_challenge(purpose, user_id=user.id if user else None,
                                         data={"box_sha256": box_hash})
        return {"challenge_id": row.id, "expires_at": iso(row.expires_at)}

    def setup_options(self, request: Request) -> dict:
        self._require_home(request)
        if self.repo.count(UserRow):
            raise ApiError(409, "conflict", ALREADY_SET_UP, reason="already_set_up")
        return self._options(request, "setup", "set up OneMind")

    def _verify_screen(self, challenge_id: str, code: str, purpose: str, label: str) -> ChallengeRow:
        row = self.repo.get(ChallengeRow, challenge_id)
        if row is None:
            raise ApiError(401, "unauthenticated", "ask for a new code on the box", reason="box_code_required")
        row = self.svc._claim_challenge(row.challenge, purpose)
        self.svc.presence.check(row.data["box_sha256"], code, label)
        return row

    def setup(self, request: Request, token: str, challenge_id: str | None, box_code: str | None,
              username: str, display_name: str, password: str, email: str | None) -> UserRow:
        from .service import clean_email, clean_profile_name, source_of

        now, source = self.svc.now(), source_of(request)
        self.svc.limiter.check(source, now)
        self._require_home(request)
        if challenge_id is not None:
            if not box_code:
                raise ApiError(401, "unauthenticated", "type the code on the box", reason="box_code_required")
        # The separate install credential stays available for scripted/headless installs. The same
        # pending account and kit requirement apply whichever proof was used.
        elif not self.svc._setup_token_ok(token):
            self.svc.limiter.fail(source, now)
            self.svc.emit("auth", "setup.rejected", {"source": source, "reason": "bad_setup_token"}, severity="warning")
            raise ApiError(401, "unauthenticated", "setup needs the box code or the install owner token")
        if self.repo.count(UserRow):
            raise ApiError(409, "conflict", ALREADY_SET_UP, reason="already_set_up")
        self.svc._check_password(password)
        user = UserRow(id=new_id("usr"), username=self.svc._new_username(username),
                       display_name=clean_profile_name(display_name), email=clean_email(email), role="owner",
                       password_hash=hash_password(password), setup_pending=True,
                       created_at=now, updated_at=now, created_by="setup")
        if challenge_id is not None:
            self._verify_screen(challenge_id, box_code, "setup", "set up OneMind")
        try:
            # The singleton and user are committed together. A second setup request, even on
            # another worker/process or with a different name and valid proof, cannot add an owner.
            self.repo.add(HouseholdFlagRow(key="first_owner", set_at=now, detail=user.id), user)
        except IntegrityError as exc:
            raise ApiError(409, "conflict", ALREADY_SET_UP, reason="already_set_up") from exc
        self.svc.emit("auth", "setup.started", {"user_id": user.id, "source": source}, self.svc.principal_for(user))
        if self.svc.gw.tokens.has_retiring():
            self.svc.emit("auth", "setup_token.retired", {"user_id": user.id}, self.svc.principal_for(user),
                          severity="warning")
        return user

    def _pending_owner(self, ctx: AuthContext | None) -> UserRow:
        user = self.svc._account(ctx, "finish setting up this box")
        if user.role != "owner" or not user.setup_pending:
            raise ApiError(409, "conflict", "this account has no unfinished setup", reason="setup_not_pending")
        return user

    def kit(self, ctx: AuthContext | None) -> dict:
        user = self._pending_owner(ctx)
        disk_key = None
        path = self.svc.cfg.recovery_key_file
        if path is not None:
            try:
                disk_key = path.read_text().strip() or None
            except FileNotFoundError:
                pass  # plain or already provisioned disk
            except OSError as exc:
                raise ApiError(503, "unavailable", "could not read the disk recovery key",
                               reason="disk_recovery_key_unavailable") from exc
        code = new_secret("recover")
        if not self.repo.update(UserRow, [UserRow.id == user.id, UserRow.setup_pending.is_(True)],
                                {"recovery_hash": sha256_hex(code)}):
            raise ApiError(409, "conflict", "setup already finished", reason="setup_not_pending")
        return {"recovery_code": code, "disk_recovery_key": disk_key}

    def finish(self, ctx: AuthContext | None, saved: bool, method: str, recovery_code: str) -> None:
        user = self._pending_owner(ctx)
        if not saved or not user.recovery_hash or not hmac.compare_digest(user.recovery_hash, sha256_hex(recovery_code)):
            raise ApiError(422, "conflict", "download or print the recovery kit and confirm you saved it",
                           reason="recovery_kit_required")
        if not self.repo.update(UserRow, [UserRow.id == user.id, UserRow.setup_pending.is_(True),
                                          UserRow.recovery_hash == user.recovery_hash], {"setup_pending": False}):
            raise ApiError(409, "conflict", "open and save the latest recovery kit", reason="setup_kit_changed")
        path = self.svc.cfg.recovery_key_file
        if path is not None:
            try:
                with path.open("r+") as key_file:
                    key_file.truncate(0)
            except FileNotFoundError:
                pass
            except OSError:
                self.svc.emit("auth", "setup.disk_key_cleanup_failed", {"user_id": user.id}, severity="warning")
        self.svc.emit("auth", "setup.completed", {"user_id": user.id, "kit_saved_by": method}, ctx.principal)

    def recovery_options(self, request: Request, username: str) -> dict:
        self._require_home(request)
        if not self.repo.count(UserRow):
            raise ApiError(409, "conflict", "set up the box before recovering an account", reason="setup_not_pending")
        user = self.repo.one(select(UserRow).where(UserRow.username == username.strip().lower()))
        return self._options(request, "reset-password", "reset a OneMind password", user)

    def reset(self, request: Request, challenge_id: str, box_code: str, recovery_code: str, password: str) -> dict:
        from .service import source_of

        self._require_home(request)
        now, source = self.svc.now(), source_of(request)
        self.svc.limiter.check(source, now)
        self.svc._check_password(password)
        row = self._verify_screen(challenge_id, box_code, "reset-password", "reset a OneMind password")
        user = self.svc._live_user(row.user_id)
        digest = sha256_hex(recovery_code)
        if user is None or user.setup_pending or not user.recovery_hash or not hmac.compare_digest(
            user.recovery_hash, digest
        ):
            self.svc.limiter.fail(source, now)
            self.svc.emit("auth", "password.reset_failed", {"source": source}, severity="warning")
            raise ApiError(401, "unauthenticated", "the recovery kit code did not match", reason="recovery_code_invalid")
        code = new_secret("recover")
        with self.repo.db.session.begin() as db:
            changed = db.execute(update(UserRow).where(
                UserRow.id == user.id, UserRow.recovery_hash == digest, UserRow.disabled.is_(False),
                UserRow.credential_revision == user.credential_revision,
            ).values(password_hash=hash_password(password), totp_secret=None, totp_pending=None,
                     totp_last_step=None, recovery_hash=sha256_hex(code), updated_at=now,
                     credential_revision=(user.credential_revision or 0) + 1).returning(UserRow.id)).scalar_one_or_none()
            if changed is None:
                raise ApiError(401, "unauthenticated", "the recovery kit code was already used",
                               reason="recovery_code_invalid")
            self.svc.revoke_sessions(db, user.id, now)
        self.svc.emit("auth", "password.reset_at_box", {"user_id": user.id, "sessions_revoked": True},
                      self.svc.principal_for(user), severity="warning")
        return {"recovery_code": code}
