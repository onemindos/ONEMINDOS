# SPDX-License-Identifier: Apache-2.0
"""Risk class and automation eligibility of each action type (contract §12.3, §12.5).

This mirrors the §12.5 registry for what automation needs: the risk class (with the
parameter-dependent upgrades) and whether an automation (`Au`) may request the type. The ledger
files only the types `actions.ActionType` lists today; `fileable()` reads that, so automation
covers each new type the moment the action registry (CORE-AUTO-1) adds it.
"""

from __future__ import annotations

import typing
from dataclasses import dataclass

from ..actions import ActionType

RISKS = ("read", "write", "sensitive", "destructive", "actuate")
POLICY_MAX_RISK = "write"  # §12.3: a standing approval covers only read and write types


@dataclass(frozen=True)
class TypeInfo:
    risk: str
    automation: bool  # §12.5 "Requested by" includes Au


# §12.5, in table order. Types an automation may never request still appear, so a standing
# approval covering them (for an agent or a person) is validated against the right risk.
TYPES: dict[str, TypeInfo] = {
    "app.install": TypeInfo("sensitive", True),
    "app.remove": TypeInfo("write", True),
    "app.update": TypeInfo("write", True),
    "app.rollback": TypeInfo("write", True),
    "app.restart": TypeInfo("write", True),
    "app.configure": TypeInfo("write", False),
    "app.reconcile": TypeInfo("write", True),
    "app.move": TypeInfo("sensitive", False),
    "node.join": TypeInfo("sensitive", False),
    "node.drain": TypeInfo("write", True),
    "node.uncordon": TypeInfo("write", True),
    "node.label": TypeInfo("write", True),
    "node.set_role": TypeInfo("sensitive", False),
    "node.renew": TypeInfo("write", True),
    "node.remove": TypeInfo("destructive", False),
    "backup.run": TypeInfo("write", True),
    "backup.verify": TypeInfo("write", True),
    "backup.restore": TypeInfo("destructive", False),
    "backup.destination.add": TypeInfo("sensitive", False),
    "backup.destination.remove": TypeInfo("destructive", False),
    "backup.snapshot.delete": TypeInfo("destructive", False),
    "backup.prune": TypeInfo("destructive", False),
    "backup.key.rotate": TypeInfo("destructive", False),
    "backup.kit.issue": TypeInfo("sensitive", False),
    "os.update.check": TypeInfo("read", True),
    "os.update.apply": TypeInfo("write", True),
    "os.update.postpone": TypeInfo("write", False),
    "os.update.settings": TypeInfo("sensitive", False),
    "os.rollback": TypeInfo("destructive", False),
    "automation.rule.create": TypeInfo("write", False),
    "automation.rule.update": TypeInfo("write", False),
    "automation.rule.enable": TypeInfo("write", False),
    "agent.resume": TypeInfo("sensitive", False),
    "tls.acme.set": TypeInfo("sensitive", False),
    "system.check": TypeInfo("read", True),
    "system.restart_unit": TypeInfo("write", True),
    "catalog.refresh": TypeInfo("write", True),
}


def known(action_type: str) -> bool:
    return action_type in TYPES


def risk_of(action_type: str, params: dict | None = None) -> str:
    """The risk class of one request, including §12.5's parameter-dependent upgrades."""
    params = params or {}
    base = TYPES[action_type].risk
    if action_type == "app.remove" and params.get("delete_data"):
        return "destructive"
    if action_type == "os.update.apply" and params.get("reboot") == "now":
        return "destructive"
    if action_type == "app.configure" and params.get("sealed"):
        return "sensitive"
    return base


def at_most(risk: str, ceiling: str) -> bool:
    return RISKS.index(risk) <= RISKS.index(ceiling)


# `write` types a standing approval still never covers: an agent proposes an automation and the
# owner approves it; it never creates, edits or enables one itself (docs/leap/core/AUTOMATION.md
# §1, §3). A policy here would also let an agent-made rule borrow an `automation:*` approval.
NEVER_BY_POLICY = frozenset({"automation.rule.create", "automation.rule.update", "automation.rule.enable"})


def policy_may_cover(action_type: str, params: dict | None = None) -> str | None:
    """Why no standing approval may accept this request, or None (§12.3: read and write only)."""
    if action_type not in TYPES:
        return f"unknown action type {action_type!r}"
    if action_type in NEVER_BY_POLICY:
        return f"{action_type} always waits for the owner; a standing approval never covers it"
    risk = risk_of(action_type, params)
    if not at_most(risk, POLICY_MAX_RISK):
        return f"{action_type} is {risk}; a standing approval covers only read and write types (§12.3)"
    return None


def automatable(action_type: str, params: dict | None = None) -> str | None:
    """Why an automation may not request this, or None (§12.1: Au types, never destructive)."""
    if action_type not in TYPES:
        return f"unknown action type {action_type!r}"
    if not TYPES[action_type].automation:
        return f"an automation may not request {action_type} (contract §12.5)"
    risk = risk_of(action_type, params)
    if risk in ("destructive", "actuate"):
        return f"{action_type} with these parameters is {risk}; automations never request it (F-11)"
    return None


def fileable() -> frozenset[str]:
    """The types the action ledger accepts today."""
    return frozenset(typing.get_args(ActionType))
