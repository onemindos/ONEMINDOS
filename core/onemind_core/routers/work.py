# SPDX-License-Identifier: Apache-2.0
"""The Work gateway. Task edits stay inside Work and never run actions."""
from typing import Annotated, Literal
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Header, Query, Request, Response
from pydantic import AwareDatetime, ConfigDict, Field, ValidationError

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity import ctx_of
from ..identity.scopes import has_any, register_route_scope
from ..jsonbody import JsonBody
from ..work.access import WORK_ROLES, delegated_reader
from ..work.parse import parse_quick_add
from ..work.service import (CaptureFields, Label, Name, PersonAssignee, Project, ProjectFields, StoredTaskFields, Task,
                            TaskFields, TaskView, WorkService)

ORDER = 260
BASE = "/v1/work"
TASK = BASE + "/projects/{project_id}/tasks/{task_id}"
register_route_scope("GET,HEAD", r"/v1/work(/.*)?", ("work:read",))
register_route_scope("POST,PATCH,DELETE", r"/v1/work(/.*)?", ("work:write",))

IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)]
# The task revision (1 or more), quoted as an ETag or bare: the schema says so, so anything else being the
# handler's 422 bad_revision is documented rather than a surprise (_revision below is the same rule).
REVISION_RE = r'^("0*[1-9][0-9]*"|0*[1-9][0-9]*)$'
RevisionHeader = Annotated[str, Header(alias="If-Match", min_length=1, max_length=12,
                                       json_schema_extra={"pattern": REVISION_RE})]


class ProjectBody(ProjectFields, JsonBody):
    pass


class CaptureBody(CaptureFields, JsonBody):
    pass


class QuickAddBody(JsonBody):
    """One line such as `Pay rent tomorrow at 5pm #Home @bills p1`; see work/parse.py."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=400)
    tz: str | None = Field(default=None, max_length=64)


def _no_default(schema: dict) -> None:
    """A left-out field means "keep it": its Python default None is not a value the schema offers."""
    schema.pop("default", None)


class ChangeBody(JsonBody):
    model_config = ConfigDict(extra="forbid")

    # Leave a field out to keep it. Null clears assignee and due_at. For dependencies, null keeps
    # the current list and [] clears it. The remaining fields reject null at validation, and title
    # and labels follow the same rules as capture.
    title: Name = Field(default=None, json_schema_extra=_no_default)
    body: str = Field(default=None, max_length=10_000, json_schema_extra=_no_default)
    status: Literal["todo", "in_progress", "done"] = Field(default=None, json_schema_extra=_no_default)
    priority: int = Field(default=None, ge=1, le=4, json_schema_extra=_no_default)
    labels: list[Label] = Field(default=None, max_length=32, json_schema_extra=_no_default)
    assignee: PersonAssignee | None = None
    due_at: AwareDatetime | None = None
    dependencies: list[str] | None = Field(default=None, max_length=100)


def _revision(value: str) -> int:
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    if not value.isascii() or not value.isdecimal() or int(value) < 1:
        raise ApiError(422, "conflict", "If-Match must contain a task revision", reason="bad_revision")
    return int(value)


def register(app: FastAPI, gw: Gateway) -> None:
    service = WorkService(gw.db, clock=gw.clock)
    app.state.work = service

    def scope(request: Request, required: str) -> bool:
        ctx = ctx_of(request)
        return ctx is None or has_any(ctx.scopes, (required,))

    def denied(p: Principal, action: str) -> ApiError:
        gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": action, "reason": "permission_denied"})
        return ApiError(403, "permission_denied", f"Work {action} is unavailable for this account")

    def reader(request: Request, p: Principal = Depends(gw.principal)) -> Principal:
        if not scope(request, "work:read") or not (
            (p.kind == "person" and p.role in WORK_ROLES)
            or (p.kind == "agent" and delegated_reader(request, p) is not None)
        ):
            raise denied(p, "read")
        return p

    def writer(request: Request, p: Principal = Depends(gw.principal)) -> Principal:
        if p.kind != "person" or p.role not in WORK_ROLES or not scope(request, "work:write"):
            raise denied(p, "write")
        return p

    def emit(name: str, p: Principal, project_id: str, task_id: str) -> None:
        gw.events.publish_event("work", name, {"task_id": task_id, "project_id": project_id}, principal=p.as_dict())

    @app.get(BASE + "/tasks", tags=["work"], operation_id="work.tasks_list",
             responses={200: {"headers": {"Link": {"description": 'Next page; rel="next"', "schema": {"type": "string"}}}},
                        **error_responses(401, 403, 404, 422)})
    def list_tasks(request: Request, response: Response, p: Principal = Depends(reader),
                   project_id: str | None = Query(None, min_length=1, max_length=40),
                   view: TaskView = "all", limit: int = Query(50, ge=1, le=100),
                   cursor: str | None = Query(None, pattern=r"^[A-Za-z0-9_-]{1,40}/[A-Za-z0-9_-]{1,40}$")) -> list[Task]:
        after_project, after = cursor.split("/") if cursor else (None, "")
        if project_id and after_project not in (None, project_id):
            raise ApiError(422, "conflict", "Cursor does not belong to this project", reason="invalid_cursor")
        rows = service.list_tasks(p, project_id, after=after, after_project=after_project, limit=limit + 1,
                                  view=view, delegated=delegated_reader(request, p))
        if len(rows) > limit:
            last = rows[limit - 1]
            args = {"view": view, "limit": limit, "cursor": f"{last.project_id}/{last.id}"}
            if project_id is not None:
                args["project_id"] = project_id
            response.headers["Link"] = f'<{BASE}/tasks?{urlencode(args)}>; rel="next"'
        return rows[:limit]

    @app.get(TASK, tags=["work"], operation_id="work.task_get", responses=error_responses(401, 403, 404))
    def get_task(project_id: str, task_id: str, request: Request, p: Principal = Depends(reader)) -> Task:
        return service.get_task(p, project_id, task_id, delegated=delegated_reader(request, p))

    @app.post(BASE + "/projects", tags=["work"], operation_id="work.project_create", status_code=201,
              responses=error_responses(401, 403, 409, 422))
    def create_project(body: ProjectBody, key: IdempotencyKey, p: Principal = Depends(writer)) -> Project:
        return service.create_project(p, body, key=key)

    @app.post(BASE + "/capture", tags=["work"], operation_id="work.capture", status_code=201,
              responses={200: {"model": Task, "description": "Idempotent capture replay"},
                         **error_responses(401, 403, 404, 409, 422)})
    def capture(body: CaptureBody, key: IdempotencyKey, response: Response, p: Principal = Depends(writer)) -> Task:
        task, fresh = service.capture(p, body, key)
        if fresh:
            emit("task_created", p, task.project_id, task.id)
        else:
            response.status_code = 200
        return task

    @app.post(BASE + "/quick-add", tags=["work"], operation_id="work.quick_add", status_code=201,
              openapi_extra={"security": [{"bearer": ["work:write"]}]},
              responses={200: {"model": Task, "description": "Idempotent quick-add replay"},
                         **error_responses(401, 403, 404, 409, 422)})
    def quick_add(body: QuickAddBody, key: IdempotencyKey, response: Response, p: Principal = Depends(writer)) -> Task:
        request = {"text": body.text, "tz": body.tz}
        earlier = service.quick_add_replay(p, request, key)
        if earlier is not None:
            response.status_code = 200
            return earlier
        try:
            parsed = parse_quick_add(body.text, gw.clock(), body.tz)
            project_id = service.project_id_named(p, parsed["project"]) if parsed["project"] else None
            assignee = {"id": parsed["assignee"]} if parsed["assignee"] else None
            fields = CaptureFields.model_validate({
                "title": parsed["title"], "labels": parsed["labels"], "priority": parsed["priority"] or 4,
                "due_at": parsed["due_at"], "assignee": assignee, "project_id": project_id,
            })
        except (ValueError, ValidationError) as error:
            raise ApiError(422, "conflict", str(error) if isinstance(error, ValueError) and not isinstance(
                error, ValidationError) else "Invalid quick-add text", reason="bad_quick_add") from None
        task, fresh = service.capture(p, fields, key, request=request)
        if fresh:
            emit("task_created", p, task.project_id, task.id)
        else:
            response.status_code = 200
        return task

    @app.patch(TASK, tags=["work"], operation_id="work.task_update", responses=error_responses(401, 403, 404, 409, 422))
    def change_task(project_id: str, task_id: str, body: ChangeBody, revision: RevisionHeader,
                    p: Principal = Depends(writer)) -> Task:
        previous = service.get_task(p, project_id, task_id)
        fields = previous.model_dump(include=set(TaskFields.model_fields))
        changes = body.model_dump(exclude_unset=True, exclude={"dependencies"})
        try:
            # The changes already passed ChangeBody's strict title and label rules; the fields kept from
            # the saved task are checked as stored, so a row from before those rules can still be edited.
            proposed = StoredTaskFields.model_validate({**fields, **changes})
        except ValidationError:
            raise ApiError(422, "conflict", "Invalid Work task fields", reason="bad_task") from None
        task = service.replace_task(p, project_id, task_id, expected_revision=_revision(revision),
                                    fields=proposed, dependencies=body.dependencies)
        event = "task_completed" if task.status == "done" and previous.status != "done" else "task_updated"
        emit(event, p, project_id, task_id)
        return task

    @app.delete(TASK, tags=["work"], operation_id="work.task_delete", status_code=204,
                responses=error_responses(401, 403, 404, 409, 422))
    def delete_task(project_id: str, task_id: str, revision: RevisionHeader, p: Principal = Depends(writer)) -> Response:
        service.delete_task(p, project_id, task_id, _revision(revision))
        emit("task_deleted", p, project_id, task_id)
        return Response(status_code=204)
