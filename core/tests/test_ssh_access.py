# SPDX-License-Identifier: Apache-2.0
"""P-06: the owner's SSH keys and switch.

Real gateway, real routes, real ledger. The one stand-in is the box side (`SshHost`), a recording host that
keeps its key list like the box does; the real client is run against a socket that speaks the host protocol
(internal/host/ssh.go). Every change must wait in the approval queue and reach the host only after the owner approved.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import shutil
import socket
import struct
import tempfile
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, GUEST, OWNER
from onemind_core.app import create_app
from onemind_core.sshaccess import HostSshClient, SshHostError, SshSettings, key_id, parse_public_key


def _blob(kind: str, *parts: bytes) -> bytes:
    out = struct.pack(">I", len(kind)) + kind.encode()
    for p in parts:
        out += struct.pack(">I", len(p)) + p
    return out


def ed25519(seed: str = "a", comment: str = "alex@laptop") -> str:
    b = _blob("ssh-ed25519", hashlib.sha256(seed.encode()).digest())
    return f"ssh-ed25519 {base64.b64encode(b).decode()} {comment}".strip()


def rsa(bits: int) -> str:
    n = (1 << (bits - 1)) | 12345
    b = _blob("ssh-rsa", b"\x01\x00\x01", b"\x00" + n.to_bytes(bits // 8, "big"))
    return f"ssh-rsa {base64.b64encode(b).decode()} old"


def fp_of(line: str) -> str:
    return parse_public_key(line).fingerprint


class Box:
    """The box side: keeps the key list and the switch like onemind-owner does."""

    def __init__(self, available: bool = True):
        self.available, self.enabled, self.running, self.keys, self.calls = available, True, False, {}, []
        self.internet = False
        self.fail: SshHostError | None = None

    def state(self):
        if not self.available:
            return {"available": False, "reason": "ssh_unavailable", "message": "no sshd", "enabled": False, "running": False, "keys": []}
        return {"available": True, "reason": None, "message": None, "enabled": self.enabled, "running": self.running and self.enabled,
                "internet": self.internet, "keys": [{"fingerprint": fp, "type": "ed25519", "bits": 256, "comment": c} for fp, c in self.keys.items()]}

    def _go(self, what):
        self.calls.append(what)
        if self.fail:
            raise self.fail

    def add_key(self, line):
        self._go(("add", line))
        p = parse_public_key(line)
        self.keys[p.fingerprint] = p.comment
        self.running = True

    def remove_key(self, fp):
        self._go(("rm", fp))
        self.keys.pop(fp)

    def set_enabled(self, on):
        self._go(("on" if on else "off",))
        self.enabled = on


@pytest.fixture
def web(settings, clock, executor):
    app = create_app(settings, clock=clock, executor=executor)
    with TestClient(app) as c:
        c.box = app.state.ssh.host = Box()
        yield c


def approve(c, r, who=OWNER, **body):
    assert r.status_code == 202, r.text
    return c.post(f"/v1/actions/{r.json()['id']}/approve", headers=who, json=body or None)


# ---- reading --------------------------------------------------------------------------------------
def test_unreachable_host_says_so_and_nothing_is_filed(settings, clock, executor, tmp_path):
    app = create_app(settings, clock=clock, executor=executor)
    with TestClient(app) as c:
        v = c.get("/v1/ssh", headers=OWNER).json()
        assert v["service"]["available"] is False and v["service"]["state"] == "unavailable" and v["keys"] == []
        r = c.post("/v1/ssh/keys", headers=OWNER, json={"public_key": ed25519()})
        assert r.status_code == 409 and r.json()["reason"] == "ssh_unavailable"
        assert c.put("/v1/ssh", headers=OWNER, json={"enabled": False}).status_code == 409
        assert c.get("/v1/actions", headers=OWNER).json() == []


def test_the_view_carries_the_rules_the_box_runs_under(web):
    s = web.get("/v1/ssh", headers=OWNER).json()["service"]
    assert (s["port"], s["user"], s["reach"], s["password_login"]) == (22, "admin", ["lan", "mesh"], False)
    assert "6 new connections a minute" in s["rate_limit"] and s["state"] == "waiting_for_key"
    web.box.keys[fp_of(ed25519())] = "alex@laptop"
    assert web.get("/v1/ssh", headers=OWNER).json()["service"]["state"] == "starting"
    web.box.running = True
    assert web.get("/v1/ssh", headers=OWNER).json()["service"]["state"] == "on"
    web.box.enabled = False
    assert web.get("/v1/ssh", headers=OWNER).json()["service"]["state"] == "off"


def test_a_cloud_board_reports_that_ssh_faces_the_internet(web):
    web.box.internet = True
    assert web.get("/v1/ssh", headers=OWNER).json()["service"]["reach"] == ["lan", "mesh", "internet"]


def test_host_client_reads_internet_from_the_host_service(settings):
    from onemind_core.sshaccess import HostSshClient, SshSettings
    c = HostSshClient(SshSettings())
    for doc, want in (({"available": True, "internet": True, "keys": []}, True), ({"available": True, "keys": []}, False),
                      ({"available": True, "internet": "yes", "keys": []}, False)):
        c._call = lambda *a, doc=doc: (200, doc)
        assert c.state()["internet"] is want


def test_only_the_owner_reads_or_asks_and_an_agent_never_does(web):
    for who in (ADULT, GUEST, AGENT):
        assert web.get("/v1/ssh", headers=who).status_code == 403
        assert web.get("/v1/ssh/keys", headers=who).status_code == 403
        assert web.post("/v1/ssh/keys", headers=who, json={"public_key": ed25519()}).status_code == 403
        assert web.put("/v1/ssh", headers=who, json={"enabled": False}).status_code == 403
        assert web.delete("/v1/ssh/keys/whatever", headers=who).status_code == 403
    generic = web.post("/v1/actions", headers=AGENT, json={"type": "ssh.toggle", "params": {"enabled": True}, "idempotency_key": "x1",
                                                          "expires_at": "2099-01-01T00:00:00Z"})
    assert generic.status_code in (403, 422), generic.text
    assert web.get("/v1/actions", headers=OWNER).json() == [] and web.box.calls == []


# ---- add -------------------------------------------------------------------------------------------
def test_adding_a_key_waits_for_approval_then_reaches_the_host(web):
    line = ed25519("one", "alex@laptop")
    r = web.post("/v1/ssh/keys", headers=OWNER, json={"public_key": line, "reason": "my laptop"})
    a = r.json()
    assert r.status_code == 202 and a["type"] == "ssh.key.add" and a["state"] == "awaiting_approval"
    assert a["params"] == {"public_key": line, "fingerprint": fp_of(line), "type": "ssh-ed25519", "comment": "alex@laptop"}
    assert web.box.calls == [] and web.get("/v1/ssh/keys", headers=OWNER).json() == {"keys": []}
    done = approve(web, r)
    assert done.status_code == 200 and done.json()["state"] == "succeeded", done.text
    assert web.box.calls == [("add", line)]
    (k,) = web.get("/v1/ssh/keys", headers=OWNER).json()["keys"]
    assert k["fingerprint"] == fp_of(line) and k["comment"] == "alex@laptop" and k["id"] == key_id(fp_of(line))


def test_the_key_list_read_and_the_ssh_view_list_the_same_keys(web):
    # The dashboard shows keys from GET /v1/ssh and the CLI from GET /v1/ssh/keys; the surface-parity exemption
    # for ssh.keys.list on the dashboard (group dashboard-wider-read) rests on both answering the same list.
    assert web.get("/v1/ssh", headers=OWNER).json()["keys"] == web.get("/v1/ssh/keys", headers=OWNER).json()["keys"] == []
    for seed, label in (("one", "alex@laptop"), ("two", "Work laptop")):
        r = web.post("/v1/ssh/keys", headers=OWNER, json={"public_key": ed25519(seed, label)})
        assert approve(web, r).json()["state"] == "succeeded"
    keys = web.get("/v1/ssh/keys", headers=OWNER).json()["keys"]
    assert len(keys) == 2 and web.get("/v1/ssh", headers=OWNER).json()["keys"] == keys


def test_a_label_replaces_the_comment_and_is_checked(web):
    r = web.post("/v1/ssh/keys", headers=OWNER, json={"public_key": ed25519("x", "whatever"), "label": "Work laptop"})
    assert r.json()["params"]["comment"] == "Work laptop" and r.json()["params"]["public_key"].endswith(" Work laptop")
    bad = web.post("/v1/ssh/keys", headers=OWNER, json={"public_key": ed25519(), "label": "a\nb"})
    assert bad.status_code == 422 and bad.json()["reason"] == "invalid_label"


@pytest.mark.parametrize("text,reason", [
    ("", None),
    ("hello", "invalid_key"),
    ('command="id" ' + ed25519(), "invalid_key"),
    ('from="*.example.org" ' + ed25519(), "invalid_key"),
    (ed25519() + "\nssh-ed25519 AAAA", "invalid_key"),
    ("ssh-dss AAAAB3NzaC1kc3M= old", "invalid_key"),
    ("ssh-ed25519 !!!notbase64 x", "invalid_key"),
    ("ssh-ed25519 " + base64.b64encode(_blob("ssh-rsa", b"x")).decode(), "invalid_key"),   # blob says another type
    (rsa(1024), "weak_key"),
])
def test_only_plain_supported_strong_keys_are_accepted(web, text, reason):
    r = web.post("/v1/ssh/keys", headers=OWNER, json={"public_key": text})
    assert r.status_code == 422, r.text
    if reason:
        assert r.json()["reason"] == reason
    assert web.get("/v1/actions", headers=OWNER).json() == []


def test_a_3072_bit_rsa_key_is_fine_and_a_duplicate_is_refused(web):
    ok = web.post("/v1/ssh/keys", headers=OWNER, json={"public_key": rsa(3072)})
    assert ok.status_code == 202 and approve(web, ok).json()["state"] == "succeeded"
    again = web.post("/v1/ssh/keys", headers=OWNER, json={"public_key": rsa(3072)})
    assert again.status_code == 409 and again.json()["reason"] == "already_authorised"


def test_a_key_added_while_waiting_is_rechecked_at_approval(web):
    line = ed25519("race")
    r = web.post("/v1/ssh/keys", headers=OWNER, json={"public_key": line})
    web.box.keys[fp_of(line)] = "added on the console meanwhile"
    out = approve(web, r)
    assert out.status_code == 409 and out.json()["error"] == "stale_precondition"
    assert web.box.calls == []


def test_the_key_limit(web):
    for i in range(20):
        web.box.keys[fp_of(ed25519(f"k{i}"))] = f"k{i}"
    r = web.post("/v1/ssh/keys", headers=OWNER, json={"public_key": ed25519("one-more")})
    assert r.status_code == 409 and r.json()["reason"] == "too_many_keys"


def test_a_host_failure_ends_the_action_failed_with_its_reason(web):
    web.box.fail = SshHostError("unsafe_home", "the owner's home holds a link where a key file should be; nothing was changed")
    r = approve(web, web.post("/v1/ssh/keys", headers=OWNER, json={"public_key": ed25519()}))
    body = r.json()
    assert body["state"] == "failed" and "holds a link" in body["result"]["message"], body
    assert web.box.keys == {}


def test_a_surprise_error_ends_the_action_without_leaking(web):
    class Boom(Box):
        def add_key(self, line):
            raise RuntimeError("secret /data/path detail")
    web.app.state.ssh.host = Boom()
    body = approve(web, web.post("/v1/ssh/keys", headers=OWNER, json={"public_key": ed25519()})).json()
    assert body["state"] == "failed" and "secret" not in json.dumps(body["result"])


# ---- step-up ---------------------------------------------------------------------------------------
def passkeys_on_but_not_for_every_approval(web, monkeypatch):
    """Passkeys are active, and the box-wide rule that every approval needs one is off: what is left is the
    ssh guard's own rule, which must still hold for adding a key and switching SSH on."""
    ident = web.app.state.identity
    monkeypatch.setattr(ident, "passkeys_active", lambda: True)
    monkeypatch.setattr(ident, "cfg", dataclasses.replace(ident.cfg, require_passkey_approval=False))


def test_adding_a_key_and_switching_on_need_a_passkey_once_passkeys_are_active(web, monkeypatch):
    passkeys_on_but_not_for_every_approval(web, monkeypatch)
    add = web.post("/v1/ssh/keys", headers=OWNER, json={"public_key": ed25519()})
    assert add.status_code == 202                       # asking is open to an owner's token (the CLI can ask)
    refused = approve(web, add)
    assert refused.status_code == 401 and refused.json()["reason"] == "step_up_required"
    web.box.enabled = False
    on = web.put("/v1/ssh", headers=OWNER, json={"enabled": True})
    refused = approve(web, on)
    assert refused.status_code == 401 and refused.json()["reason"] == "step_up_required"
    assert web.box.calls == [] and web.box.enabled is False


def test_taking_exposure_away_needs_no_passkey(web, monkeypatch):
    line = ed25519("gone")
    web.box.keys[fp_of(line)] = "x"
    passkeys_on_but_not_for_every_approval(web, monkeypatch)
    off = approve(web, web.put("/v1/ssh", headers=OWNER, json={"enabled": False}))
    rm = approve(web, web.delete(f"/v1/ssh/keys/{key_id(fp_of(line))}", headers=OWNER))
    assert off.json()["state"] == "succeeded" and rm.json()["state"] == "succeeded", (off.text, rm.text)
    assert web.box.calls == [("off",), ("rm", fp_of(line))] and web.box.keys == {}


def test_an_agent_cannot_approve(web):
    r = web.post("/v1/ssh/keys", headers=OWNER, json={"public_key": ed25519()})
    assert approve(web, r, who=AGENT).status_code == 403 and web.box.calls == []


# ---- remove and the switch --------------------------------------------------------------------------
def test_removing_a_key_by_id_or_fingerprint(web):
    a, b = ed25519("a", "first"), ed25519("b", "second")
    web.box.keys.update({fp_of(a): "first", fp_of(b): "second"})
    r = web.delete(f"/v1/ssh/keys/{key_id(fp_of(a))}", headers=OWNER)
    assert r.status_code == 202 and r.json()["type"] == "ssh.key.remove" and r.json()["params"] == {"fingerprint": fp_of(a), "comment": "first"}
    assert web.box.calls == []
    assert approve(web, r).json()["state"] == "succeeded"
    assert list(web.box.keys) == [fp_of(b)]
    r2 = web.delete("/v1/ssh/keys/" + fp_of(b).replace("/", "%2F"), headers=OWNER)
    assert r2.status_code in (202, 404)   # a raw fingerprint with a slash cannot be a path segment; the id form is the contract
    assert web.delete("/v1/ssh/keys/unknown", headers=OWNER).status_code == 404


def test_a_key_removed_while_waiting_is_a_stale_request(web):
    line = ed25519("r")
    web.box.keys[fp_of(line)] = "x"
    r = web.delete(f"/v1/ssh/keys/{key_id(fp_of(line))}", headers=OWNER)
    web.box.keys.clear()
    out = approve(web, r)
    assert out.status_code == 409 and out.json()["error"] == "stale_precondition"


def test_switching_off_and_on(web):
    off = approve(web, web.put("/v1/ssh", headers=OWNER, json={"enabled": False}))
    assert off.json()["state"] == "succeeded" and web.box.enabled is False
    assert web.get("/v1/ssh", headers=OWNER).json()["service"]["state"] == "off"
    on = approve(web, web.put("/v1/ssh", headers=OWNER, json={"enabled": True}))
    assert on.json()["state"] == "succeeded" and web.box.enabled is True
    assert web.put("/v1/ssh", headers=OWNER, json={"enabled": "maybe"}).status_code == 422
    assert web.put("/v1/ssh", headers=OWNER, json={}).status_code == 422


def test_switching_off_says_what_it_leaves_running_on_the_approval_card(web):
    off = web.put("/v1/ssh", headers=OWNER, json={"enabled": False}).json()
    note = off["params"]["note"]
    assert "already open keep running" in note and "provider" in note
    assert "note" not in web.put("/v1/ssh", headers=OWNER, json={"enabled": True}).json()["params"]


def test_a_retry_with_the_same_idempotency_key_files_one_request(web):
    h = {**OWNER, "Idempotency-Key": "ssh-retry-1"}
    first = web.put("/v1/ssh", headers=h, json={"enabled": False})
    second = web.put("/v1/ssh", headers=h, json={"enabled": False})
    assert first.json()["id"] == second.json()["id"], (first.text, second.text)
    assert (first.status_code, second.status_code) == (202, 200)


# ---- the real client against the host protocol ----------------------------------------------------
def test_the_host_client_speaks_the_host_protocol():
    short = Path(tempfile.mkdtemp(prefix="om", dir="/tmp"))
    sock = str(short / "host.sock")
    fp = fp_of(ed25519("z"))
    seen: list[tuple[str, str, dict | None]] = []
    answers = [(200, {"available": False, "unavailable_reason": "sshd is missing", "keys": []}),
               (200, {"available": True, "unavailable_reason": None, "enabled": True, "running": True,
                      "keys": [{"fingerprint": fp, "type": "ed25519", "bits": 256, "comment": "z"}, {"fingerprint": "junk"}]}),
               (200, {"added": True}), (409, {"error": "refused", "reason": "invalid_key", "message": "no"}),
               (200, {"removed": True}), (200, {"enabled": False}), (500, {"error": "internal", "reason": "ssh_switch", "message": "x"})]
    srv = socket.socket(socket.AF_UNIX)
    srv.bind(sock)
    srv.listen(5)

    def serve():
        for status, doc in answers:
            c, _ = srv.accept()
            data = b""
            while b"\r\n\r\n" not in data:
                data += c.recv(65536)
            head, _, rest = data.partition(b"\r\n\r\n")
            lines = head.split(b"\r\n")
            n = next((int(ln.split(b":")[1]) for ln in lines if ln.lower().startswith(b"content-length")), 0)
            while len(rest) < n:
                rest += c.recv(65536)
            first = lines[0].decode().split()
            seen.append((first[0], first[1], json.loads(rest) if rest else None))
            body = json.dumps(doc).encode()
            c.sendall(b"HTTP/1.1 %d X\r\nContent-Type: application/json\r\nContent-Length: %d\r\nConnection: close\r\n\r\n"
                      % (status, len(body)) + body)
            c.close()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    host = HostSshClient(SshSettings(host_socket=short / "host.sock", host_timeout_s=5))
    st = host.state()
    assert st["available"] is False and "sshd is missing" in st["message"]
    st = host.state()
    assert st["available"] and st["enabled"] and st["running"] and [k["fingerprint"] for k in st["keys"]] == [fp]   # junk dropped
    host.add_key("ssh-ed25519 AAAA a")
    with pytest.raises(SshHostError) as e:
        host.add_key("bad")
    assert e.value.reason == "invalid_key"
    host.remove_key(fp)
    host.set_enabled(False)
    with pytest.raises(SshHostError) as e2:
        host.set_enabled(True)
    assert e2.value.reason == "host_error"
    t.join(5)
    srv.close()
    shutil.rmtree(short, ignore_errors=True)
    assert seen[2] == ("POST", "/v1/ssh/keys", {"public_key": "ssh-ed25519 AAAA a"})
    assert seen[4] == ("POST", "/v1/ssh/keys/remove", {"fingerprint": fp})
    assert seen[5] == ("PUT", "/v1/ssh/enabled", {"enabled": False})


def test_no_socket_means_unavailable_with_a_reason(tmp_path):
    st = HostSshClient(SshSettings(host_socket=tmp_path / "none.sock")).state()
    assert st["available"] is False and st["reason"] == "ssh_unavailable" and "host service" in st["message"]
