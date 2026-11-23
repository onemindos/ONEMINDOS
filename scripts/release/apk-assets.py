#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The three phone files of a release (release.yml publish job; issue #880).

  RELEASE_SIGNING_KEY=<pem> apk-assets.py --apk FILE --version V --out DIR --pubkey PEM [--expect-sha256 HEX]

Writes exactly three files into DIR (which must be empty or absent):
  onemind-<V>.apk              the APK that scripts/check-apk passed
  onemind-<V>.apk.sha256       "<sha256>  onemind-<V>.apk", so `sha256sum -c` checks a download
  onemind-<V>.apk.sha256.sig   openssl signature over the .sha256 file with the release key (the same key that
                               signs the image SHA256SUMS; verify it against os/release/release-pubkey.pem)
The private key is read from the environment only, written to a 0600 temp file for openssl and removed; it is
never printed. The signature is verified against --pubkey before the script succeeds. --expect-sha256 refuses
an APK that changed since the build job checked it. Exit 2 on any refusal, leaving DIR empty.
"""
import argparse, hashlib, os, re, shutil, subprocess, sys, tempfile

VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$")


def refuse(msg):
    print(f"apk-assets: REFUSED: {msg}", file=sys.stderr)
    return 2


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apk", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pubkey", required=True)
    ap.add_argument("--expect-sha256")
    a = ap.parse_args(argv)

    if not VERSION.match(a.version):
        return refuse(f"'{a.version}' is not a release version like 1.2.0")
    key = os.environ.get("RELEASE_SIGNING_KEY", "")
    if not key.strip():
        return refuse("RELEASE_SIGNING_KEY is not set (founder item F-27); nothing is signed")
    if not os.path.isfile(a.pubkey):
        return refuse(f"no public key at {a.pubkey}")
    if not os.path.isfile(a.apk):
        return refuse(f"no APK at {a.apk}")
    digest = sha256(a.apk)
    if a.expect_sha256 and digest != a.expect_sha256.lower():
        return refuse("the APK is not the one the build job checked (SHA-256 differs)")
    if os.path.exists(a.out) and os.listdir(a.out):
        return refuse(f"{a.out} is not empty")

    name = f"onemind-{a.version}.apk"
    with tempfile.TemporaryDirectory() as work:
        stage = os.path.join(work, "out")
        os.mkdir(stage)
        shutil.copyfile(a.apk, os.path.join(stage, name))
        sums = os.path.join(stage, name + ".sha256")
        with open(sums, "w") as f:
            f.write(f"{digest}  {name}\n")
        kp = os.path.join(work, "k.pem")
        fd = os.open(kp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(key)
        try:
            sign = subprocess.run(["openssl", "dgst", "-sha256", "-sign", kp, "-out", sums + ".sig", sums],
                                  capture_output=True, text=True)
        finally:
            os.remove(kp)
        if sign.returncode != 0:
            return refuse("openssl could not sign the checksum with RELEASE_SIGNING_KEY")
        check = subprocess.run(["openssl", "dgst", "-sha256", "-verify", a.pubkey, "-signature", sums + ".sig", sums],
                               capture_output=True, text=True)
        if check.returncode != 0:
            return refuse(f"the checksum signature does not verify against {a.pubkey} (wrong key?)")
        os.makedirs(a.out, exist_ok=True)
        for f in sorted(os.listdir(stage)):
            shutil.move(os.path.join(stage, f), os.path.join(a.out, f))
    print(f"apk-assets: {name}, {name}.sha256 and {name}.sha256.sig in {a.out} (sha256 {digest})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
