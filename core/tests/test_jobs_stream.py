# SPDX-License-Identifier: Apache-2.0
"""Durable signed jobs to machines (D-029 plan N2).

The hub keeps every job in ONEMIND_JOBS (the registry's work queue) and gives each joined node one
durable pull consumer of its own jobs. Its NATS account may call exactly two hub services: "next" and
"ack" of that consumer. internal/leaf/jobs_test.go runs both golden files in real nats-servers (a hub
and two node leaves) and proves that a machine offline at publish time gets its job on reconnect, runs
it once, and that node A can neither read node B's queue nor put a job into its own.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace

from onemind_core import jetstream, natsconf
from onemind_core.natsconf import NodeAccount, render_accounts

TESTDATA = Path(__file__).resolve().parents[2] / "internal" / "leaf" / "testdata"
GOLDEN_CONSUMER = TESTDATA / "node-job-consumer.golden.json"
PUB_A = "UBBUEVU3RVFLTSYWTDDLUC2TLY3YDZKKYWVTUOW4UFVUY6BICGH55O2Y"
PUB_B = "UC3WGTQV7ERIG2GOPKU7CXZ6B6DPY4S2DC4ZIUZ4XVZENDHGM3RRMZF3"
NODES = [NodeAccount("bbb222", PUB_B), NodeAccount("aaa111", PUB_A)]
GIB = 1 << 30


def _account(text: str, name: str) -> str:
    m = re.search(rf"^  {name}: {{\n(.*?)^  }}\n", text, re.M | re.S)
    assert m, name
    return m.group(1)


def test_consumer_golden_matches_the_go_lab():
    assert json.loads(GOLDEN_CONSUMER.read_text()) == jetstream.NodeJobConsumer("aaa111").to_json()


def test_consumer_is_one_node_explicit_ack_one_at_a_time():
    c = jetstream.NodeJobConsumer("aaa111")
    cfg = c.config()
    assert cfg.durable_name == "node-aaa111" == natsconf.job_consumer("aaa111")
    assert cfg.filter_subject == "onemind.node.aaa111.job.>"
    assert cfg.ack_policy.value == "explicit" and cfg.max_ack_pending == 1 and cfg.ack_wait == 60.0
    for bad in ("AAA", "a.b", "", "x" * 40):
        try:
            jetstream.NodeJobConsumer(bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad!r} accepted")


def test_each_node_may_only_pull_and_ack_its_own_consumer():
    text = render_accounts(NODES, jetstream_max_bytes=GIB)
    hub = _account(text, "ONEMIND")
    for n in ("aaa111", "bbb222"):
        nxt, ack = natsconf.job_services(n)
        assert nxt == f"$JS.API.CONSUMER.MSG.NEXT.ONEMIND_JOBS.node-{n}"
        assert ack == f"$JS.ACK.ONEMIND_JOBS.node-{n}.>"
        assert f'{{service: "{nxt}", accounts: ["NODE_{n}"]}}' in hub
        assert f'{{service: "{ack}", accounts: ["NODE_{n}"]}}' in hub
        node = _account(text, f"NODE_{n}")
        assert f'subject: "{nxt}"}}, to: "onemind.node.{n}.jobpull"}}' in node
        # nothing else of the JetStream API: no consumer create/delete/info, no stream API
        assert "$JS.API.CONSUMER.CREATE" not in node and "$JS.API.STREAM" not in node
        other = "bbb222" if n == "aaa111" else "aaa111"
        assert f"node-{other}" not in node
    assert natsconf.job_pull_subject("aaa111") == "onemind.node.aaa111.jobpull"


def test_no_job_services_without_jetstream():
    assert "ONEMIND_JOBS" not in render_accounts(NODES)


class FakeJS:
    def __init__(self):
        self.streams, self.consumers = {}, {}

    async def stream_info(self, name):
        from nats.js.errors import NotFoundError

        if name not in self.streams:
            raise NotFoundError()
        return SimpleNamespace(config=self.streams[name])

    async def add_stream(self, cfg):
        self.streams[cfg.name] = cfg

    async def update_stream(self, cfg):
        self.streams[cfg.name] = cfg

    async def create_key_value(self, cfg):
        from nats.js.api import StreamConfig

        self.streams[f"KV_{cfg.bucket}"] = StreamConfig(name=f"KV_{cfg.bucket}", max_bytes=cfg.max_bytes)

    async def add_consumer(self, stream, cfg):
        assert stream in self.streams, "the job consumer is made after the core streams"
        self.consumers[(stream, cfg.durable_name)] = cfg


def test_join_approval_makes_the_node_job_consumer_after_the_core_streams():
    js = FakeJS()
    nc = SimpleNamespace(jetstream=lambda: js, stats={"reconnects": 0})
    core = jetstream.JetStreamCore(8 * GIB)
    core.want_source("aaa111")

    async def scenario():
        assert await core.ensure_on(nc)
        await core.ensure_sources_on(nc, every=True)

    asyncio.run(scenario())
    cfg = js.consumers[("ONEMIND_JOBS", "node-aaa111")]
    assert cfg.filter_subject == "onemind.node.aaa111.job.>"
    assert core.jobs == {"aaa111": "ensured"}
    assert core.view()["sources"][0]["job_consumer"] == "ensured"
