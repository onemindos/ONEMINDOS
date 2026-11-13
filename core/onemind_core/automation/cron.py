# SPDX-License-Identifier: Apache-2.0
"""Five-field cron expressions and maintenance windows, evaluated in a named time zone.

Cron (contract §12.17: 5 fields, at most once a minute): `minute hour day-of-month month
day-of-week`, each `*`, `n`, `a-b`, `*/s`, `a-b/s`, `a/s` or a comma list of those; month and
day-of-week also take names (`jan`, `mon`). Day-of-week 0 and 7 are Sunday. As in Vixie cron,
when both day fields are restricted a day matches if either does.

Daylight saving time: fire times are local wall-clock times. A time that does not exist on a
spring-forward day is skipped that day; a time that happens twice on a fall-back day fires once
(the slot key is the local wall-clock minute).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MONTHS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}
DAYS = {d: i for i, d in enumerate("sun mon tue wed thu fri sat".split())}
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")  # index = datetime.weekday()
_FIELDS = (("minute", 0, 59, {}), ("hour", 0, 23, {}), ("day of month", 1, 31, {}),
           ("month", 1, 12, MONTHS), ("day of week", 0, 7, DAYS))
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
BOX_TZ_NAMES = ("box", "local")


def resolve_tz(name: str | None, box_tz: str = "UTC") -> tzinfo:
    """A time zone by IANA name; `box`/`local`/None mean the box's zone. Raises ValueError."""
    if name is None or name in BOX_TZ_NAMES:
        name = box_tz
    if name in ("UTC", "Etc/UTC", "Z"):
        return UTC
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_+\-]*(/[A-Za-z0-9_+\-]+){0,2}", name or ""):
        raise ValueError(f"unknown time zone {name!r}")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"unknown time zone {name!r}") from None


def _value(token: str, lo: int, hi: int, names: dict[str, int], what: str) -> int:
    t = token.lower()
    if t in names:
        return names[t]
    if not t.isdigit():
        raise ValueError(f"cron {what}: {token!r} is not a number")
    v = int(t)
    if not lo <= v <= hi:
        raise ValueError(f"cron {what}: {v} is outside {lo}-{hi}")
    return v


def _field(text: str, what: str, lo: int, hi: int, names: dict[str, int]) -> frozenset[int]:
    out: set[int] = set()
    for part in text.split(","):
        base, _, step_s = part.partition("/")
        step = 1
        if step_s:
            if not step_s.isdigit() or int(step_s) < 1:
                raise ValueError(f"cron {what}: bad step in {part!r}")
            step = int(step_s)
        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a, _, b = base.partition("-")
            start, end = _value(a, lo, hi, names, what), _value(b, lo, hi, names, what)
            if start > end:
                raise ValueError(f"cron {what}: range {part!r} runs backwards")
        else:
            start = _value(base, lo, hi, names, what)
            end = hi if step_s else start
        out.update(range(start, end + 1, step))
    return frozenset(out)


@dataclass(frozen=True)
class Cron:
    expr: str
    minutes: frozenset[int]
    hours: frozenset[int]
    doms: frozenset[int]
    months: frozenset[int]
    dows: frozenset[int]
    dom_any: bool
    dow_any: bool

    @classmethod
    def parse(cls, expr: str) -> "Cron":
        if not isinstance(expr, str) or len(expr) > 200:
            raise ValueError("cron must be a string of at most 200 characters")
        parts = expr.split()
        if len(parts) != 5:
            raise ValueError("cron needs exactly 5 fields: minute hour day-of-month month day-of-week")
        sets = [_field(p, what, lo, hi, names) for p, (what, lo, hi, names) in zip(parts, _FIELDS)]
        dows = frozenset(0 if d == 7 else d for d in sets[4])
        return cls(" ".join(parts), sets[0], sets[1], sets[2], sets[3], dows,
                   parts[2] == "*", parts[4] == "*")

    def _day_ok(self, local: datetime) -> bool:
        dom = local.day in self.doms
        dow = (local.isoweekday() % 7) in self.dows
        if self.dom_any or self.dow_any:
            return dom and dow
        return dom or dow

    def matches(self, local: datetime) -> bool:
        return (local.minute in self.minutes and local.hour in self.hours
                and local.month in self.months and self._day_ok(local))

    def fire_times(self, tz: tzinfo, after: datetime, until: datetime) -> Iterator[tuple[datetime, str]]:
        """(UTC time, slot) of each fire with after < time <= until; the slot is the local minute.

        Walks UTC in 15-minute blocks (every real UTC offset is a multiple of 15 minutes, so a
        block is one contiguous local range inside one local hour) and looks inside a block only
        when its local month, day and hour can match.
        """
        t = after.astimezone(UTC).replace(second=0, microsecond=0) + timedelta(minutes=1)
        until = until.astimezone(UTC)
        seen: set[str] = set()
        while t <= until:
            block_end = t + timedelta(minutes=15 - t.minute % 15)
            local = t.astimezone(tz)
            if local.hour in self.hours and local.month in self.months and self._day_ok(local):
                m = t
                while m < block_end and m <= until:
                    lm = m.astimezone(tz)
                    if lm.minute in self.minutes:
                        slot = lm.replace(tzinfo=None).isoformat(timespec="minutes")
                        if slot not in seen:
                            seen.add(slot)
                            yield m, slot
                    m += timedelta(minutes=1)
            t = block_end

    def next_fire(self, tz: tzinfo, after: datetime, horizon_days: int = 366) -> datetime | None:
        for when, _ in self.fire_times(tz, after, after + timedelta(days=horizon_days)):
            return when
        return None


# ---- maintenance windows ------------------------------------------------------------------
@dataclass(frozen=True)
class WindowRange:
    days: frozenset[int]  # datetime.weekday() of the day the range starts
    start: int  # minutes after local midnight
    end: int  # end <= start means the range runs past midnight into the next day


def _minutes(hhmm: str) -> int:
    m = _HHMM.match(hhmm or "")
    if not m:
        raise ValueError(f"time {hhmm!r} must be HH:MM (24 h)")
    return int(m.group(1)) * 60 + int(m.group(2))


def parse_ranges(ranges: object) -> tuple[WindowRange, ...]:
    """Validate `[{days: [mon..sun], start: "HH:MM", end: "HH:MM"}]` (1 to 14 ranges)."""
    if not isinstance(ranges, list) or not 1 <= len(ranges) <= 14:
        raise ValueError("ranges must be a list of 1 to 14 entries")
    out = []
    for i, r in enumerate(ranges):
        if not isinstance(r, dict) or set(r) - {"days", "start", "end"}:
            raise ValueError(f"ranges[{i}] takes days, start and end")
        days = r.get("days") or list(WEEKDAYS)
        if not isinstance(days, list) or any(d not in WEEKDAYS for d in days):
            raise ValueError(f"ranges[{i}].days must be names from {', '.join(WEEKDAYS)}")
        start, end = _minutes(r.get("start")), _minutes(r.get("end"))
        if start == end:
            raise ValueError(f"ranges[{i}]: start and end are the same time")
        out.append(WindowRange(frozenset(WEEKDAYS.index(d) for d in days), start, end))
    return tuple(out)


def window_open(ranges: tuple[WindowRange, ...], tz: tzinfo, at: datetime) -> bool:
    local = at.astimezone(tz)
    m, wd = local.hour * 60 + local.minute, local.weekday()
    for r in ranges:
        if r.start < r.end:
            if wd in r.days and r.start <= m < r.end:
                return True
        elif (wd in r.days and m >= r.start) or ((wd - 1) % 7 in r.days and m < r.end):
            return True
    return False
