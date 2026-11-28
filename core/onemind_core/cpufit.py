# SPDX-License-Identifier: Apache-2.0
"""Can this box run this app's images? (NMD-09, #134.)

An image built for a newer CPU than the box has does not fail at install. It crashes later with
"illegal instruction", or, as with NOMAD's bug #661, an update bricks a working app. So install and
update are refused up front, with a sentence a person can act on, when:

- the app's images are not built for the box's architecture (`spec.archs`), or
- the app declares a minimum CPU level (`spec.requires.cpuLevel`, e.g. {"amd64": "x86-64-v2"})
  and the hub reports a lower one in its heartbeat (`cpu_level`, from internal/detect).

v0 runs every app on the hub node (CORE-FABRIC-4 adds placement), so the hub is the box that counts.
What the gateway cannot know, it does not guess: no hub heartbeat, or no `cpu_level` in it (an older
agent, or an architecture without levels), means no refusal from this check.
Pure functions over the manifest and the node registry's dicts.
"""

from __future__ import annotations

from .machine_needs import legacy_requires

X86_LEVELS = ("x86-64-v1", "x86-64-v2", "x86-64-v3", "x86-64-v4")
ARCH_NAMES = {"amd64": "x86 (amd64)", "arm64": "ARM (arm64)"}


def hub(nodes: list[dict]) -> dict | None:
    """The hub's heartbeat, or None when no hub has reported (or more than one claims to be it)."""
    hubs = [n for n in nodes if n.get("role") == "hub"]
    return hubs[0] if len(hubs) == 1 else None


def refusal(manifest: dict, node: dict | None) -> tuple[str, str, list[dict]] | None:
    """(reason code, message, details) when the box cannot run the app, else None."""
    if not node:
        return None
    spec = manifest.get("spec") or {}
    md = manifest.get("metadata") or {}
    name = md.get("name") or md.get("id") or "This app"
    arch = node.get("arch")
    archs = spec.get("archs")
    if arch and isinstance(archs, list) and archs and arch not in archs:
        built = " and ".join(ARCH_NAMES.get(a, a) for a in archs)
        return ("arch_unsupported",
                f"{name} is built for {built} only, and this box is {ARCH_NAMES.get(arch, arch)}.",
                [{"field": "spec.archs", "problem": f"box is {arch}; app supports {archs}"}])
    requires = legacy_requires(spec)  # #724: requires.arch x86-64-vN is the newer spelling of cpuLevel
    levels = requires.get("cpuLevel") if isinstance(requires.get("cpuLevel"), dict) else {}
    need = levels.get(arch or "")  # a malformed cpuLevel is ignored here; the app gate rejects it
    have = node.get("cpu_level") or ""
    if arch == "amd64" and need in X86_LEVELS and have in X86_LEVELS:
        if X86_LEVELS.index(have) < X86_LEVELS.index(need):
            return ("cpu_level_too_low",
                    f"{name} needs a newer processor: its images need {need}, and this box's CPU is {have}. "
                    "It would crash on this box, so it is not installed.",
                    [{"field": "spec.requires.cpuLevel.amd64", "problem": f"needs {need}; box is {have}"}])
    return None
