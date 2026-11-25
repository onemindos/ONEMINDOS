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
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..jsonbody import JsonBody

NAMESPACE = "machines"
NAME_PATTERN = r"^[a-z][a-z0-9-]{0,38}[a-z0-9]$"
RESERVED_NAMES = frozenset({"capabilities", "enable", "disable"})  # they would collide with GET /v1/machines/<word>


def _not_reserved(name: str) -> str:
    if name in RESERVED_NAMES:
        raise ValueError(f"{name} is reserved: pick another machine name")
    return name


# What the box keeps for k3s, the gateway and the node daemon. Machines may use the rest.
RESERVE_MB = 4096
RESERVE_CPUS = 1
MIN_VM_MB = 512
MAX_VM_MB = 262_144
GIB = 1 << 30
MAX_ISO_BYTES = 16 * GIB
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class CatalogueImage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    url: str = Field(pattern=r"^https://[^\s]{1,500}$")
    sha256: Sha256


# Canonical's dated SHA256SUMS in the same directory pins the compressed, downloaded image.
IMAGE_CATALOGUE = (
    CatalogueImage(name="Ubuntu Server 24.04 LTS (amd64)",
                   url="https://cloud-images.ubuntu.com/releases/24.04/release-20261017/ubuntu-24.04-server-cloudimg-amd64.img",
                   sha256="04e8f2461a16a44e78a370284471f29616cdd9baf1893df25807b71f985b6c94"),
)


def known_image(url: str, sha256: str) -> bool:
    return any((url, sha256) == (image.url, image.sha256) for image in IMAGE_CATALOGUE)


class CatalogueSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["catalogue"]
    url: str = Field(pattern=r"^https://[^\s]{1,500}$")
    sha256: Sha256

    @model_validator(mode="after")
    def matches_pin(self) -> Self:
        if not known_image(self.url, self.sha256):
            raise ValueError("Choose a catalogue image with its published SHA-256")
        return self


class UploadMedia(BaseModel):
    model_config = ConfigDict(extra="forbid")
    upload_id: str | None = Field(default=None, pattern=r"^upl_[0-9A-Z]{26}$")
    size_bytes: int = Field(gt=0, le=2048 * GIB)
    sha256: Sha256


class IsoSource(UploadMedia):
    kind: Literal["iso"]
    size_bytes: int = Field(gt=0, le=MAX_ISO_BYTES)


class DiskSource(UploadMedia):
    kind: Literal["disk"]


class DriversISO(UploadMedia):
    size_bytes: int = Field(gt=0, le=MAX_ISO_BYTES)


class MachineCreateParams(JsonBody):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=40, pattern=NAME_PATTERN)
    ram_mb: int = Field(ge=MIN_VM_MB, le=MAX_VM_MB)
    cpus: int = Field(ge=1, le=64)
    disk_gb: int = Field(ge=1, le=2048)
    # A cloud image the owner chose, fetched by CDI over HTTPS. The machine itself gets no network
    # beyond what the owner approves (default-deny below); only the import pod reaches this URL.
    # Preserve image_url-only requests and already queued actions from earlier clients.
    image_url: str | None = Field(default=None, pattern=r"^https://[^\s]{1,500}$")
    source: Annotated[CatalogueSource | IsoSource | DiskSource, Field(discriminator="kind")] | None = None
    firmware: Literal["bios", "uefi"] | None = None
    tpm: bool | None = None
    virtio_drivers: DriversISO | None = None
    network: Literal["isolated", "machine_peers"] | None = None
    _name_ok = field_validator("name")(_not_reserved)

    @model_validator(mode="after")
    def check_media(self) -> Self:
        if (self.image_url is None) == (self.source is None):
            raise ValueError("Choose exactly one machine image source")
        if isinstance(self.source, DiskSource) and self.source.size_bytes > self.disk_gb * GIB:
            raise ValueError("The disk image exceeds the requested disk capacity")
        if self.virtio_drivers and not isinstance(self.source, IsoSource):
            raise ValueError("A drivers ISO requires an installer ISO")
        if self.tpm and self.firmware != "uefi":
            raise ValueError("Select UEFI firmware to use the persistent TPM")
        return self


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
    templates, disks, volumes = [], [], []

    def add_disk(label: str, suffix: str, source: dict, capacity: str, device: dict) -> None:
        name = f"{p.name}-{suffix}"
        templates.append({"metadata": {"name": name}, "spec": {
            "source": source,
            "storage": {"accessModes": ["ReadWriteOnce"], "resources": {"requests": {"storage": capacity}}},
        }})
        disks.append({"name": label, **device})
        volumes.append({"name": label, "dataVolume": {"name": name}})

    if isinstance(p.source, CatalogueSource):
        root_source = {"http": {"url": p.source.url, "checksum": f"sha256:{p.source.sha256}"}}
    elif isinstance(p.source, DiskSource):
        root_source = {"upload": {}}
    elif isinstance(p.source, IsoSource):
        root_source = {"blank": {}}
    else:
        root_source = {"http": {"url": p.image_url}}
    add_disk("root", "disk", root_source, f"{p.disk_gb}Gi", {"disk": {"bus": "virtio"}, "bootOrder": 1})
    cdrom = {"cdrom": {"bus": "sata", "readonly": True}}
    if isinstance(p.source, IsoSource):
        # The empty disk falls through to the installer on first boot, then boots the installed OS.
        add_disk("installer", "installer", {"upload": {}}, str(p.source.size_bytes), {**cdrom, "bootOrder": 2})
    if p.virtio_drivers:
        add_disk("drivers", "drivers", {"upload": {}}, str(p.virtio_drivers.size_bytes), cdrom)

    domain = {
        "cpu": {"cores": p.cpus},
        # Equal requests and limits keep the VM inside the quota the owner approved.
        "resources": {"requests": {"memory": mem, "cpu": str(p.cpus)}, "limits": {"memory": mem, "cpu": str(p.cpus)}},
        "devices": {"disks": disks, "interfaces": [{"name": "default", "masquerade": {}}]},
    }
    if p.firmware == "uefi":
        domain["firmware"] = {"bootloader": {"efi": {"secureBoot": True, "persistent": True}}}
        domain["features"] = {"smm": {"enabled": True}}
    if p.tpm:
        domain["devices"]["tpm"] = {"persistent": True}
    return {
        "apiVersion": "kubevirt.io/v1", "kind": "VirtualMachine",
        "metadata": {"name": p.name, "namespace": NAMESPACE, "labels": {"onemind.io/machine": p.name}},
        "spec": {
            "runStrategy": "Halted",  # created stopped; `machine.start` is its own approved action
            "dataVolumeTemplates": templates,
            "template": {
                "metadata": {"labels": {"onemind.io/machine": p.name}},
                "spec": {
                    "domain": domain,
                    "networks": [{"name": "default", "pod": {}}],
                    "volumes": volumes,
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


def render_create(p: MachineCreateParams, *, media_action: str | None = None) -> str:
    """The objects `machine.create` applies, as one JSON document list (JSON is YAML)."""
    ns = {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": NAMESPACE}}
    policy = _deny_all(p.name)
    if p.network == "machine_peers":
        # A podSelector alone is scoped to this namespace. Both peers must allow the connection.
        peer = {"podSelector": {"matchExpressions": [{"key": "onemind.io/machine", "operator": "Exists"}]}}
        policy["spec"].update(ingress=[{"from": [peer]}], egress=[{"to": [peer]}])
    vm = _vm(p)
    if media_action:
        vm["metadata"]["labels"]["onemind.io/create-action"] = media_action
        for dv in vm["spec"]["dataVolumeTemplates"]:
            if "upload" in dv["spec"]["source"]:
                dv["metadata"]["annotations"] = {"cdi.kubevirt.io/storage.bind.immediate.requested": "true"}
    return json.dumps({"apiVersion": "v1", "kind": "List", "items": [ns, policy, vm]}, sort_keys=True)
