# SPDX-License-Identifier: Apache-2.0
"""Photos settings: ONEMIND_PHOTOS_* (docs/leap/core/PHOTOS.md §6).

Photos is built in and ON by default (founder, 2026-11-21, refs #1232, #234). The library lives in
`<ONEMIND_DATA_DIR>/photos` unless ONEMIND_PHOTOS_DIR says otherwise. ONEMIND_PHOTOS_ENABLED=0 is the
operator's hard off. The owner's own switch is the built-in app switch (app.disable / app.enable,
approved in the queue), shown by GET /v1/settings/photos.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..sections import config_section, env_name, parse_fields


@config_section("photos")
@dataclass(frozen=True)
class PhotosSettings:
    enabled: bool = True                       # ONEMIND_PHOTOS_ENABLED=0 turns the routes off for good
    dir: Path | None = None                    # ONEMIND_PHOTOS_DIR: library root; default <ONEMIND_DATA_DIR>/photos
    max_upload_bytes: int = 64 * 1024**3       # largest single file (also sent as Upload-Limit)
    upload_ttl_s: int = 7 * 24 * 3600          # an upload idle this long expires (410)
    read_timeout_s: float = 60.0               # a PATCH body that stalls this long is cut off
    reserve_bytes: int = 1024**3               # free space kept back on the library's filesystem
    max_open_uploads: int = 64                 # unfinished uploads per phone

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "PhotosSettings":
        s = parse_fields(cls, env)
        if s.dir is None:
            s = cls(**{**s.__dict__, "dir": Path(env.get("ONEMIND_DATA_DIR", "./data")) / "photos"})
        return s

    @property
    def active(self) -> bool:
        """On and with a library folder: the only state in which a route may touch the disk."""
        return self.enabled and self.dir is not None

    def validate(self) -> None:
        for name in ("max_upload_bytes", "upload_ttl_s", "max_open_uploads"):
            if getattr(self, name) < 1:
                raise ValueError(f"{env_name('photos', name)} must be at least 1")
        if self.read_timeout_s <= 0:
            raise ValueError("ONEMIND_PHOTOS_READ_TIMEOUT_S must be positive")
        if self.reserve_bytes < 0:
            raise ValueError("ONEMIND_PHOTOS_RESERVE_BYTES must not be negative")
