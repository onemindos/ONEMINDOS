# SPDX-License-Identifier: Apache-2.0
"""H-05: with HTTPS on, the gateway's plain-HTTP listener is bound to loopback, never a wildcard or
LAN address (2-VM criterion N2-5 checks the same on a real box)."""

from __future__ import annotations

import socket
from dataclasses import replace
from pathlib import Path

import pytest

from onemind_core import serve
from onemind_core.netconf import NetSettings


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


def test_serve_all_starts_a_plain_tor_listener_that_pins_the_path(settings, tmp_path: Path, monkeypatch):
    """#284: the onion forward is raw TCP, so the Tor listener is plain HTTP and fixes the path itself."""
    seen: dict[str, object] = {"configs": [], "socks": []}

    class FakeServer:
        def __init__(self, config):
            self.config, self.started, self.should_exit = config, True, False
            seen["configs"].append(config)

        async def serve(self, sockets=None):
            seen["socks"].append(sockets)

    monkeypatch.setattr(serve, "_Server", FakeServer)
    tor_port = _free_port()
    net = NetSettings(tls=True, tls_dir=tmp_path / "tls", https_host="127.0.0.1", https_ports=(str(_free_port()),),
                      tor_port=tor_port)
    s = replace(settings, port=_free_port(), sections={**settings.sections, "net": net})
    import asyncio

    seen_scope: dict = {}

    async def inner(scope, receive, send):
        seen_scope.update(scope)

    asyncio.run(serve.serve_all(inner, s))
    tor_cfg = seen["configs"][-1]
    assert tor_cfg.ssl_certfile is None  # plain HTTP: a TLS socket would fail the browser's plain request
    assert [sock.getsockname()[1] for socks in seen["socks"] if socks for sock in socks][-1] == tor_port
    asyncio.run(tor_cfg.app({"type": "http", "client": ("192.0.2.7", 1), "headers": []}, None, None))
    assert seen_scope["onemind.path"] == "tor" and seen_scope["client"] == ("192.0.2.7", 1)


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
