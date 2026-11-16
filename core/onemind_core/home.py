# SPDX-License-Identifier: Apache-2.0
"""UMB-P07 (#144): one Home document per person, kept on the hub (docs/umbrel2/desktop-ui.md §4.2).

Appearance, layout, dock, grid, widgets and the "seen" flags live here instead of in one browser's
localStorage, so the phone and the desktop show the same thing and a browser clear loses nothing.
Defaults are computed, never stored, until the person changes something.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from .ledger import Base
from .store import FeatureSchema, SqlRepository

SCHEMA = FeatureSchema("home")

# Typed item ids (desktop-ui.md §4.2). Shortcuts and automations are a later step and not accepted yet.
ITEM_ID = re.compile(r"^(sys:[a-z][a-z0-9-]{0,39}|app:[a-z0-9][a-z0-9-]{0,62}|node:[A-Za-z0-9._-]{1,64})$")
SLUG = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
MAX_DOCK = 8
MAX_WIDGETS = 6
MAX_LIST = 200
APPROVALS = "sys:approvals"


def _items(values: list[str]) -> list[str]:
    seen: list[str] = []
    for v in values:
        if not ITEM_ID.match(v):
            raise ValueError(f"{v!r} is not a valid item id (sys:<screen>, app:<id> or node:<id>)")
        if v not in seen:
            seen.append(v)
    return seen


class Appearance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    theme: Literal["system", "light", "dark"] = "system"
    wallpaper: str = Field(default="om-dusk-01", pattern=SLUG.pattern.replace("{0,39}", "{0,63}"))
    accent: str = Field(default="wallpaper", pattern=SLUG.pattern)
    density: Literal["comfortable", "compact"] = "comfortable"
    reduce_transparency: bool = False
    reduce_motion: Literal["system", "on", "off"] = "system"


class Grid(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order: list[str] = Field(default_factory=list, max_length=MAX_LIST)
    hidden: list[str] = Field(default_factory=list, max_length=MAX_LIST)

    @field_validator("order", "hidden")
    @classmethod
    def typed(cls, v: list[str]) -> list[str]:
        return _items(v)


class Widget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    size: Literal["regular", "large"] = "regular"

    @field_validator("id")
    @classmethod
    def typed(cls, v: str) -> str:
        return _items([v])[0]


class Seen(BaseModel):
    model_config = ConfigDict(extra="forbid")
    whats_new: str | None = Field(default=None, max_length=40)
    welcome_tips_closed: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("welcome_tips_closed")
    @classmethod
    def slugs(cls, v: list[str]) -> list[str]:
        if any(not SLUG.match(x) for x in v):
            raise ValueError("tip ids are lowercase words")
        return v


class HomeBody(BaseModel):
    """What a client may send. `updated_at` is accepted (so a GET result can be sent back) and ignored."""
    model_config = ConfigDict(extra="forbid")
    version: Literal[3] = 3
    layout: Literal["desktop", "classic"] = "desktop"
    appearance: Appearance = Field(default_factory=Appearance)
    dock: list[str] = Field(default_factory=list, max_length=MAX_DOCK)
    grid: Grid = Field(default_factory=Grid)
    widgets: list[Widget] = Field(default_factory=list, max_length=MAX_WIDGETS)
    seen: Seen = Field(default_factory=Seen)
    updated_at: str | None = None

    @field_validator("dock")
    @classmethod
    def typed(cls, v: list[str]) -> list[str]:
        return _items(v)


class HomeView(HomeBody):
    updated_at: str | None = None


class HomeRow(Base):
    __tablename__ = "home_documents"
    person_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    doc: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def etag_of(doc: dict) -> str:
    """A strong validator over the content (not over updated_at), quoted as HTTP wants."""
    body = {k: v for k, v in doc.items() if k != "updated_at"}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return f'"{digest[:20]}"'


def item_ids(doc: dict) -> list[str]:
    ids = list(doc["dock"]) + list(doc["grid"]["order"]) + list(doc["grid"]["hidden"])
    return ids + [w["id"] for w in doc["widgets"]]


def normalise(doc: dict, *, owner: bool) -> dict:
    """The owner's dock always starts with Approvals: it is how agents' requests reach the person."""
    if owner:
        dock = [d for d in doc["dock"] if d != APPROVALS]
        doc = {**doc, "dock": ([APPROVALS] + dock)[:MAX_DOCK]}
    return doc


def drop_invisible(doc: dict, visible) -> dict:
    """Read-time filter: ids the person can no longer see disappear without rewriting what is stored."""
    return {
        **doc,
        "dock": [d for d in doc["dock"] if visible(d)],
        "grid": {"order": [d for d in doc["grid"]["order"] if visible(d)],
                 "hidden": [d for d in doc["grid"]["hidden"] if visible(d)]},
        "widgets": [w for w in doc["widgets"] if visible(w["id"])],
    }


class HomeService(SqlRepository):
    def stored(self, person_id: str) -> dict | None:
        with self.db.session() as s:
            row = s.get(HomeRow, person_id)
            return None if row is None else {**row.doc, "updated_at": row.updated_at.isoformat().replace("+00:00", "Z")}

    def save(self, person_id: str, doc: dict, now: datetime) -> dict:
        values = {"doc": doc, "updated_at": now}
        insert = self.db.insert()(HomeRow).values(person_id=person_id, **values)
        with self.db.session.begin() as s:
            s.execute(insert.on_conflict_do_update(index_elements=[HomeRow.person_id], set_=values))
        return {**doc, "updated_at": now.isoformat().replace("+00:00", "Z")}
