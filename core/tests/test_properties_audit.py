# SPDX-License-Identifier: Apache-2.0
"""Property tests: the hash-chained audit log (contract §3 "Audit", onemind_core/audit.py).

What holds for every sequence of audit records Hypothesis generates:
- verify() accepts the file AuditLog wrote, and counts every line;
- a change to one record's content (a value, a key added or removed, its seq, prev_hash or hash),
  the removal of any record but the last, a swap or a duplicated record is reported at the first
  line that differs, with every earlier line counted as verified;
- after a one-character edit anywhere in the file, verify() either reports it or no record's
  content changed (for example 1e+16 written as 1E+16).

Malformed-record regressions cover findings F-AUD-1..3 without expected-failure markers.
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from hypothesis import assume
from hypothesis import given
from hypothesis import strategies as st

from onemind_core.audit import AuditLog, canonical_json, verify
from props import budget, json_values

EVENTS = st.sampled_from(
    ["action.requested", "action.awaiting_approval", "action.approved", "action.denied", "authz.denied",
     "gateway.started", "agent.principal.issued"]
) | st.text(min_size=1, max_size=20)
PRINCIPALS = st.none() | st.fixed_dictionaries({
    "id": st.text(min_size=1, max_size=12),
    "kind": st.sampled_from(["person", "agent"]),
    "role": st.sampled_from(["owner", "adult", "guest", "agent"]),
})
ENTRIES = st.lists(
    st.tuples(EVENTS, PRINCIPALS, st.none() | st.uuids().map(str),
              st.dictionaries(st.text(max_size=8), json_values, max_size=4)),
    min_size=1, max_size=8,
)


def write_log(path: Path, entries) -> list[str]:
    t = [datetime(2026, 11, 12, tzinfo=UTC)]

    def clock():
        t[0] += timedelta(seconds=1)
        return t[0]

    log = AuditLog(path, clock)
    for event, principal, action_id, data in entries:
        log.append(event, principal, action_id, data)
    # Split on "\n" only: lines may hold U+0085 or U+2028 raw, which str.splitlines() breaks on.
    return path.read_text(encoding="utf-8").split("\n")[:-1]


def check(lines: list[str]) -> tuple[bool, int, str]:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "audit.jsonl"
        p.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
        return verify(p)


def is_json(text: str) -> bool:
    try:
        json.loads(text)
    except ValueError:
        return False
    return True


def same(a: object, b: object) -> bool:
    """Equal as JSON (Python's == says 1 == 1.0 == True; the hash does not)."""
    return canonical_json(a) == canonical_json(b)


@budget(30)
@given(entries=ENTRIES)
def test_the_log_as_written_verifies(entries):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "audit.jsonl"
        lines = write_log(p, entries)
        assert verify(p) == (True, len(entries), "ok")
        assert [json.loads(line)["seq"] for line in lines] == list(range(1, len(entries) + 1))


# ---- one mutation, reported at the right line ------------------------------------------------

def edit_value(data, recs):
    i = data.draw(st.integers(0, len(recs) - 1), label="record")
    key = data.draw(st.sampled_from(sorted(recs[i])), label="key")
    new = data.draw(json_values, label="new value")
    assume(not same(new, recs[i][key]))
    recs[i][key] = new
    return recs, i


def drop_key(data, recs):
    i = data.draw(st.integers(0, len(recs) - 1), label="record")
    del recs[i][data.draw(st.sampled_from(sorted(recs[i])), label="key")]
    return recs, i


def add_key(data, recs):
    i = data.draw(st.integers(0, len(recs) - 1), label="record")
    key = data.draw(st.text(max_size=12).filter(lambda k: k not in recs[i]), label="key")
    recs[i][key] = data.draw(json_values, label="value")
    return recs, i


def delete_record(data, recs):
    assume(len(recs) >= 2)  # deleting the last record is the known gap below
    i = data.draw(st.integers(0, len(recs) - 2), label="record")
    del recs[i]
    return recs, i


def swap_records(data, recs):
    assume(len(recs) >= 2)
    i = data.draw(st.integers(0, len(recs) - 2), label="first")
    j = data.draw(st.integers(i + 1, len(recs) - 1), label="second")
    recs[i], recs[j] = recs[j], recs[i]
    return recs, i


def duplicate_record(data, recs):
    i = data.draw(st.integers(0, len(recs) - 1), label="record")
    recs.insert(i + 1, dict(recs[i]))
    return recs, i + 1


MUTATIONS = [edit_value, drop_key, add_key, delete_record, swap_records, duplicate_record]


@budget(120)
@given(entries=ENTRIES, mutation=st.sampled_from(MUTATIONS), data=st.data())
def test_any_record_mutation_is_reported_at_its_line(entries, mutation, data):
    with tempfile.TemporaryDirectory() as d:
        recs = [json.loads(line) for line in write_log(Path(d) / "audit.jsonl", entries)]
    recs, bad = mutation(data, recs)
    ok, verified, reason = check([canonical_json(r) for r in recs])
    assert not ok
    assert verified == bad, reason
    assert reason.startswith(f"line {bad + 1}:"), reason


@budget(40)
@given(entries=ENTRIES, data=st.data())
def test_a_line_that_is_not_json_is_reported_at_its_line(entries, data):
    with tempfile.TemporaryDirectory() as d:
        lines = write_log(Path(d) / "audit.jsonl", entries)
    i = data.draw(st.integers(0, len(lines) - 1), label="line")
    junk = data.draw(st.text(min_size=1).filter(lambda s: s.strip() and "\n" not in s and "\r" not in s))
    assume(not is_json(junk))  # valid JSON is covered by the edits and non-object regressions
    lines[i] = junk
    assert check(lines) == (False, i, f"line {i + 1}: not JSON")


@budget(120)
@given(entries=ENTRIES, data=st.data())
def test_a_one_character_edit_is_reported_or_changes_no_content(entries, data):
    with tempfile.TemporaryDirectory() as d:
        text = "\n".join(write_log(Path(d) / "audit.jsonl", entries))
    pos = data.draw(st.integers(0, len(text) - 1), label="position")
    char = data.draw(st.characters(codec="utf-8"), label="character")
    assume(char != text[pos])
    edited = text[:pos] + char + text[pos + 1:]
    ok, verified, reason = check(edited.split("\n"))
    if ok:  # nothing was reported, so nothing may have changed
        before = [json.loads(line) for line in text.split("\n")]
        after = [json.loads(line) for line in edited.split("\n") if line.strip()]
        assert len(after) == len(before) and all(same(a, b) for a, b in zip(after, before))


# ---- checkpoint limitation and malformed-record regressions ---------------------------------

def three_lines(tmp_path: Path) -> list[str]:
    return write_log(tmp_path / "audit.jsonl", [("action.requested", None, None, {"n": n}) for n in range(3)])


def test_removing_the_last_record_needs_a_checkpoint(tmp_path):
    """A hash chain alone cannot see its own tail cut off: the shorter file is a valid chain.

    Contract §12.16 (signed checkpoints, CORE-SEC-6) and the NATS copy of every line close this; this
    test documents the limit and shows the evidence a checkpoint compares: the last hash changes.
    """
    lines = three_lines(tmp_path)
    assert check(lines[:-1]) == (True, 2, "ok")
    assert json.loads(lines[-2])["hash"] != json.loads(lines[-1])["hash"]


def test_a_byte_that_is_not_utf8_is_reported(tmp_path):
    p = tmp_path / "audit.jsonl"
    three_lines(tmp_path)
    raw = bytearray(p.read_bytes())
    raw[20] = 0xFF
    p.write_bytes(bytes(raw))
    ok, verified, reason = verify(p)
    assert (ok, verified) == (False, 0) and reason.startswith("line 1:")


@pytest.mark.parametrize("line", ["[]", '"text"', "1", "null"])
def test_a_line_that_is_json_but_not_an_object_is_reported(tmp_path, line):
    lines = three_lines(tmp_path)
    lines[1] = line
    ok, verified, reason = check(lines)
    assert (ok, verified) == (False, 1) and reason.startswith("line 2:")


def test_a_duplicate_key_cannot_hide_a_forged_value(tmp_path):
    """Python's json keeps the last of two equal keys, so verify() hashes the real value while a
    reader that keeps the first one (several do) sees the forged event."""
    lines = three_lines(tmp_path)
    lines[1] = '{"event":"action.approved",' + lines[1][1:]
    assert check(lines)[0] is False


@pytest.mark.parametrize("bad", [b"[]", b'"text"', b"1", b"null", b"\xff",
                               b'{"event":"forged","event":"real"}',
                               b'{"data":{"key":1,"key":2}}'])
def test_resume_rejects_the_same_ambiguous_records(bad):
    assert AuditLog._parse_record(bad) is None


def test_invalid_utf8_reports_the_verified_prefix(tmp_path):
    p = tmp_path / "audit.jsonl"
    lines = three_lines(tmp_path)
    p.write_bytes(lines[0].encode() + b"\n\xff\n" + lines[2].encode() + b"\n")
    assert verify(p) == (False, 1, "line 2: not JSON")
