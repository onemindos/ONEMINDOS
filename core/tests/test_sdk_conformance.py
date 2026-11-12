# SPDX-License-Identifier: Apache-2.0
"""SDK conformance against a running gateway (docs/leap/dev/SDK.md §8, DEV-SDK-8).

One live gateway per test; the Python SDK runs in-process, the Go and TypeScript SDKs run their
live tests as subprocesses against the same URL. Each language skips when its toolchain is absent.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from conftest import AGENT, OWNER

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "sdk" / "python" / "src"))

OWNER_TOKEN = OWNER["Authorization"].split()[1]
AGENT_TOKEN = AGENT["Authorization"].split()[1]


@pytest.fixture
def gateway(settings, clock, executor):
    import uvicorn

    from onemind_core.app import create_app

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    # The SDKs compute expiry from the hub's clock; give the gateway the real one.
    server = uvicorn.Server(uvicorn.Config(create_app(settings, executor=executor), host="127.0.0.1", port=port,
                                           log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    t.join(timeout=5)


def _env(url: str) -> dict:
    return {**os.environ, "ONEMIND_CONFORMANCE_HUB": url, "ONEMIND_CONFORMANCE_OWNER": OWNER_TOKEN,
            "ONEMIND_CONFORMANCE_AGENT": AGENT_TOKEN}


def test_python_sdk(gateway, executor):
    from onemind_sdk import Client, NotFound, PermissionDenied, aio

    owner = Client(gateway, OWNER_TOKEN, principal="owner")
    agent = Client(gateway, AGENT_TOKEN)
    assert owner.healthz() and owner.instance.get().name == "Test OneMind"
    assert {a.id for a in owner.apps.list()} >= {"uptime-kuma", "whoami"}
    with pytest.raises(NotFound):
        owner.nodes.get("nope")
    head = (owner.audit.list(limit=500)[0] or [None])[-1]
    a = agent.actions.request("app.install", "whoami", idempotency_key="py-conformance")
    assert a.state == "awaiting_approval" and a.requested_by.id == "hermes"
    assert agent.actions.request("app.install", "whoami", idempotency_key="py-conformance").id == a.id
    with pytest.raises(PermissionDenied):
        agent.actions.approve(a.id)
    done = owner.actions.approve(a.id)
    assert done.decided_by.id == "owner" and executor.calls == [("app.install", "whoami")]
    assert owner.actions.wait(a.id, every=0.05, timeout=5).state == "succeeded"
    events = owner.events.subscribe(types=["action.*"], since_id=str(head.seq if head else 0))
    first = next(events)
    assert first["type"] == "action.requested" and first["subject"]["action_id"] == a.id
    recs, _ = owner.audit.list(action_id=a.id)
    assert [r.event for r in recs][:2] == ["action.requested", "action.awaiting_approval"]
    v = owner.audit.verify()
    assert v.ok and v.head.seq == v.records

    async def async_side():
        async with aio.Client(gateway, OWNER_TOKEN) as om:
            return [x.id for x in await om.actions.list()]

    assert a.id in asyncio.run(async_side())


def test_go_sdk(gateway):
    if not shutil.which("go"):
        pytest.skip("go not installed")
    r = subprocess.run(["go", "test", "-count=1", "-run", "TestLiveGateway", "-v", "."], cwd=REPO / "sdk" / "go",
                       env=_env(gateway), capture_output=True, text=True, timeout=300)
    assert r.returncode == 0 and "--- PASS: TestLiveGateway" in r.stdout, r.stdout + r.stderr


def test_ts_sdk(gateway):
    ts = REPO / "sdk" / "ts"
    if not shutil.which("npx") or not (ts / "node_modules" / "vitest").is_dir():
        pytest.skip("sdk/ts dependencies not installed (npm ci in sdk/ts)")
    r = subprocess.run(["npx", "vitest", "run", "test/live.test.ts"], cwd=ts, env=_env(gateway),
                       capture_output=True, text=True, timeout=300)
    out = r.stdout + r.stderr
    assert r.returncode == 0 and "1 passed" in out, out
