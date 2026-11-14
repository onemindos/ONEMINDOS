# SPDX-License-Identifier: Apache-2.0
"""Settings of the networking features: box names and HTTPS, the mesh, fabric joins.

Each is a PLUMBING §4 section (ONEMIND_<SECTION>_<FIELD>). deploy/install.sh writes them into
/etc/onemind/gateway.env; every default keeps a box without the mesh working as before.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .ca import BOX_RE, MESH_NETS, box_name_from_hostname
from .sections import config_section


@config_section("net")
@dataclass(frozen=True)
class NetSettings:
    box_name: str | None = None          # ONEMIND_NET_BOX_NAME: <box>.local; default: the hostname as a DNS label
    lan_addr: str | None = None          # ONEMIND_NET_LAN_ADDR: hub LAN IPv4 (mDNS records, join bundles)
    tls: bool = False                    # ONEMIND_NET_TLS=1: serve HTTPS with the box CA (H-05, §12.7)
    tls_dir: Path | None = None          # ONEMIND_NET_TLS_DIR: default <dir of ONEMIND_AUDIT_PATH>/tls
    https_host: str = "0.0.0.0"          # ONEMIND_NET_HTTPS_HOST
    https_ports: tuple[str, ...] = ("443", "8443")  # ONEMIND_NET_HTTPS_PORTS
    http_redirect_port: int = 0          # ONEMIND_NET_HTTP_REDIRECT_PORT: e.g. 80 -> https; 0 = off
    mdns: bool = False                   # ONEMIND_NET_MDNS=1: publish onemind.local and app names (avahi)
    path_routes: bool = False            # ONEMIND_NET_PATH_ROUTES=1: also /apps/<id>/ (see proxy.py)

    def validate(self) -> None:
        if self.box_name is not None and not BOX_RE.match(self.box_name):
            raise ValueError("ONEMIND_NET_BOX_NAME must be a lowercase DNS label")
        if self.lan_addr is not None:
            ip = ipaddress.ip_address(self.lan_addr)
            if ip.version != 4:
                raise ValueError("ONEMIND_NET_LAN_ADDR must be an IPv4 address")
        for p in self.https_ports:
            if not p.isdigit() or not 1 <= int(p) <= 65535:
                raise ValueError("ONEMIND_NET_HTTPS_PORTS must be a comma-separated list of ports")
        if not 0 <= self.http_redirect_port <= 65535:
            raise ValueError("ONEMIND_NET_HTTP_REDIRECT_PORT must be a port or 0")

    def box(self) -> str:
        return self.box_name or box_name_from_hostname(socket.gethostname())

    def box_domains(self) -> tuple[str, ...]:
        """Suffixes app hosts live under: <app>.onemind.local, <app>.<box>.local, <app>.apps.onemind.internal."""
        return ("onemind.local", f"{self.box()}.local", "apps.onemind.internal")


@config_section("mesh")
@dataclass(frozen=True)
class MeshSettings:
    enabled: bool = False                                # ONEMIND_MESH_ENABLED=1
    headscale_url: str = "http://127.0.0.1:8085"         # ONEMIND_MESH_HEADSCALE_URL (loopback only)
    headscale_key_file: Path | None = None               # ONEMIND_MESH_HEADSCALE_KEY_FILE (0600)
    # Until onemind-edge (CORE-NET-5) fronts it on :443, Headscale terminates TLS itself on :8444.
    control_url: str = "https://control.onemind.internal:8444"  # ONEMIND_MESH_CONTROL_URL
    hub_ip: str | None = None                            # ONEMIND_MESH_HUB_IP: the hub's mesh IPv4

    def validate(self) -> None:
        u = urlsplit(self.control_url)
        if u.scheme != "https" or not u.hostname:
            raise ValueError("ONEMIND_MESH_CONTROL_URL must be an https URL")
        if self.hub_ip is not None:
            ip = ipaddress.ip_address(self.hub_ip)
            if not any(ip in n for n in MESH_NETS):
                raise ValueError("ONEMIND_MESH_HUB_IP must be a mesh address (100.64.0.0/10)")
        if self.enabled and self.headscale_key_file is None:
            raise ValueError("ONEMIND_MESH_ENABLED=1 needs ONEMIND_MESH_HEADSCALE_KEY_FILE")
        if self.enabled and self.hub_ip is None:
            raise ValueError("ONEMIND_MESH_ENABLED=1 needs ONEMIND_MESH_HUB_IP")


@config_section("fabric")
@dataclass(frozen=True)
class FabricSettings:
    hub_url: str | None = None              # ONEMIND_FABRIC_HUB_URL: https URL nodes use to join
    nats_accounts_file: Path | None = None  # ONEMIND_FABRIC_NATS_ACCOUNTS_FILE: hub NATS include
    nats_leaf_port: int = 7422              # ONEMIND_FABRIC_NATS_LEAF_PORT
    k3s_ca_hash: str | None = None          # ONEMIND_FABRIC_K3S_CA_HASH: "K10<sha256 hex>" of k3s /cacerts
    k3s: bool = False                       # ONEMIND_FABRIC_K3S=1: workers get a 1-hour k3s bootstrap token
    max_pending: int = 20                   # ONEMIND_FABRIC_MAX_PENDING join requests at once

    def validate(self) -> None:
        if self.hub_url is not None and urlsplit(self.hub_url).scheme != "https":
            raise ValueError("ONEMIND_FABRIC_HUB_URL must be an https URL (nodes pin the box CA)")
        if self.k3s_ca_hash is not None and not (
            self.k3s_ca_hash.startswith("K10") and len(self.k3s_ca_hash) == 67
            and all(c in "0123456789abcdef" for c in self.k3s_ca_hash[3:])
        ):
            raise ValueError("ONEMIND_FABRIC_K3S_CA_HASH must be K10 followed by 64 lowercase hex")
