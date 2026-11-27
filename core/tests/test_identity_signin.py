# SPDX-License-Identifier: Apache-2.0
"""D-034 appliance sign-in, first run and recovery through the mounted gateway."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from onemind_core.app import create_app
from onemind_core.ca import MESH_NETS
from onemind_core.identity.crypto import totp_code
from test_identity import (
    LOCAL_PEER, PASSWORD, SoftAuthenticator, audit_events, box_code, confirm_setup_kit,
    csrf, id_settings, new_session_client, register_passkey,
)
from test_identity_levels import AttestedAuthenticator, lvc, root  # noqa: F401 - pytest fixtures

NEW_PASSWORD = "A new password chosen at the box"
CONTACT = "@".join(("owner", "example.test"))
LOGIN = {"username": "owner", "password": PASSWORD}
SETUP = {**LOGIN, "display_name": "Home owner"}


@pytest.fixture
def box(settings, clock, executor, tmp_path):
    disk_key = tmp_path / "disk-recovery"
    disk_key.write_text("a disk key in the simulated RAM filesystem\n")
    app = create_app(id_settings(settings, recovery_key_file=disk_key), clock=clock, executor=executor)
    with TestClient(app, client=LOCAL_PEER) as client:
        yield client, disk_key


def screen_signup(client, **body):
    options = client.post("/v1/auth/setup/options")
    assert options.status_code == 200, options.text
    assert set(options.json()) == {"challenge_id", "expires_at"}
    code = box_code(client)
    assert len(code) == 6 and code.isdigit()
    response = client.post("/v1/auth/setup", json={
        **SETUP, "challenge_id": options.json()["challenge_id"], "box_code": code, **body,
    })
    assert response.status_code == 201, response.text
    return response


def completed_setup(client, **body):
    screen_signup(client, **body)
    return confirm_setup_kit(client, csrf(client))


def enable_totp(client, clock):
    pending = client.post("/v1/auth/totp/setup", headers=csrf(client))
    assert pending.status_code == 200, pending.text
    assert pending.headers["cache-control"] == "no-store"
    secret = pending.json()["one_time"]["secret"]
    assert client.post("/v1/auth/totp/confirm", headers=csrf(client),
                       json={"code": totp_code(secret, int(clock.now.timestamp()) // 30)}).status_code == 204
    clock.advance(30)
    return secret


def test_first_owner_needs_screen_proof_and_explicitly_saved_recovery_kit(box, settings):
    client, disk_key = box
    assert client.get("/v1/auth/setup/status").json() == {"state": "unclaimed", "screen": True}
    assert client.post("/v1/auth/setup", json=SETUP).status_code == 401

    options = client.post("/v1/auth/setup/options").json()
    correct = box_code(client)
    wrong = "000000" if correct != "000000" else "111111"
    body = {**SETUP, "challenge_id": options["challenge_id"], "box_code": wrong}
    assert client.post("/v1/auth/setup", json=body).json()["reason"] == "box_code_required"
    assert client.post("/v1/auth/setup", json={**body, "box_code": correct}).status_code == 401

    options = client.post("/v1/auth/setup/options").json()
    proof = {"challenge_id": options["challenge_id"], "box_code": box_code(client)}
    for weak in ("elevenchars", "passwordpassword"):
        response = client.post("/v1/auth/setup", json={**SETUP, **proof, "password": weak})
        assert response.status_code == 422 and response.json()["reason"] == "weak_password"
    result = client.post("/v1/auth/setup", json={**SETUP, **proof})
    assert result.status_code == 201, result.text
    assert client.get("/v1/auth/setup/status").json()["state"] == "pending"
    assert client.get("/v1/me").json()["setup_pending"] is True
    assert client.get("/v1/users").json()["reason"] == "recovery_kit_required"
    assert client.post("/v1/tokens", headers=csrf(client), json={"name": "before kit"}).status_code == 403
    finish = {"saved": True, "method": "download", "recovery_code": "invented"}
    refused = client.post("/v1/auth/setup/finish", headers=csrf(client), json=finish)
    assert refused.status_code == 422 and refused.json()["reason"] == "recovery_kit_required"

    kit = client.post("/v1/auth/setup/kit", headers=csrf(client))
    assert kit.status_code == 200 and kit.headers["cache-control"] == "no-store"
    assert kit.json()["disk_recovery_key"] == disk_key.read_text().strip()
    finish["recovery_code"] = kit.json()["recovery_code"]
    assert client.post("/v1/auth/setup/finish", headers=csrf(client), json={**finish, "saved": False}).status_code == 422
    assert client.post("/v1/auth/setup/finish", headers=csrf(client), json=finish).status_code == 204
    assert disk_key.read_text() == ""
    assert client.get("/v1/auth/setup/status").json()["state"] == "ready"
    assert client.get("/v1/users").status_code == 200
    assert client.post("/v1/auth/setup/kit", headers=csrf(client)).status_code == 409
    assert PASSWORD not in str(audit_events(settings)) and finish["recovery_code"] not in str(audit_events(settings))


def test_password_only_stays_home_even_when_reusing_an_existing_session(box):
    client, _ = box
    completed_setup(client)
    local = new_session_client(client)
    result = local.post("/v1/auth/login", json={**LOGIN, "client": "cli"})
    assert result.status_code == 200, result.text
    session = result.json()
    bearer = {"Authorization": f"Bearer {session['access_token']}", "X-OneMind-Path": "lan"}
    for peer in (str(MESH_NETS[0].network_address + 1), "8.8.8.8", "127.0.0.1", "unknown"):
        remote = TestClient(client.app, client=(peer, 50000))
        assert remote.post("/v1/auth/login", json={**LOGIN}, headers=bearer).json()["reason"] == "remote_factor_required"
        assert remote.get("/v1/me", headers=bearer).status_code == 401
        assert remote.post("/v1/auth/refresh", json={"refresh_token": session["refresh_token"]}).status_code == 401
        assert remote.post("/v1/auth/setup/options", headers=bearer).status_code == 403
        assert remote.post("/v1/auth/recovery/options", json={"username": "owner"}, headers=bearer).status_code == 403


def test_first_totp_login_from_mesh_consumes_the_code_once_even_with_concurrent_requests(box, clock):
    client, _ = box
    completed_setup(client)
    secret = enable_totp(client, clock)
    peer = (str(MESH_NETS[0].network_address + 1), 50000)
    body = {**LOGIN, "totp": totp_code(secret, int(clock.now.timestamp()) // 30), "client": "cli"}

    def login():
        return TestClient(client.app, client=peer).post("/v1/auth/login", json=body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: login(), range(2)))
    assert sorted(r.status_code for r in results) == [200, 401]
    assert next(r for r in results if r.status_code == 401).json()["reason"] == "totp_invalid"
    assert login().json()["reason"] == "totp_invalid"


def test_family_invites_are_one_time_and_expire_in_24_hours(box, clock):
    client, _ = box
    completed_setup(client)
    invite = {"display_name": "Family member", "role": "adult"}
    denied = client.post("/v1/users/invites", headers=csrf(client), json=invite)
    assert denied.status_code == 401 and denied.json()["reason"] == "step_up_required"
    register_passkey(client, SoftAuthenticator())
    assert client.post("/v1/users/invites", headers=csrf(client), json={**invite, "role": "owner"}).status_code == 422
    expiry = (clock.now + timedelta(hours=24)).isoformat().replace("+00:00", "Z")
    invites = [client.post("/v1/users/invites", headers=csrf(client), json=invite) for _ in range(2)]
    assert all(response.status_code == 201 for response in invites), [r.text for r in invites]
    a, b = (r.json()["one_time"] for r in invites)
    assert a["expires_at"] == b["expires_at"] == expiry and a["enrolment_url"].endswith("/#enrol=" + a["enrolment_code"])
    guest = new_session_client(client)
    data = {"username": "family", "password": "their own family password", "code": a["enrolment_code"]}
    assert guest.post("/v1/auth/enrol", json=data).status_code == 201
    assert guest.post("/v1/auth/enrol", json=data).status_code == 401
    clock.advance(24 * 3600)
    assert guest.post("/v1/auth/enrol", json={**data, "code": b["enrolment_code"]}).status_code == 401


def test_forgot_password_needs_screen_and_kit_updates_only_the_account(box, tmp_path, clock):
    client, _ = box
    kit = completed_setup(client, email=CONTACT)
    assert client.get("/v1/me").json()["email_verified"] is False
    assert client.post("/v1/auth/email/options", headers=csrf(client)).json()["reason"] == "smtp_unavailable"
    old = new_session_client(client)
    assert old.post("/v1/auth/login", json=LOGIN).status_code == 200
    content = tmp_path / "kept-data"
    content.write_text("owner's file")
    enable_totp(client, clock)
    opts = old.post("/v1/auth/recovery/options", json={"username": "owner"}).json()
    payload = {"challenge_id": opts["challenge_id"], "box_code": box_code(old), "new_password": NEW_PASSWORD}
    assert old.post("/v1/auth/recovery/reset", json={**payload, "recovery_code": CONTACT}).status_code == 401

    def reset(code):
        opts = old.post("/v1/auth/recovery/options", json={"username": "owner"}).json()
        return old.post("/v1/auth/recovery/reset", json={**payload, "challenge_id": opts["challenge_id"],
                                                        "box_code": box_code(old), "recovery_code": code})

    result = reset(kit["recovery_code"])
    assert result.status_code == 200, result.text
    assert result.json()["recovery_code"] != kit["recovery_code"]
    assert client.get("/v1/me").status_code == old.get("/v1/me").status_code == 401
    assert old.post("/v1/auth/login", json=LOGIN).status_code == 401
    assert old.post("/v1/auth/login", json={**LOGIN, "password": NEW_PASSWORD}).status_code == 200
    assert old.get("/v1/me").json()["email"] == CONTACT
    assert reset(kit["recovery_code"]).status_code == 401
    assert content.read_text() == "owner's file"


def test_remote_recovery_waits_72_hours_and_adds_only_a_proven_key(lvc, root, clock):
    kit = completed_setup(lvc)
    secret = enable_totp(lvc, clock)
    remote = TestClient(lvc.app, client=(str(MESH_NETS[0].network_address + 1), 50000))

    def sign_in():
        body = {**LOGIN, "totp": totp_code(secret, int(clock.now.timestamp()) // 30)}
        assert remote.post("/v1/auth/login", json=body).status_code == 200

    sign_in()
    path = "/v1/auth/recovery/remote"
    opts_path = "/v1/auth/passkeys/register/options?remote_recovery=true"
    assert remote.post(path, headers=csrf(remote), json={"recovery_code": CONTACT}).status_code == 401
    started = remote.post(path, headers=csrf(remote), json={"recovery_code": kit["recovery_code"]})
    assert started.status_code == 200 and started.json()["state"] == "waiting", started.text
    assert any(n["topic"] == "security" and "Remote approval recovery" in n["title"]
               for n in remote.get("/v1/notifications").json())
    clock.advance(72 * 3600 - 1)
    sign_in()
    assert remote.post(opts_path, headers=csrf(remote)).json()["reason"] == "remote_recovery_wait"
    clock.advance(1)
    assert remote.get(path).json()["state"] == "ready"
    opts = remote.post(opts_path, headers=csrf(remote))
    assert opts.status_code == 200, opts.text
    reg = "/v1/auth/passkeys/register"
    assert remote.post(reg, headers=csrf(remote), json={"credential": SoftAuthenticator().register(opts.json())}).json()[
        "reason"] == "remote_recovery_proven_key_required"
    opts = remote.post(opts_path, headers=csrf(remote))
    proven = AttestedAuthenticator(root)
    enrolled = remote.post(reg, headers=csrf(remote), json={"credential": proven.register(opts.json())})
    assert enrolled.status_code == 201 and enrolled.json()["level"] == "L2", enrolled.text
    assert remote.get(path).json()["state"] == "none"
    assert remote.get("/v1/me").json()["totp"] is True


def test_email_verification_uses_the_owner_smtp_destination_and_never_authenticates(box, clock, settings, monkeypatch):
    import json

    from onemind_core.notify.store import ChannelRow
    from onemind_core.identity import email as email_service

    client, _ = box
    completed_setup(client)
    profile = client.patch("/v1/me", headers=csrf(client), json={"email": CONTACT})
    assert profile.status_code == 200 and profile.json()["email_verified"] is False
    me = client.get("/v1/me").json()
    notify = client.app.state.notify
    sent = []

    def capture(kind, config, secret, level, message, **kwargs):
        sent.append((kind, config, message))

    monkeypatch.setattr(email_service, "send_channel", capture)
    config = {"host": "smtp.example.test", "port": 587, "security": "starttls", "to": CONTACT,
              "from": "@".join(("box", "example.test"))}
    notify.repo.add_channel(ChannelRow(id="chn_owner_smtp", person_id=me["principal"]["id"], kind="email",
                                       label="Owner SMTP", config_json=json.dumps(config), content_level="title",
                                       verified=True, state="ok", created_at=clock.now, updated_at=clock.now))

    def send():
        result = client.post("/v1/auth/email/options", headers=csrf(client))
        assert result.status_code == 200, result.text
        kind, actual, message = sent[-1]
        assert kind == "email" and actual == config
        code = message.body.partition("code is ")[2].partition(".")[0]
        return {"challenge_id": result.json()["challenge_id"], "code": code}

    proof = send()
    other = new_session_client(client)
    assert other.post("/v1/auth/login", json=LOGIN).status_code == 200
    assert other.post("/v1/auth/email/verify", json=proof, headers=csrf(other)).status_code == 401
    assert client.post("/v1/auth/email/verify", json=proof, headers=csrf(client)).status_code == 204
    assert client.post("/v1/auth/email/verify", json=proof, headers=csrf(client)).status_code == 401
    assert client.get("/v1/me").json()["email_verified"] is True
    for event in audit_events(settings):
        assert CONTACT not in str(event)
    assert other.post("/v1/auth/login", json={**LOGIN, "password": proof["code"]}).status_code == 401
