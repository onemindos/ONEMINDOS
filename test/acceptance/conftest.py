# SPDX-License-Identifier: Apache-2.0
"""Fixtures for the live-hub acceptance suite (see README.md).

Everything that talks to a hub skips cleanly when ONEMIND_HUB_URL (and, for owner tests,
ONEMIND_OWNER_TOKEN) is not set, so `pytest test/acceptance` is safe in CI and on a laptop.
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

CHECKLIST = Path(__file__).resolve().parents[2] / "docs" / "leap" / "ALPHA-CHECKLIST.md"
TIMEOUT = 20


def cites(item: str):
    """Mark a test with the ALPHA-CHECKLIST.md row it serves. test_citations.py checks the row exists."""
    return pytest.mark.checklist(item)


def pytest_configure(config):
    config.addinivalue_line("markers", "checklist(item): the docs/leap/ALPHA-CHECKLIST.md row this test serves")


def checklist_text() -> str:
    return CHECKLIST.read_text(encoding="utf-8")


class Hub:
    """A thin client: base URL plus bearer tokens, no retries, no mocks."""

    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.http = requests.Session()

    def call(self, method: str, path: str, token: str | None = None, **kw) -> requests.Response:
        headers = dict(kw.pop("headers", {}))
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.http.request(method, self.base + path, headers=headers, timeout=TIMEOUT, **kw)

    def json(self, method: str, path: str, token: str | None, expect: int | tuple[int, ...], **kw):
        r = self.call(method, path, token, **kw)
        ok = (expect,) if isinstance(expect, int) else expect
        assert r.status_code in ok, f"{method} {path} -> {r.status_code} {r.text[:300]}"
        return r.json() if r.content else None


def install_request(app_id: str, tag: str) -> dict:
    """A body for POST /v1/actions that files an app.install and expires in an hour."""
    exp = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"type": "app.install", "params": {"app_id": app_id},
            "idempotency_key": f"accept-{tag}-{uuid.uuid4().hex[:12]}", "expires_at": exp}


def pick_app(apps: list[dict], wanted: str | None) -> str | None:
    """The app the suite files requests for: the one named, else the first that is not installed."""
    if wanted:
        return wanted
    for a in apps:
        if not a.get("installed") and a.get("status") == "not_installed":
            return a["id"]
    return None


_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9-]*")


@pytest.fixture(scope="session")
def hub() -> Hub:
    url = os.environ.get("ONEMIND_HUB_URL", "").strip()
    if not url:
        pytest.skip("ONEMIND_HUB_URL not set: no live hub to test")
    return Hub(url)


@pytest.fixture(scope="session")
def owner(hub: Hub) -> str:
    tok = os.environ.get("ONEMIND_OWNER_TOKEN", "").strip()
    if not tok:
        pytest.skip("ONEMIND_OWNER_TOKEN not set")
    return tok


@pytest.fixture(scope="session")
def app_id(hub: Hub, owner: str) -> str:
    wanted = os.environ.get("ONEMIND_ACCEPT_APP_ID", "").strip() or None
    if wanted and not _SAFE_ID.fullmatch(wanted):
        pytest.fail("ONEMIND_ACCEPT_APP_ID is not an app id")
    found = pick_app(hub.json("GET", "/v1/apps", owner, 200), wanted)
    if not found:
        pytest.skip("no not-installed app in the catalogue; set ONEMIND_ACCEPT_APP_ID")
    return found


def _mint(hub: Hub, owner: str, name: str, principal, scopes) -> tuple[str, str] | None:
    """Mint a token with the owner token; None when this hub does not allow it (static-file owner)."""
    r = hub.call("POST", "/v1/tokens", owner, json={"name": name, "principal": principal, "scopes": scopes,
                                                     "expires_in_days": 1})
    if r.status_code != 201:
        return None
    body = r.json()
    secret = body.get("token") or body.get("secret") or (body.get("one_time") or {}).get("token")
    return (body["id"], secret) if secret and body.get("id") else None


@pytest.fixture(scope="session")
def reader_token(hub: Hub, owner: str):
    """A narrow token (read-only bundle): ONEMIND_READER_TOKEN, else minted and revoked here."""
    env = os.environ.get("ONEMIND_READER_TOKEN", "").strip()
    if env:
        yield env
        return
    m = _mint(hub, owner, "acceptance-reader", "self", ["reader"])
    if not m:
        pytest.skip("no ONEMIND_READER_TOKEN and this owner token cannot mint one")
    yield m[1]
    hub.call("DELETE", f"/v1/tokens/{m[0]}", owner)


@pytest.fixture(scope="session")
def agent_token(hub: Hub, owner: str):
    """An AI agent's token: ONEMIND_AGENT_TOKEN, else minted (requester bundle) and revoked here."""
    env = os.environ.get("ONEMIND_AGENT_TOKEN", "").strip()
    if env:
        yield env
        return
    m = _mint(hub, owner, "acceptance-agent", {"kind": "agent", "id": "agent:acceptance"}, ["requester"])
    if not m:
        pytest.skip("no ONEMIND_AGENT_TOKEN and this owner token cannot mint one")
    yield m[1]
    hub.call("DELETE", f"/v1/tokens/{m[0]}", owner)


@pytest.fixture(scope="session")
def child_token() -> str:
    tok = os.environ.get("ONEMIND_CHILD_TOKEN", "").strip()
    if not tok:
        pytest.skip("ONEMIND_CHILD_TOKEN not set (a token of a Child-role household member)")
    return tok


@pytest.fixture
def filed(hub: Hub, owner: str, app_id: str):
    """Files install requests and denies every one still waiting at the end, so nothing is left pending."""
    ids: list[str] = []

    def file(token: str, tag: str) -> dict:
        body = hub.json("POST", "/v1/actions", token, 201, json=install_request(app_id, tag))
        ids.append(body["id"])
        return body

    yield file
    for i in ids:
        a = hub.call("GET", f"/v1/actions/{i}", owner)
        if a.status_code == 200 and a.json().get("state") == "awaiting_approval":
            hub.call("POST", f"/v1/actions/{i}/deny", owner)
