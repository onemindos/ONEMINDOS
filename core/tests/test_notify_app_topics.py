# SPDX-License-Identifier: Apache-2.0
"""Per-app notification topics, app principals, the app chip and auto-mute (#613; N1 and N7)."""

from __future__ import annotations

from dataclasses import replace

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from conftest import ADULT, AGENT, OWNER
from onemind_core import builtins, systemlist
from onemind_core.app import create_app
from onemind_core.notify import NotifySettings, routing, topics
from onemind_core.notify.store import _notify_v2

SEND = "/v1/notifications/send"


@pytest.fixture
def nclient(settings, clock, executor, tmp_path):
    s = replace(settings, sections={"notify": NotifySettings(worker=False, dir=tmp_path / "keys")})
    with TestClient(create_app(s, clock=clock, executor=executor)) as c:
        yield c


def descriptor(app_id: str, name: str, topic: str, title: str) -> dict:
    return {"apiVersion": "onemind.app/v1", "kind": "App", "metadata": {"id": app_id, "name": name},
            "spec": {"routes": {"owns": [], "calls": []},
                     "notifications": {"topics": [{"id": topic, "title": title}]},
                     "backup": {"units": [{"kind": "dir", "name": f"ONEMIND_{app_id.upper()}_DIR"}]},
                     "data": {"owns": ["owner"], "reads": []}, "phone": {"entry": "web"}}}


def registry(tmp_path, off=frozenset()) -> builtins.Builtins:
    """Calendar and World (W2 built-ins) as signed descriptors, loaded the way the gateway loads them."""
    apps = {}
    for app_id, name, topic, title in (("calendar", "Calendar", "reminders", "Reminders"),
                                       ("world", "World", "watch", "Watch area alerts")):
        (tmp_path / app_id).mkdir()
        (tmp_path / app_id / builtins.DESCRIPTOR).write_text(yaml.safe_dump(descriptor(app_id, name, topic, title)))
        apps[app_id] = systemlist.SystemApp(app_id, name, "native", "os", "allowed")
    found, errors = builtins.load(systemlist.SystemList(apps), root=tmp_path)
    assert errors == {} and set(found) == {"calendar", "world"}
    return builtins.Builtins(found, lambda: frozenset(off))


def inbox(c, headers=OWNER):
    r = c.get("/v1/notifications", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_calendar_reminder_and_world_alert_land_in_one_inbox_with_their_app_chip(nclient, tmp_path):
    reg = registry(tmp_path)
    svc = nclient.app.state.notify
    svc.topics = topics.TopicRegistry(reg)
    seen = []
    nclient.app.state.events.subscribe("notification.>", seen.append)

    out = svc.post(reg.principal("calendar"), topic="app.calendar.reminders", severity="info",
                   title="Dentist at 15:00", link="/calendar", group_key="day:2026-11-23")
    assert out == {"queued": 1, "deduplicated": False, "muted": False}
    svc.post(reg.principal("world"), topic="app.world.watch", severity="warning", title="Quake near the farm",
             asset_id="site_farm", actions=[{"id": "show", "label": "Show on map", "kind": "open", "link": "/map"}])

    world, cal = inbox(nclient)
    assert (cal["app_id"], cal["source_kind"], cal["topic"], cal["source"]) == ("calendar", "app", "app.calendar.reminders", "app:calendar")
    assert cal["group_key"] == "day:2026-11-23" and cal["actions"] == [] and cal["link"] == "/calendar"
    assert (world["app_id"], world["source_kind"], world["asset_id"]) == ("world", "app", "site_farm")
    assert world["actions"] == [{"id": "show", "label": "Show on map", "kind": "open", "link": "/map"}]
    # The stream event carries the chip and the asset (ids only, never the text).
    created = [e["data"] for e in seen if e["type"] == "notification.created"]
    assert [(d["app_id"], d["source_kind"], d["asset_id"]) for d in created] == [("calendar", "app", None), ("world", "app", "site_farm")]
    assert all("title" not in d for d in created)
    # The owner's Settings page lists both apps with their declared topics, not muted.
    r = nclient.get("/v1/notifications/sources", headers=OWNER)
    by_id = {s["id"]: s for s in r.json()}
    assert by_id["app:calendar"]["topics"] == [{"id": "reminders", "topic": "app.calendar.reminders", "title": "Reminders"}]
    assert by_id["app:world"]["name"] == "World" and by_id["app:world"]["posts_last_hour"] == 1
    assert not by_id["app:world"]["muted"]


def test_a_built_in_posts_only_its_declared_topics_below_critical_and_only_while_on(nclient, tmp_path):
    svc = nclient.app.state.notify
    svc.topics = topics.TopicRegistry(registry(tmp_path, off={"world"}))
    reg = svc.topics.builtins
    cal = reg.principal("calendar")
    with pytest.raises(PermissionError):
        svc.post(cal, topic="app.world.watch", severity="info", title="not my topic")
    with pytest.raises(PermissionError):
        svc.post(cal, topic="approvals", severity="info", title="a system topic")
    with pytest.raises(PermissionError):  # World is switched off
        svc.post(reg.principal("world"), topic="app.world.watch", severity="info", title="off")
    with pytest.raises(ValueError):
        svc.post(cal, topic="app.calendar.reminders", severity="critical", title="critical is the system's")
    with pytest.raises(ValueError):
        svc.post(cal, topic="app.calendar.reminders", severity="info", title="x", link="https://elsewhere.invalid")
    assert reg.principal("photos") is None  # no descriptor loaded: no principal
    assert not cal.is_owner and not cal.can_request_actions and cal.app_id == "calendar"
    with pytest.raises(ValueError):
        builtins.AppPrincipal(id="app:calendar", kind="agent", role="agent")
    assert inbox(nclient) == []


def test_a_plugin_alert_carries_its_plugin_chip_and_its_asset(nclient, clock):
    gw = nclient.app.state.gateway
    body = {"severity": "warning", "topic": "plugin.hermes", "title": "Door left open", "asset_id": "cam_front-door",
            "group_key": "door", "actions": [{"id": "restart", "label": "Restart", "kind": "request",
                                              "request": {"type": "app.restart", "params": {"app_id": "hermes"}}}]}
    assert nclient.post(SEND, headers=AGENT, json=body).status_code == 202
    assert (inbox(nclient)[0]["source_kind"], inbox(nclient)[0]["app_id"]) == ("agent", None)
    gw.repo.set_app_state("hermes", "installed", clock.now)  # now it is an installed app's agent
    assert nclient.post(SEND, headers=AGENT, json={**body, "title": "Door still open"}).status_code == 202
    item = inbox(nclient)[0]
    assert (item["source_kind"], item["app_id"], item["asset_id"], item["group_key"]) == ("plugin", "hermes", "cam_front-door", "door")
    assert item["actions"][0]["request"] == {"type": "app.restart", "params": {"app_id": "hermes"}}


@pytest.mark.parametrize("change", [
    {"actions": [{"id": "ok", "label": "Approve", "kind": "approve"}]},
    {"actions": [{"id": "x", "label": "Erase", "kind": "request", "request": {"type": "box.erase_everything"}}]},
    {"actions": [{"id": "x", "label": "Open", "kind": "open", "link": "https://elsewhere.invalid/"}]},
    {"actions": [{"id": "x", "label": "Open", "kind": "open", "link": "//elsewhere.invalid/"}]},
    {"actions": [{"id": "a", "label": "A", "kind": "open", "link": "/a"}] * 2},
    {"asset_id": "has a space"},
    {"group_key": "bad key!"},
    {"severity": "critical"},
])
def test_bad_fields_and_any_approve_button_are_refused(nclient, change):
    body = {"severity": "info", "topic": "plugin.hermes", "title": "t", **change}
    assert nclient.post(SEND, headers=AGENT, json=body).status_code == 422
    assert inbox(nclient) == []


def test_a_flooding_source_is_muted_with_one_owner_note(nclient):
    body = {"severity": "info", "topic": "plugin.hermes", "title": "ping"}
    codes = [nclient.post(SEND, headers=AGENT, json=body).status_code for _ in range(topics.FLOOD_POSTS + 5)]
    assert codes.count(202) >= 11 and 429 in codes
    r = nclient.post(SEND, headers=AGENT, json=body)
    assert r.status_code == 202 and r.json()["muted"] is True and r.json()["queued"] == 0
    notes = [n for n in inbox(nclient) if "was muted" in n["title"]]
    assert len(notes) == 1
    assert (notes[0]["source_kind"], notes[0]["topic"], notes[0]["severity"]) == ("system", "apps", "warning")
    [src] = [s for s in nclient.get("/v1/notifications/sources", headers=OWNER).json() if s["id"] == "plugin:hermes"]
    assert src["muted"] and src["muted_reason"] == "flood" and src["muted_by"] is None
    assert src["posts_last_hour"] > topics.FLOOD_POSTS
    assert src["topics"] == [{"id": "hermes", "topic": "plugin.hermes", "title": None}]

    # Only an owner unmutes: the agent cannot lift its own mute, nor can an adult.
    url = "/v1/notifications/sources/plugin:hermes"
    assert nclient.put(url, headers=AGENT, json={"muted": False}).status_code == 403
    assert nclient.put(url, headers=ADULT, json={"muted": False}).status_code == 403
    assert nclient.put("/v1/notifications/sources/system:approvals", headers=OWNER, json={"muted": True}).status_code == 422
    r = nclient.put(url, headers=OWNER, json={"muted": False})
    assert r.status_code == 200 and r.json()["muted"] is False and r.json()["posts_last_hour"] == 0
    assert len([n for n in inbox(nclient) if "was muted" in n["title"]]) == 1


def test_an_owner_mute_silences_a_built_in_but_never_the_system(nclient, tmp_path):
    svc = nclient.app.state.notify
    svc.topics = topics.TopicRegistry(registry(tmp_path))
    r = nclient.put("/v1/notifications/sources/app:calendar", headers=OWNER, json={"muted": True})
    assert r.status_code == 200 and r.json()["muted_reason"] == "owner" and r.json()["muted_by"] == "owner"
    out = svc.post(svc.topics.builtins.principal("calendar"), topic="app.calendar.reminders", severity="info", title="x")
    assert out["muted"] is True and inbox(nclient) == []
    svc.topics = topics.TopicRegistry(nclient.app.state.builtins)  # the gateway's own registry again
    nclient.app.state.events.publish_event("backup", "failed", {"target": "usb", "reason": "disk gone"}, severity="warning")
    [item] = inbox(nclient)
    assert (item["topic"], item["source_kind"], item["app_id"]) == ("backups", "system", "backups")


def test_a_node_event_carries_the_node_kind_and_its_built_in_chip(nclient):
    svc = nclient.app.state.notify
    raw = b'{"type": "update.available", "data": {"version": "1.2.3"}}'
    assert svc.on_node_event("onemind.node.n1.event.update.available", raw)
    [item] = inbox(nclient)
    assert (item["source_kind"], item["app_id"], item["source"]) == ("node", "updates", "node:n1")


def test_preferences_can_route_app_topics():
    doc = routing.validate({"routes": [{"match": {"topic": "app.calendar.*"}, "channels": ["*"]}]})
    assert routing.route_matches(doc["routes"][0]["match"], "app.calendar.reminders", "info")
    with pytest.raises(ValueError):
        routing.validate({"routes": [{"match": {"topic": "app..x"}, "channels": ["*"]}]})


def test_notify_schema_v2_upgrades_an_existing_inbox_table():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE notify_notifications (id VARCHAR(40) PRIMARY KEY, topic VARCHAR(80))")
        conn.exec_driver_sql("INSERT INTO notify_notifications (id, topic) VALUES ('ntf_1', 'apps')")
        _notify_v2(conn)
        _notify_v2(conn)  # idempotent
        cols = {c["name"] for c in inspect(conn).get_columns("notify_notifications")}
        assert {"source_kind", "app_id", "asset_id", "group_key", "actions_json"} <= cols
        assert conn.exec_driver_sql("SELECT source_kind FROM notify_notifications").scalar() == "system"
