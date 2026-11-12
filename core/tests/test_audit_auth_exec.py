"""Audit chain, token file parsing, and the kubernetes executor's commands and outcomes."""

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from conftest import AGENT, OWNER, action_body, make_client
from onemind_core.audit import GENESIS, AuditLog, chain_hash, main as audit_main, verify
from onemind_core.auth import TokenStore, parse_tokens
from onemind_core.catalog import Catalog
from onemind_core.executors import KubernetesExecutor, NoopExecutor


# ---- audit -----------------------------------------------------------------------------

def test_every_decision_is_audited_and_chain_verifies(client, clock, settings):
    aid = client.post("/v1/actions", json=action_body(clock), headers=AGENT).json()["id"]
    client.post(f"/v1/actions/{aid}/approve", headers=AGENT)  # denied
    client.post(f"/v1/actions/{aid}/approve", headers=OWNER)
    lines = [json.loads(l) for l in settings.audit_path.read_text().splitlines()]
    events = [l["event"] for l in lines]
    assert events == [
        "gateway.started",
        "action.requested",
        "action.awaiting_approval",
        "authz.denied",
        "action.approved",
        "action.dispatched",
        "action.succeeded",
    ]
    assert lines[0]["prev_hash"] == GENESIS
    for prev, cur in zip(lines, lines[1:]):
        assert cur["prev_hash"] == prev["hash"]
    ok, n, reason = verify(settings.audit_path)
    assert ok and n == len(lines), reason
    # No secrets in the log
    assert "dev-agent-token" not in settings.audit_path.read_text()


def _events(settings):
    return [json.loads(l) for l in settings.audit_path.read_text().splitlines()]


def test_refused_action_decisions_are_audited(client, clock, settings):
    post = client.post
    assert post("/v1/actions", json=action_body(clock, app_id="nope"), headers=OWNER).status_code == 404
    assert post("/v1/actions", json=action_body(clock, key="r", type_="app.remove"), headers=OWNER).status_code == 409
    assert post("/v1/actions", json=action_body(clock, key="x", ttl=-1), headers=OWNER).status_code == 409
    aid = post("/v1/actions", json=action_body(clock, key="a", ttl=10), headers=OWNER).json()["id"]
    assert post("/v1/actions", json=action_body(clock, key="a", app_id="whoami"), headers=OWNER).status_code == 409
    clock.advance(11)
    assert post(f"/v1/actions/{aid}/approve", headers=OWNER).status_code == 409
    assert post(f"/v1/actions/{aid}/deny", headers=OWNER).status_code == 409
    rejected = [(e["data"]["attempted"], e["data"]["error"]) for e in _events(settings) if e["event"] == "action.rejected"]
    assert rejected == [
        ("request action", "not_found"),
        ("request action", "stale_precondition"),
        ("request action", "expired"),
        ("request action", "conflict"),
        ("approve action", "expired"),
        ("deny action", "expired"),
    ]
    assert verify(settings.audit_path)[0]


def test_unauthenticated_requests_are_audited_rate_limited(client, clock, settings):
    for _ in range(3):
        assert client.get("/v1/actions", headers={"Authorization": "Bearer wrong-token-0123456789"}).status_code == 401
    clock.advance(61)
    client.post("/v1/actions", json={})
    rows = [e for e in _events(settings) if e["event"] == "auth.rejected"]
    assert [r["data"]["suppressed_since_last"] for r in rows] == [0, 2]
    assert rows[0]["data"]["reason"] == "unknown token" and rows[1]["data"]["reason"] == "missing bearer token"
    assert "wrong-token" not in settings.audit_path.read_text()


def _write_some(path, clock, n=5):
    log = AuditLog(path, clock)
    for i in range(n):
        log.append("test.event", {"id": "x", "kind": "person", "role": "owner"}, None, {"i": i})


def test_hash_formula(tmp_path, clock):
    p = tmp_path / "a.jsonl"
    _write_some(p, clock, 1)
    rec = json.loads(p.read_text())
    body = {k: v for k, v in rec.items() if k not in ("prev_hash", "hash")}
    assert rec["hash"] == chain_hash(GENESIS, body)


@pytest.mark.parametrize("tamper", ["edit", "delete", "swap", "garbage"])
def test_tampering_is_detected(tmp_path, clock, tamper):
    p = tmp_path / "a.jsonl"
    _write_some(p, clock)
    lines = p.read_text().splitlines()
    if tamper == "edit":
        lines[2] = lines[2].replace('"i":2', '"i":99')
    elif tamper == "delete":
        del lines[1]
    elif tamper == "swap":
        lines[1], lines[2] = lines[2], lines[1]
    else:
        lines[3] = "{not json"
    p.write_text("\n".join(lines) + "\n")
    ok, _, reason = verify(p)
    assert not ok, reason
    assert audit_main([str(p)]) == 1


def test_chain_resumes_after_restart(tmp_path, clock):
    p = tmp_path / "a.jsonl"
    _write_some(p, clock, 3)
    _write_some(p, clock, 3)  # a new AuditLog instance continues the same chain
    ok, n, _ = verify(p)
    assert ok and n == 6
    assert audit_main([str(p)]) == 0


def test_audit_publishes_to_nats_subject(tmp_path, clock):
    sent = []
    log = AuditLog(tmp_path / "a.jsonl", clock, publish=lambda s, d: sent.append((s, d)))
    rec = log.append("x", None, None, {})
    assert sent[0][0] == "onemind.audit"
    assert json.loads(sent[0][1])["hash"] == rec["hash"]


def test_audit_survives_publish_failure(tmp_path, clock):
    def boom(*_):
        raise RuntimeError("nats down")

    log = AuditLog(tmp_path / "a.jsonl", clock, publish=boom)
    log.append("x")
    assert verify(tmp_path / "a.jsonl")[0]


# ---- tokens ----------------------------------------------------------------------------

def test_tokens_mapping_list_and_hash_forms(tmp_path):
    import hashlib

    tok = "a-long-enough-token-1234"
    doc = {
        "tokens": [
            {"token": tok, "id": "z", "kind": "person", "role": "owner"},
            {"token": "sha256:" + hashlib.sha256(b"hashed-token-abcdefgh").hexdigest(), "id": "h", "kind": "agent", "role": "agent"},
        ]
    }
    p = tmp_path / "t.yaml"
    p.write_text(yaml.safe_dump(doc))
    store = TokenStore(p)
    assert store.lookup(tok).is_owner
    agent = store.lookup("hashed-token-abcdefgh")
    assert agent.kind == "agent" and not agent.is_owner and agent.can_request_actions
    assert store.lookup("") is None and store.lookup("other") is None


@pytest.mark.parametrize(
    "entry",
    [
        {"id": "a", "kind": "agent", "role": "owner"},   # an agent can never be an owner
        {"id": "a", "kind": "person", "role": "agent"},
        {"id": "a", "kind": "robot", "role": "guest"},
        {"id": "a", "kind": "person"},
    ],
)
def test_bad_principals_rejected(entry):
    with pytest.raises(ValueError):
        parse_tokens({"tokens": {"a-long-enough-token-1234": entry}})


@pytest.mark.parametrize("bad", ["tokens: [unclosed", "tokens: 7", "- not a mapping"])
def test_invalid_tokens_file_at_runtime_keeps_last_good(tmp_path, bad):
    import os

    tok = "a-long-enough-token-1234"
    p = tmp_path / "t.yaml"
    p.write_text(yaml.safe_dump({"tokens": {tok: {"id": "z", "kind": "person", "role": "owner"}}}))
    store = TokenStore(p)
    assert store.lookup(tok).is_owner
    p.write_text(bad)
    st = p.stat()
    os.utime(p, (st.st_atime, st.st_mtime + 5))  # make sure the mtime changes
    assert store.lookup(tok).is_owner  # no exception, last good set kept


@pytest.mark.parametrize("bad", ["tokens: [unclosed", "tokens: 7"])
def test_invalid_tokens_file_gives_401_not_500(settings, clock, tmp_path, bad):
    p = tmp_path / "t.yaml"
    p.write_text(bad)
    with make_client(settings, clock, tokens_file=p) as c:  # startup does not crash
        r = c.get("/v1/instance", headers=OWNER)
        assert r.status_code == 401 and r.json()["error"] == "unauthenticated"


def test_short_tokens_rejected():
    with pytest.raises(ValueError):
        parse_tokens({"tokens": {"short": {"id": "a", "kind": "person", "role": "owner"}}})


# ---- executors -------------------------------------------------------------------------

class FakeRun:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw.get("input")))
        r = self.results.pop(0)
        if isinstance(r, Exception):
            raise r
        return subprocess.CompletedProcess(argv, r, stdout="ok", stderr="err" if r else "")


@pytest.fixture
def kuma(settings):
    return Catalog(settings.apps_dir).get("uptime-kuma")


def test_kubernetes_install_commands(kuma):
    run = FakeRun([0, 0])
    res = KubernetesExecutor(runner=run).run("app.install", kuma)
    assert res.outcome == "succeeded"
    (ns_argv, ns_in), (apply_argv, _) = run.calls
    assert ns_argv == ["kubectl", "apply", "-f", "-"] and "name: app-uptime-kuma" in ns_in
    assert apply_argv[:3] == ["kubectl", "apply", "-k"]
    assert apply_argv[3].endswith("uptime-kuma/manifests")
    assert apply_argv[4:] == ["-n", "app-uptime-kuma"]
    # host paths are redacted in the recorded steps
    assert res.steps[1]["argv"][3] == "$ONEMIND_APPS_DIR/uptime-kuma/manifests"


def test_kubernetes_remove_commands(kuma):
    run = FakeRun([0, 0])
    res = KubernetesExecutor(runner=run).run("app.remove", kuma)
    assert res.outcome == "succeeded"
    assert run.calls[0][0][:3] == ["kubectl", "delete", "-k"]
    assert "-n" in run.calls[0][0] and "app-uptime-kuma" in run.calls[0][0]
    assert run.calls[1][0] == ["kubectl", "delete", "namespace", "app-uptime-kuma", "--ignore-not-found=true"]


@pytest.mark.parametrize(
    "results,outcome",
    [
        ([0, 1], "failed"),
        ([1], "failed"),
        ([FileNotFoundError()], "failed"),
        ([0, subprocess.TimeoutExpired("kubectl", 5)], "outcome_unknown"),
    ],
)
def test_kubernetes_outcomes(kuma, results, outcome):
    res = KubernetesExecutor(runner=FakeRun(results)).run("app.install", kuma)
    assert res.outcome == outcome


def test_kubernetes_with_real_missing_binary(kuma):
    res = KubernetesExecutor(kubectl="kubectl-does-not-exist-onemind").run("app.install", kuma)
    assert res.outcome == "failed"


def test_noop_executor(kuma):
    assert NoopExecutor().run("app.install", kuma).outcome == "succeeded"
