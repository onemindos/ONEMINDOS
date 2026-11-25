# SPDX-License-Identifier: Apache-2.0
"""App passwords: per-person credentials for WebDAV clients (files-webdav, #722).

Finder, GNOME Files (gio davs://) and other WebDAV clients can only send a user name and a password
(HTTP Basic). A gateway token must never travel that way: it opens the whole API, it would sit in the
macOS keychain of every Mac that mounts the box, and the client cannot do a passkey. So each person
makes app passwords of their own, one per device, each with scopes, and revokes them one by one.

Rules kept here:
- Only a person with role owner or adult makes one, for themself (the roles that may mint their own
  tokens, `tokens:self`). Guests, children, agents and apps never get one.
- A password is shown once. The box keeps its sha256 (the password is 100 random bits, so a fast hash
  is enough, as for tokens) and never logs or returns it.
- Scopes say which spaces it reaches and how: `home:r|rw`, `shared:r|rw`. What it may really do is
  the lower of its scope and what the person's role allows today (files/access.py).
- Revoking deletes the row; every WebDAV request looks the row up again, so the next request fails.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import datetime
from typing import Annotated

from pydantic import ConfigDict, Field
from sqlalchemy import DateTime, String, delete, func, select, update
from sqlalchemy.orm import Mapped, mapped_column

from ..auth import Principal
from ..errors import ApiError
from ..jsonbody import JsonBody
from ..ledger import Base, iso
from ..store import FeatureSchema, SqlRepository
from .store import new_id

SCHEMA = FeatureSchema("webdav")  # version 1 = the shape below
CREATE_ROLES = frozenset({"owner", "adult"})
MAX_PER_PERSON = 20
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o, 1/l/i: read off one screen, typed on another
PASSWORD_RE = re.compile(rf"^[{ALPHABET}]{{4}}(-[{ALPHABET}]{{4}}){{4}}$")
SCOPE_RE = r"^(home|shared):(r|rw)$"


class CreateBody(JsonBody):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=64, pattern=r"^[^\x00-\x1f\x7f]+$",
                       description="Which device or app uses it, e.g. 'MacBook Finder'")
    scopes: list[Annotated[str, Field(pattern=SCOPE_RE)]] = Field(
        min_length=1, max_length=2, description="home:r, home:rw, shared:r or shared:rw; each space once")


class AppPasswordRow(Base):
    __tablename__ = "webdav_app_passwords"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    person_id: Mapped[str] = mapped_column(String(200), index=True)
    label: Mapped[str] = mapped_column(String(64))
    scopes: Mapped[str] = mapped_column(String(40))              # "home:rw shared:r"
    secret_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def scope_map(self) -> dict[str, str]:
        """space kind -> 'r' | 'rw'."""
        return dict(s.split(":", 1) for s in self.scopes.split())

    def to_json(self) -> dict:
        return {"id": self.id, "person_id": self.person_id, "username": self.person_id, "label": self.label,
                "scopes": self.scopes.split(), "created_at": iso(self.created_at),
                "last_used_at": iso(self.last_used_at) if self.last_used_at else None}


def digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class AppPasswordRepository(SqlRepository):
    def all(self, person_id: str | None = None) -> list[AppPasswordRow]:
        with self.db.session() as s:
            q = select(AppPasswordRow).order_by(AppPasswordRow.created_at, AppPasswordRow.id)
            if person_id is not None:
                q = q.where(AppPasswordRow.person_id == person_id)
            rows = list(s.scalars(q))
            s.expunge_all()
            return rows

    def count(self, person_id: str) -> int:
        with self.db.session() as s:
            return s.scalar(select(func.count()).select_from(AppPasswordRow)
                            .where(AppPasswordRow.person_id == person_id)) or 0

    def by_secret(self, secret: str) -> AppPasswordRow | None:
        with self.db.session() as s:
            row = s.scalars(select(AppPasswordRow).where(AppPasswordRow.secret_sha256 == digest(secret))).first()
            if row:
                s.expunge(row)
            return row

    def add(self, row: AppPasswordRow) -> None:
        with self.db.session.begin() as s:
            s.add(row)

    def touch(self, row_id: str, now: datetime) -> None:
        with self.db.session.begin() as s:
            s.execute(update(AppPasswordRow).where(AppPasswordRow.id == row_id).values(last_used_at=now))

    def remove(self, row_id: str) -> bool:
        with self.db.session.begin() as s:
            return s.execute(delete(AppPasswordRow).where(AppPasswordRow.id == row_id)).rowcount > 0


class AppPasswords:
    def __init__(self, gw):
        self.gw = gw
        self.repo = AppPasswordRepository(gw.db)

    def role_of(self, person_id: str) -> str | None:
        """A person's role now: the tokens file, then every people source (identity accounts)."""
        for p in self.gw.tokens.principals():
            if p.kind == "person" and p.id == person_id:
                return p.role
        for source in self.gw.people_sources:
            role = source().get(person_id)
            if role is not None:
                return role
        return None

    @staticmethod
    def may_hold(p: Principal) -> bool:
        return p.kind == "person" and p.role in CREATE_ROLES

    def list(self, p: Principal) -> list[dict]:
        return [r.to_json() for r in self.repo.all(None if p.is_owner else p.id)]

    def create(self, p: Principal, body: CreateBody) -> dict:
        scopes = sorted(set(body.scopes))
        kinds = [s.split(":", 1)[0] for s in scopes]
        if len(kinds) != len(set(kinds)):
            raise ApiError(422, "conflict", "scopes are home:r, home:rw, shared:r or shared:rw, each space once",
                           reason="invalid_scopes")
        if self.repo.count(p.id) >= MAX_PER_PERSON:
            raise ApiError(409, "policy_refused", f"You already have {MAX_PER_PERSON} app passwords; revoke one first.",
                           reason="too_many_app_passwords")
        secret = "-".join("".join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(5))
        row = AppPasswordRow(id=new_id("apw"), person_id=p.id, label=body.label, scopes=" ".join(scopes),
                             secret_sha256=digest(secret), created_at=self.gw.clock())
        self.repo.add(row)
        self.gw.audit.append("webdav.app_password.created", p.as_dict(), None,
                             {"id": row.id, "label": row.label, "scopes": scopes})
        return row.to_json() | {"password": secret, "shown_once": True}

    def revoke(self, p: Principal, row_id: str) -> dict:
        row = next((r for r in self.repo.all(None if p.is_owner else p.id) if r.id == row_id), None)
        if row is None or not self.repo.remove(row.id):
            raise ApiError(404, "not_found", f"There is no app password {row_id[:60]}.")
        self.gw.audit.append("webdav.app_password.revoked", p.as_dict(), None,
                             {"id": row.id, "person_id": row.person_id, "label": row.label})
        return {"revoked": True, "id": row.id}

    def check(self, username: str, secret: str) -> AppPasswordRow | None:
        """The live row for this user name and password, or None. Looked up on every request (no cache)."""
        if not PASSWORD_RE.match(secret):
            return None
        row = self.repo.by_secret(secret)
        if row is None or not hmac.compare_digest(row.person_id.encode(), username.encode()):
            return None
        return row
