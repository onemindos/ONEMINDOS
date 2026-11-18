# SPDX-License-Identifier: Apache-2.0
"""NMD-09 (#134): install and update refuse an app whose images the box's CPU cannot run.

Pure checks on `onemind_core.cpufit`, then the real gateway: a hub heartbeat goes into the node
registry exactly as from NATS, and `POST /v1/actions` answers 409 with a sentence a person can act on.
"""
from __future__ import annotations

import json

import pytest

from conftest import OWNER, make_client
from onemind_core import cpufit
from test_appstore import add_app, install, request
from test_nodes_catalog import heartbeat

V3 = {"gpu": False, "minMemoryMb": 64, "cpuLevel": {"amd64": "x86-64-v3"}}


def manifest(archs=("amd64", "arm64"), requires=None, name="Immich"):
    return {"metadata": {"id": "immich", "name": name},
            "spec": {"archs": list(archs), "requires": requires or {"gpu": False, "minMemoryMb": 64}}}


# ---- pure ---------------------------------------------------------------------------------------

def test_a_lower_level_is_refused_with_a_clear_sentence():
    got = cpufit.refusal(manifest(requires=V3), {"arch": "amd64", "cpu_level": "x86-64-v2"})
    assert got is not None
    code, message, details = got
    assert code == "cpu_level_too_low"
    assert message.startswith("Immich needs a newer processor")
    assert "x86-64-v3" in message and "x86-64-v2" in message and "would crash" in message
    assert details == [{"field": "spec.requires.cpuLevel.amd64", "problem": "needs x86-64-v3; box is x86-64-v2"}]


@pytest.mark.parametrize("have", ["x86-64-v3", "x86-64-v4"])
def test_the_same_or_a_higher_level_is_fine(have):
    assert cpufit.refusal(manifest(requires=V3), {"arch": "amd64", "cpu_level": have}) is None


@pytest.mark.parametrize("node", [
    None,                                    # no hub has reported
    {"arch": "amd64"},                       # an older agent without cpu_level
    {"arch": "amd64", "cpu_level": ""},      # flags unreadable: unknown, never "low"
    {"arch": "amd64", "cpu_level": "x86-64-v9"},
])
def test_what_the_box_cannot_tell_is_not_guessed(node):
    assert cpufit.refusal(manifest(requires=V3), node) is None


def test_no_declared_level_means_any_cpu_of_the_arch():
    assert cpufit.refusal(manifest(), {"arch": "amd64", "cpu_level": "x86-64-v1"}) is None


def test_an_app_without_the_box_architecture_is_refused():
    code, message, _ = cpufit.refusal(manifest(archs=["amd64"]), {"arch": "arm64", "cpu_level": ""})
    assert code == "arch_unsupported"
    assert message == "Immich is built for x86 (amd64) only, and this box is ARM (arm64)."


def test_a_malformed_cpu_level_is_ignored_not_a_crash():
    for bad in ("x86-64-v3", ["x86-64-v3"], None):
        assert cpufit.refusal(manifest(requires={"gpu": False, "minMemoryMb": 64, "cpuLevel": bad}),
                              {"arch": "amd64", "cpu_level": "x86-64-v1"}) is None


def test_an_arm_box_ignores_an_amd64_level():
    assert cpufit.refusal(manifest(requires=V3), {"arch": "arm64", "cpu_level": ""}) is None


def test_the_hub_is_the_one_node_with_role_hub():
    a, b = {"node_id": "a", "role": "hub"}, {"node_id": "b", "role": "node"}
    assert cpufit.hub([b, a]) is a
    assert cpufit.hub([b]) is None
    assert cpufit.hub([a, dict(a, node_id="c")]) is None  # two hubs: unclear, so no guess


# ---- through the gateway ------------------------------------------------------------------------

def ingest(client, **hb):
    raw = heartbeat(**hb)  # the JSON bytes a node publishes
    node_id = json.loads(raw)["node_id"]
    assert client.app.state.registry.ingest(f"onemind.node.{node_id}.status", raw)


@pytest.fixture
def cpu_client(settings, clock, executor):
    add_app(settings, clock, "immich", requires=V3)
    add_app(settings, clock, "notes")
    add_app(settings, clock, "x86only", archs=["amd64"])
    with make_client(settings, clock, executor) as c:
        yield c


def test_install_refused_on_an_older_cpu(cpu_client, clock):
    ingest(cpu_client, cpu_level="x86-64-v2")
    r = request(cpu_client, clock, "app.install", {"app_id": "immich"})
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["reason"] == "cpu_level_too_low"
    assert body["message"].startswith("Immich needs a newer processor")
    install(cpu_client, clock, "notes")  # an app with no declared level still installs


def test_install_allowed_once_the_cpu_is_new_enough(cpu_client, clock):
    ingest(cpu_client, cpu_level="x86-64-v3")
    install(cpu_client, clock, "immich")


def test_install_refused_for_the_wrong_architecture(cpu_client, clock):
    ingest(cpu_client, arch="arm64", board="rpi5")
    r = request(cpu_client, clock, "app.install", {"app_id": "x86only"})
    assert r.status_code == 409 and r.json()["reason"] == "arch_unsupported"


def test_update_refused_on_an_older_cpu(cpu_client, clock):
    """NOMAD #661: a working app must not be bricked by an update that needs a newer CPU."""
    ingest(cpu_client, cpu_level="x86-64-v3")
    install(cpu_client, clock, "immich")
    ingest(cpu_client, cpu_level="x86-64-v2")  # e.g. the disk moved to an older box
    r = request(cpu_client, clock, "app.update", {"app_id": "immich"})
    assert r.status_code == 409 and r.json()["reason"] == "cpu_level_too_low", r.text


def test_rechecked_at_approval(cpu_client, clock):
    """The box can change between request and approval (a new heartbeat, a moved disk)."""
    ingest(cpu_client, cpu_level="x86-64-v3")
    r = request(cpu_client, clock, "app.install", {"app_id": "immich"})
    assert r.status_code == 201, r.text
    ingest(cpu_client, cpu_level="x86-64-v2")
    a = cpu_client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert a.status_code == 409 and a.json()["reason"] == "cpu_level_too_low"
