# SPDX-License-Identifier: Apache-2.0
"""No real packets: all approval tests inject an in-process transport."""
import json
from dataclasses import replace
from ipaddress import IPv4Address

import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, GUEST, OWNER, action_body
from onemind_core.app import create_app
from onemind_core.config import Settings
from onemind_core import wake


@pytest.fixture
def world(settings, clock, tmp_path, monkeypatch):
    path = tmp_path / "wake.json"
    target = {"mac": "02:00:00:00:00:01", "network": str(IPv4Address(10 << 24)) + "/24"}
    path.write_text(json.dumps({"gpu": target}))
    sections = Settings.from_env({"ONEMIND_WAKE_TARGETS_FILE": str(path)}).sections
    app = create_app(replace(settings, sections={**sections, **settings.sections}), clock=clock)
    packets = []
    monkeypatch.setattr(wake, "send_packet", lambda packet, destination: packets.append((packet, destination)), raising=False)
    with TestClient(app) as client:
        assert app.state.registry.ingest("onemind.node.gpu.status", json.dumps({
            "schema": "onemind.node.status/v1", "node_id": "gpu", "hostname": "GPU box",
        }).encode())
        clock.advance(121)
        yield client, app, packets, path, target


def request(client, clock, key="wake-1"):
    cap = client.get("/v1/nodes/gpu/wake", headers=OWNER).json()
    assert cap["available"] is True
    body = action_body(clock, key=key)
    body.update(type="node.wake", params=cap["params"])
    return client.post("/v1/actions", headers=AGENT, json=body)


def test_only_person_owner_approval_sends_one_packet(world, clock):
    client, app, packets, _, _ = world
    response = request(client, clock)
    assert response.status_code == 201, response.text
    action = response.json()
    assert action["state"] == "awaiting_approval"
    assert packets == []
    for principal in (AGENT, ADULT, GUEST):
        assert client.post(f"/v1/actions/{action['id']}/approve", headers=principal).status_code == 403
    assert packets == []
    result = client.post(f"/v1/actions/{action['id']}/approve", headers=OWNER)
    assert result.status_code == 200
    assert result.json()["state"] == "succeeded"
    assert "packet sent" in result.json()["result"]["message"].lower()
    mac = bytes.fromhex("020000000001")
    assert packets == [(b"\xff" * 6 + mac * 16, (str(IPv4Address((10 << 24) + 255)), 9))]
    assert app.state.registry.get("gpu")["status"] == "offline"
    assert client.post(f"/v1/actions/{action['id']}/approve", headers=OWNER).status_code == 409
    assert request(client, clock).status_code == 200
    assert len(packets) == 1
    audit = app.state.audit.path.read_text()
    assert "action.approved" in audit and "action.succeeded" in audit
    assert "02:00:00:00:00:01" not in audit



def test_unconfigured_wake_is_unavailable(client, clock):
    body = action_body(clock)
    body.update(type="node.wake", params={"node_id": "gpu", "target_sha256": "0" * 64})
    response = client.post("/v1/actions", headers=AGENT, json=body)
    assert response.status_code == 409
    assert response.json()["error"] == "stale_precondition"


@pytest.mark.parametrize("extra", [{"mac": "02:00:00:00:00:02"}, {"destination": "example.org"}, {"port": 7}])
def test_request_cannot_supply_transport_target(world, clock, extra):
    client, _, packets, _, _ = world
    cap = client.get("/v1/nodes/gpu/wake", headers=OWNER).json()
    body = action_body(clock)
    body.update(type="node.wake", params={**cap["params"], **extra})
    assert client.post("/v1/actions", headers=AGENT, json=body).status_code == 422
    assert packets == []


@pytest.mark.parametrize("change", ["removed", "mac", "unknown_node", "malformed"])
def test_approval_rechecks_target_without_retargeting(world, clock, change):
    client, app, packets, path, target = world
    action = request(client, clock).json()
    if change == "removed":
        path.write_text("{}")
    elif change == "malformed":
        path.write_text("not JSON")
    elif change == "mac":
        path.write_text(json.dumps({"gpu": {**target, "mac": "02:00:00:00:00:02"}}))
    else:
        # A new gateway's empty in-memory registry must not infer a known node from config alone.
        from onemind_core.nodes import NodeRegistry
        app.state.gateway.registry = NodeRegistry(clock)
    response = client.post(f"/v1/actions/{action['id']}/approve", headers=OWNER)
    assert response.status_code == 409
    assert packets == []
    assert client.get(f"/v1/actions/{action['id']}", headers=OWNER).json()["state"] == "awaiting_approval"


@pytest.mark.parametrize("decision", ["deny", "expired"])
def test_denied_or_expired_request_never_sends(world, clock, decision):
    client, _, packets, _, _ = world
    action = request(client, clock).json()
    if decision == "deny":
        assert client.post(f"/v1/actions/{action['id']}/deny", headers=OWNER).status_code == 200
    else:
        clock.advance(601)
    assert client.post(f"/v1/actions/{action['id']}/approve", headers=OWNER).status_code == 409
    assert packets == []


def test_transport_failure_is_unknown_and_never_retried(world, clock, monkeypatch):
    client, _, packets, _, _ = world
    def fail(packet, destination):
        packets.append(packet)
        raise OSError("private transport details must not leak")
    monkeypatch.setattr(wake, "send_packet", fail)
    action = request(client, clock).json()
    response = client.post(f"/v1/actions/{action['id']}/approve", headers=OWNER)
    assert response.json()["state"] == "outcome_unknown"
    assert "private transport" not in response.text
    assert client.post(f"/v1/actions/{action['id']}/approve", headers=OWNER).status_code == 409
    assert len(packets) == 1


def test_capability_is_authenticated_known_node_only_and_does_not_leak_target(world):
    client, _, _, _, target = world
    assert client.get("/v1/nodes/gpu/wake").status_code == 401
    assert client.get("/v1/nodes/unknown/wake", headers=OWNER).status_code == 404
    response = client.get("/v1/nodes/gpu/wake", headers=AGENT)
    assert target["mac"] not in response.text and target["network"] not in response.text


@pytest.mark.parametrize("field,value", [
    ("mac", "ff:ff:ff:ff:ff:ff"), ("mac", "01:00:00:00:00:01"),
    ("mac", "00:00:00:00:00:00"), ("mac", "bad"),
    ("network", "example.org/24"), ("network", "0.0.0.0/0"),
    ("network", "127.0.0.0/24"), ("network", "8.8.8.0/24"),
])
def test_invalid_configuration_fails_closed(world, field, value):
    client, _, packets, path, target = world
    path.write_text(json.dumps({"gpu": {**target, field: value}}))
    assert client.get("/v1/nodes/gpu/wake", headers=OWNER).json()["available"] is False
    assert packets == []


def test_real_udp_adapter_uses_only_injected_socket(monkeypatch):
    calls = []
    class Socket:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            calls.append("closed")
        def settimeout(self, value):
            calls.append(("timeout", value))
        def setsockopt(self, *args):
            calls.append(args)
        def sendto(self, packet, destination):
            calls.append((packet, destination))
            return len(packet)
    monkeypatch.setattr(wake.socket, "socket", lambda *args: Socket())
    wake.send_packet(b"packet-bytes-only", ("test-destination", 9))
    assert calls == [("timeout", 2), (wake.socket.SOL_SOCKET, wake.socket.SO_BROADCAST, 1),
                     (b"packet-bytes-only", ("test-destination", 9)), "closed"]
