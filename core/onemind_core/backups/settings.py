# SPDX-License-Identifier: Apache-2.0
"""The `backups` settings section (ONEMIND_BACKUPS_*; docs/leap/core/PLUMBING.md §4)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from ..sections import config_section

LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost")


@config_section("backups")
@dataclass(frozen=True)
class BackupsSettings:
    # ONEMIND_BACKUPS_ENABLED=1: this gateway drives the box's backup agent (onemindd backup).
    enabled: bool = False
    # The agent's loopback API (onemindd (backup drop-in)). Never another machine (H-24).
    agent_url: str = "http://127.0.0.1:7480"
    # Ed25519 job key (PEM, 0600). Unset: <directory of the audit log>/custodian/job.key, created
    # on first start. Its public half (job.pub beside it) goes into the agent's job_pubkey_file.
    job_key_file: Path | None = None
    # Hourly runs with the apps' hooks, at a minute fixed per box (-1 = derived from the box id).
    schedule: bool = True
    minute: int = -1
    # How long the gateway waits for one agent job (a large restore can take hours).
    job_timeout_s: float = 21600.0
    # How long a restored app has to come back with fresh, ready pods before the restore is undone.
    health_deadline_s: int = 300

    def validate(self) -> None:
        u = urlsplit(self.agent_url)
        if u.scheme != "http" or (u.hostname or "") not in LOOPBACK_HOSTS:
            raise ValueError("ONEMIND_BACKUPS_AGENT_URL must be http://127.0.0.1:<port> (the agent is loopback-only)")
        if not -1 <= self.minute <= 59:
            raise ValueError("ONEMIND_BACKUPS_MINUTE must be -1..59")
        if self.job_timeout_s <= 0 or self.health_deadline_s <= 0:
            raise ValueError("ONEMIND_BACKUPS_JOB_TIMEOUT_S and _HEALTH_DEADLINE_S must be positive")
