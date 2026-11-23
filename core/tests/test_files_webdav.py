# SPDX-License-Identifier: Apache-2.0
"""files-webdav (#722): WebDAV on the LAN and mesh with per-person app passwords.

Acceptance: path confinement, a revoked password fails at once, cloud read-only folders refuse
writes, no WebDAV on non-LAN interfaces. Must refuse: gateway (owner) tokens as WebDAV credentials,
and guest access. Real gateway, real routes, real files on disk; the only thing faked is the
socket address the test client reports (the LAN rule reads it).
"""

from __future__ import annotations

import base64
import os
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, GUEST, OWNER
from files_support import audit_events
from onemind_core.app import create_app
from onemind_core.files.settings import FilesSettings

LAN_PEER, LAN_BOX = "169.254.1.20", "http://169.254.1.10"  # link-local: LAN to netpath.py
PW = "/v1/files/app-passwords"


@pytest.fixture
def box(settings, clock, executor, tmp_path):
    s = replace(settings, sections={**settings.sections, "files": FilesSettings(root=tmp_path / "files", min_free_bytes=0)})
    with TestClient(create_app(s, clock=clock, executor=executor), client=(LAN_PEER, 50000), base_url=LAN_BOX) as c:
        yield c


def via(box: TestClient, peer: str, base: str = LAN_BOX) -> TestClient:
    return TestClient(box.app, client=(peer, 50000), base_url=base)


def new_password(box, headers=ADULT, scopes=("home:rw", "shared:rw"), label="Mac") -> dict:
    r = box.post(PW, headers=headers, json={"label": label, "scopes": list(scopes)})
    assert r.status_code == 201, r.text
    assert r.headers["cache-control"] == "no-store"
    return r.json()


def basic(cred: dict) -> dict:
    raw = f"{cred['username']}:{cred['password']}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


def dav(c: TestClient, method: str, path: str, cred: dict | None, **kw):
    headers = {**(basic(cred) if cred else {}), **kw.pop("headers", {})}
    return c.request(method, path, headers=headers, **kw)


def home_dir(box) -> str:
    homes = os.path.join(box.app.state.webdav.files.settings.root, "home")
    (only,) = [d for d in os.listdir(homes) if not d.startswith(".")]
    return os.path.join(homes, only)


# ---- app passwords (made and revoked in test_files_app_passwords.py) ------------------------------
def test_the_list_says_where_to_connect(box):
    info = box.get(PW, headers=ADULT).json()["webdav"]
    assert info == {"enabled": True, "path": "/dav/", "reach": ["lan", "mesh"],
                    "spaces": {"home": "Home", "shared": "Shared"}, "windows": "smb"}


def test_another_adult_cannot_revoke_someone_elses_password(box):
    cred = new_password(box, OWNER)
    assert box.post(f"{PW}/{cred['id']}/revoke", headers=ADULT).status_code == 404
    assert dav(box, "PROPFIND", "/dav/", cred, headers={"Depth": "0"}).status_code == 207


# ---- the protocol --------------------------------------------------------------------------------
def test_finder_flow_lists_writes_reads_moves_and_trashes(box):
    cred = new_password(box)
    opts = dav(box, "OPTIONS", "/dav/", cred)
    assert opts.status_code == 200 and opts.headers["dav"].startswith("1, 2")
    top = dav(box, "PROPFIND", "/dav/", cred, headers={"Depth": "1"})
    assert top.status_code == 207 and "/dav/Home/" in top.text and "/dav/Shared/" in top.text
    assert dav(box, "MKCOL", "/dav/Home/Notes", cred).status_code == 201
    big = os.urandom(300 * 1024)  # over the gateway's 256 KiB JSON body cap: WebDAV streams files
    assert dav(box, "PUT", "/dav/Home/Notes/a.bin", cred, content=big).status_code == 201
    got = dav(box, "GET", "/dav/Home/Notes/a.bin", cred)
    assert got.status_code == 200 and got.content == big
    assert "sandbox" in got.headers["content-security-policy"]  # a stored page never runs as the gateway
    listing = dav(box, "PROPFIND", "/dav/Home/Notes/", cred, headers={"Depth": "1"})
    assert "<D:getcontentlength>307200</D:getcontentlength>" in listing.text
    assert dav(box, "PUT", "/dav/Home/Notes/a.bin", cred, content=b"v2").status_code == 204
    moved = dav(box, "MOVE", "/dav/Home/Notes/a.bin", cred, headers={"Destination": f"{LAN_BOX}/dav/Home/b.bin"})
    assert moved.status_code == 201
    assert dav(box, "GET", "/dav/Home/b.bin", cred).content == b"v2"
    lock = dav(box, "LOCK", "/dav/Home/b.bin", cred, content=b"<?xml version='1.0'?><D:lockinfo xmlns:D='DAV:'/>")
    assert lock.status_code == 200 and lock.headers["lock-token"].startswith("<opaquelocktoken:")
    assert dav(box, "UNLOCK", "/dav/Home/b.bin", cred, headers={"Lock-Token": lock.headers["lock-token"]}).status_code == 204
    assert dav(box, "DELETE", "/dav/Home/b.bin", cred).status_code == 204
    trash = box.get("/v1/files/trash", headers=ADULT).json()
    assert {"/Notes/a.bin", "/b.bin"} <= {t["path"] for t in trash}  # deletes and overwrites go to Trash


def test_propfind_infinity_and_unknown_methods_are_refused(box):
    cred = new_password(box)
    assert dav(box, "PROPFIND", "/dav/Home/", cred, headers={"Depth": "infinity"}).status_code == 403
    r = dav(box, "PROPPATCH", "/dav/Home/", cred)
    assert r.status_code == 405 and "PROPFIND" in r.headers["allow"]


# ---- acceptance: path confinement ----------------------------------------------------------------
def test_paths_cannot_leave_the_space(box, tmp_path):
    cred = new_password(box)
    assert dav(box, "PROPFIND", "/dav/Home/", cred, headers={"Depth": "0"}).status_code == 207
    outside = tmp_path / "secret.txt"
    outside.write_bytes(b"not yours")
    os.symlink(outside, os.path.join(home_dir(box), "link"))
    assert dav(box, "GET", "/dav/Home/link", cred).status_code == 403
    assert dav(box, "PUT", "/dav/Home/link", cred, content=b"x").status_code == 403
    assert outside.read_bytes() == b"not yours"
    assert dav(box, "GET", "/dav/Home/%2e%2e/%2e%2e/secret.txt", cred).status_code == 400
    assert dav(box, "GET", "/dav/Elsewhere/x", cred).status_code == 404
    escape = dav(box, "MOVE", "/dav/Home/link", cred, headers={"Destination": f"{LAN_BOX}/v1/files/x"})
    assert escape.status_code == 400


def test_scopes_and_role_both_limit_what_a_password_reaches(box):
    shared_only = new_password(box, scopes=["shared:r"])
    top = dav(box, "PROPFIND", "/dav/", shared_only, headers={"Depth": "1"})
    assert "/dav/Shared/" in top.text and "/dav/Home/" not in top.text
    assert dav(box, "PROPFIND", "/dav/Home/", shared_only, headers={"Depth": "0"}).status_code == 404
    assert dav(box, "PUT", "/dav/Shared/x.txt", shared_only, content=b"x").status_code == 403
    assert dav(box, "LOCK", "/dav/Shared/x.txt", shared_only).status_code == 403


# ---- acceptance: a revoked password fails at once ------------------------------------------------
def test_a_revoked_password_fails_on_the_very_next_request(box):
    cred = new_password(box)
    assert dav(box, "PROPFIND", "/dav/", cred, headers={"Depth": "0"}).status_code == 207
    assert box.post(f"{PW}/{cred['id']}/revoke", headers=OWNER).status_code == 200  # the owner may revoke anyone's
    r = dav(box, "PROPFIND", "/dav/", cred, headers={"Depth": "0"})
    assert r.status_code == 401 and r.headers["www-authenticate"].startswith("Basic ")


def test_a_password_only_works_with_its_own_username(box):
    cred = new_password(box)
    assert dav(box, "PROPFIND", "/dav/", {**cred, "username": "owner"}, headers={"Depth": "0"}).status_code == 401


# ---- acceptance: cloud read-only folders refuse writes -------------------------------------------
def test_the_cloud_import_area_is_read_only(box):
    cred = new_password(box)
    dav(box, "PROPFIND", "/dav/Home/", cred, headers={"Depth": "0"})
    drive = os.path.join(home_dir(box), "Cloud", "Drive")
    os.makedirs(drive)
    with open(os.path.join(drive, "a.txt"), "wb") as f:
        f.write(b"mirrored")
    assert dav(box, "GET", "/dav/Home/Cloud/Drive/a.txt", cred).content == b"mirrored"
    for method, path, kw in [
        ("PUT", "/dav/Home/Cloud/Drive/a.txt", {"content": b"changed"}),
        ("PUT", "/dav/Home/Cloud/Drive/new.txt", {"content": b"new"}),
        ("DELETE", "/dav/Home/Cloud/Drive/a.txt", {}),
        ("MKCOL", "/dav/Home/Cloud/Other", {}),
        ("DELETE", "/dav/Home/Cloud", {}),
        ("MOVE", "/dav/Home/Cloud/Drive/a.txt", {"headers": {"Destination": "/dav/Home/a.txt"}}),
        ("LOCK", "/dav/Home/Cloud/Drive/a.txt", {}),
    ]:
        assert dav(box, method, path, cred, **kw).status_code == 403, (method, path)
    assert dav(box, "PUT", "/dav/Home/x.txt", cred, content=b"x").status_code == 201
    into = dav(box, "MOVE", "/dav/Home/x.txt", cred, headers={"Destination": "/dav/Home/Cloud/x.txt"})
    assert into.status_code == 403
    with open(os.path.join(drive, "a.txt"), "rb") as f:
        assert f.read() == b"mirrored"


# ---- acceptance: no WebDAV on non-LAN interfaces -------------------------------------------------
@pytest.mark.parametrize(("peer", "base"), [
    ("203.0.113.9", LAN_BOX),               # a client on the internet
    (LAN_PEER, "http://198.51.100.7"),     # a LAN client that reached the box's public interface
    ("127.0.0.1", "http://127.0.0.1"),     # loopback with no trusted edge: unknown, fails closed
    ("testclient", "http://testserver"),   # no address at all
])
def test_webdav_does_not_exist_off_the_lan_and_mesh(box, peer, base):
    cred = new_password(box)
    for method in ("OPTIONS", "PROPFIND", "GET", "PUT"):
        r = dav(via(box, peer, base), method, "/dav/Home/x", cred, content=b"x" if method == "PUT" else None)
        assert r.status_code == 404 and "www-authenticate" not in r.headers, (method, peer, base)


def test_the_mesh_reaches_webdav(box):
    cred = new_password(box)
    r = dav(via(box, "100.64.0.7", "http://100.64.0.1"), "PROPFIND", "/dav/", cred, headers={"Depth": "0"})
    assert r.status_code == 207


# ---- must refuse: gateway tokens and guests ------------------------------------------------------
@pytest.mark.parametrize("token", [OWNER, ADULT, AGENT])
def test_gateway_tokens_are_never_webdav_credentials(box, token):
    secret = token["Authorization"].split(" ", 1)[1]
    bearer = dav(box, "PROPFIND", "/dav/", None, headers={**token, "Depth": "0"})
    assert bearer.status_code == 401 and bearer.headers["www-authenticate"].startswith("Basic ")
    as_password = dav(box, "PROPFIND", "/dav/", {"username": "owner", "password": secret}, headers={"Depth": "0"})
    assert as_password.status_code == 401
    refused = [e for e in audit_events(box.app.state.gateway.settings) if e.get("event") == "webdav.token_refused"]
    assert refused and secret not in str(refused)


def test_no_anonymous_or_guest_access(box):
    assert dav(box, "PROPFIND", "/dav/", None, headers={"Depth": "0"}).status_code == 401
    guest = {"username": "guest", "password": GUEST["Authorization"].split(" ", 1)[1]}
    assert dav(box, "GET", "/dav/Shared/", guest).status_code == 401
    assert box.post(PW, headers=GUEST, json={"label": "x", "scopes": ["shared:r"]}).status_code == 403


def test_repeated_wrong_passwords_back_off(box):
    wrong = {"username": "adult", "password": "aaaa-aaaa-aaaa-aaaa-aaaa"}
    codes = [dav(box, "PROPFIND", "/dav/", wrong, headers={"Depth": "0"}).status_code for _ in range(12)]
    assert codes[0] == 401 and codes[-1] == 429
