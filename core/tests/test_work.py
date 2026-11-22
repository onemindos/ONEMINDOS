# SPDX-License-Identifier: Apache-2.0
"""The work engine (routes under /v1/work): projects, tasks, quick add, events and who may see what.

Runs on SQLite, and on PostgreSQL with ONEMIND_TEST_DB_URL. Static test principals: owner and
adult (people), guest, and hermes (an AI agent).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from onemind_core.work import parse

from conftest import ADULT, AGENT, GUEST, OWNER

W = "/v1/work"


def audit_lines(settings) -> list[dict]:
    return [json.loads(x) for x in settings.audit_path.read_text().splitlines()]


def project(c, name="Home", ai="none", who=OWNER, members=()):
    r = c.post(f"{W}/projects", json={"name": name, "ai_access": ai}, headers=who)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    for mid, kind in members:
        r = c.post(f"{W}/projects/{pid}/members", json={"id": mid, "kind": kind}, headers=who)
        assert r.status_code == 200, r.text
    return pid


def task(c, pid=None, who=OWNER, **kw):
    r = c.post(f"{W}/tasks", json={"title": "Do it", **({"project_id": pid} if pid else {}), **kw}, headers=who)
    assert r.status_code == 201, r.text
    return r.json()


def patch(c, tid, rev, who=OWNER, **kw):
    return c.patch(f"{W}/tasks/{tid}", json=kw, headers={**who, "If-Match": f'"{rev}"'})


# ---- the acceptance tests -----------------------------------------------------------------------
def test_stale_revision_is_409_and_nothing_changes(client):
    pid = project(client)
    t = task(client, pid)
    ok = patch(client, t["id"], t["revision"], title="First")
    assert ok.status_code == 200 and ok.json()["revision"] == t["revision"] + 1
    stale = patch(client, t["id"], t["revision"], title="Second")
    assert stale.status_code == 409 and stale.json()["error"] == "stale_precondition"
    assert client.get(f"{W}/tasks/{t['id']}", headers=OWNER).json()["title"] == "First"
    assert client.patch(f"{W}/tasks/{t['id']}", json={"title": "x"}, headers=OWNER).status_code == 428


def test_two_writers_with_the_same_revision_are_serialised(client, monkeypatch):
    """update_task takes the row lock (FOR UPDATE on PostgreSQL) before it compares the revision."""
    from sqlalchemy.orm import Session
    seen = []
    real = Session.get

    def spy(self, entity, ident, *a, **kw):
        if getattr(entity, "__tablename__", "").startswith("work_task") or entity.__name__ == "TaskRow":
            seen.append(kw.get("with_for_update"))
        return real(self, entity, ident, *a, **kw)

    pid = project(client)
    t = task(client, pid)
    monkeypatch.setattr(Session, "get", spy)
    assert patch(client, t["id"], 1, priority=2).status_code == 200
    assert patch(client, t["id"], 1, priority=3).status_code == 409
    assert seen and seen[0] is True


def test_dependency_cycles_are_refused(client):
    pid = project(client)
    a, b, c = (task(client, pid, title=x) for x in "abc")
    for x, y in ((a, b), (b, c)):
        r = client.post(f"{W}/tasks/{x['id']}/dependencies", json={"depends_on": y["id"]}, headers=OWNER)
        assert r.status_code == 200, r.text
    assert client.post(f"{W}/tasks/{c['id']}/dependencies", json={"depends_on": a["id"]}, headers=OWNER).status_code == 409
    assert client.post(f"{W}/tasks/{a['id']}/dependencies", json={"depends_on": a['id']}, headers=OWNER).status_code == 409
    # a task that waits on an open task cannot be completed; finishing the blocker frees it
    assert client.post(f"{W}/tasks/{a['id']}/complete", headers=OWNER).status_code == 409
    assert client.post(f"{W}/tasks/{c['id']}/complete", headers=OWNER).status_code == 200
    assert client.post(f"{W}/tasks/{b['id']}/complete", headers=OWNER).status_code == 200
    assert client.post(f"{W}/tasks/{a['id']}/complete", headers=OWNER).json()["status"] == "done"


def test_a_non_member_gets_404_and_a_guest_403(client):
    pid = project(client)
    t = task(client, pid)
    for method, path, body in (("get", f"/projects/{pid}", None), ("get", f"/tasks/{t['id']}", None),
                               ("get", f"/tasks/{t['id']}/comments", None), ("post", f"/tasks/{t['id']}/comments", {"body": "hi"}),
                               ("patch", f"/projects/{pid}", {"name": "x"}), ("delete", f"/tasks/{t['id']}", None)):
        r = getattr(client, method)(W + path, headers={**ADULT, "If-Match": '"1"'}, **({"json": body} if body else {}))
        assert r.status_code == 404, (method, path, r.status_code)
    assert client.get(f"{W}/projects", headers=ADULT).json()["items"] == []
    assert client.post(f"{W}/tasks", json={"title": "x", "project_id": pid}, headers=ADULT).status_code == 404
    assert client.get(f"{W}/tasks", headers=ADULT).json()["items"] == []
    assert client.get(f"{W}/tasks?project_id={pid}", headers=ADULT).status_code == 404
    for path in ("/projects", "/tasks", "/today", "/inbox"):
        assert client.get(W + path, headers=GUEST).status_code == 403
    # once added, the adult sees it
    client.post(f"{W}/projects/{pid}/members", json={"id": "adult", "kind": "person"}, headers=OWNER)
    assert client.get(f"{W}/tasks/{t['id']}", headers=ADULT).status_code == 200
    assert client.delete(f"{W}/projects/{pid}", headers=ADULT).status_code == 403  # a member, not an owner


def test_capture_with_an_idempotency_key_makes_one_task(client):
    pid = project(client, "Home")
    h = {**OWNER, "Idempotency-Key": "phone-1"}
    first = client.post(f"{W}/capture", json={"text": "Pay rent tomorrow #Home @bills p1"}, headers=h)
    again = client.post(f"{W}/capture", json={"text": "Pay rent tomorrow #Home @bills p1"}, headers=h)
    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["id"] == again.json()["id"]
    t = first.json()
    assert (t["title"], t["priority"], t["labels"], t["project_id"], t["due_all_day"]) == ("Pay rent", 1, ["bills"], pid, True)
    assert len(client.get(f"{W}/tasks", headers=OWNER).json()["items"]) == 1
    other = client.post(f"{W}/capture", json={"text": "Something else"}, headers=h)
    assert other.status_code == 409
    # no key: every call makes a task; no #project: it lands in the Inbox
    client.post(f"{W}/capture", json={"text": "Buy milk"}, headers=OWNER)
    client.post(f"{W}/capture", json={"text": "Buy milk"}, headers=OWNER)
    assert len(client.get(f"{W}/inbox", headers=OWNER).json()["items"]) == 2
    assert client.post(f"{W}/capture", json={"text": "x #Nowhere"}, headers=OWNER).status_code == 404


def test_every_write_leaves_an_event_an_audit_row_and_activity(client, settings):
    pid = project(client, members=[("adult", "person")])
    t = task(client, pid, assignee={"kind": "person", "id": "adult"})
    patch(client, t["id"], 1, title="Renamed", priority=2)
    client.post(f"{W}/tasks/{t['id']}/comments", json={"body": "secret words"}, headers=OWNER)
    client.post(f"{W}/tasks/{t['id']}/complete", headers=OWNER)
    client.delete(f"{W}/tasks/{t['id']}", headers=OWNER)
    rows = [r for r in audit_lines(settings) if r["event"].startswith("work.")]
    names = [r["event"] for r in rows]
    for want in ("work.project.created", "work.project.member_added", "work.task.created", "work.task.assigned",
                 "work.task.updated", "work.task.commented", "work.task.completed", "work.task.deleted"):
        assert want in names, names
    assert all(r["principal"]["kind"] == "person" and r["principal"]["id"] == "owner" for r in rows)
    text = json.dumps(rows)
    assert "secret words" not in text and "Renamed" not in text  # ids and field names, never what people typed
    updated = next(r for r in rows if r["event"] == "work.task.updated")
    assert updated["data"]["payload"]["changed"] == ["priority", "title"]


def test_activity_lists_what_happened(client):
    pid = project(client)
    t = task(client, pid)
    patch(client, t["id"], 1, priority=1)
    kinds = [a["kind"] for a in client.get(f"{W}/tasks/{t['id']}/activity", headers=OWNER).json()["items"]]
    assert kinds == ["created", "updated"]


# ---- AI agents ----------------------------------------------------------------------------------
def test_an_agent_sees_only_what_ai_access_lets_it(client):
    pid = project(client, ai="none")
    t = task(client, pid)
    assert client.post(f"{W}/projects/{pid}/members", json={"id": "hermes", "kind": "agent"}, headers=OWNER).status_code == 409
    client.patch(f"{W}/projects/{pid}", json={"ai_access": "read"}, headers={**OWNER, "If-Match": '"1"'})
    client.post(f"{W}/projects/{pid}/members", json={"id": "hermes", "kind": "agent"}, headers=OWNER)
    # read: it can look, not change
    assert client.get(f"{W}/tasks/{t['id']}", headers=AGENT).status_code == 200
    assert client.post(f"{W}/tasks", json={"title": "x", "project_id": pid}, headers=AGENT).status_code == 403
    assert patch(client, t["id"], 1, who=AGENT, title="x").status_code == 403
    assert client.post(f"{W}/tasks/{t['id']}/comments", json={"body": "hi"}, headers=AGENT).status_code == 403
    # work: it can add and change
    client.patch(f"{W}/projects/{pid}", json={"ai_access": "work"}, headers={**OWNER, "If-Match": '"2"'})
    mine = task(client, pid, who=AGENT, title="From the agent")
    assert mine["created_by_kind"] == "agent"
    assert patch(client, mine["id"], 1, who=AGENT, status="doing").status_code == 200
    assert client.post(f"{W}/tasks/{mine['id']}/comments", json={"body": "done soon"}, headers=AGENT).status_code == 201
    # back to none: gone
    client.patch(f"{W}/projects/{pid}", json={"ai_access": "none"}, headers={**OWNER, "If-Match": '"3"'})
    assert client.get(f"{W}/tasks/{t['id']}", headers=AGENT).status_code == 404
    assert client.get(f"{W}/projects", headers=AGENT).json()["items"] == []


def test_an_agent_never_creates_projects_or_deletes_or_decides_access(client):
    pid = project(client, ai="work", members=[("hermes", "agent")])
    t = task(client, pid)
    assert client.post(f"{W}/projects", json={"name": "Mine"}, headers=AGENT).status_code == 403
    assert client.delete(f"{W}/tasks/{t['id']}", headers=AGENT).status_code == 403
    assert client.delete(f"{W}/projects/{pid}", headers=AGENT).status_code == 403
    assert client.patch(f"{W}/projects/{pid}", json={"ai_access": "work"}, headers={**AGENT, "If-Match": '"1"'}).status_code == 403
    assert client.post(f"{W}/projects/{pid}/members", json={"id": "x", "kind": "agent"}, headers=AGENT).status_code == 403
    assert client.post(f"{W}/tasks", json={"title": "no project"}, headers=AGENT).status_code == 422  # the Inbox is people's
    assert client.get(f"{W}/tasks/{t['id']}", headers=OWNER).status_code == 200  # nothing was removed


def test_agents_and_machines_are_assigned_only_where_ai_works(client, settings):
    none = project(client, "Quiet", ai="none")
    ro = project(client, "Reading", ai="read", members=[("hermes", "agent")])
    work = project(client, "Busy", ai="work", members=[("hermes", "agent")])
    for pid in (none, ro):
        for who in ({"kind": "agent", "id": "hermes"}, {"kind": "machine", "id": "lab-1"}):
            r = client.post(f"{W}/tasks", json={"title": "x", "project_id": pid, "assignee": who}, headers=OWNER)
            assert r.status_code == 409 and r.json()["error"] == "policy_refused", (pid, who, r.text)
    inbox = client.post(f"{W}/tasks", json={"title": "x", "assignee": {"kind": "machine", "id": "lab-1"}}, headers=OWNER)
    assert inbox.status_code == 409
    a = task(client, work, assignee={"kind": "agent", "id": "hermes"})
    m = task(client, work, assignee={"kind": "machine", "id": "lab-1"})
    # an unknown agent is not a member
    assert client.post(f"{W}/tasks", json={"title": "x", "project_id": work, "assignee": {"kind": "agent", "id": "ghost"}}, headers=OWNER).status_code == 422
    # lowering ai_access takes the AI off its tasks
    r = client.patch(f"{W}/projects/{work}", json={"ai_access": "read"}, headers={**OWNER, "If-Match": '"1"'})
    assert r.status_code == 200
    for t in (a, m):
        assert client.get(f"{W}/tasks/{t['id']}", headers=OWNER).json()["assignee"] is None


def test_a_task_cannot_carry_anything_that_acts_outside_the_work_tables(client):
    pid = project(client)
    bad = [
        {"webhook": "https://example.invalid/hook"}, {"run": "reboot"}, {"action": {"type": "app.install"}},
        {"fields": {"url": ["a"]}}, {"fields": {"Bad Key": "x"}}, {"fields": {"k": {"nested": 1}}},
        {"fields": {"k": "x" * 201}}, {"asset_ref": "https://example.invalid/x"}, {"asset_ref": "files:../etc/passwd"},
        {"asset_ref": "file:///etc/passwd"}, {"labels": ["has space"]}, {"rrule": "FREQ=SECONDLY"},
        {"rrule": "FREQ=DAILY;COUNT=3"}, {"rrule": "FREQ=DAILY"},  # a repeat needs a due date
    ]
    for extra in bad:
        r = client.post(f"{W}/tasks", json={"title": "x", "project_id": pid, **extra}, headers=OWNER)
        assert r.status_code == 422, (extra, r.status_code, r.text)
    ok = task(client, pid, asset_ref="files:docs/plan.pdf", fields={"effort": 3, "billable": True, "client": "Acme"})
    assert ok["asset_ref"] == "files:docs/plan.pdf" and ok["fields"]["effort"] == 3
    assert client.patch(f"{W}/tasks/{ok['id']}", json={"callback": "x"}, headers={**OWNER, "If-Match": '"1"'}).status_code == 422


# ---- quick add, recurrence, views -------------------------------------------------------------------
NOW = datetime(2026, 11, 11, 22, 0, tzinfo=UTC)  # a Wednesday


def test_quick_add_tokens():
    p = parse.parse_quick_add("Call dad every monday at 5pm #Family /Evening @phone @love p2 +ana", NOW)
    assert (p["title"], p["project"], p["section"], p["labels"], p["priority"], p["assignee"]) == (
        "Call dad", "Family", "Evening", ["phone", "love"], 2, "ana")
    assert p["rrule"] == "FREQ=WEEKLY;INTERVAL=1;BYDAY=MO"
    assert p["due_at"] == datetime(2026, 11, 16, 17, 0, tzinfo=UTC) and not p["due_all_day"]
    assert parse.parse_quick_add("x in 3 days", NOW)["due_at"] == datetime(2026, 11, 14, 23, 59, 59, tzinfo=UTC)
    assert parse.parse_quick_add("x next friday", NOW)["due_at"].date().isoformat() == "2026-11-13"
    assert parse.parse_quick_add("x 2026-12-01 17:30", NOW)["due_at"] == datetime(2026, 12, 1, 17, 30, tzinfo=UTC)
    assert parse.parse_quick_add("x every 2 weeks", NOW)["rrule"] == "FREQ=WEEKLY;INTERVAL=2"
    assert parse.parse_quick_add("x every weekday", NOW)["rrule"].endswith("BYDAY=MO,TU,WE,TH,FR")
    plain = parse.parse_quick_add("Buy 2 apples", NOW)
    assert plain["title"] == "Buy 2 apples" and plain["due_at"] is None
    # "today" is the caller's today: 22:00 UTC is already Thursday in Tokyo
    assert parse.parse_quick_add("x today", NOW, "Asia/Tokyo")["due_at"] == datetime(2026, 11, 12, 14, 59, 59, tzinfo=UTC)
    for bad in ("", "#Home @x p1", "x 2026-13-45", "x at 13pm"):
        with pytest.raises(ValueError):
            parse.parse_quick_add(bad, NOW)
    with pytest.raises(ValueError):
        parse.parse_quick_add("x", NOW, "Not/AZone")


def test_parse_previews_without_creating(client):
    pid = project(client, "Home")
    r = client.post(f"{W}/parse", json={"text": "Mow lawn saturday #Home p3"}, headers=OWNER)
    assert r.status_code == 200 and r.json()["project_id"] == pid and r.json()["priority"] == 3
    assert client.get(f"{W}/tasks", headers=OWNER).json()["items"] == []


def test_a_repeating_task_moves_to_its_next_date_when_done(client, clock):
    pid = project(client)
    due = (clock.now + timedelta(hours=2)).isoformat()
    t = task(client, pid, due_at=due, rrule="FREQ=DAILY;INTERVAL=1")
    done = client.post(f"{W}/tasks/{t['id']}/complete", headers=OWNER).json()
    assert done["status"] == "todo" and done["completed_at"]
    assert datetime.fromisoformat(done["due_at"].replace("Z", "+00:00")) == datetime.fromisoformat(due) + timedelta(days=1)
    assert parse.next_due("FREQ=MONTHLY;INTERVAL=1", datetime(2026, 1, 31, 9, tzinfo=UTC)).date().isoformat() == "2026-02-28"


def test_today_upcoming_and_inbox(client, clock):
    pid = project(client, members=[("adult", "person")])
    soon = (clock.now + timedelta(hours=1)).isoformat()
    late = (clock.now - timedelta(days=2)).isoformat()
    week = (clock.now + timedelta(days=3)).isoformat()
    due_today = task(client, pid, title="today", due_at=soon, assignee={"kind": "person", "id": "owner"})
    old = task(client, pid, title="old", due_at=late)  # unassigned: its creator's
    task(client, pid, title="later", due_at=week)
    task(client, pid, title="theirs", due_at=soon, assignee={"kind": "person", "id": "adult"})
    task(client, pid, title="undated")
    got = client.get(f"{W}/today", headers=OWNER).json()
    assert [t["id"] for t in got["today"]] == [due_today["id"]] and [t["id"] for t in got["overdue"]] == [old["id"]]
    assert [t["title"] for t in client.get(f"{W}/upcoming", headers=OWNER).json()["items"]] == ["later"]
    assert [t["title"] for t in client.get(f"{W}/today", headers=ADULT).json()["today"]] == ["theirs"]
    client.post(f"{W}/tasks/{old['id']}/complete", headers=OWNER)
    assert client.get(f"{W}/today", headers=OWNER).json()["overdue"] == []
    task(client, title="inbox one")
    assert [t["title"] for t in client.get(f"{W}/inbox", headers=OWNER).json()["items"]] == ["inbox one"]
    assert client.get(f"{W}/inbox", headers=ADULT).json()["items"] == []  # the Inbox is private
    assert client.get(f"{W}/inbox", headers=AGENT).json()["items"] == []
    assert client.get(f"{W}/today?tz=Not/AZone", headers=OWNER).status_code == 422


# ---- notifications ----------------------------------------------------------------------------------
def titles(c, who) -> list[str]:
    body = c.get("/v1/notifications", headers=who).json()
    items = body["items"] if isinstance(body, dict) else body
    return [i["title"] for i in items]


def test_assigned_due_soon_and_overdue_reach_only_the_assignee(client, clock):
    pid = project(client, members=[("adult", "person")])
    t = task(client, pid, title="Fix the gate", assignee={"kind": "person", "id": "adult"})
    assert "Assigned to you: Fix the gate" in titles(client, ADULT)
    assert not any("Fix the gate" in x for x in titles(client, OWNER))
    mine = task(client, pid, title="Self task", assignee={"kind": "person", "id": "owner"})
    assert not any("Self task" in x for x in titles(client, OWNER))  # you are not told about your own doing
    due = (clock.now + timedelta(hours=5)).isoformat()
    assert patch(client, t["id"], 1, due_at=due).status_code == 200
    svc = client.app.state.work
    assert svc.sweep() == 1 and svc.sweep() == 0  # once per due date
    assert "Due soon: Fix the gate" in titles(client, ADULT)
    clock.advance(6 * 3600)
    assert svc.sweep() == 1
    assert "Overdue: Fix the gate" in titles(client, ADULT)
    assert not any("Fix the gate" in x for x in titles(client, OWNER)) and mine


def test_titles_never_reach_the_household_audit_log(client, clock):
    """An adult who is not a member can read every audit line; assigned and due-soon lines carry ids only."""
    pid = project(client)  # the adult is not a member
    t = task(client, pid, title="See lawyer", assignee={"kind": "person", "id": "owner"}, due_at=(clock.now + timedelta(hours=5)).isoformat())
    assert client.get(f"{W}/tasks/{t['id']}", headers=ADULT).status_code == 404
    assert client.app.state.work.sweep() == 1
    clock.advance(6 * 3600)
    assert client.app.state.work.sweep() == 1
    r = client.get("/v1/audit/events?event=work.*&limit=200", headers=ADULT)
    assert r.status_code == 200, r.text
    assert "work.task.due_soon" in r.text and "work.task.overdue" in r.text
    assert "See lawyer" not in r.text
    assert "Overdue: See lawyer" in titles(client, OWNER)  # the assignee still reads the title in their inbox
