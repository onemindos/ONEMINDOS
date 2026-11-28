# SPDX-License-Identifier: Apache-2.0
"""The hardware profile (NodeCapabilities, #618) on GET /v1/nodes: nodes:read only, a child cannot read it."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import OWNER
from onemind_core.app import create_app
from onemind_core.openapi import document
from test_identity import LOCAL_PEER, enrol, id_settings, setup_owner
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


def test_every_probe_document_passes_the_gateway_gate():
    from onemind_core.apimodels import NodeCapabilities

    for name in ("x86efi", "minipc", "rpi5"):
        NodeCapabilities.model_validate(profile(name))


def _bad(mutate) -> dict:
    caps = copy.deepcopy(profile("minipc"))
    mutate(caps)
    return caps


# Each is a profile a LAN publisher could plant (NATS has no users yet, H-06). The gateway drops
# the profile, keeps the heartbeat, and never serves the planted value.
PLANTED = {
    "extra top-level field": lambda c: c.update(root_shell=True),
    "extra accelerator field": lambda c: c["accelerators"][0].update(vfio_group="/dev/vfio/0"),
    "device outside /dev": lambda c: c["accelerators"][1].update(device="/etc/shadow"),
    "device path traversal": lambda c: c["accelerators"][1].update(device="/dev/accel/../../etc/shadow"),
    "device a block disk": lambda c: c["accelerators"][1].update(device="/dev/sda"),
    "bare camera device": lambda c: c["cameras"][0].update(device="video0"),
    "camera device not a video node": lambda c: c["cameras"][0].update(device="/dev/mem"),
    "pci_id not vvvv:dddd": lambda c: c["accelerators"][0].update(pci_id="0000:00:02.0"),
    "pci_slot not an address": lambda c: c["accelerators"][0].update(pci_slot="8086:7d55"),
    "old pci key": lambda c: c["accelerators"][0].update(pci="8086:7d55"),
    "usb_id a list": lambda c: c["tty_ports"][0].update(usb_id=["1cf1:0030"]),
    "old usb key on a camera": lambda c: c["cameras"][0].update(usb="046d:0825"),
    "string for a number": lambda c: c["memory"].update(total_mb="31853"),
    "wrong schema": lambda c: c.update(schema="onemind.node.capabilities/v9"),
    "required list missing": lambda c: c.pop("accelerators"),
    "too many accelerators": lambda c: c.update(accelerators=c["accelerators"] * 40),
    "battery over 100": lambda c: c["power"].update(battery_pct=900),
}


@pytest.mark.parametrize("case", sorted(PLANTED))
def test_a_malformed_profile_is_dropped_not_the_heartbeat(client, case):
    caps = _bad(PLANTED[case])
    assert client.app.state.registry.ingest(SUBJECT, heartbeat(capabilities=caps))
    r = client.get("/v1/nodes/3f9c2a1b7d4e", headers=OWNER)
    node = r.json()
    assert "capabilities" not in node and node["board"] == "x86_64-efi", case
    for planted in ("root_shell", "/etc/shadow", "/dev/vfio", "/dev/mem", "/dev/sda", "capabilities/v9"):
        assert planted not in r.text


def test_a_good_profile_after_a_bad_one_is_served(client):
    reg = client.app.state.registry
    reg.ingest(SUBJECT, heartbeat(capabilities=_bad(PLANTED["device outside /dev"])))
    reg.ingest(SUBJECT, heartbeat(capabilities=profile("minipc")))
    caps = client.get("/v1/nodes/3f9c2a1b7d4e", headers=OWNER).json()["capabilities"]
    assert caps["accelerators"][1]["device"] == "/dev/accel/accel0"
    assert caps["accelerators"][0]["pci_slot"] == "0000:00:02.0" and caps["cameras"][0]["device"] == "/dev/video0"


def test_a_child_cannot_read_the_profile(settings, clock, executor):
    with TestClient(create_app(id_settings(settings), clock=clock, executor=executor), client=LOCAL_PEER) as hc:
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
    # Every field the Go probe writes is described (no silent drift between the two). The golden
    # fixtures have no IOMMU, so they leave out `passthrough` (#690), the one field written only on a
    # box with VT-d or AMD-Vi on; internal/detect/passthrough_test.go produces it.
    for name in ("x86efi", "minipc", "rpi5"):
        assert set(profile(name)) | {"passthrough"} == set(caps["properties"])
