# SPDX-License-Identifier: Apache-2.0
"""Project membership and task mutations. Task data stays in the Work tables."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from itertools import groupby
from typing import Annotated, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from ..audit import canonical_json
from ..auth import Principal
from ..errors import ApiError
from ..identity.crypto import new_id
from ..ledger import utc
from ..store import Database, SqlRepository
from .access import OWN_TASK_ONLY_ROLES, WORK_ROLES
from .db import DependencyRow, InboxRow, ProjectMemberRow, ProjectRow, TaskRow, WorkCreateRow

# Every character str.strip() removes (str.isspace), spelled out: JSON Schema's \s (ECMA-262), Python's and
# pydantic's differ (U+0085 and U+001C..U+001F), so one explicit class means the same to all of them.
SPACE_CHARS = "\t\n\x0b\x0c\r\x1c\x1d\x1e\x1f \x85\xa0\u1680" + "".join(map(chr, range(0x2000, 0x200B))) + "\u2028\u2029\u202f\u205f\u3000"
NONBLANK = f"[^{SPACE_CHARS}]"  # unanchored: at least one character that is not space
# The length is checked on what was sent (as the schema says), then the stored value is stripped. Stripping
# first (strip_whitespace) let "   " fail a schema-valid minLength 1 and let 170 characters with spaces pass.
Name = Annotated[str, StringConstraints(min_length=1, max_length=160, pattern=NONBLANK), AfterValidator(str.strip)]
Label = Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=NONBLANK), AfterValidator(str.strip)]
# Rows already saved are read with the rules they were written under. The version before Name/Label above
# stripped with pydantic's strip_whitespace, which keeps U+001C..U+001F, so a stored title or label can be
# all "space" by NONBLANK and still be valid data: reading it strictly made GET and PATCH answer 500.
StoredName = Annotated[str, StringConstraints(min_length=1, max_length=160)]
StoredLabel = Annotated[str, StringConstraints(min_length=1, max_length=64)]
PersonID = Annotated[str, StringConstraints(min_length=1, max_length=128)]
AIAccess = Literal["none", "read", "work"]
TaskView = Literal["all", "today", "upcoming", "inbox"]
WORK_EVENTS = frozenset({"work.task_created", "work.task_updated", "work.task_completed", "work.task_deleted"})


class ProjectFields(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Name
    ai_access: AIAccess = "none"


class Project(ProjectFields):
    id: str
    name: StoredName


class PersonAssignee(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["person"] = "person"
    id: PersonID


class TaskFields(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: Name
    body: str = Field(default="", max_length=10_000)
    status: Literal["todo", "in_progress", "done"] = "todo"
    priority: int = Field(default=4, ge=1, le=4)
    labels: tuple[Label, ...] = Field(default=(), max_length=32)
    assignee: PersonAssignee | None = None
    due_at: AwareDatetime | None = None


class CaptureFields(TaskFields):
    project_id: str | None = Field(default=None, min_length=1, max_length=40)


class StoredTaskFields(TaskFields):
    """Task fields as saved: new input passed the strict rules, rows from before them load as they are."""

    title: StoredName
    labels: tuple[StoredLabel, ...] = Field(default=(), max_length=32)


class Task(StoredTaskFields):
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
    def __init__(self, db: Database, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)):
        super().__init__(db)
        self.clock = clock

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

    def get_project(self, person: Principal, project_id: str) -> Project:
        with self.db.session() as session:
            row = _project(session, person, project_id)
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
        row = TaskRow(project_id=project_id, id=new_id("tsk"), owner_id=person.id, revision=1,
                      updated_at=self.clock(), **_task_values(fields))
        session.add(row)
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
    ) -> list[Task]:
        person, via_agent = _reader(actor, delegated)
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
                cutoff = utc(self.clock()).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                due = (TaskRow.due_at < cutoff) if view == "today" else (TaskRow.due_at >= cutoff)
                page = page.where(TaskRow.status != "done", due)
            rows = page.with_only_columns(TaskRow.project_id, TaskRow.id).order_by(
                TaskRow.project_id, TaskRow.id,
            ).limit(min(max(limit, 1), 101)).subquery()
            return _task_results(session, _task_reads(visible).join(
                rows, (rows.c.project_id == TaskRow.project_id) & (rows.c.id == TaskRow.id),
            ))

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
    def _check_assignee(session: Session, person: Principal, project_id: str, assignee: PersonAssignee | None) -> None:
        if assignee is not None and (person.role in OWN_TASK_ONLY_ROLES and assignee.id != person.id
                                     or session.get(ProjectMemberRow, (project_id, assignee.id)) is None):
            raise _not_found()

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
            self._check_assignee(session, person, project_id, fields.assignee)
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
            for name, value in values.items():
                setattr(row, name, value)
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
            session.delete(row)
