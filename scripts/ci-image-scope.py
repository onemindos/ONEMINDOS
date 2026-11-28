#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Decide how much of the image workflow a pull request needs (CI-14, leap run Day 1).

Why: image.yml starts about 15 hosted jobs per PR (5 image builds, the first-boot smoke, 3 battery
legs, 5 cloud images and the installer), 1-2 hours each, on GitHub Free's ~20 shared runners. Most
PRs only change what the image *carries* (the gateway in core/, the dashboard, the design system
and the app catalogue), not how the image is built, boots or updates. For those PRs the
x86_64-efi first-boot smoke (F0-F4: the gateway really starts on the image) plus the e2e golden path
(e2e.yml: install, dashboard, agent) are the useful signal. The full matrix still runs:
  - for every PR that touches the OS itself (os/, test/qemu/, the Go daemon, the build files);
  - on every push to main, so a payload change that breaks the battery shows up within hours;
  - on manual dispatch.

Input: the PR's changed file names (and the old names of renamed files), one per line, on stdin. Output (for $GITHUB_OUTPUT):
`os=true` (run everything) or `os=false` (smoke only). Any doubt is `os=true`: an empty list,
an unreadable list, or GitHub's 3000-file cap on the PR files API. The workflow itself writes
`os=true` without calling this script when the files API fails.
"""
from __future__ import annotations

import sys

# What the image carries but does not boot or update with: the gateway, dashboard, design system, app
# catalogue and the SDK sources the image copies (schemas and policy for the gateway, TypeScript for the
# dashboard, Go for onemindd; a Go compile break is caught by ci-onemindd on every PR anyway).
# The containerized printing test also runs in the smoke job.
PAYLOAD = ("core/", "dashboard/", "ui/src/", "apps/", "sdk/", "test/printing/")
# Inside the payload folders but part of how the image is built or what the cloud tests prove:
# - the gateway's Python dependencies are resolved per architecture in the image build (only the arm64
#   builds catch a dependency with no arm64 wheel);
# - serve.py, netconf.py and the onboarding router decide that the setup wizard answers only locally
#   (cloud test C5, a security check).
PAYLOAD_EXCEPTIONS = {
    "core/pyproject.toml", "core/uv.lock",
    "core/onemind_core/serve.py", "core/onemind_core/netconf.py", "core/onemind_core/routers/onboarding.py",
}
OS_PREFIXES = ("os/", "test/qemu/", "cmd/", "internal/", "brand/")
OS_FILES = {
    "go.mod", "go.sum", ".dockerignore", "Makefile",
    ".github/workflows/image.yml", ".github/workflows/battery.yml", "scripts/ci-image-scope.py",
}
# The PR files API returns at most 3000 files; a list that long may be cut, so assume the OS changed.
API_CAP = 3000


def needs_full_image(files: list[str]) -> bool:
    """True unless every file is payload or outside what the image is built from."""
    files = [f.strip() for f in files if f.strip()]
    if not files or len(files) >= API_CAP:
        return True
    return any(is_os(f) for f in files)


def is_os(path: str) -> bool:
    """A path that changes how the image is built, boots or updates (or what the cloud tests prove)."""
    if path in PAYLOAD_EXCEPTIONS or path in OS_FILES:
        return True
    if path.startswith(PAYLOAD):
        return False
    return path.startswith(OS_PREFIXES)


def main() -> int:
    try:
        files = sys.stdin.read().splitlines()
    except (OSError, UnicodeDecodeError):
        files = []
    print(f"os={'true' if needs_full_image(files) else 'false'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
