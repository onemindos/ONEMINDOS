# SPDX-License-Identifier: Apache-2.0
"""Work v1 tables, scoped to their project."""

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..ledger import Base
from ..store import FeatureSchema

SCHEMA = FeatureSchema("work")


class ProjectRow(Base):
    __tablename__ = "work_projects"
    __table_args__ = (CheckConstraint("ai_access IN ('none', 'read', 'work')"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    creator_id: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(160))
    ai_access: Mapped[str] = mapped_column(String(4))


class ProjectMemberRow(Base):
    __tablename__ = "work_project_members"

    project_id: Mapped[str] = mapped_column(ForeignKey("work_projects.id", ondelete="CASCADE"), primary_key=True)
    person_id: Mapped[str] = mapped_column(String(128), primary_key=True)


class TaskRow(Base):
    __tablename__ = "work_tasks"
    __table_args__ = (
        CheckConstraint("revision > 0"),
        CheckConstraint("priority BETWEEN 1 AND 4"),
        CheckConstraint("status IN ('todo', 'in_progress', 'done')"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("work_projects.id", ondelete="CASCADE"), primary_key=True)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    revision: Mapped[int]
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    priority: Mapped[int]
    labels: Mapped[list[str]] = mapped_column(JSON)
    assignee_id: Mapped[str | None] = mapped_column(String(128))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DependencyRow(Base):
    __tablename__ = "work_dependencies"
    __table_args__ = (
        ForeignKeyConstraint(["project_id", "task_id"], ["work_tasks.project_id", "work_tasks.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(
            ["project_id", "required_id"], ["work_tasks.project_id", "work_tasks.id"], ondelete="CASCADE",
        ),
        CheckConstraint("task_id <> required_id"),
    )

    project_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    required_id: Mapped[str] = mapped_column(String(40), primary_key=True)
