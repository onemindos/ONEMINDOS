# SPDX-License-Identifier: Apache-2.0
"""The offline content manager (NMD-02, #127): which Kiwix books this box keeps, and their updates.

What it changes is one thing: the Kiwix app's `zims` setting (apps/kiwix/onemind.app.yaml). Every
change is an `app.configure` action on kiwix, so it waits for an owner's approval like any other
app change; the app's own library manager (library-sync.sh) then downloads, checks and serves the
books. Nothing here downloads a file or writes to the app's volume.

- A plan says what a change does before anything is filed: the books to download, with their size
  from the live Kiwix catalogue, and the books that stop being served.
- A change is filed only with the download size the owner was shown; if the catalogue moved since,
  it is refused (409 size_changed) and the page shows the new size first.
- Auto-update: inside the owner's chosen maintenance window, at most once per window, the updater
  compares each book with the newest release in the catalogue and REQUESTS the update as
  `automation:content-update`. It never approves: the owner does, or a standing approval the owner
  wrote (docs/leap/core/AUTOMATION.md §4).

Removing a book takes it out of the list, so Kiwix stops serving it. The file stays on the volume
until the owner deletes it (apps/kiwix/README.md "Remove a book"): library-sync never deletes.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy import BigInteger, Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from ..actions import ActionParams, ActionRequest
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError
from ..ledger import TERMINAL, Base, iso, utc
from ..store import FeatureSchema, SqlRepository
from .kiwix import Book, CatalogError, KiwixCatalog, book_date, book_key
from .packs import PACKS, wikipedia_name

log = logging.getLogger("onemind.content")

SCHEMA = FeatureSchema("content")  # version 1 = the shape below

KIWIX = "kiwix"
SETTING = "zims"
MAX_SETTING_LEN = 2048  # the manifest's maxLength for `zims`
DEFAULT_WINDOW = "win_nightly"  # seeded by the automation feature (automation/store.py)
UPDATER = Principal(id="automation:content-update", kind="automation", role="automation")
TICK_S = 900.0
RECHECK = timedelta(hours=12)  # one check per nightly window, not one per tick
REQUEST_TTL = timedelta(hours=24)
FLAVOURS = ("mini", "nopic", "maxi")


class ContentPrefsRow(Base):
    __tablename__ = "content_prefs"
    app_id: Mapped[str] = mapped_column(String(59), primary_key=True)
    auto_update: Mapped[bool] = mapped_column(Boolean, default=False)
    window_id: Mapped[str] = mapped_column(String(40))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_result: Mapped[str | None] = mapped_column(String(300), nullable=True)
    last_action_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    last_download_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ContentRepository(SqlRepository):
    def get(self) -> dict:
        with self.db.session() as s:
            row = s.get(ContentPrefsRow, KIWIX)
            if row is None:
                return {"auto_update": False, "window_id": DEFAULT_WINDOW, "last_checked_at": None,
                        "last_result": None, "last_action_id": None, "last_download_bytes": None}
            return {"auto_update": row.auto_update, "window_id": row.window_id, "last_checked_at": row.last_checked_at,
                    "last_result": row.last_result, "last_action_id": row.last_action_id,
                    "last_download_bytes": row.last_download_bytes}

    def put(self, now: datetime, **values) -> None:
        with self.db.session.begin() as s:
            row = s.get(ContentPrefsRow, KIWIX)
            if row is None:
                row = ContentPrefsRow(app_id=KIWIX, auto_update=False, window_id=DEFAULT_WINDOW, updated_at=now)
                s.add(row)
            for k, v in values.items():
                setattr(row, k, v)
            row.updated_at = now


def split_stem(stem: str) -> tuple[str, str]:
    """`wikipedia_en_medicine_maxi` -> (`wikipedia_en_medicine`, `maxi`); no known flavour -> (stem, "")."""
    head, _, tail = stem.rpartition("_")
    return (head, tail) if head and tail in FLAVOURS else (stem, "")


def stem_of(name: str, flavour: str) -> str:
    return f"{name}_{flavour}" if flavour else name


def _stem(path: str) -> str:
    return book_key(path).split("/", 1)[-1]


class _Declined(Exception):
    """The owner already denied this exact update."""


class ContentService:
    def __init__(self, gw: Gateway, appstore, catalog: KiwixCatalog | None = None,
                 window_open: Callable[[str, datetime], bool] | None = None,
                 window_exists: Callable[[str], bool] | None = None):
        self.gw = gw
        self.appstore = appstore  # appstore/service.py: the app's declared settings and stored values
        self.catalog = catalog or KiwixCatalog()
        self.repo = ContentRepository(gw.db)
        self.window_open = window_open or (lambda _w, _at: False)
        self.window_exists = window_exists or (lambda _w: False)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._tick_lock = threading.Lock()

    # ---- what the box has -------------------------------------------------------------------------
    def kiwix_status(self) -> tuple[bool, str]:
        if self.gw.catalog.get(KIWIX) is None:
            return False, "not_in_catalog"
        st = self.gw.repo.list_app_states().get(KIWIX)
        status = st.status if st else "not_installed"
        return True, "not_installed" if status == "removed" else status

    def current(self) -> list[str]:
        """The books in the Kiwix `zims` setting now (the manifest default until the owner changes it)."""
        from ..appstore import appsettings

        entry = self.gw.catalog.get(KIWIX)
        store = self.appstore
        if entry is None:
            return []
        stored, _, _ = store.repo.get_settings(KIWIX)
        value = appsettings.effective(store.fields(entry), stored).get(SETTING) or ""
        return [p for p in str(value).split() if p]

    def pending(self) -> dict | None:
        """The newest open app.configure on kiwix that changes `zims`, if any."""
        open_ = [a for a in self.gw.actions.list()
                 if a["type"] == "app.configure" and a["params"].get("app_id") == KIWIX
                 and SETTING in (a["params"].get("settings") or {}) and a["state"] not in TERMINAL]
        return max(open_, key=lambda a: a["created_at"]) if open_ else None

    def _require_kiwix(self) -> None:
        in_catalog, _ = self.kiwix_status()
        if not in_catalog:
            raise ApiError(409, "stale_precondition", "Kiwix is not in this box's app catalogue, so there is no library to manage.",
                           reason="kiwix_missing")

    def _book(self, name: str, flavour: str) -> Book | None:
        try:
            return self.catalog.book(name, flavour)
        except CatalogError as exc:
            raise ApiError(503, "unavailable", f"{exc}. Sizes cannot be shown, so nothing is downloaded.",
                           reason="catalog_unreachable", retry_after_s=60) from None

    # ---- reads ---------------------------------------------------------------------------------------
    def wikipedia(self, lang: str) -> list[dict]:
        self._require_kiwix()
        try:
            books = self.catalog.books(wikipedia_name(lang))
        except CatalogError as exc:
            raise ApiError(503, "unavailable", str(exc), reason="catalog_unreachable", retry_after_s=60) from None
        return [b.to_json() for b in books]

    def view(self) -> dict:
        in_catalog, status = self.kiwix_status()
        prefs = self.repo.get()
        current = self.current() if in_catalog else []
        stems = {_stem(p) for p in current}
        packs = [{**p, "books": [{**b, "in_library": stem_of(b["name"], b["flavour"]) in stems} for b in p["books"]]}
                 for p in PACKS]
        pending = self.pending() if in_catalog else None
        return {
            "app": {"id": KIWIX, "in_catalog": in_catalog, "status": status},
            "library": [{"path": p, "name": split_stem(_stem(p))[0], "flavour": split_stem(_stem(p))[1],
                         "date": book_date(p)} for p in current],
            "packs": packs,
            "pending_action_id": pending["id"] if pending else None,
            "auto_update": self._prefs_json(prefs),
        }

    def _prefs_json(self, prefs: dict) -> dict:
        return {"enabled": prefs["auto_update"], "window_id": prefs["window_id"],
                "window_open": self.window_open(prefs["window_id"], self.gw.clock()),
                "last_checked_at": iso(prefs["last_checked_at"]) if prefs["last_checked_at"] else None,
                "last_result": prefs["last_result"], "last_action_id": prefs["last_action_id"],
                "last_download_bytes": prefs["last_download_bytes"]}

    # ---- plans ---------------------------------------------------------------------------------------
    def plan(self, add: list[dict], remove: list[dict]) -> dict:
        self._require_kiwix()
        before = self.current()
        after = list(before)
        removed: list[str] = []
        for ref in remove:
            stem = stem_of(ref["name"], ref["flavour"])
            for p in [p for p in after if _stem(p) == stem]:
                after.remove(p)
                removed.append(p)
        downloads: list[Book] = []
        for ref in add:
            book = self._book(ref["name"], ref["flavour"])
            if book is None:
                raise ApiError(422, "conflict", f"{stem_of(ref['name'], ref['flavour'])} is not in the Kiwix catalogue.",
                               reason="not_in_catalog")
            after = self._put(after, book, removed)
            if book.path not in before and book not in downloads:
                downloads.append(book)
        return self._plan_json(before, after, downloads, removed)

    def updates(self) -> dict:
        """The newer release of every book in the library that the catalogue has one for."""
        self._require_kiwix()
        before = self.current()
        after = list(before)
        downloads: list[Book] = []
        replaced: list[str] = []
        for p in before:
            if book_date(p) is None:
                continue
            name, flavour = split_stem(_stem(p))
            book = self._book(name, flavour)
            if book is not None and book.key == book_key(p) and (book_date(book.path) or "") > (book_date(p) or ""):
                after = self._put(after, book, replaced)
                downloads.append(book)
        return self._plan_json(before, after, downloads, replaced)

    @staticmethod
    def _put(after: list[str], book: Book, removed: list[str]) -> list[str]:
        """Add `book`, replacing an older release of the same book in place."""
        out = []
        placed = False
        for p in after:
            if book_key(p) == book.key:
                if not placed:
                    out.append(book.path)
                    placed = True
                if p != book.path:
                    removed.append(p)
            else:
                out.append(p)
        return out if placed else [*out, book.path]

    @staticmethod
    def _plan_json(before: list[str], after: list[str], downloads: list[Book], removed: list[str]) -> dict:
        return {"zims_before": before, "zims_after": after, "downloads": [b.to_json() for b in downloads],
                "removed": sorted(set(removed)), "download_bytes": sum(b.size_bytes for b in downloads),
                "changed": after != before}

    # ---- filing --------------------------------------------------------------------------------------
    def _file(self, principal: Principal, plan: dict, idempotency_key: str, reason: str) -> dict:
        value = " ".join(plan["zims_after"])
        if len(value) > MAX_SETTING_LEN:
            raise ApiError(422, "conflict", f"The book list would be {len(value)} characters; Kiwix takes at most "
                           f"{MAX_SETTING_LEN}. Remove a book first.", reason="too_many_books")
        req = ActionRequest(type="app.configure", params=ActionParams(app_id=KIWIX, settings={SETTING: value}),
                            idempotency_key=idempotency_key, expires_at=self.gw.clock() + REQUEST_TTL)
        action, _ = self.gw.actions.create(principal, req, reason=reason)
        return action

    def request_change(self, p: Principal, add: list[dict], remove: list[dict], download_bytes: int,
                       idempotency_key: str) -> dict:
        plan = self.plan(add, remove)
        if not plan["changed"]:
            raise ApiError(409, "conflict", "The library already has exactly these books.", reason="no_change")
        if download_bytes != plan["download_bytes"]:
            raise ApiError(409, "stale_precondition", "The download size changed since it was shown "
                           f"({plan['download_bytes']} bytes now). Look at the new size and send again.",
                           reason="size_changed")
        action = self._file(p, plan, idempotency_key,
                            f"content manager: {len(plan['downloads'])} to download ({plan['download_bytes']} bytes), "
                            f"{len(plan['removed'])} to stop serving")
        return {"action": action, "plan": plan}

    def set_prefs(self, p: Principal, enabled: bool, window_id: str) -> dict:
        if not self.window_exists(window_id):
            raise ApiError(422, "conflict", f"There is no maintenance window {window_id!r}.", reason="unknown_window")
        self.repo.put(self.gw.clock(), auto_update=enabled, window_id=window_id)
        self.gw.audit.append("content.auto_update.set", p.as_dict(), None, {"enabled": enabled, "window_id": window_id})
        return self._prefs_json(self.repo.get())

    # ---- auto-update ---------------------------------------------------------------------------------
    def _update_key(self, plan: dict, digest: str, now: datetime) -> tuple[str, bool]:
        """Idempotency key for this plan, and whether the owner already declined it.

        A request's key is reused only while no earlier request for the same book list exists. If the newest
        earlier one was denied (state `cancelled`), do not file again. If it expired or otherwise ended, file
        again under a key that carries the window date, because the old key is bound to the old `expires_at`.
        """
        value = " ".join(plan["zims_after"])
        earlier = [a for a in self.gw.actions.list()
                   if a["type"] == "app.configure" and a["requested_by"].get("id") == UPDATER.id
                   and (a["params"].get("settings") or {}).get(SETTING) == value]
        if not earlier:
            return f"content-update-{digest}", False
        newest = max(earlier, key=lambda a: a["created_at"])
        if newest["state"] == "cancelled":
            return newest["idempotency_key"], True
        return f"content-update-{digest}-{utc(now):%Y%m%d}", False

    def tick(self) -> str | None:
        """One auto-update check. Returns what it recorded (None when it had nothing to do yet)."""
        with self._tick_lock:
            now = self.gw.clock()
            prefs = self.repo.get()
            if not prefs["auto_update"] or not self.window_open(prefs["window_id"], now):
                return None
            last = prefs["last_checked_at"]
            if last is not None and utc(now) - utc(last) < RECHECK:
                return None
            action_id, size = None, None
            in_catalog, status = self.kiwix_status()
            if not in_catalog or status != "installed":
                result = "Kiwix is not installed; nothing to update."
            elif (open_ := self.pending()) is not None:
                result = "An earlier library change still waits for approval; no new request."
                action_id = open_["id"]
            else:
                try:
                    plan = self.updates()
                except ApiError as exc:
                    plan, result = None, exc.message[:300]
                if plan is not None and not plan["changed"]:
                    result = "Every book is the newest release."
                elif plan is not None:
                    digest = hashlib.sha256(" ".join(plan["zims_after"]).encode()).hexdigest()[:24]
                    key, declined = self._update_key(plan, digest, now)
                    if declined:
                        result = "You declined this update; no new request until a newer release is published."
                    else:
                        result = None
                    try:
                        if declined:
                            raise _Declined
                        action = self._file(UPDATER, plan, key,
                                            f"content auto-update: {len(plan['downloads'])} newer release(s), "
                                            f"{plan['download_bytes']} bytes")
                    except _Declined:
                        pass
                    except ApiError as exc:
                        result = exc.message[:300]
                    else:
                        action_id, size = action["id"], plan["download_bytes"]
                        result = f"Requested {len(plan['downloads'])} update(s); waiting for the owner's approval."
            self.repo.put(now, last_checked_at=now, last_result=result, last_action_id=action_id,
                          last_download_bytes=size)
            self.gw.audit.append("content.auto_update.checked", UPDATER.as_dict(), action_id,
                                 {"result": result, "download_bytes": size})
            return result

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="onemind-content", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        next_tick = time.monotonic() + 60
        while not self._stop.wait(timeout=max(0.0, next_tick - time.monotonic())):
            next_tick = time.monotonic() + TICK_S
            try:
                self.tick()
            except Exception:  # one bad check must not stop the next one
                log.exception("content auto-update check failed")
