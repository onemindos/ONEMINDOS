# SPDX-License-Identifier: Apache-2.0
"""Work v1 tables, scoped to their project."""

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, Text, inspect, text
from sqlalchemy.orm import Mapped, mapped_column

from ..ledger import Base
from ..store import FeatureSchema

SCHEMA = FeatureSchema("work")


@SCHEMA.step(2, "Record the owner of each new task; ambiguous legacy tasks stay inaccessible to children")
def _task_owner(conn) -> None:
    if "owner_id" not in {column["name"] for column in inspect(conn).get_columns("work_tasks")}:
        conn.execute(text("ALTER TABLE work_tasks ADD COLUMN owner_id VARCHAR(128)"))


@SCHEMA.step(3, "Tasks can sit in a section of their project and repeat")
def _task_section_and_repeat(conn) -> None:
    have = {column["name"] for column in inspect(conn).get_columns("work_tasks")}
    if "section_id" not in have:
        conn.execute(text("ALTER TABLE work_tasks ADD COLUMN section_id VARCHAR(40)"))
    if "repeat" not in have:
        conn.execute(text("ALTER TABLE work_tasks ADD COLUMN repeat JSON"))


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
    owner_id: Mapped[str | None] = mapped_column(String(128))
    revision: Mapped[int]
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    priority: Mapped[int]
    labels: Mapped[list[str]] = mapped_column(JSON)
    assignee_id: Mapped[str | None] = mapped_column(String(128))
    section_id: Mapped[str | None] = mapped_column(String(40))
    repeat: Mapped[dict | None] = mapped_column(JSON)
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



class InboxRow(Base):
    __tablename__ = "work_inboxes"

    person_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("work_projects.id"), unique=True)


class WorkCreateRow(Base):
    """A key is unique to the actor and operation. Persist only request fingerprints and result IDs."""

    __tablename__ = "work_create_receipts"

    person_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    operation: Mapped[str] = mapped_column(String(16), primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    project_id: Mapped[str | None] = mapped_column(String(40))
    result_id: Mapped[str | None] = mapped_column(String(40))


class ActivityRow(Base):
    """One line of a task's history. It records which fields changed, never their values."""

    __tablename__ = "work_activity"
    __table_args__ = (
        ForeignKeyConstraint(["project_id", "task_id"], ["work_tasks.project_id", "work_tasks.id"], ondelete="CASCADE"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(40), index=True)
    task_id: Mapped[str] = mapped_column(String(40))
    actor_id: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(16))
    fields: Mapped[list[str]] = mapped_column(JSON)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SectionRow(Base):
    __tablename__ = "work_sections"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("work_projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    position: Mapped[int]


class CommentRow(Base):
    __tablename__ = "work_comments"
    __table_args__ = (
        ForeignKeyConstraint(["project_id", "task_id"], ["work_tasks.project_id", "work_tasks.id"], ondelete="CASCADE"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(40), index=True)
    task_id: Mapped[str] = mapped_column(String(40))
    author_id: Mapped[str] = mapped_column(String(128))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReminderRow(Base):
    """A reminder already sent for one task and one due date, so a sweep never repeats it."""

    __tablename__ = "work_reminders"
    __table_args__ = (
        ForeignKeyConstraint(["project_id", "task_id"], ["work_tasks.project_id", "work_tasks.id"], ondelete="CASCADE"),
    )

    project_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
