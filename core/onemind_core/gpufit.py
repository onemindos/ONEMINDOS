# SPDX-License-Identifier: Apache-2.0
"""Does this box have the accelerator (GPU) the app asks for? (S-5.)

An app says what it needs in vendor-neutral words under `spec.requires`:

    requires:
      gpu: true                                # a hard need: no graphics card, no install
      accelerator: {capability: gpu-compute, minMemoryMb: 8192}

or, for an app that is faster with a GPU but works without one (Ollama):

      accelerator: {capability: gpu-compute, minMemoryMb: 4096, optional: true, overlay: manifests-gpu}

The app never names NVIDIA, CUDA or a driver. The box reports what it has in its heartbeat
(`gpu: {nvidia, model, memory_mb?}`, from internal/detect) and this module maps one to the other, so a
second vendor later is a change here, not in every app.

Rules, the same as cpufit: a hard need that the box cannot meet is refused up front, in a sentence a
person can act on, instead of a pod that never starts. What the box does not say is not guessed: an
older agent that sends no `gpu` object, or a GPU whose memory it does not report, gives no refusal.
An optional accelerator never refuses; `wants_overlay` says whether the GPU manifests apply.
Pure functions over the manifest and the node registry's dicts.
"""

from __future__ import annotations

from .machine_needs import legacy_requires

CAPABILITIES = ("gpu-compute",)


def _requires(manifest: dict) -> dict:
    """spec.requires in the older shape, whichever spelling the manifest uses (#724)."""
    return legacy_requires(manifest.get("spec"))


def _name(manifest: dict) -> str:
    md = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
    return md.get("name") or md.get("id") or "This app"


def accelerator(manifest: dict) -> dict | None:
    """The app's accelerator need as {capability, minMemoryMb, optional, overlay}, or None.

    `requires.gpu: true` alone means a required gpu-compute accelerator of any size."""
    req = _requires(manifest)
    acc = req.get("accelerator")
    if isinstance(acc, dict) and acc.get("capability") in CAPABILITIES:
        mem = acc.get("minMemoryMb")
        return {"capability": acc["capability"],
                "minMemoryMb": mem if isinstance(mem, int) and not isinstance(mem, bool) and mem > 0 else 0,
                "optional": acc.get("optional") is True,
                "overlay": acc["overlay"] if isinstance(acc.get("overlay"), str) else None}
    if req.get("gpu") is True:
        return {"capability": "gpu-compute", "minMemoryMb": 0, "optional": False, "overlay": None}
    return None


def node_has(node: dict | None, capability: str = "gpu-compute") -> bool | None:
    """True or False when the box said, None when it did not (no heartbeat, or an older agent)."""
    gpu = (node or {}).get("gpu")
    if capability != "gpu-compute" or not isinstance(gpu, dict) or "nvidia" not in gpu:
        return None
    return gpu.get("nvidia") is True


def node_memory_mb(node: dict | None) -> int | None:
    mem = ((node or {}).get("gpu") or {}).get("memory_mb") if isinstance((node or {}).get("gpu"), dict) else None
    return mem if isinstance(mem, int) and not isinstance(mem, bool) and mem > 0 else None


def wants_overlay(manifest: dict, node: dict | None) -> str | None:
    """The manifests sub-directory to render for this box (e.g. "manifests-gpu"), or None for the plain manifests.

    Only when the app offers one and the box said it has an accelerator that is big enough."""
    acc = accelerator(manifest)
    if not acc or not acc["overlay"] or node_has(node, acc["capability"]) is not True:
        return None
    have = node_memory_mb(node)
    if have is not None and have < acc["minMemoryMb"]:
        return None
    return acc["overlay"]


def refusal(manifest: dict, node: dict | None) -> tuple[str, str, list[dict]] | None:
    """(reason code, message, details) when a required accelerator is missing or too small, else None."""
    acc = accelerator(manifest)
    if not acc or acc["optional"] or not node:
        return None
    name = _name(manifest)
    has = node_has(node, acc["capability"])
    if has is False:
        return ("gpu_missing",
                f"{name} needs a graphics card (GPU) and this box has none. It would not start, so it is not "
                "installed. Install it on a machine with a GPU, or use the OneMind OS GPU image.",
                [{"field": "spec.requires.accelerator", "problem": "needs gpu-compute; box reports no GPU"}])
    need, have_mb = acc["minMemoryMb"], node_memory_mb(node)
    if has is True and need and have_mb is not None and have_mb < need:
        return ("gpu_memory_too_small",
                f"{name} needs a GPU with at least {need} MB of its own memory, and this box's GPU has "
                f"{have_mb} MB. It would run out of memory, so it is not installed.",
                [{"field": "spec.requires.accelerator.minMemoryMb", "problem": f"needs {need}; box has {have_mb}"}])
    return None
