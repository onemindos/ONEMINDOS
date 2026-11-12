# SPDX-License-Identifier: Apache-2.0
"""The world an attack test runs in: a fresh gateway, every principal kind, and request probes.

A *principal kind* is one column of the authorization matrix (sec_policy.py): who is calling.
`World.mint(kind)` returns the request headers that present that principal, or skips the test
with the name of the stream that will make the kind exist. A *probe* builds one concrete request
for a route (filling path parameters with real ids and giving a valid body), so a refusal is about
who is asking and never about a malformed request.
"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass, field, replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.routing import Mount, Route, WebSocketRoute

from conftest import ScriptedExecutor
from onemind_core.app import create_app

# Columns of the matrix, in the order the report shows them.
KINDS = (
    "none", "owner", "adult", "guest", "child", "agent", "app-agent", "plugin", "automation", "node",
    "expired", "revoked", "revoked-agent",
)

# What each column means (also printed in failure messages).
DESCRIBE = {
    "none": "no Authorization header",
    "owner": "person, role owner (static tokens file, contract §3)",
    "adult": "person, role adult (static tokens file)",
    "guest": "person, role guest (static tokens file)",
    "child": "household person, role child (contract §12.6)",
    "agent": "agent principal from the static tokens file (§3)",
    "app-agent": "agent principal issued to an app at install (§11.2)",
    "plugin": "plugin principal plugin:<app-id> (§12.1)",
    "automation": "automation principal automation:<rule-id> (§12.1)",
    "node": "node principal node:<node_id> (§12.1, §12.11)",
    "expired": "a person's API token after its expires_at (§12.6)",
    "revoked": "an owner token deleted from the tokens file while the gateway runs",
    "revoked-agent": "an app's agent token after app.remove revoked it (§11.2 step 3)",
}

# Kinds that cannot exist on a tree without their stream. The skip reason names the stream.
PENDING_KINDS = {
    "child": "role child is created through household accounts: feat/identity (PR #41, CORE-SEC-2/-3, §12.6)",
    "expired": "token expiry arrives with API tokens: feat/identity (PR #41, CORE-SEC-3, §12.6)",
    "plugin": "kind plugin arrives with the plugins stream: feat/plugins-core (PLUGIN-SDK, DEV-API-6, §12.1)",
    "automation": "kind automation arrives with feat/automation (CORE-AUTO-2, §12.1, §12.17)",
    "node": "kind node arrives with feat/fabric-join (CORE-FABRIC-1, §12.1, §12.11)",
}
# Kinds whose mint() is written. A kind or role that appears in onemind_core.auth without being
# in this set fails test_every_principal_kind_has_a_column: write its mint() first.
MINTABLE = {"none", "owner", "adult", "guest", "child", "agent", "app-agent", "expired", "revoked", "revoked-agent"}

# The static tokens file: matrix column -> (principal id, kind, role).
STATIC = {
    "owner": ("owner", "person", "owner"),
    "adult": ("adult", "person", "adult"),
    "guest": ("guest", "person", "guest"),
    "agent": ("hermes", "agent", "agent"),
    "revoked": ("former-owner", "person", "owner"),
}

AGENT_APP = "hermes-like"      # fixture app with spec.agent (core/tests/fixtures/apps)
TARGET_APP = "uptime-kuma"     # fixture app every request probe asks to install
NODE_ID = "a1b2c3d4e5f6"
IDENTITY_STREAM = "feat/identity (PR #41, contract §12.6)"
ID_OWNER, ID_PASSWORD = "matrix-owner", "correct horse battery staple 1"


@dataclass
class Req:
    path: str
    json: Any = None
    content: bytes | None = None
    headers: dict[str, str] = field(default_factory=dict)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def route_methods(app) -> set[tuple[str, str]]:
    """Every (method, path template) the app answers. WebSocket routes are "WS", mounts "MOUNT"."""
    out: set[tuple[str, str]] = set()
    for r in app.routes:
        if isinstance(r, (APIRoute, Route)):
            out |= {(m, r.path) for m in (r.methods or ())}
        elif isinstance(r, WebSocketRoute):
            out.add(("WS", r.path))
        elif isinstance(r, Mount):
            out.add(("MOUNT", r.path))
        else:  # a new kind of route is a new attack surface: classify it before it ships
            out.add((type(r).__name__.upper(), getattr(r, "path", repr(r))))
    return out


class World:
    """One fresh gateway (SQLite or the CI PostgreSQL) with a scripted executor and random tokens."""

    def __init__(self, settings, clock, tmp_path: Path):
        self.clock = clock
        self.tmp = tmp_path
        self.tokens = {k: secrets.token_urlsafe(24) for k in STATIC}
        self.tokens_path = tmp_path / "matrix-tokens.yaml"
        self._write_tokens(STATIC)
        self.executor = ScriptedExecutor()
        self.settings = replace(settings, tokens_file=self.tokens_path)
        self.app = create_app(self.settings, clock=clock, executor=self.executor)
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self._keys = 0
        self._identity: dict[str, Any] = {}

    def __enter__(self) -> World:
        self.client.__enter__()
        return self

    def __exit__(self, *exc) -> None:
        self.client.__exit__(*exc)

    # ---- static tokens ------------------------------------------------------------------------
    def _write_tokens(self, kinds) -> None:
        doc = {"tokens": {self.tokens[k]: dict(zip(("id", "kind", "role"), STATIC[k], strict=True)) for k in kinds}}
        before = self.tokens_path.stat().st_mtime if self.tokens_path.exists() else None
        self.tokens_path.write_text(yaml.safe_dump(doc))
        if before is not None:  # TokenStore reloads on an mtime change; make sure there is one
            os.utime(self.tokens_path, (before + 5, before + 5))

    def static(self, kind: str) -> dict[str, str]:
        return bearer(self.tokens[kind])

    # ---- helpers that act as the owner ----------------------------------------------------------
    def key(self) -> str:
        self._keys += 1
        return f"sec-{self._keys}-{secrets.token_hex(4)}"

    def action_body(self, app_id: str = TARGET_APP, type_: str = "app.install") -> dict:
        expires = self.clock.now + timedelta(minutes=30)
        return {"type": type_, "params": {"app_id": app_id}, "idempotency_key": self.key(),
                "expires_at": expires.isoformat().replace("+00:00", "Z")}

    def owner_action(self, app_id: str = TARGET_APP, type_: str = "app.install") -> str:
        r = self.client.post("/v1/actions", json=self.action_body(app_id, type_), headers=self.static("owner"))
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def owner_approve(self, action_id: str) -> dict:
        r = self.client.post(f"/v1/actions/{action_id}/approve", headers=self.static("owner"))
        assert r.status_code == 200, r.text
        return r.json()

    def install_agent_app(self) -> str:
        """Install the fixture app with spec.agent; returns its freshly issued agent token."""
        assert self.owner_approve(self.owner_action(AGENT_APP))["state"] == "succeeded"
        grant = self.executor.agents[-1]
        assert grant is not None and grant.token
        return grant.token

    def remove_app(self, app_id: str) -> None:
        assert self.owner_approve(self.owner_action(app_id, "app.remove"))["state"] == "succeeded"

    def heartbeat(self, node_id: str = NODE_ID, **extra) -> str:
        hb = {"schema": "onemind.node.status/v1", "node_id": node_id, "hostname": "matrix-node",
              "board": "x86_64-efi", "arch": "amd64", **extra}
        assert self.app.state.registry.ingest(f"onemind.node.{node_id}.status", json.dumps(hb).encode())
        return node_id

    # ---- what the world looks like ------------------------------------------------------------------
    def routes(self) -> set[tuple[str, str]]:
        return route_methods(self.app)

    def has_route(self, method: str, path: str) -> bool:
        return (method, path) in self.routes()

    def snapshot(self) -> tuple:
        """Everything a refused request must leave unchanged: actions, their states, app states."""
        repo = self.app.state.repo
        actions = sorted((a.id, a.state, a.type, json.dumps(a.params, sort_keys=True)) for a in repo.list())
        apps = sorted((k, v.status) for k, v in repo.list_app_states().items())
        return actions, apps

    def audit(self) -> list[dict]:
        path = self.settings.audit_path
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    # ---- principals ---------------------------------------------------------------------------------
    def mint(self, kind: str) -> dict[str, str]:
        if kind == "none":
            return {}
        if kind in ("owner", "adult", "guest", "agent"):
            return self.static(kind)
        if kind == "app-agent":
            return bearer(self.install_agent_app())
        if kind == "revoked":
            headers = self.static("revoked")
            assert self.client.get("/v1/instance", headers=headers).status_code == 200  # it worked ...
            self._write_tokens([k for k in STATIC if k != "revoked"])                    # ... until now
            return headers
        if kind == "revoked-agent":
            token = self.install_agent_app()
            assert self.client.get("/v1/instance", headers=bearer(token)).status_code == 200
            self.remove_app(AGENT_APP)
            return bearer(token)
        if kind in ("child", "expired"):
            return self._mint_identity(kind)
        pytest.skip(PENDING_KINDS[kind])

    # ---- household identity (feat/identity, PR #41) ---------------------------------------------------
    def _identity_owner(self) -> dict[str, str]:
        """A household owner account with a bearer session, created through first-boot setup."""
        if "owner" not in self._identity:
            r = self.client.post("/v1/auth/setup", headers=self.static("owner"), json={
                "username": ID_OWNER, "password": ID_PASSWORD, "client": "cli"})
            assert r.status_code == 201, r.text
            self._identity["session"] = r.json()
            self._identity["owner"] = bearer(r.json()["access_token"])
        return self._identity["owner"]

    def id_session(self) -> dict:
        self._identity_owner()
        return self._identity["session"]

    def id_session_id(self) -> str:
        r = self.client.get("/v1/auth/sessions", headers=self._identity_owner())
        assert r.status_code == 200, r.text
        return r.json()[0]["id"]

    def id_user(self, role: str = "guest") -> tuple[str, str]:
        """(user id, enrolment code) of a new household member, created by the household owner."""
        r = self.client.post("/v1/users", headers=self._identity_owner(), json={"display_name": "Probe", "role": role})
        assert r.status_code == 201, r.text
        return r.json()["id"], _enrol_code(r.json())

    def id_token(self) -> str:
        r = self.client.post("/v1/tokens", headers=self._identity_owner(), json={"name": "probe"})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def _mint_identity(self, kind: str) -> dict[str, str]:
        if not (self.has_route("POST", "/v1/auth/setup") and self.has_route("POST", "/v1/users")):
            pytest.skip(PENDING_KINDS[kind])
        owner = self._identity_owner()
        if kind == "child":
            r = self.client.post("/v1/users", headers=owner, json={"display_name": "Kid", "role": "child"})
            assert r.status_code == 201, r.text
            code = _enrol_code(r.json())
            r = self.client.post("/v1/auth/enrol", json={
                "code": code, "username": "matrix-kid", "password": ID_PASSWORD, "client": "cli"})
            assert r.status_code == 201, r.text
            return bearer(r.json()["access_token"])
        # expired: the household owner's own API token, one day after it expired
        r = self.client.post("/v1/tokens", headers=owner, json={"name": "matrix", "expires_in_days": 1})
        assert r.status_code == 201, r.text
        token = r.json()["one_time"]["token"]
        assert self.client.get("/v1/instance", headers=bearer(token)).status_code == 200
        self.clock.advance(2 * 86400)
        # the household owner's own session expired with it: sign in again for the probes
        r = self.client.post("/v1/auth/login", json={"username": ID_OWNER, "password": ID_PASSWORD, "client": "cli"})
        assert r.status_code == 200, r.text
        self._identity["session"] = r.json()
        self._identity["owner"] = bearer(r.json()["access_token"])
        return bearer(token)


def _enrol_code(body: dict) -> str:
    """The enrolment code from POST /v1/users' one_time block (a code or a URL that carries it)."""
    one_time = body.get("one_time") or {}
    code = one_time.get("enrolment_code") or one_time.get("code")
    if code:
        return code
    return one_time["enrolment_url"].rsplit("enrol=", 1)[1]


# ---- probes: one valid request per route ----------------------------------------------------------------
def p_static(path: str):
    return lambda w: Req(path)


def p_node(w: World) -> Req:
    return Req(f"/v1/nodes/{w.heartbeat()}")


def p_action(w: World) -> Req:
    return Req(f"/v1/actions/{w.owner_action()}")


def p_approve(w: World) -> Req:
    return Req(f"/v1/actions/{w.owner_action()}/approve")


def p_deny(w: World) -> Req:
    return Req(f"/v1/actions/{w.owner_action()}/deny")


def p_request(w: World) -> Req:
    return Req("/v1/actions", json=w.action_body())


def p_mcp_ping(w: World) -> Req:
    return Req("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
               headers={"Accept": "application/json, text/event-stream"})


# Identity routes (feat/identity, PR #41). Bodies are valid, so a refusal is about the caller.
def p_setup(w: World) -> Req:
    # the caller's own bearer is offered as the install owner token (§12.6 first boot)
    return Req("/v1/auth/setup", json={"username": "probe-owner", "password": ID_PASSWORD, "client": "cli"})


def p_login(w: World) -> Req:
    w.id_session()
    return Req("/v1/auth/login", json={"username": ID_OWNER, "password": ID_PASSWORD, "client": "cli"})


def p_enrol(w: World) -> Req:
    return Req("/v1/auth/enrol", json={"code": w.id_user()[1], "username": "probe-member",
                                       "password": "a third long passphrase 3", "client": "cli"})


def p_refresh(w: World) -> Req:
    return Req("/v1/auth/refresh", json={"refresh_token": w.id_session()["refresh_token"]})


def p_session_delete(w: World) -> Req:
    return Req(f"/v1/auth/sessions/{w.id_session_id()}")


def p_passkey_register(w: World) -> Req:
    return Req("/v1/auth/passkeys/register", json={"credential": {"id": "probe", "type": "public-key"}})


def p_password(w: World) -> Req:
    return Req("/v1/auth/password", json={"current_password": ID_PASSWORD, "new_password": "a brand new long passphrase"})


def p_totp_confirm(w: World) -> Req:
    return Req("/v1/auth/totp/confirm", json={"code": "123456"})


def p_totp_disable(w: World) -> Req:
    return Req("/v1/auth/totp/disable", json={"password": ID_PASSWORD})


def p_user_create(w: World) -> Req:
    return Req("/v1/users", json={"display_name": "Probe", "role": "adult"})


def p_user_patch(w: World) -> Req:
    return Req(f"/v1/users/{w.id_user()[0]}", json={"display_name": "Renamed"})


def p_user_disable(w: World) -> Req:
    return Req(f"/v1/users/{w.id_user()[0]}/disable")


def p_token_create(w: World) -> Req:
    return Req("/v1/tokens", json={"name": "probe", "principal": "self"})


def p_token_rotate(w: World) -> Req:
    return Req(f"/v1/tokens/{w.id_token()}/rotate", json={"grace_s": 0})


def p_token_delete(w: World) -> Req:
    return Req(f"/v1/tokens/{w.id_token()}")


def p_access_put(w: World) -> Req:
    return Req(f"/v1/apps/{TARGET_APP}/access", json={"roles": ["owner", "adult"], "people": []})


def p_approve_options(w: World) -> Req:
    return Req(f"/v1/actions/{w.owner_action()}/approve-options")
