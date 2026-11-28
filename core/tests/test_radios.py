# SPDX-License-Identifier: Apache-2.0
"""Radio-found cards (issue #732) on GET /v1/radios and the owner's POST /v1/radios/{id}/confirm, from the Go
probe's real fixture document (internal/detect/testdata/profile/radiohub.json: the ThinkNode-M2's CH340K
named lora0, a ZBT-2 named zigbee-thread0, an FTDI adapter nobody knows)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, OWNER
from onemind_core.apimodels import SERIAL_RADIO_KINDS, NodeCapabilities
from onemind_core.app import create_app
from onemind_core.openapi import document
from test_identity import LOCAL_PEER, audit_events, enrol, id_settings, setup_owner
from test_node_capabilities import SUBJECT, profile
from test_nodes_catalog import heartbeat

TABLE = Path(__file__).resolve().parents[2] / "sdk" / "schema" / "onemind.radios.json"
NODE = "3f9c2a1b7d4e"
ASK = {"profile": "meshcore-companion-usb", "label": "MeshCore companion (USB)", "confirmed": False, "confirmed_at": None}
M2 = {"id": f"{NODE}.lora0", "node_id": NODE, "hostname": "beelink", "node_status": "online", "kind": "lora",
      "model": "CH340K USB serial (ThinkNode-M2 class)", "match": "id", "tty": "ttyUSB0",
      "device": "/dev/onemind/lora0", "usb_id": "1a86:7522", "usb_port": "1-1", "confirm": ASK}
ZBT2 = {"id": f"{NODE}.zigbee-thread0", "node_id": NODE, "hostname": "beelink", "node_status": "online", "kind": "zigbee-thread",
        "model": "Home Assistant Connect ZBT-2", "match": "product", "tty": "ttyACM0",
        "device": "/dev/onemind/zigbee-thread0", "usb_id": "303a:831a", "usb_port": "1-2", "confirm": None}
FTDI = {"id": None, "node_id": NODE, "hostname": "beelink", "node_status": "online", "kind": None, "model": None,
        "match": None, "tty": "ttyUSB1", "device": None, "usb_id": "0403:6001", "usb_port": "1-3", "confirm": None}
CONFIRM = {"profile": "meshcore-companion-usb"}
CONFIRM_M2 = f"/v1/radios/{NODE}.lora0/confirm"


def hub(client, caps=None):
    assert client.app.state.registry.ingest(SUBJECT, heartbeat(capabilities=caps or profile("radiohub")))


def radios(client, headers=OWNER):
    r = client.get("/v1/radios", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def without(caps, tty):
    caps = copy.deepcopy(caps)
    caps["tty_ports"] = [t for t in caps["tty_ports"] if t["name"] != tty]
    caps["radios"] = [r for r in caps["radios"] if r["interface"] != tty]
    return caps


def test_two_radios_get_cards_with_type_and_port_and_the_unknown_line_is_listed_unnamed(client):
    hub(client)
    assert radios(client) == [ZBT2, M2, FTDI]


def test_unplugging_removes_the_card_with_the_next_heartbeat(client):
    hub(client)
    hub(client, without(profile("radiohub"), "ttyUSB0"))
    assert [c["tty"] for c in radios(client)] == ["ttyACM0", "ttyUSB1"]


def test_the_owner_confirms_the_m2_as_a_meshcore_companion(client, settings, clock):
    hub(client)
    r = client.post(CONFIRM_M2, headers=OWNER, json=CONFIRM)
    assert r.status_code == 200, r.text
    done = {**ASK, "confirmed": True, "confirmed_at": "2026-11-11T22:00:00Z"}
    assert r.json() == {**M2, "confirm": done}
    assert [c["confirm"] for c in radios(client) if c["kind"] == "lora"] == [done]
    ev = [e for e in audit_events(settings) if e["event"] == "radio.confirmed"]
    assert len(ev) == 1 and ev[0]["data"] == {"radio_id": M2["id"], **CONFIRM, "node_id": NODE, "device": "/dev/onemind/lora0",
                                              "kind": "lora", "usb_id": "1a86:7522", "usb_port": "1-1"}
    # Still plugged in: the next heartbeat keeps it. Unplugged, the card goes; plugged back into the same
    # port, the radio is still confirmed (#854: a replug resumes without a new approval).
    hub(client)
    assert next(c for c in radios(client) if c["kind"] == "lora")["confirm"] == done
    hub(client, without(profile("radiohub"), "ttyUSB0"))
    assert [c for c in radios(client) if c["kind"] == "lora"] == []
    hub(client)
    assert next(c for c in radios(client) if c["kind"] == "lora")["confirm"] == done


def test_a_confirmation_survives_a_gateway_restart(client, settings, clock):
    hub(client)
    assert client.post(CONFIRM_M2, headers=OWNER, json=CONFIRM).status_code == 200
    with TestClient(create_app(settings, clock=clock)) as restarted:
        hub(restarted)
        card = next(c for c in radios(restarted) if c["kind"] == "lora")
    assert card["id"] == M2["id"] and card["confirm"] == {**ASK, "confirmed": True, "confirmed_at": "2026-11-11T22:00:00Z"}


def test_the_radio_id_is_stable_across_heartbeats_and_restarts_and_names_the_radio(client, settings, clock):
    hub(client)
    first = {c["tty"]: c["id"] for c in radios(client)}
    assert first == {"ttyACM0": f"{NODE}.zigbee-thread0", "ttyUSB0": f"{NODE}.lora0", "ttyUSB1": None}
    hub(client)
    assert {c["tty"]: c["id"] for c in radios(client)} == first
    with TestClient(create_app(settings, clock=clock)) as restarted:
        hub(restarted)
        assert {c["tty"]: c["id"] for c in radios(restarted)} == first
    # The id follows the stable name, not the kernel's ttyUSB number.
    renumbered = copy.deepcopy(profile("radiohub"))
    next(t for t in renumbered["tty_ports"] if t["name"] == "ttyUSB0")["name"] = "ttyUSB7"
    next(r for r in renumbered["radios"] if r["interface"] == "ttyUSB0")["interface"] = "ttyUSB7"
    hub(client, renumbered)
    assert next(c for c in radios(client) if c["tty"] == "ttyUSB7")["id"] == M2["id"]


def test_moving_the_radio_to_another_port_needs_a_new_confirmation(client):
    hub(client)
    assert client.post(CONFIRM_M2, headers=OWNER, json=CONFIRM).status_code == 200
    moved = copy.deepcopy(profile("radiohub"))
    next(t for t in moved["tty_ports"] if t["name"] == "ttyUSB0")["usb_port"] = "1-4"
    hub(client, moved)
    assert next(c for c in radios(client) if c["kind"] == "lora")["confirm"] == ASK


@pytest.mark.parametrize("rid,body,status", [
    (f"{NODE}.zigbee-thread0", CONFIRM, 409),                     # a Zigbee radio is not a MeshCore radio
    (f"{NODE}.lora1", CONFIRM, 404),                              # no such radio
    ("nosuchnode.lora0", CONFIRM, 404),
    (f"{NODE}.ttyUSB1", CONFIRM, 422),                            # an unknown serial line has no id to confirm
    (f"{NODE}", CONFIRM, 422),
    (f"{NODE}.lora0.lora0", CONFIRM, 422),
    (f"{NODE}.lora0", {"profile": "meshtastic"}, 422),
    (f"{NODE}.lora0", {**CONFIRM, "probe": True}, 422),
    (f"{NODE}.lora0", {**CONFIRM, "node_id": NODE}, 422),          # the old body shape is not accepted
])
def test_confirming_anything_but_a_current_lora_radio_is_refused(client, rid, body, status):
    hub(client)
    r = client.post(f"/v1/radios/{rid}/confirm", headers=OWNER, json=body)
    assert r.status_code == status, r.text
    assert all(c["confirm"] is None or c["confirm"]["confirmed"] is False for c in radios(client))


def test_a_radio_on_a_machine_that_is_not_online_is_not_confirmed(client, clock):
    hub(client)
    clock.advance(60)
    r = client.post(CONFIRM_M2, headers=OWNER, json=CONFIRM)
    assert r.status_code == 409, r.text


@pytest.mark.parametrize("who", [ADULT, AGENT])
def test_only_an_owner_confirms_a_radio(client, settings, who):
    hub(client)
    r = client.post(CONFIRM_M2, headers=who, json=CONFIRM)
    assert r.status_code == 403, r.text
    assert next(c for c in radios(client) if c["kind"] == "lora")["confirm"] == ASK
    assert not [e for e in audit_events(settings) if e["event"] == "radio.confirmed"]


def test_a_planted_dongle_radio_drops_the_profile_and_names_nothing(client):
    for radio in ({"kind": "lora", "interface": "wlan0", "device": "/dev/onemind/lora1"},
                  {"kind": "lora", "interface": "ttyS0", "device": "/dev/onemind/lora1"},
                  {"kind": "lora", "interface": "ttyUSB1"},                                   # no name
                  {"kind": "lora", "interface": "ttyUSB1", "device": "/dev/onemind/zigbee1"},  # another kind's name
                  {"kind": "lora", "interface": "ttyUSB1", "device": "/dev/ttyUSB1"},
                  {"kind": "wifi", "interface": "wlan0", "device": "/dev/onemind/lora1"}):
        caps = copy.deepcopy(profile("radiohub"))
        caps["radios"].append(radio)
        hub(client, caps)
        assert radios(client) == [], radio
        assert "capabilities" not in client.get(f"/v1/nodes/{NODE}", headers=OWNER).json()


def test_a_child_cannot_read_radio_cards(settings, clock, executor):
    with TestClient(create_app(id_settings(settings), clock=clock, executor=executor), client=LOCAL_PEER) as hc:
        setup_owner(hc)
        hub(hc)
        assert len(hc.get("/v1/radios").json()) == 3
        kid = enrol(hc, "child", "kid")
        r = kid.get("/v1/radios")
        assert r.status_code == 403 and "7522" not in r.text
        guest = enrol(hc, "guest", "gus")  # nodes:read
        assert [c["device"] for c in guest.get("/v1/radios").json()] == [ZBT2["device"], M2["device"], None]


def test_the_gateway_kinds_are_the_table_kinds_and_the_probe_documents_pass():
    t = json.loads(TABLE.read_text())
    assert set(SERIAL_RADIO_KINDS) == set(t["kinds"])
    assert t["confirm"] == {"lora": {k: ASK[k] for k in ("profile", "label")}}
    for name in ("radiohub", "minipc", "x86efi", "rpi5"):
        NodeCapabilities.model_validate(profile(name))


def test_radio_cards_are_in_the_published_api_contract():
    doc = document()
    assert doc["paths"]["/v1/radios"]["get"]["operationId"] == "radios.list"
    assert doc["paths"]["/v1/radios/{radio_id}/confirm"]["post"]["operationId"] == "radios.confirm"
    assert "/v1/radios/confirm" not in doc["paths"]
    card = doc["components"]["schemas"]["RadioCard"]
    assert set(card["properties"]) == set(M2)
    assert "id" in card["required"]
    assert set(doc["components"]["schemas"]["RadioConfirmRequest"]["properties"]) == {"profile"}
    assert "device" in doc["components"]["schemas"]["NodeRadio"]["properties"]
