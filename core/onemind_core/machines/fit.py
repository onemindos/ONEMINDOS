# SPDX-License-Identifier: Apache-2.0
"""Read-only machine verdicts. Placement and approved-plan decisions keep their existing checks."""

from .. import cpufit, gpufit, placement
from ..machine_needs import legacy_requires, machine_needs

UNKNOWN = frozenset({"gpu_unknown", "gpu_count_unknown", "gpu_vram_unknown"})


def fit(manifest: dict, nodes: list[dict]) -> dict:
    """Report an evidence-based verdict for each node and the IDs of machines that fit."""
    spec = manifest.get("spec") or {}
    needs = machine_needs(spec)
    requires = legacy_requires(spec)
    accelerator = gpufit.accelerator(manifest)
    results = []
    for node in nodes:
        line = placement.assess(manifest, node)
        reasons = line["reasons"]
        failed = [reason["message"] for reason in reasons if reason["blocking"] and reason["code"] not in UNKNOWN]
        unmeasured = [reason["message"] for reason in reasons if reason["code"] in UNKNOWN]
        warnings = [reason["message"] for reason in reasons if not reason["blocking"]]

        arch = node.get("arch")
        levels = requires.get("cpuLevel") or {}
        if needs["requires"].get("arch") and not arch:
            unmeasured.append("Architecture is missing from the machine profile.")
        if arch == "amd64" and levels.get(arch) and node.get("cpu_level") not in cpufit.X86_LEVELS:
            unmeasured.append("The x86 CPU level is missing from the machine profile.")
        if requires.get("minMemoryMb") and not node.get("mem_total_mb"):
            unmeasured.append("Total memory is missing from the machine profile.")
        for field, label in (("storageFreeGb", "free storage"), ("devices", "required devices"),
                             ("radios", "radios"), ("models", "model quantisations")):
            if needs["requires"].get(field):
                unmeasured.append(f"Placement does not yet check {label} from the machine profile.")

        if accelerator and accelerator["optional"]:
            has = gpufit.node_has(node, accelerator["capability"])
            memory = gpufit.node_memory_mb(node)
            if has is False or (has is True and memory is not None and memory < accelerator["minMemoryMb"]):
                warnings.append("The recommended graphics accelerator is unavailable; expect slower performance.")

        if failed:
            verdict, explanation = "not-on-this-machine", failed
        elif unmeasured:
            verdict, explanation = "not-checked", unmeasured
        elif warnings:
            verdict, explanation = "yes-but-slow", warnings
        else:
            verdict, explanation = "yes", []
        results.append({"node_id": line["node_id"], "verdict": verdict, "reasons": explanation})

    return {"nodes": results, "passing_nodes": [row["node_id"] for row in results if row["verdict"] in {"yes", "yes-but-slow"}]}
