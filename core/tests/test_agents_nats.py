# SPDX-License-Identifier: Apache-2.0
"""#627: the AGENTS NATS account and one user per agent principal (natsconf.py, agents_nats.py).

internal/leaf/agents_accounts_test.go loads hub-accounts-agents.golden.conf into a real nats-server
v2.15 and proves the acceptance test: an agent serves its prompt and heartbeat and sends a request,
cannot publish a core subject or read another agent's prompt, has no JetStream, and is refused on
its next connect once its user line is gone. These tests pin the file it loads and the gateway side.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest

from conftest import ADULT, AGENT, OWNER, apply_settings_change, approve_settings_change, enroll_agent
from onemind_core import subjects
from onemind_core.agent_principals import DEFAULT_BUDGET_PER_DAY, AgentPrincipals
from onemind_core.agents_nats import AgentNatsKeys, agent_token, agent_users
from onemind_core.mcp.tools import TOOL_NAMES
from onemind_core.natsconf import AGENTS_LIMITS, AgentUser, NodeAccount, render_accounts
from onemind_core.netconf import FabricSettings
from test_net import fabric_of, hs, kube, net_settings  # noqa: F401 (pytest fixtures)
from test_net import nc as net_client  # noqa: F401

GOLDEN = Path(__file__).resolve().parents[2] / "internal" / "leaf" / "testdata" / "hub-accounts-agents.golden.conf"
PUB_A = "UBBUEVU3RVFLTSYWTDDLUC2TLY3YDZKKYWVTUOW4UFVUY6BICGH55O2Y"
PUB_B = "UC3WGTQV7ERIG2GOPKU7CXZ6B6DPY4S2DC4ZIUZ4XVZENDHGM3RRMZF3"
AGENTS = [AgentUser("bbb", PUB_B), AgentUser("aaa", PUB_A)]
KEY_PATH = "/v1/agents/agent:aaa/nats-key"


@pytest.fixture
def nc(net_client):
    enroll_agent(net_client, "agent:aaa")
    return net_client


def agents_block(text: str) -> str:
    return text[text.index("  AGENTS: {"):]


def allow_lists(line: str) -> tuple[list[str], list[str]]:
    pub = re.search(r"publish: \{allow: \[(.*?)\]\}", line).group(1)
    sub = re.search(r"subscribe: \{allow: \[(.*?)\]\}", line).group(1)
    return re.findall(r'"([^"]+)"', pub), re.findall(r'"([^"]+)"', sub)


# ---- the file the Go test loads -------------------------------------------------------------------
def test_agents_golden_matches_the_go_acceptance_test():
    assert render_accounts([], [], 0, AGENTS) == GOLDEN.read_text()


STOPPED_GOLDEN = GOLDEN.with_name("hub-accounts-agents-stopped.golden.conf")


def test_agents_stopped_golden_matches_the_go_acceptance_test():
    """#1199 review: with the kill switch on, the file has no AGENTS account at all; the Go test reloads
    nats-server with it and sees connected agents cut off."""
    assert render_accounts([], [], 0, AGENTS, agents_stopped=True) == STOPPED_GOLDEN.read_text()
    assert "AGENTS" not in STOPPED_GOLDEN.read_text()


def test_removing_an_agent_removes_exactly_its_line():
    """The Go test revokes B by deleting B's line and reloading; that must be what the gateway writes."""
    without_b = "".join(line for line in GOLDEN.read_text().splitlines(keepends=True) if PUB_B not in line)
    assert render_accounts([], [], 0, [AgentUser("aaa", PUB_A)]) == without_b


def test_no_agents_leaves_the_file_as_before():
    nodes = [NodeAccount("aaa111", PUB_A)]
    plain = render_accounts(nodes)
    assert "AGENTS" not in plain and "agents." not in plain
    assert render_accounts(nodes, agents=[]) == plain


def test_each_agent_may_use_only_its_own_subjects():
    text = agents_block(render_accounts([], [], 0, AGENTS))
    line = next(x for x in text.splitlines() if PUB_A in x)
    pub, sub = allow_lists(line)
    assert pub == ["agents.prompt.aaa.*.*", "agents.status.aaa.*.*", "agents.hb.aaa.*.*", "_INBOX_aaa.>",
                   "onemind.request.agent.aaa.*"]
    assert sub == ["agents.prompt.aaa.*.*", "agents.status.aaa.*.*", "agents.hb.aaa.*.*", "_INBOX_aaa.>",
                   "$SRV.PING", "$SRV.INFO", "$SRV.STATS", "$SRV.*.aaa", "$SRV.*.aaa.*"]
    assert 'allowed_connection_types: ["STANDARD"]' in line and "allow_responses" in line
    for s in pub + sub:
        assert "bbb" not in s and s not in (">", "*") and not s.startswith(("$JS", "_INBOX.", "onemind.event",
                                                                              "onemind.asset", "onemind.node",
                                                                              "onemind.audit", "onemind.plugin"))
    # The one request subject is inside the registered tree, under the agent's own id.
    assert subjects.load().covers("onemind.request.agent.aaa.*").ok


def test_agents_account_has_limits_and_no_jetstream():
    text = agents_block(render_accounts([], [], 1 << 30, AGENTS))
    assert "jetstream" not in text
    # nats-server v2.15.3 parseAccountLimits knows exactly these four; any other name fails the config.
    assert {k for k, _ in AGENTS_LIMITS} == {"max_connections", "max_subscriptions", "max_payload", "max_leafnodes"}
    assert "limits: {max_connections: 64, max_subscriptions: 1024, max_payload: 262144, max_leafnodes: 0}" in text


@pytest.mark.parametrize("token", ["", "Hermes", "a.b", "a b", "a*", "a>", "x" * 64])
def test_agent_user_refuses_names_that_are_not_one_token(token):
    with pytest.raises(ValueError):
        AgentUser(token, PUB_A)


def test_agent_user_refuses_a_non_user_key():
    with pytest.raises(ValueError):
        AgentUser("aaa", "N" + PUB_A[1:])


@pytest.mark.parametrize("pid", ["hermes", "agent:a.b", "agent:", "user:aaa"])
def test_only_one_token_agent_principals_get_a_nats_user(pid):
    with pytest.raises(ValueError):
        agent_token(pid)
    assert agent_token("agent:aaa") == "aaa"


def test_no_generic_publish_or_kv_tool_for_agents():
    """Must refuse: generic publish or KV-put tools. Agents talk on their own subjects only."""
    assert not [t for t in TOOL_NAMES if re.search(r"publish|kv|put|nats|subject", t)]


# ---- the owner's routes and the accounts file ----------------------------------------------------
def accounts(client) -> str:
    path = client.app.state.gateway.settings.section(FabricSettings).nats_accounts_file
    return path.read_text() if path.exists() else ""


def test_owner_registers_and_removes_an_agent_key(nc):  # noqa: F811
    r = nc.get(KEY_PATH, headers=OWNER)
    assert r.status_code == 200 and r.json()["nkey"] is None and r.json()["subjects"] == []
    headers = {**OWNER, "Idempotency-Key": "register-agent-key"}
    request = nc.put(KEY_PATH, json={"nkey": PUB_A}, headers=headers)
    assert PUB_A not in accounts(nc)
    done = apply_settings_change(nc, request)
    replay = nc.put(KEY_PATH, json={"nkey": PUB_A}, headers=headers)
    assert replay.status_code == 202 and replay.json()["id"] == done["id"]
    assert replay.json()["state"] == "succeeded"
    assert nc.put(KEY_PATH, json={"nkey": PUB_B}, headers=headers).status_code == 409
    r = nc.get(KEY_PATH, headers=OWNER)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["account"] == "AGENTS" and body["nkey"] == PUB_A and body["tools"] == []
    assert body["inbox_prefix"] == "_INBOX_aaa" and body["request_subject"] == "onemind.request.agent.aaa.*"
    text = accounts(nc)
    assert f'{{nkey: "{PUB_A}"' in text and "# agent:aaa" in text
    assert '{service: "onemind.request.agent.>", accounts: ["AGENTS"]}' in text
    # A new key replaces the old one: one user per agent principal.
    replacement = nc.put(KEY_PATH, json={"nkey": PUB_B}, headers=OWNER)
    assert PUB_A in accounts(nc) and PUB_B not in accounts(nc)
    apply_settings_change(nc, replacement)
    assert PUB_A not in accounts(nc) and PUB_B in accounts(nc)
    r = nc.delete(KEY_PATH, headers=OWNER)
    assert r.status_code == 200 and r.json()["nkey"] is None
    assert "AGENTS" not in accounts(nc)
    assert nc.delete(KEY_PATH, headers=OWNER).status_code == 200  # removing twice is fine


def test_a_restart_writes_the_agent_users_back(nc):  # noqa: F811
    apply_settings_change(nc, nc.put(KEY_PATH, json={"nkey": PUB_A}, headers=OWNER))
    path = nc.app.state.gateway.settings.section(FabricSettings).nats_accounts_file
    path.unlink()
    fabric_of(nc).reconcile()  # what the gateway runs at start
    assert PUB_A in path.read_text()


def test_cancelling_an_agent_removes_its_nats_user(nc):  # noqa: F811
    apply_settings_change(nc, nc.put(KEY_PATH, json={"nkey": PUB_A}, headers=OWNER))
    r = nc.post("/v1/agents/agent:aaa/cancel", json={}, headers=OWNER)
    assert r.status_code == 200, r.text
    assert PUB_A not in accounts(nc)
    assert nc.get(KEY_PATH, headers=OWNER).json()["nkey"] is None


def fail_next_write(monkeypatch):
    """The next accounts-file write raises an OSError (a full or read-only disk); later ones work."""
    from onemind_core import fabric as fabric_mod
    real = fabric_mod.write_accounts
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError(28, "No space left on device")
        return real(*args, **kwargs)

    monkeypatch.setattr(fabric_mod, "write_accounts", flaky)


def test_key_rewrite_failure_reports_the_committed_key_and_restart_reconciles(nc, monkeypatch):
    apply_settings_change(nc, nc.put(KEY_PATH, json={"nkey": PUB_A}, headers=OWNER))
    fail_next_write(monkeypatch)
    reply = nc.put(KEY_PATH, json={"nkey": PUB_B}, headers={**OWNER, "Idempotency-Key": "rotate-key"})
    done = approve_settings_change(nc, reply)
    assert done["state"] == "outcome_unknown"
    assert done["result"]["steps"] == [{"committed": True, "accounts_written": False, "broker_enforced": None}]
    assert PUB_A in accounts(nc) and PUB_B not in accounts(nc)
    assert nc.get(KEY_PATH, headers=OWNER).json()["nkey"] == PUB_B
    assert agent_users(nc.app.state.gateway.db) == [AgentUser("aaa", PUB_B)]  # what callout reads
    replay = nc.put(KEY_PATH, json={"nkey": PUB_B}, headers={**OWNER, "Idempotency-Key": "rotate-key"})
    assert replay.status_code == 202 and replay.json()["id"] == done["id"]
    assert replay.json()["result"] == done["result"]
    fabric_of(nc).reconcile()
    assert PUB_A not in accounts(nc) and PUB_B in accounts(nc)


@pytest.mark.parametrize("kind", ["budget", "nats-key"])
def test_replacement_cannot_inherit_an_approval_that_is_applying(net_client, monkeypatch, kind):
    name = "agent:aaa"
    first = enroll_agent(net_client, name)
    base = f"/v1/agents/{name}"
    registry = net_client.app.state.actions.principals
    uid = registry.live(name)["uid"]
    cls, method, body = ((AgentPrincipals, "set_budget", {"budget_per_day": DEFAULT_BUDGET_PER_DAY + 1})
                         if kind == "budget" else (AgentNatsKeys, "set", {"nkey": PUB_A}))
    queued, stale = [net_client.put(f"{base}/{kind}", headers=OWNER, json=body) for _ in range(2)]
    assert queued.json()["params"]["before"]["principal_uid"] == uid
    writer_entered, replacement_checked = Event(), Event()
    write = getattr(cls, method)

    def wait_at_write(*args, **kwargs):
        writer_entered.set()
        assert replacement_checked.wait(5)
        result = write(*args, **kwargs)
        if kind == "budget":
            assert result["budget_per_day"] == body["budget_per_day"]
        else:
            assert agent_users(net_client.app.state.gateway.db) == [AgentUser("aaa", PUB_A)]
        return result

    def replace_agent():
        assert writer_entered.wait(5)
        entered_early = registry.lifecycle.acquire(blocking=False)
        if entered_early:
            registry.lifecycle.release()
        replacement_checked.set()
        assert not entered_early, "credential replacement can enter between recheck and write"
        assert net_client.delete(f"/v1/tokens/{first['id']}", headers=OWNER).status_code == 204
        enroll_agent(net_client, name)

    monkeypatch.setattr(cls, method, wait_at_write)
    with ThreadPoolExecutor(max_workers=1) as pool:
        replacement = pool.submit(replace_agent)
        apply_settings_change(net_client, queued)
        replacement.result(timeout=10)

    assert registry.live(name)["uid"] != uid
    assert approve_settings_change(net_client, stale)["state"] == "failed"
    assert net_client.get(base, headers=OWNER).json()["budget_per_day"] == DEFAULT_BUDGET_PER_DAY
    assert net_client.get(KEY_PATH, headers=OWNER).json()["nkey"] is None
    assert agent_users(net_client.app.state.gateway.db) == [] and PUB_A not in accounts(net_client)
    fabric_of(net_client).reconcile()
    assert PUB_A not in accounts(net_client)


def test_unenrolled_name_cannot_receive_an_approved_key_or_budget(net_client):
    for kind, body in (("nats-key", {"nkey": PUB_A}), ("budget", {"budget_per_day": DEFAULT_BUDGET_PER_DAY + 1})):
        r = net_client.put(f"/v1/agents/agent:aaa/{kind}", headers=OWNER, json=body)
        assert r.status_code == 409 and r.json()["reason"] == "unknown_principal"
    assert net_client.get("/v1/actions", headers=OWNER).json() == []


def test_upgrade_cannot_assign_legacy_grants_to_a_live_identity(nc, net_settings, clock):
    from sqlalchemy import text

    from conftest import make_client

    db = nc.app.state.gateway.db
    with db.engine.begin() as conn:
        conn.execute(text("UPDATE schema_versions SET version = 2 WHERE feature = 'agents'"))
        for column in ("budget_uid", "budget_ceiling", "resumed_uid"):
            conn.execute(text(f"ALTER TABLE agents_principals DROP COLUMN {column}"))
        conn.execute(text("ALTER TABLE agents_nats_keys DROP COLUMN principal_uid"))
        conn.execute(text("INSERT INTO agents_principals (principal_id, budget_per_day, updated_at) VALUES "
                          "('agent:aaa', :high, :now), ('hermes', 0, :now)"),
                     {"high": DEFAULT_BUDGET_PER_DAY + 1, "now": clock()})
        conn.execute(text("INSERT INTO agents_nats_keys (principal_id, nkey, added_by, added_at) "
                          "VALUES ('agent:aaa', :key, 'owner', :now)"), {"key": PUB_A, "now": clock()})
    with make_client(net_settings, clock) as reopened:
        assert reopened.get("/v1/agents/agent:aaa", headers=OWNER).json()["budget_per_day"] == DEFAULT_BUDGET_PER_DAY
        assert reopened.get("/v1/agents/hermes", headers=OWNER).json()["budget_per_day"] == 0
        assert reopened.get(KEY_PATH, headers=OWNER).json()["nkey"] is None
        assert agent_users(reopened.app.state.gateway.db) == [] and PUB_A not in accounts(reopened)


def test_a_retried_delete_after_a_failed_write_still_revokes(nc, monkeypatch):  # noqa: F811
    apply_settings_change(nc, nc.put(KEY_PATH, json={"nkey": PUB_A}, headers=OWNER))
    fail_next_write(monkeypatch)
    r = nc.delete(KEY_PATH, headers=OWNER)
    assert r.status_code == 503, r.text
    assert r.json()["reason"] == "nats_accounts_unwritable"
    assert PUB_A in accounts(nc)  # the row is gone but the user line is still there
    r = nc.delete(KEY_PATH, headers=OWNER)  # the retry must take the line out, not just say 200
    assert r.status_code == 200 and r.json()["nkey"] is None
    assert PUB_A not in accounts(nc) and "AGENTS" not in accounts(nc)


def test_a_retried_cancel_after_a_failed_write_still_revokes(nc, monkeypatch):  # noqa: F811
    apply_settings_change(nc, nc.put(KEY_PATH, json={"nkey": PUB_A}, headers=OWNER))
    fail_next_write(monkeypatch)
    r = nc.post("/v1/agents/agent:aaa/cancel", json={}, headers=OWNER)
    assert r.status_code == 503, r.text
    assert PUB_A in accounts(nc)
    r = nc.post("/v1/agents/agent:aaa/cancel", json={}, headers=OWNER)
    assert r.status_code == 200, r.text
    assert PUB_A not in accounts(nc)


@pytest.mark.parametrize("headers", [AGENT, ADULT])
def test_only_the_owner_sets_an_agent_key(nc, headers):  # noqa: F811
    assert nc.put(KEY_PATH, json={"nkey": PUB_A}, headers=headers).status_code == 403
    assert nc.delete(KEY_PATH, headers=headers).status_code == 403
    assert PUB_A not in accounts(nc)


@pytest.mark.real_mode_defaults
def test_a_nats_key_cannot_be_registered_before_passkey_enrollment(nc):  # noqa: F811
    r = nc.put(KEY_PATH, json={"nkey": PUB_A}, headers=OWNER)
    assert r.status_code == 409 and r.json()["reason"] == "no_owner_passkey", r.text
    assert nc.get(KEY_PATH, headers=OWNER).json()["nkey"] is None
    assert PUB_A not in accounts(nc)
    assert nc.get("/v1/actions", headers=OWNER).json() == []


@pytest.mark.parametrize("path,body", [
    ("/v1/agents/hermes/nats-key", {"nkey": PUB_A}),          # a static id: no subject token
    ("/v1/agents/agent:a.b/nats-key", {"nkey": PUB_A}),       # dotted: would own a prefix of another
    (KEY_PATH, {"nkey": "U" + "A" * 55}),                      # the checksum is wrong
    (KEY_PATH, {"nkey": PUB_A, "extra": 1}),
])
def test_bad_agent_keys_are_refused(nc, path, body):  # noqa: F811
    r = nc.put(path, json=body, headers=OWNER)
    assert r.status_code == 422, r.text
    assert "AGENTS" not in accounts(nc)
