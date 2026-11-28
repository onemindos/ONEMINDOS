# SPDX-License-Identifier: Apache-2.0
"""Fail if deploy/ uses a k3s, Debian or nats-server pin that differs from os/versions.lock.yaml (brief 30 §2 rule 2).

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
    "K3S_AIRGAP_SHA256_amd64": re.search(r"^\s+k3s-airgap-images-amd64\.tar\.zst:\s*([0-9a-f]{64})", k3s, re.M).group(1),
    "K3S_AIRGAP_SHA256_arm64": re.search(r"^\s+k3s-airgap-images-arm64\.tar\.zst:\s*([0-9a-f]{64})", k3s, re.M).group(1),
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

# deploy/bundle.sh images: digest-pinned, the same Go/Node digests as compose, Debian from the lock.
bundle = dict(re.findall(r'^(BUNDLE_[A-Z]+_IMAGE)="([^"]*)"', pins, re.M))
for key in ("BUNDLE_GO_IMAGE", "BUNDLE_NODE_IMAGE", "BUNDLE_DEBIAN_IMAGE"):
    if "@sha256:" not in bundle.get(key, ""):
        errors.append(f"deploy/pins.env {key} is missing or not pinned by digest")
if not bundle.get("BUNDLE_DEBIAN_IMAGE", "").endswith("@" + debian):
    errors.append("deploy/pins.env BUNDLE_DEBIAN_IMAGE does not use the locked Debian digest " + debian)
for key, path in (("BUNDLE_GO_IMAGE", "deploy/compose/onemindd.Dockerfile"), ("BUNDLE_NODE_IMAGE", "deploy/compose/compose.yaml")):
    if bundle.get(key, "-").split("@")[-1] not in read(path):
        errors.append(f"deploy/pins.env {key} digest differs from {path}")

for path in ("deploy/compose/compose.yaml", "deploy/compose/onemindd.Dockerfile"):
    for line in read(path).splitlines():
        m = re.search(r"(?:image:|FROM)\s+(\S+)", line)
        if m and "/" in m.group(1) and "@sha256:" not in m.group(1) and ":compose-dev" not in m.group(1):
            errors.append(f"{path}: image not pinned by digest: {m.group(1)}")

# nats-server: the image, the deploy bundle and the Go module (in-process test server, leaf code) run one version.
nats = lock.split("\n  nats_server:", 1)[1].split("\n  tailscale:", 1)[0]
nats_version = re.search(r"^\s+version:\s*(\S+)", nats, re.M).group(1)
want = {"NATS_VERSION": nats_version}
for arch in ("amd64", "arm64"):
    want[f"NATS_SHA256_{arch}"] = re.search(rf"^\s+{arch}:\s*{{tarball:\s*([0-9a-f]{{64}})", nats, re.M).group(1)
for key, value in want.items():
    got = re.search(rf'^{key}="([^"]*)"', pins, re.M)
    if not got or got.group(1) != value:
        errors.append(f"deploy/pins.env {key}={got.group(1) if got else None!r}, lock says {value!r}")
gomod = re.search(r"^\s*github\.com/nats-io/nats-server/v2\s+(\S+)", read("go.mod"), re.M)
if not gomod or gomod.group(1) != nats_version:
    errors.append(f"go.mod nats-server/v2 {gomod.group(1) if gomod else None!r}, lock says {nats_version!r}")

# The dev compose stack and the verify tests run the same nats-server as the image (the lock's version).
for path in ("deploy/compose/compose.yaml", "deploy/verify/tests/test_verify.py"):
    tags = re.findall(r"library/nats:([0-9][0-9.]*)-alpine@sha256:[0-9a-f]{64}", read(path))
    if not tags:
        errors.append(f"{path} has no digest-pinned nats image")
    for t in tags:
        if t != nats_version.lstrip("v"):
            errors.append(f"{path} runs nats {t}, lock says {nats_version}")
# The bridge test's NATS image too (G7): a dev stack on another version can pass with permissions the image would
# refuse. Its image string is split over two lines, so only the tag is checked here.
for ver in re.findall(r"library/nats:([0-9][0-9.]*)-alpine", read("apps/mosquitto/tests/test_bridge.py")):
    if ver != nats_version.lstrip("v"):
        errors.append(f"apps/mosquitto/tests/test_bridge.py: NATS image {ver}, os/versions.lock.yaml says {nats_version}")

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
