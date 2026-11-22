# SPDX-License-Identifier: Apache-2.0
"""FD-08: evidence for the seven owner check-up rows. All reads are side-effect free."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from .backups.manifest import database_spec
from .migrate.mapper import DIGEST_RE
from .monitoring.metrics import sample_from
from .scan import MAX_AGE, MAX_FUTURE_SKEW
from .sections import config_section

log = logging.getLogger("onemind.care")
PLATFORM = {"kube-public", "kube-node-lease", "kube-system", "onemind-system", "onemind-scan"}
RESOURCES = "deployments,statefulsets,jobs,cronjobs,pods,persistentvolumeclaims"


@config_section("care")
@dataclass(frozen=True)
class CareSettings:
    # Owner-mounted output of test/restore-drill/drill.py (#163), never a path from an HTTP request.
    restore_drill_dir: Path | None = None


class CareCheck(BaseModel):
    id: Literal["backup", "probe", "scan", "ownership", "image", "disk", "drill"]
    state: Literal["finding", "clear", "unavailable"]
    detail: str
    fix: Literal["backup.run"] | None = None


def result(key, bad, complete, problem, good, unknown, fix=None):
    if bad:
        names = sorted(set(bad))
        more = f" (+{len(names) - 5} more)" if len(names) > 5 else ""
        return CareCheck(id=key, state="finding", detail=f"{problem}: {', '.join(names[:5])}{more}.", fix=fix)
    return CareCheck(id=key, state="clear" if complete else "unavailable", detail=good if complete else unknown)


@dataclass
class Inventory:
    data: set[str] = field(default_factory=set)
    unowned: set[str] = field(default_factory=set)
    no_probe: set[str] = field(default_factory=set)
    unpinned: set[str] = field(default_factory=set)
    app_complete: bool = False
    cluster_complete: bool = False

    def observe(self, item, owned):
        kind, meta, spec = item["kind"], item["metadata"], item.get("spec", {})
        ns, name = meta["namespace"], meta["name"]
        if ns in PLATFORM:
            return
        if kind == "PersistentVolumeClaim":
            self.data.add(ns)
            return
        if kind == "Pod" and meta.get("ownerReferences"):
            # The controller template covers scaled-to-zero workloads and prospective replicas.
            # Retain Pods owned by controllers not requested here (e.g. a DaemonSet or custom CR).
            if all(ref["kind"] in {"Job", "StatefulSet"} for ref in meta["ownerReferences"]):
                return
        subject = f"{ns}/{name}"
        if ns not in owned:
            self.unowned.add(subject)
        if kind == "CronJob":
            spec = spec["jobTemplate"]["spec"]
        pod = spec if kind == "Pod" else spec["template"]["spec"]
        if spec.get("volumeClaimTemplates") or any("persistentVolumeClaim" in vol for vol in pod.get("volumes", [])):
            self.data.add(ns)
        for container in pod["containers"]:
            if kind not in ("Job", "CronJob") and not any(container.get(p) for p in ("readinessProbe", "livenessProbe")):
                self.no_probe.add(subject)
        for container in [*pod["containers"], *pod.get("initContainers", [])]:
            if not DIGEST_RE.search(container["image"]):
                self.unpinned.add(subject)


def inventory(kube, installed):
    inv = Inventory()
    if kube is None or installed is None:
        return inv
    owned = {f"app-{app}" for app in installed}
    def observe(args):
        doc = kube._json(["get", RESOURCES, *args, "-o", "json"])
        if not isinstance(doc, dict) or not isinstance(doc.get("items"), list):
            return False
        for item in doc["items"]:
            inv.observe(item, owned)
        return True
    if observe(["--all-namespaces"]):
        inv.app_complete = inv.cluster_complete = True
    else:
        # The shipping service account can inspect app namespaces even when cluster-wide reads are denied.
        inv.app_complete = bool(owned)
        for ns in sorted(owned):
            inv.app_complete &= observe(["-n", ns])
    return inv


def backup(gw, state, inv, installed):
    status = state.backups.status()
    if status["agent"] != "ok":
        return CareCheck(id="backup", state="unavailable", detail="The backup agent has no current report.")
    badges = status["badges"]
    managed = set()
    complete = inv.app_complete and installed is not None
    for app in installed or ():
        entry = gw.catalog.get(app)
        if entry is None:
            complete = False
        if f"app-{app}" in inv.data or (entry and database_spec(entry)):
            managed.add(app)
    outside = inv.data - {f"app-{app}" for app in installed or ()}
    units = {"system": badges["system"], **{app: badges["apps"].get(app, {"state": "none"}) for app in managed}}
    missing = []
    for name, badge in units.items():
        if badge.get("last_success_at"):
            stamp = datetime.fromisoformat(badge["last_success_at"])
            complete &= stamp <= gw.clock() + MAX_FUTURE_SKEW
        elif badge["state"] in ("none", "stale", "failing"):
            missing.append(name)
        else:
            complete = False
    fix = "backup.run" if missing and not outside and status["destinations"] and status["health"] != "failing" else None
    return result("backup", [*missing, *outside], complete, "No successful managed backup for",
                  "System and observed app data have successful backups.", "App data or backup coverage could not be read.", fix)


def scans(gw, installed):
    stale = []
    complete = installed is not None
    for app in installed or ():
        entry = gw.catalog.get(app)
        record = entry.scan if entry else None
        if not record or record.scanned_at > gw.clock() + MAX_FUTURE_SKEW:
            complete = False
        elif gw.clock() - record.scanned_at > MAX_AGE:
            stale.append(app)
    return result("scan", stale, complete, "Scan older than seven days", "No installed app has an overdue scan.",
                  "An installed app or its dated scan record could not be read.")


def disks(gw, monitoring):
    nodes = gw.registry.list()
    low, complete = [], bool(nodes)
    for node in nodes:
        sample, _ = sample_from(node, gw.clock())
        free, total = sample["disk_free_gb"], sample["disk_total_gb"]
        if node["status"] != "online" or free is None or not total or not 0 <= free <= total:
            complete = False
        elif 100 * free / total < monitoring.cfg.disk_free_pct:
            low.append(node["node_id"])
    return result("disk", low, complete, f"Below {monitoring.cfg.disk_free_pct:g}% disk space free",
                  "Reporting nodes have enough free disk space.", "A current node disk measurement is missing.")


def drill(gw):
    root = gw.settings.section(CareSettings).restore_drill_dir
    unknown = CareCheck(id="drill", state="unavailable", detail="No dated KVM restore drill report is available on this hub.")
    if not root:
        return unknown
    with (root / "run.json").open("rb") as f:
        report = json.loads(f.read(65537))
    if (report.get("suite"), report.get("criterion"), report.get("accel")) != ("restore-drill", "BAK-02", "kvm"):
        return unknown
    if report.get("verdict") in ("FAIL", "OVER_BUDGET"):
        return CareCheck(id="drill", state="finding", detail="The recorded whole-box restore drill did not pass.")
    if report.get("verdict") != "PASS":
        return unknown
    with (root / "run-logs" / "restore.log").open("rb") as f:
        f.seek(max(0, f.seek(0, 2) - 65536))
        times = re.findall(rb"^DRILL-PHASE verify end ([0-9]+(?:\.[0-9]+)?)\r?$", f.read(), re.MULTILINE)
    if not times:
        return unknown
    ended = datetime.fromtimestamp(float(times[-1]), UTC)
    if ended > gw.clock() + MAX_FUTURE_SKEW:
        return unknown
    overdue = gw.clock() - ended > timedelta(days=31)
    return CareCheck(id="drill", state="finding" if overdue else "clear",
                     detail=f"The last passing whole-box restore drill was on {ended.date()} (monthly schedule).")


def checkup(gw, state):
    def read(label, fn, default):
        try:
            return fn()
        except Exception as exc:  # A failed source does not prevent the other checks from running.
            log.warning("Care source %s unavailable (%s)", label, type(exc).__name__)
            return default
    apps = read("installed apps", state.monitoring.installed_apps, None)
    inv = read("workload inventory", lambda: inventory(state.monitoring.kube, apps), Inventory())
    def isolated(key, fn, message):
        return read(key, fn, CareCheck(id=key, state="unavailable", detail=message))
    return [
        isolated("backup", lambda: backup(gw, state, inv, apps), "Backup coverage could not be read."),
        result("probe", inv.no_probe, inv.app_complete, "No readiness or liveness probe",
               "Observed app workloads have health probes.", "App workload health probes could not be read."),
        isolated("scan", lambda: scans(gw, apps), "Installed app scan records could not be read."),
        result("ownership", inv.unowned, inv.cluster_complete, "Workload outside an installed app namespace",
               "All observed non-platform workloads belong to installed apps.", "Cluster-wide workload inventory is unavailable."),
        result("image", inv.unpinned, inv.app_complete, "Container image without a SHA-256 digest",
               "Observed app containers use pinned images.", "App container images could not be read."),
        isolated("disk", lambda: disks(gw, state.monitoring), "Node disk measurements could not be read."),
        isolated("drill", lambda: drill(gw), "A complete dated restore drill report could not be read."),
    ]
