#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Raspberry Pi Imager os_list entry for a OneMind rpi5 image (brief 30 B2 rpi5 row: "flashable
.img.xz for Raspberry Pi Imager").

Fields follow Imager's repository format (raspberrypi/rpi-imager doc/json-schema/os-list-schema.json):
name, description, url, extract_size / extract_sha256 (the .img), image_download_size /
image_download_sha256 (the .img.xz), release_date, devices. No "init_format", so Imager offers no
OS customisation: it writes cmdline.txt / firstrun files to the first FAT partition, which on
OneMind is the autoboot partition (UNVERIFIED what it would do there). OneMind is configured with
onemind.conf on that partition instead (docs/leap/core/IMAGES.md §3).

  imager_json.py --img X.img --xz X.img.xz --url-base https://host/path [--version V] [--out F]
Use the output with `rpi-imager --repo F` (Imager "Use custom" also takes the .img.xz directly).
"""
import argparse, datetime, hashlib, json, os, sys

CHUNK = 1 << 20


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(CHUNK), b""):
            h.update(b)
    return h.hexdigest()


def entry(img, xz, url_base, version, release_date, devices=("pi5-64bit",)):
    name = os.path.basename(xz)
    return {
        "name": f"OneMind OS {version} (Raspberry Pi 5)",
        "description": "OneMind OS: read-only Debian 13 image with A/B updates. Boots into the OneMind "
                       "setup at http://onemind.local:8080/ (or set role in onemind.conf on the ONEMIND partition).",
        "url": url_base.rstrip("/") + "/" + name,
        "extract_size": os.path.getsize(img),
        "extract_sha256": sha256(img),
        "image_download_size": os.path.getsize(xz),
        "image_download_sha256": sha256(xz),
        "release_date": release_date,
        "devices": list(devices),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--img", required=True)
    ap.add_argument("--xz", required=True)
    ap.add_argument("--url-base", required=True)
    ap.add_argument("--version")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    if not a.url_base.startswith("https://"):
        sys.exit("--url-base must be https://")
    ver = a.version or os.path.basename(a.img).removeprefix("onemind-rpi5-").removesuffix(".img")
    doc = {"os_list": [entry(a.img, a.xz, a.url_base, ver, a.date)]}
    text = json.dumps(doc, indent=2) + "\n"
    if a.out:
        open(a.out, "w").write(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
