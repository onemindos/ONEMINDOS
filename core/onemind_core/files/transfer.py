# SPDX-License-Identifier: Apache-2.0
"""Hub sync contract, part 2 (#699): chunked uploads, conditional commits and versions that share chunks.

A sync client cuts a file into content-defined chunks (`cut_points`: a gear-hash chunker with the
FastCDC shape, 32 KiB minimum, about 64 KiB on average, 256 KiB maximum, so a chunk fits in one
request body under the gateway's body cap), names each chunk by its SHA-256 and sends:

1. POST /v1/sync/chunks/missing   which of these chunks does the root not hold yet?
2. PUT  /v1/sync/chunks/{hash}    one chunk; refused when its bytes do not hash to {hash}
3. POST /v1/sync/commit           the manifest (the chunk list) plus `base_revision`, the file's
                                  revision the client last saw (null: the file must not exist yet)

A large file's manifest does not fit in one request body, so a client may send it as chunks too:
the binary manifest is one 36-byte record per chunk (the 32-byte SHA-256, then the size as a 4-byte
big-endian integer), cut into pieces, each PUT like any chunk, and the commit names those pieces
in order (`manifest_chunks`) instead of listing `chunks`.

Because the hub keeps every chunk it received, an upload killed part way resumes by asking step 1
again: only the chunks that never arrived are sent. A commit whose base is not the file's current
revision is refused with 412 and the current revision, so the second of two editors never
overwrites the first one's change; the client keeps its copy as a conflicted copy instead.

Chunks are kept per root (.system/chunks/<root key>/), never shared between roots, so asking
"missing?" reveals nothing about another person's files. Inside a root the chunk store answers for
the whole root, so only a caller who may write the whole root uses it: a person by role, an agent by
a read-write grant on "/" (the same rule as the change feed). An agent granted one folder writes
through /v1/files instead. A chunk a caller sent or asked about is leased for CHUNK_TTL: pruning a
version never removes a chunk another device is still uploading or about to commit, and a chunk no
version names is swept once its lease runs out, so an abandoned upload does not fill the disk. Each commit is recorded as a version
(files_sync_versions): the file's last VERSIONS_KEEP manifests are kept, and as they share chunks an
edit of a large file stores only the chunks that changed. A file changed outside sync (SMB, WebDAV,
the Files app) is cut into chunks by the hub before a commit replaces it, so it becomes a version
too. Everything here names a root id and a path inside the space, never a host path.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import time
from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Index, String, delete, select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, mapped_column

from ..auth import Principal
from ..ledger import Base, iso
from . import paths
from .access import Root, is_person, parse_root, person_access
from .errors import FilesError, conflict
from .index import IndexRow
from .store import SCHEMA, aware, new_id

CHUNK_MIN = 32 * 1024
CHUNK_AVG = 64 * 1024
CHUNK_MAX = 256 * 1024
CHUNK_LIMIT = 256 * 1024            # the largest chunk the hub accepts: the gateway's default body cap
MANIFEST_MAX_CHUNKS = 200_000       # one file: about 12 GiB at the average size, 50 GiB at the largest
RECORD = 36                         # a binary manifest record: sha256 (32 bytes) + size (4 bytes, big-endian)
VERSIONS_KEEP = 10                  # manifests kept per file
CHUNK_TTL = 24 * 3600               # seconds a chunk nobody commits is kept after it was last sent or asked about
SWEEP_EVERY = 3600                  # seconds between sweeps of one root's unreferenced chunks
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# The gear table: 256 fixed 64-bit values, derived so every implementation can rebuild it.
_GEAR = [int.from_bytes(hashlib.sha256(b"onemind-sync-gear-%d" % i).digest()[:8], "big") for i in range(256)]
_M64 = (1 << 64) - 1
_MASK_SMALL = ((1 << 18) - 1) << 24  # 18 bits before the average size: a cut is unlikely
_MASK_LARGE = ((1 << 14) - 1) << 24  # 14 bits after it: a cut comes soon


def cut_point(data: bytes | bytearray | memoryview, start: int = 0) -> int:
    """Length of the chunk that starts at `start` (content-defined, so an insert moves few cuts)."""
    n = len(data) - start
    if n <= CHUNK_MIN:
        return n
    end, mid = min(n, CHUNK_MAX), min(n, CHUNK_AVG)
    h, i, gear = 0, CHUNK_MIN, _GEAR
    while i < mid:
        h = ((h << 1) + gear[data[start + i]]) & _M64
        if not h & _MASK_SMALL:
            return i + 1
        i += 1
    while i < end:
        h = ((h << 1) + gear[data[start + i]]) & _M64
        if not h & _MASK_LARGE:
            return i + 1
        i += 1
    return end


def manifest_of(data: bytes) -> list[dict]:
    """[{hash, size}] of `data` cut by `cut_point`: what a client sends to /v1/sync/commit."""
    out, at = [], 0
    while at < len(data):
        n = cut_point(data, at)
        out.append({"hash": hashlib.sha256(data[at:at + n]).hexdigest(), "size": n})
        at += n
    return out


class VersionRow(Base):
    __tablename__ = "files_sync_versions"
    __table_args__ = (Index("ix_files_sync_versions_file", "root", "file_id", "revision"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)        # ver_...
    root: Mapped[str] = mapped_column(String(220))
    file_id: Mapped[str] = mapped_column(String(40))                     # the index row (fil_...)
    path: Mapped[str] = mapped_column(String(4200))                      # where it was at the time
    revision: Mapped[int] = mapped_column(BigInteger)                    # the file's revision then
    size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    chunks: Mapped[list] = mapped_column(JSON)                           # [[hash, size], ...]
    origin: Mapped[str] = mapped_column(String(8))                       # sync | hub (cut by the hub)
    created_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


@SCHEMA.step(3, "sync transfer: files_sync_versions (#699)")
def _files_v3(conn: Connection) -> None:
    VersionRow.__table__.create(conn, checkfirst=True)


class StaleBase(FilesError):
    """412: the commit's base is not the file's current revision. Carries the current one."""

    def __init__(self, revision: int | None, digest: str | None):
        super().__init__(412, "stale_precondition", "the file changed since your base revision; fetch it and merge",
                         reason="stale_base", headers={"ETag": f'"{revision}"'} if revision is not None else None)
        self.revision, self.digest = revision, digest

    def body(self) -> dict:
        return {**super().body(), "details": [{"current_revision": self.revision, "current_hash": self.digest}]}


class ChunksMissing(FilesError):
    def __init__(self, missing: list[str]):
        super().__init__(409, "conflict", f"{len(missing)} chunk(s) of the manifest are not on the hub; send them",
                         reason="chunks_missing")
        self.missing = missing

    def body(self) -> dict:
        return {**super().body(), "details": [{"hash": h} for h in self.missing[:1000]]}


def _hash_error(message: str) -> FilesError:
    return FilesError(422, "conflict", message, reason="hash_mismatch")


class Transfer:
    """Chunk store, commits and versions on top of FilesService (its access checks, spaces and index)."""

    def __init__(self, files, keep: int = VERSIONS_KEEP, chunk_ttl: float = CHUNK_TTL, locks=None):
        self.files = files
        self.db = files.repo.db
        self.keep = keep
        self.chunk_ttl = chunk_ttl
        self._swept: dict[str, float] = {}   # root id -> monotonic time of its last sweep
        self.locks = locks  # locks.Locks: a commit names the advisory locks of others it went over

    # ---- who may write ------------------------------------------------------------------
    def writable_root(self, p: Principal, root: str | None) -> Root:
        """A root the caller may write as a whole: a person by role, an agent by a read-write grant on "/".
        A grant on one folder is not enough: the chunk store answers for the whole root."""
        r = parse_root(root)
        ok = person_access(p, r).write if is_person(p) else any(
            g.root == r.id and g.access == "rw" and not paths.split_path(g.path) for g in self.files.grants_for(p))
        if not ok:
            raise self.files._deny(p, f"sync write {r.id}", f"{p.kind}/{p.role} may not write to {r.id}",
                                   "role" if is_person(p) else "no_grant")
        return r

    # ---- the chunk store ----------------------------------------------------------------
    @staticmethod
    def _root_key(root: Root) -> str:
        return hashlib.sha256(root.id.encode()).hexdigest()[:32]

    def _chunks_dir(self, root: Root):
        return self.files._system("chunks", self._root_key(root))

    @staticmethod
    def _chunk_name(digest: str) -> str:
        return digest  # one flat folder per root; names are fixed-length hex

    def missing(self, p: Principal, root: str | None, hashes: list[str]) -> list[str]:
        r = self.writable_root(p, root)
        bad = [h for h in hashes if not HEX64.match(h)]
        if bad:
            raise FilesError(422, "conflict", "a chunk hash is 64 lowercase hex digits", reason="invalid_hash")
        out = []
        with self._chunks_dir(r) as d:
            for h in dict.fromkeys(hashes):
                if not self._touch(d, self._chunk_name(h)):   # present: leased, so a prune keeps it
                    out.append(h)
        return out

    @staticmethod
    def _touch(d: int, name: str) -> bool:
        """Renew a chunk's lease (its mtime). False: there is no such chunk."""
        try:
            fd = os.open(name, paths.O_FILE_READ, dir_fd=d)
        except OSError:
            return False
        try:
            os.utime(fd)
        finally:
            os.close(fd)
        return True

    def _leased(self, d: int, name: str, now: float) -> bool:
        try:
            st = os.stat(name, dir_fd=d, follow_symlinks=False)
        except FileNotFoundError:
            return False
        return now - st.st_mtime < self.chunk_ttl

    def put_chunk(self, p: Principal, root: str | None, digest: str, data: bytes) -> dict:
        r = self.writable_root(p, root)
        if not HEX64.match(digest):
            raise FilesError(422, "conflict", "a chunk hash is 64 lowercase hex digits", reason="invalid_hash")
        if not data or len(data) > CHUNK_LIMIT:
            raise FilesError(413, "payload_too_large", f"a chunk is 1 to {CHUNK_LIMIT} bytes", reason="chunk_too_large")
        if hashlib.sha256(data).hexdigest() != digest:
            raise _hash_error("the chunk's bytes do not hash to its name")
        free = self.files.free_bytes()
        if free is not None and free - len(data) < self.files.settings.min_free_bytes:
            raise FilesError(413, "payload_too_large", "not enough free space on the disk", reason="insufficient_space")
        with self._chunks_dir(r) as d:
            stored = self._write_chunk(d, digest, data)
        return {"hash": digest, "size": len(data), "stored": stored}

    def _write_chunk(self, d: int, digest: str, data: bytes) -> bool:
        name = self._chunk_name(digest)
        if self._touch(d, name):
            return False
        tmp = f".{name}.{secrets.token_hex(6)}.part"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=d)
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view):]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.rename(tmp, name, src_dir_fd=d, dst_dir_fd=d)
        return True

    # ---- commits ------------------------------------------------------------------------
    def _current(self, root: Root, parts: tuple[str, ...]) -> IndexRow | None:
        """The index row at `parts` after reconciling it with the disk (an SMB edit counts)."""
        self.files.reindex(root, parts, depth=0)
        return self.files.index.rows(root.id, [paths.join(parts)]).get(paths.join(parts))

    def _manifest_from_chunks(self, root: Root, pieces: list[str]) -> list[dict]:
        cap = MANIFEST_MAX_CHUNKS * RECORD
        blob = bytearray()
        with self._chunks_dir(root) as d:
            for h in pieces:
                data = self._read_chunk(d, h)
                if data is None:
                    raise ChunksMissing([h])
                blob += data
                if len(blob) > cap:  # stop at once: repeating one large piece must not cost memory or time
                    raise FilesError(422, "conflict", f"the binary manifest is over {MANIFEST_MAX_CHUNKS} records",
                                     reason="invalid_manifest")
        if len(blob) % RECORD:
            raise FilesError(422, "conflict", "the binary manifest is not whole 36-byte records", reason="invalid_manifest")
        return [{"hash": blob[i:i + 32].hex(), "size": int.from_bytes(blob[i + 32:i + RECORD], "big")}
                for i in range(0, len(blob), RECORD)]

    def commit(self, p: Principal, root: str | None, path: str | None, size: int, sha256: str,
               chunks: list[dict] | None, base: int | None, manifest_chunks: list[str] | None = None) -> dict:
        t = self.files.target(p, root, path, "entry")   # a read-only grant or role is refused here
        if not t.parts:
            raise FilesError(422, "conflict", "commit names a file, not the root", reason="invalid_path")
        if (chunks is None) == (manifest_chunks is None):
            raise FilesError(422, "conflict", "send either chunks or manifest_chunks", reason="chunks_or_manifest")
        if manifest_chunks is not None:
            if any(not HEX64.match(h) for h in manifest_chunks):
                raise FilesError(422, "conflict", "hashes are 64 lowercase hex digits", reason="invalid_hash")
            self.writable_root(p, root)
            chunks = self._manifest_from_chunks(t.root, manifest_chunks)
        if not HEX64.match(sha256) or any(not HEX64.match(c["hash"]) for c in chunks):
            raise FilesError(422, "conflict", "hashes are 64 lowercase hex digits", reason="invalid_hash")
        if len(chunks) > MANIFEST_MAX_CHUNKS or any(not 0 < c["size"] <= CHUNK_LIMIT for c in chunks):
            raise FilesError(422, "conflict", "the manifest's chunks are out of range", reason="invalid_manifest")
        if sum(c["size"] for c in chunks) != size:
            raise FilesError(422, "conflict", "the chunk sizes do not add up to the file size", reason="invalid_manifest")
        missing = self.missing(p, root, [c["hash"] for c in chunks])
        if missing:
            raise ChunksMissing(missing)
        files = self.files
        with files._lock:
            cur = self._current(t.root, t.parts)
            if cur is not None and cur.type != "file":
                raise conflict("a folder or link is at that path", "not_a_file")
            have = cur.revision if cur is not None else None
            if base != have:
                raise StaleBase(have, cur.hash if cur is not None else None)
            files.check_space(t.root, size - ((cur.size or 0) if cur is not None else 0))  # 413 quota_exceeded
            if cur is not None:
                self._keep_previous(t.root, t.parts, cur)
            self._place(t.root, t.parts, chunks, size, sha256)
            files.reindex(t.root, t.parts, depth=0, known_hash="sha256:" + sha256)
            row = files.index.rows(t.root.id, [t.path]).get(t.path)
        if row is None:  # the file vanished between the rename and the index (another writer)
            raise conflict("the file changed while it was committed; ask for changes and retry", "raced")
        version = self._add_version(t.root, row, chunks, size, sha256, "sync", p.id)
        self._prune(t.root, row.file_id)
        self.sweep(t.root)
        files.event("sync.committed", p, {"root": t.root.id, "path": t.path, "id": row.file_id,
                                          "revision": row.revision, "size": size, "sha256": sha256,
                                          "base_revision": base, "chunks": len(chunks)})
        return {"root": t.root.id, "path": t.path, "id": row.file_id, "revision": row.revision,
                "size": size, "hash": "sha256:" + sha256, "version_id": version.id,
                "locks": self.locks.held_by_others(p, t.root.id, t.path) if self.locks is not None else []}

    def _place(self, root: Root, parts: tuple[str, ...], chunks: list[dict], size: int, sha256: str) -> None:
        """Join the chunks into a new file beside the uploads, check it, then rename it into place."""
        tmp = f"sync-{secrets.token_hex(12)}.part"
        h = hashlib.sha256()
        with self.files._system("uploads") as up, self._chunks_dir(root) as cd:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640, dir_fd=up)
            try:
                for c in chunks:
                    data = self._read_chunk(cd, c["hash"])
                    if data is None or len(data) != c["size"]:
                        raise ChunksMissing([c["hash"]])
                    h.update(data)
                    view = memoryview(data)
                    while view:
                        view = view[os.write(fd, view):]
                os.fsync(fd)
            except BaseException:
                os.close(fd)
                os.unlink(tmp, dir_fd=up)
                raise
            os.close(fd)
            if h.hexdigest() != sha256:
                os.unlink(tmp, dir_fd=up)
                raise _hash_error("the joined chunks do not hash to the file's sha256")
            try:
                with self.files._space(root) as space, paths.dir_at(space, parts[:-1]) as d:
                    os.rename(tmp, parts[-1], src_dir_fd=up, dst_dir_fd=d)
                    os.fsync(d)
            except BaseException as exc:
                try:
                    os.unlink(tmp, dir_fd=up)
                except FileNotFoundError:
                    pass
                if isinstance(exc, OSError):
                    raise paths.os_error(exc) from None
                raise

    @staticmethod
    def _read_chunk(d: int, digest: str) -> bytes | None:
        try:
            fd = os.open(digest, paths.O_FILE_READ, dir_fd=d)
        except OSError:
            return None
        try:
            parts = []
            while block := os.read(fd, CHUNK_LIMIT):
                parts.append(block)
            data = b"".join(parts)
        finally:
            os.close(fd)
        return data if hashlib.sha256(data).hexdigest() == digest else None

    # ---- versions -----------------------------------------------------------------------
    def _latest(self, root: Root, file_id: str) -> VersionRow | None:
        with self.db.session() as s:
            q = select(VersionRow).where(VersionRow.root == root.id, VersionRow.file_id == file_id)
            return s.scalars(q.order_by(VersionRow.revision.desc(), VersionRow.created_at.desc()).limit(1)).first()

    def _keep_previous(self, root: Root, parts: tuple[str, ...], cur: IndexRow) -> None:
        """The file about to be replaced is a version already unless it changed outside sync; then cut it now."""
        last = self._latest(root, cur.file_id)
        if last is not None and (last.revision == cur.revision or cur.hash == "sha256:" + last.sha256):
            return
        manifest, whole = [], hashlib.sha256()
        with self.files._space(root) as space, paths.dir_at(space, parts[:-1]) as d, self._chunks_dir(root) as cd:
            fd, _st = paths.open_file_at(d, parts[-1])
            try:
                buf, eof = bytearray(), False
                while buf or not eof:
                    while not eof and len(buf) < CHUNK_MAX:
                        block = os.read(fd, 1 << 20)
                        eof = not block
                        buf += block
                    if not buf:
                        break
                    n = cut_point(buf)
                    piece = bytes(buf[:n])
                    del buf[:n]
                    whole.update(piece)
                    digest = hashlib.sha256(piece).hexdigest()
                    self._write_chunk(cd, digest, piece)
                    manifest.append({"hash": digest, "size": n})
            finally:
                os.close(fd)
        self._add_version(root, cur, manifest, sum(c["size"] for c in manifest), whole.hexdigest(), "hub", None)

    def _add_version(self, root: Root, row: IndexRow, chunks: list[dict], size: int, sha256: str,
                     origin: str, by: str | None) -> VersionRow:
        v = VersionRow(id=new_id("ver"), root=root.id, file_id=row.file_id, path=row.path, revision=row.revision,
                       size=size, sha256=sha256, chunks=[[c["hash"], c["size"]] for c in chunks], origin=origin,
                       created_by=by, created_at=self.files.clock())
        with self.db.session.begin() as s:
            s.add(v)
        return v

    def _prune(self, root: Root, file_id: str) -> int:
        """Drop the file's versions past `keep`, then the chunks no version of this root still names
        and no device has sent or asked about within CHUNK_TTL (an upload in progress keeps its chunks)."""
        with self.db.session.begin() as s:
            q = select(VersionRow).where(VersionRow.root == root.id, VersionRow.file_id == file_id)
            rows = list(s.scalars(q.order_by(VersionRow.revision.desc(), VersionRow.created_at.desc())))
            old = rows[self.keep:]
            if not old:
                return 0
            dropped = {c[0] for v in old for c in v.chunks}
            s.execute(delete(VersionRow).where(VersionRow.id.in_([v.id for v in old])))
            s.flush()
            still = {c[0] for v in s.scalars(select(VersionRow).where(VersionRow.root == root.id)) for c in v.chunks}
        now = time.time()
        with self._chunks_dir(root) as d:
            for h in dropped - still:
                if not self._leased(d, h, now):
                    self._unlink(d, h)
        return len(old)

    def sweep(self, root: Root, force: bool = False) -> int:
        """Remove chunks (and interrupted .part writes) that no version names once their lease ran out:
        an abandoned upload's chunks do not stay on the disk. Runs at most every SWEEP_EVERY per root."""
        mono = time.monotonic()
        last = self._swept.get(root.id)
        if not force and last is not None and mono - last < SWEEP_EVERY:
            return 0
        self._swept[root.id] = mono
        with self.db.session() as s:
            named = {c[0] for v in s.scalars(select(VersionRow).where(VersionRow.root == root.id)) for c in v.chunks}
        now, removed = time.time(), 0
        with self._chunks_dir(root) as d:
            for name in os.listdir(d):
                is_part = name.startswith(".") and name.endswith(".part")
                if (is_part or (HEX64.match(name) and name not in named)) and not self._leased(d, name, now):
                    removed += self._unlink(d, name)
        return removed

    @staticmethod
    def _unlink(d: int, name: str) -> int:
        try:
            os.unlink(name, dir_fd=d)
            return 1
        except FileNotFoundError:
            return 0

    def versions(self, p: Principal, root: str | None, path: str | None) -> dict:
        t = self.files.target(p, root, path, "read")
        cur = self._current(t.root, t.parts) if t.parts else None
        if cur is None or cur.type != "file":
            raise FilesError(404, "not_found", "no such file")
        with self.db.session() as s:
            q = select(VersionRow).where(VersionRow.root == t.root.id, VersionRow.file_id == cur.file_id)
            rows = list(s.scalars(q.order_by(VersionRow.revision.desc(), VersionRow.created_at.desc())))
        self.files._audit_read(p, "sync.versions", t)
        return {"root": t.root.id, "path": t.path, "id": cur.file_id, "revision": cur.revision,
                "versions": [{"id": v.id, "revision": v.revision, "size": v.size, "sha256": v.sha256,
                              "chunks": len(v.chunks), "origin": v.origin, "created_by": v.created_by,
                              "created_at": iso(aware(v.created_at)),
                              "current": cur.hash == "sha256:" + v.sha256 and v.revision == cur.revision}
                             for v in rows]}


__all__ = ["CHUNK_AVG", "CHUNK_LIMIT", "CHUNK_MAX", "CHUNK_MIN", "CHUNK_TTL", "ChunksMissing", "MANIFEST_MAX_CHUNKS",
           "StaleBase", "Transfer", "VERSIONS_KEEP", "VersionRow", "cut_point", "manifest_of"]
