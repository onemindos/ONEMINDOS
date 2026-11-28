# SPDX-License-Identifier: Apache-2.0
"""The notifier: events in, alerts and inbox items out, deliveries to channels (contract §12.14).

Sources (docs/architecture/NOTIFICATIONS.md §2):
1. every `publish_event` (in-process subscription to `>`), including monitoring's conditions;
2. the action ledger's audit lines (the ledger appends them directly, so the notifier reads the
   audit stream through a tee on its publish hook and maps them with `catalogue.from_audit`);
3. node outbox events on NATS `onemind.node.<id>.event.>` (contract §12.9), when NATS is up.

Ingest runs in the caller's thread and only writes rows; network sends happen in the delivery
worker (`pump`), with retry and backoff (30 s, 2 min, 10 min, 1 h, 6 h, then dead). A channel
failing for over an hour opens `notify.channel_failing`, in-app only.

Per-channel limits a channel's config may set (the `sms` kind always does, issue #869):
`min_severity` (below it the channel gets nothing), `per_hour` (instead of channel_per_hour) and
`daily_cap` (provider attempts in any 24 h; over it a delivery is `dropped`, audited as
`notify.delivery.dropped`, and never sent or retried). The cap counts every attempt that may reach
the provider, written before the request goes out: a retry, a 5xx and a timeout after the provider
already took (and billed) the text all count, and the cap is checked again before each retry, so
a slow or failing provider cannot be sent more than `daily_cap` texts a day. Test sends count too.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from ..audit import AUDIT_SUBJECT
from ..auth import Principal
from ..builtins import AppPrincipal
from ..ledger import iso, utc
from ..sections import config_section
from . import catalogue, routing, topics
from .catalogue import RANK, SEVERITIES, Spec
from .channels import (
    DeliveryError, Message, send_channel, send_push,
)
from .crypto import SecretBox, Vapid
from .ids import new_id
from .store import AlertRow, ChannelRow, DeliveryRow, NotificationRow, NotifyRepository, SourceRow

log = logging.getLogger("onemind.notify")

BACKOFF_S = (30, 120, 600, 3600, 6 * 3600)
FAILING_ALERT_AFTER_S = 3600
FLAP_WINDOW_S = 600
OUTAGE_GROUP_WINDOW = timedelta(seconds=30)
NODE_EVENT_SUBJECT = "onemind.node.*.event.>"
ALERT_SUBJECT_PREFIX = "onemind.alert."
MAX_BODY = 4096
MAX_TITLE = 200


@config_section("notify")
@dataclass(frozen=True)
class NotifySettings:
    worker: bool = True                 # ONEMIND_NOTIFY_WORKER: run the delivery worker thread
    poll_s: float = 2.0                 # ONEMIND_NOTIFY_POLL_S
    dir: Path | None = None             # ONEMIND_NOTIFY_DIR: keys (default: <audit dir>/notify)
    renotify_s: int = 1800              # ONEMIND_NOTIFY_RENOTIFY_S: one re-notify per alert per 30 min
    channel_per_hour: int = 30          # ONEMIND_NOTIFY_CHANNEL_PER_HOUR: then one summary
    send_per_min: int = 10              # ONEMIND_NOTIFY_SEND_PER_MIN: POST /v1/notifications/send
    http_timeout_s: float = 10.0        # ONEMIND_NOTIFY_HTTP_TIMEOUT_S (also SMTP)
    vapid_subject: str = "https://onemind.local"  # ONEMIND_NOTIFY_VAPID_SUBJECT (RFC 8292 `sub`)

    def validate(self) -> None:
        if self.poll_s <= 0 or self.renotify_s < 0 or self.channel_per_hour < 1 or self.send_per_min < 1:
            raise ValueError("ONEMIND_NOTIFY_* intervals and limits must be positive")
        if not self.vapid_subject.startswith(("https://", "mailto:")):
            raise ValueError("ONEMIND_NOTIFY_VAPID_SUBJECT must be an https: or mailto: URI")


class NotifyService:
    def __init__(self, gw):
        self.gw = gw
        self.cfg: NotifySettings = gw.settings.section(NotifySettings)
        self.clock = gw.clock
        self.repo = NotifyRepository(gw.db)
        key_dir = self.cfg.dir or (gw.settings.audit_path.parent / "notify")
        self.box = SecretBox(key_dir / "secret.key")
        self.vapid = Vapid(key_dir / "vapid.pem")
        self.box_id = gw.settings.node_id or "onemind"
        self.base_url = gw.settings.gateway_url().rstrip("/")
        self._lock = threading.RLock()
        self._pump_lock = threading.Lock()
        self._cap_lock = threading.Lock()   # the daily-cap check and its attempt row go together
        self._kick = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._nats_task: asyncio.Task | None = None
        self._sends: dict[str, deque] = defaultdict(deque)
        self._send_dedupe: dict[tuple[str, str], datetime] = {}
        self._last_prune: datetime | None = None
        self.topics = topics.TopicRegistry()  # the built-ins' topics; routers/notifications.py wires the registry
        self._meter: dict[str, deque] = defaultdict(lambda: deque(maxlen=4096))  # source id -> post times, 1 h

    # ---- wiring -------------------------------------------------------------------------
    def attach(self) -> None:
        """Subscribe to events and the audit stream; start the worker and NATS listener with the app."""
        self.gw.events.subscribe(">", self.on_event)
        audit = self.gw.audit
        downstream = audit.publish

        def tee(subject: str, data: bytes) -> None:
            if downstream is not None:
                downstream(subject, data)
            if subject == AUDIT_SUBJECT:
                self.on_audit_line(data)

        audit.publish = tee
        self.gw.on_startup(self.start)
        self.gw.on_shutdown(self.stop)

    async def start(self) -> None:
        if self.cfg.worker:
            self._stop.clear()
            self._thread = threading.Thread(target=self._worker, name="notify-worker", daemon=True)
            self._thread.start()
        if self.gw.settings.nats_url:
            self._nats_task = asyncio.create_task(self._nats_listener(), name="notify-nats")

    async def stop(self) -> None:
        self._stop.set()
        self._kick.set()
        if self._nats_task is not None:
            self._nats_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._nats_task
        if self._thread is not None:
            await asyncio.to_thread(self._thread.join, 10)

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                self.pump()
            except Exception:
                log.exception("notify worker pass failed")
            self._kick.wait(self.cfg.poll_s)
            self._kick.clear()

    async def _nats_listener(self) -> None:
        subscribed = None
        while True:
            bus = self.gw.bus
            nc = bus.nc if bus.connected else None
            if nc is not None and nc is not subscribed:
                try:
                    await nc.subscribe(NODE_EVENT_SUBJECT, cb=self._on_nats)
                    subscribed = nc
                except Exception:
                    log.warning("could not subscribe to node events; retrying")
            await asyncio.sleep(1.0)

    async def _on_nats(self, msg) -> None:
        await asyncio.to_thread(self.on_node_event, msg.subject, msg.data)

    # ---- sources ------------------------------------------------------------------------
    def on_event(self, envelope: dict) -> None:
        spec = catalogue.lookup(envelope.get("type", ""))
        if spec is None:
            return
        data = dict(envelope.get("data") or {})
        if spec.type == "legacy.claim.reminder" and data.get("notice") == "last_day":
            return  # Recovery commits the final reminder with the claim's notice marker.
        enrich = self.gw.notify_enrichers.get(str(envelope.get("type", "")).split(".", 1)[0])
        if enrich is not None:
            try:
                data.update({k: v for k, v in enrich(data).items() if k not in data})
            except Exception:
                log.exception("notification enricher failed for %s", envelope.get("type"))
        # Recovery's outbox supplies a stable ID across retries. Other event keys can describe a
        # recurring condition rather than a single delivery.
        delivery_id = envelope.get("dedupe_key") if spec.type.startswith("recovery.request.") else None
        self.ingest(spec, data, source=envelope.get("source_id") or "gateway", delivery_id=delivery_id)

    def on_audit_line(self, line: bytes) -> None:
        try:
            rec = json.loads(line)
            mapped = catalogue.from_audit(rec, self.gw.repo.get)
            if mapped is not None:
                spec = catalogue.lookup(mapped[0])
                if spec is not None:
                    self.ingest(spec, mapped[1], source="gateway")
        except Exception:  # never break the ledger's audit append
            log.exception("notifier failed on an audit line")

    def on_node_event(self, subject: str, raw: bytes) -> bool:
        """A node outbox event (§12.9). The node id comes from the subject, never from the body."""
        parts = subject.split(".")
        if len(parts) < 5 or parts[0] != "onemind" or parts[1] != "node" or parts[3] != "event" or len(raw) > 16384:
            return False
        node_id, event_type = parts[2], ".".join(parts[4:])
        try:
            env = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return False
        if not isinstance(env, dict) or env.get("type") != event_type or not isinstance(env.get("data", {}), dict):
            return False
        spec = catalogue.lookup(event_type)
        if spec is None or spec.type not in catalogue.NODE_SOURCED:
            return False
        data = {k: v for k, v in (env.get("data") or {}).items()
                if not k.startswith("_") and k not in catalogue.NODE_RESERVED_FIELDS}
        data["node_id"] = node_id
        node = self.gw.registry.get(node_id)
        data.setdefault("hostname", (node or {}).get("hostname") or node_id)
        self.ingest(spec, data, source=f"node:{node_id}")
        return True

    # ---- people -------------------------------------------------------------------------
    def people(self) -> dict[str, str]:
        """person id -> role: the tokens file (static principals, v0), then every feature's people
        source (identity: active household accounts, §12.6)."""
        out: dict[str, str] = {}
        for p in self.gw.tokens.principals():
            if p.kind == "person":
                out.setdefault(p.id, p.role)
        for source in self.gw.people_sources:
            for pid, role in source().items():
                out.setdefault(pid, role)
        return out

    def _audience(self, spec: Spec, data: dict) -> dict:
        if spec.type in catalogue.INAPP_ONLY_ALERTS and data.get("person_id"):
            return {"roles": [], "persons": [data["person_id"]]}
        if spec.audience == catalogue.PERSON:
            return {"roles": [], "persons": [str(data["person_id"])] if data.get("person_id") else []}
        roles = ["owner"] + (["adult"] if spec.audience == catalogue.OWNERS_AND_ADULTS else [])
        persons = []
        if spec.audience == catalogue.OWNERS_AND_REQUESTER and data.get("requested_by_kind", "person") == "person":
            if data.get("requested_by"):
                persons.append(str(data["requested_by"]))
        return {"roles": roles, "persons": persons}

    def _recipients(self, audience: dict) -> list[str]:
        people = self.people()
        ids = [pid for pid, role in people.items() if role in audience.get("roles", [])]
        ids += [pid for pid in audience.get("persons", []) if pid in people]
        return list(dict.fromkeys(ids))

    # ---- ingest -------------------------------------------------------------------------
    def ingest(self, spec: Spec, data: dict, source: str = "gateway", *, delivery_id: str | None = None) -> None:
        with self._lock:
            for tpl in spec.resolves:
                key = catalogue.render(tpl, data)
                if "?" not in key:
                    self.resolve_key(key)
            if spec.kind == "open":
                self._open(spec, data, source)
            elif spec.kind in ("notify", "inbox"):
                self._notify(spec, data, source, delivery_id=delivery_id)

    def record_legacy_final_notice(self, owner_id: str, data: dict, record: Callable[[Session], None]) -> None:
        """Commit the owner's inbox item, household fanout and recovery bookkeeping together."""
        spec = catalogue.lookup("legacy.claim.reminder")
        assert spec is not None
        with self._lock:
            self._notify(spec, data, "gateway", required_person=owner_id, record=record)

    def _notify(self, spec: Spec, data: dict, source: str, *, required_person: str | None = None,
                record: Callable[[Session], None] | None = None, delivery_id: str | None = None) -> None:
        people = self._recipients(self._audience(spec, data))
        if required_person is not None and required_person not in people:
            people.append(required_person)
        self._fanout(
            people, severity=self._severity(spec, data),
            topic=catalogue.topic_for(spec, data), title=catalogue.render(spec.title, data),
            body=catalogue.render(spec.body, data), link=self._link(spec, data), source=source,
            action_id=data.get("action_id"), alert_id=None, inapp_only=spec.kind == "inbox",
            record=record, delivery_id=delivery_id, **self._chip(spec.type, source),
        )

    def _chip(self, event_type: str, source: str) -> dict:
        """Where a catalogue item came from: the node or the gateway, and the built-in that routes it."""
        return {"source_kind": "node" if source.startswith("node:") else "system",
                "app_id": self.topics.app_for_event(event_type)}

    def _severity(self, spec: Spec, data: dict) -> str:
        sev = data.get("severity") if isinstance(data.get("severity"), str) else None
        return sev if sev in SEVERITIES else spec.severity

    def _link(self, spec: Spec, data: dict) -> str | None:
        if not spec.link:
            return None
        link = catalogue.render(spec.link, data)
        return None if "?" in link else link

    def _open(self, spec: Spec, data: dict, source: str) -> None:
        key = catalogue.render(spec.dedupe or "", data)
        if not key or "?" in key:
            log.warning("event %s lacks the ids for its dedupe key; ignored", spec.type)
            return
        now = self.clock()
        severity = self._severity(spec, data)
        title = catalogue.render(spec.title, data)[:MAX_TITLE]
        body = catalogue.render(spec.body, data)[:MAX_BODY]
        row = self.repo.open_alert(key)
        if row is not None:
            escalated = RANK[severity] > RANK[row.severity]
            row.occurrences += 1
            row.updated_at = now
            row.title, row.body = title, body
            if escalated:
                row.severity = severity
            self.repo.save_alert(row)
            self._alert_event("updated", row)
            if escalated or self._renotify_due(row, now):
                self._notify_alert(row, spec, data, now)
            return
        prev = self.repo.last_resolved(key)
        if prev is not None and prev.resolved_at is not None and (now - utc(prev.resolved_at)).total_seconds() < FLAP_WINDOW_S:
            prev.state, prev.open_key, prev.resolved_at = "open", key, None
            prev.flapping, prev.occurrences, prev.updated_at = True, prev.occurrences + 1, now
            prev.acked_by = prev.acked_at = None
            escalated = RANK[severity] > RANK[prev.severity]
            prev.severity = severity if escalated else prev.severity
            prev.title, prev.body = title, body
            self.repo.save_alert(prev)
            self._alert_event("updated", prev)
            if escalated or self._renotify_due(prev, now):
                self._notify_alert(prev, spec, data, now)
            return
        fix = spec.fix(data) if spec.fix else None
        row = AlertRow(
            id=new_id("alrt"), type=spec.type, severity=severity, title=title, body=body,
            subject_json=json.dumps(_subject(data), sort_keys=True), source_id=source, state="open",
            dedupe_key=key, open_key=key, audience_json=json.dumps(self._audience(spec, data)),
            fix_json=json.dumps(fix) if fix else None, learn_more_url=spec.learn_more,
            link=self._link(spec, data), topic=catalogue.topic_for(spec, data),
            auto_resolve=spec.auto_resolve, notify_resolve=spec.notify_resolve, occurrences=1,
            flapping=False, opened_at=now, updated_at=now,
        )
        if self.repo.insert_alert(row) is None:  # lost a race with another writer: update theirs
            self._open(spec, data, source)
            return
        self._alert_event("opened", row)
        self._notify_alert(row, spec, data, now)

    def _renotify_due(self, row: AlertRow, now: datetime) -> bool:
        return row.last_notified_at is None or (now - utc(row.last_notified_at)).total_seconds() >= self.cfg.renotify_s

    def _notify_alert(self, row: AlertRow, spec: Spec | None, data: dict, now: datetime) -> None:
        audience = json.loads(row.audience_json or "{}")
        group_key = None
        if row.type == "node.offline":
            group_key = row.dedupe_key
        elif row.type == "app.unhealthy" and row.source_id == "gateway:monitoring":
            node_id = data.get("node_id")
            if isinstance(node_id, str) and node_id:
                group_key = f"node:{node_id}:offline"
        delay = OUTAGE_GROUP_WINDOW if group_key and row.type == "app.unhealthy" else timedelta()
        self._fanout(
            self._recipients(audience), severity=row.severity, topic=row.topic, title=row.title,
            body=row.body, link=row.link, source=row.source_id, action_id=data.get("action_id"),
            alert_id=row.id, inapp_only=row.type in catalogue.INAPP_ONLY_ALERTS, group_key=group_key,
            delivery_delay=delay, **self._chip(row.type, row.source_id),
        )
        row.last_notified_at, row.last_notified_severity = now, row.severity
        self.repo.save_alert(row)

    def resolve_key(self, key: str, by: str | None = None) -> AlertRow | None:
        with self._lock:
            row = self.repo.open_alert(key)
            return self._resolve(row, by) if row is not None else None

    def _resolve(self, row: AlertRow, by: str | None) -> AlertRow:
        now = self.clock()
        row.state, row.open_key, row.resolved_at, row.updated_at = "resolved", None, now, now
        self.repo.save_alert(row)
        self._alert_event("resolved", row, by=by)
        if row.notify_resolve and row.last_notified_at is not None:
            self._fanout(
                self._recipients(json.loads(row.audience_json or "{}")), severity="info", topic=row.topic,
                title=f"Resolved: {row.title}"[:MAX_TITLE], body="", link=row.link, source=row.source_id,
                action_id=None, alert_id=row.id, inapp_only=False, **self._chip(row.type, row.source_id),
            )
        return row

    def _alert_event(self, what: str, row: AlertRow, by: str | None = None) -> None:
        """Record every committed transition for ordered SSE replay, then publish the alert."""
        payload = {"alert_id": row.id, "type": row.type, "state": row.state, "by": by}
        self.gw.events.publish_event("alert", what, payload, severity=row.severity,
                                     dedupe_key=row.dedupe_key, resource={"kind": "alert", "id": row.id})
        # Contract §12.9: the alert record on onemind.alert.<source>.<kind> (best effort).
        from .store import alert_json
        try:
            self.gw.bus.publish_threadsafe(ALERT_SUBJECT_PREFIX + row.type,
                                           json.dumps(alert_json(row), separators=(",", ":")).encode())
        except Exception:
            log.exception("alert publish failed")

    # ---- fan-out ------------------------------------------------------------------------
    def preferences(self, person_id: str) -> tuple[dict, str]:
        row = self.repo.get_preferences(person_id)
        doc = routing.DEFAULT if row is None else json.loads(row.doc_json)
        return doc, routing.etag(doc)

    def _targets_of(self, person_id: str) -> list[str]:
        return ([c.id for c in self.repo.list_channels(person_id)]
                + [d.id for d in self.repo.list_devices(person_id)])

    def muted(self, person_id: str, topic: str, target: str = routing.IN_APP) -> bool:
        doc, _ = self.preferences(person_id)
        return routing.silenced(doc, self.clock()) or routing.muted(doc, topic, target)

    def _drop_muted(self, delivery: DeliveryRow, notification: NotificationRow | None) -> bool:
        if notification is None or not self.muted(delivery.person_id, notification.topic, delivery.target_id):
            return False
        delivery.state, delivery.next_attempt_at, delivery.last_error = "dropped", None, "delivery suppressed by preferences"
        self.repo.save_delivery(delivery)
        return True

    def _channel_limits(self, person_id: str) -> dict[str, dict]:
        """channel id -> its config, for the per-channel limits (min_severity, per_hour)."""
        return {c.id: json.loads(c.config_json) for c in self.repo.list_channels(person_id)}

    def _fanout(self, people: list[str], *, severity: str, topic: str, title: str, body: str,
                link: str | None, source: str, action_id: str | None, alert_id: str | None,
                inapp_only: bool, source_kind: str = "system", app_id: str | None = None,
                asset_id: str | None = None, group_key: str | None = None,
                actions: list[dict] | None = None, delivery_delay: timedelta = timedelta(),
                record: Callable[[Session], None] | None = None,
                delivery_id: str | None = None) -> list[str]:
        now = self.clock()
        created = []
        pending = []
        for pid in people:
            nid = new_id("ntf")
            row = NotificationRow(
                id=nid, person_id=pid, severity=severity, topic=topic, title=title[:MAX_TITLE],
                body=body[:MAX_BODY], link=link, source=source[:120], action_id=action_id,
                alert_id=alert_id, source_kind=source_kind, app_id=app_id, asset_id=asset_id,
                group_key=group_key, actions_json=json.dumps(actions) if actions else None, created_at=now,
            )
            deliveries = []
            doc, _ = self.preferences(pid)
            if not inapp_only and not routing.silenced(doc, now):
                held = routing.hold(doc, topic, severity, now)
                limits = self._channel_limits(pid)
                for target in routing.targets(doc, topic, severity, self._targets_of(pid)):
                    cfg = limits.get(target, {})
                    if RANK[severity] < RANK.get(cfg.get("min_severity", "info"), 0):
                        continue                       # below this channel's level: never
                    d = DeliveryRow(id=new_id("dlv"), notification_id=nid, person_id=pid, target_id=target,
                                    state="queued", attempts=0, next_attempt_at=now + delivery_delay, created_at=now)
                    window_start = now - timedelta(hours=1)
                    if self.repo.sent_count(target, window_start) >= cfg.get("per_hour", self.cfg.channel_per_hour):
                        oldest = self.repo.oldest_in_window(target, window_start) or now
                        d.state, d.held_reason = "held", "rate"
                        d.release_at, d.next_attempt_at = oldest + timedelta(hours=1), None
                    elif held is not None:
                        d.state, d.held_reason, d.release_at, d.next_attempt_at = "held", held[0], held[1], None
                    deliveries.append(d)
            if record is not None:
                pending.append((row, deliveries))
            elif self.repo.add_notification(row, deliveries, delivery_id=delivery_id):
                self._notification_created(row)
            else:
                continue
            created.append(nid)
        if record is not None:
            self.repo.add_notifications(pending, record)
            for row, _ in pending:
                self._notification_created(row)
        self._kick.set()
        return created

    def _notification_created(self, row: NotificationRow) -> None:
        self.gw.events.publish_event(
            "notification", "created",
            {"notification_id": row.id, "source_kind": row.source_kind, "app_id": row.app_id,
             "asset_id": row.asset_id, "group_key": row.group_key}, severity=row.severity,
            resource={"kind": "notification", "id": row.id},
        )

    # ---- delivery -----------------------------------------------------------------------
    def pump(self) -> int:
        """One worker pass: release held items as summaries, send what is due. Returns sends tried."""
        with self._pump_lock:
            now = self.clock()
            groups: dict[str, list[DeliveryRow]] = defaultdict(list)
            for d in self.repo.released_held(now):
                n = self.repo.get_notification(d.notification_id)
                if self._drop_muted(d, n):
                    continue
                if n is None or not self._fold_outage(d, n, now):
                    groups[d.target_id].append(d)
            for rows in groups.values():
                if len(rows) == 1:
                    d = rows[0]
                    d.state, d.next_attempt_at = "queued", now
                    self.repo.save_delivery(d)
                    continue
                latest = rows[-1]
                summary = DeliveryRow(
                    id=new_id("dlv"), notification_id=latest.notification_id, person_id=latest.person_id,
                    target_id=latest.target_id, state="queued", attempts=0, next_attempt_at=now,
                    held_reason=f"summary:{len(rows)}", created_at=now,
                )
                self.repo.add_delivery(summary)
                self.repo.mark_summarised([r.id for r in rows], summary.id, now)
            tried = 0
            for d in self.repo.due_deliveries(now):
                n = self.repo.get_notification(d.notification_id)
                if self._drop_muted(d, n):
                    continue
                if n is not None and self._fold_outage(d, n, now):
                    continue
                tried += 1
                self._deliver(d, n, now)
            if self._last_prune is None or (now - self._last_prune).total_seconds() >= 3600:
                self.repo.prune(now)
                self._last_prune = now
            return tried

    def _fold_outage(self, d: DeliveryRow, n: NotificationRow, now: datetime) -> bool:
        if d.attempts or (d.held_reason or "").startswith("summary:") or not n.group_key or not n.alert_id:
            return False
        alert = self.repo.get_alert(n.alert_id)
        if alert is None or alert.type != "app.unhealthy" or alert.source_id != "gateway:monitoring":
            return False
        outage = self.repo.open_alert(n.group_key)
        if outage is None or outage.type != "node.offline":
            return False
        since = utc(outage.opened_at) - OUTAGE_GROUP_WINDOW
        created = utc(n.created_at)
        if created < since:
            return False
        # Only a successful send to this person and destination can cover a child.
        # App-only recipients can be covered by an app warning in the same outage.
        covering = self.repo.sent_outage_delivery(
            d, n.group_key, since, (created - OUTAGE_GROUP_WINDOW, created + OUTAGE_GROUP_WINDOW),
            SEVERITIES[RANK[n.severity]:],
        )
        if covering is None:
            return False
        self.repo.mark_summarised([d.id], covering, now)
        return True

    def _message(self, n: NotificationRow, count: int) -> Message:
        title, body = n.title, n.body
        if count > 1:
            title, body = f"{count} notifications", f"Latest: {n.title}"
        link = None
        if n.link:
            link = n.link if n.link.startswith("http") else self.base_url + n.link
        return Message(id=n.id, severity=n.severity, topic=n.topic, title=title, body=body, link=link,
                       created_at=iso(n.created_at) or "", box_id=self.box_id, count=count)

    def _send_to(self, target_id: str, msg: Message, kind: str = "delivery"):
        """Send now; the provider receipt (sms) or None. Raises Capped before any byte goes out."""
        now = self.clock()
        now_s = int(now.timestamp())
        if target_id.startswith("chn_"):
            ch = self.repo.get_channel(target_id)
            if ch is None:
                raise LookupError("channel deleted")
            cfg = json.loads(ch.config_json)
            cap = cfg.get("daily_cap")
            if cap is not None:  # count the attempt before it goes out: a timeout may still be billed
                with self._cap_lock:
                    if not self.repo.claim_send(ch.id, kind, now - timedelta(hours=24), cap, now, new_id("snd")):
                        raise Capped(cap)
            secret = self.box.open(ch.secret_enc, ch.id) if ch.secret_enc else None
            return send_channel(ch.kind, cfg, secret, ch.content_level, msg, timeout=self.cfg.http_timeout_s,
                                lan_ok=bool(cfg.get("lan")), now_s=now_s)
        dev = self.repo.get_device(target_id)
        if dev is None:
            raise LookupError("device removed")
        endpoint = self.box.open(dev.endpoint_enc, dev.id)
        sealed = json.loads(self.box.open(dev.keys_enc, dev.id)) if dev.keys_enc else {}
        keys = sealed.get("keys")
        send_push(endpoint, keys, self.vapid, self.cfg.vapid_subject, msg, timeout=self.cfg.http_timeout_s,
                  lan_ok=bool(sealed.get("lan")), now_s=now_s)
        return None

    def _deliver(self, d: DeliveryRow, n: NotificationRow | None, now: datetime) -> None:
        count = int(d.held_reason.split(":", 1)[1]) if d.held_reason and d.held_reason.startswith("summary:") else 1
        try:
            if n is None:
                raise LookupError("notification pruned")
            self._send_to(d.target_id, self._message(n, count))
        except LookupError as exc:
            d.state, d.last_error = "dead", str(exc)
            self.repo.save_delivery(d)
            return
        except Capped as exc:  # a ledger entry, no send, never retried
            d.state, d.next_attempt_at, d.last_error = "dropped", None, str(exc)
            self.repo.save_delivery(d)
            self.gw.events.publish_event(
                "notify", "delivery.dropped",
                {"delivery_id": d.id, "notification_id": d.notification_id, "channel_id": d.target_id,
                 "reason": "daily_cap", "cap": exc.cap},
                severity="warning", resource={"kind": "notification", "id": d.notification_id})
            return
        except DeliveryError as exc:
            d.attempts += 1
            d.last_error = str(exc)[:300]
            if d.attempts > len(BACKOFF_S):
                d.state, d.next_attempt_at = "dead", None
            else:
                d.state, d.next_attempt_at = "failed", now + timedelta(seconds=BACKOFF_S[d.attempts - 1])
            self.repo.save_delivery(d)
            self._target_failed(d.target_id, d.person_id, d.last_error, now)
            return
        except Exception as exc:  # a bug in a sender must not kill the worker
            log.exception("sender crashed")
            d.attempts += 1
            d.last_error = f"internal error ({exc.__class__.__name__})"
            if d.attempts > len(BACKOFF_S):  # same schedule as a failed send, then dead
                d.state, d.next_attempt_at = "dead", None
            else:
                d.state, d.next_attempt_at = "failed", now + timedelta(seconds=BACKOFF_S[d.attempts - 1])
            self.repo.save_delivery(d)
            return
        d.state, d.sent_at, d.attempts, d.last_error, d.next_attempt_at = "sent", now, d.attempts + 1, None, None
        self.repo.save_delivery(d)
        self._target_ok(d.target_id)

    def _target_failed(self, target_id: str, person_id: str, error: str, now: datetime) -> None:
        row = self.repo.get_channel(target_id) if target_id.startswith("chn_") else self.repo.get_device(target_id)
        if row is None:
            return
        row.state = "failing"
        row.failing_since = row.failing_since or now
        if isinstance(row, ChannelRow):
            row.last_error, row.updated_at = error, now
            self.repo.save_channel(row)
        else:
            self.repo.save_device(row)
        if (now - utc(row.failing_since)).total_seconds() >= FAILING_ALERT_AFTER_S:
            label = row.label
            self.ingest(catalogue.lookup("notify.channel_failing"),
                        {"channel_id": target_id, "label": label, "reason": error, "person_id": person_id})

    def _target_ok(self, target_id: str) -> None:
        row = self.repo.get_channel(target_id) if target_id.startswith("chn_") else self.repo.get_device(target_id)
        if row is None or (row.state == "ok" and row.failing_since is None):
            return
        row.state, row.failing_since = "ok", None
        if isinstance(row, ChannelRow):
            row.last_error = None
            self.repo.save_channel(row)
        else:
            self.repo.save_device(row)
        self.resolve_key(f"channel:{target_id}")

    def test_target(self, target_id: str, person_id: str) -> dict:
        """Send a test message now (POST …/channels/{id}/test); marks the channel verified."""
        now = self.clock()
        msg = Message(id=new_id("ntf"), severity="info", topic="security", title="Test from OneMind",
                      body="If you can read this, the channel works.", link=None, created_at=iso(now) or "",
                      box_id=self.box_id)
        start = time.monotonic()
        try:
            receipt = self._send_to(target_id, msg, kind="test")
        except (DeliveryError, LookupError) as exc:
            return {"delivered": False, "latency_ms": int((time.monotonic() - start) * 1000), "error": str(exc)[:300]}
        latency = int((time.monotonic() - start) * 1000)
        ch = self.repo.get_channel(target_id)
        if ch is not None:
            ch.verified, ch.updated_at = True, now
            self.repo.save_channel(ch)
        self._target_ok(target_id)
        out = {"delivered": True, "latency_ms": latency}
        if receipt is not None:
            out["receipt"] = receipt.as_json()
        return out

    # ---- POST /v1/notifications/send and built-in app posts (topics.py) ---------------------
    def post(self, principal: Principal, *, topic: str, severity: str, title: str, body: str = "",
             link: str | None = None, asset_id: str | None = None, group_key: str | None = None,
             actions: list[dict] | None = None, dedupe_key: str | None = None) -> dict:
        """A notice from a built-in app, a plugin or an agent to the owners (contract §12.14, #613).

        Returns {queued, deduplicated, muted}. Raises PermissionError (403), ValueError (422) or RateLimited."""
        source_id, source_kind, app_id = self._source_of(principal, topic)
        if len(topic) > topics.MAX_TOPIC:
            raise ValueError(f"topic is longer than {topics.MAX_TOPIC} characters")
        if severity not in topics.SOURCE_SEVERITIES:
            raise ValueError("severity must be info or warning (critical is reserved for the system)")
        if asset_id is not None and not topics.ASSET_ID_RE.match(asset_id):
            raise ValueError("asset_id must be an asset id (letters, digits, _ and -, up to 128)")
        if group_key is not None and not topics.GROUP_KEY_RE.match(group_key):
            raise ValueError("group_key must be letters, digits and _ . : - (up to 200)")
        if link is not None and (not link.startswith("/") or link.startswith("//") or len(link) > 300):
            raise ValueError("link must be an in-app path starting with /")
        acts = topics.check_actions(actions, self._known_action_type)
        now = self.clock()
        with self._lock:
            posts = self._count(source_id, now)
            row = self.repo.get_source(source_id)
            if row is not None and row.muted:
                return {"queued": 0, "deduplicated": False, "muted": True}
            if posts > topics.FLOOD_POSTS:
                self._auto_mute(source_id, app_id, posts)
                return {"queued": 0, "deduplicated": False, "muted": True}
        q = self._sends[principal.id]
        while q and (now - q[0]).total_seconds() >= 60:
            q.popleft()
        if len(q) >= self.cfg.send_per_min:
            raise RateLimited(max(1, int(60 - (now - q[0]).total_seconds())))
        q.append(now)
        if dedupe_key:
            k = (principal.id, dedupe_key)
            last = self._send_dedupe.get(k)
            if last is not None and (now - last).total_seconds() < self.cfg.renotify_s:
                return {"queued": 0, "deduplicated": True, "muted": False}
            self._send_dedupe[k] = now
        people = self._recipients({"roles": ["owner"], "persons": []})
        with self._lock:
            ids = self._fanout(people, severity=severity, topic=topic, title=title, body=body, link=link,
                               source=principal.id, action_id=None, alert_id=None, inapp_only=False,
                               source_kind=source_kind, app_id=app_id, asset_id=asset_id,
                               group_key=group_key, actions=acts)
        return {"queued": len(ids), "deduplicated": False, "muted": False}

    def _source_of(self, p: Principal, topic: str) -> tuple[str, str, str | None]:
        """(source id, source kind, app id for the chip) of a poster, or PermissionError."""
        if isinstance(p, AppPrincipal):
            if self.topics.get(p.app_id, topic) is None:
                raise PermissionError(f"a built-in posts only under a topic its descriptor declares "
                                      f"(app.{p.app_id}.<topic>) while it is switched on")
            return f"app:{p.app_id}", "app", p.app_id
        if p.kind != "agent":
            raise PermissionError("only built-in apps, agents and plugins send notifications")
        own = p.id.split(":", 1)[-1]
        if topic != f"{topics.PLUGIN_TOPIC_PREFIX}{own}":
            raise PermissionError(f"an agent sends only under its own topic plugin.{own}")
        if self.gw.repo.get_app_state(own) is not None:  # an installed app's agent: its plugin chip
            return f"plugin:{own}", "plugin", own
        return f"plugin:{own}", "agent", None

    def _known_action_type(self, action_type: str) -> bool:
        from ..actions import APP_CLAIMS
        return action_type in self.gw.actions.feature_types or action_type in APP_CLAIMS

    def _count(self, source_id: str, now: datetime) -> int:
        """Record one post attempt; return the attempts in the last FLOOD_WINDOW_S (the rate meter keeps 1 h)."""
        q = self._meter[source_id]
        while q and (now - q[0]).total_seconds() >= 3600:
            q.popleft()
        q.append(now)
        return sum(1 for t in q if (now - t).total_seconds() < topics.FLOOD_WINDOW_S)

    def _auto_mute(self, source_id: str, app_id: str | None, posts: int) -> None:
        """Mute a flooding source and tell the owners once (os-completeness N7)."""
        self.set_muted(source_id, True, by=None, reason="flood")
        label = (self.topics.name(app_id) if app_id else None) or source_id.split(":", 1)[1]
        self.gw.events.publish_event("notify", "source.muted", {"source_id": source_id, "reason": "flood", "posts": posts})
        self._fanout(
            self._recipients({"roles": ["owner"], "persons": []}), severity="warning", topic="apps",
            title=f"{label} was muted: too many notifications",
            body=f"It sent {posts} notifications in {topics.FLOOD_WINDOW_S // 60} minutes. "
                 "Unmute it in Settings > Notifications > App notifications.",
            link="/settings/notifications", source="gateway", action_id=None, alert_id=None,
            inapp_only=False, source_kind="system", app_id=app_id,
        )

    def set_muted(self, source_id: str, muted: bool, by: str | None, reason: str) -> SourceRow:
        with self._lock:
            now = self.clock()
            row = self.repo.get_source(source_id) or SourceRow(source_id=source_id, muted=False, updated_at=now)
            row.muted, row.updated_at = muted, now
            row.reason, row.muted_by, row.muted_at = (reason, by, now) if muted else (None, None, None)
            self.repo.save_source(row)
            if not muted:
                self._meter.pop(source_id, None)  # a fresh start: the old burst no longer counts
            return row

    def sources(self) -> list[dict]:
        """Every source the owner can mute: switched-on built-ins with topics, plus any that posted or has a row."""
        now = self.clock()
        with self._lock:
            rows = {r.source_id: r for r in self.repo.list_sources()}
            meter = {k: sum(1 for t in q if (now - t).total_seconds() < 3600) for k, q in self._meter.items()}
        declared: dict[str, list[dict]] = defaultdict(list)
        for t in self.topics.topics():
            declared[f"app:{t.app_id}"].append({"id": t.id, "topic": t.topic, "title": t.title})
        out = []
        for sid in sorted(set(declared) | set(rows) | set(meter)):
            kind, own = sid.split(":", 1)
            r = rows.get(sid)
            out.append({
                "id": sid, "kind": kind, "app_id": own if kind == "app" else None,
                "name": (self.topics.name(own) if kind == "app" else None) or own,
                "topics": declared.get(sid) or ([] if kind == "app" else
                                                [{"id": own, "topic": f"{topics.PLUGIN_TOPIC_PREFIX}{own}", "title": None}]),
                "muted": bool(r and r.muted), "muted_reason": r.reason if r else None,
                "muted_by": r.muted_by if r else None, "muted_at": iso(r.muted_at) if r else None,
                "posts_last_hour": meter.get(sid, 0),
            })
        return out


class Capped(DeliveryError):
    """The channel's daily cap is reached: drop, do not send (issue #869)."""

    def __init__(self, cap: int):
        super().__init__(f"daily cap reached ({cap} per day)")
        self.cap = cap


class RateLimited(Exception):
    def __init__(self, retry_after_s: int):
        super().__init__("rate limited")
        self.retry_after_s = retry_after_s


def _subject(data: dict) -> dict:
    keys = ("action_id", "node_id", "app_id", "alert_id", "rule_id", "job_id", "channel_id")
    return {k: data[k] for k in keys if isinstance(data.get(k), str)}
