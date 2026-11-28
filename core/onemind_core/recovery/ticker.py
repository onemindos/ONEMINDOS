# SPDX-License-Identifier: Apache-2.0
"""A small background clock for recovery: close lapsed requests and send the notices due during a wait.

Run a pass on startup to pick up notices left by the previous gateway process.
The wait ends at its not_before time whatever the ticker does."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

log = logging.getLogger("onemind.recovery")


class Ticker:
    def __init__(self, jobs: list[Callable[[], object]], every_s: float = 300.0):
        self.jobs, self.every_s = jobs, every_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="onemind-recovery", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            for job in self.jobs:
                try:
                    job()
                except Exception:  # one bad tick must not stop the clock
                    log.exception("recovery tick failed")
            self._stop.wait(self.every_s)
