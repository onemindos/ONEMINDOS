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

Input: the PR's changed file names, one per line, on stdin. Output (for $GITHUB_OUTPUT):
`os=true` (run everything) or `os=false` (smoke only). Any doubt is `os=true`: an empty list,
an unreadable list, or GitHub's 3000-file cap on the PR files API.
"""
from __future__ import annotations

import sys

# Paths image.yml triggers on that only change the image's payload, not its build, boot or update.
PAYLOAD = ("core/", "dashboard/", "ui/src/", "apps/")
# The PR files API returns at most 3000 files; a list that long may be cut, so assume the OS changed.
API_CAP = 3000


def needs_full_image(files: list[str]) -> bool:
    """True unless every file is payload or outside the image's trigger paths entirely."""
    files = [f.strip() for f in files if f.strip()]
    if not files or len(files) >= API_CAP:
        return True
    return any(is_os(f) for f in files)


def is_os(path: str) -> bool:
    """A path image.yml triggers on that is not payload (keep in step with image.yml `paths:`)."""
    if path.startswith(PAYLOAD):
        return False
    if path.startswith(("os/", "test/qemu/", "cmd/", "internal/")):
        return True
    return path in {
        "go.mod", "go.sum", ".dockerignore", "Makefile",
        ".github/workflows/image.yml", ".github/workflows/battery.yml", "scripts/ci-image-scope.py",
    }


def main() -> int:
    try:
        files = sys.stdin.read().splitlines()
    except (OSError, UnicodeDecodeError):
        files = []
    print(f"os={'true' if needs_full_image(files) else 'false'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
