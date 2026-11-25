# SPDX-License-Identifier: Apache-2.0
"""Work project management, the task activity log and the quick-add preview (part 2 of the #798 port)."""
from conftest import AGENT, GUEST, OWNER
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
