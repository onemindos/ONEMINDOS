# SPDX-License-Identifier: Apache-2.0
"""Per-person routing (contract §12.14 "Preferences"): which channels, quiet hours, digest.

```json
{"quiet_hours": {"tz": "Europe/Berlin", "from": "22:30", "to": "07:00",
                 "except_severity": ["critical"], "except_topics": ["approvals"]},
 "routes": [{"match": {"topic": "approvals.*"}, "channels": ["chn_phone"]},
            {"match": {"severity": "critical"}, "channels": ["chn_phone", "chn_email"]}],
 "digest": {"enabled": true, "at": "08:00"}}
```

- Every matching route adds its channels (union). `"*"` means all of the person's channels and
  devices. A match may use `topic` (`x.*` also matches `x`), `severity` (one or a list) and
  `severity_at_least`. The in-app inbox always gets the item; routes pick the extra channels.
- A person without a document gets DEFAULT: warning and above, and every approval, to all of
  their channels and devices (DECISIONS-NEEDED §5 N-1).
- Quiet hours hold what does not match `except_*`; held items go out as one summary per channel
  when quiet hours end. With a digest, `info` items (approvals excepted) wait for the daily
  digest time. Both use the quiet-hours time zone (UTC when there is none).
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .catalogue import RANK, SEVERITIES, TOPICS

HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
TOPIC_RE = re.compile(r"^(?:(?:%s)(?:\.\*)?|plugin(?:\.[a-z0-9][a-z0-9-]{0,58})?(?:\.\*)?)$" % "|".join(TOPICS))
TARGET_RE = re.compile(r"^(\*|(chn|dev)_[0-9A-Z]{26})$")
MAX_ROUTES = 50

DEFAULT: dict = {
    "quiet_hours": None,
    "routes": [
        {"match": {"severity_at_least": "warning"}, "channels": ["*"]},
        {"match": {"topic": "approvals"}, "channels": ["*"]},
    ],
    "digest": {"enabled": False, "at": "08:00"},
}


def etag(doc: dict) -> str:
    return '"' + hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()[:32] + '"'


def _severity_list(value, where: str) -> list[str]:
    vals = [value] if isinstance(value, str) else value
    if not isinstance(vals, list) or not vals or any(v not in SEVERITIES for v in vals):
        raise ValueError(f"{where} must be one of {SEVERITIES} or a list of them")
    return list(vals)


def _hhmm(value, where: str) -> str:
    if not isinstance(value, str) or not HHMM.match(value):
        raise ValueError(f"{where} must be HH:MM")
    return value


def _tz(name, where: str) -> str:
    if not isinstance(name, str):
        raise ValueError(f"{where} must be an IANA time zone name")
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"{where}: unknown time zone {name!r}") from None
    return name


def validate(doc: object) -> dict:
    """The normalised document, or ValueError naming the bad field."""
    if not isinstance(doc, dict):
        raise ValueError("preferences must be a JSON object")
    unknown = set(doc) - {"quiet_hours", "routes", "digest"}
    if unknown:
        raise ValueError(f"unknown preference fields: {sorted(unknown)}")
    out: dict = {"quiet_hours": None, "routes": [], "digest": {"enabled": False, "at": "08:00"}}
    qh = doc.get("quiet_hours")
    if qh is not None:
        if not isinstance(qh, dict):
            raise ValueError("quiet_hours must be an object or null")
        out["quiet_hours"] = {
            "tz": _tz(qh.get("tz", "UTC"), "quiet_hours.tz"),
            "from": _hhmm(qh.get("from"), "quiet_hours.from"),
            "to": _hhmm(qh.get("to"), "quiet_hours.to"),
            "except_severity": [] if qh.get("except_severity", ["critical"]) == [] else
            _severity_list(qh.get("except_severity", ["critical"]), "quiet_hours.except_severity"),
            "except_topics": _topics(qh.get("except_topics", ["approvals"]), "quiet_hours.except_topics"),
        }
    routes = doc.get("routes", [])
    if not isinstance(routes, list) or len(routes) > MAX_ROUTES:
        raise ValueError(f"routes must be a list of at most {MAX_ROUTES}")
    for i, r in enumerate(routes):
        if not isinstance(r, dict) or not isinstance(r.get("match", {}), dict):
            raise ValueError(f"routes[{i}] must be {{match, channels}}")
        m = r.get("match", {})
        bad = set(m) - {"topic", "severity", "severity_at_least"}
        if bad:
            raise ValueError(f"routes[{i}].match: unknown keys {sorted(bad)}")
        match: dict = {}
        if "topic" in m:
            match["topic"] = _topics([m["topic"]], f"routes[{i}].match.topic")[0]
        if "severity" in m:
            match["severity"] = _severity_list(m["severity"], f"routes[{i}].match.severity")
        if "severity_at_least" in m:
            match["severity_at_least"] = _severity_list(m["severity_at_least"], f"routes[{i}].match.severity_at_least")[0]
        chans = r.get("channels")
        if not isinstance(chans, list) or not all(isinstance(c, str) and TARGET_RE.match(c) for c in chans):
            raise ValueError(f"routes[{i}].channels must be a list of chn_/dev_ ids or \"*\"")
        out["routes"].append({"match": match, "channels": list(dict.fromkeys(chans))})
    dg = doc.get("digest")
    if dg is not None:
        if not isinstance(dg, dict) or not isinstance(dg.get("enabled", False), bool):
            raise ValueError("digest must be {enabled: bool, at: HH:MM}")
        out["digest"] = {"enabled": dg.get("enabled", False), "at": _hhmm(dg.get("at", "08:00"), "digest.at")}
    return out


def _topics(values, where: str) -> list[str]:
    if not isinstance(values, list) or not all(isinstance(t, str) and TOPIC_RE.match(t) for t in values):
        raise ValueError(f"{where}: topics are {', '.join(TOPICS)} or plugin.<app-id>, optionally ending in .*")
    return list(values)


def topic_matches(pattern: str, topic: str) -> bool:
    if pattern.endswith(".*"):
        base = pattern[:-2]
        return topic == base or topic.startswith(base + ".")
    return topic == pattern


def route_matches(match: dict, topic: str, severity: str) -> bool:
    if "topic" in match and not topic_matches(match["topic"], topic):
        return False
    if "severity" in match and severity not in match["severity"]:
        return False
    if "severity_at_least" in match and RANK[severity] < RANK[match["severity_at_least"]]:
        return False
    return True


def targets(doc: dict, topic: str, severity: str, available: list[str]) -> list[str]:
    """The person's channel and device ids this item goes to (in `available` order)."""
    chosen: set[str] = set()
    for r in doc.get("routes", []):
        if route_matches(r["match"], topic, severity):
            chosen.update(available if "*" in r["channels"] else r["channels"])
    return [t for t in available if t in chosen]


def _zone(doc: dict) -> ZoneInfo:
    qh = doc.get("quiet_hours")
    return ZoneInfo(qh["tz"] if qh else "UTC")


def _t(hhmm: str) -> time:
    h, m = hhmm.split(":")
    return time(int(h), int(m))


def _next_at(local_now: datetime, at: time) -> datetime:
    candidate = local_now.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    return candidate if candidate > local_now else candidate + timedelta(days=1)


def hold(doc: dict, topic: str, severity: str, now: datetime) -> tuple[str, datetime] | None:
    """("quiet" | "digest", release time in UTC) when this item must wait, else None."""
    zone = _zone(doc)
    local = now.astimezone(zone)
    qh = doc.get("quiet_hours")
    if qh:
        start, end, t = _t(qh["from"]), _t(qh["to"]), local.time()
        inside = (start <= t < end) if start < end else (t >= start or t < end)
        excepted = severity in qh["except_severity"] or any(topic_matches(p, topic) for p in qh["except_topics"])
        if start != end and inside and not excepted:
            return "quiet", _next_at(local, end).astimezone(now.tzinfo)
    dg = doc.get("digest") or {}
    if dg.get("enabled") and severity == "info" and not topic_matches("approvals.*", topic):
        return "digest", _next_at(local, _t(dg["at"])).astimezone(now.tzinfo)
    return None
