# SPDX-License-Identifier: Apache-2.0
"""#608: node presence for live screens, and the departure a cleanly stopping node sends.

Acceptance (issue #608): an unplugged node shows offline within 15 s; a clean shutdown within 2 s.
The registry is the projection, GET /v1/nodes serves it, and GET /v1/events reports each change
as a `node.status` event. The node daemon side is internal/agent (TestCleanStopPublishesDepartureLast).
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import timedelta
from pathlib import Path

from conftest import OWNER, Clock
from onemind_core.auth import Principal
from onemind_core.eventstream import NODE_POLL_S, EventStream
from onemind_core.nodes import DEPARTURE_SCHEMA, HEARTBEAT_SCHEMA, NodeRegistry

SUBJECT = "onemind.node.node-a.status"
SUBJECT_B = "onemind.node.node-b.status"


def heartbeat(node_id: str = "node-a", **extra) -> bytes:
    return json.dumps({"schema": HEARTBEAT_SCHEMA, "node_id": node_id, "hostname": "a", **extra}).encode()


def departure(node_id: str = "node-a", **extra) -> bytes:
    return json.dumps({"schema": DEPARTURE_SCHEMA, "node_id": node_id, "reason": "shutdown", **extra}).encode()


def test_presence_turns_offline_once_a_heartbeat_is_clearly_missed():
    clock = Clock()
    reg = NodeRegistry(clock)
    reg.ingest(SUBJECT, heartbeat())
    start, seen = clock.now, []
    for s in (0, 10, 13, 14, 14.5, 15, 31):
        clock.now = start + timedelta(seconds=s)
        n = reg.get("node-a")
        seen.append((s, n["presence"], n["status"]))
    # status keeps its 30 s / 120 s contract, so placement and alerts do not flap on one late heartbeat
    assert seen == [(0, "online", "online"), (10, "online", "online"), (13, "online", "online"),
                    (14, "online", "online"), (14.5, "offline", "online"), (15, "offline", "online"),
                    (31, "offline", "stale")]
    reg.ingest(SUBJECT, heartbeat())
    assert reg.get("node-a")["presence"] == "online"


def test_a_departure_takes_the_node_offline_at_once_and_a_heartbeat_brings_it_back():
    clock = Clock()
    reg = NodeRegistry(clock)
    reg.ingest(SUBJECT, heartbeat())
    clock.now += timedelta(seconds=1)
    assert reg.ingest(SUBJECT, departure())
    n = reg.get("node-a")
    assert (n["status"], n["presence"]) == ("offline", "offline")
    assert n["departed_at"] == "2026-11-11T22:00:01Z" and n["hostname"] == "a"
    assert reg.list()[0]["departed_at"] == n["departed_at"]
    clock.now += timedelta(seconds=5)
    assert reg.ingest(SUBJECT, departure())  # a repeat keeps the first time
    assert reg.get("node-a")["departed_at"] == "2026-11-11T22:00:01Z"
    clock.now += timedelta(seconds=4)
    reg.ingest(SUBJECT, heartbeat())
    n = reg.get("node-a")
    assert (n["status"], n["presence"], n["departed_at"]) == ("online", "online", None)


def test_departures_that_are_not_exactly_from_a_known_node_are_dropped():
    clock = Clock()
    reg = NodeRegistry(clock)
    assert not reg.ingest(SUBJECT, departure())  # unknown node: no entry is created
    assert reg.list() == []
    reg.ingest(SUBJECT, heartbeat())
    for bad in (departure("node-b"),  # node B cannot take node A offline
                departure(extra="x"), departure(reason="reboot"),
                json.dumps({"schema": DEPARTURE_SCHEMA, "node_id": "node-a"}).encode()):
        assert not reg.ingest(SUBJECT, bad), bad
    assert not reg.ingest(SUBJECT_B, departure("node-b"))
    assert reg.get("node-a")["presence"] == "online"
    # A heartbeat cannot claim the gateway's fields.
    reg.ingest(SUBJECT, heartbeat(presence="online", departed_at="2020-01-01T00:00:00Z"))
    clock.now += timedelta(seconds=60)
    n = reg.get("node-a")
    assert (n["presence"], n["departed_at"]) == ("offline", None)


def run_stream(tmp_path: Path, reg: NodeRegistry, step) -> list[tuple[float, float, dict]]:
    """Run the live stream, calling step(i) before each poll.

    Returns (wall time, gateway clock time, event data) for each node.status event."""
    audit = tmp_path / "audit.jsonl"
    audit.write_text("")
    stream = EventStream(audit, reg.list, lambda _id: set(), reg.clock)
    p = Principal("owner", "person", "owner")
    start = reg.clock()

    async def go() -> list[tuple[float, float, dict]]:
        out: list[tuple[float, float, dict]] = []
        n = {"i": 0}

        async def gone():
            n["i"] += 1
            return step(n["i"])

        async for chunk in stream.stream(p, "node.status", None, gone, keepalive_s=60):
            text = chunk.decode()
            if "node.status" in text:
                assert "id: " not in text  # never moves the resume point
                env = json.loads(text.split("data: ", 1)[1])
                out.append((time.monotonic(), (reg.clock() - start).total_seconds(), env["data"]))
        return out

    return asyncio.run(go())


def test_acceptance_clean_shutdown_reaches_the_stream_within_two_seconds(tmp_path):
    reg = NodeRegistry(Clock())
    reg.ingest(SUBJECT, heartbeat())
    departed_at: list[float] = []

    def step(i: int) -> bool:
        if i == 2:
            reg.ingest(SUBJECT, departure())
            departed_at.append(time.monotonic())
        return i > 4

    events = run_stream(tmp_path, reg, step)
    assert [d for _, _, d in events] == [{"status": "offline", "presence": "offline", "previous": "online"}]
    assert events[0][0] - departed_at[0] < 2.0  # real stream polls (NODE_POLL_S), not simulated time
    assert NODE_POLL_S <= 0.5


def test_acceptance_unplugged_node_shows_offline_within_fifteen_seconds(tmp_path):
    """Simulated gateway time, one NODE_POLL_S per poll. node-a's plug comes out right after its
    heartbeat (the worst case); node-b's heartbeats run 3 s late and it never blinks offline."""
    clock = Clock()
    reg = NodeRegistry(clock)
    start = clock.now
    reg.ingest(SUBJECT, heartbeat())
    reg.ingest(SUBJECT_B, heartbeat("node-b"))
    last_b = [0.0]

    def step(i: int) -> bool:
        t = (i - 1) * NODE_POLL_S
        clock.now = start + timedelta(seconds=t)
        if t - last_b[0] >= 13:
            reg.ingest(SUBJECT_B, heartbeat("node-b"))
            last_b[0] = t
        return t > 40

    events = run_stream(tmp_path, reg, lambda i: step(i))
    assert [(round(t, 1), d) for _, t, d in events] == [
        (14.5, {"status": "online", "presence": "offline", "previous": "online"}),
        (30.5, {"status": "stale", "presence": "offline", "previous": "online"}),
    ]  # only node-a; 14.5 s <= 15 s


def test_nodes_api_serves_presence(client):
    reg = client.app.state.registry
    assert reg.ingest(SUBJECT, heartbeat())
    node = client.get("/v1/nodes", headers=OWNER).json()[0]
    assert (node["presence"], node["departed_at"]) == ("online", None)
    assert reg.ingest(SUBJECT, departure())
    node = client.get("/v1/nodes/node-a", headers=OWNER).json()
    assert (node["presence"], node["status"]) == ("offline", "offline") and node["departed_at"]
