# SPDX-License-Identifier: Apache-2.0
"""Work engine routes: /v1/work/... (projects, tasks, quick add, Today, Upcoming, Inbox).

The rules live in work/service.py. This file turns them into HTTP: it checks the shape of what
arrives (unknown fields are refused, so a task cannot carry a hidden instruction), reads
If-Match and Idempotency-Key, and hands the caller's principal to the service.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from datetime import datetime
from typing import Literal

from fastapi import Depends, FastAPI, Header, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope
from ..work import WorkRepository, WorkService

# A scoped token needs work:read to look and work:write to change anything (owners hold every scope).
register_route_scope("GET,HEAD", r"/v1/work(/.*)?", ("work:read",))
register_route_scope("POST", r"/v1/work/parse", ("work:read",))  # a preview: it creates nothing
register_route_scope("POST,PATCH,PUT,DELETE", r"/v1/work(/.*)?", ("work:write",))

log = logging.getLogger("onemind.work")
ORDER = 190
SWEEP_EVERY_S = 300


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Assignee(Strict):
    kind: Literal["person", "agent", "machine"]
    id: str = Field(min_length=1, max_length=128)


Scalar = str | int | float | bool


class ProjectIn(Strict):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=10000)
    ai_access: Literal["none", "read", "work"] = Field(
        default="none", description="What AI agents may do here: none (cannot see it), read, or work (add and change tasks)")


class ProjectPatch(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=10000)
    ai_access: Literal["none", "read", "work"] | None = None


class MemberIn(Strict):
    id: str = Field(min_length=1, max_length=128)
    kind: Literal["person", "agent"]


class SectionIn(Strict):
    name: str = Field(min_length=1, max_length=120)


class TaskIn(Strict):
    title: str = Field(min_length=1, max_length=300)
    project_id: str | None = Field(default=None, description="Omit for your own Inbox")
    section_id: str | None = None
    description: str = Field(default="", max_length=10000)
    status: Literal["todo", "doing", "cancelled"] = "todo"
    priority: int = Field(default=4, ge=1, le=4, description="1 is most urgent, 4 is none")
    assignee: Assignee | None = None
    due_at: datetime | None = None
    due_all_day: bool = False
    rrule: str | None = Field(default=None, max_length=120, description="FREQ=DAILY|WEEKLY|MONTHLY|YEARLY;INTERVAL=n;BYDAY=MO,..")
    tz: str = Field(default="UTC", max_length=64, description="IANA zone that repeats are worked out in")
    labels: list[str] = Field(default_factory=list, max_length=20)
    fields: dict[str, Scalar] = Field(default_factory=dict, description="Custom fields: plain text, numbers, true/false")
    asset_ref: str | None = Field(default=None, max_length=240, description="files:<path>, photos:<id>, machine:<name> or app:<id>; never opened")


class TaskPatch(Strict):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    section_id: str | None = None
    description: str | None = Field(default=None, max_length=10000)
    status: Literal["todo", "doing", "done", "cancelled"] | None = None
    priority: int | None = Field(default=None, ge=1, le=4)
    assignee: Assignee | None = None
    due_at: datetime | None = None
    due_all_day: bool | None = None
    rrule: str | None = Field(default=None, max_length=120)
    labels: list[str] | None = Field(default=None, max_length=20)
    fields: dict[str, Scalar] | None = None
    asset_ref: str | None = Field(default=None, max_length=240)


class DependencyIn(Strict):
    depends_on: str = Field(min_length=1, max_length=40)


class CommentIn(Strict):
    body: str = Field(min_length=1, max_length=10000)


class TextIn(Strict):
    text: str = Field(min_length=1, max_length=1000, description="Quick add: 'Pay rent every month #Home @bills p1 +ana'")
    tz: str | None = Field(default=None, max_length=64)


def _revision(if_match: str | None) -> int:
    if not if_match:
        raise ApiError(428, "conflict", "send If-Match with the revision you read")
    m = re.fullmatch(r'\s*(?:W/)?"?(\d{1,9})"?\s*', if_match)
    if m is None:
        raise ApiError(422, "conflict", "If-Match is the revision number, for example If-Match: \"3\"")
    return int(m.group(1))


def _json(body: dict, status: int = 200) -> JSONResponse:
    headers = {"ETag": f'"{body["revision"]}"'} if "revision" in body else {}
    return JSONResponse(body, status_code=status, headers=headers)


def register(app: FastAPI, gw: Gateway) -> None:
    def people() -> dict[str, str]:
        out: dict[str, str] = {}
        for p in gw.tokens.principals():
            if p.kind == "person":
                out.setdefault(p.id, p.role)
        for source in gw.people_sources:
            for pid, role in source().items():
                out.setdefault(pid, role)
        return out

    svc = WorkService(WorkRepository(gw.db), gw.clock, gw.events, gw.audit, people)
    principal = gw.principal
    app.state.work = svc
    gw.notify_enrichers["work"] = svc.notification_fields
    tags = ["work"]

    async def sweep_loop() -> None:
        while True:
            try:
                await run_in_threadpool(svc.sweep)
            except Exception:
                log.exception("work sweep failed")
            await asyncio.sleep(SWEEP_EVERY_S)

    loop: list[asyncio.Task] = []

    async def start() -> None:
        loop.append(asyncio.ensure_future(sweep_loop()))

    async def stop() -> None:
        for t in loop:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t

    gw.on_startup(start)
    gw.on_shutdown(stop)

    def call(fn, *a, **k):
        return run_in_threadpool(fn, *a, **k)

    # ---- projects -----------------------------------------------------------------------------
    @app.post("/v1/work/projects", tags=tags, operation_id="work.create_project", status_code=201,
              responses=error_responses(401, 403, 422))
    async def create_project(req: ProjectIn, p: Principal = Depends(principal)):
        return _json(await call(svc.create_project, p, req.name, req.description, req.ai_access), 201)

    @app.get("/v1/work/projects", tags=tags, operation_id="work.list_projects", responses=error_responses(401, 403))
    async def list_projects(p: Principal = Depends(principal)):
        return {"items": await call(svc.list_projects, p)}

    @app.get("/v1/work/projects/{project_id}", tags=tags, operation_id="work.get_project", responses=error_responses(401, 403, 404))
    async def get_project(project_id: str, p: Principal = Depends(principal)):
        return _json(await call(svc.get_project, p, project_id))

    @app.patch("/v1/work/projects/{project_id}", tags=tags, operation_id="work.update_project",
               responses=error_responses(401, 403, 404, 409, 422, 428))
    async def update_project(project_id: str, req: ProjectPatch, p: Principal = Depends(principal),
                             if_match: str | None = Header(default=None, alias="If-Match")):
        return _json(await call(svc.update_project, p, project_id, _revision(if_match), req.model_dump(exclude_unset=True)))

    @app.delete("/v1/work/projects/{project_id}", tags=tags, operation_id="work.delete_project", status_code=204,
                responses=error_responses(401, 403, 404))
    async def delete_project(project_id: str, p: Principal = Depends(principal)):
        await call(svc.delete_project, p, project_id)
        return Response(status_code=204)

    @app.post("/v1/work/projects/{project_id}/members", tags=tags, operation_id="work.add_member",
              responses=error_responses(401, 403, 404, 409, 422))
    async def add_member(project_id: str, req: MemberIn, p: Principal = Depends(principal)):
        return _json(await call(svc.add_member, p, project_id, req.id, req.kind))

    @app.delete("/v1/work/projects/{project_id}/members/{member_id}", tags=tags, operation_id="work.remove_member",
                responses=error_responses(401, 403, 404, 409))
    async def remove_member(project_id: str, member_id: str, p: Principal = Depends(principal)):
        return _json(await call(svc.remove_member, p, project_id, member_id))

    @app.post("/v1/work/projects/{project_id}/sections", tags=tags, operation_id="work.create_section", status_code=201,
              responses=error_responses(401, 403, 404, 422))
    async def create_section(project_id: str, req: SectionIn, p: Principal = Depends(principal)):
        return _json(await call(svc.create_section, p, project_id, req.name), 201)

    # ---- tasks --------------------------------------------------------------------------------
    @app.post("/v1/work/tasks", tags=tags, operation_id="work.create_task", status_code=201,
              responses=error_responses(401, 403, 404, 409, 422))
    async def create_task(req: TaskIn, p: Principal = Depends(principal)):
        return _json(await call(svc.create_task, p, req.model_dump()), 201)

    @app.get("/v1/work/tasks", tags=tags, operation_id="work.list_tasks", responses=error_responses(401, 403, 404, 422))
    async def list_tasks(project_id: str | None = Query(default=None), status: Literal["todo", "doing", "done", "cancelled"] | None = None,
                         assignee_id: str | None = Query(default=None, max_length=128), label: str | None = Query(default=None, max_length=40),
                         limit: int = Query(default=100, ge=1, le=200), p: Principal = Depends(principal)):
        return {"items": await call(svc.list_tasks, p, project_id=project_id, status=status, assignee_id=assignee_id, label=label, limit=limit)}

    @app.get("/v1/work/tasks/{task_id}", tags=tags, operation_id="work.get_task", responses=error_responses(401, 403, 404))
    async def get_task(task_id: str, p: Principal = Depends(principal)):
        return _json(await call(svc.get_task, p, task_id))

    @app.patch("/v1/work/tasks/{task_id}", tags=tags, operation_id="work.update_task",
               responses=error_responses(401, 403, 404, 409, 422, 428))
    async def update_task(task_id: str, req: TaskPatch, p: Principal = Depends(principal),
                          if_match: str | None = Header(default=None, alias="If-Match")):
        return _json(await call(svc.update_task, p, task_id, _revision(if_match), req.model_dump(exclude_unset=True)))

    @app.post("/v1/work/tasks/{task_id}/complete", tags=tags, operation_id="work.complete_task",
              responses=error_responses(401, 403, 404, 409))
    async def complete_task(task_id: str, p: Principal = Depends(principal)):
        def run():
            rev = svc.get_task(p, task_id)["revision"]
            return svc.update_task(p, task_id, rev, {"status": "done"})
        return _json(await call(run))

    @app.delete("/v1/work/tasks/{task_id}", tags=tags, operation_id="work.delete_task", status_code=204,
                responses=error_responses(401, 403, 404))
    async def delete_task(task_id: str, p: Principal = Depends(principal)):
        await call(svc.delete_task, p, task_id)
        return Response(status_code=204)

    @app.post("/v1/work/tasks/{task_id}/dependencies", tags=tags, operation_id="work.add_dependency",
              responses=error_responses(401, 403, 404, 409, 422))
    async def add_dependency(task_id: str, req: DependencyIn, p: Principal = Depends(principal)):
        return _json(await call(svc.add_dependency, p, task_id, req.depends_on))

    @app.delete("/v1/work/tasks/{task_id}/dependencies/{depends_on}", tags=tags, operation_id="work.remove_dependency",
                responses=error_responses(401, 403, 404))
    async def remove_dependency(task_id: str, depends_on: str, p: Principal = Depends(principal)):
        return _json(await call(svc.remove_dependency, p, task_id, depends_on))

    @app.post("/v1/work/tasks/{task_id}/comments", tags=tags, operation_id="work.add_comment", status_code=201,
              responses=error_responses(401, 403, 404, 422))
    async def add_comment(task_id: str, req: CommentIn, p: Principal = Depends(principal)):
        return JSONResponse(await call(svc.add_comment, p, task_id, req.body), status_code=201)

    @app.get("/v1/work/tasks/{task_id}/comments", tags=tags, operation_id="work.list_comments", responses=error_responses(401, 403, 404))
    async def list_comments(task_id: str, p: Principal = Depends(principal)):
        return {"items": await call(svc.list_comments, p, task_id)}

    @app.get("/v1/work/tasks/{task_id}/activity", tags=tags, operation_id="work.list_activity", responses=error_responses(401, 403, 404))
    async def list_activity(task_id: str, p: Principal = Depends(principal)):
        return {"items": await call(svc.list_activity, p, task_id)}

    # ---- quick add and the daily views ----------------------------------------------------------
    @app.post("/v1/work/parse", tags=tags, operation_id="work.parse", responses=error_responses(401, 403, 404, 422))
    async def parse_text(req: TextIn, p: Principal = Depends(principal)):
        return await call(svc.parse, p, req.text, req.tz)

    @app.post("/v1/work/capture", tags=tags, operation_id="work.capture", status_code=201,
              responses={200: {"description": "The same Idempotency-Key was sent before: the task it made"},
                         **error_responses(401, 403, 404, 409, 422)})
    async def capture(req: TextIn, p: Principal = Depends(principal),
                      idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=128)):
        body, created = await call(svc.capture, p, req.text, req.tz, idempotency_key)
        return _json(body, 201 if created else 200)

    @app.get("/v1/work/today", tags=tags, operation_id="work.today", responses=error_responses(401, 403, 422))
    async def today(tz: str | None = Query(default=None, max_length=64), p: Principal = Depends(principal)):
        return await call(svc.today, p, tz)

    @app.get("/v1/work/upcoming", tags=tags, operation_id="work.upcoming", responses=error_responses(401, 403, 422))
    async def upcoming(tz: str | None = Query(default=None, max_length=64), days: int = Query(default=7, ge=1, le=60),
                       p: Principal = Depends(principal)):
        return {"items": await call(svc.upcoming, p, tz, days)}

    @app.get("/v1/work/inbox", tags=tags, operation_id="work.inbox", responses=error_responses(401, 403))
    async def inbox(p: Principal = Depends(principal)):
        return {"items": await call(svc.inbox, p)}
