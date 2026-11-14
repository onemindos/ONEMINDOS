# SPDX-License-Identifier: Apache-2.0
"""OneMind Photos, box side of phone photo backup (docs/leap/core/PHOTOS.md).

The phone protocol is mobile/docs/photos-backup-api.md (interim contract §12-p): register a
source, `check` what the box already holds, upload the rest with the IETF resumable-upload draft
(POST to create, HEAD for the offset, PATCH to append), then read coverage.

Guarantees, each with a test in core/tests/test_photos.py:
- **Digest-verified:** the box hashes what it stored and refuses bytes that do not match the
  phone's declared SHA-256. No receipt exists for unverified bytes.
- **fsync before receipt:** every PATCH is fsynced before its offset is acknowledged; the stored
  copy and each new directory entry are fsynced before the database records the receipt.
- **Per-person libraries:** every query takes the caller's own principal id; another person's
  sources and uploads answer 404.
- **Dedupe without a hash oracle:** `check` answers `have` only from the asking person's own
  photos. Bytes another person holds are stored once, but only after this person uploaded and
  verified all of them, and the answer is the same as if nobody else had them.
- **Receipt levels:** on_box, in_backup, in_verified_backup, from backup.* events.
"""

from __future__ import annotations

import fcntl
import hashlib
import logging
import os
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

from ..auth import Principal
from ..errors import ApiError
from ..events import EventHub
from ..ledger import iso, utc
from .db import PhotosRepository, Source, Upload
from .files import PhotoFiles, person_folder, safe_file_name, sha256_file, source_folder
from .settings import PhotosSettings

log = logging.getLogger("onemind.photos")

KEY_RE = re.compile(r"^[0-9a-f]{64}$")
HASH_RE = re.compile(r"^sha256:([0-9a-f]{64})$")
ID_RE = re.compile(r"^(src|upl)_[0-9A-Z]{26}$")
PERSON_ROLES = ("owner", "adult")
MAX_CHECK = 500
PHOTOS_UNIT = "photos"  # the backup unit that holds ONEMIND_PHOTOS_DIR (PHOTOS.md §5)
LEVELS = ("on_box", "in_backup", "in_verified_backup")
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_id(prefix: str) -> str:
    """Prefixed ULID (contract §12.1): 48-bit milliseconds, then 80 random bits, Crockford base32."""
    n = (int(time.time() * 1000) << 80) | int.from_bytes(os.urandom(10), "big")
    return prefix + "_" + "".join(_CROCKFORD[(n >> (5 * i)) & 31] for i in range(25, -1, -1))


class PhotosError(ApiError):
    """An ApiError that may carry upload headers (Upload-Offset ...) on its error response."""

    def __init__(self, status: int, error: str, message: str, headers: dict[str, str] | None = None):
        super().__init__(status, error, message)
        self.headers = headers or {}


class HasherCache:
    """SHA-256 state per open upload, so finishing a large upload does not reread the whole file.

    An entry is used only for the exact length it covers. After a restart, in another worker, or
    after any doubt, the box rehashes the staged file from disk instead.
    """

    def __init__(self, limit: int = 256):
        self.limit = limit
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, tuple[int, object]] = OrderedDict()

    def take(self, upload_id: str, size: int):
        with self._lock:
            entry = self._entries.pop(upload_id, None)
        return entry[1] if entry is not None and entry[0] == size else None

    def put(self, upload_id: str, size: int, hasher) -> None:
        if hasher is None:
            self.drop(upload_id)
            return
        with self._lock:
            self._entries[upload_id] = (size, hasher)
            self._entries.move_to_end(upload_id)
            while len(self._entries) > self.limit:
                self._entries.popitem(last=False)

    def drop(self, upload_id: str) -> None:
        with self._lock:
            self._entries.pop(upload_id, None)


def _time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return utc(dt) if dt.tzinfo is not None else None


def _covers_photos(data: dict) -> bool:
    units = data.get("units")
    return (isinstance(units, list) and PHOTOS_UNIT in units) or data.get("unit") == PHOTOS_UNIT


class AppendSession:
    """One PATCH: holds the upload's lock and its open staging file until finish()."""

    def __init__(self, svc: PhotosService, p: Principal, up: Upload, fd: int, start: int, hasher):
        self.svc, self.p, self.up, self.fd = svc, p, up, fd
        self.start = self.size = start
        self.hasher = hasher
        self.overflow = False
        self.error: OSError | None = None

    def write(self, data: bytes) -> bool:
        """Append data; False (stop sending) once it would pass Upload-Length or the disk failed."""
        if self.overflow or self.error is not None:
            return False
        if self.size + len(data) > self.up.length:
            self.overflow = True
            return False
        view = memoryview(data)
        try:
            while view:
                n = os.write(self.fd, view)
                view = view[n:]
        except OSError as exc:  # e.g. ENOSPC: what reached the disk stays, the hash state is lost
            self.error, self.hasher = exc, None
            return False
        if self.hasher is not None:
            self.hasher.update(data)
        self.size += len(data)
        return True

    def finish(self, complete: bool, stalled: bool = False) -> dict:
        """fsync, record progress, release the lock; on the last part verify and store.

        Returns {"offset": n} or {"offset": n, "receipt": {...}}. Raises PhotosError (409) for a
        stall, an overflow, a short final part or a write error, always with the true offset.
        """
        svc, up = self.svc, self.up
        try:
            if self.overflow:
                os.ftruncate(self.fd, self.start)  # drop this request's bytes, keep the earlier ones
                self.hasher = None
            size = os.fstat(self.fd).st_size
            if self.hasher is not None and size != self.size:
                self.hasher = None
            os.fsync(self.fd)
            now = svc.clock()
            svc.repo.set_progress(up.id, size, now, now + svc.ttl)
            if self.overflow:
                raise svc.conflict(up, size, "the request carries more bytes than Upload-Length")
            if self.error is not None:
                svc.hashers.drop(up.id)
                raise svc.conflict(up, size, f"the box could not store the bytes ({self.error.strerror})")
            if stalled or not complete or size != up.length:
                svc.hashers.put(up.id, size, self.hasher)
                if stalled:
                    raise svc.conflict(up, size, "the upload stalled; ask for the offset and continue")
                if complete:
                    raise svc.conflict(up, size, f"the upload holds {size} of {up.length} bytes; send the rest")
                return {"offset": size}
            return {"offset": size, "receipt": svc.finalize(self.p, up, self.hasher)}
        finally:
            os.close(self.fd)  # also releases the flock


class PhotosService:
    def __init__(
        self,
        settings: PhotosSettings,
        repo: PhotosRepository,
        clock: Callable[[], datetime],
        events: EventHub,
        audit,
    ):
        self.settings = settings
        self.repo = repo
        self.clock = clock
        self.events = events
        self.audit = audit  # the gateway audit log: a refused caller is recorded as authz.denied
        self.files = PhotoFiles(settings.dir or Path("photos-disabled"))
        self.ttl = timedelta(seconds=settings.upload_ttl_s)
        self.hashers = HasherCache()

    # ---- who may use it ----------------------------------------------------------------------
    def person(self, p: Principal) -> str:
        """The caller's own library owner id. Photos off: 404. Guests and agents: 403."""
        if not self.settings.enabled:
            raise PhotosError(404, "not_found", "Photos is not turned on on this box")
        if p.kind != "person" or p.role not in PERSON_ROLES:
            self.audit.append("authz.denied", p.as_dict(), None,
                              {"attempted": "use photo backup", "reason": "permission_denied"})
            raise PhotosError(
                403, "permission_denied",
                "photo backup needs a person's own sign-in (owner or adult); guests and agents have no photo library",
            )
        return p.id

    def _source(self, owner: str, source_id: str) -> Source:
        src = self.repo.get_source(owner, source_id) if ID_RE.match(source_id) else None
        if src is None:  # someone else's source looks exactly like a missing one
            raise PhotosError(404, "not_found", "no such photo source")
        return src

    def _upload(self, owner: str, upload_id: str) -> Upload:
        up = self.repo.get_upload(upload_id) if ID_RE.match(upload_id) else None
        if up is None or up.owner != owner:
            raise PhotosError(404, "not_found", "no such upload")
        return up

    # ---- sources and check --------------------------------------------------------------------
    def register_source(self, p: Principal, client_id: str, name: str, platform: str) -> tuple[dict, bool]:
        owner = self.person(p)
        name = "".join(c for c in name if c.isprintable()).strip()[:100] or "Phone"
        src, created = self.repo.register_source(
            owner, client_id, name, platform, lambda: new_id("src"), lambda sid: source_folder(name, sid), self.clock()
        )
        if created:
            self.events.publish_event(
                "photos", "source.registered", {"source_id": src.id, "platform": platform},
                principal=p.as_dict(), resource={"kind": "photo_source", "id": src.id},
            )
        return src.public(), created

    def check(self, p: Principal, source_id: str, items: list[tuple[str, int, str]]) -> list[dict]:
        src = self._source(self.person(p), source_id)
        if len(items) > MAX_CHECK:
            raise PhotosError(422, "conflict", f"check takes at most {MAX_CHECK} items")
        parsed = []
        for key, size, h in items:
            m = HASH_RE.match(h)
            if not KEY_RE.match(key) or m is None or size < 0:
                raise PhotosError(422, "conflict", "each item needs client_key (64 hex), size and hash (sha256:<64 hex>)")
            parsed.append((key, size, m.group(1)))
        now = self.clock()
        held = self.repo.check(src, parsed, self.files.asset_present, now) if parsed else []
        self.repo.touch_source(src.id, now)
        return [{"client_key": k, "status": "have" if ok else "need"} for (k, _, _), ok in zip(parsed, held)]

    # ---- uploads ------------------------------------------------------------------------------
    def offset_headers(self, up: Upload, offset: int, complete: bool) -> dict[str, str]:
        return {
            "Upload-Offset": str(offset),
            "Upload-Complete": "?1" if complete else "?0",
            "Upload-Length": str(up.length),
            "Upload-Limit": f"max-size={self.settings.max_upload_bytes}",
            "Cache-Control": "no-store",
        }

    def conflict(self, up: Upload, offset: int, message: str) -> PhotosError:
        return PhotosError(409, "conflict", message, self.offset_headers(up, offset, up.state == "complete"))

    def create_upload(
        self, p: Principal, *, source_id: str, client_key: str, content_hash: str, length: int,
        file_name: str | None, created_at: str | None, complete: bool,
    ) -> tuple[str, int]:
        """A new (or the matching unfinished) upload for one phone item. Returns (id, offset)."""
        owner = self.person(p)
        src = self._source(owner, source_id)
        if complete:
            raise PhotosError(422, "conflict", "create the upload with Upload-Complete: ?0 and send the bytes with PATCH")
        m = HASH_RE.match(content_hash)
        if not KEY_RE.match(client_key) or m is None:
            raise PhotosError(422, "conflict", "OneMind-Client-Key must be 64 hex and OneMind-Content-Hash sha256:<64 hex>")
        if length < 1:
            raise PhotosError(422, "conflict", "Upload-Length must be at least 1")
        if length > self.settings.max_upload_bytes:
            raise PhotosError(409, "conflict", f"this box takes files up to {self.settings.max_upload_bytes} bytes")
        try:
            name = safe_file_name(unquote(file_name or "", errors="strict"))
        except UnicodeDecodeError:
            raise PhotosError(422, "conflict", "OneMind-File-Name must be percent-encoded UTF-8") from None
        taken_at = None
        if created_at:
            taken_at = _time(created_at)
            if taken_at is None:
                raise PhotosError(422, "conflict", "OneMind-Created-At must be an RFC 3339 time with an offset")
        h = m.group(1)
        now = self.clock()
        self.sweep(limit=50)
        existing = self.repo.find_open_upload(src.id, client_key, h, length, now)
        if existing is not None:
            size = self.files.staged_size(existing.id)
            if size is not None:
                return existing.id, size
        open_count, pending = self.repo.open_stats(src.id, now)
        if open_count >= self.settings.max_open_uploads:
            raise PhotosError(409, "conflict", "this phone has too many unfinished uploads; finish them or let them expire")
        if length + pending + self.settings.reserve_bytes > self.files.free_bytes():
            raise PhotosError(409, "conflict", "not enough free space on the box for this file")
        upload_id = new_id("upl")
        self.repo.create_upload({
            "id": upload_id, "owner": owner, "source_id": src.id, "client_key": client_key, "hash": h,
            "length": length, "received": 0, "file_name": name, "taken_at": taken_at, "state": "open",
            "receipt": None, "created_at": now, "updated_at": now, "expires_at": now + self.ttl,
        })
        try:
            self.files.create_staging(upload_id)
        except BaseException:
            self.repo.delete_upload(upload_id)
            raise
        self.repo.touch_source(src.id, now)
        return upload_id, 0

    def _alive(self, up: Upload, now: datetime) -> None:
        if up.state == "failed" or up.expires_at <= now:
            raise PhotosError(410, "expired", "this upload has ended; create a new one")

    def upload_status(self, p: Principal, upload_id: str) -> dict[str, str]:
        """HEAD: the bytes the box holds (the staged file's length) and whether the upload is done."""
        up = self._upload(self.person(p), upload_id)
        if up.state == "complete":
            return self.offset_headers(up, up.length, True)
        self._alive(up, self.clock())
        size = self.files.staged_size(up.id)
        if size is None:
            raise PhotosError(410, "expired", "this upload's bytes are gone; create a new one")
        return self.offset_headers(up, size, False)

    def _replay(self, up: Upload, offset: int, complete: bool) -> dict:
        """A repeated last PATCH of a finished upload gets the same receipt (the draft allows replay)."""
        if complete and offset == up.length and up.receipt:
            return {"replay": True, "receipt": up.receipt, "headers": self.offset_headers(up, up.length, True)}
        raise self.conflict(up, up.length, "this upload is already complete")

    def begin_append(self, p: Principal, upload_id: str, offset: int, complete: bool) -> AppendSession | dict:
        """Lock the upload, check Upload-Offset against the bytes on disk, and open it for appending."""
        up = self._upload(self.person(p), upload_id)
        if up.state == "complete":
            return self._replay(up, offset, complete)
        now = self.clock()
        self._alive(up, now)
        try:
            fd = os.open(self.files.staging(up.id), os.O_WRONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            self.repo.fail_upload(up.id, now)
            raise PhotosError(410, "expired", "this upload's bytes are gone; create a new one") from None
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise self.conflict(up, os.fstat(fd).st_size, "another request is adding to this upload") from None
            up = self.repo.get_upload(up.id) or up  # re-read under the lock: it may have just finished
            if up.state == "complete":
                replay = self._replay(up, offset, complete)  # raises: the except below closes fd once
                os.close(fd)
                return replay
            self._alive(up, now)
            size = os.fstat(fd).st_size
            if offset != size:
                raise self.conflict(up, size, f"Upload-Offset is {offset} but the box holds {size} bytes")
            os.lseek(fd, size, os.SEEK_SET)
            hasher = self.hashers.take(up.id, size)
            if hasher is None and size == 0:
                hasher = hashlib.sha256()
            return AppendSession(self, p, up, fd, size, hasher)
        except BaseException:
            os.close(fd)
            raise

    def finalize(self, p: Principal, up: Upload, hasher) -> dict:
        """Verify the complete, fsynced staged file and store it. Runs under the upload's lock."""
        staged = self.files.staging(up.id)
        digest = hasher.hexdigest() if hasher is not None else sha256_file(staged)
        now = self.clock()
        self.hashers.drop(up.id)
        if digest != up.hash:
            self.files.discard(staged)
            self.repo.fail_upload(up.id, now)
            self.events.publish_event(
                "photos", "upload.rejected",
                {"source_id": up.source_id, "upload_id": up.id, "reason": "digest_mismatch", "length": up.length},
                principal=p.as_dict(), severity="warning", resource={"kind": "photo_source", "id": up.source_id},
                dedupe_key=f"photos:{up.source_id}:upload_rejected",
            )
            raise PhotosError(409, "conflict", "the bytes do not match OneMind-Content-Hash; nothing was kept, create a new upload")
        library_path = None
        healed = False
        asset = self.repo.person_asset(up.owner, up.hash)
        if asset is None:
            self.files.place_blob(staged, up.hash, up.length)
            src = self.repo.get_source(up.owner, up.source_id)
            when = up.taken_at if up.taken_at is not None and up.taken_at.year >= 1970 and up.taken_at <= now + timedelta(days=1) else now
            folder = PurePosixPath(person_folder(up.owner), src.folder if src else "phone", f"{when:%Y}", f"{when:%m}")
            library_path = self.files.link_into_library(up.hash, folder, up.file_name)
        else:  # the person has this photo: heal whatever check found missing or damaged
            if not self.files.blob_present(up.hash, up.length):
                self.files.place_blob(staged, up.hash, up.length)
                healed = True
            if not self.files.library_file_present(asset[1], up.length):
                self.files.restore_library_file(up.hash, asset[1])
                healed = True
        self.files.discard(staged)
        # Read the clock only now, after every file is linked and fsynced: a backup snapshot that
        # started before this moment may not hold the file, so it must not raise the receipt level.
        stored_at = self.clock()
        _, deduped = self.repo.commit_upload(
            up, library_path, lambda: new_id("ast"), stored_at, stored_at + self.ttl, healed=healed
        )
        if deduped and library_path is not None:  # another of this person's uploads won the race
            self.files.discard_library(library_path)
        return {"client_key": up.client_key, "hash": "sha256:" + up.hash, "deduped": deduped}

    def sweep(self, limit: int = 200) -> int:
        """Delete expired uploads and their staged bytes. Skips an upload a request still holds."""
        if not self.settings.enabled:
            return 0
        done = 0
        for upload_id, state in self.repo.expired_uploads(self.clock(), limit):
            if state == "open":
                path = self.files.staging(upload_id)
                try:
                    fd = os.open(path, os.O_WRONLY)
                except FileNotFoundError:
                    fd = None
                if fd is not None:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        os.close(fd)
                        continue
                    try:
                        self.files.discard(path)
                    finally:
                        os.close(fd)
            self.hashers.drop(upload_id)
            self.repo.delete_upload(upload_id)
            done += 1
        return done

    # ---- coverage and receipt levels ---------------------------------------------------------
    def coverage(self, p: Principal, source_id: str) -> dict:
        src = self._source(self.person(p), source_id)
        backed, verified = self.repo.snapshot_cuts()
        total, b, v = self.repo.coverage(src.id, backed, verified)
        # Until Trash exists (UMB-PHOTO-5) every receipt's photo is on the box.
        return {"total": total, "on_box": total, "backed_up": b, "verified": v, "as_of": iso(self.clock())}

    def receipts(self, p: Principal, source_id: str, cursor: str | None, limit: int) -> dict:
        src = self._source(self.person(p), source_id)
        if cursor is not None and not KEY_RE.match(cursor):
            raise PhotosError(422, "conflict", "cursor must be a next_cursor value from this list")
        backed, verified = self.repo.snapshot_cuts()
        rows = self.repo.receipts_page(src.id, cursor, limit + 1)
        items = []
        for key, h, received_at, asset_at in rows[:limit]:
            level = "on_box"
            if verified is not None and asset_at <= verified:
                level = "in_verified_backup"
            elif backed is not None and asset_at <= backed:
                level = "in_backup"
            items.append({"client_key": key, "hash": "sha256:" + h, "received_at": iso(received_at), "level": level})
        return {"items": items, "next_cursor": rows[limit - 1][0] if len(rows) > limit else None}

    def on_backup_run(self, envelope: dict) -> None:
        """backup.run.finished: a succeeded snapshot that holds the photos unit counts as backed up."""
        data = envelope.get("data") or {}
        if not self.settings.enabled or data.get("result") != "succeeded" or not _covers_photos(data):
            return
        snapshot, started = data.get("snapshot_id"), _time(data.get("started_at"))
        if not isinstance(snapshot, str) or not snapshot or len(snapshot) > 128 or started is None:
            log.warning("backup.run.finished without snapshot_id or started_at; photos coverage unchanged")
            return
        target = str(data.get("target_id") or "")[:128]
        self.repo.record_snapshot(target, snapshot, started, _time(data.get("finished_at")) or self.clock())

    def on_backup_verify(self, envelope: dict) -> None:
        """backup.verify.finished: a passed restore check of a known snapshot makes it verified."""
        data = envelope.get("data") or {}
        if not self.settings.enabled or data.get("result") != "passed" or not _covers_photos(data):
            return
        snapshot = data.get("snapshot_id")
        if not isinstance(snapshot, str) or not snapshot:
            return
        target = str(data.get("target_id") or "")[:128]
        if not self.repo.mark_verified(target, snapshot, _time(data.get("finished_at")) or self.clock()):
            log.info("backup.verify.finished for a snapshot photos has not seen (or already verified): %s", snapshot[:40])

    def on_snapshot_removed(self, envelope: dict) -> None:
        """backup.snapshot.removed: a deleted or pruned snapshot no longer protects anything."""
        data = envelope.get("data") or {}
        ids = data.get("snapshot_ids") or ([data["snapshot_id"]] if isinstance(data.get("snapshot_id"), str) else [])
        ids = [i for i in ids if isinstance(i, str) and i]
        if self.settings.enabled and ids:
            self.repo.mark_removed(str(data.get("target_id") or "")[:128], ids, self.clock())
