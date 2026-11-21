# SPDX-License-Identifier: Apache-2.0
"""FILES-SHARE-01 (#235): SMB shares per person and a Time Machine target.

Real gateway, real routes, real ledger. The one stand-in is the box side (`SmbHost`): none exists
yet, so the default is the honest `NoSmbHost`, and the approval flow is run against a recording host
the test injects (what the host receives is the thing under test).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, GUEST, OWNER
from onemind_core.app import create_app
from onemind_core.files.settings import FilesSettings
from onemind_core.smbshares import SmbHostError

GIB = 1024**3


class RecordingHost:
    def __init__(self):
        self.calls: list[list[dict]] = []
        self.passwords: list[tuple[str, str]] = []
        self.fail: SmbHostError | None = None

    def status(self):
        return True, "", ""

    def apply(self, desired):
        if self.fail:
            raise self.fail
        self.calls.append(desired)

    def set_password(self, user, password):
        if self.fail:
            raise self.fail
        self.passwords.append((user, password))


@pytest.fixture
def box(settings, clock, executor, tmp_path):
    settings = replace(settings, sections={**settings.sections, "files": FilesSettings(root=tmp_path / "files", min_free_bytes=0)})
    app = create_app(settings, clock=clock, executor=executor)
    with TestClient(app) as c:
        c.clock, c.n, c.svc = clock, 0, app.state.shares
        yield c


@pytest.fixture
def on(box):
    box.svc.host = RecordingHost()
    return box


def ask(c, params, who=OWNER):
    c.n += 1
    return c.post("/v1/actions", headers=who, json={
        "type": "files.share.create", "params": params, "idempotency_key": f"sh{c.n}",
        "expires_at": (c.clock.now + timedelta(hours=1)).isoformat()})


def approve(c, r):
    assert r.status_code == 201, r.text
    return c.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)


# ---- the honest default: no file-sharing service on this box yet ---------------------------------
def test_off_by_default_and_says_why(box):
    body = box.get("/v1/shares/smb", headers=OWNER).json()
    assert body["service"]["available"] is False and body["service"]["reason"] == "smb_unavailable"
    assert body["service"]["off_by_default"] is True and body["service"]["reach"] == ["lan", "mesh"]
    assert body["shares"] == []
    assert {"person_id": "adult", "role": "adult", "home": True} in body["people"]
    assert {"person_id": "guest", "role": "guest", "home": False} in body["people"]


def test_a_request_is_refused_not_filed_while_nothing_can_share(box):
    r = ask(box, {"kind": "home", "person_id": "owner"})
    assert r.status_code == 409 and r.json()["reason"] == "smb_unavailable"
    assert box.get("/v1/actions", headers=OWNER).json() == []


# ---- who may see and ask --------------------------------------------------------------------------
def test_people_see_only_their_own_part_and_agents_and_guests_are_out(on):
    assert approve(on, ask(on, {"kind": "home", "person_id": "adult"})).json()["state"] == "succeeded"
    assert approve(on, ask(on, {"kind": "home", "person_id": "owner"})).json()["state"] == "succeeded"
    assert sorted(s["person_id"] for s in on.get("/v1/shares/smb", headers=OWNER).json()["shares"]) == ["adult", "owner"]
    mine = on.get("/v1/shares/smb", headers=ADULT).json()
    assert [s["person_id"] for s in mine["shares"]] == ["adult"] and [p["person_id"] for p in mine["people"]] == ["adult"]
    assert on.get("/v1/shares/smb", headers=GUEST).status_code == 403
    assert on.get("/v1/shares/smb", headers=AGENT).status_code == 403


def test_only_an_owner_can_ask_and_an_agent_never_can(on):
    for who in (AGENT, ADULT, GUEST):
        assert ask(on, {"kind": "home", "person_id": "adult"}, who).status_code == 403
    assert on.get("/v1/actions", headers=OWNER).json() == []


# ---- the approval flow ----------------------------------------------------------------------------
def test_a_share_exists_only_after_an_owner_approves(on):
    r = ask(on, {"kind": "home", "person_id": "adult"})
    assert r.status_code == 201 and r.json()["state"] == "awaiting_approval"
    assert on.get("/v1/shares/smb", headers=OWNER).json()["shares"] == [] and on.svc.host.calls == []
    assert on.post(f"/v1/actions/{r.json()['id']}/approve", headers=ADULT).status_code == 403
    assert on.svc.host.calls == []
    done = on.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER).json()
    assert done["state"] == "succeeded" and "LAN and mesh only" in done["result"]["message"]
    [s] = on.get("/v1/shares/smb", headers=OWNER).json()["shares"]
    assert (s["kind"], s["person_id"], s["name"], s["root"], s["state"]) == ("home", "adult", "adult", "home:adult", "active")
    assert s["reach"] == ["lan", "mesh"] and s["quota_bytes"] is None
    # The host was told exactly this share: its owner and root, no password and no host path.
    assert on.svc.host.calls == [[{"id": s["id"], "kind": "home", "name": "adult", "user": "adult",
                                   "path": "home/adult", "quota_bytes": None}]]
    assert (on.svc.files.settings.root / "home" / "adult").is_dir()  # made by the gateway's own user


def test_time_machine_share_needs_a_size_cap_and_is_its_own_share(on):
    assert ask(on, {"kind": "timemachine", "person_id": "adult"}).status_code == 409  # no quota
    assert ask(on, {"kind": "timemachine", "person_id": "adult", "quota_bytes": 5}).status_code == 422  # under 1 GiB
    assert ask(on, {"kind": "home", "person_id": "adult", "quota_bytes": 2 * GIB}).status_code == 409
    assert approve(on, ask(on, {"kind": "home", "person_id": "adult"})).json()["state"] == "succeeded"
    tm = approve(on, ask(on, {"kind": "timemachine", "person_id": "adult", "quota_bytes": 500 * GIB}))
    assert tm.json()["state"] == "succeeded"
    shares = {s["kind"]: s for s in on.get("/v1/shares/smb", headers=OWNER).json()["shares"]}
    assert shares["timemachine"]["root"] == "timemachine:adult"  # not in the Files home
    assert shares["timemachine"]["name"] == "adult-timemachine" and shares["timemachine"]["quota_bytes"] == 500 * GIB
    assert len(on.svc.host.calls[-1]) == 2  # the host always gets the whole desired state


def test_refusals_unknown_person_guest_duplicate(on):
    assert ask(on, {"kind": "home", "person_id": "nobody"}).json()["reason"] == "unknown_person"
    assert ask(on, {"kind": "home", "person_id": "guest"}).json()["reason"] == "no_home"
    assert approve(on, ask(on, {"kind": "home", "person_id": "owner"})).json()["state"] == "succeeded"
    assert ask(on, {"kind": "home", "person_id": "owner"}).json()["reason"] == "already_shared"
    assert ask(on, {"kind": "disk", "person_id": "owner"}).status_code == 422
    assert ask(on, {"kind": "home", "person_id": "../etc"}).status_code == 422


def test_the_check_runs_again_at_approval(on):
    r = ask(on, {"kind": "home", "person_id": "adult"})
    assert approve(on, ask(on, {"kind": "home", "person_id": "adult"})).json()["state"] == "succeeded"
    stale = on.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert stale.status_code == 409 and len(on.get("/v1/shares/smb", headers=OWNER).json()["shares"]) == 1


def test_a_host_failure_leaves_no_share_behind(on):
    on.svc.host.fail = SmbHostError("host_error", "smbd would not start")
    done = approve(on, ask(on, {"kind": "home", "person_id": "adult"})).json()
    assert done["state"] == "failed" and done["result"]["message"] == "smbd would not start"
    assert done["result"]["steps"][0]["result"] == "host_error"
    assert on.get("/v1/shares/smb", headers=OWNER).json()["shares"] == []


def test_an_unexpected_host_error_still_ends_the_action_and_leaves_no_row(on):
    class Boom(RecordingHost):
        def apply(self, desired):
            raise RuntimeError("socket exploded")
    on.svc.host = Boom()
    done = approve(on, ask(on, {"kind": "home", "person_id": "adult"})).json()
    assert done["state"] == "failed" and done["result"]["steps"][0]["result"] == "internal_error"
    assert "socket exploded" not in done["result"]["message"]
    assert on.get("/v1/shares/smb", headers=OWNER).json()["shares"] == []


def test_a_duplicate_name_at_insert_fails_the_action_and_keeps_the_other_share(on):
    from datetime import UTC, datetime

    from onemind_core.smbshares import ShareRow
    r = ask(on, {"kind": "home", "person_id": "adult"})
    # A concurrent twin took the name after the recheck passed: the insert hits the unique name.
    on.svc.repo.add(ShareRow(id="shr_twin", kind="home", person_id="adult", name="adult", quota_bytes=None,
                             state="active", action_id=None, approved_by="owner", created_at=datetime.now(UTC)))
    on.svc.refusal = lambda params: None
    done = on.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER).json()
    assert done["state"] == "failed"
    assert [s["id"] for s in on.get("/v1/shares/smb", headers=OWNER).json()["shares"]] == ["shr_twin"]


# ---- removing ------------------------------------------------------------------------------------
def test_only_an_owner_removes_a_share_and_the_host_is_told(on):
    approve(on, ask(on, {"kind": "home", "person_id": "adult"}))
    [s] = on.get("/v1/shares/smb", headers=OWNER).json()["shares"]
    assert on.post(f"/v1/shares/smb/{s['id']}/stop", headers=ADULT).status_code == 403
    assert on.post(f"/v1/shares/smb/{s['id']}/stop", headers=AGENT).status_code == 403
    assert on.post("/v1/shares/smb/shr_missing/stop", headers=OWNER).status_code == 404
    assert on.post(f"/v1/shares/smb/{s['id']}/stop", headers=OWNER).json() == {"removed": True, "id": s["id"]}
    assert on.svc.host.calls[-1] == [] and on.get("/v1/shares/smb", headers=OWNER).json()["shares"] == []


def test_a_share_the_host_cannot_remove_stays_listed(on):
    approve(on, ask(on, {"kind": "home", "person_id": "adult"}))
    [s] = on.get("/v1/shares/smb", headers=OWNER).json()["shares"]
    on.svc.host.fail = SmbHostError("host_error", "could not reload smbd")
    r = on.post(f"/v1/shares/smb/{s['id']}/stop", headers=OWNER)
    assert r.status_code == 409 and r.json()["reason"] == "host_error"
    assert len(on.get("/v1/shares/smb", headers=OWNER).json()["shares"]) == 1  # the box may still share it


def test_share_names_are_safe_for_windows_and_macos(box):
    from onemind_core.smbshares import share_name
    assert share_name("home", "A.Li@home") == "a-li-home"
    assert share_name("timemachine", "x" * 64) == "x" * 28 + "-timemachine"
    assert share_name("home", "@@@") == "person"
