# SPDX-License-Identifier: Apache-2.0
"""The Photos switch: on by default, GET/PUT /v1/settings/photos, owner approval (refs #1232, #234)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from conftest import AGENT, OWNER, make_client
from onemind_core.appstore.service import AppStoreSettings
from onemind_core.photos import PhotosSettings
from test_system_apps import row, write_list


@pytest.fixture
def photos_settings(settings, tmp_path):
    lst = write_list(tmp_path / "system-apps.json", row("photos", "native", "allowed", "os"))
    return replace(settings, sections={**settings.sections, "appstore": AppStoreSettings(system_apps_file=lst),
                                       "photos": PhotosSettings(dir=tmp_path / "photos")})


@pytest.fixture
def c(photos_settings, clock):
    with make_client(photos_settings, clock) as client:
        yield client


def put(c, enabled, headers=OWNER):
    return c.put("/v1/settings/photos", json={"enabled": enabled}, headers=headers)


def approve(c, action_id):
    r = c.post(f"/v1/actions/{action_id}/approve", headers=OWNER)
    assert r.status_code == 200 and r.json()["state"] == "succeeded", r.text


def test_photos_is_on_by_default(c):
    r = c.get("/v1/settings/photos", headers=OWNER)
    assert r.status_code == 200, r.text
    assert r.json() == {"enabled": True, "owner_switch_on": True, "operator_off": False,
                        "can_change": True, "pending_action_id": None}
    assert c.get("/v1/photos/library", headers=OWNER).status_code == 200  # the routes answer, no env flag needed


def test_switch_off_and_on_goes_through_approval(c):
    r = put(c, False)
    assert r.status_code == 202, r.text
    action = r.json()
    assert action["type"] == "app.disable" and action["params"] == {"app_id": "photos"}
    # Nothing changes before an owner approves.
    state = c.get("/v1/settings/photos", headers=OWNER).json()
    assert state["enabled"] is True and state["pending_action_id"] == action["id"]
    approve(c, action["id"])
    state = c.get("/v1/settings/photos", headers=OWNER).json()
    assert state["enabled"] is False and state["owner_switch_on"] is False and state["pending_action_id"] is None
    off = c.get("/v1/photos/library", headers=OWNER)
    assert off.status_code == 409 and off.json()["reason"] == "app_disabled"
    assert put(c, False).status_code == 409  # already off
    on = put(c, True)
    assert on.status_code == 202 and on.json()["type"] == "app.enable"
    approve(c, on.json()["id"])
    assert c.get("/v1/settings/photos", headers=OWNER).json()["enabled"] is True
    assert c.get("/v1/photos/library", headers=OWNER).status_code == 200


def test_already_on_is_refused(c):
    r = put(c, True)
    assert r.status_code == 409 and r.json()["reason"] == "already_enabled"


def test_only_an_owner_may_ask(c):
    r = put(c, False, headers=AGENT)
    assert r.status_code == 403, r.text
    assert c.get("/v1/settings/photos", headers=OWNER).json()["pending_action_id"] is None


def test_an_unsigned_caller_is_refused(c):
    assert c.get("/v1/settings/photos").status_code == 401
    assert c.put("/v1/settings/photos", json={"enabled": False}).status_code == 401


def test_operator_hard_off_cannot_be_undone_here(photos_settings, clock, tmp_path):
    off = replace(photos_settings, sections={**photos_settings.sections,
                                             "photos": PhotosSettings(enabled=False, dir=tmp_path / "photos")})
    with make_client(off, clock) as c:
        s = c.get("/v1/settings/photos", headers=OWNER).json()
        assert s["enabled"] is False and s["operator_off"] is True and s["can_change"] is False
        r = put(c, True)
        assert r.status_code == 409 and r.json()["reason"] == "operator_off"
        assert c.get("/v1/photos/library", headers=OWNER).status_code == 404


def test_off_on_off_again_files_a_new_request_each_time(c):
    first = put(c, False).json()
    approve(c, first["id"])
    on = put(c, True).json()
    approve(c, on["id"])
    again = put(c, False)
    assert again.status_code == 202, again.text
    assert again.json()["id"] not in (first["id"], on["id"]) and again.json()["state"] == "awaiting_approval"
    approve(c, again.json()["id"])
    assert c.get("/v1/settings/photos", headers=OWNER).json()["enabled"] is False


def test_deny_then_ask_again_files_a_new_request(c):
    first = put(c, False).json()
    d = c.post(f"/v1/actions/{first['id']}/deny", headers=OWNER)
    assert d.status_code == 200, d.text
    again = put(c, False)
    assert again.status_code == 202 and again.json()["id"] != first["id"], again.text
    assert again.json()["state"] == "awaiting_approval"


def test_a_double_click_returns_the_open_request(c):
    first = put(c, False)
    second = put(c, False)
    assert first.status_code == 202 and second.status_code == 200
    assert second.json()["id"] == first.json()["id"]


def test_the_opposite_ask_points_at_the_pending_request(c):
    first = put(c, False).json()
    r = put(c, True)
    assert r.status_code == 409 and r.json()["reason"] == "request_pending" and first["id"] in r.json()["message"]
