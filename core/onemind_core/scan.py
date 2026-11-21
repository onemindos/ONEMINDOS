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

from .filesig import cache_signature

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
    # ClamAV hits summed over images[].clamav.infected; None unless every listed image has a
    # readable count from a known signature database, so "no malware" is never assumed from a
    # record that does not say it (F-7 override).
    malware: int | None = None
    # Why a failed scan failed, in words an owner can read (None on a pass).
    reason: str | None = None

    def summary(self) -> dict:
        """The §11.4 catalog field: {scanned_at, result, reason}; reason is set only on a fail."""
        return {"scanned_at": self.scanned_at.isoformat().replace("+00:00", "Z"), "result": self.result,
                "reason": self.reason}


# scan.json path -> (stat signature, record). GET /v1/apps reads every app's scan on every poll; the
# parsed record only changes when the file does. Freshness (7 days) is judged by the caller with
# `now`, never cached here, and unreadable or invalid files are not cached at all. A file changed in
# the last moments is not cached either (filesig.cache_signature): a same-size rewrite in the same
# clock tick would otherwise keep serving the old record.
_CACHE: dict[Path, tuple[tuple, ScanRecord]] = {}


def read_scan(app_dir: Path) -> ScanRecord | None:
    path = app_dir / SCAN_FILE
    try:
        st = path.stat()
        sig = cache_signature(st)
        hit = _CACHE.get(path)
        if sig is not None and hit is not None and hit[0] == sig:
            return hit[1]
    except OSError:
        sig = None
    record = _read_scan_file(app_dir, path)
    if record is not None and sig is not None:
        _CACHE[path] = (sig, record)
    else:
        _CACHE.pop(path, None)
    return record


def _read_scan_file(app_dir: Path, path: Path) -> ScanRecord | None:
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
    return ScanRecord(scanned_at=ts, result=result, malware=_malware(doc.get("images")),
                      reason=_reason(doc) if result == "fail" else None)


def _count(v: object) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else 0


def _reason(doc: dict) -> str:
    """Summarise scan.json's own counts: what the gate counted, never a guess about the cause."""
    parts: list[str] = []
    images = doc.get("images")
    images = [i for i in images if isinstance(i, dict)] if isinstance(images, list) else []
    for img in images:
        trivy, clam = img.get("trivy"), img.get("clamav")
        trivy, clam = trivy if isinstance(trivy, dict) else {}, clam if isinstance(clam, dict) else {}
        ref = str(img.get("ref") or "image").split("@")[0][:120]
        bits = []
        if _count(trivy.get("critical_fixable")):
            bits.append(f"{_count(trivy.get('critical_fixable'))} CRITICAL vulnerabilities with a fix available")
        if _count(img.get("secrets")):
            bits.append(f"{_count(img.get('secrets'))} secret finding(s)")
        if _count(clam.get("infected")):
            bits.append(f"{_count(clam.get('infected'))} malware hit(s)")
        if bits:
            parts.append(f"{ref}: {', '.join(bits)}")
    if doc.get("smoke") not in (None, "pass"):
        parts.append(f"smoke test {doc.get('smoke')}")
    lic = doc.get("licence")
    if isinstance(lic, dict) and lic.get("class") == "blocked":
        parts.append(f"licence {str(lic.get('spdx'))[:40]} is not allowed")
    return "; ".join(parts)[:600] or "the gate computed fail (see the app's README)"


def _malware(images: object) -> int | None:
    # No image entries means ClamAV ran on nothing: app-gate skips an image whose pin check
    # failed, so a failed record can list none. "daily-unknown" is app-gate's mark for a run
    # without a signature database, whose count of 0 proves nothing.
    # A positive count anywhere wins over an unknown one elsewhere.
    if not isinstance(images, list) or not images:
        return None
    found, unknown = 0, False
    for img in images:
        clamav = img.get("clamav") if isinstance(img, dict) else None
        infected = clamav.get("infected") if isinstance(clamav, dict) else None
        sigs = clamav.get("signatures") if isinstance(clamav, dict) else None
        if not isinstance(infected, int) or isinstance(infected, bool) or infected < 0:
            unknown = True
            continue
        found += infected
        if not isinstance(sigs, str) or not sigs or sigs.endswith("-unknown"):
            unknown = True
    if found:
        return found
    return None if unknown else 0


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
