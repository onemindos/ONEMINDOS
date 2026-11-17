# SPDX-License-Identifier: Apache-2.0
"""The app proxy honours the exposure tier and per-app sharing (UMB-P02b, #285).

Everything goes through `create_app`: the real gateway with household accounts, the real router
wiring in routers/net.py, and a real HTTP upstream on loopback (kubectl is the only stand-in; it
answers with the upstream's address as k3s would answer with a ClusterIP).

- Exposure (§12.22): a private app answers on its LAN names and is 404 on its mesh name
  (<app>.apps.onemind.internal); a mesh or public app answers on both.
- Sharing (§12.6): a guest or child the app is not shared with gets 404 on the app's host, as in
  GET /v1/apps, over HTTP, WebSocket and /v1/auth/forward. Sharing is instant to remove.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import yaml
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import onemind_core.routers.net as net_router
from onemind_core.app import create_app
from conftest import OWNER
from test_identity import PASSWORD, csrf, enrol, id_settings, setup_owner

APP = "whoami"
LAN, MESH = f"{APP}.onemind.local", f"{APP}.apps.onemind.internal"


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
    with TestClient(app) as c:
        setup_owner(c)
        yield c


def open_app(box: TestClient, token: str, host: str):
    return box.get("/", headers={"Host": host, "Authorization": f"Bearer {token}"})


def session_token(box: TestClient, username: str) -> str:
    r = TestClient(box.app).post("/v1/auth/login", json={"username": username, "password": PASSWORD, "client": "cli"})
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
    r = box.put(f"/v1/apps/{APP}/access", json={"roles": [], "people": [gid]}, headers=csrf(box))
    assert r.status_code == 200, r.text
    assert open_app(box, gus, LAN).status_code == 200
    assert open_app(box, gia, LAN).status_code == 404  # shared with Gus, not with Gia
    box.put(f"/v1/apps/{APP}/access", json={"roles": ["guest"], "people": []}, headers=csrf(box))
    assert open_app(box, gus, LAN).status_code == 200 and open_app(box, gia, LAN).status_code == 200
    box.put(f"/v1/apps/{APP}/access", json={"roles": [], "people": []}, headers=csrf(box))
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
        return box.get("/v1/auth/forward", headers={"X-Forwarded-Host": host, "Authorization": f"Bearer {token}"})

    assert ask(LAN).status_code == 404  # not shared
    gid = guest.get("/v1/me").json()["principal"]["id"]
    box.put(f"/v1/apps/{APP}/access", json={"roles": [], "people": [gid]}, headers=csrf(box))
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
