# SPDX-License-Identifier: Apache-2.0
"""Dispatch credentials are verifiable and never proxy a caller credential or URL."""
import base64
import json

import httpx
import pytest
from cryptography.hazmat.primitives import serialization

from onemind_core.backups.jobs import load_or_create_job_key, public_pem
from onemind_core.errors import ApiError
from onemind_core.plugins import dispatch

TOOL = {"name": "greet", "effect": "read", "input": {"type": "object", "additionalProperties": False},
        "output": {"type": "object", "properties": {"text": {"type": "string"}},
                   "required": ["text"], "additionalProperties": False}}
BACKEND = {"service": "hello", "port": 8080}


def decode(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def test_signed_dispatch_claims_and_isolated_transport(client, clock, monkeypatch):
    gw = client.app.state.gateway
    sent = []

    def backend(request):
        sent.append(request)
        return httpx.Response(200, json={"text": "hello"})

    monkeypatch.setattr(dispatch, "client", lambda: httpx.Client(transport=httpx.MockTransport(backend), trust_env=False))
    for _ in range(2):
        assert dispatch.invoke(gw, "hello-plugin", BACKEND, TOOL, {}) == {"text": "hello"}
    claims = []
    for request in sent:
        assert str(request.url) == "http://hello.app-hello-plugin.svc.cluster.local:8080/onemind/v1/tools/greet"
        assert request.content == b"{}"
        token = request.headers["authorization"].removeprefix("Bearer ")
        head, body, signature = token.split(".")
        assert json.loads(decode(head)) == {"alg": "EdDSA", "typ": "JWT"}
        key = load_or_create_job_key(gw.settings.audit_path.parent / "plugins" / "dispatch.key")
        serialization.load_pem_public_key(public_pem(key)).verify(decode(signature), f"{head}.{body}".encode())
        claim = json.loads(decode(body))
        assert claim["aud"] == "plugin:hello-plugin" and claim["tool"] == "greet"
        assert claim["args_sha256"] == dispatch.arguments_hash({})
        assert claim["exp"] - claim["iat"] == 60 and claim["iat"] == int(clock().timestamp())
        assert "action_id" not in claim
        claims.append(claim)
    assert claims[0]["jti"] != claims[1]["jti"]


@pytest.mark.parametrize("backend", [{"service": "evil.com/path", "port": 8080},
    {"service": "127.0.0.1", "port": 80}, {"service": "hello", "port": True},
    {"service": "hello", "port": 65536}, {"service": "a" * 64, "port": 80}])
def test_backend_cannot_select_an_arbitrary_host(backend):
    with pytest.raises(ApiError):
        dispatch.backend_url("hello-plugin", backend, "greet")


@pytest.mark.parametrize("response", [httpx.Response(302, headers={"location": "http://evil.invalid"}),
    httpx.Response(200, content=b"x" * (dispatch.MAX_BYTES + 1)), httpx.Response(200, json={"extra": True}),
    httpx.Response(200, content=b'{"text":NaN}'), httpx.Response(200, json=["hello"])])
def test_bad_results_and_redirects_fail_closed(client, monkeypatch, response):
    monkeypatch.setattr(dispatch, "client", lambda: httpx.Client(transport=httpx.MockTransport(lambda _: response)))
    with pytest.raises(ApiError, match="dispatch or result validation"):
        dispatch.invoke(client.app.state.gateway, "hello-plugin", BACKEND, TOOL, {})


def test_mutation_requires_real_dispatched_action(client):
    for action_id in (None, "fabricated"):
        with pytest.raises(ApiError):
            dispatch.invoke(client.app.state.gateway, "hello-plugin", BACKEND, {**TOOL, "effect": "write"}, {}, action_id=action_id)


def test_external_schema_and_invalid_arguments_never_call_backend(client, monkeypatch):
    def forbidden():
        pytest.fail("network transport created for invalid tool arguments")
    monkeypatch.setattr(dispatch, "client", forbidden)
    for schema, arguments in [({**TOOL["input"], "$ref": "https://example.invalid/schema"}, {}),
                              (TOOL["input"], {"undeclared": True})]:
        with pytest.raises(ApiError):
            dispatch.invoke(client.app.state.gateway, "hello-plugin", BACKEND, {**TOOL, "input": schema}, arguments)


def test_transport_disables_proxy_environment_and_redirects(monkeypatch):
    def capture(**kwargs):
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        assert kwargs["timeout"].connect == 2 and kwargs["timeout"].read == 5
    monkeypatch.setattr(dispatch.httpx, "Client", capture)
    dispatch.client()


def test_unbounded_tool_schema_patterns_are_refused():
    from onemind_core.errors import ApiError
    from onemind_core.plugins.dispatch import schema_validator
    import pytest
    with pytest.raises(ApiError):
        schema_validator({"type": "object", "additionalProperties": False,
                          "properties": {"value": {"type": "string", "pattern": "(a+)+$"}}})
