# SPDX-License-Identifier: Apache-2.0
"""#364: GET /v1/audit/verify never returns a cached "ok" for a log that changed.

AuditReader.verify cached a full check keyed on (size, mtime). A same-size change inside one kernel
tick (4 ms on Debian arm64) keeps both, so verify() could keep reporting the old "ok" for a tampered
log. The key is now filesig.cache_signature: a log whose ctime is younger than the racy window is
verified again on every call, and only a settled log is cached.

"Same tick" is made deterministic: the tamper keeps the size and puts mtime back (what a rewrite
inside one tick looks like to stat). ctime cannot be set from user space.
"""

import json
import os
import time
from datetime import UTC, datetime

from onemind_core import auditread, filesig
from onemind_core.audit import GENESIS, canonical_json, chain_hash
from onemind_core.auditread import AuditReader


def write_log(p, events):
    prev, lines = GENESIS, []
    for i, ev in enumerate(events, 1):
        body = {"seq": i, "event": ev, "actor": "owner"}
        h = chain_hash(prev, body)
        lines.append(canonical_json({**body, "prev_hash": prev, "hash": h}))
        prev = h
    p.write_text("\n".join(lines) + "\n")


def reader(p):
    return AuditReader(p, lambda: datetime(2026, 11, 19, tzinfo=UTC), lambda _id: set())


def same_tick_tamper(p, old, new):
    assert len(old) == len(new)
    st = p.stat()
    p.write_text(p.read_text().replace(old, new, 1))
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert (p.stat().st_size, p.stat().st_mtime_ns) == (st.st_size, st.st_mtime_ns)


def test_same_size_same_tick_tamper_is_reported(tmp_path):
    p = tmp_path / "audit.jsonl"
    write_log(p, ["app.install", "app.remove"])
    r = reader(p)
    assert r.verify()["ok"] is True
    same_tick_tamper(p, '"app.remove"', '"app.rem0ve"')
    v = r.verify()                       # the (size, mtime) cache returned the old "ok"
    assert v["ok"] is False and v["first_bad_seq"] == 2


def test_a_settled_log_is_verified_once(tmp_path, monkeypatch):
    monkeypatch.setattr(filesig, "RACY_WINDOW_NS", 50_000_000)
    p = tmp_path / "audit.jsonl"
    write_log(p, ["app.install"])
    time.sleep(0.1)
    calls = []
    real = auditread.verify_file
    monkeypatch.setattr(auditread, "verify_file", lambda *a: (calls.append(1), real(*a))[1])
    r = reader(p)
    assert r.verify()["ok"] and r.verify()["ok"] and r.verify()["ok"]
    assert len(calls) == 1


def test_a_fresh_log_is_verified_every_time(tmp_path, monkeypatch):
    p = tmp_path / "audit.jsonl"
    write_log(p, ["app.install"])
    calls = []
    real = auditread.verify_file
    monkeypatch.setattr(auditread, "verify_file", lambda *a: (calls.append(1), real(*a))[1])
    r = reader(p)
    r.verify(); r.verify()
    assert len(calls) == 2


def test_a_missing_log_is_not_cached(tmp_path):
    p = tmp_path / "audit.jsonl"
    r = reader(p)
    assert r.verify()["records"] == 0
    write_log(p, ["app.install"])
    assert r.verify()["records"] == 1
    assert json.loads(p.read_text().splitlines()[0])["seq"] == 1
