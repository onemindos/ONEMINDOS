# SPDX-License-Identifier: Apache-2.0
"""Contract §12.6 identity: setup, sign-in, sessions + CSRF, TOTP, passkeys, step-up approvals,
users, API tokens, per-app sharing, /v1/me and the audit of each decision. Runs on SQLite and,
with ONEMIND_TEST_DB_URL, on PostgreSQL."""

from __future__ import annotations

import hashlib
import json
import os
import re
import struct
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from conftest import AGENT, GUEST, OWNER, action_body
from onemind_core.app import create_app
from onemind_core.identity import IdentitySettings
from onemind_core.identity.crypto import b64url, totp_code, unb64url

ORIGIN, RP_ID = "http://localhost", "localhost"
PASSWORD = "correct horse battery"


class SoftAuthenticator:
    """A software passkey (ES256, attestation "none") so tests run the real WebAuthn verification."""

    def __init__(self, rp_id: str = RP_ID, origin: str = ORIGIN):
        self.rp_id, self.origin = rp_id, origin
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.cred_id = os.urandom(16)
        self.counter = 0

    def _client_data(self, typ: str, challenge: str) -> bytes:
        return json.dumps({"type": typ, "challenge": challenge, "origin": self.origin, "crossOrigin": False}).encode()

    def register(self, options: dict) -> dict:
        nums = self.key.public_key().public_numbers()
        cose = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: nums.x.to_bytes(32, "big"), -3: nums.y.to_bytes(32, "big")})
        auth_data = (hashlib.sha256(self.rp_id.encode()).digest() + bytes([0x45]) + struct.pack(">I", 0)
                     + bytes(16) + struct.pack(">H", len(self.cred_id)) + self.cred_id + cose)
        att = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        cd = self._client_data("webauthn.create", options["publicKey"]["challenge"])
        return {"id": b64url(self.cred_id), "rawId": b64url(self.cred_id), "type": "public-key",
                "response": {"clientDataJSON": b64url(cd), "attestationObject": b64url(att), "transports": ["internal"]}}

    def assert_(self, challenge: str, flat: bool = False) -> dict:
        self.counter += 1
        auth_data = hashlib.sha256(self.rp_id.encode()).digest() + bytes([0x05]) + struct.pack(">I", self.counter)
        cd = self._client_data("webauthn.get", challenge)
        sig = self.key.sign(auth_data + hashlib.sha256(cd).digest(), ec.ECDSA(hashes.SHA256()))
        body = {"clientDataJSON": b64url(cd), "authenticatorData": b64url(auth_data), "signature": b64url(sig)}
        if flat:  # the §12.4 flat shape
            return {"id": b64url(self.cred_id), **body}
        return {"id": b64url(self.cred_id), "rawId": b64url(self.cred_id), "type": "public-key", "response": body}


def id_settings(settings, **changes):
    cfg = IdentitySettings(rp_id=RP_ID, origins=(ORIGIN,), cookie_secure=False, **changes)
    return replace(settings, sections={**settings.sections, "identity": cfg})


@pytest.fixture
def idc(settings, clock, executor):
    with TestClient(create_app(id_settings(settings), clock=clock, executor=executor)) as c:
        yield c


def csrf(c: TestClient) -> dict:
    return {"OneMind-CSRF": c.cookies.get("onemind_csrf")}


def setup_owner(c: TestClient, username="zeus") -> dict:
    r = c.post("/v1/auth/setup", headers=OWNER, json={"username": username, "display_name": "Zeus", "password": PASSWORD})
    assert r.status_code == 201, r.text
    return r.json()


def audit_events(settings) -> list[dict]:
    return [json.loads(line) for line in Path(settings.audit_path).read_text().splitlines()]


def new_session_client(c: TestClient) -> TestClient:
    """A second browser on the same app (own cookie jar)."""
    return TestClient(c.app)


# ---- bootstrap and sign-in ------------------------------------------------------------------------
def test_setup_needs_install_owner_token_and_runs_once(idc, settings):
    bad = idc.post("/v1/auth/setup", headers=GUEST, json={"username": "zeus", "password": PASSWORD})
    assert bad.status_code == 401
    body = setup_owner(idc)
    assert body["principal"]["role"] == "owner" and body["session"]["id"].startswith("ses_")
    assert "onemind_session" in idc.cookies and body["csrf_token"] == idc.cookies.get("onemind_csrf")
    me = idc.get("/v1/me").json()
    assert me["principal"]["username"] == "zeus" and me["session"]["auth_method"] == "setup"
    assert "can_approve" in me["capabilities"] and me["scopes"] == ["*"]
    again = idc.post("/v1/auth/setup", headers=OWNER, json={"username": "other", "password": PASSWORD})
    assert again.status_code == 409 and again.json()["reason"] == "already_set_up"
    events = [e["event"] for e in audit_events(settings)]
    assert "auth.setup.rejected" in events and "auth.setup.completed" in events and "auth.login.succeeded" in events


def test_setup_accepts_first_boot_token_file(settings, clock, executor, tmp_path):
    f = tmp_path / "setup-token"
    f.write_text("first-boot-" + os.urandom(8).hex() + "\n")
    s = replace(settings, sections={"identity": IdentitySettings(rp_id=RP_ID, origins=(ORIGIN,), cookie_secure=False,
                                                                 setup_token_file=f)})
    with TestClient(create_app(s, clock=clock, executor=executor)) as c:
        r = c.post("/v1/auth/setup", headers={"Authorization": "Bearer " + f.read_text().strip()},
                   json={"username": "zeus", "password": PASSWORD})
        assert r.status_code == 201


def test_cookie_session_needs_csrf_on_unsafe_methods(idc, settings):
    setup_owner(idc)
    assert idc.get("/v1/users").status_code == 200  # GET needs no CSRF header
    r = idc.post("/v1/users", json={"display_name": "Ana", "role": "adult"})
    assert r.status_code == 403 and r.json()["reason"] == "csrf"
    r = idc.post("/v1/users", json={"display_name": "Ana", "role": "adult"}, headers={"OneMind-CSRF": "wrong"})
    assert r.status_code == 403
    r = idc.post("/v1/users", json={"display_name": "Ana", "role": "adult"}, headers=csrf(idc))
    assert r.status_code == 201
    assert any(e["event"] == "authz.denied" and e["data"]["payload"]["reason"] == "csrf" for e in audit_events(settings))


def test_password_login_failures_are_rate_limited(idc, settings):
    setup_owner(idc)
    other = new_session_client(idc)
    for _ in range(10):
        r = other.post("/v1/auth/login", json={"username": "zeus", "password": "wrong password!"})
        assert r.status_code == 401 and r.json()["reason"] == "bad_credentials"
    r = other.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD})
    assert r.status_code == 429 and r.json()["error"] == "rate_limited" and int(r.headers["retry-after"]) > 0
    assert sum(e["event"] == "auth.login.failed" for e in audit_events(settings)) == 10


def test_totp_second_factor(idc, clock):
    setup_owner(idc)
    secret = idc.post("/v1/auth/totp/setup", headers=csrf(idc)).json()["one_time"]["secret"]
    step = int(clock.now.timestamp() // 30)
    assert idc.post("/v1/auth/totp/confirm", json={"code": "000000" if totp_code(secret, step) != "000000" else "111111"},
                    headers=csrf(idc)).status_code == 422
    assert idc.post("/v1/auth/totp/confirm", json={"code": totp_code(secret, step)}, headers=csrf(idc)).status_code == 204
    other = new_session_client(idc)
    r = other.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD})
    assert r.status_code == 401 and r.json()["reason"] == "totp_required"
    r = other.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD, "totp": totp_code(secret, step)})
    assert r.status_code == 401 and r.json()["reason"] == "totp_invalid"  # the confirm used this step: replay
    clock.advance(30)
    r = other.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD, "totp": totp_code(secret, step + 1)})
    assert r.status_code == 200 and other.get("/v1/me").json()["session"]["auth_method"] == "password+totp"


def test_bearer_session_for_cli_with_refresh(idc, clock):
    setup_owner(idc)
    cli = new_session_client(idc)
    body = cli.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD, "client": "cli"}).json()
    assert body["access_token"].startswith("om_ses_") and body["refresh_token"].startswith("om_ref_")
    assert "onemind_session" not in cli.cookies
    h = {"Authorization": "Bearer " + body["access_token"]}
    assert cli.post("/v1/users", headers=h, json={"display_name": "Ana", "role": "adult"}).status_code == 201  # no CSRF
    clock.advance(61 * 60)
    assert cli.get("/v1/me", headers=h).status_code == 401  # access token expired
    new = cli.post("/v1/auth/refresh", json={"refresh_token": body["refresh_token"]}).json()
    assert cli.get("/v1/me", headers={"Authorization": "Bearer " + new["access_token"]}).status_code == 200
    assert cli.post("/v1/auth/refresh", json={"refresh_token": body["refresh_token"]}).status_code == 401  # rotated


def test_sessions_list_revoke_and_logout(idc):
    setup_owner(idc)
    phone = new_session_client(idc)
    phone.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD}, headers={"User-Agent": "phone"})
    sessions = idc.get("/v1/auth/sessions").json()
    assert len(sessions) == 2 and sum(s["current"] for s in sessions) == 1
    phone_id = next(s["id"] for s in sessions if s["client"] == "phone")
    assert idc.delete(f"/v1/auth/sessions/{phone_id}", headers=csrf(idc)).status_code == 204
    assert phone.get("/v1/me").status_code == 401  # revoke is instant
    assert idc.post("/v1/auth/logout", headers=csrf(idc)).status_code == 204
    assert idc.get("/v1/me").status_code == 401


def test_idle_session_expires(idc, clock):
    setup_owner(idc)
    clock.advance(73 * 3600)
    assert idc.get("/v1/me").status_code == 401


# ---- users, roles and sharing ---------------------------------------------------------------------
def enrol(idc: TestClient, role: str, username: str) -> TestClient:
    r = idc.post("/v1/users", json={"display_name": username.title(), "role": role}, headers=csrf(idc))
    assert r.status_code == 201, r.text
    one = r.json()["one_time"]
    assert one["enrolment_url"].endswith("/signin#enrol=" + one["enrolment_code"])
    c = new_session_client(idc)
    r = c.post("/v1/auth/enrol", json={"code": one["enrolment_code"], "username": username, "password": PASSWORD})
    assert r.status_code == 201, r.text
    assert c.post("/v1/auth/enrol", json={"code": one["enrolment_code"], "username": "x" + username,
                                          "password": PASSWORD}).status_code == 401  # single use
    return c


def test_household_roles_and_role_scopes(idc, clock):
    setup_owner(idc)
    adult, guest, child = enrol(idc, "adult", "ana"), enrol(idc, "guest", "gus"), enrol(idc, "child", "kid")
    assert adult.get("/v1/actions").status_code == 200
    assert guest.get("/v1/actions").status_code == 403  # H-21
    assert child.get("/v1/nodes").status_code == 403
    assert guest.get("/v1/me").json()["principal"]["role"] == "guest"
    # The scope lets an adult reach POST /v1/actions; the §3 action rules (owner or agent requests)
    # still refuse it until the actions stream adopts §12.5's "Ad" requester column.
    r = adult.post("/v1/actions", json=action_body(clock), headers=csrf(adult))
    assert r.status_code == 403 and r.json().get("reason") is None
    aid = idc.post("/v1/actions", json=action_body(clock), headers=OWNER).json()["id"]
    assert adult.post(f"/v1/actions/{aid}/approve", headers=csrf(adult)).status_code == 403  # never approve
    assert adult.get("/v1/users").status_code == 403
    users = idc.get("/v1/users").json()
    assert {u["role"] for u in users} == {"owner", "adult", "guest", "child"}


def test_last_owner_cannot_be_demoted_or_disabled(idc):
    setup_owner(idc)
    me = idc.get("/v1/me").json()["principal"]["id"]
    r = idc.patch(f"/v1/users/{me}", json={"role": "adult"}, headers=csrf(idc))
    assert r.status_code == 409 and r.json()["reason"] == "last_owner"
    assert idc.post(f"/v1/users/{me}/disable", headers=csrf(idc)).status_code == 409


def test_disable_revokes_sessions_and_tokens(idc):
    setup_owner(idc)
    adult = enrol(idc, "adult", "ana")
    tok = adult.post("/v1/tokens", json={"name": "script"}, headers=csrf(adult)).json()["one_time"]["token"]
    uid = adult.get("/v1/me").json()["principal"]["id"]
    assert idc.post(f"/v1/users/{uid}/disable", headers=csrf(idc)).json()["disabled"] is True
    assert adult.get("/v1/me").status_code == 401
    assert idc.get("/v1/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401
    assert new_session_client(idc).post("/v1/auth/login", json={"username": "ana", "password": PASSWORD}).status_code == 401


def test_per_app_sharing(idc):
    setup_owner(idc)
    guest = enrol(idc, "guest", "gus")
    assert idc.get("/v1/apps").json()  # the owner sees every app
    assert guest.get("/v1/apps").json() == []  # nothing shared yet
    gid = guest.get("/v1/me").json()["principal"]["id"]
    r = idc.put("/v1/apps/whoami/access", json={"roles": ["adult"], "people": [gid]}, headers=csrf(idc))
    assert r.status_code == 200 and r.json()["roles"] == ["owner", "adult"]  # owner always included
    assert [a["id"] for a in guest.get("/v1/apps").json()] == ["whoami"]
    mine = guest.get("/v1/apps/whoami/access").json()
    assert mine["allowed"] is True and mine["people"] == [{"id": gid, "display_name": "Gus"}] and mine["roles"] == []
    assert guest.put("/v1/apps/whoami/access", json={"roles": ["guest"]}, headers=csrf(guest)).status_code == 403
    idc.put("/v1/apps/whoami/access", json={"roles": [], "people": []}, headers=csrf(idc))
    assert guest.get("/v1/apps").json() == []  # removing access is instant
    assert idc.get("/v1/apps/nope/access").status_code == 404


def test_static_file_principals_keep_v0_behaviour(idc):
    setup_owner(idc)
    assert [a["id"] for a in idc.get("/v1/apps", headers=GUEST).json()]  # file guest: v0, sees the catalog
    me = idc.get("/v1/me", headers=AGENT).json()
    assert me["principal"] == {"id": "hermes", "kind": "agent", "role": "agent"} and me["token"]["source"] == "file"
    assert "can_approve" not in me["capabilities"]


# ---- API tokens (H-09) ---------------------------------------------------------------------------
def test_token_lifecycle(idc, clock):
    setup_owner(idc)
    r = idc.post("/v1/tokens", json={"name": "laptop", "scopes": ["instance:read", "nodes:read"],
                                     "expires_in_days": 30}, headers=csrf(idc))
    assert r.status_code == 201
    secret, tid = r.json()["one_time"]["token"], r.json()["id"]
    assert re.fullmatch(r"om_pat_[A-Za-z0-9_-]{43}", secret) and r.json()["prefix"] == secret[:11]
    listed = idc.get("/v1/tokens").json()
    assert secret not in json.dumps(listed)
    assert {t["source"] for t in listed} == {"api", "file"}
    h = {"Authorization": f"Bearer {secret}"}
    assert idc.get("/v1/nodes", headers=h).status_code == 200
    assert idc.get("/v1/actions", headers=h).status_code == 403  # outside its scopes
    assert next(t for t in idc.get("/v1/tokens").json() if t["id"] == tid)["last_used_at"] is not None
    rot = idc.post(f"/v1/tokens/{tid}/rotate", json={"grace_s": 60}, headers=csrf(idc)).json()
    new = {"Authorization": "Bearer " + rot["one_time"]["token"]}
    assert idc.get("/v1/nodes", headers=h).status_code == 200  # old secret inside the grace period
    clock.advance(61)
    assert idc.get("/v1/nodes", headers=h).status_code == 401
    assert idc.get("/v1/nodes", headers=new).status_code == 200
    assert idc.delete(f"/v1/tokens/{tid}", headers=csrf(idc)).status_code == 204
    assert idc.get("/v1/nodes", headers=new).status_code == 401  # revoked: fails on the next request


def test_token_expiry(idc, clock):
    setup_owner(idc)
    secret = idc.post("/v1/tokens", json={"name": "t", "expires_in_days": 1}, headers=csrf(idc)).json()["one_time"]["token"]
    clock.advance(86400 + 1)
    assert idc.get("/v1/me", headers={"Authorization": f"Bearer {secret}"}).status_code == 401


def test_personal_agent_tokens_default_reader_and_never_approve(idc, clock):
    setup_owner(idc)
    r = idc.post("/v1/tokens", json={"name": "hermes", "principal": {"kind": "agent", "id": "agent:hermes"}},
                 headers=csrf(idc))
    assert r.status_code == 201
    body = r.json()
    assert body["one_time"]["token"].startswith("om_agt_") and "actions:read:own" in body["scopes"]
    assert body["expires_at"] == (clock.now + timedelta(days=90)).isoformat().replace("+00:00", "Z")  # F-15
    h = {"Authorization": "Bearer " + body["one_time"]["token"]}
    assert idc.get("/v1/me", headers=h).json()["principal"] == {"id": "agent:hermes", "kind": "agent", "role": "agent"}
    assert idc.post("/v1/actions", json=action_body(clock), headers=h).status_code == 403  # reader cannot request
    for scope in ("actions:approve", "users:admin", "tokens:admin"):
        r = idc.post("/v1/tokens", json={"name": "x", "principal": {"kind": "agent", "id": "agent:x"},
                                         "scopes": [scope]}, headers=csrf(idc))
        assert r.status_code == 403, scope
    r = idc.post("/v1/tokens", json={"name": "x", "principal": {"kind": "agent", "id": "agent:x"},
                                     "expires_in_days": 91}, headers=csrf(idc))
    assert r.status_code == 422
    requester = idc.post("/v1/tokens", json={"name": "r", "principal": {"kind": "agent", "id": "agent:r"},
                                             "scopes": ["instance:read", "actions:request", "actions:read"]},
                         headers=csrf(idc)).json()["one_time"]["token"]
    rh = {"Authorization": f"Bearer {requester}"}
    aid = idc.post("/v1/actions", json=action_body(clock), headers=rh).json()["id"]
    assert idc.post(f"/v1/actions/{aid}/approve", headers=rh).status_code == 403
    assert idc.post("/v1/tokens", json={"name": "y"}, headers=rh).status_code == 403  # agents never mint


def test_adult_tokens_cannot_exceed_the_adult(idc):
    setup_owner(idc)
    adult = enrol(idc, "adult", "ana")
    r = adult.post("/v1/tokens", json={"name": "x", "scopes": ["users:admin"]}, headers=csrf(adult))
    assert r.status_code == 403
    r = adult.post("/v1/tokens", json={"name": "x", "scopes": ["nodes:read"]}, headers=csrf(adult))
    assert r.status_code == 201
    mine = adult.get("/v1/tokens").json()
    assert [t["name"] for t in mine] == ["x"]  # own tokens only, no file tokens


# ---- passkeys and step-up approvals (F-2) ---------------------------------------------------------
def register_passkey(c: TestClient, auth: SoftAuthenticator) -> dict:
    opts = c.post("/v1/auth/passkeys/register/options", headers=csrf(c)).json()
    assert opts["publicKey"]["authenticatorSelection"]["userVerification"] == "required"
    r = c.post("/v1/auth/passkeys/register", json={"credential": auth.register(opts), "label": "phone"}, headers=csrf(c))
    assert r.status_code == 201, r.text
    return r.json()


def test_passkey_register_and_login(idc, settings):
    setup_owner(idc)
    key = SoftAuthenticator()
    assert register_passkey(idc, key)["label"] == "phone"
    assert idc.get("/v1/auth/passkeys").json()[0]["credential_id"] == b64url(key.cred_id)
    other = new_session_client(idc)
    opts = other.post("/v1/auth/login/options").json()
    r = other.post("/v1/auth/login", json={"passkey": key.assert_(opts["publicKey"]["challenge"])})
    assert r.status_code == 200, r.text
    me = other.get("/v1/me").json()
    assert me["session"]["auth_method"] == "passkey" and me["passkeys"] == 1
    # the same challenge cannot be used twice
    r = new_session_client(idc).post("/v1/auth/login", json={"passkey": key.assert_(opts["publicKey"]["challenge"])})
    assert r.status_code == 401
    wrong_origin = SoftAuthenticator(origin="https://evil.example")
    wrong_origin.key, wrong_origin.cred_id = key.key, key.cred_id
    opts = other.post("/v1/auth/login/options").json()
    assert new_session_client(idc).post(
        "/v1/auth/login", json={"passkey": wrong_origin.assert_(opts["publicKey"]["challenge"])}).status_code == 401


def test_owner_approval_needs_passkey_once_registered(idc, clock, settings):
    setup_owner(idc)
    aid = idc.post("/v1/actions", json=action_body(clock), headers=OWNER).json()["id"]
    key = SoftAuthenticator()
    register_passkey(idc, key)
    # A static owner token and a cookie without an assertion can no longer approve.
    r = idc.post(f"/v1/actions/{aid}/approve", headers=OWNER)
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required"
    assert idc.post(f"/v1/actions/{aid}/approve", headers=csrf(idc)).status_code == 401
    opts = idc.post(f"/v1/actions/{aid}/approve-options", headers=csrf(idc)).json()
    assert opts["action_sha256"].startswith("sha256:")
    assert opts["publicKey"]["allowCredentials"][0]["id"] == b64url(key.cred_id)
    assertion = key.assert_(opts["challenge"], flat=True)
    r = idc.post(f"/v1/actions/{aid}/approve", json={"webauthn": assertion}, headers=csrf(idc))
    assert r.status_code == 200 and r.json()["state"] in ("succeeded", "dispatched", "accepted"), r.text
    events = audit_events(settings)
    assert any(e["event"] == "auth.step_up.succeeded" and e["data"]["payload"]["action_id"] == aid for e in events)
    # Replaying the same signed approval on another action fails.
    aid2 = idc.post("/v1/actions", json=action_body(clock, app_id="whoami", key="k2"), headers=OWNER).json()["id"]
    r = idc.post(f"/v1/actions/{aid2}/approve", json={"webauthn": assertion}, headers=csrf(idc))
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required"
    # A challenge for one action cannot approve another.
    opts1 = idc.post(f"/v1/actions/{aid2}/approve-options", headers=csrf(idc)).json()
    aid3 = idc.post("/v1/actions", json=action_body(clock, app_id="hermes-like", key="k3"), headers=OWNER).json()["id"]
    r = idc.post(f"/v1/actions/{aid3}/approve", json={"webauthn": key.assert_(opts1["challenge"])}, headers=csrf(idc))
    assert r.status_code == 401
    assert idc.get(f"/v1/actions/{aid3}").json()["state"] == "awaiting_approval"
    # The static owner token may approve with the owner's passkey assertion (break-glass + passkey).
    opts3 = idc.post(f"/v1/actions/{aid2}/approve-options", headers=OWNER).json()
    r = idc.post(f"/v1/actions/{aid2}/approve", json={"webauthn": key.assert_(opts3["challenge"])}, headers=OWNER)
    assert r.status_code == 200, r.text


def test_approval_challenge_expires(idc, clock):
    setup_owner(idc)
    key = SoftAuthenticator()
    register_passkey(idc, key)
    aid = idc.post("/v1/actions", json=action_body(clock), headers=OWNER).json()["id"]
    opts = idc.post(f"/v1/actions/{aid}/approve-options", headers=csrf(idc)).json()
    clock.advance(121)
    r = idc.post(f"/v1/actions/{aid}/approve", json={"webauthn": key.assert_(opts["challenge"])}, headers=csrf(idc))
    assert r.status_code == 401


def test_step_up_for_user_admin_and_last_passkey(idc, clock):
    setup_owner(idc)
    key = SoftAuthenticator()
    register_passkey(idc, key)  # registering counts as a fresh passkey proof on this session
    assert idc.post("/v1/users", json={"display_name": "A", "role": "adult"}, headers=csrf(idc)).status_code == 201
    clock.advance(301)
    r = idc.post("/v1/users", json={"display_name": "B", "role": "adult"}, headers=csrf(idc))
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required"
    # A password session cannot register a second passkey or remove one without a fresh passkey.
    assert idc.post("/v1/auth/passkeys/register/options", headers=csrf(idc)).status_code == 401
    pw = new_session_client(idc)
    pw.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD})
    assert pw.delete(f"/v1/auth/passkeys/{b64url(key.cred_id)}", headers=csrf(pw)).status_code == 401
    pkc = new_session_client(idc)
    opts = pkc.post("/v1/auth/login/options").json()
    pkc.post("/v1/auth/login", json={"passkey": key.assert_(opts["publicKey"]["challenge"])})
    r = pkc.delete(f"/v1/auth/passkeys/{b64url(key.cred_id)}", headers=csrf(pkc))
    assert r.status_code == 409 and r.json()["reason"] == "last_owner"


def test_passkey_off_switch_keeps_token_approvals(settings, clock, executor):
    s = id_settings(settings, require_passkey_approval=False)
    with TestClient(create_app(s, clock=clock, executor=executor)) as c:
        setup_owner(c)
        register_passkey(c, SoftAuthenticator())
        aid = c.post("/v1/actions", json=action_body(clock), headers=OWNER).json()["id"]
        assert c.post(f"/v1/actions/{aid}/approve", headers=OWNER).status_code == 200


# ---- misc -----------------------------------------------------------------------------------------
def test_password_change_revokes_other_sessions(idc):
    setup_owner(idc)
    other = new_session_client(idc)
    other.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD})
    r = idc.post("/v1/auth/password", json={"current_password": PASSWORD, "new_password": "another long one"},
                 headers=csrf(idc))
    assert r.status_code == 204
    assert other.get("/v1/me").status_code == 401 and idc.get("/v1/me").status_code == 200


def test_secrets_never_reach_the_audit(idc, settings):
    setup_owner(idc)
    tok = idc.post("/v1/tokens", json={"name": "t"}, headers=csrf(idc)).json()["one_time"]["token"]
    text = Path(settings.audit_path).read_text()
    assert PASSWORD not in text and tok not in text and idc.cookies.get("onemind_session") not in text


def test_signin_page_is_served_with_a_strict_csp(idc):
    r = idc.get("/signin")
    assert r.status_code == 200 and "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert "/v1/auth/passkeys/register/options" in r.text


def test_only_identity_reads_cookies():
    """H-16: no cookie auth without CSRF defence. Only the identity module reads cookies."""
    root = Path(__file__).resolve().parent.parent / "onemind_core"
    readers = sorted(str(p.relative_to(root)) for p in root.rglob("*.py") if "request.cookies" in p.read_text())
    assert readers == ["identity/service.py"]


def test_openapi_lists_identity_routes(idc):
    paths = idc.get("/openapi.json").json()["paths"]
    for p in ("/v1/me", "/v1/auth/login", "/v1/auth/login/options", "/v1/auth/passkeys/register/options",
              "/v1/auth/sessions", "/v1/users", "/v1/tokens", "/v1/tokens/{token_id}/rotate",
              "/v1/apps/{app_id}/access", "/v1/actions/{action_id}/approve-options"):
        assert p in paths, p
    assert "/signin" not in paths


def test_unb64url_roundtrip():
    assert unb64url(b64url(b"\x00\xffabc")) == b"\x00\xffabc"


# ---- review fixes ---------------------------------------------------------------------------------
def test_api_tokens_cannot_change_sign_in_credentials(idc):
    setup_owner(idc)
    reader = idc.post("/v1/tokens", json={"name": "r", "scopes": ["reader"]}, headers=csrf(idc)).json()["one_time"]["token"]
    h = {"Authorization": f"Bearer {reader}"}
    for path, body in (("/v1/auth/passkeys/register/options", None), ("/v1/auth/totp/setup", None),
                       ("/v1/auth/password", {"current_password": PASSWORD, "new_password": "x" * 12}),
                       ("/v1/auth/totp/disable", {"password": PASSWORD})):
        r = idc.post(path, json=body, headers=h)
        assert r.status_code == 403, (path, r.text)
    assert idc.get("/v1/auth/passkeys", headers=h).status_code == 200  # reading own list is fine
    # A narrowed owner PAT sees and revokes only its own person's sessions, not everyone's.
    adult = enrol(idc, "adult", "ana")
    adult_sid = adult.get("/v1/me").json()["session"]["id"]
    assert all(s["principal_id"] != adult.get("/v1/me").json()["principal"]["id"]
               for s in idc.get("/v1/auth/sessions", headers=h).json())
    assert idc.delete(f"/v1/auth/sessions/{adult_sid}", headers=h).status_code == 404
    assert adult.get("/v1/me").status_code == 200
    assert idc.delete(f"/v1/auth/sessions/{adult_sid}", headers=csrf(idc)).status_code == 204  # full session


def test_personal_agent_ids_cannot_impersonate(idc):
    setup_owner(idc)
    adult = enrol(idc, "adult", "ana")
    for agent_id in ("agent:uptime-kuma",):  # an app's §11.2 agent principal
        r = adult.post("/v1/tokens", json={"name": "x", "principal": {"kind": "agent", "id": agent_id}},
                       headers=csrf(adult))
        assert r.status_code == 409 and r.json()["reason"] == "agent_id_taken"
    assert idc.post("/v1/tokens", json={"name": "a", "principal": {"kind": "agent", "id": "agent:mine"}},
                    headers=csrf(idc)).status_code == 201
    r = adult.post("/v1/tokens", json={"name": "b", "principal": {"kind": "agent", "id": "agent:mine"}},
                   headers=csrf(adult))
    assert r.status_code == 409  # another person's agent
    assert idc.post("/v1/tokens", json={"name": "c", "principal": {"kind": "agent", "id": "agent:mine"}},
                    headers=csrf(idc)).status_code == 201  # the same person may hold several


def test_owner_cannot_rotate_another_persons_token(idc):
    setup_owner(idc)
    adult = enrol(idc, "adult", "ana")
    tid = adult.post("/v1/tokens", json={"name": "x", "scopes": ["nodes:read"]}, headers=csrf(adult)).json()["id"]
    assert idc.post(f"/v1/tokens/{tid}/rotate", json={}, headers=csrf(idc)).status_code == 403
    assert adult.post(f"/v1/tokens/{tid}/rotate", json={}, headers=csrf(adult)).status_code == 201
    assert idc.delete(f"/v1/tokens/{tid}", headers=csrf(idc)).status_code == 204  # revoking is removing power


def test_a_token_never_mints_a_longer_lived_token(idc, clock):
    setup_owner(idc)
    short = idc.post("/v1/tokens", json={"name": "s", "expires_in_days": 1}, headers=csrf(idc)).json()
    h = {"Authorization": "Bearer " + short["one_time"]["token"]}
    r = idc.post("/v1/tokens", json={"name": "long", "expires_in_days": 365}, headers=h)
    assert r.status_code == 201 and r.json()["expires_at"] == short["expires_at"]


def test_approval_is_bound_to_the_plan_hash(idc, clock):
    setup_owner(idc)
    key = SoftAuthenticator()
    register_passkey(idc, key)
    aid = idc.post("/v1/actions", json=action_body(clock), headers=OWNER).json()["id"]
    opts = idc.post(f"/v1/actions/{aid}/approve-options", headers=csrf(idc)).json()
    r = idc.post(f"/v1/actions/{aid}/approve", headers=csrf(idc),
                 json={"webauthn": key.assert_(opts["challenge"]), "plan_sha256": "sha256:" + "0" * 64})
    assert r.status_code == 409 and r.json()["reason"] == "plan_changed"
    assert idc.get(f"/v1/actions/{aid}").json()["state"] == "awaiting_approval"


def test_open_login_challenges_are_capped(idc, monkeypatch):
    from onemind_core.identity import service

    monkeypatch.setattr(service, "MAX_OPEN_LOGIN_CHALLENGES", 3)
    for _ in range(3):
        assert idc.post("/v1/auth/login/options").status_code == 200
    r = idc.post("/v1/auth/login/options")
    assert r.status_code == 429 and r.json()["error"] == "rate_limited"
