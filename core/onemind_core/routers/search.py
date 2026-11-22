# SPDX-License-Identifier: Apache-2.0
"""GET /v1/search: one query over the local search index (search/, #611).

Any signed-in caller may search; what comes back is filtered per hit by the caller's own grants
(search/service.py), so the route needs no scope of its own. The query text is never logged or
audited: an agent's search is audited with its length and hit count only.

After FILES (ORDER 300), whose service the Files provider reads, and the built-in registry (135),
whose descriptors switch providers on.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope
from ..identity.service import ctx_of
from ..search import Asker, SearchIndex, SearchService, SearchSettings, SearchUnavailable
from ..search import providers as _providers  # noqa: F401  (registers the files and settings providers)

ORDER = 310
TYPES_RE = r"^[a-z][a-z0-9_.-]{0,62}(,[a-z][a-z0-9_.-]{0,62}){0,19}$"

register_route_scope("GET,HEAD", r"/v1/search", None)


class SearchHit(BaseModel):
    provider: str           # the descriptor's spec.search.provider
    app_id: str             # the app the item belongs to
    type: str               # one of that provider's spec.search.types
    id: str                 # unique within the provider
    title: str
    subtitle: str | None = None
    link: str               # deep link that opens the item: onemind://app/<app id>/<route>


class SearchOut(BaseModel):
    hits: list[SearchHit]
    providers: list[str]    # the providers searched: those of switched-on built-ins shared with the caller


def register(app: FastAPI, gw: Gateway) -> None:
    cfg = gw.settings.section(SearchSettings)
    path = cfg.index_path or gw.settings.audit_path.parent / "cache" / "search" / "index.sqlite3"
    index = SearchIndex(path)
    svc = SearchService(index, app.state.builtins, app)
    app.state.search = svc
    gw.on_shutdown(index.close)

    @app.get("/v1/search", operation_id="search.query", tags=["search"], response_model=SearchOut,
             responses=error_responses(401, 422, 503))
    async def search(request: Request,
                     q: str = Query(min_length=1, max_length=200, description="free text; every word must match"),
                     types: str | None = Query(None, max_length=1300, pattern=TYPES_RE,
                                               description="comma-separated item types, e.g. file,folder"),
                     limit: int = Query(20, ge=1, le=100),
                     p: Principal = Depends(gw.principal)):
        """Search every switched-on built-in's items at once. Each hit carries a deep link that
        opens the exact item, and only hits the caller may open are returned."""
        ctx = ctx_of(request)
        asker = Asker(p, frozenset(ctx.scopes) if ctx is not None else None,
                      lambda app_id: all(f(request, p, app_id) for f in gw.app_filters))
        wanted = frozenset(types.split(",")) if types else None
        try:
            hits, searched = await run_in_threadpool(svc.search, asker, q, types=wanted, limit=limit)
        except SearchUnavailable as exc:
            raise ApiError(503, "unavailable", f"search is not available: {exc}", reason="search_unavailable") from None
        if p.kind != "person":
            gw.audit.append("search.query", p.as_dict(), None,
                            {"q_chars": len(q), "hits": len(hits), "providers": searched})
        return SearchOut(hits=[SearchHit(provider=h.provider, app_id=h.app_id, type=h.type, id=h.id, title=h.title,
                                         subtitle=h.subtitle, link=h.link) for h in hits], providers=searched)
