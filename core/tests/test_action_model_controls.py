# SPDX-License-Identifier: Apache-2.0
"""Deterministic non-deleting boundary controls for the generated action model."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from hypothesis import given, settings, strategies as st

from conftest import write_scan
from onemind_core.actions import ActionRequest
from onemind_core.errors import ApiError
from test_properties_actions import ActionMachine, Gateway, OWNER, PRINCIPALS


def request(gw, key="key", ttl=600, app="uptime-kuma"):
    return ActionRequest(type="app.install", params={"app_id": app}, idempotency_key=key,
                         expires_at=gw.clock.now + timedelta(seconds=ttl))


def test_pending_cap_and_replay_order_and_expiry_equality(property_resources):
    gw = Gateway(property_resources)
    try:
        agent = PRINCIPALS[4]
        bodies = [request(gw, key=str(n)) for n in range(10)]
        actions = [gw.svc.create(agent, body)[0] for body in bodies]
        with pytest.raises(ApiError) as error:
            gw.svc.create(agent, request(gw, key="eleventh"))
        assert (error.value.status, error.value.error) == (429, "rate_limited")
        assert gw.svc.create(agent, bodies[0]) == (actions[0], False), "replay precedes pending cap"
        changed = bodies[0].model_copy(update={"params": request(gw, app="whoami").params})
        with pytest.raises(ApiError) as error:
            gw.svc.create(agent, changed)
        assert (error.value.status, error.value.error) == (409, "conflict")
        gw.clock.advance(600)
        expired, created = gw.svc.create(agent, bodies[0])
        assert not created and expired["id"] == actions[0]["id"] and expired["state"] == "expired"
        with pytest.raises(ApiError) as error:
            gw.svc.create(agent, request(gw, key="due-now", ttl=0))
        assert (error.value.status, error.value.error) == (409, "expired")
        # The cap lazily expires the other nine; a genuinely fresh request must work.
        fresh, created = gw.svc.create(agent, request(gw, key="fresh"))
        assert created and fresh["state"] == "awaiting_approval"
        for op in (gw.svc.approve, gw.svc.deny):
            with pytest.raises(ApiError) as error:
                op(OWNER, actions[1]["id"])
            assert (error.value.status, error.value.error) == (409, "expired")
        assert gw.executor.calls == []
    finally:
        gw.close()


@pytest.mark.parametrize("age,allowed", [
    (timedelta(days=7), True), (timedelta(days=7, microseconds=1), False),
    (-timedelta(minutes=5), True), (-timedelta(minutes=5, microseconds=1), False),
])
def test_scan_exact_boundaries(property_resources, age, allowed):
    gw = Gateway(property_resources)
    try:
        write_scan(gw.apps / "uptime-kuma", gw.clock.now - age)
        action, created = gw.svc.create(OWNER, request(gw))
        assert created
        if allowed:
            assert gw.svc.approve(OWNER, action["id"])["state"] == "succeeded"
            assert gw.executor.calls == [("app.install", "uptime-kuma")]
        else:
            with pytest.raises(ApiError) as error:
                gw.svc.approve(OWNER, action["id"])
            assert (error.value.status, error.value.error) == (409, "stale_precondition")
            assert gw.repo.get(action["id"]).state == "awaiting_approval"
            assert gw.executor.calls == []
            assert gw.svc.deny(OWNER, action["id"])["state"] == "cancelled"
    finally:
        gw.close()


@settings(database=None, deadline=None)
@given(outcome=st.sampled_from(["succeeded", "failed", "outcome_unknown"]), crash=st.booleans())
def test_model_positive_outcomes_and_per_action_dispatch(property_resources, outcome, crash):
    machine = ActionMachine(property_resources)
    try:
        machine.mandatory_authorized_decisions()
        machine.gw.executor.outcome, machine.gw.executor.raise_exc = outcome, crash
        action_id = machine.request(OWNER, "hermes-like", "app.install", 600)
        machine._decide("approve", OWNER, action_id)
        machine.states_follow_the_table()
        machine.only_owners_decide()
        machine.executor_ran_once_per_owner_approved_dispatch()
        machine.each_action_audit_matches_independent_model()
        machine.agent_token_live_exactly_while_installed()
        machine.audit_chain_verifies()
        assert machine.gw.repo.get(action_id).state == ("outcome_unknown" if crash else outcome)
    finally:
        machine.teardown()


@settings(database=None, deadline=None)
@given(status=st.sampled_from([404, 409]))
def test_model_rejects_blanket_fresh_request_refusal(property_resources, status):
    machine = ActionMachine(property_resources)
    try:
        def refuse(*args):
            raise ApiError(status, "not_found" if status == 404 else "conflict", "mutation")

        with patch.object(machine.gw.svc, "create", refuse), pytest.raises(AssertionError, match="unexpected request refusal"):
            machine.request(OWNER, "uptime-kuma", "app.install", 600)
    finally:
        machine.teardown()
