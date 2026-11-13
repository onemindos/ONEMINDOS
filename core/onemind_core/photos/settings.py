# SPDX-License-Identifier: Apache-2.0
"""Photos settings: ONEMIND_PHOTOS_* (docs/leap/core/PHOTOS.md §6)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..sections import config_section, env_name


@config_section("photos")
@dataclass(frozen=True)
class PhotosSettings:
    enabled: bool = False                      # ONEMIND_PHOTOS_ENABLED=1 turns the routes on
    dir: Path | None = None                    # ONEMIND_PHOTOS_DIR: library root, on Retain storage
    max_upload_bytes: int = 64 * 1024**3       # largest single file (also sent as Upload-Limit)
    upload_ttl_s: int = 7 * 24 * 3600          # an upload idle this long expires (410)
    read_timeout_s: float = 60.0               # a PATCH body that stalls this long is cut off
    reserve_bytes: int = 1024**3               # free space kept back on the library's filesystem
    max_open_uploads: int = 64                 # unfinished uploads per phone

    def validate(self) -> None:
        if self.enabled and self.dir is None:
            raise ValueError("ONEMIND_PHOTOS_DIR is required when ONEMIND_PHOTOS_ENABLED=1")
        for name in ("max_upload_bytes", "upload_ttl_s", "max_open_uploads"):
            if getattr(self, name) < 1:
                raise ValueError(f"{env_name('photos', name)} must be at least 1")
        if self.read_timeout_s <= 0:
            raise ValueError("ONEMIND_PHOTOS_READ_TIMEOUT_S must be positive")
        if self.reserve_bytes < 0:
            raise ValueError("ONEMIND_PHOTOS_RESERVE_BYTES must not be negative")
