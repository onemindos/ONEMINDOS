# SPDX-License-Identifier: Apache-2.0
"""Write-path regression: group-committed audit log and WAL ledger (lab finding, perf fixture)."""
import os
import threading
import time
from datetime import UTC, datetime

from onemind_core import audit as audit_mod
from onemind_core.audit import AuditLog, verify
from onemind_core.ledger import make_engine


def _clock():
    return datetime(2026, 11, 21, tzinfo=UTC)


def test_concurrent_appends_share_fsyncs_and_chain_stays_valid(tmp_path, monkeypatch):
    real = os.fsync
    calls = []

    def slow_fsync(fd):  # a slow disk: the case the lab hit
        calls.append(1)
        time.sleep(0.05)
        real(fd)

    monkeypatch.setattr(audit_mod.os, "fsync", slow_fsync)
    log = AuditLog(tmp_path / "audit.jsonl", _clock)
    calls.clear()
    threads_n, per = 8, 10
    ts = [threading.Thread(target=lambda: [log.append("x", None, None, {}) for _ in range(per)])
          for _ in range(threads_n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    total = threads_n * per
    assert verify(tmp_path / "audit.jsonl") == (True, total, "ok")
    assert len(calls) < total * 0.75  # grouped: clearly fewer fsyncs than lines (one per line before)


def test_each_append_is_durable_before_it_returns(tmp_path, monkeypatch):
    synced = []
    real = os.fsync
    monkeypatch.setattr(audit_mod.os, "fsync", lambda fd: (synced.append(1), real(fd)))
    log = AuditLog(tmp_path / "audit.jsonl", _clock)
    synced.clear()
    log.append("a")
    assert len(synced) == 1
    log.append("b")
    assert len(synced) == 2  # a lone writer still syncs every line


def test_sqlite_ledger_uses_wal(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/ledger.db")
    with engine.connect() as c:
        assert c.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert c.exec_driver_sql("PRAGMA synchronous").scalar() == 2  # FULL
    engine.dispose()


def test_sqlite_ledger_waits_for_a_writer_instead_of_failing_fast(tmp_path):
    # SQLite's default lock wait is 5 s; a loaded box can hold a write longer (seen in CI, 2026-11-28).
    engine = make_engine(f"sqlite:///{tmp_path}/ledger.db")
    with engine.connect() as c:
        assert c.exec_driver_sql("PRAGMA busy_timeout").scalar() >= 30_000  # milliseconds
    engine.dispose()
