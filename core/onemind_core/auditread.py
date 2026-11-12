# SPDX-License-Identifier: Apache-2.0
"""Read side of the audit log: list, get and verify (contract §12.16, API.md §5.7).

The log stays the append-only, hash-chained JSONL file of audit.py; nothing here writes to it.
Who sees what (§12.6 role defaults, F-19):
- person owner or adult (`audit:read`): every record;
- agent (`audit:read:own`): records it wrote, plus records about actions it requested;
- anyone else (guest, child): 403.
"""

from __future__ import annotations

import fnmatch
import json
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

from .audit import GENESIS, chain_hash
from .auth import Principal

FULL_READERS = {("person", "owner"), ("person", "adult")}
DEFAULT_LIMIT = 100
MAX_LIMIT = 500


def can_read_all(p: Principal) -> bool:
    return (p.kind, p.role) in FULL_READERS


def can_read_own(p: Principal) -> bool:
    return can_read_all(p) or p.kind == "agent"


def iter_records(path: Path, start: int = 0) -> Iterator[tuple[int, dict]]:
    """Yield (byte offset after the line, record) for each parseable line from `start`."""
    if not path.exists():
        return
    with path.open("rb") as fh:
        fh.seek(start)
        pos = start
        for raw in fh:
            if not raw.endswith(b"\n"):
                break  # a line still being written
            pos += len(raw)
            if not raw.strip():
                continue
            try:
                rec = json.loads(raw)
            except ValueError:
                continue
            if isinstance(rec, dict) and isinstance(rec.get("seq"), int):
                yield pos, rec


def glob_any(patterns: str | None, value: str | None) -> bool:
    """§12.1 filter: comma means OR, `*` is a glob. None matches everything."""
    if not patterns:
        return True
    if value is None:
        return False
    return any(fnmatch.fnmatchcase(value, p.strip()) for p in patterns.split(",") if p.strip())


class AuditReader:
    def __init__(self, path: Path, clock: Callable[[], datetime], owned_action_ids: Callable[[str], set[str]]):
        self.path = path
        self.clock = clock
        self.owned_action_ids = owned_action_ids
        self._verify_cache: tuple[tuple[int, float], dict] | None = None

    def visible(self, p: Principal) -> Callable[[dict], bool]:
        if can_read_all(p):
            return lambda rec: True
        own = self.owned_action_ids(p.id)

        def check(rec: dict) -> bool:
            who = rec.get("principal") or {}
            return who.get("id") == p.id and who.get("kind") == p.kind or rec.get("action_id") in own

        return check

    def list(
        self,
        p: Principal,
        *,
        after_seq: int | None = None,
        before_seq: int | None = None,
        event: str | None = None,
        principal_id: str | None = None,
        action_id: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> tuple[list[dict], bool]:
        """Matching records in seq order and whether more follow the last one returned."""
        ok = self.visible(p)
        out: list[dict] = []
        for _, rec in iter_records(self.path):
            seq = rec["seq"]
            if after_seq is not None and seq <= after_seq:
                continue
            if before_seq is not None and seq >= before_seq:
                break
            if not ok(rec) or not glob_any(event, rec.get("event")):
                continue
            if principal_id and (rec.get("principal") or {}).get("id") != principal_id:
                continue
            if action_id and rec.get("action_id") != action_id:
                continue
            ts = str(rec.get("ts", ""))
            if (since and ts < since) or (until and ts >= until):
                continue
            if len(out) == limit:
                return out, True
            out.append(rec)
        return out, False

    def get(self, p: Principal, seq: int) -> dict | None:
        ok = self.visible(p)
        for _, rec in iter_records(self.path):
            if rec["seq"] == seq:
                return rec if ok(rec) else None
            if rec["seq"] > seq:
                break
        return None

    def verify(self, from_seq: int | None = None) -> dict:
        """Recompute the chain. A full check is cached until the file changes."""
        try:
            st = self.path.stat()
            key = (st.st_size, st.st_mtime)
        except OSError:
            key = (0, 0.0)
        if from_seq is None and self._verify_cache and self._verify_cache[0] == key:
            return self._verify_cache[1]
        result = verify_file(self.path, from_seq)
        result["checked_at"] = self.clock().isoformat().replace("+00:00", "Z")
        if from_seq is None:
            self._verify_cache = (key, result)
        return result


def verify_lines(lines: Iterator[bytes], from_seq: int | None = None) -> dict:
    """The audit.py rule, reporting the first bad seq. Shared by the API and its tests."""
    prev, n, head = GENESIS, 0, None
    for raw in lines:
        if not raw.strip():
            continue
        bad_seq = n + 1
        try:
            rec = json.loads(raw)
            got_prev, got_hash = rec.pop("prev_hash"), rec.pop("hash")
        except (ValueError, KeyError, TypeError, AttributeError):
            return _bad(n, head, bad_seq, f"seq {bad_seq}: not a JSON audit record")
        seq = rec.get("seq")
        if from_seq is not None and isinstance(seq, int) and seq < from_seq:
            # Before the range: only follow the chain.
            prev, n, head = got_hash, seq, {"seq": seq, "hash": got_hash}
            continue
        if got_prev != prev:
            return _bad(n, head, bad_seq, f"seq {bad_seq}: prev_hash does not match the previous record")
        if seq != n + 1:
            return _bad(n, head, bad_seq, f"seq {seq!r} out of order (expected {bad_seq})")
        if chain_hash(prev, rec) != got_hash:
            return _bad(n, head, bad_seq, f"seq {bad_seq}: hash mismatch (record changed after it was written)")
        prev, n, head = got_hash, seq, {"seq": seq, "hash": got_hash}
    return {"ok": True, "records": n, "head": head, "first_bad_seq": None, "reason": "ok", "last_checkpoint": None}


def _bad(n: int, head: dict | None, seq: int, reason: str) -> dict:
    return {"ok": False, "records": n, "head": head, "first_bad_seq": seq, "reason": reason, "last_checkpoint": None}


def verify_file(path: Path, from_seq: int | None = None) -> dict:
    if not path.exists():
        return verify_lines(iter(()), from_seq)
    with path.open("rb") as fh:
        return verify_lines(iter(fh), from_seq)
