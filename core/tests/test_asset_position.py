# SPDX-License-Identifier: Apache-2.0
import json

import pytest

from conftest import AGENT, GUEST, OWNER, make_client
from onemind_core.subjects import load
from test_geo import SITE

ROUTE = "/v1/assets/Cart_1/position"
POSITION = {
    "site_id": "yard", "floor_id": "ground", "area_id": "bay", "kind": "device",
    "x": 3, "y": 7, "z": 2, "heading_deg": 45, "accuracy_m": 0.5, "source": "survey",
    "time": "2026-11-11T21:59:57Z",
}


def test_move_persists_and_publishes_registered_asset_state(client, clock, settings, monkeypatch):
    assert client.post("/v1/sites", json=SITE, headers=OWNER).status_code == 201
    sent = []
    monkeypatch.setattr(client.app.state.bus, "publish_threadsafe", lambda s, b: sent.append((s, json.loads(b))))
    assert client.get(ROUTE, headers=GUEST).status_code == 404
    for headers, status in (({}, 401), (GUEST, 403), (AGENT, 403)):
        assert client.put(ROUTE, json=POSITION, headers=headers).status_code == status
    assert not sent
    assert client.put(ROUTE, json=POSITION, headers=OWNER).status_code == 200
    later = {**POSITION, "time": clock().isoformat(), "x": 5, "y": 8}
    moved = client.put(ROUTE, json=later, headers=OWNER)
    assert moved.status_code == 200, moved.text
    assert moved.json()["lat"] == pytest.approx(40.0008, abs=1e-9)
    assert moved.json()["lon"] == pytest.approx(170.0005, abs=1e-9)
    assert [s for s, _ in sent] == ["onemind.asset.device.Cart_1.state"] * 2
    envelope = sent[1][1]
    assert not load().envelope_problems("onemind.datapoint/v1", envelope)
    assert envelope["position"]["heading_deg"] == 45 and envelope["position"]["accuracy_m"] == 0.5
    assert envelope["pose"] == {"frame": "yard", "x": 5, "y": 8, "z": 2}
    assert sent[0][1]["value"]["age_s"] == 3 and envelope["value"]["age_s"] == 0
    assert envelope["value"]["source"] == "survey"
    assert client.put(ROUTE, json=POSITION, headers=OWNER).status_code == 409
    assert len(sent) == 2
    clock.advance(12)
    with make_client(settings, clock) as restarted:
        actual = restarted.get(ROUTE, headers=GUEST)
        assert actual.json() == {**moved.json(), "age_s": 12}


@pytest.mark.parametrize("change", [
    {"kind": "person"}, {"kind": "private-person"}, {"kind": "employee"},
    {"site_id": "missing"}, {"area_id": "unknown"}, {"floor_id": "unknown"},
    {"heading_deg": 360}, {"accuracy_m": -2}, {"y": 4_000_000},
    {"time": "2031-11-11T00:00:00Z"}, {"time": "2026-11-11T21:59:57"},
    {"time": 0}, {"time": "1700000000"},
])
def test_invalid_position_does_not_write_or_publish(client, change, monkeypatch):
    assert client.post("/v1/sites", json=SITE, headers=OWNER).status_code == 201
    sent = []
    monkeypatch.setattr(client.app.state.bus, "publish_threadsafe", lambda *args: sent.append(args))
    reply = client.put(ROUTE, json={**POSITION, **change}, headers=OWNER)
    assert reply.status_code in (404, 422)
    assert client.get(ROUTE, headers=GUEST).status_code == 404
    assert not sent


def test_owner_session_can_place_assets(settings, clock):
    from test_identity import csrf, id_settings, setup_owner

    with make_client(id_settings(settings), clock) as browser:
        setup_owner(browser, username="map-owner")
        assert browser.post("/v1/sites", headers=csrf(browser), json=SITE).status_code == 201
        assert browser.put(ROUTE, headers=csrf(browser), json=POSITION).status_code == 200


@pytest.mark.nats
@pytest.mark.xdist_group("nats")
def test_move_over_real_nats(settings, clock):
    import asyncio
    import os

    import nats
    from test_nats_integration import _wait

    url = os.environ.get("ONEMIND_TEST_NATS_URL")
    if not url:
        pytest.skip("ONEMIND_TEST_NATS_URL not set")

    async def receive_move(client):
        nc = await nats.connect(url)
        try:
            sub = await nc.subscribe("onemind.asset.device.Cart_1.state")
            await nc.flush()
            response = await asyncio.to_thread(client.put, ROUTE, json=POSITION, headers=OWNER)
            assert response.status_code == 200, response.text
            msg = await sub.next_msg(timeout=5)
            data = json.loads(msg.data)
            assert data["nats_subject"] == msg.subject
            assert data["value"]["age_s"] == 3
            assert data["position"]["lat"] == pytest.approx(response.json()["lat"])
            assert not load().envelope_problems("onemind.datapoint/v1", data)
        finally:
            await nc.drain()

    with make_client(settings, clock, nats_url=url) as c:
        assert _wait(lambda: c.app.state.bus.connected)
        assert c.post("/v1/sites", json=SITE, headers=OWNER).status_code == 201
        asyncio.run(receive_move(c))
