# SPDX-License-Identifier: Apache-2.0
"""The `backups` settings section (ONEMIND_BACKUPS_*; docs/leap/core/PLUMBING.md §4)."""

from __future__ import annotations

import re
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
    # The built-ins' units (#616). Before each box run the gateway writes their table export
    # (units.py, builtin-units.tar) into this folder; the agent's `system` unit lists it (agent.json,
    # written by onemind-firstboot). Unset: no export, and no built-in is shown as in a snapshot.
    export_dir: Path | None = None
    # The built-in folder settings (ONEMIND_<SECTION>_<FIELD>) whose folders the agent's `system` unit
    # also copies, separated by spaces or commas (onemind-firstboot writes the ones it adds).
    agent_dirs: str = ""
    # The folders the agent's `system` unit really copies (absolute, separated by commas; onemind-firstboot
    # writes them from agent.json). A folder named in agent_dirs counts as carried only when it is one of
    # these or inside one, so a relocated library is reported as outside the backup. Unset: agent_dirs alone.
    agent_paths: str = ""

    def agent_dir_names(self) -> frozenset[str]:
        return frozenset(n for n in self.agent_dirs.replace(",", " ").split() if n)

    def agent_path_list(self) -> tuple[Path, ...]:
        return tuple(Path(x.strip()) for x in self.agent_paths.split(",") if x.strip())

    def validate(self) -> None:
        u = urlsplit(self.agent_url)
        if u.scheme != "http" or (u.hostname or "") not in LOOPBACK_HOSTS:
            raise ValueError("ONEMIND_BACKUPS_AGENT_URL must be http://127.0.0.1:<port> (the agent is loopback-only)")
        if not -1 <= self.minute <= 59:
            raise ValueError("ONEMIND_BACKUPS_MINUTE must be -1..59")
        if self.export_dir is not None and not Path(self.export_dir).is_absolute():
            raise ValueError("ONEMIND_BACKUPS_EXPORT_DIR must be an absolute path")
        if bad := sorted(n for n in self.agent_dir_names() if not re.fullmatch(r"ONEMIND_[A-Z0-9_]+", n)):
            raise ValueError(f"ONEMIND_BACKUPS_AGENT_DIRS names settings, not {bad}")
        if bad := sorted(str(x) for x in self.agent_path_list() if not x.is_absolute()):
            raise ValueError(f"ONEMIND_BACKUPS_AGENT_PATHS must be absolute folders, not {bad}")
        if self.job_timeout_s <= 0 or self.health_deadline_s <= 0:
            raise ValueError("ONEMIND_BACKUPS_JOB_TIMEOUT_S and _HEALTH_DEADLINE_S must be positive")
