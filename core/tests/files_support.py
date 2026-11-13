# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures and helpers for the FILES tests (imported by test_files_*.py)."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from onemind_core.app import create_app
from onemind_core.files.settings import FilesSettings

from conftest import ADULT, AGENT, GUEST, OWNER  # noqa: F401  (re-exported for the test modules)

TUS = {"Tus-Resumable": "1.0.0"}


@pytest.fixture
def files_root(tmp_path: Path) -> Path:
    return tmp_path / "files"


@pytest.fixture
def files_settings(files_root) -> FilesSettings:
    return FilesSettings(root=files_root, min_free_bytes=0)


@pytest.fixture
def fc(settings, clock, executor, files_settings):
    """A gateway client whose FILES root is a temporary directory."""
    s = replace(settings, sections={**settings.sections, "files": files_settings})
    with TestClient(create_app(s, clock=clock, executor=executor)) as c:
        yield c


def ok(r, status=200):
    assert r.status_code == status, (r.status_code, r.text)
    return r.json() if r.content and r.headers.get("content-type", "").startswith("application/json") else r


def mkdir(c, headers, root, path):
    return ok(c.post("/v1/files/ops", headers=headers, json={"op": "mkdir", "root": root, "path": path}))


def meta(**kv: str) -> str:
    return ",".join(f"{k} {base64.b64encode(v.encode()).decode()}" for k, v in kv.items())


def upload(c, headers, root, path, name, data: bytes, *, sha=True, overwrite=False):
    """Create and send an upload in one chunk. Returns the final PATCH response."""
    m = {"root": root, "path": path, "filename": name}
    if sha:
        m["sha256"] = hashlib.sha256(data).hexdigest()
    if overwrite:
        m["overwrite"] = "1"
    r = c.post("/v1/files/uploads", headers={**headers, **TUS, "Upload-Length": str(len(data)),
                                              "Upload-Metadata": meta(**m)})
    assert r.status_code == 201, r.text
    if not data:
        return r
    return c.patch(r.headers["Location"], content=data, headers={
        **headers, **TUS, "Upload-Offset": "0", "Content-Type": "application/offset+octet-stream"})


def audit_events(settings) -> list[dict]:
    return [json.loads(line) for line in settings.audit_path.read_text().splitlines() if line.strip()]
