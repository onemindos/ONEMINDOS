# SPDX-License-Identifier: Apache-2.0
"""FD-01 (#498, D-018): `GET /v1/status`, the one "needs attention" answer for the Front Door.

Seven sources (alerts, approvals, apps, storage, backups, updates, mesh) each report
`state` (ok | attention | critical | unknown) and `observed_at`. The contract is one rule:
a source that cannot be read is `unknown` with `observed_at: null`, never `ok`. Every source is
read on its own, so one broken reader cannot hide or fake another. Failure text is logged, never
sent to the client (it can hold paths and addresses). Nothing here changes anything.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from .ledger import iso
from .notify.store import NotifyRepository

log = logging.getLogger("onemind.status")

State = Literal["ok", "attention", "critical", "unknown"]
# What the overall state shows when sources disagree: a known problem outranks a blind spot, and a
# blind spot outranks "ok".
_RANK = {"ok": 0, "unknown": 1, "attention": 2, "critical": 3}


class SourceStatus(BaseModel):
    state: State
    observed_at: str | None  # when the gateway read the source; null when it could not
    summary: str
    count: int | None = None  # how many things need attention, where that is a number


class StatusView(BaseModel):
    state: State
    observed_at: str
    alerts: SourceStatus
    approvals: SourceStatus
    apps: SourceStatus
    storage: SourceStatus
    backups: SourceStatus
    updates: SourceStatus
    mesh: SourceStatus


class Unreadable(Exception):
    """A source answered, but not with a verdict (off, not wired, nothing reported yet)."""


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def read_alerts(gw, state) -> tuple[State, str, int | None]:
    sev = NotifyRepository(gw.db).open_alert_counts()
    crit, warn = sev.get("critical", 0), sev.get("warning", 0)
    if crit:
        return "critical", f"{_plural(crit, 'critical alert', 'critical alerts')}, {warn} warning", crit + warn
    if warn:
        return "attention", _plural(warn, "warning", "warnings"), warn
    return "ok", "no open alerts", 0


def read_approvals(gw, state) -> tuple[State, str, int | None]:
    n = sum(1 for a in gw.actions.list() if a["state"] == "awaiting_approval")
    if n:
        return "attention", f"{_plural(n, 'change waits', 'changes wait')} for approval", n
    return "ok", "nothing waits for approval", 0


def read_apps(gw, state) -> tuple[State, str, int | None]:
    mon = state.monitoring
    installed = mon.installed_apps()
    seen = mon.app_states()
    states = [seen.get(a, "unknown") for a in installed]
    bad = sum(1 for s in states if s == "unhealthy")
    blind = sum(1 for s in states if s == "unknown")
    if bad:
        return "critical", f"{_plural(bad, 'app is', 'apps are')} unhealthy", bad
    if blind:
        return "unknown", f"health of {_plural(blind, 'app is', 'apps are')} not known", blind
    return "ok", (f"{len(installed)} installed, none unhealthy" if installed else "no apps installed"), 0


def read_storage(gw, state) -> tuple[State, str, int | None]:
    s = state.storage.summary()
    if not s.get("enabled"):
        raise Unreadable("the storage service is not enabled on this box")
    if not s.get("available"):
        raise Unreadable("the storage service did not answer")
    mirror = s.get("state")
    if mirror in ("degraded", "unavailable", "unsupported"):
        return "critical", f"the data set is {mirror}", 1
    if mirror == "unprotected" or s.get("needs_scrub"):
        return "attention", "the data set is not fully protected" if mirror == "unprotected" else "a scrub is due", 1
    if mirror == "protected":
        return "ok", "the data set is protected", 0
    raise Unreadable("the storage service reported no data-set state")


def read_backups(gw, state) -> tuple[State, str, int | None]:
    b = state.backups.status()
    health = b.get("health")
    reason = b.get("reason") or ""
    if health == "ok":
        return "ok", "backups are current", 0
    if health == "failing":
        return "critical", "backups are failing", 1
    if health in ("stale", "not_configured"):
        return "attention", reason or ("backups are out of date" if health == "stale" else "backups are not set up"), 1
    raise Unreadable("backups reported no health")


def read_updates(gw, state) -> tuple[State, str, int | None]:
    nodes = [n for n in state.osupdate.status()["nodes"] if n["reported"]]
    if not nodes:
        raise Unreadable("no node has reported its update state")
    due = [n for n in nodes if n["state"] in ("error", "rolled_back")
           or (n["available_version"] and n["available_version"] != n["current_version"])]
    unknown = [n for n in nodes if n["state"] == "unknown"]
    if due:
        return "attention", f"{_plural(len(due), 'node needs', 'nodes need')} an update or a look", len(due)
    if unknown:
        raise Unreadable("a node reported an update state the gateway does not know")
    return "ok", "every reporting node is up to date", 0


def read_mesh(gw, state) -> tuple[State, str, int | None]:
    mesh = getattr(state, "mesh", None)
    if mesh is None:
        return "ok", "the mesh is not enabled on this box", 0
    mesh.client.list_nodes()  # raises when the control server cannot be reached
    return "ok", "the mesh control server answers", 0


SOURCES: dict[str, Callable] = {
    "alerts": read_alerts, "approvals": read_approvals, "apps": read_apps, "storage": read_storage,
    "backups": read_backups, "updates": read_updates, "mesh": read_mesh,
}


def read_source(name: str, gw, state) -> SourceStatus:
    """One source's verdict. Anything that goes wrong becomes `unknown`, never `ok`."""
    try:
        verdict, summary, count = SOURCES[name](gw, state)
    except Unreadable as exc:
        return SourceStatus(state="unknown", observed_at=None, summary=str(exc))
    except Exception:  # a failing reader must not take the whole endpoint down, or read as fine
        log.exception("status source %s could not be read", name)
        return SourceStatus(state="unknown", observed_at=None, summary=f"the {name} source could not be read")
    return SourceStatus(state=verdict, observed_at=iso(gw.clock()), summary=summary, count=count)


def build_status(gw, state) -> StatusView:
    parts = {name: read_source(name, gw, state) for name in SOURCES}
    worst = max((p.state for p in parts.values()), key=_RANK.__getitem__)
    return StatusView(state=worst, observed_at=iso(gw.clock()), **parts)
