# SPDX-License-Identifier: Apache-2.0
"""Internal event hook: publish_event(domain, name, payload) (docs/leap/core/PLUMBING.md §5).

One call does three things, in this order:

1. appends `<domain>.<name>` to the hash-chained audit log (the record of truth; it is also
   published on NATS `onemind.audit` as every audit line is);
2. publishes the `onemind.event.v1` envelope (contract §12.3 draft) on NATS
   `onemind.event.<domain>.<name>` (best effort: NATS down never fails the caller);
3. calls in-process subscribers whose pattern matches (notifications and monitoring use this).

The payload carries ids and small facts only, never secrets or file contents: it lands in the
audit log, which is kept for a year and shipped to backups.
"""

from __future__ import annotations

import logging
import re
import threading
import uuid
from collections.abc import Callable
from datetime import datetime

from .audit import AuditLog, canonical_json

log = logging.getLogger("onemind.events")

EVENT_SCHEMA = "onemind.event.v1"
SUBJECT_PREFIX = "onemind.event."
SEVERITIES = ("critical", "error", "warning", "info", "debug")
MAX_PAYLOAD_BYTES = 16 * 1024
TOKEN = r"[a-z][a-z0-9_]{0,39}"
DOMAIN_RE = re.compile(rf"^{TOKEN}$")
NAME_RE = re.compile(rf"^{TOKEN}(\.{TOKEN}){{0,3}}$")
PATTERN_TOKEN_RE = re.compile(rf"^({TOKEN}|\*|>)$")

Handler = Callable[[dict], None]


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def matches(pattern: str, event_type: str) -> bool:
    """NATS-style match on the event type: `*` is one token, a final `>` is one or more."""
    p, t = pattern.split("."), event_type.split(".")
    for i, tok in enumerate(p):
        if tok == ">":
            return i == len(p) - 1 and len(t) > i
        if i >= len(t) or (tok != "*" and tok != t[i]):
            return False
    return len(p) == len(t)


class EventHub:
    def __init__(
        self,
        audit: AuditLog,
        clock: Callable[[], datetime],
        publish: Callable[[str, bytes], None] | None = None,
        instance_id: str | None = None,
    ):
        self.audit = audit
        self.clock = clock
        self.publish = publish
        self.instance_id = instance_id
        self._lock = threading.Lock()
        self._subs: list[tuple[str, Handler]] = []

    def subscribe(self, pattern: str, handler: Handler) -> Callable[[], None]:
        """Call handler(envelope) for each event whose type matches; returns an unsubscribe function.

        Handlers run synchronously in the publisher's thread: keep them quick and hand slow work
        (sending a push, an email) to a queue or task. A handler that raises is logged and skipped.
        """
        if not all(PATTERN_TOKEN_RE.match(t) for t in pattern.split(".")) or ">" in pattern.split(".")[:-1]:
            raise ValueError(f"bad event pattern {pattern!r}")
        entry = (pattern, handler)
        with self._lock:
            self._subs.append(entry)

        def unsubscribe() -> None:
            with self._lock:
                if entry in self._subs:
                    self._subs.remove(entry)

        return unsubscribe

    def publish_event(
        self,
        domain: str,
        name: str,
        payload: dict | None = None,
        *,
        principal: dict | None = None,
        action_id: str | None = None,
        severity: str = "info",
        resource: dict | None = None,
        dedupe_key: str | None = None,
        source_id: str = "gateway",
        causation_id: str | None = None,
    ) -> dict:
        """Record and fan out one event. Returns the envelope. Raises ValueError on bad input."""
        if not DOMAIN_RE.match(domain):
            raise ValueError(f"event domain {domain!r} must match {DOMAIN_RE.pattern}")
        if not NAME_RE.match(name):
            raise ValueError(f"event name {name!r} must match {NAME_RE.pattern}")
        if severity not in SEVERITIES:
            raise ValueError(f"severity must be one of {SEVERITIES}")
        payload = payload or {}
        try:
            size = len(canonical_json(payload).encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"event payload is not JSON: {exc}") from None
        if size > MAX_PAYLOAD_BYTES:
            raise ValueError(f"event payload is {size} bytes; the limit is {MAX_PAYLOAD_BYTES}")
        event_type = f"{domain}.{name}"
        event_id = "evt_" + uuid.uuid4().hex
        now = _iso(self.clock())
        audit_data = {"event_id": event_id, "severity": severity, "payload": payload}
        if resource is not None:
            audit_data["resource"] = resource
        if dedupe_key is not None:
            audit_data["dedupe_key"] = dedupe_key
        self.audit.append(event_type, principal, action_id, audit_data)  # durable first
        envelope = {
            "schema": EVENT_SCHEMA,
            "id": event_id,
            "type": event_type,
            "instance_id": self.instance_id,
            "site_id": None,
            "source_id": source_id,
            "actor_id": (principal or {}).get("id"),
            "occurred_at": now,
            "observed_at": now,
            "correlation_id": action_id,
            "causation_id": causation_id,
            "resource": resource,
            "severity": severity,
            "dedupe_key": dedupe_key,
            "data": payload,
        }
        if self.publish is not None:
            try:
                self.publish(SUBJECT_PREFIX + event_type, canonical_json(envelope).encode("utf-8"))
            except Exception:  # the audit line is the record of truth; the bus is best effort
                log.exception("event publish failed for %s", event_type)
        with self._lock:
            subs = [h for p, h in self._subs if matches(p, event_type)]
        for handler in subs:
            try:
                handler(envelope)
            except Exception:
                log.exception("event subscriber %r failed on %s", handler, event_type)
        return envelope
