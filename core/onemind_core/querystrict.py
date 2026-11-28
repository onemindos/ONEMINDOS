# SPDX-License-Identifier: Apache-2.0
"""One value per single-valued query parameter (api-fuzz ST201 on GET /v1/audit/verify).

FastAPI reads a repeated query parameter that the route declares as a single value (`int`, `str`, an
enum) by taking the last copy and ignoring the rest, so `?from_seq=t&from_seq=5` answered 200 for a
request the OpenAPI document does not allow. Two copies of one value are ambiguous: a proxy, a cache
or an audit line may read the first while the handler reads the last. The gateway now refuses them
with 422 `invalid_request`. Parameters declared as lists (`?types=a&types=b`) are unchanged, and so
are query keys a route does not declare (it ignores them either way).
"""

from __future__ import annotations

import types
import typing
from collections import Counter
from typing import Any

from fastapi.routing import APIRoute
from starlette.requests import HTTPConnection

from .errors import ApiError

_SEQUENCES = (list, set, frozenset, tuple)
_ATTR = "_onemind_single_valued_query"
_AUTH_CACHE = "_onemind_authenticates"
AUTH_ATTR = "_onemind_runs_query_guard"  # set on the principal dependency, which calls the check itself


def _is_sequence(annotation: Any) -> bool:
    origin = typing.get_origin(annotation)
    if origin is typing.Annotated:
        return _is_sequence(typing.get_args(annotation)[0])
    if origin in (typing.Union, types.UnionType):
        return any(_is_sequence(a) for a in typing.get_args(annotation) if a is not type(None))
    return origin in _SEQUENCES or annotation in _SEQUENCES


def _single_valued(route: APIRoute) -> frozenset[str]:
    """The query keys the route (and its dependencies) declare as a single value."""
    names: set[str] = set()
    stack = [route.dependant]
    while stack:
        dependant = stack.pop()
        names.update(f.alias for f in dependant.query_params if not _is_sequence(f.field_info.annotation))
        stack.extend(dependant.dependencies)
    return frozenset(names)


def _authenticates(route: APIRoute) -> bool:
    """True when the route depends on the gateway's principal dependency, which runs the check itself
    once the caller is authenticated (an unauthenticated caller gets 401, not a validation answer)."""
    stack = [route.dependant]
    while stack:
        dependant = stack.pop()
        if getattr(dependant.call, AUTH_ATTR, False):
            return True
        stack.extend(dependant.dependencies)
    return False


def refuse_repeated_query_parameters(request: HTTPConnection) -> None:
    """422 when a single-valued query parameter arrives more than once (WebSocket routes are left alone)."""
    counts = Counter(k for k, _ in request.query_params.multi_items())
    if all(n == 1 for n in counts.values()):
        return
    route = request.scope.get("route")
    if not isinstance(route, APIRoute):
        return
    single = getattr(route, _ATTR, None)
    if single is None:  # worked out once per route, kept on the route itself
        single = _single_valued(route)
        setattr(route, _ATTR, single)
    repeated = sorted(k for k, n in counts.items() if n > 1 and k in single)
    if repeated:
        raise ApiError(422, "conflict", f"query parameter {repeated[0]!r} takes one value; it was sent more than once",
                       reason="invalid_request")


def one_value_per_query_parameter(request: HTTPConnection) -> None:
    """The app-level dependency. Routes behind the principal dependency are checked there, after
    authentication; this covers the routes with no authentication (health, setup, tokens in the body).
    HTTPConnection, not Request, so it also resolves on WebSocket routes."""
    route = request.scope.get("route")
    if isinstance(route, APIRoute):
        authed = getattr(route, _AUTH_CACHE, None)
        if authed is None:
            authed = _authenticates(route)
            setattr(route, _AUTH_CACHE, authed)
        if authed:
            return
    refuse_repeated_query_parameters(request)
