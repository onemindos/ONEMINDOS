# SPDX-License-Identifier: Apache-2.0
"""Passwords built in (#679): the real apps/_system/vaultwarden folder on the real signed list.

- the gateway's catalog takes it from apps/_system/ only because the signed list names it;
- a gate-failing (tier blocked) image never installs, built in or not;
- switching Passwords off is a stop, never a remove: the vault volume, settings and namespace stay,
  and nobody can remove it or delete its data.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
import yaml

from conftest import OWNER, ScriptedExecutor, make_client, write_scan
from onemind_core import systemlist
from onemind_core.appstore.service import AppStoreSettings
from onemind_core.catalog import Catalog
from test_appstore import request, run

REPO = Path(__file__).resolve().parents[2]
REAL = REPO / "apps" / systemlist.SYSTEM_DIR / "vaultwarden"
SIGNED = systemlist.load(systemlist.REPO_FILE)


def test_the_signed_list_makes_vaultwarden_a_container_built_in_that_can_be_switched_off():
    app = SIGNED.get("vaultwarden")
    assert app is not None and app.name == "Passwords"
    assert (app.klass, app.update, app.can_disable) == ("container", "own", True)


def test_the_real_catalog_takes_vaultwarden_from_the_system_folder():
    cat = Catalog(REPO / "apps", REPO / "sdk" / "schema" / "onemind.app.schema.json")
    cat.system_ids = SIGNED.ids
    apps = cat.load()
    assert "vaultwarden" in apps, cat.errors.get("vaultwarden")
    md = apps["vaultwarden"].manifest["metadata"]
    assert md["license"] == "AGPL-3.0" and md["source"] == "https://github.com/dani-garcia/vaultwarden"
    # without the signed list the same folder is refused: a manifest alone proves nothing
    bare = Catalog(REPO / "apps", REPO / "sdk" / "schema" / "onemind.app.schema.json")
    assert "vaultwarden" not in bare.load()
    assert "not on the signed system apps list" in bare.errors["vaultwarden"][0]


def _settings(settings, clock, tmp_path, tier: str | None):
    """The test's apps dir with a copy of the real folder and the real list row for vaultwarden."""
    dest = settings.apps_dir / systemlist.SYSTEM_DIR / "vaultwarden"
    shutil.copytree(REAL, dest)
    doc = yaml.safe_load((dest / "onemind.app.yaml").read_text())
    if tier is None:
        doc["metadata"].pop("tier", None)  # as if CI's gate had passed a fixed image
        write_scan(dest, clock.now - timedelta(hours=1))
    (dest / "onemind.app.yaml").write_text(yaml.safe_dump(doc))
    row = json.loads(systemlist.REPO_FILE.read_text())
    lst = tmp_path / "system-apps.json"
    lst.write_text(json.dumps({"schema": systemlist.SCHEMA, "apps": [r for r in row["apps"] if r["id"] == "vaultwarden"]}))
    lst.chmod(0o644)
    return replace(settings, sections={**settings.sections, "appstore": AppStoreSettings(system_apps_file=lst)})


def test_a_gate_failing_image_is_not_installed_even_as_a_built_in(settings, clock, tmp_path):
    s = _settings(settings, clock, tmp_path, tier="blocked")
    ex = ScriptedExecutor()
    with make_client(s, clock, ex) as c:
        r = run(c, clock, "app.install", {"app_id": "vaultwarden"})  # an owner asks and approves
        assert r.status_code == 409 and "tier blocked" in r.json()["message"], r.text
        assert ex.calls == []


@pytest.fixture
def ex():
    return ScriptedExecutor()


def test_switching_passwords_off_keeps_the_vault_and_it_can_never_be_removed(settings, clock, tmp_path, ex):
    s = _settings(settings, clock, tmp_path, tier=None)
    with make_client(s, clock, ex) as c:
        r = run(c, clock, "app.install", {"app_id": "vaultwarden"})
        assert r.status_code == 200 and r.json()["state"] == "succeeded", r.text
        store = c.app.state.appstore
        store.repo.set_settings("vaultwarden", {"signups": "invite-only"}, None, clock.now)

        r = run(c, clock, "app.disable", {"app_id": "vaultwarden"})
        assert r.status_code == 200 and r.json()["state"] == "succeeded", r.text
        # a stop, never a remove: the namespace and the vaultwarden-data volume are not touched
        assert [t for t, _ in ex.calls] == ["app.install", "app.stop"]
        assert store.repo.get_settings("vaultwarden")[0] == {"signups": "invite-only"}
        rows = {x["id"]: x for x in c.get("/v1/system-apps", headers=OWNER).json()}
        assert rows["vaultwarden"]["enabled"] is False and rows["vaultwarden"]["license"] == "AGPL-3.0"

        refused = request(c, clock, "app.remove", {"app_id": "vaultwarden"})
        assert refused.status_code == 409 and refused.json()["reason"] == "system_app_protected", refused.text
        erase = request(c, clock, "app.delete_data", {"app_id": "vaultwarden", "confirm": "vaultwarden"})
        assert erase.status_code == 409, erase.text

        r = run(c, clock, "app.enable", {"app_id": "vaultwarden"})
        assert r.status_code == 200 and r.json()["state"] == "succeeded", r.text
        assert [t for t, _ in ex.calls] == ["app.install", "app.stop", "app.start"]
