# SPDX-License-Identifier: Apache-2.0
"""What the gateway does for backups (contract §12.12; BACKUPS.md §3, §5, §7, §8).

One run: list each installed app's volumes, dump its database from the shared PostgreSQL, run its
`backup.pre` hooks inside its own container (stopping it first for `mode: cold`), send one signed
`backup.run` job, then run the `post` hooks and start cold apps again. An app whose preparation
fails is left out of that run (its unit is reported failed) instead of being copied inconsistently.

One app restore (an approved `backup.restore`): a pre-restore run of the app (the undo point), stop
the app, swap its volumes and database dump in from the snapshot (the agent keeps the live data
aside), recreate the database from the dump, start the app and wait for pods created after the
restore to be ready three times in a row. Pass: the agent deletes the old data. Fail: the old data
and database come back and the restore ends `failed`, never `succeeded`.

Long work runs on one worker thread, in order, so a restore never overlaps a backup.
"""

from __future__ import annotations

import hashlib
import logging
import queue
import secrets
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from ..actions import FeatureAction
from ..catalog import AppEntry
from ..context import Gateway
from ..errors import ApiError
from ..executors import ExecResult
from ..ledger import Action, iso, utc
from .jobs import AgentClient, AgentError, load_or_create_job_key
from .kit import answer_ok, challenge, kit_text, new_owner_key
from .kube import DryKube, Kube, KubeError, Workload
from .manifest import BackupSpec, backup_spec, database_spec
from .settings import BackupsSettings
from .store import (
    SCHEMA,  # noqa: F401  (importing the module registers the tables)
    BackupsRepository,
    DestinationRow,
    KitRow,
    RestoreRow,
    RunRow,
    destination_json,
    restore_json,
    run_json,
)

log = logging.getLogger("onemind.backups")

AGENT_KIND = {"usb": "usb", "box": "node", "rest": "node", "s3": "s3"}


class Unavailable(Exception):
    """Contract §12.2 `unavailable` (503): backups are off or the agent cannot be reached."""

    def __init__(self, message: str, reason: str):
        super().__init__(message)
        self.message, self.reason = message, reason


class Worker:
    """One background thread; jobs run one at a time in the order they were submitted."""

    def __init__(self, inline: bool = False):
        self.inline = inline
        self._q: queue.Queue = queue.Queue()
        self._t: threading.Thread | None = None
        self._lock = threading.Lock()

    def submit(self, fn: Callable[[], None]) -> None:
        if self.inline:
            fn()
            return
        with self._lock:
            if self._t is None or not self._t.is_alive():
                self._t = threading.Thread(target=self._loop, name="onemind-backups", daemon=True)
                self._t.start()
        self._q.put(fn)

    def _loop(self) -> None:
        while True:
            fn = self._q.get()
            try:
                if fn is None:
                    return
                fn()
            except Exception:
                log.exception("backup job crashed")
            finally:
                self._q.task_done()

    def wait_idle(self) -> None:
        self._q.join()

    def stop(self) -> None:
        if self._t is not None and self._t.is_alive():
            self._q.put(None)


def new_run_id(now: datetime) -> str:
    return "run_" + utc(now).strftime("%Y%m%dT%H%M%SZ") + "_" + secrets.token_hex(3)


def _ts(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class BackupService:
    def __init__(self, gw: Gateway, settings: BackupsSettings, *, pg=None, kube: Kube | None = None,
                 agent: AgentClient | None = None, inline: bool = False):
        self.gw = gw
        self.s = settings
        self.repo = BackupsRepository(gw.db)
        real = gw.executor.name == "kubernetes"
        self.kube = kube or (Kube(gw.settings.kubectl, gw.settings.executor_timeout_s) if real else DryKube())
        self.pg = pg
        self.agent = agent
        if self.agent is None and settings.enabled:
            key_file = settings.job_key_file or (gw.settings.audit_path.parent / "custodian" / "job.key")
            self.agent = AgentClient(settings.agent_url, load_or_create_job_key(Path(key_file)), gw.clock,
                                     settings.job_timeout_s)
        self.worker = Worker(inline)
        self._pending_secrets: dict[str, dict] = {}  # action id -> destination credentials (memory only)
        self._one_time: dict[str, dict] = {}
        self._stop = threading.Event()
        self._last_slot: datetime | None = None
        acts = gw.actions
        acts.register_type("backup.run", FeatureAction("write", self._act_run, frozenset({"person", "agent"})))
        acts.register_type("backup.verify", FeatureAction("write", self._act_verify, frozenset({"person", "agent"})))
        # Agents may request a restore only with an explicit grant (§12.5); v0 has no grants.
        acts.register_type("backup.restore", FeatureAction("destructive", self._act_restore, check=self._check_restore))
        acts.register_type("backup.destination.add", FeatureAction("sensitive", self._act_dest_add))
        acts.register_type("backup.destination.remove", FeatureAction("destructive", self._act_dest_remove))
        acts.register_type("backup.kit.issue", FeatureAction("sensitive", self._act_kit_issue))

    # ---- plumbing ---------------------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return self.agent is not None

    def _agent(self) -> AgentClient:
        if self.agent is None:
            raise Unavailable("backups are not switched on (ONEMIND_BACKUPS_ENABLED=1)", "backups_disabled")
        return self.agent

    def _job(self, kind: str, params: dict, action_id: str | None = None) -> object:
        try:
            return self._agent().job(kind, params, action_id=action_id)
        except AgentError as e:
            if e.reason == "agent_unreachable":
                raise Unavailable(str(e), "target_unreachable") from None
            raise

    def _event(self, name: str, payload: dict, severity: str = "info", domain: str = "backup", **kw) -> None:
        try:
            self.gw.events.publish_event(domain, name, payload, severity=severity, **kw)
        except Exception:
            log.exception("could not publish %s.%s", domain, name)

    def startup(self) -> None:
        now = self.gw.clock()
        if n := self.repo.fail_unfinished_runs(now):
            log.warning("%d backup runs were interrupted by a restart", n)
        for r in self.repo.restores():
            if r.state == "running":
                self.repo.update_restore(r.id, state="outcome_unknown", finished_at=utc(now),
                                         error="the gateway restarted during the restore; check the app and its data")
        if self.enabled and self.s.schedule:
            threading.Thread(target=self._schedule_loop, name="onemind-backup-schedule", daemon=True).start()

    def shutdown(self) -> None:
        self._stop.set()
        self.worker.stop()

    def installed_apps(self) -> list[AppEntry]:
        states = self.gw.repo.list_app_states()
        catalog = self.gw.catalog.load()
        return [catalog[i] for i, st in sorted(states.items()) if st.status == "installed" and i in catalog]

    # ---- schedule (the system policy that owns hourly runs) ------------------------------------
    def run_minute(self) -> int:
        if self.s.minute >= 0:
            return self.s.minute
        box = self.gw.settings.node_id or "box"
        h = hashlib.sha256(("onemind-backup-minute:" + box).encode()).digest()
        return int.from_bytes(h[:4], "big") % 60

    def slot(self, now: datetime) -> datetime:
        m = self.run_minute()
        s = now.replace(minute=m, second=0, microsecond=0)
        return s if s <= now else s - timedelta(hours=1)

    def next_run_at(self, now: datetime) -> datetime | None:
        return self.slot(now) + timedelta(hours=1) if self.enabled and self.s.schedule else None

    def schedule_tick(self) -> bool:
        """Submit the hourly run when its slot has come. Returns True when one was submitted."""
        now = self.gw.clock()
        slot = self.slot(now)
        if self._last_slot is None:  # first tick: catch up only if the last hour has no run
            last = next((r for r in self.repo.runs(20) if r.reason == "scheduled"), None)
            self._last_slot = slot if last is not None and utc(last.started_at) >= slot else slot - timedelta(hours=1)
        if slot <= self._last_slot or not self.repo.destinations():
            return False
        self._last_slot = slot
        self.gw.audit.append("backup.schedule.fired", None, None,
                             {"approved_by": "policy:backup-schedule@1", "slot": iso(slot)})
        self.worker.submit(lambda: self.run_backup("scheduled", "box", None, None))
        return True

    def _schedule_loop(self) -> None:
        while not self._stop.wait(30):
            try:
                self.schedule_tick()
            except Exception:
                log.exception("backup schedule tick failed")

    # ---- runs -------------------------------------------------------------------------------
    def _app_volumes(self, app: AppEntry, spec: BackupSpec) -> tuple[dict | None, str | None]:
        """The agent's view of one app: {id, volumes, files, volume_sqlite, excludes}, or None."""
        try:
            pvcs = [p for p in self.kube.pvcs(f"app-{app.id}") if p.get("volume")]
        except KubeError as e:
            return None, f"cannot list the app's volumes: {e}"
        entry: dict = {"id": app.id, "volumes": [{"namespace": f"app-{app.id}", "claim": p["claim"], "volume": p["volume"]}
                                                 for p in pvcs]}
        claims = {p["claim"]: p["volume"] for p in pvcs}
        sq = [{"namespace": f"app-{app.id}", "claim": c, "volume": claims[c], "path": path}
              for c, path in spec.sqlite if c in claims]
        if sq:
            entry["volume_sqlite"] = sq
        if spec.exclude:
            entry["excludes"] = list(spec.exclude)
        if database_spec(app) is not None and self.pg is not None:
            try:
                entry["files"] = [self.pg.dump_file(app.id)]
            except KubeError as e:
                return None, f"the shared database volume is not available: {e}"
        if not entry["volumes"] and not entry.get("files"):
            return None, None
        return entry, None

    def _exec_hooks(self, app: AppEntry, hooks, phase: str, log_: list[dict]) -> str | None:
        ns = f"app-{app.id}"
        for h in hooks:
            rec = {"app_id": app.id, "phase": phase, "command": h.command[0], "container": h.container}
            try:
                pod = self.kube.running_pod(ns, h.container)
                self.kube.exec(ns, pod, list(h.command), container=h.container, timeout=h.timeout_s)
                rec["ok"] = True
            except KubeError as e:
                rec.update(ok=False, error=str(e)[:300])
                log_.append(rec)
                return f"{phase} hook {h.command[0]} failed: {e}"
            log_.append(rec)
        return None

    def run_backup(self, reason: str, scope: str | dict, destination_id: str | None, action_id: str | None) -> dict:
        now = self.gw.clock()
        run_id = new_run_id(now)
        self.repo.add_run(RunRow(id=run_id, action_id=action_id, reason=reason, destination_id=destination_id,
                                 state="running", started_at=utc(now), units=[], hooks=[]))
        only = scope.get("app_id") if isinstance(scope, dict) else None
        hooks: list[dict] = []
        failed: dict[str, str] = {}
        apps: list[dict] = []
        cold: list[tuple[AppEntry, list[Workload]]] = []
        state, error, units, added = "failed", None, [], None
        try:
            for app in self.installed_apps():
                spec = backup_spec(app)
                entry, problem = self._app_volumes(app, spec)
                if entry is None:
                    if problem and (only is None or only == app.id):
                        failed[f"app:{app.id}"] = problem
                    continue
                apps.append(entry)
                if only is not None and only != app.id:
                    continue
                unit = f"app:{app.id}"
                problem = self._exec_hooks(app, spec.pre, "pre", hooks)
                if problem is None and database_spec(app) is not None and self.pg is not None:
                    try:
                        self.pg.dump(app.id)
                        hooks.append({"app_id": app.id, "phase": "pre", "command": "pg_dump", "ok": True})
                    except KubeError as e:
                        problem = f"database dump failed: {e}"
                        hooks.append({"app_id": app.id, "phase": "pre", "command": "pg_dump", "ok": False,
                                      "error": str(e)[:300]})
                if problem is None and spec.mode == "cold":
                    try:
                        ws = self.kube.workloads(f"app-{app.id}")
                        for w in ws:
                            self.kube.scale(f"app-{app.id}", w, 0)
                        cold.append((app, ws))
                        self.kube.wait_no_pods(f"app-{app.id}", 120)
                    except KubeError as e:
                        problem = f"could not stop the app for a cold copy: {e}"
                if problem:
                    failed[unit] = problem
            if only is not None and f"app:{only}" not in failed and not any(a["id"] == only for a in apps):
                failed[f"app:{only}"] = "the app is not installed or has no volumes or database"
            params: dict = {"reason": reason, "run_id": run_id, "apps": apps}
            if destination_id:
                params["target_id"] = destination_id
            if only is not None:
                params["units"] = [f"app:{only}"]
            elif failed:
                params["skip_units"] = sorted(failed)
            if only is None or f"app:{only}" not in failed:
                result = self._job("backup.run", params, action_id) or {}
                state, error = result.get("state", "failed"), result.get("error") or None
                units, added = result.get("units") or [], result.get("bytes_added")
                destination_id = destination_id or result.get("target_id")
        except (AgentError, Unavailable) as e:
            error = str(e)
        finally:
            for app, ws in cold:
                for w in ws:
                    try:
                        self.kube.scale(f"app-{app.id}", w, w.replicas)
                    except KubeError as e:
                        hooks.append({"app_id": app.id, "phase": "post", "command": "scale", "ok": False, "error": str(e)[:300]})
            for app in self.installed_apps():
                if (only is None or only == app.id) and f"app:{app.id}" not in failed:
                    self._exec_hooks(app, backup_spec(app).post, "post", hooks)
        units = units + [{"unit": u, "state": "failed", "error": msg} for u, msg in sorted(failed.items())]
        if failed and state == "succeeded":
            state = "partial"
        elif failed and only is not None:
            state, error = "failed", error or failed.get(f"app:{only}")
        self.repo.update_run(run_id, state=state, finished_at=utc(self.gw.clock()), units=units, hooks=hooks,
                             bytes_added=added, error=error, destination_id=destination_id)
        row = self.repo.run(run_id)
        sev = {"succeeded": "info", "partial": "warning"}.get(state, "error")
        self._event("run.finished", {"run_id": run_id, "reason": reason, "state": state,
                                     "failed_units": [u["unit"] for u in units if u.get("state") != "succeeded"]},
                    severity=sev, action_id=action_id, dedupe_key=None if state == "succeeded" else "backup:run:failing")
        return run_json(row)

    def _act_run(self, a: Action, finish: Callable[[ExecResult], None]) -> None:
        def work() -> None:
            p = a.params
            run = self.run_backup("manual", p.get("scope", "box"), p.get("destination_id"), a.id)
            ok = run["state"] == "succeeded"
            finish(ExecResult("succeeded" if ok else "failed",
                              f"backup run {run['id']} {run['state']}" + (f": {run['error']}" if run.get("error") else ""),
                              [{"run_id": run["id"], "state": run["state"]}]))
        self.worker.submit(work)

    # ---- verify -----------------------------------------------------------------------------
    def _act_verify(self, a: Action, finish: Callable[[ExecResult], None]) -> None:
        def work() -> None:
            p = a.params
            params = {"mode": "check" if p.get("mode") == "check" else "restore", "latest": True}
            if p.get("units"):
                params["units"] = p["units"]
            try:
                out = self._job("backup.verify", params, a.id) or []
            except (AgentError, Unavailable) as e:
                self._event("verify.finished", {"result": "error", "error": str(e)[:300]}, severity="error", action_id=a.id)
                finish(ExecResult("failed", str(e)))
                return
            bad = [v for v in out if v.get("verdict") != "passed"]
            self._event("verify.finished", {"result": "fail" if bad else "pass", "units": [v.get("unit") for v in out]},
                        severity="error" if bad else "info", action_id=a.id)
            finish(ExecResult("failed" if bad else "succeeded",
                              f"{len(out) - len(bad)} of {len(out)} verified",
                              [{"unit": v.get("unit"), "verdict": v.get("verdict"), "snapshot_id": v.get("snapshot_id")} for v in out]))
        self.worker.submit(work)

    # ---- status, runs, snapshots --------------------------------------------------------------
    def kit_state(self) -> dict:
        k = self.repo.kit()
        if k is None:
            return {"state": "missing", "issued_at": None, "confirmed_at": None, "fingerprint": None, "positions": []}
        return {"state": k.state, "issued_at": iso(k.issued_at), "confirmed_at": iso(k.confirmed_at),
                "fingerprint": k.fingerprint, "positions": k.challenge.get("positions", [])}

    def _agent_status(self) -> dict:
        return self._job("backup.status", {}) or {}

    def status(self) -> dict:
        now = self.gw.clock()
        dests = [destination_json(d) for d in self.repo.destinations()]
        kit = self.kit_state()
        out = {"health": "not_configured", "reason": None, "last_success_at": None, "last_verified_restore_at": None,
               "next_run_at": iso(self.next_run_at(now)), "copies": len(dests),
               "badges": {"box": {"state": "none"}, "system": {"state": "none"}, "apps": {}},
               "destinations": dests, "kit": kit, "crash_consistent_apps": [],
               "setup": {"blocking": [] if kit["state"] == "confirmed" else ["emergency_kit"]}, "agent": "off"}
        installed = self.installed_apps()
        out["crash_consistent_apps"] = [a.id for a in installed if not backup_spec(a).declared]
        if not self.enabled:
            out["reason"] = "backups are not switched on"
            return out
        try:
            st = self._agent_status()
        except (Unavailable, AgentError) as e:
            out.update(health="failing", reason=str(e), agent="unreachable")
            return out
        out["agent"] = "ok"
        s = st.get("status") or {}
        units = s.get("units") or {}
        apps = {}
        for name, b in units.items():
            if name.startswith("app:"):
                apps[name[4:]] = b
        out["badges"] = {"box": s.get("box") or {"state": "none"}, "system": units.get("system") or {"state": "none"},
                         "apps": apps}
        succ = [t for t in (_ts(b.get("last_success_at")) for b in units.values()) if t]
        ver = [t for t in (_ts(v.get("finished_at")) for v in (s.get("last_verified") or {}).values()) if t]
        out["last_success_at"] = iso(max(succ)) if succ else None
        out["last_verified_restore_at"] = iso(max(ver)) if ver else None
        box = out["badges"]["box"].get("state")
        if not dests:
            out["reason"] = "no backup destination yet"
        elif box == "failing":
            out.update(health="failing", reason=out["badges"]["box"].get("reason"))
        elif box in ("stale", "none"):
            out.update(health="stale", reason=out["badges"]["box"].get("reason") or "no backup yet")
        else:
            out["health"] = "ok"
        if s.get("fenced"):
            out.update(health="failing", reason="this box was replaced by a restore; backups stopped")
        return out

    def destinations(self) -> list[dict]:
        return [destination_json(d) for d in self.repo.destinations()]

    def runs(self) -> list[dict]:
        return [run_json(r) for r in self.repo.runs()]

    def run(self, run_id: str) -> dict:
        r = self.repo.run(run_id)
        if r is None:
            raise ApiError(404, "not_found", "no such run")
        return run_json(r)

    def verifications(self) -> list[dict]:
        out = []
        for v in reversed((self._agent_status() or {}).get("verifications") or []):
            verdict = v.get("verdict")
            out.append({"id": v.get("id"), "snapshot_id": v.get("snapshot_id"), "unit": v.get("unit"),
                        "destination_id": v.get("target_id"),
                        "mode": "scratch_restore" if v.get("kind") == "restore" else "check",
                        "result": {"passed": "pass", "failed": "fail"}.get(verdict, "error"),
                        "probes": v.get("details") or {}, "started_at": v.get("started_at"),
                        "finished_at": v.get("finished_at")})
        return out

    def snapshots(self, app_id: str | None = None, unit: str | None = None) -> list[dict]:
        if app_id:
            unit = f"app:{app_id}"
        params = {"unit": unit} if unit else {}
        snaps = self._job("backup.snapshots", params) or []
        verified = {}
        try:
            for name, v in ((self._agent_status().get("status") or {}).get("last_verified") or {}).items():
                verified[v.get("snapshot_id")] = v.get("finished_at")
        except (Unavailable, AgentError):
            pass
        return [{"id": s["id"], "short_id": s.get("short_id"), "unit": s.get("unit"), "app_id": s.get("app_id") or None,
                 "node_id": s.get("node_id"), "destination_id": None, "taken_at": s.get("taken_at"),
                 "size_bytes": None, "reason": s.get("reason"), "run_id": s.get("run_id"), "tags": s.get("tags") or [],
                 "paths": s.get("paths") or [], "verified_at": verified.get(s["id"])} for s in snaps]

    def snapshot(self, snapshot_id: str) -> dict:
        for s in self.snapshots():
            if s["id"] == snapshot_id or (len(snapshot_id) >= 8 and s["id"].startswith(snapshot_id)):
                return s
        raise ApiError(404, "not_found", "no such snapshot")

    def tree(self, snapshot_id: str, path: str) -> list[dict]:
        try:
            return self._job("backup.tree", {"snapshot_id": snapshot_id, "path": path or "/"}) or []
        except AgentError as e:
            raise ApiError(404, "not_found", str(e)) from None

    def file(self, snapshot_id: str, path: str):
        try:
            return self._agent().file({"snapshot_id": snapshot_id, "path": path})
        except AgentError as e:
            if e.reason == "agent_unreachable":
                raise Unavailable(str(e), "target_unreachable") from None
            raise ApiError(404, "not_found", str(e)) from None

    # ---- restore ------------------------------------------------------------------------------
    def plan_restore(self, snapshot_id: str, scope: dict) -> tuple[dict, dict]:
        """Validate a restore request and build the plan the approval card shows."""
        app_id = scope.get("app_id")
        snap = self.snapshot(snapshot_id)
        if snap["unit"] != f"app:{app_id}":
            raise ApiError(409, "stale_precondition", f"snapshot {snap['short_id']} is of {snap['unit']}, not app:{app_id}")
        app = self.gw.catalog.get(app_id)
        st = self.gw.repo.get_app_state(app_id)
        if app is None or st is None or st.status != "installed":
            raise ApiError(409, "stale_precondition",
                           f"{app_id} is not installed; install it first, then restore its data into it")
        db = database_spec(app) is not None
        taken = snap.get("taken_at")
        if "path" in scope:
            path = scope["path"]
            if not any(path == p or path.startswith(p.rstrip("/") + "/") for p in snap.get("paths") or []):
                raise ApiError(409, "stale_precondition", "the path is not inside this snapshot")
            steps = ["take a pre-restore snapshot of what is there now (the undo point)",
                     f"put back {path} as it was at {taken}; the app keeps running"]
            summary = f"Restore {path} of {app_id} from {taken}"
        else:
            steps = [f"take a pre-restore snapshot of {app_id}" + (" and its database" if db else "") + " (the undo point)",
                     f"stop {app_id}",
                     f"put back its {len(snap.get('paths') or [])} saved folder(s)" + (" and its database" if db else "") + f" from {taken}",
                     f"start {app_id} and wait up to {self.s.health_deadline_s} s for fresh, ready pods",
                     "if it does not come back healthy: put today's data back and report the restore failed"]
            summary = f"Restore {app_id} to {taken}"
        plan = {"summary": summary, "app_id": app_id, "snapshot": {"id": snap["id"], "taken_at": taken, "reason": snap.get("reason")},
                "database": db, "steps": steps, "downtime": "none" if "path" in scope else "the app is stopped during the restore",
                "warnings": [] if backup_spec(app).declared else
                ["this app declares no backup hooks: its copy is crash-consistent only"]}
        return plan, snap

    def _check_restore(self, a: Action) -> str | None:
        app_id = (a.params.get("scope") or {}).get("app_id")
        st = self.gw.repo.get_app_state(app_id) if app_id else None
        if st is None or st.status != "installed":
            return f"{app_id} is no longer installed"
        return None

    def request_restore(self, principal, body: dict, *, idempotency_key: str, expires_at: datetime, reason: str | None):
        plan, snap = self.plan_restore(body["snapshot_id"], body["scope"])
        params = {"snapshot_id": snap["id"], "scope": body["scope"], "mode": body["mode"], "target": body["target"]}
        action, created = self.gw.actions.request_feature(
            principal, "backup.restore", params, idempotency_key=idempotency_key, expires_at=expires_at, reason=reason)
        if created:
            self.repo.add_restore(RestoreRow(
                id="rst_" + secrets.token_hex(10), action_id=action["id"], snapshot_id=snap["id"], scope=body["scope"],
                mode=body["mode"], target=body["target"], state="awaiting_approval", plan=plan, steps=[],
                created_at=utc(self.gw.clock())))
        return action, created

    def restores(self) -> list[dict]:
        return [self._restore_view(r) for r in self.repo.restores()]

    def restore(self, restore_id: str) -> dict:
        r = self.repo.restore(restore_id)
        if r is None:
            raise ApiError(404, "not_found", "no such restore")
        return self._restore_view(r)

    def _restore_view(self, r: RestoreRow) -> dict:
        out = restore_json(r)
        if r.state == "awaiting_approval":
            a = self.gw.repo.get(r.action_id)
            if a is not None and a.state in ("cancelled", "expired"):
                out["state"] = a.state
        return out

    def _act_restore(self, a: Action, finish: Callable[[ExecResult], None]) -> None:
        self.worker.submit(lambda: self._do_restore(a, finish))

    def _do_restore(self, a: Action, finish: Callable[[ExecResult], None]) -> None:
        r = self.repo.restore_for_action(a.id)
        rid = r.id if r else None
        steps: list[dict] = []

        def update(**fields) -> None:
            if rid:
                self.repo.update_restore(rid, steps=steps, **fields)

        def step(text: str, **extra) -> None:
            steps.append({"at": iso(self.gw.clock()), "step": text, **extra})
            update()

        def end(state: str, outcome: str, message: str, gate: dict | None = None) -> None:
            update(state=state, finished_at=utc(self.gw.clock()), error=None if outcome == "succeeded" else message,
                   **({"health_gate": gate} if gate is not None else {}))
            self._event("state_changed", {"restore_id": rid, "action_id": a.id, "state": state},
                        severity={"succeeded": "info", "failed": "error"}.get(outcome, "critical"), domain="restore",
                        action_id=a.id)
            finish(ExecResult(outcome, message, steps))

        update(state="running", started_at=utc(self.gw.clock()))
        self._event("state_changed", {"restore_id": rid, "action_id": a.id, "state": "running"}, domain="restore",
                    action_id=a.id)
        scope = a.params.get("scope") or {}
        app_id = scope.get("app_id")
        app = self.gw.catalog.get(app_id) if app_id else None
        if app is None:
            end("failed", "failed", f"{app_id} is not in the catalog")
            return

        if "path" in scope:  # one file or folder: the agent snapshots what is there first
            try:
                res = self._job("backup.restore", {"scope": "path", "snapshot_id": a.params["snapshot_id"],
                                                   "path": scope["path"]}, a.id) or {}
            except (AgentError, Unavailable) as e:
                end("failed", "failed", f"nothing was changed: {e}")
                return
            if rid:
                self.repo.update_restore(rid, pre_restore_snapshot_id=res.get("pre_restore_snapshot_id"))
            step("restored " + scope["path"], pre_restore_snapshot_id=res.get("pre_restore_snapshot_id"))
            end("succeeded", "succeeded", f"restored {scope['path']}")
            return

        ns = f"app-{app_id}"
        has_db = database_spec(app) is not None and self.pg is not None
        # 1. The undo point.
        pre = self.run_backup("pre-restore", {"app_id": app_id}, None, a.id)
        pre_snap = next((u.get("snapshot_id") for u in pre["units"] if u.get("unit") == f"app:{app_id}" and u.get("state") == "succeeded"), None)
        if pre["state"] != "succeeded" or not pre_snap:
            end("failed", "failed", f"the pre-restore snapshot failed, so nothing was changed: {pre.get('error') or pre['state']}")
            return
        if rid:
            self.repo.update_restore(rid, pre_restore_snapshot_id=pre_snap)
        step("pre-restore snapshot taken", snapshot_id=pre_snap, run_id=pre["id"])

        # 2. Stop the app.
        workloads: list[Workload] = []
        try:
            workloads = self.kube.workloads(ns)
            for w in workloads:
                self.kube.scale(ns, w, 0)
            self.kube.wait_no_pods(ns, 180)
        except KubeError as e:
            self._start(ns, workloads)
            end("failed", "failed", f"could not stop {app_id}, nothing was changed: {e}")
            return
        step(f"stopped {app_id}")

        # 3. Swap the data in.
        stamp = utc(self.gw.clock()).strftime("%Y%m%dT%H%M%SZ")
        try:
            self._job("backup.restore", {"scope": "app", "app_id": app_id, "snapshot_id": a.params["snapshot_id"],
                                         "stamp": stamp}, a.id)
        except (AgentError, Unavailable) as e:
            self._start(ns, workloads)
            end("failed", "failed", f"the agent could not restore the volumes, the current data is unchanged: {e}")
            return
        step("volumes restored", stamp=stamp)
        try:
            if has_db:
                self.pg.restore(app_id)
                step("database recreated from the snapshot's dump")
            # 4. Start it and require fresh signals.
            t0 = self.gw.clock()
            self._start(ns, workloads)
            step(f"started {app_id}")
            ok, gate = self._health_gate(ns, t0, sum(w.replicas for w in workloads))
            if ok:
                hooks: list[dict] = []
                problem = self._exec_hooks(app, backup_spec(app).restore_post, "restore.post", hooks)
                if problem:
                    ok, gate = False, {**gate, "restore_post": problem}
        except (KubeError, Unavailable, AgentError) as e:
            ok, gate = False, {"verdict": "error", "error": str(e)[:300]}

        if ok:
            try:
                self._job("backup.restore.finish", {"app_id": app_id, "stamp": stamp, "commit": True}, a.id)
            except (AgentError, Unavailable) as e:
                step("could not delete the moved-aside data (harmless, it stays beside the volume)", error=str(e)[:200])
            step("health gate passed", **gate)
            end("succeeded", "succeeded", f"{app_id} restored to {a.params['snapshot_id'][:12]} and healthy", gate)
            return

        # 5. Did not come back: put the current data back.
        step("health gate failed, rolling back", **gate)
        try:
            for w in workloads:
                self.kube.scale(ns, w, 0)
            self.kube.wait_no_pods(ns, 180)
            self._job("backup.restore.finish", {"app_id": app_id, "stamp": stamp, "commit": False}, a.id)
            if has_db:
                self.pg.restore(app_id)  # the moved-back dump is the pre-restore one
            self._start(ns, workloads)
        except (KubeError, AgentError, Unavailable) as e:
            step("rollback failed", error=str(e)[:300])
            end("outcome_unknown", "outcome_unknown",
                f"the restore failed and putting the old data back failed too; the pre-restore snapshot {pre_snap[:12]} holds it: {e}", gate)
            return
        step("previous data put back")
        end("failed", "failed", f"{app_id} did not come back healthy after the restore; its previous data is back", gate)

    def _start(self, ns: str, workloads: list[Workload]) -> None:
        for w in workloads:
            self.kube.scale(ns, w, w.replicas)

    def _health_gate(self, ns: str, since: datetime, expected: int) -> tuple[bool, dict]:
        """Ready pods created after `since`, three checks in a row, within the deadline."""
        end = time.monotonic() + self.s.health_deadline_s
        passes, last = 0, {}
        while time.monotonic() < end:
            ok, last = self.kube.fresh_ready(ns, since, expected)
            passes = passes + 1 if ok else 0
            if passes >= 3:
                return True, {"verdict": "pass", "checks": passes, **last}
            time.sleep(0 if isinstance(self.kube, DryKube) or self.worker.inline else 5)
        return False, {"verdict": "fail", "reason": "no fresh, ready pods before the deadline", **last}

    # ---- destinations -------------------------------------------------------------------------
    def request_destination(self, principal, body: dict, *, idempotency_key: str, expires_at: datetime, reason: str | None):
        dest_id = "dst_" + secrets.token_hex(8)
        params = {"destination_id": dest_id, "kind": body["kind"], "label": body["label"],
                  "primary": bool(body.get("primary")), "config": body["config"]}
        creds = body.get("credentials") or {}
        extra = {"credentials": "provided"} if creds else {}
        action, created = self.gw.actions.request_feature(
            principal, "backup.destination.add", params, idempotency_key=idempotency_key, expires_at=expires_at,
            reason=reason, audit_extra=extra)
        if created and creds:
            self._pending_secrets[action["id"]] = creds
        return action, created

    def _targets(self, rows: list[dict]) -> list[dict]:
        out = []
        for d in rows:
            c = d["config"]
            t = {"id": d["id"], "kind": AGENT_KIND[d["kind"]], "name": d["label"], "primary": d["primary"]}
            if d["kind"] == "usb":
                t["usb_uuid"] = c["usb_uuid"]
            elif d["kind"] in ("box", "rest"):
                t.update(url=c["url"], user=c["user"], append_only=bool(c.get("append_only", d["kind"] == "box")))
            else:
                t.update({k: c[k] for k in ("endpoint", "bucket", "prefix", "region") if c.get(k)})
            out.append(t)
        return out

    def _act_dest_add(self, a: Action, finish: Callable[[ExecResult], None]) -> None:
        p = a.params
        creds = self._pending_secrets.pop(a.id, None)
        needs = {"box": ("password",), "rest": ("password",), "s3": ("access_key", "secret_key")}.get(p["kind"], ())
        if needs and not creds:
            finish(ExecResult("failed", "the credentials were held in memory only and are gone (the gateway restarted); "
                                        "add the destination again"))
            return
        rows = [destination_json(d) for d in self.repo.destinations()]
        primary = p["primary"] or not any(r["primary"] for r in rows)
        if primary:
            for r in rows:
                r["primary"] = False
        new = {"id": p["destination_id"], "kind": p["kind"], "label": p["label"], "primary": primary,
               "append_only": bool(p["config"].get("append_only", p["kind"] == "box")), "config": p["config"]}
        secrets_ = {}
        if creds:
            secrets_[new["id"]] = {k: v for k, v in creds.items() if k in ("password", "ca", "access_key", "secret_key")}
        try:
            self._job("backup.configure", {"targets": self._targets(rows + [new]), "secrets": secrets_}, a.id)
        except (AgentError, Unavailable) as e:
            finish(ExecResult("failed", f"the agent did not accept the destination: {e}"))
            return
        if primary:
            self.repo.clear_primary()
        self.repo.add_destination(DestinationRow(id=new["id"], kind=new["kind"], label=new["label"], is_primary=primary,
                                                 append_only=new["append_only"], config=new["config"], action_id=a.id,
                                                 created_at=utc(self.gw.clock())))
        self._event("destination.added", {"destination_id": new["id"], "kind": new["kind"], "primary": primary}, action_id=a.id)
        finish(ExecResult("succeeded", f"destination {new['label']} added", [{"destination_id": new["id"]}]))

    def _act_dest_remove(self, a: Action, finish: Callable[[ExecResult], None]) -> None:
        dest_id = a.params["destination_id"]
        rows = [destination_json(d) for d in self.repo.destinations() if d.id != dest_id]
        if rows and not any(r["primary"] for r in rows):
            rows[0]["primary"] = True
        try:
            self._job("backup.configure", {"targets": self._targets(rows)}, a.id)
        except (AgentError, Unavailable) as e:
            finish(ExecResult("failed", f"the agent did not accept the change: {e}"))
            return
        self.repo.remove_destination(dest_id)
        self._event("destination.removed", {"destination_id": dest_id}, action_id=a.id)
        finish(ExecResult("succeeded", "destination removed; its backups were left untouched", [{"destination_id": dest_id}]))

    # ---- emergency kit ------------------------------------------------------------------------
    def _act_kit_issue(self, a: Action, finish: Callable[[ExecResult], None]) -> None:
        dests = [destination_json(d) for d in self.repo.destinations()]
        if not dests:
            finish(ExecResult("failed", "add a backup destination first: the key is added to its repository"))
            return
        key = new_owner_key()
        try:
            res = self._job("backup.key.add", {"which": "owner", "key": key.password}, a.id)
        except (AgentError, Unavailable) as e:
            finish(ExecResult("failed", f"the key could not be added to every destination: {e}"))
            return
        now = self.gw.clock()
        ch = challenge(key)
        self.repo.put_kit(KitRow(id="kit", state="issued", fingerprint=key.fingerprint, challenge=ch, issued_at=utc(now),
                                 confirmed_at=None, attempts=0))
        self._one_time[a.id] = {
            "owner_key": key.password, "groups": list(key.groups), "check": key.check,
            "qr_payload": f"onemind-kit:v1?key={key.password}&box={self.gw.settings.node_id or ''}",
            "text": kit_text(box_name=self.gw.settings.instance_name, instance_id=self.gw.settings.node_id or "",
                             key=key, destinations=dests, issued_at=now),
        }
        self._event("kit.issued", {"fingerprint": key.fingerprint, "destinations": len(dests)}, action_id=a.id)
        finish(ExecResult("succeeded", "emergency kit issued; it is shown once",
                          [{"fingerprint": key.fingerprint, "destinations": res}]))

    def take_one_time(self, action_id: str) -> dict | None:
        return self._one_time.pop(action_id, None)

    def confirm_kit(self, principal, answers: dict[str, str]) -> dict:
        k = self.repo.kit()
        if k is None:
            raise ApiError(404, "not_found", "no emergency kit has been issued")
        if k.state == "confirmed":
            return self.kit_state()
        if not answer_ok(k.challenge, answers):
            self.repo.update_kit(attempts=k.attempts + 1)
            self.gw.audit.append("backup.kit.confirm_failed", principal.as_dict(), None, {"attempts": k.attempts + 1})
            raise ApiError(409, "conflict", "those groups do not match your kit; look at the printed key again")
        now = self.gw.clock()
        self.repo.update_kit(state="confirmed", confirmed_at=utc(now))
        self._event("kit.confirmed", {"fingerprint": k.fingerprint}, principal=principal.as_dict())
        return self.kit_state()
