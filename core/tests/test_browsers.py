# SPDX-License-Identifier: Apache-2.0
"""Browser apps in a desktop window, one profile per person (#692; browsers.py, routers/browsers.py).

The acceptance test of the issue: person A cannot reach person B's browser (403), the profile
survives a pod restart, and an unauthenticated request is refused. Also: no agent token opens a
person's browser, the shared template is never served, and a profile is erased only after an owner
approves. The cluster is a fake kubectl that keeps objects in memory; the proxy talks to a real
upstream on loopback (test_proxy.py's).
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import subprocess
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

import onemind_core.routers.browsers as browsers_router
from onemind_core.app import create_app
from onemind_core.auth import TokenStore
from onemind_core.browsers import (
    BrowserError, BrowserProfiles, BrowserSpec, browser_spec, load_secret, person_key, person_objects, split_host_label,
)
from onemind_core.catalog import Catalog
from onemind_core.executors import KubernetesExecutor
from onemind_core.policy import load_rules, network_policies
from onemind_core.proxy import AppProxy, AppProxyMiddleware, Timeouts, token_session_resolver
from conftest import ADULT, AGENT, GUEST, OWNER, ScriptedExecutor
from test_proxy import upstream_port  # noqa: F401  (module fixture: the loopback upstream)

APP = "firefox"
SECRET = bytes(range(32))  # the box's browser key secret in these tests


def key_of(person_id: str) -> str:
    return person_key(SECRET, person_id)


def template(port: int, *, host_port: bool = False) -> dict:
    """The app's own Deployment, as apps/firefox/manifests/deployment.yaml ships it (replicas 0)."""
    ports = [{"name": "http", "containerPort": port, **({"hostPort": port} if host_port else {})}]
    return {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": APP, "labels": {"app.kubernetes.io/name": APP}},
            "spec": {"replicas": 0, "selector": {"matchLabels": {"app.kubernetes.io/name": APP}},
                     "template": {"metadata": {"labels": {"app.kubernetes.io/name": APP}}, "spec": {
                         "containers": [{"name": APP, "image": "neko", "ports": ports, "env": [
                             {"name": "NEKO_MEMBER_MULTIUSER_USER_PASSWORD",
                              "valueFrom": {"secretKeyRef": {"name": f"{APP}-credentials", "key": "PASSWORD"}}},
                             {"name": "NEKO_MEMBER_MULTIUSER_ADMIN_PASSWORD",
                              "valueFrom": {"secretKeyRef": {"name": f"{APP}-credentials", "key": "PASSWORD"}}}],
                                         "volumeMounts": [{"name": "profile", "mountPath": "/profile"}]}],
                         "volumes": [{"name": "profile", "persistentVolumeClaim": {"claimName": f"{APP}-profile"}},
                                     {"name": "shm", "emptyDir": {"medium": "Memory"}}]}}}}


class FakeCluster:
    """kubectl get/apply/scale/delete over objects kept in memory, per namespace.

    A claim carries `data` (what the browser wrote) that only deleting the claim removes, so a test
    can see a profile survive its pod.
    """

    def __init__(self, port: int, *, cluster_ip: str = "127.0.0.1"):
        self.objects: dict[tuple[str, str, str], dict] = {}
        self.cluster_ip, self.serial, self.calls = cluster_ip, 0, []
        ns = f"app-{APP}"
        self.put(ns, template(port))
        self.put(ns, {"kind": "PersistentVolumeClaim", "metadata": {"name": f"{APP}-profile"},
                      "spec": {"accessModes": ["ReadWriteOnce"], "resources": {"requests": {"storage": "5Gi"}}}})

    def put(self, ns: str, obj: dict) -> None:
        self.serial += 1
        obj = json.loads(json.dumps(obj))
        obj["metadata"]["uid"] = f"uid-{self.serial}"
        if obj["kind"] == "Service":
            obj["spec"]["clusterIP"] = self.cluster_ip
        if obj["kind"] == "PersistentVolumeClaim":
            obj["data"] = {}
        self.objects[(ns, obj["kind"], obj["metadata"]["name"])] = obj

    def get(self, ns: str, kind: str, name: str) -> dict | None:
        return self.objects.get((ns, kind, name))

    def __call__(self, argv, input=None, **_):
        self.calls.append(argv)
        verb, args = argv[1], argv[2:]
        ns = args[args.index("-n") + 1]
        kinds = {"deployments": "Deployment", "deployment": "Deployment", "pvc": "PersistentVolumeClaim",
                 "service": "Service", "secret": "Secret"}

        def done(out: object = "") -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(argv, 0, out if isinstance(out, str) else json.dumps(out), "")

        missing = subprocess.CompletedProcess(argv, 1, "", 'Error from server (NotFound): not found')
        if verb == "get" and args[0] == "deployments":
            return done({"items": [o for (n, k, _), o in self.objects.items() if n == ns and k == "Deployment"]})
        if verb == "get":
            obj = self.get(ns, kinds[args[0]], args[1])
            return done(obj) if obj is not None else missing
        if verb == "create":
            obj = json.loads(input)
            if self.get(ns, obj["kind"], obj["metadata"]["name"]) is not None:
                return subprocess.CompletedProcess(argv, 1, "", "Error from server (AlreadyExists): exists")
            self.put(ns, obj)
            return done()
        if verb == "apply":
            for obj in json.loads(input)["items"]:
                if obj["kind"] == "Secret":
                    raise AssertionError("a login Secret was applied (its values would land in an annotation)")
                old = self.get(ns, obj["kind"], obj["metadata"]["name"])
                if old is not None and obj["kind"] == "PersistentVolumeClaim":
                    raise AssertionError("an existing profile claim was applied over")
                self.put(ns, obj)
            return done()
        if verb == "scale":
            dep = self.get(ns, "Deployment", args[0].split("/", 1)[1])
            if dep is None:
                return missing
            dep["spec"]["replicas"] = int(args[1].split("=", 1)[1])
            return done()
        if verb == "delete":
            self.objects.pop((ns, kinds[args[0]], args[1]), None)
            return done()
        raise AssertionError(f"unexpected kubectl call {argv}")


# ---- the model ------------------------------------------------------------------------------------
def test_person_key_is_one_way_stable_and_distinct():
    assert key_of("alice") == key_of("alice") != key_of("bob")
    assert all(c in "0123456789abcdef" for c in key_of("alice"))
    assert len(key_of("alice")) == 16 and "alice" not in key_of("alice")
    assert split_host_label(f"firefox--{key_of('alice')}") == ("firefox", key_of("alice"))
    assert split_host_label("firefox") is None and split_host_label("firefox--nothex") is None


def test_person_objects_mount_their_own_claim_and_publish_no_node_port():
    key = key_of("alice")
    pvc, dep, svc = person_objects(APP, key, BrowserSpec("profile", 8080), template(8080), {})
    assert pvc["metadata"]["name"] == f"profile-{key}"
    vols = dep["spec"]["template"]["spec"]["volumes"]
    assert {"name": "profile", "persistentVolumeClaim": {"claimName": f"profile-{key}"}} in vols
    assert all(v.get("persistentVolumeClaim", {}).get("claimName") != f"{APP}-profile" for v in vols)  # never shared
    assert svc["spec"]["type"] == "ClusterIP" and "nodePort" not in json.dumps(svc)
    assert dep["spec"]["selector"]["matchLabels"] == svc["spec"]["selector"] == {"onemind.io/browser-profile": key}


@pytest.mark.parametrize("bad", ["hostPort", "hostNetwork"])
def test_a_template_that_reaches_the_node_is_refused(bad):
    tpl = template(8080, host_port=bad == "hostPort")
    if bad == "hostNetwork":
        tpl["spec"]["template"]["spec"]["hostNetwork"] = True
    with pytest.raises(BrowserError):
        person_objects(APP, key_of("alice"), BrowserSpec("profile", 8080), tpl, {})


def test_profile_survives_pod_restart_and_close():
    cluster = FakeCluster(8080)
    profiles = BrowserProfiles(secret=SECRET, runner=cluster, ttl=0)
    key, ns, spec = key_of("alice"), f"app-{APP}", BrowserSpec("profile", 8080)
    profiles.open(APP, key, spec)
    claim = cluster.get(ns, "PersistentVolumeClaim", f"profile-{key}")
    claim["data"]["bookmarks"] = "onemind docs"
    cluster.objects.pop((ns, "Deployment", f"browser-{key}"))  # the pod goes away (node restart, crash)
    profiles.open(APP, key, spec)
    profiles.close(APP, key)
    assert cluster.get(ns, "Deployment", f"browser-{key}")["spec"]["replicas"] == 0
    profiles.open(APP, key, spec)
    again = cluster.get(ns, "PersistentVolumeClaim", f"profile-{key}")
    assert again["metadata"]["uid"] == claim["metadata"]["uid"] and again["data"] == {"bookmarks": "onemind docs"}
    assert cluster.get(ns, "Deployment", f"browser-{key}")["spec"]["replicas"] == 1


# ---- the proxy: each person reaches only their own browser ------------------------------------------
@pytest.fixture
def proxied(tmp_path: Path, upstream_port):  # noqa: F811
    toks = {who: secrets.token_urlsafe(24) for who in ("alice", "bob", "hermes")}
    (tmp_path / "tokens.yaml").write_text(yaml.safe_dump({"tokens": {
        toks["alice"]: {"id": "alice", "kind": "person", "role": "adult"},
        toks["bob"]: {"id": "bob", "kind": "person", "role": "adult"},
        toks["hermes"]: {"id": "hermes", "kind": "agent", "role": "agent"},
    }}))
    (tmp_path / "apps" / APP).mkdir(parents=True)
    (tmp_path / "apps" / APP / "onemind.app.yaml").write_text(yaml.safe_dump(browser_manifest(upstream_port)))
    cluster = FakeCluster(upstream_port)
    profiles = BrowserProfiles(secret=SECRET, runner=cluster, ttl=0)
    profiles.open(APP, key_of("alice"), BrowserSpec("profile", upstream_port))
    proxy = AppProxy(Catalog(tmp_path / "apps"), {APP: "installed"}.get,
                     token_session_resolver(TokenStore(tmp_path / "tokens.yaml")), lambda ns, port: "127.0.0.1",
                     box_domains=("onemind.local",), timeouts=Timeouts(connect=1, read=1, ws_open=2), route_ttl=0,
                     path_routes=True, browsers=profiles)
    gw = FastAPI()
    gw.add_middleware(AppProxyMiddleware, proxy=proxy)
    return {"app": gw, "tokens": toks}


def browser_manifest(port: int) -> dict:
    return {"apiVersion": "onemind.app/v1alpha1", "kind": "App",
            "metadata": {"id": APP, "name": "Firefox", "version": "3.2.0", "description": "Firefox", "category": "developer",
                         "license": "Apache-2.0", "source": "https://github.com/m1k1o/neko"},
            "spec": {"archs": ["amd64", "arm64"], "requires": {"gpu": False, "minMemoryMb": 1024},
                     "web": {"port": port}, "browser": {"profileVolume": "profile"}}}


def get(env, host: str, who: str | None, path: str = "/"):
    headers = {"Authorization": f"Bearer {env['tokens'][who]}"} if who else {}
    return TestClient(env["app"], base_url=f"http://{host}").get(path, headers=headers)


def test_person_reaches_only_their_own_browser(proxied):
    alice, bob = key_of("alice"), key_of("bob")
    r = get(proxied, f"{APP}--{alice}.onemind.local", "alice", "/neko")
    assert r.status_code == 200 and r.json()["path"] == "/neko"
    assert r.json()["headers"]["x-onemind-principal"] == "person:alice"
    assert get(proxied, f"{APP}--{alice}.onemind.local", "bob").status_code == 403  # A's browser, asked by B
    assert get(proxied, f"{APP}--{bob}.onemind.local", "bob").status_code == 404    # B never opened one


def test_unauthenticated_agent_and_shared_template_are_refused(proxied):
    alice = key_of("alice")
    assert get(proxied, f"{APP}--{alice}.onemind.local", None).status_code == 401
    assert get(proxied, f"{APP}--{alice}.onemind.local", "hermes").status_code == 403
    assert get(proxied, f"{APP}--{key_of('hermes')}.onemind.local", "hermes").status_code == 403
    assert get(proxied, f"{APP}.onemind.local", "alice").status_code == 403  # one shared profile: never
    assert get(proxied, "onemind.local", "alice", f"/apps/{APP}/").status_code == 403


# ---- the routes ---------------------------------------------------------------------------------------
@pytest.fixture
def gw(settings, clock, monkeypatch):
    app_dir = Path(settings.apps_dir) / APP
    app_dir.mkdir()
    (app_dir / "onemind.app.yaml").write_text(yaml.safe_dump(browser_manifest(8080)))
    cluster = FakeCluster(8080)
    monkeypatch.setattr(browsers_router, "BrowserProfiles",
                        lambda kubectl, secret: BrowserProfiles(kubectl, secret=secret, runner=cluster, ttl=0))
    client = TestClient(create_app(settings, clock=clock, executor=ScriptedExecutor()))
    client.app.state.repo.set_app_state(APP, "installed", clock.now)
    return client, cluster


def test_open_close_and_profile_kept(gw):
    client, cluster = gw
    key, ns = client.app.state.browsers.key_of("adult"), f"app-{APP}"
    r = client.post(f"/v1/browsers/{APP}/session", headers=ADULT)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["person_key"] == key and body["state"] == "starting" and body["profile"] == f"profile-{key}"
    assert body["url"] == f"http://{APP}--{key}.onemind.local/"
    assert cluster.get(ns, "Deployment", f"browser-{key}")["spec"]["replicas"] == 1
    uid = cluster.get(ns, "PersistentVolumeClaim", f"profile-{key}")["metadata"]["uid"]
    sec = cluster.get(ns, "Secret", f"browser-{key}")
    assert body["password"] == base64.b64decode(sec["data"]["PASSWORD"]).decode()  # their own member login
    assert r.headers["cache-control"] == "no-store"
    r = client.post(f"/v1/browsers/{APP}/session/close", headers=ADULT)
    assert r.status_code == 200 and r.json()["state"] == "stopped" and r.json()["password"] is None
    assert cluster.get(ns, "Deployment", f"browser-{key}")["spec"]["replicas"] == 0
    assert client.post(f"/v1/browsers/{APP}/session", headers=ADULT).status_code == 200
    assert cluster.get(ns, "PersistentVolumeClaim", f"profile-{key}")["metadata"]["uid"] == uid
    assert next(a for a in client.get("/v1/apps", headers=ADULT).json() if a["id"] == APP)["browser"] is True


def test_routes_refuse_unauthenticated_agents_and_other_apps(gw, clock):
    client, cluster = gw
    assert client.post(f"/v1/browsers/{APP}/session").status_code == 401
    r = client.post(f"/v1/browsers/{APP}/session", headers=AGENT)
    assert r.status_code == 403 and r.json()["error"] == "permission_denied"
    assert client.post(f"/v1/browsers/{APP}/profile/reset", headers=AGENT).status_code == 403
    assert client.post("/v1/browsers/whoami/session", headers=ADULT).status_code == 404
    client.app.state.repo.set_app_state(APP, "stopped", clock.now)
    assert client.post(f"/v1/browsers/{APP}/session", headers=ADULT).status_code == 409
    assert not any(k[1] == "PersistentVolumeClaim" and k[2].startswith("profile-") for k in cluster.objects)


def test_guest_below_the_access_level_is_refused(gw):
    client, _ = gw
    assert client.post(f"/v1/browsers/{APP}/session", headers=GUEST).status_code == 403  # web access: adults


def test_profile_reset_waits_for_an_owner(gw):
    client, cluster = gw
    key, ns = client.app.state.browsers.key_of("adult"), f"app-{APP}"
    client.post(f"/v1/browsers/{APP}/session", headers=ADULT)
    r = client.post(f"/v1/browsers/{APP}/profile/reset", headers=ADULT)
    assert r.status_code == 202, r.text
    action = r.json()
    assert action["type"] == "browser.profile.reset" and action["state"] == "awaiting_approval"
    assert action["params"] == {"app_id": APP, "person_key": key}
    assert cluster.get(ns, "PersistentVolumeClaim", f"profile-{key}") is not None  # nothing erased yet
    assert client.post(f"/v1/actions/{action['id']}/approve", headers=AGENT).status_code == 403
    assert client.post(f"/v1/actions/{action['id']}/approve", headers=ADULT).status_code == 403
    r = client.post(f"/v1/actions/{action['id']}/approve", headers=OWNER)
    assert r.status_code == 200 and r.json()["state"] == "succeeded", r.text
    assert cluster.get(ns, "PersistentVolumeClaim", f"profile-{key}") is None
    assert cluster.get(ns, "Deployment", f"browser-{key}") is None
    assert cluster.get(ns, "Secret", f"browser-{key}") is None  # the next open makes new logins


def test_dashboard_page_may_frame_browser_hosts_only(gw):
    client, _ = gw
    csp = client.get("/").headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp
    frames = csp.split("; frame-src ", 1)[1].split()
    assert "http://*.onemind.local" in frames and all(f.startswith("http://*.") for f in frames)


def test_manifest_without_web_port_is_not_a_browser():
    assert browser_spec({"spec": {"browser": {"profileVolume": "profile"}}}) is None
    assert browser_spec(browser_manifest(8080)) == BrowserSpec("profile", 8080)


# ---- review fixes: the key needs the box secret, logins are per person, pods reach no other pod ------------
REPO = Path(__file__).resolve().parents[2]


def test_key_cannot_be_worked_out_from_a_person_id(tmp_path):
    plain = hashlib.sha256(b"onemind-browser-profile\0alice").hexdigest()[:16]
    assert key_of("alice") != plain and person_key(bytes(32), "alice") != key_of("alice")
    with pytest.raises(BrowserError):
        person_key(b"short", "alice")
    with pytest.raises(BrowserError):
        BrowserProfiles(secret=b"short")
    path = tmp_path / "state" / "browser-profile.key"
    first = load_secret(path)
    assert len(first) == 32 and load_secret(path) == first and path.stat().st_mode & 0o777 == 0o600


def test_a_key_worked_out_without_the_box_secret_is_refused(proxied):
    plain = hashlib.sha256(b"onemind-browser-profile\0bob").hexdigest()[:16]
    assert get(proxied, f"{APP}--{plain}.onemind.local", "bob").status_code == 403


def test_each_person_gets_their_own_neko_logins():
    cluster, spec, ns = FakeCluster(8080), BrowserSpec("profile", 8080), f"app-{APP}"
    profiles = BrowserProfiles(secret=SECRET, runner=cluster, ttl=0)
    a, b = profiles.open(APP, key_of("alice"), spec), profiles.open(APP, key_of("bob"), spec)
    assert a != b and len(a) >= 24
    for who, password in (("alice", a), ("bob", b)):
        k = key_of(who)
        data = {n: base64.b64decode(v).decode() for n, v in cluster.get(ns, "Secret", f"browser-{k}")["data"].items()}
        assert data["PASSWORD"] == password and data["ADMIN_PASSWORD"] not in (a, b)
        env = {e["name"]: e["valueFrom"]["secretKeyRef"]
               for e in cluster.get(ns, "Deployment", f"browser-{k}")["spec"]["template"]["spec"]["containers"][0]["env"]}
        assert env["NEKO_MEMBER_MULTIUSER_USER_PASSWORD"] == {"name": f"browser-{k}", "key": "PASSWORD"}
        assert env["NEKO_MEMBER_MULTIUSER_ADMIN_PASSWORD"] == {"name": f"browser-{k}", "key": "ADMIN_PASSWORD"}
    assert profiles.open(APP, key_of("alice"), spec) == a  # kept across opens
    mine = [o for (_, _, name), o in cluster.objects.items() if name.startswith(("browser-", "profile-"))]
    assert f"{APP}-credentials" not in json.dumps(mine)  # the shared login reaches no person's pod
    assert any(c[1] == "create" for c in cluster.calls)


@pytest.mark.parametrize("how", ["envFrom", "volume", "other-key"])
def test_a_template_that_hands_out_the_shared_login_is_refused(how):
    tpl = template(8080)
    pod = tpl["spec"]["template"]["spec"]
    if how == "envFrom":
        pod["containers"][0]["envFrom"] = [{"secretRef": {"name": f"{APP}-credentials"}}]
    elif how == "volume":
        pod["volumes"].append({"name": "login", "secret": {"secretName": f"{APP}-credentials"}})
    else:
        pod["containers"][0]["env"][0]["valueFrom"]["secretKeyRef"]["key"] = "USERNAME"
    with pytest.raises(BrowserError):
        person_objects(APP, key_of("alice"), BrowserSpec("profile", 8080), tpl, {})


def test_browser_pods_are_reached_only_by_the_gateway():
    rules = load_rules(REPO / "sdk" / "policy" / "app-objects.yaml")
    deny, allow, person = network_policies(APP, ["internet"], rules, gateway_sources=["198.51.100.0"],
                                           gateway_ports=[8080], browser=True)
    exists = {"key": "onemind.io/browser-profile", "operator": "Exists"}
    # The namespace-wide allowance (pod to pod) no longer selects any person's browser pod.
    assert allow["spec"]["podSelector"] == {"matchExpressions": [{**exists, "operator": "DoesNotExist"}]}
    assert person["spec"]["podSelector"] == {"matchExpressions": [exists]}
    peers = [f for r in person["spec"]["ingress"] for f in r["from"]]
    assert peers == [{"ipBlock": {"cidr": "198.51.100.0/32"}}]  # the gateway only: no pod, no namespace
    assert all(r["ports"] == [{"protocol": "TCP", "port": 8080}] for r in person["spec"]["ingress"])
    assert all("podSelector" not in t or "namespaceSelector" in t for r in person["spec"]["egress"] for t in r["to"])
    assert len(network_policies(APP, ["internet"], rules)) == 2  # other apps are unchanged


def test_install_writes_the_browser_policy_for_a_browser_app(tmp_path):
    (tmp_path / APP).mkdir()
    (tmp_path / APP / "onemind.app.yaml").write_text(yaml.safe_dump(browser_manifest(8080)))
    app = Catalog(tmp_path).get(APP)
    names = [d["metadata"]["name"] for d in KubernetesExecutor(hub_addresses=lambda: ["198.51.100.0"])._netpols(
        app, ["internet"], None, "")]
    assert names == ["onemind-default-deny", "onemind-allow", "onemind-browser-profiles"]


class LifecycleCluster(FakeCluster):
    """FakeCluster plus what app.stop / app.start send: list workloads, annotate, scale, rollout status."""

    def __call__(self, argv, input=None, **kw):
        if argv[1:3] == ["get", "deployments,statefulsets"]:
            ns = argv[argv.index("-n") + 1]
            items = [o for (n, k, _), o in self.objects.items() if n == ns and k == "Deployment"]
            return subprocess.CompletedProcess(argv, 0, json.dumps({"items": items}), "")
        if argv[1] == "annotate":
            ns = argv[argv.index("-n") + 1]
            dep = self.get(ns, "Deployment", argv[2].split("/", 1)[1])
            k, v = argv[3].split("=", 1)
            dep["metadata"].setdefault("annotations", {})[k] = v
            self.calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, "", "")
        if argv[1] in ("rollout", "kustomize"):
            self.calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, "", "")
        return super().__call__(argv, input=input, **kw)


def test_stop_then_start_runs_neither_the_shared_profile_nor_a_closed_browser(tmp_path):
    (tmp_path / APP).mkdir()
    (tmp_path / APP / "onemind.app.yaml").write_text(yaml.safe_dump(browser_manifest(8080)))
    app = Catalog(tmp_path).get(APP)
    cluster, spec, ns = LifecycleCluster(8080), BrowserSpec("profile", 8080), f"app-{APP}"
    profiles = BrowserProfiles(secret=SECRET, runner=cluster, ttl=0)
    alice, bob = key_of("alice"), key_of("bob")
    profiles.open(APP, alice, spec)
    profiles.open(APP, bob, spec)
    profiles.close(APP, bob)  # bob closed his window; alice's is open
    ex = KubernetesExecutor(runner=cluster)
    assert ex.run("app.stop", app).outcome == "succeeded"
    replicas = lambda name: cluster.get(ns, "Deployment", name)["spec"]["replicas"]  # noqa: E731
    assert replicas(f"browser-{alice}") == replicas(f"browser-{bob}") == replicas(APP) == 0  # stop stops everyone
    assert ex.run("app.start", app).outcome == "succeeded"
    assert replicas(APP) == 0  # the template (the shared firefox-profile claim) never runs
    assert replicas(f"browser-{alice}") == replicas(f"browser-{bob}") == 0  # only the person reopens their own
    touched = [c[2] for c in cluster.calls if c[1] in ("scale", "annotate", "rollout") and len(c) > 2]
    assert f"deployment/{APP}" not in touched
    assert not any(c[1] == "annotate" for c in cluster.calls)
    assert ex.run("app.restart", app).outcome == "succeeded"
    assert replicas(APP) == 0 and replicas(f"browser-{alice}") == 0
    profiles.open(APP, alice, spec)
    assert replicas(f"browser-{alice}") == 1 and replicas(APP) == 0
