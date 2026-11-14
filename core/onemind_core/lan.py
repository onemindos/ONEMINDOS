# SPDX-License-Identifier: Apache-2.0
"""LAN names over mDNS: onemind.local, <app>.<box>.local, <app>.onemind.local (NETWORKING.md §9.1).

The gateway knows which apps are installed, so it keeps one `avahi-publish -a -R <name> <hub LAN
address>` child per name (avahi-utils; the daemon's D-Bus API, open to every local user). A name
another device already answers is a conflict: avahi-publish exits, the name is left alone for
CONFLICT_RETRY_S and `lan.name_conflict` is raised once, and the box stays reachable as <box>.local
(avahi-daemon publishes the hostname itself). `-R` skips the reverse (PTR) record, because many
names share one address.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import subprocess
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

log = logging.getLogger("onemind.lan")

NAME_RE = re.compile(r"^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+local$")
CONFLICT_RETRY_S = 300.0
RESTART_BACKOFF_S = 5.0

Spawn = Callable[[list[str]], subprocess.Popen]


def _spawn(argv: list[str]) -> subprocess.Popen:
    return subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def desired_names(box: str, apps: Iterable[str], *, hostname_label: str | None = None) -> set[str]:
    """onemind.local, <box>.local (unless avahi already publishes it as the hostname), and two names per app."""
    names = {"onemind.local"}
    if hostname_label != box:
        names.add(f"{box}.local")
    for app in apps:
        names.add(f"{app}.{box}.local")
        names.add(f"{app}.onemind.local")
    return {n for n in names if NAME_RE.match(n)}


@dataclass
class _Child:
    proc: subprocess.Popen
    started: float
    restarts: int = 0


@dataclass
class AvahiPublisher:
    addr: str
    on_conflict: Callable[[str], None] | None = None
    binary: str = "avahi-publish"
    spawn: Spawn = _spawn
    clock: Callable[[], float] = time.monotonic
    _children: dict[str, _Child] = field(default_factory=dict)
    _conflicts: dict[str, float] = field(default_factory=dict)
    _backoff: dict[str, float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self):
        if ipaddress.ip_address(self.addr).version != 4:
            raise ValueError("mDNS address must be IPv4")

    def published(self) -> set[str]:
        with self._lock:
            return {n for n, c in self._children.items() if c.proc.poll() is None}

    def conflicts(self) -> set[str]:
        with self._lock:
            return set(self._conflicts)

    def sync(self, names: set[str]) -> None:
        """Make the running children match names: start new ones, stop removed ones, restart dead ones."""
        now = self.clock()
        with self._lock:
            for name in list(self._children):
                child = self._children[name]
                if name not in names:
                    self._stop(child)
                    del self._children[name]
                    continue
                if child.proc.poll() is not None:  # exited: a conflict, or avahi-daemon restarted
                    err = b""
                    try:
                        err = child.proc.stderr.read() if child.proc.stderr else b""
                    except (OSError, ValueError):
                        pass
                    del self._children[name]
                    if b"collision" in err.lower() or b"conflict" in err.lower():
                        if name not in self._conflicts and self.on_conflict:
                            self.on_conflict(name)
                        self._conflicts[name] = now
                    else:
                        self._backoff[name] = now + RESTART_BACKOFF_S
            for name in sorted(names - set(self._children)):
                since = self._conflicts.get(name)
                if since is not None and now - since < CONFLICT_RETRY_S:
                    continue
                if self._backoff.get(name, 0) > now:
                    continue
                try:
                    proc = self.spawn([self.binary, "-a", "-R", name, self.addr])
                except OSError as exc:
                    log.warning("mDNS: cannot run %s (%s); names are not published", self.binary, exc)
                    return
                self._children[name] = _Child(proc, now)
            for name in [n for n in self._conflicts if n not in names]:
                del self._conflicts[name]

    def stop_all(self) -> None:
        with self._lock:
            for child in self._children.values():
                self._stop(child)
            self._children.clear()

    @staticmethod
    def _stop(child: _Child) -> None:
        if child.proc.poll() is None:
            child.proc.terminate()
            try:
                child.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.proc.kill()
        if child.proc.stderr:
            child.proc.stderr.close()
