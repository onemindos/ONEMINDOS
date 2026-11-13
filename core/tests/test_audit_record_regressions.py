# SPDX-License-Identifier: Apache-2.0
"""Malformed-record checks with a retained pytest root, no recovery or cleanup calls."""
from datetime import UTC, datetime

import pytest

from onemind_core.audit import AuditLog, canonical_json, chain_hash, verify


def valid_lines(path):
    log = AuditLog(path, lambda: datetime(2026, 11, 12, tzinfo=UTC))
    for n in range(3):
        log.append("action.requested", None, None, {"n": n})
    return path.read_bytes().splitlines(keepends=True)


@pytest.mark.parametrize("bad", [b"[]\n", b'"text"\n', b"1\n", b"true\n", b"null\n", b"\xff\n"])
def test_malformed_record_reports_its_verified_prefix(tmp_path, bad):
    path = tmp_path / "audit.jsonl"
    lines = valid_lines(path)
    path.write_bytes(lines[0] + bad + lines[2])
    ok, n, reason = verify(path)
    assert not ok and n == 1 and reason.startswith("line 2:")


@pytest.mark.parametrize("nested", [False, True])
def test_duplicate_keys_cannot_hide_in_a_valid_chain(tmp_path, nested):
    path = tmp_path / "audit.jsonl"
    lines = valid_lines(path)
    if nested:
        lines[1] = lines[1].replace(b'"n":1', b'"n":0,"n":1')
    else:
        lines[1] = b'{"event":"action.approved",' + lines[1][1:]
    path.write_bytes(b"".join(lines))
    assert verify(path) == (False, 1, "line 2: not JSON")
    assert AuditLog._parse_record(lines[1]) is None


def test_valid_chain_still_verifies(tmp_path):
    path = tmp_path / "audit.jsonl"
    valid_lines(path)
    assert verify(path) == (True, 3, "ok")


def test_boolean_sequence_number_cannot_impersonate_one(tmp_path):
    path = tmp_path / "audit.jsonl"
    body = {"seq": True, "event": "action.requested"}
    prev = "0" * 64
    rec = {**body, "prev_hash": prev, "hash": chain_hash(prev, body)}
    path.write_text(canonical_json(rec) + "\n", encoding="utf-8")
    assert verify(path)[0] is False
    assert AuditLog._parse_record(path.read_bytes()) is None
