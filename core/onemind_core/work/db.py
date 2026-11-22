# SPDX-License-Identifier: Apache-2.0
"""Work engine tables (feature "work"). Every table is named work_<thing>; see service.py for the rules.

A row never holds anything the gateway would act on: text, numbers, dates and ids only.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..ledger import Base
from ..store import FeatureSchema, SqlRepository

SCHEMA = FeatureSchema("work")


class ProjectRow(Base):
    __tablename__ = "work_projects"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    ai_access: Mapped[str] = mapped_column(String(8), default="none")  # none | read | work
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(Integer, default=1)


class MemberRow(Base):
    __tablename__ = "work_members"
    project_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    principal_id: Mapped[str] = mapped_column(String(128), primary_key=True, index=True)
    kind: Mapped[str] = mapped_column(String(16))  # person | agent
    role: Mapped[str] = mapped_column(String(8))  # owner | member
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SectionRow(Base):
    __tablename__ = "work_sections"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(Integer, default=0)


class TaskRow(Base):
    __tablename__ = "work_tasks"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)  # None: the creator's Inbox
    section_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(12), default="todo")  # todo | doing | done | cancelled
    priority: Mapped[int] = mapped_column(Integer, default=4)  # 1 most urgent .. 4 none
    assignee_kind: Mapped[str | None] = mapped_column(String(10), nullable=True)  # person | agent | machine
    assignee_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True, nullable=True)
    due_all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    rrule: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tz: Mapped[str] = mapped_column(String(64), default="UTC")  # the zone "today" and repeats are worked out in
    labels: Mapped[list] = mapped_column(JSON, default=list)
    fields: Mapped[dict] = mapped_column(JSON, default=dict)
    asset_ref: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_by: Mapped[str] = mapped_column(String(128))
    created_by_kind: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    due_soon_sent_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    overdue_sent_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DependencyRow(Base):
    """`task_id` cannot start until `depends_on` is done."""

    __tablename__ = "work_dependencies"
    task_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    depends_on: Mapped[str] = mapped_column(String(40), primary_key=True, index=True)


class CommentRow(Base):
    __tablename__ = "work_comments"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(40), index=True)
    author_id: Mapped[str] = mapped_column(String(128))
    author_kind: Mapped[str] = mapped_column(String(16))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ActivityRow(Base):
    """What changed on a task, by whom. Field names only, never values (the audit log gets the same)."""

    __tablename__ = "work_activity"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(40), index=True)
    project_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_id: Mapped[str] = mapped_column(String(128))
    actor_kind: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(32))
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class IdempotencyRow(Base):
    __tablename__ = "work_idempotency"
    principal_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    task_id: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WorkRepository(SqlRepository):
    """The service opens its own transactions through `self.db.session` (see WorkService)."""
