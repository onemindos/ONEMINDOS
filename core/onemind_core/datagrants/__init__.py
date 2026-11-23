# SPDX-License-Identifier: Apache-2.0
"""The data commons (#615): data classes, grants per app, agent and person, and the shared records.

A data class is one of the five the built-in descriptors already name (sdk/schema/onemind.builtin.schema.json
$defs/dataClass). A grant gives one subject (an app's plugin, an agent, a person) some of read, write
and aggregate on one class until it expires or the owner revokes it. The rules:

- The owner holds every mode on every class, but only through a full owner session or token (or the
  static owner token): an owner API token narrowed to other scopes is a token's ceiling like anywhere
  else (identity/service.py _owner_wide), so it holds only what an ordinary caller holds. Every other
  principal starts with nothing, except read and aggregate on `public`. A caller without read gets
  empty data, not an error.
- A grant only comes from an approval: the subject (or the owner on its behalf) files a `data.grant`
  action, the approval card shows exactly what it would get, and only an owner approves it. Agents and
  plugins can file, never approve; no standing approval covers the type (it is not an automation type).
- Revoking is the owner's own de-escalation and takes effect at once: the next read is empty and an
  open stream ends within STREAM_POLL_S (the acceptance bound is 5 s).

Records are the commons itself: small JSON values in one class, written by a subject with write and
read back by subjects with read (aggregate sees only the count). Each writer keeps at most KEEP_RECORDS
per class; a full writer pushes out only its own oldest, never another writer's.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import JSON, Boolean, DateTime, Integer, String, func, select, update
from sqlalchemy.orm import Mapped, mapped_column

from ..actions import FeatureAction
from ..auth import Principal
from ..errors import ApiError
from ..executors import ExecResult
from ..identity.scopes import ALL
from ..ledger import Base, iso, utc
from ..plugins.auth import plugin_app_id
from ..store import FeatureSchema, SqlRepository

SCHEMA = FeatureSchema("datagrants")

# Same five as onemind.builtin.schema.json $defs/dataClass (a test keeps them equal).
DataClass = Literal["public", "owner", "private", "location", "activity"]
CLASSES: dict[str, str] = {
    "public": "Anything you would show anyone: names, public notes, shared lists.",
    "owner": "How the box itself is set up: settings, apps, approvals, updates.",
    "private": "Your own things: files, photos, messages, notes.",
    "location": "Where people and things are or have been.",
    "activity": "What people did and when: health, fitness, habits, usage.",
}
GRANTEE_KINDS = ("app", "agent", "person")
ACTION_TYPE = "data.grant"
MAX_GRANT_DAYS = 365
MAX_VALUE_BYTES = 4096
KEEP_RECORDS = 10_000  # per class and writer; that writer's oldest go first
STREAM_POLL_S = 1.0


class DataGrantRow(Base):
    __tablename__ = "datagrants_grants"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    data_class: Mapped[str] = mapped_column(String(16), index=True)
    grantee_kind: Mapped[str] = mapped_column(String(8))
    grantee_id: Mapped[str] = mapped_column(String(200), index=True)
    can_read: Mapped[bool] = mapped_column(Boolean)
    can_write: Mapped[bool] = mapped_column(Boolean)
    can_aggregate: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    requested_by: Mapped[str] = mapped_column(String(200))
    approved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    action_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String(200), nullable=True)


class DataRecordRow(Base):
    __tablename__ = "datagrants_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_class: Mapped[str] = mapped_column(String(16), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    value: Mapped[Any] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(200), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str | None] = mapped_column(String(80), nullable=True)


class Grantee(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["app", "agent", "person"]
    id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:@-]*$")


class DataGrantParams(BaseModel):
    """params of a data.grant request: what the approval card shows and the owner approves."""

    model_config = ConfigDict(extra="forbid")
    data_class: DataClass
    # Absent: the requester itself (an app's plugin, an agent). Only an owner may name someone else.
    grantee: Grantee | None = None
    read: bool = False
    write: bool = False
    aggregate: bool = False
    expires_in_days: int = Field(ge=1, le=MAX_GRANT_DAYS)

    @model_validator(mode="after")
    def _some_mode(self):
        if not (self.read or self.write or self.aggregate):
            raise ValueError("ask for at least one of read, write, aggregate")
        return self


class RecordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,62}$", description="What the value is, e.g. place.visit")
    value: Any = Field(description=f"Any JSON value, at most {MAX_VALUE_BYTES} bytes")


@dataclass(frozen=True)
class Access:
    read: bool = False
    write: bool = False
    aggregate: bool = False

    def as_dict(self) -> dict:
        return {"read": self.read, "write": self.write, "aggregate": self.aggregate}


def subject_of(kind: str, principal_id: str) -> tuple[str, str] | None:
    """The grantee a principal is: a plugin is its app, agents and people are themselves."""
    if kind == "plugin":
        app_id = plugin_app_id(principal_id)
        return ("app", app_id) if app_id else None
    if kind in ("agent", "person"):
        return kind, principal_id
    return None


def full_owner(p: Principal, scopes: frozenset[str] | None) -> bool:
    """The owner's standing access: a static owner token (scopes None) or an owner session or token
    holding every scope. A narrowed owner token is not one (scopes are the token's ceiling)."""
    return p.is_owner and (scopes is None or ALL in scopes)


def grant_json(row: DataGrantRow, now: datetime) -> dict:
    return {
        "id": row.id, "data_class": row.data_class,
        "grantee": {"kind": row.grantee_kind, "id": row.grantee_id},
        "read": row.can_read, "write": row.can_write, "aggregate": row.can_aggregate,
        "created_at": iso(row.created_at), "expires_at": iso(row.expires_at),
        "requested_by": row.requested_by, "approved_by": row.approved_by, "action_id": row.action_id,
        "revoked_at": iso(row.revoked_at), "revoked_by": row.revoked_by,
        "active": row.revoked_at is None and utc(row.expires_at) > now,
    }


def record_json(row: DataRecordRow) -> dict:
    return {"id": row.id, "data_class": row.data_class, "kind": row.kind, "value": row.value,
            "source": row.source, "created_at": iso(row.created_at)}


class DataGrants(SqlRepository):
    """Grants, the access check every data door asks, and the shared records."""

    def __init__(self, gw):
        super().__init__(gw.db)
        self.gw = gw
        gw.actions.register_type(ACTION_TYPE, FeatureAction(
            risk="sensitive", run=self._run, requesters=frozenset({"person", "agent", "plugin"}),
            params_model=DataGrantParams, check_request=self._check_request,
        ))

    # ---- the check -----------------------------------------------------------------------------
    def access(self, p: Principal, data_class: str, *, scopes: frozenset[str] | None) -> Access:
        """What `p` may do with the class. `scopes` is the caller's token or session ceiling
        (identity AuthContext.scopes), None for a static-file token."""
        if full_owner(p, scopes):
            return Access(True, True, True)
        public = data_class == "public"
        read, write, aggregate = public, False, public
        subject = subject_of(p.kind, p.id)
        if subject is not None:
            now = self.gw.clock()
            with self.db.session() as s:
                rows = s.scalars(select(DataGrantRow).where(
                    DataGrantRow.data_class == data_class, DataGrantRow.grantee_kind == subject[0],
                    DataGrantRow.grantee_id == subject[1], DataGrantRow.revoked_at.is_(None))).all()
            for g in rows:
                if utc(g.expires_at) > now:
                    read, write, aggregate = read or g.can_read, write or g.can_write, aggregate or g.can_aggregate
        return Access(read, write, aggregate or read)

    # ---- grants --------------------------------------------------------------------------------
    def _check_request(self, params: dict, p: Principal) -> None:
        own = subject_of(p.kind, p.id)
        named = params.get("grantee")
        if p.is_owner:
            if named is None:
                raise ApiError(422, "conflict", "request failed validation: params.grantee: the owner already holds "
                                                "every class; name who the grant is for")
            return
        if own is None or (named is not None and (named["kind"], named["id"]) != own):
            raise ApiError(403, "permission_denied", "only an owner may ask for data access on someone else's behalf")

    def _run(self, action, finish) -> None:
        params = action.params
        named = params.get("grantee")
        subject = (named["kind"], named["id"]) if named else subject_of(
            action.requested_by.get("kind", ""), action.requested_by.get("id", ""))
        if subject is None:
            finish(ExecResult("failed", "the requester is not an app, agent or person"))
            return
        now = self.gw.clock()
        fresh = self.gw.repo.get(action.id)  # run() gets the request as filed; approval is on the stored row
        row = DataGrantRow(
            id="dgr_" + secrets.token_hex(8), data_class=params["data_class"],
            grantee_kind=subject[0], grantee_id=subject[1],
            can_read=bool(params.get("read")), can_write=bool(params.get("write")),
            can_aggregate=bool(params.get("aggregate")),
            created_at=now, expires_at=now + timedelta(days=int(params["expires_in_days"])),
            requested_by=str(action.requested_by.get("id")), approved_by=fresh.approved_by if fresh else None, action_id=action.id,
        )
        with self.db.session.begin() as s:
            # One live grant per class and subject: the approved one replaces what was there.
            s.execute(update(DataGrantRow).where(
                DataGrantRow.data_class == row.data_class, DataGrantRow.grantee_kind == row.grantee_kind,
                DataGrantRow.grantee_id == row.grantee_id, DataGrantRow.revoked_at.is_(None),
            ).values(revoked_at=now, revoked_by=f"superseded:{row.id}"))
            s.add(row)
        self.gw.events.publish_event("data", "grant.created", {
            "grant_id": row.id, "data_class": row.data_class,
            "grantee": {"kind": row.grantee_kind, "id": row.grantee_id},
        }, action_id=action.id)
        finish(ExecResult("succeeded", f"granted {row.data_class} to {row.grantee_kind} {row.grantee_id}",
                          steps=[{"step": "grant", "grant_id": row.id}]))

    def grants(self, p: Principal, *, scopes: frozenset[str] | None) -> list[dict]:
        now = self.gw.clock()
        q = select(DataGrantRow).order_by(DataGrantRow.created_at.desc(), DataGrantRow.id)
        if not full_owner(p, scopes):
            subject = subject_of(p.kind, p.id)
            if subject is None:
                return []
            q = q.where(DataGrantRow.grantee_kind == subject[0], DataGrantRow.grantee_id == subject[1])
        with self.db.session() as s:
            return [grant_json(r, now) for r in s.scalars(q.limit(1000)).all()]

    def revoke(self, p: Principal, grant_id: str) -> dict:
        if not p.is_owner:
            self.gw.audit.append("authz.denied", p.as_dict(), None,
                                 {"attempted": "revoke data grant", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", f"{p.kind}/{p.role} may not revoke data grants")
        now = self.gw.clock()
        with self.db.session.begin() as s:
            row = s.get(DataGrantRow, grant_id)
            if row is None:
                raise ApiError(404, "not_found", "no such data grant")
            changed = row.revoked_at is None
            if changed:
                row.revoked_at, row.revoked_by = now, p.id
            out = grant_json(row, now)
        if changed:
            self.gw.events.publish_event("data", "grant.revoked", {
                "grant_id": grant_id, "data_class": out["data_class"], "grantee": out["grantee"],
            }, principal=p.as_dict())
        return out

    # ---- records -------------------------------------------------------------------------------
    def write(self, p: Principal, data_class: str, body: RecordIn, idempotency_key: str | None = None, *,
              scopes: frozenset[str] | None) -> dict:
        if not self.access(p, data_class, scopes=scopes).write:
            self.gw.audit.append("authz.denied", p.as_dict(), None,
                                 {"attempted": f"write {data_class} data", "reason": "no_grant"})
            raise ApiError(403, "permission_denied", f"no write grant on {data_class}", reason="no_grant")
        try:
            size = len(json.dumps(body.value, separators=(",", ":"), allow_nan=False).encode())
        except ValueError as exc:
            raise ApiError(422, "conflict", "value must be plain JSON") from exc
        if size > MAX_VALUE_BYTES:
            raise ApiError(422, "conflict", f"value is {size} bytes; the limit is {MAX_VALUE_BYTES}")
        row = DataRecordRow(data_class=data_class, kind=body.kind, value=body.value, source=p.id,
                            created_at=self.gw.clock(), idempotency_key=idempotency_key)
        with self.db.session.begin() as s:
            if idempotency_key is not None:
                seen = s.scalar(select(DataRecordRow).where(DataRecordRow.source == p.id,
                                                            DataRecordRow.idempotency_key == idempotency_key))
                if seen is not None:
                    if (seen.data_class, seen.kind, seen.value) != (data_class, body.kind, body.value):
                        raise ApiError(409, "conflict", "Idempotency-Key was already used for a different record")
                    return record_json(seen)
            s.add(row)
            s.flush()
            # The cap is per writer: a writer that is full pushes out its own oldest, never anyone else's.
            mine = (DataRecordRow.data_class == data_class, DataRecordRow.source == p.id)
            floor = s.scalar(select(DataRecordRow.id).where(*mine)
                             .order_by(DataRecordRow.id.desc()).offset(KEEP_RECORDS).limit(1))
            if floor is not None:
                s.execute(DataRecordRow.__table__.delete().where(*mine, DataRecordRow.id <= floor))
        self.gw.audit.append("data.record.written", p.as_dict(), None,
                             {"data_class": data_class, "record_id": row.id, "kind": row.kind})
        return record_json(row)

    def read(self, p: Principal, data_class: str, after_id: int = 0, limit: int = 100, *,
             scopes: frozenset[str] | None) -> dict:
        acc = self.access(p, data_class, scopes=scopes)
        out: dict = {"data_class": data_class, "access": acc.as_dict(), "count": None, "records": []}
        if not (acc.read or acc.aggregate):
            return out  # no grant: empty data, not an error
        with self.db.session() as s:
            out["count"] = s.scalar(select(func.count()).select_from(DataRecordRow)
                                    .where(DataRecordRow.data_class == data_class))
            if acc.read:
                out["records"] = [record_json(r) for r in s.scalars(
                    select(DataRecordRow).where(DataRecordRow.data_class == data_class, DataRecordRow.id > after_id)
                    .order_by(DataRecordRow.id).limit(limit)).all()]
        return out

    def classes(self, p: Principal, descriptors: dict, *, scopes: frozenset[str] | None) -> list[dict]:
        out = []
        for name, about in CLASSES.items():
            owned = sorted(d.id for d in descriptors.values() if name in d.spec.get("data", {}).get("owns", []))
            reads = sorted(d.id for d in descriptors.values() if name in d.spec.get("data", {}).get("reads", []))
            out.append({"id": name, "description": about, "owned_by": owned, "read_by": reads,
                        "access": self.access(p, name, scopes=scopes).as_dict()})
        return out
