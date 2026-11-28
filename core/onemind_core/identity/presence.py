# SPDX-License-Identifier: Apache-2.0
"""Codes shown on the box for setup, recovery and local L2 verification (D-034).

On the home network an L2 approval or change can use an L1 sign-in proof and a short code shown
only on the box's screen (onemind-screen on tty1). The code belongs to that particular challenge.

How it works:
- A challenge that needs the box makes a 6-digit code, keeps only its SHA-256 in the challenge row and
  writes the code, what it is for and when it expires to `box_code_file` (0640, the gateway's own
  folder on /data). The screen reads that file every few seconds. **No API answer ever carries the
  code**, so nothing reachable over the network can read it.
- The code lives as long as its challenge (2 minutes) and is checked once, with the challenge: a wrong
  code burns the challenge, and the next try makes a new code. After MAX_FAILURES wrong codes in
  FAILURE_WINDOW the box stops making codes for that window, so guessing is never worth it.
- No `box_code_file` (a box with no screen service, a compose install) means nobody can confirm at the
  box: those L2 actions wait for a proven key (N-1 a), and the answer says why.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
import threading
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

from ..errors import ApiError

CODE_DIGITS = 6
MAX_FAILURES = 5
FAILURE_WINDOW = timedelta(minutes=15)


def code_sha256(code: str) -> str:
    return "sha256:" + hashlib.sha256(code.encode()).hexdigest()


class BoxPresence:
    def __init__(self, path: Path | None, clock, emit):
        self.path = path
        self.clock = clock
        self.emit = emit  # (name, payload, severity) -> None, audited under "auth"
        self._failures: deque[datetime] = deque()
        self._lock = threading.Lock()
        self._screen_lock = threading.Lock()

    @property
    def available(self) -> bool:
        return self.path is not None

    def _locked_out(self, now: datetime) -> bool:
        with self._lock:
            while self._failures and now - self._failures[0] > FAILURE_WINDOW:
                self._failures.popleft()
            return len(self._failures) >= MAX_FAILURES

    def issue(self, what: str, expires_at: datetime) -> str:
        """Show a new code on the box's screen; returns its digest for the challenge row."""
        now = self.clock()
        if self.path is None:
            raise ApiError(409, "conflict", "this needs your proven key (L2), or a confirmation on the box's own "
                           "screen, which this install doesn't have. Add a proven key under Settings > Security > "
                           "Sign-in keys", reason="box_presence_unavailable")
        if self._locked_out(now):
            raise ApiError(429, "rate_limited", "too many wrong box codes; try again in 15 minutes",
                           reason="box_code_locked")
        code = f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"
        doc = {"code": code, "what": what[:120], "expires_at": int(expires_at.timestamp())}
        tmp = None
        try:
            with self._screen_lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(mode="w", dir=self.path.parent, delete=False) as f:
                    tmp = f.name
                    os.fchmod(f.fileno(), 0o640)
                    json.dump(doc, f)
                os.replace(tmp, self.path)  # the screen never reads half a file
                tmp = None
        except OSError as e:
            raise ApiError(503, "unavailable", f"the box's screen can't be given a code: {e.strerror}",
                           reason="box_presence_unavailable") from e
        finally:
            if tmp is not None:
                try:
                    Path(tmp).unlink(missing_ok=True)
                except OSError:
                    pass
        self.emit("box_code.issued", {"attempted": what[:120]}, "info")
        return code_sha256(code)

    def check(self, want_sha: str | None, code: str | None, what: str) -> None:
        """Raise 401 unless `code` is the one this challenge showed on the box's screen."""
        now = self.clock()
        if not want_sha:
            return
        ok = bool(code) and not self._locked_out(now) and \
            hmac.compare_digest(code_sha256(str(code).strip().replace(" ", "")), want_sha)
        if ok:
            self.clear(want_sha)
            return
        with self._lock:
            self._failures.append(now)
        self.emit("box_code.failed", {"attempted": what[:120], "sent": bool(code)}, "warning")
        raise ApiError(401, "unauthenticated", "type the code shown on the box's own screen (it changes on every "
                       "try)" if not code else "that is not the code on the box's screen; ask again for a new one",
                       reason="box_code_required")

    def clear(self, displayed_sha: str) -> None:
        if self.path is not None:
            try:
                with self._screen_lock:
                    screen = json.loads(self.path.read_text())
                    if hmac.compare_digest(code_sha256(screen["code"]), displayed_sha):
                        self.path.unlink(missing_ok=True)
            except (OSError, ValueError, KeyError, TypeError):
                pass
