# SPDX-License-Identifier: Apache-2.0
"""Recovery contacts: invite, accept, verify (gateway permissions design PR 25d, §3.13, D-028).

An owner names up to 5 people who can later confirm that a locked-out owner is really them (25e).
A contact is a household adult (their own account) or a person outside the household (the OneMind
phone app, no account on the box). What a contact can do is deliberately tiny:

- they hold a P-256 key in their phone (the #702 approver-key machinery) and a 32-byte contact
  secret for the offline code; the box keeps the public key and the sealed secret;
- their bearer token (`omc_`) makes them the principal `contact:<id>`, which reaches the contact
  routes only (`CONTACT_PATHS`); every other route answers 403 and is audited;
- they never see, list or export the owner's data, never approve, never change a setting, never
  become owner. Finishing assisted recovery also requires the owner's current password.
  In Standard mode contacts hold no key material for the owner's data (§3.13).

Adding a contact is a security setting: owner only, from a signed-in session, behind the gateway's
passkey step-up (L1 today; D-028 sets L2 once verification levels land, PR 11). Removing one takes
power away, so it stays at L0. A new contact is usable only after a cooling-off the owner picks
(3, 7 or 14 days; 7 by default, D-028), so someone who briefly gets into the owner's session cannot
plant a contact and use it at once. Every owner and every existing contact is told.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta

from fastapi import Request
from sqlalchemy import delete, select, update

from ..auth import Principal
from ..errors import ApiError
from ..identity import approver_keys as ak
from ..identity.crypto import new_id
from ..identity.service import AuthContext, FailureLimiter, IdentityService, clean_profile_name, source_of
from ..identity.models import UserRow
from ..ledger import iso, utc
from .crypto import BoxKey, InviteError, Sealer, accept_payload, b64, nonce_hash
from .models import ContactRow, NoticeRow, SettingsRow

MAX_CONTACTS = 5  # Apple's number; D-028 "up to 5"
INVITE_TTL = timedelta(days=7)
COOLING_OFF_OPTIONS = (3, 7, 14)  # D-028: the owner picks; 7 by default
# D-028: each wait from set options, defaults in brackets: cooling-off 3, 7, 14 days [7]; the wait after
# a contact confirms 24, 48, 72 hours [24, rising to 72 by itself when a strong key was used recently];
# remote recovery 72 hours or 7 days [72 hours].
DEFAULTS: dict[str, int] = {"cooling_off_days": 7, "contact_wait_hours": 24, "remote_wait_hours": 72}
OPTIONS: dict[str, tuple[int, ...]] = {"cooling_off_days": COOLING_OFF_OPTIONS, "contact_wait_hours": (24, 48, 72),
                                       "remote_wait_hours": (72, 168)}
CONTACT_TOKEN_PREFIX = "omc_"
# Routes a contact principal may reach; anything else is refused at the door. Later PRs add theirs.
CONTACT_PATHS: list[re.Pattern[str]] = [
    re.compile(r"/v1/recovery/contact(/[a-z-]+)?"),
    re.compile(r"/v1/recovery/requests(/rr_[0-9A-Z]{26}/(vouch|cancel))?"),  # 25e: confirm or stop a recovery
]
CONTACT_KINDS = ("household", "outside")
HOUSEHOLD_CONTACT_ROLES = ("adult",)  # never child, teen or guest (§3.13); another owner already has power
LIVE_STATES = ("invited", "active")
NOTICES_KEPT = 200


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class RecoveryContacts:
    """State and rules; the router (routers/recovery.py) is a thin layer over this."""

    role = "recovery"
    principal_kind = "contact"
    noun = "recovery contact"

    def __init__(self, gw, ident: IdentityService):
        self.gw, self.ident = gw, ident
        self.db = gw.db
        base = gw.settings.audit_path.parent / "recovery"
        self.box = BoxKey(base / "invite.key")
        self.sealer = Sealer(base / "secret.key")
        self.limiter = FailureLimiter(10, timedelta(minutes=15))
        # Called after a contact ends (removed or resigned): (contact row). 25e cancels its requests.
        self.ended_hooks: list[Callable[[ContactRow], None]] = []

    # ---- helpers -------------------------------------------------------------------------------------
    def now(self) -> datetime:
        return utc(self.gw.clock())

    def _session_owner(self, ctx: AuthContext | None, what: str) -> UserRow:
        """An owner in a signed-in session (never an API token or a static token)."""
        if ctx is None or ctx.user is None or ctx.session is None:
            p = ctx.principal if ctx else None
            raise self.ident.deny(p, what, reason="session_required")
        if ctx.user.role != "owner":
            raise self.ident.deny(ctx.principal, what, reason="owner_only")
        return ctx.user

    def _rows(self, owner_id: str, *, live_only: bool = False) -> list[ContactRow]:
        q = select(ContactRow).where(ContactRow.owner_user_id == owner_id, ContactRow.role == self.role)
        if live_only:
            q = q.where(ContactRow.state.in_(LIVE_STATES))
        with self.db.session() as s:
            return list(s.scalars(q.order_by(ContactRow.invited_at)))

    def _get(self, contact_id: str) -> ContactRow | None:
        with self.db.session() as s:
            row = s.get(ContactRow, contact_id)
        return row if row is not None and row.role == self.role else None

    def state_of(self, r: ContactRow, now: datetime | None = None) -> str:
        now = now or self.now()
        if r.state == "invited" and utc(r.invite_expires_at) <= now:
            return "expired"
        if r.state == "active" and r.usable_at is not None and utc(r.usable_at) > now:
            return "cooling_off"
        return r.state

    def counts_toward_limit(self, r: ContactRow, now: datetime) -> bool:
        return self.state_of(r, now) in ("invited", "active", "cooling_off")

    def view(self, r: ContactRow) -> dict:
        now = self.now()
        return {
            "id": r.id, "role": r.role, "kind": r.kind, "display_name": r.display_name,
            "household_user_id": r.household_user_id, "state": self.state_of(r, now),
            "invited_at": iso(r.invited_at), "invite_expires_at": iso(r.invite_expires_at),
            "cooling_off_days": r.cooling_off_days, "accepted_at": iso(r.accepted_at), "usable_at": iso(r.usable_at),
            "ended_at": iso(r.ended_at), "device_label": r.device_label, "key_kind": r.key_kind,
            "key_fingerprint": r.key_fingerprint, "last_seen_at": iso(r.last_seen_at),
        }

    def tell(self, owner_id: str, event: str, data: dict, p: Principal | None = None, severity: str = "info",
             audit_only: dict | None = None, delivery_id: str | None = None) -> None:
        """Tell every owner (a notification) and every contact of this owner (their notices feed).
        `audit_only` facts go into the event (and so the audit) but not into the contacts' feed."""
        domain, _, name = event.partition(".")
        if delivery_id is not None:
            with self.db.session() as s:
                if s.get(NoticeRow, delivery_id) is not None:
                    return  # the last delivery finished, but its outbox acknowledgement did not
        delivery = {"dedupe_key": delivery_id, "require_subscribers": True} if delivery_id else {}
        self.gw.events.publish_event(domain, name, {"owner_user_id": owner_id, **data, **(audit_only or {})},
                                     principal=p.as_dict() if p else None, severity=severity, **delivery)
        now = self.now()
        with self.db.session.begin() as s:
            s.add(NoticeRow(id=delivery_id or new_id("rn"), owner_user_id=owner_id, at=now, event=event, data=data))
            old = list(s.scalars(select(NoticeRow.id).where(NoticeRow.owner_user_id == owner_id)
                                 .order_by(NoticeRow.at.desc(), NoticeRow.id.desc()).offset(NOTICES_KEPT)))
            if old:
                s.execute(delete(NoticeRow).where(NoticeRow.id.in_(old)))

    # ---- settings (the owner's waits) ------------------------------------------------------------------
    def settings(self, owner_id: str) -> dict:
        with self.db.session() as s:
            row = s.get(SettingsRow, owner_id)
        return {"values": self._settings_values(row), "defaults": dict(DEFAULTS),
                "options": {k: list(v) for k, v in OPTIONS.items()},
                "updated_at": iso(row.updated_at) if row else None}

    @staticmethod
    def _settings_values(row: SettingsRow | None) -> dict[str, int]:
        return {**DEFAULTS, **{k: v for k, v in (row.values if row else {}).items() if k in DEFAULTS}}

    def set_settings(self, ctx: AuthContext | None, changes: dict[str, int]) -> dict:
        """Each wait from its set options. A shorter wait loosens recovery, so it needs the step-up;
        a longer one only tightens and stays at L0 (D-028)."""
        user = self._session_owner(ctx, "change recovery waits")
        for k, v in changes.items():
            if k not in OPTIONS or v not in OPTIONS[k]:
                raise ApiError(422, "conflict", f"{k} must be one of {list(OPTIONS.get(k, ()))}", reason="not_an_option")
        with self.db.session.begin() as s:
            # Lock a row that exists even when this owner is using the default settings.
            s.execute(update(UserRow).where(UserRow.id == user.id).values(id=UserRow.id))
            row = s.get(SettingsRow, user.id)
            current = self._settings_values(row)
            new = {**current, **changes}
            via = None
            if any(new[k] < current[k] for k in changes):
                via = self.ident.require_fresh_passkey(ctx, ctx.principal, "shorten a recovery wait")
            now = self.now()
            if row is None:
                s.add(SettingsRow(owner_user_id=user.id, values=new, updated_at=now, updated_by=user.id))
            else:
                row.values, row.updated_at, row.updated_by = new, now, user.id
        self.gw.audit.append("recovery.settings.changed", ctx.principal.as_dict(), None,
                             {"owner_user_id": user.id, "was": current, "now": new, "via": via})
        return self.settings(user.id)

    # ---- the owner's side -------------------------------------------------------------------------------
    def list(self, ctx: AuthContext | None) -> list[dict]:
        user = self._session_owner(ctx, f"list {self.noun}s")
        return [self.view(r) for r in self._rows(user.id)]

    def _check_household(self, ctx: AuthContext, owner: UserRow, user_id: str | None) -> UserRow:
        target = self.ident.user(user_id) if user_id else None
        if target is None or target.disabled:
            raise ApiError(422, "conflict", "household_user_id: no such active household account", reason="no_such_person")
        if target.id == owner.id:
            raise ApiError(422, "conflict", f"you cannot be your own {self.noun}", reason="self")
        if target.role not in HOUSEHOLD_CONTACT_ROLES:
            self.ident.emit("authz", "denied", {"attempted": f"add a {self.noun}", "reason": "role_not_allowed",
                                                "target_role": target.role}, ctx.principal, severity="warning")
            raise ApiError(422, "conflict", f"a {self.noun} in the household must be an adult (not a child, teen or guest)",
                           reason="role_not_allowed")
        return target

    def add(self, ctx: AuthContext | None, kind: str, display_name: str, household_user_id: str | None,
            cooling_off_days: int | None, extra: dict | None = None) -> dict:
        owner = self._session_owner(ctx, f"add a {self.noun}")
        via = self.ident.require_step_up(ctx, ctx.principal, f"add a {self.noun}")
        if kind not in CONTACT_KINDS:
            raise ApiError(422, "conflict", "kind must be household or outside")
        days = cooling_off_days if cooling_off_days is not None else self.settings(owner.id)["values"]["cooling_off_days"]
        if days not in COOLING_OFF_OPTIONS:
            raise ApiError(422, "conflict", f"cooling_off_days must be one of {list(COOLING_OFF_OPTIONS)}",
                           reason="not_an_option")
        target = None
        if kind == "household":
            target = self._check_household(ctx, owner, household_user_id)
            name = target.display_name[:60]
        else:
            if household_user_id is not None:
                raise ApiError(422, "conflict", "household_user_id is only for a household contact")
            name = clean_profile_name(display_name or "")
        now = self.now()
        live = [r for r in self._rows(owner.id, live_only=True) if self.counts_toward_limit(r, now)]
        if len(live) >= MAX_CONTACTS:
            raise ApiError(422, "conflict", f"at most {MAX_CONTACTS} {self.noun}s; remove one first", reason="too_many")
        if target is not None and any(r.household_user_id == target.id for r in live):
            raise ApiError(409, "conflict", f"{target.display_name} is already a {self.noun}", reason="already_a_contact")
        cid, nonce = new_id("rc"), secrets.token_urlsafe(16)
        expires = now + INVITE_TTL
        row = ContactRow(id=cid, owner_user_id=owner.id, role=self.role, kind=kind,
                         household_user_id=target.id if target else None, display_name=name, state="invited",
                         invite_nonce_hash=nonce_hash(nonce), invited_at=now, invite_expires_at=expires,
                         cooling_off_days=days, extra=dict(extra or {}))
        with self.db.session.begin() as s:
            s.add(row)
        invite = self.box.sign_invite(invite_id=cid, nonce=nonce, owner=owner.display_name[:100], role=self.role,
                                      expires_at=expires)
        self.tell(owner.id, f"{self.role}.contact.invited", {"contact_id": cid, "kind": kind}, ctx.principal,
                  audit_only={"household_user_id": row.household_user_id, "cooling_off_days": days, "via": via})
        return {**self.view(row), "invite": invite, "box_key_fingerprint": self.box.fingerprint}

    def remove(self, ctx: AuthContext | None, contact_id: str) -> dict:
        """L0: taking power away never needs the step-up (D-028)."""
        owner = self._session_owner(ctx, f"remove a {self.noun}")
        row = self._get(contact_id)
        if row is None or row.owner_user_id != owner.id:
            raise ApiError(404, "not_found", f"no such {self.noun}")
        if row.state not in LIVE_STATES:
            return self.view(row)
        row = self._end(row, "removed")
        self.tell(owner.id, f"{self.role}.contact.removed", {"contact_id": row.id}, ctx.principal)
        return self.view(row)

    def _end(self, row: ContactRow, state: str) -> ContactRow:
        now = self.now()
        with self.db.session.begin() as s:
            s.execute(update(ContactRow).where(ContactRow.id == row.id)
                      .values(state=state, ended_at=now, token_hash=None, sealed_secret=None))
        with self.db.session() as s:
            row = s.get(ContactRow, row.id)
        for hook in self.ended_hooks:
            hook(row)
        return row

    def invitations(self, ctx: AuthContext | None) -> list[dict]:
        """Invites addressed to the signed-in household adult, with the invite text their app accepts."""
        if ctx is None or ctx.user is None:
            raise self.ident.deny(ctx.principal if ctx else None, f"read {self.noun} invitations", reason="person_only")
        now = self.now()
        with self.db.session() as s:
            rows = list(s.scalars(select(ContactRow).where(ContactRow.household_user_id == ctx.user.id,
                                                           ContactRow.role == self.role,
                                                           ContactRow.state == "invited")))
        out = []
        for r in rows:
            if self.state_of(r, now) != "invited":
                continue
            owner = self.ident.user(r.owner_user_id)
            out.append({"id": r.id, "role": r.role, "owner_display_name": owner.display_name if owner else None,
                        "invite_expires_at": iso(r.invite_expires_at), "cooling_off_days": r.cooling_off_days})
        return out

    # ---- the contact's side -----------------------------------------------------------------------------
    def accept(self, request: Request, invite_id: str, invite: str, public_key: str, key_kind: str,
               device_label: str, proof: str) -> dict:
        now, src = self.now(), source_of(request)
        self.limiter.check(src, now)
        try:
            return self._accept(request, now, invite_id, invite, public_key, key_kind, device_label, proof)
        except ApiError as exc:
            if exc.status in (401, 403, 404, 409, 422):
                self.limiter.fail(src, now)
                self.gw.audit.append(f"{self.role}.contact.accept_failed", None, None,
                                     {"invite_id": invite_id[:40], "reason": exc.reason or exc.error, "source": src})
            raise

    def _accept(self, request: Request, now: datetime, invite_id: str, invite: str, public_key: str, key_kind: str,
                device_label: str, proof: str) -> dict:
        try:
            payload = self.box.open_invite(invite)
        except InviteError as exc:
            raise ApiError(422, "conflict", str(exc), reason="invite_invalid") from None
        if payload.get("invite_id") != invite_id or payload.get("role") != self.role:
            raise ApiError(422, "conflict", "this invite is for another contact", reason="invite_invalid")
        row = self._get(invite_id)
        nonce = str(payload.get("nonce") or "")
        if row is None or row.invite_nonce_hash != nonce_hash(nonce):
            raise ApiError(422, "conflict", "unknown invite", reason="invite_invalid")
        if row.state != "invited":
            raise ApiError(409, "conflict", "this invite was already used or withdrawn", reason="invite_used")
        if utc(row.invite_expires_at) <= now:
            raise ApiError(409, "expired", "this invite expired; ask for a new one", reason="invite_expired")
        if row.kind == "household":
            # A household invite is accepted by that adult, from their own session.
            p = self.gw.principal(request)
            if p.kind != "person" or p.id != row.household_user_id:
                raise self.ident.deny(p, f"accept a {self.noun} invite addressed to someone else",
                                      reason="not_the_invitee")
        if key_kind not in ("hardware-reported", "software"):
            raise ApiError(422, "conflict", "key_kind must be hardware-reported or software (attestation is not verified yet)",
                           reason="attestation_unverified")
        try:
            der, fingerprint = ak.parse_public_key(public_key)
            ak.verify(der, accept_payload(invite_id, nonce, fingerprint), proof)
        except ak.ApproverKeyError as exc:
            raise ApiError(422, "conflict", str(exc), reason="proof_invalid") from None
        label = " ".join((device_label or "").split())[:100] or "phone"
        secret, token = secrets.token_bytes(32), CONTACT_TOKEN_PREFIX + secrets.token_urlsafe(32)
        usable = now + timedelta(days=row.cooling_off_days)
        with self.db.session.begin() as s:
            if s.scalar(select(ContactRow.id).where(ContactRow.key_fingerprint == fingerprint)) is not None:
                raise ApiError(409, "conflict", "this key is already a contact key; make a new one", reason="key_taken")
            done = s.execute(update(ContactRow).where(ContactRow.id == row.id, ContactRow.state == "invited").values(
                state="active", accepted_at=now, usable_at=usable, device_label=label, key_kind=key_kind,
                public_key=der, key_fingerprint=fingerprint, sealed_secret=self.sealer.seal(secret, row.id),
                token_hash=token_hash(token), last_seen_at=now)).rowcount
            if done != 1:
                raise ApiError(409, "conflict", "this invite was already used or withdrawn", reason="invite_used")
        self.tell(row.owner_user_id, f"{self.role}.contact.accepted",
                  {"contact_id": row.id, "usable_at": iso(usable)}, Principal(f"{self.principal_kind}:{row.id}",
                                                                              self.principal_kind, self.principal_kind))
        owner = self.ident.user(row.owner_user_id)
        return {
            "contact_id": row.id, "role": self.role, "owner_display_name": owner.display_name if owner else None,
            "usable_at": iso(usable), "box_key_fingerprint": self.box.fingerprint,
            "one_time": {"contact_token": token, "contact_secret": b64(secret)},
        }

    def allowed_path(self, path: str) -> bool:
        return any(rx.fullmatch(path) for rx in CONTACT_PATHS)

    def authenticate(self, request: Request, token: str | None) -> Principal | None:
        """The gateway's Authenticator hook for `omc_` tokens. A contact reaches only its own routes."""
        if not token or not token.startswith(CONTACT_TOKEN_PREFIX):
            return None
        with self.db.session() as s:
            row = s.scalar(select(ContactRow).where(ContactRow.token_hash == token_hash(token)))
        if row is None or row.state != "active":
            return None
        kind = "contact" if row.role == "recovery" else row.role
        p = Principal(id=f"{kind}:{row.id}", kind=kind, role=kind)
        if not self.path_allowed_for(row, request.url.path):
            self.gw.audit.append("authz.denied", p.as_dict(), None,
                                 {"attempted": f"{request.method} {request.url.path}", "reason": "contact_policy"})
            raise ApiError(403, "permission_denied", f"a {kind} principal reaches only its own recovery routes",
                           reason="contact_policy")
        now = self.now()
        if row.last_seen_at is None or now - utc(row.last_seen_at) >= timedelta(minutes=1):
            with self.db.session.begin() as s:
                s.execute(update(ContactRow).where(ContactRow.id == row.id).values(last_seen_at=now))
        request.state.recovery_contact = row
        return p

    def path_allowed_for(self, row: ContactRow, path: str) -> bool:
        """Overridden per role in a later PR (legacy contacts reach the legacy routes instead)."""
        return row.role == "recovery" and self.allowed_path(path)

    def contact_row(self, request: Request, p: Principal) -> ContactRow:
        row = getattr(request.state, "recovery_contact", None)
        if row is None or p.kind != self.principal_kind or p.id != f"{self.principal_kind}:{row.id}":
            raise self.ident.deny(p, f"use the {self.noun} routes", reason="contact_only")
        return row

    def contact_view(self, row: ContactRow) -> dict:
        owner = self.ident.user(row.owner_user_id)
        return {"contact_id": row.id, "role": row.role, "state": self.state_of(row),
                "owner_display_name": owner.display_name if owner else None, "accepted_at": iso(row.accepted_at),
                "usable_at": iso(row.usable_at), "box_key_fingerprint": self.box.fingerprint}

    def resign(self, row: ContactRow, p: Principal) -> dict:
        row = self._end(row, "resigned")
        self.tell(row.owner_user_id, f"{self.role}.contact.resigned", {"contact_id": row.id}, p)
        return self.contact_view(row)

    def notices(self, row: ContactRow, limit: int = 50) -> list[dict]:
        """What this contact is told about the owner's recovery setup since they accepted."""
        since = utc(row.accepted_at) if row.accepted_at else self.now()
        with self.db.session() as s:
            rows = list(s.scalars(select(NoticeRow).where(NoticeRow.owner_user_id == row.owner_user_id,
                                                          NoticeRow.at >= since)
                                  .order_by(NoticeRow.at.desc(), NoticeRow.id.desc()).limit(limit)))
        return [{"id": n.id, "at": iso(n.at), "event": n.event, "data": n.data} for n in rows]

    # ---- for recovery (25e) ---------------------------------------------------------------------------
    def usable(self, owner_id: str) -> list[ContactRow]:
        """Active contacts of this owner past their cooling-off."""
        now = self.now()
        return [r for r in self._rows(owner_id, live_only=True) if self.state_of(r, now) == "active"]

    def secret_of(self, row: ContactRow) -> bytes:
        if row.sealed_secret is None:
            raise ValueError("this contact holds no secret")
        return self.sealer.open(row.sealed_secret, row.id)
