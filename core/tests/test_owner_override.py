# SPDX-License-Identifier: Apache-2.0
"""F-7 owner override: off by default; when on, owner-only, typed, reasoned, passkey-gated, marked red."""

import json
import os
from dataclasses import replace
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, OWNER, ScriptedExecutor, action_body, write_scan
from onemind_core.app import create_app
from onemind_core.config import Settings
from onemind_core.override import OwnerOverrideSettings

APP = "uptime-kuma"
REASON = "I read the CVE list and accept the risk"


def enabled(settings):
    return replace(settings, sections={**settings.sections, "override": OwnerOverrideSettings(enabled=True)})


# What app-gate writes for an image ClamAV scanned with a known signature database.
CLEAN = [{"ref": "x", "clamav": {"signatures": "daily-1", "infected": 0}}]


def fail_scan(settings, clock, app_id=APP, images=CLEAN, result="fail", age=timedelta(hours=1)):
    path = settings.apps_dir / app_id / "scan.json"
    write_scan(settings.apps_dir / app_id, clock.now - age, result=result)
    doc = json.loads(path.read_text())
    doc["images"] = images
    path.write_text(json.dumps(doc))


def audit(settings):
    return [json.loads(line) for line in settings.audit_path.read_text().splitlines()]


def request(c, clock, headers=OWNER, key="k1", app_id=APP, type_="app.install"):
    r = c.post("/v1/actions", json=action_body(clock, app_id=app_id, type_=type_, key=key), headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def approve(c, aid, override=None, **extra):
    body = {**({"override": override} if override is not None else {}), **extra}
    return c.post(f"/v1/actions/{aid}/approve", json=body or None, headers=OWNER)


OK = {"reason": REASON, "confirm": APP}


@pytest.fixture
def on(settings, clock):
    fail_scan(settings, clock)
    ex = ScriptedExecutor()
    with TestClient(create_app(enabled(settings), clock=clock, executor=ex)) as c:
        c.executor = ex
        yield c


def test_off_by_default_and_audited(client, clock, settings, executor):
    fail_scan(settings, clock)
    aid = request(client, clock)
    r = approve(client, aid)
    assert r.status_code == 409 and "failed its last scan" in r.json()["message"]
    r = approve(client, aid, OK)
    assert r.status_code == 403 and "ONEMIND_ALLOW_OWNER_OVERRIDE" in r.json()["message"]
    denied = [e for e in audit(settings) if e["event"] == "authz.denied"]
    assert denied[-1]["data"]["reason"] == "owner_override_disabled"
    assert client.get(f"/v1/actions/{aid}", headers=OWNER).json()["state"] == "awaiting_approval"
    assert executor.calls == []
    assert client.get(f"/v1/apps/{APP}/owner-override", headers=OWNER).json()["enabled"] is False


def test_override_installs_and_leaves_a_red_mark(on, clock, settings):
    aid = request(on, clock)
    r = approve(on, aid, OK)
    assert r.status_code == 200 and r.json()["state"] == "succeeded", r.text
    assert on.executor.calls == [("app.install", APP)]
    assert r.json()["result"]["owner_override"] == {"mark": f"owner override: {REASON}", "approved_by": "owner"}
    lines = audit(settings)
    (mark,) = [e for e in lines if e["event"] == "app.owner_override"]
    assert mark["action_id"] == aid and mark["data"]["severity"] == "critical"
    payload = mark["data"]["payload"]
    assert payload["mark"] == f"owner override: {REASON}" and payload["tone"] == "red"
    assert payload["confirmed"] == APP and payload["step_up"] == "none (no passkeys registered)"
    assert payload["scan"]["result"] == "fail" and payload["scan"]["malware"] == 0
    (approved,) = [e for e in lines if e["event"] == "action.approved"]
    assert approved["data"]["owner_override"] is True
    assert any(e["event"] == "security.owner_override.enabled" for e in lines)


@pytest.mark.parametrize("override,status,needle", [
    ({"reason": REASON, "confirm": "uptime"}, 422, "typed exactly"),
    ({"reason": REASON, "confirm": "UPTIME-KUMA"}, 422, "typed exactly"),
    ({"reason": "because", "confirm": APP}, 422, "10 to 500"),
    ({"reason": "   ", "confirm": APP}, 422, "10 to 500"),
])
def test_override_needs_confirmation_and_reason(on, clock, override, status, needle):
    aid = request(on, clock)
    r = approve(on, aid, override)
    assert r.status_code == status and needle in r.json()["message"]
    assert on.get(f"/v1/actions/{aid}", headers=OWNER).json()["state"] == "awaiting_approval"
    assert on.executor.calls == []


def test_override_body_rejects_unknown_fields(on, clock):
    aid = request(on, clock)
    assert approve(on, aid, {**OK, "skip_everything": True}).status_code == 422


def test_never_for_an_agent_request(on, clock):
    aid = request(on, clock, headers=AGENT)
    r = approve(on, aid, OK)
    assert r.status_code == 409 and "needs an install the owner requested" in r.json()["message"]
    # the owner requests it themselves, then overrides
    assert approve(on, request(on, clock, key="mine"), OK).json()["state"] == "succeeded"


@pytest.mark.parametrize("images,needle", [
    ([{"ref": "x", "clamav": {"infected": 2}}], "found malware"),
    ([{"ref": "x"}, {"ref": "y", "clamav": {"signatures": "daily-1", "infected": 1}}], "found malware"),
    ([{"ref": "x"}], "does not say whether malware"),
    ([{"ref": "x", "clamav": {"signatures": "daily-1", "infected": "0"}}], "does not say whether malware"),
    # app-gate skips an image whose pin check failed: ClamAV ran on nothing
    ([], "does not say whether malware"),
    (None, "does not say whether malware"),
    # app-gate's mark for a run without a signature database
    ([{"ref": "x", "clamav": {"signatures": "daily-unknown", "infected": 0}}], "does not say whether malware"),
    ([*CLEAN, {"ref": "y", "clamav": {"infected": 0}}], "does not say whether malware"),
])
def test_never_over_malware_or_unknown_malware(on, clock, settings, images, needle):
    fail_scan(settings, clock, images=images)
    aid = request(on, clock)
    r = approve(on, aid, OK)
    assert r.status_code == 409 and needle in r.json()["message"]


def test_never_without_a_scan_record(on, clock, settings):
    write_scan(settings.apps_dir / APP, None)
    r = approve(on, request(on, clock), OK)
    assert r.status_code == 409 and "no scan record" in r.json()["message"]


def test_stale_passing_scan_can_be_overridden(on, clock, settings):
    fail_scan(settings, clock, result="pass", age=timedelta(days=10))
    assert approve(on, request(on, clock), OK).json()["state"] == "succeeded"


def test_passing_scan_ignores_the_override(on, clock, settings):
    write_scan(settings.apps_dir / APP, clock.now - timedelta(days=1))
    r = approve(on, request(on, clock), OK)
    assert r.json()["state"] == "succeeded" and "owner_override" not in r.json()["result"]
    assert not any(e["event"] == "app.owner_override" for e in audit(settings))


def test_only_for_app_install(on, clock):
    on.post("/v1/actions/" + request(on, clock) + "/approve", json={"override": OK}, headers=OWNER)
    rid = request(on, clock, key="rm", type_="app.remove")
    r = approve(on, rid, OK)
    assert r.status_code == 422 and "only to app.install" in r.json()["message"]


@pytest.mark.parametrize("headers", [ADULT, AGENT])
def test_non_owners_cannot_override(on, clock, headers):
    aid = request(on, clock)
    r = on.post(f"/v1/actions/{aid}/approve", json={"override": OK}, headers=headers)
    assert r.status_code == 403
    assert on.get(f"/v1/apps/{APP}/owner-override", headers=headers).status_code == 403


class Passkeys:
    def __init__(self, active):
        self.active = active

    def passkeys_active(self):
        return self.active


def test_passkey_step_up_once_identity_has_passkeys(on, clock, settings):
    on.app.state.owner_override.step_up = Passkeys(True)
    aid = request(on, clock)
    r = approve(on, aid, OK)
    assert r.status_code == 401 and "passkey" in r.json()["message"]
    assert on.get(f"/v1/apps/{APP}/owner-override", headers=OWNER).json()["step_up"] == "passkey"
    # the identity feature's approval guard verifies the assertion before the action service runs
    r = approve(on, aid, OK, webauthn={"id": "cred", "clientDataJSON": "e30", "authenticatorData": "", "signature": ""})
    assert r.json()["state"] == "succeeded"
    (mark,) = [e for e in audit(settings) if e["event"] == "app.owner_override"]
    assert mark["data"]["payload"]["step_up"] == "passkey"


def test_no_passkeys_registered_means_typed_confirmation_only(on, clock):
    on.app.state.owner_override.step_up = Passkeys(False)
    assert approve(on, request(on, clock), OK).json()["state"] == "succeeded"


def test_describe_for_the_approval_card(on, clock, settings):
    d = on.get(f"/v1/apps/{APP}/owner-override", headers=OWNER).json()
    assert d["enabled"] and d["eligible"] and d["confirm"] == APP and d["refusal"] is None
    assert "failed its last scan" in d["scan_problem"] and d["reason_length"] == [10, 500]
    fail_scan(settings, clock, images=[{"ref": "x", "clamav": {"infected": 1}}])
    d = on.get(f"/v1/apps/{APP}/owner-override", headers=OWNER).json()
    assert d["eligible"] is False and "malware" in d["refusal"]
    write_scan(settings.apps_dir / APP, clock.now)
    d = on.get(f"/v1/apps/{APP}/owner-override", headers=OWNER).json()
    assert d["scan_problem"] is None and d["eligible"] is False
    assert on.get("/v1/apps/nope/owner-override", headers=OWNER).status_code == 404


@pytest.mark.parametrize("value,expected", [("", False), ("0", False), ("no", False), ("1", True), ("true", True), ("YES", True)])
def test_env_parsing(value, expected):
    assert OwnerOverrideSettings.from_env({"ONEMIND_ALLOW_OWNER_OVERRIDE": value}).enabled is expected
    assert OwnerOverrideSettings.from_env({}).enabled is False


def test_bad_env_value_stops_the_gateway():
    with pytest.raises(ValueError, match="ONEMIND_ALLOW_OWNER_OVERRIDE"):
        Settings.from_env({"ONEMIND_ALLOW_OWNER_OVERRIDE": "maybe"})


def test_hermes_like_app_with_secrets_and_override_together(on, clock, settings):
    """The Hermes case: a failing scan, an agent principal and owner-entered secrets in one approval."""
    from onemind_core.appsecrets.crypto import seal_values

    value = "sk-test-" + os.urandom(8).hex()  # generated per run; nothing credential-like is committed
    fail_scan(settings, clock, app_id="vault-like")
    aid = request(on, clock, app_id="vault-like")
    pk = on.get("/v1/secrets/public-key", headers=OWNER).json()
    sealed = seal_values(pk, "vault-like", {"vault-like-credentials": {"PROVIDER_API_KEY": value}})
    r = approve(on, aid, {"reason": REASON, "confirm": "vault-like"}, sealed=sealed)
    assert r.status_code == 200 and r.json()["state"] == "succeeded", r.text
    assert on.executor.secrets[-1][0].data == {"PROVIDER_API_KEY": value}
