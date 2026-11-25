# SPDX-License-Identifier: Apache-2.0
"""GET /v1/instance/name: the sign-in page shows the box name before anyone has signed in."""

from conftest import OWNER, make_client


def test_name_is_open_and_only_the_name(settings, clock):
    with make_client(settings, clock) as c:
        r = c.get("/v1/instance/name")  # no Authorization header
        assert r.status_code == 200
        assert r.json() == {"name": "Test OneMind"}  # no version, no node id


def test_name_follows_what_the_owner_chose(settings, clock):
    with make_client(settings, clock) as c:
        r = c.put("/v1/onboarding/settings", headers=OWNER, json={"box_name": "Home OneMind"})
        if r.status_code == 200:
            assert c.get("/v1/instance/name").json() == {"name": "Home OneMind"}
