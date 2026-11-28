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

from .ca import BOX_RE, MESH_NETS, box_name_from_hostname, existing_box_name
from .netpath import parse_networks
from .sections import config_section


# Documentation ranges (RFC 5737, RFC 3849) count as public here so examples and tests can use them;
# Python's ip.is_global says False for them.
_DOC_NETS = tuple(ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "2001:db8::/32"))


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
    # ONEMIND_NET_TRUSTED_PROXIES: comma-separated CIDRs of edges whose X-OneMind-Path is believed
    # (netpath.py). Default none: only the socket peer decides the path.
    trusted_proxies: str = ""
    # ONEMIND_NET_HOST_SOCKET: the host service's socket (onemindd host serve), where the Network
    # screen reads the box's interfaces and listening ports (hostnet.py). Missing socket: the screen says so.
    host_socket: Path = Path("/run/onemind/host.sock")
    host_timeout_s: float = 5.0          # ONEMIND_NET_HOST_TIMEOUT_S
    # ONEMIND_NET_HOSTNAME_FILE (P-05): the name the owner gave the box (host kind set-hostname). The image's root is
    # read-only, so it lives on the data partition. When it holds a DNS label it wins over ONEMIND_NET_BOX_NAME
    # (written once at first boot), so the box certificate and the join QR follow a rename.
    hostname_file: Path = Path("/data/onemind/etc/hostname")
    # ONEMIND_NET_CHANGE_TIMEOUT_S (P-08): how long the gateway waits for the host service to apply a wired
    # address change (NetworkManager re-activates the connection, which can take most of a minute).
    change_timeout_s: float = 60.0
    # ONEMIND_NET_TOR_PORT (#284): a plain-HTTP listener whose every request is classified as the
    # Tor path. The Tor app's onion service forwards raw TCP to it (an onion origin is http://), and
    # the socket peer is then a pod or masqueraded address that looks like the LAN, so the path is
    # fixed by the listener, not guessed from the peer. 0 = off (the Tor app then gets no address).
    tor_port: int = 0

    def validate(self) -> None:
        if self.host_timeout_s <= 0:
            raise ValueError("ONEMIND_NET_HOST_TIMEOUT_S must be positive")
        if not 5 <= self.change_timeout_s <= 300:
            raise ValueError("ONEMIND_NET_CHANGE_TIMEOUT_S must be between 5 and 300")
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
        if not 0 <= self.tor_port <= 65535:
            raise ValueError("ONEMIND_NET_TOR_PORT must be a port or 0")
        if self.tor_port:
            if not self.tls:
                raise ValueError("ONEMIND_NET_TOR_PORT needs ONEMIND_NET_TLS=1 (the listener is started with the HTTPS ones)")
            if str(self.tor_port) in self.https_ports or self.tor_port == self.http_redirect_port:
                raise ValueError("ONEMIND_NET_TOR_PORT must differ from the HTTPS and redirect ports")
        try:
            parse_networks(self.trusted_proxies)
        except ValueError:
            raise ValueError("ONEMIND_NET_TRUSTED_PROXIES must be comma-separated CIDRs") from None

    def box(self) -> str:
        try:
            renamed = self.hostname_file.read_text(encoding="utf-8").strip()
        except (OSError, ValueError):
            renamed = ""
        if renamed and BOX_RE.match(renamed):
            return renamed
        return self.box_name or box_name_from_hostname(socket.gethostname())

    def tls_box(self, tls_dir: Path) -> str:
        """The box name for TLS: the one the existing CA was made with, else box(). A rename must not move the
        certificate's names outside that CA's name constraints (P-05)."""
        return existing_box_name(tls_dir) or self.box()

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
    # The owner's own relay (NETWORKING §4.4): its public IP, after the owner paired it. Unset: no
    # relay, and the box says so in the mesh view. It is only ever an address of the owner's machine.
    relay_addr: str | None = None                        # ONEMIND_MESH_RELAY_ADDR (public IP)

    def validate(self) -> None:
        u = urlsplit(self.control_url)
        if u.scheme != "https" or not u.hostname:
            raise ValueError("ONEMIND_MESH_CONTROL_URL must be an https URL")
        if self.hub_ip is not None:
            ip = ipaddress.ip_address(self.hub_ip)
            if not any(ip in n for n in MESH_NETS):
                raise ValueError("ONEMIND_MESH_HUB_IP must be a mesh address (100.64.0.0/10)")
        if self.relay_addr is not None:
            try:
                ip = ipaddress.ip_address(self.relay_addr)
            except ValueError:
                raise ValueError("ONEMIND_MESH_RELAY_ADDR must be an IP address") from None
            if not (ip.is_global or any(ip in n for n in _DOC_NETS)) or ip.is_multicast:
                raise ValueError("ONEMIND_MESH_RELAY_ADDR must be a public IP address (a relay is reached from outside)")
        if self.enabled and self.headscale_key_file is None:
            raise ValueError("ONEMIND_MESH_ENABLED=1 needs ONEMIND_MESH_HEADSCALE_KEY_FILE")
        if self.enabled and self.hub_ip is None:
            raise ValueError("ONEMIND_MESH_ENABLED=1 needs ONEMIND_MESH_HUB_IP")


@config_section("fabric")
@dataclass(frozen=True)
class FabricSettings:
    hub_url: str | None = None              # ONEMIND_FABRIC_HUB_URL: https URL nodes use to join
    nats_accounts_file: Path | None = None  # ONEMIND_FABRIC_NATS_ACCOUNTS_FILE: hub NATS include
    # CORE-SEC-4 (#161): directory of <service>.pub keys the hub account accepts (gateway, onemindd),
    # and the gateway's own seed file. Unset: the hub account keeps the passwordless loopback user.
    nats_service_keys: Path | None = None   # ONEMIND_FABRIC_NATS_SERVICE_KEYS
    nats_nkey_seed: Path | None = None      # ONEMIND_FABRIC_NATS_NKEY_SEED
    nats_leaf_port: int = 7422              # ONEMIND_FABRIC_NATS_LEAF_PORT
    # Hub JetStream (app event streams): the hub account's file-storage cap in bytes (0 = JetStream off for
    # the account) and the mount that holds the store, whose free space the gateway reports.
    jetstream_max_bytes: int = 0            # ONEMIND_FABRIC_JETSTREAM_MAX_BYTES
    jetstream_path: Path | None = None      # ONEMIND_FABRIC_JETSTREAM_PATH
    k3s_ca_hash: str | None = None          # ONEMIND_FABRIC_K3S_CA_HASH: "K10<sha256 hex>" of k3s /cacerts
    k3s: bool = False                       # ONEMIND_FABRIC_K3S=1: workers get a 1-hour k3s bootstrap token
    max_pending: int = 20                   # ONEMIND_FABRIC_MAX_PENDING join requests at once

    def validate(self) -> None:
        if self.jetstream_max_bytes < 0:
            raise ValueError("ONEMIND_FABRIC_JETSTREAM_MAX_BYTES must be 0 or more")
        if self.hub_url is not None and urlsplit(self.hub_url).scheme != "https":
            raise ValueError("ONEMIND_FABRIC_HUB_URL must be an https URL (nodes pin the box CA)")
        if self.k3s_ca_hash is not None and not (
            self.k3s_ca_hash.startswith("K10") and len(self.k3s_ca_hash) == 67
            and all(c in "0123456789abcdef" for c in self.k3s_ca_hash[3:])
        ):
            raise ValueError("ONEMIND_FABRIC_K3S_CA_HASH must be K10 followed by 64 lowercase hex")
