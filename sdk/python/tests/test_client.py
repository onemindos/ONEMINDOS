# SPDX-License-Identifier: Apache-2.0
"""onemind-sdk unit tests against httpx.MockTransport (no gateway needed)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from onemind_sdk import (
    AmbiguousResult, Client, Expired, NetworkError, NotFound, OneMindError, UnexpectedResponse,
)
from onemind_sdk import _core as core
from onemind_sdk import aio
from onemind_sdk._core import SseParser

TOKEN = "test-token-0123456789abcdef"


def make(handler, **kw):
    return Client("http://localhost:8080/", TOKEN, transport=httpx.MockTransport(handler), sleep=lambda s: None, **kw)


def action(state, decided_by=None):
    return {"id": "a1", "type": "app.install", "params": {"app_id": "x"}, "state": state, "idempotency_key": "k",
            "requested_by": {"id": "hermes", "kind": "agent", "role": "agent"}, "created_at": "t", "updated_at": "t",
            "expires_at": "t", "decided_by": {"id": decided_by, "kind": "person", "role": "owner"} if decided_by else None,
            "decided_at": None, "result": None, "version": 2}


def test_get_retries_and_typed_errors():
    n = {"nodes": 0}

    def h(req: httpx.Request):
        assert req.headers["authorization"] == f"Bearer {TOKEN}"
        p = req.url.path
        if p == "/v1/nodes":
            n["nodes"] += 1
            if n["nodes"] < 3:
                return httpx.Response(503)
            return httpx.Response(200, json=[{"node_id": "a", "status": "online", "last_seen": "t", "future": 1}])
        if p == "/v1/nodes/x":
            return httpx.Response(404, json={"error": "not_found", "message": "no such node"})
        if p == "/v1/instance":
            return httpx.Response(200, text="<html>")
        return httpx.Response(418, json={"error": "brand_new", "message": "newer"})

    om = make(h)
    nodes = om.nodes.list()
    assert n["nodes"] == 3 and nodes[0].node_id == "a" and nodes[0].model_extra == {"future": 1}
    with pytest.raises(NotFound) as e:
        om.nodes.get("x")
    assert str(e.value) == "HTTP 404 not_found: no such node"
    with pytest.raises(UnexpectedResponse):
        om.instance.get()
    with pytest.raises(OneMindError) as e:
        om.apps.list()
    assert e.value.code == "brand_new"


def test_token_never_in_repr_or_errors():
    def h(req):
        raise httpx.ConnectError(f"refused {TOKEN}")

    om = make(h, retries=1)
    assert TOKEN not in repr(om) and repr(om) == "OneMind(hub=http://localhost:8080, principal=?)"
    with pytest.raises(NetworkError) as e:
        om.healthz()
    assert TOKEN not in str(e.value)


def test_plain_http_warns_once():
    om = Client("hub.example:8080", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": True})))
    with pytest.warns(UserWarning, match="plain http"):
        om.healthz()
    om.healthz()  # no second warning (pytest would not fail on it, but the flag is set)
    assert om._warned


def test_request_reuses_key_and_uses_hub_clock():
    keys = []
    ahead = format_datetime(datetime.now(UTC) + timedelta(hours=1), usegmt=True)

    def h(req):
        if req.url.path == "/v1/instance":
            return httpx.Response(200, json={"name": "x", "version": "0", "hub_node_id": None}, headers={"date": ahead})
        b = json.loads(req.content)
        keys.append(b["idempotency_key"])
        if len(keys) == 1:
            return httpx.Response(502)
        exp = datetime.fromisoformat(b["expires_at"].replace("Z", "+00:00"))
        assert exp - datetime.now(UTC) > timedelta(hours=24, minutes=50)
        return httpx.Response(201, json=action("awaiting_approval"))

    a = make(h).actions.request("app.install", "ntfy")
    assert a.state == "awaiting_approval" and len(keys) == 2 and keys[0] == keys[1]


def test_request_reuses_expires_at_for_one_key_across_seconds():
    # The hub's clock (Date header) moves 5 s per answer, so a recomputed expires_at would differ.
    tick = {"n": 0}
    bodies = []

    def h(req):
        tick["n"] += 1
        date = format_datetime(datetime.now(UTC) + timedelta(seconds=5 * tick["n"]), usegmt=True)
        if req.url.path == "/v1/instance":
            return httpx.Response(200, json={"name": "x", "version": "0", "hub_node_id": None}, headers={"date": date})
        bodies.append(json.loads(req.content))
        return httpx.Response(201, json=action("awaiting_approval"), headers={"date": date})

    for client in (make(h),):
        client.actions.request("app.install", "ntfy", idempotency_key="k1")
        client.actions.request("app.install", "ntfy", idempotency_key="k1")
        client.actions.request("app.install", "ntfy", idempotency_key="k2")
        client.actions.request("app.install", "ntfy")
        client.actions.request("app.install", "ntfy")
    assert bodies[0]["expires_at"] == bodies[1]["expires_at"]
    assert bodies[2]["expires_at"] != bodies[0]["expires_at"]  # another key gets its own
    assert bodies[3]["idempotency_key"] != bodies[4]["idempotency_key"]  # no key: fresh uuid each call


def test_expiry_memo_is_bounded_and_drops_expired():
    memo = core.ExpiryMemo()
    now = datetime(2030, 1, 1, tzinfo=UTC)
    for i in range(core.ExpiryMemo.MAX + 10):
        memo.get(f"k{i}", now, timedelta(hours=1))
    assert len(memo._by_key) == core.ExpiryMemo.MAX
    later = now + timedelta(hours=2)
    first = memo.get("fresh", later, timedelta(hours=1))
    assert list(memo._by_key) == ["fresh"] and first == "2030-01-01T03:00:00Z"


@pytest.mark.parametrize("principal,decided,ok", [("owner", "owner", True), ("owner", "other", False), (None, "owner", False)])
def test_approve_read_back(principal, decided, ok):
    posts = []

    def h(req):
        if req.method == "POST":
            posts.append(1)
            return httpx.Response(502)
        return httpx.Response(200, json=action("succeeded", decided))

    om = make(h, principal=principal)
    if ok:
        assert om.actions.approve("a1").state == "succeeded"
    else:
        with pytest.raises(AmbiguousResult) as e:
            om.actions.approve("a1")
        assert e.value.action.state == "succeeded"
    assert len(posts) == 1
    with pytest.raises(Expired):
        make(lambda r: httpx.Response(409, json={"error": "expired", "message": "late"})).actions.deny("a1")


def test_wait_and_audit_paging():
    states = iter(["awaiting_approval", "accepted", "succeeded"])

    def h(req):
        if req.url.path.startswith("/v1/audit"):
            assert req.url.params["event"] == "action.*"
            rec = {"seq": 1, "ts": "t", "event": "x", "principal": None, "action_id": None, "data": {},
                   "prev_hash": "0" * 64, "hash": "1" * 64}
            return httpx.Response(200, json=[rec], headers={"link": '</v1/audit/events?after_seq=1>; rel="next"'})
        return httpx.Response(200, json=action(next(states), "owner"))

    om = make(h)
    seen = []
    assert om.actions.wait("a1", on_change=lambda a: seen.append(a.state)).state == "succeeded"
    assert seen == ["awaiting_approval", "accepted", "succeeded"]
    recs, more = om.audit.list(event="action.*", limit=1)
    assert recs[0].seq == 1 and more


def test_sse_parser():
    p = SseParser()
    out = list(p.feed("retry: 3000\n\n: keepalive\n\nid: 7\nevent: action.requested\ndata: {\"id\":\"7\""))
    assert out == [] and p.retry_ms == 3000
    out = list(p.feed(",\"type\":\"action.requested\"}\r\n\r\n"))
    assert out == [("7", {"id": "7", "type": "action.requested"})]


def test_subscribe_resumes_with_last_event_id():
    seen_last = []

    def h(req):
        seen_last.append(req.headers.get("last-event-id"))
        if len(seen_last) == 1:
            body = "id: 7\nevent: action.requested\ndata: {\"id\":\"7\",\"type\":\"action.requested\"}\n\n"
        else:
            body = "id: 8\nevent: action.state_changed\ndata: {\"id\":\"8\",\"type\":\"action.state_changed\"}\n\n"
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    it = make(h).events.subscribe(types=["action.*"])
    assert [next(it)["id"], next(it)["id"]] == ["7", "8"]
    assert seen_last == [None, "7"]
    with pytest.raises(NotFound):
        next(make(lambda r: httpx.Response(404, json={"error": "not_found", "message": "x"})).events.subscribe())


def test_async_client_same_surface():
    async def scenario():
        async def h(req):
            if req.method == "POST":
                return httpx.Response(502)
            return httpx.Response(200, json=action("succeeded", "owner"))

        async def nosleep(s):
            return None

        async with aio.Client("http://localhost", TOKEN, transport=httpx.MockTransport(h), sleep=nosleep,
                              principal="owner") as om:
            a = await om.actions.approve("a1")
            got = await om.actions.get("a1")
            return a.state, got.decided_by.id

    assert asyncio.run(scenario()) == ("succeeded", "owner")


def test_from_env():
    om = Client.from_env({"ONEMIND_GATEWAY_URL": "http://gw:8080", "ONEMIND_AGENT_TOKEN": "t"})
    assert om.base_url == "http://gw:8080"
    with pytest.raises(ValueError):
        Client.from_env({})
