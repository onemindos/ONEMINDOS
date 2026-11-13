"""Action ledger: the record of every state-changing request (contract section 3, D-B9.5 subset).

The ledger sits behind a small repository interface (ActionRepository). The SQLAlchemy
implementation runs on SQLite by default and on PostgreSQL (BD-04) when ONEMIND_DB_URL is a
postgresql+psycopg:// URL. State changes use compare-and-swap (UPDATE ... WHERE state IN ...),
so two approvals racing for one action cannot both dispatch it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy import JSON, DateTime, Integer, String, create_engine, delete, select, update
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

# requested -> awaiting_approval -> accepted -> dispatched -> succeeded | failed | outcome_unknown
# awaiting_approval -> expired | cancelled (contract section 3). A stale precondition at approval
# leaves the action in awaiting_approval and answers 409 stale_precondition.
STATES = (
    "requested",
    "awaiting_approval",
    "accepted",
    "dispatched",
    "succeeded",
    "failed",
    "outcome_unknown",
    "expired",
    "cancelled",
)
TERMINAL = frozenset({"succeeded", "failed", "outcome_unknown", "expired", "cancelled"})
ALLOWED = {
    "requested": {"awaiting_approval", "expired", "cancelled"},
    "awaiting_approval": {"accepted", "expired", "cancelled"},
    "accepted": {"dispatched", "failed", "outcome_unknown"},
    "dispatched": {"succeeded", "failed", "outcome_unknown"},
}


def utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def iso(dt: datetime | None) -> str | None:
    return None if dt is None else utc(dt).isoformat().replace("+00:00", "Z")


@dataclass
class Action:
    id: str
    type: str
    params: dict
    state: str
    requested_by: dict
    idempotency_key: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    decided_by: dict | None = None
    decided_at: datetime | None = None
    result: dict | None = None
    version: int = 1
    # Contract §12.4: the plan rendered at request time, its hash, and live progress {step, pct}.
    plan: dict | None = None
    plan_sha256: str | None = None
    progress: dict | None = None
    risk: str | None = None
    approved_by: str | None = None

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "params": self.params,
            "state": self.state,
            "requested_by": self.requested_by,
            "idempotency_key": self.idempotency_key,
            "created_at": iso(self.created_at),
            "updated_at": iso(self.updated_at),
            "expires_at": iso(self.expires_at),
            "decided_by": self.decided_by,
            "decided_at": iso(self.decided_at),
            "approved_by": self.approved_by,
            "result": self.result,
            "version": self.version,
            "risk": self.risk,
            "plan": self.plan,
            "plan_sha256": self.plan_sha256,
            "progress": self.progress,
        }


@dataclass
class AppState:
    app_id: str
    status: str  # installing | installed | removing | failed | unknown
    updated_at: datetime
    action_id: str | None = None
    extra: dict = field(default_factory=dict)


class ActionRepository(Protocol):
    def create(self, action: Action) -> tuple[Action, bool]: ...
    def get(self, action_id: str) -> Action | None: ...
    def get_by_idempotency_key(self, key: str) -> Action | None: ...
    def list(self, states: set[str] | None = None) -> list[Action]: ...
    def transition(
        self, action_id: str, from_states: set[str], to_state: str, now: datetime, **fields
    ) -> Action | None: ...
    def accept_and_claim(
        self, action_id: str, now: datetime, decided_by: dict, app_id: str,
        claim: str, allowed: set[str], allow_absent: bool,
    ) -> str: ...
    def set_progress(self, action_id: str, progress: dict, now: datetime) -> None: ...
    def get_runtime(self, app_id: str) -> "AppRuntime | None": ...
    def set_runtime(self, app_id: str, now: datetime, **fields) -> None: ...
    def delete_runtime(self, app_id: str) -> None: ...
    def get_app_state(self, app_id: str) -> AppState | None: ...
    def set_app_state(self, app_id: str, status: str | None, now: datetime, action_id: str | None = None) -> None: ...
    def list_app_states(self) -> dict[str, AppState]: ...
    def issue_agent_token(self, principal_id: str, app_id: str, token_hash: str, now: datetime) -> None: ...
    def agent_principal_for(self, token_hash: str) -> str | None: ...
    def revoke_agent_token(self, principal_id: str, now: datetime) -> bool: ...


@dataclass
class AppRuntime:
    """What the gateway knows about an app beyond its status: version, bundle hash, settings."""

    app_id: str
    version: str | None = None
    previous_version: str | None = None
    bundle_sha256: str | None = None
    settings: dict = field(default_factory=dict)  # non-secret settings applied by app.configure


class Base(DeclarativeBase):
    pass


class ActionRow(Base):
    __tablename__ = "actions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    type: Mapped[str] = mapped_column(String(64))
    params: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(32), index=True)
    requested_by: Mapped[dict] = mapped_column(JSON)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    # Core schema v2 (store.py): the lifecycle columns.
    plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    plan_sha256: Mapped[str | None] = mapped_column(String(80), nullable=True)
    progress: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    risk: Mapped[str | None] = mapped_column(String(16), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)


class AppRuntimeRow(Base):
    """Core schema v2: per-app version history and applied settings (app lifecycle, PD-03..07)."""

    __tablename__ = "app_runtime"
    app_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    previous_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bundle_sha256: Mapped[str | None] = mapped_column(String(80), nullable=True)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AppStateRow(Base):
    __tablename__ = "app_states"
    app_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    action_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class AgentTokenRow(Base):
    """§11.2 agent principals issued to apps. Only the sha256 of the token is stored."""

    __tablename__ = "agent_tokens"
    principal_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    app_id: Mapped[str] = mapped_column(String(64))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def _to_action(r: ActionRow) -> Action:
    return Action(
        id=r.id,
        type=r.type,
        params=dict(r.params),
        state=r.state,
        requested_by=dict(r.requested_by),
        idempotency_key=r.idempotency_key,
        created_at=utc(r.created_at),
        updated_at=utc(r.updated_at),
        expires_at=utc(r.expires_at),
        decided_by=dict(r.decided_by) if r.decided_by else None,
        decided_at=utc(r.decided_at) if r.decided_at else None,
        result=dict(r.result) if r.result else None,
        version=r.version,
        plan=dict(r.plan) if r.plan else None,
        plan_sha256=r.plan_sha256,
        progress=dict(r.progress) if r.progress else None,
        risk=r.risk,
        approved_by=r.approved_by,
    )


def make_engine(db_url: str) -> Engine:
    url = make_url(db_url)
    if url.get_backend_name() == "sqlite":
        db = url.database
        if db and db != ":memory:":
            Path(db).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(db_url, connect_args={"check_same_thread": False})
    if url.get_backend_name() == "postgresql" and url.drivername == "postgresql":
        # Plain postgresql:// would pick psycopg2; we ship psycopg (v3).
        url = url.set(drivername="postgresql+psycopg")
    return create_engine(url, pool_pre_ping=True)


class SqlActionRepository:
    def __init__(self, engine: Engine):
        self.engine = engine
        Base.metadata.create_all(engine)
        self._session = sessionmaker(engine, expire_on_commit=False)

    @classmethod
    def from_url(cls, db_url: str) -> "SqlActionRepository":
        return cls(make_engine(db_url))

    def close(self) -> None:
        """Close every pooled database connection (on shutdown)."""
        self.engine.dispose()

    def create(self, action: Action) -> tuple[Action, bool]:
        """Insert; if the idempotency key exists already, return that action and False."""
        row = ActionRow(**{k: getattr(action, k) for k in ActionRow.__table__.columns.keys()})
        try:
            with self._session.begin() as s:
                s.add(row)
            return action, True
        except IntegrityError:
            existing = self.get_by_idempotency_key(action.idempotency_key)
            if existing is None:
                raise
            return existing, False

    def get(self, action_id: str) -> Action | None:
        with self._session() as s:
            r = s.get(ActionRow, action_id)
            return _to_action(r) if r else None

    def get_by_idempotency_key(self, key: str) -> Action | None:
        with self._session() as s:
            r = s.scalars(select(ActionRow).where(ActionRow.idempotency_key == key)).first()
            return _to_action(r) if r else None

    def list(self, states: set[str] | None = None) -> list[Action]:
        """Every action, newest first (section 3 defines no pagination or limit)."""
        q = select(ActionRow).order_by(ActionRow.created_at.desc())
        if states is not None:
            q = q.where(ActionRow.state.in_(states))
        with self._session() as s:
            rows = s.scalars(q)
            return [_to_action(r) for r in rows]

    def transition(
        self, action_id: str, from_states: set[str], to_state: str, now: datetime, **fields
    ) -> Action | None:
        """Compare-and-swap: move to to_state only if the action is still in one of from_states."""
        for f in from_states:
            if to_state not in ALLOWED.get(f, set()):
                raise ValueError(f"illegal transition {f} -> {to_state}")
        with self._session.begin() as s:
            res = s.execute(
                update(ActionRow)
                .where(ActionRow.id == action_id, ActionRow.state.in_(from_states))
                .values(state=to_state, updated_at=now, version=ActionRow.version + 1, **fields)
            )
            if res.rowcount != 1:
                return None
        return self.get(action_id)

    def _insert(self):
        return (postgresql if self.engine.dialect.name == "postgresql" else sqlite).insert

    def accept_and_claim(
        self, action_id: str, now: datetime, decided_by: dict, app_id: str,
        claim: str, allowed: set[str], allow_absent: bool,
    ) -> str:
        """In one transaction: move the action awaiting_approval -> accepted and claim its app.

        The claim is a compare-and-swap on app_states: UPDATE ... WHERE status IN allowed, or (when
        the app may have no row, i.e. a fresh install) INSERT ... ON CONFLICT DO NOTHING. Two
        different actions for one app therefore cannot both reach the executor.
        Returns "accepted", "conflict" (the action was no longer awaiting_approval) or "stale"
        (the app was not in an allowed state; nothing is changed).
        """

        class _Lost(Exception):
            pass

        try:
            with self._session.begin() as s:
                res = s.execute(
                    update(ActionRow)
                    .where(ActionRow.id == action_id, ActionRow.state == "awaiting_approval")
                    .values(
                        state="accepted", updated_at=now, version=ActionRow.version + 1,
                        decided_by=decided_by, decided_at=now, approved_by=decided_by["id"],
                    )
                )
                if res.rowcount != 1:
                    return "conflict"
                res = s.execute(
                    update(AppStateRow)
                    .where(AppStateRow.app_id == app_id, AppStateRow.status.in_(allowed))
                    .values(status=claim, updated_at=now, action_id=action_id)
                )
                claimed = res.rowcount == 1
                if not claimed and allow_absent:
                    res = s.execute(
                        self._insert()(AppStateRow)
                        .values(app_id=app_id, status=claim, updated_at=now, action_id=action_id)
                        .on_conflict_do_nothing(index_elements=[AppStateRow.app_id])
                        .returning(AppStateRow.app_id)
                    )
                    # rowcount is -1 for INSERT ... ON CONFLICT under psycopg 3; RETURNING tells us
                    # whether the row was inserted on both PostgreSQL and SQLite.
                    claimed = res.first() is not None
                if not claimed:
                    raise _Lost  # roll back the accepted transition too
        except _Lost:
            return "stale"
        return "accepted"

    def set_progress(self, action_id: str, progress: dict, now: datetime) -> None:
        with self._session.begin() as s:
            s.execute(update(ActionRow).where(ActionRow.id == action_id).values(progress=progress, updated_at=now))

    def get_runtime(self, app_id: str) -> AppRuntime | None:
        with self._session() as s:
            r = s.get(AppRuntimeRow, app_id)
            if r is None:
                return None
            return AppRuntime(r.app_id, r.version, r.previous_version, r.bundle_sha256, dict(r.settings or {}))

    def set_runtime(self, app_id: str, now: datetime, **fields) -> None:
        """Upsert; only the given fields (version, previous_version, bundle_sha256, settings) change."""
        insert_values = {"version": None, "previous_version": None, "bundle_sha256": None, "settings": {}, **fields}
        with self._session.begin() as s:
            s.execute(
                self._insert()(AppRuntimeRow)
                .values(app_id=app_id, updated_at=now, **insert_values)
                .on_conflict_do_update(index_elements=[AppRuntimeRow.app_id], set_={"updated_at": now, **fields})
            )

    def delete_runtime(self, app_id: str) -> None:
        with self._session.begin() as s:
            s.execute(delete(AppRuntimeRow).where(AppRuntimeRow.app_id == app_id))

    def get_app_state(self, app_id: str) -> AppState | None:
        with self._session() as s:
            r = s.get(AppStateRow, app_id)
            return AppState(r.app_id, r.status, utc(r.updated_at), r.action_id) if r else None

    def set_app_state(self, app_id: str, status: str | None, now: datetime, action_id: str | None = None) -> None:
        """Upsert (INSERT ... ON CONFLICT DO UPDATE); status=None removes the row (not installed)."""
        with self._session.begin() as s:
            if status is None:
                s.execute(delete(AppStateRow).where(AppStateRow.app_id == app_id))
                return
            values = {"status": status, "updated_at": now, "action_id": action_id}
            s.execute(
                self._insert()(AppStateRow)
                .values(app_id=app_id, **values)
                .on_conflict_do_update(index_elements=[AppStateRow.app_id], set_=values)
            )

    def list_app_states(self) -> dict[str, AppState]:
        with self._session() as s:
            return {
                r.app_id: AppState(r.app_id, r.status, utc(r.updated_at), r.action_id)
                for r in s.scalars(select(AppStateRow))
            }


    # ---- §11.2 agent principals ---------------------------------------------------------
    def issue_agent_token(self, principal_id: str, app_id: str, token_hash: str, now: datetime) -> None:
        """Store (or replace, on reinstall) the token hash of an app's agent principal."""
        values = {"app_id": app_id, "token_hash": token_hash, "issued_at": now, "revoked_at": None}
        with self._session.begin() as s:
            s.execute(
                self._insert()(AgentTokenRow)
                .values(principal_id=principal_id, **values)
                .on_conflict_do_update(index_elements=[AgentTokenRow.principal_id], set_=values)
            )

    def agent_principal_for(self, token_hash: str) -> str | None:
        """The principal id whose live (not revoked) token has this hash."""
        with self._session() as s:
            return s.scalars(
                select(AgentTokenRow.principal_id).where(
                    AgentTokenRow.token_hash == token_hash, AgentTokenRow.revoked_at.is_(None)
                )
            ).first()

    def revoke_agent_token(self, principal_id: str, now: datetime) -> bool:
        """Revoke; True if a live token was revoked. The row stays as a record of the grant."""
        with self._session.begin() as s:
            res = s.execute(
                update(AgentTokenRow)
                .where(AgentTokenRow.principal_id == principal_id, AgentTokenRow.revoked_at.is_(None))
                .values(revoked_at=now)
                .returning(AgentTokenRow.principal_id)
            )
            return res.first() is not None


def new_action_id() -> str:
    return str(uuid.uuid4())
