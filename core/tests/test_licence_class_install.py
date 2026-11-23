# SPDX-License-Identifier: Apache-2.0
"""#173: a licence class that is not green (blocked or unknown) installs only with the owner's explicit acceptance."""

import json

import pytest

from conftest import AGENT, OWNER, action_body, write_scan
from onemind_core.catalog import AppEntry

APP = "uptime-kuma"


def set_class(settings, value, app_id=APP):
    path = settings.apps_dir / app_id / "onemind.app.yaml"
    lines = [ln for ln in path.read_text().splitlines() if not ln.startswith("  licenceClass:")]
    if value is not None:
        i = next(n for n, ln in enumerate(lines) if ln.startswith("  license:"))
        lines.insert(i + 1, f"  licenceClass: {value}")
    path.write_text("\n".join(lines) + "\n")


def file_install(c, clock, key="k1"):
    r = c.post("/v1/actions", json=action_body(clock, app_id=APP, type_="app.install", key=key), headers=OWNER)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def approve(c, aid, **body):
    return c.post(f"/v1/actions/{aid}/approve", json=body or None, headers=OWNER)


def audit(settings):
    return [json.loads(line) for line in settings.audit_path.read_text().splitlines()]


@pytest.fixture
def scanned(settings, clock):
    write_scan(settings.apps_dir / APP, clock.now)


@pytest.mark.parametrize("cls", ["L1", "L2"])
def test_green_classes_install_on_an_ordinary_approval(settings, clock, scanned, client, executor, cls):
    set_class(settings, cls)
    r = approve(client, file_install(client, clock))
    assert r.status_code == 200 and r.json()["state"] == "succeeded", r.text
    assert executor.calls == [("app.install", APP)]
    assert not [e for e in audit(settings) if e["event"] == "app.licence_accepted"]


@pytest.mark.parametrize("cls", ["blocked", "unknown", None, "L3"])
def test_not_green_needs_the_owner_to_type_the_app_id(settings, clock, scanned, client, executor, cls):
    set_class(settings, cls)  # a missing or invalid class reads as unknown, never green
    aid = file_install(client, clock)
    r = approve(client, aid)
    assert r.status_code == 409 and r.json()["reason"] == "licence_unconfirmed", r.text
    r = approve(client, aid, accept_licence="uptime")
    assert r.status_code == 409 and r.json()["reason"] == "licence_unconfirmed"
    assert client.get(f"/v1/actions/{aid}", headers=OWNER).json()["state"] == "awaiting_approval"
    assert executor.calls == []
    r = approve(client, aid, accept_licence=APP)
    assert r.status_code == 200 and r.json()["state"] == "succeeded", r.text
    assert executor.calls == [("app.install", APP)]
    lines = audit(settings)
    (ok,) = [e for e in lines if e["event"] == "app.licence_accepted"]
    assert ok["action_id"] == aid and ok["data"]["licence_class"] == (cls if cls in ("blocked", "unknown") else "unknown")
    assert [e for e in lines if e["event"] == "authz.denied"][-1]["data"]["reason"] == "licence_unconfirmed"


def test_the_acceptance_changes_nothing_for_a_green_app(settings, clock, scanned, client, executor):
    set_class(settings, "L1")
    r = approve(client, file_install(client, clock), accept_licence=APP)
    assert r.status_code == 200 and executor.calls == [("app.install", APP)]


def test_the_acceptance_does_not_skip_the_scan(settings, clock, client, executor):
    set_class(settings, "unknown")
    write_scan(settings.apps_dir / APP, clock.now, result="fail")
    r = approve(client, file_install(client, clock), accept_licence=APP)
    assert r.status_code == 409 and "scan" in r.json()["message"]
    assert executor.calls == []


def test_an_agent_cannot_approve_a_not_green_install(settings, clock, scanned, client, executor):
    set_class(settings, "unknown")
    aid = file_install(client, clock)
    r = client.post(f"/v1/actions/{aid}/approve", json={"accept_licence": APP}, headers=AGENT)
    assert r.status_code == 403
    assert executor.calls == []


def test_catalog_lists_the_licence_class(settings, client):
    set_class(settings, "L2")
    rows = {r["id"]: r for r in client.get("/v1/apps", headers=OWNER).json()}
    assert rows[APP]["licence_class"] == "L2"
    set_class(settings, "nonsense")
    rows = {r["id"]: r for r in client.get("/v1/apps", headers=OWNER).json()}
    assert rows[APP]["licence_class"] == "unknown"


def test_entry_reads_a_missing_class_as_unknown(tmp_path):
    assert AppEntry("x", tmp_path, {"metadata": {}}).licence_class == "unknown"
    assert AppEntry("x", tmp_path, {}).licence_class == "unknown"
    assert AppEntry("x", tmp_path, {"metadata": {"licenceClass": "L2"}}).licence_class == "L2"
