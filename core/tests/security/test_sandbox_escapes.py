# SPDX-License-Identifier: Apache-2.0
"""Install-sandbox escape fixtures (H-01..H-04, docs/leap/core/SANDBOX.md, contract §12.2 policy_refused).

Why: an app from the Market is untrusted code. The gateway renders its kustomization and checks
every object against sdk/policy/app-objects.yaml before `kubectl apply`. One missed field is a way
out of the app's namespace onto the box. These tests try every Kubernetes escape we know of and
assert the checker refuses it *with the right rule id* (the id is what the approval card and the
action result show the owner).

Three groups:
1. Pod-level vectors (hostPath, host namespaces, privileged, capabilities, procMount, sysctls,
   ephemeral and init containers, ...) generated into every workload kind that carries a pod
   template: Deployment, StatefulSet, Job, CronJob (allowed kinds: the vector's own rule) and
   DaemonSet, ReplicaSet, ReplicationController, bare Pod (refused as kinds: K-01).
2. Object-level fixtures in fixtures/sandbox/objects/ (RBAC, webhooks, CRDs, PersistentVolumes,
   Services, Endpoints, Lists, ...). Each file says `Expected: <rule>.`.
3. Kustomization-level fixtures in fixtures/sandbox/kustomize/ (patches, components, namespace
   override, image transformers, generators that read host files, remote bases, plugins,
   symlinks). The pre-render check runs first; when it passes, the real kustomize renders.

A vector the checker misses today is marked `gap`: a strict xfail whose reason says why it is an
escape. Fixing the checker turns it into an unexpected pass, which fails until the gap marker is
replaced by the new rule id. The shipped checker and rule file are required, not optional skips.
"""

from __future__ import annotations

import copy
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from onemind_core import policy

HERE = Path(__file__).parent
OBJECTS = HERE / "fixtures" / "sandbox" / "objects"
KUSTOMIZE = HERE / "fixtures" / "sandbox" / "kustomize"
APP_ID = "sec-app"
MANIFEST = {"apiVersion": "onemind.app/v1alpha1", "kind": "App", "metadata": {"id": APP_ID}, "spec": {}}
IMAGE = "ghcr.io/example/app:1.0@sha256:" + "0123456789abcdef" * 4
EXPECTED = re.compile(r"Expected: ([A-Z]-\d\d|allowed|gap)\.")


@pytest.fixture(scope="module")
def rules():
    path = policy.SandboxSettings().rules_path()
    assert path is not None, "the shipped sdk/policy/app-objects.yaml is required"
    return policy.load_rules(path)


def refusals(rules, docs, app_id=APP_ID, manifest=None) -> list:
    return policy.check_objects(docs, app_id, manifest or MANIFEST, rules)


# ---- 1. pod-level vectors x workload kinds --------------------------------------------------------------
def container(name: str) -> dict:
    return {"name": name, "image": IMAGE,
            "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}}}


def clean_pod() -> dict:
    """A pod spec that passes PSA restricted and the rule file: every vector starts from here."""
    return {"securityContext": {"runAsNonRoot": True, "runAsUser": 10001, "seccompProfile": {"type": "RuntimeDefault"}},
            "containers": [container("app")], "volumes": [{"name": "data", "emptyDir": {}}]}


ALLOWED_KINDS = ("Deployment", "StatefulSet", "Job", "CronJob")
REFUSED_KINDS = ("DaemonSet", "ReplicaSet", "ReplicationController", "Pod")


def workload(kind: str, pod: dict) -> dict:
    meta = {"name": "escape", "labels": {"app": "escape"}}
    tpl = {"metadata": {"labels": {"app": "escape"}}, "spec": pod}
    selector = {"matchLabels": {"app": "escape"}}
    if kind == "Pod":
        return {"apiVersion": "v1", "kind": "Pod", "metadata": meta, "spec": pod}
    if kind == "ReplicationController":
        return {"apiVersion": "v1", "kind": kind, "metadata": meta, "spec": {"selector": {"app": "escape"}, "template": tpl}}
    if kind == "Job":
        return {"apiVersion": "batch/v1", "kind": kind, "metadata": meta, "spec": {"template": tpl}}
    if kind == "CronJob":
        return {"apiVersion": "batch/v1", "kind": kind, "metadata": meta,
                "spec": {"schedule": "*/5 * * * *", "jobTemplate": {"spec": {"template": tpl}}}}
    spec = {"selector": selector, "template": tpl}
    if kind == "StatefulSet":
        spec["serviceName"] = "escape"
    return {"apiVersion": "apps/v1", "kind": kind, "metadata": meta, "spec": spec}


def _pod(**changes):
    def mutate(p):
        p.update(changes)
    return mutate


def _csc(**changes):
    def mutate(p):
        p["containers"][0]["securityContext"].update(changes)
    return mutate


def _psc(**changes):
    def mutate(p):
        p["securityContext"].update(changes)
    return mutate


def _volume(source: dict, *, init_only: bool = False):
    def mutate(p):
        p["volumes"].append({"name": "v", **source})
        c = container("grab") if init_only else p["containers"][0]
        c.setdefault("volumeMounts", []).append({"name": "v", "mountPath": "/v"})
        if init_only:
            p["initContainers"] = [c]
    return mutate


def _caps(*caps):
    return _csc(capabilities={"drop": ["ALL"], "add": list(caps)})


def _extra(key: str, **sc):
    def mutate(p):
        c = container("extra")
        c["securityContext"].update(sc)
        p[key] = [c]
    return mutate


def _ports(**port):
    def mutate(p):
        p["containers"][0]["ports"] = [{"containerPort": 8080, **port}]
    return mutate


@dataclass(frozen=True)
class Vector:
    name: str
    mutate: object
    rule: str | None        # the rule id that must refuse it; None with a gap
    field: str              # the violation's path must mention this field
    gap: str | None = None  # why it is an escape the checker misses today
    restricted_only: bool = False  # a PSA restricted rule (S-*): baseline apps may do it
    baseline_rule: str | None = None  # a restricted_only vector that a baseline (F-*) rule also refuses


ADMISSION = "PSA admission in the app namespace still refuses it, but the plan the owner approves does not show it"
POD_VECTORS = [
    Vector("hostNetwork", _pod(hostNetwork=True), "F-01", "hostNetwork"),
    Vector("hostPID", _pod(hostPID=True), "F-02", "hostPID"),
    Vector("hostIPC", _pod(hostIPC=True), "F-03", "hostIPC"),
    Vector("hostPath-root", _volume({"hostPath": {"path": "/"}}), "F-04", "hostPath"),
    Vector("hostPath-docker-socket", _volume({"hostPath": {"path": "/var/run/docker.sock", "type": "Socket"}}), "F-04", "hostPath"),
    Vector("hostPath-containerd-socket", _volume({"hostPath": {"path": "/run/k3s/containerd/containerd.sock"}}), "F-04", "hostPath"),
    Vector("hostPath-k3s-server-token", _volume({"hostPath": {"path": "/var/lib/rancher/k3s/server", "type": "Directory"}}), "F-04", "hostPath"),
    Vector("hostPath-proc", _volume({"hostPath": {"path": "/proc"}}), "F-04", "hostPath"),
    Vector("hostPath-init-container-only", _volume({"hostPath": {"path": "/etc"}}, init_only=True), "F-04", "hostPath"),
    Vector("hostPort", _ports(hostPort=80), "F-05", "hostPort"),
    Vector("hostPort-with-hostIP", _ports(hostPort=8443, hostIP="0.0.0.0"), "F-05", "hostPort"),
    Vector("privileged", _csc(privileged=True), "F-06", "privileged"),
    Vector("privileged-init-container", _extra("initContainers", privileged=True), "F-06", "initContainers"),
    Vector("privileged-ephemeral-container", _extra("ephemeralContainers", privileged=True), "F-06", "ephemeralContainers"),
    Vector("cap-SYS_ADMIN", _caps("SYS_ADMIN"), "F-07", "capabilities"),
    Vector("cap-prefixed-CAP_SYS_ADMIN", _caps("CAP_SYS_ADMIN"), "F-07", "capabilities"),
    Vector("cap-lowercase-sys_module", _caps("sys_module"), "F-07", "capabilities"),
    Vector("cap-ALL", _caps("ALL"), "F-07", "capabilities"),
    Vector("cap-NET_ADMIN", _caps("NET_ADMIN"), "F-07", "capabilities"),
    Vector("cap-NET_RAW", _caps("NET_RAW"), "F-07", "capabilities"),
    Vector("cap-SYS_PTRACE", _caps("SYS_PTRACE"), "F-07", "capabilities"),
    Vector("cap-BPF", _caps("BPF"), "F-07", "capabilities"),
    Vector("cap-in-init-container", _extra("initContainers", capabilities={"drop": ["ALL"], "add": ["SYS_ADMIN"]}),
           "F-07", "initContainers"),
    Vector("windows-hostProcess", _psc(windowsOptions={"hostProcess": True}), "F-08", "hostProcess"),
    Vector("run-as-root", _csc(runAsUser=0), "S-01", "runAsNonRoot", restricted_only=True),
    Vector("pod-runAsNonRoot-false", _psc(runAsNonRoot=False), "S-01", "runAsNonRoot", restricted_only=True),
    Vector("allowPrivilegeEscalation", _csc(allowPrivilegeEscalation=True), "S-02", "allowPrivilegeEscalation",
           restricted_only=True),
    Vector("no-drop-ALL", _csc(capabilities={"drop": ["NET_RAW"]}), "S-03", "capabilities", restricted_only=True),
    # Unconfined seccomp is also a PSA baseline violation (F-09), so a baseline app may not do it either.
    Vector("seccomp-Unconfined", _csc(seccompProfile={"type": "Unconfined"}), "S-04", "seccompProfile",
           restricted_only=True, baseline_rule="F-09"),
    Vector("volume-nfs", _volume({"nfs": {"server": "nas.example.com", "path": "/"}}), "S-05", "nfs", restricted_only=True),
    Vector("volume-gitRepo", _volume({"gitRepo": {"repository": "https://example.com/x.git"}}), "S-05", "gitRepo",
           restricted_only=True),
    Vector("procMount-Unmasked", _csc(procMount="Unmasked"), "F-10", "procMount"),
    Vector("unsafe-sysctl", _psc(sysctls=[{"name": "kernel.msgmax", "value": "65536"}]), "F-13", "sysctls"),
    Vector("selinux-spc_t", _csc(seLinuxOptions={"type": "spc_t"}), "F-12", "seLinuxOptions"),
    Vector("apparmor-Unconfined", _csc(appArmorProfile={"type": "Unconfined"}), "F-11", "appArmorProfile"),
    Vector("ephemeral-volume-storageclass",
           _volume({"ephemeral": {"volumeClaimTemplate": {"spec": {
               "storageClassName": "escape-hostpath", "accessModes": ["ReadWriteOnce"],
               "resources": {"requests": {"storage": "1Gi"}}}}}}),
           None, "ephemeral",
           gap="a generic ephemeral volume creates a PVC whose storageClassName P-01 never sees (P-01 checks only "
               "PersistentVolumeClaims and StatefulSet claim templates)"),
]
CONTROL = Vector("control", lambda p: None, None, "")


def pod_cases():
    for v in POD_VECTORS:
        for kind in ALLOWED_KINDS + REFUSED_KINDS:
            yield pytest.param(v, kind, id=f"{v.name}-in-{kind}")


@pytest.mark.parametrize("kind", ALLOWED_KINDS + REFUSED_KINDS)
def test_clean_workload_is_allowed_only_for_allowed_kinds(rules, kind):
    got = {v.rule for v in refusals(rules, [workload(kind, clean_pod())])}
    assert got == (set() if kind in ALLOWED_KINDS else {"K-01"}), got


@pytest.mark.parametrize(("vector", "kind"), list(pod_cases()))
def test_pod_vector_is_refused(rules, vector, kind, request):
    pod = clean_pod()
    vector.mutate(pod)
    found = refusals(rules, [workload(kind, pod)])
    if kind in REFUSED_KINDS:
        assert {v.rule for v in found} == {"K-01"}, [v.to_json() for v in found]
        return
    if vector.gap:
        request.applymarker(pytest.mark.xfail(strict=True, reason="gap: " + vector.gap))
        assert found, f"{vector.name} in a {kind} was not refused"
        return
    hits = [v for v in found if v.rule == vector.rule]
    assert hits, f"{vector.name} in a {kind}: expected {vector.rule}, got {[v.to_json() for v in found]}"
    assert any(vector.field in (v.path or "") for v in hits), [v.to_json() for v in hits]


@pytest.fixture(scope="module")
def baseline_app(rules):
    """An app the rule file reviewed for PSA baseline (home-assistant today)."""
    for app_id, entry in sorted(rules.reviewed.items()):
        if entry.get("level") == "baseline":
            return app_id
    pytest.skip("no app is reviewed for baseline in the rule file")


GITREPO_BASELINE = ("gitRepo volumes clone with git on the node (CVE-2024-10220); PSA baseline allows them, and the "
                    "checker refuses volume types only under restricted")


@pytest.mark.parametrize("vector", POD_VECTORS, ids=lambda v: v.name)
def test_pod_vector_under_baseline(rules, baseline_app, vector, request):
    """A reviewed baseline app may run as root, but never escape: every F- rule still holds."""
    pod = clean_pod()
    vector.mutate(pod)
    manifest = {**MANIFEST, "metadata": {"id": baseline_app}}
    found = refusals(rules, [workload("Deployment", pod)], app_id=baseline_app, manifest=manifest)
    if vector.name == "volume-gitRepo":
        request.applymarker(pytest.mark.xfail(strict=True, reason="gap: " + GITREPO_BASELINE))
        assert found
        return
    if vector.restricted_only and vector.baseline_rule:
        assert vector.baseline_rule in {v.rule for v in found}, [v.to_json() for v in found]
        assert "S-04" not in {v.rule for v in found}, "baseline is not restricted: S- rules do not apply"
        return
    if vector.restricted_only:
        assert not found, "baseline is not restricted: S- rules do not apply"
        return
    if vector.gap:
        request.applymarker(pytest.mark.xfail(strict=True, reason="gap: " + vector.gap))
        assert found
        return
    assert vector.rule in {v.rule for v in found}, [v.to_json() for v in found]


def test_reviewed_capability_does_not_leak_to_other_apps(rules):
    """capabilities.add_allowed is per rule file; a capability reviewed for one app is not global."""
    pod = clean_pod()
    _caps("NET_BIND_SERVICE")(pod)
    assert refusals(rules, [workload("Deployment", pod)]) == []  # PSA restricted allows exactly this one
    for app_id, entry in rules.reviewed.items():
        for cap in entry.get("add_capabilities") or []:
            pod = clean_pod()
            _caps(cap)(pod)
            assert "F-07" in {v.rule for v in refusals(rules, [workload("Deployment", pod)])}, (app_id, cap)


# ---- 2. object-level fixtures ------------------------------------------------------------------------------
def expected_of(text: str, where: str) -> str:
    m = EXPECTED.search(text)
    assert m, f"{where}: say `Expected: <rule>.`, `Expected: allowed.` or `Expected: gap.`"
    return m.group(1)


OBJECT_FILES = sorted(OBJECTS.glob("*.yaml"))


@pytest.mark.parametrize("path", OBJECT_FILES, ids=lambda p: p.stem)
def test_object_fixture_is_refused(rules, path, request):
    text = path.read_text()
    want = expected_of(text, path.name)
    docs = policy.parse_rendered(text)
    found = refusals(rules, docs)
    if want == "gap":
        gap = text.split("Expected: gap.", 1)[1].splitlines()[0].strip()
        request.applymarker(pytest.mark.xfail(strict=True, reason="gap: " + gap))
        assert found, f"{path.name} was not refused"
        return
    assert want in {v.rule for v in found}, [v.to_json() for v in found]


# ---- 3. kustomization-level fixtures ----------------------------------------------------------------------
KUSTOMIZE_VECTORS = sorted(p for p in KUSTOMIZE.iterdir() if p.is_dir() and not p.name.startswith("_"))


def renderer() -> list[str] | None:
    if shutil.which("kustomize"):
        return ["kustomize", "build"]
    if shutil.which("kubectl"):
        return ["kubectl", "kustomize"]
    return None


def stage(vector: Path, tmp_path: Path) -> Path:
    """Copy the vector into a scratch app folder, add the shared base and, for the symlink case, a
    link to a file outside the app folder."""
    root = tmp_path / "apps"
    app = root / APP_ID
    shutil.copytree(vector, app)
    shutil.copy(KUSTOMIZE / "_base" / "deployment.yaml", app / "manifests" / "deployment.yaml")
    (root / "tokens.yaml").write_text("tokens: {}\n")  # what the outside-reaching vectors aim at
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "kustomization.yaml").write_text("resources: []\n")
    if vector.name == "symlink-resource":
        loot = tmp_path / "loot.yaml"
        loot.write_text("apiVersion: v1\nkind: ConfigMap\nmetadata: {name: loot}\n")
        (app / "manifests" / "loot.yaml").symlink_to(loot)
    return app


@pytest.mark.parametrize("vector", KUSTOMIZE_VECTORS, ids=lambda p: p.name)
def test_kustomization_vector_is_refused(rules, vector, tmp_path):
    want = expected_of((vector / "manifests" / "kustomization.yaml").read_text(), vector.name)
    app = stage(vector, tmp_path)
    found = policy.check_kustomization(app / "manifests", app, rules)
    if want.startswith("Z-"):
        assert want in {v.rule for v in found}, [v.to_json() for v in found]
        return
    assert not found, [v.to_json() for v in found]  # a local, plugin-free kustomization renders
    cmd = renderer()
    if cmd is None:
        pytest.skip("needs kustomize or kubectl to render (both are on the GitHub ubuntu runners)")
    out = subprocess.run([*cmd, str(app / "manifests")], capture_output=True, text=True, timeout=60, cwd=tmp_path)
    assert out.returncode == 0, out.stderr
    found = refusals(rules, policy.parse_rendered(out.stdout))
    if want == "allowed":
        assert found == [], [v.to_json() for v in found]
    else:
        assert want in {v.rule for v in found}, [v.to_json() for v in found]


# ---- the fixture set keeps up with the rule file ----------------------------------------------------------
def test_every_object_rule_has_an_escape_fixture(rules):
    """A new rule in sdk/policy/app-objects.yaml needs an escape here that proves it bites."""
    covered = {v.rule for v in POD_VECTORS if v.rule}
    covered |= {v.baseline_rule for v in POD_VECTORS if v.baseline_rule}  # proved by test_pod_vector_under_baseline
    covered |= {expected_of(p.read_text(), p.name) for p in OBJECT_FILES}
    covered |= {expected_of((p / "manifests" / "kustomization.yaml").read_text(), p.name) for p in KUSTOMIZE_VECTORS}
    manifest_level = {"G-01", "G-02", "X-01"}  # about onemind.app.yaml, covered by the sandbox stream's own tests
    missing = sorted(set(rules.messages) - covered - manifest_level)
    assert not missing, f"rules with no escape fixture in core/tests/security: {missing}"


def test_vectors_are_independent_of_each_other():
    """Each generated vector changes a fresh copy: no mutation leaks into the clean pod."""
    before = copy.deepcopy(clean_pod())
    for v in POD_VECTORS:
        v.mutate(clean_pod())
    assert clean_pod() == before
    assert len({v.name for v in POD_VECTORS}) == len(POD_VECTORS)
    assert yaml.safe_dump(workload("CronJob", clean_pod()))
