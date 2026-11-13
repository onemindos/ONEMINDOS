# SPDX-License-Identifier: Apache-2.0
"""Fail if deploy/ uses a k3s or Debian pin that differs from os/versions.lock.yaml (brief 30 §2 rule 2).

Stdlib only (runs as `python3 -I deploy/check-pins.py` from the repo root, no PyYAML needed).
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
read = lambda p: open(os.path.join(ROOT, p), encoding="utf-8").read()
lock, pins = read("os/versions.lock.yaml"), read("deploy/pins.env")
errors = []

k3s = lock.split("\nk3s:", 1)[1].split("\ntools:", 1)[0]
version = re.search(r"^\s+version:\s*(\S+)", k3s, re.M).group(1)
want = {
    "K3S_VERSION": version,
    "K3S_SHA256_amd64": re.search(r"^\s+k3s:\s*([0-9a-f]{64})", k3s, re.M).group(1),
    "K3S_SHA256_arm64": re.search(r"^\s+k3s-arm64:\s*([0-9a-f]{64})", k3s, re.M).group(1),
}
for key, value in want.items():
    got = re.search(rf'^{key}="([^"]*)"', pins, re.M)
    if not got or got.group(1) != value:
        errors.append(f"deploy/pins.env {key}={got.group(1) if got else None!r}, lock says {value!r}")
if version.replace("+", "%2B") not in pins:
    errors.append("deploy/pins.env K3S_URL_BASE does not name the locked k3s version")

debian = re.search(r"debian:\n\s+image:\s*\S+\n\s+digest:\s*(sha256:[0-9a-f]{64})", lock).group(1)
if debian not in read("deploy/compose/onemindd.Dockerfile"):
    errors.append("deploy/compose/onemindd.Dockerfile does not use the locked Debian digest " + debian)

for path in ("deploy/compose/compose.yaml", "deploy/compose/onemindd.Dockerfile"):
    for line in read(path).splitlines():
        m = re.search(r"(?:image:|FROM)\s+(\S+)", line)
        if m and "/" in m.group(1) and "@sha256:" not in m.group(1) and ":compose-dev" not in m.group(1):
            errors.append(f"{path}: image not pinned by digest: {m.group(1)}")

# restic: deploy/pins.env must name exactly what the backup agent accepts (internal/backup/pins.go).
gopins = read("internal/backup/pins.go")
for arch in ("amd64", "arm64"):
    m = re.search(r'\{"restic", "([0-9.]+)", "%s",\s*"([^"]+)",\s*"([0-9a-f]{64})",\s*"([0-9a-f]{64})"' % arch, gopins)
    if not m:
        errors.append(f"internal/backup/pins.go has no restic pin for {arch}")
        continue
    for key, value in ((f"RESTIC_URL_{arch}", m.group(2)), (f"RESTIC_SHA256_{arch}", m.group(3)),
                       (f"RESTIC_BIN_SHA256_{arch}", m.group(4)), ("RESTIC_VERSION", m.group(1))):
        got = re.search(rf'^{key}="([^"]*)"', pins, re.M)
        if not got or got.group(1) != value:
            errors.append(f"deploy/pins.env {key}={got.group(1) if got else None!r}, internal/backup/pins.go says {value!r}")

print("\n".join(errors) if errors else "deploy pins match os/versions.lock.yaml and internal/backup/pins.go")
sys.exit(1 if errors else 0)
