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
from datetime import datetime, timedelta
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import JSON, DateTime, String, update
from sqlalchemy.orm import Mapped, mapped_column

from .ledger import Base, iso, utc
from .store import FeatureSchema, SqlRepository

SCHEMA = FeatureSchema("home")

# Typed item ids (desktop-ui.md §4.2). Shortcuts and automations are a later step and not accepted yet.
ITEM_ID = re.compile(r"^(sys:[a-z][a-z0-9-]{0,39}|app:[a-z0-9][a-z0-9-]{0,62}|node:[A-Za-z0-9._-]{1,64}|link:[a-z0-9][a-z0-9-]{0,39})$")
SLUG = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
MAX_DOCK = 8
MAX_WIDGETS = 12
MAX_RECENT = 8
MAX_LIST = 200
MAX_LINKS = 50
MAX_URL = 2048
APPROVALS = "sys:approvals"


def _items(values: list[str]) -> list[str]:
    seen: list[str] = []
    for v in values:
        if not ITEM_ID.match(v):
            raise ValueError(f"{v!r} is not a valid item id (sys:<screen>, app:<id>, node:<id> or link:<id>)")
        if v not in seen:
            seen.append(v)
    return seen


class Link(BaseModel):
    """FD-02: a personal web link. Shown on Home, the dock and Launchpad as `link:<id>`; it opens a page, never runs anything."""
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,39}$")
    name: str = Field(min_length=1, max_length=60)
    url: str = Field(max_length=MAX_URL)
    icon: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{0,39}$")

    @field_validator("name")
    @classmethod
    def plain_name(cls, v: str) -> str:
        v = v.strip()
        if not v or any(ord(c) < 32 or ord(c) == 127 for c in v):
            raise ValueError("a link needs a plain name")
        return v

    @field_validator("url")
    @classmethod
    def https_only(cls, v: str) -> str:
        if any(c.isspace() or ord(c) < 32 or ord(c) == 127 or c == "\\" for c in v):
            raise ValueError("the link address must not contain spaces, control characters or backslashes")
        try:
            parts = urlsplit(v)
            host = parts.hostname
            parts.port  # raises ValueError for a bad port
        except ValueError as e:
            raise ValueError("not a valid web address") from e
        if parts.scheme != "https" or not host:
            raise ValueError("only https:// links are accepted")
        if parts.username is not None or parts.password is not None:
            raise ValueError("a link must not carry a user name or password")
        return v


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
    recent: list[str] = Field(default_factory=list, max_length=MAX_RECENT)
    links: list[Link] = Field(default_factory=list, max_length=MAX_LINKS)
    seen: Seen = Field(default_factory=Seen)
    updated_at: str | None = None

    @field_validator("dock", "recent")
    @classmethod
    def typed(cls, v: list[str]) -> list[str]:
        return _items(v)

    @field_validator("links")
    @classmethod
    def unique_links(cls, v: list[Link]) -> list[Link]:
        ids = [x.id for x in v]
        if len(set(ids)) != len(ids):
            raise ValueError("link ids must be unique")
        return v


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
    return ids + [w["id"] for w in doc["widgets"]] + doc.get("recent", [])


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
        "recent": [item for item in doc.get("recent", []) if visible(item)],
    }


def link_ids(doc: dict) -> set[str]:
    return {f"link:{x['id']}" for x in doc.get("links", [])}


class HomeService(SqlRepository):
    def stored(self, person_id: str) -> dict | None:
        with self.db.session() as s:
            row = s.get(HomeRow, person_id)
            return None if row is None else {**row.doc, "updated_at": iso(row.updated_at)}

    def save(self, person_id: str, doc: dict, now: datetime, previous: str | None) -> dict | None:
        """Compare at the database write too, so simultaneous device writes cannot lose a visit."""
        with self.db.session.begin() as s:
            if previous is None:
                stmt = self.db.insert()(HomeRow).values(person_id=person_id, doc=doc, updated_at=now)
                stmt = stmt.on_conflict_do_nothing(index_elements=["person_id"])
            else:
                prior = utc(datetime.fromisoformat(previous))
                now = max(now, prior + timedelta(microseconds=1))
                stmt = update(HomeRow).where(HomeRow.person_id == person_id, HomeRow.updated_at == prior)
                stmt = stmt.values(doc=doc, updated_at=now)
            if s.scalar(stmt.returning(HomeRow.person_id)) is None:
                return None
        return {**doc, "updated_at": iso(now)}
