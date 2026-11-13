# SPDX-License-Identifier: Apache-2.0
"""Security review of the app store depth feature (contract §12.22, item A8).

One test group per risk: an untrusted Compose file, an untrusted community source, host ports,
and who may ask for what. Each test names the attack it stops.
"""

from __future__ import annotations

import ipaddress
import json
from pathlib import Path

import pytest
import yaml

from conftest import ADULT, AGENT, GUEST, OWNER, make_client
from onemind_core import policy
from onemind_core.appstore import compose, hostports
from onemind_core.appstore.sources import FetchError, GitFetcher, host_problem
from onemind_core.notify.channels import DeliveryError

REPO = Path(__file__).resolve().parents[2]
DIGEST = "sha256:" + "c" * 64
RULES = policy.load_rules(REPO / "sdk" / "policy" / "app-objects.yaml")


def rendered(res: compose.Result) -> tuple[dict, list[dict]]:
    manifest = yaml.safe_load(res.files["onemind.app.yaml"])
    docs = [yaml.safe_load(v) for k, v in res.files.items() if k.startswith("manifests/") and "kustom" not in k]
    return manifest, docs


def convert(services: dict, app_id: str = "imp", **top) -> compose.Result:
    return compose.convert(yaml.safe_dump({"services": services, **top}), app_id)


# ---- Compose import: parsing untrusted YAML ----------------------------------------------------------

@pytest.mark.parametrize("text", [
    "services: !!python/object/apply:os.system ['id']",       # arbitrary object construction
    "services: !!python/name:os.system",
    "services: [unterminated",
], ids=["python-apply", "python-name", "broken"])
def test_compose_never_builds_python_objects(text):
    with pytest.raises(compose.ComposeError):
        compose.convert(text, "imp")


def test_compose_nesting_is_limited_not_a_crash():
    deep = "services:\n  a: " + "[" * 3000 + "]" * 3000  # would exhaust the stack of PyYAML
    with pytest.raises(compose.ComposeError, match="nested too deeply"):
        compose.convert(deep, "imp")
    moderate = "services: {a: {image: x, environment: " + "{a: " * 150 + "1" + "}" * 150 + "}}"
    with pytest.raises(compose.ComposeError, match="nested"):
        compose.convert(moderate, "imp")


def test_compose_alias_bomb_is_refused_by_the_expansion_limit():
    lines = ["l0: &l0 [x, x, x, x, x, x, x, x, x, x]"]
    for i in range(1, 8):
        lines.append(f"l{i}: &l{i} [{', '.join([f'*l{i - 1}'] * 10)}]")
    text = "\n".join(lines) + "\nservices: {a: {image: x, labels: *l7}}"
    with pytest.raises(compose.ComposeError, match="expands"):
        compose.convert(text, "imp")


def test_compose_size_limit():
    with pytest.raises(compose.ComposeError, match="larger"):
        compose.convert("services: {a: {image: x}}\n#" + "x" * compose.MAX_COMPOSE_BYTES, "imp")


def test_compose_route_answers_422_for_hostile_yaml_and_writes_nothing(client, settings):
    before = sorted(p.name for p in settings.apps_dir.iterdir()) if settings.apps_dir.is_dir() else []
    for text in ("services:\n  a: " + "[" * 3000 + "]" * 3000, "services: !!python/name:os.system"):
        r = client.post("/v1/deploy/compose", headers=OWNER, json={"app_id": "imp", "compose": text})
        assert r.status_code == 422 and r.json()["error"] == "conflict", r.text
    ok = client.post("/v1/deploy/compose", headers=OWNER, json={
        "app_id": "imp", "compose": yaml.safe_dump({"services": {"a": {"image": f"x/a:1@{DIGEST}", "user": "1000"}}})})
    assert ok.status_code == 200 and ok.json()["ok"] is True
    after = sorted(p.name for p in settings.apps_dir.iterdir()) if settings.apps_dir.is_dir() else []
    assert before == after  # a conversion has no side effects: nothing is written to the catalog
    assert client.get("/v1/apps/imp", headers=OWNER).status_code == 404  # and nothing is installed


# ---- Compose import: the result cannot be something the normal manifest path refuses -----------------

def test_a_clean_import_passes_the_real_install_sandbox():
    res = convert({"web": {"image": f"x/web:1@{DIGEST}", "user": "1000", "ports": ["8080"],
                           "volumes": ["data:/var/lib/data"], "environment": {"MODE": "prod"}}},
                  volumes={"data": {}})
    assert res.ok, res.refusals
    manifest, docs = rendered(res)
    assert policy.check_objects(docs, "imp", manifest, RULES) == []


HOSTILE = {
    "privileged": ({"image": f"x/a:1@{DIGEST}", "user": "1000", "privileged": True}, "F-06"),
    "host-network": ({"image": f"x/a:1@{DIGEST}", "user": "1000", "network_mode": "host"}, "F-01"),
    "host-pid": ({"image": f"x/a:1@{DIGEST}", "user": "1000", "pid": "host"}, "F-02"),
    "host-ipc": ({"image": f"x/a:1@{DIGEST}", "user": "1000", "ipc": "host"}, "F-03"),
    "bind-relative": ({"image": f"x/a:1@{DIGEST}", "user": "1000", "volumes": ["./data:/data"]}, "F-04"),
    "bind-absolute": ({"image": f"x/a:1@{DIGEST}", "user": "1000", "volumes": ["/:/host"]}, "F-04"),
    "bind-long": ({"image": f"x/a:1@{DIGEST}", "user": "1000",
                   "volumes": [{"type": "bind", "source": "/etc", "target": "/e"}]}, "F-04"),
    "docker-socket": ({"image": f"x/a:1@{DIGEST}", "user": "1000", "volumes": ["/var/run/docker.sock:/s"]}, "F-04"),
    "cap-sys-admin": ({"image": f"x/a:1@{DIGEST}", "user": "1000", "cap_add": ["SYS_ADMIN"]}, "F-07"),
    "root-user": ({"image": f"x/a:1@{DIGEST}", "user": "root"}, "S-01"),
    "uid-0": ({"image": f"x/a:1@{DIGEST}", "user": "0:0"}, "S-01"),
    "tag-only-image": ({"image": "nginx:latest", "user": "1000"}, "I-01"),
}


@pytest.mark.parametrize("name", sorted(HOSTILE))
def test_import_refuses_what_the_normal_path_refuses(name):
    service, rule = HOSTILE[name]
    res = convert({"a": service})
    assert not res.ok and rule in {r["rule"] for r in res.refusals}, res.refusals
    assert res.to_json()["files"] == {}  # a refused import hands out no files at all


def test_an_import_without_a_user_still_runs_as_non_root():
    """No `user:` is not a way round S-01: the pod is restricted (runAsNonRoot), so a root image
    refuses to start instead of running as root; the import says so in a warning."""
    res = convert({"a": {"image": f"x/a:1@{DIGEST}"}})
    assert res.ok and any("user" in w for w in res.warnings)
    manifest, docs = rendered(res)
    assert policy.check_objects(docs, "imp", manifest, RULES) == []
    ctx = docs[0]["spec"]["template"]["spec"]["containers"][0]["securityContext"]
    assert ctx["runAsNonRoot"] is True and ctx["allowPrivilegeEscalation"] is False and ctx.get("privileged") is not True


def test_published_ports_become_service_ports_not_host_ports():
    res = convert({"a": {"image": f"x/a:1@{DIGEST}", "user": "1000", "ports": ["80:80", "443:443"]}})
    assert res.ok
    manifest, docs = rendered(res)
    assert policy.check_objects(docs, "imp", manifest, RULES) == []
    pods = [d for d in docs if d["kind"] == "Deployment"]
    assert all("hostPort" not in p for d in pods for c in d["spec"]["template"]["spec"]["containers"]
               for p in c.get("ports", []))
    assert not manifest["spec"].get("hostPorts")  # an import never declares a host port by itself


def test_import_cannot_smuggle_unknown_keys_or_variables():
    for service in ({"image": f"x/a:1@{DIGEST}", "user": "1000", "build": "."},
                    {"image": f"x/a:1@{DIGEST}", "user": "1000", "devices": ["/dev/sda"]},
                    {"image": f"x/a:1@{DIGEST}", "user": "1000", "security_opt": ["seccomp=unconfined"]},
                    {"image": f"x/a:1@{DIGEST}", "user": "1000", "sysctls": {"net.ipv4.ip_forward": 1}},
                    {"image": f"x/a:1@{DIGEST}", "user": "1000", "env_file": ["/etc/passwd"]},
                    {"image": f"x/a:1@{DIGEST}", "user": "1000", "totally_new_key": 1}):
        assert not convert({"a": service}).ok


def test_import_is_owner_only_and_audited(client, settings):
    body = {"app_id": "imp", "compose": yaml.safe_dump({"services": {"a": {"image": "x"}}})}
    for who in (ADULT, GUEST, AGENT):
        assert client.post("/v1/deploy/compose", headers=who, json=body).status_code == 403
    assert client.post("/v1/deploy/compose", headers=OWNER, json=body).status_code == 200
    events = [json.loads(x) for x in settings.audit_path.read_text().splitlines()]
    assert any(e["event"] == "deploy.compose.converted" for e in events)
    assert any(e["event"] == "authz.denied" for e in events)


# ---- Community sources: untrusted fetched content, no SSRF, owner only ------------------------------

def _addr(*names):
    return lambda host: [ipaddress.ip_address(n) for n in names]


@pytest.mark.parametrize("address", [
    "169.254.169.254",          # cloud metadata
    "169.254.10.1", "fe80::1",  # link-local
    "127.0.0.1", "::1",         # the gateway's own ports, the cluster
    "::ffff:127.0.0.1", "::ffff:169.254.169.254",  # v4-mapped spellings
    "0.0.0.0", "224.0.0.1", "240.0.0.1",
])
def test_source_host_never_resolves_to_a_dangerous_address(address):
    assert host_problem("https://git.example.org/a/b.git", _addr(address)) is not None


def test_source_host_one_bad_address_among_good_ones_is_refused():
    assert host_problem("https://x.example.org/r", _addr("93.184.216.34", "169.254.169.254")) is not None


def test_source_host_on_the_lan_or_public_is_allowed_because_an_owner_approves_it():
    for ok in ("93.184.216.34", "192.168." + "1.20", "10." + "0.0.7", "100.64." + "1.2"):  # parts: hygiene greps
        assert host_problem("https://git.example.org/r", _addr(ok)) is None


def test_unresolvable_source_host_is_refused():
    def boom(host):
        raise DeliveryError("cannot resolve host (gaierror)")
    assert "resolve" in host_problem("https://nope.invalid/r", boom)


@pytest.mark.parametrize("url", [
    "http://git.example.org/r", "ssh://git" + "@git.example.org/r", "git://git.example.org/r", "file:///etc/passwd",
    "https://user:pw" + "@git.example.org/r", "https://git.example.org/r?x=1", "https://git.example.org/r#f",
    "https://git.example.org/../r", "ftp://git.example.org/r", "https://[::1]/r",
])
def test_source_url_must_be_plain_https(url):
    from onemind_core.appstore.sources import param_problems
    assert param_problems(url=url)


def test_fetcher_refuses_a_dangerous_host_before_running_git(tmp_path):
    def never(*a, **k):
        raise AssertionError("git must not run for a refused host")
    f = GitFetcher(tmp_path / "c", runner=never, resolve=_addr("169.254.169.254"))
    with pytest.raises(FetchError, match="refusing to fetch"):
        f.fetch("src_X", "https://metadata.example.org/r.git", "a" * 40)
    assert not (tmp_path / "c" / "src_X").exists()


def test_source_add_to_a_metadata_address_is_refused_at_request(settings, clock):
    with make_client(settings, clock) as c:
        c.app.state.appstore.fetcher = GitFetcher(settings.audit_path.parent / "s", resolve=_addr("169.254.169.254"))
        body = {"type": "source.add", "params": {"name": "evil", "url": "https://meta.example.org/r.git",
                                                 "commit": "a" * 40},
                "idempotency_key": "k1", "expires_at": (clock() + __import__("datetime").timedelta(minutes=5)).isoformat()}
        r = c.post("/v1/actions", headers=OWNER, json=body)
        assert r.status_code == 422 and r.json()["reason"] == "source_host_refused", r.text
        assert c.get("/v1/actions", headers=OWNER).json() == []  # nothing was filed for the owner to approve


@pytest.mark.parametrize("who", [AGENT, ADULT, GUEST], ids=["agent", "adult", "guest"])
@pytest.mark.parametrize("type_,params", [
    ("source.add", {"name": "s1", "url": "https://git.example.org/r.git", "commit": "a" * 40}),
    ("source.move", {"source_id": "src_" + "0" * 26, "to_commit": "b" * 40}),
    ("source.remove", {"source_id": "src_" + "0" * 26}),
    ("exposure.private", {"app_id": "uptime-kuma"}),
    ("exposure.mesh", {"app_id": "uptime-kuma"}),
    ("exposure.public", {"app_id": "uptime-kuma"}),
])
def test_only_the_owner_requests_sources_and_exposure(client, clock, who, type_, params):
    import datetime
    body = {"type": type_, "params": params, "idempotency_key": f"{type_}-{id(who)}",
            "expires_at": (clock() + datetime.timedelta(minutes=5)).isoformat()}
    r = client.post("/v1/actions", headers=who, json=body)
    assert r.status_code == 403 and r.json()["error"] == "permission_denied", r.text
    assert client.get("/v1/actions", headers=OWNER).json() == []  # denied before anything was filed


def test_an_agent_cannot_name_a_feature_type_through_mcp(client):
    r = client.post("/mcp", headers={**AGENT, "Accept": "application/json, text/event-stream"}, json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "request_action", "arguments": {"type": "exposure.mesh", "app_id": "uptime-kuma"}}})
    assert r.status_code == 200 and r.json()["error"]["code"] == -32602


def test_source_routes_need_a_credential(client):
    assert client.get("/v1/sources").status_code == 401
    assert client.get("/v1/sources/src_x").status_code == 401
    assert client.post("/v1/deploy/compose", json={}).status_code == 401


# ---- Host ports: declared, owner-approved, never OneMind's own, never bound by the manifests --------

GATEWAY_PORTS = [(80, "tcp"), (443, "tcp"), (8080, "tcp"), (8443, "tcp"), (7480, "tcp"), (4222, "tcp"),
                 (6443, "tcp"), (22, "tcp")]


@pytest.mark.parametrize("port,proto", GATEWAY_PORTS)
def test_an_app_can_never_declare_a_port_onemind_uses(port, proto):
    manifest = {"spec": {"hostPorts": [{"port": port, "protocol": proto, "description": "x"}]}}
    found = hostports.conflicts("evil", manifest, {}, hostports.load_reserved())
    assert found and found[0]["with"].startswith("onemind:")


def test_privileged_ports_are_only_declarations_the_sandbox_still_refuses_to_bind():
    """53/udp may be declared (a DNS app), but the manifests cannot bind a host port or the host
    network: the install sandbox refuses hostPort (F-05) and hostNetwork (F-01) for everyone."""
    manifest = {"spec": {"hostPorts": [{"port": 53, "protocol": "udp", "description": "dns"}]}}
    assert hostports.conflicts("dns", manifest, {}, hostports.load_reserved()) == []  # declared, not bound
    pod = {"hostNetwork": True, "containers": [{
        "name": "c", "image": f"x/dns:1@{DIGEST}", "ports": [{"containerPort": 53, "hostPort": 53}],
        "securityContext": {"runAsNonRoot": True, "allowPrivilegeEscalation": False}}]}
    doc = {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "d"}, "spec": {"template": {"spec": pod}}}
    rules = {v.rule for v in policy.check_objects([doc], "dns", {"metadata": {"id": "dns"}, "spec": manifest["spec"]}, RULES)}
    assert {"F-01", "F-05"} <= rules


def test_host_port_conflict_is_symmetric_and_per_declaration():
    a = {"spec": {"hostPorts": [{"port": 5000, "protocol": "tcp", "description": "a"}]}}
    b = {"spec": {"hostPorts": [{"port": 5000, "protocol": "tcp", "description": "b"},
                                {"port": 5000, "protocol": "udp", "description": "b"}]}}
    assert hostports.conflicts("b", b, {"a": a}, {}) == [{"port": 5000, "protocol": "tcp", "with": "a"}]
    assert hostports.conflicts("a", a, {"b": b}, {}) == [{"port": 5000, "protocol": "tcp", "with": "b"}]


def test_reserved_ports_file_matches_the_builtin_list():
    assert hostports.load_reserved(REPO / "sdk" / "policy" / "host-ports.yaml") == hostports.BUILTIN_RESERVED
