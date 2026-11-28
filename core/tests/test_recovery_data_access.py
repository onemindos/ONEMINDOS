# SPDX-License-Identifier: Apache-2.0
"""Design 25b (gateway permissions design 3.13, D-028): data access never needs a strong key.

1. A restore into a NEW folder of the requester's Files is its own type, `backup.restore.copy`, with risk `write`
   (T1): nothing is overwritten and no app stops. So the everyday approval (L1: a passkey, or the phone's approver
   key) is enough; the in-place restore stays `destructive`.
2. A route pin: with passkeys active on the box, a PASSWORD session (no passkey step-up) reads, lists, downloads and
   exports every file, photo, sync and backup route, and asks for a restore copy, without ever being sent to a
   step-up. A future change that puts a strong key in front of the owner's data fails here.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from onemind_core.app import create_app
from onemind_core.databases import DatabasesSettings, SharedPostgres
from onemind_core.files.settings import FilesSettings

from conftest import AGENT, OWNER
from test_backups import FakeAgent, FakeKube, approve, bk, notes_app, restorable  # noqa: F401  (fixtures and helpers)
from test_identity import PASSWORD, SoftAuthenticator, csrf, id_settings, register_passkey, setup_owner


@pytest.fixture
def settings(settings, tmp_path):  # every test here has a Files root
    files = FilesSettings(root=tmp_path / "files", min_free_bytes=0)
    return replace(settings, sections={**settings.sections, "files": files})


def copy_agent(bk):
    """The fake agent also answers a restore copy: it writes one file into the folder the gateway made."""
    plain = bk.agent.job

    def job(kind, params, **kw):
        if kind == "backup.restore" and params.get("scope") == "copy":
            bk.agent.jobs.append((kind, params, kw.get("action_id")))
            from pathlib import Path

            Path(params["dest"], "notes.txt").write_text("v1")
            return {"dest": params["dest"], "files": 1, "skipped": 0}
        return plain(kind, params, **kw)

    bk.agent.job = job


def test_restore_into_a_new_folder_is_a_write_that_changes_nothing(client, bk, settings):
    copy_agent(bk)
    snap = restorable(client, bk)
    body = {"snapshot_id": snap["id"], "scope": {"app_id": "notes", "path": snap["paths"][0] + "/notes.txt"},
            "target": "new_folder"}
    assert client.post("/v1/restores", headers=AGENT, json=body).status_code == 403
    r = client.post("/v1/restores", headers=OWNER, json=body)
    assert r.status_code == 202, r.text
    action = r.json()
    assert action["type"] == "backup.restore.copy" and action["risk"] == "write"
    assert r.json()["restore"]["plan"]["downtime"] == "none" and r.json()["restore"]["target"] == "new_folder"
    jobs = len(bk.agent.jobs)
    done = approve(client, action["id"])
    assert done["state"] == "succeeded", done
    kinds = [k for k, _, _ in bk.agent.jobs[jobs:]]
    assert kinds == ["backup.restore"], "a copy takes no pre-restore snapshot and stops nothing"
    params = bk.agent.jobs[-1][1]
    assert params["scope"] == "copy" and params["path"].endswith("/notes.txt")
    dest = params["dest"]
    assert dest.startswith(str(settings.sections["files"].root / "home")) and "/Restored from backup/notes-" in dest
    assert not [c for c in bk.kube.calls if c[0] == "scale"], "the app keeps running"
    # the copy is in the owner's own Files
    listing = client.get("/v1/files/list", headers=OWNER, params={"root": "home:owner", "path": "/Restored from backup"})
    assert listing.status_code == 200, listing.text
    assert [e["name"] for e in listing.json()] == [dest.rsplit("/", 1)[1]]
    assert client.get("/v1/restores", headers=OWNER).json()[0]["state"] == "succeeded"
    # a second copy never lands in the first one's folder
    again = client.post("/v1/restores", headers={**OWNER, "Idempotency-Key": "second-copy"}, json=body)
    assert again.status_code == 202 and approve(client, again.json()["id"])["state"] == "succeeded"
    assert bk.agent.jobs[-1][1]["dest"] == dest + "-2"


def test_a_copy_works_when_the_app_is_gone(client, bk, clock):
    copy_agent(bk)
    snap = restorable(client, bk)
    bk.gw.repo.set_app_state("notes", "removed", clock.now)
    body = {"snapshot_id": snap["id"], "scope": {"app_id": "notes"}, "target": "new_folder"}
    assert client.post("/v1/restores", headers=OWNER, json={**body, "target": "in_place"}).status_code == 409
    r = client.post("/v1/restores", headers=OWNER, json=body)
    assert r.status_code == 202, r.text
    assert approve(client, r.json()["id"])["state"] == "succeeded"
    assert "path" not in bk.agent.jobs[-1][1], "the whole app: every saved folder"


def test_the_phone_key_may_approve_a_copy_but_not_an_in_place_restore(client, bk):
    identity = client.app.state.identity if hasattr(client.app.state, "identity") else None
    if identity is None:
        pytest.skip("identity is off in this gateway")
    assert identity._device_key_refusal({"type": "backup.restore.copy", "risk": "write"}) is None
    assert identity._device_key_refusal({"type": "backup.restore", "risk": "destructive"}) is not None


# ---- the pin: a password session reaches every data route -------------------------------------------------
DATA = re.compile(r"^/v1/(files|backups|restores|photos|sync|search|share)(/|$)")
# Routes that take their own credential, not a person's session: the office editor's WOPI access token.
OWN_CREDENTIAL = re.compile(r"^/v1/files/wopi/")


def test_a_password_session_reaches_every_data_route_without_a_step_up(settings, clock, executor):
    app = create_app(id_settings(settings), clock=clock, executor=executor)
    with TestClient(app) as c:
        setup_owner(c)
        register_passkey(c, SoftAuthenticator())  # passkeys are active: a strong key exists on the box
        pw = TestClient(app)
        r = pw.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD})
        assert r.status_code == 200, r.text
        assert pw.get("/v1/me").json()["session"]["auth_method"] == "password"
        probed = []
        for route in app.routes:
            path, methods = getattr(route, "path", ""), getattr(route, "methods", set()) or set()
            if "GET" not in methods or not DATA.match(path) or OWN_CREDENTIAL.match(path):
                continue
            url = re.sub(r"\{[^}]+\}", "x0123456789abcdef", path)
            res = pw.get(url)
            probed.append(path)
            assert res.status_code != 401, f"GET {path}: a password session must reach the owner's data ({res.text[:200]})"
        assert len(probed) >= 20 and "/v1/files/list" in probed and "/v1/backups/snapshots/{snapshot_id}/file" in probed
        r = pw.post("/v1/restores", headers=csrf(pw), json={"snapshot_id": "abcdef0123456789", "scope": {"app_id": "notes"},
                                                            "target": "new_folder"})
        assert r.status_code != 401, r.text


def wire_backups(app, clock):
    """The `bk` fixture's fakes (agent, kube, shared PostgreSQL), on an identity gateway made inside the test."""
    svc = app.state.backups
    svc.agent = FakeAgent(clock)
    svc.kube = FakeKube()
    svc.pg = SharedPostgres(svc.kube, DatabasesSettings(), dry_run=False)
    svc.worker.inline = True
    svc.s = replace(svc.s, health_deadline_s=1)
    app.state.gateway.repo.set_app_state("notes", "installed", clock.now)
    return svc


def test_an_owner_without_a_passkey_requests_and_approves_a_copy_but_not_an_in_place_restore(
        settings, clock, executor, notes_app):
    """Review of #1193: the data-first rule holds at APPROVAL, not only at the request. With a passkey registered
    (require_passkey_approval on, the default), an owner signed in with a password (L1) asks for a restore copy,
    approves it without a step-up, and the copy lands in their Files. What still needs the passkey: an in-place
    restore, a copy approved by anyone but the requester's own signed-in session (the static owner token, or the
    requester's own personal token as the CLI uses), and a copy someone else asked for."""
    app = create_app(id_settings(settings), clock=clock, executor=executor)
    with TestClient(app) as c:
        setup_owner(c)
        bk = wire_backups(app, clock)
        copy_agent(bk)
        snap = restorable(c, bk)  # before the passkey: the static owner token approves the USB disk and the run
        register_passkey(c, SoftAuthenticator())  # now a strong key exists on the box
        pw = TestClient(app)
        assert pw.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD}).status_code == 200
        me = pw.get("/v1/me").json()
        assert me["session"]["auth_method"] == "password"
        user_id = me["principal"]["id"]
        gw = app.state.gateway
        assert gw.actions.is_data_access("backup.restore.copy") and not gw.actions.is_data_access("backup.restore")
        body = {"snapshot_id": snap["id"], "scope": {"app_id": "notes"}, "target": "new_folder"}

        def ask(client, headers, key, **change):
            r = client.post("/v1/restores", headers={**headers, "Idempotency-Key": key}, json={**body, **change})
            assert r.status_code == 202, r.text
            return r.json()

        def approve_as(client, headers, action_id):
            return client.post(f"/v1/actions/{action_id}/approve", headers=headers, json={})

        copy = ask(pw, csrf(pw), "own-copy")
        assert copy["type"] == "backup.restore.copy" and copy["requested_by"]["id"] == user_id
        # the static owner token is another principal ("owner"), not the person who asked: passkey, as ever
        by_token = approve_as(c, OWNER, copy["id"])
        assert by_token.status_code == 401 and by_token.json()["reason"] == "step_up_required", by_token.text
        # review of #1319: a personal token (the CLI's credential, or a script's) of the SAME person who asks is still
        # a token, not their signed-in session: it requests a copy, but approving it with that token needs the passkey
        minted = pw.post("/v1/tokens", json={"name": "cli"}, headers=csrf(pw))
        assert minted.status_code in (200, 201), minted.text
        cli = {"Authorization": f"Bearer {minted.json()['one_time']['token']}"}
        assert c.get("/v1/me", headers=cli).json()["principal"]["id"] == user_id
        by_cli = ask(c, cli, "cli-copy")
        assert by_cli["type"] == "backup.restore.copy" and by_cli["requested_by"]["id"] == user_id
        r = approve_as(c, cli, by_cli["id"])
        assert r.status_code == 401 and r.json()["reason"] == "step_up_required", r.text
        assert gw.actions.get(by_cli["id"])["state"] == "awaiting_approval"
        jobs = len(bk.agent.jobs)
        done = approve_as(pw, csrf(pw), copy["id"])
        assert done.status_code == 200, done.text
        assert done.json()["state"] == "succeeded", done.text
        events = [json.loads(line) for line in settings.audit_path.read_text().splitlines() if line.strip()]
        shown = [e["data"]["payload"] for e in events if e["event"] == "auth.approval.token"
                 and e["data"]["payload"]["action_id"] == copy["id"]]
        assert shown == [{"action_id": copy["id"], "via": "password", "own_data_access": True}], shown  # F-12: no passkey
        [(kind, params, _)] = bk.agent.jobs[jobs:]
        assert kind == "backup.restore" and params["scope"] == "copy"
        assert params["dest"].startswith(str(settings.sections["files"].root / "home"))
        assert "/Restored from backup/notes-" in params["dest"]
        listing = pw.get("/v1/files/list", params={"root": f"home:{user_id}", "path": "/Restored from backup"})
        assert listing.status_code == 200, listing.text
        assert [e["name"] for e in listing.json()] == [params["dest"].rsplit("/", 1)[1]]
        # an in-place restore overwrites the app's data: the password session is sent to the passkey
        inplace = ask(pw, csrf(pw), "in-place", target="in_place")
        assert inplace["type"] == "backup.restore"
        r = approve_as(pw, csrf(pw), inplace["id"])
        assert r.status_code == 401 and r.json()["reason"] == "step_up_required", r.text
        # a copy another principal asked for is not the approver's own data: passkey
        theirs = ask(c, OWNER, "token-copy")
        assert theirs["type"] == "backup.restore.copy" and theirs["requested_by"]["id"] != user_id
        r = approve_as(pw, csrf(pw), theirs["id"])
        assert r.status_code == 401 and r.json()["reason"] == "step_up_required", r.text
        assert gw.actions.get(theirs["id"])["state"] == "awaiting_approval"
