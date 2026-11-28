# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy

import pytest

from conftest import AGENT, GUEST, OWNER, make_client

SITE = {
    "id": "yard", "name": "Service yard",
    "floors": [{"id": "ground", "name": "Ground"}],
    "areas": [{"id": "bay", "name": "Loading bay", "floor_id": "ground"}],
    "anchors": [{"x": 0, "y": 0, "lat": 40, "lon": 170},
                {"x": 10, "y": 0, "lat": 40, "lon": 170.001},
                {"x": 0, "y": 10, "lat": 40.001, "lon": 170}],
}


def test_site_is_persistent_and_requires_owner(client, settings, clock):
    for headers, status in (({}, 401), (GUEST, 403), (AGENT, 403)):
        assert client.post("/v1/sites", json=SITE, headers=headers).status_code == status
    assert client.get("/v1/sites", headers=GUEST).json() == []
    assert client.post("/v1/sites", json=SITE, headers=OWNER).status_code == 201
    assert client.post("/v1/sites", json=SITE, headers=OWNER).status_code == 409
    with make_client(settings, clock) as restarted:
        assert restarted.get("/v1/sites", headers=GUEST).json() == [{**SITE, "address": None}]


def test_site_keeps_the_owners_address_text(client):
    site = {**deepcopy(SITE), "id": "home", "address": "12 Orchard Lane, Springfield"}
    assert client.post("/v1/sites", json=site, headers=OWNER).status_code == 201
    assert client.get("/v1/sites", headers=OWNER).json() == [site]
    bad_text = ("", "   ", "\t", "x" * 257, "12 Orchard Lane\nSpringfield", "nul\x00here", "esc\x1b[2J", "del\x7f",
                "evil\u202eenaL", "iso\u2066late\u2069")
    for i, bad in enumerate(bad_text):
        reply = client.post("/v1/sites", json={**site, "id": f"other-{i}", "address": bad}, headers=OWNER)
        assert reply.status_code == 422, repr(bad)
    assert client.get("/v1/sites", headers=OWNER).json() == [site]


def test_site_address_is_for_the_owner_only(client):
    site = {**deepcopy(SITE), "id": "home", "address": "12 Orchard Lane, Springfield"}
    assert client.post("/v1/sites", json=site, headers=OWNER).status_code == 201
    assert client.get("/v1/sites", headers=OWNER).json()[0]["address"] == "12 Orchard Lane, Springfield"
    for headers in (GUEST, AGENT):
        reply = client.get("/v1/sites", headers=headers)
        assert reply.status_code == 200
        assert reply.json() == [{**site, "address": None}]


@pytest.mark.parametrize("bad", ["two", "flat", "latitude", "longitude", "null_island", "area_floor"])
def test_bad_site_leaves_no_records(client, bad):
    site = deepcopy(SITE)
    if bad == "two":
        site["anchors"].pop()
    elif bad == "flat":
        site["anchors"][2].update(x=25, y=0)
    elif bad == "latitude":
        site["anchors"][0]["lat"] = 91
    elif bad == "longitude":
        site["anchors"][0]["lon"] = -181
    elif bad == "null_island":
        site["anchors"][0].update(lat=0, lon=0)
    else:
        site["areas"][0]["floor_id"] = "elsewhere"
    assert client.post("/v1/sites", json=site, headers=OWNER).status_code == 422
    assert client.get("/v1/sites", headers=OWNER).json() == []


def test_anchor_uses_json_body_number_check(client):
    site = deepcopy(SITE)
    site["anchors"][0]["x"] = "3"
    reply = client.post("/v1/sites", json=site, headers=OWNER)
    assert reply.status_code == 422
    assert "x should be a JSON number" in reply.json()["message"]
