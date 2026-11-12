#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Refuse to publish unsigned artefacts (release.yml; HANDOFF B2; founder item F-27).

  check-signed.py --dir DIR --pubkey PEM [--manifest-out releases.json --version V]

DIR must hold SHA256SUMS and SHA256SUMS.sig (an openssl signature over SHA256SUMS made with the release
key), and every other file in DIR must be listed in SHA256SUMS with the right hash. The public key is the
one the founder commits after the key ceremony (os/release/release-pubkey.pem). No key, no signature, a
bad signature or a file that is not listed: exit 2 and nothing is published. This script never makes keys.
"""
import argparse, hashlib, json, os, subprocess, sys


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def refuse(msg):
    print(f"REFUSED: {msg}", file=sys.stderr)
    raise SystemExit(2)


def check(d, pubkey):
    """Return {name: sha256} of the verified artefacts, or exit 2 with the reason."""
    if not pubkey or not os.path.isfile(pubkey):
        refuse(f"no release public key at {pubkey} (the signing key is founder item F-27)")
    sums, sig = os.path.join(d, "SHA256SUMS"), os.path.join(d, "SHA256SUMS.sig")
    if not os.path.isfile(sums):
        refuse("SHA256SUMS missing")
    if not os.path.isfile(sig):
        refuse("SHA256SUMS.sig missing: these artefacts are unsigned")
    r = subprocess.run(["openssl", "dgst", "-sha256", "-verify", pubkey, "-signature", sig, sums],
                       capture_output=True, text=True)
    if r.returncode != 0:
        refuse("signature on SHA256SUMS does not verify against the release public key")
    listed = {}
    for line in open(sums).read().splitlines():
        if line.strip():
            h, name = line.split(None, 1)
            listed[name.strip().lstrip("*")] = h
    present = sorted(f for f in os.listdir(d)
                     if f not in ("SHA256SUMS", "SHA256SUMS.sig") and os.path.isfile(os.path.join(d, f)))
    for f in present:
        if f not in listed:
            refuse(f"{f} is not listed in SHA256SUMS")
        if sha256(os.path.join(d, f)) != listed[f]:
            refuse(f"{f} does not match its SHA256SUMS entry")
    for f in listed:
        if f not in present:
            refuse(f"{f} is listed but missing")
    return {f: listed[f] for f in present}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--pubkey", required=True)
    ap.add_argument("--manifest-out")
    ap.add_argument("--version", default="")
    a = ap.parse_args()
    files = check(a.dir, a.pubkey)
    if a.manifest_out:
        art = [{"name": n, "sha256": h, "bytes": os.path.getsize(os.path.join(a.dir, n))} for n, h in files.items()]
        with open(a.manifest_out, "w") as f:
            json.dump({"version": a.version, "signed": True, "artefacts": art}, f, indent=2)
    print(f"ok: {len(files)} artefact(s), signature verified")


if __name__ == "__main__":
    main()
