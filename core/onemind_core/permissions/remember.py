# SPDX-License-Identifier: Apache-2.0
"""Approve and remember (gateway permissions design §3.6.1, fix 4; F-10, D-028).

The owner approves one request and, in the same passkey ceremony, makes a standing approval for
requests like it. The danger is a rule the owner did not mean: a cross-site script on the dashboard or
a malicious app screen could swap a wider rule under the owner's real passkey. So:

1. The gateway builds the narrowest rule that covers *this* request: the same principal and type,
   every parameter pinned to this request's value, 30 days, at most 10 a day, "end if unused for
   14 days" on, notices in the daily digest. The person may widen it one field at a time (lifetime,
   per day, unpin a parameter); each choice is part of the body.
2. `approve-options` canonicalises that body and binds its hash, `rule_sha256`, into the passkey
   challenge: sha256(action_id || action_sha256 || plan_sha256 || rule_sha256 || nonce).
3. The plain-language summary is written by the gateway from the bound body, never from client text.
4. On approve the gateway stores the rule only if the canonical hash of the body sent equals the one
   in the consumed challenge. A changed body is refused (`rule_changed`), and so is any approval
   that would remember without a passkey assertion.
5. The phone's approver key is refused for remember (step_up_required) until the phone app shows the
   rule summary before signing (design PR 18a); the phone then falls back to its passkey.
6. Refused for: tainted or exposed requests, physical actions, anything above write (T2 to T4), every
   hard-floor item, a type no rule may cover, the owner's own requests, and before the owner has a
   passkey (F-8). The design allows remember for an exposed agent's read-only (T0) requests; the floor
   keeps every tainted automatic approval closed (permissions/floor.py), so remember stays refused too.

Verification level: D-028 lets an L1 key create a dated T0 rule and asks L2 for T1 and up and for
any forever rule. Levels arrive with design PR 11. Until then the passkey step-up the gateway has
today counts as L1, so a rule whose `required_level` is L2 is refused (409 needs_proven_key) both at
approve-options and again just before the approval; only a dated read-only rule can be remembered.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Literal

from pydantic import ConfigDict, Field

from ..automation import registry
from ..jsonbody import JsonBody
from .floor import floor_items

LIFETIMES = {"30d": 30, "90d": 90, "180d": 180, "forever": None}
DEFAULT_PER_DAY = 10


class RememberChoice(JsonBody):
    """What the person chose on the "Approve and remember" sheet. Everything else is the narrowest rule."""

    model_config = ConfigDict(extra="forbid")
    lifetime: Literal["30d", "90d", "180d", "forever"] = "30d"
    lapse_unused: bool = Field(default=True, description='"end if unused for 14 days" (on by default)')
    per_day: int = Field(default=DEFAULT_PER_DAY, ge=1, le=1000)
    unpin: list[str] = Field(default_factory=list, max_length=20,
                             description="parameter names to leave open; every other parameter stays this request's value")
    notify_after: Literal["each", "digest", "silent"] = "digest"


def canonical(rule: dict) -> bytes:
    return json.dumps(rule, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def rule_sha256(rule: dict) -> str:
    return "sha256:" + hashlib.sha256(canonical(rule)).hexdigest()


def requester_key(requested_by: dict) -> str:
    kind, pid = str(requested_by.get("kind", "")), str(requested_by.get("id", ""))
    return pid if pid.startswith(kind + ":") else f"{kind}:{pid}"


def why_not(action: dict, physical: bool) -> str | None:
    """Why this request cannot be remembered, or None."""
    t, who = str(action.get("type")), action.get("requested_by") or {}
    if (action.get("plan") or {}).get("taint"):
        return "the requester read outside text (tainted or exposed): only a person approves each request"
    if physical:
        return "it moves something physical: a person approves each one (#723)"
    if who.get("kind") == "person":
        return "a person's own requests are not remembered"
    risk = registry.effective_risk(t, action.get("params") or {}, action.get("risk")) if registry.known(t) else None
    if risk not in ("read", "write"):
        return f"its risk is {risk or 'unknown'}: a rule covers only read and write requests"
    items = floor_items(action_type=t, kind=str(who.get("kind") or ""), risk=risk,
                        network_paths=bool((action.get("plan") or {}).get("network_paths")),
                        sealed=t == "app.configure" and bool((action.get("params") or {}).get("sealed")))
    if items:
        return f"it is a hard-floor item ({items[0]}): a person approves it at the time"
    problem = registry.policy_may_cover(t, action.get("params") or {}, action.get("risk"))
    return problem


def narrowest_rule(action: dict, choice: RememberChoice, now: datetime) -> dict:
    """The PolicyBody JSON of the narrowest rule covering this request, with the person's choices."""
    params = action.get("params") or {}
    unknown = sorted(set(choice.unpin) - set(params))
    if unknown:
        raise ValueError(f"unpin names parameters this request does not have: {', '.join(unknown)}")
    pinned = {}
    for k, v in sorted(params.items()):
        if k in choice.unpin:
            continue
        if not isinstance(v, (str, int, float, bool)) or v is None:
            raise ValueError(f"parameter {k!r} is not a plain value, so it cannot be pinned; unpin it or approve once")
        pinned[k] = {"const": v}
    days = LIFETIMES[choice.lifetime]
    return {
        "name": f"Remembered from {action.get('id')}",
        "allow": {"types": [action["type"]], "requested_by": [requester_key(action.get("requested_by") or {})],
                  "params": pinned},
        "limits": {"per_day": choice.per_day},
        "expires_at": None if days is None else (now + timedelta(days=days)).isoformat().replace("+00:00", "Z"),
        "forever": days is None,
        "notify_after": choice.notify_after,
        "lapse_unused_days": 14 if choice.lapse_unused else None,
    }


def required_level(rule: dict) -> str:
    """D-028: a dated read-only rule needs L1; T1 and up, or any forever rule, need L2."""
    risks = {registry.risk_of(t) for t in rule["allow"]["types"] if registry.known(t)}
    return "L1" if risks <= {"read"} and not rule.get("forever") else "L2"


def summary(rule: dict) -> str:
    """The plain-language line the person approves, written from the bound body (never client text)."""
    who = ", ".join(rule["allow"]["requested_by"])
    what = ", ".join(rule["allow"]["types"])
    pins = rule["allow"]["params"]
    on = (" for " + ", ".join(f"{k} = {c['const']}" for k, c in pins.items())) if pins else " with any parameters"
    life = "with no end date" if rule.get("forever") else f"until {rule['expires_at']}"
    lapse = f"; it ends if unused for {rule['lapse_unused_days']} days" if rule.get("lapse_unused_days") else ""
    return f"{who} may {what}{on}, up to {rule['limits']['per_day']} a day, {life}{lapse}. Notices: {rule['notify_after']}."
