# SPDX-License-Identifier: Apache-2.0
"""Persist recovery notices in the transaction that makes them due."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, String, delete, or_, select, update
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.types import JSON

from ..auth import Principal
from ..identity.crypto import new_id
from ..ledger import Base
from .contacts import RecoveryContacts

log = logging.getLogger("onemind.recovery")
DELIVERY_LEASE = timedelta(minutes=1)


class PendingNoticeRow(Base):
    __tablename__ = "recovery_pending_notices"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(40))
    event: Mapped[str] = mapped_column(String(60))
    data: Mapped[dict] = mapped_column(JSON)
    actor: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    severity: Mapped[str] = mapped_column(String(10))
    audit_only: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RecoveryNotices:
    def __init__(self, contacts: RecoveryContacts):
        self.contacts = contacts
        self.db = contacts.db

    @staticmethod
    def queue(s: Session, owner_id: str, event: str, data: dict, p: Principal | None = None,
              severity: str = "warning", audit_only: dict | None = None) -> str:
        notice_id = new_id("rn")
        s.add(PendingNoticeRow(id=notice_id, owner_user_id=owner_id, event=f"recovery.request.{event}",
                               data=data, actor=p.as_dict() if p else None, severity=severity,
                               audit_only=audit_only))
        return notice_id

    def send(self, notice_id: str) -> bool:
        # Release the database transaction before dispatch: the notifier itself writes to the DB.
        # An abandoned lease expires, so a process crash leaves the notice available to another tick.
        now = datetime.now(UTC)
        lease = now + DELIVERY_LEASE
        with self.db.session.begin() as s:
            notice = s.scalars(update(PendingNoticeRow).where(
                PendingNoticeRow.id == notice_id,
                or_(PendingNoticeRow.lease_until.is_(None), PendingNoticeRow.lease_until <= now),
            ).values(lease_until=lease).returning(PendingNoticeRow)).one_or_none()
        if notice is None:
            return False
        claim = (PendingNoticeRow.id == notice_id, PendingNoticeRow.lease_until == lease)
        try:
            self.contacts.tell(notice.owner_user_id, notice.event, notice.data,
                               Principal(**notice.actor) if notice.actor else None,
                               severity=notice.severity, audit_only=notice.audit_only, delivery_id=notice_id)
        except Exception:
            log.exception("recovery notice %s delivery failed; will retry", notice_id)
            with self.db.session.begin() as s:
                s.execute(update(PendingNoticeRow).where(*claim).values(lease_until=None))
            return False
        with self.db.session.begin() as s:
            s.execute(delete(PendingNoticeRow).where(*claim))
        return True

    def retry(self) -> int:
        with self.db.session() as s:
            ids = list(s.scalars(select(PendingNoticeRow.id).order_by(PendingNoticeRow.id)))
        return sum(self.send(notice_id) for notice_id in ids)
