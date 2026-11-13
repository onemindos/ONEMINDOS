# SPDX-License-Identifier: Apache-2.0
"""Per-agent limits on /mcp (docs/leap/dev/MCP.md §5.4, DEV-MCP-4).

In-memory sliding windows per principal, on the gateway's clock (so tests advance time instead of
sleeping). A restart resets them; the pending cap is counted from the ledger and survives restarts.
Defaults can be changed with ONEMIND_MCP_* (see McpSettings).
"""

from __future__ import annotations

import math
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from ..sections import config_section


@config_section("mcp")
@dataclass(frozen=True)
class McpSettings:
    messages_per_minute: int = 120   # ONEMIND_MCP_MESSAGES_PER_MINUTE: HTTP 429 above it
    reads_per_minute: int = 60       # ONEMIND_MCP_READS_PER_MINUTE: read tools and resources
    requests_per_hour: int = 10      # ONEMIND_MCP_REQUESTS_PER_HOUR: request_action calls
    pending_max: int = 10            # ONEMIND_MCP_PENDING_MAX: awaiting_approval per agent

    def validate(self) -> None:
        for name in ("messages_per_minute", "reads_per_minute", "requests_per_hour", "pending_max"):
            if getattr(self, name) < 1:
                raise ValueError(f"ONEMIND_MCP_{name.upper()} must be at least 1")


class Window:
    """At most `limit` events per `period_s` per key. hit() returns 0 if allowed, else seconds to wait."""

    def __init__(self, limit: int, period_s: float, clock: Callable[[], datetime]):
        self.limit, self.period_s, self.clock = limit, period_s, clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> int:
        now = self.clock().timestamp()
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and q[0] <= now - self.period_s:
                q.popleft()
            if len(q) >= self.limit:
                return max(1, math.ceil(q[0] + self.period_s - now))
            q.append(now)
            return 0


class Limits:
    def __init__(self, s: McpSettings, clock: Callable[[], datetime]):
        self.settings = s
        self.messages = Window(s.messages_per_minute, 60, clock)
        self.reads = Window(s.reads_per_minute, 60, clock)
        self.requests = Window(s.requests_per_hour, 3600, clock)
