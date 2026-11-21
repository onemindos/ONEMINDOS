# SPDX-License-Identifier: Apache-2.0
"""§12.22 dependency network paths: a satisfied dependency opens one narrow, owner-approved path
through the per-app default-deny NetworkPolicy (H-04), and removing the dependent closes it."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from conftest import OWNER, FakeKubectl, make_client
from onemind_core import policy
from onemind_core.appstore import deps
from onemind_core.catalog import AppEntry
from onemind_core.executors import KubernetesExecutor, NoopExecutor
from onemind_core.lifecycle import ExecContext
from test_appstore import CtxSpyExecutor, add_app, install, request, run

REPO = Path(__file__).resolve().parents[2]
RULES = policy.load_rules(REPO / "sdk" / "policy" / "app-objects.yaml")
NS_LABEL = "kubernetes.io/metadata.name"


# ---- the policy objects ----------------------------------------------------------------------------

def test_dependency_policies_open_exactly_one_namespace_per_path_on_tcp():
    docs = policy.dependency_policies("library-chat", [("kiwix", 8080), ("ollama", 11434)])
    egress, *ingress = docs
    assert egress["metadata"] == {"name": "onemind-dependencies", "namespace": "app-library-chat", "labels": {
        "onemind.io/app": "library-chat", "onemind.io/managed-by": "onemind-gateway",
        "onemind.io/dependent": "library-chat"}}
    assert egress["spec"]["policyTypes"] == ["Egress"] and egress["spec"]["podSelector"] == {}
    assert egress["spec"]["egress"] == [
        {"to": [{"namespaceSelector": {"matchLabels": {NS_LABEL: "app-kiwix"}}, "podSelector": {}}],
         "ports": [{"protocol": "TCP", "port": 8080}]},
        {"to": [{"namespaceSelector": {"matchLabels": {NS_LABEL: "app-ollama"}}, "podSelector": {}}],
         "ports": [{"protocol": "TCP", "port": 11434}]},
    ]
    assert [(d["metadata"]["namespace"], d["metadata"]["name"]) for d in ingress] == [
        ("app-kiwix", "onemind-dependent-library-chat"), ("app-ollama", "onemind-dependent-library-chat")]
    for d, port in zip(ingress, (8080, 11434)):
        assert d["metadata"]["labels"]["onemind.io/managed-by"] == "onemind-gateway"
        assert d["metadata"]["labels"]["onemind.io/dependent"] == "library-chat"
        assert d["spec"] == {"podSelector": {}, "policyTypes": ["Ingress"], "ingress": [
            {"from": [{"namespaceSelector": {"matchLabels": {NS_LABEL: "app-library-chat"}}, "podSelector": {}}],
             "ports": [{"protocol": "TCP", "port": port}]}]}


def test_dependency_policies_never_widen():
    """No wildcard namespace, no ipBlock, no UDP, no host: every peer names one exact namespace."""
    docs = policy.dependency_policies("a", [("b", 80), ("b", 443), ("c", 5432)])
    text = json.dumps(docs)
    assert "ipBlock" not in text and "UDP" not in text and "hostNetwork" not in text
    for d in docs:
        for rule in d["spec"].get("egress", []) + d["spec"].get("ingress", []):
            peers = rule.get("to") or rule.get("from")
            assert all(set(p["namespaceSelector"]["matchLabels"]) == {NS_LABEL} for p in peers)
            assert all(p["podSelector"] == {} for p in peers)
            assert rule["ports"] and all(p["protocol"] == "TCP" for p in rule["ports"])
    assert docs[0]["spec"]["egress"][0]["ports"] == [{"protocol": "TCP", "port": 80}, {"protocol": "TCP", "port": 443}]
    assert policy.dependency_policies("a", []) == []


@pytest.mark.parametrize("dependent, paths", [
    ("a", [("a", 80)]),           # to itself
    ("a", [("", 80)]),            # empty namespace name would be a wildcard-ish selector
    ("a", [("*", 80)]),
    ("a", [("kube-system", 0)]),
    ("a", [("b", 70000)]),
    ("a", [("b", True)]),
    ("a", [("B", 80)]),
    ("../x", [("b", 80)]),
])
def test_dependency_policies_refuse_bad_input(dependent, paths):
    with pytest.raises(ValueError):
        policy.dependency_policies(dependent, paths)


def test_default_deny_is_unchanged_by_dependencies():
    """The H-04 objects for an app do not depend on whether it has dependencies."""
    assert policy.network_policies("library-chat", ["none"], RULES) == policy.network_policies("library-chat", ["none"], RULES)
    deny, allow = policy.network_policies("library-chat", ["none"], RULES)
    assert "app-kiwix" not in json.dumps(allow)


# ---- resolving the links -----------------------------------------------------------------------------

def _m(**spec):
    return {"spec": spec}


def test_links_pick_the_installed_provider_and_its_web_port():
    manifests = {"kiwix": _m(web={"port": 8080}), "ollama": _m(web={"port": 11434}), "llamacpp": _m(web={"port": 8000})}
    app = _m(dependencies=[{"id": "kiwix"}, {"id": "ollama", "alternatives": ["llamacpp"]}])
    found, warnings = deps.links("library-chat", app, manifests, {"kiwix", "llamacpp"})
    assert [(x.provider, x.port, x.requirement) for x in found] == [("kiwix", 8080, "kiwix"), ("llamacpp", 8000, "ollama")]
    assert warnings == []
    assert found[0].to_json("library-chat") == {"from": "app-library-chat", "to": "app-kiwix", "provider": "kiwix",
                                                "port": 8080, "protocol": "TCP", "requirement": "kiwix"}


def test_links_port_field_wins_and_unknown_port_opens_nothing():
    manifests = {"pg": _m(), "web": _m(web={"port": 80})}
    app = _m(dependencies=[{"id": "pg", "port": 5432}, {"id": "web", "port": 8443}, {"id": "nope"}])
    found, _ = deps.links("x", app, manifests, {"pg", "web"})
    assert [(x.provider, x.port) for x in found] == [("pg", 5432), ("web", 8443)]
    found, warnings = deps.links("x", _m(dependencies=[{"id": "pg"}]), manifests, {"pg"})
    assert found == [] and "no network path is opened" in warnings[0]


def test_links_never_to_itself_or_an_uninstalled_app():
    manifests = {"x": _m(web={"port": 1})}
    assert deps.links("x", _m(dependencies=[{"id": "x"}]), manifests, {"x"}) == ([], [])
    assert deps.links("x", _m(dependencies=[{"id": "y"}]), {"y": _m(web={"port": 1})}, set()) == ([], [])
    for bad in (0, 70000, True, "80"):
        assert deps.requirements(_m(dependencies=[{"id": "y", "port": bad}]))[0].port is None


# ---- the executor --------------------------------------------------------------------------------------

def _entry(tmp_path: Path, app_id: str) -> AppEntry:
    """The good-minimal sandbox fixture under another id."""
    d = tmp_path / app_id
    shutil.copytree(REPO / "sdk" / "policy" / "fixtures" / "good-minimal", d)
    manifest = yaml.safe_load((d / "onemind.app.yaml").read_text())
    manifest["metadata"]["id"] = app_id
    return AppEntry(id=app_id, dir=d, manifest=manifest)


class Cluster(FakeKubectl):
    """FakeKubectl that answers the reads the dependency sync makes."""

    def __init__(self, services=None, pods=None, existing=None):
        super().__init__()
        self.services = services or {}  # namespace -> [Service]
        self.pods = pods or {}
        self.existing = existing  # the app's current onemind-dependencies policy, or None

    def __call__(self, argv, **kw):
        if argv[1:3] == ["get", "services"]:
            self.calls.append((argv, None))
            return subprocess.CompletedProcess(argv, 0, json.dumps({"items": self.services.get(argv[4], [])}), "")
        if argv[1:3] == ["get", "pods"]:
            self.calls.append((argv, None))
            return subprocess.CompletedProcess(argv, 0, json.dumps({"items": self.pods.get(argv[4], [])}), "")
        if argv[1:3] == ["get", "networkpolicy"]:
            self.calls.append((argv, None))
            return subprocess.CompletedProcess(argv, 0, json.dumps(self.existing) if self.existing else "", "")
        if argv[1:2] == ["get"]:  # the workloads of a lifecycle action
            self.calls.append((argv, None))
            return subprocess.CompletedProcess(argv, 0, json.dumps({"items": []}), "")
        return super().__call__(argv, **kw)

    def applied(self) -> list[dict]:
        return [json.loads(i) for a, i in self.calls if a[1] == "apply" and i and '"onemind.io/dependent"' in i]

    def deleted(self) -> list[tuple[str, str]]:
        return [(a[3], a[5]) for a, _ in self.calls if a[1:3] == ["delete", "networkpolicy"]]


def _svc(port, target):
    return {"spec": {"ports": [{"port": port, "targetPort": target, "protocol": "TCP"}]}}


def test_install_opens_the_paths_at_the_pod_port_before_the_manifests(tmp_path):
    k = Cluster(services={"app-kiwix": [_svc(8080, 8080)], "app-ollama": [_svc(11434, "http")]},
                pods={"app-ollama": [{"spec": {"containers": [{"ports": [{"name": "http", "containerPort": 11434}]}]}}]})
    ctx = ExecContext(dependency_paths=(("kiwix", 8080), ("ollama", 11434)), dependency_sync=True)
    res = KubernetesExecutor(runner=k, rules=RULES).run("app.install", _entry(tmp_path, "library-chat"), ctx=ctx)
    assert res.outcome == "succeeded", res.message
    docs = k.applied()
    assert [(d["metadata"]["namespace"], d["metadata"]["name"]) for d in docs] == [
        ("app-library-chat", "onemind-dependencies"),
        ("app-kiwix", "onemind-dependent-library-chat"), ("app-ollama", "onemind-dependent-library-chat")]
    assert docs[2]["spec"]["ingress"][0]["ports"] == [{"protocol": "TCP", "port": 11434}]
    # the manifests are the last apply, after the paths
    assert k.cluster_calls[-1][0][1] == "apply" and '"onemind.io/dependent"' not in (k.cluster_calls[-1][1] or "")


def test_unresolvable_port_opens_nothing_and_says_why(tmp_path):
    k = Cluster(services={"app-kiwix": [_svc(9999, 9999)]})
    ctx = ExecContext(dependency_paths=(("kiwix", 8080),), dependency_sync=True)
    res = KubernetesExecutor(runner=k, rules=RULES).run("app.install", _entry(tmp_path, "library-chat"), ctx=ctx)
    assert res.outcome == "succeeded"
    assert k.applied() == []
    assert {"network_path": "app-library-chat -> app-kiwix TCP 8080", "opened": False,
            "reason": "no Service in app-kiwix exposes TCP 8080"} in res.steps


def test_install_without_dependencies_makes_no_extra_call(tmp_path):
    plain, k = FakeKubectl(), FakeKubectl()
    KubernetesExecutor(runner=plain, rules=RULES).run("app.install", _entry(tmp_path / "a", "x"))
    KubernetesExecutor(runner=k, rules=RULES).run("app.install", _entry(tmp_path / "b", "x"), ctx=ExecContext())
    assert len(k.calls) == len(plain.calls)


def test_remove_closes_both_sides(tmp_path):
    existing = policy.dependency_policies("library-chat", [("kiwix", 8080), ("ollama", 11434)])[0]
    k = Cluster(existing=existing)
    res = KubernetesExecutor(runner=k, rules=RULES).run(
        "app.remove", _entry(tmp_path, "library-chat"), ctx=ExecContext(dependency_sync=True))
    assert res.outcome == "succeeded", res.message
    assert k.applied() == []
    assert k.deleted() == [("onemind-dependencies", "app-library-chat"),
                           ("onemind-dependent-library-chat", "app-kiwix"),
                           ("onemind-dependent-library-chat", "app-ollama")]


def test_configure_closes_a_path_that_is_no_longer_linked(tmp_path):
    existing = policy.dependency_policies("library-chat", [("kiwix", 8080), ("ollama", 11434)])[0]
    k = Cluster(existing=existing, services={"app-kiwix": [_svc(8080, 8080)]})
    ctx = ExecContext(dependency_paths=(("kiwix", 8080),), dependency_sync=True, settings={"A": "1"})
    res = KubernetesExecutor(runner=k, rules=RULES).run("app.configure", _entry(tmp_path, "library-chat"), ctx=ctx)
    assert res.outcome == "succeeded", res.message
    assert [d["metadata"]["namespace"] for d in k.applied()] == ["app-library-chat", "app-kiwix"]
    assert k.deleted() == [("onemind-dependent-library-chat", "app-ollama")]


def test_remove_of_an_app_that_never_had_paths_reads_once_and_deletes_nothing(tmp_path):
    k = Cluster()
    res = KubernetesExecutor(runner=k, rules=RULES).run("app.remove", _entry(tmp_path, "x"), ctx=ExecContext(dependency_sync=True))
    assert res.outcome == "succeeded" and k.deleted() == []


def test_noop_executor_describes_the_paths(tmp_path):
    ctx = ExecContext(dependency_paths=(("kiwix", 8080),), dependency_sync=True)
    res = NoopExecutor().run("app.install", _entry(tmp_path, "library-chat"), ctx=ctx)
    assert any("open network path app-library-chat -> app-kiwix on TCP 8080" in s.get("would", "") for s in res.steps)


# ---- through the API: plan, approval, standing approvals -------------------------------------------------

@pytest.fixture
def lib(settings, clock):
    add_app(settings, clock, "kiwix", web={"port": 8080})
    add_app(settings, clock, "ollama", web={"port": 11434})
    add_app(settings, clock, "plain")
    add_app(settings, clock, "library-chat", web={"port": 3000},
            dependencies=[{"id": "kiwix", "reason": "search"}, {"id": "ollama", "reason": "chat"}])
    return settings


def test_plan_shows_the_opened_paths_and_the_executor_gets_exactly_those(lib, clock):
    spy = CtxSpyExecutor()
    with make_client(lib, clock, spy) as c:
        install(c, clock, "kiwix")
        install(c, clock, "ollama")
        plan = c.get("/v1/apps/library-chat/plan?type=app.install", headers=OWNER).json()
        paths = plan["plan"]["network_paths"]
        assert [(p["to"], p["port"], p["protocol"]) for p in paths] == [("app-kiwix", 8080, "TCP"), ("app-ollama", 11434, "TCP")]
        assert "Opens a network path: app-library-chat → app-kiwix on TCP 8080 (needs kiwix)." in plan["plan"]["warnings"]
        assert plan["plan"]["objects"][0]["network_paths"] == paths  # hashed
        r = request(c, clock, "app.install", {"app_id": "library-chat"})
        assert r.status_code == 201 and r.json()["plan"]["network_paths"] == paths
        assert c.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER).json()["state"] == "succeeded"
        assert run(c, clock, "app.remove", {"app_id": "library-chat"}).json()["state"] == "succeeded"
    by_type = {t: x for t, x in spy.ctxs}
    assert by_type["app.install"].dependency_paths == (("kiwix", 8080), ("ollama", 11434))
    assert by_type["app.remove"].dependency_paths == () and by_type["app.remove"].dependency_sync


def test_app_without_dependencies_has_no_network_paths_key(lib, clock):
    with make_client(lib, clock, NoopExecutor()) as c:
        plan = c.get("/v1/apps/plain/plan?type=app.install", headers=OWNER).json()["plan"]
        assert "network_paths" not in plan and "network_paths" not in plan["objects"][0]


def test_a_changed_provider_is_a_different_plan(settings, clock):
    add_app(settings, clock, "ollama", web={"port": 11434})
    add_app(settings, clock, "llamacpp", web={"port": 8000})
    add_app(settings, clock, "chat", dependencies=[{"id": "ollama", "alternatives": ["llamacpp"]}])
    with make_client(settings, clock, NoopExecutor()) as c:
        install(c, clock, "llamacpp")
        r = request(c, clock, "app.install", {"app_id": "chat"})
        assert r.status_code == 201
        install(c, clock, "ollama")  # now ollama satisfies it first: the approved plan is stale
        a = c.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
        assert a.status_code == 409 and a.json()["reason"] == "plan_changed"


def test_standing_approval_never_opens_a_path(lib, clock):
    with make_client(lib, clock, NoopExecutor()) as c:
        actions = c.app.state.actions
        calls = []
        actions.standing_approvals.append(lambda a: calls.append(a.type))
        install(c, clock, "kiwix")
        install(c, clock, "ollama")
        install(c, clock, "library-chat")
        n = len(calls)
        r = request(c, clock, "app.update", {"app_id": "library-chat"})
        assert r.status_code == 201 and r.json()["state"] == "awaiting_approval"
        assert len(calls) == n  # the policy was never even asked
