# SPDX-License-Identifier: Apache-2.0
"""Legacy contacts and the claim process (gateway permissions design PR 25f, §3.13, D-028).

Someone the owner names (up to 5, household or outside, added like a recovery contact: owner session,
passkey step-up, signed invite, cooling-off) can get a **read-only export of the owner's personal
data after the owner's death**. Apple has staff who check a death certificate; a OneMind box has
nobody in the loop, so the claim rests on time, notices and the owner's own silence instead:

1. **The access key.** When the contact accepts, their phone gets a legacy access key (256 random
   bits, shown as letter groups), once. In Standard mode the box keeps only a salted verifier.
2. **The claim.** The contact sends the access key and a death certificate (a PDF or a photo). OneMind
   cannot verify the certificate; it is kept for the household's adults and recorded, as evidence,
   never as a key.
3. **The wait:** 30 days by default; the owner picks 14, 30, 60 or 90 when adding the contact.
4. **Notices** at the start, every 7 days and on the last day, to every owner, every other recovery
   and legacy contact and every household adult.
5. **Any sign-in by the owner cancels the claim at once,** and the claim completes only if the owner
   did not sign in, use a key or approve anything for the whole wait (Google's inactivity idea).
6. **A second person** (another legacy contact or a household adult) must confirm when one exists
   (D-028); with nobody else, the wait, the notices and the inactivity check stand alone.
7. **Then** the contact gets a read-only export of the owner's Files home for 12 months. The data
   stays on the box afterwards: nothing here deletes anything, and a legacy contact never gets admin,
   other people's data, app secrets, sign-in keys or the recovery kit (the legacy principal reaches
   only `LEGACY_PATHS`; every other route answers 403).

Who owns the box after the owner's death is a separate, later question (N-9, 1.1).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import io
import os
import re
import secrets
import stat
import tarfile
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import DateTime, String, select, update
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..auth import Principal
from ..errors import ApiError
from ..identity.crypto import new_id
from ..identity.models import ApproverKeyRow, PasskeyRow, UserRow, iso
from ..ledger import Base, utc
from .contacts import ROLE_PATHS, RecoveryContacts
from .models import ContactRow

TS = DateTime(timezone=True)
WAIT_OPTIONS = (14, 30, 60, 90)  # D-028: the owner picks 14 to 90; 30 by default
DEFAULT_WAIT_DAYS = 30
EXPORT_WINDOW = timedelta(days=365)  # D-028: 12 months; the data is never deleted afterwards
NOTICE_EVERY = timedelta(days=7)
# The gateway takes request bodies up to 256 KiB (guard.py); base64 grows a file by a third, so the phone app
# sends a downsized photo or a small PDF. Chunked uploads of bigger files are a follow-up.
MAX_CERTIFICATE_BYTES = 180 * 1024
MAX_EXPORT_BYTES = 20 * 1024 * 1024 * 1024
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ"  # no I, L, O: easy to read back
CERT_TYPES = {b"%PDF-": ("application/pdf", "pdf"), b"\xff\xd8\xff": ("image/jpeg", "jpg"),
              b"\x89PNG\r\n\x1a\n": ("image/png", "png")}
OPEN_STATES = ("waiting", "awaiting_second")
LEGACY_PATHS = [
    re.compile(r"/v1/legacy/contact(/[a-z-]+)?"),
    re.compile(r"/v1/legacy/claims(/lcl_[0-9A-Z]{26}/confirm)?"),
    re.compile(r"/v1/legacy/export(/download)?"),
]
ROLE_PATHS["legacy"] = LEGACY_PATHS


class ClaimRow(Base):
    """Feature "recovery": a new table, so create_all adds it at this shape."""

    __tablename__ = "recovery_legacy_claims"
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

    def __init__(self, gw, ident):
        super().__init__(gw, ident)
        self.dir = gw.settings.audit_path.parent / "recovery" / "legacy"
        self.files = None  # () -> the FilesService; set by the router (files registers after recovery)
        self.ended_hooks.append(self._contact_ended)
        gw.events.subscribe("auth.login.succeeded", self._owner_signed_in)

    # ---- contacts ------------------------------------------------------------------------------------
    def add_legacy(self, ctx, kind: str, display_name: str, household_user_id: str | None,
                   cooling_off_days: int | None, wait_days: int | None) -> dict:
        wait = DEFAULT_WAIT_DAYS if wait_days is None else wait_days
        if wait not in WAIT_OPTIONS:
            raise ApiError(422, "conflict", f"wait_days must be one of {list(WAIT_OPTIONS)}", reason="not_an_option")
        out = self.add(ctx, kind, display_name, household_user_id, cooling_off_days, extra={"wait_days": wait})
        return {**out, "wait_days": wait}

    def view(self, r: ContactRow) -> dict:
        return {**super().view(r), "wait_days": int((r.extra or {}).get("wait_days", DEFAULT_WAIT_DAYS))}

    def on_accept(self, contact_id: str) -> dict:
        key, salt = new_access_key(), secrets.token_bytes(16)
        with self.db.session.begin() as s:
            row = s.get(ContactRow, contact_id)
            row.extra = {**(row.extra or {}), "access_salt": salt.hex(), "access_verifier": verifier(salt, key)}
        return {"access_key": key}

    def contact_view(self, row: ContactRow) -> dict:
        return {**super().contact_view(row), "wait_days": int((row.extra or {}).get("wait_days", DEFAULT_WAIT_DAYS))}

    # ---- the claim -----------------------------------------------------------------------------------
    def _claim(self, claim_id: str) -> ClaimRow | None:
        with self.db.session() as s:
            return s.get(ClaimRow, claim_id)

    def _set(self, row: ClaimRow, **values) -> ClaimRow:
        with self.db.session.begin() as s:
            s.execute(update(ClaimRow).where(ClaimRow.id == row.id).values(**values))
        return self._claim(row.id)

    def claim_view(self, c: ClaimRow, *, for_household: bool = False) -> dict:
        contact = self._get(c.contact_id)
        out = {"id": c.id, "contact_id": c.contact_id, "state": c.state, "created_at": iso(c.created_at),
               "ends_at": iso(c.ends_at), "needs_second": c.needs_second, "second_confirmed": c.second_at is not None,
               "granted_at": iso(c.granted_at), "access_until": iso(c.access_until), "ended_at": iso(c.ended_at),
               "end_reason": c.end_reason, "certificate_type": c.certificate_type}
        if for_household:
            out["contact_display_name"] = contact.display_name if contact else None
        return out

    def _second_people(self, owner_id: str, claimant: ContactRow) -> bool:
        """Is there someone who can confirm: another usable legacy contact, or an active household adult?"""
        others = [r for r in self.usable(owner_id) if r.id != claimant.id]
        with self.db.session() as s:
            adults = list(s.scalars(select(UserRow.id).where(UserRow.role == "adult", UserRow.disabled.is_(False))))
        adults = [a for a in adults if a != claimant.household_user_id]
        return bool(others or adults)

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
        if open_ is not None:
            raise ApiError(409, "conflict", "a legacy claim for this owner is already open", reason="already_open")
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
        with self.db.session.begin() as s:
            s.add(row)
        self.tell(contact.owner_user_id, "legacy.claim.started",
                  {"claim_id": cid, "contact_id": contact.id, "ends_at": iso(row.ends_at)}, p, severity="critical")
        return self.claim_view(row)

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
        ext = next(e for t, e in CERT_TYPES.values() if t == c.certificate_type)
        return self._cert_path(c.id, ext).read_bytes(), c.certificate_type

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

    def cancel(self, p: Principal, claim_id: str, block: bool) -> dict:
        """The owner stops a claim (and, with block, removes that contact). L0: it only takes power away."""
        if not p.is_owner:
            raise self.ident.deny(p, "cancel a legacy claim", reason="owner_only")
        c = self._claim(claim_id)
        if c is None:
            raise ApiError(404, "not_found", "no such claim")
        if c.state in OPEN_STATES or c.state == "granted":
            c = self._end_claim(c, "cancelled", "owner_cancelled", p.id)
        if block:
            contact = self._get(c.contact_id)
            if contact is not None and contact.state in ("invited", "active"):
                self._end(contact, "removed")
                self.tell(c.owner_user_id, "legacy.contact.removed", {"contact_id": contact.id}, p)
        return self.claim_view(c, for_household=True)

    def _end_claim(self, c: ClaimRow, state: str, reason: str, by: str | None) -> ClaimRow:
        c = self._set(c, state=state, ended_at=self.now(), end_reason=reason, ended_by=by)
        self.tell(c.owner_user_id, f"legacy.claim.{state}", {"claim_id": c.id, "reason": reason}, severity="warning")
        return c

    def confirm(self, p: Principal, claim_id: str, contact: ContactRow | None) -> dict:
        """The second person: another usable legacy contact of the same owner, or a household adult."""
        if contact is None and not (p.kind == "person" and p.role == "adult"):
            raise self.ident.deny(p, "confirm a legacy claim", reason="adult_or_other_legacy_contact")
        c = self._claim(claim_id)
        if c is None:
            raise ApiError(404, "not_found", "no such claim")
        if contact is not None:
            if contact.owner_user_id != c.owner_user_id or contact.id == c.contact_id \
                    or self.state_of(contact) != "active":
                raise self.ident.deny(p, "confirm this legacy claim", reason="not_a_second_person")
        else:
            claimant = self._get(c.contact_id)
            if claimant is not None and claimant.household_user_id == p.id:
                raise self.ident.deny(p, "confirm your own legacy claim", reason="not_a_second_person")
        if c.state not in OPEN_STATES:
            raise ApiError(409, "conflict", f"this claim is {c.state}", reason=c.state)
        if c.second_at is None:
            c = self._set(c, second_by=p.id, second_at=self.now())
            self.tell(c.owner_user_id, "legacy.claim.confirmed", {"claim_id": c.id}, p, severity="warning")
        self.tick()
        return self.claim_view(self._claim(c.id))

    # ---- the owner's own activity ----------------------------------------------------------------------
    def _owner_signed_in(self, envelope: dict) -> None:
        user_id = (envelope.get("data") or {}).get("user_id")
        if not user_id:
            return
        with self.db.session() as s:
            rows = list(s.scalars(select(ClaimRow).where(ClaimRow.owner_user_id == user_id,
                                                         ClaimRow.state.in_(OPEN_STATES))))
        for c in rows:
            self._end_claim(c, "cancelled", "owner_signed_in", user_id)

    def _owner_active_since(self, owner_id: str, since: datetime) -> bool:
        with self.db.session() as s:
            u = s.get(UserRow, owner_id)
            key = s.scalar(select(PasskeyRow.id).where(PasskeyRow.user_id == owner_id, PasskeyRow.last_used_at > since))
            apk = s.scalar(select(ApproverKeyRow.id).where(ApproverKeyRow.user_id == owner_id,
                                                           ApproverKeyRow.last_used_at > since))
        seen = u is not None and u.last_seen_at is not None and utc(u.last_seen_at) > since
        return seen or key is not None or apk is not None

    def _contact_ended(self, contact: ContactRow) -> None:
        if contact.role != "legacy":
            return
        with self.db.session() as s:
            rows = list(s.scalars(select(ClaimRow).where(ClaimRow.contact_id == contact.id,
                                                         ClaimRow.state.in_((*OPEN_STATES, "granted")))))
        for c in rows:
            self._end_claim(c, "cancelled", "contact_ended", f"legacy:{contact.id}")

    # ---- the clock ------------------------------------------------------------------------------------
    def tick(self) -> int:
        """Notices during the wait; at the end, cancel if the owner was active, wait for the second person,
        or grant the 12-month read-only export. Idempotent."""
        now, done = self.now(), 0
        with self.db.session() as s:
            rows = list(s.scalars(select(ClaimRow).where(ClaimRow.state.in_(OPEN_STATES))))
        for c in rows:
            start = utc(c.created_at)
            if self._owner_active_since(c.owner_user_id, start):
                self._end_claim(c, "cancelled", "owner_active", None)
                done += 1
                continue
            if now < utc(c.ends_at):
                due = [f"week{n}" for n in range(1, int((now - start) / NOTICE_EVERY) + 1)]
                if utc(c.ends_at) - now <= timedelta(days=1):
                    due.append("last_day")
                new = [d for d in due if d not in (c.notices_sent or [])]
                if new:
                    self._set(c, notices_sent=[*(c.notices_sent or []), *new])
                    self.tell(c.owner_user_id, "legacy.claim.reminder",
                              {"claim_id": c.id, "ends_at": iso(c.ends_at), "notice": new[-1]}, severity="critical")
                    done += 1
                continue
            if c.needs_second and c.second_at is None:
                if c.state != "awaiting_second":
                    self._set(c, state="awaiting_second")
                    self.tell(c.owner_user_id, "legacy.claim.awaiting_second", {"claim_id": c.id}, severity="warning")
                    done += 1
                continue
            self._set(c, state="granted", granted_at=now, access_until=now + EXPORT_WINDOW)
            self.tell(c.owner_user_id, "legacy.claim.granted",
                      {"claim_id": c.id, "access_until": iso(now + EXPORT_WINDOW)}, severity="critical")
            done += 1
        return done

    # ---- the read-only export -----------------------------------------------------------------------------
    def granted_claim(self, contact: ContactRow) -> ClaimRow:
        self.tick()
        with self.db.session() as s:
            c = s.scalar(select(ClaimRow).where(ClaimRow.contact_id == contact.id, ClaimRow.state == "granted")
                         .order_by(ClaimRow.granted_at.desc()))
        if c is None:
            raise ApiError(403, "permission_denied", "no granted legacy claim", reason="no_granted_claim")
        if c.access_until is None or utc(c.access_until) <= self.now():
            raise ApiError(403, "permission_denied", "the 12-month export window has ended; the data is still on the box",
                           reason="export_window_ended")
        return c

    def _walk(self, owner_id: str):
        """(relative path, size, dir fd, name) of every regular file in the owner's Files home, without
        following a symlink anywhere (os.fwalk on directory descriptors)."""
        from ..files.access import Root

        files = self.files() if self.files is not None else None
        if files is None:
            raise ApiError(503, "unavailable", "the files service is not available", reason="files_unavailable")
        with files._space(Root("home", owner_id)) as home:
            for top, _dirs, names, dfd in os.fwalk(".", dir_fd=home, follow_symlinks=False):
                for name in sorted(names):
                    try:
                        st = os.stat(name, dir_fd=dfd, follow_symlinks=False)
                    except OSError:
                        continue
                    if stat.S_ISREG(st.st_mode):
                        rel = os.path.normpath(os.path.join(top, name))
                        yield rel, st.st_size, dfd, name

    def manifest(self, contact: ContactRow, p: Principal) -> dict:
        c = self.granted_claim(contact)
        items = [{"path": rel, "size": size} for rel, size, _fd, _n in self._walk(c.owner_user_id)]
        self.gw.audit.append("legacy.export.listed", p.as_dict(), None, {"claim_id": c.id, "files": len(items)})
        return {"claim_id": c.id, "access_until": iso(c.access_until), "files": items,
                "total_bytes": sum(i["size"] for i in items), "read_only": True}

    def archive(self, contact: ContactRow, p: Principal):
        """A tar of the owner's Files home, built in a private temporary file (read-only on the source)."""
        c = self.granted_claim(contact)
        tmp = tempfile.TemporaryFile()  # noqa: SIM115 - handed to the streaming response, closed there
        total = 0
        with tarfile.open(fileobj=tmp, mode="w") as tar:
            for rel, size, dfd, name in self._walk(c.owner_user_id):
                total += size
                if total > MAX_EXPORT_BYTES:
                    raise ApiError(413, "payload_too_large", "the export is larger than one download; use a USB copy",
                                   reason="export_too_large")
                try:
                    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dfd)
                except OSError:
                    continue
                with os.fdopen(fd, "rb") as f:
                    info = tarfile.TarInfo(rel)
                    info.size = os.fstat(f.fileno()).st_size
                    info.mode = 0o644
                    tar.addfile(info, io.BufferedReader(f))  # type: ignore[arg-type]
        tmp.seek(0)
        self.gw.audit.append("legacy.export.downloaded", p.as_dict(), None, {"claim_id": c.id, "bytes": total})
        return tmp
