# SPDX-License-Identifier: Apache-2.0
"""Taint: an agent that read text from an outside source cannot act without a person (AIG-04, #168).

Prompt injection has no reliable prevention (Foundation Report ch. 3): text a model reads can tell
it to do things, and the model may obey. So the gateway does not try to detect bad text. It records
that an agent *read* third-party text, and from then on treats everything that agent asks for as
suspect:

- the request is filed with a `taint` note on its plan, so the approval card says where the
  agent's context came from;
- no standing approval (contract §12.17) may accept it, however the owner set the policy up;
- the owner's approval must name the plan fingerprint (plan_sha256), so the person approves the
  exact parameters they were shown, not "whatever this action id means now";
- the app it targets must be visible to AI under the app's own aiPolicy (ai_policy.require, #165).

Where taint comes from: an MCP tool or resource result that carries `onemind/untrusted` text
(mcp/tools.py), and every REST read an agent makes (`rest_source` below). The REST routes an agent
may read (apps, nodes, actions, audit, events ...) return the same third-party text MCP marks, so a
REST read taints exactly like an MCP read. It is deny by default: a read taints unless its route is
in `REST_CLEAN_READS`, which serve only what the gateway or the owner wrote.

Taint is held in memory for the gateway process and expires after `TTL` without a new read. Each
read renews it. A restart forgets who was tainted, but the plan note on an action already filed
survives in the ledger, so a pending tainted request stays tainted. Nothing an agent sends can
lower its own taint; an agent may only add to it.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

TTL = timedelta(hours=1)
MAX_SOURCES = 8
PLAN_KEY = "taint"  # where the note sits in Action.plan (outside the fingerprint, see actions.py)
MAX_SOURCE_LEN = 80
# Agent-readable REST routes that carry no third-party text: the box's own name, version and node id
# (MCP get_instance, which never taints, serves the same), and the owner's agent kill switch.
REST_CLEAN_READS = frozenset({"/v1/instance", "/v1/agents/kill-switch"})
READ_METHODS = frozenset({"GET", "HEAD"})


@dataclass(frozen=True)
class Taint:
    sources: tuple[str, ...]  # what the agent read, e.g. "mcp:list_apps"; newest last, capped
    since: datetime
    until: datetime

    def note(self) -> dict:
        """The record stored on the action's plan and shown on the approval card."""
        return {
            "sources": list(self.sources),
            "since": self.since.isoformat().replace("+00:00", "Z"),
            "message": "This agent read text written by third parties before asking. "
                       "Check the request against what you wanted, not against what the agent says.",
        }


class TaintLedger:
    def __init__(self, clock: Callable[[], datetime], ttl: timedelta = TTL):
        self._clock = clock
        self._ttl = ttl
        self._lock = threading.Lock()
        self._by_principal: dict[str, Taint] = {}

    def mark(self, principal_id: str, source: str) -> None:
        source = source[:MAX_SOURCE_LEN]
        now = self._clock()
        with self._lock:
            old = self._by_principal.get(principal_id)
            if old is not None and old.until <= now:
                old = None
            sources = old.sources if old else ()
            if source not in sources:
                sources += (source,)
            self._by_principal[principal_id] = Taint(
                sources[-MAX_SOURCES:], old.since if old else now, now + self._ttl)
            if len(self._by_principal) > 1024:  # drop expired entries; live ones are never dropped
                self._by_principal = {k: v for k, v in self._by_principal.items() if v.until > now}

    def get(self, principal_id: str) -> Taint | None:
        now = self._clock()
        with self._lock:
            t = self._by_principal.get(principal_id)
            if t is not None and t.until <= now:
                del self._by_principal[principal_id]
                return None
            return t


def plan_taint(plan: dict | None) -> dict | None:
    """The taint note on a filed action's plan, or None."""
    note = (plan or {}).get(PLAN_KEY)
    return note if isinstance(note, dict) and note else None


def rest_source(scope: dict) -> str | None:
    """The taint source of a REST request (an ASGI scope), or None when it reads nothing third-party.

    A read is GET or HEAD, or any WebSocket (event streams). The route template, not the raw path,
    names the source: "rest:GET /v1/apps/{app_id}", so the card never repeats text from the URL.
    """
    kind = scope.get("type")
    if kind == "websocket":
        method = "WS"
    elif kind == "http" and scope.get("method") in READ_METHODS:
        method = scope["method"]
    else:
        return None
    path = getattr(scope.get("route"), "path", None) or scope.get("path") or ""
    if path in REST_CLEAN_READS:
        return None
    return f"rest:{method} {path}"
