# SPDX-License-Identifier: Apache-2.0
"""SECURITY.md §3.2: the first-boot owner token is break-glass. Flagged `retire_on_setup`, it works on
the API until the first owner account exists, then answers 401. The file entry stays for the rescue
console (D-008)."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest
import yaml
from fastapi.testclient import TestClient

from onemind_core.app import create_app
from onemind_core.auth import TokenStore
from test_identity import LOCAL_PEER, PASSWORD, confirm_setup_kit, csrf, id_settings, new_session_client

FIRST = "first-boot-token-0123456789abcdef"
OTHER = "install-owner-token-0123456789ab"


def _file(tmp_path, retiring=True):
    entry = {"id": "owner", "kind": "person", "role": "owner"}
    p = tmp_path / "tokens.yaml"
    p.write_text(yaml.safe_dump({"tokens": {
        "sha256:" + hashlib.sha256(FIRST.encode()).hexdigest(): {**entry, **({"retire_on_setup": True} if retiring else {})},
        OTHER: {"id": "other", "kind": "person", "role": "owner"},
    }}))
    return p


def test_store_retires_only_flagged_entry_once_owner_exists(tmp_path):
    store = TokenStore(_file(tmp_path))
    done = {"v": False}
    store.retire_when = lambda: done["v"]
    assert store.lookup(FIRST).is_owner
    done["v"] = True
    assert store.lookup(FIRST) is None
    assert store.lookup(FIRST, include_retired=True).is_owner   # setup answers 409, not 401
    assert store.lookup(OTHER).is_owner                         # unflagged owner tokens are unchanged
    assert [p.id for _, p in store.entries()] == ["other"]      # no longer listed as an active token
    done["v"] = False
    assert store.lookup(FIRST) is None                          # never comes back


def test_failed_retire_check_denies_flagged_token(tmp_path):
    """After a restart `_retired` is False; if the database check raises, deny rather than fail open."""
    store = TokenStore(_file(tmp_path))

    def boom() -> bool:
        raise RuntimeError("database unreachable")

    store.retire_when = boom
    assert store.lookup(FIRST) is None
    assert [p.id for _, p in store.entries()] == ["other"]
    assert store.lookup(OTHER).is_owner                         # unflagged tokens are unaffected
    store.retire_when = lambda: False                           # database back, no owner yet: works again
    assert store.lookup(FIRST).is_owner


def test_unflagged_token_is_never_retired(tmp_path):
    store = TokenStore(_file(tmp_path, retiring=False))
    store.retire_when = lambda: True
    assert store.lookup(FIRST).is_owner


def test_first_boot_token_returns_401_after_setup(settings, clock, executor, tmp_path):
    cfg = replace(id_settings(settings, box_code_file=None), tokens_file=_file(tmp_path))
    first = {"Authorization": f"Bearer {FIRST}"}
    with TestClient(create_app(cfg, clock=clock, executor=executor), client=LOCAL_PEER) as c:
        assert c.get("/v1/me", headers=first).status_code == 200
        r = c.post("/v1/auth/setup", headers=first, json={"username": "zeus", "password": PASSWORD})
        assert r.status_code == 201, r.text
        assert new_session_client(c).get("/v1/me", headers=first).status_code == 401
        confirm_setup_kit(c, csrf(c))
        c.cookies.clear()  # setup signs the new owner in; the cookie is not what is under test
        assert c.get("/v1/me", headers=first).status_code == 401
        assert c.get("/v1/tokens", headers={"Authorization": f"Bearer {OTHER}"}).status_code == 200
        again = c.post("/v1/auth/setup", headers=first, json={"username": "x1", "password": PASSWORD})
        assert again.status_code == 409
