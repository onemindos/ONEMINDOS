# SPDX-License-Identifier: Apache-2.0
"""ca.py: the per-box CA is created once, constrained to the box's names, and keeps its key private."""

from __future__ import annotations

import os
import stat
from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509 import verification
from cryptography.x509.oid import NameOID

from onemind_core import ca as ca_mod
from onemind_core.ca import BoxCA


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def box(tmp_path, clock):
    return BoxCA(tmp_path / "tls", "box1", clock=clock)


def mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def verify_chain(box: BoxCA, cert_path, hostname: str, when: datetime):
    pems = x509.load_pem_x509_certificates(cert_path.read_bytes())
    store = verification.Store([x509.load_pem_x509_certificate(box.ca_pem())])
    verifier = verification.PolicyBuilder().store(store).time(when).build_server_verifier(
        verification.DNSName(hostname))
    return verifier.verify(pems[0], pems[1:])


def test_created_once_with_private_key(box, tmp_path):
    cert = box.ensure()
    key_path, dir_ = tmp_path / "tls" / "ca.key", tmp_path / "tls"
    assert mode(key_path) == 0o600 and mode(dir_) == 0o700
    assert isinstance(cert.public_key(), ec.EllipticCurvePublicKey)
    assert cert.public_key().curve.name == "secp256r1"
    bc = cert.extensions.get_extension_for_class(x509.BasicConstraints)
    assert bc.critical and bc.value.ca and bc.value.path_length == 0
    assert (cert.not_valid_after_utc - cert.not_valid_before_utc) >= timedelta(days=3650)
    # a second instance (restart) loads the same CA, never a new one
    again = BoxCA(tmp_path / "tls", "box1").ensure()
    assert again.fingerprint(hashes.SHA256()) == cert.fingerprint(hashes.SHA256())


def test_name_constraints(box):
    nc = box.ensure().extensions.get_extension_for_class(x509.NameConstraints)
    assert nc.critical
    dns = sorted(n.value for n in nc.value.permitted_subtrees if isinstance(n, x509.DNSName))
    ips = sorted(str(n.value) for n in nc.value.permitted_subtrees if isinstance(n, x509.IPAddress))
    assert dns == ["box1.local", "onemind.internal", "onemind.local"]
    assert ips == ["100.64.0.0/10", "fd7a:115c:a1e0::/48"]


def test_export_is_certificate_only(box):
    pem, der = box.ca_pem(), box.ca_der()
    assert pem.startswith(b"-----BEGIN CERTIFICATE-----") and b"PRIVATE" not in pem
    assert x509.load_der_x509_certificate(der).fingerprint(hashes.SHA256()).hex() == box.ca_fingerprint()
    assert not any("key" in n and n.startswith(("ca_", "export")) for n in dir(box))


def test_gateway_and_wildcard_certs_verify(box, clock):
    gw = box.ensure_gateway_cert()
    wc = box.ensure_wildcard_cert()
    assert mode(gw.key_path) == 0o600 and mode(wc.key_path) == 0o600
    when = clock.now + timedelta(days=1)
    for host in ("onemind.local", "box1.local", "hub.onemind.internal", "control.onemind.internal"):
        verify_chain(box, gw.cert_path, host, when)
    for host in ("uptime-kuma.onemind.local", "whoami.box1.local", "notes.apps.onemind.internal"):
        verify_chain(box, wc.cert_path, host, when)
    with pytest.raises(verification.VerificationError):
        verify_chain(box, wc.cert_path, "example.com", when)


def test_ca_cannot_vouch_for_other_sites(box, tmp_path, clock):
    """Even with the CA key (the leak case), a cert for another site fails the name constraints."""
    box.ensure()
    ca_key = serialization.load_pem_private_key((tmp_path / "tls" / "ca.key").read_bytes(), None)
    ca_cert = x509.load_pem_x509_certificate(box.ca_pem())
    key = ec.generate_private_key(ec.SECP256R1())
    rogue = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "bank.example")]))
        .issuer_name(ca_cert.subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(clock.now).not_valid_after(clock.now + timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("bank.example")]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    path = tmp_path / "rogue.crt"
    path.write_bytes(rogue.public_bytes(serialization.Encoding.PEM))
    with pytest.raises(verification.VerificationError) as exc:
        verify_chain(box, path, "bank.example", clock.now + timedelta(days=1))
    assert "constraint" in str(exc.value).lower()


def test_issue_refuses_names_outside_constraints(box):
    for names in (["example.com"], ["*.local"], ["onemind.local.example.com"], []):
        with pytest.raises(ValueError):
            box.issue("bad", names)
    with pytest.raises(ValueError):
        box.issue("bad", ["onemind.local"], ip_addresses=["192.0.2.10"])
    ok = box.issue("mesh", ["hub.onemind.internal"], ip_addresses=["100.64.0.1"])
    assert ok.dns_names == ("hub.onemind.internal",)


def test_renewal(box, clock):
    first = box.ensure_gateway_cert()
    serial = x509.load_pem_x509_certificate(first.cert_path.read_bytes()).serial_number
    assert box.ensure_gateway_cert().cert_path.read_bytes() == first.cert_path.read_bytes()  # fresh: kept
    clock.now += timedelta(days=340)  # inside the 30-day renewal window
    renewed = box.ensure_gateway_cert()
    assert x509.load_pem_x509_certificate(renewed.cert_path.read_bytes()).serial_number != serial
    assert renewed.not_after > first.not_after


def test_loose_key_permissions_refused(box, tmp_path):
    box.ensure()
    os.chmod(tmp_path / "tls" / "ca.key", 0o644)
    with pytest.raises(PermissionError):
        BoxCA(tmp_path / "tls", "box1").ensure()


def test_incomplete_ca_is_not_replaced(box, tmp_path):
    box.ensure()
    (tmp_path / "tls" / "ca.crt").unlink()
    with pytest.raises(RuntimeError):
        BoxCA(tmp_path / "tls", "box1").ensure()
    assert (tmp_path / "tls" / "ca.key").exists()


def test_box_name_validated(tmp_path):
    for bad in ("Box", "a.b", "-x", ""):
        with pytest.raises(ValueError):
            BoxCA(tmp_path, bad)
    assert ca_mod.LAN_DOMAIN == "onemind.local"


def test_https_cert_names_loopback_and_the_lan_address(tmp_path, clock):
    """App pods and local tools dial the gateway by address (https://<LAN address>:8443, https://127.0.0.1:8443),
    so the HTTPS certificate carries both addresses and a client verifies them against the box CA."""
    box = BoxCA(tmp_path / "tls", "box1", lan_addr="198.51.100.1", clock=clock)
    cert = box.ensure_https_cert()
    san = x509.load_pem_x509_certificate(cert.cert_path.read_bytes()).extensions.get_extension_for_class(
        x509.SubjectAlternativeName).value
    assert sorted(str(i) for i in san.get_values_for_type(x509.IPAddress)) == ["127.0.0.1", "198.51.100.1"]
    pems = x509.load_pem_x509_certificates(cert.cert_path.read_bytes())
    store = verification.Store([x509.load_pem_x509_certificate(box.ca_pem())])
    when = clock.now + timedelta(days=1)
    for ip in ("127.0.0.1", "198.51.100.1"):
        verifier = verification.PolicyBuilder().store(store).time(when).build_server_verifier(
            verification.IPAddress(__import__("ipaddress").ip_address(ip)))
        verifier.verify(pems[0], pems[1:])
    # an address that is not the box's is not vouched for
    verifier = verification.PolicyBuilder().store(store).time(when).build_server_verifier(
        verification.IPAddress(__import__("ipaddress").ip_address("203.0.113.9")))
    with pytest.raises(verification.VerificationError):
        verifier.verify(pems[0], pems[1:])
