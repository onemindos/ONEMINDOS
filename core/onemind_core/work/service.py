# SPDX-License-Identifier: Apache-2.0
"""The work engine: projects, tasks and the rules that keep people and AI agents apart.

Who may do what (each rule has a test in core/tests/test_work.py):
- Only a person with role owner or adult, or an AI agent, uses work. Guests and children: 403.
- A project is visible only to its members. Everyone else gets 404, the same answer as for a
  project that does not exist, so nobody can probe for names.
- `ai_access` decides what an AI agent may do in a project: none (it cannot see the project),
  read (it can read) or work (it can add and change tasks and comments). New projects are none.
- An agent never creates or deletes anything of lasting weight: no projects, no members, no
  deletes. A person does those.
- Agents and machines can be assigned a task only in a project whose ai_access is work.
- A task holds text, numbers, dates and ids. Nothing in it makes the box do anything: no
  actions, no URLs fetched, no commands. `asset_ref` names a file or photo and is never opened.
- Every write is checked against a revision (PATCH needs If-Match) and leaves an event
  (work.task.*), an audit row naming who did it, and an activity line on the task. The audit
  row and event carry ids and the names of changed fields, never the text people typed.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
import os
from collections.abc import Callable
from datetime import UTC, datetime, time as dtime, timedelta

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import Principal
from ..errors import ApiError
from ..events import EventHub
from ..ledger import iso, utc
from ..store import Database  # noqa: F401  (type of repo.db)
from . import parse
from .db import (
    ActivityRow, CommentRow, DependencyRow, IdempotencyRow, MemberRow, ProjectRow, SectionRow, TaskRow,
    WorkRepository,
)

log = logging.getLogger("onemind.work")

PERSON_ROLES = ("owner", "adult")
AI_ACCESS = ("none", "read", "work")
STATUSES = ("todo", "doing", "done", "cancelled")
OPEN = ("todo", "doing")
ASSIGNEE_KINDS = ("person", "agent", "machine")
DUE_SOON = timedelta(hours=24)
MAX_LIST = 200
LABEL_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
MACHINE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}$")
PRINCIPAL_RE = re.compile(r"^[\w:.@-]{1,128}$")
# A reference to a thing that lives elsewhere. It is stored as text and never opened or fetched.
ASSET_REF_RE = re.compile(r"^(files|photos|machine|app):[A-Za-z0-9._~/-]{1,200}$")
ID_RE = re.compile(r"^(prj|tsk|sec|cmt|act)_[0-9A-Z]{26}$")
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_id(prefix: str) -> str:
    """Prefixed ULID: 48-bit milliseconds, then 80 random bits, Crockford base32."""
    n = (int(time.time() * 1000) << 80) | int.from_bytes(os.urandom(10), "big")
    return prefix + "_" + "".join(_CROCKFORD[(n >> (5 * i)) & 31] for i in range(25, -1, -1))


class WorkError(ApiError):
    pass


def _err(status: int, code: str, message: str) -> WorkError:
    return WorkError(status, code, message)


def _a(dt: datetime | None) -> datetime | None:
    return utc(dt) if dt is not None else None


# ---- validation of what a task may hold ---------------------------------------------------------
def check_labels(labels: list[str]) -> list[str]:
    out = list(dict.fromkeys(labels))
    if len(out) > 20 or any(not LABEL_RE.match(x) for x in out):
        raise _err(422, "conflict", "labels: at most 20, each 1 to 40 letters, digits, - or _")
    return out


def check_fields(fields: dict) -> dict:
    """Custom fields: plain values only (text up to 200 characters, numbers, true/false)."""
    if len(fields) > 20:
        raise _err(422, "conflict", "custom fields: at most 20")
    for k, v in fields.items():
        if not FIELD_KEY_RE.match(k):
            raise _err(422, "conflict", f"custom field name {k!r} must be lower-case letters, digits and _")
        if isinstance(v, bool) or isinstance(v, (int, float)):
            continue
        if not isinstance(v, str) or len(v) > 200:
            raise _err(422, "conflict", f"custom field {k!r} must be text up to 200 characters, a number or true/false")
    return dict(fields)


def check_asset_ref(ref: str | None) -> str | None:
    if ref is None:
        return None
    if not ASSET_REF_RE.match(ref) or ".." in ref:
        raise _err(422, "conflict", "asset_ref looks like files:<path>, photos:<id>, machine:<name> or app:<id>")
    return ref


def check_rrule(rule: str | None) -> str | None:
    if rule is None:
        return None
    try:
        return parse.check_rrule(rule)
    except ValueError as exc:
        raise _err(422, "conflict", str(exc)) from None


def task_out(r: TaskRow, blocked_by: list[str] | None = None) -> dict:
    return {
        "id": r.id, "project_id": r.project_id, "section_id": r.section_id, "title": r.title,
        "description": r.description, "status": r.status, "priority": r.priority,
        "assignee": {"kind": r.assignee_kind, "id": r.assignee_id} if r.assignee_kind else None,
        "due_at": iso(r.due_at), "due_all_day": bool(r.due_all_day), "rrule": r.rrule, "tz": r.tz,
        "labels": list(r.labels or []), "fields": dict(r.fields or {}), "asset_ref": r.asset_ref,
        "created_by": r.created_by, "created_by_kind": r.created_by_kind, "created_at": iso(r.created_at),
        "updated_at": iso(r.updated_at), "completed_at": iso(r.completed_at), "revision": r.revision,
        "blocked_by": blocked_by or [],
    }


class WorkService:
    def __init__(self, repo: WorkRepository, clock: Callable[[], datetime], events: EventHub, audit,
                 people: Callable[[], dict[str, str]]):
        self.repo, self.db = repo, repo.db
        self.clock, self.events, self.audit, self.people = clock, events, audit, people

    # ---- who ----------------------------------------------------------------------------------
    def gate(self, p: Principal) -> None:
        if (p.kind == "person" and p.role in PERSON_ROLES) or p.kind == "agent":
            return
        self.audit.append("authz.denied", p.as_dict(), None, {"attempted": "use work", "reason": "permission_denied"})
        raise _err(403, "permission_denied", "work is for household owners and adults, and their AI agents")

    def person_only(self, p: Principal, what: str) -> None:
        self.gate(p)
        if p.kind != "person":
            self.audit.append("authz.denied", p.as_dict(), None, {"attempted": what, "reason": "agent_refused"})
            raise _err(403, "permission_denied", f"an AI agent cannot {what}; a person does that")

    def _project(self, s: Session, p: Principal, pid: str, *, write: bool = False, admin: bool = False) -> ProjectRow:
        row = s.get(ProjectRow, pid) if ID_RE.match(pid) else None
        mem = s.get(MemberRow, (pid, p.id)) if row is not None else None
        if row is None or mem is None or mem.kind != p.kind:
            raise _err(404, "not_found", "no such project")
        if p.kind == "agent":
            if row.ai_access == "none":
                raise _err(404, "not_found", "no such project")
            if (write or admin) and row.ai_access != "work":
                self.audit.append("authz.denied", p.as_dict(), None, {"attempted": "change work", "reason": "ai_access", "project_id": pid})
                raise _err(403, "permission_denied", "this project lets AI agents read, not change")
        if admin and (p.kind != "person" or mem.role != "owner"):
            raise _err(403, "permission_denied", "only a project owner can do this")
        return row

    def _task(self, s: Session, p: Principal, tid: str, *, write: bool = False) -> tuple[TaskRow, ProjectRow | None]:
        row = s.get(TaskRow, tid) if ID_RE.match(tid) else None
        if row is None:
            raise _err(404, "not_found", "no such task")
        if row.project_id is None:
            if p.kind != "person" or row.created_by != p.id:
                raise _err(404, "not_found", "no such task")
            return row, None
        return row, self._project(s, p, row.project_id, write=write)

    def _visible(self, s: Session, p: Principal) -> list[str]:
        q = select(MemberRow.project_id).where(MemberRow.principal_id == p.id, MemberRow.kind == p.kind)
        if p.kind == "agent":
            q = q.join(ProjectRow, ProjectRow.id == MemberRow.project_id).where(ProjectRow.ai_access != "none")
        return list(s.scalars(q))

    def _scope(self, s: Session, p: Principal):
        """A SQL condition for the tasks this caller may see."""
        ids = self._visible(s, p)
        cond = TaskRow.project_id.in_(ids) if ids else TaskRow.id == ""
        if p.kind == "person":
            cond = or_(cond, and_(TaskRow.project_id.is_(None), TaskRow.created_by == p.id))
        return cond

    # ---- events, audit, activity ----------------------------------------------------------------
    def _log(self, s: Session, p: Principal, t: TaskRow | None, kind: str, data: dict, now: datetime, task_id: str | None = None):
        s.add(ActivityRow(id=new_id("act"), task_id=task_id or (t.id if t else ""), project_id=t.project_id if t else None,
                          at=now, actor_id=p.id, actor_kind=p.kind, kind=kind, data=data))

    def _emit(self, p: Principal, name: str, t: TaskRow | None, data: dict | None = None, *, kind: str = "task", rid: str | None = None):
        payload = {"task_id": t.id, "project_id": t.project_id} if t is not None else {}
        payload.update(data or {})
        self.events.publish_event(
            "work", name, payload, principal=p.as_dict(),
            resource={"kind": kind, "id": rid or (t.id if t else "")},
        )

    def _notify_assigned(self, p: Principal, t: TaskRow) -> None:
        if t.assignee_kind == "person" and t.assignee_id != p.id:
            self._emit(p, "task.assigned", t, {"person_id": t.assignee_id, "title": t.title[:80]})

    # ---- projects -------------------------------------------------------------------------------
    def create_project(self, p: Principal, name: str, description: str, ai_access: str) -> dict:
        self.person_only(p, "create a project")
        name = name.strip()
        if not name or ai_access not in AI_ACCESS:
            raise _err(422, "conflict", "a project needs a name and ai_access none, read or work")
        now, pid = self.clock(), new_id("prj")
        with self.db.session.begin() as s:
            s.add(ProjectRow(id=pid, name=name[:120], description=description, ai_access=ai_access, created_by=p.id,
                             created_at=now, updated_at=now, revision=1))
            s.add(MemberRow(project_id=pid, principal_id=p.id, kind="person", role="owner", added_at=now))
        self._emit(p, "project.created", None, {"project_id": pid, "ai_access": ai_access}, kind="project", rid=pid)
        return self.get_project(p, pid)

    def _project_out(self, s: Session, r: ProjectRow) -> dict:
        members = [{"id": m.principal_id, "kind": m.kind, "role": m.role}
                   for m in s.scalars(select(MemberRow).where(MemberRow.project_id == r.id).order_by(MemberRow.added_at, MemberRow.principal_id))]
        sections = [{"id": x.id, "name": x.name, "position": x.position}
                    for x in s.scalars(select(SectionRow).where(SectionRow.project_id == r.id).order_by(SectionRow.position, SectionRow.id))]
        return {"id": r.id, "name": r.name, "description": r.description, "ai_access": r.ai_access, "members": members,
                "sections": sections, "created_by": r.created_by, "created_at": iso(r.created_at),
                "updated_at": iso(r.updated_at), "revision": r.revision}

    def get_project(self, p: Principal, pid: str) -> dict:
        self.gate(p)
        with self.db.session() as s:
            return self._project_out(s, self._project(s, p, pid))

    def list_projects(self, p: Principal) -> list[dict]:
        self.gate(p)
        with self.db.session() as s:
            ids = self._visible(s, p)
            rows = s.scalars(select(ProjectRow).where(ProjectRow.id.in_(ids)).order_by(ProjectRow.created_at, ProjectRow.id)) if ids else []
            return [self._project_out(s, r) for r in rows]

    def update_project(self, p: Principal, pid: str, revision: int, patch: dict) -> dict:
        self.person_only(p, "change a project")
        now, lowered = self.clock(), False
        with self.db.session.begin() as s:
            r = self._project(s, p, pid, admin=True)
            if r.revision != revision:
                raise _err(409, "stale_precondition", f"the project is at revision {r.revision}, not {revision}; read it again")
            if "name" in patch:
                if not patch["name"].strip():
                    raise _err(422, "conflict", "a project needs a name")
                r.name = patch["name"].strip()[:120]
            if "description" in patch:
                r.description = patch["description"]
            if "ai_access" in patch:
                if patch["ai_access"] not in AI_ACCESS:
                    raise _err(422, "conflict", "ai_access is none, read or work")
                lowered = r.ai_access == "work" and patch["ai_access"] != "work"
                r.ai_access = patch["ai_access"]
                if lowered:  # nothing stays assigned to an AI the project no longer lets work
                    for t in s.scalars(select(TaskRow).where(TaskRow.project_id == pid, TaskRow.assignee_kind.in_(("agent", "machine")))):
                        t.assignee_kind = t.assignee_id = None
                        t.revision += 1
                        t.updated_at = now
                        self._log(s, p, t, "unassigned", {"reason": "ai_access"}, now)
            r.revision += 1
            r.updated_at = now
        self._emit(p, "project.updated", None, {"project_id": pid, "changed": sorted(patch)}, kind="project", rid=pid)
        return self.get_project(p, pid)

    def delete_project(self, p: Principal, pid: str) -> None:
        self.person_only(p, "delete a project")
        with self.db.session.begin() as s:
            self._project(s, p, pid, admin=True)
            ids = list(s.scalars(select(TaskRow.id).where(TaskRow.project_id == pid)))
            if ids:
                for tbl, col in ((CommentRow, CommentRow.task_id), (ActivityRow, ActivityRow.task_id), (DependencyRow, DependencyRow.task_id),
                                 (DependencyRow, DependencyRow.depends_on)):
                    s.execute(delete(tbl).where(col.in_(ids)))
            s.execute(delete(TaskRow).where(TaskRow.project_id == pid))
            for tbl in (MemberRow, SectionRow):
                s.execute(delete(tbl).where(tbl.project_id == pid))
            s.execute(delete(ProjectRow).where(ProjectRow.id == pid))
        self._emit(p, "project.deleted", None, {"project_id": pid, "tasks": len(ids)}, kind="project", rid=pid)

    def add_member(self, p: Principal, pid: str, member_id: str, kind: str) -> dict:
        self.person_only(p, "add a project member")
        if kind not in ("person", "agent") or not PRINCIPAL_RE.match(member_id):
            raise _err(422, "conflict", "a member is a person or an agent, named by id")
        if kind == "person" and self.people().get(member_id) not in PERSON_ROLES:
            raise _err(422, "conflict", "no such owner or adult on this box")
        now = self.clock()
        with self.db.session.begin() as s:
            r = self._project(s, p, pid, admin=True)
            if kind == "agent" and r.ai_access == "none":
                raise _err(409, "policy_refused", "this project does not allow AI; set ai_access to read or work first")
            if s.get(MemberRow, (pid, member_id)) is None:
                s.add(MemberRow(project_id=pid, principal_id=member_id, kind=kind, role="member", added_at=now))
        self._emit(p, "project.member_added", None, {"project_id": pid, "member_id": member_id, "kind": kind}, kind="project", rid=pid)
        return self.get_project(p, pid)

    def remove_member(self, p: Principal, pid: str, member_id: str) -> dict:
        self.person_only(p, "remove a project member")
        with self.db.session.begin() as s:
            self._project(s, p, pid, admin=True)
            m = s.get(MemberRow, (pid, member_id))
            if m is None:
                raise _err(404, "not_found", "no such member")
            if m.role == "owner":
                raise _err(409, "conflict", "a project owner cannot be removed")
            s.delete(m)
            for t in s.scalars(select(TaskRow).where(TaskRow.project_id == pid, TaskRow.assignee_id == member_id)):
                t.assignee_kind = t.assignee_id = None
                t.revision += 1
        self._emit(p, "project.member_removed", None, {"project_id": pid, "member_id": member_id}, kind="project", rid=pid)
        return self.get_project(p, pid)

    def create_section(self, p: Principal, pid: str, name: str) -> dict:
        self.gate(p)
        name = name.strip()
        if not name:
            raise _err(422, "conflict", "a section needs a name")
        with self.db.session.begin() as s:
            self._project(s, p, pid, write=True)
            pos = s.scalar(select(func.count()).select_from(SectionRow).where(SectionRow.project_id == pid)) or 0
            sec = SectionRow(id=new_id("sec"), project_id=pid, name=name[:120], position=pos)
            s.add(sec)
        self._emit(p, "project.section_added", None, {"project_id": pid, "section_id": sec.id}, kind="project", rid=pid)
        return self.get_project(p, pid)

    def find_project(self, p: Principal, name: str) -> str | None:
        """The id of the caller's visible project called `name` (case-insensitive), for #Name in quick add."""
        with self.db.session() as s:
            ids = self._visible(s, p)
            for r in s.scalars(select(ProjectRow).where(ProjectRow.id.in_(ids))) if ids else []:
                if r.name.lower().replace(" ", "-") == name.lower() or r.name.lower() == name.lower():
                    return r.id
        return None

    # ---- tasks ----------------------------------------------------------------------------------
    def _check_assignee(self, s: Session, p: Principal, project: ProjectRow | None, a: dict | None) -> tuple[str | None, str | None]:
        if a is None:
            return None, None
        kind, aid = a.get("kind"), a.get("id")
        if kind not in ASSIGNEE_KINDS or not isinstance(aid, str) or not PRINCIPAL_RE.match(aid):
            raise _err(422, "conflict", "assignee is {kind: person|agent|machine, id}")
        if kind == "person":
            ok = (project is None and aid == p.id and p.kind == "person") or (
                project is not None and (m := s.get(MemberRow, (project.id, aid))) is not None and m.kind == "person")
            if not ok:
                raise _err(422, "conflict", "a person can be assigned only if they are a member of the project")
            return kind, aid
        if project is None or project.ai_access != "work":
            raise _err(409, "policy_refused", f"a {kind} can be assigned only in a project whose ai_access is work")
        if kind == "agent":
            m = s.get(MemberRow, (project.id, aid))
            if m is None or m.kind != "agent":
                raise _err(422, "conflict", "an agent can be assigned only if it is a member of the project")
        elif not MACHINE_RE.match(aid):
            raise _err(422, "conflict", "a machine id is lower-case letters, digits, . _ -")
        return kind, aid

    def _blocked(self, s: Session, ids: list[str]) -> dict[str, list[str]]:
        if not ids:
            return {}
        out: dict[str, list[str]] = {}
        q = (select(DependencyRow.task_id, DependencyRow.depends_on).join(TaskRow, TaskRow.id == DependencyRow.depends_on)
             .where(DependencyRow.task_id.in_(ids), TaskRow.status.in_(OPEN)))
        for tid, dep in s.execute(q):
            out.setdefault(tid, []).append(dep)
        return out

    def _create(self, s: Session, p: Principal, d: dict, now: datetime) -> TaskRow:
        title = (d.get("title") or "").strip()
        if not title:
            raise _err(422, "conflict", "a task needs a title")
        pid = d.get("project_id")
        project = None
        if pid is None:
            if p.kind != "person":
                raise _err(422, "conflict", "an AI agent must name a project")
        else:
            project = self._project(s, p, pid, write=True)
        sec = d.get("section_id")
        if sec is not None and (project is None or (x := s.get(SectionRow, sec)) is None or x.project_id != project.id):
            raise _err(422, "conflict", "no such section in this project")
        status = d.get("status", "todo")
        prio = d.get("priority", 4)
        if status not in STATUSES or status == "done" or prio not in (1, 2, 3, 4):
            raise _err(422, "conflict", "a new task is todo, doing or cancelled; priority is 1 (urgent) to 4")
        kind, aid = self._check_assignee(s, p, project, d.get("assignee"))
        tz = d.get("tz") or "UTC"
        try:
            parse.zone(tz)
        except ValueError as exc:
            raise _err(422, "conflict", str(exc)) from None
        due = d.get("due_at")
        if due is not None and due.tzinfo is None:
            due = due.replace(tzinfo=UTC)
        row = TaskRow(
            id=new_id("tsk"), project_id=pid, section_id=sec, title=title[:300], description=d.get("description", ""),
            status=status, priority=prio, assignee_kind=kind, assignee_id=aid, due_at=_a(due),
            due_all_day=bool(d.get("due_all_day")), rrule=check_rrule(d.get("rrule")), tz=tz,
            labels=check_labels(d.get("labels") or []), fields=check_fields(d.get("fields") or {}),
            asset_ref=check_asset_ref(d.get("asset_ref")), created_by=p.id, created_by_kind=p.kind,
            created_at=now, updated_at=now, revision=1,
        )
        if row.rrule and row.due_at is None:
            raise _err(422, "conflict", "a repeating task needs a due date")
        s.add(row)
        self._log(s, p, row, "created", {}, now)
        return row

    def create_task(self, p: Principal, d: dict) -> dict:
        self.gate(p)
        now = self.clock()
        with self.db.session.begin() as s:
            row = self._create(s, p, d, now)
            out = task_out(row)
        self._emit(p, "task.created", row, {"assignee_kind": row.assignee_kind})
        self._notify_assigned(p, row)
        return out

    def get_task(self, p: Principal, tid: str) -> dict:
        self.gate(p)
        with self.db.session() as s:
            row, _ = self._task(s, p, tid)
            return task_out(row, self._blocked(s, [tid]).get(tid))

    def list_tasks(self, p: Principal, *, project_id: str | None = None, status: str | None = None,
                   assignee_id: str | None = None, label: str | None = None, limit: int = 100) -> list[dict]:
        self.gate(p)
        with self.db.session() as s:
            if project_id is not None:
                self._project(s, p, project_id)
            q = select(TaskRow).where(self._scope(s, p))
            if project_id:
                q = q.where(TaskRow.project_id == project_id)
            if status:
                q = q.where(TaskRow.status == status)
            if assignee_id:
                q = q.where(TaskRow.assignee_id == assignee_id)
            rows = [r for r in s.scalars(q.order_by(TaskRow.created_at, TaskRow.id)) if not label or label in (r.labels or [])][:max(1, min(limit, MAX_LIST))]
            blocked = self._blocked(s, [r.id for r in rows])
            return [task_out(r, blocked.get(r.id)) for r in rows]

    def update_task(self, p: Principal, tid: str, revision: int, patch: dict) -> dict:
        self.gate(p)
        now, notify = self.clock(), False
        with self.db.session.begin() as s:
            r, project = self._task(s, p, tid, write=True)
            if r.revision != revision:
                raise _err(409, "stale_precondition", f"the task is at revision {r.revision}, not {revision}; read it again")
            changed = []
            for key in ("title", "description"):
                if key in patch:
                    if key == "title" and not patch["title"].strip():
                        raise _err(422, "conflict", "a task needs a title")
                    setattr(r, key, patch[key].strip()[:300] if key == "title" else patch[key])
                    changed.append(key)
            if "priority" in patch:
                if patch["priority"] not in (1, 2, 3, 4):
                    raise _err(422, "conflict", "priority is 1 (urgent) to 4")
                r.priority = patch["priority"]
                changed.append("priority")
            if "section_id" in patch:
                sec = patch["section_id"]
                if sec is not None and (project is None or (x := s.get(SectionRow, sec)) is None or x.project_id != project.id):
                    raise _err(422, "conflict", "no such section in this project")
                r.section_id = sec
                changed.append("section_id")
            if "labels" in patch:
                r.labels = check_labels(patch["labels"])
                changed.append("labels")
            if "fields" in patch:
                r.fields = check_fields(patch["fields"])
                changed.append("fields")
            if "asset_ref" in patch:
                r.asset_ref = check_asset_ref(patch["asset_ref"])
                changed.append("asset_ref")
            if "assignee" in patch:
                r.assignee_kind, r.assignee_id = self._check_assignee(s, p, project, patch["assignee"])
                changed.append("assignee")
                notify = True
            for key in ("due_at", "due_all_day", "rrule"):
                if key in patch:
                    v = patch[key]
                    if key == "due_at" and v is not None and v.tzinfo is None:
                        v = v.replace(tzinfo=UTC)
                    setattr(r, key, check_rrule(v) if key == "rrule" else (_a(v) if key == "due_at" else bool(v)))
                    changed.append(key)
            if r.rrule and r.due_at is None:
                raise _err(422, "conflict", "a repeating task needs a due date")
            event = "task.updated"
            if "status" in patch and patch["status"] != r.status:
                st = patch["status"]
                if st not in STATUSES:
                    raise _err(422, "conflict", "status is todo, doing, done or cancelled")
                if st == "done":
                    event = self._finish(s, r, now)
                else:
                    r.status = st
                    r.completed_at = now if st == "cancelled" else None
                    event = "task.reopened" if st in OPEN else "task.updated"
                changed.append("status")
            r.revision += 1
            r.updated_at = now
            self._log(s, p, r, event.split(".", 1)[1], {"changed": sorted(set(changed))}, now)
            out = task_out(r, self._blocked(s, [tid]).get(tid))
        self._emit(p, event, r, {"changed": sorted(set(changed))})
        if notify:
            self._notify_assigned(p, r)
        return out

    def _finish(self, s: Session, r: TaskRow, now: datetime) -> str:
        """Mark done, unless something it waits on is still open. A repeating task moves to its next date instead."""
        if self._blocked(s, [r.id]).get(r.id):
            raise _err(409, "conflict", "this task waits on tasks that are not done yet")
        r.completed_at = now
        if r.rrule and r.due_at is not None:
            local = utc(r.due_at).astimezone(parse.zone(r.tz))
            nxt = parse.next_due(r.rrule, local)
            while nxt.astimezone(UTC) <= now:  # a long-overdue task skips to the first future date
                nxt = parse.next_due(r.rrule, nxt)
            r.due_at, r.status = nxt.astimezone(UTC), "todo"
            r.due_soon_sent_for = r.overdue_sent_for = None
        else:
            r.status = "done"
        return "task.completed"

    def delete_task(self, p: Principal, tid: str) -> None:
        self.person_only(p, "delete a task")
        with self.db.session.begin() as s:
            r, _ = self._task(s, p, tid, write=True)
            for tbl, col in ((CommentRow, CommentRow.task_id), (ActivityRow, ActivityRow.task_id), (DependencyRow, DependencyRow.task_id),
                             (DependencyRow, DependencyRow.depends_on)):
                s.execute(delete(tbl).where(col == tid))
            s.delete(r)
        self._emit(p, "task.deleted", r)

    # ---- dependencies ---------------------------------------------------------------------------
    def add_dependency(self, p: Principal, tid: str, depends_on: str) -> dict:
        self.gate(p)
        now = self.clock()
        with self.db.session.begin() as s:
            r, _ = self._task(s, p, tid, write=True)
            other, _ = self._task(s, p, depends_on, write=False)
            if other.project_id != r.project_id:
                raise _err(422, "conflict", "a task can wait only on a task in the same project")
            if other.id == r.id or self._reaches(s, other.id, r.id):
                raise _err(409, "conflict", "that would make the tasks wait on each other in a circle")
            if s.get(DependencyRow, (tid, depends_on)) is None:
                s.add(DependencyRow(task_id=tid, depends_on=depends_on))
                r.revision += 1
                r.updated_at = now
                self._log(s, p, r, "dependency_added", {"depends_on": depends_on}, now)
            out = task_out(r, self._blocked(s, [tid]).get(tid))
        self._emit(p, "task.dependency_added", r, {"depends_on": depends_on})
        return out

    def _reaches(self, s: Session, start: str, goal: str) -> bool:
        """Whether `start` already waits (directly or through others) on `goal`."""
        seen, stack = set(), [start]
        while stack:
            cur = stack.pop()
            if cur == goal:
                return True
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(s.scalars(select(DependencyRow.depends_on).where(DependencyRow.task_id == cur)))
        return False

    def remove_dependency(self, p: Principal, tid: str, depends_on: str) -> dict:
        self.person_only(p, "remove a task dependency")
        now = self.clock()
        with self.db.session.begin() as s:
            r, _ = self._task(s, p, tid, write=True)
            d = s.get(DependencyRow, (tid, depends_on))
            if d is None:
                raise _err(404, "not_found", "no such dependency")
            s.delete(d)
            r.revision += 1
            r.updated_at = now
            self._log(s, p, r, "dependency_removed", {"depends_on": depends_on}, now)
            out = task_out(r, self._blocked(s, [tid]).get(tid))
        self._emit(p, "task.dependency_removed", r, {"depends_on": depends_on})
        return out

    # ---- comments and activity ------------------------------------------------------------------
    def add_comment(self, p: Principal, tid: str, body: str) -> dict:
        self.gate(p)
        if not body.strip():
            raise _err(422, "conflict", "a comment needs text")
        now = self.clock()
        with self.db.session.begin() as s:
            r, _ = self._task(s, p, tid, write=True)
            c = CommentRow(id=new_id("cmt"), task_id=tid, author_id=p.id, author_kind=p.kind, body=body.strip(), created_at=now)
            s.add(c)
            self._log(s, p, r, "commented", {"comment_id": c.id}, now)
            out = self._comment(c)
        self._emit(p, "task.commented", r, {"comment_id": c.id})
        return out

    @staticmethod
    def _comment(c: CommentRow) -> dict:
        return {"id": c.id, "task_id": c.task_id, "author_id": c.author_id, "author_kind": c.author_kind,
                "body": c.body, "created_at": iso(c.created_at)}

    def list_comments(self, p: Principal, tid: str) -> list[dict]:
        self.gate(p)
        with self.db.session() as s:
            self._task(s, p, tid)
            return [self._comment(c) for c in s.scalars(select(CommentRow).where(CommentRow.task_id == tid).order_by(CommentRow.created_at, CommentRow.id))]

    def list_activity(self, p: Principal, tid: str) -> list[dict]:
        self.gate(p)
        with self.db.session() as s:
            self._task(s, p, tid)
            return [{"id": a.id, "at": iso(a.at), "actor": {"id": a.actor_id, "kind": a.actor_kind}, "kind": a.kind, "data": a.data}
                    for a in s.scalars(select(ActivityRow).where(ActivityRow.task_id == tid).order_by(ActivityRow.at, ActivityRow.id))]

    # ---- quick add, capture, views --------------------------------------------------------------
    def parse(self, p: Principal, text: str, tz: str | None) -> dict:
        """What /capture would make of `text`, without making it."""
        self.gate(p)
        try:
            parsed = parse.parse_quick_add(text, self.clock(), tz)
        except ValueError as exc:
            raise _err(422, "conflict", str(exc)) from None
        parsed["project_id"] = self.find_project(p, parsed["project"]) if parsed["project"] else None
        if parsed["project"] and parsed["project_id"] is None:
            raise _err(404, "not_found", f"no project called {parsed['project']}")
        parsed["due_at"] = iso(parsed["due_at"])
        return parsed

    def capture(self, p: Principal, text: str, tz: str | None, key: str | None) -> tuple[dict, bool]:
        """Make a task from one line of text. With an Idempotency-Key the same request makes one task, however often it is sent."""
        self.gate(p)
        try:
            parsed = parse.parse_quick_add(text, self.clock(), tz)
        except ValueError as exc:
            raise _err(422, "conflict", str(exc)) from None
        pid = None
        if parsed["project"]:
            pid = self.find_project(p, parsed["project"])
            if pid is None:
                raise _err(404, "not_found", f"no project called {parsed['project']}")
        assignee = None
        if parsed["assignee"]:
            who = parsed["assignee"]
            kind, _, ident = who.partition(":") if ":" in who else ("person", "", who)
            assignee = {"kind": kind, "id": ident or who}
        sec = None
        if parsed["section"] and pid:
            with self.db.session() as s:
                sec = next((x.id for x in s.scalars(select(SectionRow).where(SectionRow.project_id == pid)) if x.name.lower().replace(" ", "-") == parsed["section"].lower()), None)
            if sec is None:
                raise _err(404, "not_found", f"no section called {parsed['section']} in that project")
        d = {"title": parsed["title"], "project_id": pid, "section_id": sec, "labels": parsed["labels"],
             "priority": parsed["priority"] or 4, "assignee": assignee, "due_at": parsed["due_at"],
             "due_all_day": parsed["due_all_day"], "rrule": parsed["rrule"], "tz": tz or "UTC"}
        if not key:
            return self.create_task(p, d), True
        if not 1 <= len(key) <= 128 or not re.match(r"^[\x21-\x7e]+$", key):
            raise _err(422, "conflict", "Idempotency-Key is 1 to 128 visible characters")
        digest = hashlib.sha256(f"{text}\n{tz or ''}".encode()).hexdigest()
        for _ in range(2):
            now = self.clock()
            try:
                with self.db.session.begin() as s:
                    seen = s.get(IdempotencyRow, (p.id, key))
                    if seen is not None:
                        if seen.request_hash != digest:
                            raise _err(409, "conflict", "this Idempotency-Key was used for a different request")
                        row = s.get(TaskRow, seen.task_id)
                        if row is not None:
                            return task_out(row), False
                        s.delete(seen)  # that task was deleted since: the same request makes a new one
                        s.flush()
                    row = self._create(s, p, d, now)
                    s.add(IdempotencyRow(principal_id=p.id, key=key, request_hash=digest, task_id=row.id, created_at=now))
                    out = task_out(row)
                self._emit(p, "task.created", row, {"assignee_kind": row.assignee_kind, "via": "capture"})
                self._notify_assigned(p, row)
                return out, True
            except IntegrityError:
                continue  # a concurrent request with the same key won; read its task
        raise _err(409, "conflict", "could not record this capture; try again")

    def _mine(self, s: Session, p: Principal):
        return and_(self._scope(s, p), TaskRow.status.in_(OPEN), or_(
            and_(TaskRow.assignee_kind == p.kind, TaskRow.assignee_id == p.id),
            and_(TaskRow.assignee_id.is_(None), TaskRow.created_by == p.id)))

    def today(self, p: Principal, tz: str | None) -> dict:
        self.gate(p)
        z = _zone(tz)
        end = datetime.combine(self.clock().astimezone(z).date(), dtime(23, 59, 59), tzinfo=z).astimezone(UTC)
        with self.db.session() as s:
            rows = list(s.scalars(select(TaskRow).where(self._mine(s, p), TaskRow.due_at.is_not(None), TaskRow.due_at <= end)
                                  .order_by(TaskRow.due_at, TaskRow.priority, TaskRow.id)))
            blocked = self._blocked(s, [r.id for r in rows])
            now = self.clock()
            over = [task_out(r, blocked.get(r.id)) for r in rows if utc(r.due_at) < now]
            today = [task_out(r, blocked.get(r.id)) for r in rows if utc(r.due_at) >= now]
        return {"overdue": over, "today": today}

    def upcoming(self, p: Principal, tz: str | None, days: int) -> list[dict]:
        self.gate(p)
        z = _zone(tz)
        local = self.clock().astimezone(z).date()
        start = datetime.combine(local, dtime(23, 59, 59), tzinfo=z).astimezone(UTC)
        end = datetime.combine(local + timedelta(days=days), dtime(23, 59, 59), tzinfo=z).astimezone(UTC)
        with self.db.session() as s:
            rows = list(s.scalars(select(TaskRow).where(self._mine(s, p), TaskRow.due_at > start, TaskRow.due_at <= end)
                                  .order_by(TaskRow.due_at, TaskRow.priority, TaskRow.id)))
            blocked = self._blocked(s, [r.id for r in rows])
            return [task_out(r, blocked.get(r.id)) for r in rows]

    def inbox(self, p: Principal) -> list[dict]:
        self.gate(p)
        if p.kind != "person":
            return []
        with self.db.session() as s:
            rows = s.scalars(select(TaskRow).where(TaskRow.project_id.is_(None), TaskRow.created_by == p.id, TaskRow.status.in_(OPEN))
                             .order_by(TaskRow.created_at, TaskRow.id))
            return [task_out(r) for r in rows]

    # ---- due soon and overdue -------------------------------------------------------------------
    def sweep(self) -> int:
        """Tell assignees about tasks due within a day or overdue, once per due date. Returns how many were sent."""
        now, sent = self.clock(), 0
        system = Principal("work", "system", "system")
        with self.db.session.begin() as s:
            rows = list(s.scalars(select(TaskRow).where(
                TaskRow.status.in_(OPEN), TaskRow.assignee_kind == "person", TaskRow.due_at.is_not(None), TaskRow.due_at <= now + DUE_SOON)))
            todo = []
            for r in rows:
                due = utc(r.due_at)
                if due < now and _a(r.overdue_sent_for) != due:
                    r.overdue_sent_for = r.due_soon_sent_for = due
                    todo.append(("task.overdue", r))
                elif due >= now and _a(r.due_soon_sent_for) != due:
                    r.due_soon_sent_for = due
                    todo.append(("task.due_soon", r))
        for name, r in todo:
            self._emit(system, name, r, {"person_id": r.assignee_id, "title": r.title[:80], "due_at": iso(r.due_at)})
            sent += 1
        return sent


def _zone(tz: str | None):
    try:
        return parse.zone(tz)
    except ValueError as exc:
        raise _err(422, "conflict", str(exc)) from None
