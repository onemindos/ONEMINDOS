# SPDX-License-Identifier: Apache-2.0
"""GET /v1/events fan-out (issue #606): one reader per source, a snapshot of the asset state on
connect, latest-wins values, kind and bbox filters, slow clients reset, and no asset without a grant.

The real-server test starts a local `nats-server` with JetStream and skips when it is not installed.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from conftest import ADULT, AGENT, GUEST, OWNER
from onemind_core import fanout, jetstream
from onemind_core.audit import AuditLog
from onemind_core.auth import Principal
from onemind_core.eventstream import EventStream, asset_event, may_read_assets
from onemind_core.fanout import AssetState, AssetValue, AssetView, Subscriber, asset_key, parse_bbox, parse_kinds

REPO = Path(__file__).resolve().parents[2]
OWNER_P = Principal("owner", "person", "owner")
WHO = {"id": "owner", "kind": "person", "role": "owner"}


def now() -> datetime:
    return datetime.now(UTC)


def dp(subject: str, value=1.0, unit="Cel", position=None, quality="live") -> dict:
    out = {"schema": "onemind.datapoint/v1", "nats_subject": subject, "time": "2026-11-22T10:00:00Z",
           "value": value, "quality": quality, "source": {"kind": "gateway", "id": "core"}}
    if unit:
        out["unit"] = unit
    if position:
        out["position"] = {"lat": position[0], "lon": position[1]}
    return out


def put(assets: AssetState, subject: str, rev: int, **kw):
    return assets.ingest(asset_key(subject), rev, json.dumps(dp(subject, **kw)).encode())


def parse(chunk: bytes) -> dict | None:
    line = next((ln for ln in chunk.decode().splitlines() if ln.startswith("data: ")), None)
    return json.loads(line[6:]) if line else None


def make(tmp_path, assets: AssetState | None = None):
    log = AuditLog(tmp_path / "audit.jsonl", now)
    log.append("gateway.started")
    es = EventStream(log.path, lambda: [], lambda _id: set(), now, assets=assets)
    log.listeners.append(es.pump.kick)
    return log, es


async def never() -> bool:
    return False


# ---------------------------------------------------------------- facts: one reader, no idle cost, p95
def test_fifty_streams_share_one_reader_idle_costs_nothing_and_p95_under_250ms(tmp_path):
    log, es = make(tmp_path)
    got: list[list[tuple[int, float]]] = [[] for _ in range(50)]
    checks = [0] * 50

    async def scenario():
        async def consume(i):
            async def gone():
                checks[i] += 1
                return False
            async for chunk in es.stream(OWNER_P, "audit.*", None, gone):
                ev = parse(chunk)
                if ev and ev["type"] == "audit.appended":
                    got[i].append((int(ev["id"]), time.perf_counter()))

        tasks = [asyncio.create_task(consume(i)) for i in range(50)]
        while len(es.pump.subscribers()) < 50:
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.1)
        reads, before = es.pump.reads, sum(checks)
        await asyncio.sleep(1.0)                                 # idle: nothing written
        assert es.pump.reads == reads                            # no stream read the file
        assert sum(checks) - before <= 50                        # each woke at most once (2 s idle sleep)
        sent: dict[int, float] = {}
        for _ in range(20):
            t0 = time.perf_counter()
            rec = await asyncio.to_thread(log.append, "test.tick", WHO)
            sent[rec["seq"]] = t0
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.3)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        return sent, reads

    sent, reads = asyncio.run(scenario())
    lat = sorted(t - sent[seq] for g in got for seq, t in g)
    assert all([s for s, _ in g] == sorted(sent) for g in got)   # every stream, every fact, in order
    assert lat[int(len(lat) * 0.95)] < 0.25
    assert es.pump.reads - reads <= 20                          # one read per append, not one per stream


def test_live_facts_survive_audit_rotation_with_no_gap(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl", now, max_bytes=2048)   # rotates every few records
    es = EventStream(log.path, lambda: [], lambda _id: set(), now)
    log.listeners.append(es.pump.kick)

    async def scenario():
        seqs: list[int] = []

        async def consume():
            async for chunk in es.stream(OWNER_P, "audit.*", None, never, keepalive_s=60):
                if (ev := parse(chunk)) is not None:
                    seqs.append(int(ev["id"]))

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.1)                                   # the stream is live, past its head
        start = (await asyncio.to_thread(log.append, "test.tick", WHO))["seq"]
        for _ in range(30):
            await asyncio.to_thread(log.append, "test.tick", WHO)
        for _ in range(100):
            if len(seqs) >= 31:
                break
            await asyncio.sleep(0.02)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return start, seqs

    start, seqs = asyncio.run(scenario())
    assert len(list(tmp_path.glob("audit.jsonl.*.gz"))) >= 3
    assert seqs == list(range(start, start + 31))


# ---------------------------------------------------------------- assets: snapshot, latest wins, opt-in
def test_snapshot_on_connect_then_latest_wins_and_only_when_asked(tmp_path):
    assets = AssetState()
    assets.state = "ready"
    put(assets, "onemind.asset.camera.cam-1.status", 1, value="online", unit=None, position=(52.5, 13.4))
    put(assets, "onemind.asset.sensor.s-1.temp", 2, value=21.5)
    _log, es = make(tmp_path, assets)
    allow = lambda ev: True  # noqa: E731

    async def scenario():
        gen = es.stream(OWNER_P, "asset.*", None, never, resource_allowed=allow, keepalive_s=60)
        first = [parse(await gen.__anext__()) for _ in range(4)][1:]
        assert [e["type"] for e in first] == ["asset.value", "asset.value", "stream.snapshot"]
        assert all(e["data"]["snapshot"] for e in first[:2]) and first[2]["data"] == {"count": 2, "state": "ready"}
        assert first[0]["subject"] == {"asset_id": "cam-1", "asset_class": "camera", "field": "status"}
        assert first[1]["data"]["datapoint"]["value"] == 21.5
        for rev in range(3, 103):                                # 100 values while the client is busy
            put(assets, "onemind.asset.sensor.s-1.temp", rev, value=float(rev))
        live = parse(await asyncio.wait_for(gen.__anext__(), 2))
        assert live["type"] == "asset.value" and not live["data"]["snapshot"]
        assert live["data"]["revision"] == 102 and live["data"]["datapoint"]["value"] == 102.0
        assets.remove("sensor.s-1.temp", 103)
        gone = parse(await asyncio.wait_for(gen.__anext__(), 2))
        assert gone["type"] == "asset.removed" and gone["data"] == {"revision": 103}
        await gen.aclose()
        # Without types=asset.* nothing about assets is sent: no snapshot, no marker.
        plain = es.stream(OWNER_P, None, None, never, resource_allowed=allow, poll_s=0.05, keepalive_s=0.1)
        await plain.__anext__()
        put(assets, "onemind.asset.sensor.s-1.temp", 200, value=1.0)
        assert await asyncio.wait_for(plain.__anext__(), 2) == b": keepalive\n\n"
        await plain.aclose()
        # Without a route-level resource check, asset events fail closed.
        closed = es.stream(OWNER_P, "asset.*", None, never, keepalive_s=60)
        chunks = [parse(await closed.__anext__()) for _ in range(2)]
        assert chunks[1]["type"] == "stream.snapshot" and chunks[1]["data"]["count"] == 0
        await closed.aclose()

    asyncio.run(scenario())


def test_kv_messages_puts_deletes_and_refusals():
    assets = AssetState()
    seen = []
    assets.listeners.append(lambda op, v: seen.append((op, v.key, v.revision)))

    def msg(key, rev, body=None, op=None):
        return SimpleNamespace(subject=f"$KV.asset-state.{key}", data=json.dumps(body).encode() if body else b"",
                               headers={"KV-Operation": op} if op else None,
                               metadata=SimpleNamespace(sequence=SimpleNamespace(stream=rev)))

    async def scenario():
        await assets.on_kv_message(msg("sensor.s-1.temp", 5, dp("onemind.asset.sensor.s-1.temp")))
        await assets.on_kv_message(msg("sensor.s-1.temp", 4, dp("onemind.asset.sensor.s-1.temp")))  # older
        await assets.on_kv_message(msg("sensor.s-2.temp", 6, dp("onemind.asset.sensor.s-2.temp", position=(0, 0))))
        await assets.on_kv_message(msg("sensor.s-3.temp", 7, dp("onemind.asset.sensor.s-9.temp")))  # wrong subject
        await assets.on_kv_message(msg("robot.r-1.dance", 8, dp("onemind.asset.robot.r-1.dance")))  # not a channel
        await assets.on_kv_message(msg("sensor.s-1.temp", 9, op="DEL"))

    asyncio.run(scenario())
    assert seen == [("value", "sensor.s-1.temp", 5), ("removed", "sensor.s-1.temp", 9)]
    assert assets.rejected == 3 and assets.snapshot() == []
    with pytest.raises(ValueError):
        asset_key("onemind.audit")


# ---------------------------------------------------------------- ?kind= and ?bbox=
def test_kind_and_bbox_filters_and_leaving_the_box():
    assets = AssetState()
    put(assets, "onemind.asset.camera.cam-1.status", 1, value="on", unit=None, position=(52.5, 13.4))
    put(assets, "onemind.asset.sensor.s-1.temp", 2, position=(48.1, 11.6))
    put(assets, "onemind.asset.sensor.s-2.temp", 3)                       # no position known
    view = AssetView(parse_kinds("sensor"), parse_bbox("11,48,12,49"), assets.position)
    assert [v.asset_id for v in assets.snapshot() if view.passes(v)] == ["s-1"]
    moved = put(assets, "onemind.asset.sensor.s-1.temp", 4, position=(40.0, -3.7))
    assert view.passes(moved)                                             # once more as it leaves
    assert not view.passes(put(assets, "onemind.asset.sensor.s-1.temp", 5, position=(40.0, -3.7)))
    pacific = AssetView(None, parse_bbox("170,-20,-170,0"), assets.position)  # crosses 180
    fiji = put(assets, "onemind.asset.sensor.fj.temp", 6, position=(-18.1, 178.4))
    assert pacific.passes(fiji) and not pacific.passes(moved)
    for bad in ("1,2,3", "a,b,c,d", "0,0,200,10", "0,10,5,5", "nan,0,1,1"):
        with pytest.raises(ValueError):
            parse_bbox(bad)
    for bad in ("Camera", "cam era", ",".join(f"k{i}" for i in range(40))):
        with pytest.raises(ValueError):
            parse_kinds(bad)
    assert parse_kinds(None) is None and parse_bbox("") is None


def test_position_comes_only_from_values_the_caller_may_see_and_goes_when_removed():
    """Design rule 8: a caller blocked from location must not learn it from which values a box keeps."""
    assets = AssetState()
    put(assets, "onemind.asset.camera.cam-1.status", 1, value="on", unit=None)
    put(assets, "onemind.asset.camera.cam-1.location", 2, value=None, unit=None, position=(52.5, 13.4))
    no_location = lambda v: "position" not in v.datapoint  # noqa: E731
    assert assets.position("camera", "cam-1") == (52.5, 13.4)
    assert assets.position("camera", "cam-1", no_location) is None
    status = assets.snapshot()[0]
    for box in ("13,52,14,53", "13.3,52.4,13.5,52.6", "13.39,52.49,13.41,52.51"):  # shrinking boxes
        assert not AssetView(None, parse_bbox(box), lambda c, i: assets.position(c, i, no_location)).passes(status)
    # The newest allowed value wins; a value that stops carrying a position no longer places it.
    put(assets, "onemind.asset.camera.cam-1.gps", 3, value=None, unit=None, position=(48.1, 11.6))
    assert assets.position("camera", "cam-1") == (48.1, 11.6)
    assert assets.position("camera", "cam-1", lambda v: v.field != "gps") == (52.5, 13.4)
    put(assets, "onemind.asset.camera.cam-1.gps", 4, value=None, unit=None)
    assert assets.position("camera", "cam-1") == (52.5, 13.4)
    assert assets.remove(asset_key("onemind.asset.camera.cam-1.location"), 5) is not None
    assert assets.position("camera", "cam-1") is None and assets._pos == {}


def test_bbox_stream_does_not_reveal_a_hidden_location(tmp_path):
    assets = AssetState()
    assets.state = "ready"
    put(assets, "onemind.asset.camera.cam-1.status", 1, value="on", unit=None)
    put(assets, "onemind.asset.camera.cam-1.location", 2, value=None, unit=None, position=(52.5, 13.4))
    _log, es = make(tmp_path, assets)

    def no_location(v: AssetValue) -> bool:
        return "position" not in v.datapoint

    async def snapshot(bbox, allowed):
        gen = es.stream(OWNER_P, "asset.*", None, never, resource_allowed=lambda ev: True,
                        bbox=parse_bbox(bbox), asset_allowed=allowed, keepalive_s=60)
        out = []
        async for chunk in gen:
            ev = parse(chunk)
            if ev is not None:
                out.append(ev)
                if ev["type"] == "stream.snapshot":
                    break
        await gen.aclose()
        return out

    async def scenario():
        for box in ("13,52,14,53", "13.39,52.49,13.41,52.51", "0,0,1,1"):  # inside, tight, far away
            evs = await snapshot(box, no_location)
            assert [e["type"] for e in evs] == ["stream.snapshot"] and evs[0]["data"]["count"] == 0
        evs = await snapshot("13.39,52.49,13.41,52.51", None)                # allowed to see location
        assert {e["subject"].get("field") for e in evs[:-1]} == {"status", "location"}
        assets.remove(asset_key("onemind.asset.camera.cam-1.location"), 3)   # the place is gone
        evs = await snapshot("13,52,14,53", None)
        assert [e["type"] for e in evs] == ["stream.snapshot"]

    asyncio.run(scenario())


# ---------------------------------------------------------------- slow clients and priority
def test_slow_client_gets_stream_reset_and_the_stream_ends(tmp_path, monkeypatch):
    monkeypatch.setattr(fanout, "FACT_QUEUE_MAX", 8)
    log, es = make(tmp_path)

    async def scenario():
        gen = es.stream(OWNER_P, "audit.*", None, never, keepalive_s=60)
        await gen.__anext__()                                      # attached; the client stops reading
        for _ in range(20):
            log.append("test.tick", WHO)
        rest = [parse(c) async for c in gen]
        return rest

    rest = asyncio.run(scenario())
    assert rest[-1]["type"] == "stream.reset" and rest[-1]["data"] == {"reason": "slow_client"}
    assert es.pump.subscribers() == []                            # the slot and the queue are freed

    monkeypatch.setattr(fanout, "VALUE_KEYS_MAX", 4)
    assets = AssetState()
    loop = asyncio.new_event_loop()
    sub = Subscriber(loop, assets=True)
    assets.listeners.append(sub.push_value)
    for i in range(6):
        put(assets, f"onemind.asset.sensor.s-{i}.temp", i + 1)
    loop.close()
    assert sub.reset == "slow_client" and sub.next() is None


def test_a_plugin_at_1000_values_a_second_delays_an_approval_under_1s(tmp_path):
    assets = AssetState()
    log, es = make(tmp_path, assets)
    out = {"produced": 0}

    async def scenario():
        gen = es.stream(OWNER_P, "action.*,asset.*", None, never, resource_allowed=lambda ev: True, keepalive_s=60)

        async def consume():
            async for chunk in gen:
                ev = parse(chunk)
                if ev and ev["type"] == "action.requested":
                    return time.perf_counter()

        async def produce():  # 1,000 values a second over 200 keys, kept up whatever the sleeps cost
            rev, start = 0, time.perf_counter()
            while (elapsed := time.perf_counter() - start) < 1.5:
                while rev < int(elapsed * 1000):
                    rev += 1
                    put(assets, f"onemind.asset.sensor.s-{rev % 200}.temp", rev, value=float(rev))
                await asyncio.sleep(0.005)
            out["produced"] = rev

        reader = asyncio.create_task(consume())
        producer = asyncio.create_task(produce())
        await asyncio.sleep(0.5)
        t0 = time.perf_counter()
        await asyncio.to_thread(log.append, "action.requested", WHO, "act-1", {})
        arrived = await asyncio.wait_for(reader, 5)
        await producer
        await gen.aclose()
        return arrived - t0

    delay = asyncio.run(scenario())
    assert out["produced"] >= 1000 and delay < 1.0


# ---------------------------------------------------------------- over HTTP: grants, filters, refusals
@pytest.fixture
def served(settings, clock, executor):
    import socket

    import uvicorn

    from onemind_core.app import create_app

    app = create_app(settings, clock=clock, executor=executor)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    yield app, f"http://127.0.0.1:{port}"
    server.should_exit = True
    t.join(timeout=5)


def _until_snapshot(lines) -> list[dict]:
    out = []
    for line in lines:
        if line.startswith("data: "):
            out.append(json.loads(line[6:]))
            if out[-1]["type"] == "stream.snapshot":
                return out
    return out


def test_a_person_without_the_grant_never_receives_that_asset(served):
    app, url = served
    assets = app.state.assets
    put(assets, "onemind.asset.camera.cam-1.status", 1, value="on", unit=None, position=(52.5, 13.4))
    put(assets, "onemind.asset.camera.cam-2.status", 2, value="on", unit=None, position=(52.6, 13.5))
    put(assets, "onemind.asset.sensor.s-1.temp", 3, position=(48.1, 11.6))
    hidden = {"cam-2"}  # what a data-class grant would hide from the adult
    app.state.gateway.asset_filters.append(lambda req, p, v: p.id == "owner" or v.asset_id not in hidden)
    with httpx.Client(base_url=url, timeout=10) as c:
        with c.stream("GET", "/v1/events?types=asset.*", headers=OWNER) as r:
            assert {e["subject"]["asset_id"] for e in _until_snapshot(r.iter_lines())[:-1]} == {"cam-1", "cam-2", "s-1"}
        with c.stream("GET", "/v1/events?types=asset.*&kind=camera&bbox=13,52,14,53", headers=ADULT) as r:
            lines = r.iter_lines()
            evs = _until_snapshot(lines)
            assert [e["subject"]["asset_id"] for e in evs[:-1]] == ["cam-1"] and evs[-1]["data"]["count"] == 1
            put(assets, "onemind.asset.camera.cam-2.status", 4, value="off", unit=None, position=(52.6, 13.5))
            put(assets, "onemind.asset.camera.cam-1.status", 5, value="off", unit=None, position=(52.5, 13.4))
            live = next(json.loads(ln[6:]) for ln in lines if ln.startswith("data: "))
            assert live["subject"]["asset_id"] == "cam-1" and live["data"]["revision"] == 5
        # A data class judged per field (location on position, design rule 8): the filter gets the
        # value itself, so it can hide one field and every datapoint carrying a position.
        app.state.gateway.asset_filters.append(
            lambda req, p, v: p.id == "owner" or (v.field != "temp" and "position" not in v.datapoint))
        put(assets, "onemind.asset.sensor.s-2.humidity", 6, value=40.0, unit="%")
        with c.stream("GET", "/v1/events?types=asset.*", headers=ADULT) as r:
            evs = _until_snapshot(r.iter_lines())
            assert [(e["subject"]["asset_id"], e["subject"]["field"]) for e in evs[:-1]] == [("s-2", "humidity")]
            assert evs[-1]["data"]["count"] == 1
        with c.stream("GET", "/v1/events?types=asset.*", headers=OWNER) as r:
            assert len(_until_snapshot(r.iter_lines())) == 5             # four values and the marker
        for who in (GUEST, AGENT):                                 # no assets:read: not even a count
            with c.stream("GET", "/v1/events?types=asset.*", headers=who) as r:
                evs = _until_snapshot(r.iter_lines())
                assert [e["type"] for e in evs] == ["stream.snapshot"] and evs[0]["data"]["count"] == 0
        for bad in ("kind=Camera", "bbox=1,2,3", "bbox=0,10,5,5"):
            r = c.get(f"/v1/events?types=asset.*&{bad}", headers=OWNER)
            assert r.status_code == 422 and r.json()["error"] == "conflict"


def test_asset_event_id_is_the_revision_and_fits_the_envelope_at_the_longest_key():
    import jsonschema

    schema = json.loads((REPO / "sdk/schema/onemind.event.schema.json").read_text())
    cls, aid, fld = "c" * 64, "a" * 128, "f" * 64                       # the registry's longest tokens
    v = AssetValue(f"{cls}.{aid}.{fld}", cls, aid, fld, 2**53, dp(f"onemind.asset.{cls}.{aid}.{fld}"))
    for ev in (asset_event(v, "2026-11-22T10:00:00Z"), asset_event(v, "2026-11-22T10:00:00Z", removed=True)):
        assert ev["id"] == f"asset:{2**53}" and len(ev["id"]) <= 128
        assert ev["subject"] == {"asset_id": aid, "asset_class": cls, "field": fld}
        jsonschema.validate(ev, schema)


def test_asset_allowed_sees_the_field_and_datapoint_in_snapshot_and_live(tmp_path):
    assets = AssetState()
    assets.state = "ready"
    put(assets, "onemind.asset.camera.cam-1.status", 1, value="on", unit=None)
    put(assets, "onemind.asset.camera.cam-1.position", 2, value=None, unit=None, position=(52.5, 13.4))
    _log, es = make(tmp_path, assets)
    asked = []

    def no_location(v: AssetValue) -> bool:
        asked.append((v.field, v.revision))
        return "position" not in v.datapoint

    async def scenario():
        gen = es.stream(OWNER_P, "asset.*", None, never, resource_allowed=lambda ev: True,
                        asset_allowed=no_location, keepalive_s=60)
        first = [parse(await gen.__anext__()) for _ in range(3)][1:]
        assert [(e["type"], e["subject"].get("field")) for e in first] == [("asset.value", "status"), ("stream.snapshot", None)]
        assert first[1]["data"]["count"] == 1
        put(assets, "onemind.asset.camera.cam-1.position", 3, value=None, unit=None, position=(52.6, 13.5))
        put(assets, "onemind.asset.camera.cam-1.status", 4, value="off", unit=None)
        live = parse(await asyncio.wait_for(gen.__anext__(), 2))
        assert live["subject"]["field"] == "status" and live["data"]["revision"] == 4
        await gen.aclose()

    asyncio.run(scenario())
    assert ("position", 2) in asked and ("position", 3) in asked


def test_asset_state_is_ready_again_after_a_nats_reconnect_on_the_same_connection():
    """nats-py keeps the same nc object across a reconnect: the state must follow stats, not id(nc)."""
    subs = []

    class Sub:
        def __init__(self):
            self.stopped = False

        async def unsubscribe(self):
            self.stopped = True

    class JS:
        async def subscribe(self, *a, **kw):
            subs.append(Sub())
            return subs[-1]

    nc = SimpleNamespace(jetstream=JS, stats={"reconnects": 0})
    bus = SimpleNamespace(nc=nc, connected=True)
    assets = AssetState()

    async def until(pred):
        for _ in range(200):
            if pred():
                return True
            await asyncio.sleep(0.01)
        return False

    async def scenario():
        task = asyncio.create_task(assets.run(bus, lambda: True, interval_s=0.01))
        assert await until(lambda: assets.state == "ready") and len(subs) == 1
        bus.connected = False                                       # NATS drops
        assert await until(lambda: assets.state == "pending") and "NATS is down" in assets.reason
        nc.stats["reconnects"] = 1                                  # nats-py reconnected the same nc
        bus.connected = True
        assert await until(lambda: assets.state == "ready")
        assert assets.reason == "" and len(subs) == 2               # subscribed again, fresh snapshot
        assert subs[0].stopped and not subs[1].stopped              # the old subscription is dropped
        await asyncio.sleep(0.05)
        assert len(subs) == 2                                       # once per connection, not per tick
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert subs[1].stopped

    asyncio.run(scenario())


def test_assets_read_is_an_owner_and_adult_default_only():
    assert may_read_assets(OWNER_P, None) and may_read_assets(Principal("a", "person", "adult"), None)
    for role in ("guest", "child", "teen", "unknown"):
        assert not may_read_assets(Principal("x", "person", role), None)
    assert not may_read_assets(Principal("h", "agent", "agent"), None)
    assert may_read_assets(Principal("h", "agent", "agent", scopes=frozenset({"assets:read"})), None)
    assert not may_read_assets(Principal("p", "plugin", "agent", scopes=frozenset({"assets:read"})), None)
    assert not may_read_assets(OWNER_P, frozenset({"events:read"}))      # a narrowed token
    assert may_read_assets(Principal("x", "person", "guest"), frozenset({"assets:read"}))


# ---------------------------------------------------------------- a real nats-server with JetStream
NATS_SERVER = __import__("shutil").which("nats-server")


@pytest.mark.skipif(NATS_SERVER is None, reason="nats-server is not installed")
def test_real_server_ordered_consumer_snapshot_and_changes(tmp_path):
    import nats

    from test_jetstream_core import Server

    srv = Server(tmp_path, jetstream.CAP_MIN_BYTES)
    srv.start()
    assets = AssetState()
    seen = []
    assets.listeners.append(lambda op, v: seen.append((op, v.key)))

    async def wait_for(pred, timeout=10.0):
        end = time.time() + timeout
        while time.time() < end and not pred():
            await asyncio.sleep(0.05)
        return pred()

    async def scenario():
        nc = await nats.connect(srv.url)
        js = nc.jetstream()
        await jetstream.ensure(js, jetstream.plan(jetstream.CAP_MIN_BYTES))
        kv = await js.key_value("asset-state")
        s1 = "onemind.asset.sensor.s-1.temp"
        await kv.put(asset_key(s1), json.dumps(dp(s1, value=1.0)).encode())
        await kv.put(asset_key(s1), json.dumps(dp(s1, value=2.0)).encode())  # only the last is the snapshot
        bus = SimpleNamespace(nc=nc, connected=True)
        task = asyncio.create_task(assets.run(bus, lambda: True, interval_s=0.05))
        assert await wait_for(lambda: assets.state == "ready" and len(assets.snapshot()) == 1)
        assert assets.snapshot()[0].datapoint["value"] == 2.0
        c1 = "onemind.asset.camera.cam-1.status"
        await kv.put(asset_key(c1), json.dumps(dp(c1, value="on", unit=None)).encode())
        await kv.delete(asset_key(s1))
        assert await wait_for(lambda: ("removed", "sensor.s-1.temp") in seen)
        assert [v.key for v in assets.snapshot()] == ["camera.cam-1.status"]
        task.cancel()
        await nc.drain()

    try:
        asyncio.run(scenario())
    finally:
        srv.stop()
