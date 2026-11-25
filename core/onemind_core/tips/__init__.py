# SPDX-License-Identifier: Apache-2.0
"""OneMind Tips, the built-in that serves the tips pack shipped in the image (#669).

Importing this package registers the "tips" table, schema chain and settings section.
pack.py holds the pack format and its signature check; service.py the role filter and dismiss state.
"""

from .pack import Loaded, Pack, PackRefused, Tip, load_first, load_key, parse_version, read_pack, running_version
from .service import SCHEMA, STATES, TipsRepository, TipsService, TipsSettings

__all__ = [
    "SCHEMA", "STATES", "Loaded", "Pack", "PackRefused", "Tip", "TipsRepository", "TipsService", "TipsSettings",
    "load_first", "load_key", "parse_version", "read_pack", "running_version",
]
