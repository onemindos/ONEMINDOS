# SPDX-License-Identifier: Apache-2.0
"""#1232 / #234: every household role signs in for real and uses Files and Photos for their own data.

Sessions here are real (enrolment, bearer sessions), so role scopes are enforced, unlike the static
test tokens that skip them. A guest has no Home and no photo library; nobody reads another person's.
"""

from dataclasses import replace
from hashlib import sha256

import pytest
from fastapi.testclient import TestClient

from onemind_core.app import create_app
from onemind_core.identity.scopes import ROLE_SCOPES, allowed_for_kind, has_any, required_scopes
from onemind_core.photos import PhotosSettings

from conftest import AGENT
from files_support import audit_events, files_root, files_settings, ok, upload  # noqa: F401
from test_photos import Phone, blob
from onemind_core.identity.crypto import totp_code
from test_identity import PASSWORD as OWNER_PASSWORD
from test_identity import LOCAL_PEER, bearer_step_up, box_code, enable_bearer_totp, id_settings, setup_bearer_owner

PASSWORD = "correct horse battery staple 1"
ROLES = ("owner", "adult", "teen", "child", "guest")
WITH_HOME = ("owner", "adult", "teen", "child")


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def box(settings, clock, executor, files_settings, tmp_path):
    s = replace(settings, sections={**settings.sections, "files": files_settings,
                                    "photos": PhotosSettings(enabled=True, dir=tmp_path / "photos")})
    s = id_settings(s)  # D-034: the box screen shows the setup and confirmation codes
    with TestClient(create_app(s, clock=clock, executor=executor), client=LOCAL_PEER) as c:
        yield c


@pytest.fixture
def people(box, clock) -> dict:
    """One signed-in person per role: {role: {id, headers}}."""
    headers = setup_bearer_owner(box)  # D-034: the screen code, then the saved recovery kit
    out = {"owner": {"id": box.get("/v1/me", headers=headers).json()["principal"]["id"], "headers": headers}}
    secret = out["owner"]["totp"] = enable_bearer_totp(box, headers, clock)
    for role in ROLES[1:]:
        body = {"display_name": role.title(), "role": role}
        asked = box.post("/v1/users", headers=headers, json=body)  # the hub names the exact step-up it needs
        step = next(d["step_up"] for d in asked.json()["details"] if "step_up" in d)
        grant = bearer_step_up(box, headers, clock, secret, step["op"], step["body"], step["target"])
        c = box.post("/v1/users", headers={**headers, "OneMind-Step-Up": grant}, json=body)
        assert c.status_code == 201, c.text
        e = box.post("/v1/auth/enrol", json={"code": c.json()["one_time"]["enrolment_code"], "username": role,
                                              "password": PASSWORD, "client": "cli"})
        assert e.status_code == 201, e.text
        assert e.json()["principal"]["role"] == role
        out[role] = {"id": e.json()["principal"]["id"], "headers": bearer(e.json()["access_token"])}
    return out


def test_every_person_role_holds_the_files_scope_and_only_people_do():
    for role in ROLES:
        assert "files:use" in ROLE_SCOPES[role] or role == "owner", role
    for role in WITH_HOME:
        assert "photos:use" in ROLE_SCOPES[role] or role == "owner", role
    assert "photos:use" not in ROLE_SCOPES["guest"]
    for scope in ("files:use", "photos:use"):
        assert allowed_for_kind(scope, "person")
        for kind in ("agent", "plugin", "automation", "node"):
            assert not allowed_for_kind(scope, kind), (scope, kind)


@pytest.mark.parametrize(("method", "path", "need"), [
    ("GET", "/v1/files/roots", "files:use"), ("GET", "/v1/files/list", "files:use"),
    ("GET", "/v1/files/download", "files:use"), ("POST", "/v1/files/ops", "files:use"),
    ("POST", "/v1/files/uploads", "files:use"), ("PATCH", "/v1/files/uploads/upl_1", "files:use"),
    ("GET", "/v1/files/requests", "files:use"), ("POST", "/v1/files/requests/frq_1/cancel", "files:use"),
    ("GET", "/v1/files/downloads", "files:use"), ("GET", "/v1/sync/changes", "files:use"),
    ("POST", "/v1/photos/sources", "photos:use"), ("GET", "/v1/photos/library", "photos:use"),
    ("GET", "/v1/photos/assets/ast_1/content", "photos:use"), ("PATCH", "/v1/photos/uploads/upl_1", "photos:use"),
    ("GET", "/v1/photos/sources/src_1/coverage", "photos:use"),
])
def test_files_and_photos_routes_ask_for_the_use_scope(method, path, need):
    assert required_scopes(method, path) == (need,)


@pytest.mark.parametrize(("method", "path"), [
    ("PUT", "/v1/files/quotas/someone"), ("POST", "/v1/files/requests/frq_1/approve"),
    ("POST", "/v1/files/trash/empty"),
    ("POST", "/v1/files/requests/frq_1/deny"), ("POST", "/v1/files/downloads/dl_1/release"),
])
def test_owner_decisions_still_ask_for_every_scope(method, path):
    assert required_scopes(method, path) == ("*",)
    for role in ROLES[1:]:
        assert not has_any(ROLE_SCOPES[role], ("*",))


@pytest.mark.parametrize("role", ROLES)
def test_each_role_lists_its_spaces_and_the_gateway_scope_gate_opens(box, people, role):
    r = box.get("/v1/files/roots", headers=people[role]["headers"])
    assert r.status_code == 200, r.text
    roots = {x["root"]: x for x in r.json()}
    assert ("home:" + people[role]["id"] in roots) == (role in WITH_HOME)
    assert set(roots) <= {"home:" + people[role]["id"], "shared"}
    assert roots["shared"]["writable"] == (role in ("owner", "adult"))
    assert box.get("/v1/files/trash", headers=people[role]["headers"]).status_code == (200 if role in WITH_HOME else 403)
    assert box.get("/v1/files/requests", headers=people[role]["headers"]).status_code == 200


@pytest.mark.parametrize("role", WITH_HOME)
def test_each_role_writes_and_reads_its_own_files(box, people, role):
    me = people[role]
    root = "home:" + me["id"]
    ok(box.post("/v1/files/ops", headers=me["headers"], json={"op": "mkdir", "root": root, "path": "/Pics"}))
    ok(upload(box, me["headers"], root, "/Pics", "a.txt", b"mine " + role.encode()), 204)
    names = [e["name"] for e in ok(box.get("/v1/files/list", headers=me["headers"], params={"root": root, "path": "/Pics"}))]
    assert names == ["a.txt"]
    d = box.get("/v1/files/download", headers=me["headers"], params={"root": root, "path": "/Pics/a.txt"})
    assert d.status_code == 200 and d.content == b"mine " + role.encode()


@pytest.mark.parametrize("role", ("adult", "teen", "child", "guest"))
def test_nobody_reads_or_writes_another_persons_files(box, people, role):
    owner, me = people["owner"], people[role]
    ok(upload(box, owner["headers"], "home:" + owner["id"], "/", "secret.txt", b"owner only"), 204)
    for params in ({"root": "home:" + owner["id"], "path": "/"},):
        assert box.get("/v1/files/list", headers=me["headers"], params=params).status_code == 403
    assert box.get("/v1/files/download", headers=me["headers"],
                   params={"root": "home:" + owner["id"], "path": "/secret.txt"}).status_code == 403
    r = box.post("/v1/files/ops", headers=me["headers"], json={"op": "mkdir", "root": "home:" + owner["id"], "path": "/x"})
    assert r.status_code == 403
    # and the owner does not read theirs either
    assert box.get("/v1/files/list", headers=owner["headers"],
                   params={"root": "home:" + me["id"], "path": "/"}).status_code == 403


def test_the_household_folder_follows_the_role(box, people):
    for role, may_write in (("owner", True), ("adult", True), ("teen", False), ("child", False), ("guest", False)):
        who = people[role]
        if may_write:
            ok(upload(box, who["headers"], "shared", "/", f"{role}.txt", b"hello"), 204)
        else:
            r = box.post("/v1/files/ops", headers=who["headers"], json={"op": "mkdir", "root": "shared", "path": f"/{role}"})
            assert r.status_code == 403 and r.json()["reason"] == "role", (role, r.text)
        assert box.get("/v1/files/list", headers=who["headers"], params={"root": "shared", "path": "/"}).status_code == 200


def test_the_owner_only_files_routes_stay_owner_only(box, people):
    for role in ROLES[1:]:
        h = people[role]["headers"]
        assert box.get("/v1/files/quotas", headers=h).status_code == 403
        assert box.put(f"/v1/files/quotas/{people[role]['id']}", headers=h, json={"limit_bytes": 1}).status_code == 403
        assert box.post("/v1/files/requests/frq_1/approve", headers=h).status_code == 403
    assert box.get("/v1/files/quotas", headers=people["owner"]["headers"]).status_code == 200


@pytest.mark.parametrize("role", ("adult", "teen", "child"))
def test_family_sessions_cannot_use_chunked_sync_uploads(box, people, settings, role):
    me = people[role]
    root = "home:" + me["id"]
    data = b"uncommitted chunk"
    digest = sha256(data).hexdigest()
    ok(box.put(f"/v1/files/quotas/{me['id']}", headers=people["owner"]["headers"], json={"limit_bytes": 1}))
    ok(box.get("/v1/sync/changes", headers=me["headers"], params={"root": root}))
    hdr = me["headers"]
    for response in (
        box.post("/v1/sync/chunks/missing", headers=hdr, json={"root": root, "hashes": [digest]}),
        box.put(f"/v1/sync/chunks/{digest}", headers=hdr, params={"root": root}, content=data),
        box.post("/v1/sync/commit", headers=hdr, json={"root": root, "path": "/staged.bin", "size": len(data),
                                                     "sha256": digest, "chunks": [{"hash": digest, "size": len(data)}]}),
    ):
        assert response.status_code == 403 and response.json()["error"] == "permission_denied", response.text

    denials = [e["data"]["payload"] for e in audit_events(settings) if e["event"] == "authz.denied"]
    assert [e["reason"] for e in denials] == ["scope"] * 3


def test_sync_openapi_bearer_scopes_match_runtime(box):
    paths = ok(box.get("/openapi.json"))["paths"]
    for path, operations in paths.items():
        if not path.startswith("/v1/sync/"):
            continue
        for method, operation in operations.items():
            probe = path.replace("{chunk_hash}", "0" * 64).replace("{lock_id}", "lck_1")
            scopes = required_scopes(method.upper(), probe)
            assert operation["security"] == [{"bearer": list(scopes)}], (method, path)


def test_family_home_trash_stays_restorable_without_a_permanent_delete_request(box, people, clock):
    teen = people["teen"]
    hdr, root = teen["headers"], "home:" + teen["id"]
    data = b"keep this"
    ok(upload(box, hdr, root, "/", "old.txt", data), 204)
    item = ok(box.post("/v1/files/ops", headers=hdr, json={"op": "trash", "root": root, "path": "/old.txt"}))

    for approve in (False, True):
        response = box.post("/v1/files/trash/empty", headers=hdr, json={"trash": "home", "approve": approve})
        assert response.status_code == 403 and response.json()["error"] == "permission_denied", response.text
        assert [entry["id"] for entry in ok(box.get("/v1/files/trash", headers=hdr))] == [item["id"]]
    assert ok(box.get("/v1/files/requests", headers=hdr)) == []
    ok(box.post("/v1/files/ops", headers=hdr, json={"op": "restore_trash", "trash_id": item["id"]}))
    restored = box.get("/v1/files/download", headers=hdr, params={"root": root, "path": "/old.txt"})
    assert restored.status_code == 200 and restored.content == data

    owner = people["owner"]["headers"]
    ok(upload(box, owner, "shared", "/", "old.txt", data), 204)
    shared_item = ok(box.post("/v1/files/ops", headers=owner,
                              json={"op": "trash", "root": "shared", "path": "/old.txt"}))
    request = ok(box.post("/v1/files/trash/empty", headers=owner, json={"trash": "shared"}), 202)
    assert request["state"] == "awaiting_approval"
    approve_path = f"/v1/files/requests/{request['id']}/approve"
    decision = {"plan_sha256": request["plan_sha256"]}
    assert box.post(approve_path, headers=hdr, json=decision).status_code == 403
    trash_path = "/v1/files/trash?trash=shared"
    assert [entry["id"] for entry in ok(box.get(trash_path, headers=owner))] == [shared_item["id"]]
    # D-034: emptying the shared trash is destructive, so the owner proves L2 at the box (password, code, screen)
    opts = ok(box.post(f"/v1/actions/{request['id']}/approve-options", headers=owner,
                       json={"method": "password+totp", "at_box": True}))
    proof = {"challenge": opts["challenge"], "password": OWNER_PASSWORD,
             "totp": totp_code(people["owner"]["totp"], int(clock.now.timestamp()) // 30)}
    decision = {**decision, "password_totp": proof, **({"box_code": box_code(box)} if opts.get("box_code_required") else {})}
    done = ok(box.post(approve_path, headers=owner, json=decision))
    assert done["state"] == "succeeded" and done["approved_by"] == people["owner"]["id"]
    assert ok(box.get(trash_path, headers=owner)) == []


@pytest.mark.parametrize("role", WITH_HOME)
def test_each_role_backs_up_and_sees_only_its_own_photos(box, people, role):
    me = people[role]
    phone = Phone(box, me["headers"], client_id=f"phone-{role}")
    data = blob(1, 4096)
    key = phone.key("asset-1")
    assert phone.check([(key, data)]) == ["need"]
    phone.upload(key, data, name="IMG_1.JPG")
    lib = box.get("/v1/photos/library", headers=me["headers"])
    assert lib.status_code == 200, lib.text
    items = lib.json()["items"]
    assert [i["file_name"] for i in items] == ["IMG_1.JPG"]
    got = box.get(f"/v1/photos/assets/{items[0]['id']}/content", headers=me["headers"])
    assert got.status_code == 200 and got.content == data
    assert phone.coverage()["total"] == 1
    for other in ROLES:
        if other == role:
            continue
        o = people[other]["headers"]
        c = box.get(f"/v1/photos/assets/{items[0]['id']}/content", headers=o)
        assert c.status_code in (403, 404), (role, other, c.status_code)
        lib2 = box.get("/v1/photos/library", headers=o)
        if other == "guest":
            assert lib2.status_code == 403
        else:
            assert [i["id"] for i in lib2.json()["items"]] == []


def test_a_guest_has_no_photo_library_and_an_agent_none_either(box, people):
    g = people["guest"]["headers"]
    r = box.post("/v1/photos/sources", headers=g, json={"client_id": "c1", "name": "P", "platform": "ios"})
    assert r.status_code == 403
    assert box.get("/v1/photos/library", headers=g).status_code == 403
    r = box.post("/v1/photos/sources", headers=AGENT, json={"client_id": "c1", "name": "P", "platform": "ios"})
    assert r.status_code == 403
