# SPDX-License-Identifier: Apache-2.0
"""Automation tables (feature `automation`, version 1) and their repository.

Rules, their firings and dry runs, standing approvals (`automation_policies`) and the uses
counted against their limits, maintenance windows, and the automation kill switch. The limit
counter lives in the database, so a gateway restart cannot reset it (CORE-AUTO-3).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, UniqueConstraint, delete, func, select, update
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..ledger import Base, utc
from ..store import FeatureSchema, SqlRepository

SCHEMA = FeatureSchema("automation")


@SCHEMA.step(2, "gateway permissions PR 5: rules record proposed_by; legacy automation:* standing approvals pause")
def _automation_v2(conn) -> None:
    import json

    from sqlalchemy import inspect, text

    if "proposed_by" not in {c["name"] for c in inspect(conn).get_columns("automation_rules")}:
        conn.execute(text("ALTER TABLE automation_rules ADD COLUMN proposed_by JSON"))
    rows = conn.execute(text("SELECT id, allow FROM automation_policies WHERE state = 'active'")).all()
    for pid, allow in rows:
        allow = json.loads(allow) if isinstance(allow, str) else allow
        if "automation:*" in (allow or {}).get("requested_by", []):
            conn.execute(text("UPDATE automation_policies SET state = 'paused', revision = revision + 1 WHERE id = :i"),
                         {"i": pid})


@SCHEMA.step(3, "gateway permissions PR 7: standing approvals bind agents and plugins to their permanent principal id")
def _automation_v3(conn) -> None:
    from sqlalchemy import inspect, text

    if "principals" not in {c["name"] for c in inspect(conn).get_columns("automation_policies")}:
        conn.execute(text("ALTER TABLE automation_policies ADD COLUMN principals JSON"))


# Gateway permissions PR 9 (F-10, D-028): rule revisions, limits, notices, lapse, target, forever.
_V4_POLICY_COLUMNS = (
    ("max_uses", "INTEGER"), ("bytes_per_day", "INTEGER"), ("items_per_day", "INTEGER"),
    ("forever", "BOOLEAN DEFAULT FALSE"), ("notify_after", "VARCHAR(8) DEFAULT 'digest'"),
    ("lapse_unused_days", "INTEGER"), ("target", "JSON"), ("suspended_at", "TIMESTAMP WITH TIME ZONE"),
    ("suspended_reason", "VARCHAR(80)"), ("accept_injection_risk", "BOOLEAN DEFAULT FALSE"),
    ("created_from", "VARCHAR(64)"), ("revoked_at", "TIMESTAMP WITH TIME ZONE"), ("revoked_by", "JSON"),
    ("last_used_at", "TIMESTAMP WITH TIME ZONE"), ("uses", "INTEGER DEFAULT 0"),
    ("reviewed_at", "TIMESTAMP WITH TIME ZONE"), ("review_notified_at", "TIMESTAMP WITH TIME ZONE"),
)


@SCHEMA.step(4, "gateway permissions PR 9: max_uses, size caps, notices, unused lapse, target, forever, suspension, revoke")
def _automation_v4(conn) -> None:
    from sqlalchemy import inspect, text

    have = {c["name"] for c in inspect(conn).get_columns("automation_policies")}
    for name, kind in _V4_POLICY_COLUMNS:
        if name not in have:
            conn.execute(text(f"ALTER TABLE automation_policies ADD COLUMN {name} {kind}"))
    have = {c["name"] for c in inspect(conn).get_columns("automation_policy_uses")}
    for name, kind in (("size", "INTEGER DEFAULT 0"), ("items", "INTEGER DEFAULT 1")):
        if name not in have:
            conn.execute(text(f"ALTER TABLE automation_policy_uses ADD COLUMN {name} {kind}"))


_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_id(prefix: str) -> str:
    """A prefixed ULID (contract §12.1): 48-bit milliseconds + 80 random bits, Crockford base32."""
    n = (int(time.time() * 1000) << 80) | int.from_bytes(os.urandom(10), "big")
    chars = []
    for _ in range(26):
        n, r = divmod(n, 32)
        chars.append(_CROCKFORD[r])
    return prefix + "".join(reversed(chars))


class RuleRow(Base):
    __tablename__ = "automation_rules"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    trigger: Mapped[dict] = mapped_column(JSON)
    conditions: Mapped[list] = mapped_column(JSON)
    actions: Mapped[list] = mapped_column(JSON)
    options: Mapped[dict] = mapped_column(JSON)
    approval_policy_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_by: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Scheduler state: the last minute evaluated, the last fire, and the actions whose outcome
    # the breaker has not counted yet.
    cursor_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pending_action_ids: Mapped[list] = mapped_column(JSON, default=list)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    breaker: Mapped[str] = mapped_column(String(8), default="closed")
    # Who asked for this rule when someone other than its author did (an agent's proposal); null for a
    # rule a person wrote by hand. A proposed rule never matches a wildcard standing approval.
    proposed_by: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class FireRow(Base):
    __tablename__ = "automation_fires"
    __table_args__ = (UniqueConstraint("rule_id", "slot", name="uq_automation_fires_rule_slot"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(40), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    slot: Mapped[str] = mapped_column(String(120))  # cron:<local minute> or event:<event id>
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    trigger_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    action_ids: Mapped[list] = mapped_column(JSON, default=list)
    outcome: Mapped[str] = mapped_column(String(32))
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class DryRunRow(Base):
    __tablename__ = "automation_dry_runs"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(40), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict] = mapped_column(JSON)


class PolicyRow(Base):
    __tablename__ = "automation_policies"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    allow: Mapped[dict] = mapped_column(JSON)
    per_day: Mapped[int] = mapped_column(Integer)
    window_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(16), default="active")  # active | paused | deleted
    lock_seq: Mapped[int] = mapped_column(Integer, default=0)  # bumped to serialise the counter
    # Gateway permissions PR 7: for each agent or plugin in allow.requested_by, the permanent id it was
    # bound to ({"agent:notes": {"uid": "prn_...", "owner_user_id": ...}}). A requester whose live id
    # differs (the token was revoked, the app reinstalled, the id taken by someone else) is not covered.
    principals: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Gateway permissions PR 9 (design §3.6). A forever rule keeps expires_at at FOREVER.
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)  # total uses; then it ends itself
    bytes_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    items_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    forever: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_after: Mapped[str] = mapped_column(String(8), default="digest")  # each | digest | silent
    lapse_unused_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspended_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    accept_injection_risk: Mapped[bool] = mapped_column(Boolean, default=False)
    created_from: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    uses: Mapped[int] = mapped_column(Integer, default=0)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PolicyUseRow(Base):
    __tablename__ = "automation_policy_uses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    policy_id: Mapped[str] = mapped_column(String(40), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    action_id: Mapped[str] = mapped_column(String(36), unique=True)
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    size: Mapped[int] = mapped_column(Integer, default=0)  # bytes this use wrote (PR 9 size caps)
    items: Mapped[int] = mapped_column(Integer, default=1)


class WindowRow(Base):
    __tablename__ = "automation_windows"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    tz: Mapped[str] = mapped_column(String(64))
    ranges: Mapped[list] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StateRow(Base):
    """One row, id "global": the automation kill switch."""

    __tablename__ = "automation_state"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    changed_by: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


DEFAULT_WINDOW = {"id": "win_nightly", "name": "nightly", "tz": "box",
                  "ranges": [{"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
                              "start": "02:00", "end": "05:00"}]}


@dataclass
class Rule:
    id: str
    name: str
    revision: int
    enabled: bool
    trigger: dict
    conditions: list
    actions: list
    options: dict
    approval_policy_id: str | None
    created_by: dict
    created_at: datetime
    updated_at: datetime
    cursor_at: datetime | None
    last_fired_at: datetime | None
    pending_action_ids: list
    failures: int
    breaker: str
    proposed_by: dict | None = None

    @property
    def principal_id(self) -> str:
        return f"automation:{self.id}"


def _rule(r: RuleRow) -> Rule:
    return Rule(
        r.id, r.name, r.revision, r.enabled, dict(r.trigger), list(r.conditions), list(r.actions),
        dict(r.options), r.approval_policy_id, dict(r.created_by), utc(r.created_at), utc(r.updated_at),
        utc(r.cursor_at) if r.cursor_at else None, utc(r.last_fired_at) if r.last_fired_at else None,
        list(r.pending_action_ids or []), r.failures, r.breaker,
        dict(r.proposed_by) if r.proposed_by else None,
    )


def _plain(row) -> dict:
    out = {c: getattr(row, c) for c in row.__table__.columns.keys()}
    for k, v in out.items():
        if isinstance(v, datetime):
            out[k] = utc(v)
    return out


class AutomationRepository(SqlRepository):
    # ---- kill switch -------------------------------------------------------------------------
    def state(self) -> dict:
        with self.db.session() as s:
            r = s.get(StateRow, "global")
            return _plain(r) if r else {"id": "global", "paused": False, "changed_by": None,
                                        "changed_at": None, "reason": None}

    def set_paused(self, paused: bool, by: dict, now: datetime, reason: str | None) -> None:
        values = {"paused": paused, "changed_by": by, "changed_at": now, "reason": reason}
        with self.db.session.begin() as s:
            s.execute(self.db.insert()(StateRow).values(id="global", **values)
                      .on_conflict_do_update(index_elements=[StateRow.id], set_=values))

    # ---- rules ---------------------------------------------------------------------------------
    def add_rule(self, **values) -> Rule:
        with self.db.session.begin() as s:
            s.add(RuleRow(pending_action_ids=[], failures=0, breaker="closed", **values))
        return self.get_rule(values["id"])  # type: ignore[return-value]

    def get_rule(self, rule_id: str) -> Rule | None:
        with self.db.session() as s:
            r = s.get(RuleRow, rule_id)
            return _rule(r) if r else None

    def list_rules(self, enabled: bool | None = None) -> list[Rule]:
        q = select(RuleRow).order_by(RuleRow.created_at, RuleRow.id)
        if enabled is not None:
            q = q.where(RuleRow.enabled.is_(enabled))
        with self.db.session() as s:
            return [_rule(r) for r in s.scalars(q)]

    def update_rule(self, rule_id: str, *, expect_revision: int | None = None, **values) -> bool:
        """Compare-and-swap on the revision when expect_revision is given; True if the row changed."""
        q = update(RuleRow).where(RuleRow.id == rule_id)
        if expect_revision is not None:
            q = q.where(RuleRow.revision == expect_revision)
        with self.db.session.begin() as s:
            return s.execute(q.values(**values)).rowcount == 1

    def delete_rule(self, rule_id: str) -> bool:
        with self.db.session.begin() as s:
            return s.execute(delete(RuleRow).where(RuleRow.id == rule_id)).rowcount == 1

    # ---- fires ---------------------------------------------------------------------------------
    def claim_fire(self, **values) -> bool:
        """Insert a fire for (rule, slot); False when that slot already fired."""
        with self.db.session.begin() as s:
            res = s.execute(
                self.db.insert()(FireRow).values(**values)
                .on_conflict_do_nothing(index_elements=[FireRow.rule_id, FireRow.slot])
                .returning(FireRow.id)
            )
            return res.first() is not None

    def finish_fire(self, fire_id: str, outcome: str, action_ids: list, detail: dict | None) -> None:
        with self.db.session.begin() as s:
            s.execute(update(FireRow).where(FireRow.id == fire_id)
                      .values(outcome=outcome, action_ids=action_ids, detail=detail))

    def list_fires(self, rule_id: str | None = None, limit: int = 100) -> list[dict]:
        q = select(FireRow).order_by(FireRow.fired_at.desc(), FireRow.id.desc()).limit(limit)
        if rule_id:
            q = q.where(FireRow.rule_id == rule_id)
        with self.db.session() as s:
            return [_plain(r) for r in s.scalars(q)]

    def last_requested_for(self, rule_id: str, resource_key: str, since: datetime) -> bool:
        with self.db.session() as s:
            return s.scalars(select(FireRow.id).where(
                FireRow.rule_id == rule_id, FireRow.resource_key == resource_key,
                FireRow.outcome == "requested", FireRow.fired_at > since,
            ).limit(1)).first() is not None

    # ---- dry runs ------------------------------------------------------------------------------
    def add_dry_run(self, **values) -> None:
        with self.db.session.begin() as s:
            s.add(DryRunRow(**values))

    def latest_dry_run(self, rule_id: str, revision: int) -> dict | None:
        with self.db.session() as s:
            r = s.scalars(select(DryRunRow).where(DryRunRow.rule_id == rule_id, DryRunRow.revision == revision)
                          .order_by(DryRunRow.created_at.desc()).limit(1)).first()
            return _plain(r) if r else None

    # ---- standing approvals --------------------------------------------------------------------
    @staticmethod
    def insert_policy(s: Session, **values) -> None:
        s.add(PolicyRow(**{"lock_seq": 0, "state": "active", "revision": 1, "uses": 0, "forever": False,
                           "notify_after": "digest", "accept_injection_risk": False, **values}))

    def add_policy(self, **values) -> dict:
        with self.db.session.begin() as s:
            self.insert_policy(s, **values)
        return self.get_policy(values["id"])  # type: ignore[return-value]

    def get_policy(self, policy_id: str) -> dict | None:
        with self.db.session() as s:
            r = s.get(PolicyRow, policy_id)
            return _plain(r) if r else None

    def list_policies(self, active_only: bool = True, *, with_paused: bool = False) -> list[dict]:
        q = select(PolicyRow).order_by(PolicyRow.created_at, PolicyRow.id)
        if active_only:
            q = q.where(PolicyRow.state.in_(("active", "paused") if with_paused else ("active",)))
        with self.db.session() as s:
            return [_plain(r) for r in s.scalars(q)]

    def delete_policy(self, policy_id: str) -> bool:
        with self.db.session.begin() as s:
            # One UPDATE sets the state and bumps the revision, so a use reserved against the old
            # revision (reserve_use matches revision and state in one statement) can never slip in.
            return s.execute(update(PolicyRow).where(PolicyRow.id == policy_id, PolicyRow.state.in_(("active", "paused")))
                             .values(state="deleted", revision=PolicyRow.revision + 1)).rowcount == 1

    def bind_principals(self, policy_id: str, principals: dict) -> None:
        with self.db.session.begin() as s:
            s.execute(update(PolicyRow).where(PolicyRow.id == policy_id).values(principals=principals))

    def bump_policies_for_window(self, window_id: str) -> list[str]:
        with self.db.session.begin() as s:
            ids = list(s.scalars(select(PolicyRow.id).where(PolicyRow.window_id == window_id,
                                                            PolicyRow.state == "active")))
            if ids:
                s.execute(update(PolicyRow).where(PolicyRow.id.in_(ids)).values(revision=PolicyRow.revision + 1))
            return ids

    def count_uses(self, policy_id: str, since: datetime) -> int:
        with self.db.session() as s:
            return s.scalar(select(func.count()).select_from(PolicyUseRow).where(
                PolicyUseRow.policy_id == policy_id, PolicyUseRow.used_at > since)) or 0

    def reserve_use(self, policy_id: str, revision: int, per_day: int, action_id: str, now: datetime, *,
                    max_uses: int | None = None, size: int = 0, items: int = 1, bytes_per_day: int | None = None,
                    items_per_day: int | None = None) -> tuple[str, int]:
        """Atomically check every limit of this policy and take one use if all hold.

        Returns ("ok", n) with n the use just taken in the last 24 h, ("limit", n) when per_day is used up,
        ("cap", n) when a size or item cap or max_uses would be passed, or ("changed", 0) when the policy
        is no longer active at this revision. The UPDATE on the policy row serialises concurrent
        reservations on PostgreSQL (row lock) and SQLite (write lock). The use that reaches max_uses
        ends the rule in the same transaction (state "ended", revision + 1).
        """

        class _Over(Exception):
            pass

        try:
            with self.db.session.begin() as s:
                res = s.execute(update(PolicyRow).where(
                    PolicyRow.id == policy_id, PolicyRow.revision == revision, PolicyRow.state == "active",
                    PolicyRow.suspended_at.is_(None),
                ).values(lock_seq=PolicyRow.lock_seq + 1))
                if res.rowcount != 1:
                    return "changed", 0
                day = PolicyUseRow.used_at > now - timedelta(days=1)
                n, sized, counted = s.execute(select(
                    func.count(), func.coalesce(func.sum(PolicyUseRow.size), 0), func.coalesce(func.sum(PolicyUseRow.items), 0),
                ).where(PolicyUseRow.policy_id == policy_id, day)).one()
                if n >= per_day:
                    raise _Over("limit", n)
                total = s.scalar(select(PolicyRow.uses).where(PolicyRow.id == policy_id)) or 0
                if (max_uses is not None and total >= max_uses) \
                        or (bytes_per_day is not None and sized + size > bytes_per_day) \
                        or (items_per_day is not None and counted + items > items_per_day):
                    raise _Over("cap", n)
                s.add(PolicyUseRow(policy_id=policy_id, revision=revision, action_id=action_id, used_at=now,
                                   size=size, items=items))
                ended = max_uses is not None and total + 1 >= max_uses
                s.execute(update(PolicyRow).where(PolicyRow.id == policy_id).values(
                    uses=PolicyRow.uses + 1, last_used_at=now,
                    **({"state": "ended", "revision": PolicyRow.revision + 1} if ended else {})))
                return "ok", n + 1
        except _Over as over:
            return str(over.args[0]), int(over.args[1])

    def release_use(self, action_id: str) -> None:
        with self.db.session.begin() as s:
            pid = s.scalar(select(PolicyUseRow.policy_id).where(PolicyUseRow.action_id == action_id))
            gone = s.execute(delete(PolicyUseRow).where(PolicyUseRow.action_id == action_id)).rowcount
            if pid is not None and gone:
                s.execute(update(PolicyRow).where(PolicyRow.id == pid).values(uses=PolicyRow.uses - 1))
                # the use that ended a max_uses rule did not go through: the rule is live again
                s.execute(update(PolicyRow).where(PolicyRow.id == pid, PolicyRow.state == "ended",
                                                  PolicyRow.max_uses > PolicyRow.uses).values(state="active"))

    def set_policy(self, policy_id: str, *, expect_revision: int | None = None, bump: bool = True,
                   states: tuple[str, ...] = ("active", "paused"), **values) -> bool:
        """Change a policy row (compare-and-swap on the revision when given); bumps the revision."""
        q = update(PolicyRow).where(PolicyRow.id == policy_id, PolicyRow.state.in_(states))
        if expect_revision is not None:
            q = q.where(PolicyRow.revision == expect_revision)
        if bump:
            values["revision"] = PolicyRow.revision + 1
        with self.db.session.begin() as s:
            return s.execute(q.values(**values)).rowcount == 1

    def list_uses(self, policy_id: str, limit: int = 100) -> list[dict]:
        with self.db.session() as s:
            return [_plain(r) for r in s.scalars(select(PolicyUseRow).where(PolicyUseRow.policy_id == policy_id)
                                                 .order_by(PolicyUseRow.used_at.desc()).limit(limit))]

    def uses_by_action(self, action_ids: list[str]) -> dict[str, str]:
        if not action_ids:
            return {}
        with self.db.session() as s:
            return dict(s.execute(select(PolicyUseRow.action_id, PolicyUseRow.policy_id)
                                  .where(PolicyUseRow.action_id.in_(action_ids))).all())

    # ---- windows -------------------------------------------------------------------------------
    def get_window(self, window_id: str) -> dict | None:
        with self.db.session() as s:
            r = s.get(WindowRow, window_id)
            return _plain(r) if r else None

    def list_windows(self) -> list[dict]:
        with self.db.session() as s:
            return [_plain(r) for r in s.scalars(select(WindowRow).order_by(WindowRow.id))]

    def put_window(self, window_id: str, name: str, tz: str, ranges: list, now: datetime) -> None:
        values = {"name": name, "tz": tz, "ranges": ranges, "updated_at": now}
        with self.db.session.begin() as s:
            s.execute(self.db.insert()(WindowRow).values(id=window_id, **values)
                      .on_conflict_do_update(index_elements=[WindowRow.id], set_=values))

    def seed_default_window(self, now: datetime) -> None:
        d = DEFAULT_WINDOW
        with self.db.session.begin() as s:
            s.execute(self.db.insert()(WindowRow).values(
                id=d["id"], name=d["name"], tz=d["tz"], ranges=d["ranges"], updated_at=now,
            ).on_conflict_do_nothing(index_elements=[WindowRow.id]))
