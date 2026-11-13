# SPDX-License-Identifier: Apache-2.0
"""Cron expressions, DST behaviour and maintenance windows (docs/architecture/AUTOMATION.md AT-1)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from onemind_core.automation.cron import Cron, parse_ranges, resolve_tz, window_open
from onemind_core.automation.policies import update_kind


def utc(*a) -> datetime:
    return datetime(*a, tzinfo=UTC)


@pytest.mark.parametrize("expr", [
    "* * * *", "* * * * * *", "60 * * * *", "* 24 * * *", "5-1 * * * *", "*/0 * * * *",
    "* * * foo *", "a * * * *", "* * 0 * *",
])
def test_bad_cron_is_refused(expr):
    with pytest.raises(ValueError):
        Cron.parse(expr)


def test_names_steps_and_lists():
    c = Cron.parse("*/15 9-17 * jan,jul mon-fri")
    assert c.matches(datetime(2027, 1, 4, 9, 45))  # Monday
    assert not c.matches(datetime(2027, 1, 4, 9, 50))
    assert not c.matches(datetime(2027, 1, 9, 9, 45))  # Saturday
    assert not c.matches(datetime(2027, 2, 1, 9, 45))
    assert Cron.parse("0 0 * * 7").matches(datetime(2027, 1, 3))  # 7 is Sunday


def test_day_fields_or_when_both_restricted():
    c = Cron.parse("0 0 13 * fri")
    assert c.matches(datetime(2027, 1, 13))  # the 13th, a Wednesday
    assert c.matches(datetime(2027, 1, 15))  # a Friday
    assert not c.matches(datetime(2027, 1, 14))


def test_daily_fire_follows_local_time_across_spring_and_autumn_in_london():
    c, tz = Cron.parse("0 3 * * *"), resolve_tz("Europe/London")
    fires = [t for t, _ in c.fire_times(tz, utc(2026, 3, 27), utc(2026, 3, 31))]
    assert fires == [utc(2026, 3, 27, 3), utc(2026, 3, 28, 3), utc(2026, 3, 29, 2), utc(2026, 3, 30, 2)]
    fires = [t for t, _ in c.fire_times(tz, utc(2026, 10, 24), utc(2026, 10, 27))]
    assert fires == [utc(2026, 10, 24, 2), utc(2026, 10, 25, 3), utc(2026, 10, 26, 3)]


def test_new_york_repeated_hour_fires_once_and_missing_hour_is_skipped():
    tz = resolve_tz("America/New_York")
    fall = list(Cron.parse("30 1 * * *").fire_times(tz, utc(2026, 11, 1), utc(2026, 11, 1, 12)))
    assert [s for _, s in fall] == ["2026-11-01T01:30"]
    spring = [s for _, s in Cron.parse("30 2 * * *").fire_times(tz, utc(2026, 3, 7), utc(2026, 3, 10))]
    assert spring == ["2026-03-07T02:30", "2026-03-09T02:30"]


def test_fire_times_bounds_and_next_fire():
    c = Cron.parse("* * * * *")
    got = list(c.fire_times(UTC, utc(2027, 1, 1, 0, 0, 30), utc(2027, 1, 1, 0, 3)))
    assert [t for t, _ in got] == [utc(2027, 1, 1, 0, 1), utc(2027, 1, 1, 0, 2), utc(2027, 1, 1, 0, 3)]
    assert Cron.parse("0 0 1 * *").next_fire(UTC, utc(2027, 1, 2)) == utc(2027, 2, 1)
    assert Cron.parse("0 0 30 2 *").next_fire(UTC, utc(2027, 1, 1)) is None  # 30 February never comes


def test_half_hour_offset_zone():
    tz = resolve_tz("Asia/Kolkata")  # UTC+05:30
    fires = [t for t, _ in Cron.parse("0 9 * * *").fire_times(tz, utc(2027, 1, 1), utc(2027, 1, 2))]
    assert fires == [utc(2027, 1, 1, 3, 30)]


def test_time_zones():
    assert resolve_tz("box", "UTC") is UTC
    assert resolve_tz(None, "Europe/London").key == "Europe/London"
    for bad in ("Mars/Olympus", "../etc/passwd", ""):
        with pytest.raises(ValueError):
            resolve_tz(bad)


def test_windows_including_overnight_ranges():
    nightly = parse_ranges([{"days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"], "start": "02:00", "end": "05:00"}])
    assert window_open(nightly, UTC, utc(2027, 1, 1, 2, 0))
    assert not window_open(nightly, UTC, utc(2027, 1, 1, 5, 0))
    late = parse_ranges([{"days": ["fri"], "start": "22:00", "end": "02:00"}])  # 2027-01-01 is a Friday
    assert window_open(late, UTC, utc(2027, 1, 1, 23, 0))
    assert window_open(late, UTC, utc(2027, 1, 2, 1, 59))
    assert not window_open(late, UTC, utc(2027, 1, 2, 2, 0))
    assert not window_open(late, UTC, utc(2027, 1, 1, 1, 0))  # Friday early morning: Thursday not listed
    london = resolve_tz("Europe/London")
    summer = parse_ranges([{"start": "02:00", "end": "03:00"}])
    assert window_open(summer, london, utc(2027, 7, 1, 1, 30))  # 02:30 BST
    for bad in ([], [{"start": "2:00", "end": "03:00"}], [{"start": "02:00", "end": "02:00"}],
                [{"days": ["funday"], "start": "01:00", "end": "02:00"}], [{"x": 1}]):
        with pytest.raises(ValueError):
            parse_ranges(bad)


def test_update_kind():
    assert update_kind("1.10.1", "1.10.2") == "patch"
    assert update_kind("v1.10.1", "1.11.0") == "minor"
    assert update_kind("1.10.1", "2.0.0") == "major"
    assert update_kind("1.10.1", "1.10.1") is None
    assert update_kind(None, "1.0.0") is None
    assert update_kind("1.2", "1.2.1") is None
    # F-6 covers released patch versions only: a pre-release or a non-string is not a patch.
    assert update_kind("1.10.1", "1.10.2-rc1") is None
    assert update_kind("1.10.1-rc1", "1.10.1") is None
    assert update_kind("1.10.1", 5) is None
