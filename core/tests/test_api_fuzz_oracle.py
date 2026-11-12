# SPDX-License-Identifier: Apache-2.0
"""Positive/negative controls for the A2 temporal approval oracle (contract §3)."""
from copy import deepcopy

import pytest

from api_fuzz_check import decision_problems

OWNER = {"id": "owner", "kind": "person", "role": "owner"}


def evidence():
    return ([{"seq": 1, "event": "action.approved", "action_id": "a", "principal": OWNER},
             {"seq": 2, "event": "action.dispatched", "action_id": "a", "principal": None},
             {"seq": 3, "event": "action.succeeded", "action_id": "a", "principal": None}],
            [{"id": "a", "state": "succeeded", "decided_by": OWNER}])


def test_valid_approval_then_dispatch_agrees_with_ledger():
    recs, ledger = evidence()
    assert decision_problems(recs, ledger) == []


def test_later_approval_cannot_legitimize_earlier_dispatch():
    recs, ledger = evidence()
    recs.reverse()
    for i, r in enumerate(recs, start=1):
        r["seq"] = i
    assert any("earlier approval" in p for p in decision_problems(recs, ledger))


def test_a_different_owner_in_the_ledger_is_not_agreement():
    recs, ledger = evidence()
    ledger[0]["decided_by"] = {**OWNER, "id": "another-owner"}
    assert any("mismatch" in p for p in decision_problems(recs, ledger))


@pytest.mark.parametrize("event", ["action.approved", "action.dispatched"])
def test_duplicate_decision_or_dispatch_is_refused(event):
    recs, ledger = evidence()
    recs.append(deepcopy(next(r for r in recs if r["event"] == event)))
    recs[-1]["seq"] = 3
    assert any("duplicate" in p for p in decision_problems(recs, ledger))


def test_missing_ledger_record_is_refused():
    recs, _ = evidence()
    assert any("mismatch" in p for p in decision_problems(recs, []))


def test_missing_audit_decision_is_refused():
    _, ledger = evidence()
    assert any("mismatch" in p for p in decision_problems([], ledger))


@pytest.mark.parametrize("decision,state", [
    ("action.denied", "succeeded"), ("action.approved", "cancelled"),
])
def test_decision_kind_must_match_ledger_state(decision, state):
    recs = [{"seq": 1, "event": decision, "action_id": "a", "principal": OWNER}]
    ledger = [{"id": "a", "state": state, "decided_by": OWNER}]
    assert any("state" in p for p in decision_problems(recs, ledger))


def test_an_agent_mislabeled_owner_is_not_an_owner():
    recs, ledger = evidence()
    principal = {**OWNER, "kind": "agent"}
    recs[0]["principal"] = ledger[0]["decided_by"] = principal
    assert any("non-owner" in p for p in decision_problems(recs, ledger))
