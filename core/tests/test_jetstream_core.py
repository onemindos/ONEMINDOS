# SPDX-License-Identifier: Apache-2.0
"""The hub JetStream budget and the core streams and KV buckets the gateway creates (issue #601).

The real-server tests start a local `nats-server` with the hub's JetStream block (file store capped,
no memory store) and skip when the binary is not installed.
"""

from __future__ import annotations

import asyncio
import shutil
import socket
import subprocess
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from onemind_core import jetstream, subjects
from onemind_core.app import create_app
from onemind_core.netconf import FabricSettings

MIB, GIB = 1 << 20, 1 << 30


# ---------------------------------------------------------------- the cap is a share of /data
def test_cap_is_a_share_of_the_data_disk_clamped_and_never_zero():
    assert jetstream.cap_from_total(24 * GIB) == int(24 * GIB * 0.10)
    assert jetstream.cap_from_total(4000 * GIB) == jetstream.CAP_MAX_BYTES
    with pytest.raises(jetstream.JetStreamCapError, match="too small"):
        jetstream.cap_from_total(1 * GIB)            # 10 % is under the 256 MiB floor: refused
    for bad in (0, -1, True, None, "4G"):
        with pytest.raises(jetstream.JetStreamCapError, match="without a cap"):
            jetstream.require_cap(bad)
    with pytest.raises(jetstream.JetStreamCapError):
        jetstream.cap_from_total(24 * GIB, share=0.9)  # never most of the owner's disk


def test_cap_for_path_reads_the_disk_total(tmp_path):
    total = shutil.disk_usage(tmp_path).total
    if total * jetstream.DATA_SHARE < jetstream.CAP_MIN_BYTES:
        pytest.skip("this machine's disk is smaller than the JetStream floor")
    assert jetstream.cap_for_path(tmp_path) == min(int(total * jetstream.DATA_SHARE), jetstream.CAP_MAX_BYTES)
    with pytest.raises(jetstream.JetStreamCapError, match="cannot be read"):
        jetstream.cap_for_path(tmp_path / "missing")


# ---------------------------------------------------------------- the plan comes from the subject tree
def test_plan_covers_every_registry_stream_once():
    reg = subjects.load()
    named = {p.stream for p in reg.patterns if p.stream}
    p = jetstream.plan(64 * GIB, reg)
    core = {s.name for s in p.streams}
    kv = {b.stream for b in p.buckets}
    assert core == {"ONEMIND_AUDIT", "ONEMIND_EVENTS", "ONEMIND_INTEL", "ONEMIND_JOBS", "ONEMIND_JOBRESULTS",
                    "ONEMIND_REQUESTS"}
    assert {b.bucket for b in p.buckets} == {"asset-state", "layer-meta"}
    assert core | kv | set(jetstream.PER_NODE_STREAMS) == named
    assert not core & kv


def test_plan_keeps_registry_retention_on_a_large_disk():
    reg = subjects.load()
    p = jetstream.plan(64 * GIB, reg)
    by = {s.name: s for s in p.streams}
    audit = by["ONEMIND_AUDIT"]
    assert audit.subjects == ("onemind.audit",) and audit.deny_delete and audit.deny_purge
    assert audit.max_bytes == 2 * GIB and audit.max_age_s == 365 * 86400 and audit.discard == "old"
    assert by["ONEMIND_EVENTS"].subjects == ("onemind.alert.*.*", "onemind.event.>")
    assert by["ONEMIND_REQUESTS"].retention == "workqueue" and by["ONEMIND_REQUESTS"].discard == "new"
    assert by["ONEMIND_REQUESTS"].subjects == ("onemind.request.agent.>", "onemind.request.app.*.*")
    assert by["ONEMIND_JOBS"].subjects == ("onemind.node.*.job.>",)
    for s in p.streams:
        cfg = s.to_json()
        assert cfg["storage"] == "file" and cfg["max_bytes"] > 0 and cfg["replicas"] == 1
        for f in s.subjects:                       # each filter lands on registered subjects only
            assert reg.covers(f).ok, f
    assert {b.bucket: b.max_bytes for b in p.buckets} == {"asset-state": 256 * MIB, "layer-meta": 64 * MIB}
    assert p.reserved_bytes <= p.budget_bytes == 32 * GIB


def test_plan_scales_down_on_a_small_disk_and_stays_inside_the_core_share():
    p = jetstream.plan(jetstream.cap_from_total(24 * GIB))
    assert p.reserved_bytes <= p.budget_bytes <= p.cap_bytes * jetstream.CORE_SHARE
    small = jetstream.plan(jetstream.CAP_MIN_BYTES)
    assert small.reserved_bytes <= small.cap_bytes // 2
    assert all(s.max_bytes >= jetstream.MIN_STREAM_BYTES for s in small.streams)
    by = {s.name: s.max_bytes for s in small.streams}
    assert by["ONEMIND_AUDIT"] > by["ONEMIND_REQUESTS"]  # scaled evenly, the order of sizes is kept


def test_plan_refuses_without_a_cap_or_with_a_useless_one():
    for bad in (0, -5):
        with pytest.raises(jetstream.JetStreamCapError, match="without a cap"):
            jetstream.plan(bad)
    with pytest.raises(jetstream.JetStreamCapError):
        jetstream.plan(4 * MIB)


def test_filters_and_cover():
    assert jetstream._covers("onemind.request.agent.>", "onemind.request.agent.*.x")
    assert not jetstream._covers("onemind.request.app.*.*", "onemind.request.agent.>")
    assert jetstream._minimal(["a.*", "a.b", "a.>", "c"]) == ("a.>", "c")


# ---------------------------------------------------------------- the gateway side, with a fake JetStream
class FakeJS:
    def __init__(self):
        self.streams: dict[str, object] = {}
        self.calls: list[str] = []
        self.fail = False

    async def stream_info(self, name):
        from nats.js.errors import NotFoundError

        if self.fail:
            raise RuntimeError("nats: timeout")
        if name not in self.streams:
            raise NotFoundError()
        return SimpleNamespace(config=self.streams[name])

    async def add_stream(self, cfg):
        self.calls.append(f"add {cfg.name}")
        self.streams[cfg.name] = cfg

    async def update_stream(self, cfg):
        self.calls.append(f"update {cfg.name}")
        self.streams[cfg.name] = cfg

    async def create_key_value(self, cfg):
        self.calls.append(f"kv {cfg.bucket}")
        from nats.js.api import StreamConfig

        self.streams[f"KV_{cfg.bucket}"] = StreamConfig(name=f"KV_{cfg.bucket}", max_bytes=cfg.max_bytes)


def test_ensure_creates_then_updates_and_never_asks_for_memory():
    from nats.js.api import StorageType

    js, p = FakeJS(), jetstream.plan(8 * GIB)
    first = asyncio.run(jetstream.ensure(js, p))
    assert set(first.values()) == {"created"} and len(first) == len(p.streams) + len(p.buckets)
    assert all(js.streams[s.name].storage == StorageType.FILE for s in p.streams)
    assert all(js.streams[s.name].max_bytes == s.max_bytes for s in p.streams)
    again = asyncio.run(jetstream.ensure(js, p))
    assert {again[s.name] for s in p.streams} == {"updated"}
    assert {again[b.stream_name] for b in p.buckets} == {"unchanged"}
    smaller = jetstream.plan(1 * GIB)
    third = asyncio.run(jetstream.ensure(js, smaller))
    assert third["KV_asset-state"] == "updated"
    assert js.streams["KV_asset-state"].max_bytes == smaller.buckets[0].max_bytes


def test_core_state_off_refused_and_clamped(tmp_path):
    off = jetstream.JetStreamCore(0)
    assert off.state == "off" and off.plan is None and "no JetStream cap" in off.reason
    refused = jetstream.JetStreamCore(2 * MIB)
    assert refused.state == "refused" and refused.plan is None
    total = shutil.disk_usage(tmp_path).total
    big = jetstream.JetStreamCore(1 << 50, tmp_path)   # a cap larger than the share of the disk is clamped
    if total * jetstream.DATA_SHARE >= jetstream.CAP_MIN_BYTES:
        assert big.plan.cap_bytes == jetstream.cap_for_path(tmp_path)
    view = big.view()
    assert view["state"] == "pending" and view["plan"]["cap_bytes"] == big.plan.cap_bytes


class FakeBus:
    def __init__(self, nc=None):
        self.nc = nc

    @property
    def connected(self):
        return self.nc is not None


def test_run_ensures_on_connect_retries_on_error_and_again_after_a_reconnect():
    js = FakeJS()
    nc = SimpleNamespace(jetstream=lambda: js, stats={"reconnects": 0})
    bus = FakeBus()
    core = jetstream.JetStreamCore(8 * GIB)

    async def scenario():
        task = asyncio.create_task(core.run(bus, interval_s=0.01))
        await asyncio.sleep(0.05)
        assert core.state == "pending" and not js.calls          # NATS down: nothing, no crash
        js.fail, bus.nc = True, nc
        await asyncio.sleep(0.05)
        assert core.state == "error" and "timeout" in core.reason  # NATS refused: kept, retried
        js.fail = False
        await asyncio.sleep(0.05)
        assert core.state == "ready" and core.ensured_at is not None
        n = len(js.calls)
        await asyncio.sleep(0.05)
        assert len(js.calls) == n                                  # no churn while nothing changed
        bus.nc = None
        await asyncio.sleep(0.05)
        assert core.state == "pending"
        nc.stats["reconnects"] = 1
        bus.nc = nc
        await asyncio.sleep(0.05)
        assert core.state == "ready" and len(js.calls) > n         # ensured again after the reconnect
        task.cancel()

    asyncio.run(scenario())


def test_gateway_keeps_the_plan_and_serves_without_nats(settings):
    fab = FabricSettings(jetstream_max_bytes=2 * GIB)
    s = replace(settings, nats_url="nats://127.0.0.1:1", sections={**settings.sections, "fabric": fab})
    app = create_app(s)
    with TestClient(app) as c:
        assert c.get("/healthz").status_code == 200
        core = app.state.jetstream
        assert core.plan is not None and core.plan.cap_bytes <= 2 * GIB
        assert core.state in ("pending", "error")
    off = create_app(settings)
    assert off.state.jetstream.state == "off"


# ---------------------------------------------------------------- a real nats-server with the hub's block
NATS_SERVER = shutil.which("nats-server")
needs_server = pytest.mark.skipif(NATS_SERVER is None, reason="nats-server is not installed")


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, tmp_path, max_file: int):
        self.port = _port()
        self.conf = tmp_path / "nats.conf"
        self.conf.write_text(
            f'listen: "127.0.0.1:{self.port}"\n'
            f'jetstream {{\n  store_dir: "{tmp_path / "js"}"\n  max_file_store: {max_file}\n  max_memory_store: 0\n}}\n')
        self.proc = None

    @property
    def url(self):
        return f"nats://127.0.0.1:{self.port}"

    def start(self):
        self.proc = subprocess.Popen([NATS_SERVER, "-c", str(self.conf)], stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        end = time.time() + 10
        while time.time() < end:
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", self.port)) == 0:
                    return
            time.sleep(0.05)
        raise RuntimeError("nats-server did not start")

    def stop(self):
        if self.proc:
            self.proc.terminate()
            self.proc.wait(10)
            self.proc = None


@pytest.fixture
def server(tmp_path):
    srv = Server(tmp_path, jetstream.CAP_MIN_BYTES)
    srv.start()
    yield srv
    srv.stop()


@needs_server
def test_real_server_full_stream_discards_old_and_audit_is_untouched(server):
    import nats
    from nats.js.api import StorageType, StreamConfig

    p = jetstream.plan(jetstream.CAP_MIN_BYTES)
    events = next(s for s in p.streams if s.name == "ONEMIND_EVENTS")

    async def scenario():
        nc = await nats.connect(server.url)
        js = nc.jetstream()
        assert set((await jetstream.ensure(js, p)).values()) == {"created"}
        await js.publish("onemind.audit", b'{"seq": 1}')
        audit_before = (await js.stream_info("ONEMIND_AUDIT")).state
        chunk = b"x" * (64 << 10)
        for i in range(events.max_bytes // len(chunk) + 40):     # well past the events cap
            await js.publish(f"onemind.event.test.fill{i % 5}", chunk)
        ev = (await js.stream_info("ONEMIND_EVENTS")).state
        assert ev.bytes <= events.max_bytes                       # the cap holds
        assert ev.first_seq > 1                                   # the oldest went (discard old)
        audit_after = (await js.stream_info("ONEMIND_AUDIT")).state
        assert audit_before.messages == 1
        assert (audit_after.messages, audit_after.bytes) == (audit_before.messages, audit_before.bytes)
        with pytest.raises(Exception):                            # max_memory_store 0: no memory stream
            await js.add_stream(StreamConfig(name="MEM", subjects=["mem.>"], storage=StorageType.MEMORY))
        with pytest.raises(Exception):                            # deny_delete on the audit stream
            await js.delete_msg("ONEMIND_AUDIT", 1)
        assert set((await jetstream.ensure(js, p)).values()) <= {"updated", "unchanged"}  # idempotent
        await nc.drain()

    asyncio.run(scenario())


@needs_server
def test_real_server_killed_and_back_the_core_is_ensured_again(server, settings):
    from onemind_core.bus import NatsBus
    from onemind_core.nodes import NodeRegistry

    core = jetstream.JetStreamCore(jetstream.CAP_MIN_BYTES)

    async def wait_for(pred, timeout=20.0):
        end = time.time() + timeout
        while time.time() < end:
            if pred():
                return True
            await asyncio.sleep(0.1)
        return False

    async def scenario():
        bus = NatsBus(server.url, NodeRegistry(lambda: None))
        await bus.start()
        task = asyncio.create_task(core.run(bus, interval_s=0.1))
        assert await wait_for(lambda: core.state == "ready")
        first = core.ensured_at
        await asyncio.to_thread(server.stop)
        assert await wait_for(lambda: core.state == "pending")    # down: the gateway notices, keeps going
        await asyncio.to_thread(server.start)
        assert await wait_for(lambda: core.state == "ready" and core.ensured_at != first)
        task.cancel()
        await bus.stop()

    asyncio.run(scenario())

