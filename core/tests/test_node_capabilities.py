# SPDX-License-Identifier: Apache-2.0
"""The hardware profile (NodeCapabilities, #618) on GET /v1/nodes: nodes:read only, a child cannot read it."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from conftest import OWNER
from onemind_core.app import create_app
from onemind_core.openapi import document
from test_identity import enrol, id_settings, setup_owner
from test_nodes_catalog import heartbeat

# The documents the Go probe produces from its fixtures (internal/detect/testdata/profile): the
# gateway is tested against the real shape, not a copy of it.
PROFILES = Path(__file__).resolve().parents[2] / "internal" / "detect" / "testdata" / "profile"
SUBJECT = "onemind.node.3f9c2a1b7d4e.status"


def profile(name: str) -> dict:
    return json.loads((PROFILES / f"{name}.json").read_text())


def test_the_profile_is_served_as_the_node_sent_it(client):
    rtx = profile("x86efi")
    assert client.app.state.registry.ingest(SUBJECT, heartbeat(capabilities=rtx))
    node = client.get("/v1/nodes/3f9c2a1b7d4e", headers=OWNER).json()
    assert node["capabilities"] == rtx
    assert client.get("/v1/nodes", headers=OWNER).json()[0]["capabilities"]["accelerators"][1]["vram_mb"] == 8188


def test_unknown_stays_unknown_through_the_gateway(client):
    pi = profile("rpi5")
    assert pi["memory"]["unified"] is None  # the fixture's own unknown
    client.app.state.registry.ingest(SUBJECT, heartbeat(capabilities=pi))
    caps = client.get("/v1/nodes/3f9c2a1b7d4e", headers=OWNER).json()["capabilities"]
    assert caps["memory"]["unified"] is None and caps["power"]["source"] is None


def test_a_profile_that_is_not_an_object_is_dropped_not_the_heartbeat(client):
    reg = client.app.state.registry
    assert reg.ingest(SUBJECT, heartbeat(capabilities="lots of GPUs"))
    node = client.get("/v1/nodes/3f9c2a1b7d4e", headers=OWNER).json()
    assert "capabilities" not in node and node["board"] == "x86_64-efi"


def test_a_child_cannot_read_the_profile(settings, clock, executor):
    with TestClient(create_app(id_settings(settings), clock=clock, executor=executor)) as hc:
        setup_owner(hc)
        hc.app.state.registry.ingest(SUBJECT, heartbeat(capabilities=profile("minipc")))
        assert hc.get("/v1/nodes/3f9c2a1b7d4e").json()["capabilities"]["usb"][1]["id"] == "1cf1:0030"
        kid = enrol(hc, "child", "kid")
        for path in ("/v1/nodes", "/v1/nodes/3f9c2a1b7d4e"):
            r = kid.get(path)
            assert r.status_code == 403, (path, r.text)
            assert "capabilities" not in r.text and "1cf1" not in r.text
        guest = enrol(hc, "guest", "gus")  # nodes:read: sees it
        assert guest.get("/v1/nodes/3f9c2a1b7d4e").json()["capabilities"]["schema"] == "onemind.node.capabilities/v1"


def test_the_profile_is_in_the_published_api_contract():
    schemas = document()["components"]["schemas"]
    node = schemas["Node"]["properties"]["capabilities"]
    assert any(ref.get("$ref", "").endswith("/NodeCapabilities") for ref in node.get("anyOf", [node]))
    caps = schemas["NodeCapabilities"]
    assert set(caps["required"]) == {"schema", "data_disk", "memory", "accelerators", "usb", "tty_ports",
                                     "radios", "cameras", "power", "thermal"}
    # Every field the Go probe writes is described (no silent drift between the two).
    for name in ("x86efi", "minipc", "rpi5"):
        assert set(profile(name)) == set(caps["properties"])
