# SPDX-License-Identifier: Apache-2.0
"""aiPolicy before app data reaches an agent (#165): one deny-by-default rule.

A plugin tool's output is the app's own data. An agent that requested the tool sees its action
through MCP (get_action, list_actions, onemind://actions/{id}) and through REST (GET /v1/actions,
GET /v1/actions/{id}, an idempotent replay of the tool call); the output must be withheld on every
one of them unless the app's catalog aiPolicy is "allowed". A read tool returns app data at once, so
an agent may not run it at all under any other policy. GET /v1/apps shows the policy, for
`onemind apps`.
"""

import json
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
import yaml

from conftest import AGENT, OWNER, make_client
from onemind_core import ai_policy
from onemind_core.identity.crypto import new_secret, sha256_hex
from onemind_core.identity.models import TokenRow
from onemind_core.plugins import dispatch
from test_identity import id_settings
from test_plugin_credentials import approve, request
from test_plugin_workload import plugin_settings  # noqa: F401

CANARY = 7_316_042  # the value the app's backend returns; it must never reach a denied agent
OUTPUT = {"type": "object", "properties": {"heart_rate": {"type": "integer"}},
          "required": ["heart_rate"], "additionalProperties": False}
ABSENT = "absent"


@pytest.fixture
def agent_tool_action(plugin_settings, clock, monkeypatch, request_policy):  # noqa: F811
    """A real install, a real agent-requested plugin.invoke, approved by the owner and run once."""
    path = Path(plugin_settings.apps_dir) / "uptime-kuma" / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["spec"]["extensions"]["tools"] = [{
        "name": "change", "title": "Change", "description": "untrusted plugin text", "effect": "write",
        "input": {"type": "object", "additionalProperties": False}, "output": deepcopy(OUTPUT),
        "exposure": {"rest": True},
    }]
    if request_policy != ABSENT:
        doc["spec"]["aiPolicy"] = request_policy
    path.write_text(yaml.safe_dump(doc))
    monkeypatch.setattr(dispatch, "client", lambda: httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"heart_rate": CANARY})), trust_env=False))
    with make_client(id_settings(plugin_settings, require_passkey_approval=False), clock) as client:
        approve(client, request(client, clock, "app.install"))
        filed = client.post("/v1/plugins/uptime-kuma/tools/change", headers=AGENT,
                            json={"arguments": {}, "idempotency_key": "ai-policy"})
        assert filed.status_code == 201, filed.text
        done = approve(client, filed.json()["id"])
        assert done["state"] == "succeeded"
        # The owner's own view keeps the output: aiPolicy limits AI, never the person.
        assert str(CANARY) in client.get(f"/v1/actions/{done['id']}", headers=OWNER).text
        yield client, done["id"]


@pytest.fixture
def request_policy(request):
    return request.param


def mcp(client, method, params):
    r = client.post("/mcp", headers=AGENT, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    assert r.status_code == 200, r.text
    return r.json()["result"]


def agent_views(client, action_id):
    one = mcp(client, "tools/call", {"name": "get_action", "arguments": {"action_id": action_id}})
    assert one["isError"] is False
    many = mcp(client, "tools/call", {"name": "list_actions", "arguments": {}})
    assert action_id in {a["id"] for a in many["structuredContent"]["actions"]}
    res = mcp(client, "resources/read", {"uri": f"onemind://actions/{action_id}"})
    return [json.dumps(one), json.dumps(many), json.dumps(res)]


def agent_rest_views(client, action_id):
    """The same action read by the same agent over REST: one action, the ledger, and a replay."""
    one = client.get(f"/v1/actions/{action_id}", headers=AGENT)
    many = client.get("/v1/actions", headers=AGENT)
    replay = client.post("/v1/plugins/uptime-kuma/tools/change", headers=AGENT,
                         json={"arguments": {}, "idempotency_key": "ai-policy"})
    for r in (one, many, replay):
        assert r.status_code == 200, r.text
    assert replay.json()["id"] == action_id and action_id in {a["id"] for a in many.json()}
    return [one.text, many.text, replay.text]


@pytest.mark.parametrize("request_policy", [
    ABSENT, "display-only", "prohibited", "consent-required", "official-mcp-only", "local-only", None,
], indirect=True)
def test_denied_app_data_never_reaches_an_agent(agent_tool_action):
    client, action_id = agent_tool_action
    for text in agent_views(client, action_id) + agent_rest_views(client, action_id):
        assert str(CANARY) not in text
        assert "output_withheld" in text
    # The agent still learns its request ran.
    one = mcp(client, "tools/call", {"name": "get_action", "arguments": {"action_id": action_id}})
    assert one["structuredContent"]["state"] == "succeeded"
    assert one["structuredContent"]["result"]["steps"][0]["tool"] == "change"


@pytest.mark.parametrize("request_policy", ["allowed"], indirect=True)
def test_allowed_app_data_reaches_an_agent(agent_tool_action):
    client, action_id = agent_tool_action
    for text in agent_views(client, action_id) + agent_rest_views(client, action_id):
        assert str(CANARY) in text
        assert "output_withheld" not in text


@pytest.fixture
def agent_read_tool(plugin_settings, clock, monkeypatch, request_policy):  # noqa: F811
    """A real install with a read tool, and an agent token holding the exact grant for tools."""
    path = Path(plugin_settings.apps_dir) / "uptime-kuma" / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["spec"]["extensions"]["tools"] = [{
        "name": "status", "title": "Status", "description": "untrusted plugin text", "effect": "read",
        "input": {"type": "object", "additionalProperties": False}, "output": deepcopy(OUTPUT),
        "exposure": {"rest": True},
    }]
    if request_policy != ABSENT:
        doc["spec"]["aiPolicy"] = request_policy
    path.write_text(yaml.safe_dump(doc))
    calls = []

    def backend(req):
        calls.append(req)
        return httpx.Response(200, json={"heart_rate": CANARY})
    monkeypatch.setattr(dispatch, "client", lambda: httpx.Client(transport=httpx.MockTransport(backend), trust_env=False))
    with make_client(id_settings(plugin_settings, require_passkey_approval=False), clock) as client:
        approve(client, request(client, clock, "app.install"))
        token = new_secret("pat")
        client.app.state.identity.repo.add(TokenRow(
            id="ai-reader", prefix=token[:11], hash=sha256_hex(token), name="AI reader", kind="agent",
            principal_id="agent:reader", owner_user_id=None,
            scopes=["apps:read", "actions:request:plugin.invoke"], source="api", created_by="owner",
            created_at=clock()))
        yield client, {"Authorization": "Bearer " + token}, calls


@pytest.mark.parametrize("request_policy", [
    ABSENT, "display-only", "prohibited", "consent-required", "official-mcp-only", "local-only", None,
], indirect=True)
def test_agent_cannot_run_a_read_tool_of_a_denied_app(agent_read_tool):
    client, agent, calls = agent_read_tool
    refused = client.post("/v1/plugins/uptime-kuma/tools/status", headers=agent, json={"arguments": {}})
    assert refused.status_code == 403, refused.text
    assert refused.json()["reason"] == "ai_policy" and str(CANARY) not in refused.text
    assert calls == []  # the app's backend was never asked
    # aiPolicy limits AI, never the person: the owner still reads the app's data.
    mine = client.post("/v1/plugins/uptime-kuma/tools/status", headers=OWNER, json={"arguments": {}})
    assert mine.status_code == 200 and mine.json() == {"output": {"heart_rate": CANARY}}


@pytest.mark.parametrize("request_policy", ["allowed"], indirect=True)
def test_agent_runs_a_read_tool_of_an_allowed_app(agent_read_tool):
    client, agent, calls = agent_read_tool
    got = client.post("/v1/plugins/uptime-kuma/tools/status", headers=agent, json={"arguments": {}})
    assert got.status_code == 200, got.text
    assert got.json() == {"output": {"heart_rate": CANARY}} and len(calls) == 1


def test_actions_for_agent_reads_the_catalog_only_when_output_is_present():
    plain = [{"id": "a", "params": {"app_id": "x"}, "result": {"steps": [{"step": "apply"}]}}]
    assert ai_policy.actions_for_agent(plain, lambda: pytest.fail("catalog read for no output")) is plain
    rows = [{"id": "b", "params": {"app_id": "x"}, "result": {"steps": [{"tool": "t", "output": CANARY}]}},
            {"id": "c", "params": {"app_id": "y"}, "result": {"steps": [{"tool": "t", "output": CANARY}]}},
            {"id": "d", "params": {"app_id": "gone"}, "result": {"steps": [{"tool": "t", "output": CANARY}]}}]
    seen = ai_policy.actions_for_agent(rows, lambda: [{"id": "x", "aiPolicy": "allowed"}, {"id": "y"}])
    assert [("output" in a["result"]["steps"][0]) for a in seen] == [True, False, False]
    assert ai_policy.app_policy([{"id": "x", "aiPolicy": "allowed"}], "x") == "allowed"
    assert ai_policy.app_policy([], "x") is ai_policy.ABSENT


@pytest.mark.parametrize("policy", [ai_policy.ABSENT, None, "unknown", {"allowed": True}, "display-only",
                                    "prohibited", "consent-required", "official-mcp-only"])
def test_withhold_is_deny_by_default(policy):
    action = {"id": "a", "params": {"app_id": "x"},
              "result": {"outcome": "succeeded", "message": "ok", "steps": [{"tool": "t", "output": {"v": CANARY}}]}}
    seen = ai_policy.withhold_app_data(action, policy)
    assert str(CANARY) not in json.dumps(seen)
    assert seen["result"]["message"] == "ok" and seen["result"]["steps"][0]["tool"] == "t"
    assert action["result"]["steps"][0]["output"] == {"v": CANARY}  # the stored action is not changed


def test_withhold_passes_allowed_data_and_actions_without_output():
    action = {"result": {"steps": [{"tool": "t", "output": {"v": 1}}]}}
    assert ai_policy.withhold_app_data(action, "allowed") is action
    plain = {"result": {"outcome": "succeeded", "steps": [{"step": "apply"}]}}
    assert ai_policy.withhold_app_data(plain, ai_policy.ABSENT) is plain
    assert ai_policy.withhold_app_data({"result": None}, ai_policy.ABSENT) == {"result": None}


def test_rest_and_mcp_read_the_same_policy():
    # agent_catalog (REST) reads the manifest, the MCP catalogue reads the catalog summary row.
    for manifest in ({"metadata": {"category": "health"}, "spec": {}},
                     {"metadata": {}, "spec": {"aiPolicy": None}},
                     {"metadata": {}, "spec": {"aiPolicy": "allowed"}},
                     {"metadata": {}, "spec": {}}):
        policy = ai_policy.manifest_policy(manifest)
        row = {} if policy is ai_policy.ABSENT else {"aiPolicy": policy}
        for destination in ai_policy.DESTINATIONS:
            assert ai_policy.decide(policy, destination) == ai_policy.decide(ai_policy.summary_policy(row), destination)


@pytest.mark.parametrize("category,declared,shown", [
    ("productivity", ABSENT, None),
    ("health", ABSENT, "display-only"),
    ("wellness", ABSENT, "display-only"),
    ("productivity", "allowed", "allowed"),
    ("productivity", "prohibited", "prohibited"),
    ("productivity", "local-only", "unknown"),
    ("productivity", None, "unknown"),
    ("productivity", {"allowed": True}, "unknown"),
])
def test_apps_list_shows_ai_policy(settings, clock, executor, category, declared, shown):
    path = settings.apps_dir / "whoami" / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["metadata"]["category"] = category
    if declared != ABSENT:
        doc["spec"]["aiPolicy"] = declared
    path.write_text(yaml.safe_dump(doc))
    with make_client(settings, clock, executor) as client:
        r = client.get("/v1/apps", headers=OWNER)
        assert r.status_code == 200, r.text
        row = next(a for a in r.json() if a["id"] == "whoami")
        assert row["aiPolicy"] == shown
        schema = client.get("/openapi.json").json()["components"]["schemas"]["CatalogApp"]
        assert "aiPolicy" in schema["properties"]
        got = mcp(client, "tools/call", {"name": "get_app", "arguments": {"app_id": "whoami"}})
        if shown in (None, "allowed"):  # the agent sees the entry, with the same aiPolicy value
            assert got["structuredContent"]["aiPolicy"] == shown
        else:
            assert got["isError"] is True
