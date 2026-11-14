# SPDX-License-Identifier: Apache-2.0
"""Backend/isolation canaries; all allocated files, schemas and rows are retained."""
from __future__ import annotations

import tempfile
from datetime import timedelta
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st
from unittest.mock import patch

from conftest import AGENT, OWNER, action_body
from property_resources import PropertyResources
from test_properties_actions import ActionMachine, OWNER as PRINCIPAL


def test_required_postgresql_cannot_silently_use_sqlite():
    with pytest.raises(ValueError, match="backend"):
        PropertyResources(expected="postgresql", db_url="sqlite://")
    with pytest.raises(ValueError, match="backend"):
        PropertyResources(expected="postgresql", db_url=None)


def test_property_examples_are_isolated_and_restart_preserves_history(property_resources):
    with property_resources.example() as first, property_resources.example() as second:
        assert first.root != second.root
        first.assert_namespace()
        second.assert_namespace()
        if first.schema:
            assert first.schema != second.schema
        with first.http() as client:
            result = client.post("/v1/actions", headers=AGENT, json=action_body(first.clock))
            assert result.status_code == 201, result.text
            action_id = result.json()["id"]
            assert second.repo.list() == []
        with first.http() as restarted:
            assert restarted.get(f"/v1/actions/{action_id}", headers=OWNER).status_code == 200
        with second.http() as client:
            result = client.post("/v1/actions", headers=AGENT, json=action_body(second.clock))
            assert result.status_code == 201, result.text
            assert result.json()["id"] != action_id
        assert len(first.repo.list()) == len(second.repo.list()) == 1
        roots = [first.root, second.root]
    assert all(root.is_dir() for root in roots), "closing handles must not delete evidence"


def test_allocation_ceiling_fails_without_reusing_an_example(property_resources):
    root = Path(tempfile.mkdtemp(prefix="property-ceiling-", dir=property_resources.root))
    factory = PropertyResources(root=root, expected="sqlite", limit=1)
    with factory.example() as sample:
        retained = sample.root
    with pytest.raises(RuntimeError, match="allocation limit"):
        with factory.example():
            pytest.fail("must not allocate beyond the explicit ceiling")
    assert retained.is_dir()


def test_owner_http_success_and_agent_refusal_are_non_vacuous(property_resources):
    from api_fuzz_check import decision_problems
    from onemind_core.audit import verify
    from conftest import ScriptedExecutor

    with property_resources.example() as sample:
        executor = ScriptedExecutor()
        with sample.http(executor=executor) as client:
            ids = []
            for key in ("approve", "deny"):
                response = client.post("/v1/actions", headers=AGENT, json=action_body(sample.clock, key=key))
                assert response.status_code == 201, response.text
                ids.append(response.json()["id"])
            for op in ("approve", "deny"):
                response = client.post(f"/v1/actions/{ids[0]}/{op}", headers=AGENT)
                assert response.status_code == 403, response.text
                assert sample.repo.get(ids[0]).state == "awaiting_approval"
                assert executor.calls == []
            denied = client.post(f"/v1/actions/{ids[1]}/deny", headers=OWNER)
            assert denied.status_code == 200 and denied.json()["state"] == "cancelled", denied.text
            approved = client.post(f"/v1/actions/{ids[0]}/approve", headers=OWNER)
            assert approved.status_code == 200 and approved.json()["state"] == "succeeded", approved.text
            assert client.post(f"/v1/actions/{ids[0]}/approve", headers=OWNER).status_code == 409
            assert executor.calls == [("app.install", "uptime-kuma")]
            records = sample.audit_records()
            assert decision_problems(records, [a.to_json() for a in sample.repo.list()]) == []
            assert {event: sum(r["event"] == event for r in records) for event in (
                "authz.denied", "action.approved", "action.denied", "action.dispatched"
            )} == {"authz.denied": 2, "action.approved": 1, "action.denied": 1, "action.dispatched": 1}
            assert verify(sample.audit_path) == (True, len(records), "ok")
        assert sample.repo.get_app_state("uptime-kuma").status == "installed"
        assert sample.clock.now + timedelta(seconds=1) > sample.clock.now


@settings(database=None, deadline=None)
@given(op=st.sampled_from(["approve", "deny"]))
def test_model_rejects_blanket_owner_refusal(property_resources, op):
    from onemind_core.errors import ApiError


    machine = ActionMachine(property_resources)
    try:
        action_id = machine.request(PRINCIPAL, "uptime-kuma", "app.install", 600)

        def always_refuse(*args):
            raise ApiError(409, "conflict", "mutation: blanket owner refusal")

        with patch.object(machine.gw.svc, op, always_refuse), pytest.raises(
            AssertionError, match="unexpected owner refusal"
        ):
            machine._decide(op, PRINCIPAL, action_id)
    finally:
        machine.teardown()
