# SPDX-License-Identifier: Apache-2.0
"""Falsifiable per-action dispatch/outcome controls for the fuzz postcheck."""
from copy import deepcopy

import pytest

from api_fuzz_check import decision_problems
from test_api_fuzz_oracle import OWNER, evidence


@pytest.mark.parametrize("mutation", ["missing_dispatch", "orphan_dispatch", "swapped_dispatch",
                                     "missing_outcome", "wrong_outcome", "early_outcome"])
def test_per_action_dispatch_and_outcome_corruption_is_refused(mutation):
    records, ledger = evidence()
    if mutation == "missing_dispatch":
        records.pop(1)
    elif mutation == "orphan_dispatch":
        records.append({"seq": 4, "event": "action.dispatched", "action_id": "unknown"})
    elif mutation == "swapped_dispatch":
        records[1]["action_id"] = "b"
        records.insert(0, {"seq": 0, "event": "action.denied", "action_id": "b", "principal": OWNER})
        ledger.append({"id": "b", "state": "cancelled", "decided_by": OWNER})
    elif mutation == "missing_outcome":
        records.pop()
    elif mutation == "wrong_outcome":
        records[-1]["event"] = "action.failed"
    else:
        records[1], records[2] = records[2], records[1]
    assert decision_problems(records, ledger), mutation


@pytest.mark.parametrize("state", ["succeeded", "failed", "outcome_unknown"])
def test_completed_approved_outcomes_are_valid(state):
    records, ledger = evidence()
    records[-1]["event"] = "action." + state
    ledger[0]["state"] = state
    assert decision_problems(records, ledger) == []


@pytest.mark.parametrize("state,event,principal", [
    ("cancelled", "action.denied", OWNER), ("expired", "action.expired", None),
    ("awaiting_approval", None, None),
])
def test_undispatched_states_are_valid(state, event, principal):
    records = [] if event is None else [{"seq": 1, "event": event, "action_id": "a", "principal": principal}]
    assert decision_problems(records, [{"id": "a", "state": state, "decided_by": principal}]) == []


def test_approved_recovery_without_dispatch_is_unknown_not_success():
    records, ledger = evidence()
    records.pop(1)
    records[-1]["event"] = "action.outcome_unknown"
    ledger[0]["state"] = "outcome_unknown"
    assert decision_problems(records, ledger) == []


def test_duplicate_outcome_is_refused():
    records, ledger = evidence()
    records.append(deepcopy(records[-1]))
    assert decision_problems(records, ledger)
