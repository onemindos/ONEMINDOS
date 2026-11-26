# SPDX-License-Identifier: Apache-2.0
"""Contact-assisted recovery and the remote wait (gateway permissions design PR 25e, §3.13, D-028).

A locked-out owner starts a recovery from the sign-in page (or `onemind recovery start`). Two paths:

**Path 3, a recovery contact.** The box makes a request with a 15-minute **request code** (two words
and 4 digits) and a 2-digit **matching number**, both shown only to the person who started it. Then
one of the owner's contacts confirms, in one of three ways, all bound to this one request:
- *A, online:* the contact's app sees the request, the contact picks the number that matches the
  owner's screen out of three (so "approve whatever pops up" fails), and signs with their contact key;
- *B, a code read over the phone:* the owner reads the request code to the contact; the contact's app
  shows an 8-digit code = HMAC(contact secret, request id and request code), which the owner types.
  It needs no network path between the contact and the box (works for iPhone-only households, D-021);
- *C, in person:* the contact does A or B standing beside the owner.
Each request allows 3 wrong tries, expires in 15 minutes, and an owner can start at most one contact
request a day. A contact can never start a request.

**Path 4, remote, with a wait.** No contact or kit: a password **and** the authenticator code (or a
passkey the owner still has) start it. A password alone never does.

**The wait.** After a contact confirms: 24, 48 or 72 hours as the owner chose (24 by default), raised
to 72 by itself when a strong key of the owner was used in the last 7 days, because a live account
being "recovered" is more likely an attack (Apple's liveness idea). The remote path waits 72 hours or
7 days (72 by default). Nobody can shorten a running wait. During it every owner and every contact is
told at the start, every 24 hours and 1 hour before the end, and any owner session, any contact or
the person who started it can cancel (L0). Data access carries on throughout.

**The end.** After the wait, the person who started it enrols a new passkey (and, on the contact
path, may set a new password), then gets a normal session. Recovery approves nothing, deletes
nothing and never touches the disk key or a backup key: there is no such step in this module.
"""

from __future__ import annotations

import hashlib
import hmac
import random
import secrets
from datetime import datetime, timedelta

from fastapi import Request
from sqlalchemy import DateTime, Integer, String, select, update
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..auth import Principal
from ..errors import ApiError
from ..identity import approver_keys as ak
from ..identity import passkeys as pk
from ..identity.crypto import PASSWORD_MAX, PASSWORD_MIN, hash_password, new_id
from ..identity.models import ApproverKeyRow, PasskeyRow, SessionRow, UserRow, iso
from ..ledger import Base, utc
from .contacts import RecoveryContacts, token_hash
from .crypto import b64
from .models import ContactRow

TS = DateTime(timezone=True)
VOUCH_TTL = timedelta(minutes=15)
MAX_TRIES = 3
CONTACT_REQUESTS_PER_DAY = 1
LIVENESS_WINDOW = timedelta(days=7)
LIVENESS_WAIT_HOURS = 72
REQUEST_TOKEN_PREFIX = "omr_"
VOUCH_TAG = "onemind-recovery-vouch-v1"
CHALLENGE_PURPOSE = "recovery-reg"
OPEN_STATES = ("awaiting_contact", "waiting")
# Short, common, unambiguous words for the request code read aloud over the phone.
WORDS = ("amber", "apple", "basil", "birch", "cedar", "cloud", "coral", "delta", "ember", "fable", "fern",
         "frost", "grape", "harbor", "hazel", "iris", "jade", "lemon", "lilac", "maple", "meadow", "mint",
         "ocean", "olive", "orbit", "pearl", "pine", "plum", "quartz", "raven", "river", "robin", "sage",
         "silver", "spruce", "stone", "sunny", "tiger", "tulip", "velvet", "willow", "zephyr")


class RequestRow(Base):
    """Feature "recovery": a new table, so create_all adds it at this shape."""

    __tablename__ = "recovery_requests"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # rr_<ulid>
    owner_user_id: Mapped[str] = mapped_column(String(40), index=True)
    path: Mapped[str] = mapped_column(String(16))  # contact | remote
    # awaiting_contact -> waiting -> completed; or cancelled | expired | failed (never deletes anything)
    state: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(TS)
    vouch_expires_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    request_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    matching_number: Mapped[str | None] = mapped_column(String(2), nullable=True)
    vouch_challenge: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tries: Mapped[int] = mapped_column(Integer, default=0)
    vouched_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    vouched_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    vouch_method: Mapped[str | None] = mapped_column(String(16), nullable=True)  # online | code
    wait_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    liveness_raised: Mapped[bool] = mapped_column(default=False)
    not_before: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    starter_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    source: Mapped[str] = mapped_column(String(80))
    ended_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    end_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ended_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    notices_sent: Mapped[list] = mapped_column(JSON, default=list)


def code_for(secret: bytes, request_id: str, request_code: str) -> str:
    """The 8-digit code the contact's app shows: HMAC-SHA256(contact secret, id and code), truncated."""
    mac = hmac.new(secret, f"{request_id}\n{request_code}".encode(), hashlib.sha256).digest()
    return f"{int.from_bytes(mac[:8], 'big') % 10**8:08d}"


def vouch_payload(request_id: str, picked: str, challenge: str) -> bytes:
    return "\n".join((VOUCH_TAG, request_id, picked, challenge)).encode()


class Recoveries:
    """Start, confirm, wait, cancel and finish a recovery."""

    def __init__(self, contacts: RecoveryContacts):
        self.contacts = contacts
        self.gw, self.ident, self.db = contacts.gw, contacts.ident, contacts.db
        contacts.ended_hooks.append(self._contact_ended)

    def now(self) -> datetime:
        return utc(self.gw.clock())

    # ---- helpers -------------------------------------------------------------------------------------
    def _get(self, request_id: str) -> RequestRow | None:
        with self.db.session() as s:
            return s.get(RequestRow, request_id)

    def _set(self, row: RequestRow, **values) -> RequestRow:
        with self.db.session.begin() as s:
            s.execute(update(RequestRow).where(RequestRow.id == row.id).values(**values))
        return self._get(row.id)

    def _end(self, row: RequestRow, state: str, reason: str, by: str | None) -> RequestRow:
        row = self._set(row, state=state, ended_at=self.now(), end_reason=reason, ended_by=by)
        severity = "warning" if state == "cancelled" else "info"
        self.contacts.tell(row.owner_user_id, f"recovery.request.{state}",
                           {"request_id": row.id, "path": row.path, "reason": reason}, severity=severity)
        return row

    def _fresh(self, row: RequestRow | None) -> RequestRow | None:
        """Lazily close a request whose 15 minutes for a contact passed."""
        if row is not None and row.state == "awaiting_contact" and row.vouch_expires_at is not None \
                and utc(row.vouch_expires_at) <= self.now():
            row = self._end(row, "expired", "no_contact_in_time", None)
        return row

    def view(self, row: RequestRow, *, starter: bool) -> dict:
        out = {
            "id": row.id, "path": row.path, "state": row.state, "created_at": iso(row.created_at),
            "vouch_expires_at": iso(row.vouch_expires_at), "vouched_at": iso(row.vouched_at),
            "vouch_method": row.vouch_method, "wait_hours": row.wait_hours, "liveness_raised": row.liveness_raised,
            "not_before": iso(row.not_before), "ended_at": iso(row.ended_at), "end_reason": row.end_reason,
            "source": row.source,
        }
        if starter:  # only the person at the sign-in page sees what to read out and to match
            out |= {"matching_number": row.matching_number, "request_code": row.request_code}
        return out

    def settings(self, owner_id: str) -> dict:
        return self.contacts.settings(owner_id)["values"]

    def _owner_by_name(self, username: str) -> UserRow | None:
        u = self.ident.repo.one(select(UserRow).where(UserRow.username == (username or "").strip().lower()))
        return u if u is not None and not u.disabled and u.role == "owner" else None

    def _starter(self, request: Request, request_id: str) -> RequestRow:
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        token = token.strip()
        row = self._fresh(self._get(request_id))
        if scheme.lower() != "bearer" or not token.startswith(REQUEST_TOKEN_PREFIX) or row is None \
                or not hmac.compare_digest(row.starter_token_hash, token_hash(token)):
            raise ApiError(401, "unauthenticated", "this needs the recovery request's own token", reason="request_token")
        return row

    # ---- start ---------------------------------------------------------------------------------------
    def start(self, request: Request, path: str, username: str, password: str | None, totp: str | None,
              passkey: dict | None) -> dict:
        now, src = self.now(), self.ident.limiter
        if path == "contact":
            src.check(f"recovery:{request.client.host if request.client else 'unknown'}", now)
            owner = self._owner_by_name(username)
            if owner is None or not self.contacts.usable(owner.id):
                # One answer for "no such owner" and "no usable contact", so this is not an account oracle.
                src.fail(f"recovery:{request.client.host if request.client else 'unknown'}", now)
                raise ApiError(409, "conflict", "recovery with a contact is not available for this account yet",
                               reason="no_usable_contact")
            with self.db.session() as s:
                recent = s.scalar(select(RequestRow.created_at).where(
                    RequestRow.owner_user_id == owner.id, RequestRow.path == "contact",
                    RequestRow.created_at > now - timedelta(days=1)).order_by(RequestRow.created_at.desc()))
            if recent is not None:
                wait = int((utc(recent) + timedelta(days=1) - now).total_seconds()) + 1
                raise ApiError(429, "rate_limited", "one recovery with a contact a day; try again later",
                               reason="one_a_day", retry_after_s=wait)
            rng = secrets.SystemRandom()
            code = f"{rng.choice(WORDS)}-{rng.choice(WORDS)}-{rng.randrange(10000):04d}"
            values = dict(path="contact", state="awaiting_contact", vouch_expires_at=now + VOUCH_TTL,
                          request_code=code, matching_number=f"{rng.randrange(100):02d}",
                          vouch_challenge=b64(secrets.token_bytes(24)))
        elif path == "remote":
            if passkey is not None:
                owner = self.ident.login_passkey(request, passkey)
            else:
                owner = self.ident.login_password(request, username, password or "", totp)
                if not owner.totp_secret:
                    # D-028 / §3.13: a password alone never starts a recovery, even with a wait.
                    raise ApiError(401, "unauthenticated", "a password alone cannot start a remote recovery; "
                                   "use your authenticator code or a passkey you still have",
                                   reason="second_factor_required")
            if owner.role != "owner" or owner.disabled:
                raise ApiError(409, "conflict", "remote recovery is for owners", reason="owner_only")
            hours = self.settings(owner.id)["remote_wait_hours"]
            values = dict(path="remote", state="waiting", wait_hours=hours, not_before=now + timedelta(hours=hours))
        else:
            raise ApiError(422, "conflict", "path must be contact or remote")
        with self.db.session() as s:
            open_ = s.scalar(select(RequestRow.id).where(RequestRow.owner_user_id == owner.id,
                                                         RequestRow.state.in_(OPEN_STATES)))
        if open_ is not None and self._fresh(self._get(open_)).state in OPEN_STATES:
            raise ApiError(409, "conflict", "a recovery is already running for this account; cancel it first",
                           reason="already_running")
        token = REQUEST_TOKEN_PREFIX + secrets.token_urlsafe(32)
        row = RequestRow(id=new_id("rr"), owner_user_id=owner.id, created_at=now, starter_token_hash=token_hash(token),
                         source=(request.client.host if request.client else "unknown")[:80], tries=0,
                         liveness_raised=False, notices_sent=["start"], **values)
        with self.db.session.begin() as s:
            s.add(row)
        self.contacts.tell(owner.id, "recovery.request.started", {"request_id": row.id, "path": row.path},
                           severity="warning", audit_only={"source": row.source})
        return {**self.view(row, starter=True), "one_time": {"request_token": token}}

    # ---- confirm -------------------------------------------------------------------------------------
    def _usable_contact(self, row: ContactRow) -> None:
        if self.contacts.state_of(row) != "active":
            raise ApiError(409, "conflict", "you cannot confirm a recovery yet: the owner's cooling-off is still running",
                           reason="cooling_off")

    def choices(self, request_id: str, contact_id: str, matching: str) -> list[str]:
        """Three numbers for this contact, one of them the owner's; the same on every poll."""
        rng = random.Random(f"{request_id}:{contact_id}")  # noqa: S311 - decoys, not a secret
        decoys: set[str] = set()
        while len(decoys) < 2:
            n = f"{rng.randrange(100):02d}"
            if n != matching:
                decoys.add(n)
        out = [matching, *sorted(decoys)]
        rng.shuffle(out)
        return out

    def pending_for(self, contact: ContactRow) -> list[dict]:
        """What a contact's app shows: requests of their owner waiting for a contact."""
        self._usable_contact(contact)
        with self.db.session() as s:
            rows = list(s.scalars(select(RequestRow).where(RequestRow.owner_user_id == contact.owner_user_id,
                                                           RequestRow.state.in_(OPEN_STATES))))
        owner = self.ident.user(contact.owner_user_id)
        out = []
        for r in rows:
            r = self._fresh(r)
            if r.state != "awaiting_contact":
                out.append({"id": r.id, "state": r.state, "owner_display_name": owner.display_name if owner else None,
                            "created_at": iso(r.created_at), "not_before": iso(r.not_before)})
                continue
            out.append({"id": r.id, "state": r.state, "owner_display_name": owner.display_name if owner else None,
                        "created_at": iso(r.created_at), "source": r.source, "expires_at": iso(r.vouch_expires_at),
                        "choices": self.choices(r.id, contact.id, r.matching_number or ""),
                        "challenge": r.vouch_challenge})
        return out

    def _one_try(self, row: RequestRow, what: str) -> ApiError:
        tries = row.tries + 1
        row = self._set(row, tries=tries)
        if tries >= MAX_TRIES:
            self._end(row, "failed", "too_many_tries", None)
            return ApiError(409, "conflict", f"{what}; this request is closed after {MAX_TRIES} tries", reason="request_closed")
        return ApiError(422, "conflict", f"{what}; {MAX_TRIES - tries} tries left", reason="wrong_answer")

    def _open_for_vouch(self, request_id: str, owner_id: str) -> RequestRow:
        row = self._fresh(self._get(request_id))
        if row is None or row.owner_user_id != owner_id:
            raise ApiError(404, "not_found", "no such recovery request")
        if row.state != "awaiting_contact":
            raise ApiError(409, "conflict", f"this request is {row.state}", reason=row.state)
        return row

    def vouch_online(self, contact: ContactRow, p: Principal, request_id: str, picked: str, signature: str) -> dict:
        self._usable_contact(contact)
        row = self._open_for_vouch(request_id, contact.owner_user_id)
        try:
            ak.verify(contact.public_key or b"", vouch_payload(row.id, picked, row.vouch_challenge or ""), signature)
        except ak.ApproverKeyError:
            raise ApiError(401, "unauthenticated", "the contact key's signature does not verify",
                           reason="signature_invalid") from None
        if not hmac.compare_digest(picked, row.matching_number or ""):
            self.gw.audit.append("recovery.request.wrong_number", p.as_dict(), None, {"request_id": row.id})
            raise self._one_try(row, "that is not the number on the owner's screen")
        return self._vouched(row, contact, "online", p)

    def vouch_code(self, request: Request, request_id: str, code: str) -> dict:
        row = self._starter(request, request_id)
        if row.state != "awaiting_contact":
            raise ApiError(409, "conflict", f"this request is {row.state}", reason=row.state)
        code = "".join(ch for ch in (code or "") if ch.isdigit())
        for contact in self.contacts.usable(row.owner_user_id):
            try:
                want = code_for(self.contacts.secret_of(contact), row.id, row.request_code or "")
            except ValueError:
                continue
            if len(code) == 8 and hmac.compare_digest(code, want):
                p = Principal(f"contact:{contact.id}", "contact", "contact")
                return self._vouched(row, contact, "code", p)
        raise self._one_try(row, "that code does not match")

    def _liveness(self, owner_id: str, now: datetime) -> bool:
        since = now - LIVENESS_WINDOW
        with self.db.session() as s:
            pk_used = s.scalar(select(PasskeyRow.id).where(PasskeyRow.user_id == owner_id,
                                                           PasskeyRow.last_used_at > since))
            ak_used = s.scalar(select(ApproverKeyRow.id).where(ApproverKeyRow.user_id == owner_id,
                                                               ApproverKeyRow.last_used_at > since))
        return pk_used is not None or ak_used is not None

    def _vouched(self, row: RequestRow, contact: ContactRow, method: str, p: Principal) -> dict:
        now = self.now()
        hours = self.settings(row.owner_user_id)["contact_wait_hours"]
        raised = hours < LIVENESS_WAIT_HOURS and self._liveness(row.owner_user_id, now)
        if raised:
            hours = LIVENESS_WAIT_HOURS
        with self.db.session.begin() as s:
            done = s.execute(update(RequestRow).where(RequestRow.id == row.id, RequestRow.state == "awaiting_contact")
                             .values(state="waiting", vouched_by=contact.id, vouched_at=now, vouch_method=method,
                                     wait_hours=hours, liveness_raised=raised, not_before=now + timedelta(hours=hours),
                                     notices_sent=["start", "vouched"])).rowcount
        if done != 1:
            raise ApiError(409, "conflict", "this request is no longer waiting for a contact", reason="not_awaiting")
        row = self._get(row.id)
        self.contacts.tell(row.owner_user_id, "recovery.request.vouched",
                           {"request_id": row.id, "contact_id": contact.id, "method": method, "wait_hours": hours,
                            "not_before": iso(row.not_before)}, p, severity="warning")
        return self.view(row, starter=False)

    # ---- cancel --------------------------------------------------------------------------------------
    def cancel_by_starter(self, request: Request, request_id: str) -> dict:
        row = self._starter(request, request_id)
        return self._cancel(row, "starter")

    def cancel_by_owner(self, p: Principal, request_id: str) -> dict:
        """Any owner (an approver) may stop any recovery on the box, from any session: L0."""
        if not p.is_owner:
            raise self.ident.deny(p, "cancel a recovery", reason="owner_only")
        row = self._fresh(self._get(request_id))
        if row is None:
            raise ApiError(404, "not_found", "no such recovery request")
        return self._cancel(row, p.id)

    def cancel_by_contact(self, contact: ContactRow, p: Principal, request_id: str) -> dict:
        row = self._fresh(self._get(request_id))
        if row is None or row.owner_user_id != contact.owner_user_id:
            raise ApiError(404, "not_found", "no such recovery request")
        return self._cancel(row, p.id)

    def _cancel(self, row: RequestRow, by: str) -> dict:
        if row.state not in OPEN_STATES:
            return self.view(row, starter=False)
        return self.view(self._end(row, "cancelled", "cancelled", by), starter=False)

    def _contact_ended(self, contact: ContactRow) -> None:
        """A contact removed or resigned during the wait they started: stop that recovery."""
        with self.db.session() as s:
            rows = list(s.scalars(select(RequestRow).where(RequestRow.vouched_by == contact.id,
                                                           RequestRow.state == "waiting")))
        for r in rows:
            self._end(r, "cancelled", "contact_ended", f"contact:{contact.id}")

    # ---- lists ---------------------------------------------------------------------------------------
    def for_owner(self, p: Principal, ctx) -> list[dict]:
        """Every open recovery on the box, for an owner's banner ("Is this you?"). No codes."""
        if not p.is_owner:
            raise self.ident.deny(p, "list recoveries", reason="owner_only")
        with self.db.session() as s:
            rows = list(s.scalars(select(RequestRow).where(RequestRow.state.in_(OPEN_STATES))
                                  .order_by(RequestRow.created_at.desc())))
        return [self.view(r, starter=False) for r in (self._fresh(r) for r in rows) if r.state in OPEN_STATES]

    def status(self, request: Request, request_id: str) -> dict:
        return self.view(self._starter(request, request_id), starter=True)

    # ---- finish --------------------------------------------------------------------------------------
    def _ready(self, row: RequestRow) -> None:
        if row.state != "waiting":
            raise ApiError(409, "conflict", f"this request is {row.state}", reason=row.state)
        if row.not_before is None or utc(row.not_before) > self.now():
            wait = int((utc(row.not_before) - self.now()).total_seconds()) + 1 if row.not_before else 0
            raise ApiError(409, "conflict", "the wait is not over yet", reason="waiting", retry_after_s=max(wait, 1))

    def complete_options(self, request: Request, request_id: str) -> dict:
        row = self._starter(request, request_id)
        self._ready(row)
        owner = self.ident.user(row.owner_user_id)
        rp_id, _ = self.ident.rp(request)
        existing = list(self.ident.repo.all(select(PasskeyRow.id).where(PasskeyRow.user_id == owner.id)))
        challenge, raw = self.ident._new_challenge(CHALLENGE_PURPOSE, user_id=owner.id, action_id=row.id)
        opts = pk.registration_options(rp_id=rp_id, rp_name=self.ident.cfg.rp_name, user_id=owner.id,
                                       user_name=owner.username or owner.id, display_name=owner.display_name,
                                       challenge=raw, exclude=existing)
        return {"challenge_id": challenge.id, "expires_at": iso(challenge.expires_at), "publicKey": opts}

    def complete(self, request: Request, request_id: str, credential: dict | None, label: str | None,
                 new_password: str | None) -> tuple[RequestRow, UserRow]:
        row = self._starter(request, request_id)
        self._ready(row)
        if row.path == "remote" and new_password is not None:
            raise ApiError(422, "conflict", "a remote recovery only adds a key; your password is unchanged",
                           reason="password_not_allowed")
        if credential is None and (row.path == "remote" or new_password is None):
            raise ApiError(422, "conflict", "enrol a new passkey" + ("" if row.path == "remote" else " or set a new password"),
                           reason="nothing_to_restore")
        owner = self.ident.user(row.owner_user_id)
        if owner is None or owner.disabled:
            raise ApiError(409, "conflict", "this account is disabled", reason="account_disabled")
        now = self.now()
        added = None
        if credential is not None:
            try:
                credential = pk.normalize(credential)
                challenge = self.ident._consume_challenge(credential, CHALLENGE_PURPOSE)
            except pk.PasskeyError as exc:
                raise ApiError(422, "conflict", str(exc)[:300], reason="assertion_invalid") from None
            if challenge.user_id != owner.id or challenge.action_id != row.id:
                raise ApiError(401, "unauthenticated", "challenge belongs to another recovery", reason="assertion_invalid")
            rp_id, origins = self.ident.rp(request)
            try:
                v = pk.verify_registration(credential=credential, challenge=pk.unb64url(challenge.challenge),
                                           rp_id=rp_id, origins=origins)
            except pk.PasskeyError as exc:
                raise ApiError(422, "conflict", str(exc)[:300], reason="assertion_invalid") from None
            if self.ident.repo.get(PasskeyRow, v["id"]) is not None:
                raise ApiError(409, "conflict", "this passkey is already registered")
            added = (label or "recovered passkey").strip()[:100] or "recovered passkey"
            self.ident.repo.add(PasskeyRow(id=v["id"], user_id=owner.id, label=added, public_key=v["public_key"],
                                           sign_count=v["sign_count"], transports=v["transports"], created_at=now))
        if new_password is not None:
            if not PASSWORD_MIN <= len(new_password) <= PASSWORD_MAX:
                raise ApiError(422, "conflict", f"password must be {PASSWORD_MIN} to {PASSWORD_MAX} characters",
                               reason="weak_password")
            self.ident.repo.update(UserRow, [UserRow.id == owner.id],
                                   {"password_hash": hash_password(new_password), "updated_at": now})
            # Whoever held the old password's sessions is signed out (as a password change does).
            self.ident.repo.update(SessionRow, [SessionRow.user_id == owner.id, SessionRow.revoked_at.is_(None)],
                                   {"revoked_at": now})
        with self.db.session.begin() as s:
            done = s.execute(update(RequestRow).where(RequestRow.id == row.id, RequestRow.state == "waiting")
                             .values(state="completed", ended_at=now, end_reason="completed")).rowcount
        if done != 1:
            raise ApiError(409, "conflict", "this request is no longer waiting", reason="not_waiting")
        row = self._get(row.id)
        self.contacts.tell(row.owner_user_id, "recovery.request.completed",
                           {"request_id": row.id, "path": row.path, "passkey_added": added is not None,
                            "password_reset": new_password is not None}, severity="warning")
        return row, self.ident.user(owner.id)

    # ---- the clock: lapse, and the notices during a wait -------------------------------------------------
    def tick(self) -> int:
        """Close requests nobody confirmed in time and send the wait's notices that are due: every 24 hours
        and 1 hour before the end. Idempotent: each notice is sent once (notices_sent)."""
        now, sent = self.now(), 0
        with self.db.session() as s:
            rows = list(s.scalars(select(RequestRow).where(RequestRow.state.in_(OPEN_STATES))))
        for r in rows:
            r = self._fresh(r)
            if r.state != "waiting" or r.not_before is None:
                continue
            start = utc(r.vouched_at or r.created_at)
            due = [f"day{n}" for n in range(1, int((now - start).total_seconds() // 86400) + 1)
                   if start + timedelta(days=n) < utc(r.not_before)]
            if utc(r.not_before) - now <= timedelta(hours=1):
                due.append("last_hour")
            new = [d for d in due if d not in (r.notices_sent or [])]
            if not new:
                continue
            self._set(r, notices_sent=[*(r.notices_sent or []), *new])
            self.contacts.tell(r.owner_user_id, "recovery.request.reminder",
                               {"request_id": r.id, "path": r.path, "not_before": iso(r.not_before),
                                "notice": new[-1]}, severity="warning")
            sent += 1
        return sent

