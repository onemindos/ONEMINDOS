# SPDX-License-Identifier: Apache-2.0
"""Private Git export, dry run and the owner-only, revision-bound apply workflow."""

import json
from shutil import copyfile

import pytest
import yaml
from fastapi.testclient import TestClient

from conftest import ADULT, OWNER
from onemind_core.app import create_app
from onemind_core.automation.updatepolicy import UpdatePolicyRepository
from onemind_core.backups.store import DestinationRow
from onemind_core.boxbundle import config_export, manifest
from onemind_core.boxbundle.config_apply import SCHEMAS
from onemind_core.boxbundle.config_export import render
from test_identity import SoftAuthenticator, csrf, id_settings, register_passkey, setup_owner

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
    installed = tmp_path / manifest._IMAGE_SCHEMAS[0].relative_to("/")
    installed.parent.mkdir(parents=True)
    copyfile(manifest._REPO_SCHEMA, installed)
    monkeypatch.setattr(manifest, "_REPO_SCHEMA", tmp_path / "missing-checkout-schema")
    monkeypatch.setattr(manifest, "_IMAGE_SCHEMAS", [installed])
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
