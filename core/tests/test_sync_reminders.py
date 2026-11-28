# SPDX-License-Identifier: Apache-2.0
"""OneMind Sync (F1) on its proof app, Reminders: /v1/sync/reminders/changes and /push (docs/design/SYNC.md)."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from conftest import ADULT, AGENT, OWNER, make_client
from onemind_core import systemlist
from onemind_core.appstore.service import AppStoreSettings
from onemind_core.sync.log import SyncChangeRow
from test_appstore import run
from test_builtin_conformance import live, problems

FEED, PUSH = "/v1/sync/reminders/changes", "/v1/sync/reminders/push"


def op(key, item_id, base=None, title="Buy milk", kind="upsert", **data):
    return {"key": key, "item_id": item_id, "op": kind, "base_version": base,
            "data": None if kind == "delete" else {"title": title, **data}}


def push(c, *ops, who=OWNER):
    r = c.post(PUSH, json={"ops": list(ops)}, headers=who)
    assert r.status_code == 200, r.text
    return r.json()["results"]


def feed(c, cursor=None, who=OWNER, limit=200):
    r = c.get(FEED, params={k: v for k, v in {"cursor": cursor, "limit": limit}.items() if v}, headers=who)
    assert r.status_code == 200, r.text
    return r.json()


def latest(changes) -> dict:
    """What a device holds after applying the feed in order: id -> newest change."""
    out = {}
    for ch in changes:
        out[ch["item_id"]] = ch
    return out


def test_two_devices_edit_the_same_item_and_both_copies_survive(client):
    assert push(client, op("phone-0001", "r1", title="Buy milk", due_at="2026-11-12T09:00:00Z"))[0]["version"] == 1
    # The phone and the laptop both saw version 1, then edited offline.
    a = push(client, op("phone-0002", "r1", base=1, title="Buy oat milk"))[0]
    b = push(client, op("laptop-0001", "r1", base=1, title="Buy milk and eggs"))[0]
    assert a == {"key": "phone-0002", "status": "applied", "item_id": "r1", "version": 2, "conflict_of": None, "replayed": False}
    assert b["status"] == "conflict" and b["conflict_of"] == "r1" and b["item_id"] != "r1"
    items = latest(feed(client))
    assert items["r1"]["data"]["title"] == "Buy oat milk" and items["r1"]["version"] == 2
    copy = items[b["item_id"]]
    assert copy["data"]["title"] == "Buy milk and eggs" and copy["conflict_of"] == "r1"
    assert copy["data"]["updated_at"] == "2026-11-11T22:00:00Z" and copy["data"]["id"] == b["item_id"]
    # Two devices that create the same new id offline: the second becomes a copy too.
    push(client, op("phone-0003", "r2", title="Call Ana"))
    assert push(client, op("laptop-0002", "r2", title="Call Ana back"))[0]["status"] == "conflict"
    # A stale delete never removes the newer edit.
    gone = push(client, op("laptop-0003", "r1", base=1, kind="delete"))[0]
    assert gone["status"] == "conflict" and latest(feed(client))["r1"]["deleted"] is False


def test_a_delete_is_a_tombstone_in_the_feed(client):
    push(client, op("phone-0001", "r1"))
    assert push(client, op("phone-0002", "r1", base=1, kind="delete"))[0] == {
        "key": "phone-0002", "status": "applied", "item_id": "r1", "version": 2, "conflict_of": None, "replayed": False}
    tomb = feed(client)[-1]
    assert tomb["deleted"] is True and tomb["data"] is None and tomb["version"] == 2
    # Deleting again (another device's outbox) changes nothing.
    assert push(client, op("laptop-0001", "r1", base=1, kind="delete"))[0]["status"] == "applied"
    assert len(feed(client)) == 2


def test_a_replayed_push_is_applied_once(client, settings):
    body = [op("phone-0001", "r1"), op("phone-0002", "r1", base=1, title="Buy oat milk")]
    first = push(client, *body)
    again = push(client, *body)  # the answer was lost on the way back; the outbox sends it again
    assert [r["replayed"] for r in again] == [True, True]
    assert [{**r, "replayed": False} for r in again] == first
    assert [(c["item_id"], c["version"]) for c in feed(client)] == [("r1", 1), ("r1", 2)]
    # The same key for a different change is refused, and nothing in that push is applied.
    r = client.post(PUSH, json={"ops": [op("phone-0003", "r9"), op("phone-0001", "r1", title="Other")]}, headers=OWNER)
    assert r.status_code == 409 and r.json()["reason"] == "key_reused"
    r = client.post(PUSH, json={"ops": [op("phone-0004", "r8"), op("phone-0004", "r7")]}, headers=OWNER)
    assert r.status_code == 422 and r.json()["reason"] == "duplicate_key"
    assert {c["item_id"] for c in feed(client)} == {"r1"}


def test_another_person_never_sees_your_items(client, settings):
    push(client, op("phone-0001", "r1", title="Owner's secret"))
    assert feed(client, who=ADULT) == []
    # The same item id is simply the adult's own item: no conflict, so an id tells nothing about others.
    assert push(client, op("adult-0001", "r1", title="Mine"), who=ADULT)[0]["status"] == "applied"
    assert [c["data"]["title"] for c in feed(client, who=ADULT)] == ["Mine"]
    assert [c["data"]["title"] for c in feed(client)] == ["Owner's secret"]
    # An agent syncs nothing (AI never writes a person's items directly) and the refusal is audited.
    for r in (client.get(FEED, headers=AGENT), client.post(PUSH, json={"ops": [op("agent-0001", "r1")]}, headers=AGENT)):
        assert r.status_code == 403 and r.json()["error"] == "permission_denied"
    audit = [json.loads(x) for x in settings.audit_path.read_text().splitlines()]
    assert sum(1 for e in audit if e.get("event") == "authz.denied" and "sync" in json.dumps(e)) >= 2
    assert client.get(FEED).status_code == 401


def test_the_cursor_resumes_where_it_stopped(client):
    push(client, *[op(f"phone-000{i}", f"r{i}") for i in range(5)])
    r = client.get(FEED, params={"limit": 2}, headers=OWNER)
    page = r.json()
    assert [c["item_id"] for c in page] == ["r0", "r1"] and 'rel="next"' in r.headers["link"]
    rest = feed(client, cursor=page[-1]["cursor"])
    assert [c["item_id"] for c in rest] == ["r2", "r3", "r4"]
    caught_up = rest[-1]["cursor"]
    assert feed(client, cursor=caught_up) == []
    push(client, op("phone-0009", "r0", base=1, done=True))
    assert [(c["item_id"], c["data"]["done"]) for c in feed(client, cursor=caught_up)] == [("r0", True)]
    assert int(rest[0]["cursor"]) < int(rest[-1]["cursor"])  # monotonic
    assert client.get(FEED, params={"cursor": "abc"}, headers=OWNER).status_code == 422


def test_bad_operations_are_refused(client):
    for bad in (op("short", "r1"), op("phone-0001", "a/b"), op("phone-0001", "-r1"), {**op("phone-0001", "r1"), "data": None},
                {**op("phone-0001", "r1"), "data": {"title": "x", "done": 1}},
                op("phone-0001", "r1", due_at="2026-11-12T09:00:00")):  # no time zone
        assert client.post(PUSH, json={"ops": [bad]}, headers=OWNER).status_code == 422, bad
    assert client.post(PUSH, json={"ops": []}, headers=OWNER).status_code == 422


@pytest.fixture
def with_reminders(settings, tmp_path):
    """The signed list plus reminders, as it will be once Reminders ships as a built-in."""
    doc = json.loads(systemlist.REPO_FILE.read_text())
    doc["apps"].append({"id": "reminders", "name": "Reminders", "class": "native", "update": "os", "disable": "allowed"})
    lst = tmp_path / "system-apps.json"
    lst.write_text(json.dumps(doc))
    lst.chmod(0o644)
    return replace(settings, sections={**settings.sections, "appstore": AppStoreSettings(system_apps_file=lst)})


def test_a_switched_off_reminders_app_answers_409_and_its_descriptor_conforms(with_reminders, clock):
    with make_client(with_reminders, clock) as c:
        found = c.app.state.builtins.descriptors
        tables, types = live(c)
        assert problems(found["reminders"], list(found.values()), tables, types) == []
        push(c, op("phone-0001", "r1"))
        assert run(c, clock, "app.disable", {"app_id": "reminders"}).json()["state"] == "succeeded"
        for r in (c.get(FEED, headers=OWNER), c.post(PUSH, json={"ops": [op("phone-0002", "r2")]}, headers=OWNER)):
            assert r.status_code == 409 and r.json()["reason"] == "app_disabled", r.text
        assert c.get(FEED, headers={"Authorization": "Bearer om_made_up"}).status_code == 401
        assert run(c, clock, "app.enable", {"app_id": "reminders"}).json()["state"] == "succeeded"
        assert [ch["item_id"] for ch in feed(c)] == ["r1"]
        db = c.app.state.gateway.db
        with db.session() as s:
            assert s.query(SyncChangeRow).count() == 1
