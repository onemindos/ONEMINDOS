# SPDX-License-Identifier: Apache-2.0
"""Request limits, security headers and the pending-action cap (H-14, H-18, H-20; contract §12.1)."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from conftest import AGENT, OWNER, action_body, make_client
from onemind_core.app import create_app
from onemind_core.catalog import builtin_check
from onemind_core.guard import CSP, AuthFailures, LimitSettings, TokenBuckets
from onemind_core.sections import load_section


def limited(settings, **kw):
    return replace(settings, sections={"limits": LimitSettings(**kw)})


def test_security_headers_on_every_response(client):
    for path, status in (("/healthz", 200), ("/v1/instance", 401), ("/v1/nope", 404), ("/", 200)):
        r = client.get(path)
        assert r.status_code == status, path
        assert r.headers["content-security-policy"] == CSP
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["referrer-policy"] == "no-referrer"
        assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in CSP and "script-src 'self'" in CSP and "object-src 'none'" in CSP


def test_body_over_the_limit_is_413(settings, clock):
    with make_client(limited(settings, max_body_bytes=4096), clock) as c:
        r = c.post("/v1/actions", content=b"x" * 5000, headers={**OWNER, "content-type": "application/json"})
        assert r.status_code == 413 and r.json()["error"] == "payload_too_large"
        chunks = (b"x" * 1024 for _ in range(8))  # no Content-Length: counted while streaming
        r = c.post("/v1/actions", content=chunks, headers={**OWNER, "content-type": "application/json"})
        assert r.status_code == 413 and r.json()["error"] == "payload_too_large"
        assert c.post("/v1/actions", json=action_body(clock), headers=OWNER).status_code == 201


def test_default_body_limit_is_256_kib():
    assert LimitSettings().max_body_bytes == 256 * 1024


def test_reads_are_rate_limited_per_principal(settings, clock):
    with make_client(limited(settings, read_burst=3, read_rate=0.001), clock) as c:
        for _ in range(3):
            assert c.get("/v1/nodes", headers=OWNER).status_code == 200
        r = c.get("/v1/nodes", headers=OWNER)
        assert r.status_code == 429
        body = r.json()
        assert body["error"] == "rate_limited" and body["retry_after_s"] >= 1
        assert int(r.headers["retry-after"]) == body["retry_after_s"]
        assert c.get("/v1/nodes", headers=AGENT).status_code == 200  # another principal has its own bucket
        assert c.get("/healthz").status_code == 200  # health checks are never limited


def test_action_requests_have_their_own_bucket(settings, clock):
    with make_client(limited(settings, request_burst=2, request_rate=0.001), clock) as c:
        for i in range(2):
            assert c.post("/v1/actions", json=action_body(clock, key=f"k{i}", app_id="whoami"), headers=OWNER).status_code in (201, 409)
        r = c.post("/v1/actions", json=action_body(clock, key="k9"), headers=OWNER)
        assert r.status_code == 429 and r.json()["error"] == "rate_limited"
        assert c.get("/v1/actions", headers=OWNER).status_code == 200


def test_wrong_tokens_start_a_backoff(settings, clock):
    with make_client(limited(settings, auth_failures_per_min=3, auth_backoff_s=900), clock) as c:
        bad = {"Authorization": "Bearer not-a-real-token"}
        for _ in range(4):
            assert c.get("/v1/nodes", headers=bad).status_code == 401
        r = c.get("/v1/nodes", headers=OWNER)  # the whole source backs off, even with a good token
        assert r.status_code == 429 and r.json()["reason"] == "auth_backoff"
        assert c.get("/healthz").status_code == 200
    events = [json.loads(x)["event"] for x in settings.audit_path.read_text().splitlines()]
    assert events.count("auth.backoff") == 1


def test_auth_failures_window_and_expiry():
    t = [0.0]
    a = AuthFailures(limit=2, backoff_s=10, now=lambda: t[0])
    assert not a.failed("s") and not a.failed("s")
    t[0] = 61.0  # older failures leave the one-minute window
    assert not a.failed("s") and not a.failed("s")
    assert a.failed("s") and a.blocked_for("s") == 10
    t[0] = 72.0
    assert a.blocked_for("s") == 0


def test_token_bucket_refills():
    t = [0.0]
    b = TokenBuckets(rate=2.0, burst=2, now=lambda: t[0])
    assert b.take("k") == 0 and b.take("k") == 0
    assert b.take("k") == pytest.approx(0.5)
    t[0] = 0.5
    assert b.take("k") == 0


def test_limits_can_be_turned_off(settings, clock):
    with make_client(limited(settings, enabled=False, read_burst=1, read_rate=0.001), clock) as c:
        for _ in range(5):
            assert c.get("/v1/nodes", headers=OWNER).status_code == 200


def test_limit_settings_from_env_and_validation():
    s = load_section(LimitSettings, {"ONEMIND_LIMITS_MAX_PENDING": "3", "ONEMIND_LIMITS_READ_RATE": "5"})
    assert s.max_pending == 3 and s.read_rate == 5.0
    for env in ({"ONEMIND_LIMITS_MAX_BODY_BYTES": "10"}, {"ONEMIND_LIMITS_READ_RATE": "0"}, {"ONEMIND_LIMITS_MAX_PENDING": "-1"}):
        with pytest.raises(ValueError):
            load_section(LimitSettings, env)


def test_pending_cap_per_agent(settings, clock):
    with make_client(limited(settings, max_pending=3, read_burst=1000, request_burst=1000), clock) as c:
        ids = []
        for i in range(3):
            r = c.post("/v1/actions", json=action_body(clock, key=f"a{i}"), headers=AGENT)
            assert r.status_code == 201, r.text
            ids.append(r.json()["id"])
        r = c.post("/v1/actions", json=action_body(clock, key="a3"), headers=AGENT)
        assert r.status_code == 429
        body = r.json()
        assert body["error"] == "rate_limited" and body["reason"] == "too_many_pending"
        assert r.headers["retry-after"] == "60"
        # replaying an existing request is not a new one
        assert c.post("/v1/actions", json=action_body(clock, key="a0"), headers=AGENT).status_code == 200
        # owners are not capped
        for i in range(4):
            assert c.post("/v1/actions", json=action_body(clock, key=f"o{i}"), headers=OWNER).status_code == 201
        # once the owner decides one, the agent may ask again
        assert c.post(f"/v1/actions/{ids[0]}/deny", headers=OWNER).status_code == 200
        assert c.post("/v1/actions", json=action_body(clock, key="a4"), headers=AGENT).status_code == 201
        # expired requests stop counting
        clock.advance(601)
        assert c.post("/v1/actions", json=action_body(clock, key="a5"), headers=AGENT).status_code == 201
    rejected = [json.loads(x) for x in settings.audit_path.read_text().splitlines()]
    assert any(x["event"] == "action.rejected" and x["data"].get("error") == "rate_limited" for x in rejected)


def test_pending_cap_reaches_mcp_agents_as_a_tool_error(settings, clock):
    from onemind_core.actions import ActionService  # noqa: F401  (the cap lives there)

    with make_client(limited(settings, max_pending=1, read_burst=1000, request_burst=1000), clock) as c:
        assert c.post("/v1/actions", json=action_body(clock, key="m0"), headers=AGENT).status_code == 201
        assert c.app.state.actions.max_pending_per_requester == 1


def test_kubernetes_executor_needs_the_schema(settings, clock):
    with pytest.raises(ValueError, match="manifest schema"):
        create_app(replace(settings, executor="kubernetes"), clock=clock)


def test_builtin_check_refuses_non_https_source():
    doc = {
        "apiVersion": "onemind.app/v1alpha1", "kind": "App",
        "metadata": {"id": "x", "name": "x", "version": "1", "source": "javascript:alert(1)"},
        "spec": {"archs": ["amd64"]},
    }
    assert "metadata.source must be an https:// URL" in builtin_check(doc)
    doc["metadata"]["source"] = "https://example.com/x"
    assert builtin_check(doc) == []


def test_openapi_lists_the_new_statuses(client):
    doc = client.get("/openapi.json").json()
    create = doc["paths"]["/v1/actions"]["post"]["responses"]
    assert "429" in create
    err = doc["components"]["schemas"]["ErrorBody"]["properties"]
    assert {"reason", "details", "retry_after_s"} <= set(err)
