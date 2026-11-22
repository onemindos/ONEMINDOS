# SPDX-License-Identifier: Apache-2.0
"""The one local search index: a SQLite FTS5 file in the gateway's cache folder (#611).

The file is a cache, never a source of truth: every row comes from a provider (service.py), so a
missing, corrupt or older-format file is deleted and filled again from the providers on the next
query. It lives on the box only (mode 0600 in a 0700 folder), is not in any backup unit, and nothing
here opens a network connection.

items      one row per searchable thing: (provider, item_id) is unique; `app_id` is the app the item
           belongs to (a disabled app's items are dropped at query time); `scope` and `key` are what
           the provider needs to decide who may see it (a Files root and path, an app and a route).
items_fts  the FTS5 index over title and body (external content: the text lives in `items`).
meta       the format version and each provider's cursors (where its last refresh stopped).
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("onemind.search")

FORMAT = "1"
TOKEN_RE = re.compile(r"\w+")
MAX_TOKENS = 12
PAGE = 200          # rows read from the index per step while filtering by the asker's grants
SCAN_MAX = 5000     # most rows looked at for one query, so a query that matches only hidden items stays cheap

_SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE items(
  rowid INTEGER PRIMARY KEY,
  provider TEXT NOT NULL, item_id TEXT NOT NULL, type TEXT NOT NULL, app_id TEXT NOT NULL,
  scope TEXT NOT NULL, key TEXT NOT NULL, title TEXT NOT NULL, subtitle TEXT, body TEXT NOT NULL,
  link TEXT NOT NULL, UNIQUE(provider, item_id));
CREATE INDEX items_scope ON items(provider, scope);
CREATE VIRTUAL TABLE items_fts USING fts5(title, body, content='items', content_rowid='rowid',
  tokenize='unicode61 remove_diacritics 2');
CREATE TRIGGER items_ai AFTER INSERT ON items BEGIN
  INSERT INTO items_fts(rowid, title, body) VALUES (new.rowid, new.title, new.body); END;
CREATE TRIGGER items_ad AFTER DELETE ON items BEGIN
  INSERT INTO items_fts(items_fts, rowid, title, body) VALUES ('delete', old.rowid, old.title, old.body); END;
CREATE TRIGGER items_au AFTER UPDATE ON items BEGIN
  INSERT INTO items_fts(items_fts, rowid, title, body) VALUES ('delete', old.rowid, old.title, old.body);
  INSERT INTO items_fts(rowid, title, body) VALUES (new.rowid, new.title, new.body); END;
"""
_COLS = ("item_id", "type", "app_id", "scope", "key", "title", "subtitle", "body", "link")


class SearchUnavailable(Exception):
    """The index cannot be opened (no FTS5 in this SQLite build, or the cache folder is not writable)."""


@dataclass(frozen=True)
class Item:
    """One searchable thing, as a provider hands it to the index and as a query returns it."""

    id: str              # unique within the provider
    type: str            # one of the provider's declared types (descriptor spec.search.types)
    app_id: str          # the app it belongs to: hidden while that app is switched off or not shared with the asker
    scope: str           # provider-defined: what visibility is decided on (a Files root, an app id)
    key: str             # provider-defined: the rest of it (a path inside the root, the route a page reads)
    title: str
    link: str            # deep link: onemind://app/<app id>/<route>
    subtitle: str | None = None
    body: str = ""       # extra searchable text, never returned
    provider: str = ""   # set by the index on the way out


def match_expression(q: str) -> str | None:
    """A safe FTS5 query from free text: each word must appear, as a word or a word prefix."""
    tokens = TOKEN_RE.findall(q)[:MAX_TOKENS]
    return " ".join(f'"{t}"*' for t in tokens) or None


class Writer:
    """What one provider may change in the index: only its own rows and cursors."""

    def __init__(self, conn: sqlite3.Connection, provider: str):
        self._c = conn
        self.provider = provider

    def cursor(self, name: str) -> str | None:
        row = self._c.execute("SELECT value FROM meta WHERE key = ?", (f"cursor:{self.provider}:{name}",)).fetchone()
        return row[0] if row else None

    def set_cursor(self, name: str, value: str | None) -> None:
        k = f"cursor:{self.provider}:{name}"
        if value is None:
            self._c.execute("DELETE FROM meta WHERE key = ?", (k,))
        else:
            self._c.execute("INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                            (k, value))

    def put(self, item: Item) -> None:
        vals = [getattr(item, "id" if c == "item_id" else c) for c in _COLS]
        sets = ", ".join(f"{c} = excluded.{c}" for c in _COLS[1:])
        self._c.execute(f"INSERT INTO items(provider, {', '.join(_COLS)}) VALUES (?{', ?' * len(_COLS)}) "
                        f"ON CONFLICT(provider, item_id) DO UPDATE SET {sets}", [self.provider, *vals])

    def delete(self, item_id: str) -> None:
        self._c.execute("DELETE FROM items WHERE provider = ? AND item_id = ?", (self.provider, item_id))

    def scopes(self) -> set[str]:
        return {r[0] for r in self._c.execute("SELECT DISTINCT scope FROM items WHERE provider = ?", (self.provider,))}

    def delete_scope(self, scope: str) -> None:
        self._c.execute("DELETE FROM items WHERE provider = ? AND scope = ?", (self.provider, scope))

    def clear(self) -> None:
        self._c.execute("DELETE FROM items WHERE provider = ?", (self.provider,))
        self._c.execute("DELETE FROM meta WHERE key LIKE ?", (f"cursor:{self.provider}:%",))


class SearchIndex:
    """One SQLite connection, used under a lock by every gateway thread."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None

    def _open(self) -> sqlite3.Connection:
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise SearchUnavailable(f"cannot create the search cache folder: {exc.__class__.__name__}") from None
        for attempt in (1, 2):
            try:
                self._create_private()
                conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
                os.chmod(self.path, 0o600)
                row = None
                try:
                    row = conn.execute("SELECT value FROM meta WHERE key = 'format'").fetchone()
                except sqlite3.OperationalError:
                    pass  # a new file (or one that is not ours)
                if row is None or row[0] != FORMAT:
                    conn.close()
                    self._drop()
                    self._create_private()
                    conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
                    os.chmod(self.path, 0o600)
                    conn.executescript("BEGIN;" + _SCHEMA + f"INSERT INTO meta VALUES ('format', '{FORMAT}'); COMMIT;")
                return conn
            except sqlite3.DatabaseError as exc:
                if "fts5" in str(exc).lower():
                    raise SearchUnavailable("this SQLite build has no FTS5") from None
                log.warning("search index unreadable (%s); rebuilding it", exc.__class__.__name__)
                self._drop()
                if attempt == 2:
                    raise SearchUnavailable("the search index cannot be created") from None
            except OSError as exc:
                raise SearchUnavailable(f"the search index cannot be opened: {exc.__class__.__name__}") from None
        raise SearchUnavailable("the search index cannot be created")  # pragma: no cover

    def _create_private(self) -> None:
        """Create the file 0600 before SQLite opens it, so it is never readable by others, even briefly."""
        os.close(os.open(self.path, os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600))

    def _drop(self) -> None:
        for suffix in ("", "-journal", "-wal", "-shm"):
            try:
                os.unlink(f"{self.path}{suffix}")
            except FileNotFoundError:
                pass

    def conn(self) -> sqlite3.Connection:
        """The open connection; reopened (and rebuilt) when the file was removed or replaced."""
        with self.lock:
            if self._conn is not None and not self.path.exists():
                self._conn.close()
                self._conn = None
            if self._conn is None:
                self._conn = self._open()
            return self._conn

    @contextmanager
    def writer(self, provider: str) -> Iterator[Writer]:
        """One transaction for one provider's refresh: all of it lands, or none of it."""
        with self.lock:
            c = self.conn()
            c.execute("BEGIN")
            try:
                yield Writer(c, provider)
            except BaseException:
                c.execute("ROLLBACK")
                raise
            c.execute("COMMIT")

    def matches(self, expr: str, providers: list[str]) -> Iterator[Item]:
        """Items matching `expr` from these providers, best first, read a page at a time."""
        if not providers:
            return
        marks = ",".join("?" * len(providers))
        sql = (f"SELECT i.provider, {', '.join('i.' + c for c in _COLS)} FROM items_fts JOIN items i "
               f"ON i.rowid = items_fts.rowid WHERE items_fts MATCH ? AND i.provider IN ({marks}) "
               "ORDER BY bm25(items_fts, 10.0, 1.0), i.rowid LIMIT ? OFFSET ?")
        offset = 0
        while offset < SCAN_MAX:
            with self.lock:
                rows = self.conn().execute(sql, [expr, *providers, PAGE, offset]).fetchall()
            for r in rows:
                yield Item(provider=r[0], id=r[1], type=r[2], app_id=r[3], scope=r[4], key=r[5],
                           title=r[6], subtitle=r[7], body=r[8], link=r[9])
            if len(rows) < PAGE:
                return
            offset += PAGE

    def close(self) -> None:
        with self.lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
