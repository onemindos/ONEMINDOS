# SPDX-License-Identifier: Apache-2.0
"""Mounted Work authorization and idempotent capture."""
import json

import pytest

from conftest import AGENT, GUEST, OWNER
from onemind_core.auth import Principal
from onemind_core.errors import ApiError
from onemind_core.eventstream import events_for_record
from onemind_core.work.service import ProjectFields, TaskFields
from onemind_core.identity.crypto import totp_code
from test_appstore import request
from test_identity import PASSWORD, at_box, csrf, idc, setup_owner  # noqa: F401 (pytest fixture)
from test_identity_signin import enable_totp
from test_mcp import H, rpc


def run_signed(c, clock, secret, type_, params) -> dict:
    """Request and approve from the owner's session. D-034: once the household has an account, an approval
    needs a fresh proof, here the password and an authenticator code."""
    headers = csrf(c)
    filed = request(c, clock, type_, params, headers=headers)
    assert filed.status_code == 201, filed.text
    approve = f"/v1/actions/{filed.json()['id']}/approve"
    opts = c.post(approve + "-options", headers=headers, json={"method": "password+totp", "at_box": True})
    assert opts.status_code == 200, opts.text
    proof = {"challenge": opts.json()["challenge"], "password": PASSWORD,
             "totp": totp_code(secret, int(clock.now.timestamp()) // 30)}
    done = c.post(approve, headers=headers, json={"password_totp": proof, **at_box(c, opts.json())})
    assert done.status_code == 200, done.text
    clock.advance(30)  # each authenticator code is accepted once
    return done.json()


def test_capture_replays_and_partial_update_uses_task_revision(client):
    headers = {**OWNER, "Idempotency-Key": "capture-test"}
    original = {"title": "Inspect backup", "body": "Private notes"}
    first = client.post("/v1/work/capture", json=original, headers=headers)
    assert first.status_code == 201, first.text
    task = first.json()
    path = f"/v1/work/projects/{task['project_id']}/tasks/{task['id']}"
    replay = client.post("/v1/work/capture", json=original, headers=headers)
    assert replay.status_code == 200 and replay.json()["id"] == task["id"]
    assert client.post("/v1/work/capture", json={"title": "Different task"}, headers=headers).status_code == 409
    assert client.get("/v1/work/tasks", headers=GUEST).status_code == 403
    assert client.post("/v1/work/capture", json=original, headers={**headers, **AGENT}).status_code == 403
    update = client.patch(path, json={"status": "done"}, headers={**OWNER, "If-Match": '"1"'})
    assert update.status_code == 200, update.text
    assert (update.json()["title"], update.json()["body"], update.json()["revision"]) == (
        original["title"], original["body"], 2,
    )
    assert client.patch(path, json={"status": "todo"}, headers={**OWNER, "If-Match": "1"}).status_code == 409
    assert client.delete(path, headers={**OWNER, "If-Match": "2"}).status_code == 204
    assert client.get(path, headers=OWNER).status_code == 404

    audit_path = client.app.state.gateway.settings.audit_path
    facts = [json.loads(line) for line in audit_path.read_text().splitlines()]
    events = [record for record in facts if record["event"].startswith("work.task_")]
    assert [record["event"] for record in events] == ["work.task_created", "work.task_completed", "work.task_deleted"]
    for record in events:
        ids = {"task_id": task["id"], "project_id": task["project_id"]}
        assert record["data"]["payload"] == ids
        assert events_for_record(record)[0]["data"] == ids


@pytest.mark.parametrize("role", ["child", "teen"])
def test_child_or_teen_cannot_list_edit_or_borrow_non_owned_task(client, role):
    service = client.app.state.work
    owner = Principal("work-owner", "person", "owner")
    child = Principal("work-child", "person", role)
    project = service.create_project(owner, ProjectFields(name="Family"))
    service.add_member(owner, project.id, child)
    other = service.create_task(owner, project.id, TaskFields(title="Owner's task", assignee={"id": child.id}))
    own = service.create_task(child, project.id, TaskFields(title="Child's task"))
    assert [task.id for task in service.list_tasks(child, project.id)] == [own.id]
    for operation in (
        lambda: service.get_task(child, project.id, other.id),
        lambda: service.replace_task(child, project.id, other.id, expected_revision=1, fields=TaskFields(title="Changed")),
        lambda: service.delete_task(child, project.id, other.id, 1),
        lambda: service.replace_task(child, project.id, own.id, expected_revision=1,
                                     fields=TaskFields(title="Child's task"), dependencies=[other.id]),
    ):
        with pytest.raises(ApiError) as failure:
            operation()
        assert failure.value.status == 404


def test_scoped_agent_reads_only_its_owners_opted_in_tasks_and_mcp_taints(idc, clock):
    setup_owner(idc)
    headers = csrf(idc)
    for key, level in (("shared", "read"), ("private", "none")):
        project = idc.post("/v1/work/projects", json={"name": key, "ai_access": level},
                           headers={**headers, "Idempotency-Key": key})
        assert project.status_code == 201, project.text
        saved = idc.post("/v1/work/capture", json={"title": key, "project_id": project.json()["id"]},
                         headers={**headers, "Idempotency-Key": key})
        assert saved.status_code == 201, saved.text
    token = idc.post("/v1/tokens", headers=headers, json={
        "name": "work reader", "principal": {"kind": "agent", "id": "agent:work-reader"}, "scopes": ["work:read"],
    })
    assert token.status_code == 201, token.text
    bearer = {"Authorization": "Bearer " + token.json()["one_time"]["token"]}
    rows = idc.get("/v1/work/tasks", headers=bearer)
    assert rows.status_code == 200, rows.text
    assert [task["title"] for task in rows.json()] == ["shared"]
    assert idc.post("/v1/work/capture", json={"title": "No"}, headers={**bearer, "Idempotency-Key": "write"}).status_code == 403
    reply = rpc(idc, "tools/call", {"name": "work_tasks_list", "arguments": {}}, headers={**H, **bearer})
    assert "result" in reply.json(), reply.text
    data = reply.json()["result"]
    assert [task["title"] for task in data["structuredContent"]["tasks"]] == ["shared"]
    assert data.get("_meta")
    catalogue = rpc(idc, "tools/list", headers={**H, **bearer}).json()["result"]["tools"]
    assert {tool["name"] for tool in catalogue} == {"get_instance", "work_tasks_list", "work_task_get"}
    request = rpc(idc, "tools/call", {"name": "request_action", "arguments": {}}, headers={**H, **bearer})
    assert request.json()["result"]["isError"]

    secret = enable_totp(idc, clock)
    assert run_signed(idc, clock, secret, "app.disable", {"app_id": "work"})["state"] == "succeeded"
    off = rpc(idc, "tools/list", headers={**H, **bearer}).json()["result"]["tools"]
    assert {tool["name"] for tool in off} == {"get_instance"}
    for name, arguments in (("work_tasks_list", {}), ("work_task_get", {"project_id": "shared", "task_id": "task"})):
        reply = rpc(idc, "tools/call", {"name": name, "arguments": arguments}, headers={**H, **bearer})
        assert reply.json()["result"]["structuredContent"]["error"] == "app_disabled"
    assert run_signed(idc, clock, secret, "app.enable", {"app_id": "work"})["state"] == "succeeded"
    assert rpc(idc, "tools/list", headers={**H, **bearer}).json()["result"]["tools"] == catalogue
