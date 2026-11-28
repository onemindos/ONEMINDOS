# SPDX-License-Identifier: Apache-2.0
"""D-029 hybrid: NATS asks the gateway who may connect (callout.py, natsjwt.py, natsconf CalloutAccount).

The unit tests pin the answers and the accounts text. internal/leaf/testdata/callout-vector.json is a
fixed answer from `answer()`; internal/leaf/callout_test.go decodes and validates it with jwt/v2 and runs
hub-accounts-callout.golden.conf in nats-server 2.15.3 (pinned users get in with no responder, anyone
else is refused). The last test runs the real responder against a real nats-server when one is installed.
"""

from __future__ import annotations

import asyncio
import base64
import json
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from conftest import apply_settings_change, enroll_agent
from onemind_core import callout, natsjwt
from onemind_core.natsconf import AgentUser, CalloutAccount, NodeAccount, ServiceKey, render_accounts
from test_net import hs, kube, net_settings  # noqa: F401 (pytest fixtures)

TESTDATA = Path(__file__).resolve().parents[2] / "internal" / "leaf" / "testdata"
VECTOR = TESTDATA / "callout-vector.json"
GOLDEN = TESTDATA / "hub-accounts-callout.golden.conf"
PUB_A = "UBBUEVU3RVFLTSYWTDDLUC2TLY3YDZKKYWVTUOW4UFVUY6BICGH55O2Y"
PUB_GW = "UC3WGTQV7ERIG2GOPKU7CXZ6B6DPY4S2DC4ZIUZ4XVZENDHGM3RRMZF3"
NOW = 1_795_000_000


def _key(n: int) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes([n]) * 32)


ISSUER, SERVICE, SERVER, AGENT, EPHEMERAL = _key(1), _key(2), _key(3), _key(4), _key(5)
AGENT_PUB = natsjwt.public_key(AGENT, natsjwt.PREFIX_USER)
USER_NKEY = natsjwt.public_key(EPHEMERAL, natsjwt.PREFIX_USER)
SERVER_ID = natsjwt.public_key(SERVER, natsjwt.PREFIX_SERVER)
HERMES = AgentUser("hermes", AGENT_PUB)


def request(nkey=AGENT_PUB, signer=AGENT, nonce="nonce-1", go_style=False, server=SERVER) -> str:
    sig = signer.sign(nonce.encode())
    enc = base64.urlsafe_b64encode(sig).decode().rstrip("=") if go_style else base64.b64encode(sig).decode()
    sid = natsjwt.public_key(server, natsjwt.PREFIX_SERVER)
    claims = {"sub": natsjwt.public_key(ISSUER, natsjwt.PREFIX_ACCOUNT), "aud": "nats-authorization-request",
              "exp": NOW + 2,
              "nats": {"server_id": {"name": "hub", "host": "127.0.0.1", "id": sid}, "user_nkey": USER_NKEY,
                       "client_info": {"host": "127.0.0.1", "id": 7, "nonce": nonce, "kind": "Client", "type": "nats"},
                       "connect_opts": {"nkey": nkey, "sig": enc, "protocol": 1},
                       "type": "authorization_request", "version": 2}}
    return natsjwt.encode(claims, server, natsjwt.PREFIX_SERVER, NOW)


# ------------------------------------------------------------------- JWTs and keys
def test_jwt_round_trip_and_tamper():
    tok = natsjwt.encode({"sub": USER_NKEY, "nats": {"x": 1}}, ISSUER, natsjwt.PREFIX_ACCOUNT, NOW)
    c = natsjwt.decode(tok, natsjwt.PREFIX_ACCOUNT)
    assert c["iss"].startswith("A") and c["iat"] == NOW and c["sub"] == USER_NKEY and len(c["jti"]) == 52
    head, body, sig = tok.split(".")
    forged = base64.urlsafe_b64encode(json.dumps({**c, "sub": AGENT_PUB}).encode()).decode().rstrip("=")
    for bad in (f"{head}.{forged}.{sig}", tok[:-2] + "AA", "a.b", ""):
        with pytest.raises(natsjwt.JwtError):
            natsjwt.decode(bad, natsjwt.PREFIX_ACCOUNT)
    with pytest.raises(natsjwt.JwtError):  # signed by an account, not a server
        natsjwt.decode(tok, natsjwt.PREFIX_SERVER)


def test_seeds_round_trip_and_files_are_private(tmp_path):
    seed = natsjwt.encode_seed(ISSUER, natsjwt.PREFIX_ACCOUNT)
    assert seed.startswith("SA")
    k = natsjwt.decode_seed(seed, natsjwt.PREFIX_ACCOUNT)
    assert natsjwt.public_key(k, natsjwt.PREFIX_ACCOUNT) == natsjwt.public_key(ISSUER, natsjwt.PREFIX_ACCOUNT)
    with pytest.raises(natsjwt.JwtError):
        natsjwt.decode_seed(seed, natsjwt.PREFIX_USER)
    keys = callout.load_keys(tmp_path)
    again = callout.load_keys(tmp_path)
    assert keys.account == again.account
    for f in (callout.ISSUER_FILE, callout.SERVICE_FILE):
        assert (tmp_path / f).stat().st_mode & 0o777 == 0o600


# ------------------------------------------------------------------- the gateway's answers
@pytest.mark.parametrize("go_style", [False, True])
def test_registered_agent_gets_a_short_lived_jwt_with_its_own_allow_lists(go_style):
    d = callout.answer(request(go_style=go_style), ISSUER, {AGENT_PUB: HERMES}, False, NOW, ttl_s=600)
    assert d.allowed and d.agent == "agent:hermes" and d.reason == ""
    r = natsjwt.decode(d.response, natsjwt.PREFIX_ACCOUNT)
    assert r["sub"] == USER_NKEY and r["aud"] == SERVER_ID and r["nats"]["type"] == "authorization_response"
    u = natsjwt.decode(r["nats"]["jwt"], natsjwt.PREFIX_ACCOUNT)
    pub, sub = HERMES.allow()
    assert u["sub"] == USER_NKEY and u["aud"] == "AGENTS" and u["exp"] == NOW + 600 and u["name"] == "agent:hermes"
    assert u["nats"]["pub"] == {"allow": pub} and u["nats"]["sub"] == {"allow": sub}
    assert "onemind.request.agent.hermes.*" in pub and ">" not in pub + sub
    assert u["nats"]["resp"] == {"max": 1000, "ttl": 600 * 10**9}


@pytest.mark.parametrize("case,why", [
    ("unknown", "unknown key"), ("bad_sig", "nonce signature"), ("stopped", "Stop everything"), ("removed", "unknown key"),
])
def test_refusals_are_signed_answers_with_a_reason(case, why):
    req = request(signer=_key(9)) if case == "bad_sig" else request(nkey=PUB_A) if case == "unknown" else request()
    agents = {} if case == "removed" else {AGENT_PUB: HERMES}
    d = callout.answer(req, ISSUER, agents, case == "stopped", NOW)
    r = natsjwt.decode(d.response, natsjwt.PREFIX_ACCOUNT)
    assert not d.allowed and why in d.reason and why in r["nats"]["error"] and "jwt" not in r["nats"]


def test_a_request_that_does_not_verify_gets_no_answer():
    tok = request()
    head, body, sig = tok.split(".")
    with pytest.raises(natsjwt.JwtError):
        callout.answer(f"{head}.{body}.{sig[::-1]}", ISSUER, {AGENT_PUB: HERMES}, False, NOW)
    other = natsjwt.decode(request(), natsjwt.PREFIX_SERVER)
    other["nats"]["server_id"]["id"] = natsjwt.public_key(_key(8), natsjwt.PREFIX_SERVER)  # iss is not this server
    with pytest.raises(natsjwt.JwtError):
        callout.answer(natsjwt.encode(other, SERVER, natsjwt.PREFIX_SERVER, NOW), ISSUER, {AGENT_PUB: HERMES}, False, NOW)
    wrong = natsjwt.decode(request(), natsjwt.PREFIX_SERVER)
    wrong["nats"]["type"] = "authorization_response"  # a server-signed JWT that is not a request
    with pytest.raises(natsjwt.JwtError):
        callout.answer(natsjwt.encode(wrong, SERVER, natsjwt.PREFIX_SERVER, NOW), ISSUER, {AGENT_PUB: HERMES}, False, NOW)


@pytest.mark.parametrize("change", ["aud", "no_exp", "expired", "bool_exp"])
def test_a_request_not_addressed_to_the_callout_or_expired_gets_no_answer(change):
    """#1199 review: aud and exp of the request are checked, so an old request replayed into AUTH
    gets no fresh answer."""
    c = natsjwt.decode(request(), natsjwt.PREFIX_SERVER)
    c.pop("iat", None), c.pop("jti", None), c.pop("iss", None)
    if change == "aud":
        c["aud"] = "something-else"
    elif change == "no_exp":
        c.pop("exp")
    elif change == "bool_exp":
        c["exp"] = True
    tok = natsjwt.encode(c, SERVER, natsjwt.PREFIX_SERVER, NOW)
    now = NOW + 2 + callout.CLOCK_SKEW_S + 1 if change == "expired" else NOW
    with pytest.raises(natsjwt.JwtError):
        callout.answer(tok, ISSUER, {AGENT_PUB: HERMES}, False, now)
    if change == "expired":  # within the skew it is still answered
        assert callout.answer(tok, ISSUER, {AGENT_PUB: HERMES}, False, NOW + 2 + callout.CLOCK_SKEW_S).allowed


def test_responder_audits_every_answer(tmp_path):
    class Audit:
        lines: list = []

        def append(self, typ, actor, target, data):
            self.lines.append((typ, data))

    keys = callout.CalloutKeys(ISSUER, tmp_path / "svc.nk")
    r = callout.CalloutResponder("nats://x", keys, lambda: [HERMES], lambda: False, Audit(), lambda: NOW)
    assert r.handle(request().encode()) and r.handle(request(nkey=PUB_A).encode())
    assert r.handle(b"not a jwt") is None
    assert [d["decision"] for _, d in Audit.lines] == ["allowed", "denied"]
    assert Audit.lines[0] == ("nats.callout", {"decision": "allowed", "agent": "agent:hermes", "nkey": AGENT_PUB, "reason": None})


def test_vector_for_the_go_side_is_current():
    d = callout.answer(request(), ISSUER, {AGENT_PUB: HERMES}, False, NOW, ttl_s=600)
    want = {"issuer": natsjwt.public_key(ISSUER, natsjwt.PREFIX_ACCOUNT), "server_id": SERVER_ID, "user_nkey": USER_NKEY,
            "now": NOW, "response": d.response, "agent": HERMES.principal_id,
            "publish": HERMES.allow()[0], "subscribe": HERMES.allow()[1]}
    assert json.loads(VECTOR.read_text()) == want


# ------------------------------------------------------------------- the accounts text
def _callout_account() -> CalloutAccount:
    return CalloutAccount(natsjwt.public_key(ISSUER, natsjwt.PREFIX_ACCOUNT), natsjwt.public_key(SERVICE, natsjwt.PREFIX_USER))


def test_callout_accounts_golden():
    text = render_accounts([NodeAccount("aaa111", PUB_A)], [ServiceKey("gateway", PUB_GW)], 0, [HERMES], _callout_account())
    assert text == GOLDEN.read_text()
    agents = text.split("  AGENTS: {", 1)[1].split("\n  }", 1)[0]
    assert "nkey" not in agents                                    # no static agent user
    assert f'auth_users: ["{_callout_account().service}", "{PUB_GW}", "{PUB_A}"]' in text  # the pinned list
    assert "no_auth_user" not in text and "xkey" not in text


def test_no_callout_on_a_passwordless_dev_hub_or_when_off():
    assert "auth_callout" not in render_accounts([], [], 0, [HERMES], _callout_account())
    assert "auth_callout" not in render_accounts([], [ServiceKey("gateway", PUB_GW)], 0, [HERMES])
    with pytest.raises(ValueError):
        CalloutAccount(PUB_A, PUB_A)  # the issuer must be an account key


# ------------------------------------------------------------------- the real thing
NATS_SERVER = shutil.which("nats-server")


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.skipif(NATS_SERVER is None, reason="nats-server is not installed")
def test_real_server_asks_the_gateway(tmp_path):
    from nats.aio.client import Client
    from nats.errors import NoServersError

    from onemind_core.bus import SeedClient
    from onemind_core.natsconf import new_user_key

    keys = callout.load_keys(tmp_path / "custodian")
    gw_seed, gw_pub = new_user_key()
    ag_seed, ag_pub = new_user_key()
    (tmp_path / "gw.nk").write_text(gw_seed)
    (tmp_path / "agent.nk").write_text(ag_seed)
    (tmp_path / "accounts.conf").write_text(render_accounts([], [ServiceKey("gateway", gw_pub)], 0,
                                                            [AgentUser("hermes", ag_pub)], keys.account))
    port = _port()
    (tmp_path / "hub.conf").write_text(f'listen: "127.0.0.1:{port}"\ninclude "accounts.conf"\n')
    proc = subprocess.Popen([NATS_SERVER, "-c", str(tmp_path / "hub.conf")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"nats://127.0.0.1:{port}"
    state = {"agents": [AgentUser("hermes", ag_pub)], "stopped": False}

    async def connect(seed):
        nc = SeedClient()
        await nc.connect(url, nkeys_seed=str(seed), connect_timeout=3, allow_reconnect=False, max_reconnect_attempts=0)
        return nc

    async def refused(seed) -> bool:
        try:
            nc = await connect(seed)
        except (NoServersError, Exception):
            return True
        await nc.close()
        return False

    async def scenario():
        for _ in range(50):
            try:
                probe = Client()
                await probe.connect(url, connect_timeout=0.2, allow_reconnect=False, max_reconnect_attempts=0)
                await probe.close()
            except Exception:
                await asyncio.sleep(0.1)
                continue
            break
        # Gateway down: the agent is refused; the pinned hub service is not.
        assert await refused(tmp_path / "agent.nk")
        svc = await connect(tmp_path / "gw.nk")
        await svc.close()
        responder = callout.CalloutResponder(url, keys, lambda: state["agents"], lambda: state["stopped"], None)
        task = asyncio.create_task(responder.run())
        for _ in range(50):
            if responder.nc is not None:
                break
            await asyncio.sleep(0.1)
        ag = await connect(tmp_path / "agent.nk")                    # registered: in, scoped
        got = asyncio.Queue()
        gw = await connect(tmp_path / "gw.nk")
        async def seen(m):
            got.put_nowait(m.subject)

        await gw.subscribe("onemind.request.agent.>", cb=seen)
        await gw.flush()
        await ag.publish("onemind.request.agent.hermes.ask", b"{}")
        await ag.publish("onemind.request.agent.other.ask", b"{}")   # another agent's subject: refused
        await ag.flush()
        assert await asyncio.wait_for(got.get(), 3) == "onemind.request.agent.hermes.ask"
        await asyncio.sleep(0.5)
        assert got.empty()
        await ag.close()
        state["stopped"] = True                                       # Stop everything: refused
        assert await refused(tmp_path / "agent.nk")
        state["stopped"] = False
        # #1199 review, D-029 "Stop everything cuts agents off the bus": an agent already connected
        # is cut at the reload that follows the switch (the file loses AGENTS), not when its JWT expires.
        ag = await connect(tmp_path / "agent.nk")
        assert ag.is_connected
        state["stopped"] = True
        (tmp_path / "accounts.conf").write_text(render_accounts([], [ServiceKey("gateway", gw_pub)], 0,
                                                                state["agents"], keys.account, agents_stopped=True))
        proc.send_signal(signal.SIGHUP)                               # what onemind-nats-reload.service does
        for _ in range(50):
            if not ag.is_connected:
                break
            await asyncio.sleep(0.1)
        assert not ag.is_connected, "a connected agent stayed on the bus after Stop everything"
        assert await refused(tmp_path / "agent.nk")
        svc = await connect(tmp_path / "gw.nk")                       # the pinned hub service is not cut
        await svc.close()
        state["stopped"], state["agents"] = False, []                 # key removed: refused, no reload
        assert await refused(tmp_path / "agent.nk")
        task.cancel()
        await gw.close()

    try:
        asyncio.run(scenario())
    finally:
        proc.terminate()
        proc.wait(5)


# ------------------------------------------------------------------- the switch, through the app
def test_callout_switch_writes_the_block_and_keeps_agents_out_of_the_file(net_settings, clock, tmp_path):  # noqa: F811
    from dataclasses import replace

    from fastapi.testclient import TestClient

    from conftest import OWNER, ScriptedExecutor
    from onemind_core.app import create_app
    from onemind_core.natsconf import make_service_key
    from onemind_core.netconf import FabricSettings

    keys_dir = tmp_path / "service-keys"
    make_service_key(keys_dir, "gateway")
    fab = replace(net_settings.section(FabricSettings), nats_service_keys=keys_dir, nats_callout=True)
    settings = replace(net_settings, sections={**net_settings.sections, "fabric": fab})
    client = TestClient(create_app(settings, clock=clock, executor=ScriptedExecutor()))
    from onemind_core.natsconf import new_user_key

    enroll_agent(client, "agent:aaa")
    _, pub = new_user_key()
    apply_settings_change(client, client.put("/v1/agents/agent:aaa/nats-key", json={"nkey": pub}, headers=OWNER))
    text = fab.nats_accounts_file.read_text()
    custodian = settings.audit_path.parent / "custodian"
    acct = callout.load_keys(custodian).account
    assert "auth_callout" in text and f'issuer: "{acct.issuer}"' in text and acct.service in text
    assert pub not in text  # the agent is asked about at connect, never written into the file
    assert (custodian / callout.ISSUER_FILE).stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("with_callout", [True, False])
def test_agents_stopped_leaves_the_agents_account_out(with_callout):
    """#1199 review: with the kill switch on, nothing names AGENTS, so the reload closes every agent
    connection (static and callout users); the callout block and the pinned list stay."""
    co = _callout_account() if with_callout else None
    on = render_accounts([NodeAccount("aaa111", PUB_A)], [ServiceKey("gateway", PUB_GW)], 0, [HERMES], co)
    off = render_accounts([NodeAccount("aaa111", PUB_A)], [ServiceKey("gateway", PUB_GW)], 0, [HERMES], co,
                          agents_stopped=True)
    assert "AGENTS" in on and "AGENTS" not in off and AGENT_PUB not in off
    assert ("auth_callout" in off) is with_callout and PUB_A in off and PUB_GW in off


def test_kill_switch_rewrites_the_accounts_file(net_settings, clock, tmp_path, monkeypatch):  # noqa: F811
    from dataclasses import replace

    from fastapi.testclient import TestClient

    from conftest import OWNER, ScriptedExecutor
    from onemind_core.app import create_app
    from onemind_core.natsconf import make_service_key, new_user_key
    from onemind_core.netconf import FabricSettings

    keys_dir = tmp_path / "service-keys"
    make_service_key(keys_dir, "gateway")
    fab = replace(net_settings.section(FabricSettings), nats_service_keys=keys_dir, nats_callout=True)
    settings = replace(net_settings, sections={**net_settings.sections, "fabric": fab})
    client = TestClient(create_app(settings, clock=clock, executor=ScriptedExecutor()))
    enroll_agent(client, "agent:aaa")
    _, pub = new_user_key()
    apply_settings_change(client, client.put("/v1/agents/agent:aaa/nats-key", json={"nkey": pub}, headers=OWNER))
    assert "  AGENTS: {" in fab.nats_accounts_file.read_text()
    confirmed = []
    monkeypatch.setattr(client.app.state.engine.reader, "wait_for_agent_cutoff", lambda marker: confirmed.append(marker) or True)
    response = client.put("/v1/agents/kill-switch", json={"on": True}, headers=OWNER)
    assert response.status_code == 200
    assert confirmed == [response.json()["changed_at"]]
    text = fab.nats_accounts_file.read_text()
    assert "AGENTS" not in text and "auth_callout" in text
    apply_settings_change(client, client.put("/v1/agents/kill-switch", json={"on": False}, headers=OWNER))
    assert "  AGENTS: {" in fab.nats_accounts_file.read_text()


def test_kill_switch_keeps_local_stop_when_accounts_write_fails(net_settings, clock, monkeypatch):  # noqa: F811
    from fastapi.testclient import TestClient

    from conftest import AGENT, OWNER, ScriptedExecutor
    from onemind_core.actions import ApprovalInput
    from onemind_core.app import create_app
    from onemind_core.auth import Principal

    app = create_app(net_settings, clock=clock, executor=ScriptedExecutor())
    stop_path = "/v1/agents/kill-switch"
    fabric = app.state.gateway.actions.handlers["node.join"]
    fabric_confirmations = []

    def fail_write():
        raise OSError("accounts file unwritable")

    with TestClient(app) as client:
        monkeypatch.setattr(fabric, "write_accounts", fail_write)
        monkeypatch.setattr(app.state.agent_stop, "confirm_fabric", fabric_confirmations.append)
        response = client.put(stop_path, json={"on": True}, headers=OWNER)
        assert response.status_code == 503, response.text
        assert response.json()["reason"] == "agent_broker_cutoff_pending"
        assert client.get(stop_path, headers=OWNER).json()["on"] is True
        assert client.get("/v1/apps", headers=AGENT).json()["reason"] == "agents_stopped"

        resume = client.put(stop_path, json={"on": False}, headers=OWNER)
        assert resume.status_code == 202, resume.text
        action = resume.json()
        done = app.state.gateway.actions.approve(Principal("owner", "person", "owner"), action["id"],
                                                 action["plan_sha256"], extra=ApprovalInput(verification_level=2))
        assert done["state"] == "failed"
        assert "NATS accounts could not be restored" in done["result"]["message"]
    assert fabric_confirmations == [True, False]


@pytest.mark.skipif(NATS_SERVER is None, reason="nats-server is not installed")
def test_kill_switch_http_waits_for_connected_agent_cutoff(net_settings, clock, tmp_path, monkeypatch):  # noqa: F811
    from fastapi.testclient import TestClient

    from conftest import AGENT, OWNER, ScriptedExecutor
    from onemind_core.app import create_app
    from onemind_core.bus import SeedClient
    from onemind_core.engine import monitor
    from onemind_core.natsconf import new_user_key
    from onemind_core.netconf import FabricSettings

    app = create_app(net_settings, clock=clock, executor=ScriptedExecutor())
    client = TestClient(app)
    enroll_agent(client, "agent:aaa")
    stop_path = "/v1/agents/kill-switch"
    seed, pub = new_user_key()
    seed_file = tmp_path / "agent.nk"
    seed_file.write_text(seed)
    apply_settings_change(client, client.put("/v1/agents/agent:aaa/nats-key", json={"nkey": pub}, headers=OWNER))
    accounts = net_settings.section(FabricSettings).nats_accounts_file
    assert "  AGENTS: {" in accounts.read_text()
    port, monitor_port = _port(), _port()
    conf = accounts.with_name("hub.conf")
    conf.write_text(f'listen: "127.0.0.1:{port}"\nhttp: "127.0.0.1:{monitor_port}"\ninclude "{accounts.name}"\n')
    reader = monitor.MonitorReader(f"http://127.0.0.1:{monitor_port}")
    app.state.engine.reader = reader

    def stop():
        return client.put(stop_path, json={"on": True}, headers=OWNER)

    async def scenario():
        agent = SeedClient()
        disconnected = asyncio.Event()

        async def on_disconnect():
            disconnected.set()

        for _ in range(100):
            try:
                if reader._get("/varz")[0] == 200:
                    break
            except monitor.httpx.HTTPError:
                pass
            await asyncio.sleep(0.05)
        await agent.connect(f"nats://127.0.0.1:{port}", nkeys_seed=str(seed_file), connect_timeout=1,
                            allow_reconnect=False, max_reconnect_attempts=0, disconnected_cb=on_disconnect)
        try:
            with monkeypatch.context() as mp:
                mp.setattr(monitor, "AGENT_CUTOFF_TIMEOUT_S", 0.25)
                response = await asyncio.to_thread(stop)  # no OS reload yet
            assert response.status_code == 503, response.text
            assert response.json()["reason"] == "agent_broker_cutoff_pending"
            assert client.get(stop_path, headers=OWNER).json()["on"] is True
            assert client.get("/v1/apps", headers=AGENT).json()["reason"] == "agents_stopped"
            await agent.flush(timeout=1)  # the agent was still connected when HTTP returned 503
            before = accounts.read_text()
            assert "AGENTS" not in before

            retry = asyncio.create_task(asyncio.to_thread(stop))
            for _ in range(100):
                if accounts.read_text() != before:
                    break
                await asyncio.sleep(0.02)
            else:
                pytest.fail("retry must rewrite the file so the OS watcher attempts another reload")
            assert not retry.done()
            await agent.flush(timeout=1)
            proc.send_signal(signal.SIGHUP)  # the OS watcher would signal after this rewrite
            response = await asyncio.wait_for(retry, timeout=6)
            assert response.status_code == 200, response.text
            await asyncio.wait_for(disconnected.wait(), timeout=1)
            assert not agent.is_connected
        finally:
            await agent.close()

    proc = subprocess.Popen([NATS_SERVER, "-c", str(conf)], stdout=subprocess.DEVNULL)
    try:
        asyncio.run(scenario())
    finally:
        reader.close()
        proc.terminate()
        proc.wait(5)


def test_callout_with_no_registered_agent_still_wires_the_agents_account():
    """Found by the NA lab: with the callout on and no agent key yet, AGENTS imports the request service
    from ONEMIND, so ONEMIND must export it, or nats-server refuses the whole file and the hub is down."""
    text = render_accounts([], [ServiceKey("gateway", PUB_GW)], 0, [], _callout_account())
    hub = text.split("  ONEMIND: {", 1)[1].split("\n  }", 1)[0]
    assert '{service: "onemind.request.agent.>", accounts: ["AGENTS"]}' in hub
    assert '{service: {account: "AGENTS", subject: "agents.prompt.>"}}' in hub


@pytest.mark.skipif(NATS_SERVER is None, reason="nats-server is not installed")
def test_key_approval_reports_live_broker_reload(net_settings, clock, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from fastapi.testclient import TestClient

    from conftest import OWNER, ScriptedExecutor
    from onemind_core.app import create_app
    from onemind_core.engine import monitor
    from onemind_core.natsconf import AGENT_KEYS_METADATA, new_user_key
    from onemind_core.netconf import FabricSettings

    app = create_app(net_settings, clock=clock, executor=ScriptedExecutor())
    client = TestClient(app)
    enroll_agent(client, "agent:aaa")
    path = "/v1/agents/agent:aaa/nats-key"
    accounts = net_settings.section(FabricSettings).nats_accounts_file
    app.state.actions.handlers["node.join"].write_accounts()
    port, monitor_port = _port(), _port()
    conf = accounts.with_name("hub.conf")
    conf.write_text(f'listen: "127.0.0.1:{port}"\nhttp: "127.0.0.1:{monitor_port}"\ninclude "{accounts.name}"\n')
    reader = monitor.MonitorReader(f"http://127.0.0.1:{monitor_port}")
    app.state.engine.reader = reader
    proc = subprocess.Popen([NATS_SERVER, "-c", str(conf)], stdout=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                if reader._get("/varz")[0] == 200:
                    break
            except monitor.httpx.HTTPError:
                time.sleep(0.02)
        else:
            pytest.fail("NATS monitoring did not start")
        _, first_key = new_user_key()
        with monkeypatch.context() as mp:
            mp.setattr(monitor, "AGENT_CUTOFF_TIMEOUT_S", 0.25)
            pending = apply_settings_change(client, client.put(path, json={"nkey": first_key}, headers=OWNER))
        assert pending["result"]["steps"] == [{"committed": True, "broker_enforced": None}]
        assert AGENT_KEYS_METADATA not in (reader._get("/varz")[1].get("metadata") or {})

        _, second_key = new_user_key()
        queued = client.put(path, json={"nkey": second_key}, headers=OWNER)
        with ThreadPoolExecutor(max_workers=1) as pool:
            done = pool.submit(apply_settings_change, client, queued)
            for _ in range(100):
                if second_key in accounts.read_text():
                    break
                time.sleep(0.02)
            else:
                pytest.fail("approval did not write the new broker configuration")
            assert not done.done()
            proc.send_signal(signal.SIGHUP)
            result = done.result(timeout=6)
        assert result["result"]["steps"] == [{"committed": True, "broker_enforced": True}]
    finally:
        reader.close()
        proc.terminate()
        proc.wait(5)
