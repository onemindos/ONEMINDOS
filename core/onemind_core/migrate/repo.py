# SPDX-License-Identifier: Apache-2.0
"""An append-only restic repository served by the gateway (restic REST protocol v2).

Why here and not a separate rest-server: the old cluster then needs to reach only the
gateway's existing listener (and its TLS), and every user is tied to one plan and one approved
action, so it expires and is revoked with that action.

On disk the layout is restic's own local layout (config, keys/, locks/, snapshots/, index/,
data/<2 hex>/), so `restic -r <dir>` reads it without OneMind.

Rules, as rest-server's `--append-only --private-repos` mode:
- a user reaches only its plan's repository;
- "w" users (the helper pod) read and add files but never overwrite one, and delete only lock
  files; "r" users (the restore Job) only read (it runs restic with --no-lock);
- every uploaded data, index, snapshot and key file must hash to its name (sha256), so a bad
  or truncated upload is refused rather than stored.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

TYPES = ("data", "keys", "locks", "snapshots", "index")
NAME_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_BLOB_BYTES = 512 * 1024 * 1024
V2 = "application/vnd.x.restic.rest.v2"


class RepoError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class Repo:
    def __init__(self, root: Path):
        self.root = root

    def _path(self, typ: str, name: str | None) -> Path:
        if typ == "config" and name is None:
            return self.root / "config"
        if typ not in TYPES or name is None or not NAME_RE.match(name):
            raise RepoError(400, "bad object path")
        if typ == "data":
            return self.root / "data" / name[:2] / name
        return self.root / typ / name

    @property
    def exists(self) -> bool:
        """Created by `POST /?create=true`. restic init then saves the key before the config."""
        return (self.root / "keys").is_dir()

    def create(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        for typ in TYPES:
            (self.root / typ).mkdir(exist_ok=True, mode=0o700)
        for i in range(256):
            (self.root / "data" / f"{i:02x}").mkdir(exist_ok=True, mode=0o700)

    def stat(self, typ: str, name: str | None) -> int | None:
        p = self._path(typ, name)
        return p.stat().st_size if p.is_file() else None

    def read(self, typ: str, name: str | None, start: int = 0, end: int | None = None) -> bytes:
        p = self._path(typ, name)
        if not p.is_file():
            raise RepoError(404, "not found")
        with p.open("rb") as f:
            f.seek(start)
            return f.read() if end is None else f.read(end - start + 1)

    def listing(self, typ: str) -> list[dict]:
        if typ not in TYPES:
            raise RepoError(400, "bad type")
        base = self.root / typ
        if not base.is_dir():
            return []
        files = base.rglob("*") if typ == "data" else base.iterdir()
        return [{"name": p.name, "size": p.stat().st_size} for p in files if p.is_file() and NAME_RE.match(p.name)]

    async def write(self, typ: str, name: str | None, body: AsyncIterator[bytes]) -> None:
        if not self.exists and typ != "config":
            raise RepoError(404, "repository does not exist")
        p = self._path(typ, name)
        if p.exists():
            raise RepoError(403, "append-only: objects are never overwritten")
        p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        h = hashlib.sha256()
        size = 0
        fd, tmp = tempfile.mkstemp(prefix=".upload-", dir=p.parent)
        try:
            with os.fdopen(fd, "wb") as f:
                async for chunk in body:
                    size += len(chunk)
                    if size > MAX_BLOB_BYTES:
                        raise RepoError(413, "object too large")
                    h.update(chunk)
                    f.write(chunk)
                f.flush()
                os.fsync(f.fileno())
            if name is not None and h.hexdigest() != name:
                raise RepoError(400, "content does not match its name")
            try:
                os.link(tmp, p)  # fails if another upload won the race: never overwrite
            except FileExistsError:
                raise RepoError(403, "append-only: objects are never overwritten") from None
        finally:
            os.unlink(tmp)

    def delete(self, typ: str, name: str) -> None:
        if typ != "locks":
            raise RepoError(403, "append-only: only lock files may be deleted")
        p = self._path(typ, name)
        if not p.is_file():
            raise RepoError(404, "not found")
        p.unlink()


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """One `bytes=a-b` / `bytes=a-` / `bytes=-n` range, clipped to size; None for the whole file."""
    if not header:
        return None
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
    if not m or (m.group(1) == "" and m.group(2) == ""):
        raise RepoError(416, "unsupported range")
    if m.group(1) == "":
        n = int(m.group(2))
        start, end = max(0, size - n), size - 1
    else:
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else size - 1
    end = min(end, size - 1)
    if start > end or start >= size:
        raise RepoError(416, "range not satisfiable")
    return start, end
