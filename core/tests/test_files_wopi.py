# SPDX-License-Identifier: Apache-2.0
"""WOPI host (issue #675): person-only file tokens, the six WOPI operations, locks and audited saves."""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import socket
import threading
import time
import tracemalloc
from dataclasses import replace

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from sqlalchemy import update

from onemind_core import serve
from onemind_core.app import create_app
from onemind_core.files import wopi as wopi_mod
from onemind_core.files.wopi import LOCK_TTL, TOKEN_TTL, WopiRepository, WopiTokenRow
from onemind_core.identity.settings import IdentitySettings

from conftest import AGENT, OWNER
from files_support import audit_events, files_root, files_settings, ok, upload  # noqa: F401

PASSWORD = "correct horse battery staple 1"
DOC = b"PK\x03\x04 first draft of the household budget"


@pytest.fixture
def wc(settings, clock, executor, files_settings):
    """A gateway with a temporary FILES root and household sign-in (bearer sessions, as the CLI and apps use)."""
    s = replace(settings, sections={**settings.sections, "files": files_settings,
                                    "identity": IdentitySettings(cookie_secure=False)})
    with TestClient(create_app(s, clock=clock, executor=executor)) as c:
        yield c


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def owner(wc) -> dict:
    """The household owner signed in with a session: {id, headers, session}."""
    r = wc.post("/v1/auth/setup", headers=OWNER, json={"username": "zeus", "password": PASSWORD, "client": "cli"})
    assert r.status_code == 201, r.text
    body = r.json()
    return {"id": body["principal"]["id"], "headers": bearer(body["access_token"]), "session": body["session"]["id"]}


def signed_in(wc, owner, role: str, username: str) -> dict:
    r = wc.post("/v1/users", headers=owner["headers"], json={"display_name": username.title(), "role": role})
    assert r.status_code == 201, r.text
    code = r.json()["one_time"]["enrolment_code"]
    r = wc.post("/v1/auth/enrol", json={"code": code, "username": username, "password": PASSWORD, "client": "cli"})
    assert r.status_code == 201, r.text
    return {"id": r.json()["principal"]["id"], "headers": bearer(r.json()["access_token"])}


def home(person) -> str:
    return f"home:{person['id']}"


def put_doc(wc, person, root=None, name="budget.docx", data=DOC):
    ok(upload(wc, person["headers"], root or home(person), "/", name, data, overwrite=True), 204)


def token(wc, person, root, path="/budget.docx", status=201):
    r = wc.post("/v1/files/wopi/tokens", headers=person["headers"], json={"root": root, "path": path})
    assert r.status_code == status, r.text
    return r.json()


def wopi(t: dict, suffix: str = "") -> str:
    return f"{t['wopi_src']}{suffix}?access_token={t['access_token']}"


def lock(wc, t, lock_id="L1", override="LOCK", **extra):
    return wc.post(wopi(t), headers={"X-WOPI-Override": override, "X-WOPI-Lock": lock_id, **extra})


def put(wc, t, data: bytes, lock_id: str | None = "L1"):
    headers = {"X-WOPI-Override": "PUT"} | ({"X-WOPI-Lock": lock_id} if lock_id is not None else {})
    return wc.post(wopi(t, "/contents"), content=data, headers=headers)


def download(wc, person, root, path="/budget.docx") -> bytes:
    r = wc.get("/v1/files/download", params={"root": root, "path": path}, headers=person["headers"])
    assert r.status_code == 200, r.text
    return r.content


# ---- the happy path ---------------------------------------------------------------------------------------
def test_open_lock_save_unlock_writes_bytes_and_audits(wc, owner, settings):
    put_doc(wc, owner)
    t = token(wc, owner, home(owner))
    assert t["access_token"].startswith("om_wopi_") and t["can_write"] is True
    assert t["file_id"].startswith("wf_") and t["wopi_src"] == f"/v1/files/wopi/files/{t['file_id']}"

    info = ok(wc.get(wopi(t)))
    sha = hashlib.sha256(DOC).hexdigest()
    assert info["BaseFileName"] == "budget.docx" and info["Size"] == len(DOC) and info["UserId"] == owner["id"]
    assert info["Version"] == sha and info["SHA256"] == base64.b64encode(bytes.fromhex(sha)).decode()
    assert info["UserCanWrite"] is True and info["SupportsLocks"] is True

    r = wc.get(wopi(t, "/contents"))
    assert r.status_code == 200 and r.content == DOC and r.headers["x-wopi-itemversion"] == sha

    assert lock(wc, t).status_code == 200
    assert wc.post(wopi(t), headers={"X-WOPI-Override": "GET_LOCK"}).headers["x-wopi-lock"] == "L1"
    assert lock(wc, t, override="REFRESH_LOCK").status_code == 200
    new = b"PK\x03\x04 second draft, with the car insurance"
    r = put(wc, t, new)
    assert r.status_code == 200, r.text
    assert r.headers["x-wopi-itemversion"] == hashlib.sha256(new).hexdigest()
    assert download(wc, owner, home(owner)) == new
    assert ok(wc.get(wopi(t)))["Version"] == hashlib.sha256(new).hexdigest()
    again = new + b" and the boiler"
    assert put(wc, t, again).status_code == 200  # the lock holder saves again: its own save is not stale
    assert lock(wc, t, override="UNLOCK").status_code == 200
    assert wc.post(wopi(t), headers={"X-WOPI-Override": "GET_LOCK"}).headers["x-wopi-lock"] == ""

    events = audit_events(settings)
    names = [e["event"] for e in events]
    for name in ("files.wopi.token.issued", "files.wopi.opened", "files.wopi.locked", "files.wopi.saved",
                 "files.wopi.unlocked"):
        assert name in names, name
    saved = [e for e in events if e["event"] == "files.wopi.saved"]
    assert len(saved) == 2 and saved[0]["principal"]["id"] == owner["id"]
    assert saved[0]["data"]["payload"]["path"] == "/budget.docx" and saved[0]["data"]["payload"]["size"] == len(new)
    assert t["access_token"] not in "\n".join(str(e) for e in events)  # the token itself is never written down


# ---- PutFile refusals --------------------------------------------------------------------------------------
def test_put_without_lock_wrong_lock_or_stale_version_is_409(wc, owner):
    put_doc(wc, owner)
    t = token(wc, owner, home(owner))
    r = put(wc, t, b"no lock")
    assert r.status_code == 409 and r.json()["reason"] == "not_locked" and r.headers["x-wopi-lock"] == ""
    assert lock(wc, t).status_code == 200
    r = put(wc, t, b"wrong lock", lock_id="L2")
    assert r.status_code == 409 and r.json()["reason"] == "lock_mismatch" and r.headers["x-wopi-lock"] == "L1"
    r = put(wc, t, b"no lock header", lock_id=None)
    assert r.status_code == 409 and r.headers["x-wopi-lock"] == "L1"
    r = lock(wc, t, lock_id="L2")  # another editing session cannot take the lock
    assert r.status_code == 409 and r.headers["x-wopi-lock"] == "L1"

    put_doc(wc, owner, data=b"changed in Files while the editor had it open")
    r = put(wc, t, b"would overwrite that change")
    assert r.status_code == 409 and r.json()["reason"] == "stale_version"
    assert download(wc, owner, home(owner)) == b"changed in Files while the editor had it open"


def test_an_expired_lock_is_no_lock(wc, owner, clock):
    put_doc(wc, owner)
    t = token(wc, owner, home(owner))
    assert lock(wc, t).status_code == 200
    clock.advance(LOCK_TTL.total_seconds() + 1)
    t = token(wc, owner, home(owner))  # a fresh token: the first one expired meanwhile
    r = put(wc, t, b"late save")
    assert r.status_code == 409 and r.json()["reason"] == "not_locked"


# ---- tokens: expiry, session, wrong user ----------------------------------------------------------------
def test_token_expires_within_minutes(wc, owner, clock):
    put_doc(wc, owner)
    t = token(wc, owner, home(owner))
    assert TOKEN_TTL.total_seconds() <= 15 * 60
    assert wc.get(wopi(t)).status_code == 200
    clock.advance(TOKEN_TTL.total_seconds() + 1)
    r = wc.get(wopi(t))
    assert r.status_code == 401 and r.json()["error"] == "unauthenticated"
    assert wc.get(wopi(t, "/contents")).status_code == 401


def test_token_dies_with_its_session(wc, owner):
    put_doc(wc, owner)
    t = token(wc, owner, home(owner))
    assert wc.post("/v1/auth/logout", headers=owner["headers"]).status_code == 204
    assert wc.get(wopi(t)).status_code == 401


def test_missing_or_unknown_token_is_401(wc, owner):
    put_doc(wc, owner)
    t = token(wc, owner, home(owner))
    src = t["wopi_src"]
    for url in (src, f"{src}?access_token=om_wopi_nope", f"{src}?access_token={t['access_token']}x"):
        r = wc.get(url, headers=owner["headers"])  # a bearer session is not a WOPI token
        assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer", url


def test_wrong_user_is_refused(wc, owner):
    olive = signed_in(wc, owner, "owner", "olive")  # a second owner: Homes stay private even between owners
    put_doc(wc, owner)
    put_doc(wc, owner, root="shared", name="shared.docx")
    # another person's Home: no token, and the refusal is audited
    token(wc, olive, home(owner), status=403)
    # a token is for one file only: the other owner's Shared token does not open the owner's Home file
    mine = token(wc, olive, "shared", "/shared.docx")
    theirs = token(wc, owner, home(owner))
    assert wc.get(f"{theirs['wopi_src']}?access_token={mine['access_token']}").status_code == 401
    assert wc.get(f"{theirs['wopi_src']}/contents?access_token={mine['access_token']}").status_code == 401
    assert ok(wc.get(wopi(mine)))["UserId"] == olive["id"]


@pytest.mark.parametrize("role", ["adult", "guest", "child", "teen"])
def test_a_non_owner_session_gets_no_token(wc, owner, role):
    """The token route needs "*" like every /v1/files/* route: no side door around the role scopes."""
    person = signed_in(wc, owner, role, f"{role}x")
    put_doc(wc, owner, root="shared", name="shared.docx")
    assert wc.get("/v1/files/list", params={"root": "shared", "path": "/"}, headers=person["headers"]).status_code == 403
    for root, path in (("shared", "/shared.docx"), (home(person), "/budget.docx")):
        r = wc.post("/v1/files/wopi/tokens", headers=person["headers"], json={"root": root, "path": path})
        assert r.status_code == 403, (root, r.text)


def test_a_demoted_person_loses_the_token_at_once(wc, owner):
    olive = signed_in(wc, owner, "owner", "olive")
    put_doc(wc, owner, root="shared", name="shared.docx")
    t = token(wc, olive, "shared", "/shared.docx")
    assert ok(wc.get(wopi(t)))["UserCanWrite"] is True
    assert lock(wc, t).status_code == 200
    r = wc.patch(f"/v1/users/{olive['id']}", headers=owner["headers"], json={"role": "adult"})
    assert r.status_code == 200, r.text
    # her session is still live, but her role no longer holds "*": every WOPI call stops now, not at expiry
    assert wc.get(wopi(t)).status_code == 401
    assert wc.get(wopi(t, "/contents")).status_code == 401
    assert lock(wc, t, override="UNLOCK").status_code == 401
    assert put(wc, t, b"after the demotion").status_code == 401
    assert download(wc, owner, "shared", "/shared.docx") == DOC


def test_a_read_only_token_cannot_lock_or_save(wc, owner):
    """A token minted without write access (a future narrower Files scope) stays read-only on every call."""
    put_doc(wc, owner, root="shared", name="shared.docx")
    t = token(wc, owner, "shared", "/shared.docx")
    repo = WopiRepository(wc.app.state.gateway.db)
    with repo.db.session.begin() as s:
        s.execute(update(WopiTokenRow).where(WopiTokenRow.file_id == t["file_id"]).values(can_write=False))
    info = ok(wc.get(wopi(t)))
    assert info["UserCanWrite"] is False and info["ReadOnly"] is True
    assert wc.get(wopi(t, "/contents")).content == DOC
    assert lock(wc, t).status_code == 403
    assert put(wc, t, b"read-only edit").status_code == 403


# ---- big files: hashed and sent a chunk at a time --------------------------------------------------------
def test_a_big_file_is_hashed_and_sent_in_chunks(wc, owner, files_root, monkeypatch):
    monkeypatch.setattr(wopi_mod, "READ_CHUNK", 64 * 1024)
    put_doc(wc, owner)
    (space,) = [d for d in (files_root / "home").iterdir()]
    big = os.urandom(1024 * 1024) * 24  # 24 MiB on disk, never read into memory whole
    (space / "budget.docx").write_bytes(big)
    sha = hashlib.sha256(big).hexdigest()
    t = token(wc, owner, home(owner))
    tracemalloc.start()
    try:
        info = ok(wc.get(wopi(t)))
        assert lock(wc, t).status_code == 200
        assert lock(wc, t, override="UNLOCK").status_code == 200
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert info["Size"] == len(big) and info["Version"] == sha
    assert peak < 8 * 1024 * 1024, peak  # CheckFileInfo, Lock and Unlock hash 64 KiB at a time
    r = wc.get(wopi(t, "/contents"))
    assert r.status_code == 200 and r.headers["x-wopi-itemversion"] == sha
    assert r.headers["content-length"] == str(len(big)) and hashlib.sha256(r.content).hexdigest() == sha


# ---- identities that never get a token -----------------------------------------------------------------
def test_agents_api_tokens_and_static_tokens_are_refused(wc, owner, settings):
    put_doc(wc, owner)
    body = {"root": home(owner), "path": "/budget.docx"}
    r = wc.post("/v1/files/wopi/tokens", headers=AGENT, json=body)
    assert r.status_code == 403
    r = wc.post("/v1/files/wopi/tokens", headers=OWNER, json={"root": "home:owner", "path": "/budget.docx"})
    assert r.status_code == 403 and r.json()["reason"] == "not_a_session"  # the tokens file is no signed-in human
    pat = wc.post("/v1/tokens", headers=owner["headers"], json={"name": "sdk"}).json()["one_time"]["token"]
    r = wc.post("/v1/files/wopi/tokens", headers=bearer(pat), json=body)
    assert r.status_code == 403 and r.json()["reason"] == "not_a_session"  # an SDK or API token is not a session
    agent = wc.post("/v1/tokens", headers=owner["headers"], json={"name": "helper", "kind": "agent"})
    if agent.status_code == 201:  # a personal agent token (F-15)
        r = wc.post("/v1/files/wopi/tokens", headers=bearer(agent.json()["one_time"]["token"]), json=body)
        assert r.status_code in (401, 403)
    denied = [e for e in audit_events(settings) if e["event"] == "authz.denied"]
    assert len(denied) >= 3


# ---- paths -------------------------------------------------------------------------------------------------
def test_traversal_and_symlinks_are_refused(wc, owner, files_root, tmp_path):
    put_doc(wc, owner)
    for bad in ("/../budget.docx", "/a/../../etc/passwd", "a\\b", "/./budget.docx"):
        r = wc.post("/v1/files/wopi/tokens", headers=owner["headers"], json={"root": home(owner), "path": bad})
        assert r.status_code == 422 and r.json()["reason"] == "invalid_path", bad
    r = wc.post("/v1/files/wopi/tokens", headers=owner["headers"], json={"root": "home:../../etc", "path": "/passwd"})
    assert r.status_code == 403
    outside = tmp_path / "outside.docx"
    outside.write_bytes(b"secret")
    (space,) = [d for d in (files_root / "home").iterdir()]
    os.symlink(outside, space / "link.docx")
    os.symlink(tmp_path, space / "linkdir")
    assert wc.post("/v1/files/wopi/tokens", headers=owner["headers"],
                   json={"root": home(owner), "path": "/link.docx"}).status_code == 403
    assert wc.post("/v1/files/wopi/tokens", headers=owner["headers"],
                   json={"root": home(owner), "path": "/linkdir/outside.docx"}).status_code == 403
    t = token(wc, owner, home(owner))
    assert wc.get(f"/v1/files/wopi/files/..%2F..%2Fetc?access_token={t['access_token']}").status_code in (401, 404)
    token(wc, owner, home(owner), "/missing.docx", status=404)
    assert token(wc, owner, home(owner), "/", status=409)["reason"] == "not_a_file"


def test_unknown_override_is_501(wc, owner):
    put_doc(wc, owner)
    t = token(wc, owner, home(owner))
    assert wc.post(wopi(t), headers={"X-WOPI-Override": "PUT_RELATIVE"}).status_code == 501
    assert wc.post(wopi(t, "/contents"), content=b"x", headers={"X-WOPI-Override": "LOCK"}).status_code == 501


# ---- the access log ---------------------------------------------------------------------------------------
class _Records(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def test_wopi_calls_leave_no_access_token_in_the_uvicorn_access_log(settings, clock, executor, files_settings):
    """The token rides in ?access_token=; a real uvicorn listener with the gateway's log config must not log it."""
    s = replace(settings, sections={**settings.sections, "files": files_settings,
                                    "identity": IdentitySettings(cookie_secure=False)})
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = serve._Server(uvicorn.Config(create_app(s, clock=clock, executor=executor), host="127.0.0.1",
                                          port=port, lifespan="on", log_config=serve.log_config()))
    captured = _Records()
    access = logging.getLogger("uvicorn.access")
    access.addHandler(captured)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 30
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline, "uvicorn did not start"
            time.sleep(0.05)
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30) as c:
            r = c.post("/v1/auth/setup", headers=OWNER, json={"username": "zeus", "password": PASSWORD, "client": "cli"})
            assert r.status_code == 201, r.text
            person = {"id": r.json()["principal"]["id"], "headers": bearer(r.json()["access_token"])}
            put_doc(c, person)
            t = token(c, person, home(person))
            assert t["access_token"].startswith("om_wopi_")
            assert c.get(wopi(t)).status_code == 200                       # CheckFileInfo
            assert c.get(wopi(t, "/contents")).content == DOC              # GetFile
            assert lock(c, t).status_code == 200                           # Lock
            assert put(c, t, b"PK\x03\x04 second draft").status_code == 200  # PutFile
    finally:
        server.should_exit = True
        thread.join(timeout=30)
        access.removeHandler(captured)
    lines = [r.getMessage() for r in captured.records]
    wopi_lines = [line for line in lines if "/v1/files/wopi/files/" in line]
    assert len(wopi_lines) >= 4, lines
    assert all("access_token=[redacted]" in line for line in wopi_lines), wopi_lines
    for record in captured.records:
        for handler in access.handlers:
            if handler is not captured and handler.formatter is not None:
                assert "om_wopi_" not in handler.format(record)
        assert "om_wopi_" not in record.getMessage() and "om_wopi_" not in repr(record.args)
