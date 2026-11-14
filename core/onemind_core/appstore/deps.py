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
    port: int | None = None  # the provider's Service port the app calls; default its spec.web.port

    @property
    def choices(self) -> tuple[str, ...]:
        out = [self.id]
        out += [a for a in self.alternatives if a not in out]
        return tuple(out)

    def to_json(self) -> dict:
        return {"id": self.id, "alternatives": list(self.alternatives), "reason": self.reason, "port": self.port}


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
        port = entry.get("port")
        port = port if isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535 else None
        out.append(Requirement(entry["id"], alts, reason, port))
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


# ---- network paths (§12.22 dependency network paths) ---------------------------------------------

@dataclass(frozen=True)
class Link:
    """One owner-approved path app-<dependent> -> app-<provider>, TCP on the provider's Service port."""

    provider: str
    port: int
    requirement: str

    def to_json(self, dependent: str) -> dict:
        return {"from": f"app-{dependent}", "to": f"app-{self.provider}", "provider": self.provider,
                "port": self.port, "protocol": "TCP", "requirement": self.requirement}


def web_port(manifest: dict) -> int | None:
    spec = manifest.get("spec") if isinstance(manifest, dict) else None
    web = spec.get("web") if isinstance(spec, dict) else None
    port = web.get("port") if isinstance(web, dict) else None
    return port if isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535 else None


def links(app_id: str, manifest: dict, manifests: Mapping[str, dict], provided: Iterable[str]
          ) -> tuple[list[Link], list[str]]:
    """(paths to open, warnings) for app_id's satisfied requirements. Pure.

    The provider is the first installed choice (as satisfied_by), never the app itself. Its port is
    the requirement's `port`, else the provider's spec.web.port; with neither, no path and a warning.
    """
    have = set(provided) - {app_id}
    out: list[Link] = []
    warnings: list[str] = []
    seen: set[tuple[str, int]] = set()
    for req in requirements(manifest):
        provider = satisfied_by(req, have)
        if provider is None or not APP_ID_RE.match(provider):
            continue
        port = req.port or web_port(manifests.get(provider) or {})
        if port is None:
            warnings.append(f"No port is known for {provider} (needed for {req.id}): no network path is opened, "
                            f"so {app_id} cannot reach it.")
            continue
        if (provider, port) in seen:
            continue
        seen.add((provider, port))
        out.append(Link(provider, port, req.id))
    return out, warnings
