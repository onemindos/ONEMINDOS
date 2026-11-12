"""Real NATS round trip: heartbeat in, audit out. Skipped unless ONEMIND_TEST_NATS_URL is set.

    docker run -d --rm -p 4222:4222 --name onemind-test-nats nats:2.10-alpine
    ONEMIND_TEST_NATS_URL=nats://127.0.0.1:4222 make -C core test
"""

import asyncio
import json
import os
import threading
import time
from datetime import UTC, datetime

import nats
import pytest
from fastapi.testclient import TestClient

from conftest import OWNER, action_body
from onemind_core.app import create_app
from test_nodes_catalog import heartbeat

URL = os.environ.get("ONEMIND_TEST_NATS_URL")
pytestmark = [pytest.mark.nats, pytest.mark.skipif(not URL, reason="ONEMIND_TEST_NATS_URL not set")]


def _wait(pred, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.1)
    return False


def test_heartbeat_and_audit_over_real_nats(settings):
    from dataclasses import replace

    s = replace(settings, nats_url=URL)
    received: list[bytes] = []
    ready = threading.Event()
    stop = threading.Event()

    async def side_channel():
        nc = await nats.connect(URL)

        async def on_audit(msg):
            received.append(msg.data)

        await nc.subscribe("onemind.audit", cb=on_audit)
        ready.set()
        while not stop.is_set():
            await nc.publish("onemind.node.realnats01.status", heartbeat("realnats01"))
            await nc.flush()
            await asyncio.sleep(0.2)
        await nc.drain()

    t = threading.Thread(target=lambda: asyncio.run(side_channel()), daemon=True)
    t.start()
    assert ready.wait(10)
    # Real clock here: staleness math against wall time.
    with TestClient(create_app(s, clock=lambda: datetime.now(UTC))) as c:
        assert _wait(lambda: c.app.state.bus.connected)
        assert _wait(lambda: any(n["node_id"] == "realnats01" for n in c.get("/v1/nodes", headers=OWNER).json()))
        node = c.get("/v1/nodes/realnats01", headers=OWNER).json()
        assert node["status"] == "online"
        body = action_body(type("C", (), {"now": datetime.now(UTC)})(), key="nats-it")
        aid = c.post("/v1/actions", json=body, headers=OWNER).json()["id"]
        c.post(f"/v1/actions/{aid}/approve", headers=OWNER)
        assert _wait(lambda: any(json.loads(d).get("event") == "action.succeeded" for d in received))
    stop.set()
    t.join(5)
