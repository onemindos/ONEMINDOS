# SPDX-License-Identifier: Apache-2.0
"""Where can this app run? (CORE-FABRIC-4, #171; contract §12.11 `GET /v1/apps/{id}/placement`.)

Three steps, all pure functions over the manifest and the node registry's dicts (heartbeats,
contract §2), so nothing here touches the cluster:

1. **Capability labels.** Each node's facts from `onemindd` (internal/detect) become labels in the
   Kubernetes style (`onemind.io/gpu=nvidia`, `onemind.io/arch=amd64`, ...). A fact the node did not
   report gives no label: an unknown is never written down as "no".
2. **Placement.** The app's `spec.requires` (gpu, minMemoryMb, cpuLevel) and `spec.archs` are checked
   against every node: `fits`, `fits_with_warning` (it runs, but the node is busy or its report is
   not live) or `no`, each with the reasons a person can read. The CPU and architecture check is
   NMD-09's (`cpufit.refusal`), reused per node.
3. **The Market verdict.** The best node wins (a clean fit before a warning, then the hub, then the
   most free memory): `here` when that is the hub, `elsewhere` when it is another machine,
   `nowhere` when no node can run it, and `unknown` when no node has reported yet.

A GPU here means an NVIDIA GPU, the only kind `onemindd` detects today (`gpu.nvidia`). A node that
does not report the `gpu` object at all (an older agent) is not counted as having one: an app that
needs a GPU is refused there rather than started on a guess.
"""

from __future__ import annotations

from . import cpufit

PREFIX = "onemind.io/"


def labels(node: dict) -> dict[str, str]:
    """The node's capability labels, from the facts its heartbeat reports. Unknown facts are left out."""
    out: dict[str, str] = {}
    for key, field in (("arch", "arch"), ("board", "board"), ("cpu-level", "cpu_level")):
        v = node.get(field)
        if isinstance(v, str) and v:
            out[PREFIX + key] = v
    fabric = node.get("fabric") if isinstance(node.get("fabric"), dict) else {}
    role = fabric.get("role") or node.get("role")
    if isinstance(role, str) and role:
        out[PREFIX + "role"] = role
    gpu = node.get("gpu")
    if isinstance(gpu, dict):
        out[PREFIX + "gpu"] = "nvidia" if gpu.get("nvidia") is True else "none"
    if isinstance(node.get("kvm"), bool):
        out[PREFIX + "kvm"] = "true" if node["kvm"] else "false"
    mem = node.get("mem_total_mb")
    if isinstance(mem, int) and not isinstance(mem, bool) and mem > 0:
        out[PREFIX + "memory-mb"] = str(mem)
    return out


def _number(v: object) -> int | float | None:
    return v if isinstance(v, int | float) and not isinstance(v, bool) else None


def _app_name(manifest: dict) -> str:
    md = manifest.get("metadata") or {}
    return md.get("name") or md.get("id") or "This app"


def assess(manifest: dict, node: dict) -> dict:
    """One node's line: {node_id, role, verdict, labels, reasons: [{code, message, blocking}]}."""
    name = _app_name(manifest)
    node_id = node.get("node_id") or "?"
    spec = manifest.get("spec") or {}
    requires = spec.get("requires") if isinstance(spec.get("requires"), dict) else {}
    reasons: list[dict] = []

    def add(code: str, message: str, blocking: bool) -> None:
        reasons.append({"code": code, "message": message, "blocking": blocking})

    status = node.get("status")
    if status == "offline":
        # The hub runs the gateway itself, so a silent hub agent is a warning; a silent worker cannot take apps.
        add("node_offline", f"Machine {node_id} has not reported for over two minutes.", node.get("role") != "hub")
    elif status == "stale":
        add("node_stale", f"Machine {node_id}'s last report is not live.", False)
    fabric = node.get("fabric") if isinstance(node.get("fabric"), dict) else {}
    k3s = node.get("k3s") if isinstance(node.get("k3s"), dict) else None
    if fabric.get("role") == "leaf" or (k3s is not None and k3s.get("present") is False):
        add("no_cluster", f"Machine {node_id} does not run apps (it is not part of the cluster).", True)
    elif k3s is not None and not k3s.get("ready"):
        add("cluster_not_ready", f"The cluster on machine {node_id} is not ready yet.", False)
    fit = cpufit.refusal(manifest, node)
    if fit:
        add(fit[0], fit[1].replace("this box", f"machine {node_id}"), True)
    if requires.get("gpu") is True:
        gpu = node.get("gpu")
        if not isinstance(gpu, dict):
            add("gpu_unknown", f"{name} needs a graphics card (GPU), and machine {node_id} did not report one.", True)
        elif gpu.get("nvidia") is not True:
            add("gpu_missing", f"{name} needs a graphics card (GPU), and machine {node_id} has none.", True)
    need = _number(requires.get("minMemoryMb"))
    total, free = _number(node.get("mem_total_mb")), _number(node.get("mem_available_mb"))
    if need is not None and total is not None and total < need:
        add("memory_too_small", f"{name} needs {need:.0f} MB of memory, and machine {node_id} has {total:.0f} MB in all.", True)
    elif need is not None and free is not None and free < need:
        add("memory_busy", f"{name} needs {need:.0f} MB of memory, and machine {node_id} has {free:.0f} MB free right now.", False)

    if any(r["blocking"] for r in reasons):
        verdict = "no"
    elif reasons:
        verdict = "fits_with_warning"
    else:
        verdict = "fits"
    return {"node_id": node_id, "role": node.get("role"), "verdict": verdict, "labels": labels(node), "reasons": reasons}


def _rank(line: dict, node: dict) -> tuple:
    free = _number(node.get("mem_available_mb")) or 0
    return (line["verdict"] != "fits", node.get("role") != "hub", -free, line["node_id"])


def place(manifest: dict, nodes: list[dict]) -> dict:
    """The Market verdict for one app over every node that has reported."""
    lines = [assess(manifest, n) for n in nodes]
    name = _app_name(manifest)
    ok = sorted(((ln, n) for ln, n in zip(lines, nodes, strict=True) if ln["verdict"] != "no"), key=lambda p: _rank(*p))
    if not nodes:
        verdict, node_id, message = "unknown", None, "No machine has reported yet, so OneMind cannot tell where this app would run."
    elif not ok:
        verdict, node_id = "nowhere", None
        message = f"{name} cannot run on any machine here. " + " ".join(
            dict.fromkeys(r["message"] for ln in lines for r in ln["reasons"] if r["blocking"]))
    else:
        best, node = ok[0]
        node_id = best["node_id"]
        if node.get("role") == "hub":
            verdict, message = "here", f"{name} runs on this box."
        else:
            verdict, message = "elsewhere", f"{name} runs on another machine: {node_id}."
        warnings = [r["message"] for r in best["reasons"]]
        if warnings:
            message += " " + " ".join(warnings)
    return {"verdict": verdict, "node_id": node_id, "message": message, "nodes": lines}
