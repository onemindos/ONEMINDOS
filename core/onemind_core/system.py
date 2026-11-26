# SPDX-License-Identifier: Apache-2.0
"""System controls (UMB-P09, #146): the diagnostic bundle, restart, shutdown and factory reset.

Restart, shutdown and factory reset are feature action types (actions.py): an owner (or, for restart
and shutdown, an agent) *requests* one, only an owner approves, and nothing reaches the host before
the approval. Factory reset is destructive: it is approved only with the owner's passkey (the guard
in routers/system.py, on top of identity's), and only an owner may even ask for it.

The host path: `onemindd host serve` (root, Unix socket) powers the box off or restarts it. The executor
is `HostLinkExecutor` (the gateway's HostLink, hostlink.py). `NoHostPath` stays as the explicit "no host"
executor: an approved control ends `failed` with that reason, so the box never pretends it acted.

The diagnostic bundle is what support needs to see what is wrong, and nothing personal: versions,
node health, recent actions and audit event names. Every string goes through `redact`, which covers
the public-repo hygiene patterns (scripts/hygiene.py: home paths, private IPv4, tailnet names, e-mail
addresses) plus every IP address, secret-looking keys and long token-shaped values; node ids are
replaced by a stable short hash and node names are dropped.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter, deque
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .apimodels import Action
from .auditread import iter_records
from .executors import ExecResult
from .ledger import TERMINAL, iso

BUNDLE_SCHEMA = "onemind.diagnostics/v1"
RECENT_ACTIONS = 50
RECENT_AUDIT = 200
RESET_PHRASE = "factory reset"

# type -> (label, risk class, principal kinds besides the owner that may request it, passkey step-up)
CONTROLS: dict[str, tuple[str, str, frozenset[str], bool]] = {
    "system.restart": ("Restart", "actuate", frozenset({"agent"}), False),
    "system.shutdown": ("Shut down", "actuate", frozenset({"agent"}), False),
    "system.factory_reset": ("Factory reset", "destructive", frozenset(), True),
}


class SystemActionRequest(BaseModel):
    """POST /v1/system/actions. `confirm` is the phrase the owner types for a factory reset."""

    model_config = ConfigDict(extra="forbid")
    type: Literal["system.restart", "system.shutdown", "system.factory_reset"]
    confirm: str | None = Field(default=None, max_length=40)
    reason: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


class SystemControl(BaseModel):
    """One control in GET /v1/system/controls: what it is and whether this box can perform it."""

    type: Literal["system.restart", "system.shutdown", "system.factory_reset"]
    label: str
    risk: str = Field(description="actuate | destructive (§12.3)")
    needs_passkey: bool
    confirm_phrase: str | None = Field(description="the phrase the owner types to ask for it; null when none")
    available: bool = Field(description="false: requests are refused with 409 host_unavailable")
    unavailable_reason: str | None


class SystemControls(BaseModel):
    """GET /v1/system/controls."""

    controls: list[SystemControl]
    pending: list[Action] = Field(description="system requests not yet finished")


class Redaction(BaseModel):
    rules: list[str]
    found: dict[str, int] = Field(description="how many values each rule removed")


class DiagnosticsBundle(BaseModel):
    """GET /v1/system/diagnostics: a redacted bundle for support. More fields may appear."""

    model_config = ConfigDict(extra="allow")
    schema_: str = Field(alias="schema", description=BUNDLE_SCHEMA)
    generated_at: str
    gateway: dict[str, Any]
    nodes: list[dict[str, Any]] = Field(description="node heartbeats: ids hashed, names dropped, text redacted")
    actions: dict[str, Any]
    audit: list[dict[str, Any]]
    system_controls: list[SystemControl]
    redaction: Redaction


class SystemExecutor(Protocol):
    """Performs a control on the host after approval."""

    def unavailable(self, action_type: str) -> str | None:
        """Why this control cannot run on this box, or None when it can."""

    def run(self, action_type: str) -> ExecResult: ...


class HostLinkExecutor:
    """The real host path: an approved control goes to `onemindd host serve` over the host link (hostlink.py).

    `unavailable` is the host's own answer (socket missing, no journal, kind not offered). `dispatch` sends
    the approved action id and kind, never a command, and the link's poller closes the ledger action from
    the host's journal: a restart or shutdown stops the box, so its answer can come after the gateway
    restarts (these types are SELF_RECONCILED). A refused or unreachable host ends the action `failed`."""

    def __init__(self, link) -> None:
        self.link = link

    def unavailable(self, action_type: str) -> str | None:
        problem = self.link.problem(action_type)
        return problem[1] if problem else None

    def run(self, action_type: str) -> ExecResult:  # the Protocol's synchronous form: a host action is never synchronous
        return ExecResult("failed", "a host control runs through dispatch, after approval", steps=[{"step": "host", "result": "bad_request"}])

    def dispatch(self, a, finish) -> None:
        self.link.run(a, finish)

    def reset_plan_hash(self) -> str | None:
        return self.link.reset_plan_hash()


class NoHostPath:
    """No host service yet: report the gap, never success."""

    MESSAGE = ("This version of OneMind cannot reach the host's power controls from the gateway yet. "
               "Use the rescue console or the power button; your approval is recorded.")

    def unavailable(self, action_type: str) -> str | None:
        return self.MESSAGE

    def run(self, action_type: str) -> ExecResult:
        return ExecResult("failed", self.MESSAGE, steps=[{"step": "host", "result": "unavailable"}])


# ---- redaction -----------------------------------------------------------------------------------
# The hygiene patterns (scripts/hygiene.py), written so the source itself does not match them.
_RULES: list[tuple[str, re.Pattern[str], str]] = [
    ("home-path", re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+"), "/[home]"),
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[email]"),
    ("tailnet", re.compile(r"[A-Za-z0-9.-]+\.ts\.net\b"), "[tailnet-name]"),
    ("ipv4", re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "[ip]"),
    # Full IPv6 (8 groups) or compressed ("::" with at least one hex digit), standing alone: not part
    # of a longer word, so "std::vector" and "deadbeef::cafe" survive; a clock time (hh:mm:ss) has no "::".
    ("ipv6", re.compile(r"(?<![0-9A-Za-z:])(?:(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}"
                        r"|(?=[0-9A-Fa-f:]*[0-9A-Fa-f])(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,6})?::"
                        r"(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,6})?)(?![0-9A-Za-z:])"), "[ip]"),
    ("bearer", re.compile(r"(?i)\bbearer\s+\S+"), "Bearer [token]"),
    ("token", re.compile(r"\b[A-Za-z0-9_\-]{40,}\b"), "[token]"),
]
_SECRET_KEY = re.compile(r"(?i)token|secret|password|passphrase|credential|cookie|authorization|api_?key|private|"
                         r"recovery|serial|hostname|email|^key$|_key$")


class Redactor:
    def __init__(self) -> None:
        self.count: Counter[str] = Counter()

    def text(self, s: str) -> str:
        for name, rx, repl in _RULES:
            s, n = rx.subn(repl, s)
            if n:
                self.count[name] += n
        return s

    def value(self, v: Any, key: str = "") -> Any:
        if key and _SECRET_KEY.search(key) and v not in (None, "", [], {}):
            self.count["secret-field"] += 1
            return "[redacted]"
        if isinstance(v, str):
            return self.text(v)
        if isinstance(v, dict):
            return {self.text(str(k)): self.value(x, str(k)) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [self.value(x) for x in v]
        return v


# Node heartbeats are free-form: a node's id or name ("zeus-mbp") can name a person. Ids become a
# stable short hash (the same node keeps the same pseudonym across bundles, so support can still
# follow one machine), and name-like fields are dropped.
_NODE_ID_KEYS = frozenset({"node_id", "hub_node_id"})
_NAME_KEY = re.compile(r"(?i)name|label|nickname")


def node_pseudonym(node_id: str) -> str:
    return "node-" + hashlib.sha256(node_id.encode()).hexdigest()[:12]


def pseudonymize(v: Any, found: Counter[str]) -> Any:
    """v with node ids hashed and name-like fields dropped, at every depth."""
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            if k in _NODE_ID_KEYS and isinstance(x, str):
                out[k] = node_pseudonym(x)
                found["node-id"] += 1
            elif _NAME_KEY.search(str(k)):
                found["name-field"] += 1
            else:
                out[k] = pseudonymize(x, found)
        return out
    if isinstance(v, (list, tuple)):
        return [pseudonymize(x, found) for x in v]
    return v


def redact(obj: Any) -> tuple[Any, dict[str, int]]:
    """obj with every personal or secret-looking value replaced, and how many of each were found."""
    r = Redactor()
    return r.value(obj), dict(sorted(r.count.items()))


# ---- the service ---------------------------------------------------------------------------------
class SystemService:
    def __init__(self, gw, executor: SystemExecutor | None = None):
        self.gw = gw
        self.executor: SystemExecutor = executor or NoHostPath()

    def controls(self) -> dict:
        pending = [a for a in self.gw.actions.list() if a["type"] in CONTROLS and a["state"] not in TERMINAL]
        return {
            "controls": [{
                "type": t, "label": label, "risk": risk, "needs_passkey": passkey,
                "confirm_phrase": RESET_PHRASE if t == "system.factory_reset" else None,
                "available": self.executor.unavailable(t) is None, "unavailable_reason": self.executor.unavailable(t),
            } for t, (label, risk, _, passkey) in CONTROLS.items()],
            "pending": pending,
        }

    def run(self, a, finish) -> None:
        """After approval: the host executor's result, or `failed` with the reason it cannot run."""
        why = self.executor.unavailable(a.type)
        if why:
            finish(ExecResult("failed", why, steps=[{"step": "host", "result": "unavailable"}]))
        elif isinstance(self.executor, HostLinkExecutor):
            self.executor.dispatch(a, finish)  # closes now on a refusal, else when the host's journal says so
        else:
            finish(self.executor.run(a.type))

    def diagnostics(self) -> dict:
        gw = self.gw
        actions = gw.actions.list()
        recent = sorted(actions, key=lambda a: a.get("created_at") or "", reverse=True)[:RECENT_ACTIONS]
        audit: deque[dict] = deque(maxlen=RECENT_AUDIT)
        for _, rec in iter_records(gw.audit.path):
            audit.append({"seq": rec.get("seq"), "ts": rec.get("ts"), "event": rec.get("event"),
                          "principal_kind": (rec.get("principal") or {}).get("kind"), "action_id": rec.get("action_id")})
        named: Counter[str] = Counter()
        bundle = {
            "schema": BUNDLE_SCHEMA,
            "generated_at": iso(gw.clock()),
            "gateway": pseudonymize({"version": __version__, "executor": gw.settings.executor,
                                     "hub_node_id": gw.settings.node_id}, named),
            "nodes": pseudonymize(gw.registry.list(), named),
            "actions": {
                "by_state": dict(sorted(Counter(a["state"] for a in actions).items())),
                "recent": [{k: a.get(k) for k in ("id", "type", "state", "created_at", "updated_at")}
                           | {"message": (a.get("result") or {}).get("message")} for a in recent],
            },
            "audit": list(audit),
            "system_controls": self.controls()["controls"],
        }
        clean, found = redact(bundle)
        found = dict(sorted((Counter(found) + named).items()))
        clean["redaction"] = {"rules": [name for name, _, _ in _RULES] + ["secret-field", "node-id", "name-field"],
                              "found": found}
        return clean
