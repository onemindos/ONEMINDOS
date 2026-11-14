# SPDX-License-Identifier: Apache-2.0
"""F-7 owner override: approve an app.install whose security scan failed (docs/leap/DECISIONS-NEEDED.md F-7).

F-7's proposed default is "no in v0", so this is **off** unless the box is started with
`ONEMIND_ALLOW_OWNER_OVERRIDE=1`. When it is on, an owner may add
`"override": {"reason": "...", "confirm": "<app id>"}` to `POST /v1/actions/{id}/approve`, and
the gateway accepts the install only when every rule below holds:

1. the approver is a person with role owner (the action service checks this first);
2. the install was requested by a person, never by an agent: an AI cannot talk the owner into
   overriding a scan it asked for (the owner can request the same install themselves);
3. the scan record exists and reports no malware: an override covers known vulnerabilities and
   stale scans, never ClamAV hits and never an app nobody scanned;
4. the owner typed the app id as confirmation, and gave a reason (10 to 500 characters);
5. once the owner has passkeys (identity feature, F-2), the approval carries a passkey
   assertion, which the identity approval guard verifies before this check runs.

The approval then writes a critical `app.owner_override` event (audit line plus NATS) whose
`mark` is `owner override: <reason>`, `owner_override: true` on the `action.approved` line, and
the same mark in the action's result, so the dashboard can show it in red wherever the install
appears. Refusals are audited like every other refused approval.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .audit import AuditLog
from .auth import Principal
from .catalog import AppEntry
from .errors import ApiError
from .events import EventHub
from .ledger import Action
from .scan import scan_problem
from .sections import FALSE, TRUE, config_section

ENV = "ONEMIND_ALLOW_OWNER_OVERRIDE"
REASON_MIN, REASON_MAX = 10, 500


@config_section("override")
@dataclass(frozen=True)
class OwnerOverrideSettings:
    enabled: bool = False  # ONEMIND_ALLOW_OWNER_OVERRIDE=1 (F-7: off in v0)

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "OwnerOverrideSettings":
        raw = (env.get(ENV) or "").strip().lower()
        if raw in ("",) + FALSE:
            return cls(enabled=False)
        if raw in TRUE:
            return cls(enabled=True)
        raise ValueError(f"{ENV} must be 1 or 0, got {raw!r}")


class StepUp(Protocol):
    """What the override needs from the identity feature (F-2 passkeys)."""

    def passkeys_active(self) -> bool: ...


class OwnerOverride:
    def __init__(self, enabled: bool, audit: AuditLog, events: EventHub, step_up: StepUp | None = None):
        self.enabled = enabled
        self.audit = audit
        self.events = events
        # Set by the identity feature when it is registered; None means no passkeys can exist.
        self.step_up = step_up

    def _needs_passkey(self) -> bool:
        return self.step_up is not None and self.step_up.passkeys_active()

    def describe(self, app: AppEntry, now: datetime) -> dict:
        """What the approval card needs to offer (or explain) the override for this app."""
        problem = scan_problem(app.id, app.scan, now)
        refusal = self._app_refusal(app) if problem else None
        return {
            "app_id": app.id,
            "enabled": self.enabled,
            "scan_problem": problem,
            "eligible": bool(self.enabled and problem and refusal is None),
            "refusal": refusal,
            "confirm": app.id,
            "reason_length": [REASON_MIN, REASON_MAX],
            "step_up": "passkey" if self._needs_passkey() else "none",
            "requester_must_be": "person",
        }

    def _app_refusal(self, app: AppEntry) -> str | None:
        record = app.scan
        if record is None:
            return f"app {app.id!r} has no scan record; there is no finding to override"
        if record.malware is None:
            return f"the scan record of {app.id!r} does not say whether malware was found; an override never covers that"
        if record.malware > 0:
            return f"the scan of {app.id!r} found malware; an owner override never covers malware"
        return None

    def check(self, principal: Principal, a: Action, app: AppEntry, problem: str, extra) -> dict:
        """Raise ApiError unless the override may be used; return the facts to record."""
        if not self.enabled:
            self.audit.append(
                "authz.denied", principal.as_dict(), a.id,
                {"attempted": "owner override", "reason": "owner_override_disabled", "app_id": app.id},
            )
            raise ApiError(403, "permission_denied",
                           f"owner override is off on this box (F-7: not in v0); {ENV}=1 turns it on")
        if a.requested_by.get("kind") != "person":
            raise ApiError(409, "stale_precondition",
                           f"{a.requested_by.get('id')} requested this install; an owner override needs an install "
                           "the owner requested (request it yourself, then approve it with the override)")
        refusal = self._app_refusal(app)
        if refusal:
            raise ApiError(409, "stale_precondition", refusal)
        body = extra.override if isinstance(extra.override, dict) else {}
        reason = " ".join(str(body.get("reason") or "").split())
        if not REASON_MIN <= len(reason) <= REASON_MAX:
            raise ApiError(422, "conflict", f"override.reason must be {REASON_MIN} to {REASON_MAX} characters")
        if body.get("confirm") != app.id:
            raise ApiError(422, "conflict", f"override.confirm must be the app id typed exactly: {app.id}")
        if self._needs_passkey() and not extra.webauthn:
            raise ApiError(401, "unauthenticated", "an owner override needs your passkey (step_up_required)")
        scan = app.scan
        return {
            "app_id": app.id,
            "mark": f"owner override: {reason}",
            "reason": reason,
            "problem": problem,
            "scan": {**scan.summary(), "malware": scan.malware} if scan else None,
            "confirmed": app.id,
            "step_up": "passkey" if self._needs_passkey() else "none (no passkeys registered)",
            "requested_by": a.requested_by.get("id"),
        }

    def record(self, principal: Principal, a: Action, facts: dict) -> None:
        """The red mark: a critical event (audit line + NATS + in-process subscribers)."""
        self.events.publish_event(
            "app", "owner_override", {**facts, "tone": "red"},
            principal=principal.as_dict(), action_id=a.id, severity="critical",
            resource={"kind": "app", "id": facts["app_id"]}, dedupe_key=f"owner-override:{a.id}",
        )
