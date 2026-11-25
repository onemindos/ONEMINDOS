# SPDX-License-Identifier: Apache-2.0
"""Quick-add text turns into a Work task through /v1/work/quick-add."""
from datetime import UTC, datetime, timedelta

import pytest

from conftest import OWNER, GUEST
from onemind_core.work.parse import parse_quick_add

NOW = datetime(2026, 11, 25, 15, 0, tzinfo=UTC)  # 10:00 in New York


def test_parse_pulls_out_every_marker_and_keeps_the_title():
    got = parse_quick_add("Pay rent tomorrow at 5pm #Home @bills @bills p1 +person-1", NOW, "America/New_York")
    assert (got["title"], got["project"], got["labels"], got["priority"], got["assignee"]) == (
        "Pay rent", "Home", ["bills"], 1, "person-1")
    assert got["due_at"] == datetime(2026, 11, 26, 22, 0, tzinfo=UTC) and not got["due_all_day"]


def test_dates_without_a_time_are_due_at_the_end_of_the_local_day():
    got = parse_quick_add("Call mum friday", NOW, "America/New_York")
    assert got["due_at"] == datetime(2026, 11, 28, 4, 59, 59, tzinfo=UTC) and got["due_all_day"]
    assert parse_quick_add("Plan in 2 weeks", NOW)["due_at"].date().isoformat() == "2026-12-09"
    assert parse_quick_add("Ship 2026-12-01", NOW)["due_at"].date().isoformat() == "2026-12-01"


@pytest.mark.parametrize("text", ["#Home p1", "   ", "x 2026-02-31", "x at 13pm"])
def test_parse_rejects_text_with_no_title_or_a_bad_date(text):
    with pytest.raises(ValueError):
        parse_quick_add(text, NOW)


def test_unknown_time_zone_is_rejected():
    with pytest.raises(ValueError):
        parse_quick_add("x today", NOW, "Mars/Base")


def test_quick_add_creates_in_a_named_project_replays_and_rejects_bad_input(client):
    key = {**OWNER, "Idempotency-Key": "qa-1"}
    project = client.post("/v1/work/projects", json={"name": "Home"}, headers={**OWNER, "Idempotency-Key": "p-qa"})
    assert project.status_code == 201, project.text
    body = {"text": "Fix tap p2 @house #home", "tz": "UTC"}
    first = client.post("/v1/work/quick-add", json=body, headers=key)
    assert first.status_code == 201, first.text
    task = first.json()
    assert (task["title"], task["priority"], task["labels"], task["project_id"]) == (
        "Fix tap", 2, ["house"], project.json()["id"])
    replay = client.post("/v1/work/quick-add", json=body, headers=key)
    assert replay.status_code == 200 and replay.json()["id"] == task["id"]
    inbox = client.post("/v1/work/quick-add", json={"text": "Loose end"}, headers={**OWNER, "Idempotency-Key": "qa-2"})
    assert inbox.status_code == 201 and inbox.json()["project_id"] != project.json()["id"]
    missing = client.post("/v1/work/quick-add", json={"text": "x #nowhere"}, headers={**OWNER, "Idempotency-Key": "qa-3"})
    assert missing.status_code == 422
    empty = client.post("/v1/work/quick-add", json={"text": "#home"}, headers={**OWNER, "Idempotency-Key": "qa-4"})
    assert empty.status_code == 422
    assert client.post("/v1/work/quick-add", json=body, headers={**GUEST, "Idempotency-Key": "qa-5"}).status_code == 403


def test_replay_returns_the_stored_task_after_the_clock_moves_or_a_project_is_renamed(client, clock):
    key = {**OWNER, "Idempotency-Key": "qa-clock"}
    body = {"text": "Water plants today", "tz": "UTC"}
    first = client.post("/v1/work/quick-add", json=body, headers=key)
    assert first.status_code == 201, first.text
    clock.now += timedelta(days=2)  # "today" now means a different day
    replay = client.post("/v1/work/quick-add", json=body, headers=key)
    assert replay.status_code == 200 and replay.json()["id"] == first.json()["id"]
    different = client.post("/v1/work/quick-add", json={**body, "text": "Water plants"}, headers=key)
    assert different.status_code == 409 and different.json()["reason"] == "idempotency_mismatch"


def test_project_names_match_beyond_ascii(client):
    project = client.post("/v1/work/projects", json={"name": "\u00c9cole"}, headers={**OWNER, "Idempotency-Key": "p-ec"})
    got = client.post("/v1/work/quick-add", json={"text": "Devoirs #\u00e9cole"}, headers={**OWNER, "Idempotency-Key": "qa-ec"})
    assert got.status_code == 201, got.text
    assert got.json()["project_id"] == project.json()["id"]


def test_short_words_that_look_like_dates_stay_in_the_title():
    got = parse_quick_add("Email Tom about rent, then sat on it", NOW)
    assert got["title"] == "Email Tom about rent, then sat on it" and got["due_at"] is None
    assert parse_quick_add("Rest next sat", NOW, "UTC")["due_at"] is not None
