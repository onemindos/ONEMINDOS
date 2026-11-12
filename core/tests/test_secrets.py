# SPDX-License-Identifier: Apache-2.0
"""App secrets (DEPLOYMENTS.md §7, DT-9): declared, entered with the approval, encrypted, applied, never shown."""

import base64
import json
import os
import stat
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from conftest import ADULT, AGENT, OWNER, ScriptedExecutor, action_body, make_client
from onemind_core.app import create_app
from onemind_core.appsecrets.crypto import SealedInputError, StoreKey, b64u, seal, seal_values, sealed_context
from onemind_core.appsecrets.service import SecretsSettings
from onemind_core.appsecrets.spec import parse_secrets, secret_spec_errors
from onemind_core.appsecrets.store import SecretValueRow, StagedSecretRow
from onemind_core.audit import verify
from onemind_core.catalog import Catalog
from onemind_core.executors import AgentSecret, AppSecret, KubernetesExecutor, NoopExecutor

APP = "vault-like"
CRED = "vault-like-credentials"
INTERNAL = "vault-like-internal"
# Test values are generated per run: nothing that looks like a credential is committed.
API_KEY = "sk-test-" + os.urandom(12).hex()
NEW_KEY = "sk-test-" + os.urandom(12).hex()
PASSWORD = "pw " + os.urandom(8).hex()


def audit_text(settings) -> str:
    return settings.audit_path.read_text()


def audit_lines(settings) -> list[dict]:
    return [json.loads(line) for line in audit_text(settings).splitlines()]


def request(client, clock, headers=OWNER, key="k1", app_id=APP, type_="app.install"):
    r = client.post("/v1/actions", json=action_body(clock, app_id=app_id, type_=type_, key=key), headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def sealed_for(client, values: dict, app_id: str = APP) -> dict:
    pk = client.get("/v1/secrets/public-key", headers=OWNER).json()
    return seal_values(pk, app_id, values)


def install(client, clock, values=None, headers=OWNER, key="k1"):
    aid = request(client, clock, headers=headers, key=key)
    body = {"sealed": sealed_for(client, values)} if values is not None else None
    r = client.post(f"/v1/actions/{aid}/approve", json=body, headers=OWNER)
    return aid, r


def everything_the_gateway_wrote(client, settings) -> str:
    """Audit log, every action, every API read of the app, and the SQLite file."""
    parts = [audit_text(settings), json.dumps(client.get("/v1/actions", headers=OWNER).json()),
             json.dumps(client.get(f"/v1/apps/{APP}/secrets", headers=OWNER).json())]
    if settings.db_url.startswith("sqlite:///"):
        parts.append(Path(settings.db_url[len("sqlite:///"):]).read_bytes().decode("latin-1"))
    return "\n".join(parts)


# ---- the manifest declaration ---------------------------------------------------------------
GOOD = {"secrets": [{"name": "creds", "description": "d", "keys": [
    {"key": "API_KEY", "kind": "api-key", "required": True},
    {"key": "BASE_URL", "kind": "url"},
    {"key": "SESSION", "generate": True},
]}]}


def test_declaration_parses_with_defaults():
    (decl,), errs = parse_secrets(GOOD)
    assert errs == []
    assert [(k.key, k.kind, k.required, k.source) for k in decl.keys] == [
        ("API_KEY", "api-key", True, "owner"), ("BASE_URL", "url", False, "owner"), ("SESSION", "password", False, "generated"),
    ]


@pytest.mark.parametrize("secrets,needle", [
    ("nope", "must be a list"),
    ([{"name": "Bad_Name", "keys": [{"key": "A"}]}], "DNS-1123"),
    ([{"name": "a", "keys": []}], "1 to 32 keys"),
    ([{"name": "a", "keys": [{"key": "A"}, {"key": "A"}]}], "declared twice"),
    ([{"name": "a", "keys": [{"key": "A"}]}, {"name": "a", "keys": [{"key": "B"}]}], "declared twice"),
    ([{"name": "a", "keys": [{"key": "A", "kind": "ssh-key"}]}], "kind must be one of"),
    ([{"name": "a", "keys": [{"key": "A", "generate": True, "required": True}]}], "exclusive"),
    ([{"name": "a", "keys": [{"key": "A", "kind": "url", "generate": True}]}], "cannot be generated"),
    ([{"name": "a", "keys": [{"key": "A", "value": "x"}]}], "unknown field 'value'"),
    ([{"name": "a", "keys": [{"key": "A b"}]}], "key must match"),
    ([{"name": "a", "keys": [{"key": "A", "required": "yes"}]}], "true or false"),
    ([{"name": "agent-secret", "keys": [{"key": "A"}]}], "spec.agent Secret"),
])
def test_declaration_errors(secrets, needle):
    spec = {"secrets": secrets, "agent": {"principal": True, "secret": "agent-secret"}}
    errs = secret_spec_errors(spec)
    assert any(needle in e for e in errs), errs


def test_invalid_declaration_skips_the_app(settings):
    app_dir = settings.apps_dir / "bad-secrets"
    (app_dir / "manifests").mkdir(parents=True)
    doc = (settings.apps_dir / APP / "onemind.app.yaml").read_text().replace("id: vault-like", "id: bad-secrets")
    (app_dir / "onemind.app.yaml").write_text(doc.replace("kind: url", "kind: phone-number"))
    cat = Catalog(settings.apps_dir)
    apps = cat.load()
    assert "bad-secrets" not in apps and any("kind must be one of" in e for e in cat.errors["bad-secrets"])
    assert [s.name for s in apps[APP].secrets] == [CRED, INTERNAL]


def test_repo_schema_says_what_the_builtin_check_says():
    """sdk/schema accepts spec.secrets and refuses what secret_spec_errors refuses."""
    from jsonschema import Draft202012Validator

    root = Path(__file__).resolve().parents[2]
    schema = Draft202012Validator(json.loads((root / "sdk" / "schema" / "onemind.app.schema.json").read_text()))
    cat = Catalog(root / "apps", root / "sdk" / "schema" / "onemind.app.schema.json")
    doc = cat.load()["uptime-kuma"].manifest  # a real, schema-valid manifest

    def with_keys(keys):
        return {**doc, "spec": {**doc["spec"], "secrets": [{"name": "s", "description": "d", "keys": keys}]}}

    assert schema.is_valid(with_keys([{"key": "S", "kind": "token", "generate": True},
                                      {"key": "U", "kind": "url", "required": True, "description": "x"}]))
    assert not schema.is_valid(with_keys([{"key": "S", "generate": True, "required": True}]))
    assert not schema.is_valid(with_keys([{"key": "S", "kind": "url", "generate": True}]))
    assert not schema.is_valid(with_keys([{"key": "S", "kind": "ssh"}]))
    assert not schema.is_valid(with_keys([{"key": "S", "value": "x"}]))
    assert not schema.is_valid(with_keys([]))


# ---- the store key and sealed input ---------------------------------------------------------
def test_store_key_file_is_created_private_and_never_overwritten(tmp_path):
    path = tmp_path / "custodian" / "secrets.key"
    k1 = StoreKey.load(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    k2 = StoreKey.load(path)
    assert k1.key_id == k2.key_id and k1.public_key == k2.public_key
    assert "secrets.key" not in repr(k1) and path.read_text().strip() not in repr(k1)


def test_store_key_refuses_loose_permissions_and_bad_content(tmp_path):
    path = tmp_path / "k"
    StoreKey.load(path)
    path.chmod(0o640)
    with pytest.raises(PermissionError):
        StoreKey.load(path)
    path.chmod(0o600)
    path.write_text("too short\n")
    with pytest.raises(ValueError):
        StoreKey.load(path)
    with pytest.raises(FileNotFoundError):
        StoreKey.load(tmp_path / "absent", create=False)


def test_raw_32_byte_key_file_is_accepted(tmp_path):
    path = tmp_path / "raw"
    path.write_bytes(os.urandom(32))
    path.chmod(0o600)
    assert StoreKey.load(path).key_id.startswith("sk_")


def test_sealed_input_round_trip_and_binding(tmp_path):
    key = StoreKey.load(tmp_path / "k")
    sealed = seal(key.public_key, b'{"values": {}}', sealed_context(APP), key.key_id)
    assert key.open_sealed(sealed, sealed_context(APP)) == b'{"values": {}}'
    with pytest.raises(SealedInputError, match="for this app"):  # replay into another app
        key.open_sealed(sealed, sealed_context("other-app"))
    other = StoreKey.load(tmp_path / "k2")
    with pytest.raises(SealedInputError, match="another key"):
        other.open_sealed(sealed, sealed_context(APP))
    with pytest.raises(SealedInputError, match="for this app"):  # same key id omitted, wrong key
        other.open_sealed({k: v for k, v in sealed.items() if k != "kid"}, sealed_context(APP))
    raw = base64.urlsafe_b64decode(sealed["ct"] + "==")
    tampered = {**sealed, "ct": b64u(raw[:-1] + bytes([raw[-1] ^ 1]))}
    with pytest.raises(SealedInputError):
        key.open_sealed(tampered, sealed_context(APP))
    for bad in ({**sealed, "alg": "RSA"}, {**sealed, "epk": "AAAA"}, "text", {**sealed, "epk": b64u(bytes(32))}):
        with pytest.raises(SealedInputError):
            key.open_sealed(bad, sealed_context(APP))


def test_settings_section_paths(tmp_path):
    assert SecretsSettings.from_env({}).key_file is None
    assert SecretsSettings.from_env({"ONEMIND_DATA_DIR": "/d"}).key_file == Path("/d/custodian/secrets.key")
    assert SecretsSettings.from_env({"ONEMIND_SECRETS_KEY_FILE": "/k"}).key_file == Path("/k")
    (tmp_path / "onemind-secrets-key").write_text("x")
    cfg = SecretsSettings.from_env({"CREDENTIALS_DIRECTORY": str(tmp_path), "ONEMIND_DATA_DIR": "/d"})
    assert cfg.key_file == tmp_path / "onemind-secrets-key" and cfg.create_key is False


def test_key_lives_next_to_the_data_by_default(client, settings):
    key = settings.audit_path.parent / "custodian" / "secrets.key"
    assert key.is_file() and stat.S_IMODE(key.stat().st_mode) == 0o600
    pk = client.get("/v1/secrets/public-key", headers=AGENT).json()
    assert pk["alg"] == "X25519" and pk["sealed_alg"] == "X25519-AES256GCM" and len(base64.urlsafe_b64decode(pk["key"] + "=")) == 32


# ---- reading declarations -------------------------------------------------------------------
@pytest.mark.parametrize("headers", [OWNER, ADULT, AGENT])
def test_describe_lists_declarations_without_values(client, headers):
    r = client.get(f"/v1/apps/{APP}/secrets", headers=headers)
    assert r.status_code == 200
    doc = r.json()
    assert doc["missing_required"] == [f"{CRED}/PROVIDER_API_KEY"]
    cred = doc["secrets"][0]
    assert cred["name"] == CRED and cred["description"] == "Keys the app needs"
    assert [(k["key"], k["kind"], k["required"], k["source"], k["set"]) for k in cred["keys"]] == [
        ("PROVIDER_API_KEY", "api-key", True, "owner", False),
        ("PROVIDER_BASE_URL", "url", False, "owner", False),
        ("ADMIN_PASSWORD", "password", False, "owner", False),
    ]
    assert client.get("/v1/apps/nope/secrets", headers=OWNER).status_code == 404


# ---- install: the approval carries the form -------------------------------------------------
def test_install_refused_until_required_secret_is_entered(client, clock, executor):
    aid, r = install(client, clock)
    assert r.status_code == 409 and "PROVIDER_API_KEY" in r.json()["message"]
    assert client.get(f"/v1/actions/{aid}", headers=OWNER).json()["state"] == "awaiting_approval"
    assert executor.calls == []
    r = client.post(f"/v1/actions/{aid}/approve", json={"sealed": sealed_for(client, {CRED: {"PROVIDER_API_KEY": API_KEY}})},
                    headers=OWNER)
    assert r.status_code == 200 and r.json()["state"] == "succeeded", r.text


def test_install_hands_values_to_executor_and_keeps_them_out_of_everything(client, clock, executor, settings):
    _, r = install(client, clock, {CRED: {"PROVIDER_API_KEY": API_KEY, "ADMIN_PASSWORD": PASSWORD}})
    assert r.status_code == 200 and r.json()["state"] == "succeeded", r.text
    (cred, internal) = executor.secrets[-1]
    assert cred.name == CRED and cred.data == {"PROVIDER_API_KEY": API_KEY, "ADMIN_PASSWORD": PASSWORD}
    assert internal.name == INTERNAL and len(internal.data["SESSION_SECRET"]) >= 40  # generated on the box
    assert API_KEY not in repr(cred)
    doc = client.get(f"/v1/apps/{APP}/secrets", headers=OWNER).json()
    assert doc["missing_required"] == []
    states = {(s["name"], k["key"]): (k["set"], k["version"]) for s in doc["secrets"] for k in s["keys"]}
    assert states[(CRED, "PROVIDER_API_KEY")] == (True, 1) and states[(CRED, "PROVIDER_BASE_URL")] == (False, None)
    assert states[(INTERNAL, "SESSION_SECRET")] == (True, 1)
    written = everything_the_gateway_wrote(client, settings)
    for value in (API_KEY, PASSWORD, internal.data["SESSION_SECRET"]):
        assert value not in written
        assert base64.b64encode(value.encode()).decode() not in written
    (event,) = [e for e in audit_lines(settings) if e["event"] == "app.secrets.changed"]
    changes = {(c["secret"], c["key"]): c for c in event["data"]["payload"]["changes"]}
    assert changes[(CRED, "PROVIDER_API_KEY")]["op"] == "set" and changes[(CRED, "PROVIDER_API_KEY")]["fingerprint"].startswith("fp_")
    assert changes[(INTERNAL, "SESSION_SECRET")]["op"] == "generate"
    assert event["principal"]["role"] == "owner"
    assert verify(settings.audit_path)[0]


def test_agent_requested_install_gets_its_secrets_from_the_owner(client, clock, executor):
    aid, r = install(client, clock, {CRED: {"PROVIDER_API_KEY": API_KEY}}, headers=AGENT)
    assert r.status_code == 200 and r.json()["requested_by"]["kind"] == "agent"
    # the agent can neither approve nor enter or change secrets
    r = client.post(f"/v1/actions/{aid}/approve", json={"sealed": sealed_for(client, {CRED: {"PROVIDER_API_KEY": API_KEY}})},
                    headers=AGENT)
    assert r.status_code == 403
    r = client.post(f"/v1/apps/{APP}/secrets", json={"generate": [f"{INTERNAL}/SESSION_SECRET"]}, headers=AGENT)
    assert r.status_code == 403 and r.json()["error"] == "permission_denied"


def test_agent_secret_and_app_secrets_both_reach_the_executor(client, clock, executor):
    install(client, clock, {CRED: {"PROVIDER_API_KEY": API_KEY}})
    assert isinstance(executor.agents[-1], AgentSecret) and executor.agents[-1].name == "vault-like-onemind"
    assert [s.name for s in executor.secrets[-1]] == [CRED, INTERNAL]


@pytest.mark.parametrize("values,needle", [
    ({CRED: {"NOT_DECLARED": "abcdef"}}, "not declared"),
    ({"other-secret": {"PROVIDER_API_KEY": "abcdef"}}, "not declared"),
    ({INTERNAL: {"SESSION_SECRET": "abcdefgh"}}, "generated by the box"),
    ({CRED: {"PROVIDER_API_KEY": "has space inside"}}, "must not contain spaces"),
    ({CRED: {"PROVIDER_API_KEY": "abc"}}, "4 to 8192"),
    ({CRED: {"PROVIDER_API_KEY": "line\nbreak"}}, "control characters"),
    ({CRED: {"PROVIDER_API_KEY": API_KEY, "PROVIDER_BASE_URL": "not-a-url"}}, "must be a URL"),
    ({CRED: {"PROVIDER_API_KEY": 12345}}, "must be text"),
])
def test_bad_form_values_are_refused_without_echoing_them(client, clock, settings, values, needle):
    aid, r = install(client, clock, values)
    assert r.status_code == 422 and needle in r.json()["message"], r.text
    for keys in values.values():
        for v in keys.values():
            if isinstance(v, str) and len(v) > 4:
                assert v not in r.json()["message"] and v not in audit_text(settings)
    assert client.get(f"/v1/actions/{aid}", headers=OWNER).json()["state"] == "awaiting_approval"


def test_form_sealed_for_another_app_is_refused(client, clock):
    aid = request(client, clock)
    sealed = sealed_for(client, {CRED: {"PROVIDER_API_KEY": API_KEY}}, app_id="whoami")
    r = client.post(f"/v1/actions/{aid}/approve", json={"sealed": sealed}, headers=OWNER)
    assert r.status_code == 422 and "for this app" in r.json()["message"]


def test_sealed_input_for_an_app_without_secrets_is_refused(client, clock):
    aid = request(client, clock, app_id="whoami")
    pk = client.get("/v1/secrets/public-key", headers=OWNER).json()
    r = client.post(f"/v1/actions/{aid}/approve", json={"sealed": seal_values(pk, "whoami", {})}, headers=OWNER)
    assert r.status_code == 422 and "declares no secrets" in r.json()["message"]


def test_plaintext_values_are_not_accepted(client, clock):
    aid = request(client, clock)
    r = client.post(f"/v1/actions/{aid}/approve", json={"sealed": {"values": {CRED: {"PROVIDER_API_KEY": API_KEY}}}},
                    headers=OWNER)
    assert r.status_code == 422 and API_KEY not in r.text


def test_apps_without_secrets_install_as_before(client, clock, executor):
    aid = request(client, clock, app_id="uptime-kuma")
    r = client.post(f"/v1/actions/{aid}/approve", headers=OWNER)
    assert r.json()["state"] == "succeeded" and executor.secrets == [[]]


def test_reinstall_after_remove_reuses_stored_values(client, clock, executor):
    install(client, clock, {CRED: {"PROVIDER_API_KEY": API_KEY}})
    first_session = executor.secrets[-1][1].data["SESSION_SECRET"]
    rid = request(client, clock, key="rm", type_="app.remove")
    assert client.post(f"/v1/actions/{rid}/approve", headers=OWNER).json()["state"] == "succeeded"
    _, r = install(client, clock, key="again")  # no form: the required key is still stored
    assert r.status_code == 200 and r.json()["state"] == "succeeded", r.text
    assert executor.secrets[-1][0].data == {"PROVIDER_API_KEY": API_KEY}
    assert executor.secrets[-1][1].data["SESSION_SECRET"] == first_session  # generated once, kept with the data


def test_values_survive_a_gateway_restart(settings, clock):
    ex = ScriptedExecutor()
    with TestClient(create_app(settings, clock=clock, executor=ex)) as c:
        install(c, clock, {CRED: {"PROVIDER_API_KEY": API_KEY}})
    ex2 = ScriptedExecutor()
    with TestClient(create_app(settings, clock=clock, executor=ex2)) as c:
        r = c.post(f"/v1/apps/{APP}/secrets", json={}, headers=OWNER)  # re-apply
        assert r.status_code == 202
        assert c.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER).json()["state"] == "succeeded"
    assert ex2.calls == [("app.configure", APP)] and ex2.secrets[-1][0].data["PROVIDER_API_KEY"] == API_KEY


def test_database_restored_without_its_key_is_refused_clearly(settings, clock, tmp_path):
    with TestClient(create_app(settings, clock=clock, executor=ScriptedExecutor())) as c:
        install(c, clock, {CRED: {"PROVIDER_API_KEY": API_KEY}})
    other = replace(settings, sections={"secrets": SecretsSettings(key_file=tmp_path / "other.key")})
    with TestClient(create_app(other, clock=clock, executor=ScriptedExecutor())) as c:
        r = c.post(f"/v1/apps/{APP}/secrets", json={}, headers=OWNER)
        r = c.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
        assert r.status_code == 409 and "does not open with this box's key" in r.json()["message"]


def test_values_lost_with_the_key_are_replaced_by_entering_them_again(settings, clock, tmp_path):
    with TestClient(create_app(settings, clock=clock, executor=ScriptedExecutor())) as c:
        install(c, clock, {CRED: {"PROVIDER_API_KEY": API_KEY}})
    other = replace(settings, sections={"secrets": SecretsSettings(key_file=tmp_path / "other.key")})
    ex = ScriptedExecutor()
    with TestClient(create_app(other, clock=clock, executor=ex)) as c:
        # Re-entering the owner key is not enough: the generated one does not open either.
        body = {"sealed": sealed_for(c, {CRED: {"PROVIDER_API_KEY": NEW_KEY}})}
        r = c.post(f"/v1/apps/{APP}/secrets", json=body, headers=OWNER)
        r = c.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
        assert r.status_code == 409, r.text
        assert f"{INTERNAL}/SESSION_SECRET" in r.json()["message"] and "rotate it" in r.json()["message"]
        # Entering one and rotating the other replaces every value the lost key protected.
        body = {"sealed": sealed_for(c, {CRED: {"PROVIDER_API_KEY": NEW_KEY}}), "generate": [f"{INTERNAL}/SESSION_SECRET"]}
        r = c.post(f"/v1/apps/{APP}/secrets", json=body, headers=OWNER)
        r = c.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
        assert r.status_code == 200 and r.json()["state"] == "succeeded", r.text
        cred, internal = ex.secrets[-1]
        assert cred.data == {"PROVIDER_API_KEY": NEW_KEY} and len(internal.data["SESSION_SECRET"]) >= 40


def test_reinstall_after_key_loss_names_the_generated_value(settings, clock, tmp_path):
    with TestClient(create_app(settings, clock=clock, executor=ScriptedExecutor())) as c:
        install(c, clock, {CRED: {"PROVIDER_API_KEY": API_KEY}})
        rid = request(c, clock, key="rm", type_="app.remove")
        assert c.post(f"/v1/actions/{rid}/approve", headers=OWNER).json()["state"] == "succeeded"
    other = replace(settings, sections={"secrets": SecretsSettings(key_file=tmp_path / "other.key")})
    with TestClient(create_app(other, clock=clock, executor=ScriptedExecutor())) as c:
        _, r = install(c, clock, {CRED: {"PROVIDER_API_KEY": NEW_KEY}}, key="again")
        assert r.status_code == 409 and f"{INTERNAL}/SESSION_SECRET" in r.json()["message"]
        assert "restore the key file" in r.json()["message"]


# ---- change and rotate: app.configure -------------------------------------------------------
def installed(client, clock):
    install(client, clock, {CRED: {"PROVIDER_API_KEY": API_KEY, "ADMIN_PASSWORD": PASSWORD}})


def stored(client):
    db = client.app.state.gateway.db
    with db.session() as s:
        return {(r.name, r.key): r for r in s.scalars(select(SecretValueRow))}, list(s.scalars(select(StagedSecretRow)))


def test_change_is_staged_then_applied_on_approval(client, clock, executor, settings):
    installed(client, clock)
    old_session = executor.secrets[-1][1].data["SESSION_SECRET"]
    body = {"sealed": sealed_for(client, {CRED: {"PROVIDER_API_KEY": NEW_KEY}}),
            "generate": [f"{INTERNAL}/SESSION_SECRET"], "clear": [f"{CRED}/ADMIN_PASSWORD"], "reason": "rotate keys"}
    r = client.post(f"/v1/apps/{APP}/secrets", json=body, headers=OWNER)
    assert r.status_code == 202, r.text
    action = r.json()
    assert r.headers["location"] == f"/v1/actions/{action['id']}"
    assert action["type"] == "app.configure" and action["state"] == "awaiting_approval"
    ops = {(c["secret"], c["key"]): c for c in action["params"]["secrets"]}
    assert ops[(CRED, "PROVIDER_API_KEY")]["op"] == "set" and ops[(CRED, "PROVIDER_API_KEY")]["fingerprint"].startswith("fp_")
    assert ops[(INTERNAL, "SESSION_SECRET")] == {"secret": INTERNAL, "key": "SESSION_SECRET", "op": "generate"}
    assert ops[(CRED, "ADMIN_PASSWORD")]["op"] == "clear"
    # nothing changed yet: the old value is current, the new one waits encrypted
    rows, staged = stored(client)
    assert len(staged) == 3 and all(NEW_KEY.encode() not in (s.ciphertext or b"") for s in staged)
    assert executor.calls == [("app.install", APP)]

    r = client.post(f"/v1/actions/{action['id']}/approve", headers=OWNER)
    assert r.status_code == 200 and r.json()["state"] == "succeeded", r.text
    assert executor.calls[-1] == ("app.configure", APP)
    assert executor.agents[-1] is None  # configure never issues a new agent token
    cred, internal = executor.secrets[-1]
    assert cred.data == {"PROVIDER_API_KEY": NEW_KEY}
    assert internal.data["SESSION_SECRET"] != old_session
    rows, staged = stored(client)
    assert staged == []
    assert rows[(CRED, "PROVIDER_API_KEY")].version == 2 and (CRED, "ADMIN_PASSWORD") not in rows
    assert rows[(INTERNAL, "SESSION_SECRET")].version == 2
    assert client.get("/v1/apps", headers=OWNER).json()[[a["id"] for a in client.get("/v1/apps", headers=OWNER).json()].index(APP)]["status"] == "installed"
    assert NEW_KEY not in everything_the_gateway_wrote(client, settings)


def test_change_needs_an_installed_app(client, clock):
    r = client.post(f"/v1/apps/{APP}/secrets", json={"generate": [f"{INTERNAL}/SESSION_SECRET"]}, headers=OWNER)
    assert r.status_code == 409 and "not installed" in r.json()["message"]


@pytest.mark.parametrize("body,needle", [
    ({"clear": [f"{CRED}/PROVIDER_API_KEY"]}, "optional owner-entered"),
    ({"clear": [f"{INTERNAL}/SESSION_SECRET"]}, "optional owner-entered"),
    ({"generate": [f"{CRED}/PROVIDER_API_KEY"]}, "only generated keys"),
    ({"generate": ["nope/KEY"]}, "not a declared"),
    ({"generate": ["no-slash"]}, "not a declared"),
    ({"generate": [f"{INTERNAL}/SESSION_SECRET"], "clear": [f"{INTERNAL}/SESSION_SECRET"]}, "optional owner-entered"),
])
def test_bad_change_requests(client, clock, body, needle):
    installed(client, clock)
    r = client.post(f"/v1/apps/{APP}/secrets", json=body, headers=OWNER)
    assert r.status_code == 422 and needle in r.json()["message"], r.text


def test_same_key_in_two_changes_is_refused(client, clock):
    installed(client, clock)
    body = {"sealed": sealed_for(client, {CRED: {"ADMIN_PASSWORD": PASSWORD}}), "clear": [f"{CRED}/ADMIN_PASSWORD"]}
    r = client.post(f"/v1/apps/{APP}/secrets", json=body, headers=OWNER)
    assert r.status_code == 422 and "more than one change" in r.json()["message"]


@pytest.mark.parametrize("headers", [ADULT, AGENT])
def test_only_owners_change_secrets(client, clock, settings, headers):
    installed(client, clock)
    r = client.post(f"/v1/apps/{APP}/secrets", json={}, headers=headers)
    assert r.status_code == 403
    denied = [e for e in audit_lines(settings) if e["event"] == "authz.denied"]
    assert denied[-1]["data"]["attempted"] == "change app secrets"


def test_denied_change_is_purged(client, clock):
    installed(client, clock)
    r = client.post(f"/v1/apps/{APP}/secrets", json={"sealed": sealed_for(client, {CRED: {"PROVIDER_API_KEY": NEW_KEY}})},
                    headers=OWNER)
    aid = r.json()["id"]
    assert len(stored(client)[1]) == 1
    assert client.post(f"/v1/actions/{aid}/deny", headers=OWNER).status_code == 200
    rows, staged = stored(client)
    assert staged == [] and rows[(CRED, "PROVIDER_API_KEY")].version == 1


def test_expired_change_is_purged(client, clock):
    installed(client, clock)
    client.post(f"/v1/apps/{APP}/secrets", json={"generate": [f"{INTERNAL}/SESSION_SECRET"]}, headers=OWNER)
    clock.advance(25 * 3600)
    assert client.app.state.app_secrets.purge() == 1


def test_change_with_lost_staging_is_refused(client, clock):
    installed(client, clock)
    r = client.post(f"/v1/apps/{APP}/secrets", json={"generate": [f"{INTERNAL}/SESSION_SECRET"]}, headers=OWNER)
    client.app.state.app_secrets.repo.drop_staged({r.json()["id"]})
    r = client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert r.status_code == 409 and "submit the secrets form again" in r.json()["message"]


def test_change_request_is_idempotent_by_header(client, clock):
    installed(client, clock)
    body = {"generate": [f"{INTERNAL}/SESSION_SECRET"]}
    r1 = client.post(f"/v1/apps/{APP}/secrets", json=body, headers={**OWNER, "Idempotency-Key": "rot-1"})
    clock.advance(30)  # a real retry comes later; the default expiry must not make it a different request
    r2 = client.post(f"/v1/apps/{APP}/secrets", json=body, headers={**OWNER, "Idempotency-Key": "rot-1"})
    assert (r1.status_code, r2.status_code) == (202, 200) and r1.json()["id"] == r2.json()["id"]
    assert len(stored(client)[1]) == 1
    r3 = client.post(f"/v1/apps/{APP}/secrets", json={}, headers={**OWNER, "Idempotency-Key": "rot-1"})
    assert r3.status_code == 409 and r3.json()["error"] == "conflict"


def test_configure_is_not_requestable_through_post_actions_or_by_agents(client, clock):
    installed(client, clock)
    r = client.post("/v1/actions", json=action_body(clock, app_id=APP, type_="app.configure", key="c"), headers=OWNER)
    assert r.status_code == 422


def test_sealed_input_with_configure_approval_is_refused(client, clock):
    installed(client, clock)
    r = client.post(f"/v1/apps/{APP}/secrets", json={}, headers=OWNER)
    sealed = sealed_for(client, {CRED: {"PROVIDER_API_KEY": NEW_KEY}})
    r = client.post(f"/v1/actions/{r.json()['id']}/approve", json={"sealed": sealed}, headers=OWNER)
    assert r.status_code == 422


def test_interrupted_configure_is_reconciled_to_unknown(settings, clock):
    ex = ScriptedExecutor()
    with TestClient(create_app(settings, clock=clock, executor=ex)) as c:
        installed(c, clock)
        aid = c.post(f"/v1/apps/{APP}/secrets", json={}, headers=OWNER).json()["id"]
        repo = c.app.state.repo
        repo.accept_and_claim(aid, clock(), {"id": "owner"}, APP, "configuring", {"installed"}, False)
    with TestClient(create_app(settings, clock=clock, executor=ScriptedExecutor())) as c:
        apps = {a["id"]: a for a in c.get("/v1/apps", headers=OWNER).json()}
        assert apps[APP]["status"] == "unknown"
        assert c.get(f"/v1/actions/{aid}", headers=OWNER).json()["state"] == "outcome_unknown"


# ---- executors ------------------------------------------------------------------------------
def kube_app(settings):
    return Catalog(settings.apps_dir).get(APP)


def test_kubernetes_plan_applies_secrets_server_side_before_manifests(settings):
    app = kube_app(settings)
    secrets = [AppSecret(CRED, {"PROVIDER_API_KEY": API_KEY}), AppSecret(INTERNAL, {"SESSION_SECRET": "generated-value"})]
    plan = KubernetesExecutor(kubectl="kubectl").plan("app.install", app, None, secrets)
    argvs = [p[0] for p in plan]
    assert argvs[0][:3] == ["kubectl", "apply", "-f"]
    for argv, stdin in plan[1:3]:
        assert argv[:3] == ["kubectl", "apply", "--server-side"] and "--field-manager=onemind-gateway" in argv
        doc = json.loads(stdin)
        assert doc["kind"] == "Secret" and doc["metadata"]["namespace"] == f"app-{APP}"
        assert doc["metadata"]["labels"] == {"onemind.io/app": APP, "onemind.io/app-secret": "true"}
        assert "stringData" not in doc
    assert json.loads(plan[1][1])["data"] == {"PROVIDER_API_KEY": base64.b64encode(API_KEY.encode()).decode()}
    assert argvs[-1][:3] == ["kubectl", "apply", "-k"]
    assert all(API_KEY not in " ".join(a) for a in argvs)  # values only ever on stdin


def test_kubernetes_configure_applies_and_restarts(settings):
    app = kube_app(settings)
    plan = KubernetesExecutor(kubectl="kubectl").plan("app.configure", app, None, [AppSecret(CRED, {"A": "abcd"})])
    assert plan[0][0][:3] == ["kubectl", "apply", "--server-side"]
    assert plan[-1] == (["kubectl", "rollout", "restart", "deployment,statefulset", "-n", f"app-{APP}"], None)


def fake_runner(outputs):
    calls = []

    def run(argv, input=None, **_):
        calls.append((argv, input))
        rc, out, err = outputs(argv)
        return subprocess.CompletedProcess(argv, rc, out, err)

    return run, calls


def test_kubectl_output_is_scrubbed_of_every_value(settings):
    b64 = base64.b64encode(API_KEY.encode()).decode()

    def outputs(argv):
        return 1, f"echo {API_KEY}", f"error near {b64}"

    run, _ = fake_runner(outputs)
    ex = KubernetesExecutor(kubectl="kubectl", runner=run)
    res = ex.run("app.configure", kube_app(settings), None, [AppSecret(CRED, {"PROVIDER_API_KEY": API_KEY})])
    assert res.outcome == "failed"
    text = json.dumps(res.to_json())
    assert API_KEY not in text and b64 not in text and "[redacted]" in text


def test_value_cut_by_the_output_tail_is_still_scrubbed(settings):
    # The value starts just before the last 2000 characters kept: only its end would remain.
    tail = API_KEY[4:]

    def outputs(argv):
        return 1, "", "x" * 3000 + API_KEY + "y" * (2000 - len(tail))

    run, _ = fake_runner(outputs)
    res = KubernetesExecutor(kubectl="kubectl", runner=run).run(
        "app.configure", kube_app(settings), None, [AppSecret(CRED, {"PROVIDER_API_KEY": API_KEY})])
    text = json.dumps(res.to_json())
    assert tail not in text and "[redacted]" in text


def test_nothing_to_restart_is_not_a_failure(settings):
    def outputs(argv):
        if argv[1:3] == ["rollout", "restart"]:
            return 1, "", "error: no objects passed to restart\n"
        return 0, "secret/x serverside-applied\n", ""

    run, calls = fake_runner(outputs)
    res = KubernetesExecutor(kubectl="kubectl", runner=run).run(
        "app.configure", kube_app(settings), None, [AppSecret(CRED, {"A": "abcd"})])
    assert res.outcome == "succeeded" and res.steps[-1]["note"] == "no Deployment or StatefulSet to restart"


def test_restart_failure_for_other_reasons_fails(settings):
    def outputs(argv):
        return (1, "", "forbidden") if argv[1:3] == ["rollout", "restart"] else (0, "", "")

    run, _ = fake_runner(outputs)
    res = KubernetesExecutor(kubectl="kubectl", runner=run).run(
        "app.configure", kube_app(settings), None, [AppSecret(CRED, {"A": "abcd"})])
    assert res.outcome == "failed"


def test_noop_executor_records_key_names_only(settings, clock):
    with make_client(settings, clock, NoopExecutor()) as c:
        aid = request(c, clock)
        r = c.post(f"/v1/actions/{aid}/approve", json={"sealed": sealed_for(c, {CRED: {"PROVIDER_API_KEY": API_KEY}})},
                   headers=OWNER)
        steps = r.json()["result"]["steps"]
        applied = [s for s in steps if "apply Secret" in s.get("would", "")]
        assert [s["keys"] for s in applied] == [["PROVIDER_API_KEY"], ["SESSION_SECRET"]]
        assert API_KEY not in r.text
