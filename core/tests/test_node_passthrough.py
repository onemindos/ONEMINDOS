# SPDX-License-Identifier: Apache-2.0
"""The hardware profile's passthrough section (#690): IOMMU groups and USB drivers, gated like the rest.

Device grants to machines read this section (machine.attach_device). NATS has no users yet (H-06),
so the gateway's gate (nodes.valid_capabilities) must take the section the Go probe writes and drop
a profile that plants a path, a malformed driver name or an extra field in it.
"""

from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from conftest import OWNER
from onemind_core.apimodels import NodeCapabilities
from test_node_capabilities import SUBJECT, profile
from test_nodes_catalog import heartbeat


def with_passthrough() -> dict:
    caps = profile("x86efi")
    caps["passthrough"] = {
        "iommu_groups": [{"group": 1, "devices": ["0000:01:00.0", "0000:01:00.1"]}],
        "usb_drivers": {"1-1": ["usbhid"], "1-2.4": ["usb-storage", "uas"]},
    }
    return caps


def test_the_section_is_served_as_the_node_sent_it(client):
    caps = with_passthrough()
    assert client.app.state.registry.ingest(SUBJECT, heartbeat(capabilities=caps))
    node = client.get("/v1/nodes/3f9c2a1b7d4e", headers=OWNER).json()
    assert node["capabilities"]["passthrough"] == caps["passthrough"]


def test_a_box_without_an_iommu_sends_no_section_and_is_still_valid():
    caps = profile("x86efi")
    assert "passthrough" not in caps  # the Go probe's golden documents: no IOMMU in those fixtures
    NodeCapabilities.model_validate(caps)


@pytest.mark.parametrize("mutate", [
    lambda p: p["iommu_groups"][0].update(devices=["../../etc"]),
    lambda p: p["iommu_groups"][0].update(group=-1),
    lambda p: p["usb_drivers"].update({"1-3": ["bad name!"]}),
    lambda p: p["usb_drivers"].update({"/dev/sda": ["usb-storage"]}),
    lambda p: p.update(extra=True),
])
def test_a_planted_section_drops_the_profile_not_the_heartbeat(client, mutate):
    caps = with_passthrough()
    mutate(caps["passthrough"])
    with pytest.raises(ValidationError):
        NodeCapabilities.model_validate(copy.deepcopy(caps))
    assert client.app.state.registry.ingest(SUBJECT, heartbeat(capabilities=caps))
    node = client.get("/v1/nodes/3f9c2a1b7d4e", headers=OWNER).json()
    assert "capabilities" not in node and node["board"] == "x86_64-efi"
