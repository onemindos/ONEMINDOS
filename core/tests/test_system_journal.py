# SPDX-License-Identifier: Apache-2.0
"""The whole-system log viewer (P-07): GET /v1/system/journal. A real gateway talks over a real Unix socket to
a stand-in for `onemindd host serve` (GET /v1/journal). Owner only, read only, redacted, bounded, audited."""

from __future__ import annotations

import http.server
import json
import shutil
import socketserver
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, GUEST, OWNER
from onemind_core.app import create_app
from onemind_core.hostlink import HostLinkSettings
from onemind_core.identity.scopes import required_scopes
from onemind_core.journalfilter import JournalRedactor
from onemind_core.netconf import NetSettings
from onemind_core.routers import journal as journal_router

# Test secrets, split so scanners do not flag them.
TOKEN = "om_pat_" + "s3cr3tT0kenValue1234"
WG_KEY = ("Zm9vYmFyQmF6" * 4)[:43] + "="  # 32 bytes of base64, the shape of a WireGuard key
AGE = "AGE-SECRET-KEY-1" + "QQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQ"
PEM_BEGIN = "-----BEGIN OPENSSH " + "PRIVATE KEY-----"
PEM_END = "-----END OPENSSH " + "PRIVATE KEY-----"
EMAIL = "owner" + "@" + "example.org"
LOG = [
    f"2026-11-22T10:00:00+0000 box onemind-gateway[7]: request Authorization: Bearer {TOKEN}",
    f"2026-11-22T10:00:01+0000 box onemind-gateway[7]: db password=hunter2 user={EMAIL}",
    f"2026-11-22T10:00:02+0000 box wg[9]: PrivateKey = {WG_KEY}",
    f"2026-11-22T10:00:03+0000 box sshd[11]: Accepted publickey for zeus from 192.0.2.44 port 5000 ssh2 SHA256:{'a' * 43}",
    f"2026-11-22T10:00:04+0000 box backup[3]: {AGE}",
    "2026-11-22T10:00:05+0000 box kernel: eth0 link up 52:54:00:12:34:56",
    "2026-11-22T10:00:06+0000 box kernel: " + PEM_BEGIN,
    "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW",
    PEM_END,
    "2026-11-22T10:00:07+0000 box onemind-gateway[7]: listening",
]


class FakeHost:
    def __init__(self, lines=None):
        self.dir = tempfile.mkdtemp(prefix="sj")  # short: AF_UNIX paths are limited to about 100 bytes
        self.path = f"{self.dir}/host.sock"
        self.requests: list[str] = []
        self.lines = LOG if lines is None else lines
        host = self

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *a):
                pass

            def do_GET(self):
                host.requests.append(self.path)
                u = urlsplit(self.path)
                q = parse_qs(u.query)
                if u.path != "/v1/journal":
                    code, body = 404, b"{}"
                elif q.get("unit") == ["bad.service"]:
                    code, body = 400, b'{"error":"bad_request"}'
                else:
                    code, body = 200, "".join(x + "\n" for x in host.lines).encode()
                self.send_response(code)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)

        class S(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
            daemon_threads = True

        self.server = S(self.path, H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.dir, ignore_errors=True)


@pytest.fixture
def host():
    h = FakeHost()
    yield h
    h.close()


@contextmanager
def box(settings, clock, sock: str):
    s = replace(settings, sections={"net": NetSettings(host_socket=Path(sock)), "hostlink": HostLinkSettings(socket=Path(sock))})
    with TestClient(create_app(s, clock=clock)) as c:
        yield c


def audit(settings) -> list[dict]:
    return [json.loads(x) for x in settings.audit_path.read_text().splitlines() if x.strip()]


def test_secrets_in_the_journal_are_masked_and_line_counts_stay_true(settings, clock, host):
    with box(settings, clock, host.path) as c:
        r = c.get("/v1/system/journal", headers=OWNER)
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain"), r.text
        assert r.headers["cache-control"] == "no-store"
        for secret in (TOKEN, "hunter2", EMAIL, WG_KEY, AGE, "192.0.2.44", "52:54:00:12:34:56", "b3BlbnNzaC1rZXk", "a" * 43):
            assert secret not in r.text, secret
        assert r.text.count("\n") == len(LOG) and "listening" in r.text and "Accepted publickey" in r.text
        s = c.get("/v1/system/journal?follow=true", headers=OWNER)
        assert s.status_code == 200 and s.headers["content-type"].startswith("text/event-stream")
        assert TOKEN not in s.text and WG_KEY not in s.text and s.text.count("data: ") == len(LOG) + 1 and "event: end" in s.text


def test_filters_reach_the_host_and_defaults_are_bounded(settings, clock, host):
    with box(settings, clock, host.path) as c:
        assert c.get("/v1/system/journal", headers=OWNER).status_code == 200
        assert host.requests[-1] == "/v1/journal?lines=200&boot=0&follow=0"
        r = c.get("/v1/system/journal?unit=sshd.service&priority=err&boot=-1&tail=50", headers=OWNER)
        assert r.status_code == 200
        assert host.requests[-1] == "/v1/journal?lines=50&boot=-1&follow=0&unit=sshd.service&priority=err"


@pytest.mark.parametrize("query", [
    "tail=0", "tail=2001", "boot=1", "boot=-51", "priority=9", "priority=err..debug", "unit=sshd", "unit=x.service%20--rotate",
    "unit=--output=export.service", "boot=-1&follow=true"])
def test_bad_filters_are_refused_before_the_host_is_asked(settings, clock, host, query):
    with box(settings, clock, host.path) as c:
        r = c.get(f"/v1/system/journal?{query}", headers=OWNER)
        assert r.status_code == 422, (query, r.text)
        assert host.requests == []


def test_only_the_owner_reads_it_and_a_refusal_is_audited(settings, clock, host):
    assert required_scopes("GET", "/v1/system/journal") == ("system:admin",)
    with box(settings, clock, host.path) as c:
        for who in (ADULT, AGENT, GUEST):
            assert c.get("/v1/system/journal", headers=who).status_code == 403
        assert c.get("/v1/system/journal").status_code == 401
        assert host.requests == []
    assert sum(1 for e in audit(settings) if e["event"] == "authz.denied" and e["data"]["attempted"] == "read system journal") == 3


def test_every_read_is_audited_without_its_content(settings, clock, host):
    with box(settings, clock, host.path) as c:
        c.get("/v1/system/journal?unit=sshd.service&priority=warning&boot=-1&tail=10", headers=OWNER)
    reads = [e for e in audit(settings) if e["event"] == "system.journal.read"]
    assert len(reads) == 1
    assert reads[0]["data"] == {"unit": "sshd.service", "priority": "warning", "boot": -1, "tail": 10, "follow": False}
    assert TOKEN not in json.dumps(reads)


def test_an_unreachable_host_says_so_and_a_host_refusal_is_a_422(settings, clock, host):
    with box(settings, clock, "/nonexistent/host.sock") as c:
        r = c.get("/v1/system/journal", headers=OWNER)
        assert r.status_code == 409 and r.json()["reason"] == "host_unavailable"
    with box(settings, clock, host.path) as c:
        r = c.get("/v1/system/journal?unit=bad.service", headers=OWNER)
        assert r.status_code == 422 and r.json()["reason"] == "invalid_query"


def test_a_read_is_cut_at_one_mebibyte(settings, clock):
    big = ["x" * 3000] * 600  # 1.8 MB
    h = FakeHost(big)
    try:
        with box(settings, clock, h.path) as c:
            r = c.get("/v1/system/journal?tail=2000", headers=OWNER)
            assert r.status_code == 200 and len(r.content) <= journal_router.MAX_BYTES + 200
            assert r.text.rstrip().endswith("narrow the filters or lower tail]")
    finally:
        h.close()


def test_reads_are_rate_limited_per_minute(settings, clock, host, monkeypatch):
    t = [1000.0]
    monkeypatch.setattr(journal_router, "now", lambda: t[0])
    with box(settings, clock, host.path) as c:
        for _ in range(journal_router.READS_PER_MINUTE):
            assert c.get("/v1/system/journal", headers=OWNER).status_code == 200
        r = c.get("/v1/system/journal", headers=OWNER)
        assert r.status_code == 429 and r.headers["retry-after"] and r.json()["reason"] == "limit_reached"
        t[0] += 61
        assert c.get("/v1/system/journal", headers=OWNER).status_code == 200


def test_open_follow_streams_are_limited_and_released(settings, clock):
    hold = threading.Event()
    h = FakeHost()
    original = h.server.RequestHandlerClass.do_GET

    def slow_get(self):
        if "follow=1" in self.path:
            hold.wait(10)
        original(self)

    h.server.RequestHandlerClass.do_GET = slow_get
    try:
        with box(settings, clock, h.path) as c:
            results: list[int] = []
            threads = [threading.Thread(target=lambda: results.append(c.get("/v1/system/journal?follow=true", headers=OWNER).status_code))
                       for _ in range(journal_router.STREAMS_PER_PRINCIPAL)]
            for t in threads:
                t.start()
            deadline = time.monotonic() + 5
            while len(h.requests) < journal_router.STREAMS_PER_PRINCIPAL and time.monotonic() < deadline:
                time.sleep(0.02)
            over = c.get("/v1/system/journal?follow=true", headers=OWNER)
            assert over.status_code == 429 and over.json()["reason"] == "limit_reached"
            hold.set()
            for t in threads:
                t.join(10)
            assert results == [200] * journal_router.STREAMS_PER_PRINCIPAL
            assert c.get("/v1/system/journal?follow=true", headers=OWNER).status_code == 200  # the slots were released
    finally:
        hold.set()
        h.close()


def test_the_journal_filter_masks_keys_and_multi_line_private_keys():
    r = JournalRedactor()
    assert WG_KEY not in r.line(f"PrivateKey = {WG_KEY}") and AGE not in r.line(AGE)
    assert r.line("link 52:54:00:12:34:56 up") == "link [mac] up"
    assert r.line(PEM_BEGIN).endswith("[redacted]")
    assert r.line("b3BlbnNzaC1rZXktdjEAAAAA") == "[redacted]" and r.line(PEM_END) == "[redacted]"
    assert r.line("plain kernel line") == "plain kernel line"
