#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check a YubiKey PIV attestation: proof that a root key was MADE ON the device and can never leave it.

A YubiKey can sign a small certificate about one of its own keys (`ykman piv keys attest 9c attest.pem`).
That certificate is signed by the device's attestation key (slot f9, `ykman piv certificates export f9
f9.pem`), whose certificate is in turn signed by Yubico's PIV attestation CA. It says, about the key in
the slot: its public key, that it was generated on the device (an imported key gets no attestation), the
device's serial and firmware, and the key's PIN and touch policy.

This checks, offline, for one holder's key:
  1. the attestation certificate is signed by the f9 certificate, and that one by --ca: Yubico's PIV
     root CA, downloaded and compared BEFORE the ceremony (see os/update/CEREMONY.md). The CA is
     REQUIRED: without it anyone's software can mint an f9-style certificate for an imported key, so
     the check would prove nothing. Only the spare-YubiKey trial may skip it, with --no-ca-spare-trial,
     and the result then says so on every line that matters;
  2. its public key is the exact key in <holder>.pub (the one that goes into root.json);
  3. the device serial in the attestation is the YubiKey that was meant (--serial);
  4. the PIN policy and touch policy are the ones asked for (default: always and always).

    python3 os/update/piv-attest.py --pub a.pub --attestation a-attest.pem --chain a-f9.pem \
        --ca yubico-piv-ca.pem [--serial 12345678] [--pin-policy always] [--touch-policy always]

Prints the device serial, firmware and policies (public values) and exits 1 on any problem.

Source of the extension layout: Yubico, "PIV attestation" (developers.yubico.com/PIV/Introduction/
PIV_attestation.html): OID 1.3.6.1.4.1.41482.3.3 firmware (3 bytes), .3.7 serial (DER INTEGER), .3.8
policy (2 bytes: PIN policy 1=never 2=once 3=always, touch policy 1=never 2=always 3=cached), .3.9 form
factor. UNVERIFIED on real hardware by an agent: the ceremony's spare-key trial is the first real check.
Needs only `cryptography` (pinned in os/update/requirements-tuf.txt).
"""
import argparse, sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

OID_FIRMWARE = x509.ObjectIdentifier("1.3.6.1.4.1.41482.3.3")
OID_SERIAL = x509.ObjectIdentifier("1.3.6.1.4.1.41482.3.7")
OID_POLICY = x509.ObjectIdentifier("1.3.6.1.4.1.41482.3.8")
PIN_POLICY = {1: "never", 2: "once", 3: "always"}
TOUCH_POLICY = {1: "never", 2: "always", 3: "cached"}


def _certs(path):
    data = open(path, "rb").read()
    if b"-----BEGIN" in data:
        return x509.load_pem_x509_certificates(data)
    return [x509.load_der_x509_certificate(data)]


def _ext(cert, oid):
    try:
        return cert.extensions.get_extension_for_oid(oid).value.value      # UnrecognizedExtension: raw bytes
    except x509.ExtensionNotFound:
        return None


def _der_int(raw):
    """A DER INTEGER (tag 0x02) as an int; None when it is not one."""
    if not raw or raw[0] != 0x02 or len(raw) < 3 or raw[1] != len(raw) - 2:
        return None
    return int.from_bytes(raw[2:], "big")


def _spki(key):
    return key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


def check(pub_path, attestation, chain, ca=None, pin_policy="always", touch_policy="always", serial=None,
          allow_no_ca=False):
    """Returns (lines to print, problems). Nothing is trusted that does not chain to `chain` and `ca`.
    No `ca` is a problem unless allow_no_ca (the spare-YubiKey trial only), which is then said loudly."""
    lines, problems = [], []
    att = _certs(attestation)[0]
    links = [c for p in chain for c in _certs(p)]
    if not links:
        return lines, ["no f9 (attestation) certificate given"]
    issuer = att
    for nxt in links:                                  # attestation -> f9 -> (more intermediates) ...
        try:
            issuer.verify_directly_issued_by(nxt)
        except Exception as e:
            problems.append(f"{issuer.subject.rfc4514_string()} is not signed by {nxt.subject.rfc4514_string()}: {e}")
            break
        issuer = nxt
    if ca:
        if not any(_ok_issued(issuer, r) for r in _certs(ca)):
            problems.append(f"the chain does not end at the CA in {ca} (last link: {issuer.subject.rfc4514_string()})")
        else:
            lines.append(f"chain ends at the CA in {ca}")
    elif allow_no_ca:
        lines.append("WARNING: SPARE TRIAL ONLY: no Yubico CA given, so the f9 certificate is not checked; this key "
                     "must never go into a real root")
    else:
        problems.append("no Yubico PIV CA given (--ca): without it any software can mint an f9-style certificate "
                        "for an imported key, so the attestation proves nothing")
    want = serialization.load_pem_public_key(open(pub_path, "rb").read())
    if _spki(att.public_key()) != _spki(want):
        problems.append(f"the attested key is NOT the key in {pub_path}")
    else:
        lines.append(f"the attested key is the key in {pub_path}")
    fw = _ext(att, OID_FIRMWARE)
    got_serial = _der_int(_ext(att, OID_SERIAL))
    pol = _ext(att, OID_POLICY)
    lines.append(f"device serial {got_serial if got_serial is not None else '?'}, firmware "
                 f"{'.'.join(str(b) for b in fw) if fw and len(fw) == 3 else '?'}")
    if serial is not None:
        if got_serial is None:
            problems.append("the attestation has no device serial extension (1.3.6.1.4.1.41482.3.7)")
        elif got_serial != int(serial):
            problems.append(f"the attestation is from YubiKey {got_serial}, not the YubiKey {serial} that was meant")
    if not pol or len(pol) != 2:
        problems.append("the attestation has no PIN/touch policy extension (1.3.6.1.4.1.41482.3.8)")
    else:
        pp, tp = PIN_POLICY.get(pol[0], f"unknown({pol[0]})"), TOUCH_POLICY.get(pol[1], f"unknown({pol[1]})")
        lines.append(f"PIN policy {pp}, touch policy {tp}")
        if pin_policy and pp != pin_policy:
            problems.append(f"PIN policy is {pp}, expected {pin_policy}")
        if touch_policy and tp != touch_policy:
            problems.append(f"touch policy is {tp}, expected {touch_policy}")
    return lines, problems


def _ok_issued(cert, root):
    if cert.fingerprint(hashes.SHA256()) == root.fingerprint(hashes.SHA256()):
        return True                                     # the chain's last link IS the CA certificate
    try:
        cert.verify_directly_issued_by(root)
        return True
    except Exception:
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pub", required=True, help="the holder's public key (PEM) that goes into root.json")
    ap.add_argument("--attestation", required=True, help="ykman piv keys attest 9c <file>")
    ap.add_argument("--chain", action="append", required=True, help="the f9 certificate (ykman piv certificates export f9)")
    ap.add_argument("--ca", help="Yubico's PIV attestation root CA (PEM), fetched and compared before going offline")
    ap.add_argument("--no-ca-spare-trial", action="store_true",
                    help="ONLY the spare-YubiKey trial: run without the CA (the key must never go into a real root)")
    ap.add_argument("--serial", type=int, help="the serial of the YubiKey that was meant (printed on its back)")
    ap.add_argument("--pin-policy", default="always", choices=sorted(PIN_POLICY.values()))
    ap.add_argument("--touch-policy", default="always", choices=sorted(TOUCH_POLICY.values()))
    a = ap.parse_args(argv)
    if a.ca and a.no_ca_spare_trial:
        ap.error("give --ca or --no-ca-spare-trial, not both")
    lines, problems = check(a.pub, a.attestation, a.chain, a.ca, a.pin_policy, a.touch_policy, a.serial,
                            allow_no_ca=a.no_ca_spare_trial)
    print("\n".join(lines))
    for p in problems:
        print("FAIL " + p)
    if problems:
        print("attestation FAILED")
    elif not a.ca:
        print("attestation OK WITHOUT Yubico's CA (spare trial only): the device answered as asked; not proof for a real root")
    else:
        print("attestation OK: the key was made on this YubiKey and cannot leave it")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
