# SPDX-License-Identifier: Apache-2.0
"""The Tips service: the loaded pack, filtered by the caller's role and the running OS version, joined
with each person's own tip state (table tips_state, feature "tips").

A tip the caller's role may not see, or one made for another OS version, does not exist for that
caller: it answers 404 like an unknown id, so a tip id is no oracle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import DateTime, String, delete, select
from sqlalchemy.orm import Mapped, mapped_column

from ..auth import Principal
from ..errors import ApiError
from ..ledger import Base, iso, utc
from ..sections import config_section
from ..store import FeatureSchema, SqlRepository
from .pack import Loaded, Tip, Version, load_first, load_key, running_version

SCHEMA = FeatureSchema("tips")
STATES = ("new", "seen", "dismissed", "done")


@config_section("tips")
@dataclass(frozen=True)
class TipsSettings:
    dir: Path = Path("/usr/share/onemind/tips")                 # ONEMIND_TIPS_DIR: the image pack
    key_file: Path = Path("/usr/lib/onemind/keys/tips.pub")     # ONEMIND_TIPS_KEY_FILE: trusted Ed25519 key (PEM)
    os_release: Path = Path("/usr/lib/os-release")              # ONEMIND_TIPS_OS_RELEASE: where ONEMIND_VERSION is


class TipStateRow(Base):
    """One person's state for one tip. No row means "new"."""

    __tablename__ = "tips_state"
    person_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    tip_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    state: Mapped[str] = mapped_column(String(16))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TipsRepository(SqlRepository):
    def states(self, person_id: str) -> dict[str, tuple[str, datetime]]:
        with self.db.session() as s:
            rows = s.scalars(select(TipStateRow).where(TipStateRow.person_id == person_id))
            return {r.tip_id: (r.state, utc(r.updated_at)) for r in rows}

    def set(self, person_id: str, tip_id: str, state: str, now: datetime) -> None:
        with self.db.session.begin() as s:
            if state == "new":
                s.execute(delete(TipStateRow).where(TipStateRow.person_id == person_id, TipStateRow.tip_id == tip_id))
                return
            values = {"state": state, "updated_at": now}
            insert = self.db.insert()(TipStateRow).values(person_id=person_id, tip_id=tip_id, **values)
            s.execute(insert.on_conflict_do_update(index_elements=[TipStateRow.person_id, TipStateRow.tip_id], set_=values))


class TipsService:
    def __init__(self, loaded: Loaded, version: Version, repo: TipsRepository):
        self.loaded = loaded
        self.version = version
        self.repo = repo

    @classmethod
    def from_settings(cls, s: TipsSettings, repo: TipsRepository) -> TipsService:
        version = running_version(s.os_release)
        # v1 is image-only; #790 puts the newer signed /data/tips pack first in this list.
        return cls(load_first([("image", s.dir)], load_key(s.key_file), version), version, repo)

    def visible(self, p: Principal) -> list[Tip]:
        pack = self.loaded.pack
        if pack is None:
            return []
        return [t for t in pack.tips if t.shows_to(p.role) and t.shows_on(self.version)]

    def _tip(self, p: Principal, tip_id: str) -> Tip:
        for t in self.visible(p):
            if t.id == tip_id:
                return t
        raise ApiError(404, "not_found", "no such tip")

    @staticmethod
    def _view(t: Tip, state: tuple[str, datetime] | None) -> dict:
        return {
            "id": t.id, "title": t.title, "collection": t.collection, "body": t.body,
            "opens": t.opens.model_dump(), "skip_if_done": list(t.skip_if_done),
            "clip": t.clip.model_dump() if t.clip else None,
            "state": state[0] if state else "new", "state_updated_at": iso(state[1]) if state else None,
        }

    def pack_info(self) -> dict | None:
        pack = self.loaded.pack
        return None if pack is None else {"version": pack.version, "source": self.loaded.source}

    def list(self, p: Principal, collection: str | None = None) -> dict:
        states = self.repo.states(p.id)
        tips = [t for t in self.visible(p) if collection is None or t.collection == collection]
        return {"pack": self.pack_info(), "tips": [self._view(t, states.get(t.id)) for t in tips]}

    def get(self, p: Principal, tip_id: str) -> dict:
        t = self._tip(p, tip_id)
        return self._view(t, self.repo.states(p.id).get(t.id))

    def collections(self, p: Principal) -> dict:
        pack = self.loaded.pack
        if pack is None:
            return {"collections": [], "checklist": []}
        tips = self.visible(p)
        counts = {c.id: sum(1 for t in tips if t.collection == c.id) for c in pack.collections}
        shown = {t.id for t in tips}
        return {"collections": [{"id": c.id, "title": c.title, "count": counts[c.id]}
                                for c in pack.collections if counts[c.id]],
                "checklist": [i for i in pack.checklist if i in shown]}

    def whats_new(self) -> dict:
        running = ".".join(str(n) for n in self.version)
        pack = self.loaded.pack
        entries = [] if pack is None else [w.model_dump() for w in pack.whats_new if w.version == running]
        return {"os_version": running, "entries": entries}

    def set_state(self, p: Principal, tip_id: str, state: str, now: datetime) -> dict:
        t = self._tip(p, tip_id)
        self.repo.set(p.id, t.id, state, now)
        return {"tip_id": t.id, "state": state, "updated_at": None if state == "new" else iso(now)}
