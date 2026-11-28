# SPDX-License-Identifier: Apache-2.0
"""Polling and replay for fixed public provider APIs. Emission uses the bridge's own gateway client."""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx

from ._core import Req
from .client import Client

MAX_DOCUMENT = 2 * 1024 * 1024
BRIDGE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
SOURCES = {
    "usgs": ("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_hour.geojson", 60),
    "nws": ("https://api.weather.gov/alerts/active", 60),
    "gdelt": ("https://api.gdeltproject.org/api/v2/doc/doc?query=%28wildfire%20OR%20earthquake%29&mode=artlist&format=jsonfeed&maxrecords=50", 900),
    "celestrak": ("https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=JSON", 7200),
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
        self.stop_on_http_error = source == "celestrak"
        self.http, self.user_agent, self.clock = http, user_agent, clock
        self.etag: str | None = None
        self.next_poll = 0.0
        self.failures = 0

    def fetch(self) -> Snapshot | None:
        start = self.clock()
        if start < self.next_poll:
            return None
        headers = {"Accept": "application/geo+json,application/json", "User-Agent": self.user_agent}
        if self.etag and not self.stop_on_http_error:
            headers["If-None-Match"] = self.etag
        self.next_poll = start + self.interval
        try:
            with self.http.stream("GET", self.url, headers=headers, follow_redirects=False, timeout=10) as response:
                if self.stop_on_http_error and response.status_code != 200:
                    # CelesTrak requires operator intervention after any unsuccessful HTTP response.
                    self.next_poll = float("inf")
                    raise ValueError(f"CelesTrak returned {response.status_code}; check the provider before polling again")
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
            if self.next_poll != float("inf"):
                self.next_poll = start + max(self.interval, min(3600, 10 * 2 ** min(self.failures, 9)))
            raise

    def commit(self, snapshot: Snapshot):
        """Confirm the ETag only once this snapshot's records have been processed."""
        self.etag = snapshot.etag
        self.failures = 0


def emit(client: Client, bridge_id: str, events: list[dict]) -> list[Any]:
    if not BRIDGE_ID.fullmatch(bridge_id):
        raise ValueError("invalid bridge id")
    reports = []
    for index in range(0, len(events), 100):
        report = client.call(Req("POST", f"/v1/bridges/{bridge_id}/events", body={"events": events[index:index + 100]}))
        reports.append(report)
        if report.get("paused") or report.get("rejected"):
            break
    return reports


def _metadata(source: str, document: object) -> list[dict]:
    articles = source == "gdelt"
    records = document.get("items") if articles and isinstance(document, dict) else document
    if not isinstance(records, list):
        raise ValueError("provider response must contain a metadata list")
    events = []
    for record in records:
        if not isinstance(record, dict):
            continue
        if articles:
            key, headline, timestamp = record.get("url"), record.get("title"), record.get("date_published")
            if not isinstance(key, str):
                continue
            try:
                link = urlsplit(key)
            except ValueError:
                continue
            if link.scheme not in ("http", "https") or not link.hostname or link.username or link.password:
                continue
            value = {"publisher": link.hostname}
            kind, name = "article", "news"
        else:
            catalog = record.get("NORAD_CAT_ID")
            if type(catalog) is not int or catalog <= 0:
                continue
            key, headline, timestamp = str(catalog), record.get("OBJECT_NAME"), record.get("EPOCH")
            value = {"catalog_id": catalog}
            kind, name = "intel", "orbit"
        if not isinstance(headline, str) or not headline.strip() or not isinstance(timestamp, str):
            continue
        try:
            at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        if not at.tzinfo:
            if articles:
                continue
            at = at.replace(tzinfo=timezone.utc)  # CelesTrak GP JSON uses UTC.
        revision = int(at.timestamp() * 1000)
        if 0 <= revision <= 2**53 - 1:
            events.append({"id": sha256(key.encode()).hexdigest(), "time": at.isoformat(), "revision": revision,
                           "kind": kind, "name": name, "value": {**value, "headline": headline[:240]}})
    return events


def replay(source: str, document: object) -> list[dict]:
    """Map a recorded provider response without a clock, network or gateway credential."""
    if source not in SOURCES:
        raise ValueError("unknown fixed provider")
    if source in {"gdelt", "celestrak"}:
        return _metadata(source, document)
    if not isinstance(document, dict):
        raise ValueError("provider response must be a feature collection")
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
            at = datetime.fromtimestamp(stamp / 1000, tz=timezone.utc) if type(stamp) is int and 0 < stamp < 4_102_444_800_000 else None
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
                    # The datapoint schema wants {lat, lon[, alt_m]}, not GeoJSON; exactly 0,0 is refused.
                    if not (lat == 0 and lon == 0):
                        position = {"lat": lat, "lon": lon}
                        if len(coordinates) >= 3 and type(coordinates[2]) in (int, float) and math.isfinite(coordinates[2]):
                            position["alt_m"] = coordinates[2]
                        event["position"] = position
        events.append(event)
    return events
