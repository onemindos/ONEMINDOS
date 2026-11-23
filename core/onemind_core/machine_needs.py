# SPDX-License-Identifier: Apache-2.0
"""One requires / recommends / supports block for what an app needs from a machine (#724).

The app schema (sdk/schema/onemind.app.schema.json, $defs/machineNeeds) gives all three strengths one
shape: arch, memoryMb, storageFreeGb, accelerator {capability, minMemoryMb, rtCores, count, overlay},
devices, radios and models {quantisations}. Manifests written before it use older keys that stay
valid; this module is the one place that maps them, both ways:

    spec.archs + requires.cpuLevel.amd64   ->  requires.arch      (x86-64-vN stands for amd64 at that level)
    requires.minMemoryMb                   ->  requires.memoryMb
    requires.gpu: true                     ->  requires.accelerator {capability: gpu-compute}
    requires.gpuCount                      ->  requires.accelerator.count
    requires.minVramMb                     ->  requires.accelerator.minMemoryMb (the larger of the two)
    requires.accelerator {optional: true}  ->  recommends.accelerator

machine_needs() gives the new shape (for the verdict engine and later readers); legacy_requires()
gives the older shape the current fit code (placement, cpufit, gpufit) reads, so a manifest written
with the new keys is checked exactly like one written with the old ones. A fact a manifest does not
state is left out: never assumed.
"""

from __future__ import annotations

STRENGTHS = ("requires", "recommends", "supports")
KEYS = ("arch", "memoryMb", "storageFreeGb", "accelerator", "devices", "radios", "models")
ACCELERATOR_KEYS = ("capability", "minMemoryMb", "rtCores", "count", "overlay")
X86_LEVELS = ("x86-64-v1", "x86-64-v2", "x86-64-v3", "x86-64-v4")
# A manifest may say each fact once: (older key, newer key) pairs that may not both be in spec.requires.
TWICE = (("minMemoryMb", "memoryMb"), ("cpuLevel", "arch"), ("gpuCount", "accelerator.count"))


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def base_arch(arch: str) -> str:
    """amd64 for an x86-64 level, else the name itself."""
    return "amd64" if arch in X86_LEVELS else arch


def _accelerator(raw: dict) -> dict:
    return {k: raw[k] for k in ACCELERATOR_KEYS if k in raw}


def _block(raw: object) -> dict:
    """The new keys of one strength, copied (the accelerator without the older optional flag)."""
    block = {k: v for k, v in _dict(raw).items() if k in KEYS}
    if isinstance(block.get("accelerator"), dict):
        block["accelerator"] = _accelerator(block["accelerator"])
    for key in ("arch", "devices", "radios"):
        if isinstance(block.get(key), list):
            block[key] = list(block[key])
    if isinstance(block.get("models"), dict):
        block["models"] = {"quantisations": list(_dict(block["models"]).get("quantisations") or [])}
    return block


def machine_needs(spec: object) -> dict[str, dict]:
    """{requires, recommends, supports} in the new shape, from a manifest spec in either spelling."""
    spec = _dict(spec)
    raw = _dict(spec.get("requires"))
    out = {name: _block(spec.get(name)) for name in STRENGTHS}
    req = out["requires"]
    archs = spec.get("archs")
    if "arch" not in req and isinstance(archs, list) and archs:
        level = _dict(raw.get("cpuLevel")).get("amd64")
        req["arch"] = [level if a == "amd64" and level in X86_LEVELS else a for a in archs]
    if "memoryMb" not in req and _count(raw.get("minMemoryMb")):
        req["memoryMb"] = raw["minMemoryMb"]
    acc = _dict(raw.get("accelerator"))
    if acc.get("optional") is True:
        req.pop("accelerator", None)
        out["recommends"].setdefault("accelerator", _accelerator(acc))
        acc = {}
    if acc or raw.get("gpu") is True:
        need = _accelerator(acc) if acc else {"capability": "gpu-compute"}
        sizes = [m for m in (_count(acc.get("minMemoryMb")), _count(raw.get("minVramMb"))) if m]
        if sizes:
            need["minMemoryMb"] = max(sizes)
        if "count" not in need and _count(raw.get("gpuCount")):
            need["count"] = raw["gpuCount"]
        req["accelerator"] = need
    return out


def legacy_requires(spec: object) -> dict:
    """spec.requires in the older shape (gpu, minMemoryMb, gpuCount, minVramMb, accelerator, cpuLevel) for the
    fit code written before #724. Only the newer keys are translated: a manifest in the older spelling comes
    back as it is, so its placement does not change. A required accelerator's minMemoryMb becomes minVramMb
    too (card memory the machine must report, #595)."""
    spec = _dict(spec)
    raw = _dict(spec.get("requires"))
    out = {k: v for k, v in raw.items() if k not in KEYS or k == "accelerator"}
    if "minMemoryMb" not in out and _count(raw.get("memoryMb")):
        out["minMemoryMb"] = raw["memoryMb"]
    arch = raw.get("arch")
    levels = [a for a in arch if a in X86_LEVELS] if isinstance(arch, list) else []
    if "cpuLevel" not in out and levels:
        out["cpuLevel"] = {"amd64": levels[0]}
    acc = _dict(raw.get("accelerator"))
    if acc and acc.get("optional") is not True:
        if "gpu" not in raw:
            out["gpu"] = True
            if "minVramMb" not in out and _count(acc.get("minMemoryMb")):
                out["minVramMb"] = acc["minMemoryMb"]
        if "gpuCount" not in out and _count(acc.get("count")):
            out["gpuCount"] = acc["count"]
    better = _dict(_dict(spec.get("recommends")).get("accelerator"))
    if "accelerator" not in out and better:
        out["accelerator"] = {**{k: better[k] for k in ("capability", "minMemoryMb", "overlay") if k in better},
                              "optional": True}
    out.setdefault("gpu", False)
    return out


def overlays(spec: object) -> list[str]:
    """Every accelerator overlay directory the manifest names, in any strength."""
    found = []
    for block in machine_needs(spec).values():
        name = _dict(block.get("accelerator")).get("overlay")
        if isinstance(name, str) and name not in found:
            found.append(name)
    return found


def _strings(value: object) -> list[tuple[str, str]]:
    return [(str(i), v) for i, v in enumerate(value) if isinstance(v, str)] if isinstance(value, list) else []


def vendor_errors(spec: object) -> list[str]:
    """A vendor resource (nvidia.com/gpu) or a host path (/dev/ttyUSB0) where a vendor-neutral name goes."""
    errs = []
    for name in STRENGTHS:
        block = _dict(_dict(spec).get(name))
        found = [(f"devices/{i}", v) for i, v in _strings(block.get("devices"))]
        capability = _dict(block.get("accelerator")).get("capability")
        if isinstance(capability, str):
            found.append(("accelerator/capability", capability))
        for where, value in found:
            if "/" in value or "." in value:
                errs.append(f"spec/{name}/{where}: {value} names a vendor or a host path; use a vendor-neutral name")
    return errs


def errors(spec: object) -> list[str]:
    """The rules the schema cannot say: one spelling per fact (an optional requires.accelerator is the older
    spelling of recommends.accelerator), each architecture once, and requires.arch
    names the same architectures as spec.archs (the images' own list, which the app gate checks)."""
    spec = _dict(spec)
    errs = vendor_errors(spec)
    raw = _dict(spec.get("requires"))
    for old, new in TWICE:
        head, _, tail = new.partition(".")
        if old in raw and head in raw and (not tail or tail in _dict(raw[head])):
            errs.append(f"spec/requires: {old} and {new} say the same thing; keep {new}")
    if _dict(raw.get("accelerator")).get("optional") is True and "accelerator" in _dict(spec.get("recommends")):
        # The older optional accelerator is the recommends.accelerator of the new shape: with both, the fit code
        # (legacy_requires) and the overlay check (overlays) would each read a different one.
        errs.append("spec: requires.accelerator.optional and recommends.accelerator say the same thing; "
                    "keep recommends.accelerator")
    for name in STRENGTHS:
        seen: set[str] = set()
        for _, arch in _strings(_dict(spec.get(name)).get("arch")):
            if base_arch(arch) in seen:
                errs.append(f"spec/{name}/arch: {base_arch(arch)} is named twice")
            seen.add(base_arch(arch))
    arch, archs = raw.get("arch"), spec.get("archs")
    if isinstance(arch, list) and isinstance(archs, list):
        if {base_arch(a) for a in arch if isinstance(a, str)} != {a for a in archs if isinstance(a, str)}:
            errs.append("spec/requires/arch: must name the same architectures as spec.archs")
    return errs
