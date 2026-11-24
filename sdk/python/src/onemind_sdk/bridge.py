# SPDX-License-Identifier: Apache-2.0
"""Polling and replay for fixed public provider APIs. Emission uses the bridge's own gateway client."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Callable

import httpx

from ._core import Req
from .client import Client

MAX_DOCUMENT = 2 * 1024 * 1024
BRIDGE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
SOURCES = {
    "usgs": ("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_hour.geojson", 60),
    "nws": ("https://api.weather.gov/alerts/active", 60),
    "eonet": ("https://eonet.gsfc.nasa.gov/api/v3/events/geojson?status=open&limit=100", 600),
}


@dataclass(frozen=True)
class Snapshot:
    etag: str | None
    body: bytes


class BridgePoller:
    def __init__(self, source: str, user_agent: str, http: httpx.Client, clock: Callable[[], float] = time.monotonic):
        if not user_agent.strip():
            raise ValueError("a descriptive User-Agent is required")
        self.url, self.interval = SOURCES[source]
        self.http, self.user_agent, self.clock = http, user_agent, clock
        self.etag: str | None = None
        self.next_poll = 0.0
        self.failures = 0

    def fetch(self) -> Snapshot | None:
        start = self.clock()
        if start < self.next_poll:
            return None
        headers = {"Accept": "application/geo+json,application/json", "User-Agent": self.user_agent}
        if self.etag:
            headers["If-None-Match"] = self.etag
        self.next_poll = start + self.interval
        try:
            with self.http.stream("GET", self.url, headers=headers, follow_redirects=False, timeout=10) as response:
                if response.status_code == 304:
                    self.failures = 0
                    return None
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_bytes():
                    if len(data) + len(chunk) > MAX_DOCUMENT or self.clock() - start > 15:
                        raise ValueError("provider response exceeded its read limit")
                    data.extend(chunk)
                return Snapshot(response.headers.get("ETag"), bytes(data))
        except (httpx.HTTPError, ValueError):
            self.failures += 1
            self.next_poll = start + max(self.interval, min(3600, 10 * 2 ** min(self.failures, 9)))
            raise

    def commit(self, snapshot: Snapshot):
        """Confirm the ETag only once this snapshot's records have been processed."""
        self.etag = snapshot.etag
        self.failures = 0


def emit(client: Client, bridge_id: str, events: list[dict]) -> list[Any]:
    if not BRIDGE_ID.fullmatch(bridge_id):
        raise ValueError("invalid app id")
    reports = []
    for index in range(0, len(events), 100):
        report = client.call(Req("POST", f"/v1/bridges/{bridge_id}/events", body={"events": events[index:index + 100]}))
        reports.append(report)
        if report.get("paused") or report.get("rejected"):
            break
    return reports


def replay(source: str, document: dict) -> list[dict]:
    """Map a recorded provider response without a clock, network or gateway credential."""
    if source not in SOURCES:
        raise ValueError("unknown fixed provider")
    features = document.get("features")
    if document.get("type") != "FeatureCollection" or not isinstance(features, list):
        raise ValueError("provider response must be a feature collection")
    events = []
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            continue
        props = feature.get("properties")
        if not isinstance(props, dict):
            continue
        if source == "usgs":
            key, title, stamp = feature.get("id"), props.get("title") or props.get("place"), props.get("updated")
            at = datetime.fromtimestamp(stamp / 1000, tz=timezone.utc) if isinstance(stamp, int) and 0 < stamp < 4_102_444_800_000 else None
        else:
            key = props.get("id") or feature.get("id")
            title = (props.get("headline") or props.get("event")) if source == "nws" else props.get("title")
            when = props.get("sent") if source == "nws" else props.get("date")
            try:
                at = datetime.fromisoformat(when.replace("Z", "+00:00")) if isinstance(when, str) else None
            except ValueError:
                at = None
        if not isinstance(key, str) or not key or not isinstance(title, str) or not title.strip() or not at or not at.tzinfo:
            continue
        epoch = int(at.timestamp() * 1000)
        if not 0 <= epoch <= 2**53 - 1:
            continue
        event = {
            "id": sha256(key.encode()).hexdigest(), "time": at.isoformat(), "revision": epoch,
            "kind": "alert", "name": {"usgs": "earthquake", "nws": "weather", "eonet": "natural_event"}[source],
            "value": {"headline": title[:240]},
        }
        geometry = feature.get("geometry")
        if isinstance(geometry, dict) and geometry.get("type") == "Point":
            coordinates = geometry.get("coordinates")
            if isinstance(coordinates, list) and len(coordinates) >= 2:
                lon, lat = coordinates[:2]
                if all(type(value) in (int, float) for value in (lon, lat)) and -180 <= lon <= 180 and -90 <= lat <= 90:
                    event["position"] = {"type": "Point", "coordinates": [lon, lat]}
        events.append(event)
    return events
