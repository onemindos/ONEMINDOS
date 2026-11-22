# SPDX-License-Identifier: Apache-2.0
"""What a machine is: its parameters, the quota the box keeps for itself, and its KubeVirt objects.

Pure functions (docs/umbrel2/machines.md §4.8, #281 scope 4 and the "no network beyond what the
owner approves" rule). The gateway renders the objects here and applies them only after an owner
approved the action (service.py, runtime.py). Nothing in this file talks to a cluster.

Design is written against KubeVirt's public API (Apache-2.0). No code from umbrelOS or Olares.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

NAMESPACE = "machines"
NAME_PATTERN = r"^[a-z][a-z0-9-]{0,38}[a-z0-9]$"
RESERVED_NAMES = frozenset({"capabilities", "enable"})  # they would collide with GET /v1/machines/<word>


def _not_reserved(name: str) -> str:
    if name in RESERVED_NAMES:
        raise ValueError(f"{name} is reserved: pick another machine name")
    return name


# What the box keeps for k3s, the gateway and the node daemon. Machines may use the rest.
RESERVE_MB = 4096
RESERVE_CPUS = 1
MIN_VM_MB = 512
MAX_VM_MB = 262_144


class MachineCreateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=40, pattern=NAME_PATTERN)
    ram_mb: int = Field(ge=MIN_VM_MB, le=MAX_VM_MB)
    cpus: int = Field(ge=1, le=64)
    disk_gb: int = Field(ge=1, le=2048)
    # A cloud image the owner chose, fetched by CDI over HTTPS. The machine itself gets no network
    # beyond what the owner approves (default-deny below); only the import pod reaches this URL.
    image_url: str = Field(pattern=r"^https://[^\s]{1,500}$")
    _name_ok = field_validator("name")(_not_reserved)


class MachineRefParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=40, pattern=NAME_PATTERN)


class MachineDeleteParams(MachineRefParams):
    # Deleting a machine deletes its disk. The name typed again by the owner, never one click.
    confirm: str = Field(min_length=2, max_length=40)


class MachineSnapshotParams(MachineRefParams):
    snapshot: str = Field(min_length=2, max_length=40, pattern=NAME_PATTERN)


class MachineCloneParams(BaseModel):
    """`name` is the NEW machine (like machine.create), so the quota claim and the name check are shared."""
    model_config = ConfigDict(extra="forbid")
    source: str = Field(min_length=2, max_length=40, pattern=NAME_PATTERN)
    name: str = Field(min_length=2, max_length=40, pattern=NAME_PATTERN)
    _name_ok = field_validator("name")(_not_reserved)


Verb = Literal["create", "start", "stop", "delete", "restart", "force_stop", "snapshot", "clone"]

# Disk copies are not free: each one grows with what changed since. A small cap keeps a hub's disk safe.
MAX_SNAPSHOTS = 5

# What a snapshot guarantees, in words for the owner. `quiesce` = the guest agent froze the disk first.
CONSISTENCY_TEXT = {
    "offline": "The machine was stopped, so the disk copy is complete and consistent.",
    "quiesced": "The machine's guest agent paused its disk writes first, so the copy is consistent.",
    "best_effort": "The machine was running without a guest agent, so the copy is best effort: like pulling the power cord, "
                   "it usually starts but files written at that moment may be half done.",
    "quiesce_failed": "The guest agent could not pause the disk (QuiesceFailed), so the copy is best effort: like pulling "
                      "the power cord, it usually starts but files written at that moment may be half done.",
}


def consistency(state: str, indications: list[str]) -> str:
    """How safe a snapshot is, from the machine's state and KubeVirt's `status.indications`."""
    if state != "running":
        return "offline"
    if "QuiesceFailed" in indications:
        return "quiesce_failed"
    return "quiesced" if "GuestAgent" in indications else "best_effort"


def budget(node: dict) -> tuple[int, int]:
    """(RAM in MB, CPUs) machines may use in total on this node, after the box's own reserve."""
    mem = node.get("mem_total_mb")
    cpus = node.get("cpus")
    ram = max(0, int(mem) - RESERVE_MB) if isinstance(mem, int | float) and not isinstance(mem, bool) else 0
    cpu = max(0, int(cpus) - RESERVE_CPUS) if isinstance(cpus, int | float) and not isinstance(cpus, bool) else None
    return ram, cpu if cpu is not None else 10**6  # a node that does not report cpus is capped by RAM only


def quota_problem(node: dict, existing: list[dict], ram_mb: int, cpus: int) -> str | None:
    """Why this machine does not fit next to the ones already there; None when it fits."""
    ram_cap, cpu_cap = budget(node)
    used_ram = sum(m["ram_mb"] for m in existing)
    used_cpu = sum(m["cpus"] for m in existing)
    if used_ram + ram_mb > ram_cap:
        return (f"Not enough memory: machines may use {ram_cap} MB on this box (the rest is kept for the system), "
                f"{used_ram} MB is already promised and this one needs {ram_mb} MB.")
    if used_cpu + cpus > cpu_cap:
        return (f"Not enough processor cores: machines may use {cpu_cap}, {used_cpu} are already promised "
                f"and this one needs {cpus}.")
    return None


def _vm(p: MachineCreateParams) -> dict:
    mem = f"{p.ram_mb}Mi"
    return {
        "apiVersion": "kubevirt.io/v1", "kind": "VirtualMachine",
        "metadata": {"name": p.name, "namespace": NAMESPACE, "labels": {"onemind.io/machine": p.name}},
        "spec": {
            "runStrategy": "Halted",  # created stopped; `machine.start` is its own approved action
            "dataVolumeTemplates": [{
                "metadata": {"name": f"{p.name}-disk"},
                "spec": {"source": {"http": {"url": p.image_url}},
                         "storage": {"accessModes": ["ReadWriteOnce"], "resources": {"requests": {"storage": f"{p.disk_gb}Gi"}}}},
            }],
            "template": {
                "metadata": {"labels": {"onemind.io/machine": p.name}},
                "spec": {
                    "domain": {
                        "cpu": {"cores": p.cpus},
                        # requests == limits: the machine can never take more than its quota.
                        "resources": {"requests": {"memory": mem, "cpu": str(p.cpus)}, "limits": {"memory": mem, "cpu": str(p.cpus)}},
                        "devices": {"disks": [{"name": "root", "disk": {"bus": "virtio"}}],
                                    "interfaces": [{"name": "default", "masquerade": {}}]},
                    },
                    "networks": [{"name": "default", "pod": {}}],
                    "volumes": [{"name": "root", "dataVolume": {"name": f"{p.name}-disk"}}],
                },
            },
        },
    }


def _deny_all(name: str) -> dict:
    # Default-deny both ways: the machine reaches and is reached by nothing until the owner approves a path.
    return {
        "apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
        "metadata": {"name": f"{name}-deny", "namespace": NAMESPACE, "labels": {"onemind.io/machine": name}},
        "spec": {"podSelector": {"matchLabels": {"onemind.io/machine": name}}, "policyTypes": ["Ingress", "Egress"]},
    }


def snapshot_name(machine: str, snap: str) -> str:
    """One object name per (machine, snapshot) pair, never shared by two pairs.

    Names allow hyphens, so plain `machine-snap` joining is ambiguous (web + db-1 and web-db + 1 both
    give web-db-1) and the 63-character cut can merge long names. A digest of the NUL-separated pair
    (NUL cannot occur in a name) is appended; the readable prefix is only for people."""
    digest = hashlib.sha256(f"{machine}\0{snap}".encode()).hexdigest()[:12]
    return f"{machine[:19]}-{snap[:19]}-{digest}".rstrip("-")


def render_snapshot(machine: str, snap: str) -> str:
    return json.dumps({
        "apiVersion": "snapshot.kubevirt.io/v1beta1", "kind": "VirtualMachineSnapshot",
        "metadata": {"name": snapshot_name(machine, snap), "namespace": NAMESPACE, "labels": {"onemind.io/machine": machine}},
        "spec": {"source": {"apiGroup": "kubevirt.io", "kind": "VirtualMachine", "name": machine}}}, sort_keys=True)


def render_clone(source: str, target: str) -> str:
    """The clone object plus the deny-all policy of the new machine, applied before the copy exists.

    The clone filters out our own labels, so the copy is never selected by the source's policy, and
    the runtime relabels it before anything can start it (runtime.KubectlRuntime.clone)."""
    clone = {
        "apiVersion": "clone.kubevirt.io/v1alpha1", "kind": "VirtualMachineClone",
        "metadata": {"name": f"{target}-clone", "namespace": NAMESPACE, "labels": {"onemind.io/machine": target}},
        "spec": {"source": {"apiGroup": "kubevirt.io", "kind": "VirtualMachine", "name": source},
                 "target": {"apiGroup": "kubevirt.io", "kind": "VirtualMachine", "name": target},
                 "labelFilters": ["*", "!onemind.io/*"], "template": {"labelFilters": ["*", "!onemind.io/*"]}}}
    return json.dumps({"apiVersion": "v1", "kind": "List", "items": [_deny_all(target), clone]}, sort_keys=True)


def render_create(p: MachineCreateParams) -> str:
    """The objects `machine.create` applies, as one JSON document list (JSON is YAML)."""
    ns = {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": NAMESPACE}}
    return json.dumps({"apiVersion": "v1", "kind": "List", "items": [ns, _deny_all(p.name), _vm(p)]}, sort_keys=True)
