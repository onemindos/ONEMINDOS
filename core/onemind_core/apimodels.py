# SPDX-License-Identifier: Apache-2.0
"""Response shapes published in /openapi.json for the SDKs (docs/leap/dev/SDK.md §3.2, DEV-SDK-1).

These models document what the routes already return; the routes attach them through
`responses={200: {"model": ...}}`, which describes the body without filtering it, so adding a
model here never changes a response. Enums that may grow (action state, node status) are plain
strings marked `x-onemind-open-enum`: an SDK must accept a value it does not know.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

OPEN_ENUM = {"x-onemind-open-enum": True}


class Healthz(BaseModel):
    ok: bool


class Instance(BaseModel):
    """GET /v1/instance."""

    name: str
    version: str
    hub_node_id: str | None


class InstanceName(BaseModel):
    """GET /v1/instance/name: the box name alone, readable before sign-in."""

    name: str


class PrincipalRef(BaseModel):
    """{id, kind, role} of contract §3; kind and role may gain values (§12.1). An action's
    `requested_by` carries only {id, kind} (§12.4), so role is optional."""

    model_config = ConfigDict(extra="allow")
    id: str
    kind: str = Field(json_schema_extra=OPEN_ENUM)
    role: str | None = Field(default=None, json_schema_extra=OPEN_ENUM)


class NodeOS(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str | None = None
    version_id: str | None = None
    pretty: str | None = None


class NodeK3s(BaseModel):
    model_config = ConfigDict(extra="allow")
    present: bool | None = None
    role: str | None = None
    ready: bool | None = None


# ---- the hardware profile (NodeCapabilities, #618; internal/heartbeat/capabilities.go) ----------
# Every field may be null, which means "could not be read on that machine", never "no" or zero. A
# list is null when the machine had nothing to read it from and [] when it read and found none.
#
# Unlike the rest of this file these models are also the gateway's gate: nodes.py validates every
# heartbeat's profile against NodeCapabilities and drops the profile when it does not fit. NATS has
# no users yet (H-06), so a LAN publisher could otherwise plant fake accelerators or device paths
# that VM grants and app verdicts read. Hence: no extra fields (a new field is a new schema
# version), strict types, and pinned formats. Naming rule: `device` is always a full /dev path,
# `id` and `*_id` are always "vvvv:pppp", `*port` is a USB port path.

PROFILE_SCHEMA = "onemind.node.capabilities/v1"
MAX_LISTED = 64  # the Go probe's maxListed
VID_PID = r"^[0-9a-f]{4}:[0-9a-f]{4}$"
PCI_SLOT = r"^[0-9a-f]{4,8}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]$"
USB_PORT = r"^[0-9]+-[0-9]+(\.[0-9]+)*$"
HEX2 = r"^[0-9a-f]{2}$"
ACCEL_DEVICE = r"^/dev/(hailo[0-9]+|accel/accel[0-9]+)$"
CAMERA_DEVICE = r"^/dev/video[0-9]+$"
SHORT = 128  # model, driver and sensor names


class _Profile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class NodeDataDisk(_Profile):
    kind: str | None = Field(default=None, max_length=16, description="nvme | ssd | hdd | sd | emmc | usb | virtual", json_schema_extra=OPEN_ENUM)
    ssd: bool | None = None


class NodeMemoryProfile(_Profile):
    total_mb: int | None = Field(default=None, ge=0)
    unified: bool | None = Field(default=None, description="the main GPU uses system RAM (Jetson, Intel iGPU only)")


class NodeAccelerator(_Profile):
    class_: str = Field(alias="class", max_length=16, description="gpu | npu", json_schema_extra=OPEN_ENUM)
    vendor: str = Field(max_length=16, description="nvidia | amd | intel | hailo", json_schema_extra=OPEN_ENUM)
    model: str | None = Field(default=None, max_length=SHORT)
    pci_id: str | None = Field(default=None, pattern=VID_PID, description="PCI vendor:device id vvvv:dddd (which kind of card); null when not on PCI")
    pci_slot: str | None = Field(default=None, pattern=PCI_SLOT, description="PCI address dddd:bb:dd.f (which card; what a VFIO grant binds); null when not on PCI")
    driver: str | None = Field(default=None, max_length=SHORT)
    driver_version: str | None = Field(default=None, max_length=SHORT)
    vram_mb: int | None = Field(default=None, ge=0)
    compute_capability: str | None = Field(default=None, pattern=r"^[0-9]+\.[0-9]+$", description="NVIDIA major.minor")
    integrated: bool | None = None
    device: str | None = Field(default=None, pattern=ACCEL_DEVICE, description="full path of the device node an app is granted, e.g. /dev/hailo0")


class NodeUSBDevice(_Profile):
    port: str = Field(pattern=USB_PORT, description="kernel port path, e.g. 1-1.2")
    id: str = Field(pattern=VID_PID, description="vvvv:pppp")
    class_: str | None = Field(default=None, alias="class", pattern=HEX2, description="bDeviceClass, two hex digits")
    interface_classes: list[Annotated[str, Field(pattern=HEX2)]] = Field(default_factory=list, max_length=32)


class NodeTTYPort(_Profile):
    name: str = Field(pattern=r"^tty(USB|ACM|AMA|THS|S)[0-9]+$")
    kind: str = Field(max_length=16, description="usb | uart", json_schema_extra=OPEN_ENUM)
    usb_id: str | None = Field(default=None, pattern=VID_PID, description="vvvv:pppp of the USB device behind it; null for an on-board UART")
    usb_port: str | None = Field(default=None, pattern=USB_PORT)


# The known USB dongle kinds (sdk/schema/onemind.radios.json, #732). Such a radio's interface is its
# USB serial line and its device the stable name udev gave it, /dev/onemind/<kind><n>: the only path a
# grant (#854) ever passes into an app. wifi, bluetooth and cellular radios carry no device.
SERIAL_RADIO_KINDS = ("zigbee", "zigbee-thread", "lora")
USB_TTY = r"^tty(USB|ACM)[0-9]+$"
RADIO_DEVICE = r"^/dev/onemind/(zigbee|zigbee-thread|lora)([0-9]|1[0-5])$"
# A radio's stable id: the machine's node id, a dot, the stable name's last part (3f9c2a1b7d4e.lora0).
RADIO_ID = r"^[A-Za-z0-9_-]{1,64}\.(zigbee|zigbee-thread|lora)([0-9]|1[0-5])$"


class NodeRadio(_Profile):
    kind: str = Field(max_length=16, description="wifi | bluetooth | cellular | zigbee | zigbee-thread | lora", json_schema_extra=OPEN_ENUM)
    interface: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,15}$", description="the network interface (wlan0, hci0), or for a USB dongle its serial line (ttyUSB0)")
    device: str | None = Field(default=None, pattern=RADIO_DEVICE, description="a USB dongle's stable name, /dev/onemind/<kind><n> (lora0); absent for wifi, bluetooth and cellular")

    @model_validator(mode="after")
    def _dongle_is_a_named_usb_tty(self):
        if self.kind in SERIAL_RADIO_KINDS:
            if not re.match(USB_TTY, self.interface):
                raise ValueError(f"a {self.kind} radio's interface must be a USB serial line")
            if self.device is None or re.match(RADIO_DEVICE, self.device).group(1) != self.kind:
                raise ValueError(f"a {self.kind} radio needs its own /dev/onemind/{self.kind}<n> name")
        elif self.device is not None:
            raise ValueError("only a known USB dongle has a /dev/onemind name")
        return self


class NodeCamera(_Profile):
    bus: str = Field(max_length=16, description="usb | csi", json_schema_extra=OPEN_ENUM)
    device: str | None = Field(default=None, pattern=CAMERA_DEVICE, description="full path of the video node, e.g. /dev/video0; null for a CSI sensor")
    name: str | None = Field(default=None, max_length=SHORT)
    usb_id: str | None = Field(default=None, pattern=VID_PID, description="vvvv:pppp of a USB camera")


class NodePowerProfile(_Profile):
    source: str | None = Field(default=None, max_length=16, description="mains | battery | usb", json_schema_extra=OPEN_ENUM)
    battery_pct: int | None = Field(default=None, ge=0, le=100)
    undervoltage: bool | None = None


class NodeThermalProfile(_Profile):
    max_c: float | None = None
    state: str | None = Field(default=None, max_length=16, description="normal | passive | hot | critical", json_schema_extra=OPEN_ENUM)


DRIVER_NAME = r"^[A-Za-z0-9_.-]{1,32}$"


class NodeIOMMUGroup(_Profile):
    group: int = Field(ge=0, description="the kernel's IOMMU group number (/sys/kernel/iommu_groups/N)")
    devices: list[Annotated[str, Field(pattern=PCI_SLOT)]] = Field(max_length=32, description="PCI addresses in the group")


class NodePassthrough(_Profile):
    """What a VM device grant reads (#690). Present only when the kernel runs with an IOMMU (VT-d, AMD-Vi)."""

    iommu_groups: list[NodeIOMMUGroup] = Field(max_length=MAX_LISTED, description="the groups that hold an accelerator")
    usb_drivers: dict[Annotated[str, Field(pattern=USB_PORT)], list[Annotated[str, Field(pattern=DRIVER_NAME)]]] = Field(
        max_length=MAX_LISTED, description="USB port -> drivers bound to its interfaces; a port that is not a key has none")


class NodeCapabilities(_Profile):
    """The machine's hardware profile, sent in its heartbeat; read with nodes:read only."""

    schema_: Literal["onemind.node.capabilities/v1"] = Field(alias="schema")
    data_disk: NodeDataDisk
    memory: NodeMemoryProfile
    accelerators: list[NodeAccelerator] | None = Field(max_length=MAX_LISTED)
    usb: list[NodeUSBDevice] | None = Field(max_length=MAX_LISTED)
    tty_ports: list[NodeTTYPort] | None = Field(max_length=MAX_LISTED)
    radios: list[NodeRadio] | None = Field(max_length=MAX_LISTED)
    cameras: list[NodeCamera] | None = Field(max_length=MAX_LISTED)
    power: NodePowerProfile
    thermal: NodeThermalProfile
    passthrough: NodePassthrough | None = Field(default=None, description="absent without an IOMMU: no device can be passed to a machine (#690)")


class RadioConfirmation(BaseModel):
    """What the owner confirms on a radio's card before anything may open it (#732; the grant is #854)."""

    profile: str = Field(description="meshcore-companion-usb", json_schema_extra=OPEN_ENUM)
    label: str = Field(description="what the card asks, e.g. MeshCore companion (USB)")
    confirmed: bool = Field(description="true once an owner confirmed this radio on this machine and USB port; kept across gateway restarts and replugs into the same port, asked again on another port")
    confirmed_at: str | None = None


class RadioCard(BaseModel):
    """One radio-found card (GET /v1/radios, #732): a USB serial line on a machine, from its latest heartbeat.

    A known radio has a kind and its stable name `device`; any other USB serial line is listed with
    kind and device null: never named, never granted. Unplugging removes the card with the next heartbeat.
    OneMind never probes a radio: kind and model come from the USB ids alone.
    """

    id: str | None = Field(pattern=RADIO_ID, description="the radio's stable id, <node_id>.<kind><n> (3f9c2a1b7d4e.lora0), used by /v1/radios/{id}/...; null when not a known radio")
    node_id: str
    hostname: str | None = None
    node_status: str = Field(description="online | stale | offline", json_schema_extra=OPEN_ENUM)
    kind: str | None = Field(description="zigbee | zigbee-thread | lora; null: not a known radio", json_schema_extra=OPEN_ENUM)
    model: str | None = Field(description="from sdk/schema/onemind.radios.json; null when unknown or several products share the id")
    match: str | None = Field(description="product: the USB id and product string name the product | id: a generic USB-serial chip, the id alone proves nothing; null when unknown", json_schema_extra=OPEN_ENUM)
    tty: str = Field(pattern=USB_TTY, description="the kernel's name for the serial line, e.g. ttyUSB0")
    device: str | None = Field(pattern=RADIO_DEVICE, description="the stable name, /dev/onemind/<kind><n>; null when not named")
    usb_id: str | None = Field(pattern=VID_PID, description="vvvv:pppp")
    usb_port: str | None = Field(pattern=USB_PORT, description="kernel port path, e.g. 1-1.2")
    confirm: RadioConfirmation | None = Field(description="the owner's confirmation this kind needs before a grant; null when none is needed")


class RadioConfirmRequest(BaseModel):
    """POST /v1/radios/{id}/confirm: an owner says the radio with this id is this profile."""

    model_config = ConfigDict(extra="forbid")
    profile: Literal["meshcore-companion-usb"]


class Node(BaseModel):
    """One node: the §2 heartbeat plus the gateway's `status` and `last_seen`. More fields may appear."""

    model_config = ConfigDict(extra="allow")
    schema_: str | None = Field(default=None, alias="schema")
    node_id: str
    hostname: str | None = None
    role: str | None = None
    board: str | None = Field(default=None, json_schema_extra=OPEN_ENUM)
    arch: str | None = None
    os: NodeOS | None = None
    k3s: NodeK3s | None = None
    capabilities: NodeCapabilities | None = Field(default=None, description="hardware profile (#618); absent from older agents")
    status: str = Field(description="online | stale | offline", json_schema_extra=OPEN_ENUM)
    presence: str | None = Field(default=None, description="online | offline: the fast view for live screens "
                                 "(#608). Offline once a heartbeat is clearly missed (14 s) or at once after a "
                                 "clean shutdown. Absent from older gateways", json_schema_extra=OPEN_ENUM)
    departed_at: str | None = Field(default=None, description="RFC 3339 time the node announced a clean "
                                    "shutdown; null while it is running or after it came back")
    last_seen: str = Field(description="RFC 3339 time the gateway last received a heartbeat")


class ApprovalLimit(BaseModel):
    """One limit shown on an approval card, with its unit (#723). The gateway and the device check it again."""

    name: str
    value: str | int | float | bool
    unit: str | None = None


class ApprovalPreview(BaseModel):
    """The approval card's preview slot (#723): what the action will do, drawn by the host."""

    kind: str = Field(description="what the preview is, e.g. image or path", json_schema_extra=OPEN_ENUM)
    ref: str | None = None
    text: str | None = None


class ApprovalCard(BaseModel):
    """The approval card of every action (#723). The host draws it, never an app.

    hold is true for an action that cannot be undone (risk destructive) or that moves something
    physical; physical says which. A physical card also carries limits and a preview and is part of
    plan_sha256.
    """

    physical: bool = Field(description="moves or switches something physical: passkey, hold, never standing or automated")
    hold: bool = Field(description="approve with hold-to-approve (physical, or cannot be undone)")
    hold_ms: int | None = Field(default=None, description="how long to hold, in ms; send at least this as hold_ms")
    limits: list[ApprovalLimit] = Field(default_factory=list)
    preview: ApprovalPreview | None = None


class Action(BaseModel):
    """One action of the ledger (contract §3). §12.4 adds optional fields; ignore what you do not know."""

    model_config = ConfigDict(extra="allow")
    id: str
    type: str = Field(description="app.install | app.remove | app.start | app.stop | app.restart | app.update | app.configure | app.delete_data (more in §12.5)", json_schema_extra=OPEN_ENUM)
    params: dict[str, Any]
    state: str = Field(
        description="requested | awaiting_approval | accepted | dispatched | succeeded | failed | "
        "cancelled | expired | outcome_unknown",
        json_schema_extra=OPEN_ENUM,
    )
    requested_by: PrincipalRef
    idempotency_key: str
    created_at: str
    updated_at: str
    expires_at: str
    decided_by: PrincipalRef | None
    decided_at: str | None
    approved_by: str | None = Field(default=None, description="Approving person's id; null before approval or on denial. decided_by/decided_at are retained.")
    result: dict[str, Any] | None
    version: int
    risk: str | None = Field(default=None, description="read | write | sensitive | destructive | actuate (§12.3)")
    plan: dict[str, Any] | None = Field(default=None, description="§12.4: what the action would do, rendered at request time")
    plan_sha256: str | None = Field(default=None, description="§12.4: fingerprint the approval is bound to")
    progress: dict[str, Any] | None = Field(default=None, description="{step, pct} while an executor runs")
    approval: ApprovalCard | None = Field(default=None, description="#723: the approval card; set on every action (hold for destructive or physical)")
    required_level: Literal["L1", "L2", "L3"] | None = Field(default=None, description="D-028: the key level approving this needs now (awaiting_approval only, when read by a person); approve-options says the same and whether the box's code is needed")


class AuditRecord(BaseModel):
    """One hash-chained audit line (contract §3 "Audit", §12.16)."""

    seq: int
    ts: str
    event: str
    principal: PrincipalRef | None
    action_id: str | None
    data: dict[str, Any]
    prev_hash: str
    hash: str


class AuditHead(BaseModel):
    seq: int
    hash: str


class AuditVerify(BaseModel):
    """GET /v1/audit/verify (§12.16). `last_checkpoint` stays null until signed checkpoints ship (H-10)."""

    ok: bool
    records: int
    head: AuditHead | None
    first_bad_seq: int | None
    reason: str
    checked_at: str
    last_checkpoint: dict[str, Any] | None


class PlanPreview(BaseModel):
    """GET /v1/apps/{id}/plan and POST /v1/plans (contract §12.4): what an action would do. Files nothing."""

    type: str = Field(description="the action type previewed", json_schema_extra=OPEN_ENUM)
    app_id: str
    risk: str = Field(description="read | write | sensitive | destructive | actuate (§12.3)", json_schema_extra=OPEN_ENUM)
    policy_verdict: str = Field(
        description="needs_approval | refused (the app is in a state this action cannot start from)",
        json_schema_extra=OPEN_ENUM,
    )
    reason: str | None = Field(description="why the verdict is refused; null otherwise")
    plan: dict[str, Any] = Field(description="summary, objects, volumes, warnings: what the approval card shows")
    plan_sha256: str = Field(description="send this with the request and the approval; a different plan is refused")


class AppCredentials(BaseModel):
    """GET /v1/apps/{id}/credentials: the app's generated login. Owner only, audited, never cached."""

    username: str | None
    password: str


class AboutNode(BaseModel):
    """One box in GET /v1/os/about. Never carries a serial number or an address."""

    node_id: str
    hostname: str | None = None
    role: str | None = None
    board: str | None = Field(default=None, json_schema_extra=OPEN_ENUM)
    arch: str | None = None
    status: str = Field(description="online | stale | offline", json_schema_extra=OPEN_ENUM)
    last_seen: str | None = None
    os_pretty: str | None = Field(default=None, description="The Debian base, from /etc/os-release")
    os_id: str | None = None
    os_version_id: str | None = None
    onemind_version: str | None = Field(default=None, description="The update service's current version")
    agent_version: str | None = None
    booted_slot: str | None = Field(default=None, description="The RAUC A/B slot this box booted from")
    kernel: str | None = None
    cpu_model: str | None = None
    cpus: int | None = None
    mem_total_mb: int | None = None
    mem_available_mb: int | None = None
    disk_total_gb: float | None = None
    disk_free_gb: float | None = None
    uptime_s: int | None = None


class About(BaseModel):
    """GET /v1/os/about."""

    hub_node_id: str | None
    node_count: int
    nodes: list[AboutNode]



class PlacementReason(BaseModel):
    """Why a node cannot run an app (`blocking`), or runs it with a warning."""

    code: str = Field(description="gpu_missing | gpu_unknown | memory_too_small | memory_busy | cpu_level_too_low | "
                                  "arch_unsupported | node_offline | node_stale | no_cluster | cluster_not_ready",
                      json_schema_extra=OPEN_ENUM)
    message: str
    blocking: bool


class NodePlacement(BaseModel):
    """One node's line in the placement (contract §12.11)."""

    node_id: str
    role: str | None = Field(json_schema_extra=OPEN_ENUM)
    verdict: str = Field(description="fits | fits_with_warning | no", json_schema_extra=OPEN_ENUM)
    labels: dict[str, str] = Field(description="capability labels from the node's heartbeat (onemind.io/gpu, /arch, ...)")
    reasons: list[PlacementReason]


class MachineFit(BaseModel):
    node_id: str
    verdict: Literal["yes", "yes-but-slow", "not-on-this-machine", "not-checked"]
    reasons: list[str]


class MachineFitReport(BaseModel):
    nodes: list[MachineFit]
    passing_nodes: list[str]


class AppPlacement(BaseModel):
    """GET /v1/apps/{id}/placement (CORE-FABRIC-4): where the app would run, from its `spec.requires`."""

    app_id: str
    verdict: str = Field(description="here | elsewhere | nowhere | unknown (no node has reported)", json_schema_extra=OPEN_ENUM)
    node_id: str | None = Field(description="the node it would be placed on; null for nowhere and unknown")
    message: str
    nodes: list[NodePlacement]
    fit: MachineFitReport | None = None
