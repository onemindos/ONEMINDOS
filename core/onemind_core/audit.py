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

import gzip
import hashlib
import json
import logging
import os
import re
import sys
import threading
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

log = logging.getLogger("onemind.audit")

GENESIS = "0" * 64
AUDIT_SUBJECT = "onemind.audit"
PRUNED_EVENT = "audit.pruned"
# The active file is compressed into a segment once it reaches this size. A record is about 1.4 KB
# as JSON; gzip makes a segment roughly a quarter of that, so the log costs well under 1 KB per
# event on disk instead of growing without bound in one file.
DEFAULT_MAX_BYTES = 16 * 1024 * 1024
_SEGMENT = re.compile(r"\.(\d{12})-(\d{12})\.gz$")


def segments(path: Path) -> list[tuple[int, int, Path]]:
    """Closed, compressed segments next to the active file as (first seq, last seq, path), oldest first."""
    found = []
    if path.parent.is_dir():
        for p in path.parent.glob(glob_escape(path.name) + ".*.gz"):
            m = _SEGMENT.search(p.name[len(path.name):])
            if m and p.name == f"{path.name}.{m.group(1)}-{m.group(2)}.gz":
                found.append((int(m.group(1)), int(m.group(2)), p))
    return sorted(found)


def glob_escape(name: str) -> str:
    return re.sub(r"([*?\[])", r"[\1]", name)


def chain_anchored(path: Path) -> bool:
    """True when the oldest history was pruned, so the chain starts from a recorded anchor."""
    segs = segments(path)
    return bool(segs) and segs[0][0] > 1


def iter_lines(path: Path, min_seq: int = 0) -> Iterator[bytes]:
    """Every line of the log in order: closed segments, then the active file.

    Segments whose last seq is below min_seq are skipped without being decompressed.
    """
    for _first, last, seg in segments(path):
        if last < min_seq:
            continue
        with gzip.open(seg, "rb") as fh:
            yield from fh
    if path.exists():
        with path.open("rb") as fh:
            yield from fh


def _last_record(seg: Path) -> dict | None:
    rec = None
    with gzip.open(seg, "rb") as fh:
        for line in fh:
            if line.strip():
                rec = _record(line)
    return rec


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
        max_bytes: int | None = DEFAULT_MAX_BYTES,
        keep_segments: int | None = None,
    ):
        """max_bytes: compress the active file into a segment at this size (None = never).

        keep_segments: keep only the newest N segments (None = keep all). Older ones are deleted
        and an audit.pruned event, inside the chain, records the seq and hash the chain resumes
        from, so verify still works on what is left.
        """
        self.max_bytes = max_bytes
        self.keep_segments = keep_segments
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
        segs = segments(self.path)
        if segs and self.path.exists():
            # A crash after the segment was saved but before the active file was emptied leaves
            # the same records in both places; the segment is complete, so empty the file.
            first_line = next((ln for ln in self.path.read_bytes().splitlines() if ln.strip()), None)
            rec = self._parse_record(first_line) if first_line else None
            if rec is not None and rec["seq"] <= segs[-1][1]:
                with self.path.open("r+b") as fh:
                    fh.truncate(0)
                    os.fsync(fh.fileno())
        if not self.path.exists():
            return self._after_segments(segs)
        data = self.path.read_bytes()
        seq, last_hash, good_end, pos = 0, GENESIS, 0, 0
        for line in data.splitlines(keepends=True):
            pos += len(line)
            if line.strip():
                rec = self._parse_record(line)
                if rec is not None:
                    seq, last_hash, good_end = rec["seq"], rec["hash"], pos
        if good_end == 0:
            seq, last_hash = self._after_segments(segs)[:2]
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

    @staticmethod
    def _after_segments(segs: list[tuple[int, int, Path]]) -> tuple[int, str, None]:
        if not segs:
            return 0, GENESIS, None
        rec = _last_record(segs[-1][2])
        if rec is None:
            raise ValueError(f"audit segment {segs[-1][2].name} is empty")
        return rec["seq"], rec["hash"], None

    def _rotate(self) -> None:
        """Compress the active file into a closed segment, then empty it (the chain carries on)."""
        first = next(
            (r["seq"] for ln in self.path.read_bytes().splitlines() if ln.strip()
             and (r := self._parse_record(ln)) is not None),
            None,
        )
        if first is None:
            return
        seg = self.path.with_name(f"{self.path.name}.{first:012d}-{self._seq:012d}.gz")
        tmp = seg.with_name(seg.name + ".tmp")
        with self.path.open("rb") as src, tmp.open("wb") as out:
            with gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as gz:
                while chunk := src.read(1 << 20):
                    gz.write(chunk)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, seg)
        _fsync_dir(seg.parent)
        with self.path.open("r+b") as fh:
            fh.truncate(0)
            os.fsync(fh.fileno())
        self._prune()

    def _prune(self) -> None:
        segs = segments(self.path)
        if self.keep_segments is None or len(segs) <= self.keep_segments:
            return
        drop = segs[: len(segs) - self.keep_segments]
        last = _last_record(drop[-1][2])
        if last is None:
            return
        for _f, _l, p in drop:
            p.unlink()
        _fsync_dir(self.path.parent)
        self._append_locked(PRUNED_EVENT, None, None, {
            "through_seq": last["seq"], "through_hash": last["hash"], "segments": len(drop),
        })

    def append(
        self,
        event: str,
        principal: dict | None = None,
        action_id: str | None = None,
        data: dict | None = None,
    ) -> dict:
        with self._lock:
            record, line = self._append_locked(event, principal, action_id, data)
            if self.max_bytes and self.path.stat().st_size >= self.max_bytes:
                self._rotate()
        if self.publish is not None:
            try:
                self.publish(AUDIT_SUBJECT, line.encode("utf-8"))
            except Exception:  # the file is the record of truth; the bus is best effort
                log.exception("audit publish failed")
        return record

    def _append_locked(self, event, principal, action_id, data) -> tuple[dict, str]:
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
        return record, line


def _fsync_dir(d: Path) -> None:
    try:
        fd = os.open(d, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def verify(path: Path) -> tuple[bool, int, str]:
    """Check the whole chain, across closed segments and the active file.

    Returns (ok, number of lines checked, reason). When old segments were pruned the chain starts
    at the first retained record; its prev_hash must be the one an audit.pruned event inside the
    chain recorded, so deleting history without that event is reported.
    """
    prev = GENESIS
    n = 0
    segs = segments(path)
    if not path.exists() and not segs:
        return True, 0, "no audit log yet"
    anchor: tuple[int, str] | None = None
    accounted = False
    # Decode per line: a text stream may decode a later damaged line while buffering an
    # earlier one, losing the exact verified-prefix count.
    for lineno, line in enumerate(iter_lines(path), start=1):
        if not line.strip():
            continue
        try:
            rec = _record(line)
        except (ValueError, UnicodeError):
            return False, n, f"line {lineno}: not JSON"
        got_prev, got_hash = rec.pop("prev_hash", None), rec.pop("hash", None)
        if n == 0 and chain_anchored(path) and type(rec.get("seq")) is int:
            prev, n = got_prev, rec["seq"] - 1
            anchor = (n, got_prev)
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
        if anchor and rec.get("event") == PRUNED_EVENT:
            d = rec.get("data") or {}
            accounted = accounted or (d.get("through_seq"), d.get("through_hash")) == anchor
        prev = got_hash
        n += 1
    if anchor and not accounted:
        return False, n, "old records are missing and no audit.pruned event in the chain accounts for them"
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
