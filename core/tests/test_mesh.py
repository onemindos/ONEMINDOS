# SPDX-License-Identifier: Apache-2.0
"""mesh.py against a fake Headscale that speaks the v0.29.7 REST shapes (no real coordinator)."""

from __future__ import annotations

import json
import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from onemind_core import mesh
from onemind_core.audit import AuditLog, verify
from onemind_core.ledger import Action
from onemind_core.mesh import (
    HeadscaleClient, HeadscaleError, MeshPerson, MeshRefused, MeshService, read_api_key_file, render_policy,
)

NOW = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)
BASE = "http://127.0.0.1:8085"


class FakeHeadscale:
    """Just enough of Headscale's /api/v1 to exercise the client. Keys are made at test time."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.users: dict[str, dict] = {}
        self.keys: dict[str, dict] = {}
        self.nodes: dict[str, dict] = {}
        self.pending: dict[str, str] = {}  # auth id -> node name
        self.policy = ""
        self.reject_policy = False
        self.calls: list[tuple[str, str, dict | None]] = []
        self.down = False
        self._n = 0

    def _id(self) -> str:
        self._n += 1
        return str(self._n)

    def __call__(self, method, url, headers, body, timeout):
        if self.down:
            raise ConnectionRefusedError("down")
        parts = urlsplit(url)
        assert parts.path.startswith("/api/v1/"), parts.path
        path, query = parts.path[len("/api/v1"):], parse_qs(parts.query)
        data = json.loads(body) if body else None
        self.calls.append((method, path, data))
        if headers.get("Authorization") != f"Bearer {self.api_key}":
            return 401, b'{"message":"Unauthorized"}'

        def ok(obj):
            return 200, json.dumps(obj).encode()

        if (method, path) == ("GET", "/health"):
            return ok({"databaseConnectivity": True})
        if (method, path) == ("GET", "/user"):
            name = query.get("name", [None])[0]
            return ok({"users": [u for u in self.users.values() if name in (None, u["name"])]})
        if (method, path) == ("POST", "/user"):
            if data["name"] in {u["name"] for u in self.users.values()}:
                return 400, b'{"message":"user already exists"}'
            uid = self._id()
            self.users[uid] = {"id": uid, "name": data["name"]}
            return ok({"user": self.users[uid]})
        if (method, path) == ("POST", "/preauthkey"):
            assert set(data) == {"user", "reusable", "ephemeral", "expiration", "aclTags"}
            if data["user"] not in self.users:
                return 404, b'{"message":"user not found"}'
            kid = self._id()
            self.keys[kid] = {"id": kid, "key": secrets.token_hex(24), "user": self.users[data["user"]],
                              "reusable": data["reusable"], "ephemeral": data["ephemeral"], "used": False,
                              "expiration": data["expiration"], "aclTags": data["aclTags"]}
            return ok({"preAuthKey": self.keys[kid]})
        if (method, path) == ("POST", "/preauthkey/expire"):
            assert set(data) == {"id"}
            self.keys[data["id"]]["expiration"] = "1970-01-01T00:00:00Z"
            return ok({})
        if (method, path) == ("GET", "/preauthkey"):
            return ok({"preAuthKeys": list(self.keys.values())})
        if (method, path) == ("GET", "/node"):
            return ok({"nodes": list(self.nodes.values())})
        if method == "DELETE" and path.startswith("/node/"):
            self.nodes.pop(path.split("/")[2], None)
            return ok({})
        if method == "POST" and path.startswith("/node/") and path.endswith("/tags"):
            node = self.nodes[path.split("/")[2]]
            node["tags"] = data["tags"]
            return ok({"node": node})
        if (method, path) == ("POST", "/auth/register"):
            name = self.pending.pop(data["authId"], None)
            if name is None:
                return 404, json.dumps({"message": f"no pending registration {data['authId']}"}).encode()
            return ok({"node": self.add_node(name, user=data["user"])})
        if (method, path) == ("POST", "/policy/check"):
            if self.reject_policy:
                return 400, b'{"message":"policy: unknown group"}'
            json.loads(data["policy"])
            return ok({})
        if (method, path) == ("PUT", "/policy"):
            self.policy = data["policy"]
            return ok({"policy": self.policy})
        if (method, path) == ("GET", "/policy"):
            return ok({"policy": self.policy})
        return 404, b'{"message":"not found"}'

    def add_node(self, name, *, key_id=None, tags=(), user=None):
        nid = self._id()
        node = {"id": nid, "givenName": name, "name": name, "tags": list(tags), "online": True,
                "ipAddresses": ["100.64.0.2"], "user": {"name": user} if user else None}
        if key_id is not None:
            node["preAuthKey"] = {"id": key_id}
            self.keys[key_id]["used"] = True
        self.nodes[nid] = node
        return node


@pytest.fixture
def api_key():
    return secrets.token_urlsafe(32)


@pytest.fixture
def hs(api_key):
    return FakeHeadscale(api_key)


@pytest.fixture
def audit(tmp_path):
    return AuditLog(tmp_path / "audit.jsonl", lambda: NOW)


@pytest.fixture
def service(hs, api_key, audit):
    return MeshService(HeadscaleClient(BASE, api_key, transport=hs), audit, lambda: NOW)


def action(type_="node.join", state="accepted", params=None, decided_by=None, aid="a1"):
    return Action(
        id=aid, type=type_, params=params if params is not None else {"node_id": "abc123def456", "role": "worker"},
        state=state, requested_by={"id": "owner", "kind": "person"}, idempotency_key=aid,
        created_at=NOW, updated_at=NOW, expires_at=NOW + timedelta(minutes=10),
        decided_by={"id": "owner", "kind": "person", "role": "owner"} if decided_by is None else decided_by,
    )


def audit_text(tmp_path) -> str:
    return (tmp_path / "audit.jsonl").read_text()


# ---- client ------------------------------------------------------------------------------------
def test_client_pins_version_and_refuses_non_loopback(api_key, hs):
    assert mesh.HEADSCALE_VERSION == "0.29.7" and mesh.HEADSCALE_API_PREFIX == "/api/v1"
    for url in ("http://192.0.2.10:8085", "https://control.onemind.internal", "ftp://127.0.0.1"):
        with pytest.raises(ValueError):
            HeadscaleClient(url, api_key, transport=hs)
    c = HeadscaleClient("http://[::1]:8085", api_key, transport=hs)
    assert api_key not in repr(c)
    assert c.health() is True


def test_api_key_file_must_be_private(tmp_path, api_key):
    f = tmp_path / "headscale.key"
    f.write_text(api_key + "\n")
    os.chmod(f, 0o644)
    with pytest.raises(PermissionError):
        read_api_key_file(f)
    os.chmod(f, 0o600)
    assert read_api_key_file(f) == api_key


def test_errors_are_scrubbed_and_unreachable_is_reported(hs, api_key):
    def echo_key(method, url, headers, body, timeout):
        return 500, json.dumps({"message": f"bad token {api_key}"}).encode()

    with pytest.raises(HeadscaleError) as e:
        HeadscaleClient(BASE, api_key, transport=echo_key).health()
    assert api_key not in str(e.value) and "[redacted]" in str(e.value)
    hs.down = True
    with pytest.raises(HeadscaleError) as e:
        HeadscaleClient(BASE, api_key, transport=hs).health()
    assert e.value.status is None


def test_wrong_api_key_is_401(hs):
    with pytest.raises(HeadscaleError) as e:
        HeadscaleClient(BASE, secrets.token_urlsafe(32), transport=hs).list_nodes()
    assert e.value.status == 401


# ---- minting --------------------------------------------------------------------------------------
def test_mint_join_key_single_use_tagged_15_minutes(service, hs, tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    minted = service.mint_join_key(action())
    raw = hs.keys[minted.key_id]
    assert minted.key == raw["key"] and minted.key not in repr(minted)
    assert raw["reusable"] is False and raw["ephemeral"] is False
    assert raw["aclTags"] == ["tag:onemind-worker", "tag:onemind-k3s"]
    assert raw["expiration"] == "2026-11-12T09:15:00Z"
    assert raw["user"]["name"] == mesh.MACHINES_USER
    log = audit_text(tmp_path)
    assert minted.key not in log and minted.key not in caplog.text
    assert '"event":"mesh.key.minted"' in log and '"approved_by":"owner"' in log
    assert verify(tmp_path / "audit.jsonl")[0]


@pytest.mark.parametrize("role,tags", [("leaf", ["tag:onemind-leaf"]), ("worker", ["tag:onemind-worker", "tag:onemind-k3s"])])
def test_role_tags(service, hs, role, tags):
    minted = service.mint_join_key(action(params={"node_id": "n1", "role": role}))
    assert hs.keys[minted.key_id]["aclTags"] == tags


@pytest.mark.parametrize("a", [
    action(state="awaiting_approval"),
    action(state="requested"),
    action(state="cancelled"),
    action(type_="app.install"),
    action(decided_by={"id": "hermes", "kind": "agent", "role": "agent"}),
    action(decided_by={"id": "kid", "kind": "person", "role": "adult"}),
    action(params={"node_id": "abc", "role": "owner"}),
    action(params={"node_id": "abc", "role": "hub"}),  # the hub enrolls itself (§5.2), never via join
    action(params={"node_id": "../x", "role": "worker"}),
])
def test_mint_refused_without_owner_approved_join(service, hs, a):
    with pytest.raises(MeshRefused):
        service.mint_join_key(a)
    assert hs.keys == {}


def test_one_key_per_approval(service, hs):
    service.mint_join_key(action())
    with pytest.raises(MeshRefused):
        service.mint_join_key(action())
    assert len(hs.keys) == 1


def test_failed_mint_is_audited_and_can_retry(service, hs, tmp_path):
    hs.down = True
    with pytest.raises(HeadscaleError):
        service.mint_join_key(action())
    assert '"event":"mesh.key.mint_failed"' in audit_text(tmp_path)
    hs.down = False
    assert service.mint_join_key(action()).key


def test_device_key_untagged_in_person_user(service, hs, tmp_path):
    minted = service.mint_device_key(action("mesh.device.add", params={"person_id": "ab12"}, aid="d1"))
    raw = hs.keys[minted.key_id]
    assert raw["aclTags"] == [] and raw["user"]["name"] == "person-ab12"
    assert raw["expiration"] == "2026-11-12T09:10:00Z"
    assert minted.key not in audit_text(tmp_path)


def test_register_pending_device(service, hs, tmp_path):
    auth_id = secrets.token_hex(12)
    hs.pending[auth_id] = "phone"
    node = service.register_device(action("mesh.device.add", params={"person_id": "ab12", "auth_id": auth_id}, aid="d2"))
    assert node.user == "person-ab12"
    assert '"event":"mesh.device.registered"' in audit_text(tmp_path)
    with pytest.raises(MeshRefused):
        service.register_device(action("mesh.device.add", params={"person_id": "ab12", "auth_id": "x"}, aid="d3"))


def test_expire_and_remove_are_audited(service, hs, tmp_path):
    minted = service.mint_join_key(action())
    service.expire_key(minted.key_id, reason="join cancelled", action_id="a1")
    assert hs.keys[minted.key_id]["expiration"].startswith("1970")
    node = hs.add_node("node-abc123def456", key_id=minted.key_id, tags=["tag:onemind-worker", "tag:onemind-k3s"])
    service.remove_node(node["id"], reason="node.remove")
    assert hs.nodes == {}
    log = audit_text(tmp_path)
    assert '"event":"mesh.key.expired"' in log and '"event":"mesh.node.removed"' in log
    with pytest.raises(MeshRefused):
        service.remove_node("1/../2", reason="x")


def test_check_join_binds_or_deletes(service, hs, tmp_path):
    a = action()
    minted = service.mint_join_key(a)
    assert service.check_join(minted.key_id, "abc123def456", "worker") is None
    hs.add_node("node-abc123def456", key_id=minted.key_id, tags=["tag:onemind-worker", "tag:onemind-k3s"])
    assert service.check_join(minted.key_id, "abc123def456", "worker").name == "node-abc123def456"
    # a node that used another key but claims a different name is deleted
    m2 = service.mint_join_key(action(aid="a2"))
    bad = hs.add_node("node-imposter", key_id=m2.key_id, tags=["tag:onemind-worker", "tag:onemind-k3s"])
    with pytest.raises(MeshRefused):
        service.check_join(m2.key_id, "abc123def456", "worker")
    assert bad["id"] not in hs.nodes
    assert '"event":"mesh.node.rejected"' in audit_text(tmp_path)


def test_set_role_retags(service, hs):
    node = hs.add_node("node-x", tags=["tag:onemind-worker", "tag:onemind-k3s"])
    assert service.set_role(node["id"], "leaf").tags == ("tag:onemind-leaf",)
    with pytest.raises(MeshRefused):
        service.set_role(node["id"], "hub")


# ---- policy -----------------------------------------------------------------------------------------
def test_render_policy_matches_design():
    doc = json.loads(render_policy([MeshPerson("owner", "owner"), MeshPerson("ab12", "adult"), MeshPerson("g1", "guest")]))
    assert doc["groups"] == {"group:adults": ["person-ab12@"], "group:guests": ["person-g1@"], "group:owners": ["person-owner@"]}
    assert all(v == [] for v in doc["tagOwners"].values()) and len(doc["tagOwners"]) == 4
    grants = {(tuple(g["src"]), tuple(g["dst"])): g["ip"] for g in doc["grants"]}
    assert grants[(("group:owners", "group:adults"), ("tag:onemind-hub",))] == ["tcp:443"]
    assert grants[(("tag:onemind-worker", "tag:onemind-leaf"), ("tag:onemind-hub",))] == ["tcp:443", "tcp:7422"]
    assert grants[(("tag:onemind-worker",), ("tag:onemind-hub",))] == ["tcp:6443", "tcp:8443"]  # 8443: agent pods (H-05)
    assert grants[(("tag:onemind-k3s",), ("tag:onemind-k3s",))] == ["tcp:10250", "udp:51820"]
    # guests reach nothing; no node port is granted to people; no SSH unless enabled
    flat = json.dumps(doc["grants"])
    assert "group:guests" not in flat and "tcp:22" not in flat
    assert all("tcp:7422" not in g["ip"] for g in doc["grants"] if "group:owners" in g["src"])
    assert "autoApprovers" not in doc
    assert "tcp:22" in render_policy([], owner_ssh=True)


def test_render_policy_is_deterministic_and_refuses_bad_people():
    a = render_policy([MeshPerson("b", "adult"), MeshPerson("a", "adult")])
    assert a == render_policy([MeshPerson("a", "adult"), MeshPerson("b", "adult")])
    for bad in (MeshPerson("agent:hermes", "adult"), MeshPerson("x", "agent"), MeshPerson("Bob@x", "owner")):
        with pytest.raises(MeshRefused):
            render_policy([bad])


def test_push_policy_checks_first(service, hs, tmp_path):
    digest = service.push_policy([MeshPerson("owner", "owner")])
    assert hs.policy and len(digest) == 64
    assert [c[1] for c in hs.calls[-2:]] == ["/policy/check", "/policy"]
    hs.reject_policy, before = True, hs.policy
    with pytest.raises(HeadscaleError):
        service.push_policy([MeshPerson("owner", "owner")], owner_ssh=True)
    assert hs.policy == before
    log = audit_text(tmp_path)
    assert '"event":"mesh.policy.applied"' in log and '"event":"mesh.policy_rejected"' in log


# ---- the mesh mounted in the gateway (CORE-NET-8, #876) -------------------------------------------------
# The owner's mesh state lives in the settings store (table mesh_state). The fake Headscale stands in
# for the coordinator; the box CA lives in the test's tls directory.
from dataclasses import replace  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

import onemind_core.routers.net as net_router  # noqa: E402
from onemind_core.app import create_app  # noqa: E402
from onemind_core.netconf import MeshSettings, NetSettings  # noqa: E402
from conftest import ADULT, AGENT, OWNER, ScriptedExecutor  # noqa: E402


def _events(settings, name: str) -> list[dict]:
    if not settings.audit_path.exists():
        return []
    rows = [json.loads(line) for line in settings.audit_path.read_text().splitlines() if line.strip()]
    return [r for r in rows if r["event"] == name]


@pytest.fixture
def mesh_box(settings, tmp_path, hs, monkeypatch):
    """Build a gateway app. installed=True: Headscale's key file and the hub mesh IP are on the box
    (deploy/install.sh writes them); enabled is ONEMIND_MESH_ENABLED."""
    keyfile = tmp_path / "headscale.key"
    keyfile.write_text(hs.api_key)
    keyfile.chmod(0o600)
    real = HeadscaleClient.from_key_file
    monkeypatch.setattr(net_router.HeadscaleClient, "from_key_file",
                        classmethod(lambda cls, url, kf, **kw: real.__func__(cls, url, kf, transport=hs)))

    def build(*, installed: bool, enabled: bool = False, relay: str | None = None):
        mesh_cfg = MeshSettings(enabled=enabled, relay_addr=relay,
                                **({"headscale_key_file": keyfile, "hub_ip": "100.64.0.1"} if installed else {}))
        sections = {**settings.sections, "mesh": mesh_cfg,
                    "net": NetSettings(box_name="box1", lan_addr="192.0.2.10", tls_dir=tmp_path / "tls")}
        s = replace(settings, sections=sections)
        return s, TestClient(create_app(s, clock=lambda: NOW, executor=ScriptedExecutor()))

    return build


def test_mesh_routes_are_mounted_and_documented(mesh_box):
    _, c = mesh_box(installed=False)
    routes = {(m, r.path) for r in c.app.routes for m in getattr(r, "methods", ())}
    assert {("GET", "/v1/mesh"), ("PUT", "/v1/mesh/settings")} <= routes
    op = c.get("/openapi.json").json()["paths"]["/v1/mesh/settings"]["put"]
    assert op["operationId"] == "mesh.settings_update" and op["tags"] == ["mesh"]
    assert {"200", "401", "403", "409", "422"} <= set(op["responses"])


def test_no_provider_answers_not_set_up_with_a_next_step(mesh_box):
    _, c = mesh_box(installed=False)
    view = c.get("/v1/mesh", headers=OWNER).json()
    assert view["mode"] == "off" and view["control"]["state"] == "off"
    assert view["settings"] == {"enabled": False, "provider": None,
                                "control_url": "https://control.onemind.internal:8444", "saved": False,
                                "updated_at": None, "updated_by": None}
    setup = view["setup"]
    assert setup["state"] == "not_set_up" and setup["reason"] == "no_provider"
    assert "onemind mesh settings --provider headscale" in setup["next_step"]
    r = c.put("/v1/mesh/settings", json={"enabled": True}, headers=OWNER)
    assert r.status_code == 409 and r.json()["reason"] == "mesh_no_provider"
    assert "onemind mesh settings --provider headscale" in r.json()["message"]


def test_mesh_state_change_is_owner_only_and_audited(mesh_box):
    s, c = mesh_box(installed=False)
    for who in (ADULT, AGENT):
        r = c.put("/v1/mesh/settings", json={"provider": "headscale"}, headers=who)
        assert r.status_code == 403, r.text
    assert len(_events(s, "authz.denied")) == 2 and not _events(s, "mesh.settings.changed")
    assert c.put("/v1/mesh/settings", json={"provider": "headscale"}).status_code == 401
    r = c.put("/v1/mesh/settings", json={"provider": "headscale", "enabled": True,
                                         "control_url": "https://control.onemind.internal:9444"}, headers=OWNER)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["settings"]["enabled"] is True and out["settings"]["provider"] == "headscale" and out["settings"]["saved"]
    # chosen but not installed on this box: still 'not set up', and the next step says how to install it
    assert out["setup"]["state"] == "not_set_up" and out["setup"]["reason"] == "provider_not_installed"
    assert "install" in out["setup"]["next_step"].lower()
    (ev,) = _events(s, "mesh.settings.changed")
    assert ev["principal"]["role"] == "owner"
    assert ev["data"]["before"] == {"enabled": False, "provider": None, "control_url": "https://control.onemind.internal:8444"}
    assert ev["data"]["after"] == {"enabled": True, "provider": "headscale", "control_url": "https://control.onemind.internal:9444"}
    # the same values again change nothing and write no second entry
    assert c.put("/v1/mesh/settings", json={"provider": "headscale"}, headers=OWNER).status_code == 200
    assert len(_events(s, "mesh.settings.changed")) == 1
    # stored, not in memory: a new gateway on the same database reads it back
    _, c2 = mesh_box(installed=False)
    assert c2.get("/v1/mesh", headers=OWNER).json()["settings"]["provider"] == "headscale"


@pytest.mark.parametrize("body", [{"provider": "tailscale-saas"}, {"control_url": "http://control.onemind.internal"},
                                  {"control_url": "https://"}, {"enabled": "yes"}, {"extra": 1}])
def test_bad_mesh_settings_are_refused(mesh_box, body):
    s, c = mesh_box(installed=False)
    assert c.put("/v1/mesh/settings", json=body, headers=OWNER).status_code == 422
    assert not _events(s, "mesh.settings.changed")


def test_owner_turns_the_installed_mesh_off_and_on_live(mesh_box, hs):
    hs.users["9"] = {"id": "9", "name": "onemind-machines"}
    s, c = mesh_box(installed=True, enabled=True)
    view = c.get("/v1/mesh", headers=OWNER).json()
    assert view["mode"] == "lan" and view["setup"]["state"] == "ready" and view["settings"]["provider"] == "headscale"
    assert c.app.state.mesh is not None
    off = c.put("/v1/mesh/settings", json={"enabled": False}, headers=OWNER).json()
    assert off["setup"]["state"] == "off" and "onemind mesh settings --enable" in off["setup"]["next_step"]
    assert c.app.state.mesh is None  # GET /v1/status reads this: the mesh is not enabled
    view = c.get("/v1/mesh", headers=OWNER).json()
    assert view["mode"] == "off" and view["control"]["state"] == "off" and view["names"]["mesh"] == []
    on = c.put("/v1/mesh/settings", json={"enabled": True}, headers=OWNER).json()
    assert on["setup"]["state"] == "ready" and c.app.state.mesh is not None
    assert c.get("/v1/mesh", headers=OWNER).json()["control"]["state"] == "up"
    assert [e["data"]["after"]["enabled"] for e in _events(s, "mesh.settings.changed")] == [False, True]


def test_box_ca_starts_only_when_the_mesh_is_enabled(mesh_box, tmp_path):
    _, c = mesh_box(installed=True, enabled=False)
    view = c.get("/v1/mesh", headers=OWNER).json()
    assert view["setup"]["state"] == "off" and view["ca_sha256"] == ""
    assert not (tmp_path / "tls" / "ca.crt").exists()  # reading the mesh view does not create a CA
    c.put("/v1/mesh/settings", json={"enabled": True}, headers=OWNER)
    assert (tmp_path / "tls" / "ca.crt").exists()
    fp = c.get("/v1/mesh", headers=OWNER).json()["ca_sha256"]
    assert len(fp) == 64 and fp == c.get("/v1/tls", headers=OWNER).json()["ca_sha256"]


def _join(c, node_id="n1a2b3c4d5e6"):
    """One worker join through the real routes; returns the delivered credentials (the join bundle)."""
    from test_net import Node  # imported late: test_net imports this module

    t = c.post("/v1/fabric/join-tickets", json={"role": "worker"}, headers=OWNER).json()
    node = Node(node_id=node_id)
    jr = c.post("/v1/fabric/join-requests", json=node.body(t["one_time"]["join_code"])).json()
    assert c.post(f"/v1/actions/{jr['action']['id']}/approve", headers=OWNER).status_code == 200
    return node.poll(c, jr["join_request_id"], t["one_time"]["join_code"]).json()["credentials"]


# Keys a node of the previous release reads from the bundle's mesh block (internal/fabric MeshBlock). New
# fields are only ever added beside them (#697: N and N-1 both work), so none of these may go.
BUNDLE_V1_MESH_KEYS = {"control_url", "control_addrs", "relay_addrs", "ca_sha256", "auth_key", "hostname",
                       "hub_mesh_ip", "tags", "shields_up"}


def test_join_bundle_carries_mesh_fields_beside_the_relay_fields(mesh_box, hs):
    hs.users["9"] = {"id": "9", "name": "onemind-machines"}
    _, c = mesh_box(installed=True, enabled=True, relay="203.0.113.7")
    m = _join(c)["mesh"]
    assert BUNDLE_V1_MESH_KEYS <= set(m)
    assert m["provider"] == "headscale" and m["relay_addrs"] == ["203.0.113.7"] and m["control_addrs"] == ["192.0.2.10"]
    assert m["control_url"] == "https://control.onemind.internal:8444"


def test_join_bundle_has_no_mesh_block_when_the_owner_turned_it_off(mesh_box, hs):
    hs.users["9"] = {"id": "9", "name": "onemind-machines"}
    _, c = mesh_box(installed=True, enabled=True)
    c.put("/v1/mesh/settings", json={"enabled": False}, headers=OWNER)
    creds = _join(c)
    assert "mesh" not in creds and not hs.keys  # no key minted for a mesh that is off
    assert {"role", "node_cert", "ca_cert", "nats"} <= set(creds)  # the rest of the bundle is unchanged
