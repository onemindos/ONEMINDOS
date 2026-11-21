# SPDX-License-Identifier: Apache-2.0
"""Offline: every checklist row the acceptance tests cite really is a row in ALPHA-CHECKLIST.md,
and the pure helpers behave. Needs no hub."""

from __future__ import annotations

import re
from pathlib import Path

from conftest import checklist_text, install_request, pick_app

HERE = Path(__file__).parent


def test_every_test_cites_a_real_checklist_row():
    src = (HERE / "test_acceptance.py").read_text(encoding="utf-8")
    consts = dict(re.findall(r'^([A-Z]+) = "([^"]+)"$', src, re.M))
    rows = {m.strip() for m in re.findall(r"^\| ([^|]+?) \|", checklist_text(), re.M)}
    assert consts
    for name, row in consts.items():
        if name == "UNAUTH_PATHS":
            continue
        assert row in rows, f"{name}: {row!r} is not a row of docs/leap/ALPHA-CHECKLIST.md"
    tests = re.findall(r"^@cites\((\w+)\)\ndef (test_\w+)", src, re.M)
    defs = re.findall(r"^def (test_\w+)", src, re.M)
    assert len(tests) == len(defs), "every test needs a @cites(...)"
    assert all(c in consts for c, _ in tests)


def test_pick_app_prefers_the_named_then_the_first_free():
    apps = [{"id": "a", "installed": True, "status": "installed"},
            {"id": "b", "installed": False, "status": "not_installed"}]
    assert pick_app(apps, None) == "b"
    assert pick_app(apps, "a") == "a"
    assert pick_app([apps[0]], None) is None


def test_install_request_shape():
    r = install_request("x", "t")
    assert r["type"] == "app.install" and r["params"] == {"app_id": "x"}
    assert r["idempotency_key"].startswith("accept-t-") and r["expires_at"].endswith("Z")
    assert install_request("x", "t")["idempotency_key"] != r["idempotency_key"]
