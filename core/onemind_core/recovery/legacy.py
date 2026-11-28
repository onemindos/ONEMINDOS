# SPDX-License-Identifier: Apache-2.0
"""Legacy contacts and the claim process (gateway permissions design PR 25f, §3.13, D-028).

Someone the owner names (up to 5, household or outside, with an owner action and passkey approval,
signed invite and cooling-off) can get a **read-only export of the owner's personal
data after the owner's death**. Apple has staff who check a death certificate; a OneMind box has
nobody in the loop, so the claim rests on time, notices and the owner's own silence instead:

1. **The access key.** When the contact accepts, their phone gets a legacy access key (256 random
   bits, shown as letter groups), once. In Standard mode the box keeps only a salted verifier.
2. **The claim.** The contact sends the access key and a death certificate (a PDF or a photo). OneMind
   cannot verify the certificate; it is kept for the household's adults and recorded, as evidence,
   never as a key.
3. **The wait:** 30 days by default; the owner picks 14, 30, 60 or 90 when adding the contact.
4. **Notices** at the start, every 7 days and on the last day, to every owner, every recovery
   and legacy contact and every household adult. After downtime, the latest due reminder is sent,
   with the last-day reminder sent before processing the grant if the box missed that day.
5. **Any sign-in by the owner cancels the claim at once,** and the claim completes only if the owner
   did not sign in, use a key, use one of their own personal access tokens or approve anything for the
   whole wait (Google's inactivity idea). Calls made with the owner's own personal token (`om_pat_`,
   kind `person`) count as the owner being alive, including calls from a script or app that runs by
   itself; agent, plugin, node and automation tokens do not. This
   holds after a grant too: an owner who signs in again (back from a trip, say) ends a granted claim,
   and the export refuses as soon as the owner was active after the grant.
6. **A second person** (another legacy contact or a household adult, never the claimant themselves) must
   confirm when one exists (D-028); with nobody else, the wait, the notices and the inactivity check stand
   alone. Whether one exists is checked again when the wait ends, so a claim never waits for someone who
   was disabled or removed meanwhile.
7. **Then** the contact gets a read-only export of the owner's Files home for 12 months. The data
   stays on the box afterwards: nothing here deletes anything, and a legacy contact never gets admin,
   other people's data, app secrets, sign-in keys or the recovery kit (the legacy principal reaches
   only `LEGACY_PATHS`; every other route answers 403).

Who owns the box after the owner's death is a separate, later question (N-9, 1.1).
"""

from __future__ import annotations

import base64
import binascii
import contextvars
import fcntl
import hashlib
import hmac
import logging
import os
import re
import secrets
import stat
import tarfile
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path

from sqlalchemy import DateTime, Index, String, cast, or_, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.types import JSON

from ..actions import FeatureAction
from ..auth import Principal
from ..errors import ApiError
from ..executors import ExecResult
from ..files.errors import FilesError
from ..files.paths import open_file_at
from ..identity.crypto import new_id
from ..identity.models import ApproverKeyRow, PasskeyRow, TokenRow, UserRow, iso
from ..identity.service import AuthContext
from ..ledger import Base, utc
from ..notify.service import NotifyService
from .contacts import ROLE_PATHS, RecoveryContacts
from .models import ContactRow

TS = DateTime(timezone=True)
WAIT_OPTIONS = (14, 30, 60, 90)  # D-028: the owner picks 14 to 90; 30 by default
DEFAULT_WAIT_DAYS = 30
EXPORT_WINDOW = timedelta(days=365)  # D-028: 12 months; the data is never deleted afterwards
INVITE_ACTION = "legacy.contact.add"
NOTICE_EVERY = timedelta(days=7)
# Older gateways could record "last_day" or "last_day_recorded" without a durable owner inbox item.
FINAL_NOTICE_RECORDED = "last_day_inbox_recorded"
# The gateway takes request bodies up to 256 KiB (guard.py); base64 grows a file by a third, so the phone app
# sends a downsized photo or a small PDF. Chunked uploads of bigger files are a follow-up.
MAX_CERTIFICATE_BYTES = 180 * 1024
MAX_EXPORT_BYTES = 20 * 1024 * 1024 * 1024
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ"  # no I, L, O: easy to read back
CERT_TYPES = {b"%PDF-": ("application/pdf", "pdf"), b"\xff\xd8\xff": ("image/jpeg", "jpg"),
              b"\x89PNG\r\n\x1a\n": ("image/png", "png")}
OPEN_STATES = ("waiting", "awaiting_second")
LIVE_STATES = (*OPEN_STATES, "granted")  # every state the owner's return must end
log = logging.getLogger(__name__)
LEGACY_PATHS = [
    re.compile(r"/v1/legacy/contact(/notices|/resign)?"),
    re.compile(r"/v1/legacy/claims(/lcl_[0-9A-Z]{26}/confirm)?"),
    re.compile(r"/v1/legacy/export(/download)?"),
]

def register_paths() -> None:
    """Called by the router when it wires legacy: the legacy principal reaches only LEGACY_PATHS."""
    ROLE_PATHS["legacy"] = LEGACY_PATHS


# Who was signed in on the device that is accepting a legacy invite (resolved before the accept runs, read by
# on_accept so it is written in the same transaction as the access key). A ContextVar, so each request has its own.
_ACCEPTED_BY: contextvars.ContextVar[tuple[bool, str | None] | None] = contextvars.ContextVar("legacy_accepted_by",
                                                                                              default=None)


class ClaimRow(Base):
    """Feature "recovery": a new table, so create_all adds it at this shape."""

    __tablename__ = "recovery_legacy_claims"
    # At most one open claim per owner, enforced by the database (two simultaneous claims: the second fails).
    __table_args__ = (Index("uq_legacy_one_open_claim", "owner_user_id", unique=True,
                            sqlite_where=text("state IN ('waiting', 'awaiting_second')"),
                            postgresql_where=text("state IN ('waiting', 'awaiting_second')")),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # lcl_<ulid>
    owner_user_id: Mapped[str] = mapped_column(String(40), index=True)
    contact_id: Mapped[str] = mapped_column(String(40), index=True)
    # waiting -> awaiting_second (the wait is over, a second person has not confirmed) -> granted;
    # or cancelled. Never anything that deletes.
    state: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(TS)
    ends_at: Mapped[datetime] = mapped_column(TS)
    needs_second: Mapped[bool] = mapped_column(default=False)
    second_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    second_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    certificate_type: Mapped[str] = mapped_column(String(40))
    certificate_sha256: Mapped[str] = mapped_column(String(64))
    granted_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    access_until: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    end_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ended_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    notices_sent: Mapped[list] = mapped_column(JSON, default=list)


def new_access_key() -> str:
    """At least 256 random bits: 16 groups of 4 letters from a 23-letter alphabet (16 x 4 x log2(23) = 289 bits)."""
    return "-".join("".join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(16))


def normal_key(text: str) -> str:
    return "".join(ch for ch in (text or "").upper() if ch in ALPHABET)


def verifier(salt: bytes, key: str) -> str:
    return hashlib.sha256(b"legacy-access\n" + salt + normal_key(key).encode()).hexdigest()


class LegacyContacts(RecoveryContacts):
    role = "legacy"
    principal_kind = "legacy"
    noun = "legacy contact"

    def __init__(self, gw, ident, notify: NotifyService):
        super().__init__(gw, ident)
        self.notify = notify
        self.dir = gw.settings.audit_path.parent / "recovery" / "legacy"
        self.files = None  # () -> the FilesService; set by the router (files registers after recovery)
        self.ended_hooks.append(self._contact_ended)
        gw.events.subscribe("auth.login.succeeded", self._owner_signed_in)

    # ---- contacts ------------------------------------------------------------------------------------
    def register_actions(self) -> None:
        self.gw.actions.register_type(INVITE_ACTION, FeatureAction(
            risk="sensitive", requesters=frozenset(), run=self._approve_invite, owner_passkey=True,
        ))

    @staticmethod
    def _require_enrollment() -> None:
        # D-028 requires L2 or, before the first L2 key, L1 plus confirmation at the box.
        # Keep the hold until the shared approval path can enforce both cases.
        raise ApiError(503, "unavailable", "Legacy enrollment requires a verified hardware key or first-key setup at this OneMind.",
                       reason="legacy_enrollment_unavailable")

    def request_invite(self, ctx, kind: str, display_name: str, household_user_id: str | None,
                       cooling_off_days: int | None, wait_days: int | None) -> dict:
        owner = self._session_owner(ctx, "request a legacy contact")
        self._require_enrollment()
        wait = DEFAULT_WAIT_DAYS if wait_days is None else wait_days
        if wait not in WAIT_OPTIONS:
            raise ApiError(422, "conflict", f"wait_days must be one of {list(WAIT_OPTIONS)}", reason="not_an_option")
        target, name, days = self._invite_details(owner, ctx.principal, kind, display_name, household_user_id,
                                                  cooling_off_days)
        with self.db.session() as s:
            self._check_invite_limit(s, owner.id, target, name, self.now())
        contact_id = new_id("rc")
        action, _ = self.gw.actions.request_feature(
            ctx.principal, INVITE_ACTION, {"contact_id": contact_id, "kind": kind, "target": name,
                                          "household_user_id": target, "cooling_off_days": days, "wait_days": wait},
            idempotency_key=contact_id, expires_at=self.now() + timedelta(minutes=15), pending_cap=True,
        )
        return {"action_id": action["id"], "contact_id": contact_id, "wait_days": wait}

    def _approve_invite(self, action, finish) -> None:
        owner = self.ident.user(action.requested_by["id"])
        if owner is None or owner.disabled or owner.role != "owner":
            finish(ExecResult("failed", "The requesting account is no longer an active owner."))
            return
        params = action.params
        try:
            self._require_enrollment()
            self._issue_invite(owner, self.ident.principal_for(owner), params["kind"], params["target"],
                               params["household_user_id"], params["cooling_off_days"], via="action_passkey",
                               extra={"wait_days": params["wait_days"]}, contact_id=params["contact_id"],
                               retain_invite=True)
        except ApiError as e:
            finish(ExecResult("failed", e.message))
            return
        finish(ExecResult("succeeded", "Legacy contact invited."))

    def invite(self, ctx, contact_id: str) -> dict:
        owner = self._session_owner(ctx, "read a legacy invite")
        row = self._get(contact_id)
        if (row is None or row.owner_user_id != owner.id or self.state_of(row) != "invited"
                or row.sealed_secret is None):
            raise ApiError(404, "not_found", "no pending legacy invite for this contact")
        self._require_enrollment()
        nonce = self.sealer.open(row.sealed_secret, f"invite:{row.id}").decode()
        return self._invite_view(owner, row, nonce)

    def view(self, r: ContactRow) -> dict:
        return {**super().view(r), "wait_days": int((r.extra or {}).get("wait_days", DEFAULT_WAIT_DAYS))}

    def on_accept(self, contact_id: str) -> dict:
        """The access key, and who accepted, written in ONE transaction: a contact that has an access key
        always has `accepted_signed_in` recorded (True with `accepted_by_user_id`, or False)."""
        key, salt = new_access_key(), secrets.token_bytes(16)
        signed_in, who = _ACCEPTED_BY.get() or (False, None)
        with self.db.session.begin() as s:
            row = s.get(ContactRow, contact_id)
            row.extra = {**(row.extra or {}), "access_salt": salt.hex(), "access_verifier": verifier(salt, key),
                         "accepted_signed_in": signed_in, "accepted_by_user_id": who}
        return {"access_key": key}

    def accept(self, request, invite_id: str, *args, **kwargs) -> dict:
        """As for a recovery contact; also record which household account (if any) was signed in on the
        device that accepted, so that adult can never be the second person on this contact's claim.

        When it is recorded, precisely: the accept request carries a valid OneMind session, that is a
        bearer session (the phone app or the CLI signed in) or a browser cookie session WITH its CSRF
        header (every @onemind/sdk client sends it). It is resolved before the accept runs and written with
        the access key. When it is not: a signed-out device, or a cookie without its CSRF header, which
        identity refuses on purpose (H-16: a cross-site page can make a browser send the cookie) and this
        code must not read itself. Such an accept is recorded as `accepted_signed_in: False`, and the
        household's claim view shows it, so owners and adults know the second person cannot be checked
        against the claimant's account (see `_contact_users`)."""
        self._require_enrollment()
        token = _ACCEPTED_BY.set(self._session_user(request))
        try:
            return super().accept(request, invite_id, *args, **kwargs)
        finally:
            _ACCEPTED_BY.reset(token)

    def _session_user(self, request) -> tuple[bool, str | None]:
        """(signed in as a household person?, that person's user id)."""
        # Only skip the lookup for a bare phone (no credentials at all), so it leaves no auth.rejected line.
        # The session itself is resolved by identity (its cookie and CSRF rules, H-16), never read here.
        if not request.headers.get("authorization") and not request.headers.get("cookie"):
            return False, None
        try:
            p = self.gw.principal(request)
        except ApiError:
            return False, None
        return (True, p.id) if p.kind == "person" else (False, None)

    def contact_view(self, row: ContactRow) -> dict:
        return {**super().contact_view(row), "wait_days": int((row.extra or {}).get("wait_days", DEFAULT_WAIT_DAYS))}

    # ---- the claim -----------------------------------------------------------------------------------
    def _claim(self, claim_id: str) -> ClaimRow | None:
        with self.db.session() as s:
            return s.get(ClaimRow, claim_id)

    def _lock_active_contact(self, s: Session, claim: ClaimRow, now: datetime) -> bool:
        # The write locks the same row updated by removal and resignation until this transaction commits.
        locked = s.scalar(update(ContactRow).where(
            ContactRow.id == claim.contact_id, ContactRow.owner_user_id == claim.owner_user_id,
            ContactRow.role == self.role, ContactRow.state == "active",
            or_(ContactRow.usable_at.is_(None), ContactRow.usable_at <= now),
        ).values(last_seen_at=ContactRow.last_seen_at).returning(ContactRow.id))
        return locked is not None

    def _set(self, row: ClaimRow, expect: tuple[str, ...], *where, **values) -> bool:
        """Compare-and-set: write only while the claim is still in one of the `expect` states (and any extra
        `where` conditions hold), checked by the database at the write. So a sign-in that cancels a claim
        while tick() is granting it can never be overwritten back to `granted`: whichever commits second
        changes nothing (or, for a grant that commits first, the cancel still ends it). Returns whether this
        call made the change."""
        with self.db.session.begin() as s:
            if values.get("state") == "granted":
                # Serialize with Identity's owner activity writes. SQLite locks the writer and
                # PostgreSQL locks this owner row until the grant transaction commits.
                self._lock_owner(s, row.owner_user_id)
                if not self._lock_active_contact(s, row, self.now()):
                    return False
                where += (~self._activity_after(row.owner_user_id, utc(row.created_at)),
                          ~self._granted_before(row.owner_user_id, row.contact_id),
                          cast(ClaimRow.notices_sent, String).contains(f'"{FINAL_NOTICE_RECORDED}"', autoescape=True))
            done = s.execute(update(ClaimRow).where(ClaimRow.id == row.id, ClaimRow.state.in_(expect), *where)
                             .values(**values).returning(ClaimRow.id)).scalar()
        return done is not None

    @contextmanager
    def _claim_lock(self, claim_id: str):
        """Order claim transitions with their notices across gateway workers on this box."""
        locks = self.dir / "claim-locks"
        locks.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Every worker must lock the same inode, including workers that already opened it and are waiting.
        fd = os.open(locks / claim_id, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def _set_and_tell(self, c: ClaimRow, expect: tuple[str, ...], *where,
                      event: str, data: dict, severity: str, p: Principal | None = None, **values) -> bool:
        with self._claim_lock(c.id):
            if not self._set(c, expect, *where, **values):
                return False
            self.tell(c.owner_user_id, event, {"claim_id": c.id, **data}, p, severity=severity)
            return True

    def claim_view(self, c: ClaimRow, *, for_household: bool = False) -> dict:
        contact = self._get(c.contact_id)
        out = {"id": c.id, "contact_id": c.contact_id, "state": c.state, "created_at": iso(c.created_at),
               "ends_at": iso(c.ends_at), "needs_second": c.needs_second, "second_confirmed": c.second_at is not None,
               "granted_at": iso(c.granted_at), "access_until": iso(c.access_until), "ended_at": iso(c.ended_at),
               "end_reason": c.end_reason, "certificate_type": c.certificate_type}
        if for_household:
            # Shown side by side so owners and adults can see the confirmer is someone else (Opus review, #1208).
            out["contact_display_name"] = contact.display_name if contact else None
            out["confirmed_by_display_name"] = self._display_name_of(c.second_by)
            out["claimant_accepted_signed_in"] = bool((contact.extra or {}).get("accepted_signed_in")) if contact else False
        return out

    def _display_name_of(self, who: str | None) -> str | None:
        if not who:
            return None
        if who.startswith("legacy:"):
            other = self._get(who.removeprefix("legacy:"))
            return other.display_name if other else None
        u = self.ident.user(who)
        return (u.display_name or u.username) if u else None

    def _second_people(self, owner_id: str, claimant: ContactRow) -> bool:
        """Is there someone who can confirm: another usable legacy contact, or an active household adult?"""
        if any(self._is_other_contact(claimant, r) for r in self.usable(owner_id)):
            return True
        with self.db.session() as s:
            adults = list(s.scalars(select(UserRow.id).where(UserRow.role == "adult", UserRow.disabled.is_(False))))
        return bool(set(adults) - self._contact_users(claimant))

    def _is_other_contact(self, claimant: ContactRow, contact: ContactRow) -> bool:
        return (claimant.id != contact.id
                and not (claimant.key_fingerprint and claimant.key_fingerprint == contact.key_fingerprint)
                and self._contact_users(claimant).isdisjoint(self._contact_users(contact)))

    def _check_key(self, contact: ContactRow, access_key: str) -> None:
        extra = contact.extra or {}
        try:
            salt = bytes.fromhex(str(extra.get("access_salt") or ""))
        except ValueError:
            salt = b""
        want = str(extra.get("access_verifier") or "")
        if not want or not hmac.compare_digest(verifier(salt, access_key), want):
            raise ApiError(401, "unauthenticated", "that is not your legacy access key", reason="access_key_invalid")

    def start_claim(self, contact: ContactRow, p: Principal, access_key: str, cert_type: str, cert_b64: str) -> dict:
        now = self.now()
        key = f"legacy:{contact.id}"
        self.limiter.check(key, now)
        if self.state_of(contact, now) != "active":
            raise ApiError(409, "conflict", "you cannot claim yet: the owner's cooling-off is still running",
                           reason="cooling_off")
        try:
            self._check_key(contact, access_key)
        except ApiError:
            self.limiter.fail(key, now)
            self.gw.audit.append("legacy.claim.key_refused", p.as_dict(), None, {"contact_id": contact.id})
            raise
        ctype, ext, raw = self._certificate(cert_type, cert_b64)
        with self.db.session() as s:
            open_ = s.scalar(select(ClaimRow.id).where(ClaimRow.owner_user_id == contact.owner_user_id,
                                                       ClaimRow.state.in_(OPEN_STATES)))
            previously_granted = s.scalar(select(self._granted_before(contact.owner_user_id, contact.id)))
        if open_ is not None:
            raise ApiError(409, "conflict", "a legacy claim for this owner is already open", reason="already_open")
        if previously_granted:
            raise self._export_already_granted()
        wait = int((contact.extra or {}).get("wait_days", DEFAULT_WAIT_DAYS))
        cid = new_id("lcl")
        path = self._cert_path(cid, ext)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        row = ClaimRow(id=cid, owner_user_id=contact.owner_user_id, contact_id=contact.id, state="waiting",
                       created_at=now, ends_at=now + timedelta(days=wait),
                       needs_second=self._second_people(contact.owner_user_id, contact),
                       certificate_type=ctype, certificate_sha256=hashlib.sha256(raw).hexdigest(),
                       notices_sent=["start"])
        with self._claim_lock(cid):
            try:
                with self.db.session.begin() as s:
                    self._lock_owner(s, row.owner_user_id)
                    if not self._lock_active_contact(s, row, now):
                        raise self._contact_unavailable()
                    if s.scalar(select(self._granted_before(row.owner_user_id, row.contact_id))):
                        raise self._export_already_granted()
                    s.add(row)
            except IntegrityError:  # a simultaneous claim won the one-open-claim index
                path.unlink(missing_ok=True)
                raise ApiError(409, "conflict", "a legacy claim for this owner is already open",
                               reason="already_open") from None
            except ApiError:
                path.unlink(missing_ok=True)
                raise
            self.tell(contact.owner_user_id, "legacy.claim.started",
                      {"claim_id": cid, "contact_id": contact.id, "ends_at": iso(row.ends_at)}, p, severity="critical")
        return self.claim_view(row)

    @staticmethod
    def _granted_before(owner_id: str, contact_id: str):
        # One export per authorization (contact/key), and at most one grant for a silent owner.
        # After returning, the owner can end the prior grant and approve a new contact and key.
        # Use a separate alias so this also works inside a ClaimRow UPDATE.
        past = ClaimRow.__table__.alias()
        return select(past.c.id).where(
            past.c.owner_user_id == owner_id, past.c.granted_at.is_not(None),
            or_(past.c.contact_id == contact_id, past.c.state == "granted"),
        ).exists()

    @staticmethod
    def _contact_unavailable() -> ApiError:
        return ApiError(403, "permission_denied", "the legacy contact is no longer active", reason="contact_ended")

    @staticmethod
    def _export_already_granted() -> ApiError:
        return ApiError(409, "conflict", "the owner must authorize a new contact for another legacy export",
                        reason="export_already_granted")

    def _certificate(self, cert_type: str, cert_b64: str) -> tuple[str, str, bytes]:
        try:
            raw = base64.b64decode(cert_b64 or "", validate=True)
        except (binascii.Error, ValueError):
            raise ApiError(422, "conflict", "certificate: base64 expected", reason="certificate_invalid") from None
        if not raw or len(raw) > MAX_CERTIFICATE_BYTES:
            raise ApiError(422, "conflict", f"certificate: 1 byte to {MAX_CERTIFICATE_BYTES // 1024} KiB",
                           reason="certificate_size")
        for magic, (ctype, ext) in CERT_TYPES.items():
            if raw.startswith(magic):
                if cert_type and cert_type != ctype:
                    raise ApiError(422, "conflict", f"certificate: the file is {ctype}, not {cert_type}",
                                   reason="certificate_type")
                return ctype, ext, raw
        raise ApiError(422, "conflict", "certificate: a PDF, JPEG or PNG", reason="certificate_type")

    def _cert_path(self, claim_id: str, ext: str) -> Path:
        return self.dir / claim_id / f"certificate.{ext}"

    def certificate(self, claim_id: str) -> tuple[bytes, str]:
        c = self._claim(claim_id)
        if c is None:
            raise ApiError(404, "not_found", "no such claim")
        ext = next((e for t, e in CERT_TYPES.values() if t == c.certificate_type), None)
        if ext is None:
            raise ApiError(404, "not_found", "certificate unavailable")
        try:
            return self._cert_path(c.id, ext).read_bytes(), c.certificate_type
        except FileNotFoundError:
            raise ApiError(404, "not_found", "certificate unavailable") from None

    def claims_of(self, contact: ContactRow) -> list[dict]:
        self.tick()
        with self.db.session() as s:
            rows = list(s.scalars(select(ClaimRow).where(ClaimRow.contact_id == contact.id)
                                  .order_by(ClaimRow.created_at.desc())))
        return [self.claim_view(r) for r in rows]

    def claims_for_household(self, p: Principal) -> list[dict]:
        """Every claim on the box, for the owners and adults who are told and may cancel or confirm."""
        if p.kind != "person" or p.role not in ("owner", "adult"):
            raise self.ident.deny(p, "read legacy claims", reason="owner_or_adult")
        self.tick()
        with self.db.session() as s:
            rows = list(s.scalars(select(ClaimRow).order_by(ClaimRow.created_at.desc())))
        return [self.claim_view(r, for_household=True) for r in rows]

    def household_reads_certificate(self, p: Principal, claim_id: str) -> tuple[bytes, str]:
        if p.kind != "person" or p.role not in ("owner", "adult"):
            raise self.ident.deny(p, "read a legacy claim's certificate", reason="owner_or_adult")
        data = self.certificate(claim_id)
        self.gw.audit.append("legacy.claim.certificate_read", p.as_dict(), None, {"claim_id": claim_id})
        return data

    def cancel(self, ctx, claim_id: str, block: bool) -> dict:
        """The owner stops a claim (and, with block, removes that contact). L0: it only takes power away."""
        owner = self._session_owner(ctx, "cancel a legacy claim")
        c = self._claim(claim_id)
        if c is None:
            raise ApiError(404, "not_found", "no such claim")
        if c.state in LIVE_STATES:
            c = self._end_claim(c, "cancelled", "owner_cancelled", owner.id)
        if block:
            contact = self._get(c.contact_id)
            if contact is not None and contact.state in ("invited", "active"):
                self._end(contact, "removed")
                self.tell(c.owner_user_id, "legacy.contact.removed", {"contact_id": contact.id}, ctx.principal)
        return self.claim_view(c, for_household=True)

    def _end_claim(self, c: ClaimRow, state: str, reason: str, by: str | None,
                   expect: tuple[str, ...] = LIVE_STATES) -> ClaimRow:
        """End a live claim, with a notice only if this call wins the transition. Return the current claim."""
        self._set_and_tell(c, expect, event=f"legacy.claim.{state}", data={"reason": reason}, severity="warning",
                           state=state, ended_at=self.now(), end_reason=reason, ended_by=by)
        return self._claim(c.id)

    def confirm(self, p: Principal, claim_id: str, contact: ContactRow | None, *, ctx: AuthContext | None = None) -> dict:
        """The second person: another usable legacy contact of the same owner, or a household adult."""
        confirmer_id = p.id
        if contact is None:
            if ctx is None or ctx.session is None or ctx.user is None:
                raise self.ident.deny(p, "confirm a legacy claim", reason="session_required")
            if ctx.user.role != "adult":
                raise self.ident.deny(p, "confirm a legacy claim", reason="adult_only")
            confirmer_id = ctx.session.user_id
        c = self._claim(claim_id)
        if c is None:
            raise ApiError(404, "not_found", "no such claim")
        claimant = self._get(c.contact_id)
        if contact is not None:
            if claimant is None or contact.owner_user_id != c.owner_user_id \
                    or not self._is_other_contact(claimant, contact) \
                    or self.state_of(contact) != "active":
                raise self.ident.deny(p, "confirm this legacy claim", reason="not_a_second_person")
        elif claimant is None or confirmer_id in self._contact_users(claimant):
            raise self.ident.deny(p, "confirm your own legacy claim", reason="not_a_second_person")
        if c.state not in OPEN_STATES:
            raise ApiError(409, "conflict", f"this claim is {c.state}", reason=c.state)
        if c.second_at is None:
            self._set_and_tell(c, OPEN_STATES, ClaimRow.second_at.is_(None), second_by=confirmer_id, second_at=self.now(),
                               event="legacy.claim.confirmed", data={}, severity="warning", p=p)
        self.tick()
        return self.claim_view(self._claim(c.id))

    def _contact_users(self, contact: ContactRow) -> set[str]:
        """Known household accounts of this contact:
        1. linked as the claimant's household contact;
        2. the account that was signed in on the device that accepted the claimant's invite; or
        3. holding the claimant's contact key as one of its approver keys.
        Not refused by a matching name, on purpose: two real people can share a name, and refusing the only
        adult would leave a genuine heir's claim waiting for a second person forever (while excluding that
        adult from "is there a second person" would let anyone skip the second person by copying a name).
        The gap that stays, stated precisely: an adult who accepted an outside invite on a signed-out device
        with a new key cannot be told apart by the box. For that case the household view shows the claimant
        and the confirmer side by side and flags a claimant who accepted signed out
        (`claimant_accepted_signed_in: false`); every owner is told of the confirmation (the event carries the confirmer's account);
        and the wait and the owner-silence check (any sign-in ends the claim, granted or not) still stand."""
        users = {contact.household_user_id, (contact.extra or {}).get("accepted_by_user_id")}
        users.discard(None)
        if contact.key_fingerprint:
            with self.db.session() as s:
                users.update(s.scalars(select(ApproverKeyRow.user_id)
                                       .where(ApproverKeyRow.fingerprint == contact.key_fingerprint)))
        return users

    # ---- the owner's own activity ----------------------------------------------------------------------
    def _owner_signed_in(self, envelope: dict) -> None:
        """Any sign-in by the owner ends every claim on them, a granted one included."""
        user_id = (envelope.get("data") or {}).get("user_id")
        if not user_id:
            return
        with self.db.session() as s:
            rows = list(s.scalars(select(ClaimRow).where(ClaimRow.owner_user_id == user_id,
                                                         ClaimRow.state.in_(LIVE_STATES))))
        for c in rows:
            self._end_claim(c, "cancelled", "owner_signed_in", user_id, expect=LIVE_STATES)

    def _owner_active_since(self, owner_id: str, since: datetime) -> bool:
        with self.db.session() as s:
            return bool(s.scalar(select(self._activity_after(owner_id, since))))

    @staticmethod
    def _activity_after(owner_id: str, since: datetime):
        # Keep using previously persisted activity, alongside the unthrottled owner watermark.
        return or_(
            select(UserRow.id).where(UserRow.id == owner_id, UserRow.last_seen_at > since).exists(),
            select(PasskeyRow.id).where(PasskeyRow.user_id == owner_id, PasskeyRow.last_used_at > since).exists(),
            select(ApproverKeyRow.id).where(ApproverKeyRow.user_id == owner_id,
                                           ApproverKeyRow.last_used_at > since).exists(),
            select(TokenRow.id).where(TokenRow.kind == "person", TokenRow.owner_user_id == owner_id,
                                      TokenRow.last_used_at > since).exists(),
        )

    def _contact_ended(self, contact: ContactRow) -> None:
        if contact.role != "legacy":
            return
        with self.db.session() as s:
            rows = list(s.scalars(select(ClaimRow).where(ClaimRow.contact_id == contact.id,
                                                         ClaimRow.state.in_(LIVE_STATES))))
        for c in rows:
            self._end_claim(c, "cancelled", "contact_ended", f"legacy:{contact.id}", expect=LIVE_STATES)

    # ---- the clock ------------------------------------------------------------------------------------
    def _remind(self, c: ClaimRow, now: datetime) -> tuple[ClaimRow, bool]:
        with self._claim_lock(c.id):
            # Another worker may have recorded a different reminder since tick read this row.
            c = self._claim(c.id)
            if c.state not in OPEN_STATES:
                return c, False
            sent = c.notices_sent or []
            end = utc(c.ends_at)
            weeks = int((min(now, end) - utc(c.created_at)) / NOTICE_EVERY)
            due = [f"week{n}" for n in range(1, weeks + 1)]
            if end - now <= timedelta(days=1):
                due.append(FINAL_NOTICE_RECORDED)
            new = [notice for notice in due if notice not in sent]
            if not new:
                return c, False

            def record(s):
                s.execute(update(ClaimRow).where(ClaimRow.id == c.id).values(notices_sent=[*sent, *new]))

            final_day = new[-1] == FINAL_NOTICE_RECORDED
            data = {"claim_id": c.id, "ends_at": iso(c.ends_at), "notice": "last_day" if final_day else new[-1]}
            commit = partial(self.notify.record_legacy_final_notice, c.owner_user_id, data) if final_day else None
            self.tell(c.owner_user_id, "legacy.claim.reminder", data, severity="critical", record=record, commit=commit)
            return c, True

    def tick(self) -> int:
        """Notices during the wait; at the end, cancel if the owner was active, wait for the second person,
        or grant the 12-month read-only export. Idempotent."""
        now, done = self.now(), 0
        with self.db.session() as s:
            rows = list(s.scalars(select(ClaimRow).where(ClaimRow.state.in_(LIVE_STATES))))
        for c in rows:
            start = utc(c.created_at)
            if self._owner_active_since(c.owner_user_id, start):
                self._end_claim(c, "cancelled", "owner_active", None)
                done += 1
                continue
            claimant = self._get(c.contact_id)
            if claimant is None or self.state_of(claimant, now) != "active":
                self._end_claim(c, "cancelled", "contact_ended", None)
                done += 1
                continue
            if c.state == "granted":
                continue
            try:
                c, reminded = self._remind(c, now)
            except SQLAlchemyError:
                log.exception("Could not persist the legacy claim reminder for %s", c.id)
                continue  # No grant on this pass. Retry the reminder on the next tick.
            if c.state not in OPEN_STATES:
                continue
            end = utc(c.ends_at)
            if now < end:
                done += int(reminded)
                continue
            if c.second_at is None:
                if self._second_people(c.owner_user_id, claimant):
                    awaiting = (c.state != "awaiting_second" or not c.needs_second) and self._set_and_tell(
                        c, (c.state,), ClaimRow.needs_second.is_(c.needs_second), ClaimRow.second_at.is_(None),
                        state="awaiting_second", needs_second=True, event="legacy.claim.awaiting_second",
                        data={}, severity="warning",
                    )
                    done += int(reminded or awaiting)
                    continue
                if c.needs_second:
                    # Everyone who could confirm was disabled or removed during the wait.
                    if not self._set_and_tell(
                        c, (c.state,), ClaimRow.needs_second.is_(True), ClaimRow.second_at.is_(None),
                        needs_second=False, event="legacy.claim.no_second_person", data={}, severity="warning",
                    ):
                        continue
            # Only from an open state, and only with the second person's confirmation when one is needed:
            # a sign-in cancel that committed first leaves this write with nothing to change (no grant, no
            # notice); one that commits after it ends the fresh grant (LIVE_STATES includes granted).
            access_until = now + EXPORT_WINDOW
            if self._set_and_tell(c, OPEN_STATES, ClaimRow.needs_second.is_(False) | ClaimRow.second_at.is_not(None),
                                  event="legacy.claim.granted", data={"access_until": iso(access_until)},
                                  severity="critical", state="granted", granted_at=now, access_until=access_until):
                done += 1
            else:
                # A qualifying activity write or a prior grant can win after the initial read.
                if self._owner_active_since(c.owner_user_id, start):
                    self._end_claim(c, "cancelled", "owner_active", None, expect=OPEN_STATES)
                    done += 1
                else:
                    with self.db.session() as s:
                        replay = s.scalar(select(self._granted_before(c.owner_user_id, c.contact_id)))
                    if replay:
                        self._end_claim(c, "cancelled", "export_already_granted", None, expect=OPEN_STATES)
                        done += 1
        return done

    # ---- the read-only export -----------------------------------------------------------------------------
    def granted_claim(self, contact: ContactRow) -> ClaimRow:
        self.tick()
        with self.db.session() as s:
            c = s.scalar(select(ClaimRow).where(ClaimRow.contact_id == contact.id, ClaimRow.state == "granted")
                         .order_by(ClaimRow.granted_at))
        return self._check_export_access(c)

    def _check_export_access(self, c: ClaimRow | None) -> ClaimRow:
        if c is None or c.state != "granted":
            raise ApiError(403, "permission_denied", "no granted legacy claim", reason="no_granted_claim")
        contact = self._get(c.contact_id)
        if contact is None or self.state_of(contact) != "active":
            self._end_claim(c, "cancelled", "contact_ended", None, expect=("granted",))
            raise self._contact_unavailable()
        if c.granted_at is None or self._owner_active_since(c.owner_user_id, utc(c.created_at)):
            self._end_claim(c, "cancelled", "owner_active", None, expect=("granted",))
            raise ApiError(403, "permission_denied", "the owner was active after the grant; the claim has ended",
                           reason="owner_active")
        if c.access_until is None or utc(c.access_until) <= self.now():
            raise ApiError(403, "permission_denied", "the 12-month export window has ended; the data is still on the box",
                           reason="export_window_ended")
        return c

    def _walk(self, owner_id: str, *, check=None):
        """(relative path, size, dir fd, name) of every regular file in the owner's Files home, without
        following a symlink anywhere (os.fwalk on directory descriptors)."""
        from ..files.access import Root

        files = self.files() if self.files is not None else None
        if files is None:
            raise ApiError(503, "unavailable", "the files service is not available", reason="files_unavailable")
        with files._space(Root("home", owner_id)) as home:
            for top, _dirs, names, dfd in os.fwalk(".", dir_fd=home, follow_symlinks=False):
                if check is not None:
                    check()
                for name in sorted(names):
                    if check is not None:
                        check()
                    try:
                        st = os.stat(name, dir_fd=dfd, follow_symlinks=False)
                    except OSError:
                        continue
                    if stat.S_ISREG(st.st_mode):
                        rel = os.path.normpath(os.path.join(top, name))
                        yield rel, st.st_size, dfd, name

    def manifest(self, contact: ContactRow, p: Principal) -> dict:
        c = self.granted_claim(contact)

        def check():
            self._check_export_access(self._claim(c.id))

        items = [{"path": rel, "size": size} for rel, size, _fd, _n in self._walk(c.owner_user_id, check=check)]
        out = {"claim_id": c.id, "access_until": iso(c.access_until), "files": items,
               "total_bytes": sum(i["size"] for i in items), "read_only": True}
        check()
        self.gw.audit.append("legacy.export.listed", p.as_dict(), None, {"claim_id": c.id, "files": len(items)})
        return out

    def archive(self, contact: ContactRow, p: Principal) -> Generator[bytes, None, None]:
        """A tar of the owner's Files home, streamed: nothing is staged on disk or in RAM beyond one block.
        Too large is refused before the first byte; one download per contact at a time. Read-only on the source.
        Returns an iterator of bytes; the slot is released when it ends or is closed."""
        c = self.granted_claim(contact)
        stream = self._locked_archive(c, p)
        next(stream)  # Run preflight before HTTP headers and arm cleanup even if no tar chunk is pulled.
        return stream

    def _locked_archive(self, c: ClaimRow, p: Principal) -> Generator[bytes, None, None]:
        slots = self.dir / "downloads"
        slots.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Workers on the box share this lock file. Keep its inode so concurrent opens always contend.
        slot = os.open(slots / c.contact_id, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(slot, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ApiError(409, "conflict", "a download for this contact is already running",
                               reason="download_running") from None
            total = 1024  # the two terminating TAR blocks
            for rel, size, _fd, _n in self._walk(c.owner_user_id):
                header, padding = self._tar_entry(rel, size)
                total += len(header) + size + padding
                self._check_export_size(total)
            self._check_export_access(self._claim(c.id))
            self.gw.audit.append("legacy.export.downloaded", p.as_dict(), None, {"claim_id": c.id, "bytes": total})
            yield b""  # Readiness marker consumed by archive(), before any response bytes.
            try:
                yield from self._stream(c)
            except ApiError as exc:
                self.gw.audit.append("legacy.export.stopped", p.as_dict(), None,
                                     {"claim_id": c.id, "reason": exc.reason})
        finally:
            os.close(slot)  # Also releases the lock, even on preflight failure or disconnect.

    def _stream(self, c: ClaimRow) -> Generator[bytes, None, None]:
        block = 1 << 20
        total = 1024
        for rel, _size, dfd, name in self._walk(c.owner_user_id):
            self._check_export_access(self._claim(c.id))
            try:
                fd, st = open_file_at(dfd, name)
            except FilesError:
                continue
            with os.fdopen(fd, "rb") as f:
                size = st.st_size
                header, padding = self._tar_entry(rel, size)
                total += len(header) + size + padding
                self._check_export_size(total)
                yield header
                left = size
                while left > 0:  # exactly `size` bytes, so the tar stays valid if the file changes meanwhile
                    self._check_export_access(self._claim(c.id))
                    data = f.read(min(block, left))
                    if not data:
                        data = b"\0" * min(block, left)
                    left -= len(data)
                    yield data
                if padding:
                    yield b"\0" * padding
        self._check_export_access(self._claim(c.id))
        yield b"\0" * 1024

    @staticmethod
    def _tar_entry(rel: str, size: int) -> tuple[bytes, int]:
        info = tarfile.TarInfo(rel)
        info.size, info.mode = size, 0o644
        return info.tobuf(tarfile.PAX_FORMAT), -size % 512

    @staticmethod
    def _check_export_size(total: int) -> None:
        if total > MAX_EXPORT_BYTES:
            raise ApiError(413, "payload_too_large", "the export is larger than one download; use a USB copy",
                           reason="export_too_large")
