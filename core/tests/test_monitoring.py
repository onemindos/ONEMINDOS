# SPDX-License-Identifier: Apache-2.0
"""Monitoring (contract §12.15): node status and metrics, thresholds, app health, logs."""

from __future__ import annotations

import json
import subprocess
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, GUEST, OWNER, action_body, write_scan
from onemind_core.app import create_app
from onemind_core.ledger import iso
from onemind_core.monitoring import KubeReader, MonitoringService, MonitoringSettings
from onemind_core.monitoring.kube import parse_cpu, parse_mem
from onemind_core.monitoring.redact import redact_lines
from onemind_core.notify import NotifySettings


class FakeKube:
    def __init__(self):
        self.pods_by_ns: dict[str, list[dict] | None] = {}
        self.log_lines = ["started", "password=hunter2 user ok", "GET / 200"]
        self.usage: dict | None = None
        self.nodes: dict | None = None
        self.calls: list[tuple] = []

    def pods(self, ns):
        return self.pods_by_ns.get(ns, [])

    def events(self, ns, limit=10):
        return []

    def logs(self, ns, pod, container, tail, since_s):
        self.calls.append(("logs", ns, pod, tail, since_s))
        return self.log_lines[-tail:]

    @contextmanager
    def follow(self, ns, pod, container, tail, max_s):
        self.calls.append(("follow", ns, pod, tail, max_s))
        yield iter(self.log_lines)

    def pod_metrics(self, ns):
        return self.usage

    def node_metrics(self):
        return self.nodes


def pod(name, component="web", ready=True, restarts=0, reason=None, waiting=None, start="2026-11-11T21:50:00Z",
        finished="2026-11-11T21:59:00Z"):
    cs = {"name": "main", "restartCount": restarts, "state": {"waiting": {"reason": waiting}} if waiting else {"running": {}}}
    if reason:
        cs["lastState"] = {"terminated": {"reason": reason, "finishedAt": finished}}
    return {
        "metadata": {"name": name, "labels": {"app.kubernetes.io/component": component}},
        "status": {"startTime": start, "conditions": [{"type": "Ready", "status": "True" if ready else "False"}],
                   "containerStatuses": [cs]},
    }


def hb(node_id="n1", **extra):
    doc = {
        "schema": "onemind.node.status/v1", "node_id": node_id, "hostname": "beelink", "role": "hub",
        "board": "x86_64-efi", "arch": "amd64", "cpus": 4, "mem_total_mb": 8000, "mem_available_mb": 6000,
        "disk_total_gb": 100.0, "disk_free_gb": 60.0, "observed_at": "2026-11-11T22:00:00Z",
    }
    doc.update(extra)
    return json.dumps(doc).encode()


@pytest.fixture
def mclient(settings, clock, executor, tmp_path):
    s = replace(settings, sections={"notify": NotifySettings(worker=False, dir=tmp_path / "keys"),
                                    "monitoring": MonitoringSettings(enabled=False)})
    with TestClient(create_app(s, clock=clock, executor=executor)) as c:
        c.app.state.monitoring.kube = FakeKube()
        yield c


def mon(c) -> MonitoringService:
    return c.app.state.monitoring


def beat(c, node_id="n1", **extra):
    assert c.app.state.registry.ingest(f"onemind.node.{node_id}.status", hb(node_id, **extra))


def alerts(c, headers=OWNER):
    return {a["dedupe_key"]: a for a in c.get("/v1/alerts", headers=headers, params={"state": "open"}).json()}


def minute(c, clock, **extra):
    beat(c, **extra)
    mon(c).tick()
    clock.advance(60)


# ---- nodes --------------------------------------------------------------------------------

def test_node_stale_offline_online(mclient, clock):
    beat(mclient)
    mon(mclient).tick()
    clock.advance(40)
    mon(mclient).tick()
    inbox = mclient.get("/v1/notifications", headers=OWNER).json()
    assert [n["title"] for n in inbox] == ["beelink is late"]
    clock.advance(90)
    mon(mclient).tick()
    mon(mclient).tick()
    assert alerts(mclient)["node:n1:offline"]["occurrences"] == 1
    beat(mclient)
    mon(mclient).tick()
    assert "node:n1:offline" not in alerts(mclient)


def test_metric_history_window_and_sources(mclient, clock):
    for i in range(5):
        minute(mclient, clock, metrics={"cpu_pct": 10.0 + i, "load1": 0.5, "temp_c": 50.0})
    r = mclient.get("/v1/nodes/n1/metrics", headers=GUEST, params={"window": "3m"})
    body = r.json()
    assert body["source"] == "heartbeat" and [s["cpu_pct"] for s in body["samples"]] == [12.0, 13.0, 14.0]
    s = body["samples"][-1]
    assert s["mem_used_mb"] == 2000 and s["disk_free_gb"] == 60.0 and s["temp_c"] == 50.0
    assert len(mclient.get("/v1/nodes/n1/metrics", headers=GUEST).json()["samples"]) == 5
    assert mclient.get("/v1/nodes/n1/metrics", headers=GUEST, params={"window": "25h"}).status_code == 422
    assert mclient.get("/v1/nodes/nope/metrics", headers=GUEST).status_code == 404
    beat(mclient)  # two heartbeats within a minute keep one sample
    mon(mclient).tick()
    mon(mclient).tick()
    assert len(mclient.get("/v1/nodes/n1/metrics", headers=GUEST).json()["samples"]) == 6


def test_metrics_server_fills_cpu(mclient, clock):
    mon(mclient).kube.nodes = {"beelink": 2000.0}
    minute(mclient, clock)
    body = mclient.get("/v1/nodes/n1/metrics", headers=OWNER).json()
    assert body["source"] == "metrics-server" and body["samples"][0]["cpu_pct"] == 50.0


def test_disk_threshold_with_hysteresis(mclient, clock):
    minute(mclient, clock, disk_free_gb=5.0)
    a = alerts(mclient)["node:n1:disk"]
    assert a["type"] == "disk.low" and a["topic"] == "storage" and "5.0% free" in a["body"]
    minute(mclient, clock, disk_free_gb=11.0)   # within 2 points: still low
    assert "node:n1:disk" in alerts(mclient)
    minute(mclient, clock, disk_free_gb=40.0)
    assert "node:n1:disk" not in alerts(mclient)


def test_storage_object_wins_over_root_disk(mclient, clock):
    minute(mclient, clock, storage={"state": "protected", "mount": "/data", "used_bytes": 95e9, "free_bytes": 5e9})
    assert "node:n1:disk" in alerts(mclient)
    assert mclient.get("/v1/monitoring/summary", headers=GUEST).json()["storage"] == [{"node_id": "n1", "state": "protected"}]


def test_temperature_escalates_then_clears(mclient, clock):
    minute(mclient, clock, metrics={"temp_c": 88.0})
    assert alerts(mclient)["node:n1:temperature"]["severity"] == "warning"
    minute(mclient, clock, metrics={"temp_c": 97.0})
    assert alerts(mclient)["node:n1:temperature"]["severity"] == "critical"
    minute(mclient, clock, metrics={"temp_c": 60.0})
    assert "node:n1:temperature" not in alerts(mclient)


def test_cpu_must_be_sustained_and_memory_three_samples(mclient, clock):
    for _ in range(4):
        minute(mclient, clock, metrics={"cpu_pct": 99.0}, mem_available_mb=400)
    assert "node:n1:cpu" not in alerts(mclient)
    assert alerts(mclient)["node:n1:memory"]["type"] == "memory.high"
    minute(mclient, clock, metrics={"cpu_pct": 99.0})
    assert alerts(mclient)["node:n1:cpu"]["type"] == "cpu.high"
    minute(mclient, clock, metrics={"cpu_pct": 20.0})
    assert {"node:n1:cpu", "node:n1:memory"}.isdisjoint(alerts(mclient))


def test_heartbeat_update_and_backup_objects(mclient, clock):
    upd = {"channel": "security", "current_version": "1", "available_version": None, "state": "idle"}
    minute(mclient, clock, update=upd, backup={"running": False, "last_result": "failed"})
    assert alerts(mclient)["backup:node-n1"]["fix"] == {"type": "backup.run", "params": {"scope": "box"}}
    minute(mclient, clock, update={**upd, "available_version": "2"}, backup={"last_result": "succeeded"})
    a = alerts(mclient)
    assert a["os:n1:available"]["title"] == "Update 2 available for beelink" and "backup:node-n1" not in a
    minute(mclient, clock, update={**upd, "current_version": "2", "state": "committed"})
    assert "os:n1:available" not in alerts(mclient)
    minute(mclient, clock, update={**upd, "state": "rolled_back", "last_result": "health gate failed"})
    assert alerts(mclient)["os:n1:rollback"]["body"] == "health gate failed"


def test_state_survives_restart_through_open_alerts(mclient, clock):
    minute(mclient, clock, disk_free_gb=5.0)
    gw = mclient.app.state.gateway
    fresh = MonitoringService(gw, kube=FakeKube())        # a restarted gateway remembers nothing
    beat(mclient, disk_free_gb=50.0)
    fresh.tick()
    assert "node:n1:disk" not in alerts(mclient)


# ---- apps ---------------------------------------------------------------------------------

def install(c, clock, app_id="uptime-kuma"):
    a = c.post("/v1/actions", headers=OWNER, json=action_body(clock, app_id=app_id, key=f"i-{app_id}")).json()
    assert c.post(f"/v1/actions/{a['id']}/approve", headers=OWNER).json()["state"] == "succeeded"


def test_app_unhealthy_after_three_minutes_and_recovers(mclient, clock):
    install(mclient, clock)
    k = mon(mclient).kube
    k.pods_by_ns["app-uptime-kuma"] = [pod("web-1", ready=False, start=iso(clock.now - timedelta(seconds=60)))]
    mon(mclient).tick()
    body = mclient.get("/v1/apps/uptime-kuma", headers=GUEST).json()
    assert body["health"]["state"] == "starting" and body["installed"] is True
    assert body["components"] == [{"name": "web", "ready": False, "restarts": 0, "last_restart_at": None,
                                   "last_exit_reason": None}]
    clock.advance(150)
    mon(mclient).tick()
    a = alerts(mclient, ADULT)["app:uptime-kuma:health"]   # adults are in the app audience
    assert a["fix"] == {"type": "app.restart", "params": {"app_id": "uptime-kuma"}}
    assert mclient.get("/v1/apps/uptime-kuma", headers=OWNER).json()["health"]["state"] == "unhealthy"
    assert mclient.get("/v1/monitoring/summary", headers=OWNER).json()["apps"]["unhealthy"] == 1
    k.pods_by_ns["app-uptime-kuma"] = [pod("web-1")]
    mon(mclient).tick()
    assert "app:uptime-kuma:health" not in alerts(mclient)
    assert mclient.get("/v1/apps/whoami", headers=OWNER).json()["health"]["state"] == "stopped"
    assert mclient.get("/v1/apps/nope", headers=OWNER).status_code == 404


def test_crashloop_backoff_is_unhealthy_at_once(mclient, clock):
    install(mclient, clock)
    mon(mclient).kube.pods_by_ns["app-uptime-kuma"] = [pod("web-1", ready=False, waiting="CrashLoopBackOff",
                                                           restarts=2, reason="Error")]
    mon(mclient).tick()
    assert "CrashLoopBackOff" in alerts(mclient)["app:uptime-kuma:health"]["body"]


def test_restarts_oom_and_crashloop(mclient, clock):
    install(mclient, clock)
    k = mon(mclient).kube
    k.pods_by_ns["app-uptime-kuma"] = [pod("web-1", restarts=0)]
    mon(mclient).tick()
    k.pods_by_ns["app-uptime-kuma"] = [pod("web-1", restarts=1, reason="OOMKilled")]
    mon(mclient).tick()
    titles = [n["title"] for n in mclient.get("/v1/notifications", headers=OWNER).json()]
    assert "uptime-kuma ran out of memory" in titles and "uptime-kuma restarted" in titles
    k.pods_by_ns["app-uptime-kuma"] = [pod("web-1", restarts=3, reason="Error")]
    clock.advance(60)
    mon(mclient).tick()
    a = alerts(mclient)["app:uptime-kuma:crashloop"]
    assert a["body"] == "3 restarts in 10 minutes. Last exit: Error."
    clock.advance(11 * 60)
    mon(mclient).tick()
    assert "app:uptime-kuma:crashloop" not in alerts(mclient)


def test_scan_conditions_for_installed_apps(mclient, clock, settings):
    install(mclient, clock)
    write_scan(settings.apps_dir / "uptime-kuma", clock.now, result="fail")
    mon(mclient).tick()
    assert alerts(mclient)["app:uptime-kuma:scan"]["severity"] == "critical"
    write_scan(settings.apps_dir / "uptime-kuma", clock.now - timedelta(days=9))
    mon(mclient).tick()
    a = alerts(mclient)
    assert "app:uptime-kuma:scan" not in a and "app:uptime-kuma:scan_stale" in a
    write_scan(settings.apps_dir / "uptime-kuma", clock.now)
    mon(mclient).tick()
    assert alerts(mclient) == {}


def test_removed_app_conditions_resolve(mclient, clock):
    install(mclient, clock)
    mon(mclient).kube.pods_by_ns["app-uptime-kuma"] = [pod("web-1", ready=False, waiting="ImagePullBackOff")]
    mon(mclient).tick()
    assert "app:uptime-kuma:health" in alerts(mclient)
    a = mclient.post("/v1/actions", headers=OWNER,
                     json=action_body(clock, type_="app.remove", key="rm")).json()
    mclient.post(f"/v1/actions/{a['id']}/approve", headers=OWNER)
    mon(mclient).tick()
    assert "app:uptime-kuma:health" not in alerts(mclient)


def test_app_metrics(mclient, clock):
    install(mclient, clock)
    k = mon(mclient).kube
    k.pods_by_ns["app-uptime-kuma"] = [pod("web-1", restarts=2), pod("db-0", component="db")]
    body = mclient.get("/v1/apps/uptime-kuma/metrics", headers=GUEST).json()
    assert body["components"][0] == {"name": "db", "cpu_millicores": None, "mem_mb": None, "restarts": 0}
    k.usage = {"web-1": {"main": (12.5, 100.0)}, "db-0": {"main": (3.0, 50.0)}}
    web = mclient.get("/v1/apps/uptime-kuma/metrics", headers=GUEST).json()["components"][1]
    assert web == {"name": "web", "cpu_millicores": 12.5, "mem_mb": 100.0, "restarts": 2}


# ---- logs ---------------------------------------------------------------------------------

def test_logs_permissions_redaction_and_audit(mclient, clock, settings):
    install(mclient, clock)
    k = mon(mclient).kube
    k.pods_by_ns["app-uptime-kuma"] = [pod("web-1"), pod("db-0", component="db")]
    for h in (GUEST, AGENT):
        assert mclient.get("/v1/apps/uptime-kuma/logs", headers=h).status_code == 403
    r = mclient.get("/v1/apps/uptime-kuma/logs", headers=ADULT, params={"tail": 2, "component": "web", "since": "5m"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert r.text == "password=[redacted] user ok\nGET / 200\n"
    assert k.calls[-1] == ("logs", "app-uptime-kuma", "web-1", 2, 300)
    assert mclient.get("/v1/apps/uptime-kuma/logs", headers=OWNER, params={"tail": 2001}).status_code == 422
    assert mclient.get("/v1/apps/uptime-kuma/logs", headers=OWNER, params={"component": "nope"}).status_code == 404
    assert mclient.get("/v1/apps/whoami/logs", headers=OWNER).status_code == 404
    audit = [json.loads(x) for x in settings.audit_path.read_text().splitlines()]
    opened = [x for x in audit if x["event"] == "logs.opened"]
    assert opened[0]["principal"]["id"] == "adult" and opened[0]["data"]["payload"]["app_id"] == "uptime-kuma"


def test_logs_follow_is_sse_and_bounded(mclient, clock):
    install(mclient, clock)
    k = mon(mclient).kube
    k.pods_by_ns["app-uptime-kuma"] = [pod("web-1")]
    r = mclient.get("/v1/apps/uptime-kuma/logs", headers=OWNER, params={"follow": 1})
    assert r.headers["content-type"].startswith("text/event-stream")
    assert "data: password=[redacted] user ok\n\n" in r.text and r.text.endswith("event: end\ndata: stream closed\n\n")
    assert k.calls[-1][-1] == 15 * 60


def test_logs_without_kubernetes(settings, clock, executor, tmp_path):
    s = replace(settings, sections={"notify": NotifySettings(worker=False, dir=tmp_path / "k"),
                                    "monitoring": MonitoringSettings(enabled=False)})
    with TestClient(create_app(s, clock=clock, executor=executor)) as c:
        install(c, clock)
        assert mon(c).kube is None  # noop executor, kube=auto
        assert c.get("/v1/apps/uptime-kuma/logs", headers=OWNER).status_code == 404
        assert c.get("/v1/apps/uptime-kuma", headers=OWNER).json()["health"]["state"] == "unknown"
        assert c.get("/v1/apps/uptime-kuma/metrics", headers=OWNER).json()["components"] == []


def test_redactor():
    lines = [
        "Authorization: Bearer abcdefghijklmnop",
        '{"api_key": "sk-123456", "user": "x"}',
        "connect postgres://app:s3cret@db:5432/app",
        "token " + "eyJ" + "hbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiIxMjMifQ" + ".abcdefghijk",  # test values, split for scanners
        "issued " + "om_pat_" + "ABCDEFGHIJKLMNOP and " + "AKIA" + "ABCDEFGHIJKLMNOP",
        "mail from " + "alice" + "@" + "example.org" + " at 203.0.113.9",
        "-----BEGIN OPENSSH " + "PRIVATE KEY-----", "fake-key-body-line", "-----END OPENSSH " + "PRIVATE KEY-----",
        "plain line " + "x" * 5000,
    ]
    out = redact_lines(lines)
    assert out[0] == "Authorization: Bearer [redacted]"
    assert out[1] == '{"api_key": "[redacted]", "user": "x"}'
    assert out[2] == "connect postgres://[redacted]@db:5432/app"
    assert out[3] == "token [redacted]"
    assert out[4] == "issued [redacted] and [redacted]"
    assert out[5] == "mail from [email] at [ip]"
    assert out[6:9] == ["[redacted]"] * 3
    assert len(out[9]) == 4096 and len(out) == len(lines)


# ---- the Kubernetes reader ----------------------------------------------------------------

def test_kube_reader_uses_read_only_verbs():
    seen = []

    def runner(argv, **kw):
        seen.append(argv)
        if argv[1:3] == ["get", "pods"]:
            return subprocess.CompletedProcess(argv, 0, json.dumps({"items": [pod("a")]}), "")
        if argv[1:3] == ["get", "--raw"]:
            doc = {"items": [{"metadata": {"name": "a"}, "containers": [{"name": "main", "usage": {"cpu": "250000000n", "memory": "2048Ki"}}]}]}
            return subprocess.CompletedProcess(argv, 0, json.dumps(doc), "")
        if argv[1] == "logs":
            return subprocess.CompletedProcess(argv, 0, "one\ntwo\nthree\n", "")
        return subprocess.CompletedProcess(argv, 1, "", "boom")

    k = KubeReader("kubectl", runner=runner)
    assert len(k.pods("app-x")) == 1
    assert k.pod_metrics("app-x") == {"a": {"main": (250.0, 2.0)}}
    assert k.logs("app-x", "a", None, 2, 60) == ["two", "three"]
    assert k.events("app-x") is None
    verbs = {a[1] for a in seen}
    assert verbs <= {"get", "logs"}
    assert ["kubectl", "logs", "a", "-n", "app-x", "--tail=2", "--limit-bytes=2097152", "--all-containers=true",
            "--prefix=true", "--since=60s"] in seen

    def missing(argv, **kw):
        raise FileNotFoundError("kubectl")
    assert KubeReader(runner=missing).pods("app-x") is None


def test_quantities():
    assert parse_cpu("250m") == 250 and parse_cpu("2") == 2000 and parse_cpu("1500000n") == 1.5
    assert parse_mem("512Mi") == 512 and parse_mem("1Gi") == 1024 and parse_cpu("x") is None


def test_settings_validation():
    with pytest.raises(ValueError):
        MonitoringSettings(kube="maybe").validate()
