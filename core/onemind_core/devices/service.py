# SPDX-License-Identifier: Apache-2.0
"""My devices (#715): join everything one device holds for a person, and revoke it in one step.

What a device holds, per credential kind ("source"):

- sessions       live identity sessions (cookie or bearer + refresh token), label = the session's client
- passkeys       WebAuthn credentials, label = the name given at registration
- approver_keys  device-bound P-256 approver keys (#702), when that table exists in this gateway
- push           push registrations (Web Push / UnifiedPush), label = the name the client sent
- mesh, nats     reported as absent: the mesh coordinator is not mounted and there are no
                 per-person NATS accounts yet, so there is nothing of theirs to revoke

There is no shared device id across these tables yet, so a device is the set of a person's
credentials that carry the same label (trimmed, case-folded). The phone sends its device name as
the session's client_name, the push label and the passkey label, so its credentials meet. The
device id is a hash of (person, label): stable while the credentials exist, opaque, and the same
id on every call, which makes Lost this device idempotent: a second call finds nothing and says so.

Lost this device is one person-approved step: a signed-in household session (never an API token,
so never an agent), a fresh passkey once passkeys are on (biometrics on the phone), and never the
device the request comes from or the last owner device or passkey on the box.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select

from ..auth import Principal
from ..errors import ApiError
from ..identity import AuthContext, IdentityService
from ..identity import models as idm
from ..identity.models import PasskeyRow, SessionRow, iso, utc

SOURCES = ("sessions", "passkeys", "approver_keys", "push", "mesh", "nats")


def label_key(label: str | None) -> str:
    key = " ".join((label or "").split()).casefold()
    return key or "unknown"


def device_id(user_id: str, key: str) -> str:
    return "mdv_" + hashlib.sha256(f"{user_id}\0{key}".encode()).hexdigest()[:24]


@dataclass
class Credential:
    source: str
    id: str
    label: str
    created_at: datetime | None
    last_seen_at: datetime | None
    detail: str = ""  # transport for sessions, platform for push, key kind for approver keys

    def json(self) -> dict:
        return {"source": self.source, "id": self.id, "label": self.label, "detail": self.detail,
                "created_at": iso(self.created_at), "last_seen_at": iso(self.last_seen_at)}


@dataclass
class Device:
    id: str
    label: str
    credentials: list[Credential] = field(default_factory=list)
    current: bool = False

    @property
    def kind(self) -> str:
        details = {(c.source, c.detail) for c in self.credentials}
        sources = {c.source for c in self.credentials}
        if ("push", "unifiedpush") in details or "approver_keys" in sources:
            return "phone"
        if ("sessions", "cookie") in details or ("push", "webpush") in details:
            return "browser"
        if ("sessions", "bearer") in details:
            return "app"
        return "unknown"

    def last_seen(self) -> datetime | None:
        seen = [utc(c.last_seen_at or c.created_at) for c in self.credentials if c.last_seen_at or c.created_at]
        return max(seen) if seen else None

    def json(self) -> dict:
        firsts = [utc(c.created_at) for c in self.credentials if c.created_at]
        return {"id": self.id, "label": self.label, "kind": self.kind, "current": self.current,
                "last_seen_at": iso(self.last_seen()), "first_seen_at": iso(min(firsts)) if firsts else None,
                "credentials": [c.json() for c in self.credentials]}


class MyDevicesService:
    def __init__(self, identity: IdentityService, notify=None):
        self.identity = identity
        self.notify = notify  # NotifyService, or None when push is not part of this gateway
        self.repo = identity.repo
        # #702 adds identity_approver_keys; until it is in this gateway the source is absent.
        self.approver_rows = getattr(idm, "ApproverKeyRow", None)

    def sources(self) -> dict[str, bool]:
        return {"sessions": True, "passkeys": True, "approver_keys": self.approver_rows is not None,
                "push": self.notify is not None, "mesh": False, "nats": False}

    # ---- the join ----------------------------------------------------------------------------------
    def _credentials(self, user_id: str) -> list[Credential]:
        now = self.identity.now()
        out: list[Credential] = []
        for s in self.repo.all(select(SessionRow).where(SessionRow.user_id == user_id, SessionRow.revoked_at.is_(None))):
            if self.identity._session_live(s, now):
                out.append(Credential("sessions", s.id, s.client, s.created_at, s.last_seen_at, s.transport))
        for k in self.repo.all(select(PasskeyRow).where(PasskeyRow.user_id == user_id)):
            out.append(Credential("passkeys", k.id, k.label, k.created_at, k.last_used_at))
        if self.approver_rows is not None:
            row = self.approver_rows
            for a in self.repo.all(select(row).where(row.user_id == user_id, row.revoked_at.is_(None))):
                out.append(Credential("approver_keys", a.id, a.label, a.created_at, a.last_used_at, a.key_kind))
        if self.notify is not None:
            for d in self.notify.repo.list_devices(user_id):
                out.append(Credential("push", d.id, d.label, d.created_at, d.last_seen_at, d.platform))
        return out

    def devices(self, user_id: str, current_session: str | None = None) -> list[Device]:
        groups: dict[str, Device] = {}
        for c in self._credentials(user_id):
            key = label_key(c.label)
            dev = groups.setdefault(key, Device(device_id(user_id, key), " ".join(c.label.split()) or "unknown"))
            dev.credentials.append(c)
            if c.source == "sessions" and c.id == current_session:
                dev.current = True
        out = list(groups.values())
        out.sort(key=lambda d: (d.last_seen() is None, -(d.last_seen().timestamp() if d.last_seen() else 0), d.label))
        return out

    # ---- routes ------------------------------------------------------------------------------------
    def _session_person(self, ctx: AuthContext | None, p: Principal, what: str):
        """A household person's own session: never an API token, so never an agent. Refusals are audited."""
        if p.kind != "person" or ctx is None or ctx.user is None or ctx.session is None:
            raise self.identity.deny(p, what, reason="session_required")
        return ctx.user

    def list(self, ctx: AuthContext | None, p: Principal) -> dict:
        user = self._session_person(ctx, p, "list your devices")
        return {"devices": [d.json() for d in self.devices(user.id, ctx.session.id)], "sources": self.sources()}

    def remove(self, ctx: AuthContext | None, p: Principal, dev_id: str) -> dict:
        """Lost this device: revoke every credential the device holds. Idempotent."""
        user = self._session_person(ctx, p, "remove a device")
        how = self.identity.require_step_up(ctx, p, "remove a device")
        found = {d.id: d for d in self.devices(user.id, ctx.session.id)}
        dev = found.get(dev_id)
        revoked = dict.fromkeys(("sessions", "passkeys", "approver_keys", "push"), 0)
        if dev is None:  # already removed (or never this person's): nothing left to revoke
            return {"id": dev_id, "removed": False, "revoked": revoked}
        if dev.current:
            raise ApiError(409, "conflict", "this is the device you are using; sign out here instead",
                           reason="current_device")
        self._last_owner_guard(user, dev)
        now = self.identity.now()
        for c in dev.credentials:
            if c.source == "sessions":
                done = self.repo.update(SessionRow, [SessionRow.id == c.id, SessionRow.revoked_at.is_(None)],
                                        {"revoked_at": now})
            elif c.source == "passkeys":
                self.repo.delete(PasskeyRow, PasskeyRow.id == c.id, PasskeyRow.user_id == user.id)
                done = [c.id]
            elif c.source == "approver_keys":
                row = self.approver_rows
                done = self.repo.update(row, [row.id == c.id, row.revoked_at.is_(None)], {"revoked_at": now})
            else:
                self.notify.repo.delete_device(c.id)
                done = [c.id]
            revoked[c.source] += len(done)
        self.identity.emit("auth", "device.removed", {"user_id": user.id, "device_id": dev.id, "kind": dev.kind,
                                                      "revoked": revoked, "proof": how}, p, severity="warning")
        return {"id": dev.id, "removed": True, "revoked": revoked}

    def _last_owner_guard(self, user, dev: Device) -> None:
        # The owner's last device is always the one they are using, which is refused above; what is
        # left to guard is the box's last owner passkey, which may sit on another device.
        if user.role != "owner":
            return
        mine = {c.id for c in dev.credentials if c.source == "passkeys"}
        if mine:
            owners = self.identity.active_owner_ids()
            left = self.repo.count(PasskeyRow, PasskeyRow.user_id.in_(owners), PasskeyRow.id.not_in(mine))
            if left == 0:
                raise ApiError(409, "conflict", "this device holds the last owner passkey on the box",
                               reason="last_owner")
