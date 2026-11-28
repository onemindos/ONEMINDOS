# SPDX-License-Identifier: Apache-2.0
"""The app proxy honours the exposure tier and per-app sharing (UMB-P02b, #285).

Everything goes through `create_app`: the real gateway with household accounts, the real router
wiring in routers/net.py, and a real HTTP upstream on loopback (kubectl is the only stand-in; it
answers with the upstream's address as k3s would answer with a ClusterIP).

- Exposure (§12.22): a private app answers on its LAN names and is 404 on its mesh name
  (<app>.apps.onemind.internal); a mesh or public app answers on both.
- Network path (#285): the tier is also enforced by where the request came from (LAN, mesh, Tor,
  public), not only the Host header, so a LAN-only app cannot be reached from the internet by
  sending its LAN name. Anything that cannot be told fails closed.
- Sharing (§12.6): a guest or child the app is not shared with gets 404 on the app's host, as in
  GET /v1/apps, over HTTP, WebSocket and /v1/auth/forward. Sharing is instant to remove.
"""

from __future__ import annotations

import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import yaml
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import onemind_core.routers.net as net_router
from onemind_core.app import create_app
from onemind_core.netconf import NetSettings
from onemind_core.netpath import path_of_peer
from onemind_core.serve import pinned_path_app
from conftest import OWNER
from test_identity import PASSWORD, SoftAuthenticator, csrf, enrol, id_settings, register_passkey, setup_owner, stepped

APP = "whoami"
LAN, MESH = f"{APP}.onemind.local", f"{APP}.apps.onemind.internal"
LAN_PEER = "192.168.1.20"  # the socket peer of a household device on the LAN (the path rule reads it)


class Hello(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (http.server API)
        body = b"hello from the app"
        self.send_response(200)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


@pytest.fixture
def upstream():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Hello)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    thread.join(5)


@pytest.fixture
def box(settings, clock, executor, upstream, monkeypatch):
    # The app's web port is the upstream's, and anyone signed in may open it (the sharing rule,
    # not the access level, is what these tests are about).
    path = settings.apps_dir / APP / "onemind.app.yaml"
    manifest = yaml.safe_load(path.read_text())
    manifest["spec"]["web"] = {"port": upstream, "access": "signed_in"}
    path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    monkeypatch.setattr(net_router, "KubectlServiceResolver", lambda _kubectl: (lambda _ns, _port: "127.0.0.1"))
    app = create_app(id_settings(settings), clock=clock, executor=executor)
    app.state.repo.set_app_state(APP, "installed", clock.now)
    with TestClient(app, client=(LAN_PEER, 50000)) as c:
        setup_owner(c)
        yield c


def open_app(box: TestClient, token: str, host: str):
    return box.get("/", headers={"Host": host, "Authorization": f"Bearer {token}"})


def session_token(box: TestClient, username: str) -> str:
    c = TestClient(box.app, client=(LAN_PEER, 50000))
    if username == "zeus":
        if not getattr(box, "passkey", None):
            register_passkey(box, SoftAuthenticator())
        key = box.passkey
    else:
        # These tests exercise exposure tiers after an authenticated remote sign-in.
        r = c.post("/v1/auth/login", json={"username": username, "password": PASSWORD})
        assert r.status_code == 200, r.text
        key = SoftAuthenticator()
        register_passkey(c, key)
    opts = c.post("/v1/auth/login/options")
    assert opts.status_code == 200, opts.text
    r = c.post("/v1/auth/login", json={"passkey": key.assert_(opts.json()["publicKey"]["challenge"]), "client": "cli"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def set_tier(box: TestClient, clock, tier: str) -> None:
    box.app.state.appstore.repo.set_exposure(APP, tier, None, clock.now)


def test_a_private_app_is_404_on_its_mesh_name_and_opens_on_its_lan_name(box, clock):
    token = session_token(box, "zeus")
    lan = open_app(box, token, LAN)
    assert lan.status_code == 200 and lan.text == "hello from the app"
    mesh = open_app(box, token, MESH)
    assert mesh.status_code == 404 and mesh.text == "No such app."


@pytest.mark.parametrize("tier", ["mesh", "public"])
def test_a_mesh_or_public_app_opens_on_both(box, clock, tier):
    set_tier(box, clock, tier)
    token = session_token(box, "zeus")
    assert open_app(box, token, LAN).status_code == 200
    assert open_app(box, token, MESH).status_code == 200


def test_going_back_to_private_closes_the_mesh_name_at_once(box, clock):
    token = session_token(box, "zeus")
    set_tier(box, clock, "mesh")
    assert open_app(box, token, MESH).status_code == 200
    set_tier(box, clock, "private")
    assert open_app(box, token, MESH).status_code == 404


def test_a_person_the_app_is_not_shared_with_gets_404_as_in_the_app_list(box, clock):
    guest = enrol(box, "guest", "gus")
    token = session_token(box, "gus")
    assert guest.get("/v1/apps").json() == []  # not listed ...
    r = open_app(box, token, LAN)  # ... and not openable
    assert r.status_code == 404 and r.text == "No such app."
    # an installed-but-stopped app does not tell them it exists either
    box.app.state.repo.set_app_state(APP, "stopped", clock.now)
    assert open_app(box, token, LAN).status_code == 404


def test_sharing_opens_the_app_and_removing_it_closes_it_at_once(box):
    gus_client = enrol(box, "guest", "gus")
    enrol(box, "guest", "gia")
    gus, gia = session_token(box, "gus"), session_token(box, "gia")
    gid = gus_client.get("/v1/me").json()["principal"]["id"]
    r = stepped(box, "PUT", f"/v1/apps/{APP}/access", json={"roles": [], "people": [gid]})
    assert r.status_code == 200, r.text
    assert open_app(box, gus, LAN).status_code == 200
    assert open_app(box, gia, LAN).status_code == 404  # shared with Gus, not with Gia
    assert stepped(box, "PUT", f"/v1/apps/{APP}/access", json={"roles": ["guest"], "people": []}).status_code == 200
    assert open_app(box, gus, LAN).status_code == 200 and open_app(box, gia, LAN).status_code == 200
    assert stepped(box, "PUT", f"/v1/apps/{APP}/access", json={"roles": [], "people": []}).status_code == 200
    assert open_app(box, gus, LAN).status_code == 404 and open_app(box, gia, LAN).status_code == 404


def test_owners_and_adults_open_every_app_without_sharing(box):
    enrol(box, "adult", "ana")
    assert open_app(box, session_token(box, "zeus"), LAN).status_code == 200
    assert open_app(box, session_token(box, "ana"), LAN).status_code == 200


def test_static_file_tokens_keep_opening_apps(box):
    # v0 principals (the tokens file) have no household identity; sharing does not apply to them
    token = OWNER["Authorization"].split(" ", 1)[1]
    assert open_app(box, token, LAN).status_code == 200


def test_an_unknown_session_token_is_signed_out(box):
    assert open_app(box, "om_ses_" + "x" * 40, LAN).status_code == 401


def test_a_websocket_to_an_unshared_app_is_refused(box):
    enrol(box, "guest", "gus")
    token = session_token(box, "gus")
    with pytest.raises(WebSocketDisconnect) as closed:
        with box.websocket_connect("/ws", headers={"Host": LAN, "Origin": f"https://{LAN}",
                                                   "Authorization": f"Bearer {token}"}):
            pass
    assert closed.value.code == 1008


def test_forward_auth_agrees_with_the_proxy(box, clock, monkeypatch):
    monkeypatch.setattr(net_router, "_is_loopback", lambda _request: True)
    guest = enrol(box, "guest", "gus")
    token = session_token(box, "gus")

    def ask(host: str):
        return box.get("/v1/auth/forward", headers={"X-Forwarded-Host": host, "Authorization": f"Bearer {token}",
                                                      "X-OneMind-Path": "lan"})

    assert ask(LAN).status_code == 404  # not shared
    gid = guest.get("/v1/me").json()["principal"]["id"]
    assert stepped(box, "PUT", f"/v1/apps/{APP}/access", json={"roles": [], "people": [gid]}).status_code == 200
    ok = ask(LAN)
    assert ok.status_code == 204 and ok.headers["x-onemind-role"] == "guest"
    assert ask(MESH).status_code == 404  # shared, but the app is private: no mesh name
    set_tier(box, clock, "mesh")
    assert ask(MESH).status_code == 204


@pytest.mark.parametrize("scopes", [["instance:read"], ["apps:read"]])
def test_a_scoped_api_token_does_not_open_an_app_host(box, scopes):
    # An API token is scoped to routes; an app host is whole-app interactive access, so only a
    # household session (or a tokens-file principal) opens it, whatever read scope the token has.
    r = box.post("/v1/tokens", json={"name": "widget", "scopes": scopes}, headers=csrf(box))
    assert r.status_code in (200, 201), r.text
    token = r.json()["one_time"]["token"]
    assert open_app(box, token, LAN).status_code == 401


# ---- the network path, not the Host header (#285 follow-up) --------------------------------------
LAN_V4, LAN_V6, LAN_MAPPED = LAN_PEER, "fd12:3456::5", "::ffff:192.168.1.20"
MESH_V4, MESH_V6 = "100.64.0.7", "fd7a:115c:a1e0::7"
PUBLIC_V4, PUBLIC_V6 = "93.184.216.34", "2001:4860:4860::8888"
UNTELLABLE = ["127.0.0.1", "::1", "testclient", "0.0.0.0", "224.0.0.1"]  # loopback, junk, multicast
# "private" to Python's ipaddress, yet not the home LAN: reachable from the internet or reserved
NOT_LAN = ["2001:0:5ef5:79fd::1", "2002:808:808::1", "2001:db8::1", "198.18.0.1", "240.0.0.1"]  # Teredo, 6to4, docs, benchmark, reserved
ALL_PEERS = [LAN_V4, LAN_V6, LAN_MAPPED, MESH_V4, MESH_V6, PUBLIC_V4, PUBLIC_V6, *UNTELLABLE, *NOT_LAN]
ADMITTED = {  # tier -> the peers that may open the app
    "private": {LAN_V4, LAN_V6, LAN_MAPPED},
    "mesh": {LAN_V4, LAN_V6, LAN_MAPPED, MESH_V4, MESH_V6},
    "public": {LAN_V4, LAN_V6, LAN_MAPPED, MESH_V4, MESH_V6, PUBLIC_V4, PUBLIC_V6},
}


@pytest.mark.parametrize("peer", NOT_LAN)
def test_ranges_python_calls_private_but_the_internet_can_reach_are_not_the_lan(peer):
    assert path_of_peer(peer) != "lan"


def from_peer(box: TestClient, peer: str) -> TestClient:
    return TestClient(box.app, client=(peer, 50000))


@pytest.mark.parametrize("tier", ["private", "mesh", "public"])
@pytest.mark.parametrize("host", [LAN, MESH])
@pytest.mark.parametrize("peer", ALL_PEERS)
def test_the_tier_is_enforced_by_the_path_whatever_host_the_client_sends(box, clock, tier, host, peer):
    set_tier(box, clock, tier)
    token = session_token(box, "zeus")
    r = open_app(from_peer(box, peer), token, host)
    # the name rule still closes the mesh name of a private app, for everyone
    open_here = peer in ADMITTED[tier] and not (host == MESH and tier == "private")
    assert (r.status_code, r.text == "hello from the app") == ((200, True) if open_here else (404, False)), \
        (tier, host, peer, r.status_code)


def test_a_lan_name_over_a_public_path_does_not_open_a_private_app(box):
    token = session_token(box, "zeus")
    assert open_app(from_peer(box, LAN_V4), token, LAN).status_code == 200
    r = open_app(from_peer(box, PUBLIC_V4), token, LAN)  # the spoof: right name, wrong road
    assert r.status_code == 404 and r.text == "No such app."


def test_claiming_to_be_the_lan_in_a_header_changes_nothing_from_an_untrusted_peer(box):
    token = session_token(box, "zeus")
    c = from_peer(box, PUBLIC_V4)
    for spoof in ({"X-OneMind-Path": "lan"}, {"X-Forwarded-For": LAN_V4}, {"Forwarded": f"for={LAN_V4}"},
                  {"X-Real-IP": LAN_V4}, {"X-Forwarded-Host": LAN}):
        r = c.get("/", headers={"Host": LAN, "Authorization": f"Bearer {token}", **spoof})
        assert r.status_code == 404, spoof


def test_the_path_is_judged_for_the_app_path_route_too(box, monkeypatch):
    # the /apps/<id>/ route is off by default; it must obey the same rule when on
    proxy = next(m for m in box.app.user_middleware if m.cls is net_router.AppProxyMiddleware).kwargs["proxy"]
    monkeypatch.setattr(proxy, "path_routes", True)
    token = session_token(box, "zeus")
    ok = from_peer(box, LAN_V4).get(f"/apps/{APP}/", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200
    bad = from_peer(box, PUBLIC_V4).get(f"/apps/{APP}/", headers={"Authorization": f"Bearer {token}"})
    assert bad.status_code == 404


def test_a_stopped_app_does_not_reveal_itself_to_a_path_that_may_not_open_it(box, clock):
    token = session_token(box, "zeus")
    box.app.state.repo.set_app_state(APP, "stopped", clock.now)
    assert open_app(from_peer(box, LAN_V4), token, LAN).status_code == 503
    r = open_app(from_peer(box, PUBLIC_V4), token, LAN)
    assert r.status_code == 404 and "stopped" not in r.text.lower()


def test_a_websocket_over_a_path_the_tier_does_not_admit_is_refused(box):
    token = session_token(box, "zeus")
    with pytest.raises(WebSocketDisconnect) as closed:
        with from_peer(box, PUBLIC_V4).websocket_connect(
            "/ws", headers={"Host": LAN, "Origin": f"https://{LAN}", "Authorization": f"Bearer {token}"}
        ):
            pass
    assert closed.value.code == 1008


@pytest.mark.parametrize("tier,path,code", [
    ("private", "lan", 204), ("private", "mesh", 404), ("private", "tor", 404), ("private", "public", 404),
    ("mesh", "lan", 204), ("mesh", "mesh", 204), ("mesh", "tor", 404), ("mesh", "public", 404),
    ("public", "lan", 204), ("public", "mesh", 204), ("public", "tor", 204), ("public", "public", 204),
    ("private", None, 404), ("public", None, 404), ("public", "nonsense", 404), ("public", "LAN, public", 404),
])
def test_forward_auth_takes_the_path_from_the_edge_and_fails_closed(box, clock, monkeypatch, tier, path, code):
    monkeypatch.setattr(net_router, "_is_loopback", lambda _request: True)
    set_tier(box, clock, tier)
    token = session_token(box, "zeus")
    headers = {"X-Forwarded-Host": LAN, "Authorization": f"Bearer {token}"}
    if path is not None:
        headers["X-OneMind-Path"] = path
    assert box.get("/v1/auth/forward", headers=headers).status_code == code


@pytest.fixture
def edge_box(settings, clock, executor, upstream, monkeypatch):
    """The same box with a trusted edge on loopback (ONEMIND_NET_TRUSTED_PROXIES)."""
    path = settings.apps_dir / APP / "onemind.app.yaml"
    manifest = yaml.safe_load(path.read_text())
    manifest["spec"]["web"] = {"port": upstream, "access": "signed_in"}
    path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    monkeypatch.setattr(net_router, "KubectlServiceResolver", lambda _kubectl: (lambda _ns, _port: "127.0.0.1"))
    with_edge = id_settings(settings)
    with_edge = replace(with_edge, sections={**with_edge.sections, "net": NetSettings(trusted_proxies="127.0.0.0/8, ::1")})
    app = create_app(with_edge, clock=clock, executor=executor)
    app.state.repo.set_app_state(APP, "installed", clock.now)
    with TestClient(app, client=(LAN_PEER, 50000)) as c:
        setup_owner(c)
        yield c


@pytest.mark.parametrize("tier,path,code", [
    ("private", "lan", 200), ("private", "mesh", 404), ("private", "tor", 404), ("private", "public", 404),
    ("mesh", "mesh", 200), ("mesh", "tor", 404), ("mesh", "public", 404),
    ("public", "tor", 200), ("public", "public", 200),
    ("public", None, 404), ("public", "bogus", 404), ("private", None, 404),
])
def test_a_trusted_edge_states_the_path_and_silence_is_unknown(edge_box, clock, tier, path, code):
    set_tier(edge_box, clock, tier)
    token = session_token(edge_box, "zeus")
    extra = {} if path is None else {"X-OneMind-Path": path}
    r = from_peer(edge_box, "127.0.0.1").get("/", headers={"Host": LAN, "Authorization": f"Bearer {token}", **extra})
    assert r.status_code == code, (tier, path)


def test_the_edges_word_is_not_taken_from_a_peer_that_is_not_the_edge(edge_box, clock):
    set_tier(edge_box, clock, "private")
    token = session_token(edge_box, "zeus")
    r = from_peer(edge_box, PUBLIC_V4).get("/", headers={"Host": LAN, "Authorization": f"Bearer {token}",
                                                        "X-OneMind-Path": "lan"})
    assert r.status_code == 404
    # a client of the edge cannot smuggle the header past it: the app never sees X-OneMind-Path from clients
    assert from_peer(edge_box, LAN_V4).get("/", headers={"Host": LAN, "Authorization": f"Bearer {token}",
                                                        "X-OneMind-Path": "public"}).status_code == 200


def test_trusted_proxies_must_be_networks(settings):
    with pytest.raises(ValueError, match="TRUSTED_PROXIES"):
        NetSettings(trusted_proxies="not-an-ip").validate()
    NetSettings(trusted_proxies="127.0.0.0/8,::1").validate()


# ---- the Tor listener pins the path (#284, §12.22) ------------------------------------------------------

POD_PEER = LAN_PEER  # a pod or masqueraded peer: inside a private range, so by its socket alone it reads as the LAN


def from_tor_listener(box: TestClient, peer: str = POD_PEER) -> TestClient:
    return TestClient(pinned_path_app(box.app, "tor"), client=(peer, 50000))


def test_a_private_peer_alone_reads_as_the_lan_so_only_the_listener_can_say_tor():
    assert path_of_peer(POD_PEER) == "lan"


@pytest.mark.parametrize("tier,code", [("private", 404), ("mesh", 404), ("public", 200)])
@pytest.mark.parametrize("host", [LAN, MESH])
def test_a_request_on_the_tor_listener_opens_only_a_public_app(box, clock, tier, code, host):
    set_tier(box, clock, tier)
    token = session_token(box, "zeus")
    r = open_app(from_tor_listener(box), token, host)
    opened = r.status_code == 200
    assert opened == (code == 200), (tier, host, r.status_code)
    # the same peer on the ordinary listener is the LAN: this is the bypass the listener closes
    if tier == "private" and host == LAN:
        assert open_app(from_peer(box, POD_PEER), token, host).status_code == 200


def test_the_tor_listener_ignores_a_path_header_and_the_app_path_route_obeys_it_too(box, clock, monkeypatch):
    proxy = next(m for m in box.app.user_middleware if m.cls is net_router.AppProxyMiddleware).kwargs["proxy"]
    monkeypatch.setattr(proxy, "path_routes", True)
    token = session_token(box, "zeus")
    c = from_tor_listener(box)
    for tier in ("private", "mesh"):
        set_tier(box, clock, tier)
        r = c.get(f"/apps/{APP}/", headers={"Authorization": f"Bearer {token}", "X-OneMind-Path": "lan"})
        assert r.status_code == 404, tier
    set_tier(box, clock, "public")
    assert c.get(f"/apps/{APP}/", headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_a_websocket_on_the_tor_listener_is_refused_for_a_private_app(box):
    token = session_token(box, "zeus")
    with pytest.raises(WebSocketDisconnect):
        with from_tor_listener(box).websocket_connect("/ws", headers={"Host": LAN, "Authorization": f"Bearer {token}"}):
            pass
