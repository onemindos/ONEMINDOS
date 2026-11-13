# SPDX-License-Identifier: Apache-2.0
"""FILES: per-person spaces and the household Shared folder on /data, as a core service.

Design: docs/umbrel2/files-backups.md §4 (on main). API for clients: docs/leap/core/FILES.md.
Modules: settings (ONEMIND_FILES_*), paths (confined path handling), store (tables), access
(who may read or write what), preview (metadata), service (browse, ops, trash, quotas, grants),
uploads (tus 1.0 resumable uploads with digest checks). Routes: routers/files.py.
"""

from .errors import FilesError
from .service import FilesService
from .settings import FilesSettings

__all__ = ["FilesError", "FilesService", "FilesSettings"]
