# SPDX-License-Identifier: Apache-2.0
"""Remote access over Tor, the Market app (NET-TOR-01, #284, D-014).

The app's own code (apps/tor-remote-access/manifests/tor_access.py) and its manifests, checked
with the gateway's real install sandbox, NetworkPolicy builder, executor and approval flow. The
live Tor test (a device without a key refused, with a key reaching the sign-in page, refused again
after removal) needs the Tor network and runs separately.
"""

from __future__ import annotations

import base64
import importlib.util
import os
import shutil
import socket
import tempfile
import threading
import urllib.error
import urllib.request
from datetime import timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

from conftest import ADULT, AGENT, OWNER, FakeKubectl, action_body, fake_kustomize, write_scan
from onemind_core import policy
from onemind_core.app import create_app
from onemind_core.catalog import AppEntry
from onemind_core.executors import KubernetesExecutor

REPO = Path(__file__).resolve().parents[2]
APP_ID = "tor-remote-access"
APP_DIR = REPO / "apps" / APP_ID
RULES = policy.load_rules(REPO / "sdk" / "policy" / "app-objects.yaml")
spec = importlib.util.spec_from_file_location("tor_access", APP_DIR / "manifests" / "tor_access.py")
tor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tor)

ONION = "a" * 56 + ".onion"


def entry() -> AppEntry:
    return AppEntry(id=APP_ID, dir=APP_DIR, manifest=yaml.safe_load((APP_DIR / "onemind.app.yaml").read_text()))


def rendered() -> list[dict]:
    return policy.parse_rendered(fake_kustomize(APP_DIR / "manifests"))


def torrc_lines(text: str) -> list[tuple[str, str]]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition(" ")
            out.append((key, value))
    return out


@pytest.fixture
def data(tmp_path):
    d = tmp_path / "tor"
    tor.ensure_lock(d)
    (tor.onion_dir(d) / "hostname").write_text(ONION + "\n")
    return d


# ---- keys -------------------------------------------------------------------------------------------

def test_x25519_matches_rfc_7748():
    h = bytes.fromhex
    assert tor.x25519(h("a546e36bf0527c9d3b16154b82465edd62144c0ac1fc5a18506a2244ba449ac4"),
                      h("e6db6867583030db3594c1a424b15f7c726624ec26b3353b10a903a6d0ab1c4c")).hex() == \
        "c3da55379de9c6908e94ea4df28d084f32eccf03491c71f754b4075577a28552"
    # section 6.1: Alice's public key from her private key
    assert tor.x25519(h("77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a"), (9).to_bytes(32, "little")).hex() == \
        "8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a"


def test_device_keys_are_tor_base32_and_pairs():
    public, private = tor.new_client_key()
    assert len(public) == len(private) == 52 and public.isupper()
    raw = lambda s: base64.b32decode(s + "====")  # noqa: E731
    assert tor.x25519(raw(private), (9).to_bytes(32, "little")) == raw(public)


# ---- fail closed: the lock key, show-once, removal ----------------------------------------------------

def test_no_devices_still_means_client_auth_on(tmp_path):
    d = tmp_path / "fresh"
    tor.ensure_lock(d)
    auth = list(tor.clients_dir(d).glob("*.auth"))
    assert [p.name for p in auth] == ["onemind-lock.auth"]  # Tor never sees an empty list
    assert auth[0].read_text().startswith("descriptor:x25519:")
    assert tor.devices(d) == []
    for p in (tor.onion_dir(d), tor.clients_dir(d)):
        assert p.stat().st_mode & 0o077 == 0  # Tor refuses group- or world-readable folders
    before = auth[0].read_text()
    tor.ensure_lock(d)
    assert auth[0].read_text() == before


def test_add_device_stores_only_the_public_half(data):
    s, line = tor.add_device("Zeus phone", data)
    assert s == "zeus-phone" and tor.devices(data) == ["zeus-phone"]
    address, kind, alg, private = line.split(":")
    assert (address, kind, alg) == ("a" * 56, "descriptor", "x25519")
    stored = (tor.clients_dir(data) / "zeus-phone.auth").read_text().strip()
    public = stored.removeprefix("descriptor:x25519:")
    assert tor.x25519(base64.b32decode(private + "===="), (9).to_bytes(32, "little")) == base64.b32decode(public + "====")
    assert all(private not in p.read_text() for p in data.rglob("*") if p.is_file())  # shown once, never kept
    assert (tor.clients_dir(data) / "zeus-phone.auth").stat().st_mode & 0o077 == 0


@pytest.mark.parametrize("name", ["", "../x", "a" * 33, "onemind-lock", "x/y", "née"])
def test_bad_device_names_are_refused(data, name):
    with pytest.raises(ValueError):
        tor.add_device(name, data)
    assert tor.devices(data) == []


def test_duplicates_limit_and_no_address_yet(data, tmp_path):
    tor.add_device("laptop", data)
    with pytest.raises(ValueError, match="already"):
        tor.add_device("Laptop", data)
    for i in range(tor.MAX_DEVICES - 1):
        tor.add_device(f"d{i}", data)
    with pytest.raises(ValueError, match="At most"):
        tor.add_device("one-more", data)
    empty = tmp_path / "noaddr"
    tor.ensure_lock(empty)
    with pytest.raises(ValueError, match="address"):
        tor.add_device("phone", empty)


def test_remove_device_never_removes_the_lock(data):
    tor.add_device("phone", data)
    assert tor.remove_device("phone", data) is True
    assert tor.devices(data) == [] and (tor.clients_dir(data) / "onemind-lock.auth").is_file()
    assert tor.remove_device("onemind-lock", data) is False
    assert tor.remove_device("../onion/hostname", data) is False
    assert tor.remove_device("phone", data) is False


# ---- the torrc: onion service only, no listener, never a proxy, relay or exit ------------------------

def test_torrc_is_onion_service_only():
    text = tor.render_torrc(("192.0.2.10", 8080), Path("/var/lib/tor"))
    lines = torrc_lines(text)
    conf = dict(lines)
    for port in ("SocksPort", "DNSPort", "TransPort", "NATDPort", "HTTPTunnelPort", "ORPort", "DirPort"):
        assert conf[port] == "0", port
    assert conf["ClientOnly"] == "1" and conf["ExitRelay"] == "0" and conf["ExitPolicy"] == "reject *:*"
    assert conf["HiddenServiceEnableIntroDoSDefense"] == "1"
    # The only listeners: the onion service's one virtual port, and a Unix control socket (no TCP).
    keys = [k for k, _ in lines]
    assert keys.count("HiddenServicePort") == 1 and conf["HiddenServicePort"] == "80 192.0.2.10:8080"
    assert conf["ControlSocket"].startswith("unix:/var/lib/tor/data/")
    assert not {"ControlPort", "MetricsPort", "ExtORPort", "ServerTransportPlugin", "ClientTransportPlugin",
                "BridgeRelay", "HiddenServiceNonAnonymousMode", "HiddenServiceSingleHopMode"} & set(keys)
    assert {k for k in keys if k.endswith("Port")} == {
        "SocksPort", "DNSPort", "TransPort", "NATDPort", "HTTPTunnelPort", "ORPort", "DirPort", "HiddenServicePort"}
    assert "HiddenServicePort 80 [fd00::1]:443" in tor.render_torrc(("fd00::1", 443))


@pytest.mark.parametrize("value", [None, "", "dashboard:8080", "192.0.2.1", "192.0.2.1:0", "192.0.2.1:70000",
                                   "0.0.0.0:80", "224.0.0.1:80", "192.0.2.1:80 extra", "192.0.2.1:80\nSocksPort 9050"])
def test_dashboard_target_must_be_ip_and_port(value):
    with pytest.raises(ValueError):
        tor.parse_target(value)


def test_init_refuses_to_start_without_the_dashboard_address(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(tor.TARGET_ENV, raising=False)
    torrc = tmp_path / "torrc"
    assert tor.init(tmp_path / "d", torrc) == 1 and not torrc.exists()
    assert "dashboard address" in capsys.readouterr().err
    monkeypatch.setenv(tor.TARGET_ENV, "192.0.2.10:8080")
    assert tor.init(tmp_path / "d", torrc) == 0
    assert "HiddenServicePort 80 192.0.2.10:8080" in torrc.read_text()
    assert (tmp_path / "d" / "data").stat().st_mode & 0o077 == 0
    assert (tor.clients_dir(tmp_path / "d") / "onemind-lock.auth").is_file()


def test_manifests_expose_only_the_owner_page():
    docs = rendered()
    pods = [d for d in docs if d["kind"] == "Deployment"]
    assert len(pods) == 1
    pod = pods[0]["spec"]["template"]["spec"]
    ports = [(c["name"], p["containerPort"]) for c in pod["containers"] + pod["initContainers"] for p in c.get("ports", [])]
    assert ports == [("owner-page", 8080)]
    services = [d for d in docs if d["kind"] == "Service"]
    assert [(s["spec"]["type"], [p["port"] for p in s["spec"]["ports"]]) for s in services] == [("ClusterIP", [8080])]
    tor_c = next(c for c in pod["containers"] if c["name"] == "tor")
    assert tor_c["command"] == ["tor", "--defaults-torrc", "/dev/null", "-f", "/etc/onemind-tor/torrc"]
    assert not pod.get("hostNetwork") and not pod.get("hostPID")
    assert all(c["securityContext"]["readOnlyRootFilesystem"] for c in pod["containers"] + pod["initContainers"])


# ---- the install sandbox and the network ---------------------------------------------------------------

def test_app_passes_the_install_sandbox():
    app = entry()
    assert policy.check_kustomization(app.manifests_dir, app.dir, RULES) == []
    assert policy.check_objects(rendered(), APP_ID, app.manifest, RULES) == []
    assert policy.pod_security_level(APP_ID, app.manifest, RULES)[0] == "restricted"


def test_network_policy_has_no_lan_egress_and_no_extra_ingress():
    egress, bad = policy.egress_entries(APP_ID, entry().manifest, RULES)
    assert egress == ["internet"] and bad == []
    deny, allow = policy.network_policies(APP_ID, egress, RULES)
    assert deny["spec"] == {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]}
    blocks = [b["ipBlock"] for r in allow["spec"]["egress"] for b in r["to"] if "ipBlock" in b]
    assert {b["cidr"] for b in blocks} == {"0.0.0.0/0", "::/0"}
    v4 = next(b for b in blocks if b["cidr"] == "0.0.0.0/0")["except"]
    lan = [c for c in RULES.internet_except if ":" not in c]
    assert lan and set(v4) == set(lan)  # every LAN, node, pod and service range is excluded
    # Ingress: its own pods and the gateway's app proxy only.
    assert allow["spec"]["ingress"] == [
        {"from": [{"podSelector": {}}]},
        {"from": [{"namespaceSelector": {"matchLabels": dict(RULES.proxy_label)}}]},
    ]


# ---- install, remove, delete data: owner-approved; the key survives a plain uninstall ------------------

@pytest.fixture
def market(settings, clock):
    shutil.copytree(APP_DIR, settings.apps_dir / APP_ID)
    write_scan(settings.apps_dir / APP_ID, clock.now - timedelta(days=1))
    return settings


def test_install_waits_for_the_owner_and_an_agent_cannot_approve(market, clock, executor):
    from fastapi.testclient import TestClient

    with TestClient(create_app(market, clock=clock, executor=executor)) as c:
        r = c.post("/v1/actions", json=action_body(clock, app_id=APP_ID, key="tor"), headers=AGENT)
        assert r.status_code == 201 and r.json()["state"] == "awaiting_approval", r.text
        aid, sha = r.json()["id"], r.json()["plan_sha256"]
        assert c.post(f"/v1/actions/{aid}/approve", json={"plan_sha256": sha}, headers=AGENT).status_code == 403
        assert c.post(f"/v1/actions/{aid}/approve", json={"plan_sha256": sha}, headers=ADULT).status_code == 403
        assert executor.calls == []  # nothing ran
        assert c.post(f"/v1/actions/{aid}/approve", json={"plan_sha256": sha}, headers=OWNER).status_code == 200
        assert executor.calls == [("app.install", APP_ID)]


def test_uninstall_keeps_the_onion_key_and_delete_data_removes_it():
    ex = KubernetesExecutor(runner=FakeKubectl(), rules=RULES)
    install = ex.plan("app.install", entry(), rendered=fake_kustomize(APP_DIR / "manifests"))
    applied = [yaml.safe_load_all(stdin) for _, stdin in install if stdin]
    kinds = {d["kind"] for docs in applied for d in docs if isinstance(d, dict)}
    assert "PersistentVolumeClaim" in kinds  # the onion key lives on the app's volume
    (remove,) = ex.plan("app.remove", entry())
    assert remove[0][:2] == ["kubectl", "delete"] and "persistentvolumeclaims" not in remove[0][2]
    assert "namespace" not in remove[0][2].split(",")
    (wipe,) = ex.plan("app.delete_data", entry())
    assert wipe[0][:4] == ["kubectl", "delete", "namespace", f"app-{APP_ID}"]


# ---- the owner page --------------------------------------------------------------------------------------

class Page:
    def __init__(self, data: Path, reload):
        handler = type("H", (tor.Handler,), {"data": data, "reload": staticmethod(reload)})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def call(self, path, *, role="owner", body=None, origin=True):
        headers = {"X-Forwarded-Host": "tor-remote-access.onemind.local"}
        if role:
            headers["X-OneMind-Role"] = role
        if origin:
            headers["Origin"] = "https://tor-remote-access.onemind.local" if origin is True else origin
        req = urllib.request.Request(self.base + path, data=body.encode() if body is not None else None, headers=headers)

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        try:
            with urllib.request.build_opener(NoRedirect).open(req, timeout=5) as r:
                return r.status, r.read().decode(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(), dict(e.headers)


@pytest.fixture
def page(data):
    calls = []
    p = Page(data, lambda d, cut=False: calls.append(cut))
    p.calls = calls
    yield p
    p.server.shutdown()


def test_owner_page_answers_only_the_owner(page):
    assert page.call("/healthz", role=None)[0] == 200
    for role in (None, "adult", "child", "agent"):
        assert page.call("/", role=role)[0] == 403
        assert page.call("/devices", role=role, body="name=x")[0] == 403
    status, text, headers = page.call("/")
    assert status == 200 and ONION in text and "slower than the mesh" in text and "Nobody can connect" in text
    assert "default-src 'none'" in headers["Content-Security-Policy"] and headers["Cache-Control"] == "no-store"


def test_add_shows_the_key_once_and_reloads_without_cutting(page, data):
    status, text, _ = page.call("/devices", body="name=Zeus+phone")
    assert status == 200 and "shown <b>once</b>" in text and f"{'a' * 56}:descriptor:x25519:" in text
    assert page.calls == [False] and tor.devices(data) == ["zeus-phone"]
    assert "x25519:" not in page.call("/")[1]  # the home page never shows a key again


def test_remove_restarts_tor_so_open_circuits_close(page, data):
    tor.add_device("laptop", data)
    status, _, headers = page.call("/devices/laptop/delete", body="")
    assert status == 303 and headers["Location"] == "/" and page.calls == [True] and tor.devices(data) == []
    assert page.call("/devices/onemind-lock/delete", body="")[0] == 404


def test_cross_origin_or_origin_less_posts_are_refused(page, data):
    for origin in (None, "https://other-app.onemind.local", "null"):
        assert page.call("/devices", body="name=x", origin=origin or False)[0] == 403
    assert tor.devices(data) == [] and page.calls == []


def test_tor_that_does_not_confirm_is_reported(data):
    def broken(d, cut=False):
        raise OSError("no socket")
    p = Page(data, broken)
    try:
        status, text, _ = p.call("/devices", body="name=phone")
        assert status == 503 and "did not confirm" in text
    finally:
        p.server.shutdown()


# ---- the control socket ----------------------------------------------------------------------------------

def test_reload_and_halt_over_the_control_socket():
    # A short folder: a Unix socket path is limited to about 100 bytes (the pod's is /var/lib/tor/...).
    data = Path(tempfile.mkdtemp(prefix="tor", dir="/tmp" if os.path.isdir("/tmp") else None))
    seen = []
    try:
        tor.ensure_lock(data)
        (data / "data").mkdir()
        cookie = os.urandom(32)
        (data / "data" / "control.cookie").write_bytes(cookie)
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(data / "data" / "control.sock"))
        srv.listen(2)

        def control():
            for _ in range(2):
                conn, _ = srv.accept()
                with conn, conn.makefile("rwb") as f:
                    for line in f:
                        cmd = line.decode().strip()
                        seen.append(cmd)
                        if cmd == "SIGNAL HALT":
                            break  # Tor exits without answering
                        if cmd == "QUIT":
                            break  # the client hangs up without reading
                        f.write(b"250 OK\r\n")
                        f.flush()

        t = threading.Thread(target=control, daemon=True)
        t.start()
        tor.reload_tor(data)
        tor.reload_tor(data, cut=True)
        t.join(5)
        assert seen == [f"AUTHENTICATE {cookie.hex()}", "SIGNAL RELOAD", "QUIT",
                        f"AUTHENTICATE {cookie.hex()}", "SIGNAL HALT"]
        srv.close()
        with pytest.raises(OSError):
            tor.reload_tor(data, timeout=0.5)  # nothing listening any more
    finally:
        shutil.rmtree(data, ignore_errors=True)


def test_a_refusing_tor_is_an_error():
    data = Path(tempfile.mkdtemp(prefix="tor", dir="/tmp" if os.path.isdir("/tmp") else None))
    try:
        tor.ensure_lock(data)
        (data / "data").mkdir()
        (data / "data" / "control.cookie").write_bytes(b"x" * 32)
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(data / "data" / "control.sock"))
        srv.listen(1)

        def control():
            conn, _ = srv.accept()
            with conn, conn.makefile("rwb") as f:
                f.readline()
                f.write(b"515 Authentication failed\r\n")
                f.flush()

        threading.Thread(target=control, daemon=True).start()
        with pytest.raises(OSError, match="refused AUTHENTICATE"):
            tor.reload_tor(data)
        srv.close()
    finally:
        shutil.rmtree(data, ignore_errors=True)
