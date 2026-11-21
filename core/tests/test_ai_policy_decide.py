# SPDX-License-Identifier: Apache-2.0
"""The stable aiPolicy decision interface (#165): deny by default, per destination."""

import pytest

from onemind_core import ai_policy as ap

DESTS = sorted(ap.DESTINATIONS)
MODEL_OR_TOOL = [ap.MCP_TOOL, ap.LOCAL_MODEL, ap.REMOTE_MODEL, ap.OFFICIAL_MCP]


@pytest.mark.parametrize("dest", DESTS)
def test_allowed_goes_everywhere(dest):
    assert ap.decide("allowed", dest).allowed


@pytest.mark.parametrize("policy", ["display-only", "prohibited"])
@pytest.mark.parametrize("dest", DESTS)
def test_ai_no_never_reaches_a_model_or_tool(policy, dest):
    assert not ap.decide(policy, dest, consented=True).allowed


@pytest.mark.parametrize("policy", ["local-only", "", "ALLOWED", None, False, True, 1, ["allowed"], {"allowed": 1}, b"allowed"])
@pytest.mark.parametrize("dest", DESTS)
def test_unknown_or_malformed_policy_denies(policy, dest):
    assert not ap.decide(policy, dest, consented=True).allowed


@pytest.mark.parametrize("dest", ["", "model", None, "LOCAL-MODEL"])
def test_unknown_destination_denies(dest):
    assert not ap.decide("allowed", dest).allowed


@pytest.mark.parametrize("dest", MODEL_OR_TOOL)
def test_absent_policy_sends_no_data(dest):
    assert not ap.decide(ap.ABSENT, dest, consented=True).allowed


def test_absent_policy_keeps_legacy_catalog_metadata():
    assert ap.decide(ap.ABSENT, ap.CATALOG).allowed


@pytest.mark.parametrize("dest", DESTS)
def test_consent_required_needs_stored_consent(dest):
    refused = ap.decide("consent-required", dest)
    assert not refused.allowed and refused.needs_consent
    assert ap.decide("consent-required", dest, consented=True).allowed
    assert not ap.decide("consent-required", dest, consented="yes").allowed  # only a real True counts


@pytest.mark.parametrize("dest", DESTS)
def test_official_mcp_only(dest):
    assert ap.decide("official-mcp-only", dest, consented=True).allowed is (dest == ap.OFFICIAL_MCP)


def test_manifest_defaults_health_to_display_only():
    health = {"metadata": {"category": "health"}, "spec": {}}
    plain = {"metadata": {"category": "productivity"}, "spec": {}}
    for dest in MODEL_OR_TOOL:
        assert not ap.decide_for_manifest(health, dest).allowed
        assert not ap.decide_for_manifest(plain, dest).allowed
    assert not ap.decide_for_manifest(health, ap.CATALOG).allowed
    assert ap.decide_for_manifest(plain, ap.CATALOG).allowed


def test_manifest_explicit_null_is_not_absent():
    assert not ap.decide_for_manifest({"spec": {"aiPolicy": None}}, ap.CATALOG).allowed


def test_require_raises_with_the_decision():
    with pytest.raises(ap.AIPolicyDenied) as err:
        ap.require({"spec": {"aiPolicy": "prohibited"}}, ap.REMOTE_MODEL)
    assert not err.value.decision.allowed
    ap.require({"spec": {"aiPolicy": "allowed"}}, ap.REMOTE_MODEL)
