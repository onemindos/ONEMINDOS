# SPDX-License-Identifier: Apache-2.0
"""App dependencies with alternatives (contract §12.22, PD-10).

`spec.dependencies: [{id, alternatives?, reason?}]`: a requirement is satisfied when its `id` or
any alternative is installed. Installing an app with an unsatisfied requirement is refused
(`dependency_missing`, naming the choices); removing an app that an installed app still needs,
with no other installed provider, is refused with the list of apps to remove first
(`has_dependents`).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from ..catalog import APP_ID_RE

MAX_DEPENDENCIES = 10

# Install statuses that provide what an app needs. "installing", "removing", "failed", "unknown"
# do not: a half-installed database satisfies nobody.
PROVIDING = frozenset({"installed", "configuring", "updating", "reverting", "drifted", "stopped", "starting",
                       "stopping", "restarting"})


@dataclass(frozen=True)
class Requirement:
    id: str
    alternatives: tuple[str, ...]
    reason: str | None

    @property
    def choices(self) -> tuple[str, ...]:
        out = [self.id]
        out += [a for a in self.alternatives if a not in out]
        return tuple(out)

    def to_json(self) -> dict:
        return {"id": self.id, "alternatives": list(self.alternatives), "reason": self.reason}


def requirements(manifest: dict) -> list[Requirement]:
    """The app's requirements. Malformed entries are skipped (the schema refuses them in CI)."""
    spec = manifest.get("spec") if isinstance(manifest, dict) else None
    raw = spec.get("dependencies") if isinstance(spec, dict) else None
    if not isinstance(raw, list):
        return []
    out = []
    for entry in raw[:MAX_DEPENDENCIES]:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not APP_ID_RE.match(entry["id"]):
            continue
        alts = entry.get("alternatives") or []
        alts = tuple(a for a in alts if isinstance(a, str) and APP_ID_RE.match(a)) if isinstance(alts, list) else ()
        reason = entry.get("reason") if isinstance(entry.get("reason"), str) else None
        out.append(Requirement(entry["id"], alts, reason))
    return out


def providing(statuses: Mapping[str, str]) -> set[str]:
    return {app_id for app_id, status in statuses.items() if status in PROVIDING}


def satisfied_by(req: Requirement, provided: Iterable[str]) -> str | None:
    have = set(provided)
    return next((c for c in req.choices if c in have), None)


def unsatisfied(manifest: dict, provided: Iterable[str]) -> list[Requirement]:
    have = set(provided)
    return [r for r in requirements(manifest) if satisfied_by(r, have) is None]


def dependents(app_id: str, manifests: Mapping[str, dict], statuses: Mapping[str, str]) -> list[str]:
    """Apps with a state row (any status but removing) that would lose their last provider."""
    have = providing(statuses) - {app_id}
    out = []
    for other, status in sorted(statuses.items()):
        if other == app_id or status == "removing" or other not in manifests:
            continue
        for req in requirements(manifests[other]):
            if app_id in req.choices and satisfied_by(req, have) is None:
                out.append(other)
                break
    return out


def missing_message(app_id: str, missing: list[Requirement]) -> str:
    parts = []
    for r in missing:
        what = f" ({r.reason})" if r.reason else ""
        parts.append(f"one of {', '.join(r.choices)}{what}" if len(r.choices) > 1 else f"{r.id}{what}")
    return f"app {app_id!r} needs {'; '.join(parts)} installed first"
