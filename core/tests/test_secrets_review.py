# SPDX-License-Identifier: Apache-2.0
"""Security review of app secrets and the F-7 override after the merge with the app lifecycle and identity.

Each test proves one property of docs/leap/core/SECRETS.md §6: a value leaves the box nowhere (logs, audit,
events, errors, reads), only the owner writes, the override stays off, the scan gate keeps blocked tiers.
"""

import base64
import json
import logging
import os
from datetime import timedelta

import pytest
import yaml

from conftest import ADULT, AGENT, GUEST, OWNER, action_body, write_scan
from onemind_core.appsecrets.crypto import seal_values
from test_owner_override import OK, approve, enabled, fail_scan
from test_owner_override import on  # noqa: F401  (fixture)
from test_secrets import (
    API_KEY, APP, CRED, INTERNAL, NEW_KEY, PASSWORD, audit_text, everything_the_gateway_wrote, install, installed,
    request, sealed_for, stored,
)


def forms(value: str) -> list[str]:
    return [value, base64.b64encode(value.encode()).decode()]


def configure_body(clock, key):
    body = action_body(clock, app_id=APP, type_="app.configure", key=key)
    body["params"]["settings"] = {"LANG": "en"}
    return body


def collect_events(client):
    seen = []
    client.app.state.events.subscribe("*.>", seen.append)  # every type, as an SSE subscriber would get them
    return seen


# ---- values leave the box nowhere ---------------------------------------------------------------
def test_no_value_reaches_logs_events_audit_errors_or_reads(client, clock, settings, caplog):
    caplog.set_level(logging.DEBUG)
    events = collect_events(client)
    installed(client, clock)
    wrong = client.post(f"/v1/apps/{APP}/secrets", json={"sealed": sealed_for(client, {CRED: {"PROVIDER_API_KEY": "x"}}, "other")},
                        headers=OWNER)
    assert wrong.status_code == 422
    r = client.post(f"/v1/apps/{APP}/secrets", json={"sealed": sealed_for(client, {CRED: {"PROVIDER_API_KEY": NEW_KEY}}),
                                                     "generate": [f"{INTERNAL}/SESSION_SECRET"]}, headers=OWNER)
    assert r.status_code == 202
    ok = client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert ok.status_code == 200
    # an error answer for a bad form, a bad key and a replayed approval: none may quote input
    bad = client.post(f"/v1/apps/{APP}/secrets", json={"sealed": {"epk": "x", "ct": NEW_KEY}}, headers=OWNER)
    again = client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    reads = [client.get(p, headers=h).text for h in (OWNER, ADULT, AGENT) for p in
             (f"/v1/apps/{APP}/secrets", "/v1/apps", f"/v1/apps/{APP}", "/v1/actions", "/v1/secrets/public-key",
              f"/v1/audit/events?limit=200")]
    generated = client.app.state.app_secrets.materialize(client.app.state.catalog.get(APP))[1].data["SESSION_SECRET"]
    haystack = "\n".join([everything_the_gateway_wrote(client, settings), bad.text, again.text, caplog.text, *reads,
                          json.dumps(events, default=str)])
    for value in (API_KEY, NEW_KEY, PASSWORD, generated):
        for form in forms(value):
            assert form not in haystack
    assert events, "the review must have seen real events"


def test_stored_values_are_ciphertext_in_the_database(client, clock, settings):
    installed(client, clock)
    rows, _ = stored(client)
    for row in rows.values():
        assert row.ciphertext and API_KEY.encode() not in row.ciphertext and PASSWORD.encode() not in row.ciphertext
    # and the whole database file holds no plaintext (the sqlite leg; PostgreSQL holds the same bytes)
    if settings.db_url.startswith("sqlite:///"):
        raw = open(settings.db_url[len("sqlite:///"):], "rb").read()
        assert API_KEY.encode() not in raw and PASSWORD.encode() not in raw


def test_settings_configure_reapplies_stored_secrets_without_leaking(client, clock, executor, settings):
    """app.configure with plain settings (lifecycle) shares the type with secret changes (here)."""
    installed(client, clock)
    r = client.post("/v1/actions", headers=OWNER, json=configure_body(clock, "cfg"))
    assert r.status_code == 201, r.text
    ok = client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert ok.status_code == 200 and ok.json()["state"] == "succeeded", ok.text
    cred, _internal = executor.secrets[-1]
    assert cred.data["PROVIDER_API_KEY"] == API_KEY  # current values travel to the executor, never into a result
    for value in (API_KEY, PASSWORD):
        for form in forms(value):
            assert form not in everything_the_gateway_wrote(client, settings) + ok.text


def test_settings_configure_refuses_sealed_values(client, clock):
    installed(client, clock)
    r = client.post("/v1/actions", headers=OWNER, json=configure_body(clock, "cfg2"))
    sealed = sealed_for(client, {CRED: {"PROVIDER_API_KEY": NEW_KEY}})
    refused = client.post(f"/v1/actions/{r.json()['id']}/approve", json={"sealed": sealed}, headers=OWNER)
    assert refused.status_code == 422 and NEW_KEY not in refused.text


# ---- who may do what -------------------------------------------------------------------------------
@pytest.mark.parametrize("headers", [AGENT, GUEST, ADULT], ids=["agent", "guest", "adult"])
def test_only_the_owner_files_or_approves_secret_changes(client, clock, executor, settings, headers):
    installed(client, clock)
    calls = list(executor.calls)
    body = {"sealed": sealed_for(client, {CRED: {"PROVIDER_API_KEY": NEW_KEY}})}
    assert client.post(f"/v1/apps/{APP}/secrets", json=body, headers=headers).status_code == 403
    owner_filed = client.post(f"/v1/apps/{APP}/secrets", json={"generate": [f"{INTERNAL}/SESSION_SECRET"]}, headers=OWNER)
    assert client.post(f"/v1/actions/{owner_filed.json()['id']}/approve", headers=headers).status_code == 403
    assert client.post(f"/v1/actions/{owner_filed.json()['id']}/deny", headers=headers).status_code == 403
    assert executor.calls == calls
    assert NEW_KEY not in audit_text(settings)


@pytest.mark.parametrize("headers", [AGENT, GUEST, ADULT], ids=["agent", "guest", "adult"])
def test_no_non_owner_can_enter_values_with_an_install_approval(client, clock, executor, headers):
    aid = request(client, clock)
    sealed = sealed_for(client, {CRED: {"PROVIDER_API_KEY": API_KEY}})
    assert client.post(f"/v1/actions/{aid}/approve", json={"sealed": sealed}, headers=headers).status_code == 403
    assert executor.calls == [] and stored(client)[0] == {}


def test_no_route_returns_a_stored_value(client):
    """Every route that mentions secrets is listed here; none other than these may exist."""
    paths = {(m, r.path) for r in client.app.routes for m in getattr(r, "methods", ()) or () if "secret" in r.path}
    assert paths == {("GET", "/v1/secrets/public-key"), ("GET", "/v1/apps/{app_id}/secrets"),
                     ("POST", "/v1/apps/{app_id}/secrets")}


def test_secret_names_follow_per_app_sharing(client):
    """An app hidden from a person (contract 12.6) does not show its secret names either."""
    gw = client.app.state.gateway
    gw.app_filters.append(lambda request, p, app_id: p.is_owner)
    assert client.get(f"/v1/apps/{APP}/secrets", headers=OWNER).status_code == 200
    for headers in (ADULT, AGENT):
        r = client.get(f"/v1/apps/{APP}/secrets", headers=headers)
        assert r.status_code == 404 and "PROVIDER_API_KEY" not in r.text


def test_secrets_need_a_credential(client):
    for method, path in (("GET", f"/v1/apps/{APP}/secrets"), ("POST", f"/v1/apps/{APP}/secrets"),
                         ("GET", "/v1/secrets/public-key"), ("GET", f"/v1/apps/{APP}/owner-override")):
        assert client.request(method, path, json={}).status_code == 401


# ---- the F-7 override stays off ----------------------------------------------------------------------
def test_override_is_off_by_default_and_nothing_at_runtime_turns_it_on(client, clock, settings, executor):
    assert client.app.state.owner_override.enabled is False
    routes = {(m, r.path) for r in client.app.routes for m in getattr(r, "methods", ()) or () if "override" in r.path}
    assert routes == {("GET", "/v1/apps/{app_id}/owner-override")}  # a read; nothing writes the switch
    fail_scan(settings, clock)
    aid = client.post("/v1/actions", headers=OWNER, json=action_body(clock, app_id="uptime-kuma", key="o1")).json()["id"]
    for headers in (OWNER,):
        for attempt in (OK, {**OK, "enabled": True}):
            r = client.post(f"/v1/actions/{aid}/approve", json={"override": attempt}, headers=headers)
            assert r.status_code in (403, 422)
    assert client.get(f"/v1/actions/{aid}", headers=OWNER).json()["state"] == "awaiting_approval"
    assert executor.calls == []


def test_override_env_only_one_value_turns_it_on(monkeypatch):
    from onemind_core.override import ENV, OwnerOverrideSettings

    for off in ({}, {ENV: ""}, {ENV: "0"}, {ENV: "false"}, {"ONEMIND_OVERRIDE_ENABLED": "1"}, {"ONEMIND_ALLOW_UNSCANNED": "1"}):
        assert OwnerOverrideSettings.from_env(off).enabled is False
    assert OwnerOverrideSettings.from_env({ENV: "1"}).enabled is True


def test_override_never_lifts_a_blocked_tier(on, clock, settings):
    """Contract 9.4: tier blocked is a human review; the owner override covers scan findings only."""
    d = settings.apps_dir / "uptime-kuma"
    manifest = d / "onemind.app.yaml"
    doc = yaml.safe_load(manifest.read_text())
    doc.setdefault("metadata", {})["tier"] = "blocked"
    manifest.write_text(yaml.safe_dump(doc))
    aid = on.post("/v1/actions", headers=OWNER, json=action_body(clock, app_id="uptime-kuma", key="b1")).json()["id"]
    r = approve(on, aid, OK)
    assert r.status_code == 409 and "tier blocked" in r.json()["message"]
    assert on.executor.calls == []
