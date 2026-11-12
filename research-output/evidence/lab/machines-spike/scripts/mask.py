#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""LAB-machines-spike: copy one run's evidence into the repo folder, masked.

  python3 -I mask.py <run dir> <dest dir> <lab dir as seen by the VM>

Text files: private IPv4 (RFC 1918 and 100.64/10) -> <ip>, the lab folder -> <lab-dir>, any other home
path -> <host-path>, SSH public keys -> <generated-at-run-time>, PVC directory names -> <pvc-dir>.
Images are copied unchanged. Files over 2 MiB are skipped and listed.
"""
import os, re, shutil, sys

PRIV = re.compile(r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01])|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7]))\.\d{1,3}\.\d{1,3}\b")
HOME = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+[^\s\"']*")
KEY = re.compile(r"ssh-ed25519 [A-Za-z0-9+/=]+")
PVC = re.compile(r"pvc-[0-9a-f]{8}-[0-9a-f-]{27}_[a-z0-9-]+_[a-z0-9-]+")

def mask(text, lab):
    text = text.replace(lab, "<lab-dir>")
    text = HOME.sub("<host-path>", text)
    text = KEY.sub("ssh-ed25519 <generated-at-run-time>", text)
    text = PVC.sub("<pvc-dir>", text)
    return PRIV.sub("<ip>", text)

def main():
    src, dst, lab = sys.argv[1], sys.argv[2], sys.argv[3].rstrip("/")
    skipped = []
    for root, _, files in os.walk(src):
        for name in files:
            s = os.path.join(root, name); rel = os.path.relpath(s, src); d = os.path.join(dst, rel)
            if name.endswith((".fifo", ".tar", ".img")) or not os.path.isfile(s):
                continue
            if os.path.getsize(s) > 2 << 20:
                skipped.append(rel); continue
            os.makedirs(os.path.dirname(d), exist_ok=True)
            if name.endswith(".png"):
                shutil.copyfile(s, d); continue
            with open(s, encoding="utf-8", errors="replace") as f:
                text = f.read()
            with open(d, "w", encoding="utf-8") as f:
                f.write(mask(text, lab))
    for rel in skipped:
        print("skipped (over 2 MiB):", rel)

if __name__ == "__main__":
    main()
