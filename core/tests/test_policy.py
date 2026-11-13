# SPDX-License-Identifier: Apache-2.0
"""Install sandbox (H-01..H-04, docs/leap/core/SANDBOX.md): rule file, checker, executor, API."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from conftest import conform_to_schema, OWNER, FakeKubectl, action_body, fake_kustomize, write_scan
from onemind_core import policy
from onemind_core.app import create_app
from onemind_core.catalog import AppEntry, Catalog
from onemind_core.executors import KubernetesExecutor, kubectl_hub_addresses
from onemind_core.policy import SandboxSettings

REPO = Path(__file__).resolve().parents[2]
RULES_FILE = REPO / "sdk" / "policy" / "app-objects.yaml"
FIXTURES = REPO / "sdk" / "policy" / "fixtures"
SCHEMA = REPO / "sdk" / "schema" / "onemind.app.schema.json"
SEED_APPS = ("ntfy", "uptime-kuma", "home-assistant")


def expected(app_dir: Path) -> str | None:
    m = re.search(r"Expected: ([A-Z]-\d\d|allowed)\.", (app_dir / "onemind.app.yaml").read_text())
    assert m, app_dir
    return None if m.group(1) == "allowed" else m.group(1)


def entry(app_dir: Path) -> AppEntry:
    return AppEntry(id=app_dir.name, dir=app_dir, manifest=yaml.safe_load((app_dir / "onemind.app.yaml").read_text()))


BAD = sorted(p for p in FIXTURES.iterdir() if p.is_dir() and p.name.startswith("bad-"))


@pytest.fixture(scope="module")
def rules():
    return policy.load_rules(RULES_FILE)


def test_rule_file_loads_and_every_rule_has_a_message(rules):
    assert rules.version >= 1 and rules.psa_default == "restricted"
    used = set(re.findall(r'"([A-Z]-\d\d)"', (REPO / "core" / "onemind_core" / "policy.py").read_text()))
    assert used <= set(rules.messages), used - set(rules.messages)
    cluster_scoped = {"Namespace", "ClusterRole", "ClusterRoleBinding", "CustomResourceDefinition", "PersistentVolume",
                      "StorageClass", "ValidatingWebhookConfiguration", "MutatingWebhookConfiguration"}
    assert not cluster_scoped & {kind for _, kind in rules.allow}


def test_rule_file_refuses_bad_shapes(tmp_path):
    bad = tmp_path / "rules.yaml"
    bad.write_text("schema: something-else\nversion: 1\n")
    with pytest.raises(ValueError):
        policy.load_rules(bad)
    bad.write_text(RULES_FILE.read_text().replace("level: baseline", "level: privileged"))
    with pytest.raises(ValueError):
        policy.load_rules(bad)


def test_fixture_set_covers_the_threat_model():
    rules_hit = {expected(p) for p in BAD}
    # H-02 acceptance list plus the task's: cluster-scoped kinds, RBAC, hostPath/Network/PID/IPC,
    # privileged, capabilities, NodePort/LoadBalancer, digests, remote bases, foreign namespace.
    assert {"K-01", "R-01", "R-02", "R-03", "F-01", "F-02", "F-03", "F-04", "F-05", "F-06", "F-07",
            "V-01", "V-02", "I-01", "Z-01", "Z-02", "Z-03", "N-01", "S-01", "P-01", "G-01", "X-01"} <= rules_hit


@pytest.mark.parametrize("app_dir", BAD, ids=lambda p: p.name)
def test_bad_fixture_is_refused_by_the_checker(app_dir, rules):
    app = entry(app_dir)
    violations = policy.check_kustomization(app.manifests_dir, app.dir, rules)
    if not violations:
        docs = policy.parse_rendered(fake_kustomize(app.manifests_dir))
        violations = policy.check_objects(docs, app.id, app.manifest, rules)
        violations += policy.egress_entries(app.id, app.manifest, rules)[1]
    assert expected(app_dir) in {v.rule for v in violations}, [v.to_json() for v in violations]


@pytest.mark.parametrize("app_dir", BAD, ids=lambda p: p.name)
def test_bad_fixture_never_reaches_the_cluster(app_dir, rules):
    run = FakeKubectl()
    res = KubernetesExecutor(runner=run, rules=rules).run("app.install", entry(app_dir))
    assert res.outcome == "failed"
    assert expected(app_dir) in {v["rule"] for v in res.violations}
    assert run.cluster_calls == []  # only the local render (if any) ran; nothing was applied
    # a remote or escaping kustomization is refused before rendering
    if expected(app_dir).startswith("Z-"):
        assert run.calls == []


def test_good_fixture_installs(rules):
    run = FakeKubectl()
    res = KubernetesExecutor(runner=run, rules=rules).run("app.install", entry(FIXTURES / "good-minimal"))
    assert res.outcome == "succeeded" and res.violations is None
    allow = json.loads(run.cluster_calls[1][1].split("\n---\n")[1])
    # egress: none -> only DNS and its own namespace
    assert len(allow["spec"]["egress"]) == 2


@pytest.mark.parametrize("app_id", SEED_APPS)
def test_seed_apps_pass(app_id, rules):
    app = entry(REPO / "apps" / app_id)
    assert policy.check_kustomization(app.manifests_dir, app.dir, rules) == []
    docs = policy.parse_rendered(fake_kustomize(app.manifests_dir))
    assert policy.check_objects(docs, app_id, app.manifest, rules) == []
    level = policy.pod_security_level(app_id, app.manifest, rules)[0]
    assert level == ("baseline" if app_id == "home-assistant" else "restricted")


@pytest.mark.skipif(shutil.which("kustomize") is None, reason="kustomize not installed")
@pytest.mark.parametrize("app_id", SEED_APPS)
def test_seed_apps_pass_with_the_real_renderer(app_id, rules):
    app = entry(REPO / "apps" / app_id)
    out = subprocess.run(["kustomize", "build", str(app.manifests_dir)], capture_output=True, text=True, check=True)
    assert policy.check_objects(policy.parse_rendered(out.stdout), app_id, app.manifest, rules) == []


def test_psa_levels(rules):
    m = {"spec": {"security": {"podSecurity": "baseline"}}}
    assert policy.pod_security_level("home-assistant", {}, rules) == ("baseline", None)
    assert policy.pod_security_level("home-assistant", {"spec": {"security": {"podSecurity": "restricted"}}}, rules)[0] == "restricted"
    level, v = policy.pod_security_level("ntfy", m, rules)
    assert level == "restricted" and v.rule == "G-01"
    assert policy.pod_security_level("x", {"spec": {"security": {"podSecurity": "privileged"}}}, rules)[1].rule == "G-01"


@pytest.mark.parametrize(("rule", "ok"), [
    ({"apiGroups": [""], "resources": ["configmaps", "pods/log"], "verbs": ["get", "list"]}, True),
    ({"apiGroups": ["apps"], "resources": ["deployments"], "verbs": ["get", "patch"]}, True),
    ({"apiGroups": [""], "resources": ["namespaces"], "verbs": ["patch"]}, False),
    ({"apiGroups": [""], "resources": ["namespaces/status"], "verbs": ["update"]}, False),
    ({"apiGroups": ["networking.k8s.io"], "resources": ["networkpolicies"], "verbs": ["create"]}, False),
    ({"apiGroups": [""], "resources": ["pods/exec"], "verbs": ["create"]}, False),
    ({"apiGroups": [""], "resources": ["serviceaccounts/token"], "verbs": ["create"]}, False),
    ({"apiGroups": [""], "resources": ["pods/*"], "verbs": ["get"]}, False),
    ({"apiGroups": ["rbac.authorization.k8s.io"], "resources": ["roles"], "verbs": ["get"]}, False),
    ("not-a-mapping", False),
])
def test_app_role_rules(rules, rule, ok):
    role = {"apiVersion": "rbac.authorization.k8s.io/v1", "kind": "Role", "metadata": {"name": "r"}, "rules": [rule]}
    hit = {v.rule for v in policy.check_objects([role], "x", {}, rules)}
    assert (hit == set()) if ok else ("R-03" in hit)


def test_kustomize_references_must_exist_in_the_app(tmp_path, rules):
    m = tmp_path / "manifests"
    m.mkdir()
    (m / "objects.yaml").write_text("{}\n")
    (m / "kustomization.yaml").write_text(
        "resources: [objects.yaml]\nreplacements: [{path: missing.yaml}]\n"
        "patchesJson6902: [{path: ../../outside.yaml}]\n"
    )
    hit = {(v.rule, v.path) for v in policy.check_kustomization(m, tmp_path, rules)}
    assert hit == {("Z-01", "replacements"), ("Z-02", "patchesJson6902")}


def test_restricted_checks_apply_to_init_containers(rules):
    d = next(yaml.safe_load_all((FIXTURES / "good-minimal" / "manifests" / "objects.yaml").read_text()))
    d["spec"]["template"]["spec"]["initContainers"] = [{"name": "init", "image": "x@sha256:" + "b" * 64}]
    rules_hit = {v.rule for v in policy.check_objects([d], "good-minimal", {}, rules)}
    assert {"S-02", "S-03"} <= rules_hit


def test_network_policy_default_egress_is_internet_without_private_ranges(rules):
    deny, allow = policy.network_policies("x", ["internet"], rules)
    assert deny["spec"] == {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]}
    v4 = allow["spec"]["egress"][2]["to"][0]["ipBlock"]
    assert v4["cidr"] == "0.0.0.0/0" and "192.168.0.0/16" in v4["except"] and "10.0.0.0/8" in v4["except"]
    assert allow["spec"]["ingress"][1]["from"][0]["namespaceSelector"]["matchLabels"] == {"onemind.io/role": "gateway-proxy"}
    lan = policy.network_policies("x", ["192.168.1.0/24"], rules)[1]
    assert {"ipBlock": {"cidr": "192.168.1.0/24"}} in lan["spec"]["egress"][2]["to"]


def test_gateway_rolebinding_when_configured(rules):
    run = FakeKubectl()
    ex = KubernetesExecutor(runner=run, rules=rules, sandbox=SandboxSettings(gateway_sa="onemind-system/onemind-gateway"))
    assert ex.run("app.install", entry(FIXTURES / "good-minimal")).outcome == "succeeded"
    rb = json.loads(run.cluster_calls[1][1])
    assert rb["kind"] == "RoleBinding" and rb["metadata"]["namespace"] == "app-good-minimal"
    assert rb["roleRef"] == {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": "onemind-app-deployer"}
    assert rb["subjects"] == [{"kind": "ServiceAccount", "name": "onemind-gateway", "namespace": "onemind-system"}]


def test_forbidden_right_after_the_rolebinding_is_retried(rules):
    calls = {"n": 0}

    class Flaky(FakeKubectl):
        def __call__(self, argv, **kw):
            if argv[1:2] == ["apply"] and "onemind-default-deny" in (kw.get("input") or ""):
                calls["n"] += 1
                if calls["n"] == 1:
                    self.calls.append((argv, kw.get("input")))
                    return subprocess.CompletedProcess(argv, 1, stdout="", stderr="Error: ... is forbidden: User ...")
            return super().__call__(argv, **kw)

    slept = []
    ex = KubernetesExecutor(runner=Flaky(), rules=rules, sleep=slept.append,
                            sandbox=SandboxSettings(gateway_sa="onemind-system/onemind-gateway"))
    assert ex.run("app.install", entry(FIXTURES / "good-minimal")).outcome == "succeeded"
    assert slept == [1.0]


def test_executor_refuses_to_start_without_rules(tmp_path):
    with pytest.raises(ValueError, match="sandbox rules"):
        KubernetesExecutor(sandbox=SandboxSettings(rules=tmp_path / "missing.yaml"))


def test_sandbox_settings_validate():
    with pytest.raises(ValueError):
        SandboxSettings(gateway_sa="no-slash").validate()


def test_approve_returns_policy_refused_and_fails_the_action(settings, clock, rules):
    shutil.copytree(FIXTURES / "bad-clusterrolebinding", settings.apps_dir / "bad-clusterrolebinding")
    conform_to_schema(settings.apps_dir / "bad-clusterrolebinding")
    write_scan(settings.apps_dir / "bad-clusterrolebinding", clock.now)
    run = FakeKubectl()
    s = replace(settings, executor="kubernetes", app_schema_path=SCHEMA)
    with TestClient(create_app(s, clock=clock, executor=KubernetesExecutor(runner=run, rules=rules))) as c:
        r = c.post("/v1/actions", json=action_body(clock, app_id="bad-clusterrolebinding"), headers=OWNER)
        assert r.status_code == 201, r.text
        aid = r.json()["id"]
        r = c.post(f"/v1/actions/{aid}/approve", headers=OWNER)
        assert r.status_code == 409
        body = r.json()
        assert body["error"] == "policy_refused"
        assert body["details"][0]["rule"] == "K-01" and "ClusterRoleBinding/evil-admin" in body["details"][0]["field"]
        action = c.get(f"/v1/actions/{aid}", headers=OWNER).json()
        assert action["state"] == "failed"
        assert action["result"]["violations"][0]["kind"] == "ClusterRoleBinding"
        assert run.cluster_calls == []
    lines = [json.loads(x) for x in settings.audit_path.read_text().splitlines()]
    events = [x["event"] for x in lines]
    assert "policy.refused" in events and "action.rejected" not in events


def _hub_rule(allow):
    return [r for r in allow["spec"]["ingress"] if r["from"] and "ipBlock" in r["from"][0]]


def test_network_policy_lets_only_the_hub_host_reach_the_web_port(rules):
    allow = policy.network_policies(
        "x", ["none"], rules, gateway_sources=["10.42.0.0", "192.0.2.10"], gateway_ports=[8080, 80])[1]
    [rule] = _hub_rule(allow)
    assert rule["from"] == [{"ipBlock": {"cidr": "10.42.0.0/32"}}, {"ipBlock": {"cidr": "192.0.2.10/32"}}]
    assert rule["ports"] == [{"protocol": "TCP", "port": 80}, {"protocol": "TCP", "port": 8080}]
    assert policy.network_policies("x", ["none"], rules, gateway_sources=["2001:db8::1"], gateway_ports=[80])[1][
        "spec"]["ingress"][-1]["from"] == [{"ipBlock": {"cidr": "2001:db8::1/128"}}]


def test_network_policy_has_no_hub_rule_without_an_address_or_a_port(rules):
    for kw in ({}, {"gateway_sources": ["10.42.0.0"]}, {"gateway_ports": [80]}):
        assert _hub_rule(policy.network_policies("x", ["none"], rules, **kw)[1]) == []


def test_web_ports_follow_the_service_target_port():
    manifest = {"spec": {"web": {"port": 8080}}}
    docs = [
        {"kind": "Deployment", "spec": {"template": {"spec": {"containers": [{"ports": [{"name": "http", "containerPort": 80}]}]}}}},
        {"kind": "Service", "spec": {"ports": [{"port": 8080, "targetPort": "http"}, {"port": 9999, "targetPort": 9}]}},
    ]
    assert policy.web_ports(manifest, docs) == [80, 8080]
    assert policy.web_ports({"spec": {}}, docs) == []


def test_install_applies_the_hub_rule_only_for_the_web_port(rules, tmp_path):
    app_dir = tmp_path / "good-minimal"
    shutil.copytree(FIXTURES / "good-minimal", app_dir)
    manifest = yaml.safe_load((app_dir / "onemind.app.yaml").read_text())
    manifest["spec"]["web"] = {"port": 80}
    (app_dir / "onemind.app.yaml").write_text(yaml.safe_dump(manifest))
    run = FakeKubectl()
    ex = KubernetesExecutor(runner=run, rules=rules, hub_addresses=lambda: ["10.42.0.0", "192.0.2.10"])
    assert ex.run("app.install", entry(app_dir)).outcome == "succeeded"
    docs = [json.loads(d) for d in run.cluster_calls[1][1].split("\n---\n")]
    allow = next(d for d in docs if d["metadata"]["name"] == "onemind-allow")
    [rule] = _hub_rule(allow)
    assert [b["ipBlock"]["cidr"] for b in rule["from"]] == ["10.42.0.0/32", "192.0.2.10/32"]
    assert rule["ports"] == [{"protocol": "TCP", "port": 80}]
    # no known hub address: the policy stays closed
    run2 = FakeKubectl()
    assert KubernetesExecutor(runner=run2, rules=rules).run("app.install", entry(app_dir)).outcome == "succeeded"
    assert "ipBlock" not in run2.cluster_calls[1][1].split("onemind-allow")[1].split('"egress"')[0]


def test_kubectl_hub_addresses_reads_this_hosts_node():
    nodes = {"items": [
        {"metadata": {"name": "hub"}, "spec": {"podCIDR": "10.42.0.0/24", "podCIDRs": ["10.42.0.0/24"]},
         "status": {"addresses": [{"type": "InternalIP", "address": "192.0.2.10"}, {"type": "Hostname", "address": "hub"}]}},
        {"metadata": {"name": "node"}, "spec": {"podCIDR": "10.42.1.0/24"},
         "status": {"addresses": [{"type": "InternalIP", "address": "192.0.2.11"}]}},
    ]}

    def runner(argv, **kw):
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(nodes), stderr="")

    find = kubectl_hub_addresses
    assert find(runner=runner, hostname="Hub.lan")() == ["10.42.0.0", "192.0.2.10"]
    assert find(runner=runner, hostname="other")() == []
    assert find(runner=lambda argv, **kw: subprocess.CompletedProcess(argv, 1, stdout="", stderr="x"), hostname="hub")() == []
