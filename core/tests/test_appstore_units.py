# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the appstore building blocks (contract §12.22): settings schema, redaction,
dependencies, host ports, the Compose mapper and the pinned Git fetcher."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from onemind_core.appstore import appsettings, compose, deps, hostports
from onemind_core.monitoring.redact import Redactor, redact_lines
from onemind_core.appstore.sources import FetchError, GitFetcher, check_objects, param_problems

DIGEST = "sha256:" + "b" * 64


# ---- settings schema ---------------------------------------------------------------------------------

def fields(*raw):
    return appsettings.parse_fields({"spec": {"settings": list(raw)}})


@pytest.mark.parametrize("raw,needle", [
    ({"name": "api_key", "env": "X", "type": "string"}, "credential"),
    ({"name": "x", "env": "GITHUB_TOKEN", "type": "string"}, "credential"),
    ({"name": "X", "env": "X", "type": "string"}, "name must match"),
    ({"name": "x", "env": "x", "type": "string"}, "env must match"),
    ({"name": "x", "env": "X", "type": "object"}, "type must be"),
    ({"name": "x", "env": "X", "type": "string", "pattern": "(a+)+$"}, "quantifies a group"),
    ({"name": "x", "env": "X", "type": "string", "pattern": "(\\w*)*"}, "quantifies a group"),
    ({"name": "x", "env": "X", "type": "string", "pattern": "("}, "not a valid regular expression"),
    ({"name": "x", "env": "X", "type": "string", "pattern": "a" * 201}, "at most 200"),
    ({"name": "x", "env": "X", "type": "integer", "default": "7"}, "default does not fit"),
    ({"name": "x", "env": "X", "type": "integer", "default": 0, "minimum": 1}, "default does not fit"),
    ({"name": "x", "env": "X", "type": "enum"}, "needs an enum"),
    ({"name": "x", "env": "X", "type": "integer", "enum": ["a"]}, "fit the field's type"),
    ({"name": "x", "env": "X", "type": "boolean", "pattern": "x"}, "boolean takes no"),
    ({"name": "x", "env": "X", "type": "string", "secret": True}, "unknown keys"),
])
def test_bad_settings_fields_are_refused(raw, needle):
    with pytest.raises(appsettings.SettingsSchemaError) as exc:
        fields(raw)
    assert needle in str(exc.value)


@pytest.mark.parametrize("pattern,ok", [
    ("[A-Za-z ]+", True), ("^[a-z0-9-]{1,63}$", True), (r"\d+\.\d+", True), ("(http|https)://.*", True),
    ("(?:ab)?c", True), ("[(]+x", True), ("(a+)+$", False), ("(a|a)*$", False), ("((a+))+", False),
    ("a{2,}b{2,}c{2,}", False), (r"\d+\d+\d+", False), (r"(a)\1", False), ("(?=a)b", False),
    ("(?P<n>a)", False), ("(ab){3}", False),
])
def test_patterns_limited_to_a_shape_that_cannot_blow_up(pattern, ok):
    assert (appsettings.pattern_risk(pattern) is None) is ok


def test_duplicate_names_and_envs():
    with pytest.raises(appsettings.SettingsSchemaError, match="duplicate env"):
        fields({"name": "a", "env": "X", "type": "string"}, {"name": "b", "env": "X", "type": "string"})


def test_values_and_configmap():
    fs = fields(
        {"name": "days", "env": "DAYS", "type": "int", "default": 7, "minimum": 1},
        {"name": "ratio", "env": "RATIO", "type": "number", "maximum": 1},
        {"name": "on", "env": "ON", "type": "bool", "default": True, "restart": False},
    )
    assert appsettings.value_problems(fs, {"days": 3}) == []
    assert appsettings.value_problems(fs, {"days": True}) == ["days: must be an integer"]
    assert appsettings.value_problems(fs, {"ratio": float("nan")}) == ["ratio: must be a finite number"]
    assert appsettings.value_problems(fs, {"ratio": 2}) == ["ratio: must be at most 1"]
    assert appsettings.value_problems(fs, []) and appsettings.value_problems(fs, {})
    values = {**appsettings.effective(fs, {"days": 0, "gone": 1}), "ratio": 0.5}
    assert values == {"days": 7, "on": True, "ratio": 0.5}  # a stored value that no longer fits falls back
    assert appsettings.configmap_data(fs, values) == {"DAYS": "7", "RATIO": "0.5", "ON": "true"}
    assert appsettings.needs_restart(fs, {"on": False}) is False
    assert appsettings.needs_restart(fs, {"days": 2}) is True


def test_no_settings_is_empty():
    assert appsettings.parse_fields({"spec": {}}) == []


# ---- redaction ---------------------------------------------------------------------------------------

# Credential-shaped test values are assembled at run time, so secret scanners do not flag this file.
_AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
_KEY_VALUE = "abc123" + "def456"
_BEGIN, _END = "-----BEGIN " + "PRIVATE KEY-----", "-----END " + "PRIVATE KEY-----"


@pytest.mark.parametrize("line,secret", [
    ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJlX2hlcmU", "eyJzdWIiOiIxIn0"),
    ("POSTGRES_PASSWORD=s3cr3t-value", "s3cr3t-value"),
    ('{"api_key": "' + _KEY_VALUE + '"}', _KEY_VALUE),
    ("connecting to postgres://app:pa55w0rd@db:5432/app", "pa55w0rd"),
    ("token=ghp_" + "A" * 36, "ghp_"),
    (f"aws {_AWS} used", _AWS),
    ("client_secret: zzzzzzzzzz", "zzzzzzzzzz"),
    ("using om_agt_abcdefghijklmnopqrstu", "om_agt_"),
    ("slack xoxb-1234567890-abcdefghij", "xoxb-"),
    ("Basic dXNlcjpwYXNzd29yZA==", "dXNlcjpwYXNzd29yZA=="),
])
def test_redact_masks_credentials(line, secret):
    # App logs are §12.15 (monitoring/redact.py); these shapes are what a log read must never show.
    out = redact_lines([line])[0]
    assert secret not in out and "[redacted]" in out, out


def test_redact_keeps_ordinary_lines():
    for line in ("GET /health 200 3ms", "user alice logged in"):
        assert redact_lines([line]) == [line]


def test_private_key_block_is_masked_line_by_line():
    r = Redactor()
    lines = [_BEGIN, "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC", "abcdef==", _END, "after"]
    out = [r.line(line) for line in lines]
    assert out[:4] == ["[redacted]"] * 4 and out[4] == "after"


# ---- dependencies ------------------------------------------------------------------------------------

def test_dependents_only_lose_their_last_provider():
    manifests = {
        "wiki": {"spec": {"dependencies": [{"id": "postgres", "alternatives": ["mariadb"]}]}},
        "blog": {"spec": {"dependencies": [{"id": "mariadb"}]}},
        "postgres": {}, "mariadb": {},
    }
    statuses = {"wiki": "installed", "blog": "failed", "postgres": "installed", "mariadb": "installed"}
    assert deps.dependents("postgres", manifests, statuses) == []  # wiki still has mariadb
    assert deps.dependents("mariadb", manifests, statuses) == ["blog"]  # a failed dependant still counts
    statuses["postgres"] = "removing"
    assert deps.dependents("mariadb", manifests, statuses) == ["blog", "wiki"]
    req = deps.requirements(manifests["wiki"])[0]
    assert req.choices == ("postgres", "mariadb")
    assert deps.unsatisfied(manifests["wiki"], {"mariadb"}) == []
    assert deps.requirements({"spec": {"dependencies": [{"id": "../x"}, "bad", {"id": "ok"}]}})[0].id == "ok"


# ---- host ports --------------------------------------------------------------------------------------

def test_reserved_file_matches_the_builtin_list():
    assert hostports.load_reserved() == hostports.BUILTIN_RESERVED
    assert (53, "udp") not in hostports.BUILTIN_RESERVED  # DNS apps (Pi-hole, AdGuard) may declare it


def test_host_port_conflicts_and_self_duplicates():
    me = {"spec": {"hostPorts": [{"port": 53, "protocol": "udp", "description": "dns"},
                                 {"port": 53, "protocol": "udp", "description": "again"},
                                 {"port": 4222, "protocol": "tcp", "description": "nats"},
                                 {"port": 53, "protocol": "tcp", "description": "dns tcp"}]}}
    other = {"spec": {"hostPorts": [{"port": 53, "protocol": "tcp", "description": "dns"}]}}
    found = hostports.conflicts("me", me, {"other": other, "me": me}, hostports.BUILTIN_RESERVED)
    assert found == [
        {"port": 53, "protocol": "udp", "with": "me"},
        {"port": 4222, "protocol": "tcp", "with": "onemind:nats"},
        {"port": 53, "protocol": "tcp", "with": "other"},
    ]


# ---- static checks of source manifests ---------------------------------------------------------------

def test_static_checks_mirror_the_sandbox_rules():
    pod = {"hostPID": True, "volumes": [{"name": "h", "hostPath": {"path": "/"}}],
           "containers": [{"name": "c", "image": "nginx:1", "ports": [{"containerPort": 80, "hostPort": 80}],
                           "securityContext": {"privileged": True, "capabilities": {"add": ["SYS_ADMIN"]}}}]}
    docs = [
        {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "d", "namespace": "kube-system"},
         "spec": {"template": {"spec": pod}}},
        {"apiVersion": "rbac.authorization.k8s.io/v1", "kind": "ClusterRoleBinding", "metadata": {"name": "x"}},
        {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "s"}, "spec": {"type": "NodePort"}},
    ]
    problems, images = check_objects(docs, "app1")
    rules = {p.split()[0] for p in problems}
    assert {"N-01", "F-02", "F-04", "F-05", "F-06", "F-07", "I-01", "K-01", "V-01"} <= rules
    assert images == ["nginx:1"]


def test_source_params():
    assert param_problems("ok", "https://git.example.org/a/b.git", "a" * 40) == []
    for url in ("https://u:p@gitserver/r", "https://x.org/r#frag", "git@gitserver:r", "file:///etc", "https://x.org/../r"):
        assert param_problems(url=url), url
    assert param_problems(commit="A" * 40) and param_problems(name="a" * 21)


# ---- Compose mapper ----------------------------------------------------------------------------------

def test_compose_mapper_details():
    text = yaml.safe_dump({"services": {"my_app": {
        "image": f"x/y:1@{DIGEST}", "user": "1000", "command": "serve --port 80", "entrypoint": ["/bin/app"],
        "ports": [{"target": 80, "published": 8081, "protocol": "udp"}], "read_only": True,
        "cap_add": ["NET_BIND_SERVICE"], "tmpfs": ["/run"], "volumes": ["/cache"],
        "deploy": {"resources": {"limits": {"cpus": "0.5", "memory": "256M"}}, "replicas": 2},
        "extra_hosts": ["host.example:192.0.2.10"], "restart": "no",
    }}})
    res = compose.convert(text, "imp", "Imported")
    assert res.ok, res.refusals
    dep = yaml.safe_load(res.files["manifests/my-app-deployment.yaml"])
    c = dep["spec"]["template"]["spec"]["containers"][0]
    assert c["command"] == ["/bin/app"] and c["args"] == ["serve", "--port", "80"]
    assert c["securityContext"]["capabilities"]["add"] == ["NET_BIND_SERVICE"]
    assert c["securityContext"]["readOnlyRootFilesystem"] is True
    assert c["resources"]["limits"] == {"cpu": "500m", "memory": "256Mi"}
    assert dep["spec"]["replicas"] == 2
    assert dep["spec"]["template"]["spec"]["hostAliases"] == [{"ip": "192.0.2.10", "hostnames": ["host.example"]}]
    vols = {v["name"]: v for v in dep["spec"]["template"]["spec"]["volumes"]}
    assert any(v.get("emptyDir") == {"medium": "Memory"} for v in vols.values())
    svc = yaml.safe_load(res.files["manifests/my-app-service.yaml"])
    assert svc["spec"]["ports"][0]["protocol"] == "UDP" and svc["spec"]["type"] == "ClusterIP"
    assert any("renamed 'my-app'" in w for w in res.warnings)
    assert any("anonymous volume" in w for w in res.warnings)
    kust = yaml.safe_load(res.files["manifests/kustomization.yaml"])
    assert sorted(kust["resources"]) == ["my-app-deployment.yaml", "my-app-service.yaml"]


def test_compose_output_passes_the_static_checks():
    text = yaml.safe_dump({"services": {"a": {"image": f"x/a:1@{DIGEST}", "user": "1000", "ports": ["80"]}}})
    res = compose.convert(text, "imp")
    docs = [yaml.safe_load(v) for k, v in res.files.items() if k.startswith("manifests/") and "kustom" not in k]
    assert check_objects(docs, "imp") == ([], [f"x/a:1@{DIGEST}"])


@pytest.mark.parametrize("app_id", ["Bad", "1abc", "a" * 60, "../x"])
def test_compose_app_id_must_be_a_label(app_id):
    with pytest.raises(compose.ComposeError):
        compose.convert("services: {a: {image: x}}", app_id)


# ---- pinned Git fetcher (real git, local repository) -------------------------------------------------

def _git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "nobody",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "nobody"}
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True, env=env).stdout


@pytest.fixture
def repo(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    r = tmp_path / "upstream"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    (r / "comm-a").mkdir()
    (r / "comm-a" / "onemind.app.yaml").write_text("apiVersion: onemind.app/v1alpha1\n")
    os.symlink("/etc/hostname", r / "comm-a" / "link")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "one")
    first = _git(r, "rev-parse", "HEAD").strip()
    (r / "comm-a" / "onemind.app.yaml").write_text("apiVersion: onemind.app/v1alpha1\nkind: App\n")
    _git(r, "commit", "-q", "-am", "two")
    return r, first, _git(r, "rev-parse", "HEAD").strip()


def test_git_fetch_is_pinned_and_inert(repo, tmp_path):
    upstream, first, second = repo
    f = GitFetcher(tmp_path / "cache", allow_file_urls=True)
    out = f.fetch("src_X", f"file://{upstream}", second)
    assert out == f.path("src_X", second) and not (out / ".git").exists()
    assert (out / "comm-a" / "onemind.app.yaml").read_text().endswith("kind: App\n")
    link = out / "comm-a" / "link"
    assert not link.is_symlink() and link.read_text() == "/etc/hostname"  # checked out as a plain file
    with pytest.raises(FetchError):
        f.fetch("src_X", f"file://{upstream}", "f" * 40)  # not in the repository
    assert not any(p.name.startswith(".tmp-") for p in (tmp_path / "cache" / "src_X").iterdir())
    f.drop("src_X", keep=second)
    assert [p.name for p in (tmp_path / "cache" / "src_X").iterdir()] == [second]


def test_git_fetch_refuses_non_https_without_the_test_flag(repo, tmp_path):
    upstream, first, _ = repo
    with pytest.raises(FetchError, match="refusing"):
        GitFetcher(tmp_path / "cache").fetch("src_Y", f"file://{upstream}", first)


def test_git_fetch_size_limit(repo, tmp_path):
    upstream, first, _ = repo
    f = GitFetcher(tmp_path / "cache", allow_file_urls=True, max_files=1)
    with pytest.raises(FetchError, match="larger than"):
        f.fetch("src_Z", f"file://{upstream}", first)
    assert not f.path("src_Z", first).exists()
