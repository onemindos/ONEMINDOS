# SPDX-License-Identifier: Apache-2.0
"""Host-port declarations and conflicts (contract §12.22, PD-11).

The default is no host port: every app is reached through the gateway. An app that must listen
on the host (DNS on 53/udp, a game server) declares `spec.hostPorts`. A declaration is checked
against the ports OneMind uses (`sdk/policy/host-ports.yaml`) and every other app's declaration:
in CI across the catalog, and here per node when an install is requested and again at approval.

Declaring a port does not let an app bind it: the install sandbox still refuses `hostPort` and
`hostNetwork` (F-05, F-01) until a reviewed exception exists. The declaration is what the owner
sees and what keeps two apps from claiming the same port.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

log = logging.getLogger("onemind.appstore")

PROTOCOLS = ("tcp", "udp")
MAX_HOST_PORTS = 10
_REPO_FILE = Path(__file__).resolve().parents[3] / "sdk" / "policy" / "host-ports.yaml"
_IMAGE_FILE = Path("/opt/onemind/sdk/policy/host-ports.yaml")
# The same list as sdk/policy/host-ports.yaml (a test keeps them equal); used when the file is
# not shipped next to the gateway.
BUILTIN_RESERVED: dict[tuple[int, str], str] = {
    (22, "tcp"): "ssh", (80, "tcp"): "edge-http", (443, "tcp"): "edge-https",
    (2379, "tcp"): "k3s-datastore", (2380, "tcp"): "k3s-datastore-peer", (3478, "udp"): "derp-stun",
    (4222, "tcp"): "nats", (5353, "udp"): "mdns", (6443, "tcp"): "k3s-api", (6444, "tcp"): "k3s-supervisor",
    (7422, "tcp"): "nats-leaf", (7480, "tcp"): "onemindd", (8080, "tcp"): "gateway",
    (8443, "tcp"): "gateway-https", (8472, "udp"): "flannel-vxlan", (10250, "tcp"): "kubelet",
    (41641, "udp"): "mesh-wireguard", (51820, "udp"): "flannel-wireguard", (51821, "udp"): "flannel-wireguard-v6",
}


@dataclass(frozen=True)
class HostPort:
    port: int
    protocol: str
    description: str

    @property
    def key(self) -> tuple[int, str]:
        return (self.port, self.protocol)

    def to_json(self) -> dict:
        return {"port": self.port, "protocol": self.protocol, "description": self.description}


def load_reserved(path: Path | None = None) -> dict[tuple[int, str], str]:
    path = path or next((p for p in (_REPO_FILE, _IMAGE_FILE) if p.is_file()), None)
    if path is None:
        return dict(BUILTIN_RESERVED)
    doc = yaml.safe_load(path.read_text())
    if not isinstance(doc, dict) or doc.get("schema") != "onemind.io/host-ports/v1":
        raise ValueError(f"{path.name}: schema must be onemind.io/host-ports/v1")
    out: dict[tuple[int, str], str] = {}
    for e in doc.get("reserved") or []:
        port, proto = e.get("port"), e.get("protocol")
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535 or proto not in PROTOCOLS:
            raise ValueError(f"{path.name}: bad reserved entry {e!r}")
        out[(port, proto)] = str(e.get("what") or "onemind")
    return out


def declared(manifest: dict) -> list[HostPort]:
    """The app's declarations. Malformed entries are skipped here (the schema refuses them in CI)."""
    spec = manifest.get("spec") if isinstance(manifest, dict) else None
    raw = spec.get("hostPorts") if isinstance(spec, dict) else None
    if not isinstance(raw, list):
        return []
    out = []
    for e in raw[:MAX_HOST_PORTS]:
        if not isinstance(e, dict):
            continue
        port, proto = e.get("port"), e.get("protocol")
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535 or proto not in PROTOCOLS:
            continue
        out.append(HostPort(port, proto, str(e.get("description") or "")))
    return out


def conflicts(
    app_id: str, manifest: dict, others: Mapping[str, dict], reserved: Mapping[tuple[int, str], str],
) -> list[dict]:
    """[{port, protocol, with}] for each declaration that OneMind or another app already holds.

    `others` are the manifests of the apps on the same node (installed or being installed).
    """
    out = []
    seen: set[tuple[int, str]] = set()
    held: dict[tuple[int, str], str] = {}
    for other_id, other in sorted(others.items()):
        if other_id == app_id:
            continue
        for hp in declared(other):
            held.setdefault(hp.key, other_id)
    for hp in declared(manifest):
        if hp.key in seen:
            out.append({"port": hp.port, "protocol": hp.protocol, "with": app_id})
            continue
        seen.add(hp.key)
        if hp.key in reserved:
            out.append({"port": hp.port, "protocol": hp.protocol, "with": f"onemind:{reserved[hp.key]}"})
        elif hp.key in held:
            out.append({"port": hp.port, "protocol": hp.protocol, "with": held[hp.key]})
    return out


def conflict_message(app_id: str, found: list[dict]) -> str:
    parts = [f"{c['port']}/{c['protocol']} (held by {c['with']})" for c in found]
    return f"app {app_id!r} declares host ports already in use on the node: {', '.join(parts)}"
