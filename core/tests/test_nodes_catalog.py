"""Contract §2/§3 nodes (registry, staleness) and §3/§4 apps (catalog)."""

import json
from pathlib import Path

import pytest

from conftest import AGENT, GUEST, OWNER, make_client
from onemind_core.catalog import Catalog, builtin_check
from onemind_core.nodes import NodeRegistry


def heartbeat(node_id="3f9c2a1b7d4e", **extra):
    hb = {
        "schema": "onemind.node.status/v1",
        "node_id": node_id,
        "hostname": "beelink",
        "role": "hub",
        "board": "x86_64-efi",
        "arch": "amd64",
        "os": {"id": "debian", "version_id": "13", "pretty": "Debian GNU/Linux 13 (trixie)"},
        "kernel": "6.12.0-amd64",
        "cpus": 4,
        "k3s": {"present": True, "role": "server", "ready": True},
        "rauc": {"present": False, "booted_slot": None, "slots": []},
        "agent_version": "0.1.0",
        "observed_at": "2026-11-11T22:00:00Z",
    }
    hb.update(extra)
    return json.dumps(hb).encode()


def test_nodes_empty_when_nats_down(client):
    # conftest runs with NATS disabled; the gateway still serves an empty list.
    r = client.get("/v1/nodes", headers=GUEST)
    assert r.status_code == 200 and r.json() == []


def test_nodes_with_unreachable_nats_url_still_serves(settings, clock):
    with make_client(settings, clock, nats_url="nats://127.0.0.1:1") as c:
        assert c.get("/v1/nodes", headers=OWNER).json() == []
        assert c.get("/healthz").json() == {"ok": True}


def test_node_status_online_stale_offline(client, clock):
    reg = client.app.state.registry
    assert reg.ingest("onemind.node.3f9c2a1b7d4e.status", heartbeat())
    n = client.get("/v1/nodes/3f9c2a1b7d4e", headers=AGENT).json()
    assert n["status"] == "online" and n["last_seen"] == "2026-11-11T22:00:00Z"
    assert n["board"] == "x86_64-efi"
    clock.advance(30)
    assert client.get("/v1/nodes", headers=OWNER).json()[0]["status"] == "online"
    clock.advance(1)
    assert client.get("/v1/nodes", headers=OWNER).json()[0]["status"] == "stale"
    clock.advance(89)
    assert client.get("/v1/nodes", headers=OWNER).json()[0]["status"] == "stale"
    clock.advance(1)
    assert client.get("/v1/nodes", headers=OWNER).json()[0]["status"] == "offline"
    reg.ingest("onemind.node.3f9c2a1b7d4e.status", heartbeat())
    assert client.get("/v1/nodes", headers=OWNER).json()[0]["status"] == "online"


def test_get_unknown_node_404(client):
    r = client.get("/v1/nodes/nope", headers=OWNER)
    assert r.status_code == 404 and r.json()["error"] == "not_found"


@pytest.mark.parametrize(
    "subject,data",
    [
        ("onemind.node.aaa.status", heartbeat("bbb")),           # node_id != subject
        ("onemind.node.aaa.status", b"not json"),
        ("onemind.node.aaa.status", json.dumps({"node_id": "aaa"}).encode()),  # no schema
        ("onemind.node.a.b.status", heartbeat("a")),             # bad subject
        ("onemind.node.aaa.status", heartbeat("aaa", pad="x" * 70000)),  # too big
    ],
)
def test_bad_heartbeats_are_dropped(clock, subject, data):
    reg = NodeRegistry(clock)
    assert reg.ingest(subject, data) is False
    assert reg.list() == []


def test_forbidden_fields_are_stripped(clock):
    reg = NodeRegistry(clock)
    assert reg.ingest("onemind.node.n1.status", heartbeat("n1", mac_address="aa:bb", serial="X1", status="online"))
    n = reg.get("n1")
    assert "mac_address" not in n and "serial" not in n
    assert n["status"] == "online"


# ---- apps ------------------------------------------------------------------------------

CATALOG_KEYS = {
    "id", "name", "version", "description", "category", "icon", "license", "source",
    "archs", "requires", "web_port", "installed", "status", "data_kept",
    "links", "tier", "scan",  # §11.4
}
VALID_APPS = {"uptime-kuma", "whoami", "hermes-like"}


def test_apps_catalog_shape(client):
    r = client.get("/v1/apps", headers=GUEST)
    assert r.status_code == 200
    apps = {a["id"]: a for a in r.json()}
    assert set(apps) == VALID_APPS  # broken + wrong-folder are skipped
    ku = apps["uptime-kuma"]
    assert set(ku) == CATALOG_KEYS
    assert ku["version"] == "2.0.2" and ku["web_port"] == 3001
    assert ku["archs"] == ["amd64", "arm64"]
    assert ku["requires"] == {"gpu": False, "minMemoryMb": 256}
    assert ku["installed"] is False and ku["status"] == "not_installed"


@pytest.mark.parametrize("path", ["/v1/apps/uptime-kuma/icon"])
def test_no_routes_beyond_contract(client, path):
    # §12.15 adds GET /v1/apps/{id}; an open icon route would still break "only /healthz is open".
    assert client.get(path).status_code in (401, 404)
    assert client.get(path, headers=OWNER).status_code == 404


def test_catalog_reports_errors(settings):
    cat = Catalog(settings.apps_dir)
    apps = cat.load()
    assert set(apps) == VALID_APPS
    assert "broken" in cat.errors and "wrong-folder" in cat.errors
    assert cat.validation_mode == "builtin"


@pytest.mark.parametrize("bad", ["  requires: [gpu]\n", "  web: 3001\n"])
@pytest.mark.parametrize("use_schema", [False, True])
def test_malformed_spec_field_never_hides_the_market(client, settings, tmp_path, bad, use_schema):
    folder = settings.apps_dir / "odd"
    folder.mkdir()
    (folder / "onemind.app.yaml").write_text(
        "apiVersion: onemind.app/v1alpha1\nkind: App\nmetadata:\n  id: odd\n  name: Odd\n"
        "  version: '1'\nspec:\n  archs: [amd64]\n" + bad
    )
    if use_schema:  # a permissive schema lets the manifest through; summary() must still cope
        p = tmp_path / "schema.json"
        p.write_text(json.dumps({"type": "object"}))
        rows = [Catalog(settings.apps_dir, p).load()[a].summary() for a in ("odd", "whoami")]
        assert rows[0]["requires"] == {} and rows[0]["web_port"] is None
        return
    r = client.get("/v1/apps", headers=OWNER)
    assert r.status_code == 200
    assert {a["id"] for a in r.json()} == VALID_APPS
    cat = Catalog(settings.apps_dir)
    cat.load()
    assert any("must be a mapping" in e for e in cat.errors["odd"])


def test_catalog_missing_dir_is_empty(tmp_path):
    assert Catalog(tmp_path / "none").load() == {}


def test_catalog_uses_json_schema_when_present(settings, tmp_path):
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["apiVersion", "kind", "metadata", "spec"],
        "properties": {
            "metadata": {
                "type": "object",
                "required": ["id", "name", "version", "license"],
            }
        },
    }
    p = tmp_path / "schema.json"
    p.write_text(json.dumps(schema))
    cat = Catalog(settings.apps_dir, p)
    assert cat.validation_mode == "schema"
    apps = cat.load()
    # whoami has a license, uptime-kuma too; broken lacks name/version/license
    assert set(apps) == VALID_APPS
    assert any("license" in e or "name" in e for e in cat.errors["broken"])


def test_manifests_dir_cannot_escape_app_folder(settings):
    p = settings.apps_dir / "whoami" / "onemind.app.yaml"
    p.write_text(p.read_text() + "  manifests: ../../\n")
    entry = Catalog(settings.apps_dir).get("whoami")
    with pytest.raises(ValueError):
        entry.manifests_dir


def test_builtin_check_rejects_bad_ids():
    doc = {
        "apiVersion": "onemind.app/v1alpha1", "kind": "App",
        "metadata": {"id": "Bad_ID", "name": "x", "version": "1"},
        "spec": {"archs": ["amd64"]},
    }
    assert any("metadata.id" in e for e in builtin_check(doc))
