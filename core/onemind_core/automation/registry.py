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

_UNSET: object = object()
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
    "app.remove": TypeInfo("sensitive", True),  # moved up from write: a rule never removes an app
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
    # A handler type (routers/browsers.py): it wipes a person's browser profile, which cannot be undone.
    # Listed so every filing path knows its risk (gateway permissions PR 8: unknown risk is refused).
    "browser.profile.reset": TypeInfo("destructive", False),
}


def known(action_type: str) -> bool:
    return action_type in TYPES


def register_feature(action_type: str, risk: str, *, automation: bool = False) -> None:
    """Record a feature-registered type (ActionService.register_type) in the one risk table.

    A type already in the table must agree on its risk class: two values for one type would let a
    policy check read the lower one. An unknown risk class is refused.
    """
    if risk not in RISKS:
        raise ValueError(f"{action_type}: unknown risk class {risk!r}")
    have = TYPES.get(action_type)
    if have is None:
        TYPES[action_type] = TypeInfo(risk, automation)
    elif have.risk != risk:
        raise ValueError(f"{action_type}: registered as {risk} but the risk table says {have.risk}")


def effective_risk(action_type: str, params: dict | None = None, stored: object = _UNSET) -> str | None:
    """The risk class one request really has: the higher of the table's (with parameter upgrades)
    and the class stored on the request when it was filed (a feature's risk_for). None when there
    is no valid class to judge, which every caller treats as a refusal."""
    found = []
    if action_type in TYPES:
        found.append(risk_of(action_type, params))
    if stored is not _UNSET:
        if stored not in RISKS:
            return None
        found.append(stored)
    return max(found, key=RISKS.index) if found else None


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


# #723: action types registered as physical (actions.FeatureAction.physical). Whatever their risk
# class, a standing approval never covers them and an automation never requests them. Filled by
# ActionService.register_type; a type once physical stays physical for the life of the process.
PHYSICAL: set[str] = set()


def mark_physical(action_type: str) -> None:
    PHYSICAL.add(action_type)


def policy_may_cover(action_type: str, params: dict | None = None, stored_risk: object = _UNSET) -> str | None:
    """Why no standing approval may accept this request, or None (§12.3: read and write only).

    stored_risk is the class recorded on a filed request (Action.risk); pass it whenever there is
    one, so a request a feature raised above its type's base class is judged at the raised class.
    """
    if action_type in PHYSICAL:
        return f"{action_type} moves something physical; only a person approves it, never a standing approval"
    if action_type not in TYPES:
        return f"unknown action type {action_type!r}"
    if action_type in NEVER_BY_POLICY:
        return f"{action_type} always waits for the owner; a standing approval never covers it"
    risk = effective_risk(action_type, params, stored_risk)
    if risk is None:
        return f"{action_type} has no valid risk class; a standing approval never covers it"
    if not at_most(risk, POLICY_MAX_RISK):
        return f"{action_type} is {risk}; a standing approval covers only read and write types (§12.3)"
    return None


def automatable(action_type: str, params: dict | None = None) -> str | None:
    """Why an automation may not request this, or None (§12.1: Au types, never destructive)."""
    if action_type in PHYSICAL:
        return f"{action_type} moves something physical; an automation never requests it"
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
