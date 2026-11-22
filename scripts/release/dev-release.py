#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Pick the files of the nightly "dev build" pre-release out of an image.yml run (DEV-SEE-01, #234).

  dev-release.py --dl DIR --out DIR --sha GIT_SHA --date YYYYMMDD

DIR holds the downloaded artifacts of one successful image.yml run on main. The downloads someone
actually wants (three images, the update bundles of the two update-capable boards, vm-do and the
x86_64-efi installer board, and each board's dev CA certificate) go flat into --out with an
update-compat-<board>.json per board, a SHA256SUMS and a NOTES.md that says, first, that this is a
development build with throwaway keys. The tag name is printed on the last line (`dev-<date>-<sha7>`).
Exit 2 and nothing published if a download is missing or too big for a GitHub release asset.
This is not release.yml: it never signs, never makes keys, and release.yml still refuses `-dev` builds.
"""
import argparse, base64, hashlib, json, os, re, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# (what, regex on the file name, who needs it)
WANTED = [
    ("mac", re.compile(r"^onemind-arm64-efi-[\w.-]+\.qcow2$"), "Apple Silicon Mac in UTM (docs/see-onemind/mac-utm.md)"),
    ("beelink", re.compile(r"^onemind-installer-amd64-[\w.-]+\.img\.xz$"), "x86-64 PC from a USB stick (docs/see-onemind/beelink-usb.md)"),
    ("droplet", re.compile(r"^onemind-vm-do-[\w.-]+\.qcow2$"), "DigitalOcean custom image (lab-kits/LT-DO-01)"),
    # The update test (lab-kits/LT-DO-01 D5, R530 lab) needs the signed-by-the-throwaway-CA bundles and that CA.
    ("update-bundle", re.compile(r"^onemind-vm-do-[\w.-]+(?<!-next)\.raucb$"), "RAUC update bundle, the version the droplet image boots (update tests)"),
    ("update-next", re.compile(r"^onemind-vm-do-[\w.-]+-next\.raucb$"), "RAUC update bundle, the next version to install over it (update tests)"),
    ("dev-ca", re.compile(r"^dev-ca\.cert\.pem$"), "throwaway dev CA certificate that signed both bundles (public part only; no key)"),
    # The installer stick (the Dell, a Beelink) carries the x86_64-efi image. Its own throwaway CA is not the droplet's,
    # so its bundles and CA come from the stick's artifact folder (image.yml, installer job) and are kept apart.
    ("update-bundle-x86_64-efi", re.compile(r"^onemind-x86_64-efi-[\w.-]+(?<!-next)\.raucb$"), "RAUC update bundle for a box installed from the USB stick (x86_64-efi): the version the stick installs"),
    ("update-next-x86_64-efi", re.compile(r"^onemind-x86_64-efi-[\w.-]+-next\.raucb$"), "RAUC update bundle for a box installed from the USB stick: the next version to install over it"),
    ("dev-ca-x86_64-efi", re.compile(r"^dev-ca\.cert\.pem$"), "throwaway dev CA certificate of the USB-stick image (public part only; no key)"),
]
# image.yml uploads the whole out/image-<board>/ folder, and dev-image.sh puts dev-ca.cert.pem in every one,
# so the bundles and the CA only count when they sit in their own board's artifact folder.
SCOPE = {w: "image-debian-vm-do" for w in ("update-bundle", "update-next", "dev-ca")}
SCOPE.update({w: "installer-debian-x86_64" for w in ("update-bundle-x86_64-efi", "update-next-x86_64-efi", "dev-ca-x86_64-efi")})
# Name in the release when it differs from the name in the artifact (two CAs, one flat folder).
RENAME = {"dev-ca-x86_64-efi": "dev-ca-x86_64-efi.cert.pem"}
# The boards a box can take an update on from a dev release: (board, bundle key, next key, CA key).
UPDATE_BOARDS = [
    ("vm-do", "update-bundle", "update-next", "dev-ca"),
    ("x86_64-efi", "update-bundle-x86_64-efi", "update-next-x86_64-efi", "dev-ca-x86_64-efi"),
]
MAX_ASSET = 2 * 1024**3 - 1   # GitHub release assets stop at 2 GiB


def refuse(msg):
    print(f"REFUSED: {msg}", file=sys.stderr)
    raise SystemExit(2)


def pick(dl):
    found = {}
    for root, _, files in os.walk(dl):
        for name in sorted(files):
            top = os.path.relpath(root, dl).split(os.sep)[0]
            for what, rx, _ in WANTED:
                if rx.match(name) and SCOPE.get(what, top) == top:
                    if what in found:
                        refuse(f"two files match the {what} download: {found[what]} and {name}")
                    found[what] = os.path.join(root, name)
    for what, _, who in WANTED:
        if what not in found:
            refuse(f"the {what} download ({who}) is not in {dl}")
    return found


# ---- N to N+1: the same rules the box applies (internal/update/semver.go, tuf.go; os/update/CHANNEL.md section 5)
def _parse_version(v):
    v = v.lstrip("v").split("+")[0]
    core, _, pre = v.partition("-")
    try:
        nums = [int(p) for p in core.split(".")]
    except ValueError:
        raise ValueError(f"version {v!r} is not dot-separated integers")
    if "-" in v and (not pre or "" in pre.split(".")):
        raise ValueError(f"version {v!r}: empty pre-release")
    return nums, (pre.split(".") if pre else [])


def compare_versions(a, b):
    """-1, 0, 1 with the box's ordering: numeric parts first, a pre-release (-dev.7) ranks below none."""
    (na, pa), (nb, pb) = _parse_version(a), _parse_version(b)
    for i in range(max(len(na), len(nb))):
        x, y = (na[i] if i < len(na) else 0), (nb[i] if i < len(nb) else 0)
        if x != y:
            return -1 if x < y else 1
    if not pa and not pb:
        return 0
    if not pa:
        return 1
    if not pb:
        return -1
    for x, y in zip(pa, pb):
        if x == y:
            continue
        if x.isdigit() and y.isdigit():
            return -1 if int(x) < int(y) else 1
        if x.isdigit():
            return -1
        if y.isdigit():
            return 1
        return -1 if x < y else 1
    return (len(pa) > len(pb)) - (len(pa) < len(pb))


def ca_fingerprint(pem):
    """sha256 of the DER of the one certificate in a PEM file; refuses a file with a private key or no certificate."""
    if "PRIVATE KEY" in pem:
        refuse("a dev CA file contains a private key; nothing is published")
    m = re.findall(r"-----BEGIN CERTIFICATE-----(.*?)-----END CERTIFICATE-----", pem, re.S)
    if len(m) != 1:
        refuse(f"a dev CA file must hold exactly one certificate, found {len(m)}")
    try:
        return hashlib.sha256(base64.b64decode("".join(m[0].split()), validate=True)).hexdigest()
    except ValueError:
        refuse("a dev CA file is not a valid PEM certificate")


def accepts(box, release):
    """Why a box described by `box` refuses the release `release`, or "" if it installs it.
    Both are update-compat records: board, compatible, version, min_from_version, ca_sha256."""
    if release["board"] != box["board"]:
        return f"board {release['board']!r} is not {box['board']!r}"
    if release["compatible"] != box["compatible"]:
        return f"compatible {release['compatible']!r} is not {box['compatible']!r}"
    if release["ca_sha256"] != box["ca_sha256"]:
        return "signed by a different CA than the box trusts (RAUC refuses the bundle)"
    if compare_versions(release["version"], box["version"]) <= 0:
        return f"not newer than {box['version']}"
    if release.get("min_from_version") and compare_versions(release["min_from_version"], box["version"]) > 0:
        return f"needs at least {release['min_from_version']}"
    return ""


def board_field(board, key):
    with open(os.path.join(ROOT, "os", "boards", board, "board.yaml")) as f:
        m = re.search(rf"^{key}: *([^ #\n]+)", f.read(), re.M)
    if not m:
        refuse(f"os/boards/{board}/board.yaml has no {key}")
    return m.group(1)


def compat_record(board, bundle, nxt, ca_pem):
    """What a box installed from `bundle` accepts: the next bundle, and nothing else, until the real keys exist."""
    prefix = f"onemind-{board}-"
    ver = os.path.basename(bundle)[len(prefix):-len(".raucb")]
    nver = os.path.basename(nxt)[len(prefix):-len(".raucb")]
    if nver != ver + "-next":
        refuse(f"the {board} next bundle ({nver}) is not {ver}-next")
    with open(os.path.join(ROOT, "os", "update", "channel.json")) as f:
        minfrom = json.load(f)["min_from_version"]
    # Dev bundles are installed straight with `rauc install`, not through the TUF channel, so the channel's
    # min_from_version does not gate them (and 0.1.0-dev.N ranks below 0.1.0, so it would refuse them).
    box = {"board": board, "compatible": board_field(board, "compatible"), "version": ver,
           "min_from_version": "", "ca_sha256": ca_fingerprint(ca_pem)}
    nxt_rec = dict(box, version=nver)
    why = accepts(box, nxt_rec)
    if why:
        refuse(f"the {board} dev bundles are not an N to N+1 pair: {why}")
    return {"schema": "onemind.dev-update-compat/v1", "board": board, "compatible": box["compatible"],
            "version": ver, "next_version": nver, "channel_min_from_version": minfrom, "ca_sha256": box["ca_sha256"],
            "signing": "dev-throwaway", "installs": [{"from": ver, "to": nver}],
            "note": "A dev build's CA is made per build and destroyed with it: this box takes only the -next bundle "
                    "of the same build. A box accepts release N+1 from another build only once both are signed by the "
                    "channel keys (os/update/CEREMONY.md)."}


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
        "signing ceremony (#153). A box installed from the USB stick takes the `-next` bundle of its own build "
        "(see `update-compat-x86_64-efi.json`), never a bundle from another build.", "",
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
    compat = {}
    for board, b, n, c in UPDATE_BOARDS:
        with open(found[c]) as f:
            compat[board] = compat_record(board, found[b], found[n], f.read())
    os.makedirs(a.out, exist_ok=True)
    rows, sums = [], []
    for what, _, who in WANTED:
        src = found[what]
        name = RENAME.get(what, os.path.basename(src))
        shutil.copyfile(src, os.path.join(a.out, name))
        digest = sha256(src)
        sums.append(f"{digest}  {name}")
        rows.append((name, who, digest))
    for board, rec in compat.items():
        name = f"update-compat-{board}.json"
        with open(os.path.join(a.out, name), "w") as f:
            json.dump(rec, f, indent=1, sort_keys=True)
            f.write("\n")
        digest = sha256(os.path.join(a.out, name))
        sums.append(f"{digest}  {name}")
        rows.append((name, f"which version a {board} box installed from this build accepts as its update", digest))
    tag = f"dev-{a.date}-{a.sha[:7]}"
    with open(os.path.join(a.out, "SHA256SUMS"), "w") as f:
        f.write("\n".join(sums) + "\n")
    with open(os.path.join(a.out, "NOTES.md"), "w") as f:
        f.write(notes(tag, rows))
    print(tag)


if __name__ == "__main__":
    main()
