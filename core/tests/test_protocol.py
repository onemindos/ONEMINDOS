# SPDX-License-Identifier: Apache-2.0
"""The client protocol policy (#697, sdk/contracts/protocol-versions.md).

The corpus half replays recorded requests of every older generation still served against the
current gateway: a change that breaks what an old app sends or reads fails here, not on a phone.
Re-record only on purpose (a reviewed generation bump): ONEMIND_RECORD_PROTOCOL_CORPUS=1.
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from conftest import GUEST, OWNER
from fastapi.testclient import TestClient

from onemind_core import protocol as p
from onemind_core.app import create_app
from onemind_core.files.settings import FilesSettings
from onemind_core.protocol import ProtocolSettings

CORPUS = Path(__file__).parent / "fixtures" / "protocol"
AS = {"owner": OWNER, "guest": GUEST, "none": {}}


def shape(body):
    """What an old client may rely on: the JSON type and the keys it reads (new keys are allowed)."""
    if isinstance(body, dict):
        return {"type": "object", "keys": sorted(body)}
    if isinstance(body, list):
        first = body[0] if body and isinstance(body[0], dict) else None
        return {"type": "array", "item_keys": sorted(first) if first else []}
    return {"type": type(body).__name__}


def compatible(recorded: dict, now: dict) -> bool:
    if recorded["type"] != now["type"]:
        return False
    return set(recorded.get("keys", recorded.get("item_keys", []))) <= set(now.get("keys", now.get("item_keys", [])))


def corpus_versions() -> list[int]:
    """Every generation still served below the current one: the N-1 window (and older, if kept)."""
    return list(range(p.PROTOCOL_MINIMUM, p.PROTOCOL_CURRENT))


@pytest.fixture
def corpus_client(settings, clock, executor, tmp_path):
    # The corpus records Files with unavailable storage. A file in place of
    # the storage directory makes that true on every worker, even as root.
    root = tmp_path / "unavailable-files"
    root.touch()
    isolated = replace(settings, sections={**settings.sections, "files": FilesSettings(root=root)})
    with TestClient(create_app(isolated, clock=clock, executor=executor)) as client:
        yield client


@pytest.mark.parametrize("version", corpus_versions())
def test_recorded_old_requests_still_work(corpus_client, version):
    path = CORPUS / f"v{version}.json"
    assert path.is_file(), f"generation {version} is still served, so its recorded corpus {path.name} must exist"
    doc = json.loads(path.read_text())
    assert doc["version"] == version and doc["requests"], "a corpus records at least one request"
    record = os.environ.get("ONEMIND_RECORD_PROTOCOL_CORPUS") == "1"
    broken = []
    for r in doc["requests"]:
        headers = {**AS[r["as"]], **r.get("headers", {})}
        res = corpus_client.request(r["method"], r["path"], headers=headers, json=r.get("body"))
        got = {"status": res.status_code, "shape": shape(res.json()) if res.content else {"type": "empty"}}
        if record:
            r.update(got)
        elif got["status"] != r["status"] or not compatible(r["shape"], got["shape"]):
            broken.append(f"{r['method']} {r['path']}: recorded {r['status']} {r['shape']}, now {got['status']} {got['shape']}")
    if record:
        path.write_text(json.dumps(doc, indent=1) + "\n")
    assert not broken, "a change breaks protocol %d clients (add a generation instead):\n%s" % (version, "\n".join(broken))


def test_every_answer_carries_the_supported_range(client):
    for path, headers in (("/healthz", {}), ("/v1/instance", OWNER), ("/v1/instance", {})):
        res = client.get(path, headers=headers)
        assert res.headers[p.PROTOCOL_MIN_HEADER] == str(p.PROTOCOL_MINIMUM)
        assert res.headers[p.PROTOCOL_MAX_HEADER] == str(p.PROTOCOL_CURRENT)


def test_declared_current_and_newer_clients_are_served(client):
    for sent in (p.PROTOCOL_CURRENT, p.PROTOCOL_CURRENT + 1):
        res = client.get("/v1/instance", headers={**OWNER, p.PROTOCOL_HEADER: str(sent)})
        assert res.status_code == 200, sent


@pytest.mark.parametrize("value", ["0", "two", "2.0", "-1", "99999", ""])
def test_a_malformed_header_is_refused(client, value):
    res = client.get("/v1/instance", headers={**OWNER, p.PROTOCOL_HEADER: value})
    assert res.status_code == 422
    assert res.json()["reason"] == "protocol_header_invalid"


@pytest.fixture
def strict_client(settings, clock, executor):
    """A hub whose owner refuses clients below generation 2 (ONEMIND_PROTOCOL_MINIMUM=2)."""
    s = replace(settings, sections={**settings.sections, "protocol": ProtocolSettings(minimum=2)})
    with TestClient(create_app(s, clock=clock, executor=executor)) as c:
        yield c


def test_an_old_client_gets_upgrade_required(strict_client):
    for headers in ({}, {p.PROTOCOL_HEADER: "1"}):  # no header speaks generation 1
        res = strict_client.get("/v1/instance", headers={**OWNER, **headers})
        assert res.status_code == 400
        body = res.json()
        assert body["error"] == "upgrade_required" and body["reason"] == "protocol_too_old"
        assert body["details"] == [{"field": p.PROTOCOL_HEADER, "sent": 1, "minimum": 2, "maximum": p.PROTOCOL_CURRENT}]
        assert res.headers[p.PROTOCOL_MIN_HEADER] == "2"
        assert res.headers["x-content-type-options"] == "nosniff"  # guard still wraps the refusal
    assert strict_client.get("/v1/instance", headers={**OWNER, p.PROTOCOL_HEADER: "2"}).status_code == 200


def test_the_probe_and_the_policy_stay_open_to_old_clients(strict_client):
    assert strict_client.get("/healthz").status_code == 200
    res = strict_client.get("/v1/protocol")
    assert res.status_code == 200
    info = res.json()
    assert info["header"] == p.PROTOCOL_HEADER
    assert (info["minimum"], info["maximum"], info["current"]) == (2, p.PROTOCOL_CURRENT, p.PROTOCOL_CURRENT)
    assert [v["supported"] for v in info["versions"]] == [v.version >= 2 for v in p.PROTOCOL_VERSIONS]


def test_policy_route_lists_each_generation(client):
    info = client.get("/v1/protocol").json()
    assert [v["version"] for v in info["versions"]] == list(range(1, p.PROTOCOL_CURRENT + 1))
    assert info["versions"][-1]["supported_until"] is None
    assert info["versions"][0]["supported_until"] == "2027-11-21"  # generation 2 shipped 2026-11-21


def test_the_minimum_setting_cannot_lower_or_overshoot():
    with pytest.raises(ValueError):
        ProtocolSettings(minimum=p.PROTOCOL_CURRENT + 1).validate()
    with pytest.raises(ValueError):
        ProtocolSettings(minimum=0).validate()


def test_the_version_table_keeps_n_minus_1_for_twelve_months():
    versions = [v.version for v in p.PROTOCOL_VERSIONS]
    assert versions == list(range(1, len(versions) + 1)), "generations are 1, 2, 3, ... and only appended"
    assert all(a.released <= b.released for a, b in zip(p.PROTOCOL_VERSIONS, p.PROTOCOL_VERSIONS[1:]))
    # A generation below the minimum was dropped only after its 12 months: refuse silent breaks.
    for v in range(1, p.PROTOCOL_MINIMUM):
        assert p.supported_until(v) <= date.today(), f"generation {v} is dropped before {p.supported_until(v)}"
    assert p._add_months(date(2027, 2, 28), 12) == date(2028, 2, 28)
    assert p._add_months(date(2024, 2, 29), 12) == date(2025, 2, 28)


def test_openapi_names_the_current_generation(client):
    doc = client.get("/openapi.json").json()
    assert doc["info"]["x-onemind-protocol"] == {"header": p.PROTOCOL_HEADER, "current": p.PROTOCOL_CURRENT}
    assert "upgrade_required" in doc["components"]["schemas"]["ErrorBody"]["properties"]["error"]["enum"]
