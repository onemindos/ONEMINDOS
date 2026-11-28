# SPDX-License-Identifier: Apache-2.0
"""ONB-P1 software preferences on the shared database; no host or backup execution."""
from contextlib import nullcontext

from sqlalchemy import String
from sqlalchemy.orm import Mapped, Session, mapped_column

from .ledger import Base
from .store import FeatureSchema, SqlRepository

SCHEMA = FeatureSchema("onboarding")
BACKUP_DEFAULTS = {"backup_choice": "later", "backup_destination_id": None}


class SettingsRow(Base):
    __tablename__ = "onboarding_settings"
    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    box_name: Mapped[str] = mapped_column(String(63))
    time_zone: Mapped[str] = mapped_column(String(128))
    backup_choice: Mapped[str] = mapped_column(String(8))
    backup_destination_id: Mapped[str | None] = mapped_column(String(40), nullable=True)


class OnboardingService(SqlRepository):
    def read(self, *, session: Session | None = None) -> dict:
        with (self.db.session() if session is None else nullcontext(session)) as s:
            row = s.get(SettingsRow, "box")
            if row is None:
                return {"box_name": None, "time_zone": None, **BACKUP_DEFAULTS, "saved": False}
            return {key: getattr(row, key) for key in
                    ("box_name", "time_zone", "backup_choice", "backup_destination_id")} | {"saved": True}

    def save(self, values: dict) -> dict:
        # One upsert, not four independent settings writes; readers see a complete replacement.
        with self.db.session.begin() as s:
            self._upsert(s, values, values)
        return values | {"saved": True}

    def import_box_settings(self, session: Session, *, box: dict, changes: dict) -> None:
        # A new box needs backup defaults. Existing rows keep any settings the import did not select.
        self._upsert(session, {**BACKUP_DEFAULTS, **box}, changes)

    def _upsert(self, session: Session, values: dict, changes: dict) -> None:
        insert = self.db.insert()(SettingsRow).values(id="box", **values)
        session.execute(insert.on_conflict_do_update(index_elements=[SettingsRow.id], set_=changes))
