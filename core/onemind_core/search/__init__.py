# SPDX-License-Identifier: Apache-2.0
"""Global search: one local SQLite FTS5 index fed by providers that descriptors switch on (#611).

index.py      the index file (a rebuildable cache on the box) and the Item and Writer types.
service.py    Provider, register_provider, Asker and the query path of GET /v1/search.
providers.py  the first two providers: files and settings.
"""

from .index import Item, SearchIndex, SearchUnavailable, Writer
from .service import Asker, Provider, SearchPage, SearchService, SearchSettings, register_provider

__all__ = ["Asker", "Item", "Provider", "SearchIndex", "SearchPage", "SearchService", "SearchSettings", "SearchUnavailable",
           "Writer", "register_provider"]
