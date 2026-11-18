# SPDX-License-Identifier: Apache-2.0
"""System controls (UMB-P09, #146): the diagnostic bundle, restart, shutdown and factory reset.

Restart, shutdown and factory reset are feature action types (actions.py): an owner (or, for restart
and shutdown, an agent) *requests* one, only an owner approves, and nothing reaches the host before
the approval. Factory reset is destructive: it is approved only with the owner's passkey (the guard
in routers/system.py, on top of identity's), and only an owner may even ask for it.

The host path: the gateway runs inside k3s and has no way to power the host off yet. `onemindd`
reboots only from the rescue console (internal/rescue, a person at the LAN page) and the update
engine (internal/update); neither listens to the gateway. Until a host service exists (a Unix socket
like `onemindd storage serve`), the executor here is `NoHostPath`: an approved control ends `failed`
with that reason, so the ledger shows the owner's decision and the box never pretends it acted.

The diagnostic bundle is what support needs to see what is wrong, and nothing personal: versions,
node health, recent actions and audit event names. Every string goes through `redact`, which covers
the public-repo hygiene patterns (scripts/hygiene.py: home paths, private IPv4, tailnet names, e-mail
addresses) plus every IP address, secret-looking keys and long token-shaped values.
"""

from __future__ import annotations

import re
from collections import Counter, deque
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from . import __version__
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


class SystemExecutor(Protocol):
    """Performs a control on the host after approval."""

    def unavailable(self, action_type: str) -> str | None:
        """Why this control cannot run on this box, or None when it can."""

    def run(self, action_type: str) -> ExecResult: ...


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
    # Full IPv6 (8 groups) or compressed ("::"); a clock time (hh:mm:ss) is neither.
    ("ipv6", re.compile(r"\b(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}\b|(?:[0-9A-Fa-f]{1,4})?::(?:[0-9A-Fa-f]{1,4}:?)*"), "[ip]"),
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
        finish(ExecResult("failed", why, steps=[{"step": "host", "result": "unavailable"}]) if why
               else self.executor.run(a.type))

    def diagnostics(self) -> dict:
        gw = self.gw
        actions = gw.actions.list()
        recent = sorted(actions, key=lambda a: a.get("created_at") or "", reverse=True)[:RECENT_ACTIONS]
        audit: deque[dict] = deque(maxlen=RECENT_AUDIT)
        for _, rec in iter_records(gw.audit.path):
            audit.append({"seq": rec.get("seq"), "ts": rec.get("ts"), "event": rec.get("event"),
                          "principal_kind": (rec.get("principal") or {}).get("kind"), "action_id": rec.get("action_id")})
        bundle = {
            "schema": BUNDLE_SCHEMA,
            "generated_at": iso(gw.clock()),
            "gateway": {"version": __version__, "executor": gw.settings.executor, "hub_node_id": gw.settings.node_id},
            "nodes": gw.registry.list(),
            "actions": {
                "by_state": dict(sorted(Counter(a["state"] for a in actions).items())),
                "recent": [{k: a.get(k) for k in ("id", "type", "state", "created_at", "updated_at")}
                           | {"message": (a.get("result") or {}).get("message")} for a in recent],
            },
            "audit": list(audit),
            "system_controls": self.controls()["controls"],
        }
        clean, found = redact(bundle)
        clean["redaction"] = {"rules": [name for name, _, _ in _RULES] + ["secret-field"], "found": found}
        return clean
