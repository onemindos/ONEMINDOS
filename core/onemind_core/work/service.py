# SPDX-License-Identifier: Apache-2.0
"""Project membership and task mutations. Task data stays in the Work tables."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from itertools import groupby
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..auth import Principal
from ..errors import ApiError
from ..identity.crypto import new_id
from ..ledger import utc
from ..store import Database, SqlRepository
from .db import DependencyRow, ProjectMemberRow, ProjectRow, TaskRow

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
PersonID = Annotated[str, StringConstraints(min_length=1, max_length=128)]
AIAccess = Literal["none", "read", "work"]


class ProjectFields(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Name
    ai_access: AIAccess = "none"


class Project(ProjectFields):
    id: str


class PersonAssignee(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["person"] = "person"
    id: PersonID


class TaskFields(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: Name
    body: str = Field(default="", max_length=10_000)
    status: Literal["todo", "in_progress", "done"] = "todo"
    priority: int = Field(default=4, ge=1, le=4, strict=True)
    labels: tuple[Label, ...] = Field(default=(), max_length=32)
    assignee: PersonAssignee | None = None
    due_at: AwareDatetime | None = None


class Task(TaskFields):
    id: str
    project_id: str
    revision: int
    dependencies: tuple[str, ...]
    updated_at: AwareDatetime


def _not_found() -> ApiError:
    return ApiError(404, "not_found", "Work item not found")


def _member(project_id: str, person_id: str):
    return select(ProjectMemberRow.project_id).where(
        ProjectMemberRow.project_id == project_id, ProjectMemberRow.person_id == person_id,
    ).exists()


def _project(session: Session, person: Principal, project_id: str, *, write: bool = False) -> ProjectRow:
    if person.kind != "person":
        raise _not_found()
    visible = (ProjectRow.id == project_id, _member(project_id, person.id))
    if write:
        # Take the project write lock before reading tasks. The guard also works on SQLite, where
        # SELECT FOR UPDATE is unavailable. It serializes dependency checks across gateway workers.
        statement = update(ProjectRow).where(*visible).values(name=ProjectRow.name).returning(ProjectRow)
    else:
        statement = select(ProjectRow).where(*visible)
    row = session.scalars(statement).one_or_none()
    if row is None:
        raise _not_found()
    return row


def _task_values(fields: TaskFields) -> dict:
    return {
        "title": fields.title,
        "body": fields.body,
        "status": fields.status,
        "priority": fields.priority,
        "labels": list(fields.labels),
        "assignee_id": fields.assignee.id if fields.assignee else None,
        "due_at": utc(fields.due_at) if fields.due_at else None,
    }


def _task(row: TaskRow, dependencies: tuple[str, ...]) -> Task:
    return Task(
        id=row.id, project_id=row.project_id, revision=row.revision, title=row.title, body=row.body,
        status=row.status, priority=row.priority, labels=tuple(row.labels),
        assignee=PersonAssignee(id=row.assignee_id) if row.assignee_id else None,
        due_at=utc(row.due_at) if row.due_at else None, dependencies=dependencies, updated_at=utc(row.updated_at),
    )


def _task_reads(project_id: str, person_id: str):
    # Task revisions and dependency edges come from one statement's snapshot.
    return select(TaskRow, DependencyRow.required_id).outerjoin(
        DependencyRow, (DependencyRow.project_id == TaskRow.project_id) & (DependencyRow.task_id == TaskRow.id),
    ).where(TaskRow.project_id == project_id, _member(project_id, person_id))


def _task_results(session: Session, query) -> list[Task]:
    rows = session.execute(query.order_by(TaskRow.id, DependencyRow.required_id))
    return [
        _task(task, tuple(dependency for _, dependency in edges if dependency is not None))
        for task, edges in groupby(rows, key=lambda row: row[0])
    ]


def _replace_dependencies(session: Session, project_id: str, task_id: str, dependencies: tuple[str, ...]) -> None:
    allowed = select(TaskRow.id).where(TaskRow.project_id == project_id, TaskRow.id.in_(dependencies))
    if set(session.scalars(allowed)) != set(dependencies):
        raise _not_found()
    if dependencies:
        reachable = allowed.cte("work_required_tasks", recursive=True)
        reachable = reachable.union(select(DependencyRow.required_id).where(
            DependencyRow.project_id == project_id, DependencyRow.task_id == reachable.c.id,
        ))
        if session.scalar(select(reachable.c.id).where(reachable.c.id == task_id)) is not None:
            raise ApiError(409, "conflict", "Task dependencies must be acyclic", reason="dependency_cycle")
    session.execute(delete(DependencyRow).where(
        DependencyRow.project_id == project_id, DependencyRow.task_id == task_id,
    ))
    session.add_all(
        DependencyRow(project_id=project_id, task_id=task_id, required_id=dependency)
        for dependency in dependencies
    )


class WorkService(SqlRepository):
    def __init__(self, db: Database, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)):
        super().__init__(db)
        self.clock = clock

    def create_project(self, person: Principal, fields: ProjectFields) -> Project:
        if person.kind != "person":
            raise ApiError(403, "permission_denied", "Only people can create Work projects")
        project = Project(id=new_id("prj"), name=fields.name, ai_access=fields.ai_access)
        with self.db.session.begin() as session:
            session.add(ProjectRow(id=project.id, creator_id=person.id, name=project.name, ai_access=project.ai_access))
            session.flush()
            session.add(ProjectMemberRow(project_id=project.id, person_id=person.id))
        return project

    def get_project(self, person: Principal, project_id: str) -> Project:
        with self.db.session() as session:
            row = _project(session, person, project_id)
            return Project(id=row.id, name=row.name, ai_access=row.ai_access)

    def add_member(self, person: Principal, project_id: str, member: Principal) -> None:
        with self.db.session.begin() as session:
            project = _project(session, person, project_id, write=True)
            if project.creator_id != person.id or member.kind != "person":
                raise ApiError(403, "permission_denied", "Only the project creator can add people to Work")
            session.execute(self.db.insert()(ProjectMemberRow).values(
                project_id=project_id, person_id=member.id,
            ).on_conflict_do_nothing(index_elements=[ProjectMemberRow.project_id, ProjectMemberRow.person_id]))

    def create_task(self, person: Principal, project_id: str, fields: TaskFields) -> Task:
        with self.db.session.begin() as session:
            _project(session, person, project_id, write=True)
            self._check_assignee(session, project_id, fields.assignee)
            row = TaskRow(project_id=project_id, id=new_id("tsk"), revision=1,
                          updated_at=self.clock(), **_task_values(fields))
            session.add(row)
            return _task(row, ())

    def get_task(self, person: Principal, project_id: str, task_id: str) -> Task:
        with self.db.session() as session:
            if person.kind != "person":
                raise _not_found()
            tasks = _task_results(session, _task_reads(project_id, person.id).where(TaskRow.id == task_id))
            if not tasks:
                raise _not_found()
            return tasks[0]

    def list_tasks(self, person: Principal, project_id: str, *, after: str = "", limit: int = 100) -> list[Task]:
        with self.db.session() as session:
            _project(session, person, project_id)
            page = select(TaskRow.id).where(TaskRow.project_id == project_id, TaskRow.id > after).order_by(
                TaskRow.id,
            ).limit(min(max(limit, 1), 100))
            return _task_results(session, _task_reads(project_id, person.id).where(TaskRow.id.in_(page)))

    @staticmethod
    def _check_assignee(session: Session, project_id: str, assignee: PersonAssignee | None) -> None:
        if assignee is not None and session.get(ProjectMemberRow, (project_id, assignee.id)) is None:
            raise _not_found()

    def replace_task(
        self, person: Principal, project_id: str, task_id: str, *, expected_revision: int, fields: TaskFields,
        dependencies: Sequence[str] | None = None,
    ) -> Task:
        with self.db.session.begin() as session:
            _project(session, person, project_id, write=True)
            row = session.get(TaskRow, (project_id, task_id))
            if row is None:
                raise _not_found()
            if row.revision != expected_revision:
                raise ApiError(409, "stale_precondition", "Work task revision has changed")
            self._check_assignee(session, project_id, fields.assignee)
            if dependencies is not None:
                if len(dependencies) > 100:
                    raise ApiError(422, "conflict", "Work allows up to 100 dependencies per task")
                required = tuple(sorted(set(dependencies)))
                _replace_dependencies(session, project_id, task_id, required)
            else:
                required = tuple(session.scalars(select(DependencyRow.required_id).where(
                    DependencyRow.project_id == project_id, DependencyRow.task_id == task_id,
                ).order_by(DependencyRow.required_id)))
            values = _task_values(fields)
            for name, value in values.items():
                setattr(row, name, value)
            row.revision += 1
            row.updated_at = self.clock()
            return _task(row, required)
