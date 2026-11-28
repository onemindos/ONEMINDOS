# SPDX-License-Identifier: Apache-2.0
"""One risk table: a standing approval is judged on each request's actual risk (gateway permissions PR 1).

Each test fails without its fix: the lifecycle table and the registry agree, app.remove is sensitive,
a request a feature raised above its base class is never covered, a request with no valid risk
class is refused, and feature registrations feed the one table.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from onemind_core import lifecycle
from onemind_core.actions import ExecResult, FeatureAction, _never_by_policy
from onemind_core.ledger import Action
from onemind_core.app import create_app
from onemind_core.automation import registry

from conftest import OWNER


@pytest.fixture
def client(settings, clock, executor):
    with TestClient(create_app(settings, clock=clock, executor=executor)) as c:
        yield c


def _action(type_, params=None, risk="write") -> Action:
    from datetime import UTC, datetime

    now = datetime(2026, 1, 1, tzinfo=UTC)
    return Action(id="act_1", type=type_, params=params or {}, state="awaiting_approval",
                  requested_by={"id": "hermes", "kind": "agent"}, idempotency_key="k", created_at=now,
                  updated_at=now, expires_at=now + timedelta(hours=1), risk=risk)


def test_lifecycle_and_registry_agree_on_every_shared_type():
    shared = set(lifecycle.TYPES) & set(registry.TYPES)
    assert shared  # app.install, app.restart, app.update, app.remove, ...
    for t in shared:
        assert lifecycle.TYPES[t].risk == registry.TYPES[t].risk, t


def test_app_remove_is_sensitive_and_never_covered():
    assert registry.TYPES["app.remove"].risk == "sensitive"
    assert lifecycle.TYPES["app.remove"].risk == "sensitive"
    assert registry.policy_may_cover("app.remove", {"app_id": "x"}) is not None
    assert _never_by_policy(_action("app.remove", {"app_id": "x"}, risk="sensitive"))


def test_a_rule_for_app_remove_gets_422(client, clock):
    body = {"allow": {"types": ["app.remove"], "requested_by": ["agent:hermes"], "params": {}},
            "limits": {"per_day": 1}, "expires_at": (clock.now + timedelta(days=7)).isoformat().replace("+00:00", "Z")}
    r = client.post("/v1/approval-policies", json=body, headers=OWNER)
    assert r.status_code == 422, r.text


def test_stored_risk_above_the_table_blocks_a_rule():
    # app.restart is write in the table; a request stored as destructive is not covered.
    assert not _never_by_policy(_action("app.restart", {"app_id": "x"}, risk="write"))
    assert _never_by_policy(_action("app.restart", {"app_id": "x"}, risk="destructive"))
    assert _never_by_policy(_action("app.restart", {"app_id": "x"}, risk="actuate"))


def test_stored_risk_below_the_table_cannot_lower_it():
    # The table's parameter upgrade still counts when the stored class is lower.
    assert _never_by_policy(_action("os.update.apply", {"reboot": "now"}, risk="write"))


def test_missing_or_unknown_risk_is_refused():
    assert _never_by_policy(_action("app.restart", {"app_id": "x"}, risk=None))
    assert _never_by_policy(_action("app.restart", {"app_id": "x"}, risk="harmless"))
    assert registry.effective_risk("not.a.type") is None
    assert registry.effective_risk("not.a.type", None, "write") == "write"
    assert registry.effective_risk("app.restart", None, "bogus") is None


def test_effective_risk_is_the_higher_of_the_two():
    assert registry.effective_risk("app.restart", None, "sensitive") == "sensitive"
    assert registry.effective_risk("app.remove", {"delete_data": True}, "sensitive") == "destructive"


def test_feature_registration_feeds_the_table_and_checks_consistency(client):
    acts = client.app.state.actions

    def run(a, finish):
        finish(ExecResult("succeeded", "ok"))

    acts.register_type("test.risk.fresh", FeatureAction(risk="write", run=run))
    assert registry.TYPES["test.risk.fresh"].risk == "write"
    assert registry.policy_may_cover("test.risk.fresh") is None  # write: a rule may name it
    # a type the table already holds must agree on its class
    with pytest.raises(ValueError, match="risk table"):
        registry.register_feature("app.restart", "destructive")
    with pytest.raises(ValueError, match="unknown risk"):
        registry.register_feature("test.risk.bad", "mild")
    assert "test.risk.bad" not in registry.TYPES


def test_a_feature_whose_params_raise_it_is_not_covered(client):
    """A write-base feature whose risk_for returns destructive is never covered by a rule."""
    acts = client.app.state.actions

    def run(a, finish):
        finish(ExecResult("succeeded", "ok"))

    acts.register_type("test.risk.raised", FeatureAction(
        risk="write", run=run, risk_for=lambda p: "destructive" if p.get("wipe") else "write"))
    assert not _never_by_policy(_action("test.risk.raised", {}, risk="write"))
    assert _never_by_policy(_action("test.risk.raised", {"wipe": True}, risk="destructive"))
