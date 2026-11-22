# SPDX-License-Identifier: Apache-2.0
"""The one NATS subject tree (issue #600): load sdk/schema/onemind.subjects.json and check subjects against it.

Every message on the bus has a dotted address (a *subject*) of the shape
`onemind.<kind>.<scope>.<id>.<field>`. The first token after `onemind` is the *kind*; it decides
who may publish, which JetStream stream keeps it and which envelope schema its payload follows.
The registry file is the contract; this module only reads it, so the gateway, the lint
(sdk/tools/subject-lint) and Go (sdk/schema/embed.go) can never disagree.

`check(subject, publisher, owner_id)` answers "may this publisher send on this subject?" with a
reason a person can read. Core kinds (audit, event, asset ...) belong to the gateway alone, a node
may only name its own node id and an app only its own app id, so no plugin can name a core subject.
`covers(filter)` answers "is anything registered under this subscription filter?" for the lint.
`envelope_problems(envelope_id, obj)` validates a payload, with plain reasons for positions.
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

REGISTRY_FILE = "onemind.subjects.json"
PUBLISHERS = ("gateway", "node", "app", "agent")
MAX_SUBJECT_LEN = 255
MAX_ENVELOPE_BYTES = 16 * 1024
_PLACEHOLDER = re.compile(r"^\{([a-z_]+):([a-z_]+)\}$")
_TOKEN_CHARS = re.compile(r"^[A-Za-z0-9_-]+$")

_SCHEMA_DIR_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "sdk" / "schema",   # the repo
    Path("/usr/lib/onemind/sdk/schema"),                       # the OS image (os/rootfs/Containerfile)
    Path("/opt/onemind/sdk/schema"),                           # the gateway container (core/Dockerfile)
)


class RegistryError(RuntimeError):
    """The registry file is missing or malformed: callers fail closed."""


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reason: str
    kind: str | None = None
    pattern: str | None = None


@dataclass(frozen=True)
class Slot:
    literal: str | None = None
    name: str | None = None
    re: re.Pattern | None = None
    enum: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()
    lo: int = 1
    hi: int = 1

    def accepts(self, token: str) -> bool:
        if self.literal is not None:
            return token == self.literal
        if token in self.deny:
            return False
        if self.enum:
            return token in self.enum
        return bool(self.re and self.re.match(token))


@dataclass(frozen=True)
class Pattern:
    kind: str
    text: str
    slots: tuple[Slot, ...]
    publishers: tuple[str, ...]
    owner: str | None
    stream: str | None
    retention: dict
    envelope: str

    def bind(self, tokens: list[str]) -> dict[str, list[str]] | None:
        """Placeholder values when `tokens` is a concrete subject of this pattern, else None."""
        return _bind(self.slots, tokens, 0, {})


def _bind(slots, tokens, i, out):
    if not slots:
        return out if i == len(tokens) else None
    s, rest = slots[0], slots[1:]
    for n in range(s.lo, s.hi + 1):
        part = tokens[i:i + n]
        if len(part) < n or not all(s.accepts(t) for t in part):
            break
        got = _bind(rest, tokens, i + n, {**out, s.name: part} if s.name else out)
        if got is not None:
            return got
    return None


def _overlaps(slots, tokens, i) -> bool:
    """True when the filter tokens[i:] (with * and >) can match some subject of `slots`."""
    if not slots:
        return i == len(tokens)
    if i < len(tokens) and tokens[i] == ">":
        return True  # '>' takes one or more tokens, and every remaining slot holds at least one
    s, rest = slots[0], slots[1:]
    for n in range(s.lo, s.hi + 1):
        for j in range(n):
            if i + j >= len(tokens):
                return False
            t = tokens[i + j]
            if t == ">":
                return True
            if t != "*" and not s.accepts(t):
                return False
        if _overlaps(rest, tokens, i + n):
            return True
    return False


@dataclass
class Registry:
    raw: dict
    patterns: list[Pattern] = field(default_factory=list)
    kinds: dict[str, dict] = field(default_factory=dict)
    reserved: dict[str, str] = field(default_factory=dict)

    @property
    def root(self) -> str:
        return self.raw["root"]

    def _split(self, subject: object) -> tuple[list[str] | None, str]:
        if not isinstance(subject, str) or not subject:
            return None, "a subject is a non-empty string"
        if len(subject) > MAX_SUBJECT_LEN:
            return None, f"a subject is at most {MAX_SUBJECT_LEN} characters"
        tokens = subject.split(".")
        if "" in tokens:
            return None, "a subject has no empty tokens (no leading, trailing or double dot)"
        if tokens[0] != self.root:
            return None, f"OneMind subjects start with {self.root!r}"
        return tokens, ""

    def _kind(self, tokens: list[str]) -> tuple[str | None, str]:
        if len(tokens) < 2:
            return None, f"{self.root!r} alone names no kind"
        kind = tokens[1]
        if kind in self.reserved:
            return None, f"kind {kind!r} is reserved: {self.reserved[kind]}"
        if kind not in self.kinds:
            return None, f"unknown kind {kind!r}; registered kinds: {', '.join(self.kinds)}"
        return kind, ""

    def check(self, subject: str, publisher: str, owner_id: str | None = None) -> Verdict:
        """May `publisher` (gateway, node, app, agent) with its own id `owner_id` publish on `subject`?"""
        tokens, why = self._split(subject)
        if tokens is None:
            return Verdict(False, why)
        if any(t in ("*", ">") for t in tokens):
            return Verdict(False, "a published subject holds no wildcard (* or >)")
        if not all(_TOKEN_CHARS.match(t) for t in tokens):
            return Verdict(False, "subject tokens use letters, digits, '_' and '-' only")
        kind, why = self._kind(tokens)
        if kind is None:
            return Verdict(False, why)
        if publisher not in PUBLISHERS:
            return Verdict(False, f"unknown publisher class {publisher!r}", kind)
        shaped = [(p, b) for p in self.patterns if p.kind == kind and (b := p.bind(tokens)) is not None]
        if not shaped:
            shapes = "; ".join(p.text for p in self.patterns if p.kind == kind)
            return Verdict(False, f"{subject!r} does not fit kind {kind!r}: {shapes}", kind)
        refusals: list[str] = []
        for p, bound in shaped:
            if publisher not in p.publishers:
                who = " and ".join(p.publishers)
                refusals.append(f"kind {kind!r} is {'core' if self.kinds[kind].get('core') else 'restricted'}: "
                                f"only {who} may publish {p.text}")
                continue
            if publisher != "gateway" and p.owner:
                own = ".".join(bound.get(p.owner, []))
                if not owner_id or own != owner_id:
                    refusals.append(f"{'an' if publisher[0] in 'aeiou' else 'a'} {publisher} may publish only under its own {p.owner} "
                                    f"({owner_id or 'not given'}), not {own!r}")
                    continue
            return Verdict(True, "registered", kind, p.text)
        return Verdict(False, refusals[0], kind, shaped[0][0].text)

    def covers(self, subject_filter: str) -> Verdict:
        """Is `subject_filter` (wildcards allowed) inside the registered tree? For the lint and subscribers."""
        tokens, why = self._split(subject_filter)
        if tokens is None:
            return Verdict(False, why)
        if ">" in tokens[:-1]:
            return Verdict(False, "'>' may only be the last token")
        if tokens[1:] == [">"] or tokens[1:2] == ["*"]:
            return Verdict(True, f"spans every kind under {self.root}.")
        kind, why = self._kind(tokens)
        if kind is None:
            return Verdict(False, why)
        for p in self.patterns:
            if p.kind == kind and _overlaps(p.slots, tokens, 0):
                return Verdict(True, "registered", kind, p.text)
        shapes = "; ".join(p.text for p in self.patterns if p.kind == kind)
        return Verdict(False, f"{subject_filter!r} matches nothing registered for kind {kind!r}: {shapes}", kind)

    def pattern_for(self, subject: str) -> Pattern | None:
        tokens, _ = self._split(subject)
        if not tokens or len(tokens) < 2:
            return None
        return next((p for p in self.patterns if p.kind == tokens[1] and p.bind(tokens) is not None), None)

    def envelope_problems(self, envelope_id: str, obj: object) -> list[str]:
        """Plain reasons `obj` is not a valid `envelope_id` payload; empty when valid."""
        spec = self.raw.get("envelopes", {}).get(envelope_id)
        if spec is None:
            return [f"unknown envelope {envelope_id!r}"]
        try:
            size = len(json.dumps(obj, separators=(",", ":")).encode())
        except (TypeError, ValueError):
            return ["the envelope is not JSON"]
        if size > MAX_ENVELOPE_BYTES:
            return [f"the envelope is {size} bytes; the limit is {MAX_ENVELOPE_BYTES}"]
        problems = position_problems(obj.get("position")) if isinstance(obj, dict) and "position" in obj else []
        if problems or "file" not in spec:
            return problems
        from jsonschema import Draft202012Validator, FormatChecker

        schema = _schema(self.raw["_dir"], spec["file"])
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for err in sorted(validator.iter_errors(obj), key=lambda e: list(e.absolute_path)):
            where = ".".join(str(x) for x in err.absolute_path) or "envelope"
            problems.append(f"{where}: {err.message}")
        return problems

    def public(self) -> dict:
        """The registry as GET /v1/subjects returns it."""
        kinds = []
        for name, k in self.kinds.items():
            kinds.append({
                "kind": name, "description": k["description"], "core": bool(k.get("core")),
                "stream": k.get("stream"), "retention": k["retention"], "envelope": k["envelope"],
                "subjects": [{"pattern": p.text, "publishers": list(p.publishers), "owner": p.owner,
                              "stream": p.stream, "retention": p.retention, "envelope": p.envelope}
                             for p in self.patterns if p.kind == name],
            })
        return {"version": self.raw["schema"], "root": self.root, "grammar": self.raw["grammar"], "kinds": kinds,
                "reserved": [{"kind": k, "reason": v} for k, v in self.reserved.items()],
                "envelopes": [{"id": k, "file": v.get("file"), "contract": v.get("contract"),
                               "description": v["description"]} for k, v in self.raw["envelopes"].items()],
                "mappings": [{"grammar": m["grammar"], "old": m["from"], "new": m["to"], "note": m["note"]}
                             for m in self.raw["mappings"]]}


def position_problems(pos: object) -> list[str]:
    """WGS-84 checks with reasons: lat -90..90, lon -180..180, finite, and never exactly 0,0."""
    if not isinstance(pos, dict):
        return ["position must be an object with lat and lon"]
    out = []
    lat, lon = pos.get("lat"), pos.get("lon")
    for name, v, lim in (("lat", lat, 90), ("lon", lon, 180)):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            out.append(f"position.{name} must be a finite number")
        elif not -lim <= v <= lim:
            out.append(f"position.{name} {v} is outside WGS-84 (-{lim} to {lim})")
    if not out and lat == 0 and lon == 0:
        out.append("position 0,0 is refused: it is almost always a missing GPS fix, not a real place")
    return out


@lru_cache(maxsize=8)
def _schema(directory: str, name: str) -> dict:
    return json.loads((Path(directory) / name).read_text())


def _compile(raw: dict, directory: Path) -> Registry:
    try:
        holes = raw["placeholders"]
        reg = Registry(raw={**raw, "_dir": str(directory)}, kinds=dict(raw["kinds"]),
                       reserved=dict(raw.get("reserved_kinds", {})))
        for kind, spec in raw["kinds"].items():
            for s in spec["subjects"]:
                slots = []
                for i, tok in enumerate(s["pattern"].split(".")):
                    m = _PLACEHOLDER.match(tok)
                    if not m:
                        slots.append(Slot(literal=tok))
                        continue
                    name, typ = m.groups()
                    h = holes[typ]
                    slots.append(Slot(name=name, re=re.compile(h["re"]) if "re" in h else None,
                                      enum=tuple(h.get("enum", ())), deny=tuple(h.get("not", ())),
                                      lo=int(h.get("min", 1)), hi=int(h.get("max", 1))))
                if slots[0].literal != raw["root"] or slots[1].literal != kind:
                    raise RegistryError(f"pattern {s['pattern']!r} must start with {raw['root']}.{kind}")
                owner = s.get("owner")
                if owner and owner not in {x.name for x in slots}:
                    raise RegistryError(f"pattern {s['pattern']!r} has no placeholder {owner!r}")
                bad = set(s["publishers"]) - set(PUBLISHERS)
                if bad:
                    raise RegistryError(f"pattern {s['pattern']!r}: unknown publishers {sorted(bad)}")
                env = s.get("envelope", spec["envelope"])
                if env not in raw["envelopes"]:
                    raise RegistryError(f"pattern {s['pattern']!r}: unknown envelope {env!r}")
                reg.patterns.append(Pattern(kind, s["pattern"], tuple(slots), tuple(s["publishers"]), owner,
                                            s.get("stream", spec.get("stream")),
                                            s.get("retention", spec["retention"]), env))
        clash = set(reg.kinds) & set(reg.reserved)
        if clash:
            raise RegistryError(f"kinds both registered and reserved: {sorted(clash)}")
        return reg
    except (KeyError, TypeError, ValueError, re.error) as exc:
        raise RegistryError(f"malformed subject registry: {exc!r}") from None


def registry_path() -> Path:
    """The registry beside the app schema the gateway already uses, else the repo or image copy."""
    app_schema = os.environ.get("ONEMIND_APP_SCHEMA", "").strip()
    dirs = ([Path(app_schema).parent] if app_schema else []) + list(_SCHEMA_DIR_CANDIDATES)
    for d in dirs:
        if (d / REGISTRY_FILE).is_file():
            return d / REGISTRY_FILE
    raise RegistryError(f"{REGISTRY_FILE} not found in {', '.join(str(d) for d in dirs)}")


def load(path: Path | None = None) -> Registry:
    path = Path(path) if path else registry_path()
    return _load(str(path))


@lru_cache(maxsize=4)
def _load(path: str) -> Registry:
    try:
        raw = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise RegistryError(f"cannot read {path}: {exc}") from None
    return _compile(raw, Path(path).parent)
