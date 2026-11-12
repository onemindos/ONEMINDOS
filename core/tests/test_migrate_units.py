# SPDX-License-Identifier: Apache-2.0
"""Migration kit units: kubeconfig parsing, the verb fence, the mapper, the bundle, job specs."""

from __future__ import annotations

import base64
import json

import pytest
import yaml

from migrate_fakes import DIGEST_A, DIGEST_B, MANIFEST_SHA, NS, SNAPSHOT, TOKEN, FakeCluster, kubeconfig
from onemind_core.migrate import bundle, copyjobs
from onemind_core.migrate.inventory import Forbidden, Inventory, read_namespace
from onemind_core.migrate.kube import (
    HELPER, SCALE, FenceError, KubeClient, KubeconfigError, fence, parse_kubeconfig,
)
from onemind_core.migrate.mapper import app_manifest, map_namespace, quantity
from onemind_core.migrate.repo import RepoError, parse_range


# ---- kubeconfig ----------------------------------------------------------------------------------
def test_kubeconfig_token_target_hides_secret():
    t = parse_kubeconfig(kubeconfig())
    assert t.server == "https://old.example.test:6443" and t.namespace == NS and t.token == TOKEN
    assert TOKEN not in repr(t) and t.fingerprint.startswith("sha256:")
    assert "BEGIN CERTIFICATE" in t.ca_pem


def test_kubeconfig_client_certificate():
    pem = base64.b64encode(b"-----BEGIN X-----\n").decode()
    t = parse_kubeconfig(kubeconfig(user={"client-certificate-data": pem, "client-key-data": pem}))
    assert t.token is None and t.client_key_pem.startswith("-----BEGIN")


@pytest.mark.parametrize("user,extra,why", [
    ({"exec": {"command": "aws"}}, {}, "exec"),
    ({"auth-provider": {"name": "gcp"}}, {}, "auth-provider"),
    ({"tokenFile": "/var/run/token"}, {}, "points at a file"),
    ({"token": TOKEN}, {"certificate-authority": "/etc/ca.crt"}, "points at a file"),
    ({"token": TOKEN}, {"insecure-skip-tls-verify": True}, "insecure"),
    ({"token": TOKEN}, {"proxy-url": "http://proxy.example.test"}, "proxy-url"),
    ({"username": "a", "password": "b"}, {}, "basic auth"),
    ({}, {}, "no token"),
    ({"client-certificate-data": "eA=="}, {}, "go together"),
])
def test_kubeconfig_refusals(user, extra, why):
    with pytest.raises(KubeconfigError, match=why):
        parse_kubeconfig(kubeconfig(user=user, **extra))


def test_kubeconfig_plain_http_and_paths_refused():
    with pytest.raises(KubeconfigError, match="https"):
        parse_kubeconfig(kubeconfig(server="http://old.example.test:6443"))
    with pytest.raises(KubeconfigError, match="no path"):
        parse_kubeconfig(kubeconfig(server="https://old.example.test/k8s"))
    with pytest.raises(KubeconfigError, match="no context"):
        parse_kubeconfig(kubeconfig(), context="other")
    with pytest.raises(KubeconfigError):
        parse_kubeconfig("{not yaml")
    with pytest.raises(KubeconfigError, match="larger"):
        parse_kubeconfig("a" * 70000)


# ---- the fence -----------------------------------------------------------------------------------
@pytest.mark.parametrize("method,path,grants,ok", [
    ("GET", f"/apis/apps/v1/namespaces/{NS}/deployments", (), True),
    ("GET", f"/api/v1/namespaces/{NS}/pods", (), True),
    ("GET", f"/api/v1/namespaces/{NS}/secrets", (), False),  # secrets are never read
    ("GET", f"/api/v1/namespaces/{NS}/secrets", (HELPER, SCALE), False),
    ("GET", "/api/v1/namespaces/other/pods", (), False),  # another namespace
    ("GET", "/api/v1/nodes", (), False),
    ("POST", f"/api/v1/namespaces/{NS}/pods", (), False),
    ("POST", f"/api/v1/namespaces/{NS}/pods", (HELPER,), True),
    ("DELETE", f"/api/v1/namespaces/{NS}/pods/notes-7d9-abc", (HELPER,), False),  # not a helper
    ("DELETE", f"/api/v1/namespaces/{NS}/pods/onemind-migrate-copy-abc", (HELPER,), True),
    ("GET", f"/api/v1/namespaces/{NS}/pods/notes-7d9-abc/log", (HELPER,), False),
    ("GET", f"/api/v1/namespaces/{NS}/pods/onemind-migrate-copy-abc/log", (HELPER,), True),
    ("PATCH", f"/apis/apps/v1/namespaces/{NS}/deployments/notes/scale", (HELPER,), False),
    ("PATCH", f"/apis/apps/v1/namespaces/{NS}/deployments/notes/scale", (SCALE,), True),
    ("PATCH", f"/apis/apps/v1/namespaces/{NS}/deployments/notes", (SCALE,), False),
    ("PUT", f"/apis/apps/v1/namespaces/{NS}/deployments/notes", (HELPER, SCALE), False),
    ("DELETE", f"/apis/apps/v1/namespaces/{NS}/deployments/notes", (HELPER, SCALE), False),
])
def test_fence(method, path, grants, ok):
    if ok:
        fence(method, path, NS, frozenset(grants))
    else:
        with pytest.raises(FenceError):
            fence(method, path, NS, frozenset(grants))


def test_read_client_sends_only_gets_and_never_secrets():
    cluster = FakeCluster()
    client = KubeClient(parse_kubeconfig(kubeconfig()), NS, transport=cluster.send)
    inv = read_namespace(client)
    assert inv.server_version == "v1.30.0"
    assert {m for m, _ in cluster.requests} == {"GET"}
    assert not any("secret" in p for _, p in cluster.requests)
    with pytest.raises(FenceError):
        client.create_helper_pod({"metadata": {"name": "onemind-migrate-x", "labels": {"onemind.io/migrate-helper": "1"}}})
    with pytest.raises(FenceError):
        client.scale("Deployment", "notes", 0)
    assert all(m == "GET" for m, _ in cluster.requests)


def test_helper_client_refuses_foreign_pods():
    client = KubeClient(parse_kubeconfig(kubeconfig()), NS, grants=frozenset({HELPER}), transport=FakeCluster().send)
    with pytest.raises(FenceError):
        client.create_helper_pod({"metadata": {"name": "evil", "labels": {"onemind.io/migrate-helper": "1"}}})
    with pytest.raises(FenceError):
        client.create_helper_pod({"metadata": {"name": "onemind-migrate-x"}})  # no helper label
    with pytest.raises(FenceError):
        client.create_helper_pod({"metadata": {"name": "onemind-migrate-x", "namespace": "kube-system",
                                               "labels": {"onemind.io/migrate-helper": "1"}}})


def test_forbidden_required_kind_stops_and_optional_is_noted():
    client = KubeClient(parse_kubeconfig(kubeconfig()), NS, transport=FakeCluster(forbidden={"pods"}).send)
    with pytest.raises(Forbidden):
        read_namespace(client)
    client = KubeClient(parse_kubeconfig(kubeconfig()), NS, transport=FakeCluster(forbidden={"cronjobs"}).send)
    inv = read_namespace(client)
    assert inv.not_read == {"CronJob": "HTTP 403"}


# ---- the mapper ----------------------------------------------------------------------------------
def _inventory() -> Inventory:
    client = KubeClient(parse_kubeconfig(kubeconfig()), NS, transport=FakeCluster().send)
    return read_namespace(client)


def _levels(result) -> dict[tuple[str, str], list[str]]:
    out: dict = {}
    for f in result.findings:
        out.setdefault((f.kind, f.name), []).append(f.level)
    return out


def test_mapper_report_and_objects():
    r = map_namespace(_inventory(), "notes")
    lv = _levels(r)
    assert r.blocking == 0
    assert "fixed" in lv[("Image", "registry.example.test/notes:1.4")]
    assert lv[("Secret", "notes-env")] == ["move"] and lv[("Secret", "regcred")] == ["move"]
    assert lv[("Ingress", "notes")] == ["drop"]
    assert lv[("DaemonSet", "log-agent")] == ["skip"] and lv[("CronJob", "nightly")] == ["skip"]
    assert lv[("Service", "notes")] == ["fixed"] and lv[("Service", "external")] == ["skip"]
    assert lv[("PersistentVolumeClaim", "orphan")] == ["skip"]
    assert "fixed" in lv[("StatefulSet", "db")]  # retention Delete -> Retain
    kinds = sorted((o["kind"], o["metadata"]["name"]) for o in r.objects)
    assert kinds == [
        ("ConfigMap", "notes-config"), ("Deployment", "notes"), ("PersistentVolumeClaim", "data-db-0"),
        ("PersistentVolumeClaim", "notes-data"), ("Service", "db"), ("Service", "notes"), ("StatefulSet", "db"),
    ]
    dep = next(o for o in r.objects if o["kind"] == "Deployment")
    pod = dep["spec"]["template"]["spec"]
    c = pod["containers"][0]
    assert c["image"] == f"registry.example.test/notes:1.4@{DIGEST_A}"
    assert "hostPort" not in c["ports"][0]
    assert c["resources"]["limits"] == {"memory": "1Gi", "cpu": "1"}
    assert pod["automountServiceAccountToken"] is False
    assert not {"nodeSelector", "serviceAccountName", "imagePullSecrets"} & set(pod)
    assert dep["metadata"] == {"name": "notes", "labels": {"app": "notes"}}  # no uid, annotations
    svc = next(o for o in r.objects if o["kind"] == "Service" and o["metadata"]["name"] == "notes")
    assert "type" not in svc["spec"] and "nodePort" not in svc["spec"]["ports"][0] and "clusterIP" not in svc["spec"]
    pvc = next(o for o in r.objects if o["metadata"]["name"] == "notes-data")
    assert pvc["spec"]["storageClassName"] == "onemind-local"
    sts = next(o for o in r.objects if o["kind"] == "StatefulSet")
    assert sts["spec"]["volumeClaimTemplates"][0]["spec"]["storageClassName"] == "onemind-local"
    assert sts["spec"]["persistentVolumeClaimRetentionPolicy"] == {"whenDeleted": "Retain", "whenScaled": "Retain"}
    assert sts["spec"]["template"]["spec"]["containers"][0]["image"].endswith(DIGEST_B)
    assert {v["pvc"]: v["node"] for v in r.volumes} == {"notes-data": "node-a", "data-db-0": "node-a"}
    assert r.hosts == ["notes.example.test"] and r.web == {"service": "notes", "port": 80}
    assert r.secrets[0]["name"] == "notes-env" and r.secrets[0]["keys"] == ["API_KEY"]
    assert next(s for s in r.secrets if s["name"] == "notes-extra")["all_keys"] is True
    assert {w["name"]: w["selector"] for w in r.workloads} == {"notes": {"app": "notes"}, "db": {"app": "db"}}
    assert r.findings[0].level in ("move", "fixed")  # blocking first, then actionable
    placement = next(f for f in r.findings if f.kind == "Deployment" and f.level == "drop" and "places" in f.message)
    assert "nodeSelector" in placement.message and "schedulerName" not in placement.message  # server default


def test_mapper_blocks_unsafe_workloads():
    objs = FakeCluster().objects
    spec = objs["deployments"][0]["spec"]["template"]["spec"]
    spec["hostNetwork"] = True
    spec["volumes"].append({"name": "host", "hostPath": {"path": "/srv"}})
    spec["containers"][0]["securityContext"] = {"privileged": True, "capabilities": {"add": ["SYS_ADMIN", "CHOWN"]}}
    objs["pods"][0]["status"]["containerStatuses"] = []  # no digest to pin
    client = KubeClient(parse_kubeconfig(kubeconfig()), NS, transport=FakeCluster(objs).send)
    r = map_namespace(read_namespace(client), "notes")
    fails = [f.message for f in r.findings if f.level == "fail"]
    assert r.blocking == len(fails) >= 5
    assert any("hostNetwork" in m for m in fails) and any("hostPath" in m for m in fails)
    assert any("privileged" in m for m in fails) and any("SYS_ADMIN" in m for m in fails)
    assert any("no digest" in m for m in fails)
    assert not any(o["kind"] == "Deployment" for o in r.objects)  # a blocked workload is not written


def test_mapper_empty_namespace_blocks():
    r = map_namespace(Inventory(namespace=NS), "empty")
    assert r.blocking == 1


def test_quantity():
    assert quantity("1Gi") == 2**30 and quantity("500m") == 0.5 and quantity("2") == 2 and quantity("x") is None


def test_manifest_and_bundle(tmp_path):
    r = map_namespace(_inventory(), "notes")
    m = app_manifest(r, name="Notes", arch="arm64", version="0.1.0")
    assert m["metadata"]["origin"] == "private" and m["spec"]["web"] == {"port": 80}
    assert m["spec"]["secrets"][0] == {"name": "notes-env", "keys": [{"key": "API_KEY", "required": False}]}
    root = tmp_path / "b"
    digest = bundle.write_bundle(root, m, r.objects, r.workloads)
    assert digest == bundle.bundle_sha256(root)
    staging = yaml.safe_load((root / "staging/kustomization.yaml").read_text())
    assert staging["resources"] == ["../manifests"]
    assert sorted(x["name"] for x in staging["replicas"]) == ["db", "notes"] and {x["count"] for x in staging["replicas"]} == {0}
    k = yaml.safe_load((root / "manifests/kustomization.yaml").read_text())
    assert len(k["resources"]) == len(r.objects) and k["labels"][0]["pairs"] == {"onemind.io/app": "notes"}
    (root / "scan.json").write_text("{}")
    assert bundle.bundle_sha256(root) == digest  # the scan record is not part of the bundle hash
    (root / "manifests" / k["resources"][0]).write_text("tampered")
    assert bundle.bundle_sha256(root) != digest
    e = bundle.entry(root, m, staging=True)
    assert e.manifests_dir == (root / "staging").resolve()
    assert bundle.entry(root, m, staging=False).manifests_dir == (root / "manifests").resolve()
    for f in root.rglob("*.yaml"):
        assert "198.51.100.9" not in f.read_text()  # the old cluster's addresses never reach the bundle


# ---- job specs and results -----------------------------------------------------------------------
def test_helper_pod_is_minimal():
    pod = copyjobs.helper_pod(
        name="onemind-migrate-copy-x", plan_id="mig_1", copy_id="cpy_1", pvc="notes-data", node="node-a",
        image="img@sha256:" + "0" * 64, repository="rest:https://user:secret@box/v1/migrate/repo/mig_1/",
        repo_password="pw", tags=["onemind"], ca_pem=None, deadline_s=60,
    )
    spec = pod["spec"]
    c = spec["containers"][0]
    assert spec["automountServiceAccountToken"] is False and spec["nodeName"] == "node-a"
    assert spec["volumes"][0]["persistentVolumeClaim"] == {"claimName": "notes-data", "readOnly": True}
    assert c["volumeMounts"][0]["readOnly"] is True
    assert c["securityContext"]["capabilities"] == {"drop": ["ALL"], "add": ["DAC_READ_SEARCH"]}
    assert c["securityContext"]["readOnlyRootFilesystem"] is True and c["securityContext"]["allowPrivilegeEscalation"] is False
    assert pod["metadata"]["labels"]["onemind.io/migrate-helper"] == "cpy_1"


def test_restore_job_reads_credentials_from_secret():
    job = copyjobs.restore_job(name="onemind-migrate-restore-x", namespace="app-notes", app_id="notes", plan_id="mig_1",
                               pvc="notes-data", snapshot_id=SNAPSHOT, image="img", secret="s", deadline_s=60)
    c = job["spec"]["template"]["spec"]["containers"][0]
    assert c["envFrom"] == [{"secretRef": {"name": "s"}}]
    assert all("RESTIC" not in e["name"] for e in c["env"])
    sec = copyjobs.restore_secret(name="s", namespace="app-notes", app_id="notes", repository="rest:x", repo_password="pw", ca_pem="CA")
    assert base64.b64decode(sec["data"]["RESTIC_PASSWORD"]) == b"pw" and "ONEMIND_CA_PEM" in sec["data"]


def test_results_parsing():
    log = 'x\nONEMIND-RESULT {"files":2,"manifest_sha256":"%s","summary":{"snapshot_id":"%s","total_bytes_processed":9}}\n' % (MANIFEST_SHA, SNAPSHOT)
    out = copyjobs.helper_outcome(copyjobs.parse_result(log))
    assert out == {"snapshot_id": SNAPSHOT, "files": 2, "bytes": 9, "manifest_sha256": "sha256:" + MANIFEST_SHA}
    assert copyjobs.helper_outcome(copyjobs.parse_result('ONEMIND-RESULT {"files":1,"summary":}')) is None
    assert copyjobs.helper_outcome(copyjobs.parse_result("nothing")) is None
    assert copyjobs.restore_outcome({"files": 1, "failed": 0, "present": 1, "manifest_sha256": "e"})["manifest_sha256"] == "sha256:e"
    assert copyjobs.restore_outcome({"files": 1}) is None
    assert copyjobs.scrub("rest:https://u:secret@h", ["secret"]) == "rest:https://u:[redacted]@h"


def test_scripts_are_constant_and_reference_env_only():
    for script in (copyjobs.HELPER_SCRIPT, copyjobs.RESTORE_SCRIPT):
        assert "set -eu" in script and "ONEMIND-RESULT" in script
        assert "RESTIC_PASSWORD" not in script  # read by restic from the environment, never echoed


def test_parse_range():
    assert parse_range(None, 10) is None
    assert parse_range("bytes=2-4", 10) == (2, 4)
    assert parse_range("bytes=5-", 10) == (5, 9)
    assert parse_range("bytes=-3", 10) == (7, 9)
    assert parse_range("bytes=0-99", 10) == (0, 9)
    for bad in ("bytes=9-2", "bytes=10-", "items=0-1", "bytes=-"):
        with pytest.raises(RepoError):
            parse_range(bad, 10)


def test_fixture_has_no_real_names():
    text = json.dumps(FakeCluster().objects)
    assert "example.test" in text
