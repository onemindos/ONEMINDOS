# SPDX-License-Identifier: Apache-2.0
"""Live usage (UMB-P11, #429): GET /v1/usage joins heartbeats, metrics-server and kubelet volume stats."""

from __future__ import annotations

from conftest import GUEST, OWNER
from onemind_core.monitoring.kube import KubeReader, pvc_usage
from test_monitoring import FakeKube, beat, install, mclient, mon, pod  # noqa: F401  (fixture re-export)


class UsageKube(FakeKube):
    def __init__(self):
        super().__init__()
        self.stats: dict[str, dict | None] = {}
        self.stats_calls = 0

    def node_stats(self, name):
        self.stats_calls += 1
        return self.stats.get(name)


def with_node(p, node="k1"):
    p["spec"] = {"nodeName": node}
    return p


def summary(ns, pod_name, used):
    return {"pods": [
        {"podRef": {"name": pod_name, "namespace": ns},
         "volume": [{"name": "data", "usedBytes": used, "pvcRef": {"name": "data", "namespace": ns}},
                    {"name": "tmp", "usedBytes": 999e6}]},          # an emptyDir: not the app's data
        {"podRef": {"name": "other", "namespace": "kube-system"},
         "volume": [{"name": "d", "usedBytes": 5e9, "pvcRef": {"name": "d", "namespace": "kube-system"}}]},
    ]}


def usage(c, headers=OWNER):
    r = c.get("/v1/usage", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_machines_and_apps_from_the_real_sources(mclient, clock):
    k = mon(mclient).kube = UsageKube()
    install(mclient, clock)
    beat(mclient, metrics={"cpu_pct": 12.5, "load1": 0.7, "temp_c": 51.0})
    k.pods_by_ns["app-uptime-kuma"] = [with_node(pod("web-1"))]
    k.usage = {"web-1": {"main": (250.0, 128.0)}, "gone": {"main": (50.0, 2.0)}}
    k.stats["k1"] = summary("app-uptime-kuma", "web-1", 3e9)
    body = usage(mclient)
    [n] = body["nodes"]
    assert (n["node_id"], n["status"], n["stale"], n["cpu_pct"], n["cpu_source"]) == ("n1", "online", False, 12.5, "heartbeat")
    assert (n["mem_used_mb"], n["mem_total_mb"], n["disk_used_gb"], n["disk_total_gb"], n["temp_c"]) == (2000, 8000, 40.0, 100.0, 51.0)
    assert body["apps"]["source"] == "kubernetes" and body["apps"]["stale"] is False
    [a] = body["apps"]["items"]
    assert a["app_id"] == "uptime-kuma" and a["cpu_millicores"] == 300.0 and a["mem_mb"] == 130.0
    assert a["disk_mb"] == 3000.0   # only the claim-backed volume, only this app's namespace


def test_unreported_numbers_are_null_not_zero(mclient, clock):
    k = mon(mclient).kube = UsageKube()
    install(mclient, clock)
    beat(mclient)                                           # no metrics object: no CPU, no temperature
    k.pods_by_ns["app-uptime-kuma"] = [with_node(pod("web-1"))]   # metrics-server and kubelet stats answer nothing
    body = usage(mclient)
    n = body["nodes"][0]
    assert n["cpu_pct"] is None and n["temp_c"] is None
    [a] = body["apps"]["items"]
    assert (a["cpu_millicores"], a["mem_mb"], a["disk_mb"]) == (None, None, None)


def test_old_heartbeat_is_stale_not_current(mclient, clock):
    mon(mclient).kube = UsageKube()
    beat(mclient, metrics={"cpu_pct": 90.0})
    clock.advance(45)
    n = usage(mclient)["nodes"][0]
    assert (n["status"], n["stale"], n["age_s"], n["cpu_pct"]) == ("stale", True, 45, 90.0)
    clock.advance(200)
    n = usage(mclient)["nodes"][0]
    assert n["status"] == "offline" and n["stale"] is True


def test_no_runtime_means_unavailable_apps(mclient, clock):
    install(mclient, clock)
    mon(mclient).kube = None
    apps = usage(mclient)["apps"]
    assert apps == {"source": "unavailable", "sampled_at": None, "stale": True, "items": []}


def test_failed_refresh_serves_the_last_reading_marked_stale(mclient, clock):
    k = mon(mclient).kube = UsageKube()
    install(mclient, clock)
    k.pods_by_ns["app-uptime-kuma"] = [with_node(pod("web-1"))]
    k.usage = {"web-1": {"main": (100.0, 64.0)}}
    first = usage(mclient)["apps"]
    assert first["stale"] is False and first["items"][0]["cpu_millicores"] == 100.0
    k.pods_by_ns["app-uptime-kuma"] = None                  # kubectl stops answering
    clock.advance(10)
    mid = usage(mclient)["apps"]
    assert mid["stale"] is False and mid["sampled_at"] == first["sampled_at"]
    clock.advance(40)
    late = usage(mclient)["apps"]
    assert late["stale"] is True and late["sampled_at"] == first["sampled_at"]
    assert late["items"][0]["cpu_millicores"] == 100.0


def test_cache_spares_kubectl_between_close_polls(mclient, clock):
    k = mon(mclient).kube = UsageKube()
    install(mclient, clock)
    k.pods_by_ns["app-uptime-kuma"] = [with_node(pod("web-1"))]
    usage(mclient)
    usage(mclient)
    assert k.stats_calls == 1
    clock.advance(6)
    usage(mclient)
    assert k.stats_calls == 2


def test_apps_not_shared_with_the_reader_are_left_out(mclient, clock):
    k = mon(mclient).kube = UsageKube()
    install(mclient, clock)
    k.pods_by_ns["app-uptime-kuma"] = [with_node(pod("web-1"))]
    mclient.app.state.gateway.app_filters.append(lambda request, p, app_id: p.is_owner)
    assert len(usage(mclient, OWNER)["apps"]["items"]) == 1
    assert usage(mclient, GUEST)["apps"]["items"] == []


def test_route_needs_a_signed_in_principal(mclient):
    assert mclient.get("/v1/usage").status_code == 401


def test_pvc_usage_ignores_other_namespaces_and_emptydirs():
    assert pvc_usage(summary("app-a", "p", 7e9), "app-a") == {"p": 7e9}
    assert pvc_usage(None, "app-a") == {}


def test_kubelet_stats_read_is_a_read_only_raw_get_and_rejects_odd_node_names():
    calls = []

    class CP:
        returncode, stdout = 0, '{"pods": []}'

    def runner(argv, **kw):
        calls.append(argv)
        return CP()

    r = KubeReader("kubectl", runner=runner)
    assert r.node_stats("k1.local") == {"pods": []}
    assert calls == [["kubectl", "get", "--raw", "/api/v1/nodes/k1.local/proxy/stats/summary"]]
    assert r.node_stats("../x") is None and len(calls) == 1
