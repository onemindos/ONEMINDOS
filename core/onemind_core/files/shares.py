# SPDX-License-Identifier: Apache-2.0
"""Expiring share links (FILES-02, #237): an owner or adult lets someone outside the household
download a few of their files or photos until a set time.

What keeps a link safe:
- The link secret is 256 random bits, shown once at creation. The box keeps only its SHA-256, so
  a copy of the database cannot be turned back into working links. An optional password is kept
  as a scrypt hash (identity.crypto); ten wrong passwords end the link.
- Every link has an expiry, at most 30 days away. After it, or after a revoke, the link answers
  410 and serves nothing.
- A link carries no rights of its own. Each use re-checks the creator: they must still be an
  active owner or adult, and still able to read each item, through the same FILES confinement
  (no symlinks, no `..`, only their own Home or Shared) or their own photo library. A person who
  is demoted, disabled or loses access to a folder takes their links' reach down with them.
- A link serves only the items picked at creation: single regular files and photos, by index.
  The anonymous routes (/v1/share/...) reach nothing else, so a relay can forward that one
  prefix without exposing the rest of the box.
- Every creation, revoke, open, download and refusal is an audit record (files.share.*), with
  the link id and never the secret or the password. Download records name the item by index,
  never by path: the audit log is owner-readable, and a Home is private (files/access.py).
- An owner sees every link and may revoke any of them, but a link made by someone else is shown
  without the paths in that person's Home, their photo hashes, or the link name they typed:
  oversight of what leaves the house, without reading another person's Home.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any

from ..auth import Principal
from ..identity.crypto import hash_password, verify_password
from ..ledger import iso
from ..photos import PhotosRepository, PhotosSettings
from ..photos.files import LibraryEscape, PhotoFiles
from . import paths
from .access import is_person
from .errors import FilesError, denied, not_found
from .service import FilesService
from .store import ShareRow, aware, new_id

CREATOR_ROLES = frozenset({"owner", "adult"})
MAX_TTL = timedelta(days=30)
MIN_TTL = timedelta(minutes=5)
MAX_ITEMS = 100
MAX_ACTIVE = 200          # live links per person
MAX_FAILED = 10           # wrong passwords before the link is ended
TOKEN_PREFIX = "oms_"
TOKEN_RE = re.compile(r"^oms_[A-Za-z0-9_-]{43}$")
SHARE_ID_RE = re.compile(r"^shl_[0-9A-Z]{26}$")
PHOTO_RE = re.compile(r"^sha256:([0-9a-f]{64})$")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class ShareService:
    def __init__(self, files: FilesService, gw: Any):
        self.files = files
        self.gw = gw
        self.repo = files.repo
        self.photos_settings = gw.settings.section(PhotosSettings)
        self.photos_repo = PhotosRepository(gw.db)
        self.photo_files = PhotoFiles(self.photos_settings.dir) if self.photos_settings.dir else None

    def now(self) -> datetime:
        return self.files.clock()

    # ---- audit -----------------------------------------------------------------------------
    def event(self, name: str, p: Principal | None, share_id: str, payload: dict, severity: str = "info") -> None:
        self.gw.events.publish_event(
            "files", f"share.{name}", {"share_id": share_id, **payload}, principal=p.as_dict() if p else None,
            severity=severity, resource={"kind": "files_share", "id": share_id},
        )

    # ---- who may share ---------------------------------------------------------------------
    def _creator(self, p: Principal) -> None:
        if not is_person(p) or p.role not in CREATOR_ROLES:
            self.gw.audit.append("authz.denied", p.as_dict(), None,
                                 {"attempted": "create files share link", "reason": "permission_denied"})
            raise denied("only an owner or an adult may share files outside the household", "role")

    def current_role(self, person_id: str) -> str | None:
        """The person's role now: the tokens file, then each people source (identity accounts)."""
        for fp in self.gw.tokens.principals():
            if fp.kind == "person" and fp.id == person_id:
                return fp.role
        for source in self.gw.people_sources:
            role = source().get(person_id)
            if role is not None:
                return role
        return None

    # ---- items -----------------------------------------------------------------------------
    def _check_items(self, p: Principal, items: list[dict]) -> list[dict]:
        out = []
        for item in items:
            if "photo" in item:
                h = self._photo_hash(item["photo"])
                self._photo_path(p.id, h)  # 404 unless it is this person's own photo
                out.append({"kind": "photo", "hash": h})
            else:
                with self.files.open_file(p, item["root"], item["path"], "share") as (_fd, _st, _name):
                    pass
                t = self.files.target(p, item["root"], item["path"], "read")
                out.append({"kind": "file", "root": t.root.id, "path": t.path})
        return out

    @staticmethod
    def _photo_hash(raw: str) -> str:
        m = PHOTO_RE.match(raw)
        if not m:
            raise FilesError(422, "conflict", "a photo is sha256:<64 lower-case hex>", reason="invalid_photo")
        return m.group(1)

    def _photo_path(self, owner: str, h: str) -> str:
        if not self.photos_settings.active or self.photo_files is None or "photos" in self.gw.disabled_apps():
            raise not_found("Photos is not turned on on this box")
        found = self.photos_repo.person_asset(owner, h)
        if found is None:
            raise not_found("no such photo in your library")
        return found[1]

    @contextmanager
    def open_item(self, creator: Principal, item: dict) -> Iterator[tuple[int, os.stat_result, str]]:
        """(fd, stat, name) of one shared item, read with the creator's rights as they are now."""
        if item["kind"] == "file":
            with self.files.open_file(creator, item["root"], item["path"], "share") as opened:
                yield opened
            return
        library_path = self._photo_path(creator.id, item["hash"])
        try:
            *folder, name = paths.split_path(library_path)
            with self.photo_files._dir(tuple(folder)) as d:
                fd, st = paths.open_file_at(d, name)
        except (FileNotFoundError, LibraryEscape):
            raise not_found("the photo is no longer on the box") from None
        try:
            yield fd, st, name
        finally:
            os.close(fd)

    # ---- the creator's side ----------------------------------------------------------------
    @staticmethod
    def _private(item: dict) -> bool:
        """An item from its creator's own Home or photo library (anything but Shared)."""
        return not (item["kind"] == "file" and item["root"] == "shared")

    def json(self, row: ShareRow, viewer: Principal | None = None) -> dict:
        """The link as `viewer` may see it. The creator (or no viewer: creation) sees everything;
        anyone else (an owner) sees Shared items in full and private items only by kind."""
        now = self.now()
        state = "revoked" if row.revoked_at else ("expired" if aware(row.expires_at) <= now else "active")
        items = [dict(i) for i in row.items]
        name = row.name
        hidden = 0
        if viewer is not None and viewer.id != row.created_by:
            shown = []
            for i in items:
                if self._private(i):
                    hidden += 1
                    shown.append({"kind": i["kind"], "hidden": True,
                                  **({"root": i["root"]} if i["kind"] == "file" else {})})
                else:
                    shown.append(i)
            items = shown
            if hidden:
                name = f"{len(items)} shared item{'s' if len(items) != 1 else ''}"
        return {
            "id": row.id, "name": name, "created_by": row.created_by, "state": state,
            "items": items, "items_hidden": hidden, "password": row.password_hash is not None,
            "created_at": iso(aware(row.created_at)), "expires_at": iso(aware(row.expires_at)),
            "revoked_at": iso(aware(row.revoked_at)) if row.revoked_at else None,
            "opened_count": row.opened_count,
            "last_opened_at": iso(aware(row.last_opened_at)) if row.last_opened_at else None,
        }

    def create(self, p: Principal, name: str | None, items: list[dict], expires_at: datetime,
               password: str | None) -> dict:
        self._creator(p)
        now = self.now()
        if not MIN_TTL <= expires_at - now <= MAX_TTL:
            raise FilesError(422, "conflict", "expires_at must be between 5 minutes and 30 days from now",
                             reason="invalid_expiry")
        live = [r for r in self.repo.shares(p.id) if r.revoked_at is None and aware(r.expires_at) > now]
        if len(live) >= MAX_ACTIVE:
            raise FilesError(429, "rate_limited", f"at most {MAX_ACTIVE} live share links per person; revoke some",
                             reason="too_many_shares")
        checked = self._check_items(p, items)
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        label = "".join(c for c in (name or "") if c.isprintable()).strip()[:120]
        row = ShareRow(id=new_id("shl"), token_hash=token_hash(token), created_by=p.id,
                       name=label or f"{len(checked)} shared item{'s' if len(checked) != 1 else ''}",
                       items=checked, password_hash=hash_password(password) if password else None,
                       created_at=now, expires_at=expires_at, failed_attempts=0, opened_count=0)
        self.repo.add_share(row)
        self.event("created", p, row.id, {"items": len(checked), "password": password is not None,
                                          "expires_at": iso(expires_at)})
        return {**self.json(row), "one_time": {"token": token, "path": f"/v1/share/{token}"}}

    def _visible(self, p: Principal, row: ShareRow | None) -> bool:
        return row is not None and (row.created_by == p.id or p.is_owner)

    def list(self, p: Principal) -> list[dict]:
        if not is_person(p):
            return []
        return [self.json(r, p) for r in self.repo.shares(None if p.is_owner else p.id)]

    def revoke(self, p: Principal, share_id: str) -> dict:
        row = self.repo.share(share_id) if SHARE_ID_RE.match(share_id) else None
        if not self._visible(p, row):
            raise not_found("no such share link")
        if self.repo.revoke_share(share_id, p.id, self.now()):
            self.event("revoked", p, share_id, {"created_by": row.created_by})
        return self.json(self.repo.share(share_id), p)

    # ---- the outside user's side -----------------------------------------------------------
    def resolve(self, token: str, password: str | None) -> tuple[ShareRow, Principal]:
        """The live link for this secret and its creator as they are now, or the refusal."""
        row = self.repo.share_by_token(token_hash(token)) if TOKEN_RE.match(token) else None
        if row is None:
            raise not_found("no such share link")
        now = self.now()
        if row.revoked_at is not None or aware(row.expires_at) <= now:
            reason = "revoked" if row.revoked_at is not None else "expired"
            self.event("refused", None, row.id, {"reason": reason})
            raise FilesError(410, "expired", f"this share link has {'been revoked' if reason == 'revoked' else 'expired'}",
                             reason=reason)
        if row.password_hash is not None:
            if not password:
                raise FilesError(401, "unauthenticated", "this share link needs its password (OneMind-Share-Password)",
                                 reason="password_required")
            if not verify_password(password, row.password_hash):
                failed = self.repo.share_failed(row.id)
                self.event("refused", None, row.id, {"reason": "wrong_password", "failed_attempts": failed},
                           severity="warning")
                if failed >= MAX_FAILED and self.repo.revoke_share(row.id, "system:password-attempts", now):
                    self.event("revoked", None, row.id, {"reason": "too_many_wrong_passwords"}, severity="warning")
                raise FilesError(401, "unauthenticated", "wrong password for this share link", reason="wrong_password")
        role = self.current_role(row.created_by)
        if role not in CREATOR_ROLES:
            self.event("refused", None, row.id, {"reason": "creator_access"}, severity="warning")
            raise FilesError(410, "expired", "the person who shared this can no longer share it", reason="creator_access")
        return row, Principal(id=row.created_by, kind="person", role=role)

    def describe(self, token: str, password: str | None) -> dict:
        row, creator = self.resolve(token, password)
        items = []
        for i, item in enumerate(row.items):
            entry: dict = {"index": i, "available": False, "name": None, "size": None}
            try:
                with self.open_item(creator, item) as (_fd, st, name):
                    entry.update(available=True, name=name, size=st.st_size)
            except FilesError:
                pass  # gone, or the creator lost access: listed, but not served
            items.append(entry)
        self.repo.share_opened(row.id, self.now())
        self.event("opened", None, row.id, {"created_by": row.created_by})
        return {"name": row.name, "expires_at": iso(aware(row.expires_at)), "items": items}

    @contextmanager
    def open_download(self, token: str, password: str | None, index: int) -> Iterator[tuple[int, os.stat_result, str]]:
        row, creator = self.resolve(token, password)
        if not 0 <= index < len(row.items):
            raise not_found("no such item in this share link")
        item = row.items[index]
        try:
            with self.open_item(creator, item) as (fd, st, name):
                self.event("downloaded", None, row.id, {"index": index, "kind": item["kind"], "size": st.st_size,
                                                         "created_by": row.created_by})
                yield fd, st, name
        except FilesError as exc:
            if exc.status in (403, 404):
                self.event("refused", None, row.id, {"reason": "item_unavailable", "index": index}, severity="warning")
                raise not_found("this item is no longer shared") from None
            raise


__all__ = ["ShareService", "token_hash"]
