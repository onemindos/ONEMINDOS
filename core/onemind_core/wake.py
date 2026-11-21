# SPDX-License-Identifier: Apache-2.0
"""Known-node Wake-on-LAN; packet delivery does not prove the machine is awake.

An administrator provisions ONEMIND_WAKE_TARGETS_FILE locally as JSON:
{node_id: {"mac": "<unicast MAC>", "network": "<RFC1918 LAN CIDR>"}}.
No targets by default. Never derive MACs or destinations from heartbeats or requests.
The hub must be on that LAN; UDP/9 broadcast is not a routed/mesh wake relay.
"""
from __future__ import annotations

import hashlib
import json
import re
import socket
from dataclasses import dataclass
from ipaddress import IPv4Network
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .actions import FeatureAction
from .errors import ApiError
from .executors import ExecResult
from .sections import config_section


@config_section("wake")
@dataclass(frozen=True)
class WakeSettings:
    targets_file: Path | None = None


class WakeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    target_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class WakeCapability(BaseModel):
    available: bool
    reason: str
    params: WakeParams | None = None


@dataclass(frozen=True)
class Target:
    mac: bytes
    broadcast: str

    def fingerprint(self, node_id: str) -> str:
        return hashlib.sha256(node_id.encode() + self.mac + self.broadcast.encode()).hexdigest()


def load_target(path: Path | None, node_id: str) -> Target | None:
    """Fail closed, including malformed config; never log local addresses or MACs."""
    if path is None:
        return None
    try:
        with path.open("rb") as source:
            raw = source.read(65537)
        if len(raw) > 65536:
            return None
        row = json.loads(raw)[node_id]
        if not isinstance(row, dict) or set(row) != {"mac", "network"}:
            return None
        if not isinstance(row["mac"], str) or not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", row["mac"]):
            return None
        mac = bytes.fromhex(row["mac"].replace(":", ""))
        if not any(mac) or mac[0] & 1:  # refuse zero, multicast and broadcast MACs
            return None
        network = IPv4Network(row["network"], strict=True)
        a, b, *_ = network.network_address.packed
        private = a == 10 or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168)
        if not private or not 16 <= network.prefixlen <= 30:
            return None
        return Target(mac, str(network.broadcast_address))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def send_packet(packet: bytes, destination: tuple[str, int]) -> None:
    """One bounded UDP send, never retries. Tests replace this transport, never send on a LAN."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as transport:
        transport.settimeout(2)
        transport.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        if transport.sendto(packet, destination) != len(packet):
            raise OSError("incomplete wake packet")


class WakeService:
    def __init__(self, gw):
        self.gw = gw
        self.path = gw.settings.section(WakeSettings).targets_file
        gw.actions.register_type("node.wake", FeatureAction(
            risk="actuate", requesters=frozenset({"person", "agent"}), params_model=WakeParams,
            check_request=self.check_request, check=lambda a: self.problem(a.params), run=self.run,
        ))

    def target(self, node_id: str) -> Target | None:
        if self.gw.registry.get(node_id) is None:
            return None
        return load_target(self.path, node_id)

    def capability(self, node_id: str) -> WakeCapability:
        target = self.target(node_id)
        if target is None:
            return WakeCapability(available=False, reason="No valid configured wake target for this known node")
        return WakeCapability(available=True, reason="Owner approval sends one wake packet; wait for a fresh heartbeat",
                              params=WakeParams(node_id=node_id, target_sha256=target.fingerprint(node_id)))

    def problem(self, params: dict) -> str | None:
        target = self.target(params["node_id"])
        if target is None or target.fingerprint(params["node_id"]) != params["target_sha256"]:
            return "Wake target unavailable or changed; refresh the node and request again"
        return None

    def check_request(self, params, _principal):
        if problem := self.problem(params):
            raise ApiError(409, "stale_precondition", problem)

    def run(self, action, finish):
        # Re-resolve immediately before dispatch: config revocation/changes never retarget approval.
        target = self.target(action.params["node_id"])
        if target is None or target.fingerprint(action.params["node_id"]) != action.params["target_sha256"]:
            finish(ExecResult("failed", "Wake target changed after approval; no packet sent"))
            return
        try:
            send_packet(b"\xff" * 6 + target.mac * 16, (target.broadcast, 9))
        except OSError:
            finish(ExecResult("outcome_unknown", "Wake packet delivery unconfirmed; no automatic retry"))
            return
        finish(ExecResult("succeeded", "Wake packet sent; awake status requires a fresh node heartbeat"))
