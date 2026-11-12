# SPDX-License-Identifier: Apache-2.0
"""Monitoring: watch nodes and installed apps, publish condition events (contract §12.15).

Every `interval_s` (30 s) `tick()`:
- nodes: status changes (`node.stale` once, `node.offline` / `node.online`), one metric sample
  per minute into the in-memory history, threshold rules (disk, memory, temperature, CPU), and
  the heartbeat's `update` and `backup` objects (`update.available|applied|rolled_back`,
  `backup.failed|succeeded`);
- apps (installed ones, through the Kubernetes API when it is available): restarts
  (`app.restarted`, `app.oom_killed`), crash loops (≥ 3 restarts in 10 min), health (not ready
  for 3 min = `app.unhealthy`, back = `app.healthy`), and the scan record (`app.scan_blocked`,
  `app.scan_stale`, `app.scan_ok`).

Each finding is a `publish_event` (audited, on NATS, and seen by the notifier, which turns it
into an alert per the catalogue). Only transitions are published. After a restart the open
alerts in the database stand in for the remembered state, so a cleared condition still resolves.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

from ..notify.store import NotifyRepository
from ..scan import scan_problem
from ..sections import config_section
from . import health as H
from .kube import KubeReader
from .metrics import NodeHistory, sample_from

log = logging.getLogger("onemind.monitoring")


@config_section("monitoring")
@dataclass(frozen=True)
class MonitoringSettings:
    enabled: bool = True             # ONEMIND_MONITORING_ENABLED: run the background watcher
    interval_s: float = 30.0         # ONEMIND_MONITORING_INTERVAL_S
    kube: str = "auto"               # ONEMIND_MONITORING_KUBE: auto (with the kubernetes executor) | kubectl | off
    disk_free_pct: float = 10.0      # disk.low below this % free (§12.15)
    mem_used_pct: float = 90.0       # memory.high above this % used for 3 samples
    temp_c: float = 85.0             # temperature.high at or above (critical at +10 °C)
    cpu_pct: float = 95.0            # cpu.high when every sample of cpu_sustain_min is at or above
    cpu_sustain_min: int = 5
    unhealthy_after_s: int = 180     # app.unhealthy after 3 min not ready (§12.15)
    crashloop_restarts: int = 3      # app.crashlooping at >= 3 restarts ...
    crashloop_window_s: int = 600    # ... in 10 min

    def validate(self) -> None:
        if self.kube not in ("auto", "kubectl", "off"):
            raise ValueError("ONEMIND_MONITORING_KUBE must be auto, kubectl or off")
        if self.interval_s <= 0 or self.cpu_sustain_min < 1 or self.crashloop_restarts < 1:
            raise ValueError("ONEMIND_MONITORING_* intervals and counts must be positive")


@dataclass
class AppTrack:
    restarts: dict[tuple[str, str], int] = field(default_factory=dict)
    restart_times: deque = field(default_factory=deque)
    not_ready_since: datetime | None = None
    seen: bool = False
    health: dict | None = None
    components: list[dict] = field(default_factory=list)
    last_exit_reason: str | None = None


class MonitoringService:
    def __init__(self, gw, kube: KubeReader | None = None):
        self.gw = gw
        self.cfg: MonitoringSettings = gw.settings.section(MonitoringSettings)
        use_kube = self.cfg.kube == "kubectl" or (self.cfg.kube == "auto" and gw.settings.executor == "kubernetes")
        self.kube = kube if kube is not None else (KubeReader(gw.settings.kubectl) if use_kube else None)
        self.history = NodeHistory()
        self.alerts = NotifyRepository(gw.db)
        self._cond: dict[str, bool] = {}
        self._node_status: dict[str, str] = {}
        self._node_update: dict[str, dict] = {}
        self._apps: dict[str, AppTrack] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---- lifecycle ----------------------------------------------------------------------
    def start(self) -> None:
        if not self.cfg.enabled:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="monitoring", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(10)

    def _loop(self) -> None:
        while not self._stop.wait(self.cfg.interval_s):
            try:
                self.tick()
            except Exception:
                log.exception("monitoring pass failed")

    # ---- one pass -----------------------------------------------------------------------
    def tick(self) -> None:
        with self._lock:
            now = self.gw.clock()
            open_keys = self.alerts.open_alert_keys()
            self._tick_nodes(now, open_keys)
            self._tick_apps(now, open_keys)

    def _emit(self, domain: str, name: str, data: dict, severity: str = "info") -> None:
        try:
            self.gw.events.publish_event(domain, name, data, severity=severity, source_id="gateway:monitoring")
        except Exception:
            log.exception("monitoring event %s.%s failed", domain, name)

    def _condition(self, key: str, bad: bool, open_keys: set[str], bad_evt: tuple[str, str] | None,
                   ok_evt: tuple[str, str] | None, data: dict, severity: str = "warning") -> None:
        prev = self._cond.get(key)
        if prev is None:
            prev = key in open_keys
        if bad and not prev and bad_evt:
            self._emit(*bad_evt, data, severity)
        elif not bad and prev and ok_evt:
            self._emit(*ok_evt, data, "info")
        self._cond[key] = bad

    # ---- nodes --------------------------------------------------------------------------
    def _tick_nodes(self, now: datetime, open_keys: set[str]) -> None:
        ms = self.kube.node_metrics() if self.kube is not None else None
        for n in self.gw.registry.list():
            nid = n["node_id"]
            host = n.get("hostname") or nid
            seen = H.parse_time(n.get("last_seen"))
            age = int((now - seen).total_seconds()) if seen else 0
            base = {"node_id": nid, "hostname": host}
            status, prev = n.get("status"), self._node_status.get(nid)
            if status == "stale" and prev == "online":
                self._emit("node", "stale", {**base, "age_s": age})
            self._condition(f"node:{nid}:offline", status == "offline", open_keys, ("node", "offline"),
                            ("node", "online"), {**base, "age_s": age})
            self._node_status[nid] = status
            if status == "offline":
                continue  # the last heartbeat is old news: no samples, no thresholds
            sample, source = sample_from(n, now, (ms or {}).get(host))
            if self.history.add(nid, sample, source, now):
                self._thresholds(nid, base, sample, open_keys)
            self._heartbeat_objects(nid, base, n, open_keys)

    def _thresholds(self, nid: str, base: dict, s: dict, open_keys: set[str]) -> None:
        c = self.cfg
        free, total = s.get("disk_free_gb"), s.get("disk_total_gb")
        if free is not None and total:
            pct = round(free / total * 100, 1)
            key = f"node:{nid}:disk"
            was = self._cond.get(key, key in open_keys)
            bad = pct < c.disk_free_pct + (2 if was else 0)  # 2 points of hysteresis
            self._condition(key, bad, open_keys, ("disk", "low"), ("disk", "ok"),
                            {**base, "free_pct": pct, "free_gb": free, "mount": "/data"})
        recent = self.history.recent(nid, max(3, c.cpu_sustain_min))
        mems = [x["mem_used_mb"] / x["mem_total_mb"] * 100 for x in recent[-3:]
                if x.get("mem_used_mb") is not None and x.get("mem_total_mb")]
        if mems:
            key = f"node:{nid}:memory"
            was = self._cond.get(key, key in open_keys)
            bad = (len(mems) == 3 and min(mems) > c.mem_used_pct) or (was and mems[-1] > c.mem_used_pct - 5)
            self._condition(key, bad, open_keys, ("memory", "high"), ("memory", "ok"),
                            {**base, "used_pct": round(mems[-1], 1)})
        temp = s.get("temp_c")
        if temp is not None:
            key = f"node:{nid}:temperature"
            was = self._cond.get(key, key in open_keys)
            bad = temp >= c.temp_c - (5 if was else 0)
            sev = "critical" if temp >= c.temp_c + 10 else "warning"
            data = {**base, "temp_c": temp, "limit_c": c.temp_c, "severity": sev}
            if bad and was and sev == "critical" and self._cond.get(key + ":critical") is False:
                self._emit("temperature", "high", data, sev)  # escalation notifies at once
            self._cond[key + ":critical"] = bad and sev == "critical"
            self._condition(key, bad, open_keys, ("temperature", "high"), ("temperature", "ok"), data, sev)
        cpus = [x["cpu_pct"] for x in recent[-c.cpu_sustain_min:] if x.get("cpu_pct") is not None]
        if cpus:
            key = f"node:{nid}:cpu"
            was = self._cond.get(key, key in open_keys)
            bad = (len(cpus) >= c.cpu_sustain_min and min(cpus) >= c.cpu_pct) or (was and cpus[-1] >= c.cpu_pct - 10)
            self._condition(key, bad, open_keys, ("cpu", "high"), ("cpu", "ok"),
                            {**base, "cpu_pct": cpus[-1], "minutes": c.cpu_sustain_min})

    def _heartbeat_objects(self, nid: str, base: dict, n: dict, open_keys: set[str]) -> None:
        upd = n.get("update") if isinstance(n.get("update"), dict) else None
        prev = self._node_update.get(nid)
        if upd is not None:
            avail, state = upd.get("available_version"), upd.get("state")
            if avail and (prev is None or prev.get("available_version") != avail):
                if prev is not None or f"os:{nid}:available" not in open_keys:
                    self._emit("update", "available", {**base, "version": avail})
            if prev is not None and state == "committed" and prev.get("state") != "committed":
                self._emit("update", "applied", {**base, "version": upd.get("current_version")})
            self._condition(f"os:{nid}:rollback", state == "rolled_back", open_keys, ("update", "rolled_back"),
                            None, {**base, "reason": str(upd.get("last_result") or "the new version failed its health check")})
            self._node_update[nid] = dict(upd)
        bk = n.get("backup") if isinstance(n.get("backup"), dict) else None
        if bk is not None and bk.get("last_result") in ("failed", "succeeded"):
            target = f"node-{nid}"
            self._condition(f"backup:{target}", bk["last_result"] == "failed", open_keys, ("backup", "failed"),
                            ("backup", "succeeded"), {**base, "target": target, "reason": "the last backup run failed"})

    # ---- apps ---------------------------------------------------------------------------
    def installed_apps(self) -> list[str]:
        return sorted(a for a, st in self.gw.repo.list_app_states().items() if st.status == "installed")

    def _tick_apps(self, now: datetime, open_keys: set[str]) -> None:
        installed = self.installed_apps()
        for app_id in installed:
            self._scan(app_id, now, open_keys)
            if self.kube is not None:
                self._observe(app_id, self.kube.pods(f"app-{app_id}"), now, open_keys)
        for app_id in list(self._apps):
            if app_id not in installed:  # removed: its conditions are over
                for key, evt in ((f"app:{app_id}:health", ("app", "healthy")),
                                 (f"app:{app_id}:crashloop", ("app", "crashloop_ended"))):
                    self._condition(key, False, open_keys, None, evt, {"app_id": app_id})
                del self._apps[app_id]

    def _scan(self, app_id: str, now: datetime, open_keys: set[str]) -> None:
        entry = self.gw.catalog.get(app_id)
        if entry is None:
            return
        rec = entry.scan
        problem = scan_problem(app_id, rec, now)
        blocked = rec is not None and rec.result != "pass"
        data = {"app_id": app_id, "reason": problem or ""}
        self._condition(f"app:{app_id}:scan", blocked, open_keys, ("app", "scan_blocked"), ("app", "scan_ok"),
                        data, "critical")
        self._condition(f"app:{app_id}:scan_stale", bool(problem) and not blocked, open_keys,
                        ("app", "scan_stale"), ("app", "scan_ok"), data)

    def _observe(self, app_id: str, pods: list[dict] | None, now: datetime, open_keys: set[str]) -> None:
        t = self._apps.setdefault(app_id, AppTrack())
        if pods is None:
            t.health = H.assess(None, True, None, now, self.cfg.unhealthy_after_s)
            return
        for pod in pods:
            comp = H.component_of(pod)
            for cs in H.containers(pod):
                k = (cs["pod"], cs["container"])
                before = t.restarts.get(k)
                t.restarts[k] = cs["restarts"]
                if before is None or cs["restarts"] <= before:
                    continue
                t.restart_times.extend([now] * (cs["restarts"] - before))
                t.last_exit_reason = cs["last_exit_reason"]
                data = {"app_id": app_id, "component": comp, "restarts": cs["restarts"],
                        "last_exit_reason": cs["last_exit_reason"] or "unknown"}
                self._emit("app", "restarted", data)
                if cs["last_exit_reason"] == "OOMKilled":
                    self._emit("app", "oom_killed", data, "warning")
        live = {(c["pod"], c["container"]) for p in pods for c in H.containers(p)}
        t.restarts = {k: v for k, v in t.restarts.items() if k in live}
        while t.restart_times and (now - t.restart_times[0]).total_seconds() > self.cfg.crashloop_window_s:
            t.restart_times.popleft()
        self._condition(f"app:{app_id}:crashloop", len(t.restart_times) >= self.cfg.crashloop_restarts, open_keys,
                        ("app", "crashlooping"), ("app", "crashloop_ended"),
                        {"app_id": app_id, "restarts": len(t.restart_times),
                         "window_min": self.cfg.crashloop_window_s // 60,
                         "last_exit_reason": t.last_exit_reason or "unknown"})
        if all(H.pod_ready(p) for p in pods):
            t.not_ready_since = None
        elif t.not_ready_since is None:
            t.not_ready_since = (H.earliest_start(pods) if not t.seen else None) or now
        t.seen = True
        t.health = H.assess(pods, True, t.not_ready_since, now, self.cfg.unhealthy_after_s)
        t.components = H.summarise(pods)
        self._condition(f"app:{app_id}:health", t.health["state"] == "unhealthy", open_keys,
                        ("app", "unhealthy"), ("app", "healthy"),
                        {"app_id": app_id, "reason": t.health.get("reason", "")})

    # ---- read models for the routes -------------------------------------------------------
    def app_view(self, app_id: str, installed: bool) -> tuple[dict, list[dict]]:
        """(health, components), read live from the Kubernetes API when it is available."""
        now = self.gw.clock()
        if not installed:
            return H.assess(None, False, None, now, self.cfg.unhealthy_after_s), []
        if self.kube is None:
            return {"state": "unknown", "checked_at": None, "reason": "no Kubernetes API on this box"}, []
        pods = self.kube.pods(f"app-{app_id}")
        with self._lock:
            t = self._apps.get(app_id)
            since = t.not_ready_since if t else None
        if pods is not None and since is None and not all(H.pod_ready(p) for p in pods):
            since = H.earliest_start(pods)
        comps = [{k: v for k, v in c.items() if k != "pods"} for c in H.summarise(pods or [])]
        return H.assess(pods, True, since, now, self.cfg.unhealthy_after_s), comps

    def app_states(self) -> dict[str, str]:
        with self._lock:
            return {a: (t.health or {}).get("state", "unknown") for a, t in self._apps.items()}
