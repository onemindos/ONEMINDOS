# SPDX-License-Identifier: Apache-2.0
"""Work project management, the task activity log and the quick-add preview (part 2 of the #798 port)."""
from datetime import timedelta

from conftest import ADULT, AGENT, GUEST, OWNER
from onemind_core.auth import Principal
from onemind_core.work.service import ProjectFields, TaskFields


def _project(client, name="Home", **extra):
    made = client.post("/v1/work/projects", json={"name": name, **extra}, headers={**OWNER, "Idempotency-Key": "p-" + name})
    assert made.status_code == 201, made.text
    return made.json()


def test_project_list_get_rename_and_delete_with_its_tasks(client):
    home = _project(client)
    task = client.post("/v1/work/capture", json={"title": "Fix tap", "project_id": home["id"]},
                       headers={**OWNER, "Idempotency-Key": "t1"}).json()
    assert [p["name"] for p in client.get("/v1/work/projects", headers=OWNER).json()] == ["Home"]
    assert client.get(f"/v1/work/projects/{home['id']}", headers=OWNER).json()["name"] == "Home"
    renamed = client.patch(f"/v1/work/projects/{home['id']}", json={"name": "House", "ai_access": "read"}, headers=OWNER)
    assert renamed.status_code == 200 and (renamed.json()["name"], renamed.json()["ai_access"]) == ("House", "read")
    assert client.patch(f"/v1/work/projects/{home['id']}", json={"name": ""}, headers=OWNER).status_code == 422
    assert client.patch(f"/v1/work/projects/{home['id']}", json={"name": "x"}, headers=GUEST).status_code == 403
    assert client.delete(f"/v1/work/projects/{home['id']}", headers=OWNER).status_code == 204
    assert client.get(f"/v1/work/projects/{home['id']}", headers=OWNER).status_code == 404
    assert client.get(f"/v1/work/projects/{home['id']}/tasks/{task['id']}", headers=OWNER).status_code == 404
    assert client.delete(f"/v1/work/projects/{home['id']}", headers=OWNER).status_code == 404


def test_the_inbox_cannot_be_renamed_or_deleted(client):
    inbox = client.post("/v1/work/capture", json={"title": "Loose"}, headers={**OWNER, "Idempotency-Key": "i"}).json()
    path = f"/v1/work/projects/{inbox['project_id']}"
    assert client.patch(path, json={"name": "Mine"}, headers=OWNER).status_code == 409
    assert client.delete(path, headers=OWNER).status_code == 409


def test_only_the_creator_changes_a_project_and_removing_a_member_unassigns_their_tasks(client):
    service = client.app.state.work
    owner, ana = Principal("p-owner", "person", "owner"), Principal("p-ana", "person", "adult")
    project = service.create_project(owner, ProjectFields(name="Team"))
    service.add_member(owner, project.id, ana)
    assigned = service.create_task(owner, project.id, TaskFields(title="Dishes", assignee={"id": ana.id}))
    assert service.members(ana, project.id) == ["p-ana", "p-owner"]
    from onemind_core.errors import ApiError
    import pytest
    for call in (lambda: service.remove_member(ana, project.id, owner.id), lambda: service.delete_project(ana, project.id)):
        with pytest.raises(ApiError) as failure:
            call()
        assert failure.value.status == 403
    with pytest.raises(ApiError) as failure:
        service.remove_member(owner, project.id, owner.id)
    assert failure.value.status == 409
    service.remove_member(owner, project.id, ana.id)
    assert service.get_task(owner, project.id, assigned.id).assignee is None
    with pytest.raises(ApiError):
        service.get_project(ana, project.id)


def test_member_routes_refuse_unknown_people(client):
    home = _project(client)
    assert client.put(f"/v1/work/projects/{home['id']}/members/nobody", headers=OWNER).status_code == 404
    assert client.get(f"/v1/work/projects/{home['id']}/members", headers=OWNER).status_code == 200
    assert client.put(f"/v1/work/projects/{home['id']}/members/nobody", headers=AGENT).status_code == 403
    assert client.get("/v1/work/projects", headers=AGENT).status_code == 403
    assert client.get(f"/v1/work/projects/{home['id']}/members", headers=AGENT).status_code == 403


def test_activity_records_field_names_not_values_and_vanishes_with_the_task(client):
    task = client.post("/v1/work/capture", json={"title": "Secret plan"}, headers={**OWNER, "Idempotency-Key": "a"}).json()
    path = f"/v1/work/projects/{task['project_id']}/tasks/{task['id']}"
    client.patch(path, json={"title": "Renamed", "priority": 1}, headers={**OWNER, "If-Match": "1"})
    client.patch(path, json={"status": "done"}, headers={**OWNER, "If-Match": "2"})
    client.patch(path, json={"status": "todo"}, headers={**OWNER, "If-Match": "3"})
    log = client.get(path + "/activity", headers=OWNER)
    assert log.status_code == 200, log.text
    got = [(row["kind"], row["fields"]) for row in log.json()]
    assert got == [("reopened", []), ("completed", []), ("updated", ["priority", "title"]), ("created", [])]
    assert "Secret plan" not in log.text and "Renamed" not in log.text
    assert client.get(path + "/activity", headers=GUEST).status_code == 403
    client.delete(path, headers={**OWNER, "If-Match": "4"})
    assert client.get(path + "/activity", headers=OWNER).status_code == 404


def test_parse_previews_without_creating_anything(client):
    _project(client)
    seen = client.post("/v1/work/parse", json={"text": "Pay rent tomorrow #home @bills p1", "tz": "UTC"}, headers=OWNER)
    assert seen.status_code == 200, seen.text
    body = seen.json()
    assert (body["title"], body["labels"], body["priority"], body["project_found"]) == ("Pay rent", ["bills"], 1, True)
    assert body["project_id"] is not None and body["due_at"] is not None
    assert client.post("/v1/work/parse", json={"text": "x #nowhere"}, headers=OWNER).json()["project_found"] is False
    assert client.post("/v1/work/parse", json={"text": "#home"}, headers=OWNER).status_code == 422
    assert client.post("/v1/work/parse", json={"text": "x"}, headers=GUEST).status_code == 403
    assert client.get("/v1/work/tasks", headers=OWNER).json() == []


def test_comments_replay_by_key_belong_to_their_author_and_follow_task_visibility(client):
    task = client.post("/v1/work/capture", json={"title": "Plan"}, headers={**OWNER, "Idempotency-Key": "c0"}).json()
    base = f"/v1/work/projects/{task['project_id']}/tasks/{task['id']}/comments"
    key = {**OWNER, "Idempotency-Key": "c1"}
    first = client.post(base, json={"body": "Call the plumber"}, headers=key)
    assert first.status_code == 201, first.text
    assert client.post(base, json={"body": "Call the plumber"}, headers=key).json()["id"] == first.json()["id"]
    assert client.post(base, json={"body": "Different"}, headers=key).status_code == 409
    assert client.post(base, json={"body": ""}, headers={**OWNER, "Idempotency-Key": "c2"}).status_code == 422
    assert [c["body"] for c in client.get(base, headers=OWNER).json()] == ["Call the plumber"]
    assert client.get(base, headers=AGENT).status_code == 403
    assert client.delete(f"{base}/missing", headers=OWNER).status_code == 404
    assert client.delete(f"{base}/{first.json()['id']}", headers=OWNER).status_code == 204
    assert client.get(base, headers=OWNER).json() == []


def test_sections_group_tasks_and_deleting_one_keeps_its_tasks(client):
    home = _project(client)
    sections = f"/v1/work/projects/{home['id']}/sections"
    made = client.post(sections, json={"name": "This week"}, headers={**OWNER, "Idempotency-Key": "s1"})
    assert made.status_code == 201, made.text
    assert client.post(sections, json={"name": "This week"}, headers={**OWNER, "Idempotency-Key": "s1"}).json() == made.json()
    later = client.post(sections, json={"name": "Later"}, headers={**OWNER, "Idempotency-Key": "s2"}).json()
    assert [(s["name"], s["position"]) for s in client.get(sections, headers=OWNER).json()] == [("This week", 0), ("Later", 1)]
    task = client.post("/v1/work/capture", json={"title": "Fix tap", "project_id": home["id"], "section_id": later["id"]},
                       headers={**OWNER, "Idempotency-Key": "t"}).json()
    assert task["section_id"] == later["id"]
    other = _project(client, "Work")
    foreign = client.post("/v1/work/capture", json={"title": "x", "project_id": other["id"], "section_id": later["id"]},
                          headers={**OWNER, "Idempotency-Key": "t2"})
    assert foreign.status_code == 422
    assert client.patch(f"{sections}/{later['id']}", json={"name": "Someday"}, headers=OWNER).json()["name"] == "Someday"
    assert client.delete(f"{sections}/{later['id']}", headers=OWNER).status_code == 204
    after = client.get(f"/v1/work/projects/{home['id']}/tasks/{task['id']}", headers=OWNER).json()
    assert after["section_id"] is None
    assert client.delete(f"{sections}/{later['id']}", headers=OWNER).status_code == 404


def test_completing_a_repeating_task_moves_it_to_the_next_occurrence(client, clock):
    body = {"title": "Water plants", "due_at": "2026-11-25T09:00:00Z", "repeat": {"every": "week"}}
    task = client.post("/v1/work/capture", json=body, headers={**OWNER, "Idempotency-Key": "r1"}).json()
    path = f"/v1/work/projects/{task['project_id']}/tasks/{task['id']}"
    done = client.patch(path, json={"status": "done"}, headers={**OWNER, "If-Match": "1"})
    assert done.status_code == 200, done.text
    got = done.json()
    assert got["status"] == "todo" and got["due_at"].startswith("2026-12-02T09:00:00") and got["repeat"] == {
        "every": "week", "interval": 1}
    log = client.get(path + "/activity", headers=OWNER).json()
    assert [row["kind"] for row in log] == ["completed", "created"] and log[0]["fields"] == ["due_at"]
    stop = client.patch(path, json={"repeat": None}, headers={**OWNER, "If-Match": "2"})
    assert stop.status_code == 200 and stop.json()["repeat"] is None


def test_quick_add_reads_repeat_rules():
    from datetime import UTC, datetime
    from onemind_core.work.parse import next_due, parse_quick_add
    now = datetime(2026, 11, 25, 15, 0, tzinfo=UTC)
    got = parse_quick_add("Water plants every 2 weeks #Home", now)
    assert got["repeat"] == {"every": "week", "interval": 2} and got["title"] == "Water plants"
    assert got["due_at"].date().isoformat() == "2026-11-25"
    assert parse_quick_add("Standup every weekday", now)["repeat"] == {"every": "weekday", "interval": 1}
    friday = datetime(2026, 11, 27, 9, 0, tzinfo=UTC)
    assert next_due(friday, {"every": "weekday", "interval": 1}, now).date().isoformat() == "2026-11-30"
    jan31 = datetime(2027, 1, 31, 9, 0, tzinfo=UTC)
    assert next_due(jan31, {"every": "month", "interval": 1}, now).date().isoformat() == "2027-02-28"
    assert next_due(datetime(2026, 1, 1, 9, 0, tzinfo=UTC), {"every": "day", "interval": 1}, now).date().isoformat() == "2026-11-26"


def _shared_project(client):
    home = _project(client, "Shared")
    client.app.state.work.add_member(Principal("owner", "person", "owner"), home["id"], Principal("adult", "person", "adult"))
    return home["id"]


def test_sweep_reminds_the_assignee_once_per_due_date(client, clock):
    due = (clock() + timedelta(hours=3)).isoformat().replace("+00:00", "Z")
    body = {"title": "Pay the bill", "assignee": {"id": "adult"}, "due_at": due, "project_id": _shared_project(client)}
    task = client.post("/v1/work/capture", json=body, headers={**OWNER, "Idempotency-Key": "w1"}).json()
    client.post("/v1/work/capture", json={"title": "No owner of this", "due_at": due},
                headers={**OWNER, "Idempotency-Key": "w2"})
    work = client.app.state.work
    first = work.sweep()
    assert [(n, who, t) for n, who, _, t, _ in first] == [("task.due_soon", "adult", task["id"])]
    assert work.sweep() == []
    clock.advance(4 * 3600)
    assert [n for n, *_ in work.sweep()] == ["task.overdue"]
    assert work.sweep() == []
    path = f"/v1/work/projects/{task['project_id']}/tasks/{task['id']}"
    client.patch(path, json={"status": "done"}, headers={**OWNER, "If-Match": "1"})
    clock.advance(86400)
    assert work.sweep() == []


def test_assigning_a_task_tells_only_the_assignee_with_the_title_added_at_render_time(client):
    body = {"title": "Mow the lawn", "assignee": {"id": "adult"}, "project_id": _shared_project(client)}
    task = client.post("/v1/work/capture", json=body, headers={**OWNER, "Idempotency-Key": "n1"}).json()
    assert task["assignee"]["id"] == "adult"
    items = client.get("/v1/notifications", headers=ADULT).json()
    assert [i["title"] for i in items] == ["Assigned to you: Mow the lawn"]
    assert client.get("/v1/notifications", headers=OWNER).json() == []
    audit = client.app.state.gateway.settings.audit_path.read_text()
    assert "Mow the lawn" not in audit
