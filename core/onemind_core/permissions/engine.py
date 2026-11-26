# SPDX-License-Identifier: Apache-2.0
"""The permission engine: facts for one request, and `decide()` applied on every filing path.

ActionService calls it twice for each request it files (`_create`, `file()`, `_file_feature`; never
`request_configure`, whose secrets only a person types):

- `gate()` before the request is stored. A refusal (steps 1 to 5, Headless at 6 and 11) raises 403
  with the reason, audited as `authz.denied`, and nothing is filed.
- `filed()` once it is stored. Only an "approve" lets the owner's rules run; the policy module then
  reserves one use of the rule (and a rule that ran out in between leaves the request waiting).

Every decision that lets a rule run is written to the audit log as `permission.decided` on the
action, with the step and the reason, so the record says why no person was asked.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ..audit import AuditLog
from ..errors import ApiError
from ..ledger import Action
from ..principals import display_key
from ..taint import plan_taint
from .clock import ClockGuard
from .decide import Decision, Facts, decide
from .denies import DenyStore

log = logging.getLogger("onemind.permissions")

ANY_RULE = "policy:*"  # the rule fact of filed(): whichever live rule the policy module finds


class PermissionEngine:
    def __init__(self, denies: DenyStore, clock_guard: ClockGuard, audit: AuditLog):
        self.denies, self.clock_guard, self.audit = denies, clock_guard, audit
        # Each lookup fails closed when it raises (see _safe). Set by routers/permissions.py.
        self.agents_stopped: Callable[[], bool] = lambda: False
        self.motion_lockout: Callable[[], bool] = lambda: False
        self.automation_paused: Callable[[], bool] = lambda: False
        self.floor_settings_on: Callable[[], bool] = lambda: True
        # PR 10 sets these from the mode table and the owner-passkey check (F-8). Without them every
        # principal keeps the PR 8 behaviour: the owner's rules apply ("auto").
        self.mode_of: Callable[[str, str], str] = lambda _name, _kind: "auto"
        self.owner_passkey: Callable[[], bool] = lambda: True
        # §3.5.1: the owner's own requests run directly and are exempt from modes (PR 10 wires it).
        self.is_owner: Callable[[dict], bool] = lambda _requested_by: False
        # (action_type, params, requested_by) -> "policy:<id>@<rev>" of a live rule that would cover it.
        self.rule_for: Callable[[str, dict, dict], str | None] = lambda _t, _p, _r: None
        self.licence_green: Callable[[str, dict], bool] = lambda _t, _p: True
        self.taint: Any = None  # the ActionService's TaintLedger
        self.modes: Any = None  # permissions.modes.ModeStore (PR 10)

    @staticmethod
    def _safe(fn: Callable[[], bool], closed: bool) -> bool:
        try:
            return bool(fn())
        except Exception:
            log.exception("permission fact lookup failed")
            return closed

    def facts(self, requested_by: dict, action_type: str, params: dict, risk: str | None, *,
              physical: bool = False, plan: dict | None = None, scope_ok: bool = True, lookahead: bool = True) -> Facts:
        name, kind = display_key(requested_by), str(requested_by.get("kind") or "")
        t = self.taint.get(str(requested_by.get("id") or ""), kind) if self.taint is not None else None
        note = plan_taint(plan)
        try:
            deny = self.denies.match(name, action_type, risk, physical)
        except Exception:
            log.exception("deny rule lookup failed")
            deny = "lookup_failed"
        mode = self._mode(name, kind, requested_by)
        # Only Headless needs to know before filing whether a rule covers it (it refuses instead of
        # waiting); otherwise the policy module finds the rule after filing and reserves a use.
        rule = ANY_RULE
        if lookahead and mode == "headless":
            try:
                rule = self.rule_for(action_type, params, requested_by)
            except Exception:
                log.exception("rule lookup failed")
                rule = None
        try:
            clock_ok = self.clock_guard.check() is None
        except Exception:
            log.exception("clock check failed")
            clock_ok = False
        return Facts(
            principal=name, kind=kind, action_type=action_type, risk=risk,
            mode=mode, physical=physical,
            tainted=t is not None or note is not None, exposed=t is not None and t.permanent,
            network_paths=bool((plan or {}).get("network_paths")),
            sealed=action_type == "app.configure" and bool(params.get("sealed")),
            licence_green=self._safe(lambda: self.licence_green(action_type, params), False),
            agents_stopped=self._safe(self.agents_stopped, True),
            motion_lockout=self._safe(self.motion_lockout, True) if physical else False,
            automation_paused=self._safe(self.automation_paused, True) if kind == "automation" else False,
            deny=deny, scope_ok=scope_ok, clock_trusted=clock_ok,
            floor_settings_on=self._safe(self.floor_settings_on, False),
            owner_passkey=self._safe(self.owner_passkey, False), rule=rule,
        )

    def _mode(self, name: str, kind: str, requested_by: dict | None = None) -> str:
        # The owner's own requests: no mode applies (a Locked or Headless household default included),
        # so they behave as before modes existed. Their floor items still wait for a person.
        if kind == "person" and requested_by is not None and self._safe(lambda: self.is_owner(requested_by), False):
            return "auto"
        try:
            return self.mode_of(name, kind)
        except Exception:
            log.exception("mode lookup failed")
            return "ask"

    def gate(self, requested_by: dict, action_type: str, params: dict, risk: str | None, *,
             physical: bool = False, plan: dict | None = None, scope_ok: bool = True) -> Decision:
        """Before a request is stored: raises 403 on a refusal; otherwise returns the decision."""
        d = decide(self.facts(requested_by, action_type, params, risk, physical=physical, plan=plan, scope_ok=scope_ok))
        if d.outcome == "refuse":
            self.audit.append("authz.denied", {"id": requested_by.get("id"), "kind": requested_by.get("kind")}, None,
                              {"attempted": f"request {action_type}", "reason": d.reason, "step": d.step,
                               **({"deny_id": d.via} if d.step == 3 else {}), **({"floor": list(d.floor)} if d.floor else {})})
            raise ApiError(403, "permission_denied", MESSAGES.get(d.reason.split(":")[0], d.reason), reason=d.reason)
        return d

    def filed(self, a: Action) -> Decision:
        """Once stored: may the owner's rules decide it? "approve" here means "if a live rule covers it";
        the policy module then finds that rule and reserves one use (or the request waits)."""
        from ..automation.registry import effective_risk

        risk = effective_risk(a.type, a.params, a.risk) if a.risk is not None else effective_risk(a.type, a.params)
        return decide(self.facts(a.requested_by, a.type, a.params, risk, physical=_physical(a), plan=a.plan,
                                 lookahead=False))


def _physical(a: Action) -> bool:
    from ..automation.registry import PHYSICAL

    return a.type in PHYSICAL


MESSAGES = {
    "agents_stopped": "the owner stopped every AI agent",
    "motion_lockout": "the motion lockout is on: no physical action is requested or approved",
    "automation_paused": "automation is paused",
    "mode_locked": "this principal is locked: the owner refuses all its requests",
    "denied_by_rule": "a deny rule refuses this principal this request",
    "scope": "this token may not request this action type",
    "unknown_risk": "this request has no known risk class, so it is refused",
    "floor": "this request needs a person at the time, and this principal's mode refuses anything that would wait",
    "no_rule": "no rule covers this request, and this principal's mode refuses anything that would wait",
}
