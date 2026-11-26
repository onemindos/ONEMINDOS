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
from typing import Any

from fastapi import Request
from fastapi.routing import APIRoute

from .errors import ApiError

_SEQUENCES = (list, set, frozenset, tuple)
_ATTR = "_onemind_single_valued_query"


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


def one_value_per_query_parameter(request: Request) -> None:
    """A dependency on every route: 422 when a single-valued query parameter arrives more than once."""
    keys = [k for k, _ in request.query_params.multi_items()]
    if len(keys) == len(set(keys)):
        return
    route = request.scope.get("route")
    if not isinstance(route, APIRoute):
        return
    single = getattr(route, _ATTR, None)
    if single is None:  # worked out once per route, kept on the route itself
        single = _single_valued(route)
        setattr(route, _ATTR, single)
    repeated = sorted({k for k in keys if k in single and keys.count(k) > 1})
    if repeated:
        raise ApiError(422, "conflict", f"query parameter {repeated[0]!r} takes one value; it was sent more than once",
                       reason="invalid_request")
