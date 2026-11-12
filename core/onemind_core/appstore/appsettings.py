# SPDX-License-Identifier: Apache-2.0
"""App settings (contract §12.22, PD-09): `spec.settings` fields and their values.

Each field is a small JSON Schema subset (type, enum, minimum/maximum, minLength/maxLength,
pattern) plus the environment variable it is delivered as. The dashboard renders the fields as
a form; saving files one `app.configure` request with the changed values. The gateway checks the
values when the request is filed and again at approval (the manifest may have moved), then
writes ConfigMap `onemind-settings` in `app-<id>`.

Settings are not secret: they are stored in the action ledger and the audit log. A field whose
name or variable looks like a credential is refused; credentials go through `spec.secrets`.

A manifest (official or from a community source) is untrusted input here, and Python's `re`
backtracks without a time limit, so `pattern` is limited to a shape that cannot blow up: no
quantified groups (other than `?`), no back-references or lookarounds, at most two unbounded
quantifiers, and values matched against a pattern are at most 256 characters.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,62}$")
SECRETISH_RE = re.compile(r"(password|secret|token|api_?key|apikey|private_?key)", re.IGNORECASE)
TYPES = {
    "string": "string", "integer": "integer", "number": "number", "boolean": "boolean",
    "int": "integer", "bool": "boolean", "enum": "string",  # §12.18 aliases
}
FIELD_KEYS = frozenset({
    "name", "env", "type", "title", "description", "default", "enum", "minimum", "maximum",
    "minLength", "maxLength", "pattern", "restart",
})
MAX_FIELDS = 50
MAX_STRING = 4096
MAX_PATTERN = 200
MAX_PATTERN_VALUE = 256
MAX_UNBOUNDED = 2
MAX_ENUM = 100
_BRACE = re.compile(r"\{(\d{1,4})(,(\d{0,4}))?\}")
# Control characters other than tab and newline never belong in an environment value.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class SettingsSchemaError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class SettingField:
    name: str
    env: str
    type: str  # string | integer | number | boolean
    title: str | None = None
    description: str | None = None
    default: Any = None
    enum: tuple | None = None
    minimum: float | None = None
    maximum: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    restart: bool = True

    def to_json(self) -> dict:
        out: dict[str, Any] = {"name": self.name, "env": self.env, "type": self.type}
        for key, value in (
            ("title", self.title), ("description", self.description), ("default", self.default),
            ("enum", list(self.enum) if self.enum is not None else None), ("minimum", self.minimum),
            ("maximum", self.maximum), ("minLength", self.min_length), ("maxLength", self.max_length),
            ("pattern", self.pattern),
        ):
            if value is not None:
                out[key] = value
        out["restart"] = self.restart
        return out

    def problem(self, value: Any) -> str | None:
        """Why value is not acceptable for this field, or None."""
        t = self.type
        if t == "boolean":
            if not isinstance(value, bool):
                return f"{self.name}: must be true or false"
        elif t == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                return f"{self.name}: must be an integer"
        elif t == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                return f"{self.name}: must be a finite number"
        elif t == "string":
            if not isinstance(value, str):
                return f"{self.name}: must be a string"
            if len(value) > MAX_STRING:
                return f"{self.name}: at most {MAX_STRING} characters"
            if _CONTROL.search(value):
                return f"{self.name}: control characters are not allowed"
        if self.enum is not None and value not in self.enum:
            return f"{self.name}: must be one of {list(self.enum)}"
        if t in ("integer", "number"):
            if self.minimum is not None and value < self.minimum:
                return f"{self.name}: must be at least {self.minimum}"
            if self.maximum is not None and value > self.maximum:
                return f"{self.name}: must be at most {self.maximum}"
        if t == "string":
            if self.min_length is not None and len(value) < self.min_length:
                return f"{self.name}: at least {self.min_length} characters"
            if self.max_length is not None and len(value) > self.max_length:
                return f"{self.name}: at most {self.max_length} characters"
            if self.pattern is not None:
                if len(value) > MAX_PATTERN_VALUE:
                    return f"{self.name}: at most {MAX_PATTERN_VALUE} characters for a field with a pattern"
                if re.fullmatch(self.pattern, value) is None:
                    return f"{self.name}: does not match the pattern {self.pattern!r}"
        return None


def pattern_risk(pattern: str) -> str | None:
    """Why a pattern could backtrack catastrophically, or None for the allowed safe subset."""
    unbounded = 0
    i, n, in_class, prev = 0, len(pattern), False, ""
    while i < n:
        ch = pattern[i]
        if ch == "\\":
            nxt = pattern[i + 1:i + 2]
            if not in_class and nxt.isdigit() and nxt != "0":
                return "uses a back-reference"
            prev, i = "atom", i + 2
            continue
        if in_class:
            in_class = ch != "]" or prev == "class-open"
            prev = "class" if in_class else "atom"
            i += 1
            continue
        if ch == "[":
            in_class, prev = True, "class-open"
            if pattern[i + 1:i + 2] == "^":
                i += 1
            i += 1
            continue
        if ch == "(":
            if pattern.startswith("(?", i) and not pattern.startswith("(?:", i):
                return "uses a lookaround, flag or named group"
            prev = "open"
        elif ch == ")":
            prev = "group"
        elif ch in "*+" or (ch == "{" and _BRACE.match(pattern, i)):
            m = _BRACE.match(pattern, i) if ch == "{" else None
            # {n} is a fixed count; {n,} and {n,m} with a large m count as unbounded.
            big = m is None or (m.group(2) is not None and (m.group(3) == "" or int(m.group(3)) > 32))
            if prev == "group":
                return "quantifies a group"
            if big:
                unbounded += 1
                if unbounded > MAX_UNBOUNDED:
                    return f"has more than {MAX_UNBOUNDED} unbounded quantifiers"
            if m is not None:
                i = m.end()
                prev = "quant"
                continue
            prev = "quant"
        else:
            prev = "atom" if ch != "|" else "alt"
        i += 1
    return None


def _num(raw: dict, key: str, where: str, problems: list[str]) -> float | None:
    v = raw.get(key)
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        problems.append(f"{where}.{key} must be a number")
        return None
    return v


def _int(raw: dict, key: str, where: str, problems: list[str]) -> int | None:
    v = raw.get(key)
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= MAX_STRING:
        problems.append(f"{where}.{key} must be an integer 0-{MAX_STRING}")
        return None
    return v


def _field(raw: object, i: int, problems: list[str]) -> SettingField | None:
    where = f"spec.settings[{i}]"
    if not isinstance(raw, dict):
        problems.append(f"{where} must be a mapping")
        return None
    unknown = sorted(set(raw) - FIELD_KEYS)
    if unknown:
        problems.append(f"{where}: unknown keys {unknown}")
    name, env, typ = raw.get("name"), raw.get("env"), raw.get("type")
    before = len(problems)
    if not isinstance(name, str) or not NAME_RE.match(name):
        problems.append(f"{where}.name must match {NAME_RE.pattern}")
    if not isinstance(env, str) or not ENV_RE.match(env):
        problems.append(f"{where}.env must match {ENV_RE.pattern}")
    for key, value in (("name", name), ("env", env)):
        if isinstance(value, str) and SECRETISH_RE.search(value):
            problems.append(f"{where}.{key} {value!r} looks like a credential; settings are not secret (use spec.secrets)")
    if typ not in TYPES:
        problems.append(f"{where}.type must be one of {sorted(TYPES)}")
    for key in ("title", "description"):
        v = raw.get(key)
        if v is not None and (not isinstance(v, str) or not 0 < len(v) <= (80 if key == "title" else 300)):
            problems.append(f"{where}.{key} must be a non-empty string ({80 if key == 'title' else 300} max)")
    restart = raw.get("restart", True)
    if not isinstance(restart, bool):
        problems.append(f"{where}.restart must be true or false")
    enum = raw.get("enum")
    if enum is not None and (
        not isinstance(enum, list) or not 0 < len(enum) <= MAX_ENUM
        or any(isinstance(e, (bool, dict, list)) or e is None for e in enum)
        or len({repr(e) for e in enum}) != len(enum)
    ):
        problems.append(f"{where}.enum must be 1-{MAX_ENUM} distinct strings or numbers")
        enum = None
    if typ == "enum" and enum is None:
        problems.append(f"{where}: type enum needs an enum list")
    pattern = raw.get("pattern")
    if pattern is not None:
        if not isinstance(pattern, str) or not 0 < len(pattern) <= MAX_PATTERN:
            problems.append(f"{where}.pattern must be a string of at most {MAX_PATTERN} characters")
            pattern = None
        elif (why := pattern_risk(pattern)) is not None:
            problems.append(f"{where}.pattern {why} (catastrophic backtracking); simplify it")
            pattern = None
        else:
            try:
                re.compile(pattern)
            except re.error:
                problems.append(f"{where}.pattern is not a valid regular expression")
                pattern = None
    minimum, maximum = _num(raw, "minimum", where, problems), _num(raw, "maximum", where, problems)
    min_len, max_len = _int(raw, "minLength", where, problems), _int(raw, "maxLength", where, problems)
    if len(problems) > before:
        return None
    field = SettingField(
        name=name, env=env, type=TYPES[typ], title=raw.get("title"), description=raw.get("description"),
        default=raw.get("default"), enum=tuple(enum) if enum is not None else None, minimum=minimum,
        maximum=maximum, min_length=min_len, max_length=max_len, pattern=pattern, restart=restart,
    )
    if field.type == "boolean" and (field.enum or pattern or min_len is not None or max_len is not None):
        problems.append(f"{where}: a boolean takes no enum, pattern or length")
        return None
    if field.enum is not None and any(field.problem(e) for e in field.enum if not isinstance(e, bool)):
        problems.append(f"{where}.enum values must fit the field's type")
        return None
    if field.default is not None and (p := field.problem(field.default)):
        problems.append(f"{where}.default does not fit the field ({p})")
        return None
    return field


def parse_fields(manifest: dict) -> list[SettingField]:
    """The app's settings fields; raises SettingsSchemaError listing every problem."""
    spec = manifest.get("spec") if isinstance(manifest, dict) else None
    raw = spec.get("settings") if isinstance(spec, dict) else None
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_FIELDS:
        raise SettingsSchemaError([f"spec.settings must be a list of at most {MAX_FIELDS} fields"])
    problems: list[str] = []
    fields = [f for i, r in enumerate(raw) if (f := _field(r, i, problems)) is not None]
    for attr in ("name", "env"):
        seen: set[str] = set()
        for f in fields:
            value = getattr(f, attr)
            if value in seen:
                problems.append(f"spec.settings: duplicate {attr} {value!r}")
            seen.add(value)
    if problems:
        raise SettingsSchemaError(problems)
    return fields


def value_problems(fields: list[SettingField], values: object) -> list[str]:
    """Problems with a partial {name: value} map (what an app.configure request carries)."""
    if not isinstance(values, dict) or not values:
        return ["settings must be a non-empty mapping of setting names to values"]
    by_name = {f.name: f for f in fields}
    problems = [f"{k}: no such setting" for k in values if k not in by_name]
    problems += [p for k, v in values.items() if k in by_name and (p := by_name[k].problem(v))]
    return problems


def effective(fields: list[SettingField], stored: dict) -> dict:
    """Defaults overlaid with stored values that still fit the current fields."""
    out: dict[str, Any] = {}
    for f in fields:
        v = stored.get(f.name, f.default)
        if v is not None and f.problem(v) is None:
            out[f.name] = v
        elif f.default is not None:
            out[f.name] = f.default
    return out


def env_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def configmap_data(fields: list[SettingField], values: dict) -> dict[str, str]:
    """ConfigMap onemind-settings data: env name -> string value, for every field with a value."""
    return {f.env: env_value(values[f.name]) for f in fields if f.name in values}


def needs_restart(fields: list[SettingField], changed: dict) -> bool:
    return any(f.restart for f in fields if f.name in changed)
