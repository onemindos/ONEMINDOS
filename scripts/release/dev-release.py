#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Pick the files of the nightly "dev build" pre-release out of an image.yml run (DEV-SEE-01, #234).

  dev-release.py --dl DIR --out DIR --sha GIT_SHA --date YYYYMMDD

DIR holds the downloaded artifacts of one successful image.yml run on main. The downloads someone
actually wants (three images, the two update bundles and the dev CA certificate) go flat into --out with a SHA256SUMS and a NOTES.md that says, first, that this is a
development build with throwaway keys. The tag name is printed on the last line (`dev-<date>-<sha7>`).
Exit 2 and nothing published if a download is missing or too big for a GitHub release asset.
This is not release.yml: it never signs, never makes keys, and release.yml still refuses `-dev` builds.
"""
import argparse, hashlib, os, re, shutil, sys

# (what, regex on the file name, who needs it)
WANTED = [
    ("mac", re.compile(r"^onemind-arm64-efi-[\w.-]+\.qcow2$"), "Apple Silicon Mac in UTM (docs/see-onemind/mac-utm.md)"),
    ("beelink", re.compile(r"^onemind-installer-amd64-[\w.-]+\.img\.xz$"), "x86-64 PC from a USB stick (docs/see-onemind/beelink-usb.md)"),
    ("droplet", re.compile(r"^onemind-vm-do-[\w.-]+\.qcow2$"), "DigitalOcean custom image (lab-kits/LT-DO-01)"),
    # The update test (lab-kits/LT-DO-01 D5, R530 lab) needs the signed-by-the-throwaway-CA bundles and that CA.
    ("update-bundle", re.compile(r"^onemind-vm-do-[\w.-]+(?<!-next)\.raucb$"), "RAUC update bundle, the version the droplet image boots (update tests)"),
    ("update-next", re.compile(r"^onemind-vm-do-[\w.-]+-next\.raucb$"), "RAUC update bundle, the next version to install over it (update tests)"),
    ("dev-ca", re.compile(r"^dev-ca\.cert\.pem$"), "throwaway dev CA certificate that signed both bundles (public part only; no key)"),
]
MAX_ASSET = 2 * 1024**3 - 1   # GitHub release assets stop at 2 GiB


def refuse(msg):
    print(f"REFUSED: {msg}", file=sys.stderr)
    raise SystemExit(2)


def pick(dl):
    found = {}
    for root, _, files in os.walk(dl):
        for name in sorted(files):
            for what, rx, _ in WANTED:
                if rx.match(name):
                    if what in found:
                        refuse(f"two files match the {what} download: {found[what]} and {name}")
                    found[what] = os.path.join(root, name)
    for what, _, who in WANTED:
        if what not in found:
            refuse(f"the {what} download ({who}) is not in {dl}")
    return found


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def notes(tag, rows):
    lines = [
        "# DEVELOPMENT BUILD. NOT FOR PRODUCTION.", "",
        "Built automatically from `main` with **throwaway signing keys** and a throwaway certificate authority. "
        "It is for looking at OneMind, not for anything you care about: no Secure Boot, no signed updates, "
        "no support. Never put real family data on it. The RAUC update bundles and `dev-ca.cert.pem` are signed by that "
        "throwaway CA, so they only install on dev images from the same build, and they stay that way until the "
        "signing ceremony (#153).", "",
        "Pick one (guides: `docs/see-onemind/`):", "",
    ]
    for name, who, digest in rows:
        lines.append(f"- **{name}**: {who}  \n  `sha256 {digest}`")
    lines += ["", f"Tag `{tag}`. Check a download with `shasum -a 256 -c SHA256SUMS --ignore-missing`."]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dl", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--date", required=True)
    a = ap.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{7,40}", a.sha):
        refuse(f"--sha {a.sha!r} is not a git commit id")
    if not re.fullmatch(r"\d{8}", a.date):
        refuse(f"--date {a.date!r} is not YYYYMMDD")
    found = pick(a.dl)
    for what, path in found.items():
        if os.path.getsize(path) > MAX_ASSET:
            refuse(f"{os.path.basename(path)} is {os.path.getsize(path)} bytes: more than a release asset may hold (2 GiB)")
    os.makedirs(a.out, exist_ok=True)
    rows, sums = [], []
    for what, _, who in WANTED:
        src = found[what]
        name = os.path.basename(src)
        shutil.copyfile(src, os.path.join(a.out, name))
        digest = sha256(src)
        sums.append(f"{digest}  {name}")
        rows.append((name, who, digest))
    tag = f"dev-{a.date}-{a.sha[:7]}"
    with open(os.path.join(a.out, "SHA256SUMS"), "w") as f:
        f.write("\n".join(sums) + "\n")
    with open(os.path.join(a.out, "NOTES.md"), "w") as f:
        f.write(notes(tag, rows))
    print(tag)


if __name__ == "__main__":
    main()
