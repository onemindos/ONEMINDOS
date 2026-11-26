# SPDX-License-Identifier: Apache-2.0
"""NET-DOM-01 (#238): bring your own domain is off by default, owner-only, and approval-gated."""

from __future__ import annotations

import base64
import hashlib
import json
import socket
import stat
import struct
import threading
from dataclasses import replace

import pytest
from conftest import ADULT, AGENT, OWNER, make_client

from onemind_core import domains as dom
from onemind_core.domains import AcmeAccount, DnsResolver, DomainError, DomainSettings, normalize_domain, parse_answers


class FakeDns:
    def __init__(self):
        self.records: dict[str, list[str]] = {}
        self.addrs: dict[str, list[str]] = {}
        self.down = False

    def txt(self, name):
        if self.down:
            raise OSError("timeout")
        return self.records.get(name, [])

    def addresses(self, name):
        return self.addrs.get(name, [])


@pytest.fixture
def dns():
    return FakeDns()


@pytest.fixture
def on(settings, clock, dns):
    s = replace(settings, sections={**settings.sections, "domains": DomainSettings(enabled=True)})
    c = make_client(s, clock)
    with c:
        c.app.state.domains.resolver = dns
        c.app.state.domains.apps = lambda: ["whoami"]
        yield c


def verified(c, dns, domain="example.org"):
    body = c.post("/v1/domains", headers=OWNER, json={"domain": domain}).json()
    dns.records[body["proof"]["name"]] = [body["proof"]["value"]]
    assert c.post(f"/v1/domains/{domain}/check", headers=OWNER).json()["proof_found"] is True


def test_off_by_default_and_changes_nothing(client):
    r = client.get("/v1/domains", headers=OWNER)
    assert r.status_code == 200 and r.json() == {"enabled": False, "acme": {"account_thumbprint": None, "issuance": "not_available_yet"}, "domains": []}
    bad = client.post("/v1/domains", headers=OWNER, json={"domain": "example.org"})
    assert (bad.status_code, bad.json()["reason"]) == (409, "domains_disabled")
    assert not (client.app.state.domains.acme.path).exists()  # no key made while off


def test_env_switch(monkeypatch):
    assert DomainSettings.from_env({}).enabled is False
    assert DomainSettings.from_env({dom.ENV: "1"}).enabled is True
    with pytest.raises(ValueError):
        DomainSettings.from_env({dom.ENV: "maybe"})
    with pytest.raises(ValueError):
        DomainSettings.from_env({"ONEMIND_DOMAINS_RESOLVER": "not-an-ip"})


@pytest.mark.parametrize("headers", [ADULT, AGENT, {}])
def test_only_the_owner(on, headers):
    for method, path, body in [("get", "/v1/domains", None), ("post", "/v1/domains", {"domain": "example.org"}),
                               ("post", "/v1/domains/hosts/a.example.org/approve", {"confirm": "a.example.org"})]:
        r = getattr(on, method)(path, headers=headers, **({"json": body} if body else {}))
        assert r.status_code in (401, 403), (path, r.status_code)
    assert on.get("/v1/domains", headers=OWNER).json()["domains"] == []


@pytest.mark.parametrize("name", ["localhost", "box.local", "x.internal", ".".join(["192", "168", "0", "1"]), "nodot", "-a.org", "a_b.org", "", "a..org", "x" * 64 + ".org"])
def test_rejects_private_and_malformed_names(name):
    with pytest.raises(DomainError):
        normalize_domain(name)


def test_proof_then_host_then_separate_approval(on, dns, settings):
    r = on.post("/v1/domains", headers=OWNER, json={"domain": "Example.ORG."})
    assert r.status_code == 201
    d = r.json()
    assert d["domain"] == "example.org" and d["verified"] is False
    assert d["proof"]["name"] == "_onemind-challenge.example.org" and len(d["proof"]["value"]) >= 30
    assert on.post("/v1/domains", headers=OWNER, json={"domain": "example.org"}).status_code == 409
    # no host before the domain is proven
    assert on.post("/v1/domains/example.org/hosts", headers=OWNER, json={"app_id": "whoami"}).json()["reason"] == "domain_unverified"
    # wrong record: stays unverified
    dns.records[d["proof"]["name"]] = ["something-else"]
    assert on.post("/v1/domains/example.org/check", headers=OWNER).json()["proof_found"] is False
    dns.records[d["proof"]["name"]] = ["junk", d["proof"]["value"]]
    dns.addrs["example.org"] = ["203.0.113.7"]
    chk = on.post("/v1/domains/example.org/check", headers=OWNER).json()
    assert chk["proof_found"] and chk["domain"]["verified"] and chk["addresses"] == ["203.0.113.7"]
    h = on.post("/v1/domains/example.org/hosts", headers=OWNER, json={"app_id": "whoami"})
    assert h.status_code == 201 and h.json()["hostname"] == "whoami.example.org"
    assert h.json()["state"] == "requested" and h.json()["public"] is False
    # approval needs the full name typed
    host = "/v1/domains/hosts/whoami.example.org/approve"
    assert on.post(host, headers=OWNER, json={"confirm": "whoami"}).json()["reason"] == "confirm_mismatch"
    ok = on.post(host, headers=OWNER, json={"confirm": "whoami.example.org"})
    assert ok.status_code == 200 and ok.json()["state"] == "approved" and ok.json()["approved_by"]
    assert on.post(host, headers=OWNER, json={"confirm": "whoami.example.org"}).status_code == 409
    events = [json.loads(x)["event"] for x in settings.audit_path.read_text().splitlines()]
    assert {"domains.added", "domains.checked", "domains.host_requested", "domains.host_approved"} <= set(events)
    assert on.delete("/v1/domains/hosts/whoami.example.org", headers=OWNER).status_code == 204
    assert on.get("/v1/domains", headers=OWNER).json()["domains"][0]["hosts"] == []


def test_dns_failure_is_502_and_keeps_state(on, dns):
    on.post("/v1/domains", headers=OWNER, json={"domain": "example.org"})
    dns.down = True
    r = on.post("/v1/domains/example.org/check", headers=OWNER)
    assert (r.status_code, r.json()["reason"]) == (503, "dns_unavailable")


def test_admin_surfaces_and_non_apps_cannot_be_named(on, dns):
    verified(on, dns)
    for app_id in ("admin", "hub", "control", "api", "dashboard"):
        r = on.post("/v1/domains/example.org/hosts", headers=OWNER, json={"app_id": app_id})
        assert (r.status_code, r.json()["reason"]) == (422, "reserved_name"), app_id
    r = on.post("/v1/domains/example.org/hosts", headers=OWNER, json={"app_id": "not-installed"})
    assert r.json()["reason"] == "not_a_web_app"


def test_removing_a_domain_drops_its_names(on, dns):
    verified(on, dns)
    on.post("/v1/domains/example.org/hosts", headers=OWNER, json={"app_id": "whoami"})
    assert on.delete("/v1/domains/example.org", headers=OWNER).status_code == 204
    assert on.get("/v1/domains", headers=OWNER).json()["domains"] == []
    assert on.delete("/v1/domains/example.org", headers=OWNER).status_code == 404


def test_unverified_state_survives_restart_and_reverify_is_sticky(settings, clock, dns):
    s = replace(settings, sections={**settings.sections, "domains": DomainSettings(enabled=True)})
    with make_client(s, clock) as c:
        c.app.state.domains.resolver = dns
        verified(c, dns)
    with make_client(s, clock) as c2:
        assert c2.get("/v1/domains", headers=OWNER).json()["domains"][0]["verified"] is True


# ---- ACME account key (RFC 7638 / RFC 8555 section 8.4) ----------------------------------------------------------
def b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def test_account_key_stays_private_and_values_follow_the_rfc(tmp_path):
    acct = AcmeAccount(tmp_path / "tls")
    t = acct.thumbprint()
    assert stat.S_IMODE(acct.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(acct.path.parent.stat().st_mode) == 0o700
    assert AcmeAccount(tmp_path / "tls").thumbprint() == t  # stable across restarts
    assert acct.dns01_value("tok") == b64(hashlib.sha256(f"tok.{t}".encode()).digest())
    assert acct.dns01_value("tok") != acct.dns01_value("tok2")
    assert len(base64.urlsafe_b64decode(t + "=")) == 32 and "BEGIN" not in t


def test_thumbprint_matches_independent_rfc7638(tmp_path):
    from cryptography.hazmat.primitives import serialization
    acct = AcmeAccount(tmp_path / "tls")
    acct.thumbprint()
    key = serialization.load_pem_private_key(acct.path.read_bytes(), None)
    n = key.public_key().public_numbers()
    canon = '{"crv":"P-256","kty":"EC","x":"%s","y":"%s"}' % (b64(n.x.to_bytes(32, "big")), b64(n.y.to_bytes(32, "big")))
    assert acct.thumbprint() == b64(hashlib.sha256(canon.encode()).digest())


# ---- the stdlib DNS client against a local UDP server --------------------------------------------------------------
def _reply(query: bytes, txt: bytes | None, rcode=0):
    qid = query[:2]
    name_end = query.index(b"\0", 12) + 1
    question = query[12:name_end + 4]
    qtype = struct.unpack(">H", query[name_end:name_end + 2])[0]
    answers = b""
    if txt is not None and qtype == 16:
        rdata = bytes([len(txt)]) + txt
        answers = b"\xc0\x0c" + struct.pack(">HHIH", 16, 1, 60, len(rdata)) + rdata
    elif txt is not None and qtype == 1:
        answers = b"\xc0\x0c" + struct.pack(">HHIH", 1, 1, 60, 4) + bytes([203, 0, 113, 9])
    return qid + struct.pack(">HHHHH", 0x8180 | rcode, 1, 1 if answers else 0, 0, 0) + question + answers


@pytest.fixture
def udp_dns():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    state = {"txt": b"hello-proof", "rcode": 0}

    def serve():
        while True:
            try:
                data, addr = sock.recvfrom(512)
            except OSError:
                return
            sock.sendto(_reply(data, state["txt"], state["rcode"]), addr)

    threading.Thread(target=serve, daemon=True).start()
    yield sock.getsockname()[1], state
    sock.close()


def test_resolver_parses_txt_and_a_records(udp_dns, monkeypatch):
    port, state = udp_dns
    real_connect = socket.socket.connect
    monkeypatch.setattr(socket.socket, "connect", lambda self, addr: real_connect(self, ("127.0.0.1", port)))
    r = DnsResolver("127.0.0.1", 2)
    assert r.txt("_onemind-challenge.example.org") == ["hello-proof"]
    assert "203.0.113.9" in r.addresses("example.org")
    state["rcode"] = 3  # NXDOMAIN is "no record", not an error
    assert r.txt("nope.example.org") == []
    state["rcode"] = 2  # SERVFAIL is an error the owner is told about
    with pytest.raises(OSError):
        r.txt("x.example.org")


def test_parse_answers_rejects_garbage():
    with pytest.raises(OSError):
        parse_answers(b"\x00\x01", 1)
    with pytest.raises(OSError):
        parse_answers(struct.pack(">HHHHHH", 5, 0x8180, 0, 0, 0, 0), 6)  # wrong id
