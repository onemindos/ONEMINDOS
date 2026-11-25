# SPDX-License-Identifier: Apache-2.0
"""Hub sourcing across the per-node NATS accounts (#747).

internal/leaf/hubsource_test.go runs the two golden files here in real nats-servers (a hub and two
node leaves) and proves the acceptance test: a node cut while it writes 600 events delivers exactly
those 600 in order, and node A reaches neither node B's stream nor its JetStream API. These tests
pin what the gateway writes and when: the account text, the source stream, and that approving a
join (POST /v1/actions/{id}/approve) is what makes the node's source stream.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from onemind_core import jetstream, subjects
from onemind_core.app import create_app
from onemind_core.natsconf import NodeAccount, render_accounts, source_deliver_prefix, source_services
from onemind_core.netconf import FabricSettings
from conftest import OWNER, ScriptedExecutor
from test_jetstream_core import FakeBus, FakeJS
from test_net import Node, hs, kube, net_settings, ticket  # noqa: F401 (fixtures)

TESTDATA = Path(__file__).resolve().parents[2] / "internal" / "leaf" / "testdata"
GOLDEN_JS = TESTDATA / "hub-accounts-jetstream.golden.conf"
GOLDEN_SOURCE = TESTDATA / "hub-source-stream.golden.json"
PUB_A = "UBBUEVU3RVFLTSYWTDDLUC2TLY3YDZKKYWVTUOW4UFVUY6BICGH55O2Y"
PUB_B = "UC3WGTQV7ERIG2GOPKU7CXZ6B6DPY4S2DC4ZIUZ4XVZENDHGM3RRMZF3"
NODES = [NodeAccount("bbb222", PUB_B), NodeAccount("aaa111", PUB_A)]
GIB = 1 << 30


def _account(text: str, name: str) -> str:
    """The body of one account in the rendered file (accounts are two-space indented blocks)."""
    m = re.search(rf"^  {name}: {{\n(.*?)^  }}\n", text, re.M | re.S)
    assert m, name
    return m.group(1)


def _section(body: str, key: str) -> list[str]:
    m = re.search(rf"^    {key}: \[\n(.*?)^    \]\n", body, re.M | re.S)
    return [ln.strip() for ln in m.group(1).splitlines()] if m else []


# ---------------------------------------------------------------- the account text
def test_jetstream_accounts_golden_matches_the_go_sourcing_lab():
    """hubsource_test.go loads this exact file into the hub of its two-leaf lab."""
    assert render_accounts(NODES, jetstream_max_bytes=GIB) == GOLDEN_JS.read_text()


def test_each_node_exports_its_outbox_api_flow_control_and_delivery_to_the_hub_only():
    text = render_accounts(NODES, jetstream_max_bytes=GIB)
    for node, other in (("aaa111", "bbb222"), ("bbb222", "aaa111")):
        body = _account(text, f"NODE_{node}")
        exports = _section(body, "exports")
        for subj in source_services(node):
            assert f'{{service: "{subj}", accounts: ["ONEMIND"]}}' in exports
        assert f'{{stream: "{source_deliver_prefix(node)}.>", accounts: ["ONEMIND"]}}' in exports
        assert all('accounts: ["ONEMIND"]' in e for e in exports)          # never to another node
        assert not any(other in e for e in exports)
        # what the node may import stays its own jobs: no JetStream API, no other node's anything
        assert _section(body, "imports") == [f'{{stream: {{account: "ONEMIND", subject: "onemind.node.{node}.job.>"}}}}']
    hub = _account(text, "ONEMIND")
    imports = _section(hub, "imports")
    for node in ("aaa111", "bbb222"):
        for subj in source_services(node):
            assert f'{{service: {{account: "NODE_{node}", subject: "{subj}"}}}}' in imports
        assert f'{{stream: {{account: "NODE_{node}", subject: "{source_deliver_prefix(node)}.>"}}}}' in imports
    # the hub offers the nodes no service at all (no JetStream API, no request path into ONEMIND)
    assert not any("service" in e for e in _section(hub, "exports"))


def test_sourcing_subjects_are_scoped_to_the_outbox_and_the_node():
    api = source_services("aaa111")
    assert api[:3] == ("$JS.node-aaa111.API.CONSUMER.CREATE.OUTBOX", "$JS.node-aaa111.API.CONSUMER.CREATE.OUTBOX.>",
                       "$JS.node-aaa111.API.CONSUMER.DELETE.OUTBOX.>")
    assert api[3] == "$JS.FC.OUTBOX.>"
    assert not any(s.endswith("API.>") or ".STREAM." in s for s in api)  # no stream reads, no whole API
    assert source_deliver_prefix("aaa111") == "onemind.node.aaa111.outbox"
    assert render_accounts([]) == render_accounts([], jetstream_max_bytes=0)  # no node, no sourcing lines
    assert "OUTBOX" not in render_accounts([])


# ---------------------------------------------------------------- the stream the gateway creates
def test_hub_source_matches_the_go_golden_and_hub_source_stream():
    src = jetstream.HubSource("aaa111")
    assert json.loads(GOLDEN_SOURCE.read_text()) == src.to_json()
    d = src.config().as_dict()
    assert d["name"] == "NODE_node_aaa111_OUTBOX" == src.name
    assert d["sources"] == [{"name": "OUTBOX", "external": {"api": "$JS.node-aaa111.API",
                                                             "deliver": "onemind.node.aaa111.outbox"}}]
    assert d["retention"].value == "limits" and d["storage"].value == "file"
    assert d["duplicate_window"] == 24 * 3600 * 10**9
    assert d["max_bytes"] == 256 << 20 and d["max_age"] == 7 * 24 * 3600 * 10**9 and d["discard"].value == "old"
    assert not d.get("subjects")  # a source stream takes no subjects of its own


def test_each_node_copy_keeps_the_registry_retention_sized_to_the_cap():
    """A node's copy is never unbounded (#747): the registry's age and size, less on a small hub disk,
    so NODE_COPY_SLOTS nodes fit in NODE_SHARE next to the core streams and one node fills only its own."""
    reg = subjects.load()
    kept = {p.retention["policy"]: p.retention for p in reg.patterns if p.stream == "ONEMIND_NODE_OUTBOX"}
    assert set(kept) == {"limits"}
    assert (kept["limits"]["max_bytes"], kept["limits"]["max_age_s"]) == (
        jetstream.HUB_COPY_MAX_BYTES, jetstream.HUB_COPY_MAX_AGE_S)
    assert jetstream.plan(64 * GIB).node_copy_bytes == 256 << 20
    small = jetstream.plan(jetstream.CAP_MIN_BYTES)
    assert small.node_copy_bytes == 8 << 20 and small.node_copy_age_s == 7 * 24 * 3600
    for cap in (jetstream.CAP_MIN_BYTES, GIB, 8 * GIB, 64 * GIB):
        p = jetstream.plan(cap)
        fleet = jetstream.NODE_COPY_SLOTS * p.node_copy_bytes
        assert p.reserved_bytes + fleet <= cap * (jetstream.CORE_SHARE + jetstream.NODE_SHARE)
        assert p.to_json()["node_copy"] == {"max_bytes": p.node_copy_bytes, "max_age_s": 604800, "discard": "old"}
    d = small.hub_source("aaa111").config().as_dict()
    assert d["max_bytes"] == 8 << 20 and d["max_age"] == 604800 * 10**9 and d["discard"].value == "old"
    for bad in ({"max_bytes": 0}, {"max_bytes": 1024}, {"max_age_s": 0}, {"max_bytes": True}):
        with pytest.raises(ValueError):
            jetstream.HubSource("aaa111", **bad)


@pytest.mark.parametrize("bad", ["", "Bad", "a.b", "a" * 33, None, "hub-1"])
def test_hub_source_refuses_bad_node_ids(bad):
    with pytest.raises(ValueError):
        jetstream.HubSource(bad)
    with pytest.raises(ValueError):
        jetstream.JetStreamCore(8 * GIB).want_source(bad)


def test_core_creates_wanted_sources_retries_errors_and_reensures_after_a_reconnect():
    js = FakeJS()
    nc = SimpleNamespace(jetstream=lambda: js, stats={"reconnects": 0})
    bus = FakeBus()
    core = jetstream.JetStreamCore(8 * GIB)
    core.want_source("aaa111")
    assert core.view()["sources"] == [{"node_id": "aaa111", "stream": "NODE_node_aaa111_OUTBOX", "state": "pending"}]

    async def scenario():
        task = asyncio.create_task(core.run(bus, interval_s=0.01))
        await asyncio.sleep(0.05)
        assert core.sources == {"aaa111": "pending"}                 # NATS down: kept, nothing made
        bus.nc = nc
        await asyncio.sleep(0.05)
        assert core.sources == {"aaa111": "created"} and "add NODE_node_aaa111_OUTBOX" in js.calls
        cfg = js.streams["NODE_node_aaa111_OUTBOX"]
        assert cfg.sources[0].external.deliver == "onemind.node.aaa111.outbox"
        assert (cfg.max_bytes, cfg.max_age) == (core.plan.node_copy_bytes, 604800.0)   # bounded copy
        n = len(js.calls)
        await asyncio.sleep(0.05)
        assert len(js.calls) == n                                    # no churn
        js.fail = True                                               # approval while NATS refuses
        core.want_source("bbb222")
        await asyncio.sleep(0.05)
        assert core.sources["bbb222"].startswith("error: RuntimeError")
        assert core.sources["aaa111"] == "created"                   # one node's error is its own
        js.fail = False
        await asyncio.sleep(0.05)
        assert core.sources["bbb222"] == "created"                   # retried
        nc.stats["reconnects"] = 1                                   # new connection: ensure every one
        await asyncio.sleep(0.05)
        assert core.sources == {"aaa111": "updated", "bbb222": "updated"}
        core.want_source("aaa111")                                   # approving again does not redo it
        assert core.sources["aaa111"] == "updated"
        task.cancel()

    asyncio.run(scenario())


def test_core_without_a_cap_wants_no_source():
    off = jetstream.JetStreamCore(0)
    off.want_source("aaa111")
    assert off.sources == {} and off.view()["sources"] == []


# ---------------------------------------------------------------- join approval makes it (the route)
@pytest.fixture
def js_settings(net_settings):  # noqa: F811
    fab = replace(net_settings.section(FabricSettings), jetstream_max_bytes=2 * GIB)
    return replace(net_settings, sections={**net_settings.sections, "fabric": fab})


def _join(client, node: Node) -> dict:
    code = ticket(client)["one_time"]["join_code"]
    r = client.post("/v1/fabric/join-requests", json=node.body(code))
    assert r.status_code == 202, r.text
    return r.json()


def test_approving_a_join_wants_the_node_source_stream(js_settings, clock):
    app = create_app(js_settings, clock=clock, executor=ScriptedExecutor())
    c = TestClient(app)
    core = app.state.jetstream
    node = Node(node_id="aaa111")
    jr = _join(c, node)
    assert core.sources == {}                                        # requested is not approved
    a = c.post(f"/v1/actions/{jr['action']['id']}/approve", headers=OWNER)
    assert a.status_code == 200 and a.json()["state"] == "dispatched", a.text
    assert core.sources == {"aaa111": "pending"}
    accounts = js_settings.section(FabricSettings).nats_accounts_file.read_text()
    assert '{stream: "onemind.node.aaa111.outbox.>", accounts: ["ONEMIND"]}' in accounts


def test_a_failing_hook_never_undoes_the_approval(js_settings, clock):
    app = create_app(js_settings, clock=clock, executor=ScriptedExecutor())
    c = TestClient(app)
    fabric = app.state.gateway.actions.handlers["node.join"]

    def broken(node_id):
        raise RuntimeError("boom")

    fabric.approved_hooks.insert(0, broken)
    jr = _join(c, Node(node_id="bbb222"))
    a = c.post(f"/v1/actions/{jr['action']['id']}/approve", headers=OWNER)
    assert a.status_code == 200 and a.json()["state"] == "dispatched", a.text
    assert app.state.jetstream.sources == {"bbb222": "pending"}      # the next hook still ran
    assert fabric.node_ids() == ["bbb222"]


def test_nodes_approved_before_a_restart_get_their_source_at_startup(js_settings, clock):
    first = create_app(js_settings, clock=clock, executor=ScriptedExecutor())
    c = TestClient(first)
    jr = _join(c, Node(node_id="ccc333"))
    assert c.post(f"/v1/actions/{jr['action']['id']}/approve", headers=OWNER).status_code == 200
    again = create_app(replace(js_settings, nats_url=""), clock=clock, executor=ScriptedExecutor())
    assert again.state.jetstream.sources == {}
    with TestClient(again):
        assert again.state.jetstream.sources == {"ccc333": "pending"}


# ---------------------------------------------------------------- the real nats-server accepts it
NATS_SERVER = shutil.which("nats-server")


@pytest.mark.skipif(NATS_SERVER is None, reason="nats-server is not installed")
def test_real_server_loads_the_accounts_and_takes_the_source_stream(tmp_path):
    import nats

    from test_jetstream_core import _port

    port = _port()
    (tmp_path / "accounts.conf").write_text(render_accounts(NODES, jetstream_max_bytes=GIB))
    conf = tmp_path / "hub.conf"
    conf.write_text(f'listen: "127.0.0.1:{port}"\njetstream {{\n  store_dir: "{tmp_path / "js"}"\n'
                    f'  max_file_store: {GIB}\n  max_memory_store: 0\n}}\ninclude "accounts.conf"\n')
    assert subprocess.run([NATS_SERVER, "-t", "-c", str(conf)], capture_output=True).returncode == 0
    proc = subprocess.Popen([NATS_SERVER, "-c", str(conf)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    async def scenario():
        for _ in range(100):
            try:
                nc = await nats.connect(f"nats://127.0.0.1:{port}", connect_timeout=1, max_reconnect_attempts=0)
                break
            except Exception:
                await asyncio.sleep(0.1)
        js = nc.jetstream()
        src = jetstream.HubSource("aaa111")
        assert await jetstream.ensure_hub_source(js, src) == "created"   # no leaf yet: the source waits
        assert await jetstream.ensure_hub_source(js, src) == "updated"   # idempotent
        info = await js.stream_info(src.name)
        assert info.config.sources[0].external.api == "$JS.node-aaa111.API"
        # the server took the bounded copy: its size is reserved, a full copy drops its own oldest
        assert info.config.max_bytes == 256 << 20 and info.config.discard == "old"
        assert info.config.max_age == 604800
        await nc.close()

    try:
        asyncio.run(scenario())
    finally:
        proc.terminate()
        proc.wait(10)
