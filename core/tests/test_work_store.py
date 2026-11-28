# SPDX-License-Identifier: Apache-2.0
"""Work on the gateway database, including concurrency between independent sessions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import pytest
from pydantic import ValidationError

from onemind_core.auth import Principal
from onemind_core.errors import ApiError
from onemind_core.ledger import make_engine
from onemind_core.store import Database, migrate
from onemind_core.work.db import SCHEMA
from onemind_core.work.service import PersonAssignee, ProjectFields, TaskFields, WorkService

CREATOR = Principal("creator", "person", "adult")
MEMBER = Principal("member", "person", "adult")
OTHER = Principal("other", "person", "owner")
AGENT = Principal("creator", "agent", "agent")
NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def work(settings):
    engine = make_engine(settings.db_url)
    try:
        assert migrate(engine, [SCHEMA]) == {"work": 3}
        yield WorkService(Database(engine), clock=lambda: NOW, person_role=lambda _: "adult")
    finally:
        engine.dispose()


def test_projects_and_tasks_are_private_to_members(work):
    project = work.create_project(CREATOR, ProjectFields(name=" Private project "))
    task = work.create_task(CREATOR, project.id, TaskFields(title="First"))
    assert project.name == "Private project"
    assert project.ai_access == "none"
    assert task.revision == 1

    for outsider in (OTHER, AGENT):
        for access in (
            lambda: work.get_project(outsider, project.id),
            lambda: work.get_task(outsider, project.id, task.id),
            lambda: work.list_tasks(outsider, project.id),
            lambda: work.create_task(outsider, project.id, TaskFields(title="Write")),
            lambda: work.replace_task(outsider, project.id, task.id, expected_revision=1,
                                      fields=TaskFields(title="Replace")),
        ):
            with pytest.raises(ApiError) as refused:
                access()
            assert (refused.value.status, refused.value.error) == (404, "not_found")
    assert work.get_task(CREATOR, project.id, task.id) == task


def test_membership_controls_assignment_and_can_only_be_added_by_creator(work):
    project = work.create_project(CREATOR, ProjectFields(name="Project"))
    fields = TaskFields(title="Work", assignee=PersonAssignee(id=MEMBER.id), due_at=NOW)
    with pytest.raises(ApiError) as refused:
        work.create_task(CREATOR, project.id, fields)
    assert refused.value.status == 404

    work.add_member(CREATOR, project.id, MEMBER)
    work.add_member(CREATOR, project.id, MEMBER)
    task = work.create_task(MEMBER, project.id, fields)
    assert work.list_tasks(CREATOR, project.id) == [task]
    assert task.assignee == fields.assignee
    assert task.due_at == NOW

    for actor, invitee in ((MEMBER, OTHER), (CREATOR, AGENT)):
        with pytest.raises(ApiError) as refused:
            work.add_member(actor, project.id, invitee)
        assert refused.value.status == 403

    with pytest.raises(ValidationError):
        TaskFields.model_validate({"title": "Work", "assignee": {"kind": "agent", "id": AGENT.id}})
    with pytest.raises(ValidationError):
        TaskFields.model_validate({"title": "Work", "effect": {"kind": "run"}})


def test_cross_project_and_cyclic_dependencies_leave_task_and_revision_intact(work):
    project = work.create_project(CREATOR, ProjectFields(name="Project"))
    other = work.create_project(CREATOR, ProjectFields(name="Other"))
    a, b, c = [work.create_task(CREATOR, project.id, TaskFields(title=name)) for name in ("A", "B", "C")]
    outside = work.create_task(CREATOR, other.id, TaskFields(title="Outside"))

    def replace(task, *ids):
        return work.replace_task(CREATOR, project.id, task.id, expected_revision=task.revision,
                                 fields=TaskFields(title=task.title), dependencies=ids)

    a = replace(a, b.id)
    b = replace(b, c.id)
    assert a.dependencies == (b.id,)
    assert b.dependencies == (c.id,)

    for required_id in (a.id, c.id):
        with pytest.raises(ApiError) as refused:
            replace(c, required_id)
        assert (refused.value.status, refused.value.reason) == (409, "dependency_cycle")
    with pytest.raises(ApiError) as refused:
        replace(c, outside.id)
    assert refused.value.status == 404
    with pytest.raises(ApiError) as refused:
        replace(outside, c.id)
    assert refused.value.status == 404

    assert work.get_task(CREATOR, project.id, c.id) == c
    updated = replace(a, b.id, c.id, c.id)
    assert updated.dependencies == tuple(sorted((b.id, c.id)))
    assert work.get_task(CREATOR, project.id, a.id) == updated
    page = work.list_tasks(CREATOR, project.id, limit=1)
    assert work.list_tasks(CREATOR, project.id, after=page[0].id) == [
        task for task in sorted([updated, b, c], key=lambda item: item.id) if task.id > page[0].id
    ]


@pytest.mark.parametrize("opposing_dependencies", [False, True])
def test_concurrent_mutations_commit_exactly_one_valid_revision_or_edge(work, opposing_dependencies):
    project = work.create_project(CREATOR, ProjectFields(name="Project"))
    a = work.create_task(CREATOR, project.id, TaskFields(title="A"))
    b = work.create_task(CREATOR, project.id, TaskFields(title="B"))
    barrier = Barrier(2, timeout=5)

    def writer(index):
        row = (a, b)[index] if opposing_dependencies else a
        requires = [(b, a)[index].id] if opposing_dependencies else None
        # Separate repository/session factory as in different gateway workers.
        service = WorkService(Database(work.db.engine), clock=lambda: NOW, person_role=lambda _: "adult")
        barrier.wait()
        try:
            return service.replace_task(CREATOR, project.id, row.id, expected_revision=row.revision,
                                        fields=TaskFields(title=f"Writer {index}"), dependencies=requires)
        except ApiError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(writer, range(2)))

    changed, = [item for item in results if not isinstance(item, ApiError)]
    rejected, = [item for item in results if isinstance(item, ApiError)]
    assert rejected.status == 409
    assert changed.revision == 2
    assert work.get_task(CREATOR, project.id, changed.id) == changed
    if opposing_dependencies:
        assert rejected.reason == "dependency_cycle"
        other, = changed.dependencies
        assert work.get_task(CREATOR, project.id, other).revision == 1
    else:
        assert rejected.error == "stale_precondition"
