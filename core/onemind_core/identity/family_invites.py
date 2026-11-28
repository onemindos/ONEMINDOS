# SPDX-License-Identifier: Apache-2.0
"""D-034 queued family invitations require a verified owner decision."""

from __future__ import annotations

from datetime import datetime, timedelta
from threading import Lock
from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError

from ..actions import FeatureAction
from ..auth import Principal
from ..errors import ApiError
from ..executors import ExecResult
from . import levels as lv
from .crypto import new_id, sha256_hex
from .service import ctx_of

if TYPE_CHECKING:
    from fastapi import Request

    from .service import AuthContext, IdentityService

INVITE = "users.invite"
REINVITE = "users.reinvite"
CLAIM_TTL = timedelta(minutes=10)


class FamilyInvites:
    def __init__(self, svc: IdentityService):
        self.svc = svc
        self.actions = svc.gw.actions
        self._lock = Lock()
        # action ID -> (expires, user ID, code, approving session ID)
        self._pending: dict[str, tuple[datetime, str, str, str | None]] = {}
        for name in (INVITE, REINVITE):
            self.actions.register_type(name, FeatureAction(lv.FAMILY_INVITE_RISK, self._issue, frozenset(),
                                                           check=self._recheck))
        svc.gw.approval_observers.append(self._bind_claim)

    def request_invite(self, ctx: AuthContext, params: dict, key: str | None) -> dict:
        self.svc._owner_only(ctx.principal, "invite a family member")
        if params["role"] == "owner":
            raise ApiError(422, "conflict", "a family invitation must be for a non-owner role", reason="invalid_role")
        self.svc._role(params["role"])
        return self._file(ctx, INVITE, params, key)

    def request_replacement(self, ctx: AuthContext, user_id: str, key: str | None) -> dict:
        self.svc._owner_only(ctx.principal, "replace a family invitation")
        user = self.svc._live_user(user_id)
        if user is None or user.role == "owner":
            raise ApiError(404, "not_found", "no active family account with that ID")
        return self._file(ctx, REINVITE, {"user_id": user.id, "display_name": user.display_name,
                                        "credential_revision": user.credential_revision}, key)

    def _file(self, ctx: AuthContext, kind: str, params: dict, key: str | None) -> dict:
        action, _ = self.actions.request_feature(ctx.principal, kind, params, idempotency_key=key or new_id("inv"),
                                                 expires_at=self.svc.now() + CLAIM_TTL, pending_cap=True)
        return action

    def _recheck(self, action) -> str | None:
        if action.type == REINVITE:
            user = self.svc._live_user(action.params["user_id"])
            if user is None or user.role == "owner" or user.credential_revision != action.params["credential_revision"]:
                return "the family account changed; request a new replacement invitation"
        return None

    def _issue(self, action, finish) -> None:
        approver = self.actions.repo.get(action.id).approved_by
        p = Principal(id=approver, kind="person", role="owner")
        try:
            if action.type == INVITE:
                user, code = self.svc._create_invited_user(p, **action.params, via="approval")
                user_id = user.id
            else:
                user_id = action.params["user_id"]
                code = self.svc._replace_invite(p, user_id, action.params["credential_revision"])
        except ApiError as exc:
            finish(ExecResult("failed", exc.message))
            return
        except IntegrityError:
            finish(ExecResult("failed", "a family account already uses that sign-in name"))
            return
        now = self.svc.now()
        with self._lock:
            self._pending = {aid: item for aid, item in self._pending.items() if item[0] > now}
            self._pending[action.id] = (now + CLAIM_TTL, user_id, code, None)
        finish(ExecResult("succeeded", "family invitation issued"))

    def _bind_claim(self, request: Request, p: Principal, action: dict) -> None:
        if action.get("type") not in lv.FAMILY_INVITE_ACTIONS or action["state"] != "succeeded":
            return
        ctx = ctx_of(request)
        if not p.is_owner or ctx is None or ctx.session is None:
            return
        with self._lock:
            item = self._pending.get(action["id"])
            if item is not None:
                self._pending[action["id"]] = (*item[:3], ctx.session.id)

    def claim(self, request: Request, ctx: AuthContext, action_id: str) -> dict:
        self.svc._owner_only(ctx.principal, "collect a family invitation")
        with self._lock:
            item = self._pending.get(action_id)
            if item is None or item[0] <= self.svc.now() or item[3] != ctx.session.id:
                raise ApiError(409, "conflict", "no invitation is available to this session",
                               reason="invite_unavailable")
            _, user_id, code, _ = self._pending.pop(action_id)
        user = self.svc._live_user(user_id)
        if user is None or user.role == "owner" or user.enrol_hash != sha256_hex(code):
            raise ApiError(409, "conflict", "the invitation is no longer current", reason="invite_unavailable")
        return self.svc._invite_response(request, user, code, "/")
