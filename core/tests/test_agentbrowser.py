# SPDX-License-Identifier: Apache-2.0
"""The agent browser (#694): owner-approved allowlist, one sealed pod per session, egress only via the proxy.

Acceptance: an unapproved host is unreachable from the pod (its NetworkPolicy lets it reach only the
gateway's proxy, and the proxy refuses the host), the kill switch ends the session, the budget caps
pages. The cluster is a fake kubectl keeping objects in memory; the proxy is the real one on a local
port, and an approved tunnel reaches a real local TCP server.
"""

from __future__ import annotations

import base64
import json
import socket
import subprocess
import threading
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, OWNER
from onemind_core.agentbrowser import policy
from onemind_core.agentbrowser.pods import SESSION_LABEL, isolation_problems, session_docs
from onemind_core.agentbrowser.proxy import EgressProxy, EgressRefused
from onemind_core.agentbrowser.settings import AgentBrowserSettings
from onemind_core.app import create_app

BASE = "/v1/agent-browser"


class FakeCluster:
    """kubectl apply / get pod / delete -l over objects kept in memory."""

    def __init__(self):
        self.objects: dict[tuple[str, str], dict] = {}
        self.deleted: list[str] = []

    def __call__(self, argv, input=None, **_):
        args = argv[1:]
        out = ""
        if args[0] == "apply":
            for item in json.loads(input)["items"]:
                self.objects[(item["kind"], item["metadata"]["name"])] = item
        elif args[0] == "delete":
            label = args[args.index("-l") + 1]
            key, _, value = label.partition("=")
            for k, obj in list(self.objects.items()):
                got = (obj["metadata"].get("labels") or {}).get(key)
                if k[0] in ("Pod", "Secret") and got is not None and (not value or got == value):
                    del self.objects[k]
                    self.deleted.append(k[1])
        elif args[:2] == ["get", "pod"]:
            pod = self.objects.get(("Pod", args[2]))
            if pod is not None:
                out = json.dumps({**pod, "status": {"phase": "Running", "podIP": "127.0.0.1"}})
        return subprocess.CompletedProcess(argv, 0, out, "")

    def pods(self) -> list[dict]:
        return [o for (kind, _), o in self.objects.items() if kind == "Pod"]


@pytest.fixture
def echo_port():
    """A TCP server standing in for an approved site: it echoes what it is sent."""
    srv = socket.create_server(("127.0.0.1", 0))

    def serve():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            threading.Thread(target=lambda c=conn: [c.sendall(d) for d in iter(lambda: c.recv(4096), b"")],
                             daemon=True).start()

    threading.Thread(target=serve, daemon=True).start()
    yield srv.getsockname()[1]
    srv.close()


@pytest.fixture
def ab(settings, clock, executor, echo_port):
    cfg = AgentBrowserSettings(enabled=True, image="registry.example/onemind/agent-browser@sha256:" + "a" * 64,
                               proxy_listen="127.0.0.1", proxy_port=0, hub_cidrs=("192.0.2.1",), max_pages=5)
    s = replace(settings, sections={**settings.sections, "agentbrowser": cfg})
    app = create_app(s, clock=clock, executor=executor)
    svc = app.state.agent_browser
    cluster = FakeCluster()
    svc.pods.runner = cluster
    pages: list[dict] = []

    def control(ip, port, token, body):
        pages.append(body)
        return {"status": 200, "final_url": body["url"], "title": "A page", "text": "hello"}

    svc.control = control

    async def dial(host, port):
        import asyncio
        return await asyncio.open_connection("127.0.0.1", echo_port)

    svc.proxy.dial = dial
    with TestClient(app) as c:
        yield {"c": c, "svc": svc, "cluster": cluster, "pages": pages, "settings": s}


def start(c, headers=AGENT, **body):
    r = c.post(f"{BASE}/sessions", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def approve_site(c, entry: str, headers=AGENT, agent: str | None = None) -> dict:
    r = c.post(f"{BASE}/sites", json={"entry": entry, **({"agent": agent} if agent else {})}, headers=headers)
    assert r.status_code in (200, 201), r.text
    assert r.json()["state"] == "awaiting_approval"
    assert c.post(f"/v1/actions/{r.json()['id']}/approve", headers=AGENT).status_code == 403  # never self-approved
    done = c.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert done.json()["state"] == "succeeded", done.text
    return done.json()


def connect(port: int, sid: str, token: str, host: str) -> tuple[socket.socket, bytes]:
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    cred = base64.b64encode(f"{sid}:{token}".encode()).decode()
    s.sendall(f"CONNECT {host}:443 HTTP/1.1\r\nHost: {host}:443\r\nProxy-Authorization: Basic {cred}\r\n\r\n".encode())
    head = b""
    while b"\r\n\r\n" not in head:
        chunk = s.recv(1024)
        if not chunk:
            break
        head += chunk
    return s, head


def audit(settings) -> list[dict]:
    return [json.loads(line) for line in settings.audit_path.read_text().splitlines()]


# ---- acceptance ----------------------------------------------------------------------------------------
def test_unapproved_host_is_unreachable_from_the_pod(ab):
    c, svc, cluster = ab["c"], ab["svc"], ab["cluster"]
    sess = start(c)
    # The network: the pod may reach only the hub's proxy port, and only the hub may reach its control port.
    pols = {o["metadata"]["name"]: o for (k, _), o in cluster.objects.items() if k == "NetworkPolicy"}
    assert pols["default-deny"]["spec"] == {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]}
    assert pols["agent-browser"]["spec"]["egress"] == [{"to": [{"ipBlock": {"cidr": "192.0.2.1/32"}}],
                                                         "ports": [{"protocol": "TCP", "port": svc.proxy.port}]}]
    (pod,) = cluster.pods()
    assert isolation_problems(pod) == []
    token = svc.sessions[sess["id"]].proxy_token
    port = svc.proxy.port
    # The proxy: an unapproved host is refused, and so is a wrong credential.
    s, head = connect(port, sess["id"], token, "unapproved.example.org")
    assert head.startswith(b"HTTP/1.1 403")
    s.close()
    s, head = connect(port, sess["id"], "wrong", "example.org")
    assert head.startswith(b"HTTP/1.1 403")
    s.close()
    # The API: a visit there answers approval_required and files the site request for the owner.
    r = c.post(f"{BASE}/sessions/{sess['id']}/visit", json={"url": "https://unapproved.example.org/x?q=secret"}, headers=AGENT)
    assert r.status_code == 202 and r.json()["decision"] == "approval_required"
    assert r.json()["reason"] == "site_not_approved" and r.json()["action"]["type"] == "agentbrowser.site.allow"
    assert r.json()["action"]["state"] == "awaiting_approval" and ab["pages"] == []
    # Once the owner approves, the same host is reachable through the proxy (a real tunnel to a local server).
    approve_site(c, "example.org")
    s, head = connect(port, sess["id"], token, "example.org")
    assert head.startswith(b"HTTP/1.1 200")
    s.sendall(b"ping")
    assert s.recv(16) == b"ping"
    s.close()
    lines = audit(ab["settings"])
    refused = [x for x in lines if x["event"] == "agentbrowser.egress_refused"]
    assert {x["data"]["host"] for x in refused} >= {"unapproved.example.org"}
    visit = next(x for x in lines if x["event"] == "agentbrowser.visit")
    assert visit["data"]["url"] == "https://unapproved.example.org/x" and "secret" not in json.dumps(visit)


def test_kill_switch_ends_the_session(ab):
    c, svc, cluster = ab["c"], ab["svc"], ab["cluster"]
    approve_site(c, "example.org")
    sess = start(c)
    token = svc.sessions[sess["id"]].proxy_token
    s, head = connect(svc.proxy.port, sess["id"], token, "example.org")
    assert head.startswith(b"HTTP/1.1 200")
    assert c.put("/v1/agents/kill-switch", json={"on": True, "reason": "stop"}, headers=OWNER).status_code == 200
    assert s.recv(16) == b""  # the open tunnel was closed
    s.close()
    assert cluster.pods() == [] and any(n.startswith("ab-") for n in cluster.deleted)
    view = c.get(f"{BASE}/sessions", headers=OWNER).json()
    assert view[0]["state"] == "ended" and view[0]["ended_reason"] == "agents_stopped"
    s, head = connect(svc.proxy.port, sess["id"], token, "example.org")
    assert head.startswith(b"HTTP/1.1 403")
    s.close()
    assert c.post(f"{BASE}/sessions", json={}, headers=AGENT).status_code == 403  # agents refused at the door


def test_budget_caps_pages(ab):
    c = ab["c"]
    approve_site(c, "*.example.org")
    sess = start(c, max_pages=2)
    for path in ("a", "b"):
        r = c.post(f"{BASE}/sessions/{sess['id']}/visit", json={"url": f"https://docs.example.org/{path}"}, headers=AGENT)
        assert r.status_code == 200 and r.json()["decision"] == "allowed", r.text
    assert r.json()["session"]["pages_left"] == 0 and r.json()["page"]["text"] == "hello"
    r = c.post(f"{BASE}/sessions/{sess['id']}/visit", json={"url": "https://docs.example.org/c"}, headers=AGENT)
    assert r.status_code == 409 and r.json()["reason"] == "page_budget_exhausted"
    assert len(ab["pages"]) == 2
    assert start(c, max_pages=900)["max_pages"] == 200  # the box's cap wins over a bigger ask


# ---- the rules around it -------------------------------------------------------------------------------
def test_sign_in_needs_a_one_time_owner_approval(ab):
    c = ab["c"]
    approve_site(c, "example.org")
    sess = start(c)
    url = "https://example.org/login?next=/home"
    r = c.post(f"{BASE}/sessions/{sess['id']}/visit", json={"url": url}, headers=AGENT)
    assert r.status_code == 202 and r.json()["reason"] == "sign_in"
    action = r.json()["action"]
    assert action["type"] == "agentbrowser.step" and action["params"]["url"] == "https://example.org/login"
    body = {"url": url, "approval_id": action["id"]}
    assert c.post(f"{BASE}/sessions/{sess['id']}/visit", json=body, headers=AGENT).status_code == 202  # not approved yet
    assert c.post(f"/v1/actions/{action['id']}/approve", headers=OWNER).json()["state"] == "succeeded"
    assert c.post(f"{BASE}/sessions/{sess['id']}/visit", json=body, headers=AGENT).status_code == 200
    assert c.post(f"{BASE}/sessions/{sess['id']}/visit", json=body, headers=AGENT).status_code == 202  # once only
    r = c.post(f"{BASE}/sessions/{sess['id']}/visit", json={"url": "https://example.org/f.zip", "kind": "download"}, headers=AGENT)
    assert r.status_code == 202 and r.json()["reason"] == "download"


def test_who_may_use_it(ab):
    c = ab["c"]
    assert c.get(f"{BASE}/sites", headers=ADULT).status_code == 403
    assert c.post(f"{BASE}/sessions", json={}, headers=ADULT).status_code == 403
    assert any(x["event"] == "authz.denied" for x in audit(ab["settings"]))
    sess = start(c, headers=OWNER)
    assert c.post(f"{BASE}/sessions/{sess['id']}/visit", json={"url": "https://example.org/"}, headers=AGENT).status_code == 404
    assert c.post(f"{BASE}/sites", json={"entry": "example.org", "agent": "someone-else"}, headers=AGENT).status_code == 403
    assert c.post(f"{BASE}/sites", json={"entry": "example.org"}, headers=OWNER).status_code == 422  # name the agent
    site = approve_site(c, "example.org", headers=OWNER, agent="hermes")
    rows = c.get(f"{BASE}/sites", headers=AGENT).json()
    assert [r["entry"] for r in rows] == ["example.org"] and rows[0]["plan_sha256"] == site["params"]["plan_sha256"]
    assert c.delete(f"{BASE}/sites/{rows[0]['id']}", headers=AGENT).status_code == 403
    assert c.delete(f"{BASE}/sites/{rows[0]['id']}", headers=OWNER).status_code == 200
    assert c.get(f"{BASE}/sites", headers=AGENT).json() == []
    assert c.delete(f"{BASE}/sessions/{sess['id']}", headers=OWNER).json()["state"] == "ended"
    start(c)
    start(c)
    r = c.post(f"{BASE}/sessions", json={}, headers=AGENT)
    assert r.status_code == 409 and r.json()["reason"] == "too_many_sessions"


def test_off_by_default(client):
    r = client.post(f"{BASE}/sessions", json={}, headers=AGENT)
    assert r.status_code == 409 and r.json()["reason"] == "agent_browser_off"


def test_url_rules():
    for bad in ("http://example.org/", "https://192.0.2.1/", "https://[::1]/", "https://user@localhost/",
                "https://example.org:8443/", "https://nas.local/", "https://localhost/", "ftp://example.org/"):
        with pytest.raises(policy.UrlRefused):
            policy.parse(bad)
    t = policy.parse("https://Docs.Example.org/a/b?token=x#frag")
    assert (t.host, t.url) == ("docs.example.org", "https://docs.example.org/a/b")
    assert policy.allowed("a.b.example.org", frozenset({"*.example.org"}))
    assert not policy.allowed("example.org", frozenset({"*.example.org"}))
    assert not policy.allowed("evilexample.org", frozenset({"example.org", "*.example.org"}))
    assert policy.classify(policy.parse("https://checkout.stripe.com/x"), "navigate") == "payment"
    assert policy.classify(policy.parse("https://shop.example.org/cart/checkout"), "navigate") == "payment"
    assert policy.classify(policy.parse("https://example.org/docs"), "submit") is None
    assert not policy.public_address("192.0.2.10") and not policy.public_address("::ffff:127.0.0.1")
    assert policy.public_address("93.184.215.14")


def test_pod_is_sealed():
    docs = session_docs("onemind-agent-browser", "abs_1", image="x@sha256:" + "b" * 64, control_token="t",
                        proxy_url="http://p", control_port=9300, lifetime_s=900, max_pages=5)
    pod = next(d for d in docs if d["kind"] == "Pod")
    assert pod["spec"]["automountServiceAccountToken"] is False and pod["spec"]["activeDeadlineSeconds"] == 900
    assert pod["metadata"]["labels"][SESSION_LABEL] == "ab-1"
    assert isolation_problems(pod) == []
    pod["spec"]["volumes"].append({"name": "cookies", "persistentVolumeClaim": {"claimName": "profile-x"}})
    pod["spec"]["containers"][0]["ports"].append({"containerPort": 9222})
    assert len(isolation_problems(pod)) == 2


def test_proxy_never_dials_a_private_address():
    import asyncio

    async def resolve(host, port):
        return ["127.0.0.1", "198.51.100.7"]

    proxy = EgressProxy(lambda *a: None, resolve=resolve)
    with pytest.raises(EgressRefused):
        asyncio.run(proxy._dial_public("approved.example.org", 443))


def test_idempotency_key_replays_without_a_second_pod_or_page(ab):
    c, cluster = ab["c"], ab["cluster"]
    approve_site(c, "example.org")
    key = {**AGENT, "Idempotency-Key": "start-1"}
    first = c.post(f"{BASE}/sessions", json={}, headers=key).json()
    assert c.post(f"{BASE}/sessions", json={}, headers=key).json()["id"] == first["id"]
    assert len(cluster.pods()) == 1
    visit = {**AGENT, "Idempotency-Key": "v-1"}
    url = f"{BASE}/sessions/{first['id']}/visit"
    a = c.post(url, json={"url": "https://example.org/a"}, headers=visit)
    b = c.post(url, json={"url": "https://example.org/a"}, headers=visit)
    assert a.status_code == b.status_code == 200 and b.json()["session"]["pages"] == 1 and len(ab["pages"]) == 1
    assert c.post(url, json={"url": "https://example.org/b"}, headers=visit).status_code == 409
