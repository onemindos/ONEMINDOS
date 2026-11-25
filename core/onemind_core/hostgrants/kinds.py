# SPDX-License-Identifier: Apache-2.0
"""What a host grant can name, and what an active set of grants lets the sandbox allow.

Each grant is exactly one thing, so the owner's approval card shows exactly what the app gets:

| kind           | names                                   | lets the sandbox allow (policy.py)            |
|----------------|-----------------------------------------|-----------------------------------------------|
| `device`       | one device node of a class below        | a hostPath volume of that path, CharDevice    |
| `gpu`          | one GPU render node under /dev/dri      | a hostPath volume of that path, CharDevice    |
| `host-network` | nothing more                            | `hostNetwork: true` (F-01)                    |
| `realtime`     | nothing more                            | `capabilities.add: [SYS_NICE]` (F-07)         |

Nothing else moves: privileged (F-06), hostPID/hostIPC (F-02, F-03), hostPort (F-05), any other
host path and any other capability stay refused for every app, granted or not. NVIDIA GPUs keep
going through the scheduler's resource request (placement.py), not through a host path.

Pure module: no I/O, no imports from the gateway, so policy.py can import it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

KINDS = ("device", "gpu", "host-network", "realtime")

# Device classes and the exact node paths each one may name. One path per grant, never a folder:
# /dev/serial/by-id names survive a replug, /dev/ttyUSB0 is what most add-on guides use.
DEVICE_CLASSES: dict[str, tuple[re.Pattern[str], ...]] = {
    # Zigbee, Z-Wave, Thread and other USB serial sticks (Home Assistant, Zigbee2MQTT, Z-Wave JS).
    "usb-serial": (
        re.compile(r"/dev/tty(?:USB|ACM)[0-9]{1,3}"),
        re.compile(r"/dev/serial/by-id/[A-Za-z0-9][A-Za-z0-9._:+-]{0,199}"),
    ),
    # One raw USB device by bus and device number (an SDR dongle, a Coral accelerator).
    "usb": (re.compile(r"/dev/bus/usb/[0-9]{3}/[0-9]{3}"),),
    # One V4L2 camera or capture card.
    "video": (re.compile(r"/dev/video[0-9]{1,3}"),),
}
GPU_PATHS = (re.compile(r"/dev/dri/renderD[0-9]{3}"), re.compile(r"/dev/dri/card[0-9]{1,2}"))
REALTIME_CAPABILITIES = frozenset({"SYS_NICE"})
# The hostPath type a granted node must carry: kubelet then checks it is a character device.
DEVICE_HOSTPATH_TYPE = "CharDevice"


def problem(kind: str, device_class: str | None, path: str | None) -> str | None:
    """Why this grant shape is refused, or None when it names exactly one allowed thing."""
    if kind not in KINDS:
        return f"kind must be one of {', '.join(KINDS)}"
    if kind == "device":
        patterns = DEVICE_CLASSES.get(device_class or "")
        if patterns is None:
            return f"a device grant needs device_class, one of {', '.join(DEVICE_CLASSES)}"
        if not isinstance(path, str) or not any(p.fullmatch(path) for p in patterns):
            return f"path is not one {device_class} device node"
        return None
    if device_class is not None:
        return f"a {kind} grant takes no device_class"
    if kind == "gpu":
        if not isinstance(path, str) or not any(p.fullmatch(path) for p in GPU_PATHS):
            return "a gpu grant names one node under /dev/dri (renderD<n> or card<n>)"
        return None
    if path is not None:
        return f"a {kind} grant takes no path"
    return None


@dataclass(frozen=True)
class HostAllowance:
    """What one app's active grants let its pods use. The empty allowance allows nothing."""

    device_paths: frozenset[str] = frozenset()
    host_network: bool = False
    add_capabilities: frozenset[str] = frozenset()

    def __bool__(self) -> bool:
        return bool(self.device_paths or self.host_network or self.add_capabilities)

    @classmethod
    def of(cls, grants: Iterable[tuple[str, str | None]]) -> HostAllowance:
        """From (kind, path) pairs of active grants."""
        paths: set[str] = set()
        host_network = False
        caps: set[str] = set()
        for kind, path in grants:
            if kind in ("device", "gpu") and path:
                paths.add(path)
            elif kind == "host-network":
                host_network = True
            elif kind == "realtime":
                caps |= REALTIME_CAPABILITIES
        return cls(frozenset(paths), host_network, frozenset(caps))

    def allows_host_path(self, host_path: object) -> bool:
        """A pod's volumes[].hostPath is allowed only as exactly a granted node, typed CharDevice."""
        return (isinstance(host_path, dict) and set(host_path) <= {"path", "type"}
                and host_path.get("type") == DEVICE_HOSTPATH_TYPE and host_path.get("path") in self.device_paths)

    def to_json(self) -> dict:
        """The plan entry: an install approval is bound to the grants that were active at render."""
        return {"device_paths": sorted(self.device_paths), "host_network": self.host_network,
                "add_capabilities": sorted(self.add_capabilities)}


NO_HOST = HostAllowance()
