# SPDX-License-Identifier: Apache-2.0
"""Automation rules: schedules and event rules that REQUEST actions (contract §12.17, CORE-AUTO-2/4).

A rule never acts by itself. When its trigger fires it files ordinary requests through the
action service as the principal `automation:<rule-id>` (kind `automation`, §12.1), exactly as an
agent would. A request then waits for the owner unless a standing approval covers it (policies.py).

- **Schedule** `{"schedule": {"cron": "0 3 * * *", "tz": "Europe/London"}}`: fires at local
  wall-clock times. `options.catch_up` `none` (default) skips fires missed while the gateway was
  down; `last` fires the latest missed one once. Never all of them.
- **Event** `{"event": {"type": "app.unhealthy", "where": {"resource.id": "uptime-kuma"}}}`:
  matches events from the plumbing hook (`gw.events.publish_event`, also on NATS
  `onemind.event.>`). Debounce per resource (default 300 s) and a loop guard: an event that
  belongs to an action this rule requested does not fire it again.
- **Templates** substitute whole parameter values only (`"${event.resource.id}"`), and each
  substituted value must look like an id; the rendered request is validated before it is filed.
  An invalid render is a `template_error` fire, never a best-effort request.
- **Safety:** a rule naming a `destructive` type, or one automations may not request, is refused
  with 422 (F-11). Concurrency 1: a rule whose last request is not final does not fire again.
  Breaker: three failed or unknown outcomes in a row disable the rule and raise an event.
- **Dry run** shows what a rule would request and each request's verdict; enabling needs a dry
  run of the current revision less than 24 hours old.
- **Kill switch** `POST /v1/automation/pause` stops every rule and every standing approval at
  once; requests already filed stay in the ledger and wait for a person.
"""

from __future__ import annotations

import logging
import queue
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from ..actions import ActionRequest
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError
from ..events import PATTERN_TOKEN_RE, matches
from ..ledger import TERMINAL, iso, utc
from ..sections import config_section
from . import registry
from .cron import Cron, resolve_tz
from .policies import PolicyService
from .store import AutomationRepository, Rule, new_id

log = logging.getLogger("onemind.automation")

DRY_RUN_TTL = timedelta(hours=24)
MAX_DRY_RUN_SPAN = timedelta(days=31)
MAX_DRY_RUN_ITEMS = 200
BREAKER_AFTER = 3
REF_RE = re.compile(r"^\$\{(trigger\.time|event\.id|event\.type|event\.resource\.(?:id|kind)|event\.data\.[a-z][a-z0-9_]{0,39})\}$")
SAFE_VALUE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
WHERE_KEY_RE = re.compile(r"^(resource\.(id|kind)|severity|source_id|data\.[a-z][a-z0-9_]{0,39})$")


@config_section("automation")
@dataclass(frozen=True)
class AutomationSettings:
    enabled: bool = True  # ONEMIND_AUTOMATION_ENABLED: run the scheduler and event rules here
    tick_s: float = 30.0  # ONEMIND_AUTOMATION_TICK_S: how often schedules are checked
    tz: str = "UTC"  # ONEMIND_AUTOMATION_TZ: the box's time zone ("box"/"local" in a rule)

    def validate(self) -> None:
        if not 1 <= self.tick_s <= 300:
            raise ValueError("ONEMIND_AUTOMATION_TICK_S must be between 1 and 300")
        try:
            resolve_tz(self.tz)
        except ValueError as exc:
            raise ValueError(f"ONEMIND_AUTOMATION_TZ: {exc}") from None


class ActionTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str = Field(min_length=1, max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)


class Options(BaseModel):
    model_config = ConfigDict(extra="forbid")
    catch_up: Literal["none", "last"] = "none"
    debounce_s: int = Field(default=300, ge=0, le=86400)
    window_id: str | None = Field(default=None, max_length=40)
    expires_s: int = Field(default=86400, ge=60, le=7 * 86400)  # §12.1: at most 7 days


class RuleBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    trigger: dict[str, Any]
    conditions: list[Any] = Field(default_factory=list)
    actions: list[ActionTemplate] = Field(min_length=1, max_length=5)
    options: Options = Field(default_factory=Options)
    approval_policy_id: str | None = Field(default=None, max_length=40)


class RulePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    trigger: dict[str, Any] | None = None
    conditions: list[Any] | None = None
    actions: list[ActionTemplate] | None = Field(default=None, min_length=1, max_length=5)
    options: Options | None = None
    approval_policy_id: str | None = Field(default=None, max_length=40)


class DryRunBody(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    from_: AwareDatetime | None = Field(default=None, alias="from")
    to: AwareDatetime | None = None
    sample_event: dict[str, Any] | None = None


class PauseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=500)


class TemplateError(ValueError):
    pass


def _refs(value: Any) -> list[str]:
    """Every `${...}` reference in a params tree; a partial-string substitution is refused."""
    if isinstance(value, dict):
        return [r for v in value.values() for r in _refs(v)]
    if isinstance(value, list):
        return [r for v in value for r in _refs(v)]
    if isinstance(value, str) and "${" in value:
        m = REF_RE.match(value)
        if not m:
            raise ValueError(f"{value!r}: a substitution must be a whole value like \"${{event.resource.id}}\"")
        return [m.group(1)]
    return []


def _lookup(ref: str, ctx: dict) -> Any:
    cur: Any = ctx
    for part in ref.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise TemplateError(f"${{{ref}}} has no value for this trigger")
        cur = cur[part]
    return cur


def render(value: Any, ctx: dict) -> Any:
    if isinstance(value, dict):
        return {k: render(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v, ctx) for v in value]
    if isinstance(value, str) and "${" in value:
        m = REF_RE.match(value)
        if not m:
            raise TemplateError(f"{value!r} is not a whole-value substitution")
        out = _lookup(m.group(1), ctx)
        if not isinstance(out, str) or not SAFE_VALUE_RE.match(out):
            raise TemplateError(f"${{{m.group(1)}}} rendered {str(out)[:80]!r}, which is not an id")
        return out
    return value


def _event_path(env: dict, key: str) -> Any:
    cur: Any = env
    for part in key.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def automation_principal(rule: Rule) -> Principal:
    return Principal(id=rule.principal_id, kind="automation", role="automation")


class AutomationService:
    def __init__(self, gw: Gateway, settings: AutomationSettings | None = None):
        self.gw = gw
        self.settings = settings or gw.settings.section(AutomationSettings)
        self.clock = gw.clock
        self.audit = gw.audit
        self.repo = AutomationRepository(gw.db)
        self.policies = PolicyService(self.repo, gw.audit, gw.catalog, gw.clock, box_tz=self.settings.tz)
        self._lock = threading.RLock()
        self._queue: queue.Queue[dict] = queue.Queue(maxsize=1000)
        self._recent: deque[dict] = deque(maxlen=2000)  # events seen since start, for dry runs
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.repo.seed_default_window(self.clock())

    # ---- helpers -------------------------------------------------------------------------------
    def _deny(self, principal: Principal, what: str) -> ApiError:
        self.audit.append("authz.denied", principal.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
        return ApiError(403, "permission_denied", f"{principal.kind}/{principal.role} may not {what}")

    def _rule(self, rule_id: str) -> Rule:
        rule = self.repo.get_rule(rule_id)
        if rule is None:
            raise ApiError(404, "not_found", "no such automation rule")
        return rule

    def paused(self) -> bool:
        return bool(self.repo.state()["paused"])

    def tz(self, name: str | None):
        return resolve_tz(name, self.settings.tz)

    def rule_json(self, r: Rule) -> dict:
        return {
            "id": r.id, "name": r.name, "system": False, "revision": r.revision, "enabled": r.enabled,
            "trigger": r.trigger, "conditions": r.conditions, "actions": r.actions, "options": r.options,
            "created_by": r.created_by, "approval_policy_id": r.approval_policy_id,
            "last_fired_at": iso(r.last_fired_at), "breaker": r.breaker, "failures": r.failures,
            "created_at": iso(r.created_at), "updated_at": iso(r.updated_at),
        }

    # ---- validation ----------------------------------------------------------------------------
    def _trigger(self, trigger: dict) -> dict:
        if len(trigger) != 1:
            raise ValueError("trigger needs exactly one of schedule, event, webhook, manual")
        kind, spec = next(iter(trigger.items()))
        if kind in ("webhook", "manual"):
            raise ValueError(f"{kind} triggers are not built yet; use schedule or event")
        if not isinstance(spec, dict):
            raise ValueError(f"trigger.{kind} must be an object")
        if kind == "schedule":
            if set(spec) - {"cron", "tz"}:
                raise ValueError("trigger.schedule takes cron and tz")
            cron = Cron.parse(spec.get("cron"))
            tz = spec.get("tz") or "box"
            self.tz(tz)
            return {"schedule": {"cron": cron.expr, "tz": tz}}
        if kind == "event":
            if set(spec) - {"type", "where", "for_s"}:
                raise ValueError("trigger.event takes type, where and for_s")
            etype = spec.get("type")
            tokens = etype.split(".") if isinstance(etype, str) and len(etype) <= 200 else []
            if (not tokens or not all(PATTERN_TOKEN_RE.match(t) for t in tokens) or ">" in tokens[:-1]
                    or tokens[0] in ("*", ">")):
                raise ValueError("trigger.event.type must be an event type such as app.unhealthy or app.*")
            if tokens[0] == "automation":
                raise ValueError("a rule may not trigger on automation.* events (loop guard)")
            where = spec.get("where") or {}
            if not isinstance(where, dict) or len(where) > 10:
                raise ValueError("trigger.event.where must be an object of at most 10 fields")
            for k, v in where.items():
                if not WHERE_KEY_RE.match(k) or not isinstance(v, (str, int, float, bool)):
                    raise ValueError(f"where {k!r}: keys are resource.id, resource.kind, severity, source_id or data.<field>; values are scalars")
            if spec.get("for_s"):
                raise ValueError("trigger.event.for_s is not built yet; leave it out or 0")
            return {"event": {"type": etype, "where": where}}
        raise ValueError(f"unknown trigger {kind!r}")

    def _validate(self, body: RuleBody) -> dict:
        """The stored form of a rule body; ApiError 422/404 when it is refused."""
        try:
            trigger = self._trigger(body.trigger)
            if body.conditions:
                raise ValueError("conditions are not built yet; leave the list empty")
            actions = []
            for i, tpl in enumerate(body.actions):
                refs = _refs(tpl.params)
                if "schedule" in trigger and any(r.startswith("event.") for r in refs):
                    raise ValueError(f"actions[{i}]: a schedule rule has no event to substitute")
                problem = registry.automatable(tpl.type, tpl.params)
                if problem:
                    raise ValueError(f"actions[{i}]: {problem}")
                if tpl.type not in registry.fileable():
                    raise ValueError(f"actions[{i}]: the action ledger cannot file {tpl.type} yet "
                                     f"(it files {', '.join(sorted(registry.fileable()))})")
                probe = render(tpl.params, _probe_ctx())
                try:
                    ActionRequest.model_validate({"type": tpl.type, "params": probe, "idempotency_key": "probe",
                                                  "expires_at": "2099-01-01T00:00:00Z"})
                except ValidationError as exc:
                    raise ValueError(f"actions[{i}]: params do not fit {tpl.type}: {_short(exc)}") from None
                actions.append({"type": tpl.type, "params": tpl.params})
        except (ValueError, TemplateError) as exc:
            raise ApiError(422, "conflict", str(exc)) from None
        if body.options.window_id and self.repo.get_window(body.options.window_id) is None:
            raise ApiError(404, "not_found", f"no window {body.options.window_id!r}")
        if body.approval_policy_id and self.repo.get_policy(body.approval_policy_id) is None:
            raise ApiError(404, "not_found", f"no standing approval {body.approval_policy_id!r}")
        return {"name": body.name, "trigger": trigger, "conditions": [], "actions": actions,
                "options": body.options.model_dump(), "approval_policy_id": body.approval_policy_id}

    # ---- rule CRUD -----------------------------------------------------------------------------
    def list(self) -> list[dict]:
        return [self.rule_json(r) for r in self.repo.list_rules()]

    def get(self, rule_id: str) -> dict:
        return self.rule_json(self._rule(rule_id))

    def create(self, principal: Principal, body: RuleBody) -> dict:
        if not principal.is_owner:
            # §12.17 lets agents and plugins request automation.rule.create; the ledger cannot file
            # that type until the action registry (CORE-AUTO-1) lands, so they are refused for now.
            raise self._deny(principal, "create automation rules")
        values = self._validate(body)
        now = self.clock()
        rule = self.repo.add_rule(id=new_id("rule_"), revision=1, enabled=False, created_by=principal.as_dict(),
                                  created_at=now, updated_at=now, **values)
        self.audit.append("automation.rule.created", principal.as_dict(), None,
                          {"rule_id": rule.id, "revision": 1, "trigger": rule.trigger, "actions": rule.actions})
        return self.rule_json(rule)

    def update(self, principal: Principal, rule_id: str, patch: RulePatch) -> dict:
        if not principal.is_owner:
            raise self._deny(principal, "change automation rules")
        rule = self._rule(rule_id)
        merged = RuleBody(
            name=patch.name or rule.name,
            trigger=patch.trigger if patch.trigger is not None else rule.trigger,
            conditions=patch.conditions if patch.conditions is not None else rule.conditions,
            actions=patch.actions if patch.actions is not None else [ActionTemplate(**a) for a in rule.actions],
            options=patch.options or Options(**rule.options),
            approval_policy_id=patch.approval_policy_id if "approval_policy_id" in patch.model_fields_set
            else rule.approval_policy_id,
        )
        values = self._validate(merged)
        now = self.clock()
        # A new revision needs its own dry run before it runs, so an edit always disables the rule.
        changed = self.repo.update_rule(rule.id, expect_revision=rule.revision, revision=rule.revision + 1,
                                        enabled=False, updated_at=now, cursor_at=None, **values)
        if not changed:
            raise ApiError(409, "conflict", "the rule changed concurrently")
        self.audit.append("automation.rule.updated", principal.as_dict(), None,
                          {"rule_id": rule.id, "revision": rule.revision + 1, "was_enabled": rule.enabled})
        return self.get(rule.id)

    def enable(self, principal: Principal, rule_id: str) -> dict:
        if not principal.is_owner:
            raise self._deny(principal, "enable automation rules")
        rule = self._rule(rule_id)
        now = self.clock()
        dry = self.repo.latest_dry_run(rule.id, rule.revision)
        if dry is None or now - dry["created_at"] > DRY_RUN_TTL:
            raise ApiError(409, "stale_precondition",
                           f"dry_run_required: run POST /v1/automation/rules/{rule.id}/dry-run for revision "
                           f"{rule.revision} (valid 24 h) before enabling")
        self.repo.update_rule(rule.id, enabled=True, cursor_at=now, failures=0, breaker="closed",
                              pending_action_ids=[], updated_at=now)
        self.audit.append("automation.rule.enabled", principal.as_dict(), None,
                          {"rule_id": rule.id, "revision": rule.revision, "dry_run_id": dry["id"]})
        return self.get(rule.id)

    def disable(self, principal: Principal, rule_id: str) -> dict:
        # Turning a rule off only removes power: the owner, or any agent (§12.17 automation:request).
        if not (principal.is_owner or principal.kind == "agent"):
            raise self._deny(principal, "disable automation rules")
        rule = self._rule(rule_id)
        self.repo.update_rule(rule.id, enabled=False, updated_at=self.clock())
        self.audit.append("automation.rule.disabled", principal.as_dict(), None,
                          {"rule_id": rule.id, "revision": rule.revision, "was_enabled": rule.enabled})
        return self.get(rule.id)

    def delete(self, principal: Principal, rule_id: str) -> None:
        if not principal.is_owner:
            raise self._deny(principal, "delete automation rules")
        rule = self._rule(rule_id)
        self.repo.delete_rule(rule.id)
        self.audit.append("automation.rule.deleted", principal.as_dict(), None,
                          {"rule_id": rule.id, "revision": rule.revision})

    def runs(self, rule_id: str | None, limit: int) -> list[dict]:
        out = []
        for f in self.repo.list_fires(rule_id, limit):
            out.append({"id": f["id"], "rule_id": f["rule_id"], "revision": f["revision"],
                        "fired_at": iso(f["fired_at"]), "trigger_event_id": f["trigger_event_id"],
                        "action_ids": f["action_ids"] or [], "outcome": f["outcome"],
                        **({"detail": f["detail"]} if f["detail"] else {})})
        return out

    def schedules(self) -> list[dict]:
        now = self.clock()
        out = []
        for r in self.repo.list_rules():
            sched = r.trigger.get("schedule")
            if not sched:
                continue
            nxt = Cron.parse(sched["cron"]).next_fire(self.tz(sched["tz"]), now)
            out.append({"rule_id": r.id, "name": r.name, "enabled": r.enabled, "cron": sched["cron"],
                        "tz": sched["tz"], "next_fire_at": iso(nxt) if r.enabled else None,
                        "next_match_at": iso(nxt)})
        return out

    # ---- kill switch ---------------------------------------------------------------------------
    def state(self) -> dict:
        s = self.repo.state()
        return {"paused": bool(s["paused"]), "changed_by": s["changed_by"], "changed_at": iso(s["changed_at"]),
                "reason": s["reason"]}

    def set_paused(self, principal: Principal, paused: bool, reason: str | None) -> dict:
        if not principal.is_owner:  # §12.5: agents never change the kill switch
            raise self._deny(principal, "pause or resume automation")
        self.repo.set_paused(paused, principal.as_dict(), self.clock(), reason)
        self.gw.events.publish_event(
            "automation", "paused" if paused else "resumed", {"reason": reason},
            principal=principal.as_dict(), severity="warning" if paused else "info",
            resource={"kind": "automation", "id": "global"}, dedupe_key="automation:kill_switch",
        )
        if not paused:  # schedules resume from now, not from when they were paused
            now = self.clock()
            for r in self.repo.list_rules(enabled=True):
                self.repo.update_rule(r.id, cursor_at=now)
        return self.state()

    # ---- firing --------------------------------------------------------------------------------
    def _busy(self, rule: Rule) -> bool:
        for aid in rule.pending_action_ids:
            a = self.gw.repo.get(aid)
            if a is not None and self.gw.actions.expire_if_due(a).state not in TERMINAL:
                return True
        return False

    def _loop(self, rule: Rule, env: dict) -> bool:
        aid = env.get("correlation_id")
        a = self.gw.repo.get(aid) if isinstance(aid, str) else None
        return a is not None and a.requested_by.get("id") == rule.principal_id

    def _fire(self, rule: Rule, slot: str, now: datetime, *, trigger_time: datetime,
              event: dict | None = None) -> dict | None:
        rule = self.repo.get_rule(rule.id) or rule
        if not rule.enabled:
            return None
        principal = automation_principal(rule)
        fire_id = new_id("run_")
        resource = (event or {}).get("resource") or {}
        resource_key = (f"{resource.get('kind')}:{resource.get('id')}" if resource.get("id")
                        else (event or {}).get("type")) if event else None
        opts = rule.options
        skip = None
        if event is not None and self._loop(rule, event):
            skip = "skipped_loop"
        elif opts.get("window_id") and not self.policies.window_is_open(opts["window_id"], now):
            skip = "skipped_window"
        elif self._busy(rule):
            skip = "skipped_concurrency"
        elif (event is not None and opts.get("debounce_s") and resource_key
              and self.repo.last_requested_for(rule.id, resource_key, now - timedelta(seconds=opts["debounce_s"]))):
            skip = "skipped_debounce"
        claimed = self.repo.claim_fire(
            id=fire_id, rule_id=rule.id, revision=rule.revision, slot=slot[:120], fired_at=now,
            trigger_event_id=(event or {}).get("id"), resource_key=resource_key, action_ids=[],
            outcome=skip or "requesting", detail=None,
        )
        if not claimed:
            return None  # this slot fired already (a second tick, or a fall-back hour)
        if skip:
            return {"id": fire_id, "outcome": skip, "action_ids": []}
        ctx = {"trigger": {"time": iso(trigger_time)}, "event": event or {}}
        action_ids: list[str] = []
        errors: list[dict] = []
        for i, tpl in enumerate(rule.actions):
            try:
                params = render(tpl["params"], ctx)
                req = ActionRequest.model_validate({
                    "type": tpl["type"], "params": params, "idempotency_key": f"{fire_id}:{i}",
                    "expires_at": iso(now + timedelta(seconds=opts.get("expires_s", 86400))),
                })
            except (TemplateError, ValidationError) as exc:
                errors.append({"index": i, "error": "template_error", "message": _short(exc)})
                continue
            problem = registry.automatable(req.type, params)
            if problem:  # defence in depth: validated at create, checked again on the rendered request
                errors.append({"index": i, "error": "permission_denied", "message": problem})
                continue
            try:
                action, _ = self.gw.actions.create(principal, req, reason=f"automation rule {rule.name!r}")
                action_ids.append(action["id"])
            except ApiError as exc:
                errors.append({"index": i, "error": exc.error, "message": exc.message})
        if not errors:
            outcome = "requested"
        elif action_ids:
            outcome = "partial"
        else:
            outcome = errors[0]["error"] if errors[0]["error"] == "template_error" else "refused"
        self.repo.finish_fire(fire_id, outcome, action_ids, {"errors": errors} if errors else None)
        self.repo.update_rule(rule.id, last_fired_at=now, pending_action_ids=rule.pending_action_ids + action_ids)
        self.gw.events.publish_event(
            "automation", "fired",
            {"rule_id": rule.id, "revision": rule.revision, "run_id": fire_id, "action_ids": action_ids,
             "outcome": outcome, "trigger_event_id": (event or {}).get("id"),
             **({"errors": errors} if errors else {})},
            principal=principal.as_dict(), severity="warning" if errors else "info",
            resource={"kind": "automation_rule", "id": rule.id},
            causation_id=(event or {}).get("id"),
        )
        return {"id": fire_id, "outcome": outcome, "action_ids": action_ids}

    def _check_outcomes(self, now: datetime) -> None:
        """Breaker: count final outcomes of each rule's requests; trip after 3 failures in a row."""
        for rule in self.repo.list_rules():
            if not rule.pending_action_ids:
                continue
            pending, failures = [], rule.failures
            for aid in rule.pending_action_ids:
                a = self.gw.repo.get(aid)
                if a is None:
                    continue
                state = self.gw.actions.expire_if_due(a).state
                if state not in TERMINAL:
                    pending.append(aid)
                elif state == "succeeded":
                    failures = 0
                elif state in ("failed", "outcome_unknown"):
                    failures += 1
            trip = failures >= BREAKER_AFTER and rule.breaker == "closed"
            values: dict = {"pending_action_ids": pending, "failures": failures}
            if trip:
                values |= {"breaker": "open", "enabled": False, "updated_at": now}
            self.repo.update_rule(rule.id, **values)
            if trip:
                self.gw.events.publish_event(
                    "automation", "breaker.opened",
                    {"rule_id": rule.id, "name": rule.name, "failures": failures,
                     "message": f"automation {rule.name!r} paused after {failures} failed requests"},
                    severity="error", resource={"kind": "automation_rule", "id": rule.id},
                    dedupe_key=f"automation:{rule.id}:breaker",
                )

    def tick(self, now: datetime | None = None) -> list[dict]:
        """Fire every schedule that is due, then handle queued events. Safe to call twice."""
        fired: list[dict] = []
        with self._lock:
            now = now or self.clock()
            self._check_outcomes(now)
            paused = self.paused()
            grace = timedelta(seconds=max(120.0, 2 * self.settings.tick_s))
            for rule in self.repo.list_rules(enabled=True):
                sched = rule.trigger.get("schedule")
                if not sched:
                    continue
                cursor = max(rule.cursor_at or now, now - timedelta(days=8))
                self.repo.update_rule(rule.id, cursor_at=now)
                if paused or cursor >= now:
                    continue
                due = list(Cron.parse(sched["cron"]).fire_times(self.tz(sched["tz"]), cursor, now))
                on_time = [d for d in due if now - d[0] <= grace]
                if not on_time and due and rule.options.get("catch_up") == "last":
                    on_time = [due[-1]]
                for when, slot in on_time:
                    res = self._fire(rule, f"cron:{slot}", now, trigger_time=when)
                    if res:
                        fired.append(res)
            fired += self.process_events()
        return fired

    # ---- events --------------------------------------------------------------------------------
    def on_event(self, env: dict) -> None:
        """In-process subscriber (publisher's thread): queue only; the worker files requests."""
        if str(env.get("type", "")).startswith("automation."):
            return
        self._recent.append(env)
        try:
            self._queue.put_nowait(env)
        except queue.Full:
            log.warning("automation event queue full; dropped %s", env.get("type"))
        self._wake.set()

    def process_events(self) -> list[dict]:
        fired: list[dict] = []
        with self._lock:
            while True:
                try:
                    env = self._queue.get_nowait()
                except queue.Empty:
                    return fired
                if self.paused():
                    continue
                now = self.clock()
                for rule in self.repo.list_rules(enabled=True):
                    spec = rule.trigger.get("event")
                    if spec and _event_matches(spec, env):
                        res = self._fire(rule, f"event:{env.get('id')}", now, trigger_time=now, event=env)
                        if res:
                            fired.append(res)

    # ---- dry run -------------------------------------------------------------------------------
    def dry_run(self, principal: Principal, rule_id: str, body: DryRunBody) -> dict:
        rule = self._rule(rule_id)
        now = self.clock()
        is_event = "event" in rule.trigger
        frm = utc(body.from_) if body.from_ else (now - timedelta(days=7) if is_event else now)
        to = utc(body.to) if body.to else (now if is_event else frm + timedelta(days=7))
        if to <= frm or to - frm > MAX_DRY_RUN_SPAN:
            raise ApiError(422, "conflict", "the dry-run range must be positive and at most 31 days")
        paused = self.paused()
        sim_uses: dict[str, list[datetime]] = {}
        would, skipped, truncated = [], [], False

        def simulate(at: datetime, event: dict | None) -> None:
            ctx = {"trigger": {"time": iso(at)}, "event": event or {}}
            for i, tpl in enumerate(rule.actions):
                item: dict = {"at": iso(at), "trigger_event_id": (event or {}).get("id"), "index": i,
                              "type": tpl["type"]}
                try:
                    params = render(tpl["params"], ctx)
                    ActionRequest.model_validate({"type": tpl["type"], "params": params,
                                                  "idempotency_key": "dry-run", "expires_at": iso(at + timedelta(days=1))})
                except (TemplateError, ValidationError) as exc:
                    would.append({**item, "params": tpl["params"], "verdict": "template_error", "reason": _short(exc)})
                    continue
                item["params"] = params
                item["risk"] = registry.risk_of(tpl["type"], params)
                problem = registry.automatable(tpl["type"], params)
                if problem:
                    would.append({**item, "verdict": "denied", "reason": problem})
                    continue
                v = self.policies.evaluate(tpl["type"], params, {"id": rule.principal_id, "kind": "automation"},
                                           at, paused=paused, extra_uses=sim_uses)
                if v.outcome == "auto_approved":
                    sim_uses.setdefault(v.policy["id"], []).append(at)  # type: ignore[index]
                would.append({**item, **v.to_json()})

        window_id = rule.options.get("window_id")
        if not is_event:
            sched = rule.trigger["schedule"]
            for at, _slot in Cron.parse(sched["cron"]).fire_times(self.tz(sched["tz"]), frm, to):
                if len(would) + len(skipped) >= MAX_DRY_RUN_ITEMS:
                    truncated = True
                    break
                if window_id and not self.policies.window_is_open(window_id, at):
                    skipped.append({"at": iso(at), "reason": "skipped_window"})
                    continue
                simulate(at, None)
        else:
            spec = rule.trigger["event"]
            events = [body.sample_event] if body.sample_event is not None else [
                e for e in list(self._recent) if frm <= _event_time(e, now) <= to]
            last_by_key: dict[str, datetime] = {}
            for env in events:
                if len(would) + len(skipped) >= MAX_DRY_RUN_ITEMS:
                    truncated = True
                    break
                if not isinstance(env, dict) or not _event_matches(spec, env):
                    continue
                at = _event_time(env, now)
                res = env.get("resource") or {}
                key = f"{res.get('kind')}:{res.get('id')}" if isinstance(res, dict) and res.get("id") else str(env.get("type"))
                debounce = timedelta(seconds=rule.options.get("debounce_s", 300))
                if self._loop(rule, env):
                    skipped.append({"at": iso(at), "trigger_event_id": env.get("id"), "reason": "skipped_loop"})
                elif window_id and not self.policies.window_is_open(window_id, at):
                    skipped.append({"at": iso(at), "trigger_event_id": env.get("id"), "reason": "skipped_window"})
                elif key in last_by_key and at - last_by_key[key] < debounce:
                    skipped.append({"at": iso(at), "trigger_event_id": env.get("id"), "reason": "skipped_debounce"})
                else:
                    last_by_key[key] = at
                    simulate(at, env)
        verdicts = {w["verdict"] for w in would}
        outcome = "auto_approved" if would and verdicts == {"auto_approved"} else "needs_approval"
        dry_id = new_id("dry_")
        result = {
            "id": dry_id, "rule_id": rule.id, "revision": rule.revision, "created_at": iso(now),
            "from": iso(frm), "to": iso(to), "would_request": would, "skipped": skipped,
            "policy_outcome": outcome, "truncated": truncated,
            "source": ("sample_event" if body.sample_event is not None else "events_seen_since_start")
            if is_event else "schedule",
        }
        self.repo.add_dry_run(id=dry_id, rule_id=rule.id, revision=rule.revision, created_at=now, result=result)
        self.audit.append("automation.dry_run", principal.as_dict(), None,
                          {"rule_id": rule.id, "revision": rule.revision, "dry_run_id": dry_id,
                           "would_request": len(would), "policy_outcome": outcome})
        return result

    # ---- background worker ---------------------------------------------------------------------
    def start(self) -> None:
        if not self.settings.enabled or self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="onemind-automation", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        next_tick = time.monotonic() + self.settings.tick_s
        while not self._stop.is_set():
            self._wake.wait(timeout=max(0.0, next_tick - time.monotonic()))
            self._wake.clear()
            if self._stop.is_set():
                return
            try:
                if time.monotonic() >= next_tick:
                    next_tick = time.monotonic() + self.settings.tick_s
                    self.tick()
                else:
                    self.process_events()
            except Exception:  # one bad tick must not stop the scheduler
                log.exception("automation tick failed")


def _probe_ctx() -> dict:
    """Stand-in values used to check a template's shape at creation."""
    return {"trigger": {"time": "2099-01-01T00:00:00Z"},
            "event": {"id": "evt_probe", "type": "probe", "resource": {"id": "probe", "kind": "probe"},
                      "data": _AnyData()}}


class _AnyData(dict):
    def __contains__(self, key: object) -> bool:
        return True

    def __getitem__(self, key: str) -> str:
        return "probe"


def _event_matches(spec: dict, env: dict) -> bool:
    if not isinstance(env.get("type"), str) or not matches(spec["type"], env["type"]):
        return False
    return all(_event_path(env, k) == v for k, v in (spec.get("where") or {}).items())


def _event_time(env: dict, default: datetime) -> datetime:
    try:
        return utc(datetime.fromisoformat(str(env.get("occurred_at")).replace("Z", "+00:00")))
    except ValueError:
        return default


def _short(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        e = exc.errors()[0]
        return f"{'.'.join(str(x) for x in e.get('loc', ()))}: {e.get('msg')}"[:300]
    return str(exc)[:300]
