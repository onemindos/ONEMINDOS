# SPDX-License-Identifier: Apache-2.0
"""App topics and notification sources (#613; os-completeness N1 and N7).

Topic tree (catalogue.py has the fixed system part):
- system topics (`approvals`, `backups`, ...): catalogue events the gateway raises itself;
- `app.<app_id>.<topic_id>`: what a built-in app posts through its app principal
  (builtins.AppPrincipal). The topic must be declared in the app's descriptor
  (`spec.notifications.topics[].id`) and the app must be switched on;
- `plugin.<id>`: what an agent or an installed app's agent posts (`POST /v1/notifications/send`).

A source is who posts outside the catalogue: `app:<app_id>` for a built-in, `plugin:<id>` for an
agent's or installed app's `plugin.<id>` topic. The owner can mute a source; a source that posts
more than FLOOD_POSTS times in FLOOD_WINDOW_S is muted by the gateway, and the owners get one note.
System sources (the catalogue) are never muted here: approvals and security alerts always arrive.

Each inbox item says where it came from (the app chip): `source_kind` (SOURCE_KINDS) and `app_id`,
plus an optional `asset_id` (a map asset, subjects `id` placeholder), `group_key` and `actions`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

APP_TOPIC_PREFIX = "app."
PLUGIN_TOPIC_PREFIX = "plugin."
SOURCE_KINDS = ("system", "node", "app", "plugin", "agent")
SOURCE_ID_RE = re.compile(r"^(app|plugin):[a-z0-9][a-z0-9_.-]{0,62}$")
ASSET_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")  # sdk/schema/onemind.subjects.json `id`
GROUP_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
ACTION_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
ACTION_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
MAX_ACTIONS = 3
MAX_TOPIC = 80  # notify_notifications.topic
FLOOD_POSTS = 60
FLOOD_WINDOW_S = 600
# Severity ceiling for every non-system source: critical is reserved for the system (contract §12.14).
SOURCE_SEVERITIES = ("info", "warning")


def app_topic(app_id: str, topic_id: str) -> str:
    return f"{APP_TOPIC_PREFIX}{app_id}.{topic_id}"


@dataclass(frozen=True)
class AppTopic:
    app_id: str
    id: str              # the descriptor's topic id
    title: str | None
    events: tuple[str, ...]

    @property
    def topic(self) -> str:
        return app_topic(self.app_id, self.id)


class TopicRegistry:
    """The topics of the switched-on built-ins, read live from the descriptor registry (builtins.Builtins)."""

    def __init__(self, builtins=None):
        self.builtins = builtins

    def _enabled(self) -> list:
        return self.builtins.enabled() if self.builtins is not None else []

    def topics(self) -> list[AppTopic]:
        return [AppTopic(d.id, t["id"], t.get("title"), tuple(t.get("events", ())))
                for d in self._enabled() for t in (d.spec.get("notifications") or {}).get("topics", [])]

    def get(self, app_id: str, topic: str) -> AppTopic | None:
        """The declared topic `topic` (full `app.<app_id>.<id>` name) of a switched-on built-in."""
        return next((t for t in self.topics() if t.app_id == app_id and t.topic == topic), None)

    def app_for_event(self, event_type: str) -> str | None:
        """The built-in whose descriptor routes this catalogue event (its chip on a system notification)."""
        return next((t.app_id for t in self.topics() if event_type in t.events), None)

    def name(self, app_id: str) -> str | None:
        d = (self.builtins.descriptors if self.builtins is not None else {}).get(app_id)
        return d.name if d is not None else None


def check_actions(actions: list[dict] | None, known_type: Callable[[str], bool]) -> list[dict]:
    """Validate notification action buttons; ValueError on anything else.

    `open` follows an in-app link; `request` lets the person who taps it file a normal action
    request, which still waits for an approval. There is no approve button (AI can ask, only a
    person approves, and an approval needs the approval sheet, never a notification).
    """
    out: list[dict] = []
    for a in actions or []:
        if not isinstance(a, dict) or not ACTION_ID_RE.match(str(a.get("id", ""))):
            raise ValueError("each action needs an id (lowercase, up to 32 characters)")
        label = a.get("label")
        if not isinstance(label, str) or not 1 <= len(label) <= 40:
            raise ValueError("each action needs a label of 1 to 40 characters")
        kind = a.get("kind")
        if kind == "open":
            link = a.get("link")
            if set(a) != {"id", "label", "kind", "link"} or not isinstance(link, str) \
                    or not link.startswith("/") or link.startswith("//") or len(link) > 300:
                raise ValueError("an open action has exactly id, label, kind and an in-app link starting with /")
            out.append({"id": a["id"], "label": label, "kind": kind, "link": link})
        elif kind == "request":
            req = a.get("request")
            if set(a) != {"id", "label", "kind", "request"} or not isinstance(req, dict) \
                    or set(req) - {"type", "params"} or not isinstance(req.get("params", {}), dict) \
                    or not isinstance(req.get("type"), str) or not ACTION_TYPE_RE.match(req["type"]) \
                    or not known_type(req["type"]):
                raise ValueError("a request action has exactly id, label, kind and request {type, params} "
                                 "naming a registered action type")
            out.append({"id": a["id"], "label": label, "kind": kind,
                        "request": {"type": req["type"], "params": dict(req.get("params", {}))}})
        else:
            raise ValueError("action kind must be open or request")
    if len(out) > MAX_ACTIONS or len({a["id"] for a in out}) != len(out):
        raise ValueError(f"at most {MAX_ACTIONS} actions, each with its own id")
    return out
