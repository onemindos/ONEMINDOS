# SPDX-License-Identifier: Apache-2.0
"""Opening an installed app, end to end over HTTPS (UMB-P02, #139).

The real entrypoint (`python -m onemind_core`) runs with ONEMIND_NET_TLS=1, so serve.py serves the
gateway over HTTPS with the box CA. The app's upstream is a real HTTP server on loopback; the only
stand-in is kubectl, a script that answers `kubectl get services` with that server's address, as
k3s would answer with the app's ClusterIP.

The client does what the dashboard's Open button does: ask the gateway for the app-host cookie
(POST /v1/auth/app-session with the person's token), then open https://<app>.onemind.local/
with that cookie, verifying the certificate against the box CA by the app's name.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
import yaml

from onemind_core.app import create_app
from conftest import ADULT, EXAMPLES, OWNER

CORE = Path(__file__).resolve().parents[1]
REPO_APPS = CORE.parent / "apps"
# Two real Market apps, so the catalog check is the one the box runs (the repo's app schema).
OPEN_APP, STOPPED_APP = "actual-budget", "audiobookshelf"
STARTING_APP, DOWN_APP = "bazarr", "komga"
pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the gateway runs on Linux and macOS")


HITS: list[str] = []  # every request that reached the app's upstream


class Echo(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (http.server API)
        HITS.append(f"GET {self.path}")
        body = json.dumps({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _other(self):
        HITS.append(f"{self.command} {self.path}")
        self.send_response(204)
        self.end_headers()

    do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = _other  # noqa: N815 (http.server API)

    def log_message(self, *_):
        pass


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def upstream():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Echo)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    thread.join(5)


@pytest.fixture
def box(settings, tmp_path, upstream, clock):
    """The gateway process, HTTPS on, one app installed and one stopped."""
    apps = tmp_path / "market"
    dead = free_port()  # nothing listens here: an installed app that does not answer
    for app_id in (OPEN_APP, STOPPED_APP, STARTING_APP, DOWN_APP):
        shutil.copytree(REPO_APPS / app_id, apps / app_id)
        path = apps / app_id / "onemind.app.yaml"
        m = yaml.safe_load(path.read_text())
        m["spec"]["web"]["port"] = dead if app_id == DOWN_APP else upstream  # where the upstream listens
        path.write_text(yaml.safe_dump(m, sort_keys=False))
    # The ledger as installs left it (create_app makes the tables).
    gw = create_app(settings, clock=clock)
    gw.state.repo.set_app_state(OPEN_APP, "installed", clock.now)
    gw.state.repo.set_app_state(STOPPED_APP, "stopped", clock.now)
    gw.state.repo.set_app_state(STARTING_APP, "installing", clock.now)
    gw.state.repo.set_app_state(DOWN_APP, "installed", clock.now)
    if hasattr(gw.state.repo, "close"):
        gw.state.repo.close()

    kubectl = tmp_path / "kubectl"
    services = {"items": [{"metadata": {"name": "web"}, "spec": {
        "type": "ClusterIP", "clusterIP": "127.0.0.1", "ports": [{"port": upstream, "protocol": "TCP"}, {"port": dead, "protocol": "TCP"}]}}]}
    kubectl.write_text(f"#!{sys.executable}\nimport sys\nprint({json.dumps(json.dumps(services))})\n")
    kubectl.chmod(0o755)

    https_port, plain_port = free_port(), free_port()
    env = {
        "PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path),
        "ONEMIND_DATA_DIR": str(tmp_path / "data"), "ONEMIND_DB_URL": settings.db_url,
        "ONEMIND_TOKENS_FILE": str(EXAMPLES / "tokens.example.yaml"), "ONEMIND_APPS_DIR": str(apps),
        "ONEMIND_AUDIT_PATH": str(tmp_path / "audit.jsonl"), "ONEMIND_NATS_URL": "",
        "ONEMIND_NODE_ID": "abc123def456", "ONEMIND_KUBECTL": str(kubectl),
        "ONEMIND_HOST": "127.0.0.1", "ONEMIND_PORT": str(plain_port),
        "ONEMIND_NET_TLS": "1", "ONEMIND_NET_BOX_NAME": "box1", "ONEMIND_NET_TLS_DIR": str(tmp_path / "tls"),
        "ONEMIND_NET_HTTPS_HOST": "127.0.0.1", "ONEMIND_NET_HTTPS_PORTS": str(https_port),
        # The test client connects over loopback, which says nothing about the real path (#285): it plays
        # the trusted edge and states the path itself with X-OneMind-Path.
        "ONEMIND_NET_TRUSTED_PROXIES": "127.0.0.0/8",
    }
    proc = subprocess.Popen([sys.executable, "-m", "onemind_core"], cwd=CORE, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        ca = tmp_path / "tls" / "ca.crt"
        deadline = time.time() + 60
        while time.time() < deadline and proc.poll() is None:
            try:
                with socket.create_connection(("127.0.0.1", https_port), timeout=0.5):
                    if ca.is_file():
                        break
            except OSError:
                time.sleep(0.2)
        if proc.poll() is not None or not ca.is_file():
            out = proc.stdout.read().decode() if proc.stdout else ""
            pytest.fail(f"gateway did not start over HTTPS:\n{out[-4000:]}")
        context = ssl.create_default_context(cafile=str(ca))
        with httpx.Client(verify=context, timeout=10) as client:
            yield Box(client, https_port)
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(5)


class Box:
    def __init__(self, client: httpx.Client, port: int):
        self.client, self.port = client, port

    def request(self, method: str, host: str, path: str = "/", **kw) -> httpx.Response:
        """A request to https://<host>/, connecting to the gateway's loopback port; TLS checks <host>."""
        headers = {"Host": host, "X-OneMind-Path": "lan", **kw.pop("headers", {})}
        return self.client.request(method, f"https://127.0.0.1:{self.port}{path}", headers=headers,
                                   extensions={"sni_hostname": host}, **kw)

    def app_cookie(self, who: dict) -> str:
        r = self.request("POST", "onemind.local", "/v1/auth/app-session", headers=who)
        assert r.status_code == 204, r.text
        set_cookie = r.headers["set-cookie"]
        attrs = {a.strip().lower() for a in set_cookie.split(";")}
        assert {"secure", "httponly", "domain=onemind.local"} <= attrs, set_cookie
        return set_cookie.split(";", 1)[0]


def test_open_reaches_the_installed_app_over_https(box):
    cookie = box.app_cookie(OWNER)
    r = box.request("GET", f"{OPEN_APP}.onemind.local", "/dashboard?x=1", headers={"Cookie": cookie})
    assert r.status_code == 200, r.text
    seen = r.json()
    assert seen["path"] == "/dashboard?x=1"
    assert seen["headers"]["x-onemind-principal"] == "person:owner"
    assert seen["headers"]["x-forwarded-proto"] == "https"
    assert "onemind_session" not in seen["headers"].get("cookie", "")  # the session never reaches the app
    # The same app on the box's own name.
    assert box.request("GET", f"{OPEN_APP}.box1.local", headers={"Cookie": cookie}).status_code == 200


def test_signed_out_request_to_an_app_is_refused(box):
    for host in (f"{OPEN_APP}.onemind.local", f"{STOPPED_APP}.onemind.local", "nosuch.onemind.local"):
        r = box.request("GET", host, headers={"Accept": "text/html"})
        assert r.status_code == 401, (host, r.status_code)
        assert "Sign in to OneMind" in r.text
    # an agent token is not a person: never on app hosts
    r = box.request("GET", f"{OPEN_APP}.onemind.local", headers={"Authorization": "Bearer dev-agent-token-change-me"})
    assert r.status_code == 403


def test_stopped_app_says_so(box):
    cookie = box.app_cookie(ADULT)
    r = box.request("GET", f"{STOPPED_APP}.onemind.local", headers={"Cookie": cookie, "Accept": "text/html"})
    assert r.status_code == 503
    assert "is stopped. Start it from the OneMind dashboard." in r.text
    assert box.request("GET", "nosuch.onemind.local", headers={"Cookie": cookie}).status_code == 404


SIGNED_OUT_URLS = ["/", "/dashboard?x=1", "/v1/instance", "/apps/actual-budget/", "/%2e%2e/", "//evil/", "/a/../../b", "/.well-known/x"]


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
def test_every_app_url_needs_sign_in_and_the_app_never_sees_it(box, method):
    """Auth is enforced for every app URL: any method, any path, a forged or empty credential."""
    HITS.clear()
    credentials = [{}, {"Cookie": "onemind_session=not-a-token"}, {"Authorization": "Bearer not-a-token"}]
    for host in (f"{OPEN_APP}.onemind.local", f"{OPEN_APP}.box1.local", f"{STOPPED_APP}.onemind.local"):
        for path in SIGNED_OUT_URLS:
            for creds in credentials:
                r = box.request(method, host, path, headers={**creds, "Origin": f"https://{host}"})
                assert r.status_code == 401, (method, host, path, creds, r.status_code)
    assert HITS == []  # not one request reached the app


def test_signed_in_person_still_reaches_the_app_on_the_same_urls(box):
    """The refusal above is about sign-in, not the paths: the same URLs open once signed in."""
    HITS.clear()
    cookie = box.app_cookie(OWNER)
    for path in ("/", "/dashboard?x=1", "/v1/instance"):
        assert box.request("GET", f"{OPEN_APP}.onemind.local", path, headers={"Cookie": cookie}).status_code == 200
    assert HITS == ["GET /", "GET /dashboard?x=1", "GET /v1/instance"]


def test_unknown_and_unreachable_apps_are_told_apart(box):
    cookie = box.app_cookie(ADULT)
    r = box.request("GET", f"{STARTING_APP}.onemind.local", headers={"Cookie": cookie, "Accept": "text/html"})
    # A change that was in flight when the gateway restarted is recovered as "unknown": the page says so
    # rather than guessing (the in-progress wording is unit-tested in test_proxy.py).
    assert r.status_code == 503 and "Bazarr may not be running: OneMind cannot tell right now." in r.text
    r = box.request("GET", f"{DOWN_APP}.onemind.local", headers={"Cookie": cookie})
    assert r.status_code == 502
    assert r.text == "Komga is installed but not answering. It may still be starting."
