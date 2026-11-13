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
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from ..audit import AUDIT_SUBJECT
from ..auth import Principal
from ..ledger import iso, utc
from ..sections import config_section
from . import catalogue, routing
from .catalogue import RANK, SEVERITIES, Spec
from .channels import (
    DeliveryError, Message, send_channel, send_push,
)
from .crypto import SecretBox, Vapid
from .ids import new_id
from .store import AlertRow, ChannelRow, DeliveryRow, NotificationRow, NotifyRepository

log = logging.getLogger("onemind.notify")

BACKOFF_S = (30, 120, 600, 3600, 6 * 3600)
FAILING_ALERT_AFTER_S = 3600
FLAP_WINDOW_S = 600
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
        self._kick = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._nats_task: asyncio.Task | None = None
        self._sends: dict[str, deque] = defaultdict(deque)
        self._send_dedupe: dict[tuple[str, str], datetime] = {}
        self._last_prune: datetime | None = None

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
        self.ingest(spec, data, source=envelope.get("source_id") or "gateway")

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
    def ingest(self, spec: Spec, data: dict, source: str = "gateway") -> None:
        with self._lock:
            for tpl in spec.resolves:
                key = catalogue.render(tpl, data)
                if "?" not in key:
                    self.resolve_key(key)
            if spec.kind == "open":
                self._open(spec, data, source)
            elif spec.kind in ("notify", "inbox"):
                self._fanout(
                    self._recipients(self._audience(spec, data)), severity=self._severity(spec, data),
                    topic=catalogue.topic_for(spec, data), title=catalogue.render(spec.title, data),
                    body=catalogue.render(spec.body, data), link=self._link(spec, data), source=source,
                    action_id=data.get("action_id"), alert_id=None, inapp_only=spec.kind == "inbox",
                )

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
        self._fanout(
            self._recipients(audience), severity=row.severity, topic=row.topic, title=row.title,
            body=row.body, link=row.link, source=row.source_id, action_id=data.get("action_id"),
            alert_id=row.id, inapp_only=row.type in catalogue.INAPP_ONLY_ALERTS,
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
                action_id=None, alert_id=row.id, inapp_only=False,
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

    def _fanout(self, people: list[str], *, severity: str, topic: str, title: str, body: str,
                link: str | None, source: str, action_id: str | None, alert_id: str | None,
                inapp_only: bool) -> list[str]:
        now = self.clock()
        created = []
        for pid in people:
            nid = new_id("ntf")
            row = NotificationRow(
                id=nid, person_id=pid, severity=severity, topic=topic, title=title[:MAX_TITLE],
                body=body[:MAX_BODY], link=link, source=source[:120], action_id=action_id,
                alert_id=alert_id, created_at=now,
            )
            deliveries = []
            if not inapp_only:
                doc, _ = self.preferences(pid)
                held = routing.hold(doc, topic, severity, now)
                for target in routing.targets(doc, topic, severity, self._targets_of(pid)):
                    d = DeliveryRow(id=new_id("dlv"), notification_id=nid, person_id=pid, target_id=target,
                                    state="queued", attempts=0, next_attempt_at=now, created_at=now)
                    window_start = now - timedelta(hours=1)
                    if self.repo.sent_count(target, window_start) >= self.cfg.channel_per_hour:
                        oldest = self.repo.oldest_in_window(target, window_start) or now
                        d.state, d.held_reason = "held", "rate"
                        d.release_at, d.next_attempt_at = oldest + timedelta(hours=1), None
                    elif held is not None:
                        d.state, d.held_reason, d.release_at, d.next_attempt_at = "held", held[0], held[1], None
                    deliveries.append(d)
            self.repo.add_notification(row, deliveries)
            self.gw.events.publish_event(
                "notification", "created", {"notification_id": nid}, severity=severity,
                resource={"kind": "notification", "id": nid},
            )
            created.append(nid)
        self._kick.set()
        return created

    # ---- delivery -----------------------------------------------------------------------
    def pump(self) -> int:
        """One worker pass: release held items as summaries, send what is due. Returns sends tried."""
        with self._pump_lock:
            now = self.clock()
            groups: dict[str, list[DeliveryRow]] = defaultdict(list)
            for d in self.repo.released_held(now):
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
                tried += 1
                self._deliver(d, now)
            if self._last_prune is None or (now - self._last_prune).total_seconds() >= 3600:
                self.repo.prune(now)
                self._last_prune = now
            return tried

    def _message(self, n: NotificationRow, count: int) -> Message:
        title, body = n.title, n.body
        if count > 1:
            title, body = f"{count} notifications", f"Latest: {n.title}"
        link = None
        if n.link:
            link = n.link if n.link.startswith("http") else self.base_url + n.link
        return Message(id=n.id, severity=n.severity, topic=n.topic, title=title, body=body, link=link,
                       created_at=iso(n.created_at) or "", box_id=self.box_id, count=count)

    def _send_to(self, target_id: str, msg: Message) -> None:
        now_s = int(self.clock().timestamp())
        if target_id.startswith("chn_"):
            ch = self.repo.get_channel(target_id)
            if ch is None:
                raise LookupError("channel deleted")
            cfg = json.loads(ch.config_json)
            secret = self.box.open(ch.secret_enc, ch.id) if ch.secret_enc else None
            send_channel(ch.kind, cfg, secret, ch.content_level, msg, timeout=self.cfg.http_timeout_s,
                         lan_ok=bool(cfg.get("lan")), now_s=now_s)
            return
        dev = self.repo.get_device(target_id)
        if dev is None:
            raise LookupError("device removed")
        endpoint = self.box.open(dev.endpoint_enc, dev.id)
        sealed = json.loads(self.box.open(dev.keys_enc, dev.id)) if dev.keys_enc else {}
        keys = sealed.get("keys")
        send_push(endpoint, keys, self.vapid, self.cfg.vapid_subject, msg, timeout=self.cfg.http_timeout_s,
                  lan_ok=bool(sealed.get("lan")), now_s=now_s)

    def _deliver(self, d: DeliveryRow, now: datetime) -> None:
        n = self.repo.get_notification(d.notification_id)
        count = int(d.held_reason.split(":", 1)[1]) if d.held_reason and d.held_reason.startswith("summary:") else 1
        try:
            if n is None:
                raise LookupError("notification pruned")
            self._send_to(d.target_id, self._message(n, count))
        except LookupError as exc:
            d.state, d.last_error = "dead", str(exc)
            self.repo.save_delivery(d)
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
            self._send_to(target_id, msg)
        except (DeliveryError, LookupError) as exc:
            return {"delivered": False, "latency_ms": int((time.monotonic() - start) * 1000), "error": str(exc)[:300]}
        latency = int((time.monotonic() - start) * 1000)
        ch = self.repo.get_channel(target_id)
        if ch is not None:
            ch.verified, ch.updated_at = True, now
            self.repo.save_channel(ch)
        self._target_ok(target_id)
        return {"delivered": True, "latency_ms": latency}

    # ---- POST /v1/notifications/send -----------------------------------------------------
    def send_from(self, principal: Principal, severity: str, topic: str, title: str, body: str,
                  dedupe_key: str | None) -> dict:
        """An agent's own notice to the owners (contract §12.14). Returns {queued, deduplicated}.

        Raises PermissionError (403), ValueError (422) or RateLimited."""
        if principal.kind != "agent":
            raise PermissionError("only agents, plugins and automations send notifications")
        own = principal.id.split(":", 1)[-1]
        if topic != f"plugin.{own}":
            raise PermissionError(f"an agent sends only under its own topic plugin.{own}")
        if severity not in ("info", "warning"):
            raise ValueError("severity must be info or warning (critical is reserved for the system)")
        now = self.clock()
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
                return {"queued": 0, "deduplicated": True}
            self._send_dedupe[k] = now
        people = self._recipients({"roles": ["owner"], "persons": []})
        with self._lock:
            ids = self._fanout(people, severity=severity, topic=topic, title=title, body=body, link=None,
                               source=principal.id, action_id=None, alert_id=None, inapp_only=False)
        return {"queued": len(ids), "deduplicated": False}


class RateLimited(Exception):
    def __init__(self, retry_after_s: int):
        super().__init__("rate limited")
        self.retry_after_s = retry_after_s


def _subject(data: dict) -> dict:
    keys = ("action_id", "node_id", "app_id", "alert_id", "rule_id", "job_id", "channel_id")
    return {k: data[k] for k in keys if isinstance(data.get(k), str)}
