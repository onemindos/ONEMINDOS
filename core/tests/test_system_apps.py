# SPDX-License-Identifier: Apache-2.0
"""Built-in (system) apps: switch off, never uninstall (appstore/system.py, systemlist.py, refs #234)."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from conftest import AGENT, OWNER, ScriptedExecutor, make_client
from onemind_core import systemlist
from onemind_core.appstore.service import AppStoreSettings
from onemind_core.catalog import Catalog
from test_appstore import add_app, request, run

SYSTEM_SPEC = {"class": "container", "update": "own", "disable": "allowed", "keepDataOnDisable": True}


def write_list(path: Path, *rows) -> Path:
    path.write_text(json.dumps({"schema": systemlist.SCHEMA, "apps": list(rows)}))
    path.chmod(0o644)
    return path


def row(app_id, klass="container", disable="allowed", update="own"):
    return {"id": app_id, "name": app_id.title(), "class": klass, "update": update, "disable": disable}


def add_system_app(settings, clock, app_id="notebook", **spec_extra) -> Path:
    d = add_app(settings, clock, f"_system/{app_id}", **{"system": SYSTEM_SPEC, **spec_extra})
    doc = yaml.safe_load((d / "onemind.app.yaml").read_text())
    doc["metadata"]["id"] = app_id  # add_app wrote the folder name "_system/<id>" into the id
    (d / "onemind.app.yaml").write_text(yaml.safe_dump(doc))
    return d


@pytest.fixture
def sys_settings(settings, clock, tmp_path):
    add_system_app(settings, clock)
    lst = write_list(tmp_path / "system-apps.json", row("notebook"), row("files", "native", "never", "os"),
                     row("market", "native", "allowed", "os"))  # the file lies about market: code wins
    return replace(settings, sections={**settings.sections, "appstore": AppStoreSettings(system_apps_file=lst)})


@pytest.fixture
def ex():
    return ScriptedExecutor()


@pytest.fixture
def c(sys_settings, clock, ex):
    with make_client(sys_settings, clock, ex) as client:
        yield client


def install(c, clock, app_id="notebook"):
    r = run(c, clock, "app.install", {"app_id": app_id})
    assert r.status_code == 200 and r.json()["state"] == "succeeded", r.text


def by_id(c, headers=OWNER):
    r = c.get("/v1/system-apps", headers=headers)
    assert r.status_code == 200, r.text
    return {x["id"]: x for x in r.json()}


# ---- the signed list is the only authority ---------------------------------------------------------

def test_system_app_in_system_folder_on_the_list_is_in_the_catalog_and_listed(c, clock):
    assert "notebook" in {a["id"] for a in c.get("/v1/apps", headers=OWNER).json()}
    rows = by_id(c)
    assert rows["notebook"]["enabled"] and rows["notebook"]["can_disable"] and rows["notebook"]["kind"] == "container"
    assert rows["notebook"]["version"] == "1.0.0" and rows["notebook"]["license"] == "MIT"
    assert rows["files"]["can_disable"] is False and rows["files"]["status"] is None


def test_third_party_manifest_claiming_system_is_rejected(sys_settings, clock):
    add_app(sys_settings, clock, "sneaky", system=SYSTEM_SPEC)            # in apps/, not apps/_system/
    add_system_app(sys_settings, clock, "unlisted")                       # in _system/, not on the list
    with make_client(sys_settings, clock, ScriptedExecutor()) as c:
        ids = {a["id"] for a in c.get("/v1/apps", headers=OWNER).json()}
        assert "sneaky" not in ids and "unlisted" not in ids
    cat = Catalog(sys_settings.apps_dir)
    cat.system_ids = lambda: frozenset({"notebook"})
    cat.load()
    assert "spec.system" in cat.errors["sneaky"][0]
    assert "not on the signed system apps list" in cat.errors["unlisted"][0]


def test_a_source_manifest_claiming_system_fails_validation(sys_settings):
    cat = Catalog(sys_settings.apps_dir)
    doc = {"apiVersion": "onemind.app/v1alpha1", "kind": "App", "metadata": {"id": "x", "name": "X", "version": "1"},
           "spec": {"system": SYSTEM_SPEC}}
    assert any("spec.system" in e for e in cat.validate(doc))


def test_id_reserved_by_the_list_cannot_be_used_by_an_ordinary_app(sys_settings, clock):
    add_app(sys_settings, clock, "market")
    with make_client(sys_settings, clock, ScriptedExecutor()) as c:
        assert "market" not in {a["id"] for a in c.get("/v1/apps", headers=OWNER).json()}


def test_list_file_that_others_can_write_is_refused(tmp_path):
    p = write_list(tmp_path / "l.json", row("notebook"))
    assert systemlist.load(p).ids() == {"notebook"}
    os.chmod(p, 0o666)
    assert systemlist.load(p).ids() == frozenset()


@pytest.mark.parametrize("doc", [
    {"schema": "x", "apps": []}, {"schema": systemlist.SCHEMA, "apps": [{"id": "A b"}]},
    {"schema": systemlist.SCHEMA, "apps": [row("a"), row("a")]},
    {"schema": systemlist.SCHEMA, "apps": [{**row("a"), "disable": "sometimes"}]},
])
def test_bad_list_documents_are_rejected(doc):
    with pytest.raises(systemlist.SystemListError):
        systemlist.parse(doc)


def test_the_image_list_names_the_four_that_stay_on():
    lst = systemlist.parse(json.loads(systemlist.REPO_FILE.read_text()))
    assert {"files", "approvals", "settings", "market"} <= lst.ids()
    assert all(not lst.get(i).can_disable for i in systemlist.NEVER_DISABLE if lst.get(i))


# ---- disable and enable ------------------------------------------------------------------------------

def test_disable_scales_to_zero_keeps_data_and_hides_the_app(c, clock, ex, sys_settings):
    install(c, clock)
    store = c.app.state.appstore
    store.repo.set_settings("notebook", {"theme": "dark"}, None, clock.now)
    r = run(c, clock, "app.disable", {"app_id": "notebook"})
    assert r.status_code == 200 and r.json()["state"] == "succeeded", r.text
    # a stop, never a remove: the namespace, volumes and secrets are never deleted
    assert [t for t, _ in ex.calls] == ["app.install", "app.stop"]
    assert store.repo.get_settings("notebook")[0] == {"theme": "dark"}
    row_ = by_id(c)["notebook"]
    assert row_["enabled"] is False and row_["status"] == "stopped" and row_["disabled_at"]
    # hidden from the list everyone (dock, search, phone, MCP) reads
    assert "notebook" not in {a["id"] for a in c.get("/v1/apps", headers=OWNER).json()}
    # and its routes say why
    for path in ("settings", "dependencies", "exposure"):
        g = c.get(f"/v1/apps/notebook/{path}", headers=OWNER)
        assert g.status_code == 409 and g.json()["reason"] == "app_disabled", g.text


def test_a_switched_off_app_cannot_be_started_or_configured_until_enabled(c, clock, ex):
    install(c, clock)
    run(c, clock, "app.disable", {"app_id": "notebook"})
    r = request(c, clock, "app.start", {"app_id": "notebook"})
    assert r.status_code == 409 and r.json()["reason"] == "app_disabled", r.text
    for t in ("app.restart", "app.update"):  # the stopped state already refuses these
        assert request(c, clock, t, {"app_id": "notebook"}).status_code == 409, t
    again = request(c, clock, "app.disable", {"app_id": "notebook"})
    assert again.status_code == 409 and again.json()["reason"] == "already_disabled"
    r = run(c, clock, "app.enable", {"app_id": "notebook"})
    assert r.status_code == 200 and r.json()["state"] == "succeeded", r.text
    assert [t for t, _ in ex.calls] == ["app.install", "app.stop", "app.start"]
    assert by_id(c)["notebook"]["enabled"] and by_id(c)["notebook"]["status"] == "installed"
    assert "notebook" in {a["id"] for a in c.get("/v1/apps", headers=OWNER).json()}
    assert c.get("/v1/apps/notebook/settings", headers=OWNER).status_code == 200


def test_failed_stop_leaves_the_app_on(sys_settings, clock):
    ex = ScriptedExecutor()
    with make_client(sys_settings, clock, ex) as c:
        install(c, clock)
        ex.outcome = "failed"
        r = run(c, clock, "app.disable", {"app_id": "notebook"})
        assert r.json()["state"] == "failed"
        assert by_id(c)["notebook"]["enabled"] is True


def test_disabling_a_native_app_only_flips_the_switch(sys_settings, clock, tmp_path, ex):
    lst = write_list(tmp_path / "n.json", row("photos", "native", "allowed", "os"))
    s = replace(sys_settings, sections={**sys_settings.sections, "appstore": AppStoreSettings(system_apps_file=lst)})
    with make_client(s, clock, ex) as c:
        r = run(c, clock, "app.disable", {"app_id": "photos"})
        assert r.json()["state"] == "succeeded" and ex.calls == []
        assert by_id(c)["photos"]["enabled"] is False
        assert run(c, clock, "app.enable", {"app_id": "photos"}).json()["state"] == "succeeded"


@pytest.mark.parametrize("app_id", ["files", "approvals", "settings", "market"])
def test_files_approvals_settings_and_market_cannot_be_switched_off(c, clock, app_id):
    r = request(c, clock, "app.disable", {"app_id": app_id})
    # approvals/settings are not on this test's list at all (404); files and market are, and still refused
    assert r.status_code in (404, 409), r.text
    if r.status_code == 409:
        assert r.json()["reason"] == "system_app_protected"


def test_an_app_that_is_not_a_system_app_cannot_be_disabled(c, clock):
    r = request(c, clock, "app.disable", {"app_id": "whoami"})
    assert r.status_code == 404


# ---- uninstall is refused for everyone ---------------------------------------------------------------

@pytest.mark.parametrize("who", [OWNER, AGENT])
@pytest.mark.parametrize("t", ["app.remove", "app.delete_data"])
def test_a_system_app_cannot_be_removed_by_owner_or_agent(c, clock, who, t):
    install(c, clock)
    params = {"app_id": "notebook", **({"confirm": "notebook"} if t == "app.delete_data" else {})}
    r = request(c, clock, t, params, headers=who)
    assert r.status_code in (403, 409), r.text
    if r.status_code == 409 and t == "app.remove":  # delete_data is refused by the app's state first
        assert r.json()["reason"] == "system_app_protected"


def test_owner_remove_is_409_with_the_reason(c, clock):
    install(c, clock)
    r = request(c, clock, "app.remove", {"app_id": "notebook"})
    assert r.status_code == 409 and r.json()["reason"] == "system_app_protected"


# ---- agents ask, owners decide ---------------------------------------------------------------------------

def test_an_agent_disable_waits_for_an_owner_and_cannot_be_approved_by_the_agent(c, clock, ex):
    install(c, clock)
    r = request(c, clock, "app.disable", {"app_id": "notebook"}, headers=AGENT)
    assert r.status_code == 201 and r.json()["state"] == "awaiting_approval", r.text
    assert c.post(f"/v1/actions/{r.json()['id']}/approve", headers=AGENT).status_code == 403
    assert by_id(c)["notebook"]["enabled"] is True and [t for t, _ in ex.calls] == ["app.install"]
    assert c.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER).json()["state"] == "succeeded"
    assert by_id(c)["notebook"]["enabled"] is False


def test_a_switched_off_app_leaves_the_home_dock(c, clock, ex):
    install(c, clock)
    got = c.get("/v1/me/home", headers=OWNER)
    doc = {**got.json(), "dock": ["app:notebook"]}
    saved = c.put("/v1/me/home", headers={**OWNER, "If-Match": got.headers["etag"]}, json=doc)
    assert saved.status_code == 200, saved.text
    assert "app:notebook" in c.get("/v1/me/home", headers=OWNER).json()["dock"]
    run(c, clock, "app.disable", {"app_id": "notebook"})
    assert "app:notebook" not in c.get("/v1/me/home", headers=OWNER).json()["dock"]
