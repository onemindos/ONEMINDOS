# SPDX-License-Identifier: Apache-2.0
"""Event streams an app declares (`spec.streams`) and the hub's JetStream store (CORE-FABRIC, cluster replacement P1).

An app that needs a durable, replayable event log (sensor readings, a job queue) declares a stream
instead of running its own broker. The declaration is bounded on purpose, so no app can fill the box:

- `subjects` are written relative to the app. The hub puts them under `onemind.app.<app_id>.`, so an
  app can never name (or read) `onemind.node.*`, another app's subjects or the audit stream;
- `maxBytes` and `maxAgeSeconds` are required: a stream with no limit is not accepted. When a limit
  is hit the oldest messages go (`discard: old`); a stream never blocks the producer;
- storage is file, replicas 1 (one hub), and the total of all streams is capped by the hub's own
  JetStream limit (natsconf.render_accounts).

The plan the owner approves at install lists every stream with its exact limits and is hashed, so a
changed limit is a different plan. Creating the streams on the hub is the next slice (see core/README.md).
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
_TOKEN = r"(?:[a-z0-9_-]{1,32}|\*)"
SUBJECT_RE = re.compile(rf"^{_TOKEN}(?:\.{_TOKEN})*(?:\.>)?$|^>$")
MAX_STREAMS = 4
MAX_SUBJECTS = 8
MIN_BYTES = 1 << 20                 # 1 MiB
MAX_BYTES = 1 << 30                 # 1 GiB per stream
MAX_AGE_S = 30 * 86400              # 30 days
SUBJECT_ROOT = "onemind.app"

# Free space the store must keep: below this the hub reports JetStream as degraded and refuses to
# plan a new stream. NATS itself stops accepting writes when the disk is full; this warns first.
MIN_FREE_BYTES = 256 << 20
MIN_FREE_FRACTION = 0.05


@dataclass(frozen=True)
class Stream:
    name: str
    subjects: tuple[str, ...]   # relative, as declared
    max_bytes: int
    max_age_s: int
    description: str = ""

    def full_subjects(self, app_id: str) -> list[str]:
        return [f"{SUBJECT_ROOT}.{app_id}.{s}" for s in self.subjects]

    def stream_name(self, app_id: str) -> str:
        return f"APP_{app_id}_{self.name}".upper().replace("-", "_")

    def to_json(self, app_id: str) -> dict:
        """The exact parameters the owner approves (hashed into the plan)."""
        return {"name": self.stream_name(app_id), "subjects": self.full_subjects(app_id), "storage": "file",
                "replicas": 1, "retention": "limits", "discard": "old",
                "max_bytes": self.max_bytes, "max_age_s": self.max_age_s}


def validate(manifest: dict) -> list[dict]:
    """[{field, problem}] for `spec.streams`; empty when absent or valid."""
    spec = manifest.get("spec") if isinstance(manifest, dict) else None
    raw = spec.get("streams") if isinstance(spec, dict) else None
    if raw is None:
        return []
    if not isinstance(raw, list):
        return [{"field": "spec.streams", "problem": "must be a list"}]
    problems: list[dict] = []
    if len(raw) > MAX_STREAMS:
        problems.append({"field": "spec.streams", "problem": f"at most {MAX_STREAMS} streams"})
    names: set[str] = set()
    subjects: set[str] = set()
    for i, e in enumerate(raw[:MAX_STREAMS]):
        at = f"spec.streams[{i}]"
        if not isinstance(e, dict):
            problems.append({"field": at, "problem": "must be an object"})
            continue
        name = e.get("name")
        if not isinstance(name, str) or not NAME_RE.match(name):
            problems.append({"field": f"{at}.name", "problem": "lowercase letters, digits and dashes, starting with a letter"})
        elif name in names:
            problems.append({"field": f"{at}.name", "problem": f"{name!r} is declared twice"})
        else:
            names.add(name)
        subs = e.get("subjects")
        if not isinstance(subs, list) or not 1 <= len(subs) <= MAX_SUBJECTS:
            problems.append({"field": f"{at}.subjects", "problem": f"1 to {MAX_SUBJECTS} subjects"})
        else:
            for s in subs:
                if not isinstance(s, str) or not SUBJECT_RE.match(s) or s.startswith("$"):
                    problems.append({"field": f"{at}.subjects", "problem": f"{s!r} is not a relative subject"})
                elif s in subjects:
                    problems.append({"field": f"{at}.subjects", "problem": f"{s!r} is used by two streams"})
                else:
                    subjects.add(s)
        for key, lo, hi in (("maxBytes", MIN_BYTES, MAX_BYTES), ("maxAgeSeconds", 60, MAX_AGE_S)):
            v = e.get(key)
            if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
                problems.append({"field": f"{at}.{key}", "problem": f"required, a whole number from {lo} to {hi}"})
        extra = set(e) - {"name", "subjects", "maxBytes", "maxAgeSeconds", "description"}
        if extra:
            problems.append({"field": at, "problem": f"unknown field(s): {', '.join(sorted(extra))}"})
    return problems


def declared(manifest: dict) -> list[Stream]:
    """The valid declarations (call `validate` first to refuse a bad manifest)."""
    if validate(manifest):
        return []
    spec = manifest.get("spec") if isinstance(manifest, dict) else None
    return [Stream(e["name"], tuple(e["subjects"]), e["maxBytes"], e["maxAgeSeconds"], str(e.get("description") or ""))
            for e in (spec or {}).get("streams") or []]


def plan_entries(app_id: str, manifest: dict) -> list[dict]:
    return [s.to_json(app_id) for s in declared(manifest)]


def store_state(path: Path | None, min_free_bytes: int | None = None, min_free_fraction: float | None = None) -> dict:
    """The hub JetStream store's state: ok, degraded (disk nearly or fully full) or unavailable.

    `path` is the mount that holds the store. Reading the free space never touches the store itself
    (it is owned by the NATS user). Explicit by design: a full disk is shown, never silent.
    """
    if path is None:
        return {"state": "unavailable", "reason": "no JetStream store is configured on this node"}
    try:
        u = shutil.disk_usage(path)
    except OSError as exc:
        return {"state": "unavailable", "reason": f"the JetStream store cannot be read: {exc.strerror or exc}"}
    out = {"free_bytes": u.free, "total_bytes": u.total}
    floor = max(MIN_FREE_BYTES if min_free_bytes is None else min_free_bytes,
                int(u.total * (MIN_FREE_FRACTION if min_free_fraction is None else min_free_fraction)))
    if u.free < floor:
        return {"state": "degraded", "reason": "the disk is nearly full: new events may be refused, oldest events are dropped",
                **out}
    return {"state": "ok", **out}
