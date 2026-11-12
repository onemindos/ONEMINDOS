# SPDX-License-Identifier: Apache-2.0
"""Contract §11.2: an app that declares spec.agent gets its own agent principal at install."""

import base64
import json
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from conftest import conform_to_schema, AGENT, OWNER, FakeKubectl, ScriptedExecutor, action_body, make_client
from onemind_core.app import create_app
from onemind_core.audit import verify
from onemind_core.catalog import Catalog, agent_spec_errors
from onemind_core.config import Settings
from onemind_core.executors import KubernetesExecutor

SCHEMA = Path(__file__).resolve().parents[2] / "sdk" / "schema" / "onemind.app.schema.json"
from onemind_core.ledger import AgentTokenRow

APP = "hermes-like"
SECRET = "hermes-like-onemind"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def run_action(client, clock, type_="app.install", key="k1", app_id=APP, requester=OWNER):
    r = client.post("/v1/actions", json=action_body(clock, app_id=app_id, type_=type_, key=key), headers=requester)
    assert r.status_code == 201, r.text
    r = client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert r.status_code == 200, r.text
    return r.json()


def audit_lines(settings):
    return [json.loads(line) for line in settings.audit_path.read_text().splitlines()]


def stored_rows(client):
    repo = client.app.state.repo
    with repo._session() as s:
        return list(s.scalars(select(AgentTokenRow)))


def test_install_issues_principal_and_hands_secret_to_executor(client, clock, executor, settings):
    assert run_action(client, clock)["state"] == "succeeded"
    grant = executor.agents[-1]
    assert grant.name == SECRET and grant.principal_id == f"agent:{APP}"
    assert grant.gateway_url == "http://127.0.0.1:8080"  # derived from ONEMIND_HOST/PORT
    assert len(grant.token) >= 40
    assert grant.token not in repr(grant)

    # the token works as a bearer token, as an agent principal
    r = client.get("/v1/apps", headers=bearer(grant.token))
    assert r.status_code == 200
    r = client.post("/v1/actions", json=action_body(clock, app_id="whoami", key="by-app"), headers=bearer(grant.token))
    assert r.status_code == 201
    assert r.json()["requested_by"] == {"id": f"agent:{APP}", "kind": "agent"}
    # ... and can never approve
    r2 = client.post(f"/v1/actions/{r.json()['id']}/approve", headers=bearer(grant.token))
    assert r2.status_code == 403 and r2.json()["error"] == "permission_denied"

    # only a hash is stored; the token is nowhere on disk the gateway writes
    (row,) = stored_rows(client)
    assert row.principal_id == f"agent:{APP}" and row.revoked_at is None
    assert row.token_hash != grant.token and len(row.token_hash) == 64
    assert grant.token not in settings.audit_path.read_text()
    assert grant.token not in json.dumps(client.get("/v1/actions", headers=OWNER).json())
    if settings.db_url.startswith("sqlite:///"):
        assert grant.token.encode() not in open(settings.db_url[len("sqlite:///"):], "rb").read()
    events = [rec["event"] for rec in audit_lines(settings)]
    assert "agent.principal.issued" in events


def test_apps_without_spec_agent_get_no_principal(client, clock, executor):
    run_action(client, clock, app_id="uptime-kuma")
    assert executor.agents == [None]
    assert stored_rows(client) == []


def test_remove_revokes_principal_and_deletes_secret(client, clock, executor, settings):
    run_action(client, clock)
    token = executor.agents[-1].token
    assert client.get("/v1/nodes", headers=bearer(token)).status_code == 200
    run_action(client, clock, type_="app.remove", key="k2")
    grant = executor.agents[-1]
    assert grant.name == SECRET and grant.token is None
    r = client.get("/v1/nodes", headers=bearer(token))
    assert r.status_code == 401 and r.json()["error"] == "unauthenticated"
    (row,) = stored_rows(client)
    assert row.revoked_at is not None
    assert "agent.principal.revoked" in [rec["event"] for rec in audit_lines(settings)]


def test_reinstall_rotates_the_token(client, clock, executor):
    run_action(client, clock)
    first = executor.agents[-1].token
    run_action(client, clock, type_="app.remove", key="k2")
    run_action(client, clock, key="k3")
    second = executor.agents[-1].token
    assert first != second
    assert client.get("/v1/apps", headers=bearer(first)).status_code == 401
    assert client.get("/v1/apps", headers=bearer(second)).status_code == 200
    assert len(stored_rows(client)) == 1


@pytest.mark.parametrize("outcome", ["failed", "outcome_unknown"])
def test_failed_install_revokes_principal(settings, clock, outcome):
    ex = ScriptedExecutor(outcome)
    with TestClient(create_app(settings, clock=clock, executor=ex)) as c:
        assert run_action(c, clock)["state"] == outcome
        assert c.get("/v1/apps", headers=bearer(ex.agents[-1].token)).status_code == 401


def test_executor_crash_revokes_principal(settings, clock):
    ex = ScriptedExecutor(raise_exc=True)
    with TestClient(create_app(settings, clock=clock, executor=ex)) as c:
        assert run_action(c, clock)["state"] == "outcome_unknown"
        assert c.get("/v1/apps", headers=bearer(ex.agents[-1].token)).status_code == 401


def test_static_tokens_still_honoured_alongside_db(client, clock, executor):
    run_action(client, clock)
    assert client.get("/v1/apps", headers=AGENT).status_code == 200
    assert client.get("/v1/apps", headers=OWNER).status_code == 200


def test_public_url_goes_into_the_secret(settings, clock):
    ex = ScriptedExecutor()
    s = replace(settings, public_url="https://hub.example.test")
    with TestClient(create_app(s, clock=clock, executor=ex)) as c:
        run_action(c, clock)
    assert ex.agents[-1].gateway_url == "https://hub.example.test"


def test_public_url_env_parsing(monkeypatch):
    base = {"ONEMIND_NODE_ID": "x"}
    s = Settings.from_env({**base, "ONEMIND_PUBLIC_URL": "https://hub.example.test/"})
    assert s.gateway_url() == "https://hub.example.test"
    with pytest.raises(ValueError):
        Settings.from_env({**base, "ONEMIND_PUBLIC_URL": "hub.example.test"})
    monkeypatch.setattr("socket.gethostname", lambda: "hubhost")
    assert Settings.from_env({**base, "ONEMIND_PORT": "9000"}).gateway_url() == "http://hubhost:9000"


def test_audit_records_requester_and_approver_ids(client, clock, executor, settings):
    run_action(client, clock, app_id="uptime-kuma", requester=AGENT)
    recs = audit_lines(settings)
    requested = next(r for r in recs if r["event"] == "action.requested")
    assert requested["principal"]["id"] == "hermes" and requested["data"]["requested_by"] == "hermes"
    for event in ("action.approved", "action.dispatched", "action.succeeded"):
        rec = next(r for r in recs if r["event"] == event)
        assert rec["data"]["requested_by"] == "hermes", event
        assert rec["data"]["approved_by"] == "owner", event
    assert verify(settings.audit_path)[0]


# ---- manifests and executors ------------------------------------------------------------

@pytest.mark.parametrize(
    "agent,ok",
    [
        ({"principal": True, "secret": "hermes-agent-onemind"}, True),
        ({"principal": False}, True),
        ({"principal": True}, False),
        ({"principal": True, "secret": "Bad_Name"}, False),
        ({"principal": "yes", "secret": "x"}, False),
        ("true", False),
    ],
)
def test_spec_agent_validation(agent, ok):
    assert (agent_spec_errors({"agent": agent}) == []) is ok


def test_invalid_spec_agent_skips_the_app(settings):
    p = settings.apps_dir / APP / "onemind.app.yaml"
    p.write_text(p.read_text().replace(f"secret: {SECRET}", "secret: NOPE"))
    cat = Catalog(settings.apps_dir)
    assert APP not in cat.load() and APP in cat.errors


def test_kubernetes_executor_creates_secret_before_manifests(settings, clock):
    # a hostile kubectl that echoes its input must not leak the token into the result
    run = FakeKubectl(echo=True)
    ex = KubernetesExecutor(runner=run, resolve=lambda host: ["192.0.2.10"])
    conform_to_schema(settings.apps_dir / APP)
    s = replace(settings, executor="kubernetes", public_url="http://hub.example.test:8080", app_schema_path=SCHEMA)
    with TestClient(create_app(s, clock=clock, executor=ex)) as c:
        action = run_action(c, clock)
        assert action["state"] == "succeeded"
        calls = run.cluster_calls
        argvs = [argv for argv, _ in calls]
        assert argvs[0] == ["kubectl", "apply", "-f", "-"]  # namespace
        assert "onemind-allow" in calls[1][1]  # network policy, with egress to the gateway only
        allow = json.loads(calls[1][1].split("---")[1])
        assert {"to": [{"ipBlock": {"cidr": "192.0.2.10/32"}}], "ports": [{"protocol": "TCP", "port": 8080}]} in allow["spec"]["egress"]
        assert argvs[2] == [  # agent Secret, server-side so no last-applied annotation holds the token
            "kubectl", "apply", "--server-side", "--field-manager=onemind-gateway", "--force-conflicts",
            "-n", "app-hermes-like", "-f", "-",
        ]
        assert argvs[3] == ["kubectl", "apply", "-n", "app-hermes-like", "-f", "-"]  # then the checked render
        secret = json.loads(calls[2][1])
        assert secret["kind"] == "Secret" and secret["metadata"]["name"] == SECRET
        assert secret["metadata"]["namespace"] == "app-hermes-like"
        assert "stringData" not in secret
        data = {k: base64.b64decode(v).decode() for k, v in secret["data"].items()}
        assert data["ONEMIND_GATEWAY_URL"] == "http://hub.example.test:8080"
        token = data["ONEMIND_AGENT_TOKEN"]
        assert c.get("/v1/nodes", headers=bearer(token)).status_code == 200
        for form in (token, secret["data"]["ONEMIND_AGENT_TOKEN"]):  # raw and base64
            assert form not in json.dumps(action)
            assert form not in settings.audit_path.read_text()

        run.calls.clear()
        assert run_action(c, clock, type_="app.remove", key="k2")["state"] == "succeeded"
        argvs = [argv for argv, _ in run.calls]
        assert argvs[0] == ["kubectl", "delete", "secret", SECRET, "-n", "app-hermes-like", "--ignore-not-found=true"]
        assert argvs[1][:3] == ["kubectl", "delete", "namespace"]
        assert c.get("/v1/nodes", headers=bearer(token)).status_code == 401


def test_noop_executor_records_what_it_would_do(settings, clock):
    with make_client(settings, clock) as c:
        action = run_action(c, clock)
        steps = action["result"]["steps"]
        assert steps[0]["would"] == f"create Secret {SECRET} in app-{APP}"
        assert steps[0]["keys"] == ["ONEMIND_GATEWAY_URL", "ONEMIND_AGENT_TOKEN"]
        assert steps[0]["principal"] == f"agent:{APP}"
        removal = run_action(c, clock, type_="app.remove", key="k2")
        assert removal["result"]["steps"][0]["would"] == f"delete Secret {SECRET} in app-{APP}"
