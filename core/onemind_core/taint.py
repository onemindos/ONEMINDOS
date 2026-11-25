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
(mcp/tools.py, and MCP tasks/get, mcp/tasks.py), and every REST read an agent makes (`rest_source`
below). The REST routes an agent may read (apps, nodes, actions, audit, events ...) return the same
third-party text MCP marks, so a REST read taints exactly like an MCP read. It is deny by default: a
read taints unless its route is in `REST_CLEAN_READS`, which serve only what the gateway or the owner
wrote. A read is GET, HEAD, a WebSocket, or a POST that only previews (`REST_READ_POSTS`: POST
/v1/plans returns a plan built from the app's manifest and files nothing; POST /v1/storage/plans
returns a storage plan that carries disk text, a firmware model and filesystem labels, and files nothing).

An agent's own request (POST /v1/actions, POST /v1/alerts/{id}/fix) is answered without
third-party text (`agent_answer`), as MCP request_action answers with only the id and the state:
the plan carries manifest text (the app's name, its tool and stream names) and the result carries
the executor's output, so the answer keeps the id, the state, the risk and the plan fingerprint and
leaves the plan and result out. An agent that wants them reads the action (GET /v1/actions/{id})
and is tainted by that read. Should an answer ever carry plan or result text, the route taints the
agent once the answer is built (`answer_source`): the request itself is filed clean, the next one
is not. Owner-set approval policies therefore keep working for an agent that reads nothing.

Taint expires after `TTL` without a new read. Each read renews it. It is written through to the
database (`agents_taint_marks`, taint_store.py) on every mark and read back at start, so a restart no
longer forgets who was tainted, and the TTL runs on across the restart. Nothing an agent sends
can lower its own taint; an agent may only add to it.

An *exposed* agent is tainted all the time (gateway permissions PR 6, F-11 = a). The gateway sees only
the text an agent reads through the gateway; a web page, an email or a file the agent opens with
its own tools is invisible to it. So every agent and plugin is treated as permanently tainted until the owner
declares what it reads (D-028; including "nothing") (`exposure`, taint_store.py): `get` answers a taint that
never expires, with a source per input. Only the owner can change that declaration.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

log = logging.getLogger("onemind.taint")

TTL = timedelta(hours=1)
FOREVER = datetime(9999, 12, 31, tzinfo=UTC)  # `until` of an exposed agent: it never expires
MAX_SOURCES = 8
PLAN_KEY = "taint"  # where the note sits in Action.plan (outside the fingerprint, see actions.py)
MAX_SOURCE_LEN = 80
# Agent-readable REST routes that carry no third-party text: the box's own name, version and node id
# (MCP get_instance, which never taints, serves the same), and the owner's agent kill switch.
REST_CLEAN_READS = frozenset({"/v1/instance", "/v1/agents/kill-switch"})
READ_METHODS = frozenset({"GET", "HEAD"})
# POST routes an agent may call that only read: they file nothing and answer with third-party text.
REST_READ_POSTS = frozenset({"/v1/plans", "/v1/storage/plans"})


@dataclass(frozen=True)
class Exposure:
    """What an agent is declared (or defaults) to read outside the gateway's sight."""

    inputs: tuple[str, ...]  # "web", "email", "files", "chat", "app", "plugin", "agent"
    since: datetime


@dataclass(frozen=True)
class Taint:
    sources: tuple[str, ...]  # what the agent read, e.g. "mcp:list_apps"; newest last, capped
    since: datetime
    until: datetime

    @property
    def permanent(self) -> bool:
        return self.until >= FOREVER

    def note(self) -> dict:
        """The record stored on the action's plan and shown on the approval card."""
        return {
            "sources": list(self.sources),
            "since": self.since.isoformat().replace("+00:00", "Z"),
            "message": "This agent can read text written by third parties outside OneMind (web, email, files). "
                       "Check the request against what you wanted, not against what the agent says."
                       if self.permanent else
                       "This agent read text written by third parties before asking. "
                       "Check the request against what you wanted, not against what the agent says.",
        }


class TaintLedger:
    def __init__(self, clock: Callable[[], datetime], ttl: timedelta = TTL):
        self._clock = clock
        self._ttl = ttl
        self._lock = threading.Lock()
        self._by_principal: dict[str, Taint] = {}
        # Set by attach(): durable storage for the transient marks, exposure lookup, audit hook.
        self._store = None
        self._exposure: Callable[..., Exposure | None] = lambda _pid, _kind=None: None
        self._on_event: Callable[[str, str, dict], None] | None = None

    def attach(self, store, exposure: Callable[..., Exposure | None],
               on_event: Callable[[str, str, dict], None] | None = None) -> None:
        """Back the ledger with the database and an exposure lookup; reload marks still alive."""
        now = self._clock()
        loaded = {pid: t for pid, t in store.load().items() if t.until > now}
        with self._lock:
            self._store, self._exposure, self._on_event = store, exposure, on_event
            for pid, t in loaded.items():
                self._by_principal.setdefault(pid, t)

    def _emit(self, event: str, pid: str, data: dict) -> None:
        if self._on_event is not None:
            try:
                self._on_event(event, pid, data)
            except Exception:  # an audit failure must not lose the taint
                log.exception("taint audit failed")

    def mark(self, principal_id: str, source: str) -> None:
        source = source[:MAX_SOURCE_LEN]
        now = self._clock()
        fresh = False
        with self._lock:
            old = self._by_principal.get(principal_id)
            if old is not None and old.until <= now:
                old = None
            fresh = old is None
            sources = old.sources if old else ()
            if source not in sources:
                sources += (source,)
            t = Taint(sources[-MAX_SOURCES:], old.since if old else now, now + self._ttl)
            self._by_principal[principal_id] = t
            if len(self._by_principal) > 1024:  # drop expired entries; live ones are never dropped
                self._by_principal = {k: v for k, v in self._by_principal.items() if v.until > now}
            store = self._store
        if store is not None:  # the database write stays outside the process-wide lock
            try:
                store.save(principal_id, t)
            except Exception:  # the in-memory mark still holds; never fail a read for storage
                log.exception("taint store write failed")
        if fresh:
            self._emit("taint.set", principal_id, {"source": source})

    def get(self, principal_id: str, kind: str | None = None) -> Taint | None:
        """The taint of a caller. Pass the principal's kind: an unknown kind counts as exposed."""
        now = self._clock()
        exposed = self._exposure(principal_id, kind)  # an Exposure, or None
        expired = False
        with self._lock:
            t = self._by_principal.get(principal_id)
            if t is not None and t.until <= now:
                del self._by_principal[principal_id]
                expired = True
                t = None
        if expired and self._store is not None:  # the database write stays outside the process-wide lock
            try:
                self._store.delete(principal_id)
            except Exception:
                log.exception("taint store delete failed")
        if expired and exposed is None:
            self._emit("taint.cleared", principal_id, {"reason": "expired"})
        if exposed is not None:
            names = tuple(f"input:{n}" for n in exposed.inputs)
            room = MAX_SOURCES - len(names)
            read = t.sources[-room:] if (t and room > 0) else ()
            return Taint(names + read, exposed.since, FOREVER)
        return t


def plan_taint(plan: dict | None) -> dict | None:
    """The taint note on a filed action's plan, or None."""
    note = (plan or {}).get(PLAN_KEY)
    return note if isinstance(note, dict) and note else None


def rest_source(scope: dict) -> str | None:
    """The taint source of a REST request (an ASGI scope), or None when it reads nothing third-party.

    A read is GET or HEAD, any WebSocket (event streams), or a POST in `REST_READ_POSTS`. The route
    template, not the raw path, names the source: "rest:GET /v1/apps/{app_id}", so the card never
    repeats text from the URL.
    """
    kind = scope.get("type")
    path = _route(scope)
    if kind == "websocket":
        method = "WS"
    elif kind == "http" and (scope.get("method") in READ_METHODS
                             or (scope.get("method") == "POST" and path in REST_READ_POSTS)):
        method = scope["method"]
    else:
        return None
    if path in REST_CLEAN_READS:
        return None
    return f"rest:{method} {path}"


# What an agent's own request answer keeps (deny by default): the agent's own words and what the
# gateway wrote. Left out: the plan text, the result, progress and the approval card's limits and
# preview, which can name apps or devices.
ANSWER_KEEPS = frozenset({
    "id", "type", "params", "state", "requested_by", "idempotency_key", "created_at", "updated_at",
    "expires_at", "decided_by", "decided_at", "approved_by", "version", "risk", "plan_sha256", "reason",
})
CARD_KEEPS = ("physical", "hold", "hold_ms")


def agent_answer(action: dict) -> dict:
    """An agent's own request as it is answered to the agent: no plan text, no result.

    The taint note stays, so the agent can tell its request waits for a person and why.
    """
    out = {k: v for k, v in action.items() if k in ANSWER_KEEPS}
    note = plan_taint(action.get("plan"))
    out["plan"] = {PLAN_KEY: note} if note else None
    out["result"] = None
    if isinstance(action.get("approval"), dict):
        out["approval"] = {k: action["approval"][k] for k in CARD_KEEPS if k in action["approval"]}
    return out


def answer_source(scope: dict, action: dict) -> str | None:
    """The taint source of an agent write that answers with `action`, or None when it carries no text.

    Called by the route once it has built the response (POST /v1/actions, POST
    /v1/alerts/{alert_id}/fix), so the request that produced the answer is not tainted by it. The
    answer carries text when it holds a plan (beyond a taint note the gateway wrote) or a result
    message; a feature request that is still waiting has neither.
    """
    plan = {k: v for k, v in (action.get("plan") or {}).items() if k != PLAN_KEY}
    if not plan and not (action.get("result") or {}).get("message"):
        return None
    return f"rest:{scope.get('method') or 'POST'} {_route(scope)}"


def _route(scope: dict) -> str:
    return getattr(scope.get("route"), "path", None) or scope.get("path") or ""
