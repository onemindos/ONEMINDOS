# SPDX-License-Identifier: Apache-2.0
"""Resumable uploads: tus 1.0.0 core with the creation, termination, checksum and expiration
extensions (https://tus.io/protocols/resumable-upload), plus whole-file digest verification.

Why tus and not the IETF draft (draft-ietf-httpbis-resumable-upload): tus is stable, has MIT
client libraries for browsers, React Native and Go (tus-js-client, tusd), and the IETF draft is
still changing. The digest headers follow the IETF style where they overlap: the creation
request may carry `Repr-Digest: sha-256=:<base64>:` (RFC 9530) instead of `sha256` metadata.

Flow: POST creates an upload (permission, name, quota and free space checked, the full length
reserved against the quota) -> PATCH appends bytes at `Upload-Offset` (each chunk may carry
`Upload-Checksum: sha256 <base64>`; a mismatch discards the chunk, answer 460) -> when the last
byte arrives, the whole file's sha256 is compared with the declared one, and only then is the
file moved into place in one rename. A failed digest deletes the upload. HEAD returns the
offset to resume from after a dropped connection or a gateway restart.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import timedelta

from ..auth import Principal
from ..ledger import iso
from . import paths
from .errors import FilesError, conflict, not_found
from .service import FilesService
from .store import UploadRow, aware, new_id

log = logging.getLogger("onemind.files.uploads")

TUS_VERSION = "1.0.0"
TUS_EXTENSIONS = "creation,termination,checksum,expiration"
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
READ_CHUNK = 1024 * 1024


class ChecksumMismatch(FilesError):
    def __init__(self, message: str = "the chunk does not match its Upload-Checksum"):
        super().__init__(460, "conflict", message, reason="checksum_mismatch")


def parse_metadata(header: str | None) -> dict[str, str]:
    """tus Upload-Metadata: comma-separated `key base64value` pairs (value may be absent)."""
    out: dict[str, str] = {}
    if not header:
        return out
    for item in header.split(","):
        item = item.strip()
        if not item:
            continue
        key, _, value = item.partition(" ")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", key) or key in out:
            raise FilesError(422, "conflict", "malformed Upload-Metadata", reason="invalid_metadata")
        try:
            out[key] = base64.b64decode(value.strip(), validate=True).decode("utf-8") if value.strip() else ""
        except (binascii.Error, UnicodeDecodeError):
            raise FilesError(422, "conflict", f"Upload-Metadata {key} is not base64 UTF-8", reason="invalid_metadata") from None
    return out


def parse_repr_digest(header: str | None) -> str | None:
    """RFC 9530 `Repr-Digest: sha-256=:<base64>:` -> hex, or None when absent or another algorithm."""
    if not header:
        return None
    m = re.search(r"(?:^|,)\s*sha-256=:([A-Za-z0-9+/=]+):", header)
    if not m:
        return None
    try:
        raw = base64.b64decode(m.group(1), validate=True)
    except binascii.Error:
        raise FilesError(422, "conflict", "Repr-Digest is not valid base64", reason="invalid_digest") from None
    if len(raw) != 32:
        raise FilesError(422, "conflict", "Repr-Digest sha-256 must be 32 bytes", reason="invalid_digest")
    return raw.hex()


def parse_checksum(header: str | None) -> bytes | None:
    if not header:
        return None
    algo, _, value = header.strip().partition(" ")
    if algo.lower() != "sha256":
        raise FilesError(400, "conflict", "only sha256 Upload-Checksum is supported", reason="checksum_algorithm")
    try:
        raw = base64.b64decode(value.strip(), validate=True)
    except binascii.Error:
        raise FilesError(400, "conflict", "Upload-Checksum is not valid base64", reason="checksum_algorithm") from None
    if len(raw) != 32:
        raise FilesError(400, "conflict", "Upload-Checksum sha256 must be 32 bytes", reason="checksum_algorithm")
    return raw


@dataclass
class Patch:
    upload: UploadRow
    fd: int
    start: int
    expected: bytes | None
    limit: int
    written: int = 0
    hasher: "hashlib._Hash" = field(default_factory=hashlib.sha256)


class Uploads:
    def __init__(self, files: FilesService):
        self.files = files
        self.settings = files.settings
        self.repo = files.repo
        self.clock = files.clock
        self._busy: set[str] = set()
        self._busy_lock = threading.Lock()

    @staticmethod
    def part_name(upload_id: str) -> str:
        return f"{upload_id}.part"

    def json(self, row: UploadRow) -> dict:
        return {
            "id": row.id, "root": row.root, "path": paths.join(paths.split_path(row.dir_path) + (row.name,)),
            "length": row.length, "offset": row.received, "sha256": row.sha256, "state": row.state,
            "created_at": iso(aware(row.created_at)), "expires_at": iso(aware(row.expires_at)),
        }

    # ---- create ---------------------------------------------------------------------------
    def create(self, p: Principal, length: int | None, metadata: dict[str, str], repr_digest: str | None) -> UploadRow:
        if length is None or length < 0:
            raise FilesError(422, "conflict", "Upload-Length is required (deferred length is not supported)",
                             reason="length_required")
        if length > self.settings.upload_max_bytes:
            raise FilesError(413, "payload_too_large", f"uploads are limited to {self.settings.upload_max_bytes} bytes",
                             reason="upload_too_large", headers={"Tus-Max-Size": str(self.settings.upload_max_bytes)})
        name = metadata.get("filename") or metadata.get("name")
        if not name:
            raise FilesError(422, "conflict", "Upload-Metadata needs filename", reason="invalid_metadata")
        paths.validate_name(name)
        digest = (metadata.get("sha256") or "").lower() or None
        if digest is not None and not SHA256_HEX.match(digest):
            raise FilesError(422, "conflict", "sha256 metadata must be 64 hex characters", reason="invalid_digest")
        if repr_digest is not None:
            if digest is not None and digest != repr_digest:
                raise FilesError(422, "conflict", "sha256 metadata and Repr-Digest disagree", reason="invalid_digest")
            digest = repr_digest
        overwrite = metadata.get("overwrite", "") in ("1", "true", "yes")
        t = self.files.target(p, metadata.get("root"), metadata.get("path"), "write")
        self.expire_due()  # abandoned partial files are removed as soon as anyone starts another upload
        with self.files._lock, self.files._space(t.root) as space, paths.dir_at(space, t.parts) as d:
            if sum(1 for u in self.repo.open_uploads() if u.principal_id == p.id) >= self.settings.max_open_uploads:
                raise FilesError(429, "rate_limited",
                                 f"at most {self.settings.max_open_uploads} unfinished uploads at once; finish or delete one",
                                 reason="too_many_uploads", headers={"Retry-After": "60"})
            if paths.exists_at(d, name) and not overwrite:
                raise conflict("a file with that name already exists (send overwrite=1 to replace it)", "exists")
            self.files.check_space(t.root, length)
            now = self.clock()
            row = UploadRow(
                id=new_id("upl"), principal_id=p.id, root=t.root.id, dir_path=t.path, name=name, length=length,
                received=0, sha256=digest, overwrite=overwrite, state="open", created_at=now, updated_at=now,
                expires_at=now + timedelta(hours=self.settings.upload_expiry_hours),
            )
            with self.files._system("uploads") as up:
                fd = os.open(self.part_name(row.id), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640, dir_fd=up)
                os.close(fd)
            self.repo.add_upload(row)
        self.files.event("upload.created", p, {"upload_id": row.id, "root": row.root,
                                               "path": paths.join(t.parts + (name,)), "length": length,
                                               "sha256": digest})
        if length == 0:
            return self.complete(p, row.id)
        return row

    # ---- lookup, expiry, termination -------------------------------------------------------
    def get(self, p: Principal, upload_id: str) -> UploadRow:
        row = self.repo.upload(upload_id) if re.fullmatch(r"upl_[0-9A-Z]{26}", upload_id or "") else None
        if row is None or row.principal_id != p.id:
            raise not_found("no such upload")
        if row.state == "open" and self.clock() >= aware(row.expires_at):
            self._discard(row, "expired", None)
            row = self.repo.upload(upload_id)
        if row.state in ("expired", "terminated", "failed"):
            raise FilesError(404, "not_found", f"upload is {row.state}", reason=f"upload_{row.state}")
        return row

    def _discard(self, row: UploadRow, state: str, p: Principal | None, **extra) -> None:
        if not self.repo.update_upload(row.id, self.clock(), from_states={"open"}, state=state):
            return
        try:
            with self.files._system("uploads") as up:
                os.unlink(self.part_name(row.id), dir_fd=up)
        except FileNotFoundError:
            pass
        self.files.event(f"upload.{state}", p, {"upload_id": row.id, "root": row.root, **extra},
                         severity="warning" if state == "failed" else "info")

    def terminate(self, p: Principal, upload_id: str) -> None:
        row = self.get(p, upload_id)
        if row.state != "open":
            raise conflict(f"upload is {row.state}")
        self._discard(row, "terminated", p)

    def expire_due(self) -> int:
        n = 0
        now = self.clock()
        for row in self.repo.open_uploads():
            if now >= aware(row.expires_at):
                self._discard(row, "expired", None)
                n += 1
        return n

    # ---- PATCH ----------------------------------------------------------------------------
    def begin_patch(self, p: Principal, upload_id: str, offset: int | None, checksum: str | None,
                    content_length: int | None) -> Patch:
        row = self.get(p, upload_id)
        if row.state != "open":
            raise conflict(f"upload is {row.state}", "upload_closed")
        if offset is None or offset != row.received:
            raise conflict(f"Upload-Offset must be {row.received}", "offset_mismatch")
        expected = parse_checksum(checksum)
        limit = min(row.length - row.received, self.settings.chunk_max_bytes)
        if content_length is not None and content_length > limit:
            raise FilesError(413, "payload_too_large", f"this chunk may be at most {limit} bytes", reason="chunk_too_large")
        free = self.files.free_bytes()  # the space reserved at creation is not on disk until written
        if free is not None and free - (content_length or 0) < self.settings.min_free_bytes:
            raise FilesError(413, "payload_too_large", "not enough free space on the disk", reason="insufficient_space")
        with self._busy_lock:
            if row.id in self._busy:
                raise conflict("another request is writing this upload", "upload_busy")
            self._busy.add(row.id)
        try:
            with self.files._system("uploads") as up:
                fd = os.open(self.part_name(row.id), os.O_WRONLY | os.O_NOFOLLOW, dir_fd=up)
            os.ftruncate(fd, row.received)  # drop bytes a crashed request wrote but never committed
            os.lseek(fd, row.received, os.SEEK_SET)
        except OSError as exc:
            self._release(row.id)
            raise paths.os_error(exc) from None
        return Patch(upload=row, fd=fd, start=row.received, expected=expected, limit=limit)

    def write(self, patch: Patch, data: bytes) -> None:
        if patch.written + len(data) > patch.limit:
            raise FilesError(413, "payload_too_large", "the chunk is longer than the upload or the chunk limit",
                             reason="chunk_too_large")
        view = memoryview(data)
        while view:
            n = os.write(patch.fd, view)
            view = view[n:]
        patch.hasher.update(data)
        patch.written += len(data)

    def abort(self, patch: Patch) -> None:
        """A request that failed mid-body: keep nothing it wrote (the client resumes from HEAD)."""
        try:
            os.ftruncate(patch.fd, patch.start)
        finally:
            os.close(patch.fd)
            self._release(patch.upload.id)

    def finish(self, p: Principal, patch: Patch, *, interrupted: bool = False) -> UploadRow:
        """Commit the chunk. An interrupted chunk without a checksum keeps what arrived (tus core)."""
        try:
            if patch.expected is not None and (interrupted or patch.hasher.digest() != patch.expected):
                os.ftruncate(patch.fd, patch.start)
                raise ChecksumMismatch() if not interrupted else conflict("chunk interrupted", "interrupted")
            os.fsync(patch.fd)
            offset = patch.start + patch.written
            self.repo.update_upload(patch.upload.id, self.clock(), from_states={"open"}, received=offset)
        finally:
            os.close(patch.fd)
            self._release(patch.upload.id)
        row = self.repo.upload(patch.upload.id)
        if row.received == row.length and not interrupted:
            return self.complete(p, row.id)
        return row

    def _release(self, upload_id: str) -> None:
        with self._busy_lock:
            self._busy.discard(upload_id)

    # ---- completion -----------------------------------------------------------------------
    def _file_sha256(self, upload_id: str) -> str:
        h = hashlib.sha256()
        with self.files._system("uploads") as up:
            fd = os.open(self.part_name(upload_id), os.O_RDONLY | os.O_NOFOLLOW, dir_fd=up)
        try:
            while chunk := os.read(fd, READ_CHUNK):
                h.update(chunk)
        finally:
            os.close(fd)
        return h.hexdigest()

    def complete(self, p: Principal, upload_id: str) -> UploadRow:
        row = self.repo.upload(upload_id)
        actual = self._file_sha256(row.id)
        if row.sha256 is not None and actual != row.sha256:
            self._discard(row, "failed", p, reason="digest_mismatch", expected=row.sha256, actual=actual)
            raise conflict("the uploaded file does not match its declared sha256; upload again", "digest_mismatch")
        # Permission is checked again: a grant may have been revoked while the bytes arrived.
        try:
            t = self.files.target(p, row.root, row.dir_path, "write")
        except FilesError:
            self._discard(row, "failed", p, reason="permission_revoked")
            raise
        replaced = None
        with self.files._lock, self.files._space(t.root) as space:
            try:
                d = paths.open_dir(space, t.parts)
            except FilesError as exc:
                self._discard(row, "failed", p, reason="folder_gone")
                raise FilesError(409, "stale_precondition", f"the destination folder is gone ({exc.message})") from None
            try:
                if paths.exists_at(d, row.name):
                    if not row.overwrite:
                        self._discard(row, "failed", p, reason="exists")
                        raise conflict("a file with that name appeared meanwhile", "exists")
                    if paths.kind_of(paths.lstat_at(d, row.name)) != "file":
                        self._discard(row, "failed", p, reason="exists")
                        raise conflict("only a file can be replaced by an upload", "exists")
                    replaced = self.files.trash(p, row.root, paths.join(t.parts + (row.name,)))["id"]
                with self.files._system("uploads") as up:
                    os.rename(self.part_name(row.id), row.name, src_dir_fd=up, dst_dir_fd=d)
                os.fsync(d)
            finally:
                os.close(d)
        self.repo.update_upload(row.id, self.clock(), from_states={"open"}, state="done", sha256=actual)
        self.files.event("upload.completed", p, {
            "upload_id": row.id, "root": row.root, "path": paths.join(t.parts + (row.name,)),
            "size": row.length, "sha256": actual, **({"replaced_trash_id": replaced} if replaced else {}),
        })
        return self.repo.upload(row.id)
