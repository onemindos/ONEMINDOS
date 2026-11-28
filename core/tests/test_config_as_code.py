# SPDX-License-Identifier: Apache-2.0
"""Private Git export, dry run and the owner-only, revision-bound apply workflow."""

import json
from dataclasses import replace
from shutil import copyfile
from uuid import uuid4

import pytest
import yaml
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, OWNER, make_client
from onemind_core.app import create_app
from onemind_core.automation.cron import WEEKDAYS
from onemind_core.automation.updatepolicy import UpdatePolicyRepository
from onemind_core.backups.store import DestinationRow
from onemind_core.boxbundle import config_export, manifest
from onemind_core.boxbundle.config_apply import SCHEMAS
from onemind_core.boxbundle.config_export import render
from test_identity import SoftAuthenticator, csrf, id_settings, register_passkey, setup_owner
from test_mcp import call

EXPORT = "/v1/config/export"
DIFF = "/v1/config/diff"
APPLY = "/v1/config/apply"
SETTINGS = "/v1/onboarding/settings"
BODY = {"box_name": "home-hub", "time_zone": "UTC", "backup_choice": "later"}


def exported(client):
    response = client.get(EXPORT, headers=OWNER)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["yaml"] == response.json()["files"]["settings.yaml"]
    return response.json()["files"]


def proposed(client, name="new-hub"):
    doc = yaml.safe_load(exported(client)["settings.yaml"])
    doc["box"] = {"box_name": name, "time_zone": "UTC"}
    return {"settings.yaml": render(doc)}


def preview(client, files):
    response = client.post(DIFF, headers=OWNER, json={"files": files})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def file_request(client, files, dry_run, **headers):
    return client.post(APPLY, headers={**OWNER, **headers},
                       json={"files": files, "revision": dry_run["revision"]})


def test_export_survives_restart_and_installed_schema_path(settings, clock, monkeypatch, tmp_path):
    with TestClient(create_app(settings, clock=clock)) as client:
        assert client.put(SETTINGS, headers=OWNER, json=BODY).status_code == 200
        client.app.state.gateway.repo.set_app_state("uptime-kuma", "installed", clock.now)
        before = exported(client)
        assert set(before) == set(SCHEMAS)
        assert {name: yaml.safe_load(value)["schema"] for name, value in before.items()} == SCHEMAS
        assert preview(client, before)["changes"] == []

    # Emulate the installed filesystem with the repo copy unavailable and no warm schema cache.
    installed = tmp_path / manifest._APPLIANCE_SCHEMA.relative_to("/")
    installed.parent.mkdir(parents=True)
    copyfile(manifest._REPO_SCHEMA, installed)
    monkeypatch.setattr(manifest, "_REPO_SCHEMA", tmp_path / "missing-checkout-schema")
    monkeypatch.setattr(manifest, "_APPLIANCE_SCHEMA", installed)
    monkeypatch.setattr(manifest, "_CONTAINER_SCHEMA", tmp_path / "missing-container-schema")
    manifest.schema.cache_clear()
    try:
        with TestClient(create_app(settings, clock=clock)) as restarted:
            assert exported(restarted) == before
    finally:
        manifest.schema.cache_clear()
    events = [json.loads(line) for line in settings.audit_path.read_text().splitlines()]
    exports = [entry for entry in events if entry["event"] == "config.exported"]
    assert len(exports) == 2
    for event in exports:
        assert event["ts"] and event["principal"]["role"] == "owner"
        assert event["data"] == {"files": {
            name: {"schema": SCHEMAS[name], "sha256": manifest.sha256(yaml_text.encode())}
            for name, yaml_text in before.items()
        }}


def test_unavailable_export_schema_refuses_without_a_success_event(client, settings, monkeypatch):
    monkeypatch.setattr(config_export, "schema", lambda: {"$defs": {"boxConfig": {}}})
    response = client.get(EXPORT, headers=OWNER)
    assert response.status_code == 409
    assert '"event":"config.exported"' not in settings.audit_path.read_text()


@pytest.mark.parametrize("files", [
    {"network.yaml": "schema: onemind.io/config-as-code/network/v1"},
    {"settings.yaml": "schema: onemind.io/config-as-code/settings/v2"},
    {"settings.yaml": "schema: onemind.io/config-as-code/settings/v1\nschema: duplicate"},
    {"settings.yaml": "schema: onemind.io/config-as-code/settings/v1\nbox: &loop [*loop]"},
    {"settings.yaml": "schema: onemind.io/config-as-code/settings/v1\n---\n{}"},
    {"settings.yaml": """schema: onemind.io/config-as-code/settings/v1
box: {box_name: new-hub, time_zone: UTC, password: example}
backups: {choice: later, content_tier_apps: []}
updates: null
"""},
])
def test_bad_configuration_never_files_an_action(client, files):
    assert client.post(DIFF, headers=OWNER, json={"files": files}).status_code == 422
    assert file_request(client, files, {"revision": "0" * 64}).status_code == 422
    assert client.get("/v1/actions", headers=OWNER).json() == []


def test_apply_is_idempotent_and_only_changes_after_bound_owner_approval(client):
    assert client.put(SETTINGS, headers=OWNER, json=BODY).status_code == 200
    files = proposed(client)
    dry_run = preview(client, files)
    assert [change["file"] for change in dry_run["changes"]] == ["settings.yaml"]
    assert "home-hub" in dry_run["changes"][0]["before"]
    assert "new-hub" in dry_run["changes"][0]["after"]
    assert dry_run["blockers"] == []
    assert client.get("/v1/actions", headers=OWNER).json() == []

    key = {"Idempotency-Key": "config-test"}
    queued = file_request(client, files, dry_run, **key)
    assert queued.status_code == 202, queued.text
    action = queued.json()
    assert action["type"] == "config.apply" and action["state"] == "awaiting_approval"
    assert action["plan"]["params"]["patch"]["box"]["after"]["box_name"] == "new-hub"
    assert client.get(SETTINGS, headers=OWNER).json()["box_name"] == "home-hub"
    approval = f"/v1/actions/{action['id']}/approve"
    body = {"plan_sha256": action["plan_sha256"]}
    assert client.post(approval, headers=ADULT, json=body).status_code == 403
    assert client.post(approval, headers=OWNER).json()["reason"] == "plan_unchecked"
    assert client.post(approval, headers=OWNER, json={"plan_sha256": "wrong"}).json()["reason"] == "plan_changed"
    response = client.post(approval, headers=OWNER, json=body)
    assert response.status_code == 200 and response.json()["state"] == "succeeded", response.text
    assert client.get(SETTINGS, headers=OWNER).json()["box_name"] == "new-hub"
    assert preview(client, files)["changes"] == []

    replay = file_request(client, files, dry_run, **key)
    assert replay.headers["onemind-idempotent-replay"] == "true"
    assert replay.json()["id"] == action["id"] and replay.json()["state"] == "succeeded"
    assert file_request(client, proposed(client, "other-hub"), dry_run, **key).status_code == 409
    assert len(client.get("/v1/actions", headers=OWNER).json()) == 1


@pytest.mark.parametrize("reader", [AGENT, ADULT], ids=["agent", "adult"])
def test_config_action_history_only_shows_the_patch_to_the_owner(client, clock, reader):
    destination = "dst_0123456789abcdef"
    client.app.state.backups.repo.add_destination(DestinationRow(
        id=destination, kind="usb", label="Test USB", is_primary=True, append_only=False, config={},
        created_at=clock.now,
    ))
    assert client.put(SETTINGS, headers=OWNER,
                      json={**BODY, "backup_choice": "usb", "backup_destination_id": destination}).status_code == 200
    files = proposed(client)
    queued = file_request(client, files, preview(client, files))
    assert queued.status_code == 202, queued.text
    action = queued.json()
    patch = action["params"]["patch"]
    assert patch["box"]["before"]["backup_destination_id"] == destination
    assert patch["box"]["after"]["box_name"] == "new-hub"
    for url in ("/v1/actions", f"/v1/actions/{action['id']}"):
        owner = client.get(url, headers=OWNER)
        assert owner.status_code == 200, owner.text
        row = owner.json()[0] if isinstance(owner.json(), list) else owner.json()
        assert row["params"]["patch"] == row["plan"]["params"]["patch"] == patch
        assert row["plan_sha256"] == action["plan_sha256"]
        other = client.get(url, headers=reader)
        assert other.status_code == 200, other.text
        row = other.json()[0] if isinstance(other.json(), list) else other.json()
        assert row["id"] == action["id"] and row["state"] == "awaiting_approval"
        assert row["params"] == {} and row.get("plan") is None and row.get("plan_sha256") is None


@pytest.fixture
def matching_agent_id(settings, tmp_path):
    tokens = yaml.safe_load(settings.tokens_file.read_text())
    principals = tokens["tokens"]
    principals[AGENT["Authorization"].removeprefix("Bearer ")]["id"] = "owner"
    token_file = tmp_path / "tokens.yaml"
    token_file.write_text(yaml.safe_dump(tokens))
    return token_file


def test_config_action_is_not_an_agent_mcp_request_even_if_principal_ids_match(settings, clock, matching_agent_id):
    with make_client(settings, clock, tokens_file=matching_agent_id) as client:
        files = proposed(client)
        queued = file_request(client, files, preview(client, files))
        assert queued.status_code == 202, queued.text
        action = queued.json()
        listing = call(client, "list_actions")["result"]
        assert listing["isError"] is False and listing["structuredContent"]["actions"] == []
        detail = call(client, "get_action", {"action_id": action["id"]})["result"]
        assert detail["isError"] is True and detail["structuredContent"]["error"] == "not_found"
        audit = call(client, "search_audit", {"event": "action.*"})["result"]
        assert audit["isError"] is False and audit["structuredContent"]["entries"] == []


@pytest.mark.parametrize("legacy_agent_request", [False, True], ids=["shared-id", "legacy-agent"])
def test_agent_cancellation_preserves_owner_config_and_redacts_audit(
    settings, clock, matching_agent_id, monkeypatch, legacy_agent_request,
):
    with make_client(settings, clock, tokens_file=matching_agent_id) as client:
        gateway = client.app.state.gateway
        published = []
        monkeypatch.setattr(gateway.audit, "publish", lambda _, line: published.append(json.loads(line)))
        files = proposed(client)
        queued = file_request(client, files, preview(client, files))
        assert queued.status_code == 202, queued.text
        action_id = queued.json()["id"]
        if legacy_agent_request:
            # Exercise cancellation redaction with a stored config action even though new ones require an owner.
            stored = gateway.repo.get(action_id)
            legacy, created = gateway.repo.create(replace(
                stored, id=str(uuid4()), idempotency_key="legacy-config",
                requested_by={"kind": "agent", "id": "owner"},
            ))
            assert created

        response = client.post("/v1/agents/owner/cancel", headers=OWNER)
        assert response.status_code == 200, response.text
        action = client.get(f"/v1/actions/{action_id}", headers=OWNER).json()
        assert action["state"] == "awaiting_approval"
        assert response.json()["requests_cancelled"] == int(legacy_agent_request)
        decisions = [row for row in published if row["event"] == "action.denied"]
        if legacy_agent_request:
            cancelled = client.get(f"/v1/actions/{legacy.id}", headers=OWNER).json()
            assert cancelled["state"] == "cancelled"
            assert [row["action_id"] for row in decisions] == [legacy.id]
        else:
            assert decisions == []
        records = [json.loads(line) for line in settings.audit_path.read_text().splitlines()]
        assert decisions == [row for row in records if row["event"] == "action.denied"]
        assert all("patch" not in row["data"].get("params", {}) for row in decisions)


def test_config_action_audit_records_decisions_without_publishing_the_patch(client, settings, monkeypatch):
    published = []
    monkeypatch.setattr(client.app.state.gateway.audit, "publish", lambda _, line: published.append(json.loads(line)))
    assert client.put(SETTINGS, headers=OWNER, json=BODY).status_code == 200
    for decision, event in (("approve", "action.approved"), ("deny", "action.denied")):
        files = proposed(client, f"{decision}-hub")
        queued = file_request(client, files, preview(client, files))
        assert queued.status_code == 202, queued.text
        action = queued.json()
        response = client.post(f"/v1/actions/{action['id']}/{decision}", headers=OWNER,
                               json={"plan_sha256": action["plan_sha256"]})
        assert response.status_code == 200, response.text
        records = [json.loads(line) for line in settings.audit_path.read_text().splitlines()]
        events = {row["event"]: row for row in records if row["action_id"] == action["id"]}
        assert events["action.requested"]["principal"]["role"] == "owner"
        assert events[event]["principal"]["role"] == "owner"
        assert all("patch" not in row["data"].get("params", {}) for row in events.values())
        assert [row for row in published if row["action_id"] == action["id"]] == list(events.values())


def test_legacy_config_audit_patch_is_owner_only(client):
    files = proposed(client)
    queued = file_request(client, files, preview(client, files))
    assert queued.status_code == 202, queued.text
    action = queued.json()
    audit = client.app.state.gateway.audit
    # Older builds wrote the full parameters, even on denial where the action type was omitted.
    for event, details in (("action.requested", {"type": action["type"]}), ("action.denied", {})):
        audit.append(event, None, action["id"], {**details, "params": action["params"]})
    url = "/v1/audit/events"
    owner = client.get(url, headers=OWNER, params={"action_id": action["id"]})
    assert owner.status_code == 200, owner.text
    legacy = [row for row in owner.json() if row["principal"] is None and "params" in row["data"]]
    assert len(legacy) == 2
    adult = client.get(url, headers=ADULT, params={"action_id": action["id"]})
    assert adult.status_code == 200, adult.text
    assert {row["seq"] for row in adult.json()}.isdisjoint(row["seq"] for row in legacy)
    for row in legacy:
        assert client.get(f"{url}/{row['seq']}", headers=OWNER).json() == row
        assert client.get(f"{url}/{row['seq']}", headers=ADULT).status_code == 404
    assert client.get("/v1/audit/verify", headers=OWNER).json()["ok"]


def test_live_off_hours_defaults_export_and_compare_without_changes(client):
    off = [
        {"start": "23:00", "end": "07:00", "days": None},
        {"start": "08:00", "end": "09:00", "days": []},
        {"start": "10:00", "end": "11:00"},
        {"start": "12:00", "end": "13:00", "days": ["fri", "sat"]},
    ]
    saved = client.put("/v1/update-policy", headers=OWNER, json={"ai_schedule": {"off": off}})
    assert saved.status_code == 200, saved.text
    assert saved.json()["ai_schedule"]["off"] == off

    files = exported(client)
    exported_off = yaml.safe_load(files["settings.yaml"])["updates"]["ai_schedule"]["off"]
    assert exported_off == [{**entry, "days": list(WEEKDAYS)} for entry in off[:3]] + off[3:]
    assert preview(client, files)["changes"] == []


def test_legacy_v1_off_hours_days_remain_readable_for_diff_and_apply(client):
    off = [{"start": "23:00", "end": "07:00", "days": list(WEEKDAYS)}]
    saved = client.put("/v1/update-policy", headers=OWNER, json={"ai_schedule": {"off": off}})
    assert saved.status_code == 200, saved.text
    doc = yaml.safe_load(exported(client)["settings.yaml"])
    doc["updates"]["ai_schedule"]["off"][0]["days"] = None
    assert preview(client, {"settings.yaml": render(doc)})["changes"] == []

    doc["box"] = {"box_name": "recovered-hub", "time_zone": "UTC"}
    files = {"settings.yaml": render(doc)}
    dry_run = preview(client, files)
    queued = file_request(client, files, dry_run)
    assert queued.status_code == 202, queued.text
    action = queued.json()
    assert set(action["params"]["patch"]) == {"box"}
    approved = client.post(f"/v1/actions/{action['id']}/approve", headers=OWNER,
                           json={"plan_sha256": action["plan_sha256"]})
    assert approved.status_code == 200 and approved.json()["state"] == "succeeded", approved.text
    assert preview(client, files)["changes"] == []


def test_config_update_policy_records_the_approving_owner(client):
    files = exported(client)
    settings = yaml.safe_load(files["settings.yaml"])
    policy = client.get("/v1/update-policy", headers=OWNER).json()
    settings["updates"] = {key: policy[key] for key in (
        "window_id", "cool_off_hours", "same_major_only", "backoff_after_failures", "ai_schedule",
    )}
    settings["updates"]["cool_off_hours"] = 48
    proposal = {"settings.yaml": render(settings)}
    queued = file_request(client, proposal, preview(client, proposal))
    assert queued.status_code == 202, queued.text
    action = queued.json()
    response = client.post(f"/v1/actions/{action['id']}/approve", headers=OWNER,
                           json={"plan_sha256": action["plan_sha256"]})
    assert response.status_code == 200 and response.json()["state"] == "succeeded", response.text
    approver = response.json()["decided_by"]
    assert approver["role"] == "owner"
    updated = client.get("/v1/update-policy", headers=OWNER).json()
    assert updated["cool_off_hours"] == 48
    assert updated["updated_by"] == approver


def test_revision_covers_both_proposal_and_live_configuration(client):
    files = proposed(client)
    dry_run = preview(client, files)
    assert file_request(client, proposed(client, "different-hub"), dry_run).status_code == 409
    assert client.put(SETTINGS, headers=OWNER, json=BODY).status_code == 200
    assert file_request(client, files, dry_run).status_code == 409
    queued = file_request(client, files, preview(client, files))
    assert queued.status_code == 202, queued.text

    # A later config write makes approval stale even though its plan fingerprint still matches.
    assert client.put(SETTINGS, headers=OWNER, json={**BODY, "box_name": "different-hub"}).status_code == 200
    action = queued.json()
    refused = client.post(f"/v1/actions/{action['id']}/approve", headers=OWNER,
                          json={"plan_sha256": action["plan_sha256"]})
    assert refused.status_code == 409 and refused.json()["error"] == "stale_precondition"
    assert client.get(SETTINGS, headers=OWNER).json()["box_name"] == "different-hub"


def test_inventory_diff_reports_the_normal_management_path(client):
    doc = yaml.safe_load(exported(client)["users.yaml"])
    doc["users"].append({"id": "example", "username": "example", "display_name": "Example",
                         "role": "adult", "disabled": False})
    files = {"users.yaml": render(doc)}
    dry_run = preview(client, files)
    assert dry_run["changes"][0]["file"] == "users.yaml"
    assert "People" in dry_run["blockers"][0]
    assert file_request(client, files, dry_run).status_code == 422
    assert client.get("/v1/actions", headers=OWNER).json() == []


def test_approval_updates_copy_cadence_and_policy_without_losing_resumes(client, clock):
    assert client.put(SETTINGS, headers=OWNER, json=BODY).status_code == 200
    backups = client.app.state.backups.repo
    destination = "dst_0123456789abcdef"
    backups.add_destination(DestinationRow(id=destination, kind="usb", label="Test USB",
        is_primary=True, append_only=False, config={}, created_at=clock.now))
    policy = UpdatePolicyRepository(client.app.state.gateway.db)
    custom = client.get("/v1/update-policy", headers=OWNER).json()
    doc = {key: custom[key] for key in ("window_id", "cool_off_hours", "same_major_only",
                                        "backoff_after_failures", "ai_schedule")}
    resumed = {"uptime-kuma": "2026-11-27T00:00:00Z"}
    policy.put(now=clock.now, doc=doc, resumed=resumed)
    live = exported(client)
    schedules, settings = yaml.safe_load(live["schedules.yaml"]), yaml.safe_load(live["settings.yaml"])
    schedules["destination_copies"][0]["cadence"] = "daily"
    settings["updates"] = None
    files = {"settings.yaml": render(settings), "schedules.yaml": render(schedules)}
    queued = file_request(client, files, preview(client, files))
    assert queued.status_code == 202, queued.text
    assert backups.destinations()[0].copy_cadence == "manual" and policy.get()["doc"] == doc
    action = queued.json()
    response = client.post(f"/v1/actions/{action['id']}/approve", headers=OWNER,
                           json={"plan_sha256": action["plan_sha256"]})
    assert response.status_code == 200 and response.json()["state"] == "succeeded", response.text
    assert backups.destinations()[0].copy_cadence == "daily"
    assert policy.get()["doc"] is None and policy.get()["resumed"] == resumed
    assert preview(client, files)["changes"] == []


def test_config_approval_uses_existing_passkey_guard(settings, clock):
    with TestClient(create_app(id_settings(settings), clock=clock)) as client:
        setup_owner(client)
        key = SoftAuthenticator()
        register_passkey(client, key)
        files = proposed(client)
        queued = file_request(client, files, preview(client, files))
        assert queued.status_code == 202, queued.text
        action = queued.json()
        approval = f"/v1/actions/{action['id']}"
        body = {"plan_sha256": action["plan_sha256"]}
        refused = client.post(f"{approval}/approve", headers=OWNER, json=body)
        assert refused.status_code == 401 and refused.json()["reason"] == "step_up_required"
        options = client.post(f"{approval}/approve-options", headers=csrf(client)).json()
        approved = client.post(f"{approval}/approve", headers=csrf(client),
                               json={**body, "webauthn": key.assert_(options["challenge"])})
        assert approved.status_code == 200 and approved.json()["state"] == "succeeded", approved.text
