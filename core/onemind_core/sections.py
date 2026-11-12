# SPDX-License-Identifier: Apache-2.0
"""Per-feature settings sections, loaded from ONEMIND_<SECTION>_<FIELD> (docs/leap/core/PLUMBING.md §4).

A feature declares a frozen dataclass and registers it:

    @config_section("notify")
    @dataclass(frozen=True)
    class NotifySettings:
        enabled: bool = False          # ONEMIND_NOTIFY_ENABLED
        ntfy_url: str | None = None    # ONEMIND_NOTIFY_NTFY_URL
        retry_s: float = 30.0          # ONEMIND_NOTIFY_RETRY_S

        def validate(self) -> None:    # optional; raise ValueError to refuse startup
            ...

`Settings.from_env` loads every registered section; the feature reads it with
`gw.settings.section(NotifySettings)`. Supported field types: str, int, float, bool, Path,
tuple[str, ...] (comma separated) and `X | None` of those (empty value = None). A field with no
default is required. A class may define `from_env(cls, env)` instead to parse by hand.
"""

from __future__ import annotations

import dataclasses
import re
import types
import typing
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypeVar

SECTION_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
TRUE = ("1", "true", "yes", "on")
FALSE = ("0", "false", "no", "off")

T = TypeVar("T")

_SECTIONS: dict[str, type] = {}


def config_section(name: str):
    """Class decorator: register a settings dataclass under `name` (env prefix ONEMIND_<NAME>_)."""
    if not SECTION_RE.match(name):
        raise ValueError(f"section name {name!r} must match {SECTION_RE.pattern}")

    def deco(cls: type[T]) -> type[T]:
        if not dataclasses.is_dataclass(cls):
            raise TypeError(f"{cls.__name__} must be a dataclass")
        prev = _SECTIONS.get(name)
        if prev is not None and prev.__qualname__ != cls.__qualname__:
            raise ValueError(f"settings section {name!r} registered twice ({prev.__qualname__}, {cls.__qualname__})")
        _SECTIONS[name] = cls
        cls.__onemind_section__ = name  # type: ignore[attr-defined]
        return cls

    return deco


def section_name(cls: type) -> str:
    try:
        return cls.__onemind_section__  # type: ignore[attr-defined]
    except AttributeError:
        raise TypeError(f"{cls.__name__} is not registered with @config_section") from None


def env_name(section: str, field_name: str) -> str:
    return f"ONEMIND_{section.upper()}_{field_name.upper()}"


def _coerce(value: str, typ: Any, var: str) -> Any:
    origin = typing.get_origin(typ)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(typ) if a is not type(None)]
        if value.strip() == "":
            return None
        if len(args) != 1:
            raise TypeError(f"{var}: unsupported type {typ!r}")
        return _coerce(value, args[0], var)
    if origin is tuple:
        return tuple(v.strip() for v in value.split(",") if v.strip())
    try:
        if typ is bool:
            v = value.strip().lower()
            if v in TRUE:
                return True
            if v in FALSE:
                return False
            raise ValueError
        if typ is int:
            return int(value)
        if typ is float:
            return float(value)
    except ValueError:
        raise ValueError(f"{var} must be a {typ.__name__}, got {value!r}") from None
    if typ is Path:
        return Path(value)
    if typ is str:
        return value
    raise TypeError(f"{var}: unsupported type {typ!r}")


def load_section(cls: type[T], env: Mapping[str, str]) -> T:
    name = section_name(cls)
    custom = cls.__dict__.get("from_env")
    if custom is not None:
        obj = cls.from_env(env)  # type: ignore[attr-defined]
    else:
        hints = typing.get_type_hints(cls)
        kwargs: dict[str, Any] = {}
        for f in dataclasses.fields(cls):
            if not f.init:
                continue
            var = env_name(name, f.name)
            if var in env:
                kwargs[f.name] = _coerce(env[var], hints[f.name], var)
            elif f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
                raise ValueError(f"{var} is required")
        obj = cls(**kwargs)
    validate = getattr(obj, "validate", None)
    if callable(validate):
        validate()
    return obj


def load_sections(env: Mapping[str, str]) -> dict[str, Any]:
    """Every registered section, parsed from env. Raises ValueError on a bad or missing value."""
    return {name: load_section(cls, env) for name, cls in sorted(_SECTIONS.items())}


def registered_sections() -> dict[str, type]:
    return dict(_SECTIONS)
