# SPDX-License-Identifier: Apache-2.0
"""Machines preflight (MACH-01, #281): which boxes may run virtual machines, and enabling them.

Heartbeats go through the real gateway's node registry; the answers come from the real routes.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, GUEST, OWNER
from onemind_core.app import create_app
from onemind_core.identity.scopes import required_scopes
from onemind_core.machines.capability import MIN_MEMORY_MB, refusals
from test_identity import LOCAL_PEER, csrf, enrol, id_settings, setup_owner

PC = {"node_id": "pc0123456789", "hostname": "beelink", "role": "hub", "board": "x86_64-efi", "arch": "amd64",
      "mem_total_mb": 15_800, "kvm": True, "k3s": {"present": True, "role": "server", "ready": True}}


def codes(node: dict) -> set[str]:
    return {r.code for r in refusals(node)}


def beat(**changes) -> dict:
    return {"schema": "onemind.node.status/v1", **PC, **changes}


@pytest.fixture
def box(settings, clock, executor):
    app = create_app(settings, clock=clock, executor=executor)
    with TestClient(app) as c:
        def report(**changes):
            hb = beat(**changes)
            assert app.state.registry.ingest(f"onemind.node.{hb['node_id']}.status", json.dumps(hb).encode())
        c.report = report
        yield c


def test_a_16gb_x86_hub_with_kvm_is_eligible():
    assert codes(PC) == set()


@pytest.mark.parametrize(("changes", "code"), [
    ({"board": "rpi5", "arch": "arm64", "mem_total_mb": 15_800}, "not_x86"),
    ({"board": "jetson-orin", "arch": "arm64"}, "not_x86"),
    ({"board": "arm64-efi", "arch": "arm64"}, "not_x86"),
    ({"board": "vm"}, "already_a_vm"),
    ({"board": "vm-do"}, "already_a_vm"),
    ({"board": "unknown"}, "not_x86"),
    ({"mem_total_mb": 7_800}, "memory_below_16gb"),
    ({"mem_total_mb": MIN_MEMORY_MB - 1}, "memory_below_16gb"),
    ({"mem_total_mb": None}, "memory_below_16gb"),
    ({"mem_total_mb": True}, "memory_below_16gb"),
    ({"kvm": False}, "no_kvm"),
    ({"kvm": None}, "no_kvm"),
    ({"kvm": "yes"}, "no_kvm"),
    ({"role": "node"}, "not_a_hub"),
    ({"k3s": {"present": True, "ready": False}}, "cluster_not_ready"),
    ({"k3s": None}, "cluster_not_ready"),
])
def test_each_limit_refuses_with_its_own_reason(changes, code):
    assert code in codes({**PC, **changes})


def test_a_node_that_does_not_report_kvm_is_refused_not_guessed():
    without = {k: v for k, v in PC.items() if k != "kvm"}
    assert codes(without) == {"no_kvm"}


def test_a_pi_reports_every_reason_that_applies():
    pi = {**PC, "board": "rpi5", "arch": "arm64", "mem_total_mb": 7_800, "kvm": False}
    assert codes(pi) == {"not_x86", "memory_below_16gb", "no_kvm"}


def test_capabilities_list_each_node_with_its_reasons(box):
    assert box.get("/v1/machines/capabilities", headers=GUEST).json()["nodes"] == []
    box.report()
    box.report(node_id="pi0123456789", hostname="pi", role="node", board="rpi5", arch="arm64", mem_total_mb=7_800, kvm=False)
    body = box.get("/v1/machines/capabilities", headers=ADULT).json()
    assert body["enabled"] is False and body["requirements"] == {"min_memory_mb": MIN_MEMORY_MB, "arch": "amd64", "kvm": True}
    assert body["eligible_node_ids"] == ["pc0123456789"]
    pc, pi = body["nodes"]
    assert pc["eligible"] and pc["reasons"] == [] and pc["kvm"] is True
    assert not pi["eligible"] and {r["code"] for r in pi["reasons"]} == {"not_a_hub", "not_x86", "memory_below_16gb", "no_kvm"}
    assert all(r["message"] for r in pi["reasons"])


def test_capabilities_need_a_sign_in(box):
    assert box.get("/v1/machines/capabilities").status_code == 401


def test_enable_is_refused_on_a_pi_with_the_reasons(box):
    box.report(role="hub", board="rpi5", arch="arm64", mem_total_mb=7_800, kvm=False)
    r = box.post("/v1/machines/enable", headers=OWNER)
    assert r.status_code == 409, r.text
    err = r.json()
    assert err["error"] == "policy_refused" and err["reason"] == "machines_unsupported"
    assert {d["code"] for d in err["details"]} == {"not_x86", "memory_below_16gb", "no_kvm"}
    assert "Raspberry Pi" in err["message"] and "16 GB" in err["message"]


def test_enable_is_refused_on_an_8gb_box_and_with_no_node_reporting(box):
    r = box.post("/v1/machines/enable", headers=OWNER)
    assert r.status_code == 409 and "no node has reported" in r.json()["message"]
    box.report(mem_total_mb=7_800)
    r = box.post("/v1/machines/enable", headers=OWNER)
    assert r.status_code == 409 and [d["code"] for d in r.json()["details"]] == ["memory_below_16gb"]
    assert "8 GB" in r.json()["message"]


def test_enable_on_an_eligible_box_files_a_request_and_installs_nothing(box):
    box.report()
    r = box.post("/v1/machines/enable", headers=OWNER)
    assert r.status_code == 202 and r.json()["type"] == "machines.enable" and r.json()["state"] == "awaiting_approval"
    caps = box.get("/v1/machines/capabilities", headers=OWNER).json()
    assert caps["enabled"] is False  # nothing is switched on before an owner approves


@pytest.mark.parametrize("who", [AGENT, ADULT, GUEST])
def test_only_the_owner_can_enable_and_the_refusal_is_audited(box, who, settings):
    box.report()
    r = box.post("/v1/machines/enable", headers=who)
    assert r.status_code == 403
    events = [json.loads(line) for line in settings.audit_path.read_text().splitlines()]
    assert any(e["event"] == "authz.denied" and e["data"]["attempted"] == "enable machines" for e in events)


# ---- who can reach the routes with a household account or a scoped token (identity/scopes.py) ---------

def test_the_routes_have_their_own_scope_rows(box):
    assert required_scopes("GET", "/v1/machines/capabilities") == ("nodes:read",)
    assert required_scopes("HEAD", "/v1/machines/capabilities") == ("nodes:read",)
    assert required_scopes("POST", "/v1/machines/enable") == ("machines:admin",)
    # not the full-scope fallback ("*") that an unregistered route gets
    assert required_scopes("GET", "/v1/machines/other/extra") == ("*",)


def test_household_accounts_read_the_capabilities_and_only_the_owner_enables(settings, clock, executor):
    s = id_settings(settings)
    with TestClient(create_app(s, clock=clock, executor=executor), client=LOCAL_PEER) as hc:
        setup_owner(hc)
        adult, guest = enrol(hc, "adult", "ana"), enrol(hc, "guest", "gus")
        for who in (adult, guest):  # nodes:read: the same facts as /v1/nodes
            assert who.get("/v1/machines/capabilities").status_code == 200
        assert enrol(hc, "child", "kid").get("/v1/machines/capabilities").status_code == 403  # no nodes:read
        for who in (adult, guest):
            assert who.post("/v1/machines/enable", headers=csrf(who)).status_code == 403
        assert hc.post("/v1/machines/enable", headers=csrf(hc)).status_code == 409  # the owner got past the scope


def test_a_narrow_owner_token_reads_but_cannot_enable(settings, clock, executor):
    with TestClient(create_app(id_settings(settings), clock=clock, executor=executor), client=LOCAL_PEER) as hc:
        setup_owner(hc)
        pat = hc.post("/v1/tokens", headers=csrf(hc), json={"name": "n", "scopes": ["nodes:read"]}).json()["one_time"]["token"]
        bearer = {"Authorization": f"Bearer {pat}"}
        assert hc.get("/v1/machines/capabilities", headers=bearer).status_code == 200
        r = hc.post("/v1/machines/enable", headers=bearer)
        assert r.status_code == 403, r.text
        assert hc.post("/v1/tokens", headers=csrf(hc), json={"name": "m", "scopes": ["machines:admin"]}).status_code == 422
