# SPDX-License-Identifier: Apache-2.0
"""Developer surface, gateway side: OpenAPI export, audit read API (§12.16), events SSE (§12.8)."""

from __future__ import annotations

import json
import re
import socket
import threading
import time
from pathlib import Path

import httpx
import pytest

from conftest import ADULT, AGENT, GUEST, OWNER, action_body
from onemind_core import openapi
from onemind_core.auditread import verify_file
from onemind_core.eventstream import events_for_record

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / "sdk" / "openapi" / "onemind-v1.json"


# ---- OpenAPI ---------------------------------------------------------------------------------
def test_committed_openapi_is_current():
    assert SPEC.read_text(encoding="utf-8") == openapi.render(), "run `make -C sdk openapi`"


def test_export_is_deterministic():
    assert openapi.render() == openapi.render()


def test_every_operation_has_a_stable_unique_id():
    doc = json.loads(openapi.render())
    ids = [op["operationId"] for p in doc["paths"].values() for op in p.values()]
    assert len(ids) == len(set(ids))
    for i in ids:
        assert re.fullmatch(r"[a-z]+(\.[a-z_]+)+", i), i


def test_served_openapi_equals_export(client):
    assert json.dumps(client.get("/openapi.json").json(), sort_keys=True, indent=2, ensure_ascii=False) + "\n" \
        == openapi.render()


def test_check_flag(tmp_path):
    f = tmp_path / "spec.json"
    assert openapi.main(["--check", str(f)]) == 1
    assert openapi.main(["--out", str(f)]) == 0
    assert openapi.main(["--check", str(f)]) == 0


# ---- audit read API --------------------------------------------------------------------------
def _request(client, clock, key="k1", headers=OWNER, app_id="uptime-kuma"):
    r = client.post("/v1/actions", json=action_body(clock, app_id=app_id, key=key), headers=headers)
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_audit_events_owner_sees_all_with_paging(client, clock):
    _request(client, clock, "a")
    _request(client, clock, "b", headers=AGENT, app_id="whoami")
    r = client.get("/v1/audit/events", headers=OWNER)
    assert r.status_code == 200
    rows = r.json()
    assert [x["seq"] for x in rows] == list(range(1, len(rows) + 1))
    assert {"seq", "ts", "event", "principal", "action_id", "data", "prev_hash", "hash"} <= set(rows[0])
    page = client.get("/v1/audit/events?limit=2&event=action.*", headers=OWNER)
    assert len(page.json()) == 2 and all(x["event"].startswith("action.") for x in page.json())
    link = page.headers["link"]
    nxt = re.match(r"<([^>]+)>; rel=\"next\"", link).group(1)
    rest = client.get(nxt, headers=OWNER).json()
    assert rest and rest[0]["seq"] > page.json()[-1]["seq"]
    assert all(x["event"].startswith("action.") for x in rest)
    one = client.get(f"/v1/audit/events/{rows[0]['seq']}", headers=OWNER).json()
    assert one == rows[0]
    assert client.get("/v1/audit/events/99999", headers=OWNER).status_code == 404


def test_audit_events_agent_sees_only_own(client, clock):
    mine = _request(client, clock, "b", headers=AGENT, app_id="whoami")
    _request(client, clock, "a")
    rows = client.get("/v1/audit/events", headers=AGENT).json()
    assert rows
    for x in rows:
        assert (x["principal"] or {}).get("id") == "hermes" or x["action_id"] == mine["id"]
    assert client.get("/v1/audit/events", headers=ADULT).status_code == 200
    assert client.get("/v1/audit/events", headers=GUEST).status_code == 403
    assert client.get("/v1/audit/verify", headers=AGENT).status_code == 403


def test_audit_verify_ok_then_tampered(client, clock, settings):
    _request(client, clock)
    v = client.get("/v1/audit/verify", headers=OWNER).json()
    assert v["ok"] is True and v["first_bad_seq"] is None and v["records"] == v["head"]["seq"] >= 2
    assert v["last_checkpoint"] is None
    lines = settings.audit_path.read_text().splitlines(keepends=True)
    rec = json.loads(lines[1])
    rec["event"] = "tampered"
    lines[1] = json.dumps(rec, sort_keys=True, separators=(",", ":")) + "\n"
    settings.audit_path.write_text("".join(lines))
    v = client.get("/v1/audit/verify", headers=OWNER).json()
    assert v["ok"] is False and v["first_bad_seq"] == 2 and "hash mismatch" in v["reason"]


def test_shared_audit_vectors():
    """sdk/testdata/audit: the Go CLI checks the same files (one rule, two languages)."""
    root = REPO / "sdk" / "testdata" / "audit"
    expected = json.loads((root / "expected.json").read_text())
    assert expected
    for name, want in expected.items():
        got = verify_file(root / name)
        assert (got["ok"], got["records"], got["first_bad_seq"]) == (want["ok"], want["records"], want["first_bad_seq"]), name


def test_event_mapping():
    evs = events_for_record({"seq": 7, "ts": "t", "event": "action.approved", "principal": {"id": "owner"},
                             "action_id": "a1", "data": {}})
    assert [e["type"] for e in evs] == ["action.state_changed", "audit.appended"]
    assert evs[0]["data"]["to"] == "accepted" and evs[0]["id"] == "7" and evs[0]["schema"] == "onemind.event/v1"


# ---- events SSE (live server) ----------------------------------------------------------------
def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def live(settings, clock, executor):
    import uvicorn

    from onemind_core.app import create_app

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(
        create_app(settings, clock=clock, executor=executor), host="127.0.0.1", port=port, log_level="warning",
    ))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    t.join(timeout=5)


def _read_events(resp, n, timeout=10.0):
    out, cur, deadline = [], {}, time.monotonic() + timeout
    for line in resp.iter_lines():
        if time.monotonic() > deadline:
            break
        if line == "":
            if "data" in cur:
                out.append(cur)
                if len(out) >= n:
                    break
            cur = {}
            continue
        if line.startswith(":"):
            continue
        k, _, v = line.partition(": ")
        cur[k] = v
    return out


def test_events_stream_live_and_resume(live, clock):
    with httpx.Client(base_url=live, timeout=15) as c:
        with c.stream("GET", "/v1/events?types=action.*", headers=OWNER) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            c2 = httpx.Client(base_url=live, timeout=15)
            a = c2.post("/v1/actions", json=action_body(clock), headers=OWNER).json()
            c2.post(f"/v1/actions/{a['id']}/deny", headers=OWNER)
            evs = _read_events(resp, 3)
        types = [e["event"] for e in evs]
        assert types[0] == "action.requested" and "action.state_changed" in types
        data = [json.loads(e["data"]) for e in evs]
        assert all(d["subject"]["action_id"] == a["id"] for d in data)
        assert any(d["data"].get("to") == "cancelled" for d in data)
        first_id = int(evs[0]["id"])
        # Resume from before the request: the same events are replayed.
        with c.stream("GET", "/v1/events?types=action.*", headers={**OWNER, "Last-Event-ID": str(first_id - 1)}) as r2:
            again = _read_events(r2, 3)
        assert [e["id"] for e in again] == [e["id"] for e in evs]
        # The agent does not see the owner's actions nor audit.*; a guest sees no action.*.
        with c.stream("GET", "/v1/events?since_id=0", headers=AGENT) as r3:
            mine = c2.post("/v1/actions", json=action_body(clock, app_id="whoami", key="ag"), headers=AGENT).json()
            got = _read_events(r3, 1)
        d = json.loads(got[0]["data"])
        assert d["type"] == "action.requested" and d["subject"]["action_id"] == mine["id"]
        c2.close()


def test_events_stream_reset_and_limit(live):
    with httpx.Client(base_url=live, timeout=15) as c:
        with c.stream("GET", "/v1/events?since_id=999999", headers=OWNER) as r:
            evs = _read_events(r, 1)
        assert evs[0]["event"] == "stream.reset" and "id" not in evs[0]
        streams = [c.stream("GET", "/v1/events", headers=GUEST) for _ in range(5)]
        opened = [s.__enter__() for s in streams]
        assert all(o.status_code == 200 for o in opened)
        sixth = c.get("/v1/events", headers=GUEST)
        assert sixth.status_code == 429 and sixth.json()["error"] == "rate_limited" and sixth.headers["retry-after"]
        for s in streams:
            s.__exit__(None, None, None)
        assert c.get("/v1/events", headers={}).status_code == 401


# ---- review fixes ------------------------------------------------------------------------------
def test_audit_time_filters_are_instants_and_validated(client, clock):
    _request(client, clock)
    rows = client.get("/v1/audit/events", headers=OWNER).json()
    ts = rows[0]["ts"]
    # The same instant written with an offset selects the same records as the Z form.
    from datetime import datetime, timedelta, timezone

    t = datetime.fromisoformat(ts)
    shifted = t.astimezone(timezone(timedelta(hours=2))).isoformat()
    a = client.get("/v1/audit/events", params={"since": ts}, headers=OWNER).json()
    b = client.get("/v1/audit/events", params={"since": shifted}, headers=OWNER).json()
    assert a and [x["seq"] for x in a] == [x["seq"] for x in b]
    assert client.get("/v1/audit/events", params={"until": ts}, headers=OWNER).json() == [
        x for x in rows if datetime.fromisoformat(x["ts"]) < t
    ]
    for bad in ("yesterday", "2026-11-12T09:00:00"):  # not RFC 3339; no zone
        r = client.get("/v1/audit/events", params={"since": bad}, headers=OWNER)
        assert r.status_code == 422 and r.json()["error"] == "conflict", bad


def test_event_filter_reads_the_ledger_once_not_per_event():
    from onemind_core.auth import Principal
    from onemind_core.eventstream import EventStream

    calls = []

    def owned(pid):
        calls.append(pid)
        return {"mine-1", "mine-2"}

    es = EventStream(Path("/nonexistent"), lambda: [], owned, lambda: None)
    ok = es._allowed(Principal(id="hermes", kind="agent", role="agent"))

    def ev(t, aid=None):
        return {"type": t, "subject": {"action_id": aid} if aid else {"node_id": "n"}}

    assert ok(ev("action.requested", "mine-1")) and ok(ev("action.state_changed", "mine-2"))
    for _ in range(50):
        assert not ok(ev("action.state_changed", "theirs"))
    assert len(calls) == 2  # first lookup, plus one refresh for the unknown id
    assert ok(ev("node.status")) and not ok(ev("audit.appended")) and not ok(ev("backup.run.finished"))

    guest = es._allowed(Principal(id="g", kind="person", role="guest"))
    assert guest(ev("node.status")) and not guest(ev("action.requested", "mine-1"))
    child = es._allowed(Principal(id="c", kind="person", role="child"))  # §12.6: no nodes:read
    assert not child(ev("node.status"))


def test_mcp_search_audit_rejects_bad_times():
    import pytest as _pytest

    from onemind_core.auth import Principal
    from onemind_core.mcp.tools import Catalogue, RpcError

    class Svc:
        @staticmethod
        def audit_list(p, **kw):
            from onemind_core.auditread import parse_time

            parse_time(kw.get("since"), "since")
            return [], False

    class Lim:
        class reads:
            @staticmethod
            def hit(_):
                return 0

    cat = Catalogue(Svc(), Lim())
    with _pytest.raises(RpcError) as e:
        cat.call(Principal(id="hermes", kind="agent", role="agent"), "search_audit", {"since": "soon"})
    assert e.value.code == -32602 and "RFC 3339" in e.value.message
