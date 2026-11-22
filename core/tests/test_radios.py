# SPDX-License-Identifier: Apache-2.0
"""Radio-found cards (issue #732) on GET /v1/radios, from the Go probe's real fixture documents."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from conftest import OWNER
from onemind_core.apimodels import SERIAL_RADIO_KINDS, NodeCapabilities
from onemind_core.app import create_app
from onemind_core.openapi import document
from test_identity import enrol, id_settings, setup_owner
from test_node_capabilities import SUBJECT, profile
from test_nodes_catalog import heartbeat

TABLE = Path(__file__).resolve().parents[2] / "sdk" / "schema" / "onemind.radios.json"


def test_a_known_radio_gets_a_card_with_type_port_and_its_stable_name(client):
    # The mini PC fixture: a ConBee II on 1-2 and a CP2102 board (Heltec V3 class) on 1-1, both named
    # by udev, plus an on-board UART that is not a USB serial line.
    client.app.state.registry.ingest(SUBJECT, heartbeat(capabilities=profile("minipc")))
    got = client.get("/v1/radios", headers=OWNER).json()
    assert got == [
        {"node_id": "3f9c2a1b7d4e", "hostname": "beelink", "node_status": "online", "kind": "zigbee",
         "model": "ConBee II", "match": "product", "tty": "ttyACM0", "device": "/dev/onemind/zigbee-1-2",
         "usb_id": "1cf1:0030", "usb_port": "1-2"},
        {"node_id": "3f9c2a1b7d4e", "hostname": "beelink", "node_status": "online", "kind": "lora",
         "model": "Heltec WiFi LoRa 32 V3", "match": "chip", "tty": "ttyUSB0", "device": "/dev/onemind/lora-1-1",
         "usb_id": "10c4:ea60", "usb_port": "1-1"},
    ]


def test_an_unknown_serial_device_is_listed_but_never_named(client):
    caps = copy.deepcopy(profile("minipc"))
    caps["radios"] = [r for r in caps["radios"] if r["kind"] != "lora"]  # udev did not name it
    client.app.state.registry.ingest(SUBJECT, heartbeat(capabilities=caps))
    usb0 = [c for c in client.get("/v1/radios", headers=OWNER).json() if c["tty"] == "ttyUSB0"]
    assert usb0 == [{"node_id": "3f9c2a1b7d4e", "hostname": "beelink", "node_status": "online", "kind": None,
                     "model": None, "match": None, "tty": "ttyUSB0", "device": None,
                     "usb_id": "10c4:ea60", "usb_port": "1-1"}]


def test_unplugging_removes_the_card_with_the_next_heartbeat(client):
    reg = client.app.state.registry
    reg.ingest(SUBJECT, heartbeat(capabilities=profile("minipc")))
    assert len(client.get("/v1/radios", headers=OWNER).json()) == 2
    caps = copy.deepcopy(profile("minipc"))
    caps["tty_ports"] = [t for t in caps["tty_ports"] if t["name"] != "ttyACM0"]
    caps["radios"] = [r for r in caps["radios"] if r["interface"] != "ttyACM0"]
    reg.ingest(SUBJECT, heartbeat(capabilities=caps))
    assert [c["tty"] for c in client.get("/v1/radios", headers=OWNER).json()] == ["ttyUSB0"]


def test_a_planted_dongle_radio_drops_the_profile_and_names_nothing(client):
    for interface in ("wlan0", "ttyS0", "../sda"):
        caps = copy.deepcopy(profile("minipc"))
        caps["radios"].append({"kind": "zigbee-thread", "interface": interface})
        client.app.state.registry.ingest(SUBJECT, heartbeat(capabilities=caps))
        assert client.get("/v1/radios", headers=OWNER).json() == [], interface
        assert "capabilities" not in client.get("/v1/nodes/3f9c2a1b7d4e", headers=OWNER).json()


def test_a_child_cannot_read_radio_cards(settings, clock, executor):
    with TestClient(create_app(id_settings(settings), clock=clock, executor=executor)) as hc:
        setup_owner(hc)
        hc.app.state.registry.ingest(SUBJECT, heartbeat(capabilities=profile("minipc")))
        assert len(hc.get("/v1/radios").json()) == 2
        kid = enrol(hc, "child", "kid")
        r = kid.get("/v1/radios")
        assert r.status_code == 403 and "1cf1" not in r.text
        guest = enrol(hc, "guest", "gus")  # nodes:read
        assert guest.get("/v1/radios").json()[0]["device"] == "/dev/onemind/zigbee-1-2"


def test_the_gateway_kinds_are_the_table_kinds_and_the_probe_documents_pass():
    assert set(SERIAL_RADIO_KINDS) == set(json.loads(TABLE.read_text())["kinds"])
    NodeCapabilities.model_validate(profile("minipc"))


def test_radio_cards_are_in_the_published_api_contract():
    doc = document()
    op = doc["paths"]["/v1/radios"]["get"]
    assert op["operationId"] == "radios.list"
    card = doc["components"]["schemas"]["RadioCard"]
    assert set(card["properties"]) == {"node_id", "hostname", "node_status", "kind", "model", "match", "tty",
                                       "device", "usb_id", "usb_port"}
