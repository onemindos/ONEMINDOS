# SPDX-License-Identifier: Apache-2.0
"""Install the image's IPP authorization policy on the data-backed CUPS server."""

import grp
import os
import re
import sys
import tempfile
from pathlib import Path


POLICY = re.compile(r"^[ \t]*<Policy[ \t]+[^>\n]+>[^\n]*\n.*?^[ \t]*</Policy>[^\n]*$", re.I | re.M | re.S)
DEFAULT_POLICY = re.compile(r"^[ \t]*DefaultPolicy[ \t]+[^\n]*\n?", re.I | re.M)
SPOOL_FILE = re.compile(r"c[0-9]+|d[0-9]+-[0-9]+")


def sync_dir(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def quarantine_previous_jobs(spool):
    """Jobs submitted under the old policy have no recorded owner release."""
    jobs = [path for path in spool.iterdir() if SPOOL_FILE.fullmatch(path.name)]
    if not jobs:
        return
    quarantine = spool / ".pre-owner-release"
    quarantine.mkdir(mode=0o700, exist_ok=True)
    for path in jobs:
        path.rename(quarantine / path.name)
    sync_dir(quarantine)
    sync_dir(spool)


def enforce(seed, config, spool):
    managed_policy = POLICY.search(seed.read_text()).group()
    if config.is_symlink():
        raise ValueError("refusing a symlinked CUPS configuration")
    text = config.read_text()
    settings = DEFAULT_POLICY.sub("", POLICY.sub("", text))
    if re.search(r"^[ \t]*</?Policy\b", settings, re.I | re.M):
        raise ValueError("could not parse the existing CUPS policies")
    if POLICY.findall(text) == [managed_policy] and not DEFAULT_POLICY.search(text):
        return

    quarantine_previous_jobs(spool)
    # Install the policy without overwriting queue metadata or other CUPS settings.
    with tempfile.NamedTemporaryFile(mode="w", dir=config.parent, delete=False) as target:
        try:
            os.fchown(target.fileno(), os.geteuid(), grp.getgrnam("lp").gr_gid)
            os.fchmod(target.fileno(), 0o640)
            target.write(f"{settings.rstrip()}\n\n{managed_policy}\n")
            target.flush()
            os.fsync(target.fileno())
            os.replace(target.name, config)
            sync_dir(config.parent)
        finally:
            Path(target.name).unlink(missing_ok=True)


if __name__ == "__main__":
    enforce(*(Path(arg) for arg in sys.argv[1:]))
