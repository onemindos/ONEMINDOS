# SPDX-License-Identifier: Apache-2.0
"""Per-box certificate authority (H-05; NETWORKING.md §9.4). Not mounted yet (CORE-NET-8): no importer.

On first start the box creates its own CA under the data dir (ECDSA P-256, 10 years) and issues
the server certificates the box presents on the LAN and the mesh:

- the gateway certificate: onemind.local, <box>.local, hub/control/join.onemind.internal;
- the apps wildcard: *.onemind.local, *.<box>.local, *.apps.onemind.internal.

The CA certificate carries X.509 name constraints (RFC 5280 §4.2.1.10) that permit only the
box's own names and the mesh address ranges, so a phone that trusts it cannot be fooled for any
other site even if the key leaked. The CA private key is written 0600 in a 0700 directory and
there is no function that returns it: only the CA *certificate* is exported (PEM/DER + sha256
fingerprint) for phones and laptops to install.
"""

from __future__ import annotations

import hashlib
import ipaddress
import os
import re
import stat
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CA_VALIDITY = timedelta(days=3652)
LEAF_VALIDITY = timedelta(days=365)
NODE_VALIDITY = timedelta(days=365)  # renewal (POST /v1/fabric/nodes/{id}/renew) is a follow-up
RENEW_BEFORE = timedelta(days=30)
CLOCK_SKEW = timedelta(minutes=5)  # backdate notBefore so a slightly slow phone clock still accepts
BOX_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
NODE_ID_RE = re.compile(r"^[a-z0-9]{1,32}$")
LAN_DOMAIN = "onemind.local"
MESH_DOMAIN = "onemind.internal"
# Mesh address ranges (Headscale defaults, NETWORKING §3).
MESH_NETS = (ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48"))

CA_KEY, CA_CERT = "ca.key", "ca.crt"


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class IssuedCert:
    name: str
    cert_path: Path
    key_path: Path
    not_after: datetime
    dns_names: tuple[str, ...]


class BoxCA:
    """The box CA and the server certificates it issues. One instance per tls directory."""

    def __init__(self, tls_dir: Path, box_name: str, *, clock: Callable[[], datetime] = _utcnow):
        if not BOX_RE.match(box_name):
            raise ValueError("box name must be a lowercase DNS label")
        self.dir = tls_dir
        self.box = box_name
        self.clock = clock
        self._lock = threading.Lock()
        self._key: ec.EllipticCurvePrivateKey | None = None
        self._cert: x509.Certificate | None = None

    # ---- names -------------------------------------------------------------------------------
    @property
    def box_domain(self) -> str:
        return f"{self.box}.local"

    def permitted_domains(self) -> tuple[str, ...]:
        # A DNS name constraint covers the name and every name under it.
        return (LAN_DOMAIN, self.box_domain, MESH_DOMAIN)

    def gateway_names(self) -> tuple[str, ...]:
        return (LAN_DOMAIN, self.box_domain, f"hub.{MESH_DOMAIN}", f"control.{MESH_DOMAIN}", f"join.{MESH_DOMAIN}")

    def wildcard_names(self) -> tuple[str, ...]:
        return (f"*.{LAN_DOMAIN}", f"*.{self.box_domain}", f"*.apps.{MESH_DOMAIN}")

    # ---- files -------------------------------------------------------------------------------
    def _path(self, name: str) -> Path:
        return self.dir / name

    def _prepare_dir(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.dir, 0o700)

    @staticmethod
    def _write(path: Path, data: bytes, mode: int) -> None:
        tmp = path.with_name(f".{path.name}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.chmod(tmp, mode)
        os.replace(tmp, path)

    @staticmethod
    def _check_private(path: Path) -> None:
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise PermissionError(f"{path.name} must not be readable by group or others (expected 0600)")

    # ---- CA ----------------------------------------------------------------------------------
    def ensure(self) -> x509.Certificate:
        """Load the CA, creating it on first start. Never replaces an existing CA."""
        with self._lock:
            if self._cert is not None:
                return self._cert
            key_path, cert_path = self._path(CA_KEY), self._path(CA_CERT)
            if key_path.exists() or cert_path.exists():
                if not (key_path.exists() and cert_path.exists()):
                    raise RuntimeError("box CA is incomplete (one of ca.key / ca.crt is missing); refusing to replace it")
                self._check_private(key_path)
                key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
                cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
                if not isinstance(key, ec.EllipticCurvePrivateKey) or key.public_key() != cert.public_key():
                    raise RuntimeError("box CA key does not match its certificate")
            else:
                self._prepare_dir()
                key, cert = self._new_ca()
                # Key first: a crash between the writes leaves an incomplete CA, which is refused
                # above rather than silently replaced.
                self._write(key_path, key.private_bytes(
                    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
                ), 0o600)
                self._write(cert_path, cert.public_bytes(serialization.Encoding.PEM), 0o644)
            self._key, self._cert = key, cert
            return cert

    def _new_ca(self) -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
        key = ec.generate_private_key(ec.SECP256R1())
        now = self.clock()
        name = x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "OneMind box"),
            x509.NameAttribute(NameOID.COMMON_NAME, f"OneMind {self.box} CA"),
        ])
        constraints = x509.NameConstraints(
            permitted_subtrees=[x509.DNSName(d) for d in self.permitted_domains()]
            + [x509.IPAddress(n) for n in MESH_NETS],
            excluded_subtrees=None,
        )
        ski = x509.SubjectKeyIdentifier.from_public_key(key.public_key())
        cert = (
            x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - CLOCK_SKEW).not_valid_after(now + CA_VALIDITY)
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(
                digital_signature=False, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
                encipher_only=False, decipher_only=False,
            ), critical=True)
            .add_extension(constraints, critical=True)
            .add_extension(ski, critical=False)
            .sign(key, hashes.SHA256())
        )
        return key, cert

    # ---- export (certificate only) --------------------------------------------------------------
    def ca_pem(self) -> bytes:
        return self.ensure().public_bytes(serialization.Encoding.PEM)

    def ca_der(self) -> bytes:
        """DER form, served as application/x-x509-ca-cert for phone install pages."""
        return self.ensure().public_bytes(serialization.Encoding.DER)

    def ca_fingerprint(self) -> str:
        """sha256 of the DER certificate, lowercase hex (shown in the pairing QR, pinned by nodes)."""
        return hashlib.sha256(self.ca_der()).hexdigest()

    # ---- server certificates --------------------------------------------------------------------
    def _check_names(self, dns_names: Iterable[str]) -> tuple[str, ...]:
        names = tuple(dns_names)
        if not names:
            raise ValueError("a certificate needs at least one name")
        allowed = self.permitted_domains()
        for n in names:
            bare = n[2:] if n.startswith("*.") else n
            if not any(bare == d or bare.endswith("." + d) for d in allowed):
                raise ValueError(f"{n!r} is outside the box CA's name constraints")
        return names

    def issue(self, name: str, dns_names: Iterable[str], *, ip_addresses: Iterable[str] = ()) -> IssuedCert:
        """Issue (or re-issue) a server certificate; key and cert land in <tls_dir>/<name>.{key,crt}."""
        if not BOX_RE.match(name):
            raise ValueError("certificate name must be a lowercase DNS label")
        names = self._check_names(dns_names)
        ips = tuple(ipaddress.ip_address(i) for i in ip_addresses)
        for ip in ips:
            if not any(ip in net for net in MESH_NETS):
                raise ValueError(f"{ip} is outside the box CA's address constraints (mesh ranges only)")
        ca_cert = self.ensure()
        with self._lock:
            assert self._key is not None
            key = ec.generate_private_key(ec.SECP256R1())
            now = self.clock()
            not_after = min(now + LEAF_VALIDITY, ca_cert.not_valid_after_utc)
            san = [x509.DNSName(n) for n in names] + [x509.IPAddress(i) for i in ips]
            cert = (
                x509.CertificateBuilder()
                .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0])]))
                .issuer_name(ca_cert.subject)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - CLOCK_SKEW).not_valid_after(not_after)
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(x509.KeyUsage(
                    digital_signature=True, content_commitment=False, key_encipherment=False,
                    data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
                    encipher_only=False, decipher_only=False,
                ), critical=True)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                .add_extension(x509.SubjectAlternativeName(san), critical=False)
                .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
                .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(self._key.public_key()), critical=False)
                .sign(self._key, hashes.SHA256())
            )
            key_path, cert_path = self._path(f"{name}.key"), self._path(f"{name}.crt")
            self._write(key_path, key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            ), 0o600)
            # The chain file holds leaf + CA so TLS servers can present the full chain.
            self._write(cert_path, cert.public_bytes(serialization.Encoding.PEM)
                        + ca_cert.public_bytes(serialization.Encoding.PEM), 0o644)
        return IssuedCert(name, cert_path, key_path, cert.not_valid_after_utc, names)

    def ensure_cert(self, name: str, dns_names: Iterable[str], *, ip_addresses: Iterable[str] = ()) -> IssuedCert:
        """Keep a certificate current: re-issue when missing, near expiry, or the names changed."""
        names = self._check_names(dns_names)
        ips = sorted(str(ipaddress.ip_address(i)) for i in ip_addresses)
        ca_cert = self.ensure()
        cert_path, key_path = self._path(f"{name}.crt"), self._path(f"{name}.key")
        if cert_path.exists() and key_path.exists():
            try:
                self._check_private(key_path)
                cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
                san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
                have = tuple(san.get_values_for_type(x509.DNSName))
                have_ips = sorted(str(i) for i in san.get_values_for_type(x509.IPAddress))
                fresh = cert.not_valid_after_utc - self.clock() > RENEW_BEFORE
                if fresh and sorted(have) == sorted(names) and have_ips == ips and cert.issuer == ca_cert.subject:
                    return IssuedCert(name, cert_path, key_path, cert.not_valid_after_utc, names)
            except (ValueError, x509.ExtensionNotFound, PermissionError):
                pass  # unreadable, wrong or too open: re-issue
        return self.issue(name, names, ip_addresses=ips)

    def https_names(self) -> tuple[str, ...]:
        """One certificate for the gateway's HTTPS listener: the box names and every app name."""
        return self.gateway_names() + self.wildcard_names()

    def ensure_https_cert(self) -> IssuedCert:
        return self.ensure_cert("https", self.https_names())

    def ensure_nats_cert(self, hub_mesh_ip: str) -> IssuedCert:
        """The hub's NATS leaf listener: nodes dial tls://<hub mesh ip>:7422, so the IP is a SAN."""
        return self.ensure_cert("nats", (f"hub.{MESH_DOMAIN}",), ip_addresses=(hub_mesh_ip,))

    def ensure_control_cert(self) -> IssuedCert:
        """Headscale's own TLS listener (control.onemind.internal) until onemind-edge fronts it."""
        return self.ensure_cert("control", (f"control.{MESH_DOMAIN}",))

    # ---- node certificates (contract §12.11) ------------------------------------------------------
    def sign_node_csr(self, csr_pem: bytes | str, node_id: str, *, validity: timedelta = NODE_VALIDITY) -> x509.Certificate:
        """Sign a joining node's CSR after the owner approved node.join.

        Only the CSR's public key is used: the subject and names are the box's choice
        (CN=node-<id>, SAN node-<id>.onemind.internal), never what the node asked for. The node's
        private key never leaves the node. The certificate is for TLS client and server use (the
        NATS leaf link presents it; FABRIC §3).
        """
        if not NODE_ID_RE.match(node_id):
            raise ValueError("node id must be lowercase letters and digits")
        if isinstance(csr_pem, str):
            csr_pem = csr_pem.encode()
        try:
            csr = x509.load_pem_x509_csr(csr_pem)
        except ValueError:
            raise ValueError("csr_pem is not a PEM certificate request") from None
        if not csr.is_signature_valid:
            raise ValueError("the certificate request's signature does not verify")
        pub = csr.public_key()
        if not isinstance(pub, ec.EllipticCurvePublicKey) or pub.curve.name != "secp256r1":
            raise ValueError("node keys must be ECDSA P-256")
        ca_cert = self.ensure()
        with self._lock:
            assert self._key is not None
            now = self.clock()
            name = f"node-{node_id}"
            cert = (
                x509.CertificateBuilder()
                .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
                .issuer_name(ca_cert.subject)
                .public_key(pub)
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - CLOCK_SKEW)
                .not_valid_after(min(now + validity, ca_cert.not_valid_after_utc))
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(x509.KeyUsage(
                    digital_signature=True, content_commitment=False, key_encipherment=False,
                    data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
                    encipher_only=False, decipher_only=False,
                ), critical=True)
                .add_extension(x509.ExtendedKeyUsage(
                    [ExtendedKeyUsageOID.CLIENT_AUTH, ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                .add_extension(x509.SubjectAlternativeName([x509.DNSName(f"{name}.{MESH_DOMAIN}")]), critical=False)
                .add_extension(x509.SubjectKeyIdentifier.from_public_key(pub), critical=False)
                .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(self._key.public_key()), critical=False)
                .sign(self._key, hashes.SHA256())
            )
        return cert

    def ensure_gateway_cert(self) -> IssuedCert:
        return self.ensure_cert("gateway", self.gateway_names())

    def ensure_wildcard_cert(self) -> IssuedCert:
        return self.ensure_cert("apps-wildcard", self.wildcard_names())


def box_name_from_hostname(hostname: str | None) -> str:
    """A DNS label for <box>.local from a hostname: lower case, [a-z0-9-], at most 63, never empty."""
    label = re.sub(r"[^a-z0-9-]+", "-", (hostname or "").split(".")[0].lower()).strip("-")[:63].strip("-")
    return label or "onemind"


def main(argv: list[str] | None = None) -> int:
    """`python -m onemind_core.ca`: what the installer runs (as the gateway's user) before NATS,
    Headscale and the gateway start, so their certificates exist. Prints the CA fingerprint."""
    import argparse

    ap = argparse.ArgumentParser(prog="python -m onemind_core.ca")
    ap.add_argument("--dir", required=True, type=Path, help="tls directory (the box CA lives here)")
    ap.add_argument("--box", required=True, help="box name (DNS label): <box>.local")
    ap.add_argument("--nats-ip", help="hub mesh IPv4: also issue the NATS leaf listener certificate")
    ap.add_argument("--control", action="store_true", help="also issue Headscale's control.onemind.internal certificate")
    args = ap.parse_args(argv)
    box = BoxCA(args.dir, args.box)
    box.ensure_https_cert()
    if args.nats_ip:
        box.ensure_nats_cert(args.nats_ip)
    if args.control:
        box.ensure_control_cert()
    print(box.ca_fingerprint())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
