# SPDX-License-Identifier: Apache-2.0
"""Quick-add text and repeat rules for the work engine (no network, no database, pure functions).

`parse_quick_add("Pay rent every month #Home @bills p1 +ana", now)` returns the task fields the
words stand for, in the style of Todoist's quick add (a pattern, not its code):

    #Name project   @label   p1..p4 priority (p1 most urgent)   +person-id assignee
    today, tomorrow, monday, next fri, in 3 days, 2026-12-01, "at 5pm", "17:30"

Repeat rules ("every day", "every 2 weeks", "every weekday", "every month", "every year") come back as
`repeat`. "every monday" and /sections are left in the title rather than guessed at.

Dates are worked out in the caller's time zone (`tz`, an IANA name, default UTC) and returned in UTC.
A date with no time is "all day": it is due at the end of that local day.
"""

from __future__ import annotations

import calendar
import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_FULL_WD = "monday|tuesday|wednesday|thursday|friday|saturday|sunday"
_WD = "mon(?:day)?|tue(?:s|sday)?|wed(?:nesday)?|thu(?:rs|rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?"


def zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ValueError(f"unknown time zone {name!r}") from None


def _wd(word: str) -> int:
    w = word.lower()[:3]
    return [d[:3] for d in WEEKDAYS].index(w)


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


# ---- quick add ---------------------------------------------------------------------------------
def _take(rx: re.Pattern, text: str) -> tuple[re.Match | None, str]:
    m = rx.search(text)
    return (m, text[:m.start()] + " " + text[m.end():]) if m else (None, text)


def _rx(p: str) -> re.Pattern:
    return re.compile(r"(?<![\w@#/+])(?:" + p + r")(?![\w])", re.I)


_IN = _rx(r"in\s+(?P<n>\d{1,3})\s+(?P<unit>day|week|month)s?")
_EVERY = _rx(r"every\s+(?:(?P<n>\d{1,3})\s+)?(?P<unit>weekday|day|week|month|year)s?")
_ISO = _rx(r"(?P<d>\d{4}-\d{2}-\d{2})")
# A bare short word ("sat", "wed", "sun") is often a name or a verb, so it counts only after "next".
_NEXT_WD = _rx(rf"(?:next\s+(?P<wd>{_WD})|(?P<full>{_FULL_WD}))")
_REL = _rx(r"(?P<w>today|tomorrow|tonight)")
_TIME = _rx(r"(?:at\s+)?(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>am|pm)|(?:at\s+)?(?P<h24>[01]?\d|2[0-3]):(?P<m24>[0-5]\d)")
_PROJECT = re.compile(r"(?<![\w])#(?P<v>[\w-]{1,60})")
_LABEL = re.compile(r"(?<![\w])@(?P<v>[A-Za-z0-9_-]{1,40})")
_PRIO = re.compile(r"(?<![\w])p(?P<v>[1-4])(?![\w])", re.I)
_WHO = re.compile(r"(?<![\w])\+(?P<v>[\w:.-]{1,64})")


def next_due(due: datetime, repeat: dict, now: datetime) -> datetime:
    """The first occurrence of `repeat` after both `due` and `now`, keeping the local time of day.

    The days are counted in the rule's own zone (`repeat["tz"]`, an IANA name, default UTC), so "every
    weekday" skips the local weekend and a task due at 23:59 local stays at 23:59 across a DST change.
    """
    every, step = repeat["every"], repeat.get("interval", 1)
    z = zone(repeat.get("tz"))
    wall = due.astimezone(z).replace(tzinfo=None)
    for _ in range(5000):
        d = wall.date()
        if every == "day":
            d += timedelta(days=step)
        elif every == "week":
            d += timedelta(weeks=step)
        elif every == "month":
            d = add_months(d, step)
        elif every == "year":
            d = add_months(d, 12 * step)
        else:  # weekday: the next Monday-to-Friday
            d += timedelta(days=1)
            while d.weekday() > 4:
                d += timedelta(days=1)
        wall = datetime.combine(d, wall.time())
        nxt = wall.replace(tzinfo=z).astimezone(UTC)
        if nxt > due and nxt > now:
            return nxt
    raise ValueError("repeat rule did not reach the future")


def parse_quick_add(text: str, now: datetime, tz: str | None = None) -> dict:
    """Task fields from one line of text. Raises ValueError when nothing is left for a title."""
    z = zone(tz)
    local_now = now.astimezone(z)
    rest = " " + text.strip() + " "
    out: dict = {"repeat": None, "project": None, "labels": [], "priority": None, "assignee": None, "due_at": None,
                 "due_all_day": False}
    for key, rx in (("project", _PROJECT), ("assignee", _WHO)):
        m, rest = _take(rx, rest)
        if m:
            out[key] = m["v"]
    while (m := _LABEL.search(rest)):
        if m["v"] not in out["labels"]:
            out["labels"].append(m["v"])
        rest = rest[:m.start()] + " " + rest[m.end():]
    m, rest = _take(_EVERY, rest)
    if m:
        out["repeat"] = {"every": m["unit"].lower(), "interval": 1 if m["unit"].lower() == "weekday" else int(m["n"] or 1)}
        if tz:
            out["repeat"]["tz"] = z.key
    m, rest = _take(_PRIO, rest)
    if m:
        out["priority"] = int(m["v"])

    day: date | None = None
    m, rest = _take(_ISO, rest)
    if m:
        try:
            day = date.fromisoformat(m["d"])
        except ValueError:
            raise ValueError(f"{m['d']} is not a date") from None
    if day is None:
        m, rest = _take(_IN, rest)
        if m:
            n = int(m["n"])
            day = local_now.date() + (timedelta(days=n) if m["unit"].lower() == "day" else
                                      timedelta(weeks=n) if m["unit"].lower() == "week" else timedelta(0))
            if m["unit"].lower() == "month":
                day = add_months(local_now.date(), n)
    if day is None:
        m, rest = _take(_REL, rest)
        if m:
            day = local_now.date() + timedelta(days=1 if m["w"].lower().startswith("tom") else 0)
    if day is None:
        m, rest = _take(_NEXT_WD, rest)
        if m:
            ahead = (_wd(m["wd"] or m["full"]) - local_now.weekday()) % 7 or 7
            day = local_now.date() + timedelta(days=ahead)
    at: time | None = None
    m, rest = _take(_TIME, rest)
    if m:
        if m["ap"]:
            h, mi = int(m["h"]), int(m["m"] or 0)
            if not 1 <= h <= 12 or mi > 59:
                raise ValueError("that time is not valid")
            at = time(h % 12 + (12 if m["ap"].lower() == "pm" else 0), mi)
        else:
            at = time(int(m["h24"]), int(m["m24"]))
    if out["repeat"] and day is None and at is None:
        day = local_now.date()
    if at is not None and day is None:
        day = local_now.date() + timedelta(days=0 if at > local_now.time() else 1)
    if day is not None:
        local = datetime.combine(day, at or time(23, 59, 59), tzinfo=z)
        out["due_at"], out["due_all_day"] = local.astimezone(UTC), at is None
    title = " ".join(rest.split())
    if not title:
        raise ValueError("a task needs a title")
    out["title"] = title
    return out
