# SPDX-License-Identifier: Apache-2.0
"""FILES-SHARE-01 part 2 (#235): the folders Samba serves, the SMB password, and the real host client.

The client is run against a socket that speaks the host service's protocol (internal/host/smb.go), not a
patched-in object, so the paths, verbs and bodies it sends are the ones the Go side parses.
"""

from __future__ import annotations

import json
import shutil
import socket
import tempfile
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import AGENT, GUEST, OWNER
from onemind_core.smbshares import FileShareSettings, HostSmbClient, SmbHostError, smb_user
from test_identity import LOCAL_PEER, setup_bearer_owner
from test_smb_shares import GIB, approve, ask, box, on  # noqa: F401  (fixtures)


def test_time_machine_gets_its_own_folder_outside_the_files_home(on):
    approve(on, ask(on, {"kind": "home", "person_id": "adult"}))
    approve(on, ask(on, {"kind": "timemachine", "person_id": "adult", "quota_bytes": 5 * GIB}))
    root = on.svc.files.settings.root
    assert {s["path"] for s in on.svc.host.calls[-1]} == {"home/adult", ".system/timemachine/adult"}
    assert (root / ".system" / "timemachine" / "adult").is_dir()
    assert not (root / "home" / "adult" / "timemachine").exists()


def test_a_person_with_a_share_gets_a_password_shown_once_and_sent_only_to_the_host(on):
    assert on.post("/v1/shares/smb/password", headers=OWNER).json()["reason"] == "no_share"
    approve(on, ask(on, {"kind": "home", "person_id": "owner"}))
    r = on.post("/v1/shares/smb/password", headers=OWNER)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    body = r.json()
    assert body["user"] == smb_user("owner") and body["shown_once"] is True and len(body["password"]) == 19
    assert on.svc.host.passwords == [(smb_user("owner"), body["password"])]
    assert body["password"] not in on.get("/v1/shares/smb", headers=OWNER).text  # kept nowhere on the gateway
    assert on.post("/v1/shares/smb/password", headers=OWNER).json()["password"] != body["password"]
    for who in (AGENT, GUEST):
        assert on.post("/v1/shares/smb/password", headers=who).status_code == 403


def test_a_new_smb_password_needs_l1_after_setup(on):
    """A left-open password or token session must not mint an SMB password that opens the whole Files home."""
    approve(on, ask(on, {"kind": "home", "person_id": "owner"}))
    assert on.post("/v1/shares/smb/password", headers=OWNER).status_code == 200
    passwords = list(on.svc.host.passwords)
    home = TestClient(on.app, client=LOCAL_PEER)
    signed_in = setup_bearer_owner(home)
    r = on.post("/v1/shares/smb/password", headers=OWNER)
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required"
    r = home.post("/v1/shares/smb/password", headers=signed_in)
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required", r.text
    assert on.svc.host.passwords == passwords  # neither refusal reached the host


def test_a_password_the_host_cannot_set_is_a_refusal(on):
    approve(on, ask(on, {"kind": "home", "person_id": "owner"}))
    on.svc.host.fail = SmbHostError("host_error", "smbpasswd failed")
    r = on.post("/v1/shares/smb/password", headers=OWNER)
    assert r.status_code == 409 and r.json()["reason"] == "host_error"


def test_the_host_client_speaks_the_host_protocol():
    short = Path(tempfile.mkdtemp(prefix="om", dir="/tmp"))  # a Unix socket path is limited to about 100 bytes
    sock = str(short / "host.sock")
    seen: list[tuple[str, str, dict | None]] = []
    answers = [(200, {"available": False, "unavailable_reason": "Samba is not installed", "shares": 0}),
               (200, {"available": True, "unavailable_reason": None, "shares": 0}),
               (200, {"applied": 1}), (409, {"error": "refused", "reason": "config_rejected", "message": "rejected"}),
               (200, {"ok": True}), (500, {"error": "internal", "reason": "smb_apply", "message": "x"})]
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
    host = HostSmbClient(FileShareSettings(host_socket=short / "host.sock", host_timeout_s=5))
    ok, reason, msg = host.status()
    assert not ok and reason == "smb_unavailable" and "Samba is not installed" in msg
    assert host.status()[0] is True
    host.apply([{"id": "shr_1"}])
    with pytest.raises(SmbHostError) as e:
        host.apply([])
    assert e.value.reason == "config_rejected"
    host.set_password("alex", "pw-pw-pw-pw")
    with pytest.raises(SmbHostError) as e2:
        host.set_password("alex", "x")
    assert e2.value.reason == "host_error"
    t.join(5)
    srv.close()
    shutil.rmtree(short, ignore_errors=True)
    assert seen[2] == ("PUT", "/v1/smb/shares", {"shares": [{"id": "shr_1"}]})
    assert seen[4] == ("PUT", "/v1/smb/users/alex/password", {"password": "pw-pw-pw-pw"})


def test_no_socket_means_unavailable_with_a_reason(tmp_path):
    ok, reason, msg = HostSmbClient(FileShareSettings(host_socket=tmp_path / "none.sock")).status()
    assert (ok, reason) == (False, "smb_unavailable") and "host service" in msg
