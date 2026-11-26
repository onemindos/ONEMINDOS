# SPDX-License-Identifier: Apache-2.0
"""Request bodies that take each JSON value as the type /openapi.json gives it (api-fuzz ST201).

Pydantic's lax mode converts between JSON types: `0` became `false`, `false` became age 0 and
`"5"` became 5. The OpenAPI document forbids all three, so a client that sent them got a 200 for
a request the contract says is wrong (api-fuzz runs 44982704938 and 44984786513 found two). Strict
mode is not the answer either: JSON Schema's `integer` includes `3.0`, and `Field(strict=True)`
refuses it with a 422 the document does not allow (run 44984786513, PUT /v1/family/apps/{app_id}).

A request model derives from `JsonBody` instead of `BaseModel`. Before pydantic converts anything,
every field declared `bool`, `int` or `float` (also optional, or as list items) is checked against
the JSON type itself:

    bool    only true or false
    int     a JSON number (3 and 3.0; 3.5 is still refused by pydantic), never true/false or text
    float   a JSON number, never true/false or text

    date-time, date   a JSON string, never a number (pydantic's lax mode read 0 as 1970-01-01)

Nothing else changes: the generated schema, the constraints and the error envelope stay the same,
and a wrong type answers 422 like any other schema violation. `str` needs nothing: pydantic 2
already refuses a number where it expects text. Unions of several scalar types (an app's typed
`settings`) are left to pydantic's smart union, which keeps the value's own type.
"""

from __future__ import annotations

import datetime
import types
import typing
from collections.abc import Callable
from typing import Any, ClassVar

from pydantic import AwareDatetime, BaseModel, FutureDatetime, NaiveDatetime, PastDatetime, model_validator
from pydantic_core import PydanticCustomError

Check = Callable[[Any], tuple[str, Any] | None]  # None, or (the JSON type wanted, the offending value)


def _json_kind(v: Any) -> str:
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "string"
    return type(v).__name__


def _boolean(v: Any) -> tuple[str, Any] | None:
    # Anything else (an object, a list) is left for pydantic to refuse with its own message.
    return None if isinstance(v, bool) or not isinstance(v, (int, float, str)) else ("boolean", v)


def _number(kind: str) -> Check:
    return lambda v: (kind, v) if isinstance(v, (bool, str)) else None


def _text(v: Any) -> tuple[str, Any] | None:
    # A date-time is text in JSON: a number or a boolean is refused (objects and lists stay pydantic's).
    return ("string", v) if isinstance(v, (bool, int, float)) else None


_SCALARS: dict[type, Check] = {bool: _boolean, int: _number("integer"), float: _number("number"),
                               datetime.datetime: _text, datetime.date: _text, AwareDatetime: _text,
                               NaiveDatetime: _text, PastDatetime: _text, FutureDatetime: _text}


def scalar_check(annotation: Any) -> Check | None:
    """The check for one field's annotation, or None when the field takes no JSON scalar of its own."""
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin is typing.Annotated:
        return scalar_check(args[0])
    if origin in (typing.Union, types.UnionType):
        members = [a for a in args if a is not type(None)]
        if len(members) != 1:
            return None  # a real union: pydantic's smart mode keeps the value's own type
        inner = scalar_check(members[0])
        return None if inner is None else (lambda v: None if v is None else inner(v))
    if origin in (list, set, frozenset) and args:
        item = scalar_check(args[0])
        if item is None:
            return None
        return lambda v: next((e for e in map(item, v) if e), None) if isinstance(v, list) else None
    return _SCALARS.get(annotation) if isinstance(annotation, type) else None


class JsonBody(BaseModel):
    """A request body whose booleans and numbers must arrive as JSON booleans and numbers."""

    __json_checks__: ClassVar[dict[str, tuple[str, Check]]] = {}

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        checks: dict[str, tuple[str, Check]] = {}
        for name, field in cls.model_fields.items():
            if (check := scalar_check(field.annotation)) is None:
                continue
            keys = {name, field.alias or name}
            if isinstance(field.validation_alias, str):
                keys.add(field.validation_alias)
            for key in keys:
                checks[key] = (name, check)
        cls.__json_checks__ = checks

    @model_validator(mode="before")
    @classmethod
    def _json_types(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for key, (name, check) in cls.__json_checks__.items():
                if key in data and (bad := check(data[key])) is not None:
                    raise PydanticCustomError(
                        "json_type", "{field} should be a JSON {want}, not a {got}",
                        {"field": name, "want": bad[0], "got": _json_kind(bad[1])},
                    )
        return data
