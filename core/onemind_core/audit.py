"""Hash-chained JSONL audit log (contract section 3 "Audit"; v0 subset of D-B9.7).

Each line is one JSON object:

    {"seq": 7, "ts": "...", "event": "action.approved", "principal": {...},
     "action_id": "...", "data": {...}, "prev_hash": "<64 hex>", "hash": "<64 hex>"}

    hash = sha256(prev_hash + canonical_json(line without prev_hash and hash))

canonical_json = sorted keys, no whitespace, UTF-8. The first line uses prev_hash = 64 zeros.
Changing, removing or reordering any earlier line breaks every later hash, which verify() detects.
Every appended line is also published to NATS subject onemind.audit when NATS is connected.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

log = logging.getLogger("onemind.audit")

GENESIS = "0" * 64
AUDIT_SUBJECT = "onemind.audit"


def canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def chain_hash(prev_hash: str, body: dict) -> str:
    return hashlib.sha256((prev_hash + canonical_json(body)).encode("utf-8")).hexdigest()


def _record(line: str | bytes) -> dict:
    """Read one unambiguous UTF-8 object, including nested objects.

    Last-key-wins JSON would let different readers see different events in the same chain.
    Use the same decoder for verification and crash recovery.
    """
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    if isinstance(line, bytes):
        line = line.decode("utf-8")
    rec = json.loads(line, object_pairs_hook=unique)
    if not isinstance(rec, dict):
        raise ValueError("audit record is not an object")
    return rec


class AuditLog:
    def __init__(
        self,
        path: Path,
        clock: Callable[[], datetime],
        publish: Callable[[str, bytes], None] | None = None,
    ):
        self.path = path
        self.clock = clock
        self.publish = publish
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seq, self._last_hash, recovered = self._resume()
        if recovered is not None:
            log.warning("audit log had an incomplete tail; moved it to %s", recovered["moved_to"])
            self.append("audit.recovered", None, None, recovered)

    @staticmethod
    def _parse_record(line: bytes) -> dict | None:
        """A line that parses and whose own hash is right, else None."""
        try:
            rec = _record(line)
            body = {k: v for k, v in rec.items() if k not in ("prev_hash", "hash")}
            if type(rec["seq"]) is int and chain_hash(rec["prev_hash"], body) == rec["hash"]:
                return rec
        except (ValueError, KeyError, TypeError, UnicodeError):
            pass
        return None

    def _resume(self) -> tuple[int, str, dict | None]:
        """Continue the chain after a restart from the last complete, self-consistent line.

        A crash or power loss can leave a partial last line. Instead of refusing to start, the
        bytes after the last good line are moved to <name>.corrupt (appended, never lost), the
        file is truncated there, and the caller writes an audit.recovered event. Damage earlier
        in the file is left in place for verify() to report.
        """
        if not self.path.exists():
            return 0, GENESIS, None
        data = self.path.read_bytes()
        seq, last_hash, good_end, pos = 0, GENESIS, 0, 0
        for line in data.splitlines(keepends=True):
            pos += len(line)
            if line.strip():
                rec = self._parse_record(line)
                if rec is not None:
                    seq, last_hash, good_end = rec["seq"], rec["hash"], pos
        tail = data[good_end:]
        if not tail.strip():
            if data and not data.endswith(b"\n"):
                with self.path.open("ab") as fh:
                    fh.write(b"\n")
            return seq, last_hash, None
        corrupt = self.path.with_name(self.path.name + ".corrupt")
        with corrupt.open("ab") as fh:
            fh.write(tail if tail.endswith(b"\n") else tail + b"\n")
            fh.flush()
            os.fsync(fh.fileno())
        with self.path.open("r+b") as fh:
            fh.truncate(good_end)
            if good_end and not data[:good_end].endswith(b"\n"):
                fh.seek(good_end)
                fh.write(b"\n")
            fh.flush()
            os.fsync(fh.fileno())
        return seq, last_hash, {"moved_bytes": len(tail), "moved_to": corrupt.name}

    def append(
        self,
        event: str,
        principal: dict | None = None,
        action_id: str | None = None,
        data: dict | None = None,
    ) -> dict:
        with self._lock:
            body = {
                "seq": self._seq + 1,
                "ts": self.clock().isoformat().replace("+00:00", "Z"),
                "event": event,
                "principal": principal,
                "action_id": action_id,
                "data": data or {},
            }
            digest = chain_hash(self._last_hash, body)
            record = {**body, "prev_hash": self._last_hash, "hash": digest}
            line = canonical_json(record) + "\n"
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line)
                fh.flush()
                os.fsync(fh.fileno())
            self._seq, self._last_hash = body["seq"], digest
        if self.publish is not None:
            try:
                self.publish(AUDIT_SUBJECT, line.encode("utf-8"))
            except Exception:  # the file is the record of truth; the bus is best effort
                log.exception("audit publish failed")
        return record


def verify(path: Path) -> tuple[bool, int, str]:
    """Check the whole chain. Returns (ok, number of lines checked, reason)."""
    prev = GENESIS
    n = 0
    if not path.exists():
        return True, 0, "no audit log yet"
    # Decode per line: a text stream may decode a later damaged line while buffering an
    # earlier one, losing the exact verified-prefix count.
    with path.open("rb") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                rec = _record(line)
            except (ValueError, UnicodeError):
                return False, n, f"line {lineno}: not JSON"
            got_prev, got_hash = rec.pop("prev_hash", None), rec.pop("hash", None)
            if got_prev != prev:
                return False, n, f"line {lineno}: prev_hash does not match the previous line"
            if type(rec.get("seq")) is not int or rec["seq"] != n + 1:
                return False, n, f"line {lineno}: seq {rec.get('seq')} out of order"
            try:
                digest = chain_hash(prev, rec)
            except UnicodeError:
                return False, n, f"line {lineno}: invalid Unicode in record"
            if digest != got_hash:
                return False, n, f"line {lineno}: hash mismatch (line was altered)"
            prev = got_hash
            n += 1
    return True, n, "ok"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: onemind-audit-verify <audit.jsonl>", file=sys.stderr)
        return 2
    ok, n, reason = verify(Path(argv[0]))
    print(f"{'OK' if ok else 'BROKEN'}: {n} lines verified; {reason}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
