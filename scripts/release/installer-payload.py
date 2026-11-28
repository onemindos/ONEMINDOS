#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Which image the security build's installer stick carries (#234, D-010; os/boards/installer-x86_64/UPDATES.md).

  installer-payload.py --release-dir rel --version V --publish true|false --trust-dir DIR

Reads release-<board>.json, written by os/update/build-release.sh for the installer's target board (board.yaml
`target_board`), and prints one line for $GITHUB_OUTPUT:
  mode=release  the bundle was signed with the release keys ("dry_run": false). The CA certificate it was verified
                against (<bundle>.keyring.pem, public) is copied to DIR/keyring.pem for os/assemble/release-image.sh, so
                the installed box trusts the release CA and takes every later release as an update.
  mode=dev      a dry run (no release keys): the stick is built the way image.yml builds it (`make image`,
                os/assemble/dev-image.sh, throwaway CA). DIR is not created.
Every mismatch is refused (exit 1) instead of guessed: a publishing run with a dry-run record, a release record on a run
that does not publish, another board or version, a keyring that holds anything but certificates. Never reads, prints or
writes a private key: the only PEM file it opens must hold certificates, and nothing from it is printed.
"""
import argparse
import base64
import binascii
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INSTALLER = "installer-x86_64"
SCHEMA = "onemind.release/v1"
PEM = re.compile(r"-----BEGIN ([A-Z0-9 ]+)-----(.*?)-----END \1-----", re.S)


def refuse(msg):
    sys.exit(f"REFUSED: {msg}")


def target_board():
    """The board whose image the installer writes (os/boards/installer-x86_64/board.yaml)."""
    with open(os.path.join(ROOT, "os", "boards", INSTALLER, "board.yaml")) as f:
        m = re.search(r"(?m)^target_board:\s*([^\s#]+)", f.read())
    if not m:
        refuse(f"{INSTALLER}/board.yaml names no target_board")
    return m.group(1)


def check_certificates(text):
    """One or more certificates and nothing else: a key is refused, never used. Returns the number of certificates."""
    if "PRIVATE KEY" in text:
        refuse("the keyring holds a private key; only the CA certificate may reach the installer build")
    if text.count("-----BEGIN ") != len(PEM.findall(text)):
        refuse("the keyring holds a PEM block without its end line")
    blocks = PEM.findall(text)
    if not blocks:
        refuse("the keyring holds no certificate")
    for kind, body in blocks:
        if kind != "CERTIFICATE":
            refuse(f"the keyring holds a {kind} block; only certificates may be given")
        try:
            der = base64.b64decode("".join(body.split()), validate=True)
        except (binascii.Error, ValueError):
            refuse("a certificate in the keyring is not valid base64")
        if not der or der[0] != 0x30:
            refuse("a certificate in the keyring is not a DER sequence")
    return len(blocks)


def flag(value):
    if value not in ("true", "false"):
        refuse(f"--publish must be true or false, not {value!r}")
    return value == "true"


def select(release_dir, version, publish, board=None):
    """("release", keyring path) when the build was release-signed, ("dev", None) on a dry run; refuses the rest."""
    board = board or target_board()
    path = os.path.join(release_dir, f"release-{board}.json")
    if not os.path.isfile(path):
        refuse(f"{path} is missing: the security build made no release for {board}")
    with open(path) as f:
        rec = json.load(f)
    if rec.get("schema") != SCHEMA:
        refuse(f"{path} is not a {SCHEMA} record")
    if rec.get("board") != board:
        refuse(f"{path} is for board {rec.get('board')!r}, the installer writes {board!r}")
    if rec.get("version") != version:
        refuse(f"{path} is version {rec.get('version')!r}, this run builds {version!r}")
    dry = rec.get("dry_run")
    if not isinstance(dry, bool):
        refuse(f"{path} has no true/false dry_run")
    if publish and dry:
        refuse("this run publishes, but the release is a dry run: the stick would carry a dev-keyed image")
    if not publish and not dry:
        refuse("a release-signed bundle on a run that does not publish: refusing to guess which keys the stick needs")
    if dry:
        return "dev", None
    if "-dev" in version:
        refuse(f"{version!r} is a development version")
    keyring = os.path.join(release_dir, f"onemind-{board}-{version}.keyring.pem")
    if not os.path.isfile(keyring):
        refuse(f"{keyring} is missing: build-release.sh writes the keyring next to the bundle")
    with open(keyring) as f:
        check_certificates(f.read())
    return "release", keyring


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--release-dir", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--publish", required=True)
    ap.add_argument("--trust-dir", required=True)
    a = ap.parse_args(argv)
    mode, keyring = select(a.release_dir, a.version, flag(a.publish))
    if mode == "release":
        if os.path.exists(a.trust_dir) and os.listdir(a.trust_dir):
            refuse(f"{a.trust_dir} is not empty: it may hold only the keyring copied here")
        os.makedirs(a.trust_dir, exist_ok=True)
        shutil.copyfile(keyring, os.path.join(a.trust_dir, "keyring.pem"))
    print(f"mode={mode}")


if __name__ == "__main__":
    main()
