# SPDX-License-Identifier: Apache-2.0
"""Project membership and task mutations. Task data stays in the Work tables."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from itertools import groupby
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator
from sqlalchemy import case, delete, or_, select, update
from sqlalchemy.orm import Session

from ..audit import canonical_json
from ..auth import Principal
from ..errors import ApiError
from ..identity.crypto import new_id
from ..ledger import utc
from ..store import Database, SqlRepository
from .access import OWN_TASK_ONLY_ROLES, WORK_ROLES
from .db import (ActivityRow, CommentRow, DependencyRow, InboxRow, ProjectMemberRow, ProjectRow, ReminderRow, SectionRow,
                 TaskRow, WorkCreateRow)
from .parse import next_due, zone

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
PersonID = Annotated[str, StringConstraints(min_length=1, max_length=128)]
AIAccess = Literal["none", "read", "work"]
TaskView = Literal["all", "today", "upcoming", "inbox"]
DUE_SOON = timedelta(hours=24)
WORK_EVENTS = frozenset({"work.task_created", "work.task_updated", "work.task_completed", "work.task_deleted"})


class ProjectFields(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Name
    ai_access: AIAccess = "none"


class Project(ProjectFields):
    id: str


class ProjectChanges(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Name | None = None
    ai_access: AIAccess | None = None


class Activity(BaseModel):
    """What changed on a task and who changed it. Field names only, never the old or new values."""

    id: int
    actor_id: str
    kind: Literal["created", "updated", "completed", "reopened"]
    fields: tuple[str, ...]
    at: AwareDatetime


class PersonAssignee(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["person"] = "person"
    id: PersonID


class Repeat(BaseModel):
    """Finishing a repeating task moves its due date to the next occurrence and keeps it open."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    every: Literal["day", "weekday", "week", "month", "year"]
    interval: int = Field(default=1, ge=1, le=365, strict=True)
    tz: str | None = Field(default=None, max_length=64, description="IANA zone the repeat days are counted in (default UTC)")

    @field_validator("tz")
    @classmethod
    def _known_zone(cls, value: str | None) -> str | None:
        if value is not None:
            from .parse import zone
            zone(value)
        return value


class SectionFields(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Name


class Section(SectionFields):
    id: str
    project_id: str
    position: int


class CommentFields(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    body: str = Field(min_length=1, max_length=5000)


class Comment(CommentFields):
    id: str
    author_id: str
    created_at: AwareDatetime


class TaskFields(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: Name
    body: str = Field(default="", max_length=10_000)
    status: Literal["todo", "in_progress", "done"] = "todo"
    priority: int = Field(default=4, ge=1, le=4, strict=True)
    labels: tuple[Label, ...] = Field(default=(), max_length=32)
    assignee: PersonAssignee | None = None
    due_at: AwareDatetime | None = None
    section_id: str | None = Field(default=None, min_length=1, max_length=40)
    repeat: Repeat | None = None


class CaptureFields(TaskFields):
    project_id: str | None = Field(default=None, min_length=1, max_length=40)


class Task(TaskFields):
    id: str
    project_id: str
    revision: int
    dependencies: tuple[str, ...]
    updated_at: AwareDatetime


def _not_found() -> ApiError:
    return ApiError(404, "not_found", "Work item not found")


def _writer(person: Principal) -> None:
    if person.kind != "person":
        raise _not_found()
    if person.role not in WORK_ROLES:
        raise ApiError(403, "permission_denied", "Work writes require a household person")


def _reader(actor: Principal, delegated: Principal | None) -> tuple[Principal, bool]:
    if actor.kind == "person" and actor.role in WORK_ROLES:
        return actor, False
    if actor.kind == "agent" and delegated is not None and delegated.kind == "person" and delegated.role in WORK_ROLES:
        return delegated, True
    raise _not_found()


def _member(project_id, person_id: str):
    return select(ProjectMemberRow.project_id).where(
        ProjectMemberRow.project_id == project_id, ProjectMemberRow.person_id == person_id,
    ).exists()


def _project(session: Session, person: Principal, project_id: str, *, write: bool = False) -> ProjectRow:
    if person.kind != "person" or person.role not in WORK_ROLES:
        raise _not_found()
    visible = (ProjectRow.id == project_id, _member(project_id, person.id))
    if write:
        # Take the project write lock before reading tasks. The guarded UPDATE works on SQLite,
        # where SELECT FOR UPDATE is unavailable, and serializes concurrent edge mutations.
        statement = update(ProjectRow).where(*visible).values(name=ProjectRow.name).returning(ProjectRow)
    else:
        statement = select(ProjectRow).where(*visible)
    row = session.scalars(statement).one_or_none()
    if row is None:
        raise _not_found()
    return row


def _owned_query(person: Principal, project_id: str, task_id: str | None = None):
    query = select(TaskRow).where(TaskRow.project_id == project_id)
    if task_id is not None:
        query = query.where(TaskRow.id == task_id)
    if person.role in OWN_TASK_ONLY_ROLES:
        query = query.where(TaskRow.owner_id == person.id)
    return query


def _log(session: Session, person: Principal, row: TaskRow, kind: str, names: Sequence[str], at: datetime) -> None:
    session.add(ActivityRow(project_id=row.project_id, task_id=row.id, actor_id=person.id, kind=kind,
                            fields=sorted(names), at=at))


def _task_values(fields: TaskFields) -> dict:
    return {
        "title": fields.title,
        "body": fields.body,
        "status": fields.status,
        "priority": fields.priority,
        "labels": list(fields.labels),
        "assignee_id": fields.assignee.id if fields.assignee else None,
        "due_at": utc(fields.due_at) if fields.due_at else None,
        "section_id": fields.section_id,
        "repeat": fields.repeat.model_dump(exclude_none=True) if fields.repeat else None,
    }


def _task(row: TaskRow, dependencies: tuple[str, ...]) -> Task:
    return Task(
        id=row.id, project_id=row.project_id, revision=row.revision, title=row.title, body=row.body,
        status=row.status, priority=row.priority, labels=tuple(row.labels),
        assignee=PersonAssignee(id=row.assignee_id) if row.assignee_id else None,
        due_at=utc(row.due_at) if row.due_at else None, section_id=row.section_id,
        repeat=Repeat(**row.repeat) if row.repeat else None, dependencies=dependencies, updated_at=utc(row.updated_at),
    )


def _visible_tasks(person: Principal, via_agent: bool):
    query = select(TaskRow).join(ProjectRow, ProjectRow.id == TaskRow.project_id).where(
        _member(TaskRow.project_id, person.id).correlate(TaskRow),
    )
    if via_agent:
        query = query.where(ProjectRow.ai_access.in_(("read", "work")))
    if person.role in OWN_TASK_ONLY_ROLES:
        query = query.where(TaskRow.owner_id == person.id)
    return query


def _task_reads(visible):
    # Task revisions and dependency edges come from one statement's snapshot.
    # An edge reaching a hidden task is hidden with it, even when this task is visible.
    ids = visible.with_only_columns(TaskRow.project_id, TaskRow.id).subquery()
    requirements = ids.alias("visible_requirements")
    edges = select(DependencyRow).join(
        requirements, (requirements.c.project_id == DependencyRow.project_id)
        & (requirements.c.id == DependencyRow.required_id),
    ).subquery()
    return select(TaskRow, edges.c.required_id).join(
        ids, (ids.c.project_id == TaskRow.project_id) & (ids.c.id == TaskRow.id),
    ).outerjoin(edges, (edges.c.project_id == TaskRow.project_id) & (edges.c.task_id == TaskRow.id)).order_by(
        TaskRow.project_id, TaskRow.id, edges.c.required_id,
    )


def _task_results(session: Session, query) -> list[Task]:
    rows = session.execute(query)
    return [
        _task(task, tuple(dependency for _, dependency in edges if dependency is not None))
        for task, edges in groupby(rows, key=lambda row: row[0])
    ]


def _replace_dependencies(
    session: Session, person: Principal, project_id: str, task_id: str, dependencies: tuple[str, ...],
) -> None:
    allowed = _owned_query(person, project_id).with_only_columns(TaskRow.id).where(TaskRow.id.in_(dependencies))
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
    def __init__(self, db: Database, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC),
                 person_role: Callable[[str], str | None]):
        super().__init__(db)
        self.clock = clock
        self.person_role = person_role

    @staticmethod
    def _new_project(session: Session, person: Principal, fields: ProjectFields) -> Project:
        project = Project(id=new_id("prj"), name=fields.name, ai_access=fields.ai_access)
        session.add(ProjectRow(id=project.id, creator_id=person.id, name=project.name, ai_access=project.ai_access))
        session.flush()
        session.add(ProjectMemberRow(project_id=project.id, person_id=person.id))
        return project

    def _create_receipt(self, session: Session, person: Principal, operation: str, key: str, body: dict):
        key_hash = sha256(key.encode()).hexdigest()
        fingerprint = sha256(canonical_json(body).encode()).hexdigest()
        identity = (person.id, operation, key_hash)
        fresh = session.scalar(self.db.insert()(WorkCreateRow).values(
            person_id=person.id, operation=operation, key_hash=key_hash, fingerprint=fingerprint,
        ).on_conflict_do_nothing(index_elements=[
            WorkCreateRow.person_id, WorkCreateRow.operation, WorkCreateRow.key_hash,
        ]).returning(WorkCreateRow))
        if fresh is not None:
            return fresh, True
        receipt = session.get(WorkCreateRow, identity)
        if receipt is None or receipt.fingerprint != fingerprint:
            raise ApiError(409, "conflict", "Idempotency-Key was used for a different Work request",
                           reason="idempotency_mismatch")
        return receipt, False

    def create_project(self, person: Principal, fields: ProjectFields, *, key: str | None = None) -> Project:
        _writer(person)
        with self.db.session.begin() as session:
            receipt, fresh = self._create_receipt(session, person, "project", key, fields.model_dump(mode="json")) if key else (None, True)
            if not fresh:
                row = _project(session, person, receipt.project_id)
                return Project(id=row.id, name=row.name, ai_access=row.ai_access)
            project = self._new_project(session, person, fields)
            if receipt is not None:
                receipt.project_id = project.id
            return project

    def get_project(self, actor: Principal, project_id: str, delegated: Principal | None = None) -> Project:
        person, via_agent = _reader(actor, delegated)
        with self.db.session() as session:
            row = _project(session, person, project_id)
            if via_agent and row.ai_access == "none":
                raise _not_found()
            return Project(id=row.id, name=row.name, ai_access=row.ai_access)

    def project_id_named(self, person: Principal, name: str) -> str | None:
        """A project the person can write to, by name (case-insensitive); None means the Inbox."""
        _writer(person)
        if name.casefold() == "inbox":
            return None
        with self.db.session() as session:
            # Compared in Python: SQLite's lower() folds ASCII only, so "École" would never match in SQL.
            ids = [row.id for row in session.execute(select(ProjectRow.id, ProjectRow.name).where(
                _member(ProjectRow.id, person.id)).order_by(ProjectRow.id)) if row.name.casefold() == name.casefold()]
        if len(ids) != 1:
            raise ApiError(422, "conflict", f"No single project named {name!r}", reason="bad_project")
        return ids[0]

    def list_projects(self, actor: Principal, delegated: Principal | None = None) -> list[Project]:
        person, via_agent = _reader(actor, delegated)
        query = select(ProjectRow).where(_member(ProjectRow.id, person.id).correlate(ProjectRow))
        if via_agent:
            query = query.where(ProjectRow.ai_access.in_(("read", "work")))
        with self.db.session() as session:
            return [Project(id=row.id, name=row.name, ai_access=row.ai_access)
                    for row in session.scalars(query.order_by(ProjectRow.id))]

    @staticmethod
    def _owned_project(session: Session, person: Principal, project_id: str) -> ProjectRow:
        """The project, for its creator only. The Inbox is part of the account and cannot be edited."""
        row = _project(session, person, project_id, write=True)
        if row.creator_id != person.id:
            raise ApiError(403, "permission_denied", "Only the project creator can change this project")
        if session.get(InboxRow, person.id) is not None and session.get(InboxRow, person.id).project_id == row.id:
            raise ApiError(409, "conflict", "The Inbox cannot be changed or deleted", reason="inbox_fixed")
        return row

    def update_project(self, person: Principal, project_id: str, changes: ProjectChanges) -> Project:
        _writer(person)
        with self.db.session.begin() as session:
            row = self._owned_project(session, person, project_id)
            for name, value in changes.model_dump(exclude_none=True).items():
                setattr(row, name, value)
            return Project(id=row.id, name=row.name, ai_access=row.ai_access)

    def delete_project(self, person: Principal, project_id: str) -> None:
        _writer(person)
        with self.db.session.begin() as session:
            self._owned_project(session, person, project_id)
            # Explicit deletes: the guarantee must not depend on the database enforcing foreign keys.
            for table in (ActivityRow, CommentRow, ReminderRow, DependencyRow, TaskRow, SectionRow):
                session.execute(delete(table).where(table.project_id == project_id))
            session.execute(delete(ProjectMemberRow).where(ProjectMemberRow.project_id == project_id))
            session.execute(delete(WorkCreateRow).where(WorkCreateRow.project_id == project_id))
            session.execute(delete(ProjectRow).where(ProjectRow.id == project_id))

    def members(self, actor: Principal, project_id: str, delegated: Principal | None = None) -> list[str]:
        person, via_agent = _reader(actor, delegated)
        with self.db.session() as session:
            if _project(session, person, project_id).ai_access == "none" and via_agent:
                raise _not_found()
            return list(session.scalars(select(ProjectMemberRow.person_id).where(
                ProjectMemberRow.project_id == project_id).order_by(ProjectMemberRow.person_id)))

    def remove_member(self, person: Principal, project_id: str, member_id: str) -> None:
        """The creator removes anyone but themselves; any other member may remove only themselves (leave)."""
        _writer(person)
        with self.db.session.begin() as session:
            if member_id == person.id:
                project = _project(session, person, project_id, write=True)
            else:
                project = self._owned_project(session, person, project_id)
            if member_id == project.creator_id:
                raise ApiError(409, "conflict", "The project creator cannot be removed", reason="creator_fixed")
            session.execute(delete(ProjectMemberRow).where(
                ProjectMemberRow.project_id == project_id, ProjectMemberRow.person_id == member_id))
            # Tasks assigned to someone who can no longer see the project fall back to unassigned.
            # Each is a change like any other: its revision moves and the activity log says who did it.
            for row in session.scalars(select(TaskRow).where(
                    TaskRow.project_id == project_id, TaskRow.assignee_id == member_id)):
                row.assignee_id = None
                row.revision += 1
                row.updated_at = self.clock()
                _log(session, person, row, "updated", ("assignee",), self.clock())

    def activity(self, actor: Principal, project_id: str, task_id: str, *, delegated: Principal | None = None,
                 limit: int = 100) -> list[Activity]:
        """Newest first. Reading it needs the same visibility as reading the task."""
        with self.db.session() as session:
            self._get_task(session, actor, project_id, task_id, delegated)
            rows = session.scalars(select(ActivityRow).where(
                ActivityRow.project_id == project_id, ActivityRow.task_id == task_id,
            ).order_by(ActivityRow.id.desc()).limit(min(max(limit, 1), 200)))
            return [Activity(id=r.id, actor_id=r.actor_id, kind=r.kind, fields=tuple(r.fields), at=utc(r.at))
                    for r in rows]

    @staticmethod
    def _section_writer(person: Principal) -> None:
        """Sections are shared by everyone in the project, so a child or teen cannot change them: deleting
        one rewrites tasks they are not allowed to see."""
        _writer(person)
        if person.role in OWN_TASK_ONLY_ROLES:
            raise ApiError(403, "permission_denied", "Only adults can change a project's sections")

    @staticmethod
    def _section_row(session: Session, project_id: str, section_id: str) -> SectionRow:
        row = session.get(SectionRow, section_id)
        if row is None or row.project_id != project_id:
            raise _not_found()
        return row

    def sections(self, actor: Principal, project_id: str) -> list[Section]:
        person, _ = _reader(actor, None)
        with self.db.session() as session:
            _project(session, person, project_id)
            return [Section(id=r.id, project_id=r.project_id, name=r.name, position=r.position)
                    for r in session.scalars(select(SectionRow).where(SectionRow.project_id == project_id)
                                             .order_by(SectionRow.position, SectionRow.id))]

    def create_section(self, person: Principal, project_id: str, fields: SectionFields, key: str) -> Section:
        self._section_writer(person)
        with self.db.session.begin() as session:
            _project(session, person, project_id, write=True)
            receipt, fresh = self._create_receipt(session, person, "section", key,
                                                  {"project_id": project_id, **fields.model_dump()})
            if not fresh:
                row = self._section_row(session, project_id, receipt.result_id)
                return Section(id=row.id, project_id=project_id, name=row.name, position=row.position)
            last = session.scalar(select(SectionRow.position).where(SectionRow.project_id == project_id)
                                  .order_by(SectionRow.position.desc()).limit(1))
            row = SectionRow(id=new_id("sec"), project_id=project_id, name=fields.name,
                             position=0 if last is None else last + 1)
            session.add(row)
            receipt.project_id, receipt.result_id = project_id, row.id
            return Section(id=row.id, project_id=project_id, name=row.name, position=row.position)

    def rename_section(self, person: Principal, project_id: str, section_id: str, fields: SectionFields) -> Section:
        self._section_writer(person)
        with self.db.session.begin() as session:
            _project(session, person, project_id, write=True)
            row = self._section_row(session, project_id, section_id)
            row.name = fields.name
            return Section(id=row.id, project_id=project_id, name=row.name, position=row.position)

    def delete_section(self, person: Principal, project_id: str, section_id: str) -> None:
        """Its tasks stay in the project, outside any section."""
        self._section_writer(person)
        with self.db.session.begin() as session:
            _project(session, person, project_id, write=True)
            row = self._section_row(session, project_id, section_id)
            session.execute(update(TaskRow).where(TaskRow.project_id == project_id, TaskRow.section_id == row.id)
                            .values(section_id=None))
            session.delete(row)

    def comments(self, actor: Principal, project_id: str, task_id: str) -> list[Comment]:
        with self.db.session() as session:
            self._get_task(session, actor, project_id, task_id)
            return [Comment(id=r.id, author_id=r.author_id, body=r.body, created_at=utc(r.created_at))
                    for r in session.scalars(select(CommentRow).where(
                        CommentRow.project_id == project_id, CommentRow.task_id == task_id,
                    ).order_by(CommentRow.created_at, CommentRow.id).limit(500))]

    def add_comment(self, person: Principal, project_id: str, task_id: str, fields: CommentFields, key: str) -> Comment:
        _writer(person)
        with self.db.session.begin() as session:
            _project(session, person, project_id, write=True)
            if session.scalar(_owned_query(person, project_id, task_id).with_only_columns(TaskRow.id)) is None:
                raise _not_found()
            receipt, fresh = self._create_receipt(session, person, "comment", key,
                                                  {"task_id": task_id, **fields.model_dump()})
            if not fresh:
                earlier = session.get(CommentRow, receipt.result_id)
                if earlier is None:
                    raise _not_found()
                return Comment(id=earlier.id, author_id=earlier.author_id, body=earlier.body,
                               created_at=utc(earlier.created_at))
            row = CommentRow(id=new_id("cmt"), project_id=project_id, task_id=task_id, author_id=person.id,
                             body=fields.body, created_at=self.clock())
            session.add(row)
            receipt.project_id, receipt.result_id = project_id, row.id
            return Comment(id=row.id, author_id=row.author_id, body=row.body, created_at=utc(row.created_at))

    def delete_comment(self, person: Principal, project_id: str, task_id: str, comment_id: str) -> None:
        """Only the author removes a comment; anyone else, and a missing one, gets the same 404."""
        _writer(person)
        with self.db.session.begin() as session:
            _project(session, person, project_id, write=True)
            row = session.get(CommentRow, comment_id)
            if row is None or (row.project_id, row.task_id, row.author_id) != (project_id, task_id, person.id):
                raise _not_found()
            session.delete(row)

    def add_member(self, person: Principal, project_id: str, member: Principal) -> None:
        with self.db.session.begin() as session:
            project = _project(session, person, project_id, write=True)
            if project.creator_id != person.id or member.kind != "person":
                raise ApiError(403, "permission_denied", "Only the project creator can add people to Work")
            session.execute(self.db.insert()(ProjectMemberRow).values(
                project_id=project_id, person_id=member.id,
            ).on_conflict_do_nothing(index_elements=[ProjectMemberRow.project_id, ProjectMemberRow.person_id]))

    def _new_task(self, session: Session, person: Principal, project_id: str, fields: TaskFields) -> Task:
        self._check_assignee(session, person, project_id, fields.assignee)
        self._check_section(session, project_id, fields.section_id)
        row = TaskRow(project_id=project_id, id=new_id("tsk"), owner_id=person.id, revision=1,
                      updated_at=self.clock(), **_task_values(fields))
        session.add(row)
        session.flush()
        _log(session, person, row, "created", (), self.clock())
        return _task(row, ())

    def create_task(self, person: Principal, project_id: str, fields: TaskFields) -> Task:
        _writer(person)
        with self.db.session.begin() as session:
            _project(session, person, project_id, write=True)
            return self._new_task(session, person, project_id, fields)

    def _inbox(self, session: Session, person: Principal) -> str:
        existing = session.get(InboxRow, person.id)
        if existing is not None:
            return existing.project_id
        project = self._new_project(session, person, ProjectFields(name="Inbox"))
        attached = session.scalar(self.db.insert()(InboxRow).values(
            person_id=person.id, project_id=project.id,
        ).on_conflict_do_nothing(index_elements=[InboxRow.person_id]).returning(InboxRow.project_id))
        if attached is not None:
            return attached
        # Another key created the inbox first. Roll back the unused project's rows inside this
        # transaction, retaining the receipt for the distinct capture into the winning inbox.
        session.execute(delete(ProjectMemberRow).where(ProjectMemberRow.project_id == project.id))
        session.execute(delete(ProjectRow).where(ProjectRow.id == project.id))
        return session.get(InboxRow, person.id).project_id

    def quick_add_replay(self, person: Principal, request: dict, key: str) -> Task | None:
        """The task an earlier quick-add with this key made, or None for a new key.

        The fingerprint is the raw request, not the parsed fields, so a retry still replays after the clock
        has moved or a project was renamed. A key reused for different text is a 409.
        """
        _writer(person)
        key_hash = sha256(key.encode()).hexdigest()
        fingerprint = sha256(canonical_json(request).encode()).hexdigest()
        with self.db.session() as session:
            receipt = session.get(WorkCreateRow, (person.id, "quick_add", key_hash))
            if receipt is None:
                return None
            if receipt.fingerprint != fingerprint:
                raise ApiError(409, "conflict", "Idempotency-Key was used for a different Work request",
                               reason="idempotency_mismatch")
            if receipt.result_id is None:
                return None
            return self._get_task(session, person, receipt.project_id, receipt.result_id)

    def capture(self, person: Principal, fields: CaptureFields, key: str, *, request: dict | None = None,
                ) -> tuple[Task, bool]:
        """Create one task. `request` (quick-add) is what the key is fingerprinted on, under its own operation."""
        _writer(person)
        with self.db.session.begin() as session:
            receipt, fresh = self._create_receipt(
                session, person, "capture" if request is None else "quick_add", key,
                fields.model_dump(mode="json") if request is None else request)
            if not fresh:
                return self._get_task(session, person, receipt.project_id, receipt.result_id), False
            project_id = fields.project_id if fields.project_id is not None else self._inbox(session, person)
            _project(session, person, project_id, write=True)
            task = self._new_task(session, person, project_id, fields)
            receipt.project_id, receipt.result_id = task.project_id, task.id
            return task, True

    @staticmethod
    def _get_task(
        session: Session, actor: Principal, project_id: str, task_id: str, delegated: Principal | None = None,
    ) -> Task:
        person, via_agent = _reader(actor, delegated)
        visible = _visible_tasks(person, via_agent)
        tasks = _task_results(session, _task_reads(visible).where(
            TaskRow.project_id == project_id, TaskRow.id == task_id,
        ))
        if not tasks:
            raise _not_found()
        return tasks[0]

    def get_task(
        self, person: Principal, project_id: str, task_id: str, *, delegated: Principal | None = None,
    ) -> Task:
        with self.db.session() as session:
            return self._get_task(session, person, project_id, task_id, delegated)

    def list_tasks(
        self, actor: Principal, project_id: str | None = None, *, after: str = "", after_project: str | None = None,
        limit: int = 100, view: TaskView = "all", delegated: Principal | None = None,
        tz: str | None = None,
    ) -> list[Task]:
        """`tz` (an IANA name, default UTC) decides where "today" ends for the today and upcoming views."""
        person, via_agent = _reader(actor, delegated)
        local = zone(tz)
        with self.db.session() as session:
            visible = _visible_tasks(person, via_agent)
            if project_id is not None:
                project = _project(session, person, project_id)
                if via_agent and project.ai_access == "none":
                    raise _not_found()
            page = visible
            if project_id is not None:
                page = page.where(TaskRow.project_id == project_id, TaskRow.id > after)
            elif after_project is not None:
                page = page.where(or_(
                    TaskRow.project_id > after_project,
                    (TaskRow.project_id == after_project) & (TaskRow.id > after),
                ))
            if view == "inbox":
                page = page.join(InboxRow, InboxRow.project_id == TaskRow.project_id).where(InboxRow.person_id == person.id)
            if view in ("today", "upcoming"):
                tomorrow = self.clock().astimezone(local).date() + timedelta(days=1)
                cutoff = datetime.combine(tomorrow, datetime.min.time(), tzinfo=local).astimezone(UTC)
                due = (TaskRow.due_at < cutoff) if view == "today" else (TaskRow.due_at >= cutoff)
                page = page.where(TaskRow.status != "done", due)
            rows = page.with_only_columns(TaskRow.project_id, TaskRow.id).order_by(
                TaskRow.project_id, TaskRow.id,
            ).limit(min(max(limit, 1), 101)).subquery()
            return _task_results(session, _task_reads(visible).join(
                rows, (rows.c.project_id == TaskRow.project_id) & (rows.c.id == TaskRow.id),
            ))

    def notification_fields(self, data: dict) -> dict:
        """The title the notifier shows in the assignee's inbox. Events carry ids only; this looks the task up."""
        project_id, task_id = data.get("project_id"), data.get("task_id")
        if not isinstance(project_id, str) or not isinstance(task_id, str):
            return {}
        with self.db.session() as session:
            row = session.get(TaskRow, (project_id, task_id))
            return {"title": row.title[:80]} if row is not None else {}

    def sweep(self) -> list[tuple[str, str, str, str, datetime]]:
        """Reminders due now: (name, person, project, task, due). Open assigned tasks due within a day or late.

        Each task and due date is reminded once per kind (a late task gets only `overdue`), so a sweep that
        runs every few minutes never repeats itself, and a repeating task is reminded again for its next date.
        """
        now, found = self.clock(), []
        with self.db.session.begin() as session:
            # Tasks already reminded for their current due date and state are left out in the query, so a
            # sweep every few minutes stays cheap however many overdue tasks are waiting.
            reminded = select(ReminderRow.task_id).where(
                ReminderRow.project_id == TaskRow.project_id, ReminderRow.task_id == TaskRow.id,
                ReminderRow.due_at == TaskRow.due_at,
                ReminderRow.kind == case((TaskRow.due_at < now, "overdue"), else_="due_soon"),
            ).exists()
            rows = session.scalars(select(TaskRow).where(
                TaskRow.status != "done", TaskRow.assignee_id.is_not(None), TaskRow.due_at.is_not(None),
                TaskRow.due_at <= now + DUE_SOON, ~reminded,
            ).order_by(TaskRow.project_id, TaskRow.id)).all()
            for row in rows:
                due = utc(row.due_at)
                kind = "overdue" if due < now else "due_soon"
                fresh = session.scalar(self.db.insert()(ReminderRow).values(
                    project_id=row.project_id, task_id=row.id, kind=kind, due_at=due,
                ).on_conflict_do_nothing(index_elements=[
                    ReminderRow.project_id, ReminderRow.task_id, ReminderRow.kind, ReminderRow.due_at,
                ]).returning(ReminderRow.task_id))
                if fresh is not None:
                    found.append((f"task.{kind}", row.assignee_id, row.project_id, row.id, due))
        return found

    def event_visible(self, actor: Principal, event: dict, *, delegated: Principal | None = None) -> bool:
        """Filter ids-only events by current task visibility. Deleted and missing tasks fail closed."""
        if event.get("type") not in WORK_EVENTS or not isinstance(event.get("data"), dict):
            return False
        project_id, task_id = event["data"].get("project_id"), event["data"].get("task_id")
        if not isinstance(project_id, str) or not isinstance(task_id, str):
            return False
        try:
            person, via_agent = _reader(actor, delegated)
        except ApiError:
            return False
        with self.db.session() as session:
            return session.scalar(_visible_tasks(person, via_agent).with_only_columns(TaskRow.id).where(
                TaskRow.project_id == project_id, TaskRow.id == task_id,
            )) is not None

    @staticmethod
    def _check_section(session: Session, project_id: str, section_id: str | None) -> None:
        if section_id is not None:
            section = session.get(SectionRow, section_id)
            if section is None or section.project_id != project_id:
                raise ApiError(422, "conflict", "That section is not in this project", reason="bad_section")

    def _check_assignee(self, session: Session, person: Principal, project_id: str,
                        assignee: PersonAssignee | None, *, changing: bool = True) -> None:
        if assignee is None:
            return
        if person.role in OWN_TASK_ONLY_ROLES and assignee.id != person.id \
                or session.get(ProjectMemberRow, (project_id, assignee.id)) is None:
            raise _not_found()
        if changing and assignee.id != person.id and self.person_role(assignee.id) in OWN_TASK_ONLY_ROLES:
            # A child or teen sees only the tasks they create, so a task assigned to them would be one
            # they get reminders for but cannot open.
            raise ApiError(422, "conflict", "Children and teens see only their own tasks, so a task cannot be assigned to them",
                           reason="assignee_cannot_see")

    def replace_task(
        self, person: Principal, project_id: str, task_id: str, *, expected_revision: int, fields: TaskFields,
        dependencies: Sequence[str] | None = None,
    ) -> Task:
        _writer(person)
        with self.db.session.begin() as session:
            _project(session, person, project_id, write=True)
            row = session.scalar(_owned_query(person, project_id, task_id))
            if row is None:
                raise _not_found()
            if row.revision != expected_revision:
                raise ApiError(409, "stale_precondition", "Work task revision has changed")
            # PATCH sends the current assignee back unchanged; only a new assignee must be able to see the task.
            self._check_assignee(session, person, project_id, fields.assignee,
                                 changing=fields.assignee is None or fields.assignee.id != row.assignee_id)
            self._check_section(session, project_id, fields.section_id)
            if dependencies is not None:
                if len(dependencies) > 100:
                    raise ApiError(422, "conflict", "Work allows up to 100 dependencies per task")
                required = tuple(sorted(set(dependencies)))
                _replace_dependencies(session, person, project_id, task_id, required)
            else:
                visible_requirements = _owned_query(person, project_id).with_only_columns(TaskRow.id)
                required = tuple(session.scalars(select(DependencyRow.required_id).where(
                    DependencyRow.project_id == project_id, DependencyRow.task_id == task_id,
                    DependencyRow.required_id.in_(visible_requirements),
                ).order_by(DependencyRow.required_id)))
            values = _task_values(fields)
            before = row.status
            changed = [name for name, value in values.items() if getattr(row, name) != value
                       and not (name == "due_at" and row.due_at is not None and value is not None
                                and utc(row.due_at) == value)]
            for name, value in values.items():
                setattr(row, name, value)
            if dependencies is not None:
                changed.append("dependencies")
            finished = before != "done" and row.status == "done"
            if finished and row.repeat and row.due_at is not None:
                # A repeating task is never finished: it moves to its next occurrence and stays open.
                row.due_at = next_due(utc(row.due_at), row.repeat, self.clock())
                row.status = "todo"
                changed = [name for name in changed if name not in ("status", "due_at")] + ["due_at"]
            if finished:
                kind, changed = "completed", [name for name in changed if name != "status"]
            elif "status" in changed and before == "done":
                kind, changed = "reopened", [name for name in changed if name != "status"]
            else:
                kind = "updated"
            _log(session, person, row, kind, changed, self.clock())
            row.revision += 1
            row.updated_at = self.clock()
            return _task(row, required)


    def delete_task(self, person: Principal, project_id: str, task_id: str, expected_revision: int) -> None:
        _writer(person)
        with self.db.session.begin() as session:
            _project(session, person, project_id, write=True)
            row = session.scalar(_owned_query(person, project_id, task_id))
            if row is None:
                raise _not_found()
            if row.revision != expected_revision:
                raise ApiError(409, "stale_precondition", "Work task revision has changed")
            session.execute(delete(DependencyRow).where(
                DependencyRow.project_id == project_id,
                or_(DependencyRow.task_id == task_id, DependencyRow.required_id == task_id),
            ))
            for table in (ActivityRow, CommentRow, ReminderRow):
                session.execute(delete(table).where(table.project_id == project_id, table.task_id == task_id))
            session.delete(row)
