# SPDX-License-Identifier: Apache-2.0
"""The change log behind OneMind Sync (docs/design/SYNC.md).

One append-only table for every app: each accepted change is a row with a gateway-wide sequence
number (the cursor), the app, the owning person, the item id, the item's version and its data (null
for a tombstone). An item's current state is its newest row. A person's feed for an app is their rows
after a cursor, so another person's items never reach it.

Pushes are applied under one lock, so sequence numbers commit in order and a reader never skips a row
that commits late (single gateway process; SYNC.md §8 says what a second process needs).
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column

from ..errors import ApiError
from ..ledger import Base, iso
from ..store import FeatureSchema, SqlRepository

SCHEMA = FeatureSchema("sync")
ITEM_RE = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"  # client-made ids (offline); also a NATS subject id token
KEY_RE = r"^[A-Za-z0-9_.:-]{8,80}$"    # one idempotency key per client operation
CURSOR_RE = r"^[0-9]{1,18}$"           # opaque to clients; today the log's sequence number
PUSH_MAX = 100                         # operations in one push
_LOCK = threading.Lock()


@dataclass(frozen=True)
class SyncApp:
    """An app on the sync contract: its id (the path segment) and the model of what a client sends."""
    id: str
    record: type[BaseModel]


class SyncChangeRow(Base):
    __tablename__ = "sync_changes"
    __table_args__ = (Index("ix_sync_changes_feed", "app", "owner_id", "seq"),
                      Index("ix_sync_changes_item", "app", "owner_id", "item_id", "seq"),
                      {"sqlite_autoincrement": True})
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app: Mapped[str] = mapped_column(String(40))
    owner_id: Mapped[str] = mapped_column(String(200))
    item_id: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    deleted: Mapped[bool] = mapped_column(Boolean)
    conflict_of: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SyncReceiptRow(Base):
    """What one client operation did, kept so a replay of its key is answered, not applied again."""
    __tablename__ = "sync_receipts"
    app: Mapped[str] = mapped_column(String(40), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    op_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def copy_id(item_id: str, key: str) -> str:
    """The id of the conflict copy an operation makes: fixed by its key, so a retry names the same copy."""
    return f"{item_id[:40]}-conflict-{hashlib.sha256(key.encode()).hexdigest()[:12]}"


class SyncLog(SqlRepository):
    def changes(self, app: SyncApp, owner_id: str, cursor: str | None, limit: int) -> tuple[list[dict], bool]:
        """The owner's changes after the cursor, oldest first, and whether more are waiting."""
        after = int(cursor) if cursor else 0
        with self.db.session() as s:
            rows = list(s.scalars(select(SyncChangeRow).where(
                SyncChangeRow.app == app.id, SyncChangeRow.owner_id == owner_id, SyncChangeRow.seq > after,
            ).order_by(SyncChangeRow.seq).limit(limit + 1)))
        return [self._view(r) for r in rows[:limit]], len(rows) > limit

    @staticmethod
    def _view(r: SyncChangeRow) -> dict:
        data = None if r.deleted else {**(r.data or {}), "id": r.item_id, "updated_at": iso(r.changed_at)}
        return {"cursor": str(r.seq), "item_id": r.item_id, "version": r.version, "deleted": r.deleted,
                "conflict_of": r.conflict_of, "changed_at": iso(r.changed_at), "data": data}

    def push(self, app: SyncApp, owner_id: str, ops: list[dict], now: datetime) -> list[dict]:
        """Apply each operation once, in order, in one transaction. A stale base never overwrites:
        an edit becomes a conflict copy next to the newer item, a delete is dropped."""
        keys = [o["key"] for o in ops]
        if len(set(keys)) != len(keys):
            raise ApiError(422, "conflict", "each operation in a push needs its own key", reason="duplicate_key")
        results = []
        with _LOCK, self.db.session.begin() as s:
            for op in ops:
                op_hash = hashlib.sha256(json.dumps(op, sort_keys=True, default=str).encode()).hexdigest()
                seen = s.get(SyncReceiptRow, (app.id, owner_id, op["key"]))
                if seen is not None:
                    if seen.op_hash != op_hash:
                        raise ApiError(409, "conflict", f"key {op['key']} was already used for a different change",
                                       reason="key_reused")
                    results.append({**seen.result, "replayed": True})
                    continue
                result = self._apply(s, app, owner_id, op, now)
                s.add(SyncReceiptRow(app=app.id, owner_id=owner_id, key=op["key"], op_hash=op_hash,
                                     result=result, created_at=now))
                s.flush()
                results.append({**result, "replayed": False})
        return results

    def _apply(self, s, app: SyncApp, owner_id: str, op: dict, now: datetime) -> dict:
        item_id, base, delete = op["item_id"], op["base_version"], op["op"] == "delete"
        cur = s.scalars(select(SyncChangeRow).where(
            SyncChangeRow.app == app.id, SyncChangeRow.owner_id == owner_id, SyncChangeRow.item_id == item_id,
        ).order_by(SyncChangeRow.seq.desc()).limit(1)).first()
        version = cur.version if cur else None

        def write(iid: str, v: int, conflict_of: str | None = None) -> None:
            s.add(SyncChangeRow(app=app.id, owner_id=owner_id, item_id=iid, version=v, deleted=delete,
                                conflict_of=conflict_of, data=None if delete else op["data"], changed_at=now))

        if delete and (cur is None or cur.deleted):
            return {"key": op["key"], "status": "applied", "item_id": item_id, "version": version or 0, "conflict_of": None}
        if base == version:
            write(item_id, (version or 0) + 1)
            return {"key": op["key"], "status": "applied", "item_id": item_id, "version": (version or 0) + 1,
                    "conflict_of": None}
        if delete:  # someone changed it since this device saw it: the newer edit stays
            return {"key": op["key"], "status": "conflict", "item_id": item_id, "version": version, "conflict_of": None}
        copy = copy_id(item_id, op["key"])
        write(copy, 1, conflict_of=item_id)
        return {"key": op["key"], "status": "conflict", "item_id": copy, "version": 1, "conflict_of": item_id}
