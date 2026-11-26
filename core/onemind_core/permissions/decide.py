# SPDX-License-Identifier: Apache-2.0
"""`decide()`: the one ordered decision for a request (gateway permissions design §3.5.2, fix 8).

Deny first: the stop buttons, then Locked, then deny rules, then the scope and the risk, then the
hard floor, and only then the mode and the owner's rules. Nothing later in the list can undo an
earlier "no", so a narrower allow never opens a deny and no mode lifts the floor.

     1. agents stopped (agents) / motion lockout (physical) / automation paused (automations) -> refuse
     2. mode Locked                                                                         -> refuse
     3. a deny rule matches (principal x type or tier)                                     -> refuse
     4. the token may not request this type                                                -> refuse
     5. effective risk unknown                                                             -> refuse
     6. a hard floor item (floor.py)                          -> wait for a person (Headless: refuse)
     7. clock not trusted, floor settings off, no owner passkey yet       -> treat the mode as Always ask
     8. mode Always ask or Ask once then remember                                          -> wait
     9. (bypass in a sandbox: design PR 23; until then Bypass behaves as Auto within rules)
    10. mode Auto, Headless or Bypass and a live rule matches             -> approve as policy:<id>@<rev>
    11. mode Headless                                                       -> refuse ("no rule covers this")
    12. otherwise                                                                          -> wait

`decide()` is pure: the engine (engine.py) gathers the facts. It never reserves a rule's use; the
policy module does that after a request is filed, and a rule that runs out in between leaves the
request waiting.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..automation.registry import RISKS
from .floor import floor_items

MODES = ("locked", "ask", "remember", "auto", "headless", "bypass")
RULE_MODES = frozenset({"auto", "headless", "bypass"})
AI_KINDS = frozenset({"agent", "plugin"})


@dataclass(frozen=True)
class Facts:
    principal: str  # the display key, kind:id
    kind: str
    action_type: str
    risk: str | None  # the effective risk of this exact request
    mode: str = "auto"
    physical: bool = False
    tainted: bool = False
    exposed: bool = False
    network_paths: bool = False
    sealed: bool = False
    licence_green: bool = True
    agents_stopped: bool = False
    motion_lockout: bool = False
    automation_paused: bool = False
    deny: str | None = None  # id of a deny rule that matches
    scope_ok: bool = True
    clock_trusted: bool = True
    floor_settings_on: bool = True
    owner_passkey: bool = True
    rule: str | None = None  # "policy:<id>@<rev>" of a live rule that would cover it


@dataclass(frozen=True)
class Decision:
    outcome: str  # approve | wait | refuse
    reason: str
    step: int
    via: str | None = None
    floor: tuple[str, ...] = field(default=())

    def to_json(self) -> dict:
        out = {"outcome": self.outcome, "reason": self.reason, "step": self.step}
        if self.via:
            out["via"] = self.via
        if self.floor:
            out["floor"] = list(self.floor)
        return out


def decide(f: Facts) -> Decision:
    if f.agents_stopped and f.kind in AI_KINDS:
        return Decision("refuse", "agents_stopped", 1)
    if f.physical and f.motion_lockout:
        return Decision("refuse", "motion_lockout", 1)
    if f.automation_paused and f.kind == "automation":
        return Decision("refuse", "automation_paused", 1)
    if f.mode == "locked":
        return Decision("refuse", "mode_locked", 2)
    if f.deny is not None:
        return Decision("refuse", "denied_by_rule", 3, via=f.deny)
    if not f.scope_ok:
        return Decision("refuse", "scope", 4)
    if f.risk not in RISKS:
        return Decision("refuse", "unknown_risk", 5)
    items = floor_items(action_type=f.action_type, kind=f.kind, risk=f.risk, physical=f.physical, tainted=f.tainted,
                        exposed=f.exposed, network_paths=f.network_paths, sealed=f.sealed,
                        licence_green=f.licence_green)
    if items:
        if f.mode == "headless":
            return Decision("refuse", f"floor:{items[0]}", 6, floor=items)
        return Decision("wait", f"floor:{items[0]}", 6, floor=items)
    mode = f.mode if f.mode in MODES else "ask"  # an unknown mode is the default
    if not f.clock_trusted:
        return Decision("wait", "clock_untrusted", 7)
    if not f.floor_settings_on:
        return Decision("wait", "floor_settings_off", 7)
    if not f.owner_passkey and mode != "ask":
        return Decision("wait", "no_owner_passkey", 7)
    if mode in ("ask", "remember"):
        return Decision("wait", f"mode_{mode}", 8)
    if mode in RULE_MODES and f.rule:
        return Decision("approve", "rule", 10, via=f.rule)
    if mode == "headless":
        return Decision("refuse", "no_rule", 11)
    return Decision("wait", "no_rule", 12)
