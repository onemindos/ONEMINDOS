# SPDX-License-Identifier: Apache-2.0
"""Networking part 2 in the gateway: fabric join (§12.11), per-node NATS accounts, the box CA
routes (§12.7), the mesh view, forward-auth, the app-host cookie, mDNS names and the HTTP redirect.

Every key, CSR and nkey is made at test time. Headscale is the fake from test_mesh.py; k3s is a
fake kubectl runner.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import secrets
import subprocess
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509 import verification
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient

import onemind_core.routers.net as net_router
from onemind_core.app import create_app
from onemind_core.ca import BoxCA, box_name_from_hostname
from onemind_core.fabric import POLL_CONTEXT, SourceLimiter, code_hash, match_code, new_join_code, normalize_code
from onemind_core.lan import AvahiPublisher, desired_names
from onemind_core.natsconf import NodeAccount, _crc16, is_user_public_nkey, render_accounts
from onemind_core.netconf import FabricSettings, MeshSettings, NetSettings
from onemind_core.mesh import HeadscaleClient
from onemind_core.serve import redirect_app
from conftest import AGENT, OWNER, ADULT, ScriptedExecutor
from test_mesh import FakeHeadscale

GOLDEN = Path(__file__).resolve().parents[2] / "internal" / "leaf" / "testdata" / "hub-accounts.golden.conf"
PUB_A = "UBBUEVU3RVFLTSYWTDDLUC2TLY3YDZKKYWVTUOW4UFVUY6BICGH55O2Y"
PUB_B = "UC3WGTQV7ERIG2GOPKU7CXZ6B6DPY4S2DC4ZIUZ4XVZENDHGM3RRMZF3"


def nkey_pub() -> str:
    raw = bytes([20 << 3]) + secrets.token_bytes(32)
    raw += _crc16(raw).to_bytes(2, "little")
    return base64.b32encode(raw).decode()


class Node:
    """A joining machine: its own key (never sent), CSR and NATS public key."""

    def __init__(self, node_id="n1a2b3c4d5e6", hostname="mini-pc"):
        self.node_id, self.hostname = node_id, hostname
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.csr = (x509.CertificateSigningRequestBuilder()
                    .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "whatever-i-ask")]))
                    .sign(self.key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM).decode())
        self.nkey = nkey_pub()

    def body(self, code, **over):
        b = {"join_code": code, "csr_pem": self.csr, "nats_pubkey": self.nkey,
             "node": {"node_id": self.node_id, "hostname": self.hostname, "board": "x86_64-efi", "arch": "amd64",
                      "os": {"id": "debian", "version_id": "13", "pretty": "Debian GNU/Linux 13 (trixie)"}}}
        b.update(over)
        return b

    def proof(self, rid: str) -> str:
        return base64.b64encode(self.key.sign(POLL_CONTEXT + rid.encode(), ec.ECDSA(hashes.SHA256()))).decode()

    def poll(self, client, rid, code):
        return client.get(f"/v1/fabric/join-requests/{rid}",
                          headers={"OneMind-Join-Code": code, "OneMind-Join-Proof": self.proof(rid)})


class FakeKubectl:
    def __init__(self):
        self.created: list[str] = []
        self.deleted: list[str] = []
        self.fail = False

    def __call__(self, argv, input=None, **_):
        if argv[1] == "create":
            if self.fail:
                return subprocess.CompletedProcess(argv, 1, b"", b"boom")
            self.created.append(input.decode())
        elif "delete" in argv:
            self.deleted.append(argv[-2])
        return subprocess.CompletedProcess(argv, 0, b"", b"")


@pytest.fixture
def hs():
    return FakeHeadscale(secrets.token_urlsafe(32))


@pytest.fixture
def kube():
    return FakeKubectl()


@pytest.fixture
def net_settings(settings, tmp_path, hs, kube, monkeypatch):
    keyfile = tmp_path / "headscale.key"
    keyfile.write_text(hs.api_key)
    keyfile.chmod(0o600)
    real_from_key_file = HeadscaleClient.from_key_file

    monkeypatch.setattr(net_router.HeadscaleClient, "from_key_file",
                        classmethod(lambda cls, url, kf, **kw: real_from_key_file.__func__(cls, url, kf, transport=hs)))
    real_k3s = net_router.K3sBootstrapTokens
    monkeypatch.setattr(net_router, "K3sBootstrapTokens", lambda kubectl, h: real_k3s(kubectl, h, runner=kube))
    return replace(settings, sections={
        "net": NetSettings(box_name="box1", lan_addr="192.0.2.10", tls_dir=tmp_path / "tls"),
        "mesh": MeshSettings(enabled=True, headscale_key_file=keyfile, hub_ip="100.64.0.1"),
        "fabric": FabricSettings(nats_accounts_file=tmp_path / "nats" / "accounts.conf", k3s=True,
                                 k3s_ca_hash="K10" + "ab" * 32),
    })


@pytest.fixture
def nc(net_settings, clock):
    app = create_app(net_settings, clock=clock, executor=ScriptedExecutor())
    return TestClient(app)  # no lifespan: tests drive fabric.tick() themselves


def fabric_of(client):
    return client.app.state.gateway.actions.handlers["node.join"]


def ticket(client, role="worker", **kw):
    r = client.post("/v1/fabric/join-tickets", json={"role": role, **kw}, headers=OWNER)
    assert r.status_code == 201, r.text
    return r.json()


def heartbeat(client, node_id, k3s_ready=True):
    hb = {"schema": "onemind.node.status/v1", "node_id": node_id, "hostname": "mini-pc", "role": "node",
          "k3s": {"present": True, "role": "agent", "ready": k3s_ready},
          "mesh": {"state": "up", "path": "direct"}, "fabric": {"role": "worker", "leaf_link": "up"}}
    assert client.app.state.registry.ingest(f"onemind.node.{node_id}.status", json.dumps(hb).encode())


# ---- NATS accounts ---------------------------------------------------------------------------------
def test_accounts_golden_matches_the_go_isolation_test():
    """internal/leaf/accounts_test.go loads this exact file into a real nats-server."""
    assert render_accounts([NodeAccount("bbb222", PUB_B), NodeAccount("aaa111", PUB_A)]) == GOLDEN.read_text()


def test_accounts_refuse_bad_input():
    assert is_user_public_nkey(PUB_A) and is_user_public_nkey(nkey_pub())
    assert not is_user_public_nkey("N" + PUB_A[1:]) and not is_user_public_nkey(PUB_A[:-1] + "A")
    with pytest.raises(ValueError):
        NodeAccount("Bad.Id", PUB_A)
    with pytest.raises(ValueError):
        NodeAccount("aaa111", "UNOTAKEY")
    empty = render_accounts([])
    assert "no_auth_user" in empty and "NODE_" not in empty and 'allowed_connection_types: ["STANDARD"]' in empty


# ---- codes -------------------------------------------------------------------------------------------
def test_join_codes():
    code = new_join_code()
    assert len(code) == 14 and code.count("-") == 2
    assert normalize_code(code.lower().replace("-", " ")) == code.replace("-", "")
    assert code_hash(code) == code_hash(code.lower())
    assert normalize_code("short") == "" and len(match_code("jr_x", b"k")) == 7


# ---- tickets ----------------------------------------------------------------------------------------
def test_ticket_is_owner_only_and_carries_the_ca(nc):
    t = ticket(nc)
    assert t["role"] == "worker" and t["one_time"]["join_code"] in t["qr_payload"]
    ca = BoxCA(Path(nc.app.state.settings.section(NetSettings).tls_dir), "box1").ca_fingerprint()
    assert f"ca={ca}" in t["qr_payload"] and t["hub_ca_sha256"] == ca
    assert "hub=https%3A%2F%2Fbox1.local" in t["qr_payload"]
    assert nc.post("/v1/fabric/join-tickets", json={}, headers=AGENT).status_code == 403
    assert nc.post("/v1/fabric/join-tickets", json={}, headers=ADULT).status_code == 403
    listed = nc.get("/v1/fabric/join-tickets", headers=OWNER).json()
    assert listed[0]["ticket_id"] == t["ticket_id"] and "join_code" not in json.dumps(listed)
    audit = Path(nc.app.state.settings.audit_path).read_text()
    assert t["one_time"]["join_code"] not in audit and "fabric.ticket.created" in audit
    assert nc.post("/v1/fabric/join-tickets", json={"expires_in_s": 7200}, headers=OWNER).status_code == 422


def test_revoked_ticket_cannot_join(nc):
    t = ticket(nc)
    assert nc.delete(f"/v1/fabric/join-tickets/{t['ticket_id']}", headers=OWNER).status_code == 204
    r = nc.post("/v1/fabric/join-requests", json=Node().body(t["one_time"]["join_code"]))
    assert r.status_code == 401 and r.json()["reason"] == "code_unknown"


# ---- the whole join ----------------------------------------------------------------------------------
def test_join_end_to_end(nc, hs, kube, clock, net_settings):
    t = ticket(nc)
    code = t["one_time"]["join_code"]
    node = Node()
    r = nc.post("/v1/fabric/join-requests", json=node.body(code))
    assert r.status_code == 202, r.text
    jr = r.json()
    rid, aid = jr["join_request_id"], jr["action"]["id"]
    assert jr["action"]["type"] == "node.join" and jr["action"]["state"] == "awaiting_approval"
    assert jr["action"]["requested_by"] == {"id": f"node:{node.node_id}", "kind": "node"}
    assert jr["action"]["params"]["match_code"] == jr["match_code"]
    assert r.headers["location"] == f"/v1/fabric/join-requests/{rid}"

    # the code is single use
    again = nc.post("/v1/fabric/join-requests", json=Node(node_id="other1").body(code))
    assert again.status_code == 401 and again.json()["reason"] == "code_used"
    # polling needs the code and a signature by the node's own key
    assert nc.get(f"/v1/fabric/join-requests/{rid}", headers={"OneMind-Join-Code": code}).status_code == 401
    assert Node().poll(nc, rid, code).status_code == 401  # someone else's key
    assert node.poll(nc, rid, new_join_code()).status_code == 401
    p = node.poll(nc, rid, code)
    assert p.status_code == 200 and p.json()["state"] == "awaiting_approval" and "credentials" not in p.json()

    # an agent can never approve; the owner can
    assert nc.post(f"/v1/actions/{aid}/approve", headers=AGENT).status_code == 403
    a = nc.post(f"/v1/actions/{aid}/approve", headers=OWNER)
    assert a.status_code == 200 and a.json()["state"] == "dispatched", a.text
    accounts = net_settings.section(FabricSettings).nats_accounts_file.read_text()
    assert f"NODE_{node.node_id}" in accounts and node.nkey in accounts

    # first poll after approval: the credentials, once
    p = node.poll(nc, rid, code).json()
    assert p["state"] == "delivered"
    c = p["credentials"]
    cert = x509.load_pem_x509_certificate(c["node_cert"].encode())
    assert cert.public_key().public_numbers() == node.key.public_key().public_numbers()
    assert cert.subject.rfc4514_string() == f"CN=node-{node.node_id}"  # not what the CSR asked for
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
    assert san == [f"node-{node.node_id}.onemind.internal"]
    store = verification.Store([x509.load_pem_x509_certificate(c["ca_cert"].encode())])
    verification.PolicyBuilder().store(store).time(clock.now).build_client_verifier().verify(cert, [])
    assert c["nats"] == {"url": "tls://100.64.0.1:7422", "account": f"NODE_{node.node_id}", "user_pubkey": node.nkey}
    m = c["mesh"]
    assert m["hostname"] == f"node-{node.node_id}" and m["hub_mesh_ip"] == "100.64.0.1"
    assert m["control_url"] == "https://control.onemind.internal:8444" and m["control_addrs"] == ["192.0.2.10"]
    assert set(m["tags"]) == {"tag:onemind-worker", "tag:onemind-k3s"} and m["shields_up"] is False
    key = next(k for k in hs.keys.values() if k["key"] == m["auth_key"])
    assert not key["reusable"] and not key["ephemeral"]
    assert c["k3s"]["server_url"] == "https://100.64.0.1:6443"
    assert c["k3s"]["token"].startswith("K10" + "ab" * 32 + "::")
    assert len(kube.created) == 1 and "bootstrap.kubernetes.io/token" in kube.created[0]
    # ... and never again, never in the audit log
    again = node.poll(nc, rid, code).json()
    assert again["state"] == "delivered" and "credentials" not in again
    audit = Path(net_settings.audit_path).read_text()
    for secret in (m["auth_key"], c["k3s"]["token"].split("::")[1], code):
        assert secret not in audit

    # the node comes up: the mesh node is bound to our key and its heartbeat arrives
    fab = fabric_of(nc)
    fab.tick()
    assert nc.get(f"/v1/actions/{aid}", headers=OWNER).json()["state"] == "dispatched"
    hs.add_node(f"node-{node.node_id}", key_id=key["id"], tags=["tag:onemind-worker", "tag:onemind-k3s"])
    heartbeat(nc, node.node_id, k3s_ready=False)  # leaf and mesh up, k3s agent still joining
    fab.tick()
    assert nc.get(f"/v1/actions/{aid}", headers=OWNER).json()["state"] == "dispatched"
    assert kube.deleted == []  # the agent still needs its 1-hour token (found in the lab)
    heartbeat(nc, node.node_id)
    fab.tick()
    done = nc.get(f"/v1/actions/{aid}", headers=OWNER).json()
    assert done["state"] == "succeeded", done
    assert kube.deleted and kube.deleted[0].startswith("bootstrap-token-")
    summary = nc.get("/v1/fabric", headers=OWNER).json()
    assert summary["counts"]["worker"] == 1 and summary["nodes"][0]["state"] == "online"
    assert summary["nodes"][0]["leaf_link"] == "up"
    assert "node.joined" in Path(net_settings.audit_path).read_text()
    # the same machine cannot join twice
    t2 = ticket(nc)
    dup = nc.post("/v1/fabric/join-requests", json=node.body(t2["one_time"]["join_code"]))
    assert dup.status_code == 409 and dup.json()["reason"] == "duplicate_node_id"


def test_denied_join_gets_nothing(nc, net_settings):
    t = ticket(nc)
    node = Node()
    jr = nc.post("/v1/fabric/join-requests", json=node.body(t["one_time"]["join_code"])).json()
    assert nc.post(f"/v1/actions/{jr['action']['id']}/deny", headers=OWNER).status_code == 200
    p = node.poll(nc, jr["join_request_id"], t["one_time"]["join_code"]).json()
    assert p["state"] == "denied" and "credentials" not in p
    assert "NODE_" not in (net_settings.section(FabricSettings).nats_accounts_file.read_text()
                           if net_settings.section(FabricSettings).nats_accounts_file.exists() else "")


def test_unapproved_request_expires(nc, clock):
    t = ticket(nc)
    node = Node()
    jr = nc.post("/v1/fabric/join-requests", json=node.body(t["one_time"]["join_code"])).json()
    clock.advance(16 * 60)
    fabric_of(nc).tick()
    assert node.poll(nc, jr["join_request_id"], t["one_time"]["join_code"]).json()["state"] == "expired"
    assert nc.post(f"/v1/actions/{jr['action']['id']}/approve", headers=OWNER).status_code == 409


def test_uncollected_credentials_expire_and_account_goes(nc, clock, net_settings):
    t = ticket(nc, role="leaf")
    node = Node()
    jr = nc.post("/v1/fabric/join-requests", json=node.body(t["one_time"]["join_code"])).json()
    nc.post(f"/v1/actions/{jr['action']['id']}/approve", headers=OWNER)
    accounts = net_settings.section(FabricSettings).nats_accounts_file
    assert f"NODE_{node.node_id}" in accounts.read_text()
    clock.advance(16 * 60)
    fabric_of(nc).tick()
    assert f"NODE_{node.node_id}" not in accounts.read_text()
    assert nc.get(f"/v1/actions/{jr['action']['id']}", headers=OWNER).json()["state"] == "failed"
    assert node.poll(nc, jr["join_request_id"], t["one_time"]["join_code"]).json()["state"] == "expired"


def test_leaf_gets_no_k3s_and_shields_up(nc, kube):
    t = ticket(nc, role="leaf")
    node = Node()
    jr = nc.post("/v1/fabric/join-requests", json=node.body(t["one_time"]["join_code"])).json()
    nc.post(f"/v1/actions/{jr['action']['id']}/approve", headers=OWNER)
    c = node.poll(nc, jr["join_request_id"], t["one_time"]["join_code"]).json()["credentials"]
    assert "k3s" not in c and c["mesh"]["shields_up"] is True and c["mesh"]["tags"] == ["tag:onemind-leaf"]
    assert kube.created == []


def test_wrong_mesh_binding_fails_the_join(nc, hs):
    t = ticket(nc)
    node = Node()
    jr = nc.post("/v1/fabric/join-requests", json=node.body(t["one_time"]["join_code"])).json()
    nc.post(f"/v1/actions/{jr['action']['id']}/approve", headers=OWNER)
    c = node.poll(nc, jr["join_request_id"], t["one_time"]["join_code"]).json()["credentials"]
    key = next(k for k in hs.keys.values() if k["key"] == c["mesh"]["auth_key"])
    hs.add_node("node-impostor", key_id=key["id"], tags=["tag:onemind-worker", "tag:onemind-k3s"])
    heartbeat(nc, node.node_id)
    fabric_of(nc).tick()
    assert nc.get(f"/v1/actions/{jr['action']['id']}", headers=OWNER).json()["state"] == "failed"
    assert not [n for n in hs.nodes.values() if n["name"] == "node-impostor"]


def test_headscale_down_at_delivery_is_retryable(nc, hs, kube):
    t = ticket(nc)
    node = Node()
    jr = nc.post("/v1/fabric/join-requests", json=node.body(t["one_time"]["join_code"])).json()
    nc.post(f"/v1/actions/{jr['action']['id']}/approve", headers=OWNER)
    hs.down = True
    r = node.poll(nc, jr["join_request_id"], t["one_time"]["join_code"])
    assert r.status_code == 503 and r.json()["reason"] == "mesh_control_down"
    assert kube.deleted  # the k3s token minted before the failure was withdrawn
    hs.down = False
    assert "credentials" in node.poll(nc, jr["join_request_id"], t["one_time"]["join_code"]).json()


def test_bad_requests_and_rate_limit(nc):
    t = ticket(nc)
    code = t["one_time"]["join_code"]
    node = Node()
    assert nc.post("/v1/fabric/join-requests", json=node.body(code, nats_pubkey="U" + "A" * 55)).status_code == 422
    assert nc.post("/v1/fabric/join-requests", json=node.body(code, csr_pem="x" * 200)).status_code == 422
    bad = node.body(code)
    bad["node"]["node_id"] = "Bad.Id"
    assert nc.post("/v1/fabric/join-requests", json=bad).status_code == 422
    statuses = [nc.post("/v1/fabric/join-requests", json=node.body(new_join_code())).status_code for _ in range(12)]
    assert 429 in statuses and statuses.count(401) <= 10


def test_failed_approval_frees_the_node_and_its_account(nc, net_settings, monkeypatch):
    """Dispatch fails (the NATS accounts file cannot be written): the request must not stay
    awaiting_approval for ever, holding the node id and a pending slot (review finding)."""
    t = ticket(nc)
    node = Node()
    code = t["one_time"]["join_code"]
    jr = nc.post("/v1/fabric/join-requests", json=node.body(code)).json()
    fab = fabric_of(nc)

    def broken():
        raise OSError("read-only file system")

    monkeypatch.setattr(fab, "write_accounts", broken)
    a = nc.post(f"/v1/actions/{jr['action']['id']}/approve", headers=OWNER).json()
    assert a["state"] == "failed", a
    monkeypatch.undo()
    fab.tick()
    p = node.poll(nc, jr["join_request_id"], code).json()
    assert p["state"] == "failed" and "credentials" not in p
    assert fab.repo.node(node.node_id) is None and fab.repo.count_pending() == 0
    again = nc.post("/v1/fabric/join-requests", json=node.body(ticket(nc)["one_time"]["join_code"]))
    assert again.status_code == 202, again.text


def test_restart_during_approval_ends_outcome_unknown(nc, net_settings, clock):
    """A crash between "accepted"/"dispatched" and the request moving on: reconcile closes the
    action as outcome_unknown (never a retry) and removes any NATS account it had written."""
    t = ticket(nc)
    node = Node()
    code = t["one_time"]["join_code"]
    jr = nc.post("/v1/fabric/join-requests", json=node.body(code)).json()
    aid = jr["action"]["id"]
    fab = fabric_of(nc)
    fab.d.actions.repo.transition(aid, {"awaiting_approval"}, "accepted", clock.now)
    fab.repo.upsert_node(node_id=node.node_id, role="worker", hostname=node.hostname, nats_pubkey=node.nkey,
                         state="joining", request_id=jr["join_request_id"], mesh_node_id=None,
                         cert_expires_at=None, created_at=clock.now, joined_at=None)
    fab.write_accounts()
    accounts = net_settings.section(FabricSettings).nats_accounts_file
    assert f"NODE_{node.node_id}" in accounts.read_text()
    fab.reconcile()
    assert nc.get(f"/v1/actions/{aid}", headers=OWNER).json()["state"] == "outcome_unknown"
    assert node.poll(nc, jr["join_request_id"], code).json()["state"] == "failed"
    assert f"NODE_{node.node_id}" not in accounts.read_text() and fab.repo.node(node.node_id) is None


def test_rate_limiter_memory_is_bounded(clock):
    lim = SourceLimiter(lambda: clock.now)
    for i in range(SourceLimiter.MAX_KEYS + 50):
        lim.check(f"198.51.100.{i}")
        lim.fail(f"198.51.100.{i}")
    clock.advance(61)
    lim.check("203.0.113.1")
    assert len(lim._hits) == 1 and len(lim._fails) == 0
    for _ in range(10):
        lim.fail("203.0.113.9")
    with pytest.raises(Exception) as blocked:
        lim.check("203.0.113.9")
    assert blocked.value.status == 429  # a blocked source stays blocked through a gc


def test_agents_cannot_file_node_join(nc, clock):
    body = {"type": "node.join", "params": {"app_id": "x"}, "idempotency_key": "k",
            "expires_at": (clock.now + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")}
    assert nc.post("/v1/actions", json=body, headers=AGENT).status_code == 422


# ---- box CA routes, mesh view, forward-auth, cookie ------------------------------------------------
def test_ca_routes(nc):
    der = nc.get("/v1/tls/ca.crt")  # open: a joining node and a phone need it before signing in
    assert der.status_code == 200 and der.headers["content-type"] == "application/x-x509-ca-cert"
    ca = x509.load_der_x509_certificate(der.content)
    assert ca.extensions.get_extension_for_class(x509.NameConstraints).critical
    info = nc.get("/v1/tls", headers=OWNER).json()
    assert "*.box1.local" in info["names"] and info["https"] is False
    assert info["ca_sha256"] == hashlib.sha256(der.content).hexdigest()
    assert nc.get("/v1/tls").status_code == 401
    assert nc.get("/v1/tls/ca.crt?format=pem").text.startswith("-----BEGIN CERTIFICATE-----")


def test_mesh_view_hides_addresses_by_default(nc, hs):
    hs.users["9"] = {"id": "9", "name": "onemind-machines"}
    hs.add_node("hub", tags=["tag:onemind-hub", "tag:onemind-k3s"])
    view = nc.get("/v1/mesh", headers=OWNER).json()
    assert view["mode"] == "lan" and view["control"]["state"] == "up"
    assert view["nodes"][0]["role"] == "hub" and "mesh_ip" not in json.dumps(view)
    assert "100.64.0.2" in json.dumps(nc.get("/v1/mesh?addresses=1", headers=OWNER).json())
    assert "100.64.0." not in json.dumps(nc.get("/v1/mesh?addresses=1", headers=ADULT).json())
    hs.down = True
    assert nc.get("/v1/mesh", headers=OWNER).json()["control"]["state"] == "down"


def test_forward_auth_is_loopback_only(nc):
    # TestClient's client address is "testclient", not loopback
    r = nc.get("/v1/auth/forward", headers={"X-Forwarded-Host": "uptime-kuma.box1.local"})
    assert r.status_code == 404


def test_app_session_cookie(nc):
    r = nc.post("/v1/auth/app-session", headers={**OWNER, "Host": "box1.local"})
    assert r.status_code == 204
    cookie = r.headers["set-cookie"]
    assert "onemind_session=" in cookie and "HttpOnly" in cookie and "Secure" in cookie
    assert "Domain=box1.local" in cookie and "SameSite=lax" in cookie
    assert nc.post("/v1/auth/app-session", headers=AGENT).status_code == 403
    assert nc.post("/v1/auth/app-session").status_code == 401


def test_app_host_goes_through_the_proxy(nc):
    # not signed in: 401 for any app name, installed or not
    r = nc.get("/", headers={"Host": "vaultwarden.box1.local"})
    assert r.status_code == 401 and "Sign in" in r.text
    r = nc.get("/", headers={"Host": "uptime-kuma.onemind.local", **OWNER})
    assert r.status_code == 404  # signed in, but not installed
    assert nc.get("/healthz", headers={"Host": "box1.local"}).status_code == 200


# ---- mDNS names ---------------------------------------------------------------------------------------
class FakeProc:
    def __init__(self, argv, exit_code=None, err=b""):
        self.argv, self.code, self.stderr = argv, exit_code, _Err(err)

    def poll(self):
        return self.code

    def terminate(self):
        self.code = -15

    def wait(self, timeout=None):
        return self.code

    def kill(self):
        self.code = -9


class _Err:
    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data

    def close(self):
        pass


def test_desired_names():
    names = desired_names("box1", ["vaultwarden", "Bad_Name"], hostname_label="box1")
    assert names == {"onemind.local", "vaultwarden.box1.local", "vaultwarden.onemind.local"}
    assert "box1.local" in desired_names("box1", [], hostname_label="other")
    assert box_name_from_hostname("My_Box.lan") == "my-box" and box_name_from_hostname("") == "onemind"


def test_avahi_publisher_conflict_and_removal():
    procs, conflicts = [], []
    now = [0.0]

    def spawn(argv):
        p = FakeProc(argv)
        procs.append(p)
        return p

    pub = AvahiPublisher("192.0.2.10", on_conflict=conflicts.append, spawn=spawn, clock=lambda: now[0])
    pub.sync({"onemind.local", "vaultwarden.box1.local"})
    assert sorted(p.argv[3] for p in procs) == ["onemind.local", "vaultwarden.box1.local"]
    assert all(p.argv[:3] == ["avahi-publish", "-a", "-R"] and p.argv[4] == "192.0.2.10" for p in procs)
    taken = next(p for p in procs if p.argv[3] == "onemind.local")
    taken.code, taken.stderr = 255, _Err(b"Failed to add address: Local name collision")
    pub.sync({"onemind.local", "vaultwarden.box1.local"})
    assert conflicts == ["onemind.local"] and pub.conflicts() == {"onemind.local"}
    pub.sync({"onemind.local", "vaultwarden.box1.local"})
    assert conflicts == ["onemind.local"] and len(procs) == 2  # not retried yet, raised once
    pub.sync({"onemind.local"})  # app removed: its name goes
    assert next(p for p in procs if p.argv[3] == "vaultwarden.box1.local").code == -15
    with pytest.raises(ValueError):
        AvahiPublisher("fd00::1")


# ---- HTTP -> HTTPS -------------------------------------------------------------------------------------
def test_redirect_app():
    sent = []

    async def run(port, host, path, qs=b""):
        sent.clear()
        scope = {"type": "http", "headers": [(b"host", host)], "raw_path": path, "query_string": qs,
                 "server": ("192.0.2.10", 80)}

        async def send(m):
            sent.append(m)

        await redirect_app(port)(scope, None, send)
        return dict(sent[0]["headers"])[b"location"], sent[0]["status"]

    assert asyncio.run(run(443, b"vaultwarden.box1.local", b"/a b", b"x=1")) == (
        b"https://vaultwarden.box1.local/a b?x=1", 308)
    assert asyncio.run(run(8443, b"box1.local:80", b"/"))[0] == b"https://box1.local:8443/"
    assert asyncio.run(run(443, b"evil.example/@x", b"/"))[0] == b"https://192.0.2.10/"


# ---- CA additions ---------------------------------------------------------------------------------------
def test_sign_node_csr_and_ip_certs(tmp_path):
    box = BoxCA(tmp_path / "tls", "box1")
    node = Node()
    cert = box.sign_node_csr(node.csr, "n1a2b3c4d5e6")
    eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    assert x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH in eku
    with pytest.raises(ValueError):
        box.sign_node_csr(node.csr, "BAD")
    broken = node.csr.replace("REQUEST-----\nM", "REQUEST-----\nX")
    with pytest.raises(ValueError):
        box.sign_node_csr(broken, "n1")
    from cryptography.hazmat.primitives.asymmetric import rsa
    rkey = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rsa_csr = x509.CertificateSigningRequestBuilder().subject_name(x509.Name([])).sign(rkey, hashes.SHA256())
    with pytest.raises(ValueError, match="P-256"):
        box.sign_node_csr(rsa_csr.public_bytes(serialization.Encoding.PEM), "n1")
    nats = box.ensure_nats_cert("100.64.0.1")
    c = x509.load_pem_x509_certificates(nats.cert_path.read_bytes())[0]
    ips = c.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.IPAddress)
    assert [str(i) for i in ips] == ["100.64.0.1"]
    assert box.ensure_nats_cert("100.64.0.1").cert_path.stat().st_mtime == nats.cert_path.stat().st_mtime
    assert [str(i) for i in x509.load_pem_x509_certificates(box.ensure_nats_cert("100.64.0.9").cert_path.read_bytes())[0]
            .extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.IPAddress)] == ["100.64.0.9"]
    with pytest.raises(ValueError):
        box.ensure_nats_cert("192.0.2.1")  # outside the CA's address constraints
    assert "*.box1.local" in box.https_names() and "control.onemind.internal" in box.https_names()
