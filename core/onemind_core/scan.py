# SPDX-License-Identifier: Apache-2.0
"""Scan records (contract §11.1) and the "nothing unscanned runs" check (§10.3).

The app CI gate (§9.4) and the daily rescan (§10.2) write apps/<id>/scan.json. The gateway only
reads it: the catalog shows {scanned_at, result}, and approving an app.install is refused with
409 stale_precondition unless the record exists, says "pass" and is at most 7 days old.

A record that cannot be read, is not JSON, or has a bad timestamp or result counts as missing:
an unreadable scan is no evidence that the app was scanned.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("onemind.scan")

SCAN_FILE = "scan.json"
MAX_AGE = timedelta(days=7)
# A record dated in the future is accepted only within this clock skew; beyond it, it is invalid
# (otherwise a mistyped year would keep an app "fresh" forever).
MAX_FUTURE_SKEW = timedelta(minutes=5)
MAX_BYTES = 1024 * 1024
RESULTS = ("pass", "fail")


@dataclass(frozen=True)
class ScanRecord:
    scanned_at: datetime
    result: str

    def summary(self) -> dict:
        """The §11.4 catalog field: {scanned_at, result}."""
        return {"scanned_at": self.scanned_at.isoformat().replace("+00:00", "Z"), "result": self.result}


def read_scan(app_dir: Path) -> ScanRecord | None:
    path = app_dir / SCAN_FILE
    try:
        if path.stat().st_size > MAX_BYTES:
            log.warning("ignoring %s/%s: larger than %d bytes", app_dir.name, SCAN_FILE, MAX_BYTES)
            return None
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        log.warning("ignoring %s/%s: %s", app_dir.name, SCAN_FILE, exc.__class__.__name__)
        return None
    if not isinstance(doc, dict):
        return None
    result, raw_ts = doc.get("result"), doc.get("scanned_at")
    if result not in RESULTS or not isinstance(raw_ts, str):
        log.warning("ignoring %s/%s: needs result pass|fail and scanned_at", app_dir.name, SCAN_FILE)
        return None
    try:
        ts = datetime.fromisoformat(raw_ts)
    except ValueError:
        ts = None
    if ts is None or ts.tzinfo is None:
        log.warning("ignoring %s/%s: scanned_at is not an RFC 3339 timestamp", app_dir.name, SCAN_FILE)
        return None
    return ScanRecord(scanned_at=ts, result=result)


def scan_problem(app_id: str, record: ScanRecord | None, now: datetime) -> str | None:
    """Why app_id may not be installed now (§10.3), or None when its scan allows it."""
    if record is None:
        return f"app {app_id!r} has no valid scan record ({SCAN_FILE}); nothing unscanned runs"
    if record.result != "pass":
        return f"app {app_id!r} failed its last scan ({record.summary()['scanned_at']})"
    age = now - record.scanned_at
    if age < -MAX_FUTURE_SKEW:
        return f"app {app_id!r} has a scan record dated in the future; treating it as invalid"
    if age > MAX_AGE:
        return f"app {app_id!r} was last scanned {age.days} days ago; a scan newer than 7 days is required"
    return None
