# SPDX-License-Identifier: Apache-2.0
"""Quick-add text and repeat rules for the work engine (no network, no database, pure functions).

`parse_quick_add("Pay rent every month #Home @bills p1 +ana", now)` returns the task fields the
words stand for, in the style of Todoist's quick add (a pattern, not its code):

    #Name project   /Name section   @label   p1..p4 priority (p1 most urgent)   +name assignee
    today, tomorrow, monday, next friday, in 3 days, 2026-12-01, "at 5pm", "17:30"
    every day, every weekday, every monday, every 2 weeks, every month, every year

Dates are worked out in the caller's time zone (`tz`, an IANA name, default UTC) and returned in UTC.
A date with no time is "all day": it is due at the end of that local day.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from datetime import UTC

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_DAY_CODES = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
_FREQS = ("DAILY", "WEEKLY", "MONTHLY", "YEARLY")
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


# ---- repeat rules ------------------------------------------------------------------------------
def check_rrule(rule: str) -> str:
    """Accept only FREQ, INTERVAL and (weekly) BYDAY; returns the canonical text or raises ValueError."""
    parts: dict[str, str] = {}
    for item in rule.strip().upper().split(";"):
        k, sep, v = item.partition("=")
        if not sep or k in parts or k not in ("FREQ", "INTERVAL", "BYDAY"):
            raise ValueError("repeat rule: only FREQ, INTERVAL and BYDAY are supported")
        parts[k] = v
    if parts.get("FREQ") not in _FREQS:
        raise ValueError("repeat rule: FREQ must be DAILY, WEEKLY, MONTHLY or YEARLY")
    interval = parts.get("INTERVAL", "1")
    if not interval.isdigit() or not 1 <= int(interval) <= 99:
        raise ValueError("repeat rule: INTERVAL is 1 to 99")
    out = f"FREQ={parts['FREQ']};INTERVAL={int(interval)}"
    if "BYDAY" in parts:
        days = parts["BYDAY"].split(",")
        if parts["FREQ"] != "WEEKLY" or not days or any(d not in _DAY_CODES for d in days):
            raise ValueError("repeat rule: BYDAY is a list of MO..SU and only goes with FREQ=WEEKLY")
        out += ";BYDAY=" + ",".join(sorted(set(days), key=_DAY_CODES.index))
    return out


def next_due(rule: str, after: datetime) -> datetime:
    """The next occurrence after `after` (a local, timezone-aware time), keeping its time of day."""
    p = dict(i.split("=") for i in check_rrule(rule).split(";"))
    n, d = int(p["INTERVAL"]), after.date()
    if p["FREQ"] == "DAILY":
        nd = d + timedelta(days=n)
    elif p["FREQ"] == "WEEKLY" and "BYDAY" in p:
        days = sorted(_DAY_CODES.index(c) for c in p["BYDAY"].split(","))
        later = [x for x in days if x > d.weekday()]
        nd = d + timedelta(days=later[0] - d.weekday()) if later else (
            d - timedelta(days=d.weekday()) + timedelta(weeks=n, days=days[0]))
    elif p["FREQ"] == "WEEKLY":
        nd = d + timedelta(weeks=n)
    elif p["FREQ"] == "MONTHLY":
        nd = add_months(d, n)
    else:
        nd = add_months(d, 12 * n)
    return datetime.combine(nd, after.timetz().replace(tzinfo=None), tzinfo=after.tzinfo)


def describe_rrule(rule: str) -> str:
    p = dict(i.split("=") for i in check_rrule(rule).split(";"))
    unit = {"DAILY": "day", "WEEKLY": "week", "MONTHLY": "month", "YEARLY": "year"}[p["FREQ"]]
    n = int(p["INTERVAL"])
    base = f"every {unit}" if n == 1 else f"every {n} {unit}s"
    return base + (" on " + ", ".join(WEEKDAYS[_DAY_CODES.index(c)] for c in p["BYDAY"].split(",")) if "BYDAY" in p else "")


# ---- quick add ---------------------------------------------------------------------------------
def _take(rx: re.Pattern, text: str) -> tuple[re.Match | None, str]:
    m = rx.search(text)
    return (m, text[:m.start()] + " " + text[m.end():]) if m else (None, text)


def _rx(p: str) -> re.Pattern:
    return re.compile(r"(?<![\w@#/+])(?:" + p + r")(?![\w])", re.I)


_EVERY = _rx(rf"every\s+(?:(?P<n>\d{{1,2}})\s+(?P<unit>day|week|month|year)s?|(?P<word>day|daily|weekday|weekdays|week|month|year|(?:(?:{_WD})(?:\s*(?:,|and)\s*(?:{_WD}))*)))")
_IN = _rx(r"in\s+(?P<n>\d{1,3})\s+(?P<unit>day|week|month)s?")
_ISO = _rx(r"(?P<d>\d{4}-\d{2}-\d{2})")
_NEXT_WD = _rx(rf"(?:next\s+)?(?P<wd>{_WD})")
_REL = _rx(r"(?P<w>today|tod|tomorrow|tom|tonight)")
_TIME = _rx(r"(?:at\s+)?(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>am|pm)|(?:at\s+)?(?P<h24>[01]?\d|2[0-3]):(?P<m24>[0-5]\d)")
_PROJECT = re.compile(r"(?<![\w])#(?P<v>[\w-]{1,60})")
_SECTION = re.compile(r"(?<![\w/])/(?P<v>[\w-]{1,60})(?![\w/])")
_LABEL = re.compile(r"(?<![\w])@(?P<v>[A-Za-z0-9_-]{1,40})")
_PRIO = re.compile(r"(?<![\w])p(?P<v>[1-4])(?![\w])", re.I)
_WHO = re.compile(r"(?<![\w])\+(?P<v>[\w:.-]{1,64})")


def parse_quick_add(text: str, now: datetime, tz: str | None = None) -> dict:
    """Task fields from one line of text. Raises ValueError when nothing is left for a title."""
    z = zone(tz)
    local_now = now.astimezone(z)
    rest = " " + text.strip() + " "
    out: dict = {"project": None, "section": None, "labels": [], "priority": None, "assignee": None,
                 "due_at": None, "due_all_day": False, "rrule": None}
    for key, rx in (("project", _PROJECT), ("section", _SECTION), ("assignee", _WHO)):
        m, rest = _take(rx, rest)
        if m:
            out[key] = m["v"]
    while (m := _LABEL.search(rest)):
        if m["v"] not in out["labels"]:
            out["labels"].append(m["v"])
        rest = rest[:m.start()] + " " + rest[m.end():]
    m, rest = _take(_PRIO, rest)
    if m:
        out["priority"] = int(m["v"])

    day: date | None = None
    m, rest = _take(_EVERY, rest)
    if m:
        w = (m["word"] or "").lower()
        if m["n"]:
            rule = f"FREQ={m['unit'].upper()}LY;INTERVAL={int(m['n'])}".replace("DAYLY", "DAILY")
        elif w in ("day", "daily"):
            rule = "FREQ=DAILY;INTERVAL=1"
        elif w in ("weekday", "weekdays"):
            rule = "FREQ=WEEKLY;INTERVAL=1;BYDAY=MO,TU,WE,TH,FR"
        elif w in ("week", "month", "year"):
            rule = f"FREQ={w.upper()}LY;INTERVAL=1"
        else:
            rule = "FREQ=WEEKLY;INTERVAL=1;BYDAY=" + ",".join(_DAY_CODES[_wd(x)] for x in re.findall(_WD, w, re.I))
        out["rrule"] = check_rrule(rule)
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
            ahead = (_wd(m["wd"]) - local_now.weekday()) % 7 or 7
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
    if out["rrule"] and day is None:  # "every monday": the first one from now
        first = datetime.combine(local_now.date(), time(0), tzinfo=z)
        day = next_due(out["rrule"], first).date() if "BYDAY" in out["rrule"] else local_now.date()
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
