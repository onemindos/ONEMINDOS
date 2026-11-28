# SPDX-License-Identifier: Apache-2.0
"""D-028/D-034 delayed recovery of remote approval capability."""

from __future__ import annotations

import hmac
from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, exists, or_, select
from sqlalchemy.exc import IntegrityError

from ..errors import ApiError
from .crypto import new_id, new_secret, sha256_hex
from .models import RemoteRecoveryRow, UserRow, iso, utc

if TYPE_CHECKING:
    from fastapi import Request

    from .service import AuthContext, IdentityService

WAIT = timedelta(hours=72)
REDEMPTION_WINDOW = timedelta(days=7)


def _owner(svc: IdentityService, ctx: AuthContext | None, fresh: bool = False):
    user = svc._account(ctx, "recover remote approvals")
    svc._owner_only(ctx.principal, "recover remote approvals")
    if fresh and not svc._fresh_l1(ctx):
        raise ApiError(401, "unauthenticated", "sign in again with your authenticator or passkey",
                       reason="step_up_required")
    return user


def _live(svc: IdentityService, user) -> RemoteRecoveryRow | None:
    row = svc.repo.get(RemoteRecoveryRow, user.id)
    if row is not None and row.credential_revision == user.credential_revision and utc(row.expires_at) > svc.now():
        return row
    return None


def status(svc: IdentityService, ctx: AuthContext | None) -> dict:
    user = _owner(svc, ctx)
    row = _live(svc, user)
    upgrade_kit_available = ctx.home and not svc.presence.available and not user.setup_pending and not user.recovery_hash
    if row is None:
        return {"state": "none", "available_at": None, "expires_at": None,
                "upgrade_kit_available": upgrade_kit_available}
    return {"state": "ready" if svc.now() >= utc(row.available_at) else "waiting",
            "available_at": iso(row.available_at), "expires_at": iso(row.expires_at),
            "upgrade_kit_available": False}


def upgrade_kit(svc: IdentityService, ctx: AuthContext) -> dict:
    """An existing headless owner may initialise the code that gates delayed recovery."""
    user = _owner(svc, ctx, fresh=True)
    if not ctx.home:
        raise svc.deny(ctx.principal, "issue an upgrade recovery kit", reason="home_network_required")
    code = new_secret("recover")
    if svc.presence.available or user.setup_pending or not svc.repo.update(UserRow, [
        UserRow.id == user.id, UserRow.role == "owner", UserRow.disabled.is_(False),
        UserRow.setup_pending.is_not(True), UserRow.credential_revision == user.credential_revision,
        UserRow.recovery_hash.is_(None),
    ], {"recovery_hash": sha256_hex(code)}):
        raise ApiError(409, "conflict", "this account cannot issue an upgrade kit", reason="upgrade_kit_unavailable")
    svc.emit("auth", "remote_recovery.upgrade_kit_issued", {"user_id": user.id}, ctx.principal, severity="warning")
    return {"recovery_code": code, "disk_recovery_key": None}


def start(svc: IdentityService, request: Request, ctx: AuthContext | None, kit_code: str) -> dict:
    from .service import source_of

    user = _owner(svc, ctx, fresh=True)
    now, source = svc.now(), source_of(request)
    key = f"account:{user.username}"
    for limit in (source, key):
        svc.limiter.check(limit, now)
    if not user.recovery_hash or not hmac.compare_digest(sha256_hex(kit_code), user.recovery_hash):
        for limit in (source, key):
            svc.limiter.fail(limit, now)
        raise ApiError(401, "unauthenticated", "the recovery kit code did not match", reason="recovery_code_invalid")
    if _live(svc, user) is not None:
        return status(svc, ctx)
    # An old request cannot survive a password/TOTP reset or the end of its redemption window.
    ready_at = now + WAIT
    try:
        with svc.repo.db.session.begin() as db:
            db.execute(delete(RemoteRecoveryRow).where(
                RemoteRecoveryRow.user_id == user.id, or_(
                    RemoteRecoveryRow.expires_at <= now,
                    RemoteRecoveryRow.credential_revision.is_distinct_from(user.credential_revision),
                ),
            ))
            db.add(RemoteRecoveryRow(user_id=user.id, request_id=new_id("rec"),
                                     credential_revision=user.credential_revision, available_at=ready_at,
                                     expires_at=ready_at + REDEMPTION_WINDOW))
    except IntegrityError:
        return status(svc, ctx)
    svc.emit("auth", "remote_recovery.started", {"user_id": user.id, "available_at": iso(ready_at)},
             ctx.principal, severity="critical")
    return status(svc, ctx)


def cancel(svc: IdentityService, ctx: AuthContext | None) -> None:
    user = _owner(svc, ctx)
    svc.repo.delete(RemoteRecoveryRow, RemoteRecoveryRow.user_id == user.id)
    svc.emit("auth", "remote_recovery.cancelled", {"user_id": user.id}, ctx.principal, severity="warning")


def registration_id(svc: IdentityService, ctx: AuthContext | None) -> str:
    row = _live(svc, _owner(svc, ctx, fresh=True))
    if row is None or svc.now() < utc(row.available_at):
        raise ApiError(409, "conflict", "remote approval recovery is available after a 72-hour wait",
                       reason="remote_recovery_wait")
    return row.request_id


def consume(svc: IdentityService, db, ctx: AuthContext, request_id: str) -> None:
    if registration_id(svc, ctx) != request_id:
        raise ApiError(409, "conflict", "the recovery request changed; start again", reason="remote_recovery_changed")
    claimed = db.execute(delete(RemoteRecoveryRow).where(
        RemoteRecoveryRow.user_id == ctx.user.id, RemoteRecoveryRow.request_id == request_id,
        RemoteRecoveryRow.credential_revision == ctx.user.credential_revision,
        RemoteRecoveryRow.available_at <= svc.now(), RemoteRecoveryRow.expires_at > svc.now(),
        exists(select(UserRow.id).where(UserRow.id == ctx.user.id, UserRow.disabled.is_(False),
                                        UserRow.role == "owner", UserRow.credential_revision == ctx.user.credential_revision)),
    ).returning(RemoteRecoveryRow.request_id)).scalar_one_or_none()
    if claimed is None:
        raise ApiError(409, "conflict", "the recovery request changed; start again", reason="remote_recovery_changed")
