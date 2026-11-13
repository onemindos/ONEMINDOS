# SPDX-License-Identifier: Apache-2.0
"""OneMind Photos, box side of phone photo backup (docs/leap/core/PHOTOS.md).

Importing this package registers the "photos" tables, schema chain and settings section.
"""

from .db import SCHEMA, PhotosRepository
from .service import LEVELS, MAX_CHECK, PHOTOS_UNIT, PhotosError, PhotosService, new_id
from .settings import PhotosSettings

__all__ = [
    "LEVELS", "MAX_CHECK", "PHOTOS_UNIT", "SCHEMA", "PhotosError", "PhotosRepository", "PhotosService",
    "PhotosSettings", "new_id",
]
