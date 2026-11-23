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
