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
        self._seq, self._last_hash = self._resume()

    def _resume(self) -> tuple[int, str]:
        """Continue the chain after a restart from the last line on disk."""
        if not self.path.exists():
            return 0, GENESIS
        last = None
        with self.path.open("rb") as fh:
            for line in fh:
                if line.strip():
                    last = line
        if last is None:
            return 0, GENESIS
        rec = json.loads(last)
        return int(rec["seq"]), rec["hash"]

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
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                return False, n, f"line {lineno}: not JSON"
            got_prev, got_hash = rec.pop("prev_hash", None), rec.pop("hash", None)
            if got_prev != prev:
                return False, n, f"line {lineno}: prev_hash does not match the previous line"
            if rec.get("seq") != n + 1:
                return False, n, f"line {lineno}: seq {rec.get('seq')} out of order"
            if chain_hash(prev, rec) != got_hash:
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
