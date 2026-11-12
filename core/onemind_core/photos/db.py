# SPDX-License-Identifier: Apache-2.0
"""Photos tables (feature "photos") and their repository (docs/leap/core/PLUMBING.md §3).

Identity rules (docs/leap/core/PHOTOS.md §3):
- a blob is one set of bytes, keyed by its SHA-256, stored once on the box;
- an asset is one person's photo: (owner, blob) is unique, so a person never holds two copies;
- a receipt says "this phone's item (source, client_key) is these bytes, in this person's asset".
Every read and write here takes the owner or a source the caller already resolved for that owner.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, String, UniqueConstraint, case, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from ..ledger import Base, utc
from ..store import FeatureSchema, SqlRepository

SCHEMA = FeatureSchema("photos")


class PhotoSourceRow(Base):
    """One phone (one app install) backing up into one person's library."""

    __tablename__ = "photos_sources"
    __table_args__ = (UniqueConstraint("owner", "client_id", name="uq_photos_sources_owner_client"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    owner: Mapped[str] = mapped_column(String(128), index=True)
    client_id: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(100))
    platform: Mapped[str] = mapped_column(String(16))
    folder: Mapped[str] = mapped_column(String(80))  # library sub-folder, fixed at registration
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PhotoBlobRow(Base):
    """Bytes stored once in library/.shared-store/<aa>/<hash>."""

    __tablename__ = "photos_blobs"
    hash: Mapped[str] = mapped_column(String(64), primary_key=True)  # SHA-256, lower-case hex
    size: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PhotoAssetRow(Base):
    """One person's photo or video: a human-readable file in that person's library."""

    __tablename__ = "photos_assets"
    __table_args__ = (UniqueConstraint("owner", "blob_hash", name="uq_photos_assets_owner_blob"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    owner: Mapped[str] = mapped_column(String(128), index=True)
    blob_hash: Mapped[str] = mapped_column(String(64), index=True)
    library_path: Mapped[str] = mapped_column(String(1024))
    file_name: Mapped[str] = mapped_column(String(255))
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PhotoReceiptRow(Base):
    """What the box confirmed to one phone: its item `client_key` is held as `blob_hash`."""

    __tablename__ = "photos_receipts"
    source_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    client_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    blob_hash: Mapped[str] = mapped_column(String(64))
    asset_id: Mapped[str] = mapped_column(String(40), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PhotoUploadRow(Base):
    """A resumable upload. The bytes live in staging/<id>; their length on disk is the offset."""

    __tablename__ = "photos_uploads"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    owner: Mapped[str] = mapped_column(String(128))
    source_id: Mapped[str] = mapped_column(String(40), index=True)
    client_key: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
    length: Mapped[int] = mapped_column(BigInteger)
    received: Mapped[int] = mapped_column(BigInteger)  # last fsynced length (accounting only)
    file_name: Mapped[str] = mapped_column(String(255))
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state: Mapped[str] = mapped_column(String(16))  # open | complete | failed
    receipt: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class PhotoSnapshotRow(Base):
    """A box backup snapshot that holds the Photos library (from backup.* events)."""

    __tablename__ = "photos_snapshots"
    target_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


@dataclass(frozen=True)
class Source:
    id: str
    owner: str
    client_id: str
    name: str
    platform: str
    folder: str

    def public(self) -> dict:
        return {"id": self.id, "client_id": self.client_id, "name": self.name, "platform": self.platform}


@dataclass(frozen=True)
class Upload:
    id: str
    owner: str
    source_id: str
    client_key: str
    hash: str
    length: int
    file_name: str
    taken_at: datetime | None
    state: str
    receipt: dict | None
    expires_at: datetime


def _source(row: PhotoSourceRow) -> Source:
    return Source(row.id, row.owner, row.client_id, row.name, row.platform, row.folder)


def _upload(row: PhotoUploadRow) -> Upload:
    return Upload(
        row.id, row.owner, row.source_id, row.client_key, row.hash, row.length, row.file_name,
        utc(row.taken_at) if row.taken_at else None, row.state, row.receipt, utc(row.expires_at),
    )


def _opt_utc(dt: datetime | None) -> datetime | None:
    return utc(dt) if dt is not None else None


class PhotosRepository(SqlRepository):
    # ---- sources ------------------------------------------------------------------------------
    def register_source(
        self, owner: str, client_id: str, name: str, platform: str,
        new_id: Callable[[], str], folder_for: Callable[[str], str], now: datetime,
    ) -> tuple[Source, bool]:
        """The source for (owner, client_id), created if new. Returns (source, created)."""
        for _ in range(2):  # a concurrent first registration loses the insert and reads the winner
            try:
                with self.db.session.begin() as s:
                    row = s.execute(
                        select(PhotoSourceRow).where(PhotoSourceRow.owner == owner, PhotoSourceRow.client_id == client_id)
                    ).scalar_one_or_none()
                    if row is not None:
                        row.name, row.last_seen_at = name, now
                        return _source(row), False
                    sid = new_id()
                    row = PhotoSourceRow(
                        id=sid, owner=owner, client_id=client_id, name=name, platform=platform,
                        folder=folder_for(sid), created_at=now, last_seen_at=now,
                    )
                    s.add(row)
                return _source(row), True
            except IntegrityError:
                continue
        raise RuntimeError("could not register the photo source")

    def get_source(self, owner: str, source_id: str) -> Source | None:
        with self.db.session() as s:
            row = s.execute(
                select(PhotoSourceRow).where(PhotoSourceRow.id == source_id, PhotoSourceRow.owner == owner)
            ).scalar_one_or_none()
            return _source(row) if row else None

    def touch_source(self, source_id: str, now: datetime) -> None:
        with self.db.session.begin() as s:
            s.execute(update(PhotoSourceRow).where(PhotoSourceRow.id == source_id).values(last_seen_at=now))

    # ---- check --------------------------------------------------------------------------------
    def check(
        self, source: Source, items: list[tuple[str, int, str]],
        present: Callable[[str, int], bool], now: datetime,
    ) -> list[bool]:
        """For each (client_key, size, hash): True when this person holds those bytes on disk.

        Only the source owner's own assets are consulted, so the answer never depends on what
        another person holds (no hash oracle). A hit without a receipt (a duplicate on the phone,
        or bytes from the same person's other phone) records the receipt without an upload.
        """
        keys = {k for k, _, _ in items}
        hashes = {h for _, _, h in items}
        for attempt in range(2):
            try:
                with self.db.session.begin() as s:
                    receipts = {
                        r.client_key: r for r in s.scalars(
                            select(PhotoReceiptRow).where(
                                PhotoReceiptRow.source_id == source.id, PhotoReceiptRow.client_key.in_(keys)
                            )
                        )
                    }
                    held = {
                        h: (aid, size) for aid, h, size in s.execute(
                            select(PhotoAssetRow.id, PhotoAssetRow.blob_hash, PhotoBlobRow.size)
                            .join(PhotoBlobRow, PhotoBlobRow.hash == PhotoAssetRow.blob_hash)
                            .where(PhotoAssetRow.owner == source.owner, PhotoAssetRow.blob_hash.in_(hashes))
                        )
                    }
                    out: list[bool] = []
                    for key, size, h in items:
                        hit = held.get(h)
                        ok = hit is not None and hit[1] == size and present(h, size)
                        if ok:
                            r = receipts.get(key)
                            if r is None:
                                r = PhotoReceiptRow(
                                    source_id=source.id, client_key=key, blob_hash=h, asset_id=hit[0], received_at=now
                                )
                                s.add(r)
                                receipts[key] = r
                            elif r.blob_hash != h or r.asset_id != hit[0]:
                                r.blob_hash, r.asset_id, r.received_at = h, hit[0], now
                        out.append(ok)
                return out
            except IntegrityError:  # a concurrent check of the same new key; the retry reads it
                if attempt:
                    raise
        return []

    # ---- uploads ------------------------------------------------------------------------------
    def create_upload(self, row: dict) -> None:
        with self.db.session.begin() as s:
            s.add(PhotoUploadRow(**row))

    def get_upload(self, upload_id: str) -> Upload | None:
        with self.db.session() as s:
            row = s.get(PhotoUploadRow, upload_id)
            return _upload(row) if row else None

    def find_open_upload(self, source_id: str, client_key: str, h: str, length: int, now: datetime) -> Upload | None:
        with self.db.session() as s:
            row = s.execute(
                select(PhotoUploadRow).where(
                    PhotoUploadRow.source_id == source_id, PhotoUploadRow.client_key == client_key,
                    PhotoUploadRow.hash == h, PhotoUploadRow.length == length,
                    PhotoUploadRow.state == "open", PhotoUploadRow.expires_at > now,
                ).order_by(PhotoUploadRow.created_at.desc()).limit(1)
            ).scalar_one_or_none()
            return _upload(row) if row else None

    def open_stats(self, source_id: str, now: datetime) -> tuple[int, int]:
        """(open uploads of this source, bytes still to come across every open upload)."""
        with self.db.session() as s:
            mine = s.execute(
                select(func.count()).select_from(PhotoUploadRow).where(
                    PhotoUploadRow.source_id == source_id, PhotoUploadRow.state == "open", PhotoUploadRow.expires_at > now
                )
            ).scalar_one()
            pending = s.execute(
                select(func.coalesce(func.sum(PhotoUploadRow.length - PhotoUploadRow.received), 0)).where(
                    PhotoUploadRow.state == "open", PhotoUploadRow.expires_at > now
                )
            ).scalar_one()
            return int(mine), int(pending)

    def set_progress(self, upload_id: str, received: int, now: datetime, expires_at: datetime) -> None:
        with self.db.session.begin() as s:
            s.execute(
                update(PhotoUploadRow).where(PhotoUploadRow.id == upload_id, PhotoUploadRow.state == "open")
                .values(received=received, updated_at=now, expires_at=expires_at)
            )

    def fail_upload(self, upload_id: str, now: datetime) -> None:
        with self.db.session.begin() as s:
            s.execute(
                update(PhotoUploadRow).where(PhotoUploadRow.id == upload_id, PhotoUploadRow.state == "open")
                .values(state="failed", updated_at=now)
            )

    def delete_upload(self, upload_id: str) -> None:
        with self.db.session.begin() as s:
            s.execute(delete(PhotoUploadRow).where(PhotoUploadRow.id == upload_id))

    def expired_uploads(self, now: datetime, limit: int) -> list[tuple[str, str]]:
        with self.db.session() as s:
            return [
                (r.id, r.state) for r in s.scalars(
                    select(PhotoUploadRow).where(PhotoUploadRow.expires_at <= now).limit(limit)
                )
            ]

    def person_asset(self, owner: str, h: str) -> str | None:
        with self.db.session() as s:
            return s.execute(
                select(PhotoAssetRow.id).where(PhotoAssetRow.owner == owner, PhotoAssetRow.blob_hash == h)
            ).scalar_one_or_none()

    def commit_upload(
        self, up: Upload, library_path: str | None, new_id: Callable[[], str], now: datetime, keep_until: datetime,
    ) -> tuple[str, bool]:
        """Record a verified, fsynced upload: blob, asset, receipt and the upload's own receipt.

        Returns (asset_id, deduped). deduped is True when this person already held these bytes
        (from this or another of their phones); the caller then drops its new library file.
        """
        ins = self.db.insert()
        with self.db.session.begin() as s:
            s.execute(
                ins(PhotoBlobRow).values(hash=up.hash, size=up.length, created_at=now)
                .on_conflict_do_nothing(index_elements=[PhotoBlobRow.hash])
            )
            asset_id = None
            if library_path is not None:
                asset_id = s.execute(
                    ins(PhotoAssetRow).values(
                        id=new_id(), owner=up.owner, blob_hash=up.hash, library_path=library_path,
                        file_name=up.file_name, taken_at=up.taken_at, created_at=now,
                    ).on_conflict_do_nothing(index_elements=[PhotoAssetRow.owner, PhotoAssetRow.blob_hash])
                    .returning(PhotoAssetRow.id)
                ).scalar_one_or_none()
            deduped = asset_id is None
            if asset_id is None:
                asset_id = s.execute(
                    select(PhotoAssetRow.id).where(PhotoAssetRow.owner == up.owner, PhotoAssetRow.blob_hash == up.hash)
                ).scalar_one()
            s.execute(
                ins(PhotoReceiptRow).values(
                    source_id=up.source_id, client_key=up.client_key, blob_hash=up.hash, asset_id=asset_id, received_at=now,
                ).on_conflict_do_update(
                    index_elements=[PhotoReceiptRow.source_id, PhotoReceiptRow.client_key],
                    set_={"blob_hash": up.hash, "asset_id": asset_id, "received_at": now},
                )
            )
            receipt = {"client_key": up.client_key, "hash": "sha256:" + up.hash, "deduped": deduped}
            s.execute(
                update(PhotoUploadRow).where(PhotoUploadRow.id == up.id).values(
                    state="complete", received=up.length, receipt=receipt, updated_at=now, expires_at=keep_until
                )
            )
        return asset_id, deduped

    # ---- coverage and receipt levels ---------------------------------------------------------
    def snapshot_cuts(self) -> tuple[datetime | None, datetime | None]:
        """Start time of the newest kept snapshot, and of the newest kept verified one."""
        S = PhotoSnapshotRow
        with self.db.session() as s:
            backed = s.execute(select(func.max(S.started_at)).where(S.removed_at.is_(None))).scalar_one()
            verified = s.execute(
                select(func.max(S.started_at)).where(S.removed_at.is_(None), S.verified_at.is_not(None))
            ).scalar_one()
        return _opt_utc(backed), _opt_utc(verified)

    def coverage(self, source_id: str, backed: datetime | None, verified: datetime | None) -> tuple[int, int, int]:
        A, R = PhotoAssetRow, PhotoReceiptRow

        def upto(cut: datetime | None):
            if cut is None:
                return func.sum(0)
            return func.sum(case((A.created_at <= cut, 1), else_=0))

        with self.db.session() as s:
            total, b, v = s.execute(
                select(func.count(R.client_key), upto(backed), upto(verified))
                .select_from(R).join(A, A.id == R.asset_id).where(R.source_id == source_id)
            ).one()
        return int(total or 0), int(b or 0), int(v or 0)

    def receipts_page(self, source_id: str, after: str | None, limit: int) -> list[tuple[str, str, datetime, datetime]]:
        """(client_key, hash, received_at, asset created_at) ordered by key, after the cursor."""
        A, R = PhotoAssetRow, PhotoReceiptRow
        q = (
            select(R.client_key, R.blob_hash, R.received_at, A.created_at)
            .join(A, A.id == R.asset_id).where(R.source_id == source_id)
        )
        if after:
            q = q.where(R.client_key > after)
        with self.db.session() as s:
            return [
                (k, h, utc(rec), utc(created))
                for k, h, rec, created in s.execute(q.order_by(R.client_key).limit(limit))
            ]

    def record_snapshot(self, target_id: str, snapshot_id: str, started_at: datetime, completed_at: datetime,
                        verified_at: datetime | None = None) -> None:
        ins = self.db.insert()
        values = {"target_id": target_id, "snapshot_id": snapshot_id, "started_at": started_at, "completed_at": completed_at}
        if verified_at is not None:
            values["verified_at"] = verified_at
        with self.db.session.begin() as s:
            s.execute(
                ins(PhotoSnapshotRow).values(**values).on_conflict_do_nothing(
                    index_elements=[PhotoSnapshotRow.target_id, PhotoSnapshotRow.snapshot_id]
                )
            )
            if verified_at is not None:
                self._set_verified(s, target_id, snapshot_id, verified_at)

    def mark_verified(self, target_id: str, snapshot_id: str, at: datetime) -> bool:
        with self.db.session.begin() as s:
            return self._set_verified(s, target_id, snapshot_id, at)

    @staticmethod
    def _set_verified(s, target_id: str, snapshot_id: str, at: datetime) -> bool:
        S = PhotoSnapshotRow
        res = s.execute(
            update(S).where(S.target_id == target_id, S.snapshot_id == snapshot_id, S.verified_at.is_(None)).values(verified_at=at)
        )
        return bool(res.rowcount)

    def mark_removed(self, target_id: str, snapshot_ids: Iterable[str], at: datetime) -> None:
        S = PhotoSnapshotRow
        with self.db.session.begin() as s:
            s.execute(
                update(S).where(S.target_id == target_id, S.snapshot_id.in_(list(snapshot_ids)), S.removed_at.is_(None))
                .values(removed_at=at)
            )
