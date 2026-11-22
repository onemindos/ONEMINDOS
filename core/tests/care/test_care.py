# SPDX-License-Identifier: Apache-2.0
import json
import subprocess
from datetime import timedelta
from types import SimpleNamespace

from conftest import ADULT, AGENT, OWNER, write_scan
from onemind_core.monitoring.kube import KubeReader


def checks(client):
    res = client.get("/v1/care/checkup", headers=OWNER)
    assert res.status_code == 200, res.text
    return {row["id"]: row for row in res.json()}


def test_unavailable_and_owner_only(client):
    rows = checks(client)
    assert set(rows) == {"backup", "probe", "scan", "ownership", "image", "disk", "drill"}
    for key in ("backup", "probe", "ownership", "image", "disk", "drill"):
        assert rows[key]["state"] == "unavailable"
    assert all(row["fix"] is None for row in rows.values())
    for who, code in (({}, 401), (ADULT, 403), (AGENT, 403)):
        assert client.get("/v1/care/checkup", headers=who).status_code == code


def workload(namespace, image, probe=False):
    container = {"image": image, **({"readinessProbe": {"tcpSocket": {"port": 80}}} if probe else {})}
    return {"kind": "Deployment", "metadata": {"namespace": namespace, "name": "web"},
            "spec": {"template": {"spec": {"containers": [container]}}}}


def test_live_findings_and_approval_contract(client, clock, settings, monkeypatch):
    st = client.app.state
    gw = st.gateway
    gw.repo.set_app_state("uptime-kuma", "installed", clock())
    write_scan(settings.apps_dir / "uptime-kuma", clock() - timedelta(days=8))
    objects = [workload("app-uptime-kuma", "example:daily"), workload("other", "example:daily"),
               {"kind": "PersistentVolumeClaim", "metadata": {"namespace": "app-uptime-kuma", "name": "data"}}]
    def kubectl(args, **kwargs):
        assert args[1] == "get"
        return subprocess.CompletedProcess(args, 0, json.dumps({"items": objects}))
    monkeypatch.setattr(st.monitoring, "kube", KubeReader(runner=kubectl))
    monkeypatch.setattr(gw.registry, "list", lambda: [{"node_id": "one", "status": "online", "disk_free_gb": 1, "disk_total_gb": 100}])
    monkeypatch.setattr(st.backups, "status", lambda: {"agent": "ok", "health": "stale", "destinations": [{"id": "one"}],
                        "badges": {"system": {"state": "verified", "last_success_at": clock().isoformat()}, "apps": {}}})
    rows = checks(client)
    assert all(rows[key]["state"] == "finding" for key in ("backup", "probe", "scan", "ownership", "image", "disk"))
    assert "uptime-kuma" in rows["backup"]["detail"]
    assert "other/web" in rows["ownership"]["detail"]
    assert rows["backup"]["fix"] == "backup.run"
    assert all(row["fix"] is None for key, row in rows.items() if key != "backup")
    monkeypatch.setattr(st.backups, "agent", object())  # no agent call is possible before approval
    reply = client.post("/v1/backups/runs", json={"scope": "box", "approve": False}, headers=OWNER)
    assert reply.status_code == 202
    action = reply.json()
    assert (action["type"], action["state"], action["approved_by"]) == (rows["backup"]["fix"], "awaiting_approval", None)


def test_partial_namespace_access_keeps_known_evidence(client, clock, monkeypatch):
    st = client.app.state
    st.gateway.repo.set_app_state("whoami", "installed", clock())
    obj = workload("app-whoami", "example@sha256:" + "a" * 64, True)
    def kubectl(args, **kwargs):
        if "--all-namespaces" in args:
            return subprocess.CompletedProcess(args, 1, "")
        assert args[args.index("-n") + 1] == "app-whoami"
        return subprocess.CompletedProcess(args, 0, json.dumps({"items": [obj]}))
    monkeypatch.setattr(st.monitoring, "kube", KubeReader(runner=kubectl))
    monkeypatch.setattr(st.backups, "status", lambda: {"agent": "ok", "health": "ok", "destinations": [],
                        "badges": {"system": {"state": "verified", "last_success_at": clock().isoformat()}, "apps": {}}})
    rows = checks(client)
    assert rows["backup"]["state"] == "unavailable"
    assert rows["probe"]["state"] == rows["image"]["state"] == "clear"
    assert rows["ownership"]["state"] == "unavailable"
    assert rows["scan"]["state"] == "clear"


def test_restore_drill_uses_dated_kvm_evidence_only(client, clock, tmp_path, monkeypatch):
    from onemind_core.care import CareSettings
    gw = client.app.state.gateway
    original = gw.settings.section
    monkeypatch.setattr(type(gw.settings), "section", lambda self, cfg: SimpleNamespace(restore_drill_dir=tmp_path) if cfg is CareSettings else original(cfg))
    report = {"suite": "restore-drill", "criterion": "BAK-02", "accel": "kvm", "verdict": "PASS"}
    (tmp_path / "run.json").write_text(json.dumps(report))
    assert checks(client)["drill"]["state"] == "unavailable"
    (tmp_path / "run-logs").mkdir()
    log = tmp_path / "run-logs/restore.log"
    for days, expected in ((1, "clear"), (32, "finding"), (-1, "unavailable")):
        log.write_text(f"DRILL-PHASE verify end {(clock() - timedelta(days=days)).timestamp()}\n")
        assert checks(client)["drill"]["state"] == expected
    (tmp_path / "run.json").write_text(json.dumps(dict(report, accel="tcg")))
    assert checks(client)["drill"]["state"] == "unavailable"


def test_zero_pod_controllers_visible_and_generated_replicas_not_counted(client, monkeypatch):
    missing = workload("other", "example:daily")
    missing["kind"] = "DaemonSet"
    standalone = workload("other", "example:daily")
    standalone.update(kind="ReplicaSet")
    standalone["metadata"]["name"] = "standalone"
    standalone["spec"]["replicas"] = 0
    generated = workload("other", "example:daily")
    generated.update(kind="ReplicaSet")
    generated["metadata"].update(name="generated-hash", ownerReferences=[{"kind": "Deployment", "controller": True}])
    def kubectl(args, **kwargs):
        assert {"daemonsets", "replicasets"} <= set(args[2].split(","))
        return subprocess.CompletedProcess(args, 0, json.dumps({"items": [missing, standalone, generated]}))
    monkeypatch.setattr(client.app.state.monitoring, "kube", KubeReader(runner=kubectl))
    rows = checks(client)
    for key in ("ownership", "image", "probe"):
        assert rows[key]["state"] == "finding"
        assert "other/web" in rows[key]["detail"] and "other/standalone" in rows[key]["detail"]
        assert "generated-hash" not in rows[key]["detail"]
