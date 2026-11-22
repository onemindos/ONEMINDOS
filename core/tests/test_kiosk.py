# SPDX-License-Identifier: Apache-2.0
"""UX-07 (#242 part 2): the owner reaches kiosk mode over the API, since the box has no root login or SSH."""

import json

import pytest

from conftest import ADULT, AGENT, GUEST, OWNER, make_client
from onemind_core.identity.scopes import required_scopes
from onemind_core.routers.kiosk import FLAG_ENV


def client(settings, clock, tmp_path, monkeypatch):
    flag = tmp_path / "kiosk" / "enabled"
    monkeypatch.setenv(FLAG_ENV, str(flag))
    return make_client(settings, clock), flag


def test_owner_turns_the_flag_on_and_off(settings, clock, tmp_path, monkeypatch):
    c, flag = client(settings, clock, tmp_path, monkeypatch)
    assert c.get("/v1/instance/kiosk", headers=OWNER).json()["enabled"] is False
    r = c.put("/v1/instance/kiosk", json={"enabled": True}, headers=OWNER)
    assert r.status_code == 200 and r.json()["enabled"] is True
    assert flag.exists()
    assert c.get("/v1/instance/kiosk", headers=OWNER).json()["enabled"] is True
    assert c.put("/v1/instance/kiosk", json={"enabled": False}, headers=OWNER).json()["enabled"] is False
    assert not flag.exists()
    # off when already off is fine
    assert c.put("/v1/instance/kiosk", json={"enabled": False}, headers=OWNER).status_code == 200
    events = [json.loads(line) for line in settings.audit_path.read_text().splitlines()]
    assert [e["data"]["enabled"] for e in events if e["event"] == "kiosk.set"] == [True, False, False]


def test_only_the_owner_may_change_it(settings, clock, tmp_path, monkeypatch):
    c, flag = client(settings, clock, tmp_path, monkeypatch)
    for h in (ADULT, GUEST, AGENT):
        assert c.put("/v1/instance/kiosk", json={"enabled": True}, headers=h).status_code == 403
        assert c.get("/v1/instance/kiosk", headers=h).status_code == 403
    assert c.put("/v1/instance/kiosk", json={"enabled": True}).status_code == 401
    assert not flag.exists()


def test_unwritable_flag_is_unavailable_not_a_crash(settings, clock, tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv(FLAG_ENV, str(blocker / "enabled"))   # parent is a file: mkdir fails
    c = make_client(settings, clock)
    r = c.put("/v1/instance/kiosk", json={"enabled": True}, headers=OWNER)
    assert r.status_code == 503 and r.json()["error"] == "unavailable"


@pytest.mark.parametrize(("method", "expected"), [
    ("GET", ("instance:read",)),
    ("HEAD", ("instance:read",)),
    ("PUT", ("users:admin",)),
    ("POST", ("*",)),     # no such route: the fail-closed fallback (owner only), never a scope grant
    ("DELETE", ("*",)),
])
def test_kiosk_routes_have_their_own_scope_rows(method, expected):
    # #323 rule: every route registers its scopes at module level in its router. Reading the switch
    # needs instance:read, changing it an admin scope; the handlers still demand the owner on top.
    assert required_scopes(method, "/v1/instance/kiosk") == expected
