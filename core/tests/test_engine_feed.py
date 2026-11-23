# SPDX-License-Identifier: Apache-2.0
"""The Engine feed (issue #619): GET /v1/engine from the hub nats-server's loopback monitor.

Acceptance (issue #619): with two leaves up and one cut, the endpoint shows one link down within
60 seconds and the outbox lag after return; a non-owner gets only their own scope; no route returns
NATS credentials. The monitor answers below have the shape nats-server v2.15 gives (server/monitor.go),
with the fields that must never come back (client addresses, nkeys, JWTs, the store path, subjects)
filled in on purpose. The last test runs a real hub and two real leaves when nats-server is installed.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import socket
import subprocess
import threading
import time
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, GUEST, OWNER
from onemind_core.app import create_app
from onemind_core.auth import Principal
from onemind_core.engine import MonitorError, MonitorReader, Scope, check_url, scope_for, view
from onemind_core.engine.monitor import Snapshot, reduce_connz, reduce_jsz, reduce_leafz, reduce_varz
from onemind_core.identity.scopes import required_scopes
from onemind_core.netconf import FabricSettings

A, B = "aaaa1111", "bbbb2222"
CAP = 256 << 20
LEAKS = ("UAGATEWAYNKEYPUBLIC", "FAKE-JWT-MARKER-NOT-A-TOKEN", "192.0.2.10", "198.51.100.7", "/data/nats/js",
         "onemind.event.", "NSERVERIDSECRET", "hub-box.lan", "SUAENGINESEED")


def varz(**over):
    d = {"server_id": "NSERVERIDSECRET", "server_name": "hub-box.lan", "version": "2.15.3", "host": "127.0.0.1",
         "port": 4222, "uptime": "1h2m3s", "connections": 4, "total_connections": 9, "leafnodes": 2,
         "slow_consumers": 1, "slow_consumer_stats": {"clients": 1, "routes": 0, "gateways": 0, "leafs": 0},
         "in_msgs": 100, "out_msgs": 200,
         "jetstream": {"config": {"max_memory": 0, "max_storage": CAP, "store_dir": "/data/nats/js"}}}
    d.update(over)
    return d


def connz():
    def c(cid, acc, user):
        return {"cid": cid, "ip": "192.0.2.10", "port": 50000 + cid, "name": f"client-{cid}", "authorized_user": user,
                "account": acc, "jwt": "FAKE-JWT-MARKER-NOT-A-TOKEN", "subscriptions_list": ["onemind.event.x"]}
    conns = [c(1, "ONEMIND", "UAGATEWAYNKEYPUBLIC"), c(2, "ONEMIND", "hub-local"), c(3, f"NODE_{A}", "UAGATEWAYNKEYPUBLIC")]
    return {"server_id": "NSERVERIDSECRET", "num_connections": 3, "total": 3, "connections": conns}


def leafz(*up):
    leafs = [{"name": f"node-{n}", "account": f"NODE_{n}", "ip": "198.51.100.7", "port": 7422, "rtt": "1.2ms",
              "in_msgs": 5, "out_msgs": 3, "subscriptions": 4, "subscriptions_list": ["onemind.event.y"]} for n in up]
    return {"server_id": "NSERVERIDSECRET", "leafnodes": len(leafs), "leafs": leafs}


def jsz(lag_a=0, max_memory=0, max_storage=CAP, messages_a=7):
    def outbox(n, lag, msgs):
        return {"name": f"NODE_node_{n}_OUTBOX", "state": {"messages": msgs, "bytes": msgs * 100},
                "config": {"subjects": ["onemind.event.z"]},
                "sources": [{"name": "OUTBOX", "external": {"api": f"$JS.node-{n}.API"}, "lag": lag, "active": 1_500_000_000}]}
    return {"server_id": "NSERVERIDSECRET", "config": {"max_memory": max_memory, "max_storage": max_storage,
                                                        "store_dir": "/data/nats/js"},
            "memory": 0, "storage": 64 << 20, "reserved_storage": 128 << 20, "streams": 3, "consumers": 2,
            "messages": 20, "bytes": 64 << 20,
            "account_details": [{"name": "ONEMIND", "storage": 64 << 20, "stream_detail": [
                {"name": "ONEMIND_EVENTS", "state": {"messages": 3, "bytes": 300}, "config": {"subjects": ["onemind.event.>"]}},
                outbox(A, lag_a, messages_a), outbox(B, 0, 0)]}]}


class FakeMonitor:
    """The hub monitor as an httpx transport: each endpoint's answer can be changed by a test."""

    def __init__(self):
        self.answers = {"/varz": (200, varz()), "/connz": (200, connz()), "/jsz": (200, jsz()),
                        "/healthz": (200, {"status": "ok"}), "/leafz": (200, leafz(A, B))}
        self.calls: list[str] = []
        self.down = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("connection refused")
        self.calls.append(request.url.path)
        code, body = self.answers[request.url.path]
        return httpx.Response(code, json=body)


class Tick:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def mon():
    return FakeMonitor()


@pytest.fixture
def tick():
    return Tick()


@pytest.fixture
def eclient(settings, clock, executor, mon, tick):
    with TestClient(create_app(settings, clock=clock, executor=executor)) as c:
        c.app.state.engine.reader = MonitorReader(transport=httpx.MockTransport(mon.handler), monotonic=tick, clock=clock)
        yield c


def get(c, headers=OWNER, code=200):
    r = c.get("/v1/engine", headers=headers)
    assert r.status_code == code, r.text
    return r.json()


def node(body, nid):
    return next(n for n in body["nodes"] if n["node_id"] == nid)


# ---- the owner's view ----------------------------------------------------------------------------
def test_owner_sees_accounts_links_outbox_lag_jetstream_and_slow_consumers(eclient, mon):
    mon.answers["/jsz"] = (200, jsz(lag_a=12))
    body = get(eclient)
    assert body["scope"] == "all" and body["monitor"]["state"] == "up" and body["health"] == {"status": "ok", "error": None}
    accounts = {a["account"]: a for a in body["accounts"]}
    assert accounts["ONEMIND"]["connections"] == 2 and accounts["ONEMIND"]["node_id"] is None
    assert accounts[f"NODE_{A}"] == {"account": f"NODE_{A}", "node_id": A, "connections": 1, "leafnodes": 1,
                                     "jetstream_bytes": None}
    assert accounts["ONEMIND"]["jetstream_bytes"] == 64 << 20
    a = node(body, A)
    assert (a["link"], a["rtt"]) == ("up", "1.2ms")
    assert a["outbox"] == {"stream": f"NODE_node_{A}_OUTBOX", "messages": 7, "bytes": 700, "lag": 12,
                           "last_active_s": 1.5, "error": None}
    assert body["links"] == {"up": 2, "down": 0}
    js = body["jetstream"]
    assert (js["enabled"], js["used_bytes"], js["cap_bytes"], js["used_pct"]) == (True, 64 << 20, CAP, 25.0)
    assert body["slow_consumers"] == {"total": 1, "clients": 1, "routes": 0, "gateways": 0, "leafs": 0}
    assert body["server"]["version"] == "2.15.3" and body["server"]["uptime"] == "1h2m3s"


def test_no_credential_address_path_or_subject_is_returned(eclient):
    text = eclient.get("/v1/engine", headers=OWNER).text
    for leak in LEAKS:
        assert leak not in text, leak
    for key in ("authorized_user", "jwt", "ip", "store_dir", "server_id", "server_name", "subjects", "host"):
        assert f'"{key}"' not in text, key


def test_the_reducers_keep_only_allow_listed_fields():
    kept = json.dumps([reduce_varz(varz()), reduce_connz(connz()), reduce_leafz(leafz(A)), reduce_jsz(jsz())])
    for leak in LEAKS:
        assert leak not in kept, leak


# ---- two leaves, one cut ---------------------------------------------------------------------------
def test_two_leaves_one_cut_shows_the_link_down_and_the_lag_after_return(eclient, mon, tick):
    assert get(eclient)["links"] == {"up": 2, "down": 0}
    mon.answers["/leafz"] = (200, leafz(B))                 # node A's link is cut
    tick.t += 2.1                                          # past the 2 s cache: the next read is fresh
    body = get(eclient)
    assert node(body, A)["link"] == "down" and node(body, B)["link"] == "up"
    assert body["links"] == {"up": 1, "down": 1}
    mon.answers["/leafz"] = (200, leafz(A, B))              # back, with 40 messages still to copy
    mon.answers["/jsz"] = (200, jsz(lag_a=40, messages_a=7))
    tick.t += 2.1
    a = node(get(eclient), A)
    assert a["link"] == "up" and a["outbox"]["lag"] == 40
    mon.answers["/jsz"] = (200, jsz(lag_a=0, messages_a=47))
    tick.t += 2.1
    a = node(get(eclient), A)
    assert (a["outbox"]["lag"], a["outbox"]["messages"]) == (0, 47)


def test_a_joined_node_without_a_leaf_is_down_and_the_hub_itself_has_no_link(eclient, mon, tick, settings):
    from test_monitoring import beat

    beat(eclient, node_id="cccc3333")
    beat(eclient, node_id=settings.node_id)
    body = get(eclient)
    c = node(body, "cccc3333")
    assert (c["link"], c["heartbeat"], c["outbox"]) == ("down", "online", None)
    assert settings.node_id not in {n["node_id"] for n in body["nodes"]}


def test_reads_are_cached_for_two_seconds(eclient, mon, tick):
    get(eclient)
    get(eclient)
    assert mon.calls.count("/varz") == 1
    tick.t += 1.9
    get(eclient)
    assert mon.calls.count("/varz") == 1
    tick.t += 0.2
    get(eclient)
    assert mon.calls.count("/varz") == 2
    assert {"/varz", "/connz", "/jsz", "/healthz", "/leafz"} <= set(mon.calls)


# ---- NATS down, partial answers ---------------------------------------------------------------------
def test_nats_down_still_answers_and_says_so(eclient, mon):
    mon.down = True
    body = get(eclient)
    assert body["monitor"]["state"] == "down" and body["health"]["status"] == "unknown"
    assert set(body["monitor"]["errors"]) == {"varz", "connz", "jsz", "healthz", "leafz"}
    assert body["jetstream"]["enabled"] is None and body["nodes"] == [] and body["server"] is None


def test_unhealthy_nats_and_a_server_without_leaf_data(eclient, mon):
    from test_monitoring import beat

    beat(eclient, node_id=A)
    mon.answers["/healthz"] = (503, {"status": "unavailable", "error": "JetStream stream 'X' is not current"})
    mon.answers["/leafz"] = (404, {})
    body = get(eclient)
    assert body["health"] == {"status": "unavailable", "error": "JetStream stream 'X' is not current"}
    assert node(body, A)["link"] == "unknown" and "leafz" not in body["monitor"]["errors"]


# ---- must refuse: JetStream without a cap -------------------------------------------------------------
@pytest.mark.parametrize("over", [{"max_memory": 6 << 30}, {"max_storage": 0}])
def test_jetstream_without_a_cap_is_refused(eclient, mon, over):
    mon.answers["/jsz"] = (200, jsz(**over))
    js = get(eclient)["jetstream"]
    assert js["state"] == "refused" and "without a cap" in js["reason"]


def test_jetstream_off_in_nats_and_the_gateway_state_is_passed_through(eclient, mon):
    mon.answers["/jsz"] = (200, {"server_id": "N", "disabled": True})
    js = get(eclient)["jetstream"]
    assert js["enabled"] is False and js["state"] == "off" and js["cap_bytes"] is None


# ---- scope: a non-owner sees only their own ------------------------------------------------------------
@pytest.mark.parametrize("headers", [ADULT, GUEST, AGENT])
def test_non_owner_gets_the_summary_only(eclient, headers):
    body = get(eclient, headers)
    assert body["scope"] == "summary"
    assert body["accounts"] == [] and body["nodes"] == [] and body["server"] is None
    assert body["slow_consumers"] is None and body["monitor"]["errors"] == {}
    assert body["links"] == {"up": 2, "down": 0} and body["jetstream"]["cap_bytes"] == CAP


def test_a_node_sees_its_own_account_link_and_outbox_only():
    snap = Snapshot(at=__import__("datetime").datetime(2026, 11, 22, tzinfo=__import__("datetime").timezone.utc),
                    varz=reduce_varz(varz()), connz=reduce_connz(connz()), jsz=reduce_jsz(jsz(lag_a=3)),
                    healthz={"status": "ok", "error": None}, leafz=reduce_leafz(leafz(A, B)))
    body = view(snap, scope_for(Principal(id=f"node:{A}", kind="node", role="node")), jetstream=None, nodes=[],
                hub_node_id="hub")
    assert body["scope"] == "node"
    assert [n["node_id"] for n in body["nodes"]] == [A] and body["nodes"][0]["outbox"]["lag"] == 3
    assert [a["account"] for a in body["accounts"]] == [f"NODE_{A}"]
    assert body["server"] is None and body["slow_consumers"] is None and body["links"] == {"up": 1, "down": 0}


@pytest.mark.parametrize(("kind", "role", "want"), [
    ("person", "owner", Scope("all")), ("person", "adult", Scope("summary")), ("agent", "agent", Scope("summary")),
    ("person", "child", None), ("person", "teen", None), ("plugin", "plugin", None), ("automation", "automation", None),
    ("node", "node", None),   # a node principal whose id is not node:<node_id>
])
def test_scope_for(kind, role, want):
    assert scope_for(Principal(id="x y", kind=kind, role=role)) == want


def test_route_scopes_and_contract():
    assert required_scopes("GET", "/v1/engine") == ("monitoring:read", "nodes:report")


def test_openapi_documents_the_route_its_statuses_and_its_scopes(eclient):
    doc = eclient.get("/openapi.json").json()
    op = doc["paths"]["/v1/engine"]["get"]
    assert {"200", "401", "403"} <= set(op["responses"])
    assert op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/EngineView")
    assert op["security"] == [{"bearer": ["monitoring:read", "nodes:report"]}]
    assert doc["components"]["securitySchemes"]["bearer"]["scheme"] == "bearer"


def test_unauthenticated_is_401(eclient):
    assert eclient.get("/v1/engine").status_code == 401


# ---- loopback only --------------------------------------------------------------------------------
@pytest.mark.parametrize("url", ["http://192.0.2.1:8222", "https://127.0.0.1:8222", "http://user:pw@127.0.0.1:8222",
                                 "http://127.0.0.1:8222/varz", "http://example.com:8222", "http://127.0.0.1:8222?x=1"])
def test_the_monitor_is_read_on_loopback_only(url):
    with pytest.raises(MonitorError):
        check_url(url)


def test_loopback_urls_are_accepted():
    assert check_url("http://127.0.0.1:8222/") == "http://127.0.0.1:8222"
    assert check_url("http://[::1]:8222") == "http://[::1]:8222"


# ---- no route returns NATS credentials ---------------------------------------------------------------
def test_no_route_returns_the_nats_seed(settings, clock, executor, tmp_path, mon):
    seed = tmp_path / "gateway.nk"
    seed.write_text("SUAENGINESEEDNEVERRETURNEDBYANYROUTE0000000000000000000000\n")
    s = replace(settings, sections={**settings.sections, "fabric": FabricSettings(nats_nkey_seed=seed)})
    with TestClient(create_app(s, clock=clock, executor=executor)) as c:
        c.app.state.engine.reader = MonitorReader(transport=httpx.MockTransport(mon.handler), clock=clock)
        live = {r.path for r in c.app.routes if "GET" in getattr(r, "methods", ())}
        paths = [p for p in ("/v1/engine", "/v1/fabric", "/v1/mesh", "/v1/nodes", "/v1/status", "/v1/instance",
                             "/v1/os/about", "/v1/monitoring/summary", "/openapi.json") if p in live]
        assert "/v1/engine" in paths and len(paths) >= 5
        for p in paths:
            r = c.get(p, headers=OWNER)
            assert "SUAENGINESEED" not in r.text and "FAKE-JWT-MARKER" not in r.text, p


# ---- a real hub and two real leaves ------------------------------------------------------------------
NATS_SERVER = shutil.which("nats-server")
needs_server = pytest.mark.skipif(NATS_SERVER is None, reason="nats-server is not installed")


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Cut:
    """A TCP relay in front of the hub's leaf port. cut() stops relaying without closing (a dead cable:
    the hub only notices when its pings go unanswered); restore() drops the dead pipes and relays again."""

    def __init__(self, target: int):
        self.target, self.cut_now, self.pipes = target, False, []
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen()
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            if self.cut_now:
                conn.close()
                continue
            up = socket.create_connection(("127.0.0.1", self.target))
            self.pipes += [conn, up]
            for a, b in ((conn, up), (up, conn)):
                threading.Thread(target=self._pump, args=(a, b), daemon=True).start()

    def _pump(self, src, dst):
        try:
            while data := src.recv(65536):
                if not self.cut_now:
                    dst.sendall(data)
        except OSError:
            pass

    def cut(self):
        self.cut_now = True

    def restore(self):
        for s in self.pipes:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            s.close()
        self.pipes = []
        self.cut_now = False

    def close(self):
        self.restore()
        self.sock.close()


def _server(tmp_path, name: str, body: str):
    conf = tmp_path / f"{name}.conf"
    conf.write_text(body)
    return subprocess.Popen([NATS_SERVER, "-c", str(conf)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _wait_port(port: int):
    end = time.time() + 10
    while time.time() < end:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.05)
    raise RuntimeError(f"nothing listens on {port}")


@needs_server
def test_real_hub_two_leaves_one_cut_link_down_within_60s_and_lag_after_return(settings, clock, executor, tmp_path):
    import nats
    from nats.js.api import ExternalStream, StorageType, StreamConfig, StreamSource

    hub, mon_port, leaf_port, a_port, b_port = _port(), _port(), _port(), _port(), _port()
    pings = 'ping_interval: "1s"\nping_max: 2\n'
    procs = [_server(tmp_path, "hub", f'server_name: hub\nlisten: "127.0.0.1:{hub}"\nhttp: "127.0.0.1:{mon_port}"\n{pings}'
                     f'jetstream {{\n  store_dir: "{tmp_path / "hub-js"}"\n  domain: hub\n  max_file_store: {CAP}\n'
                     f'  max_memory_store: 0\n}}\nleafnodes {{ listen: "127.0.0.1:{leaf_port}" }}\n')]
    _wait_port(leaf_port)
    relay = Cut(leaf_port)

    def leaf(name, port, remote, js):
        jsb = (f'jetstream {{\n  store_dir: "{tmp_path / name}"\n  domain: {name}\n  max_file_store: {CAP}\n'
               '  max_memory_store: 0\n}\n') if js else ""
        return _server(tmp_path, name, f'server_name: {name}\nlisten: "127.0.0.1:{port}"\n{pings}{jsb}'
                                       f'leafnodes {{\n  reconnect: "1s"\n  remotes: [{{url: "nats-leaf://127.0.0.1:{remote}"}}]\n}}\n')

    procs += [leaf(f"node-{A}", a_port, relay.port, True), leaf(f"node-{B}", b_port, leaf_port, False)]
    try:
        with TestClient(create_app(settings, clock=clock, executor=executor)) as c:
            c.app.state.engine.reader = MonitorReader(f"http://127.0.0.1:{mon_port}", ttl=0.2)

            async def feed():
                r = await asyncio.to_thread(c.get, "/v1/engine", headers=OWNER)
                assert r.status_code == 200, r.text
                return r.json()

            async def until(pred, timeout):
                end, body = time.monotonic() + timeout, None
                while time.monotonic() < end:
                    body = await feed()
                    if pred(body):
                        return body
                    await asyncio.sleep(0.25)
                raise AssertionError(f"not reached in {timeout} s: {body}")

            def link(body, nid):
                return next((n["link"] for n in body["nodes"] if n["node_id"] == nid), None)

            def outbox(body):
                return next((n["outbox"] for n in body["nodes"] if n["node_id"] == A), None) or {}

            async def scenario():
                await until(lambda b: link(b, A) == "up" and link(b, B) == "up", 20)
                leaf_nc, hub_nc = await nats.connect(f"nats://127.0.0.1:{a_port}"), await nats.connect(f"nats://127.0.0.1:{hub}")
                await leaf_nc.jetstream().add_stream(StreamConfig(name="OUTBOX", subjects=[f"outbox.{A}.>"],
                                                                  storage=StorageType.FILE, max_bytes=16 << 20))
                await hub_nc.jetstream().add_stream(StreamConfig(
                    name=f"NODE_node_{A}_OUTBOX", storage=StorageType.FILE, max_bytes=16 << 20,
                    sources=[StreamSource(name="OUTBOX", external=ExternalStream(api=f"$JS.node-{A}.API"))]))
                ljs = leaf_nc.jetstream()
                for i in range(3):
                    await ljs.publish(f"outbox.{A}.status", f"{i}".encode())
                await until(lambda b: outbox(b).get("messages") == 3 and outbox(b).get("lag") == 0, 30)

                relay.cut()
                cut_at = time.monotonic()
                body = await until(lambda b: link(b, A) == "down", 60)
                assert time.monotonic() - cut_at < 60
                assert link(body, B) == "up" and body["links"] == {"up": 1, "down": 1}
                for i in range(20):                                  # written while the link is down
                    await ljs.publish(f"outbox.{A}.status", f"late-{i}".encode())

                relay.restore()
                await until(lambda b: link(b, A) == "up", 60)
                body = await until(lambda b: outbox(b).get("messages") == 23, 60)
                assert outbox(body)["lag"] == 0 and isinstance(outbox(body)["last_active_s"], float)
                assert body["jetstream"]["cap_bytes"] == CAP and body["jetstream"]["used_bytes"] > 0
                assert "192.0.2" not in json.dumps(body) and "127.0.0.1" not in json.dumps(body)
                await leaf_nc.drain()
                await hub_nc.drain()

            asyncio.run(scenario())
    finally:
        relay.close()
        for p in procs:
            p.terminate()
            p.wait(10)
