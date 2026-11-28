# SPDX-License-Identifier: Apache-2.0
"""Registry checks use real temporary catalog files and the gateway app-state store."""
from __future__ import annotations

import yaml

from conftest import AGENT, GUEST, OWNER



def declare_plugin(client, settings, clock, *, state="installed"):
    path = settings.apps_dir / "uptime-kuma" / "onemind.app.yaml"
    manifest = yaml.safe_load(path.read_text())
    manifest["spec"].update({
        "plugin": {"principal": True, "secret": "plugin-token", "backend": {"service": "app", "port": 8080}},
        "compat": {"onemind": ">=0.3 <1.0"},
        "permissions": ["nodes:read"],
        "extensions": {"tools": [{"name": "status", "title": "Status", "effect": "read", "description": "Read status",
                                   "input": {"type": "object", "additionalProperties": False}}]},
    })
    path.write_text(yaml.safe_dump(manifest))
    client.app.state.gateway.repo.set_app_state("uptime-kuma", state, clock.now)
    client.app.state.gateway.repo.set_runtime("uptime-kuma", clock.now, version="2.0.2")
    return path


def test_installed_registry_tracks_real_state(client, settings, clock):
    assert client.get("/v1/plugins", headers=OWNER).json() == []
    path = declare_plugin(client, settings, clock)
    row = client.get("/v1/plugins/uptime-kuma", headers=OWNER)
    assert row.status_code == 200
    body = row.json()
    slots = body.pop("slots")
    assert body == {"id": "uptime-kuma", "name": "Uptime Kuma", "installed_version": "2.0.2", "status": "installed"}
    assert [x["slot"] for x in slots] == ["home_tile", "map_layer", "settings_panel", "commands", "dock_item"]
    assert client.get("/v1/plugins", headers=OWNER).json() == [row.json()]
    manifest = yaml.safe_load(path.read_text())
    manifest["metadata"]["version"] = "2.0.0"
    path.write_text(yaml.safe_dump(manifest))
    assert client.get("/v1/plugins/uptime-kuma", headers=OWNER).json()["installed_version"] == "2.0.2"
    repo = client.app.state.gateway.repo
    repo.delete_runtime("uptime-kuma")
    assert client.get("/v1/plugins/uptime-kuma", headers=OWNER).json()["installed_version"] is None
    repo.set_app_state("uptime-kuma", "stopped", clock.now)
    assert client.get("/v1/plugins/uptime-kuma", headers=OWNER).json()["status"] == "stopped"
    repo.set_app_state("uptime-kuma", "failed", clock.now)
    assert client.get("/v1/plugins/uptime-kuma", headers=OWNER).json()["status"] == "failed"
    assert [r["status"] for r in client.get("/v1/plugins", headers=OWNER).json()] == ["failed"]
    for status in ("removed", "installing", "unknown", None):
        repo.set_app_state("uptime-kuma", status, clock.now)
        assert client.get("/v1/plugins", headers=OWNER).json() == []
        assert client.get("/v1/plugins/uptime-kuma", headers=OWNER).status_code == 404


def test_slots_show_the_five_places_from_the_manifest(client, settings, clock):
    path = declare_plugin(client, settings, clock)
    by = lambda: {x["slot"]: x for x in client.get("/v1/plugins/uptime-kuma", headers=OWNER).json()["slots"]}
    slots = by()
    assert slots["commands"] == {"slot": "commands", "declared": True, "names": ["status"], "approval": "none"}
    assert not slots["home_tile"]["declared"] and not slots["map_layer"]["declared"]
    manifest = yaml.safe_load(path.read_text())
    manifest["spec"]["extensions"]["widgets"] = [{"id": "overview"}]
    manifest["spec"]["extensions"]["tools"].append({"name": "run", "title": "Run", "effect": "write", "description": "Run",
                                                    "input": {"type": "object", "additionalProperties": False}})
    manifest["spec"]["mapLayers"] = [{"id": "lines", "title": "Lines", "source": "emits"}]
    path.write_text(yaml.safe_dump(manifest))
    slots = by()
    assert slots["home_tile"]["names"] == ["overview"] and slots["map_layer"]["names"] == ["lines"]
    assert slots["commands"]["approval"] == "each_time"


def test_registry_requires_authentication_and_preserves_sharing(client, settings, clock):
    declare_plugin(client, settings, clock)
    for route in ("/v1/plugins", "/v1/plugins/uptime-kuma"):
        assert client.get(route).status_code == 401
        for headers in (OWNER, GUEST, AGENT):
            assert client.get(route, headers=headers).status_code == 200
    client.app.state.gateway.app_filters.append(lambda request, p, app_id: p.is_owner)
    assert client.get("/v1/plugins", headers=GUEST).json() == []
    assert client.get("/v1/plugins/uptime-kuma", headers=GUEST).status_code == 404
    assert client.get("/v1/plugins/uptime-kuma", headers=OWNER).status_code == 200
    assert client.get("/v1/plugins/nonexistent", headers=OWNER).status_code == 404


def test_registry_never_exposes_raw_manifest(client, settings, clock):
    declare_plugin(client, settings, clock)
    response = client.get("/v1/plugins", headers=OWNER)
    assert response.status_code == 200
    assert not ({"secret", "backend", "permissions", "extensions", "dir"} & response.json()[0].keys())
    repo = client.app.state.gateway.repo
    repo.set_app_state("whoami", "installed", clock.now)
    assert [row["id"] for row in client.get("/v1/plugins", headers=OWNER).json()] == ["uptime-kuma"]
    assert client.get("/v1/plugins/whoami", headers=OWNER).status_code == 404


def test_identity_tokens_need_apps_read(settings, clock, executor):
    from fastapi.testclient import TestClient
    from onemind_core.app import create_app
    from test_identity import LOCAL_PEER, csrf, id_settings, setup_owner

    with TestClient(create_app(id_settings(settings), clock=clock, executor=executor), client=LOCAL_PEER) as client:
        setup_owner(client)
        declare_plugin(client, settings, clock)
        for scopes, expected in ((["apps:read"], 200), (["instance:read"], 403)):
            minted = client.post("/v1/tokens", json={"name": "registry-reader", "scopes": scopes}, headers=csrf(client))
            assert minted.status_code == 201, minted.text
            headers = {"Authorization": "Bearer " + minted.json()["one_time"]["token"]}
            for path in ("/v1/plugins", "/v1/plugins/uptime-kuma"):
                assert client.get(path, headers=headers).status_code == expected


def test_registry_does_not_activate_invalid_declarations(client, settings, clock):
    path = declare_plugin(client, settings, clock)
    manifest = yaml.safe_load(path.read_text())
    for invalid in (False, None):
        manifest["spec"]["plugin"]["principal"] = invalid
        path.write_text(yaml.safe_dump(manifest))
        assert client.get("/v1/plugins", headers=OWNER).json() == []
    manifest["spec"]["plugin"]["principal"] = True
    manifest["spec"]["extensions"]["tools"] = "not-a-list"
    path.write_text(yaml.safe_dump(manifest))
    assert client.get("/v1/plugins", headers=OWNER).json() == []


def test_registry_lists_installed_declarative_plugin_without_identity(client, settings, clock):
    path = declare_plugin(client, settings, clock)
    manifest = yaml.safe_load(path.read_text())
    manifest["spec"].pop("plugin")
    manifest["spec"]["extensions"] = {"tiles": [{"id": "open", "label": "Open", "opens": "web"}]}
    path.write_text(yaml.safe_dump(manifest))
    r = client.get("/v1/plugins/uptime-kuma", headers=OWNER)
    assert r.status_code == 200 and r.json()["status"] == "installed"


def test_registry_projects_installed_receipt_after_catalog_changes(client, settings, clock):
    from onemind_core.plugins.models import PluginInstallRow
    path = declare_plugin(client, settings, clock)
    manifest = yaml.safe_load(path.read_text())
    gw = client.app.state.gateway
    with gw.db.session.begin() as session:
        session.add(PluginInstallRow(app_id="uptime-kuma", secret_name="plugin-identity",
            bundle_sha256="sha256:" + "a" * 64, manifest=manifest))
    manifest["spec"].pop("plugin"); manifest["spec"].pop("extensions")
    manifest["metadata"]["name"] = "Catalog changed"
    path.write_text(yaml.safe_dump(manifest))
    r = client.get("/v1/plugins/uptime-kuma", headers=OWNER)
    assert r.status_code == 200 and r.json()["name"] == "Uptime Kuma"
