#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Gather the release artefacts from the downloaded image.yml artifacts and classify every one
(release.yml; HANDOFF B2; founder item F-27).

  collect.py --dl DIR --out DIR [--version V]

Every file under DIR is either an artefact (copied flat into --out, and so signed by release.yml and
checked by check-signed.py), a known non-artefact (checksum lists, test results, logs: skipped), or
unknown, which refuses the whole release (exit 2): nothing reaches the release unclassified, so nothing
can slip past signing. Also refused: development builds (`-dev` in the name; they are signed with
throwaway keys), a name collision between two artifacts, and a release that lacks any class of artefact
(disk image, RAUC bundle, installer stick, cloud image). This script never makes keys.
"""
import argparse, json, os, re, shutil, sys

# (kind, regex on the file name); first match wins.
KINDS = [
    ("installer", re.compile(r"^onemind-installer-[\w.-]+\.img(\.xz)?$")),
    ("cloud", re.compile(r"^onemind-cloud-(aws|gcp|azure|hetzner|proxmox)-[\w.-]+\.(raw\.xz|vhd\.xz|qcow2|tar\.gz)$")),
    ("rauc-bundle", re.compile(r"^[\w.-]+\.raucb$")),
    ("image", re.compile(r"^onemind-[\w.-]+\.(img\.xz|raw\.xz|qcow2|vhdx|vmdk|vdi|ova)$")),
    ("imager-list", re.compile(r"^os_list\.json$")),
]
# Not artefacts: per-artifact checksum lists (the release makes its own SHA256SUMS), test evidence, logs.
SKIP = re.compile(r"^(SHA256SUMS|results\.json|t0\.json|[\w.-]*\.log)$")
REQUIRED = ("image", "rauc-bundle", "installer", "cloud")


def refuse(msg):
    print(f"REFUSED: {msg}", file=sys.stderr)
    raise SystemExit(2)


def kind_of(name):
    for k, rx in KINDS:
        if rx.match(name):
            return k
    return None


def collect(dl, out):
    """Copy the artefacts to `out`; return {name: kind}. Exits 2 on anything unclassified."""
    found, skipped = {}, []
    for root, _, files in os.walk(dl):
        for name in sorted(files):
            src = os.path.join(root, name)
            if SKIP.match(name):
                skipped.append(name)
                continue
            k = kind_of(name)
            if k is None:
                refuse(f"{os.path.relpath(src, dl)} is not a known artefact or known non-artefact; "
                       "classify it in scripts/release/collect.py before releasing")
            if "-dev" in name:
                refuse(f"{name} is a development build (throwaway signing keys); release from a release build")
            if name in found:
                refuse(f"{name} appears in two artifacts")
            found[name] = (k, src)
    missing = [k for k in REQUIRED if not any(v[0] == k for v in found.values())]
    if missing:
        refuse("no artefact of class: " + ", ".join(missing))
    os.makedirs(out, exist_ok=True)
    for name, (_, src) in found.items():
        shutil.copyfile(src, os.path.join(out, name))
    return {n: v[0] for n, v in found.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dl", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--kinds-out", help="write {name: kind} here (the downloads page groups by it)")
    a = ap.parse_args()
    kinds = collect(a.dl, a.out)
    if a.kinds_out:
        with open(a.kinds_out, "w") as f:
            json.dump(kinds, f, indent=2, sort_keys=True)
    print(f"ok: {len(kinds)} artefact(s) collected: " + ", ".join(sorted(set(kinds.values()))))


if __name__ == "__main__":
    main()
