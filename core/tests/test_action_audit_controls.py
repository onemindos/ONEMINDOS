# SPDX-License-Identifier: Apache-2.0
"""Independent-model mutation controls, including equal-count swapped decisions."""
from unittest.mock import patch

import pytest
from hypothesis import given, settings, strategies as st

from test_properties_actions import ActionMachine


@settings(database=None, deadline=None)
@given(mutation=st.sampled_from(["decision_kind", "swapped_ids", "missing_dispatch", "wrong_outcome", "wrong_call"]))
def test_model_rejects_per_action_audit_or_call_corruption(property_resources, mutation):
    machine = ActionMachine(property_resources)
    try:
        machine.mandatory_authorized_decisions()
        records = machine.gw.audit_records()
        machine.each_action_audit_matches_independent_model()
        approved = next(r for r in records if r["event"] == "action.approved")
        denied = next(r for r in records if r["event"] == "action.denied")
        if mutation == "decision_kind":
            denied["event"] = "action.approved"
        elif mutation == "swapped_ids":
            approved["action_id"], denied["action_id"] = denied["action_id"], approved["action_id"]
        elif mutation == "missing_dispatch":
            records = [r for r in records if r["event"] != "action.dispatched"]
        elif mutation == "wrong_outcome":
            next(r for r in records if r["event"] == "action.succeeded")["event"] = "action.failed"
        else:
            machine.gw.executor.calls[0] = ("app.install", "wrong-app")
        with patch.object(machine.gw, "audit_records", return_value=records), pytest.raises(AssertionError):
            machine.each_action_audit_matches_independent_model()
    finally:
        machine.teardown()
