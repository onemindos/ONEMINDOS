# SPDX-License-Identifier: Apache-2.0
"""FILES settings: ONEMIND_FILES_<FIELD> (docs/leap/core/PLUMBING.md §4)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..sections import config_section

GIB = 1024**3
MIB = 1024**2


@config_section("files")
@dataclass(frozen=True)
class FilesSettings:
    # Where the spaces live on the box: <root>/home/<person>, <root>/shared, <root>/.system.
    root: Path = Path("/data/onemind/files")          # ONEMIND_FILES_ROOT
    # Per-person quota when the owner set none; 0 = no limit.
    default_quota_bytes: int = 0                      # ONEMIND_FILES_DEFAULT_QUOTA_BYTES
    # Limit for the household Shared folder; 0 = no limit.
    shared_quota_bytes: int = 0                       # ONEMIND_FILES_SHARED_QUOTA_BYTES
    # Space an upload, move or restore must leave free on the disk.
    min_free_bytes: int = 256 * MIB                   # ONEMIND_FILES_MIN_FREE_BYTES
    trash_retention_days: int = 30                    # ONEMIND_FILES_TRASH_RETENTION_DAYS
    upload_max_bytes: int = 64 * GIB                  # ONEMIND_FILES_UPLOAD_MAX_BYTES
    # Largest PATCH body; clients send bigger files in several chunks.
    chunk_max_bytes: int = 64 * MIB                   # ONEMIND_FILES_CHUNK_MAX_BYTES
    upload_expiry_hours: int = 24                     # ONEMIND_FILES_UPLOAD_EXPIRY_HOURS
    # Unfinished uploads one principal may hold at once (each reserves quota and a partial file).
    max_open_uploads: int = 16                        # ONEMIND_FILES_MAX_OPEN_UPLOADS
    # Bytes of a text file returned inline by the preview endpoint.
    preview_text_bytes: int = 64 * 1024               # ONEMIND_FILES_PREVIEW_TEXT_BYTES

    def validate(self) -> None:
        if not self.root.is_absolute():
            raise ValueError("ONEMIND_FILES_ROOT must be an absolute path")
        for name in ("default_quota_bytes", "shared_quota_bytes", "min_free_bytes"):
            if getattr(self, name) < 0:
                raise ValueError(f"ONEMIND_FILES_{name.upper()} must not be negative")
        if self.trash_retention_days < 1:
            raise ValueError("ONEMIND_FILES_TRASH_RETENTION_DAYS must be at least 1")
        if self.upload_max_bytes < 1 or self.chunk_max_bytes < 1:
            raise ValueError("ONEMIND_FILES_UPLOAD_MAX_BYTES and _CHUNK_MAX_BYTES must be positive")
        if self.max_open_uploads < 1:
            raise ValueError("ONEMIND_FILES_MAX_OPEN_UPLOADS must be at least 1")
        if not 1 <= self.upload_expiry_hours <= 24 * 7:
            raise ValueError("ONEMIND_FILES_UPLOAD_EXPIRY_HOURS must be between 1 and 168")
        if not 0 <= self.preview_text_bytes <= MIB:
            raise ValueError("ONEMIND_FILES_PREVIEW_TEXT_BYTES must be between 0 and 1 MiB")
