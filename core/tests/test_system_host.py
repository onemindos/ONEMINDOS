# SPDX-License-Identifier: Apache-2.0
"""Power controls reach the box (W1, audit b1): an approved restart, shutdown or factory reset goes through
the gateway's real host link to a stand-in for `onemindd host serve` (test_hostlink.FakeHost, same routes
and JSON as internal/host/server.go), and the ledger action closes from the host's journal.
"""

from __future__ import annotations

import pytest

from conftest import AGENT, OWNER
from onemind_core.system import HostLinkExecutor
from test_hostlink import box, host, state  # noqa: F401  (fixtures)


def ask(c, typ, who=OWNER, **extra):
    c.n += 1
    return c.post("/v1/system/actions", headers=who, json={"type": typ, "idempotency_key": f"sys{c.n}", **extra})


def approve(c, action_id):
    return c.post(f"/v1/actions/{action_id}/approve", headers=OWNER)


def test_the_system_service_uses_the_host_link(box):
    assert isinstance(box.app_.state.system.executor, HostLinkExecutor)
    ctl = {x["type"]: x for x in box.get("/v1/system/controls", headers=OWNER).json()["controls"]}
    assert ctl["system.restart"]["available"] and ctl["system.shutdown"]["available"]
    assert ctl["system.factory_reset"] == {**ctl["system.factory_reset"], "available": False, "unavailable_reason": "factory-reset is off here"}


@pytest.mark.parametrize("typ, kind", [("system.restart", "restart"), ("system.shutdown", "shutdown")])
def test_an_approved_power_control_reaches_the_host_and_ends_succeeded(box, host, typ, kind):
    a = ask(box, typ).json()
    assert host.posts == []  # nothing before the owner approves
    done = approve(box, a["id"])
    assert done.status_code == 200 and done.json()["state"] == "dispatched", done.text
    assert host.posts == [{"action_id": a["id"], "kind": kind}]  # the id and the kind, never a command
    host.set_state(a["id"], "going_down", message="restarting")
    box.link.poll()
    assert state(box, a["id"])["state"] == "dispatched"  # the box is going down: the journal keeps the answer
    host.set_state(a["id"], "succeeded", message=f"{kind} done")
    box.link.poll()
    final = state(box, a["id"])
    assert final["state"] == "succeeded" and final["result"]["steps"][0]["kind"] == kind


def test_an_agent_asks_but_only_the_owner_approval_reaches_the_host(box, host):
    a = ask(box, "system.restart", who=AGENT).json()
    assert box.post(f"/v1/actions/{a['id']}/approve", headers=AGENT).status_code == 403
    box.link.poll()
    assert host.posts == []


def test_a_host_that_refuses_ends_failed_with_its_message(box, host):
    a = ask(box, "system.restart").json()
    host.refuse = (409, {"error": "conflict", "reason": "busy", "message": "another action is running"})
    done = approve(box, a["id"]).json()
    assert done["state"] == "failed" and "another action is running" in done["result"]["message"]
    assert done["result"]["steps"][0]["result"] == "busy"


def test_a_host_that_failed_in_its_journal_ends_failed(box, host):
    a = ask(box, "system.shutdown").json()
    approve(box, a["id"])
    host.set_state(a["id"], "failed", reason="host_error", message="systemctl poweroff failed")
    box.link.poll()
    final = state(box, a["id"])
    assert final["state"] == "failed" and final["result"]["message"] == "systemctl poweroff failed"


def test_a_host_that_vanishes_after_the_request_ends_failed_not_succeeded(box, host):
    a = ask(box, "system.restart").json()
    host.close()  # the socket goes away between filing and approval
    done = approve(box, a["id"]).json()
    assert done["state"] == "failed" and "host service" in done["result"]["message"]


def test_a_control_that_becomes_unavailable_is_refused_before_filing(box, host):
    host.available["restart"] = False
    r = ask(box, "system.restart")
    assert r.status_code == 409 and r.json()["reason"] == "host_unavailable" and "restart is off here" in r.json()["message"]
    assert box.get("/v1/actions", headers=OWNER).json() == []


def test_factory_reset_carries_the_plan_the_owner_was_shown(box, host):
    host.available["factory-reset"] = True
    r = ask(box, "system.factory_reset", confirm="factory reset")
    assert r.status_code == 202, r.text
    assert r.json()["params"]["plan_sha256"] == host.plan_sha
    # The passkey step-up is covered in test_system_controls; here the ledger is advanced as the approve route would.
    a = box.app_.state.gateway.repo.get(r.json()["id"])
    results = []
    box.link.run(a, results.append)
    assert host.posts[-1] == {"action_id": a.id, "kind": "factory-reset", "plan_sha256": host.plan_sha} and results == []


def test_factory_reset_without_a_plan_is_not_sent(box, host):
    a = box.app_.state.gateway.repo.get(ask(box, "system.restart").json()["id"])
    a.type, a.params = "system.factory_reset", {"confirm": "factory reset"}
    results = []
    box.link.run(a, results.append)
    assert host.posts == [] and results[0].outcome == "failed" and "no approved plan" in results[0].message
