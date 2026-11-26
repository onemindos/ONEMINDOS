# SPDX-License-Identifier: Apache-2.0
"""No automatic approval while the clock cannot be trusted (gateway permissions design §3.4 item 12, fix 10).

A rule's expiry, its time window and its per-day count all read the clock. A clock set back (a dead
RTC battery, a spoofed time server) would make an expired rule live again or reset a day's count. So:

- **High-water mark:** the latest time the gateway has ever recorded, kept in the database. A clock
  that reads more than `TOLERANCE` earlier than that is wrong, and every request waits for a person
  until the clock catches up again.
- **Synchronised:** when `ONEMIND_CLOCK_SYNC_FILE` names a file (systemd-timesyncd writes
  `/run/systemd/timesync/synchronized` once it has synchronised with a time server), a missing file
  means the clock was never synchronised since boot, and the same applies.

A person's own approval never depends on this: it only turns automatic approvals off. `clock.untrusted`
and `clock.trusted` are audited on each change.

Table `permissions_clock` (feature "permissions"; one row, id "hwm").
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from ..audit import AuditLog
from ..ledger import Base, iso, utc
from ..store import Database

TOLERANCE = timedelta(minutes=5)
WRITE_EVERY = timedelta(minutes=1)
SYNC_FILE_ENV = "ONEMIND_CLOCK_SYNC_FILE"


class ClockRow(Base):
    __tablename__ = "permissions_clock"
    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    high_water: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ClockGuard:
    def __init__(self, db: Database, audit: AuditLog, clock: Callable[[], datetime], sync_file: str | None = None):
        self.db, self.audit, self.clock = db, audit, clock
        self.sync_file = sync_file if sync_file is not None else (os.environ.get(SYNC_FILE_ENV) or None)
        self._lock = threading.Lock()
        self._hwm: datetime | None = None
        self._untrusted: str | None = None  # the last reason, so a change is audited once

    def high_water(self) -> datetime | None:
        if self._hwm is None:
            with self.db.session() as s:
                r = s.get(ClockRow, "hwm")
                self._hwm = utc(r.high_water) if r else None
        return self._hwm

    def _write(self, at: datetime) -> None:
        values = {"high_water": at}
        with self.db.session.begin() as s:
            s.execute(self.db.insert()(ClockRow).values(id="hwm", **values)
                      .on_conflict_do_update(index_elements=[ClockRow.id], set_=values))
        self._hwm = at

    def check(self) -> str | None:
        """Why the clock cannot be trusted now, or None."""
        now = utc(self.clock())
        reason = None
        with self._lock:
            hwm = self.high_water()
            if self.sync_file and not os.path.exists(self.sync_file):
                reason = "not_synchronised"
            elif hwm is not None and now < hwm - TOLERANCE:
                reason = "clock_behind"
            elif hwm is None or now - hwm >= WRITE_EVERY:
                self._write(now)
            changed, self._untrusted = reason != self._untrusted, reason
        if changed:
            data = {"reason": reason, "now": iso(now), "high_water": iso(hwm) if hwm else None}
            self.audit.append("clock.untrusted" if reason else "clock.trusted", None, None, data)
        return reason
