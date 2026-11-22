# SPDX-License-Identifier: Apache-2.0
"""OneMind Work, the work engine: projects, tasks and events people and AI agents share.

Importing this package registers the "work" tables and schema chain.
"""

from .db import SCHEMA, WorkRepository
from .service import WorkError, WorkService, new_id

__all__ = ["SCHEMA", "WorkError", "WorkRepository", "WorkService", "new_id"]
