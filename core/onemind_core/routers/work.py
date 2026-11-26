# SPDX-License-Identifier: Apache-2.0
"""The Work gateway. Task edits stay inside Work and never run actions."""
import asyncio
import contextlib
import logging
from typing import Annotated, Literal
from urllib.parse import urlencode

from fastapi.concurrency import run_in_threadpool
from fastapi import Depends, FastAPI, Header, Query, Request, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity import ctx_of
from ..identity.scopes import has_any, register_route_scope
from ..jsonbody import JsonBody
from ..work.access import OWN_TASK_ONLY_ROLES, WORK_ROLES, delegated_reader
from ..work.parse import parse_quick_add, zone
from ..work.service import (Activity, CaptureFields, Comment, CommentFields, Repeat, Section, SectionFields, PersonAssignee, Project, ProjectChanges, ProjectFields, Task,
                            TaskFields, TaskView, WorkService)

ORDER = 260
SWEEP_EVERY_S = 300
log = logging.getLogger("onemind.work")
BASE = "/v1/work"
TASK = BASE + "/projects/{project_id}/tasks/{task_id}"
register_route_scope("GET,HEAD", r"/v1/work(/.*)?", ("work:read",))
register_route_scope("POST,PUT,PATCH,DELETE", r"/v1/work(/.*)?", ("work:write",))

IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)]
RevisionHeader = Annotated[str, Header(alias="If-Match", min_length=1, max_length=12)]


class ProjectBody(ProjectFields, JsonBody):
    pass


class ProjectChangeBody(ProjectChanges, JsonBody):
    pass


class ParsedLine(BaseModel):
    """What quick-add would file for a line of text. Nothing is created."""

    title: str
    project: str | None
    project_id: str | None
    project_found: bool
    labels: list[str]
    repeat: Repeat | None
    priority: int | None
    assignee: str | None
    due_at: AwareDatetime | None
    due_all_day: bool


class CaptureBody(CaptureFields, JsonBody):
    pass


class QuickAddBody(JsonBody):
    """One line such as `Pay rent tomorrow at 5pm #Home @bills p1`; see work/parse.py."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=400)
    tz: str | None = Field(default=None, max_length=64)


class ChangeBody(JsonBody):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=160)
    body: str | None = Field(default=None, max_length=10_000)
    status: Literal["todo", "in_progress", "done"] | None = None
    priority: int | None = Field(default=None, ge=1, le=4, strict=True)
    labels: list[str] | None = Field(default=None, max_length=32)
    assignee: PersonAssignee | None = None
    due_at: AwareDatetime | None = None
    section_id: str | None = Field(default=None, min_length=1, max_length=40)
    repeat: Repeat | None = None
    dependencies: list[str] | None = Field(default=None, max_length=100)


def _revision(value: str) -> int:
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    if not value.isascii() or not value.isdecimal() or int(value) < 1:
        raise ApiError(422, "conflict", "If-Match must contain a task revision", reason="bad_revision")
    return int(value)


def bad_zone(name: str | None) -> str | None:
    """The zone name as given, or a 422 for one that does not exist."""
    try:
        zone(name)
    except ValueError as error:
        raise ApiError(422, "conflict", str(error), reason="bad_zone") from None
    return name


def register(app: FastAPI, gw: Gateway) -> None:
    def person_role(person_id: str) -> str | None:
        user = app.state.identity.user(person_id)
        return user.role if user is not None else None

    service = WorkService(gw.db, clock=gw.clock, person_role=person_role)
    app.state.work = service
    gw.notify_enrichers["work"] = service.notification_fields

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

    def person_reader(request: Request, p: Principal = Depends(gw.principal)) -> Principal:
        """Project lists, members and task history are a person's own view; agents read tasks instead."""
        if p.kind != "person" or p.role not in WORK_ROLES or not scope(request, "work:read"):
            raise denied(p, "read")
        return p

    def writer(request: Request, p: Principal = Depends(gw.principal)) -> Principal:
        if p.kind != "person" or p.role not in WORK_ROLES or not scope(request, "work:write"):
            raise denied(p, "write")
        return p

    def adult_writer(request: Request, p: Principal = Depends(writer)) -> Principal:
        """Project-wide changes (adding people, sections) are for adults: a child or teen is refused here,
        audited, before any lookup (the service refuses them again)."""
        if p.role in OWN_TASK_ONLY_ROLES:
            gw.audit.append("authz.denied", p.as_dict(), None,
                            {"attempted": "change a project's people or sections", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "Only adults can change a project's people or sections")
        return p

    def emit(name: str, p: Principal, project_id: str, task_id: str) -> None:
        gw.events.publish_event("work", name, {"task_id": task_id, "project_id": project_id}, principal=p.as_dict())

    def tell_assignee(p: Principal, task: Task, previous: Task | None = None) -> None:
        """An inbox item for the person a task was just given to (never for assigning to yourself)."""
        who = task.assignee.id if task.assignee else None
        if who and who != p.id and (previous is None or previous.assignee is None or previous.assignee.id != who):
            gw.events.publish_event("work", "task.assigned", {"person_id": who, "task_id": task.id,
                                    "project_id": task.project_id}, principal=p.as_dict())

    def remind() -> int:
        sent = service.sweep()
        for name, person, project_id, task_id, due in sent:
            gw.events.publish_event("work", name, {"person_id": person, "task_id": task_id, "project_id": project_id,
                                                   "due_at": due.isoformat().replace("+00:00", "Z")})
        return len(sent)

    sweeper: list[asyncio.Task] = []

    async def sweep_loop() -> None:
        while True:
            try:
                await run_in_threadpool(remind)
            except Exception:
                log.exception("work reminder sweep failed")
            await asyncio.sleep(SWEEP_EVERY_S)

    @gw.on_startup
    async def start_reminders() -> None:
        sweeper.append(asyncio.ensure_future(sweep_loop()))

    @gw.on_shutdown
    async def stop_reminders() -> None:
        for task in sweeper:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    @app.get(BASE + "/tasks", tags=["work"], operation_id="work.tasks_list",
             responses={200: {"headers": {"Link": {"description": 'Next page; rel="next"', "schema": {"type": "string"}}}},
                        **error_responses(401, 403, 404, 422)})
    def list_tasks(request: Request, response: Response, p: Principal = Depends(reader),
                   project_id: str | None = Query(None, min_length=1, max_length=40),
                   view: TaskView = "all", limit: int = Query(50, ge=1, le=100),
                   tz: str | None = Query(None, max_length=64, description="IANA zone where today ends (default UTC)"),
                   cursor: str | None = Query(None, pattern=r"^[A-Za-z0-9_-]{1,40}/[A-Za-z0-9_-]{1,40}$")) -> list[Task]:
        after_project, after = cursor.split("/") if cursor else (None, "")
        if project_id and after_project not in (None, project_id):
            raise ApiError(422, "conflict", "Cursor does not belong to this project", reason="bad_cursor")
        rows = service.list_tasks(p, project_id, after=after, after_project=after_project, limit=limit + 1,
                                  view=view, delegated=delegated_reader(request, p), tz=bad_zone(tz))
        if len(rows) > limit:
            last = rows[limit - 1]
            args = {"view": view, "limit": limit, "cursor": f"{last.project_id}/{last.id}"}
            if project_id is not None:
                args["project_id"] = project_id
            if tz:
                args["tz"] = tz
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
            tell_assignee(p, task)
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
                "due_at": parsed["due_at"], "assignee": assignee, "repeat": parsed["repeat"], "project_id": project_id,
            })
        except (ValueError, ValidationError) as error:
            raise ApiError(422, "conflict", str(error) if isinstance(error, ValueError) and not isinstance(
                error, ValidationError) else "Invalid quick-add text", reason="bad_quick_add") from None
        task, fresh = service.capture(p, fields, key, request=request)
        if fresh:
            emit("task_created", p, task.project_id, task.id)
            tell_assignee(p, task)
        else:
            response.status_code = 200
        return task

    @app.post(BASE + "/parse", tags=["work"], operation_id="work.parse",
              openapi_extra={"security": [{"bearer": ["work:write"]}]}, responses=error_responses(401, 403, 422))
    def parse(body: QuickAddBody, p: Principal = Depends(writer)) -> ParsedLine:
        """Preview quick-add: the fields a line would become, without filing a task."""
        try:
            parsed = parse_quick_add(body.text, gw.clock(), body.tz)
        except ValueError as error:
            raise ApiError(422, "conflict", str(error), reason="bad_quick_add") from None
        project_id, found = None, True
        if parsed["project"]:
            try:
                project_id = service.project_id_named(p, parsed["project"])
            except ApiError:
                found = False
        return ParsedLine(project_id=project_id, project_found=found, **{
            key: parsed[key] for key in ("title", "project", "labels", "repeat", "priority", "assignee", "due_at", "due_all_day")})

    @app.get(BASE + "/projects", tags=["work"], operation_id="work.projects_list", openapi_extra={"security": [{"bearer": ["work:read"]}]}, responses=error_responses(401, 403))
    def list_projects(p: Principal = Depends(person_reader)) -> list[Project]:
        return service.list_projects(p)

    @app.get(BASE + "/projects/{project_id}", tags=["work"], operation_id="work.project_get", openapi_extra={"security": [{"bearer": ["work:read"]}]},
             responses=error_responses(401, 403, 404))
    def get_project(project_id: str, p: Principal = Depends(person_reader)) -> Project:
        return service.get_project(p, project_id)

    @app.patch(BASE + "/projects/{project_id}", tags=["work"], operation_id="work.project_update", openapi_extra={"security": [{"bearer": ["work:write"]}]},
               responses=error_responses(401, 403, 404, 409, 422))
    def update_project(project_id: str, body: ProjectChangeBody, p: Principal = Depends(writer)) -> Project:
        return service.update_project(p, project_id, body)

    @app.delete(BASE + "/projects/{project_id}", tags=["work"], operation_id="work.project_delete", openapi_extra={"security": [{"bearer": ["work:write"]}]}, status_code=204,
                responses=error_responses(401, 403, 404, 409))
    def delete_project(project_id: str, p: Principal = Depends(writer)) -> Response:
        service.delete_project(p, project_id)
        return Response(status_code=204)

    @app.get(BASE + "/projects/{project_id}/members", tags=["work"], operation_id="work.members_list", openapi_extra={"security": [{"bearer": ["work:read"]}]},
             responses=error_responses(401, 403, 404))
    def list_members(project_id: str, p: Principal = Depends(person_reader)) -> list[str]:
        return service.members(p, project_id)

    @app.put(BASE + "/projects/{project_id}/members/{person_id}", tags=["work"], operation_id="work.member_add", openapi_extra={"security": [{"bearer": ["work:write"]}]},
             status_code=204, responses=error_responses(401, 403, 404))
    def add_member(project_id: str, person_id: str, request: Request, p: Principal = Depends(adult_writer)) -> Response:
        user = request.app.state.identity.user(person_id)
        if user is None or user.disabled or user.role not in WORK_ROLES:
            raise ApiError(404, "not_found", "Work item not found")
        service.add_member(p, project_id, Principal(id=user.id, kind="person", role=user.role))
        return Response(status_code=204)

    @app.delete(BASE + "/projects/{project_id}/members/{person_id}", tags=["work"], operation_id="work.member_remove", openapi_extra={"security": [{"bearer": ["work:write"]}]},
                status_code=204, responses=error_responses(401, 403, 404, 409))
    def remove_member(project_id: str, person_id: str, p: Principal = Depends(writer)) -> Response:
        service.remove_member(p, project_id, person_id)
        return Response(status_code=204)

    @app.get(TASK + "/activity", tags=["work"], operation_id="work.task_activity", openapi_extra={"security": [{"bearer": ["work:read"]}]},
             responses=error_responses(401, 403, 404))
    def task_activity(project_id: str, task_id: str, p: Principal = Depends(person_reader)) -> list[Activity]:
        """The newest 100 entries, newest first."""
        return service.activity(p, project_id, task_id)

    COMMENTS = TASK + "/comments"
    SECTIONS = BASE + "/projects/{project_id}/sections"

    @app.get(COMMENTS, tags=["work"], operation_id="work.comments_list",
             openapi_extra={"security": [{"bearer": ["work:read"]}]}, responses=error_responses(401, 403, 404))
    def list_comments(project_id: str, task_id: str, p: Principal = Depends(person_reader)) -> list[Comment]:
        """Oldest first, up to 500."""
        return service.comments(p, project_id, task_id)

    @app.post(COMMENTS, tags=["work"], operation_id="work.comment_add", status_code=201,
              openapi_extra={"security": [{"bearer": ["work:write"]}]}, responses=error_responses(401, 403, 404, 422))
    def add_comment(project_id: str, task_id: str, body: CommentFields, key: IdempotencyKey,
                    p: Principal = Depends(writer)) -> Comment:
        return service.add_comment(p, project_id, task_id, body, key)

    @app.delete(COMMENTS + "/{comment_id}", tags=["work"], operation_id="work.comment_delete", status_code=204,
                openapi_extra={"security": [{"bearer": ["work:write"]}]}, responses=error_responses(401, 403, 404))
    def delete_comment(project_id: str, task_id: str, comment_id: str, p: Principal = Depends(writer)) -> Response:
        service.delete_comment(p, project_id, task_id, comment_id)
        return Response(status_code=204)

    @app.get(SECTIONS, tags=["work"], operation_id="work.sections_list",
             openapi_extra={"security": [{"bearer": ["work:read"]}]}, responses=error_responses(401, 403, 404))
    def list_sections(project_id: str, p: Principal = Depends(person_reader)) -> list[Section]:
        return service.sections(p, project_id)

    @app.post(SECTIONS, tags=["work"], operation_id="work.section_create", status_code=201,
              openapi_extra={"security": [{"bearer": ["work:write"]}]}, responses=error_responses(401, 403, 404, 422))
    def create_section(project_id: str, body: SectionFields, key: IdempotencyKey, p: Principal = Depends(adult_writer)) -> Section:
        return service.create_section(p, project_id, body, key)

    @app.patch(SECTIONS + "/{section_id}", tags=["work"], operation_id="work.section_update",
               openapi_extra={"security": [{"bearer": ["work:write"]}]}, responses=error_responses(401, 403, 404, 422))
    def rename_section(project_id: str, section_id: str, body: SectionFields, p: Principal = Depends(adult_writer)) -> Section:
        return service.rename_section(p, project_id, section_id, body)

    @app.delete(SECTIONS + "/{section_id}", tags=["work"], operation_id="work.section_delete", status_code=204,
                openapi_extra={"security": [{"bearer": ["work:write"]}]}, responses=error_responses(401, 403, 404))
    def delete_section(project_id: str, section_id: str, p: Principal = Depends(adult_writer)) -> Response:
        service.delete_section(p, project_id, section_id)
        return Response(status_code=204)

    @app.patch(TASK, tags=["work"], operation_id="work.task_update", responses=error_responses(401, 403, 404, 409, 422))
    def change_task(project_id: str, task_id: str, body: ChangeBody, revision: RevisionHeader,
                    p: Principal = Depends(writer)) -> Task:
        previous = service.get_task(p, project_id, task_id)
        fields = previous.model_dump(include=set(TaskFields.model_fields))
        changes = body.model_dump(exclude_unset=True, exclude={"dependencies"})
        try:
            proposed = TaskFields.model_validate({**fields, **changes})
        except ValidationError:
            raise ApiError(422, "conflict", "Invalid Work task fields", reason="bad_task") from None
        task = service.replace_task(p, project_id, task_id, expected_revision=_revision(revision),
                                    fields=proposed, dependencies=body.dependencies)
        event = "task_completed" if proposed.status == "done" and previous.status != "done" else "task_updated"
        emit(event, p, project_id, task_id)
        tell_assignee(p, task, previous)
        return task

    @app.delete(TASK, tags=["work"], operation_id="work.task_delete", status_code=204,
                responses=error_responses(401, 403, 404, 409, 422))
    def delete_task(project_id: str, task_id: str, revision: RevisionHeader, p: Principal = Depends(writer)) -> Response:
        service.delete_task(p, project_id, task_id, _revision(revision))
        emit("task_deleted", p, project_id, task_id)
        return Response(status_code=204)
