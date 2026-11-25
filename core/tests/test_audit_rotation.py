# SPDX-License-Identifier: Apache-2.0
"""Audit log rotation and retention: bounded disk, chain still verifiable (perf lab finding)."""

import gzip
from datetime import UTC, datetime

from onemind_core.audit import AuditLog, chain_anchored, segments, verify
from onemind_core.auditread import AuditReader, verify_file


def clock():
    return datetime(2026, 11, 21, tzinfo=UTC)


def fill(log, n, start=0):
    for i in range(start, start + n):
        log.append("files.write", {"id": "p"}, None, {"path": f"/f/{i}", "pad": "x" * 200})


def test_rotation_keeps_chain_verifiable_and_active_file_small(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path, clock, max_bytes=4000)
    fill(log, 60)
    segs = segments(path)
    assert len(segs) >= 5
    assert path.stat().st_size < 4000 + 800
    assert all(s[2].stat().st_size < 4000 for s in segs)  # gzip makes closed segments smaller
    assert verify(path) == (True, 60, "ok")
    assert verify_file(path)["ok"] and verify_file(path)["records"] == 60


def test_restart_continues_chain_from_a_segment(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path, clock, max_bytes=2000)
    fill(log, 20)
    last = segments(path)[-1][1]
    path.write_bytes(b"")  # active file empty right after a rotation
    again = AuditLog(path, clock, max_bytes=2000)
    rec = again.append("x")
    assert rec["seq"] == last + 1
    assert verify(path)[0]


def test_crash_between_segment_and_truncate_does_not_duplicate(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path, clock, max_bytes=None)
    fill(log, 5)
    data = path.read_bytes()
    seg = path.with_name(f"{path.name}.{1:012d}-{5:012d}.gz")
    seg.write_bytes(gzip.compress(data))  # segment saved, active file not yet emptied
    again = AuditLog(path, clock, max_bytes=None)
    assert again.append("next")["seq"] == 6
    assert verify(path) == (True, 6, "ok")


def test_reader_lists_and_gets_across_segments(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path, clock, max_bytes=3000)
    fill(log, 40)
    reader = AuditReader(path, clock, lambda _id: set())
    from onemind_core.auth import Principal
    owner = Principal(id="o", kind="person", role="owner")
    recs, more = reader.list(owner, after_seq=3, limit=500)
    assert [r["seq"] for r in recs] == list(range(4, 41)) and not more
    assert reader.get(owner, 2)["seq"] == 2
    assert reader.get(owner, 40)["seq"] == 40
    assert reader.verify()["records"] == 40


def test_altered_segment_is_detected(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path, clock, max_bytes=3000)
    fill(log, 30)
    first = segments(path)[0][2]
    first.write_bytes(gzip.compress(gzip.decompress(first.read_bytes()).replace(b"/f/1", b"/f/9", 1)))
    ok, _n, reason = verify(path)
    assert not ok and "hash mismatch" in reason
    assert not verify_file(path)["ok"]


def test_retention_prunes_old_segments_and_verify_still_works(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path, clock, max_bytes=3000, keep_segments=2)
    fill(log, 80)
    assert len(segments(path)) <= 3 and chain_anchored(path)
    ok, n, reason = verify(path)
    assert ok, reason
    assert n > 40
    res = verify_file(path)
    assert res["ok"] and res["head"]["seq"] == n
    # restart still resumes the same chain
    again = AuditLog(path, clock, max_bytes=3000, keep_segments=2)
    again.append("after.restart")
    assert verify(path)[0]


def test_deleting_history_without_a_pruned_event_is_detected(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path, clock, max_bytes=3000)
    fill(log, 40)
    segments(path)[0][2].unlink()
    ok, _n, reason = verify(path)
    assert not ok and "audit.pruned" in reason
    assert not verify_file(path)["ok"]


def test_truncated_segment_is_reported_not_raised(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path, clock, max_bytes=2000)
    fill(log, 20)
    segs = segments(path)
    first = segs[0][2]
    first.write_bytes(first.read_bytes()[:-20])
    ok, _n, reason = verify(path)
    assert not ok and "damaged" in reason
    res = verify_file(path)
    assert res["ok"] is False and res["first_bad_seq"] is not None


def test_corrupt_newest_segment_does_not_stop_the_gateway_starting(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path, clock, max_bytes=2000)
    fill(log, 20)
    path.write_bytes(b"")
    last = segments(path)[-1][2]
    last.write_bytes(last.read_bytes()[:-20])
    AuditLog(path, clock, max_bytes=2000)  # must not raise
    assert verify(path)[0] is False
