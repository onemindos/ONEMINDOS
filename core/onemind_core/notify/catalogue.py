# SPDX-License-Identifier: Apache-2.0
"""The v1 event catalogue: which events become notifications and alerts (contract §12.14).

An incoming event (an `onemind.event.v1` envelope from `publish_event`, a node outbox event from
NATS, or an action-ledger audit line mapped by `from_audit`) is looked up here by its type:

- `open`:    opens or updates the alert `dedupe` (one per key while open) and notifies its audience;
- `resolve`: resolves the alerts named in `resolves` (and tells the audience it cleared, if the
             alert had `notify_resolve`);
- `notify`:  a one-off inbox item (and may also resolve alerts);
- `inbox`:   a one-off inbox item that is never pushed to a channel (in-app only).

Types not listed are ignored. Severity is the contract's three levels: info, warning, critical
(docs/architecture/NOTIFICATIONS.md §3 "error" maps to warning; DECISIONS-NEEDED §5 N-3).
Topics are the fixed tree of contract §12.14.
"""

from __future__ import annotations

import string
from collections.abc import Callable
from dataclasses import dataclass, field

SEVERITIES = ("info", "warning", "critical")
RANK = {s: i for i, s in enumerate(SEVERITIES)}
TOPICS = ("approvals", "backups", "updates", "nodes", "apps", "storage", "security", "automation")

# Audiences: who receives it (resolved to people by role; contract §12.14 / N-R9).
OWNERS = "owners"
OWNERS_AND_REQUESTER = "owners+requester"
OWNERS_AND_ADULTS = "owners+adults"
PERSON = "person"  # only the person named by data.person_id (their own download, #693); never pushed for them by role


@dataclass(frozen=True)
class Spec:
    type: str
    kind: str                     # open | resolve | notify | inbox
    topic: str
    severity: str = "info"
    title: str = ""
    body: str = ""
    dedupe: str | None = None     # alert key template (kind open)
    resolves: tuple[str, ...] = ()
    audience: str = OWNERS
    link: str | None = None
    fix: Callable[[dict], dict | None] | None = None
    notify_resolve: bool = False  # tell the audience when the alert clears
    auto_resolve: bool = True     # False: only an owner can resolve it (§12.14)
    learn_more: str | None = None
    aliases: tuple[str, ...] = field(default=())


class _Missing(dict):
    def __missing__(self, key: str) -> str:
        return "?"


_FMT = string.Formatter()


def render(template: str, data: dict) -> str:
    """str.format with missing keys shown as "?", only plain field names (no attribute access)."""
    safe = {k: v for k, v in data.items() if isinstance(v, (str, int, float, bool)) or v is None}
    out = []
    for literal, name, _spec, _conv in _FMT.parse(template):
        out.append(literal)
        if name is not None:
            out.append(str(_Missing(safe)[name]) if name.isidentifier() else "?")
    return "".join(out)


def _fix(type_: str, *keys: str) -> Callable[[dict], dict | None]:
    def make(data: dict) -> dict | None:
        params = {k: data[k] for k in keys if data.get(k) is not None}
        return {"type": type_, "params": params} if len(params) == len(keys) else None
    return make


def _topic_for_action(action_type: str | None) -> str:
    prefix = (action_type or "").split(".", 1)[0]
    return {"app": "apps", "backup": "backups", "node": "nodes", "os": "updates",
            "automation": "automation", "tls": "security", "agent": "security"}.get(prefix, "apps")


_DOCS = "https://github.com/onemindos/ONEMINDOS/blob/main/docs"
_NODE_HELP = "https://github.com/onemindos/ONEMINDOS/blob/main/site/src/content/docs/docs/guides/troubleshooting.md"
_STORAGE_HELP = f"{_DOCS}/leap/core/STORAGE-ACTIONS.md"


_SPECS = [
    # ---- approvals and actions (from the action ledger) ----------------------------------
    Spec("approval.requested", "open", "approvals", "info",
         "Approval needed: {action_type} {app_id}", "Requested by {requested_by}. Expires {expires_at}.",
         dedupe="approval:{action_id}", link="/approvals/{action_id}",
         learn_more=f"{_DOCS}/learning/09-gateway-approvals-agents-mcp.md"),
    Spec("approval.closed", "resolve", "approvals", resolves=("approval:{action_id}",)),
    Spec("action.succeeded", "notify", "apps", "info",
         "Done: {action_type} {app_id}", "{message}", audience=OWNERS_AND_REQUESTER,
         link="/activity/{action_id}", resolves=("approval:{action_id}",)),
    Spec("action.failed", "notify", "apps", "warning",
         "Failed: {action_type} {app_id}", "{message}", audience=OWNERS_AND_REQUESTER,
         link="/activity/{action_id}", resolves=("approval:{action_id}",)),
    Spec("action.outcome_unknown", "open", "apps", "critical",
         "Outcome unknown: {action_type} {app_id}",
         "OneMind cannot tell whether this change was applied. Check the app before retrying. {message}",
         dedupe="action:{action_id}", link="/activity/{action_id}", auto_resolve=False,
         learn_more=f"{_DOCS}/learning/09-gateway-approvals-agents-mcp.md"),
    # ---- nodes ---------------------------------------------------------------------------
    Spec("node.joined", "notify", "nodes", "info", "Node {node_id} joined",
         "The node joined as a {role}.", link="/nodes"),
    Spec("node.stale", "inbox", "nodes", "info", "{hostname} is late",
         "No heartbeat from {hostname} for {age_s} s.", link="/nodes/{node_id}"),
    Spec("node.offline", "open", "nodes", "warning", "{hostname} is offline",
         "No heartbeat from {hostname} for {age_s} s.", dedupe="node:{node_id}:offline",
         link="/nodes/{node_id}", notify_resolve=True, learn_more=_NODE_HELP),
    Spec("node.online", "resolve", "nodes", resolves=("node:{node_id}:offline",)),
    Spec("disk.low", "open", "storage", "warning", "Disk almost full on {hostname}",
         "{free_pct}% free on {mount} ({free_gb} GB).", dedupe="node:{node_id}:disk",
         link="/nodes/{node_id}", notify_resolve=True, learn_more=_STORAGE_HELP),
    Spec("disk.ok", "resolve", "storage", resolves=("node:{node_id}:disk",)),
    Spec("disk.budget_near", "open", "storage", "warning", "Image disk filling up on {hostname}",
         "{disk_used_pct}% used; the image budget is {budget_pct}%. OneMind already removes only superseded "
         "app images (never an installed app's, stopped or not); add a disk or remove apps you no longer need.",
         dedupe="node:{node_id}:disk_budget", link="/nodes/{node_id}", notify_resolve=True, learn_more=_STORAGE_HELP),
    Spec("disk.budget_ok", "resolve", "storage", resolves=("node:{node_id}:disk_budget",)),
    Spec("memory.high", "open", "nodes", "warning", "Memory almost full on {hostname}",
         "{used_pct}% of memory in use.", dedupe="node:{node_id}:memory", link="/nodes/{node_id}", learn_more=_NODE_HELP),
    Spec("memory.ok", "resolve", "nodes", resolves=("node:{node_id}:memory",)),
    Spec("temperature.high", "open", "nodes", "warning", "{hostname} is running hot",
         "{temp_c} °C (limit {limit_c} °C).", dedupe="node:{node_id}:temperature",
         link="/nodes/{node_id}", notify_resolve=True, learn_more=_NODE_HELP),
    Spec("temperature.ok", "resolve", "nodes", resolves=("node:{node_id}:temperature",)),
    Spec("cpu.high", "open", "nodes", "warning", "{hostname} is overloaded",
         "CPU at {cpu_pct}% for {minutes} minutes.", dedupe="node:{node_id}:cpu", link="/nodes/{node_id}", learn_more=_NODE_HELP),
    Spec("cpu.ok", "resolve", "nodes", resolves=("node:{node_id}:cpu",)),
    Spec("storage.disk.warning", "open", "storage", "warning", "Disk health warning on {node_id}",
         "Check the health report for {disk} in Storage.", dedupe="storage:{node_id}:disk:{disk_key}",
         link="/storage", learn_more=_STORAGE_HELP),
    Spec("storage.disk.failing", "open", "storage", "critical", "Disk failing on {node_id}",
         "Check {disk} in Storage and verify an off-box backup.", dedupe="storage:{node_id}:disk:{disk_key}",
         link="/storage", learn_more=_STORAGE_HELP),
    Spec("storage.disk.ok", "resolve", "storage", resolves=("storage:{node_id}:disk:{disk_key}",)),
    # P-10: smartd (the background disk watcher on the image) raised a warning. Only an owner clears it.
    Spec("storage.smart.warning", "open", "storage", "warning", "Disk warning on {device}",
         "{message} Check {device} in Storage and keep a backup.", dedupe="storage:{node_id}:smartd:{alert_id}",
         link="/storage", auto_resolve=False, learn_more=_STORAGE_HELP),
    Spec("storage.smart.failing", "open", "storage", "critical", "Disk failing: {device}",
         "{message} Back up now, then check {device} in Storage.", dedupe="storage:{node_id}:smartd:{alert_id}",
         link="/storage", auto_resolve=False, learn_more=_STORAGE_HELP),
    # ---- automation and security ---------------------------------------------------------
    Spec("automation.breaker.opened", "open", "automation", "warning", "Automation paused: {name}",
         "{failures} requests failed. Review the rule and run a dry run before enabling it again.",
         dedupe="automation:{rule_id}:breaker", link="/automation", learn_more=f"{_DOCS}/leap/core/AUTOMATION.md"),
    Spec("automation.rule.enabled", "resolve", "automation", resolves=("automation:{rule_id}:breaker",)),
    Spec("security.owner_override.enabled", "open", "security", "warning", "Owner overrides are enabled",
         "An owner may approve eligible app installs with a failed scan. Review the gateway setting.",
         dedupe="owner-override-enabled", link="/activity", learn_more=f"{_DOCS}/leap/core/SECRETS.md",
         auto_resolve=False),
    Spec("app.owner_override", "notify", "security", "critical", "Owner override for {app_id}",
         "An owner approved the install despite a failed scan. Review the audit entry in Activity.",
         link="/activity"),
    # ---- apps ----------------------------------------------------------------------------
    Spec("app.unhealthy", "open", "apps", "warning", "{app_id} is not working",
         "{reason}", dedupe="app:{app_id}:health", audience=OWNERS_AND_ADULTS,
         link="/apps/{app_id}", fix=_fix("app.restart", "app_id"), notify_resolve=True),
    Spec("app.healthy", "resolve", "apps", resolves=("app:{app_id}:health",)),
    Spec("app.crashlooping", "open", "apps", "warning", "{app_id} keeps restarting",
         "{restarts} restarts in {window_min} minutes. Last exit: {last_exit_reason}.",
         dedupe="app:{app_id}:crashloop", link="/apps/{app_id}", fix=_fix("app.restart", "app_id")),
    Spec("app.crashloop_ended", "resolve", "apps", resolves=("app:{app_id}:crashloop",)),
    Spec("app.restarted", "inbox", "apps", "info", "{app_id} restarted",
         "Component {component} restarted ({last_exit_reason}).", link="/apps/{app_id}"),
    Spec("app.oom_killed", "notify", "apps", "warning", "{app_id} ran out of memory",
         "Component {component} was stopped for using too much memory and restarted.", link="/apps/{app_id}"),
    Spec("app.rolled_back", "open", "apps", "warning", "{app_id} was rolled back",
         "{reason}", dedupe="app:{app_id}:revert", link="/apps/{app_id}", auto_resolve=False,
         learn_more=f"{_DOCS}/leap/core/APP-LIFECYCLE.md", aliases=("app.update_reverted",)),
    Spec("app.scan_blocked", "open", "security", "critical", "{app_id} failed its security scan",
         "The last scan of {app_id} found a problem. Remove it or wait for a fixed version.",
         dedupe="app:{app_id}:scan", link="/apps/{app_id}", fix=_fix("app.remove", "app_id")),
    Spec("app.scan_stale", "open", "security", "warning", "{app_id} has not been scanned recently",
         "{reason}", dedupe="app:{app_id}:scan_stale", link="/apps/{app_id}",
         fix=lambda _d: {"type": "catalog.refresh", "params": {}}),
    Spec("app.scan_ok", "resolve", "security", resolves=("app:{app_id}:scan", "app:{app_id}:scan_stale")),
    # ---- bridges (#610: core/onemind_core/bridges.py) ------------------------------------
    Spec("bridge.paused", "open", "apps", "warning", "{app_id} was paused",
         "It sent {rejects} events OneMind refused within {window_min} minutes (last: {reason}). Nothing more "
         "is taken from it until you resume it.", dedupe="bridge:{app_id}:paused", link="/apps/{app_id}",
         learn_more="https://github.com/onemindos/ONEMINDOS/blob/release/next/sdk/contracts/connectors.md#the-intake-post-v1bridgesidevents-610"),
    Spec("bridge.resumed", "resolve", "apps", resolves=("bridge:{app_id}:paused",)),
    # ---- OS updates ----------------------------------------------------------------------
    Spec("update.available", "open", "updates", "info", "Update {version} available for {hostname}",
         "", dedupe="os:{node_id}:available", link="/updates",
         fix=_fix("os.update.apply", "node_id", "version"), learn_more=f"{_DOCS}/leap/core/UPDATES.md"),
    Spec("update.applied", "notify", "updates", "info", "{hostname} updated to {version}", "",
         link="/updates", resolves=("os:{node_id}:available", "os:{node_id}:rollback")),
    Spec("update.rolled_back", "open", "updates", "warning", "Update on {hostname} was rolled back",
         "{reason}", dedupe="os:{node_id}:rollback", link="/updates", auto_resolve=False, learn_more=f"{_DOCS}/leap/core/UPDATES.md"),
    # ---- backups -------------------------------------------------------------------------
    Spec("backup.failed", "open", "backups", "warning", "Backup to {target} failed", "{reason}",
         dedupe="backup:{target}", link="/backups", fix=lambda _d: {"type": "backup.run", "params": {"scope": "box"}},
         notify_resolve=True, aliases=("backup.run.failed",)),
    Spec("backup.succeeded", "resolve", "backups", resolves=("backup:{target}",),
         aliases=("backup.run.succeeded",)),
    Spec("backup.verify_failed", "open", "backups", "warning", "Test restore of {unit} failed", "{reason}",
         dedupe="verify:{unit}", link="/backups", learn_more=f"{_DOCS}/leap/core/BACKUPS.md",
         aliases=("backup.verify.failed",)),
    Spec("backup.verified", "notify", "backups", "info", "Test restore of {unit} passed", "",
         link="/backups", resolves=("verify:{unit}",), aliases=("backup.verify.succeeded",)),
    # ---- browser downloads (#693; files/downloads.py) ---------------------------------------
    # A held file is an owner's alert; it clears when the file is released to Files (by a clean
    # rescan or an owner's approval of the fix) or discarded. Nothing in quarantine is ever opened.
    Spec("files.download.quarantined", "open", "security", "warning", "Download held: {name}",
         "{reason} The file stays in quarantine, unopened, until an owner approves moving it to Files "
         "or discards it.", dedupe="download:{download_id}",
         fix=_fix("files.download.release", "download_id", "verdict")),
    Spec("files.download.delivered", "inbox", "storage", "info", "Downloaded: {name}",
         "Saved to {path} in your Files.", audience=PERSON, link="/files",
         resolves=("download:{download_id}",)),
    Spec("files.download.discarded", "resolve", "security", resolves=("download:{download_id}",)),
    # ---- the notifier itself -------------------------------------------------------------
    Spec("notify.channel_failing", "open", "security", "warning", "Notification channel {label} is failing",
         "{reason}", dedupe="channel:{channel_id}", link="/settings/notifications", learn_more=f"{_DOCS}/leap/core/NOTIFICATIONS.md"),
    Spec("notify.channel_ok", "resolve", "security", resolves=("channel:{channel_id}",)),
    # ---- the message bus (#620, fabricwatch.py): who tried to connect ----------------------
    Spec("fabric.unknown_key", "open", "security", "warning", "An unknown device tried to join the message bus",
         "A key this box never issued ({key_short}) was refused. Nothing was let in.",
         dedupe="fabric:unknown:{key}", auto_resolve=False, link="/settings/about",
         learn_more=f"{_DOCS}/learning/nats-fabric.md"),
    Spec("fabric.revoked_retry", "open", "security", "warning", "{who} was removed but keeps trying to connect",
         "A key that was removed ({key_short}) is still being refused at the message bus.",
         dedupe="fabric:revoked:{key}", auto_resolve=False, link="/settings/about",
         learn_more=f"{_DOCS}/learning/nats-fabric.md"),
    Spec("fabric.key_refused", "open", "security", "warning", "A device was refused while using {who}'s key",
         "A sign-in claiming the key {key_short} was refused. The key is real, so someone may be trying to pose as it.",
         dedupe="fabric:refused:{key}", auto_resolve=False, link="/settings/about",
         learn_more=f"{_DOCS}/learning/nats-fabric.md"),
    Spec("fabric.flapping", "open", "security", "warning", "{who} keeps disconnecting",
         "It connected {connects} times in {window_s} seconds.", dedupe="fabric:flap:{key}", link="/settings/about",
         learn_more=f"{_DOCS}/learning/nats-fabric.md"),
    Spec("fabric.flap_cleared", "resolve", "security", resolves=("fabric:flap:{key}",)),
]

CATALOGUE: dict[str, Spec] = {}
for _s in _SPECS:
    for _name in (_s.type, *_s.aliases):
        CATALOGUE[_name] = _s

# Types whose alerts reach only the in-app inbox (a failing channel must not hide behind itself).
INAPP_ONLY_ALERTS = {"notify.channel_failing"}

# Types a node may raise through its NATS outbox (§12.9: the gateway validates them). Only
# conditions of the node itself, whose alert keys carry the node id taken from the subject, plus
# backup results from the node's backup agent. Never approvals, actions, app health, scans or the
# notifier's own alerts: a node (or anything able to publish on its subject) must not be able to
# resolve a security alert, forge an approval prompt or address a notification to a person.
NODE_SOURCED = frozenset({
    "disk.low", "disk.ok", "memory.high", "memory.ok", "temperature.high", "temperature.ok",
    "cpu.high", "cpu.ok", "update.available", "update.applied", "update.rolled_back",
    "backup.failed", "backup.succeeded", "backup.verify_failed", "backup.verified",
})
# Fields a node never sets: they pick recipients or link the item to an action.
NODE_RESERVED_FIELDS = frozenset({"person_id", "requested_by", "requested_by_kind", "action_id", "channel_id"})


def lookup(event_type: str) -> Spec | None:
    return CATALOGUE.get(event_type)


def from_audit(record: dict, get_action: Callable[[str], object | None]) -> tuple[str, dict] | None:
    """Map one action-ledger audit line to (catalogue type, data), or None.

    The ledger writes audit lines directly (not through publish_event), so the notifier reads
    them; lines written by publish_event carry `data.event_id` and arrive as events instead.
    """
    data = record.get("data") or {}
    if "event_id" in data:
        return None
    event = record.get("event")
    if event == "automation.rule.enabled" and data.get("rule_id"):
        return event, {"rule_id": data["rule_id"]}
    action_id = record.get("action_id")
    if not action_id or not isinstance(event, str) or not event.startswith("action."):
        return None
    a = get_action(action_id)
    if a is None:
        return None
    params = getattr(a, "params", {}) or {}
    facts = {
        "action_id": action_id,
        "action_type": getattr(a, "type", None),
        "app_id": params.get("app_id"),
        "requested_by": (getattr(a, "requested_by", {}) or {}).get("id"),
        "requested_by_kind": (getattr(a, "requested_by", {}) or {}).get("kind"),
        "expires_at": data.get("expires_at") or _iso(getattr(a, "expires_at", None)),
        "message": str(data.get("message") or "")[:500],
    }
    mapped = {
        "action.awaiting_approval": "approval.requested",
        "action.approved": "approval.closed",
        "action.denied": "approval.closed",
        "action.expired": "approval.closed",
        "action.cancelled": "approval.closed",
        "action.succeeded": "action.succeeded",
        "action.failed": "action.failed",
        "action.outcome_unknown": "action.outcome_unknown",
    }.get(event)
    return (mapped, facts) if mapped else None


def topic_for(spec: Spec, data: dict) -> str:
    if spec.type.startswith("action."):
        return _topic_for_action(data.get("action_type"))
    return spec.topic


def _iso(dt) -> str | None:
    return None if dt is None else dt.isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    # Run standalone from make lint. This needs only the standard library on the CI runner.
    from urllib.parse import urlsplit

    missing = []
    for alert in _SPECS:
        if alert.kind != "open" or callable(alert.fix):
            continue
        help_url = urlsplit(alert.learn_more or "")
        local_page = not help_url.netloc and (alert.learn_more or "").startswith("/")
        if not local_page and not (help_url.scheme in {"https", "http"} and help_url.hostname):
            missing.append(alert.type)
    if missing:
        raise SystemExit("Alerts without a fix action or help link: " + ", ".join(missing))
