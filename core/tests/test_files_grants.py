# SPDX-License-Identifier: Apache-2.0
"""FILES: folder grants to agents and apps exist only after an owner approval."""

from __future__ import annotations

from datetime import timedelta

from onemind_core.files.service import FilesService

from files_support import ADULT, AGENT, GUEST, OWNER, audit_events, fc, files_root, files_settings, mkdir, ok, upload  # noqa: F401


def grant_body(**kw):
    body = {"subject": {"kind": "agent", "id": "hermes"}, "root": "shared", "path": "/Media", "access": "r"}
    body.update(kw)
    return body


def test_agent_reads_only_through_an_approved_grant(fc, settings):
    mkdir(fc, OWNER, "shared", "/Media")
    ok(upload(fc, OWNER, "shared", "/Media", "song.txt", b"la la"), 204)
    mkdir(fc, OWNER, "shared", "/Private")
    assert fc.get("/v1/files/list", params={"root": "shared", "path": "/Media"}, headers=AGENT).status_code == 403

    r = fc.post("/v1/files/grants", headers=AGENT, json=grant_body(reason="index my music"))
    assert r.status_code == 202
    req = r.json()
    assert req["state"] == "awaiting_approval" and req["risk"] == "sensitive"
    assert req["plan"]["summary"] == "agent hermes gets read-only access to shared:/Media"
    assert fc.post(f"/v1/files/requests/{req['id']}/approve", headers=AGENT).status_code == 403  # never self-approve
    assert fc.post(f"/v1/files/requests/{req['id']}/approve", headers=ADULT).status_code == 403
    assert fc.get("/v1/files/list", params={"root": "shared", "path": "/Media"}, headers=AGENT).status_code == 403

    done = ok(fc.post(f"/v1/files/requests/{req['id']}/approve", headers=OWNER))
    assert done["state"] == "succeeded" and done["approved_by"] == "owner" and done["approval"] == "token"
    roots = ok(fc.get("/v1/files/roots", headers=AGENT))
    assert [(r["root"], r["path"], r["access"]) for r in roots] == [("shared", "/Media", "r")]
    assert [i["name"] for i in ok(fc.get("/v1/files/list", params={"root": "shared", "path": "/Media"}, headers=AGENT))] == ["song.txt"]
    assert fc.get("/v1/files/download", params={"root": "shared", "path": "/Media/song.txt"}, headers=AGENT).content == b"la la"
    assert fc.get("/v1/files/list", params={"root": "shared", "path": "/"}, headers=AGENT).status_code == 403
    assert fc.get("/v1/files/list", params={"root": "shared", "path": "/Private"}, headers=AGENT).status_code == 403
    r = fc.post("/v1/files/ops", headers=AGENT, json={"op": "mkdir", "root": "shared", "path": "/Media/new"})
    assert r.status_code == 403  # read-only grant

    reads = [e for e in audit_events(settings) if e["event"] == "files.read"]
    assert {e["data"]["payload"]["op"] for e in reads} >= {"list", "download"}
    assert any(e["data"]["payload"].get("size") == 5 for e in reads)

    grant_id = done["result"]["grant_id"]
    assert [g["id"] for g in ok(fc.get("/v1/files/grants", headers=AGENT))] == [grant_id]
    assert ok(fc.get("/v1/files/grants", headers=ADULT)) == []
    ok(fc.delete(f"/v1/files/grants/{grant_id}", headers=AGENT))  # an agent may drop its own power
    assert fc.get("/v1/files/list", params={"root": "shared", "path": "/Media"}, headers=AGENT).status_code == 403
    assert "files.grant.revoked" in [e["event"] for e in audit_events(settings)]


def test_read_write_grant_lets_the_agent_write_inside_only(fc):
    mkdir(fc, OWNER, "shared", "/Inbox")
    r = fc.post("/v1/files/grants", headers=OWNER, json=grant_body(path="/Inbox", access="rw", approve=True))
    assert r.status_code == 202 and r.json()["state"] == "succeeded"
    ok(upload(fc, AGENT, "shared", "/Inbox", "note.md", b"# hi"), 204)
    ok(fc.post("/v1/files/ops", headers=AGENT, json={"op": "trash", "root": "shared", "path": "/Inbox/note.md"}))
    r = fc.post("/v1/files/ops", headers=AGENT, json={"op": "move", "root": "shared", "path": "/Inbox", "to_path": "/Elsewhere"})
    assert r.status_code == 403


def test_who_may_request_and_approve(fc):
    mkdir(fc, OWNER, "shared", "/Media")
    mkdir(fc, ADULT, "home:adult", "/Photos")
    assert fc.post("/v1/files/grants", headers=ADULT, json=grant_body()).status_code == 403
    assert fc.post("/v1/files/grants", headers=GUEST, json=grant_body()).status_code == 403
    r = fc.post("/v1/files/grants", headers=AGENT, json=grant_body(subject={"kind": "agent", "id": "other"}))
    assert r.status_code == 403 and r.json()["reason"] == "not_self"
    r = fc.post("/v1/files/grants", headers=AGENT, json=grant_body(subject={"kind": "app", "id": "whoami"}))
    assert r.status_code == 403
    r = fc.post("/v1/files/grants", headers=AGENT, json=grant_body(approve=True))
    assert r.status_code == 403  # the owner shortcut is for owners only, and nothing is filed
    assert ok(fc.get("/v1/files/requests", headers=AGENT)) == []
    # an agent may ask for an adult's folder, but the owner cannot approve access to someone else's Home
    req = ok(fc.post("/v1/files/grants", headers=AGENT, json=grant_body(root="home:adult", path="/Photos")), 202)
    r = fc.post(f"/v1/files/requests/{req['id']}/approve", headers=OWNER)
    assert r.status_code == 403 and r.json()["reason"] == "not_home_owner"
    r = fc.post("/v1/files/grants", headers=OWNER, json=grant_body(root="home:adult", path="/Photos"))
    assert r.status_code == 403
    r = fc.post("/v1/files/grants", headers=OWNER, json=grant_body(path="/Nope"))
    assert r.status_code == 404
    r = fc.post("/v1/files/grants", headers=OWNER, json=grant_body(subject={"kind": "app", "id": "not-an-app"}))
    assert r.status_code == 404


def test_app_grants_feed_the_executor_hook(fc, settings, files_root):
    mkdir(fc, OWNER, "shared", "/Media")
    req = ok(fc.post("/v1/files/grants", headers=OWNER, json=grant_body(
        subject={"kind": "app", "id": "whoami"}, slot="media", approve=True)), 202)
    assert req["state"] == "succeeded"
    svc = FilesService(fc.app.state.gateway)
    mounts = svc.app_mounts("whoami")
    assert mounts == [{"grant_id": req["result"]["grant_id"], "slot": "media",
                       "host_path": str(files_root / "shared" / "Media"), "read_only": True}]
    assert svc.app_mounts("uptime-kuma") == []


def test_idempotency_deny_cancel_expiry_and_pending_cap(fc, clock):
    mkdir(fc, OWNER, "shared", "/Media")
    h = {**AGENT, "Idempotency-Key": "k-1"}
    first = fc.post("/v1/files/grants", headers=h, json=grant_body())
    again = fc.post("/v1/files/grants", headers=h, json=grant_body())
    assert first.json()["id"] == again.json()["id"] and again.headers["onemind-idempotent-replay"] == "true"
    r = fc.post("/v1/files/grants", headers=h, json=grant_body(access="rw"))
    assert r.status_code == 409 and r.json()["reason"] == "idempotency_mismatch"

    denied = ok(fc.post(f"/v1/files/requests/{first.json()['id']}/deny", headers=OWNER, json={"reason": "not now"}))
    assert denied["state"] == "cancelled" and denied["deny_reason"] == "not now"
    assert fc.post(f"/v1/files/requests/{first.json()['id']}/approve", headers=OWNER).status_code == 409

    req = ok(fc.post("/v1/files/grants", headers=AGENT, json=grant_body()), 202)
    assert ok(fc.post(f"/v1/files/requests/{req['id']}/cancel", headers=AGENT))["state"] == "cancelled"
    assert fc.post(f"/v1/files/requests/{req['id']}/cancel", headers=ADULT).status_code == 404

    req = ok(fc.post("/v1/files/grants", headers=AGENT, json=grant_body()), 202)
    clock.advance(timedelta(hours=25).total_seconds())
    r = fc.post(f"/v1/files/requests/{req['id']}/approve", headers=OWNER)
    assert r.status_code == 409 and r.json()["error"] == "expired"

    for _ in range(10):
        ok(fc.post("/v1/files/grants", headers=AGENT, json=grant_body()), 202)
    r = fc.post("/v1/files/grants", headers=AGENT, json=grant_body())
    assert r.status_code == 429 and r.json()["reason"] == "too_many_pending" and r.headers["retry-after"]
    states = [x["state"] for x in ok(fc.get("/v1/files/requests", headers=OWNER, params={"limit": 500}))]
    assert states.count("awaiting_approval") == 10


def test_folder_gone_at_approval_is_stale(fc):
    mkdir(fc, OWNER, "shared", "/Temp")
    req = ok(fc.post("/v1/files/grants", headers=AGENT, json=grant_body(path="/Temp")), 202)
    ok(fc.post("/v1/files/ops", headers=OWNER, json={"op": "trash", "root": "shared", "path": "/Temp"}))
    r = fc.post(f"/v1/files/requests/{req['id']}/approve", headers=OWNER)
    assert r.status_code == 409 and r.json()["error"] == "stale_precondition"
    assert ok(fc.get(f"/v1/files/requests/{req['id']}", headers=OWNER))["state"] == "awaiting_approval"
