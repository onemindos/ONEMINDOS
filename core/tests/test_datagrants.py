# SPDX-License-Identifier: Apache-2.0
"""The data commons (#615): data classes, grants and their enforcement.

Acceptance: a plugin with no grant gets empty data; revoke ends an open stream within 5 s; agents
cannot approve their own request (must refuse).
"""

from __future__ import annotations

import json
import threading
import time
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from conftest import ADULT, AGENT, OWNER
from onemind_core.datagrants import CLASSES, STREAM_POLL_S
from onemind_core.identity.crypto import new_secret, sha256_hex
from onemind_core.identity.models import TokenRow

REPO = Path(__file__).resolve().parents[2]


def grant_body(clock, key: str, **params) -> dict:
    return {"type": "data.grant", "params": {"expires_in_days": 7, **params}, "idempotency_key": key,
            "expires_at": (clock.now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")}


def request(c, clock, headers, key, **params):
    return c.post("/v1/actions", headers=headers, json=grant_body(clock, key, **params))


def granted(c, clock, key, **params) -> str:
    """The owner files and approves a grant; returns the new grant id."""
    a = request(c, clock, OWNER, key, **params)
    assert a.status_code == 201, a.text
    done = c.post(f"/v1/actions/{a.json()['id']}/approve", headers=OWNER).json()
    assert done["state"] == "succeeded", done
    return done["result"]["steps"][0]["grant_id"]


def write(c, cls="location", headers=OWNER, value=None, key=None):
    h = {**headers, **({"Idempotency-Key": key} if key else {})}
    return c.post(f"/v1/data/classes/{cls}/records", headers=h, json={"kind": "place.visit", "value": value or {"at": "home"}})


def records(c, headers, cls="location"):
    r = c.get(f"/v1/data/classes/{cls}/records", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def plugin_token(c, clock, app_id="uptime-kuma") -> dict:
    """A real installed-plugin token (hashed into the identity store), as the install would issue."""
    token = new_secret("plg")
    c.app.state.identity.repo.add(TokenRow(
        id=f"tok_{app_id}", prefix=token[:11], name="Installed plugin", hash=sha256_hex(token), kind="plugin",
        principal_id=f"plugin:{app_id}", owner_user_id=None, scopes=["apps:read"], source="app-install",
        created_by="owner", created_at=clock(), expires_at=clock() + timedelta(days=1)))
    c.app.state.repo.set_app_state(app_id, "installed", clock())
    return {"Authorization": "Bearer " + token}


# ---- a plugin with no grant gets empty data -----------------------------------------------------------

def test_a_plugin_with_no_grant_gets_empty_data(client, clock):
    assert write(client).status_code == 201
    plugin = plugin_token(client, clock)
    assert records(client, plugin) == []
    one = client.get("/v1/data/classes/location", headers=plugin).json()
    assert one["count"] is None and one["access"] == {"read": False, "write": False, "aggregate": False}
    assert all(c["access"]["read"] is (c["id"] == "public") for c in client.get("/v1/data/classes", headers=plugin).json())

    granted(client, clock, "g1", data_class="location", read=True, grantee={"kind": "app", "id": "uptime-kuma"})
    got = records(client, plugin)
    assert [r["value"] for r in got] == [{"at": "home"}] and got[0]["source"] == "owner"
    assert records(client, plugin, "activity") == []  # a grant covers its own class only
    assert records(client, plugin_token(client, clock, "other-app")) == []  # and its own app only


def test_an_expired_grant_reads_empty_again(client, clock):
    write(client)
    granted(client, clock, "g1", data_class="location", read=True, grantee={"kind": "agent", "id": "hermes"},
            expires_in_days=1)
    assert len(records(client, AGENT)) == 1
    clock.advance(86400 + 1)
    assert records(client, AGENT) == []
    assert client.get("/v1/data/grants", headers=AGENT).json()[0]["active"] is False


def test_aggregate_sees_the_count_only_and_write_needs_a_write_grant(client, clock):
    write(client)
    write(client)
    assert write(client, headers=AGENT).status_code == 403
    granted(client, clock, "g1", data_class="location", aggregate=True, write=True,
            grantee={"kind": "agent", "id": "hermes"})
    assert records(client, AGENT) == []
    assert client.get("/v1/data/classes/location", headers=AGENT).json()["count"] == 2
    first = write(client, headers=AGENT, key="k1")
    assert first.status_code == 201 and first.json()["source"] == "hermes"
    assert write(client, headers=AGENT, key="k1").json()["id"] == first.json()["id"]  # replay, not a copy
    assert write(client, headers=AGENT, key="k1", value={"at": "work"}).status_code == 409
    assert client.get("/v1/data/classes/location", headers=OWNER).json()["count"] == 3


def test_public_is_readable_by_everyone_and_the_owner_holds_every_class(client, clock):
    write(client, "public", value={"note": "hi"})
    assert [r["value"] for r in records(client, ADULT, "public")] == [{"note": "hi"}]
    assert write(client, "public", headers=ADULT).status_code == 403
    assert all(c["access"] == {"read": True, "write": True, "aggregate": True}
               for c in client.get("/v1/data/classes", headers=OWNER).json())


def test_records_page_with_limit_cursor_and_link(client):
    for _ in range(3):
        write(client)
    r = client.get("/v1/data/classes/location/records?limit=2", headers=OWNER)
    assert len(r.json()) == 2 and 'rel="next"' in r.headers["link"]
    cursor = r.json()[-1]["id"]
    rest = client.get(f"/v1/data/classes/location/records?limit=2&cursor={cursor}", headers=OWNER)
    assert len(rest.json()) == 1 and "link" not in rest.headers


# ---- a request is an approval card; agents never approve their own ---------------------------------------

def test_an_agent_request_is_an_approval_card_the_agent_cannot_approve(client, clock):
    write(client)
    a = request(client, clock, AGENT, "a1", data_class="location", read=True)
    assert a.status_code == 201, a.text
    action = a.json()
    assert action["state"] == "awaiting_approval" and action["type"] == "data.grant"
    assert action["params"] == {"data_class": "location", "read": True, "write": False, "aggregate": False,
                                "expires_in_days": 7}
    r = client.post(f"/v1/actions/{action['id']}/approve", headers=AGENT)
    assert r.status_code == 403 and r.json()["error"] == "permission_denied"
    assert client.get(f"/v1/actions/{action['id']}", headers=OWNER).json()["state"] == "awaiting_approval"
    assert records(client, AGENT) == [] and client.get("/v1/data/grants", headers=AGENT).json() == []

    done = client.post(f"/v1/actions/{action['id']}/approve", headers=OWNER).json()
    assert done["state"] == "succeeded"
    assert len(records(client, AGENT)) == 1
    mine = client.get("/v1/data/grants", headers=AGENT).json()
    assert [(g["grantee"], g["approved_by"], g["requested_by"]) for g in mine] == \
        [({"kind": "agent", "id": "hermes"}, "owner", "hermes")]


def test_an_agent_cannot_ask_for_someone_else_or_revoke(client, clock):
    r = request(client, clock, AGENT, "a1", data_class="private", read=True, grantee={"kind": "person", "id": "adult"})
    assert r.status_code == 403
    gid = granted(client, clock, "g1", data_class="private", read=True, grantee={"kind": "agent", "id": "hermes"})
    assert client.delete(f"/v1/data/grants/{gid}", headers=AGENT).status_code == 403
    assert client.delete(f"/v1/data/grants/{gid}", headers=ADULT).status_code == 403
    assert client.get("/v1/data/grants", headers=AGENT).json()[0]["active"] is True


def test_bad_requests_are_refused(client, clock):
    assert request(client, clock, AGENT, "a1", data_class="location").status_code == 422  # no mode
    assert request(client, clock, AGENT, "a2", data_class="secrets", read=True).status_code == 422
    assert request(client, clock, AGENT, "a3", data_class="location", read=True, expires_in_days=400).status_code == 422
    assert request(client, clock, OWNER, "a4", data_class="location", read=True).status_code == 422  # for whom?
    assert client.get("/v1/data/classes/secrets/records", headers=OWNER).status_code == 422


def test_revoke_takes_access_away_and_a_new_grant_replaces_the_old(client, clock):
    write(client)
    g1 = granted(client, clock, "g1", data_class="location", read=True, grantee={"kind": "person", "id": "adult"})
    g2 = granted(client, clock, "g2", data_class="location", read=True, grantee={"kind": "person", "id": "adult"})
    grants = {g["id"]: g for g in client.get("/v1/data/grants", headers=OWNER).json()}
    assert grants[g1]["active"] is False and grants[g1]["revoked_by"] == f"superseded:{g2}"
    assert len(records(client, ADULT)) == 1
    out = client.delete(f"/v1/data/grants/{g2}", headers={**OWNER, "Idempotency-Key": "r1"})
    assert out.status_code == 200 and out.json()["revoked_by"] == "owner" and out.json()["active"] is False
    assert records(client, ADULT) == []
    assert client.delete(f"/v1/data/grants/{g2}", headers=OWNER).status_code == 200  # twice is a no-op
    assert client.delete("/v1/data/grants/dgr_missing", headers=OWNER).status_code == 404


def test_classes_are_the_descriptor_schema_classes(client):
    schema = json.loads((REPO / "sdk/schema/onemind.builtin.schema.json").read_text())
    assert list(CLASSES) == schema["$defs"]["dataClass"]["enum"]
    photos = next(c for c in client.get("/v1/data/classes", headers=OWNER).json() if c["id"] == "location")
    assert "photos" in photos["owned_by"]


# ---- revoke ends an open stream within 5 s (live server) ---------------------------------------------------

@pytest.fixture
def live(settings, clock, executor):
    import socket

    import uvicorn

    from onemind_core.app import create_app

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(settings, clock=clock, executor=executor),
                                           host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=15) as c:
        yield c
    server.should_exit = True
    t.join(timeout=5)


def sse(resp):
    """(event, data) pairs from an open SSE response."""
    cur: dict = {}
    for line in resp.iter_lines():
        if line == "":
            if "event" in cur:
                yield cur["event"], json.loads(cur.get("data") or "null")
            cur = {}
        elif not line.startswith(":"):
            k, _, v = line.partition(": ")
            cur[k] = v


def test_revoke_ends_an_open_stream_within_5_seconds(live, clock):
    with live.stream("GET", "/v1/data/classes/location/stream", headers=AGENT) as r:
        assert r.status_code == 200
        assert next(sse(r)) == ("end", {"reason": "no_grant"})  # no grant: nothing, and the stream ends

    gid = granted(live, clock, "g1", data_class="location", read=True, grantee={"kind": "agent", "id": "hermes"})
    with live.stream("GET", "/v1/data/classes/location/stream", headers=AGENT) as r:
        events = sse(r)
        assert write(live).status_code == 201
        assert next(events)[0] == "record"
        revoked = time.monotonic()
        assert live.delete(f"/v1/data/grants/{gid}", headers=OWNER).status_code == 200
        assert next(events) == ("end", {"reason": "revoked"})
        took = time.monotonic() - revoked
    assert took < 5, took
    assert took <= STREAM_POLL_S + 1
