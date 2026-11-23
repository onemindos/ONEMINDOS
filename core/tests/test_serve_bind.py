# SPDX-License-Identifier: Apache-2.0
"""H-05: with HTTPS on, the gateway's plain-HTTP listener is bound to loopback, never a wildcard or
LAN address (2-VM criterion N2-5 checks the same on a real box)."""

from __future__ import annotations

import socket
from dataclasses import replace
from pathlib import Path

import pytest

from onemind_core import serve
from onemind_core.netconf import MeshSettings, NetSettings


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "[::]", "", "198.51.100.1", "hub.example.test"])
def test_non_loopback_plain_http_host_becomes_loopback(host):
    assert serve.plain_http_host(host) == "127.0.0.1"


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.2", "::1", "localhost"])
def test_loopback_host_is_kept(host):
    assert serve.plain_http_host(host) == host


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.parametrize("configured", ["0.0.0.0", "198.51.100.1"])
def test_serve_all_binds_plain_http_to_loopback(settings, tmp_path: Path, monkeypatch, configured):
    seen: dict[str, object] = {}

    class FakeServer:
        def __init__(self, config):
            self.config, self.started, self.should_exit = config, True, False
            seen.setdefault("configs", []).append(config)

        async def serve(self, sockets=None):
            return None

    monkeypatch.setattr(serve, "_Server", FakeServer)
    port = _free_port()
    net = NetSettings(tls=True, tls_dir=tmp_path / "tls", https_host="127.0.0.1", https_ports=(str(_free_port()),))
    s = replace(settings, host=configured, port=port, sections={**settings.sections, "net": net})
    import asyncio

    asyncio.run(serve.serve_all(object(), s))
    main = seen["configs"][0]
    assert main.host == "127.0.0.1" and main.port == port, (main.host, main.port)
    assert main.ssl_certfile is None  # the plain listener; the TLS one is the second server
    assert seen["configs"][1].ssl_certfile  # and the LAN one is HTTPS


HUB_MESH_IP = "100.64.0.1"


def _run_serve_all(settings, tmp_path, monkeypatch, *, mesh, https_host="0.0.0.0", app=None):
    """serve_all with fake servers; returns (configs, binds as (host, port), served sockets)."""
    seen: dict[str, list] = {"configs": [], "binds": [], "socks": []}

    class FakeServer:
        def __init__(self, config):
            self.config, self.started, self.should_exit = config, True, False
            seen["configs"].append(config)

        async def serve(self, sockets=None):
            seen["socks"].append(sockets)

    class FakeSock:
        def __init__(self, host, port):
            self.addr = (host, port)

        def getsockname(self):
            return self.addr

    def fake_bind(host, port):
        seen["binds"].append((host, port))
        return FakeSock(host, port)

    monkeypatch.setattr(serve, "_Server", FakeServer)
    monkeypatch.setattr(serve, "_bind", fake_bind)
    net = NetSettings(tls=True, tls_dir=tmp_path / "tls", https_host=https_host, https_ports=("8443",),
                      tor_port=8446)
    s = replace(settings, port=_free_port(), sections={**settings.sections, "net": net, "mesh": mesh})
    import asyncio

    asyncio.run(serve.serve_all(app if app is not None else object(), s))
    return seen


def _mesh(hub_ip):
    return MeshSettings(enabled=True, headscale_key_file=Path("/nonexistent/key"), hub_ip=hub_ip)


def test_tor_listener_binds_only_to_the_hub_mesh_address(settings, tmp_path: Path, monkeypatch):
    """#284: the Tor listener is plain HTTP, so it must never bind a wildcard or LAN address,
    whatever https_host says (here the default wildcard)."""
    seen = _run_serve_all(settings, tmp_path, monkeypatch, mesh=_mesh(HUB_MESH_IP), https_host="0.0.0.0")
    assert ("0.0.0.0", 8446) not in seen["binds"]
    assert [b for b in seen["binds"] if b[1] == 8446] == [(HUB_MESH_IP, 8446)]
    tor_cfg = seen["configs"][-1]
    assert tor_cfg.ssl_certfile is None  # plain HTTP: a TLS socket would fail the browser's plain request


@pytest.mark.parametrize("mesh", [MeshSettings(), _mesh(None)])
def test_no_tor_listener_without_a_mesh_address(settings, tmp_path: Path, monkeypatch, mesh):
    seen = _run_serve_all(settings, tmp_path, monkeypatch, mesh=mesh, https_host="0.0.0.0")
    assert all(port != 8446 for _, port in seen["binds"])  # never falls back to a wildcard


@pytest.mark.parametrize("hub_ip", [None, "0.0.0.0", "192.168.1.5", "::", "100.64.0.1"])
def test_tor_bind_host_is_never_a_wildcard_or_lan_address(settings, hub_ip):
    host = serve.tor_bind_host(replace(settings, sections={**settings.sections, "mesh": MeshSettings(
        enabled=True, headscale_key_file=Path("/x"), hub_ip=hub_ip)}))
    assert host in (None, "100.64.0.1")


def _call(app, client, path="/x"):
    import asyncio

    out: list = []

    async def send(msg):
        out.append(msg)

    asyncio.run(app({"type": "http", "client": client, "headers": [], "path": path}, None, send))
    return out


def test_pinned_path_app_pins_the_path_for_allowed_peers():
    seen: dict = {}

    async def inner(scope, receive, send):
        seen.update(scope)

    wrapped = serve.pinned_path_app(inner, "tor", peers=serve.TOR_PEER_NETWORKS, enabled=lambda: True)
    _call(wrapped, ("10.42.0.7", 1))
    assert seen["onemind.path"] == "tor" and seen["client"] == ("10.42.0.7", 1)


@pytest.mark.parametrize("peer", ["192.168.1.20", "10.0.0.5", "203.0.113.9", "::ffff:192.168.1.20", "nonsense"])
def test_pinned_path_app_refuses_peers_outside_the_pod_and_mesh_networks(peer):
    called: list = []

    async def inner(scope, receive, send):
        called.append(1)

    out = _call(serve.pinned_path_app(inner, "tor", peers=serve.TOR_PEER_NETWORKS, enabled=lambda: True),
                (peer, 1))
    assert not called and out[0]["status"] == 403
    assert _call(serve.pinned_path_app(inner, "tor", peers=serve.TOR_PEER_NETWORKS), None)[0]["status"] == 403


def test_tor_listener_answers_503_while_the_tor_app_is_not_installed():
    called: list = []

    async def inner(scope, receive, send):
        called.append(1)

    state = {"on": False}
    wrapped = serve.pinned_path_app(inner, "tor", peers=serve.TOR_PEER_NETWORKS, enabled=lambda: state["on"])
    assert _call(wrapped, ("10.42.0.7", 1))[0]["status"] == 503 and not called
    state["on"] = True
    _call(wrapped, ("10.42.0.7", 1))
    assert called


def test_serve_all_gates_the_tor_listener_on_the_installed_app(settings, tmp_path: Path, monkeypatch):
    from types import SimpleNamespace

    status = {"v": None}
    reached: list = []

    async def app(scope, receive, send):
        reached.append(scope["onemind.path"] if "onemind.path" in scope else None)

    app.state = SimpleNamespace(repo=SimpleNamespace(
        get_app_state=lambda i: SimpleNamespace(status=status["v"]) if status["v"] else None))
    seen = _run_serve_all(settings, tmp_path, monkeypatch, mesh=_mesh(HUB_MESH_IP), app=app)
    tor_app = seen["configs"][-1].app
    assert _call(tor_app, ("10.42.0.7", 1))[0]["status"] == 503 and not reached  # not installed
    status["v"] = "installed"
    _call(tor_app, ("10.42.0.7", 1))
    assert reached == ["tor"]
    assert _call(tor_app, ("192.168.1.20", 1))[0]["status"] == 403  # the LAN stays out even when installed


def test_no_tor_listener_unless_configured(settings, tmp_path: Path, monkeypatch):
    configs: list = []

    class FakeServer:
        def __init__(self, config):
            self.config, self.started, self.should_exit = config, True, False
            configs.append(config)

        async def serve(self, sockets=None):
            return None

    monkeypatch.setattr(serve, "_Server", FakeServer)
    net = NetSettings(tls=True, tls_dir=tmp_path / "tls", https_host="127.0.0.1", https_ports=(str(_free_port()),))
    s = replace(settings, port=_free_port(), sections={**settings.sections, "net": net})
    import asyncio

    asyncio.run(serve.serve_all(object(), s))
    assert len(configs) == 2  # the plain loopback one and the HTTPS one


def test_tor_port_is_validated():
    NetSettings(tls=True, tor_port=8446).validate()
    for bad in (dict(tor_port=70000), dict(tls=False, tor_port=8446), dict(tls=True, tor_port=8443),
                dict(tls=True, tor_port=80, http_redirect_port=80)):
        with pytest.raises(ValueError):
            NetSettings(**bad).validate()


_FAKE = "om_wopi_" + "x" * 8  # built at run time so no secret-shaped literal sits in the repo


@pytest.mark.parametrize("text", [
    "GET /v1/files/wopi/files/f1?access_token={t} HTTP/1.1",
    "POST /v1/files/wopi/files/f1/contents?x=1&ACCESS_TOKEN={t}&y=2",
])
def test_redact_query_hides_the_access_token(text):
    out = serve.redact_query(text.format(t=_FAKE))
    assert "om_wopi_" not in out and "access_token=[redacted]" in out.lower()


def test_every_listener_gets_the_redacting_log_config(settings, monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(serve.uvicorn, "run", lambda app, **kw: seen.update(kw))
    serve.run(object(), settings)
    cfg = seen["log_config"]
    assert "redact_access_token" in cfg["loggers"]["uvicorn.access"]["filters"]
    assert cfg["filters"]["redact_access_token"]["()"] is serve.RedactAccessToken


def test_serve_all_listeners_all_redact(settings, tmp_path: Path, monkeypatch):
    configs: list = []

    class FakeServer:
        def __init__(self, config):
            self.config, self.started, self.should_exit = config, True, False
            configs.append(config)

        async def serve(self, sockets=None):
            return None

    monkeypatch.setattr(serve, "_Server", FakeServer)
    net = NetSettings(tls=True, tls_dir=tmp_path / "tls", https_host="127.0.0.1",
                      https_ports=(str(_free_port()),), http_redirect_port=_free_port())
    s = replace(settings, host="127.0.0.1", port=_free_port(), sections={**settings.sections, "net": net})
    import asyncio

    asyncio.run(serve.serve_all(object(), s))
    assert len(configs) == 3
    for c in configs:
        assert "redact_access_token" in c.log_config["loggers"]["uvicorn.access"]["filters"]
