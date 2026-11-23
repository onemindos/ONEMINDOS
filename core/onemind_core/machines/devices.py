# SPDX-License-Identifier: Apache-2.0
"""Device grants: a USB device or a GPU passed through to a machine, approved by the owner (#690).

`machine.attach_device` and `machine.detach_device` are feature actions on the same ledger as the
other machine actions (service.py): an owner or an agent may request one, only an owner approves,
no standing approval covers an attach (risk sensitive), and nothing reaches the cluster before an
approval. The facts come from the machine's node hardware profile (#618, internal/detect): its USB
devices, its accelerators, and the `passthrough` section the probe adds when the kernel runs with an
IOMMU. There is no second detector.

Refusals, each a 409 policy_refused with a reason the owner can read, at the request and again at
approval:
- `device_busy`: a kernel driver on the host holds the device (a keyboard's usbhid, a stick's
  usb-storage, a GPU's i915 or nvidia) until the owner sets `confirm_busy`;
- `owner_confirms`: an agent set `confirm_busy`; taking a device from the host is the owner's word;
- `iommu_group_shared`: the GPU's IOMMU group holds another card's device, so passing it through
  would hand that device to the machine too (even with `confirm_busy`);
- `iommu_off`, `no_profile`, `device_unknown`, `iommu_group_unknown`, `already_granted`,
  `device_granted` (another machine holds it), `machine_unknown`, `not_granted` (detach).

What runs after approval: KubeVirt's `permittedHostDevices` lists every granted device (by
vendor:device id, the only selector KubeVirt has) and the machine's VirtualMachine lists its own
under `gpus` and `hostDevices`. KubeVirt reads those when the machine's instance starts, so a grant
applies the next time the machine starts. A GPU must also be bound to vfio-pci on the host; that is
the lab kit's step (lab-kits/LT-MACH-DEV-01), not the gateway's. Machines stay gated off on real
hardware until LT-MACH-2.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import DateTime, String, delete, select, update
from sqlalchemy.orm import Mapped, mapped_column

from ..actions import FeatureAction
from ..apimodels import PCI_SLOT, USB_PORT
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError
from ..executors import ExecResult
from ..ledger import Base, iso
from ..store import SqlRepository
from .runtime import KubectlRuntime
from .spec import NAME_PATTERN, NAMESPACE

APPLIES = "next_start"
FREE_GPU_DRIVERS = frozenset({"vfio-pci"})  # a card bound to vfio-pci is waiting for a machine, not used by the host


class GrantRow(Base):
    """One device granted to one machine. The key is the device, so two machines never hold it."""
    __tablename__ = "machines_device_grants"
    node_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(8), primary_key=True)  # usb | gpu
    device: Mapped[str] = mapped_column(String(16), primary_key=True)  # USB port path or PCI address
    machine: Mapped[str] = mapped_column(String(40))
    hw_id: Mapped[str] = mapped_column(String(9))  # vvvv:pppp, what KubeVirt selects by
    state: Mapped[str] = mapped_column(String(12))  # pending | granted | unknown
    action_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def to_json(self) -> dict:
        return {"node_id": self.node_id, "kind": self.kind, "device": self.device, "machine": self.machine,
                "hw_id": self.hw_id, "state": self.state, "created_at": iso(self.created_at)}


class GrantsRepository(SqlRepository):
    def all(self) -> list[dict]:
        with self.db.session() as s:
            return [r.to_json() for r in s.scalars(select(GrantRow).order_by(GrantRow.created_at, GrantRow.device))]

    def get(self, node_id: str, kind: str, device: str) -> dict | None:
        with self.db.session() as s:
            row = s.get(GrantRow, (node_id, kind, device))
            return row.to_json() if row else None

    def put(self, row: GrantRow) -> None:
        """Insert, or take over a row whose machine is gone (the caller checked under its lock)."""
        with self.db.session.begin() as s:
            s.merge(row)

    def set_state(self, node_id: str, kind: str, device: str, state: str, action_id: str) -> None:
        with self.db.session.begin() as s:
            s.execute(update(GrantRow).where(GrantRow.node_id == node_id, GrantRow.kind == kind, GrantRow.device == device,
                                             GrantRow.action_id == action_id).values(state=state))

    def remove(self, node_id: str, kind: str, device: str, *, action_id: str | None = None) -> None:
        with self.db.session.begin() as s:
            q = delete(GrantRow).where(GrantRow.node_id == node_id, GrantRow.kind == kind, GrantRow.device == device)
            if action_id:
                q = q.where(GrantRow.action_id == action_id)
            s.execute(q)


class DeviceRefParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=40, pattern=NAME_PATTERN, description="the machine")
    kind: Literal["usb", "gpu"]
    device: str = Field(max_length=16, description="usb: the port path (1-2); gpu: the PCI address (0000:01:00.0)")

    @model_validator(mode="after")
    def _device_fits_kind(self):
        if not re.match(USB_PORT if self.kind == "usb" else PCI_SLOT, self.device):
            raise ValueError(f"device: not a {'USB port path' if self.kind == 'usb' else 'PCI address'}")
        return self


class DeviceAttachParams(DeviceRefParams):
    confirm_busy: bool = Field(default=False, description="the owner confirms taking a device the host is using")


class DeviceRefusal(BaseModel):
    code: str = Field(description="device_busy | iommu_group_shared | iommu_off | device_granted | ...")
    message: str


class MachineDevice(BaseModel):
    """One USB device or GPU of the machine's box, as a grant sees it."""
    kind: Literal["usb", "gpu"]
    device: str = Field(description="usb: port path; gpu: PCI address")
    id: str | None = Field(description="vvvv:pppp")
    vendor: str | None
    model: str | None
    drivers: list[str] | None = Field(description="host drivers holding it; null when unknown")
    busy: bool = Field(description="the host is using it (or it cannot be told): a grant needs the owner's confirmation")
    granted_to: str | None = Field(description="the machine that has it")
    refusal: DeviceRefusal | None = Field(description="why a grant to this machine is refused now; null when it can be asked")


class MachineDevices(BaseModel):
    machine: str
    node_id: str
    iommu: bool = Field(description="the box runs with an IOMMU (VT-d, AMD-Vi); without it nothing can be granted")
    applies: Literal["next_start"] = Field(description="when a grant or a release takes effect")
    devices: list[MachineDevice]


# ---- what KubeVirt is told ---------------------------------------------------------------
def resource_name(g: dict) -> str:
    return f"onemind.io/{g['kind']}-{g['hw_id'].replace(':', '-')}"


def kubevirt_patch(grants: list[dict]) -> dict:
    """The merge patch for the KubeVirt CR: every granted device, and nothing else, is permitted."""
    pci, usb = {}, {}
    for g in grants:
        rn = resource_name(g)
        if g["kind"] == "gpu":
            pci[rn] = {"pciVendorSelector": g["hw_id"].upper(), "resourceName": rn}
        else:
            vendor, product = g["hw_id"].split(":")
            usb[rn] = {"resourceName": rn, "selectors": [{"vendor": vendor, "product": product}]}
    return {"spec": {"configuration": {"permittedHostDevices": {
        "pciHostDevices": [pci[k] for k in sorted(pci)], "usb": [usb[k] for k in sorted(usb)]}}}}


def vm_patch(grants: list[dict]) -> dict:
    """The merge patch for one VirtualMachine: its own granted devices (read when it next starts)."""
    gpus = [g for g in grants if g["kind"] == "gpu"]
    usbs = [g for g in grants if g["kind"] == "usb"]
    return {"spec": {"template": {"spec": {"domain": {"devices": {
        "gpus": [{"name": f"gpu{i}", "deviceName": resource_name(g)} for i, g in enumerate(gpus)],
        "hostDevices": [{"name": f"usb{i}", "deviceName": resource_name(g)} for i, g in enumerate(usbs)]}}}}}}


class DeviceRuntime(Protocol):
    def apply(self, machine: str, everyone: list[dict], mine: list[dict]) -> ExecResult: ...


class NoopDevices:
    def apply(self, machine: str, everyone: list[dict], mine: list[dict]) -> ExecResult:
        return ExecResult("succeeded", f"noop: devices of {machine} not changed", [
            {"would": "patch KubeVirt permittedHostDevices", "patch": kubevirt_patch(everyone)},
            {"would": f"patch VirtualMachine {machine} devices", "patch": vm_patch(mine)}])


class KubectlDevices(KubectlRuntime):
    def apply(self, machine: str, everyone: list[dict], mine: list[dict]) -> ExecResult:
        steps: list[dict] = []
        k = self.kubectl
        bad = (self._run(steps, [k, "patch", "kubevirt", "kubevirt", "-n", "kubevirt", "--type", "merge", "-p",
                                 json.dumps(kubevirt_patch(everyone))])
               or self._run(steps, [k, "patch", "virtualmachine", machine, "-n", NAMESPACE, "--type", "merge", "-p",
                                    json.dumps(vm_patch(mine))]))
        return bad or ExecResult("succeeded", f"devices of {machine} changed", steps)


# ---- the grants --------------------------------------------------------------------------
def _devices(node: dict) -> list[dict]:
    """The devices a node could pass through, from its hardware profile, with who holds them on the host."""
    caps = node.get("capabilities") or {}
    pt = caps.get("passthrough")
    drivers = (pt or {}).get("usb_drivers") or {}
    out = []
    for u in caps.get("usb") or []:
        held = drivers.get(u["port"], []) if pt else None
        out.append({"kind": "usb", "device": u["port"], "id": u["id"], "vendor": None, "model": None, "drivers": held})
    for a in caps.get("accelerators") or []:
        if a.get("class") == "gpu" and a.get("pci_slot"):
            out.append({"kind": "gpu", "device": a["pci_slot"], "id": a.get("pci_id"), "vendor": a.get("vendor"),
                        "model": a.get("model"), "drivers": [a["driver"]] if a.get("driver") else []})
    return out


def _busy(d: dict) -> bool:
    held = d["drivers"]
    if held is None:
        return True  # unknown counts as busy: the owner confirms
    return bool([x for x in held if x not in FREE_GPU_DRIVERS] if d["kind"] == "gpu" else held)


def _group_peers(node: dict, slot: str) -> list[str] | None:
    """Devices of other cards in the GPU's IOMMU group ([] when it is alone); None when no group lists it."""
    card = slot.rsplit(".", 1)[0]  # functions of one card (VGA, HDMI audio) travel together
    for g in ((node.get("capabilities") or {}).get("passthrough") or {}).get("iommu_groups") or []:
        if slot in g["devices"]:
            return [d for d in g["devices"] if d.rsplit(".", 1)[0] != card]
    return None


class DeviceGrants:
    def __init__(self, gw: Gateway, machines, runtime: DeviceRuntime | None = None):
        self.gw, self.machines = gw, machines
        self.repo = GrantsRepository(gw.db)
        s = gw.settings
        self.runtime: DeviceRuntime = runtime or (
            NoopDevices() if s.executor == "noop" else KubectlDevices(s.kubectl, timeout_s=s.executor_timeout_s))
        self._lock = threading.Lock()

    def _live(self) -> list[dict]:
        """Grants whose machine still exists (a deleted machine's grant holds nothing)."""
        return [g for g in self.repo.all() if self.machines.repo.get(g["machine"]) is not None]

    def _holder(self, node_id: str, kind: str, device: str) -> str | None:
        g = self.repo.get(node_id, kind, device)
        return g["machine"] if g and self.machines.repo.get(g["machine"]) is not None else None

    def _verdict(self, machine: str, node: dict, d: dict, confirm: bool, requester: dict | None) -> tuple[str, str] | None:
        holder = self._holder(node["node_id"], d["kind"], d["device"])
        if holder == machine:
            return "already_granted", f"{machine} already has this device."
        if holder is not None:
            return "device_granted", f"Machine {holder} has this device. Take it back from {holder} first."
        if not d["id"]:
            return "device_unknown", "This card did not report its vendor and device id, so it cannot be passed through."
        if d["kind"] == "gpu":
            peers = _group_peers(node, d["device"])
            if peers is None:
                return "iommu_group_unknown", "This card is in no IOMMU group the box reported, so it cannot be passed through safely."
            if peers:
                return "iommu_group_shared", ("This card shares its IOMMU group with " + ", ".join(peers) + ", which would go to the "
                                              "machine too. Move the card to another slot, or pick a board that isolates it.")
        if _busy(d) and not confirm:
            held = ", ".join(d["drivers"] or []) or "an unknown driver"
            return "device_busy", (f"The host is using this device ({held}). Confirm to hand it to {machine}; "
                                   "the host loses it when the machine next starts.")
        return None

    def problem(self, verb: str, params: dict, requester: dict | None) -> tuple[str, str] | None:
        name, kind, dev = params["name"], params["kind"], params["device"]
        if verb == "attach" and params.get("confirm_busy") and (requester or {}).get("kind") != "person":
            return "owner_confirms", "Only the owner can confirm taking a device the host is using. File it without confirm_busy."
        row = self.machines.repo.get(name)
        if row is None:
            return "machine_unknown", f"There is no machine named {name}."
        if verb == "detach":
            return None if self._holder(row["node_id"], kind, dev) == name else ("not_granted", f"{name} does not have this device.")
        node = self.gw.registry.get(row["node_id"])
        if node is None or not node.get("capabilities"):
            return "no_profile", "The machine's box has not reported its hardware yet."
        if not node["capabilities"].get("passthrough"):
            return "iommu_off", ("This box has no IOMMU switched on, so no device can be passed to a machine. "
                                 "Turn on VT-d (Intel) or AMD-Vi / IOMMU (AMD) in the firmware settings.")
        d = next((x for x in _devices(node) if x["kind"] == kind and x["device"] == dev), None)
        if d is None:
            return "device_unknown", f"The box does not report a {'USB device on port' if kind == 'usb' else 'GPU at'} {dev}."
        return self._verdict(name, node, d, bool(params.get("confirm_busy")), requester)

    def inventory(self, name: str) -> dict:
        row = self.machines.repo.get(name)
        if row is None:
            raise ApiError(404, "not_found", f"There is no machine named {name}.")
        node = self.gw.registry.get(row["node_id"]) or {"node_id": row["node_id"]}
        iommu = bool((node.get("capabilities") or {}).get("passthrough"))
        out = []
        for d in _devices(node):
            why = self._verdict(name, node, d, False, None) if iommu else (
                "iommu_off", "Turn on VT-d (Intel) or AMD-Vi / IOMMU (AMD) in the firmware settings.")
            out.append({**d, "busy": _busy(d), "granted_to": self._holder(row["node_id"], d["kind"], d["device"]),
                        "refusal": None if why is None or why[0] == "already_granted" else {"code": why[0], "message": why[1]}})
        return {"machine": name, "node_id": row["node_id"], "iommu": iommu, "applies": APPLIES, "devices": out}

    # ---- the actions ----------------------------------------------------------------------
    def _check_request(self, verb: str):
        def check(params: dict, principal: Principal) -> None:
            if verb == "attach" and params.get("confirm_busy") and not principal.is_owner:
                raise ApiError(409, "policy_refused", "Only the owner can confirm taking a device the host is using.",
                               reason="owner_confirms")
            if (found := self.problem(verb, params, principal.as_dict())) is not None:
                raise ApiError(409, "policy_refused", found[1], reason=found[0])
        return check

    def _recheck(self, verb: str):
        def check(a) -> str | None:
            found = self.problem(verb, a.params, a.requested_by)
            return found[1] if found else None
        return check

    def _claim(self, a) -> str | None:
        with self._lock:  # two approved grants never take the same device
            if (found := self.problem("attach", a.params, a.requested_by)) is not None:
                return found[1]
            p, row = a.params, self.machines.repo.get(a.params["name"])
            d = next(x for x in _devices(self.gw.registry.get(row["node_id"])) if x["kind"] == p["kind"] and x["device"] == p["device"])
            self.repo.put(GrantRow(node_id=row["node_id"], kind=p["kind"], device=p["device"], machine=p["name"], hw_id=d["id"],
                                   state="pending", action_id=a.id, created_at=self.gw.clock()))
            return None

    def _release(self, a) -> None:
        """A grant that surely did nothing is handed back; an unknown outcome keeps the device booked."""
        final = self.gw.actions.repo.get(a.id)
        row = self.machines.repo.get(a.params["name"])
        if row is None or (final is not None and final.state == "succeeded"):
            return
        key = (row["node_id"], a.params["kind"], a.params["device"])
        if final is not None and final.state == "outcome_unknown":
            self.repo.set_state(*key, "unknown", a.id)
        else:
            self.repo.remove(*key, action_id=a.id)

    def _apply(self, name: str, grants: list[dict]) -> ExecResult:
        return self.runtime.apply(name, grants, [g for g in grants if g["machine"] == name])

    def _run_attach(self, a, finish) -> None:
        name = a.params["name"]
        res = self._apply(name, self._live())
        if res.outcome == "succeeded":
            row = self.machines.repo.get(name)
            self.repo.set_state(row["node_id"], a.params["kind"], a.params["device"], "granted", a.id)
            res.message = f"{res.message}. The device moves to {name} the next time {name} starts."
        finish(res)

    def _run_detach(self, a, finish) -> None:
        name, kind, dev = a.params["name"], a.params["kind"], a.params["device"]
        node_id = self.machines.repo.get(name)["node_id"]
        res = self._apply(name, [g for g in self._live() if (g["node_id"], g["kind"], g["device"]) != (node_id, kind, dev)])
        if res.outcome == "succeeded":
            self.repo.remove(node_id, kind, dev)
            res.message = f"{res.message}. The host gets the device back the next time {name} starts."
        finish(res)

    def register(self, requesters: frozenset[str]) -> None:
        acts = self.gw.actions
        acts.register_type("machine.attach_device", FeatureAction(
            "sensitive", self._run_attach, requesters, check=self._recheck("attach"), params_model=DeviceAttachParams,
            check_request=self._check_request("attach"), claim=self._claim, release=self._release))
        acts.register_type("machine.detach_device", FeatureAction(
            "write", self._run_detach, requesters, check=self._recheck("detach"), params_model=DeviceRefParams,
            check_request=self._check_request("detach")))
