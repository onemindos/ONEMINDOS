# SPDX-License-Identifier: Apache-2.0
"""Search providers and the query path of GET /v1/search (#611).

A provider is the code that feeds one app's items into the one index. It is switched on by the app's
descriptor, never by itself: for each switched-on built-in whose descriptor has a `spec.search`
block, the provider registered under `spec.search.provider` is built (register_provider) and only
the item types that block declares are returned. A descriptor naming a provider nobody has
registered yet (Photos, Market today) is skipped; a provider no descriptor names never runs.

Every query: each active provider brings its rows up to date (a cheap cursor check when nothing
changed), then hits are read best first and each one is kept only when
- the app it belongs to is switched on and shared with the asker (gw.app_filters), and
- its provider says this asker may see it (Files: the asker's role or folder grants; Settings:
  the asker's scopes for the route the page reads).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..auth import Principal
from ..builtins import Builtins, Descriptor
from ..identity import scopes as sc
from ..sections import config_section
from .index import Item, SearchIndex, Writer, match_expression

log = logging.getLogger("onemind.search")

MAX_LIMIT = 100


@config_section("search")
@dataclass(frozen=True)
class SearchSettings:
    # The index file. None: $ONEMIND_DATA_DIR/cache/search/index.sqlite3, or the cache folder next to
    # the audit log when Settings was built in code. Under cache/: rebuildable, so never backed up.
    index_path: Path | None = None    # ONEMIND_SEARCH_INDEX_PATH

    @classmethod
    def from_env(cls, env) -> "SearchSettings":
        explicit = (env.get("ONEMIND_SEARCH_INDEX_PATH") or "").strip()
        if explicit:
            return cls(index_path=Path(explicit))
        data_dir = (env.get("ONEMIND_DATA_DIR") or "").strip()
        return cls(index_path=Path(data_dir) / "cache" / "search" / "index.sqlite3" if data_dir else None)


@dataclass(frozen=True)
class Asker:
    """Who is searching, as the providers need to know it."""

    principal: Principal
    # The identity scopes of a session or issued token; None for a tokens-file principal, which the
    # gateway does not check against the route scope table (contract v0 behaviour).
    scopes: frozenset[str] | None
    app_visible: Callable[[str], bool]

    def may_call(self, call: str) -> bool:
        """Whether the route scope table lets this asker call `METHOD /v1/path` (always, without scopes)."""
        if self.scopes is None:
            return True
        method, _, path = call.partition(" ")
        required = sc.required_scopes(method, path)
        return required is None or sc.has_any(self.scopes, required)


class Provider:
    """Base class of a search provider. One instance per (provider id, app) pair, kept across queries."""

    def __init__(self, descriptor: Descriptor):
        search = descriptor.spec["search"]
        self.id: str = search["provider"]
        self.app_id = descriptor.id
        self.types = frozenset(search["types"])

    def refresh(self, w: Writer) -> None:
        """Bring this provider's rows up to date. Called before every query, so make "nothing changed" cheap."""
        raise NotImplementedError

    def visible(self, asker: Asker) -> Callable[[Item], bool]:
        """A test for one hit, built once per query (load grants here, not per hit)."""
        raise NotImplementedError


# provider id -> factory(descriptor, app) -> Provider | None (None: what it needs is not mounted).
ProviderFactory = Callable[[Descriptor, Any], "Provider | None"]
_FACTORIES: dict[str, ProviderFactory] = {}


def register_provider(provider_id: str, factory: ProviderFactory) -> None:
    """Make `provider_id` available to descriptors that name it in spec.search.provider."""
    prev = _FACTORIES.get(provider_id)
    if prev is not None and prev is not factory:
        raise ValueError(f"search provider {provider_id!r} registered twice")
    _FACTORIES[provider_id] = factory


class SearchService:
    def __init__(self, index: SearchIndex, builtins: Builtins, app: Any):
        self.index = index
        self.builtins = builtins
        self.app = app
        self._built: dict[tuple[str, str], Provider | None] = {}

    def providers(self) -> list[Provider]:
        """The providers of the switched-on built-ins, in app id order."""
        out: list[Provider] = []
        for d in self.builtins.enabled():
            search = d.spec.get("search")
            if not search:
                continue
            if any(p.id == search["provider"] for p in out):  # one provider id, one app: the index is keyed by it
                log.warning("search: %s names provider %r, which another built-in already uses", d.id, search["provider"])
                continue
            k = (search["provider"], d.id)
            if k not in self._built:
                factory = _FACTORIES.get(search["provider"])
                self._built[k] = factory(d, self.app) if factory else None
                if self._built[k] is None:
                    log.info("search: no provider %r for %s yet; its items are not searchable", *k)
            if self._built[k] is not None:
                out.append(self._built[k])
        return out

    def refresh(self, providers: list[Provider]) -> None:
        for prov in providers:
            try:
                with self.index.writer(prov.id) as w:
                    prov.refresh(w)
            except Exception:  # one broken provider must not take search down: its last good rows stay
                log.exception("search: provider %s could not refresh", prov.id)

    def search(self, asker: Asker, q: str, *, types: frozenset[str] | None = None,
               limit: int = 20) -> tuple[list[Item], list[str]]:
        """(hits the asker may see, best first; the provider ids that were searched)."""
        limit = max(1, min(limit, MAX_LIMIT))
        providers = self.providers()
        enabled = {d.id for d in self.builtins.enabled()}
        visible_app: dict[str, bool] = {}

        def app_ok(app_id: str) -> bool:
            if app_id not in visible_app:
                visible_app[app_id] = app_id in enabled and asker.app_visible(app_id)
            return visible_app[app_id]

        live = [p for p in providers if app_ok(p.app_id)]
        expr = match_expression(q)
        if expr is None or not live:
            return [], [p.id for p in live]
        with self.index.lock:
            self.refresh(live)
        by_id = {p.id: p for p in live}
        tests = {p.id: p.visible(asker) for p in live}
        hits: list[Item] = []
        for item in self.index.matches(expr, list(by_id)):
            prov = by_id[item.provider]
            if item.type not in prov.types or (types and item.type not in types):
                continue
            if not app_ok(item.app_id) or not tests[item.provider](item):
                continue
            hits.append(item)
            if len(hits) >= limit:
                break
        return hits, [p.id for p in live]
