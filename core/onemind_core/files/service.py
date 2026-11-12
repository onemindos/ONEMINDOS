# SPDX-License-Identifier: Apache-2.0
"""FILES service: browse, metadata, moves, trash, quotas, folder grants and their approvals.

Data plane vs control plane (docs/umbrel2/files-backups.md §4.1, decision D-F1): a person
reading or changing files inside a space they already hold is a direct, audited write. What
changes who can reach what (a folder grant to an app or agent) or destroys data for good
(emptying a trash) is a request that only an owner approves (§12.1, §12.3).

Every write appends to the audit log through `publish_event("files", ...)`, which also tells
NATS and in-process subscribers. Agent reads are audited as well (§4.6).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import stat as stat_mod
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from ..auth import Principal
from ..ledger import iso, utc
from . import paths
from .access import NONE, READ, READ_WRITE, Access, Root, has_home, is_person, parse_root, person_access
from .errors import FilesError, conflict, denied, not_found
from .preview import describe, guess_mime
from .settings import FilesSettings
from .store import FilesRepository, GrantRow, RequestRow, TrashRow, aware, new_id

log = logging.getLogger("onemind.files")

SHARED_TRASH = "@shared"          # the household trash: items deleted from Shared
SYSTEM_DIR = ".system"            # beside home/ and shared/, never inside a space
MAX_PENDING = 10                  # §12.1: awaiting_approval requests per non-owner requester
REQUEST_TTL = timedelta(hours=24)
REQUEST_TTL_MAX = timedelta(days=7)
GRANT_SUBJECTS = ("app", "agent")


def _ensure_dir(parent_fd: int, name: str, mode: int = 0o750) -> int:
    try:
        os.mkdir(name, mode, dir_fd=parent_fd)
    except FileExistsError:
        pass
    try:
        return os.open(name, paths.O_DIR, dir_fd=parent_fd)
    except OSError as exc:
        raise paths.os_error(exc) from None


def _trash_dir_name(person_id: str, space_dirs: Callable[[str], str]) -> str:
    return "_shared" if person_id == SHARED_TRASH else space_dirs(person_id)


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


@dataclass
class Target:
    """A resolved (root, path) a principal is allowed to touch."""

    root: Root
    parts: tuple[str, ...]
    access: Access

    @property
    def path(self) -> str:
        return paths.join(self.parts)


class FilesService:
    def __init__(self, gw: Any, settings: FilesSettings | None = None, repo: FilesRepository | None = None):
        self.gw = gw
        self.settings = settings or gw.settings.section(FilesSettings)
        self.repo = repo or FilesRepository(gw.db)
        self.clock: Callable[[], datetime] = gw.clock
        self._lock = threading.RLock()

    # ---- events and audit ---------------------------------------------------------------
    def event(self, name: str, p: Principal | None, payload: dict, *, severity: str = "info",
              request_id: str | None = None) -> None:
        self.gw.events.publish_event(
            "files", name, payload, principal=p.as_dict() if p else None, severity=severity,
            resource={"kind": "files", "id": payload.get("root") or payload.get("request_id") or "files"},
            causation_id=request_id,
        )

    def _deny(self, p: Principal, attempted: str, message: str, reason: str | None = None) -> FilesError:
        self.gw.audit.append("authz.denied", p.as_dict(), None,
                             {"attempted": attempted, "reason": reason or "permission_denied"})
        return denied(message, reason)

    def _audit_read(self, p: Principal, op: str, t: Target, size: int | None = None) -> None:
        if not is_person(p):  # §4.6: every agent file read is audited with path and size
            payload = {"op": op, "root": t.root.id, "path": t.path}
            if size is not None:
                payload["size"] = size
            self.event("read", p, payload)

    # ---- the directory layout -----------------------------------------------------------
    @contextmanager
    def _base(self) -> Iterator[int]:
        base = self.settings.root
        try:
            base.mkdir(mode=0o750, parents=True, exist_ok=True)
            fd = os.open(base, paths.O_DIR)
        except OSError as exc:
            log.error("files root %s is not usable: %s", base, exc)
            raise FilesError(503, "unavailable", "the files storage is not available", reason="storage_unavailable") from None
        try:
            yield fd
        finally:
            os.close(fd)

    def space_dir_name(self, person_id: str) -> str:
        return self.repo.space_dir(person_id, self.clock())

    @contextmanager
    def _space(self, root: Root) -> Iterator[int]:
        """Descriptor of a space's own directory, created on first use."""
        with self._base() as base:
            top = _ensure_dir(base, "home" if root.kind == "home" else "shared")
            try:
                if root.kind == "home":
                    fd = _ensure_dir(top, self.space_dir_name(root.person_id))
                    os.close(top)
                    top = fd
                yield top
            finally:
                os.close(top)

    @contextmanager
    def _system(self, *names: str) -> Iterator[int]:
        with self._base() as base:
            fd = _ensure_dir(base, SYSTEM_DIR, 0o700)
            try:
                for name in names:
                    nfd = _ensure_dir(fd, name, 0o700)
                    os.close(fd)
                    fd = nfd
                yield fd
            finally:
                os.close(fd)

    @contextmanager
    def _trash(self, person_id: str) -> Iterator[int]:
        with self._system("trash", _trash_dir_name(person_id, self.space_dir_name)) as fd:
            yield fd

    # ---- authorization ------------------------------------------------------------------
    def grants_for(self, p: Principal) -> list[GrantRow]:
        if p.kind != "agent":
            return []
        return self.repo.grants(subject_kind="agent", subject_id=p.id)

    def access(self, p: Principal, root: Root, parts: tuple[str, ...]) -> Access:
        if is_person(p):
            return person_access(p, root)
        best = NONE
        for g in self.grants_for(p):
            if g.root == root.id and paths.is_within(parts, paths.split_path(g.path)):
                best = READ_WRITE if g.access == "rw" else (best if best.write else READ)
        return best

    def target(self, p: Principal, root: str | None, path: str | None, need: str) -> Target:
        r = parse_root(root)
        parts = paths.split_path(path)
        acc = self.access(p, r, parts)
        if not (acc.write if need == "write" else acc.read):
            what = "change" if need == "write" else "read"
            raise self._deny(p, f"files {need} {r.id}", f"{p.kind}/{p.role} may not {what} {r.id}{paths.join(parts)}",
                             "no_grant" if not is_person(p) else "role")
        return Target(r, parts, acc)

    # ---- quotas and space ---------------------------------------------------------------
    def limit(self, root: Root) -> int | None:
        if root.kind == "shared":
            return self.settings.shared_quota_bytes or None
        row = self.repo.quota(root.person_id)
        if row is not None:
            return row.limit_bytes
        return self.settings.default_quota_bytes or None

    def usage(self, root: Root) -> int:
        """Files in the space, plus its items in trash, plus open uploads into it (reserved)."""
        with self._space(root) as fd:
            used = paths.tree_size(fd)
        used += self.repo.trash_bytes(root.id)
        used += sum(u.length for u in self.repo.open_uploads(root.id))
        return used

    def free_bytes(self) -> int | None:
        try:
            return shutil.disk_usage(self.settings.root).free
        except OSError:
            return None

    def check_space(self, root: Root, add: int) -> None:
        if add <= 0:
            return
        limit = self.limit(root)
        if limit is not None:
            used = self.usage(root)
            if used + add > limit:
                raise FilesError(413, "payload_too_large",
                                 f"{root.id} would use {used + add} of its {limit} byte quota",
                                 reason="quota_exceeded")
        free = self.free_bytes()
        if free is not None and free - add < self.settings.min_free_bytes:
            raise FilesError(413, "payload_too_large", "not enough free space on the disk", reason="insufficient_space")

    # ---- browse -------------------------------------------------------------------------
    @staticmethod
    def _entry(name: str, parent: tuple[str, ...], st: os.stat_result) -> dict:
        kind = paths.kind_of(st)
        out = {
            "name": name,
            "path": paths.join(parent + (name,)),
            "type": kind,
            "size": st.st_size if kind == "file" else None,
            "mtime": iso(datetime.fromtimestamp(st.st_mtime, tz=UTC)),
        }
        if kind == "file":
            out["mime"] = guess_mime(name)
        return out

    def roots(self, p: Principal) -> list[dict]:
        out = []
        free = self.free_bytes()
        if is_person(p):
            candidates = ([Root("home", p.id)] if has_home(p) else []) + [Root("shared", None)]
            for r in candidates:
                acc = person_access(p, r)
                if not acc.read:
                    continue
                out.append({
                    "root": r.id, "kind": r.kind, "name": "My files" if r.kind == "home" else "Shared",
                    "path": "/", "access": acc.label, "writable": acc.write,
                    "used_bytes": self.usage(r), "quota_bytes": self.limit(r), "free_bytes": free,
                })
            return out
        for g in self.grants_for(p):
            out.append({
                "root": g.root, "kind": "grant", "name": g.slot or g.path.rsplit("/", 1)[-1] or g.root,
                "path": g.path, "access": g.access, "writable": g.access == "rw", "grant_id": g.id,
                "used_bytes": None, "quota_bytes": None, "free_bytes": free,
            })
        return out

    def list(self, p: Principal, root: str | None, path: str | None) -> list[dict]:
        t = self.target(p, root, path, "read")
        entries = []
        with self._space(t.root) as space, paths.dir_at(space, t.parts) as d:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        st = e.stat(follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    entries.append(self._entry(e.name, t.parts, st))
        entries.sort(key=lambda e: (e["type"] != "dir", e["name"].casefold(), e["name"]))
        self._audit_read(p, "list", t)
        return entries

    def stat(self, p: Principal, root: str | None, path: str | None) -> dict:
        t = self.target(p, root, path, "read")
        with self._space(t.root) as space:
            if not t.parts:
                st = os.fstat(space)
                out = self._entry("", (), st) | {"path": "/", "name": t.root.id}
            else:
                with paths.dir_at(space, t.parts[:-1]) as d:
                    out = self._entry(t.parts[-1], t.parts[:-1], paths.lstat_at(d, t.parts[-1]))
        out.update({"root": t.root.id, "access": t.access.label, "versions_available": False})
        self._audit_read(p, "stat", t)
        return out

    @contextmanager
    def open_file(self, p: Principal, root: str | None, path: str | None, op: str = "download") -> Iterator[tuple[int, os.stat_result, str]]:
        """(fd, stat, name) of a regular file; the fd stays open for the caller's block."""
        t = self.target(p, root, path, "read")
        if not t.parts:
            raise conflict("a space is a folder, not a file", "not_a_file")
        with self._space(t.root) as space, paths.dir_at(space, t.parts[:-1]) as d:
            fd, st = paths.open_file_at(d, t.parts[-1])
        self._audit_read(p, op, t, st.st_size)
        try:
            yield fd, st, t.parts[-1]
        finally:
            os.close(fd)

    def preview(self, p: Principal, root: str | None, path: str | None) -> dict:
        limit = self.settings.preview_text_bytes
        with self.open_file(p, root, path, "preview") as (fd, st, name):
            head = os.pread(fd, max(limit, 64 * 1024), 0)
        out = describe(name, head, st.st_size, limit)
        out.update({"root": parse_root(root).id, "path": paths.join(paths.split_path(path)), "name": name})
        return out

    # ---- data-plane writes --------------------------------------------------------------
    def mkdir(self, p: Principal, root: str | None, path: str | None) -> dict:
        t = self.target(p, root, path, "write")
        if not t.parts:
            raise conflict("the space already exists", "exists")
        with self._lock, self._space(t.root) as space, paths.dir_at(space, t.parts[:-1]) as d:
            try:
                os.mkdir(t.parts[-1], 0o750, dir_fd=d)
            except FileExistsError:
                raise conflict("something with that name already exists", "exists") from None
            except OSError as exc:
                raise paths.os_error(exc) from None
            entry = self._entry(t.parts[-1], t.parts[:-1], paths.lstat_at(d, t.parts[-1]))
        self.event("folder.created", p, {"root": t.root.id, "path": t.path})
        return entry

    def move(self, p: Principal, root: str | None, path: str | None, to_root: str | None, to_path: str | None,
             *, op: str = "move") -> dict:
        src = self.target(p, root, path, "write")
        dst = self.target(p, to_root or root, to_path, "write")
        if not src.parts or not dst.parts:
            raise conflict("a space itself cannot be moved or replaced", "space_root")
        if src.root.id == dst.root.id and paths.is_within(dst.parts, src.parts):
            raise conflict("a folder cannot be moved into itself", "into_itself")
        with self._lock, self._space(src.root) as s_space, self._space(dst.root) as d_space:
            with paths.dir_at(s_space, src.parts[:-1]) as sd, paths.dir_at(d_space, dst.parts[:-1]) as dd:
                st = paths.lstat_at(sd, src.parts[-1])
                if paths.exists_at(dd, dst.parts[-1]):
                    raise conflict("something with that name already exists at the destination", "exists")
                if src.root.id != dst.root.id:
                    self.check_space(dst.root, paths.tree_size(sd, src.parts[-1]))
                try:
                    os.rename(src.parts[-1], dst.parts[-1], src_dir_fd=sd, dst_dir_fd=dd)
                except OSError as exc:
                    raise paths.os_error(exc) from None
                entry = self._entry(dst.parts[-1], dst.parts[:-1], paths.lstat_at(dd, dst.parts[-1]))
        kind = paths.kind_of(st)
        self.event("moved" if op == "move" else "renamed", p, {
            "root": src.root.id, "path": src.path, "to_root": dst.root.id, "to_path": dst.path, "type": kind,
        })
        return entry | {"root": dst.root.id}

    def rename(self, p: Principal, root: str | None, path: str | None, name: str) -> dict:
        parts = paths.split_path(path)
        if not parts:
            raise conflict("a space itself cannot be renamed", "space_root")
        paths.validate_name(name)
        return self.move(p, root, path, root, paths.join(parts[:-1] + (name,)), op="rename")

    # ---- trash --------------------------------------------------------------------------
    @staticmethod
    def trash_owner(root: Root) -> str:
        return root.person_id if root.kind == "home" else SHARED_TRASH

    def may_see_trash(self, p: Principal, owner: str) -> bool:
        if owner == SHARED_TRASH:
            return person_access(p, Root("shared", None)).write
        return is_person(p) and owner == p.id and has_home(p)

    def _trash_json(self, row: TrashRow) -> dict:
        trashed = aware(row.trashed_at)
        return {
            "id": row.id, "trash": "shared" if row.person_id == SHARED_TRASH else "home",
            "root": row.root, "path": row.path, "name": row.path.rsplit("/", 1)[-1],
            "type": row.kind, "size": row.size_bytes, "trashed_at": iso(trashed), "trashed_by": row.trashed_by,
            "purge_at": iso(trashed + timedelta(days=self.settings.trash_retention_days)),
        }

    def trash(self, p: Principal, root: str | None, path: str | None) -> dict:
        t = self.target(p, root, path, "write")
        if not t.parts:
            raise conflict("a space itself cannot be moved to the trash", "space_root")
        owner = self.trash_owner(t.root)
        trash_id = new_id("trs")
        with self._lock, self._space(t.root) as space, paths.dir_at(space, t.parts[:-1]) as d, self._trash(owner) as tr:
            st = paths.lstat_at(d, t.parts[-1])
            kind = paths.kind_of(st)
            size = paths.tree_size(d, t.parts[-1])
            try:
                os.rename(t.parts[-1], trash_id, src_dir_fd=d, dst_dir_fd=tr)
            except OSError as exc:
                raise paths.os_error(exc) from None
            row = TrashRow(id=trash_id, person_id=owner, root=t.root.id, path=t.path,
                           kind=kind if kind in ("file", "dir") else "file",
                           size_bytes=size, trashed_at=self.clock(), trashed_by=p.id)
            try:
                self.repo.add_trash(row)
            except Exception:  # keep disk and ledger in step: put it back
                os.rename(trash_id, t.parts[-1], src_dir_fd=tr, dst_dir_fd=d)
                raise
        self.event("trashed", p, {"root": t.root.id, "path": t.path, "trash_id": trash_id, "size": size})
        return self._trash_json(row)

    def list_trash(self, p: Principal, which: str = "home") -> list[dict]:
        self.purge_expired()
        owner = SHARED_TRASH if which == "shared" else p.id
        if not self.may_see_trash(p, owner):
            raise self._deny(p, f"files trash list {which}", f"{p.kind}/{p.role} has no {which} trash")
        return [self._trash_json(r) for r in self.repo.trash_items(owner)]

    def restore_trash(self, p: Principal, trash_id: str, to_root: str | None = None, to_path: str | None = None) -> dict:
        row = self.repo.trash_item(trash_id)
        if row is None or row.purged_at is not None or not self.may_see_trash(p, row.person_id):
            raise not_found("no such item in your trash")
        dst = self.target(p, to_root or row.root, to_path or row.path, "write")
        if not dst.parts:
            raise conflict("cannot restore over a space", "space_root")
        with self._lock, self._trash(row.person_id) as tr, self._space(dst.root) as space:
            with paths.dir_at(space, dst.parts[:-1]) as d:
                if paths.exists_at(d, dst.parts[-1]):
                    raise conflict("something with that name is already there; restore it under another name", "exists")
                if dst.root.id != row.root:
                    self.check_space(dst.root, row.size_bytes)
                try:
                    os.rename(row.id, dst.parts[-1], src_dir_fd=tr, dst_dir_fd=d)
                except OSError as exc:
                    raise paths.os_error(exc) from None
                if not self.repo.mark_trash(row.id, self.clock(), purged=False):
                    os.rename(dst.parts[-1], row.id, src_dir_fd=d, dst_dir_fd=tr)
                    raise conflict("the item was restored or purged concurrently")
                entry = self._entry(dst.parts[-1], dst.parts[:-1], paths.lstat_at(d, dst.parts[-1]))
        self.event("restored", p, {"trash_id": row.id, "root": dst.root.id, "path": dst.path})
        return entry | {"root": dst.root.id}

    def _purge(self, row: TrashRow, reason: str, p: Principal | None, request_id: str | None = None) -> int:
        with self._lock, self._trash(row.person_id) as tr:
            if not self.repo.mark_trash(row.id, self.clock(), purged=True):
                return 0
            try:
                st = os.stat(row.id, dir_fd=tr, follow_symlinks=False)
                if stat_mod.S_ISDIR(st.st_mode):
                    fd = os.open(row.id, paths.O_DIR, dir_fd=tr)
                    try:
                        for top, dirs, files, rootfd in os.fwalk(".", topdown=False, dir_fd=fd, follow_symlinks=False):
                            for f in files:
                                os.unlink(f, dir_fd=rootfd)
                            for dname in dirs:
                                try:
                                    os.rmdir(dname, dir_fd=rootfd)
                                except NotADirectoryError:  # a symlink to a folder is listed as a dir
                                    os.unlink(dname, dir_fd=rootfd)
                    finally:
                        os.close(fd)
                    os.rmdir(row.id, dir_fd=tr)
                else:
                    os.unlink(row.id, dir_fd=tr)
            except FileNotFoundError:
                pass
        self.event("purged", p, {"trash_id": row.id, "root": row.root, "path": row.path,
                                 "size": row.size_bytes, "reason": reason}, request_id=request_id)
        return row.size_bytes

    def purge_expired(self) -> int:
        cutoff = self.clock() - timedelta(days=self.settings.trash_retention_days)
        n = 0
        for row in self.repo.trash_items():
            if aware(row.trashed_at) <= cutoff:
                self._purge(row, "retention", None)
                n += 1
        return n

    # ---- quotas (direct owner writes) ---------------------------------------------------
    def list_quotas(self, p: Principal) -> list[dict]:
        if not p.is_owner:
            raise self._deny(p, "files quotas list", "only an owner sees every quota")
        people = sorted(set(self.repo.spaces()) | set(self.repo.quotas()))
        out = []
        for pid in people:
            r = Root("home", pid)
            out.append({"person_id": pid, "root": r.id, "limit_bytes": self.limit(r), "used_bytes": self.usage(r)})
        shared = Root("shared", None)
        out.append({"person_id": None, "root": "shared", "limit_bytes": self.limit(shared), "used_bytes": self.usage(shared)})
        return out

    def set_quota(self, p: Principal, person_id: str, limit_bytes: int | None) -> dict:
        if not p.is_owner:
            raise self._deny(p, "files quota set", "only an owner sets quotas")
        if limit_bytes is not None and limit_bytes < 0:
            raise FilesError(422, "conflict", "limit_bytes must be at least 0 or null", reason="invalid_quota")
        root = parse_root(f"home:{person_id}")
        self.repo.set_quota(person_id, limit_bytes, p.id, self.clock())
        self.event("quota.set", p, {"root": root.id, "person_id": person_id, "limit_bytes": limit_bytes})
        return {"person_id": person_id, "root": root.id, "limit_bytes": limit_bytes, "used_bytes": self.usage(root)}

    # ---- requests: changes that need an owner approval ----------------------------------
    def _request_json(self, row: RequestRow) -> dict:
        return {
            "id": row.id, "type": row.type, "params": row.params, "plan": row.plan, "risk": row.risk,
            "state": row.state, "reason": row.reason, "requested_by": row.requested_by,
            "approved_by": row.approved_by, "approved_via": row.approved_via, "approval": row.approval,
            "deny_reason": row.deny_reason, "result": row.result, "expires_at": iso(aware(row.expires_at)),
            "created_at": iso(aware(row.created_at)), "updated_at": iso(aware(row.updated_at)),
        }

    def _expire_if_due(self, row: RequestRow) -> RequestRow:
        if row.state == "awaiting_approval" and self.clock() >= aware(row.expires_at):
            moved = self.repo.transition_request(row.id, {"awaiting_approval"}, "expired", self.clock())
            if moved is not None:
                self.event("request.expired", None, {"request_id": row.id, "type": row.type})
                return moved
            return self.repo.request(row.id) or row
        return row

    def _grant_plan(self, p: Principal, params: dict) -> tuple[dict, str]:
        subject = params["subject"]
        root = parse_root(params["root"])
        parts = paths.split_path(params["path"])
        if subject["kind"] not in GRANT_SUBJECTS:
            raise FilesError(422, "conflict", "subject.kind must be app or agent", reason="invalid_subject")
        if subject["kind"] == "app" and self.gw.catalog.get(subject["id"]) is None:
            raise not_found(f"app {subject['id']!r} is not in the catalog")
        if p.kind == "agent":
            if subject != {"kind": "agent", "id": p.id}:
                raise self._deny(p, "files.grant.create", "an agent may request folder access only for itself", "not_self")
        elif p.is_owner:
            if root.kind == "home" and root.person_id != p.id:
                raise self._deny(p, "files.grant.create", "an owner grants only Shared or their own Home", "not_home_owner")
        else:
            raise self._deny(p, "files.grant.create", f"{p.kind}/{p.role} may not request folder grants")
        self._require_folder(root, parts)
        access = "read-write" if params["access"] == "rw" else "read-only"
        who = f"{subject['kind']} {subject['id']}"
        plan = {"summary": f"{who} gets {access} access to {root.id}:{paths.join(parts)}",
                "subject": subject, "root": root.id, "path": paths.join(parts), "access": params["access"],
                "slot": params.get("slot")}
        return plan, "sensitive"

    def _require_folder(self, root: Root, parts: tuple[str, ...]) -> None:
        with self._space(root) as space, paths.dir_at(space, parts):
            pass

    def _trash_plan(self, p: Principal, params: dict) -> tuple[dict, str]:
        owner = SHARED_TRASH if params["trash"] == "shared" else p.id
        if not self.may_see_trash(p, owner):
            raise self._deny(p, "files.trash.empty", f"{p.kind}/{p.role} has no {params['trash']} trash")
        items = self.repo.trash_items(owner)
        plan = {"summary": f"permanently delete {len(items)} item(s) from the {params['trash']} trash",
                "trash": params["trash"], "items": len(items), "bytes": sum(i.size_bytes for i in items)}
        return plan, "destructive"

    def create_request(self, p: Principal, type_: str, params: dict, *, reason: str | None, expires_at: datetime | None,
                       approve: bool, idempotency_key: str | None, http_request: Any = None) -> tuple[dict, bool]:
        """Returns (request, created). created=False is an idempotent replay."""
        if approve and not p.is_owner:
            raise self._deny(p, f"{type_} with approve", "only an owner may request and approve in one step")
        body_hash = hashlib.sha256(canonical({"type": type_, "params": params, "reason": reason,
                                              "expires_at": iso(expires_at) if expires_at else None,
                                              "approve": approve}).encode()).hexdigest()
        existing = self.repo.request_by_key(p.id, idempotency_key)
        if existing is not None:
            if existing.body_sha256 != body_hash:
                raise conflict("Idempotency-Key was already used for a different request", "idempotency_mismatch")
            return self._request_json(self._expire_if_due(existing)), False
        now = self.clock()
        expires = utc(expires_at) if expires_at else now + REQUEST_TTL
        if expires <= now:
            raise FilesError(409, "expired", "expires_at is already in the past")
        if expires > now + REQUEST_TTL_MAX:
            raise FilesError(422, "conflict", "expires_at may be at most 7 days ahead", reason="expiry_too_far")
        plan, risk = (self._grant_plan if type_ == "files.grant.create" else self._trash_plan)(p, params)
        if not p.is_owner and self.repo.pending_count(p.id) >= MAX_PENDING:
            raise FilesError(429, "rate_limited", f"at most {MAX_PENDING} requests may wait for approval",
                             reason="too_many_pending", headers={"Retry-After": "60"})
        row = RequestRow(
            id=new_id("frq"), type=type_, params=params, plan=plan, risk=risk, state="awaiting_approval",
            reason=reason, requested_by={"id": p.id, "kind": p.kind}, requested_by_id=p.id,
            idempotency_key=idempotency_key, body_sha256=body_hash, approved_by=None, approved_via=None,
            approval=None, deny_reason=None, result=None, expires_at=expires, created_at=now, updated_at=now,
        )
        stored, created = self.repo.add_request(row)
        if not created:
            if stored.body_sha256 != body_hash:
                raise conflict("Idempotency-Key was already used for a different request", "idempotency_mismatch")
            return self._request_json(stored), False
        self.event("request.created", p, {"request_id": stored.id, "type": type_, "risk": risk,
                                          "plan": plan, **({"reason": reason} if reason else {})})
        if approve:
            return self.approve(p, stored.id, http_request=http_request, owner_initiated=True), True
        return self._request_json(stored), True

    def get_request(self, p: Principal, request_id: str) -> dict:
        row = self.repo.request(request_id)
        if row is None or not (p.is_owner or row.requested_by_id == p.id):
            raise not_found("no such request")
        return self._request_json(self._expire_if_due(row))

    def list_requests(self, p: Principal, state: str | None = None) -> list[dict]:
        rows = self.repo.requests(None if p.is_owner else p.id)
        out = [self._request_json(self._expire_if_due(r)) for r in rows]
        if state:
            wanted = set(state.split(","))
            out = [r for r in out if r["state"] in wanted]
        return out

    def _decidable(self, p: Principal, request_id: str, attempted: str) -> RequestRow:
        if not p.is_owner:
            raise self._deny(p, attempted, "only an owner decides files requests")
        row = self.repo.request(request_id)
        if row is None:
            raise not_found("no such request")
        row = self._expire_if_due(row)
        if row.state == "expired":
            raise FilesError(409, "expired", "the request expired before a decision")
        if row.state != "awaiting_approval":
            raise conflict(f"request is {row.state}, not awaiting_approval")
        return row

    def approve(self, p: Principal, request_id: str, *, http_request: Any = None, owner_initiated: bool = False) -> dict:
        row = self._decidable(p, request_id, "approve files request")
        # Approval guards other features add (identity: passkey step-up, F-2). Absent until then.
        for guard in getattr(self.gw, "approval_guards", ()) or ():
            guard(p, row.type, row.params, http_request)
        params = row.params
        if row.type == "files.grant.create":
            root = parse_root(params["root"])
            if root.kind == "home" and root.person_id != p.id:
                raise self._deny(p, "approve files.grant.create",
                                 "only the person whose Home it is may approve access to it", "not_home_owner")
            if params["subject"]["kind"] == "app" and self.gw.catalog.get(params["subject"]["id"]) is None:
                raise FilesError(409, "stale_precondition", "the app is no longer in the catalog")
            try:
                self._require_folder(root, paths.split_path(params["path"]))
            except FilesError as exc:
                raise FilesError(409, "stale_precondition", f"the folder is no longer there ({exc.message})") from None
        now = self.clock()
        approval = "token"
        moved = self.repo.transition_request(row.id, {"awaiting_approval"}, "accepted", now,
                                             approved_by=p.id, approved_via="api", approval=approval)
        if moved is None:
            raise conflict("the request was decided concurrently")
        self.event("request.approved", p, {"request_id": row.id, "type": row.type, "approved_by": p.id,
                                           "requested_by": row.requested_by_id, "approval": approval,
                                           "owner_initiated": owner_initiated})
        try:
            result = self._apply(p, moved)
            final = self.repo.transition_request(row.id, {"accepted"}, "succeeded", self.clock(), result=result)
        except Exception as exc:
            log.exception("applying files request %s failed", row.id)
            result = {"error": exc.__class__.__name__, "message": str(exc)[:300]}
            final = self.repo.transition_request(row.id, {"accepted"}, "failed", self.clock(), result=result)
            self.event("request.failed", None, {"request_id": row.id, "type": row.type, **result}, severity="error")
        return self._request_json(final or self.repo.request(row.id))

    def _apply(self, p: Principal, row: RequestRow) -> dict:
        params = row.params
        if row.type == "files.grant.create":
            grant = GrantRow(
                id=new_id("grt"), request_id=row.id, subject_kind=params["subject"]["kind"],
                subject_id=params["subject"]["id"], slot=params.get("slot"), root=parse_root(params["root"]).id,
                path=paths.join(paths.split_path(params["path"])), access=params["access"],
                created_at=self.clock(), approved_by=p.id,
            )
            self.repo.add_grant(grant)
            self.event("grant.created", p, {"grant_id": grant.id, "request_id": row.id, "root": grant.root,
                                            "path": grant.path, "access": grant.access,
                                            "subject": params["subject"]}, request_id=row.id)
            return {"grant_id": grant.id}
        owner = SHARED_TRASH if params["trash"] == "shared" else row.requested_by_id
        purged = freed = 0
        for item in self.repo.trash_items(owner):
            if aware(item.trashed_at) <= aware(row.created_at):  # only what the plan counted
                freed += self._purge(item, "emptied", p, request_id=row.id)
                purged += 1
        self.event("trash.emptied", p, {"request_id": row.id, "trash": params["trash"], "items": purged, "bytes": freed},
                   request_id=row.id)
        return {"items": purged, "bytes": freed}

    def deny(self, p: Principal, request_id: str, reason: str | None) -> dict:
        row = self._decidable(p, request_id, "deny files request")
        moved = self.repo.transition_request(row.id, {"awaiting_approval"}, "cancelled", self.clock(),
                                             approved_by=None, deny_reason=reason)
        if moved is None:
            raise conflict("the request was decided concurrently")
        self.event("request.denied", p, {"request_id": row.id, "type": row.type, **({"reason": reason} if reason else {})})
        return self._request_json(moved)

    def cancel(self, p: Principal, request_id: str) -> dict:
        row = self.repo.request(request_id)
        if row is None or row.requested_by_id != p.id:
            raise not_found("no such request of yours")
        row = self._expire_if_due(row)
        moved = self.repo.transition_request(row.id, {"awaiting_approval"}, "cancelled", self.clock())
        if moved is None:
            raise conflict(f"request is {row.state}, not awaiting_approval")
        self.event("request.cancelled", p, {"request_id": row.id, "type": row.type})
        return self._request_json(moved)

    # ---- grants -------------------------------------------------------------------------
    @staticmethod
    def _grant_json(g: GrantRow) -> dict:
        return {
            "id": g.id, "subject": {"kind": g.subject_kind, "id": g.subject_id}, "slot": g.slot, "root": g.root,
            "path": g.path, "access": g.access, "request_id": g.request_id, "approved_by": g.approved_by,
            "created_at": iso(aware(g.created_at)), "revoked_at": iso(aware(g.revoked_at)), "revoked_by": g.revoked_by,
        }

    def _may_see_grant(self, p: Principal, g: GrantRow) -> bool:
        if p.is_owner:
            return True
        if p.kind == "agent":
            return g.subject_kind == "agent" and g.subject_id == p.id
        return is_person(p) and g.root == f"home:{p.id}"

    def list_grants(self, p: Principal, include_revoked: bool = False) -> list[dict]:
        return [self._grant_json(g) for g in self.repo.grants(active=not include_revoked) if self._may_see_grant(p, g)]

    def revoke_grant(self, p: Principal, grant_id: str) -> dict:
        """Removing power is a direct write (§12.1): the owner, the Home's person, or the agent itself."""
        g = self.repo.grant(grant_id)
        if g is None or not self._may_see_grant(p, g):
            raise not_found("no such grant")
        if g.revoked_at is None and not self.repo.revoke_grant(g.id, p.id, self.clock()):
            raise conflict("the grant was revoked concurrently")
        if g.revoked_at is None:
            self.event("grant.revoked", p, {"grant_id": g.id, "root": g.root, "path": g.path,
                                            "subject": {"kind": g.subject_kind, "id": g.subject_id}})
        return self._grant_json(self.repo.grant(g.id))

    def app_mounts(self, app_id: str) -> list[dict]:
        """Approved folder grants of an app, as host paths for the executor hook (CORE-SANDBOX owner).

        Each folder is opened through the confined walk first, so a symlink planted in its path
        refuses the mount instead of exposing another directory.
        """
        out = []
        for g in self.repo.grants(subject_kind="app", subject_id=app_id):
            root = parse_root(g.root)
            parts = paths.split_path(g.path)
            self._require_folder(root, parts)
            top = self.settings.root / ("home" if root.kind == "home" else "shared")
            if root.kind == "home":
                top = top / self.space_dir_name(root.person_id)
            out.append({"grant_id": g.id, "slot": g.slot, "host_path": str(top.joinpath(*parts)),
                        "read_only": g.access != "rw"})
        return out
