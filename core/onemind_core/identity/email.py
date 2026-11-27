# SPDX-License-Identifier: Apache-2.0
"""Prove a contact address through an SMTP channel already configured by an owner."""

from __future__ import annotations

import hmac
import json
import secrets
from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from ..errors import ApiError
from ..notify.channels import DeliveryError, Message, send_channel
from .crypto import new_id, sha256_hex
from .models import ChallengeRow, UserRow, iso

if TYPE_CHECKING:
    from fastapi import Request

    from ..notify.service import NotifyService
    from .service import AuthContext, IdentityService

EMAIL_PURPOSE = "email-verify"


def send_code(svc: IdentityService, notify: NotifyService, ctx: AuthContext | None) -> dict:
    user = svc._account(ctx, "verify a contact email")
    if not user.email:
        raise ApiError(409, "conflict", "save an email address first", reason="email_missing")
    if user.email_verified_at is not None:
        raise ApiError(409, "conflict", "this address is already verified", reason="email_verified")

    # Keep the destination bound to the owner's existing SMTP configuration. A family member can
    # never use the owner's credentials to send to a destination the owner did not configure.
    owners = set(svc.active_owner_ids())
    for channel in notify.repo.list_channels():
        if channel.kind == "email" and channel.person_id in owners and channel.verified:
            config = json.loads(channel.config_json)
            if config["to"].casefold() == user.email.casefold():
                break
    else:
        raise ApiError(409, "conflict", "set up and test an owner SMTP notification channel for this address",
                       reason="smtp_unavailable")

    now = svc.now()
    with notify._cap_lock:
        if not notify.repo.claim_send(user.id, "email_verify", now - timedelta(minutes=15), 3, now, new_id("snd")):
            raise ApiError(429, "rate_limited", "too many verification emails; try again in 15 minutes",
                           reason="email_rate_limited", retry_after_s=900)
    code = f"{secrets.randbelow(1_000_000):06d}"
    row, _ = svc._new_challenge(EMAIL_PURPOSE, user_id=user.id, data={
        "email_hash": sha256_hex(user.email), "code_hash": sha256_hex(code), "session_id": ctx.session.id})
    secret = notify.box.open(channel.secret_enc, channel.id) if channel.secret_enc else None
    msg = Message(row.id, "info", "identity.email.verify", "OneMind email verification",
                  f"Your verification code is {code}. It expires in two minutes.", None, iso(now), notify.box_id)
    try:
        send_channel("email", config, secret, "full", msg, timeout=notify.cfg.http_timeout_s,
                     lan_ok=bool(config.get("lan")), now_s=int(now.timestamp()))
    except (DeliveryError, ValueError):
        svc.repo.delete(ChallengeRow, ChallengeRow.id == row.id)
        raise ApiError(503, "unavailable", "the owner's SMTP channel could not send a verification code",
                       reason="smtp_unavailable") from None
    svc.emit("auth", "email.verification_sent", {"user_id": user.id}, ctx.principal)
    return {"challenge_id": row.id, "expires_at": iso(row.expires_at)}


def verify_code(svc: IdentityService, request: Request, ctx: AuthContext | None, challenge_id: str, code: str) -> None:
    from .service import source_of

    user = svc._account(ctx, "verify a contact email")
    now, source = svc.now(), source_of(request)
    svc.limiter.check(source, now)
    row = svc.repo.one(select(ChallengeRow).where(ChallengeRow.id == challenge_id,
                                                ChallengeRow.purpose == EMAIL_PURPOSE,
                                                ChallengeRow.user_id == user.id))
    if row is None or row.data.get("session_id") != ctx.session.id:
        raise ApiError(401, "unauthenticated", "start a new email verification", reason="email_code_invalid")
    row = svc._claim_challenge(row.challenge, EMAIL_PURPOSE)
    if (not user.email or sha256_hex(user.email) != row.data["email_hash"]
            or not hmac.compare_digest(sha256_hex(code), row.data["code_hash"])):
        svc.limiter.fail(source, now)
        raise ApiError(401, "unauthenticated", "the email code did not match", reason="email_code_invalid")
    if not svc.repo.update(UserRow, [
        UserRow.id == user.id, UserRow.email == user.email, UserRow.credential_revision == user.credential_revision,
    ], {"email_verified_at": now}):
        raise ApiError(409, "conflict", "the account changed; start a new verification")
    svc.emit("auth", "email.verified", {"user_id": user.id}, ctx.principal)
