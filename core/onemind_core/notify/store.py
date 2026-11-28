# SPDX-License-Identifier: Apache-2.0
"""Notification tables (feature "notify", docs/leap/core/PLUMBING.md §3).

alerts         one row per condition; `open_key` = dedupe_key while open, NULL once resolved, so
               the unique index allows one open alert per key and any number of resolved ones
notifications  one person's inbox items
receipts       committed fanout for a durable event delivery, per person
deliveries     one notification (or summary) to one channel or device: queued, held, sent,
               failed (retrying), dead, summarised, dropped (over the channel's daily cap)
sends          one row per attempt to reach a capped (sms) channel's provider, whatever its outcome:
               the daily cap counts these, so a retry or a timeout the provider billed is counted
channels       a person's outbound channels; the secret is sealed (SecretBox), never returned
devices        push registrations (Web Push / UnifiedPush); endpoint and keys sealed
preferences    a person's routing document (contract §12.14)
sources        the owner's mute switch per notification source (`app:<id>`, `plugin:<id>`; topics.py)
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, and_, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..ledger import Base, iso, utc
from ..store import Database, FeatureSchema, SqlRepository
from .routing import MAX_INBOX_DAYS

SCHEMA = FeatureSchema("notify")


@SCHEMA.step(2, "where an inbox item came from: source kind, app, asset, group key, actions (#613)")
def _notify_v2(conn) -> None:
    from sqlalchemy import inspect, text

    have = {c["name"] for c in inspect(conn).get_columns("notify_notifications")}
    for name, ddl in (("source_kind", "VARCHAR(16) NOT NULL DEFAULT 'system'"), ("app_id", "VARCHAR(80)"),
                      ("asset_id", "VARCHAR(128)"), ("group_key", "VARCHAR(200)"), ("actions_json", "TEXT")):
        if name not in have:
            conn.execute(text(f"ALTER TABLE notify_notifications ADD COLUMN {name} {ddl}"))


@SCHEMA.step(3, "install_id on push registrations: the app install that registered it, for My devices (#715)")
def _notify_v3(conn) -> None:
    from sqlalchemy import inspect, text

    if "install_id" not in {c["name"] for c in inspect(conn).get_columns("notify_devices")}:
        conn.execute(text("ALTER TABLE notify_devices ADD COLUMN install_id VARCHAR(64)"))


class AlertRow(Base):
    __tablename__ = "notify_alerts"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    type: Mapped[str] = mapped_column(String(80))
    severity: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="")
    subject_json: Mapped[str] = mapped_column(Text, default="{}")
    source_id: Mapped[str] = mapped_column(String(80), default="gateway")
    state: Mapped[str] = mapped_column(String(16), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(200), index=True)
    open_key: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True)
    audience_json: Mapped[str] = mapped_column(Text, default="{}")
    fix_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    learn_more_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    link: Mapped[str | None] = mapped_column(String(300), nullable=True)
    topic: Mapped[str] = mapped_column(String(80))
    auto_resolve: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_resolve: Mapped[bool] = mapped_column(Boolean, default=False)
    occurrences: Mapped[int] = mapped_column(Integer, default=1)
    flapping: Mapped[bool] = mapped_column(Boolean, default=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acked_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_notified_severity: Mapped[str | None] = mapped_column(String(16), nullable=True)


class NotificationRow(Base):
    __tablename__ = "notify_notifications"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    person_id: Mapped[str] = mapped_column(String(120))
    severity: Mapped[str] = mapped_column(String(16))
    topic: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source: Mapped[str] = mapped_column(String(120))
    action_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    alert_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_kind: Mapped[str] = mapped_column(String(16), default="system", server_default="system")
    app_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    asset_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    group_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    actions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (Index("notify_notifications_person_created", "person_id", "created_at"),)


class NotificationReceiptRow(Base):
    """Keep delivery acknowledgements independent of inbox retention."""

    __tablename__ = "notify_notification_receipts"
    delivery_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    person_id: Mapped[str] = mapped_column(String(120), primary_key=True)


class DeliveryRow(Base):
    __tablename__ = "notify_deliveries"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    notification_id: Mapped[str] = mapped_column(String(40), index=True)
    person_id: Mapped[str] = mapped_column(String(120))
    target_id: Mapped[str] = mapped_column(String(40))          # chn_… or dev_…
    state: Mapped[str] = mapped_column(String(16))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    release_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    held_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (Index("notify_deliveries_state_next", "state", "next_attempt_at"),)


class SendRow(Base):
    """One attempt to reach a capped channel's provider (issue #869), written before any byte goes out."""
    __tablename__ = "notify_sends"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    target_id: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(16))               # delivery | test
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("notify_sends_target_at", "target_id", "at"),)


class ChannelRow(Base):
    __tablename__ = "notify_channels"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    person_id: Mapped[str] = mapped_column(String(120), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    label: Mapped[str] = mapped_column(String(120))
    config_json: Mapped[str] = mapped_column(Text)
    secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_level: Mapped[str] = mapped_column(String(8))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    state: Mapped[str] = mapped_column(String(16), default="ok")
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    failing_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DeviceRow(Base):
    __tablename__ = "notify_devices"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    person_id: Mapped[str] = mapped_column(String(120), index=True)
    platform: Mapped[str] = mapped_column(String(16))
    endpoint_enc: Mapped[str] = mapped_column(Text)
    keys_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    label: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(16), default="ok")
    failing_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    install_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # #715, see devices/service.py


class PreferencesRow(Base):
    __tablename__ = "notify_preferences"
    person_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    doc_json: Mapped[str] = mapped_column(Text)
    etag: Mapped[str] = mapped_column(String(80))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SourceRow(Base):
    __tablename__ = "notify_sources"
    source_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    muted: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str | None] = mapped_column(String(16), nullable=True)   # owner | flood
    muted_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    muted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# ---- JSON views --------------------------------------------------------------------------

def alert_json(r: AlertRow) -> dict:
    """The `onemind.alert/v1` record of contract §12.14 (plus `topic`, `link`, `acked_by`)."""
    return {
        "schema": "onemind.alert/v1", "id": r.id, "type": r.type, "severity": r.severity,
        "title": r.title, "body": r.body, "subject": json.loads(r.subject_json or "{}"),
        "source_id": r.source_id, "state": r.state, "dedupe_key": r.dedupe_key,
        "opened_at": iso(r.opened_at), "updated_at": iso(r.updated_at), "resolved_at": iso(r.resolved_at),
        "occurrences": r.occurrences, "flapping": r.flapping,
        "fix": json.loads(r.fix_json) if r.fix_json else None,
        "learn_more_url": r.learn_more_url, "topic": r.topic, "link": r.link,
        "acked_by": r.acked_by, "acked_at": iso(r.acked_at),
    }


def notification_json(r: NotificationRow) -> dict:
    return {
        "id": r.id, "severity": r.severity, "topic": r.topic, "title": r.title, "body": r.body,
        "link": r.link, "source": r.source, "action_id": r.action_id, "alert_id": r.alert_id,
        "source_kind": r.source_kind or "system", "app_id": r.app_id, "asset_id": r.asset_id,
        "group_key": r.group_key, "actions": json.loads(r.actions_json) if r.actions_json else [],
        "created_at": iso(r.created_at), "read_at": iso(r.read_at),
    }


def channel_json(r: ChannelRow) -> dict:
    return {
        "id": r.id, "kind": r.kind, "label": r.label, "content_level": r.content_level,
        "config": {k: v for k, v in json.loads(r.config_json).items() if k != "lan"}, "verified": r.verified, "state": r.state,
        "last_error": r.last_error, "owner_person_id": r.person_id,
        "secret": "provided" if r.secret_enc else None,
        "created_at": iso(r.created_at), "updated_at": iso(r.updated_at),
    }


def device_json(r: DeviceRow) -> dict:
    return {"id": r.id, "platform": r.platform, "label": r.label, "state": r.state,
            "created_at": iso(r.created_at), "last_seen_at": iso(r.last_seen_at)}


def encode_cursor(created_at: datetime, row_id: str) -> str:
    return base64.urlsafe_b64encode(f"{iso(created_at)}|{row_id}".encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, str] | None:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        ts, row_id = raw.split("|", 1)
        return utc(datetime.fromisoformat(ts.replace("Z", "+00:00"))), row_id
    except (ValueError, UnicodeDecodeError):
        return None


class NotifyRepository(SqlRepository):
    """Every read and write of the notify tables. Callers serialise alert updates (one gateway)."""

    def __init__(self, db: Database):
        super().__init__(db)

    # ---- alerts ----------------------------------------------------------------------------
    def open_alert(self, key: str) -> AlertRow | None:
        with self.db.session() as s:
            return s.scalars(select(AlertRow).where(AlertRow.open_key == key)).first()

    def last_resolved(self, key: str) -> AlertRow | None:
        with self.db.session() as s:
            return s.scalars(
                select(AlertRow).where(AlertRow.dedupe_key == key, AlertRow.state == "resolved")
                .order_by(AlertRow.resolved_at.desc()).limit(1)
            ).first()

    def insert_alert(self, row: AlertRow) -> AlertRow | None:
        """Insert; None if another open alert with the same key won the race."""
        try:
            with self.db.session.begin() as s:
                s.add(row)
            return row
        except IntegrityError:
            return None

    def save_alert(self, row: AlertRow) -> None:
        with self.db.session.begin() as s:
            s.merge(row)

    def get_alert(self, alert_id: str) -> AlertRow | None:
        with self.db.session() as s:
            return s.get(AlertRow, alert_id)

    def list_alerts(self, states: set[str] | None = None, limit: int = 1000) -> list[AlertRow]:
        with self.db.session() as s:
            q = select(AlertRow).order_by(AlertRow.opened_at.desc(), AlertRow.id.desc()).limit(limit)
            if states:
                q = q.where(AlertRow.state.in_(states))
            return list(s.scalars(q))

    def open_alert_keys(self) -> set[str]:
        with self.db.session() as s:
            return set(s.scalars(select(AlertRow.open_key).where(AlertRow.open_key.is_not(None))))

    def open_alert_counts(self) -> dict[str, int]:
        with self.db.session() as s:
            rows = s.execute(
                select(AlertRow.severity, func.count()).where(AlertRow.open_key.is_not(None)).group_by(AlertRow.severity)
            ).all()
        return {sev: n for sev, n in rows}

    # ---- notifications ---------------------------------------------------------------------
    def add_notification(self, row: NotificationRow, deliveries: list[DeliveryRow], *,
                         delivery_id: str | None = None) -> bool:
        with self.db.session.begin() as s:
            if delivery_id is not None:
                claimed = s.scalar(self.db.insert()(NotificationReceiptRow)
                                   .values(delivery_id=delivery_id, person_id=row.person_id)
                                   .on_conflict_do_nothing()
                                   .returning(NotificationReceiptRow.delivery_id))
                if claimed is None:
                    return False
            s.add(row)
            s.add_all(deliveries)
        return True

    def add_notifications(self, pending: list[tuple[NotificationRow, list[DeliveryRow]]],
                          record: Callable[[Session], None]) -> None:
        with self.db.session.begin() as s:
            for row, deliveries in pending:
                s.add(row)
                s.add_all(deliveries)
            record(s)

    def get_notification(self, nid: str) -> NotificationRow | None:
        with self.db.session() as s:
            return s.get(NotificationRow, nid)

    def list_notifications(
        self, person_id: str, *, unread: bool | None, severities: list[str] | None,
        topics: list[str] | None, since: datetime | None, limit: int, cursor: tuple[datetime, str] | None,
    ) -> list[NotificationRow]:
        q = select(NotificationRow).where(NotificationRow.person_id == person_id)
        if unread is True:
            q = q.where(NotificationRow.read_at.is_(None))
        elif unread is False:
            q = q.where(NotificationRow.read_at.is_not(None))
        if severities:
            q = q.where(NotificationRow.severity.in_(severities))
        if topics:
            conds = []
            for t in topics:
                if t.endswith(".*"):
                    base = t[:-2]
                    conds += [NotificationRow.topic == base, NotificationRow.topic.like(base + ".%")]
                else:
                    conds.append(NotificationRow.topic == t)
            q = q.where(or_(*conds))
        if since is not None:
            q = q.where(NotificationRow.created_at >= since)
        if cursor is not None:
            ts, rid = cursor
            q = q.where(or_(NotificationRow.created_at < ts, and_(NotificationRow.created_at == ts, NotificationRow.id < rid)))
        q = q.order_by(NotificationRow.created_at.desc(), NotificationRow.id.desc()).limit(limit)
        with self.db.session() as s:
            return list(s.scalars(q))

    def unread_summary(self, person_id: str) -> dict:
        """One person's inbox in one answer: unread counts per severity and the two times that
        move whenever the inbox changes (a new item, or an item read on any device)."""
        mine = NotificationRow.person_id == person_id
        with self.db.session() as s:
            counts = dict(s.execute(
                select(NotificationRow.severity, func.count())
                .where(mine, NotificationRow.read_at.is_(None)).group_by(NotificationRow.severity)
            ).all())
            latest, last_read = s.execute(
                select(func.max(NotificationRow.created_at), func.max(NotificationRow.read_at)).where(mine)
            ).one()
        by_severity = {sev: int(counts.get(sev, 0)) for sev in ("info", "warning", "critical")}
        return {"unread": sum(int(n) for n in counts.values()), "by_severity": by_severity,
                "latest_created_at": iso(latest), "last_read_at": iso(last_read)}

    def mark_read(self, person_id: str, nid: str | None, now: datetime) -> int:
        conds = [NotificationRow.person_id == person_id, NotificationRow.read_at.is_(None)]
        if nid is not None:
            conds.append(NotificationRow.id == nid)
        with self.db.session.begin() as s:
            ids = list(s.scalars(select(NotificationRow.id).where(*conds)))
            if ids:
                s.execute(update(NotificationRow).where(NotificationRow.id.in_(ids)).values(read_at=now))
            return len(ids)

    # ---- deliveries ------------------------------------------------------------------------
    def due_deliveries(self, now: datetime, limit: int = 50) -> list[DeliveryRow]:
        with self.db.session() as s:
            return list(s.scalars(
                select(DeliveryRow).where(
                    DeliveryRow.state.in_(("queued", "failed")), DeliveryRow.next_attempt_at <= now
                ).order_by(DeliveryRow.next_attempt_at, DeliveryRow.id).limit(limit)
            ))

    def released_held(self, now: datetime) -> list[DeliveryRow]:
        with self.db.session() as s:
            return list(s.scalars(
                select(DeliveryRow).where(DeliveryRow.state == "held", DeliveryRow.release_at <= now)
                .order_by(DeliveryRow.created_at, DeliveryRow.id)
            ))

    def sent_outage_delivery(self, d: DeliveryRow, key: str, since: datetime,
                             sibling_window: tuple[datetime, datetime], severities: tuple[str, ...]) -> str | None:
        with self.db.session() as s:
            return s.scalar(
                select(DeliveryRow.id).join(NotificationRow, NotificationRow.id == DeliveryRow.notification_id)
                .join(AlertRow, AlertRow.id == NotificationRow.alert_id)
                .where(
                    DeliveryRow.person_id == d.person_id, DeliveryRow.target_id == d.target_id,
                    DeliveryRow.state == "sent", NotificationRow.group_key == key,
                    or_(DeliveryRow.held_reason.is_(None), ~DeliveryRow.held_reason.like("summary:%")),
                    NotificationRow.created_at >= since, NotificationRow.severity.in_(severities),
                    or_(AlertRow.type == "node.offline",
                        and_(AlertRow.type == "app.unhealthy", AlertRow.source_id == "gateway:monitoring",
                             NotificationRow.created_at.between(*sibling_window))),
                )
                .order_by(DeliveryRow.sent_at, DeliveryRow.id).limit(1)
            )

    def save_delivery(self, row: DeliveryRow) -> None:
        with self.db.session.begin() as s:
            s.merge(row)

    def add_delivery(self, row: DeliveryRow) -> None:
        with self.db.session.begin() as s:
            s.add(row)

    def mark_summarised(self, ids: list[str], summary_id: str, now: datetime) -> None:
        with self.db.session.begin() as s:
            s.execute(update(DeliveryRow).where(DeliveryRow.id.in_(ids)).values(
                state="summarised", sent_at=now, last_error=f"in {summary_id}"[:300]))

    def sent_count(self, target_id: str, since: datetime) -> int:
        with self.db.session() as s:
            return s.scalar(select(func.count()).select_from(DeliveryRow).where(
                DeliveryRow.target_id == target_id, DeliveryRow.created_at >= since,
                DeliveryRow.state.in_(("queued", "sent", "failed")),
            )) or 0

    def claim_send(self, target_id: str, kind: str, since: datetime, cap: int, now: datetime, send_id: str) -> bool:
        """Record one provider attempt unless `cap` attempts were made since `since`; False when capped.

        Every attempt counts (a failure, a 5xx, a timeout the provider may already have billed), so a
        retry loop cannot send more than `cap` in the window. Callers serialise per gateway."""
        with self.db.session.begin() as s:
            made = s.scalar(select(func.count()).select_from(SendRow).where(
                SendRow.target_id == target_id, SendRow.at >= since)) or 0
            if made >= cap:
                return False
            s.add(SendRow(id=send_id, target_id=target_id, kind=kind, at=now))
            return True

    def sends_since(self, target_id: str, since: datetime) -> int:
        with self.db.session() as s:
            return s.scalar(select(func.count()).select_from(SendRow).where(
                SendRow.target_id == target_id, SendRow.at >= since)) or 0

    def deliveries_for(self, notification_id: str) -> list[DeliveryRow]:
        with self.db.session() as s:
            return list(s.scalars(select(DeliveryRow).where(DeliveryRow.notification_id == notification_id)))

    def oldest_in_window(self, target_id: str, since: datetime) -> datetime | None:
        with self.db.session() as s:
            v = s.scalar(select(func.min(DeliveryRow.created_at)).where(
                DeliveryRow.target_id == target_id, DeliveryRow.created_at >= since,
                DeliveryRow.state.in_(("queued", "sent", "failed"))))
        return None if v is None else utc(v)

    # ---- channels and devices --------------------------------------------------------------
    def add_channel(self, row: ChannelRow) -> None:
        with self.db.session.begin() as s:
            s.add(row)

    def get_channel(self, cid: str) -> ChannelRow | None:
        with self.db.session() as s:
            return s.get(ChannelRow, cid)

    def save_channel(self, row: ChannelRow) -> None:
        with self.db.session.begin() as s:
            s.merge(row)

    def delete_channel(self, cid: str) -> None:
        with self.db.session.begin() as s:
            s.execute(delete(ChannelRow).where(ChannelRow.id == cid))
            s.execute(update(DeliveryRow).where(
                DeliveryRow.target_id == cid, DeliveryRow.state.in_(("queued", "failed", "held"))
            ).values(state="dead", last_error="channel deleted"))

    def list_channels(self, person_id: str | None = None) -> list[ChannelRow]:
        with self.db.session() as s:
            q = select(ChannelRow).order_by(ChannelRow.created_at, ChannelRow.id)
            if person_id is not None:
                q = q.where(ChannelRow.person_id == person_id)
            return list(s.scalars(q))

    def add_device(self, row: DeviceRow) -> None:
        with self.db.session.begin() as s:
            s.add(row)

    def get_device(self, did: str) -> DeviceRow | None:
        with self.db.session() as s:
            return s.get(DeviceRow, did)

    def save_device(self, row: DeviceRow) -> None:
        with self.db.session.begin() as s:
            s.merge(row)

    def delete_device(self, did: str) -> None:
        with self.db.session.begin() as s:
            s.execute(delete(DeviceRow).where(DeviceRow.id == did))
            s.execute(update(DeliveryRow).where(
                DeliveryRow.target_id == did, DeliveryRow.state.in_(("queued", "failed", "held"))
            ).values(state="dead", last_error="device removed"))

    def list_devices(self, person_id: str | None = None) -> list[DeviceRow]:
        with self.db.session() as s:
            q = select(DeviceRow).order_by(DeviceRow.created_at, DeviceRow.id)
            if person_id is not None:
                q = q.where(DeviceRow.person_id == person_id)
            return list(s.scalars(q))

    def known_people(self) -> set[str]:
        with self.db.session() as s:
            return (set(s.scalars(select(ChannelRow.person_id))) | set(s.scalars(select(DeviceRow.person_id)))
                    | set(s.scalars(select(PreferencesRow.person_id))))

    # ---- preferences -----------------------------------------------------------------------
    def get_preferences(self, person_id: str) -> PreferencesRow | None:
        with self.db.session() as s:
            return s.get(PreferencesRow, person_id)

    def put_preferences(self, person_id: str, doc: dict, etag: str, now: datetime) -> None:
        stmt = self.db.insert()(PreferencesRow).values(
            person_id=person_id, doc_json=json.dumps(doc, sort_keys=True), etag=etag, updated_at=now
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[PreferencesRow.person_id],
            set_={"doc_json": stmt.excluded.doc_json, "etag": stmt.excluded.etag, "updated_at": stmt.excluded.updated_at},
        ).returning(PreferencesRow.person_id)
        with self.db.session.begin() as s:
            s.execute(stmt).scalar()

    # ---- sources (topics.py) ----------------------------------------------------------------
    def get_source(self, source_id: str) -> SourceRow | None:
        with self.db.session() as s:
            return s.get(SourceRow, source_id)

    def list_sources(self) -> list[SourceRow]:
        with self.db.session() as s:
            return list(s.scalars(select(SourceRow).order_by(SourceRow.source_id)))

    def save_source(self, row: SourceRow) -> None:
        with self.db.session.begin() as s:
            s.merge(row)

    # ---- retention (NOTIFICATIONS.md §9) ---------------------------------------------------
    def prune(self, now: datetime) -> None:
        with self.db.session.begin() as s:
            s.execute(delete(NotificationRow).where(NotificationRow.created_at < now - timedelta(days=MAX_INBOX_DAYS)))
            for person_id, doc_json in s.execute(select(PreferencesRow.person_id, PreferencesRow.doc_json)):
                days = json.loads(doc_json).get("retention_days", MAX_INBOX_DAYS)
                if type(days) is int and 1 <= days < MAX_INBOX_DAYS:
                    s.execute(delete(NotificationRow).where(NotificationRow.person_id == person_id,
                                                            NotificationRow.created_at < now - timedelta(days=days)))
            s.execute(delete(DeliveryRow).where(
                DeliveryRow.created_at < now - timedelta(days=30),
                DeliveryRow.state.in_(("sent", "dead", "summarised", "dropped"))))
            s.execute(delete(SendRow).where(SendRow.at < now - timedelta(days=2)))
            s.execute(delete(AlertRow).where(
                AlertRow.state == "resolved", AlertRow.resolved_at < now - timedelta(days=180)))
