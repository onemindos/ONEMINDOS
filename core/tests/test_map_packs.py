# SPDX-License-Identifier: Apache-2.0
"""Map pack requests use the ledger and verified catalog; the gateway serves only the index."""
import base64
import hashlib
import io
import json
from collections import namedtuple

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from conftest import AGENT, OWNER, action_body, make_client
from onemind_core.geo import map_packs
from onemind_core.geo.map_packs import MapSettings

ARCHIVE = b"PMTiles\x03test pack"
REGION_ID = "test-region"
Disk = namedtuple("Disk", "total used free")


@pytest.fixture
def box(settings, clock, tmp_path, monkeypatch):
    root = tmp_path / "packs"
    root.mkdir()
    key = Ed25519PrivateKey.generate()
    public = tmp_path / "regions.pub"
    public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,
                                                     serialization.PublicFormat.SubjectPublicKeyInfo))
    catalog = tmp_path / "regions.json"
    body = json.dumps({"schema": "onemind.map.regions/v1", "regions": [{
        "id": REGION_ID, "region": "Test Region", "url": "https://example.test/region.pmtiles",
        "sha256": hashlib.sha256(ARCHIVE).hexdigest(), "bytes": len(ARCHIVE),
    }]}).encode()
    catalog.write_bytes(body)
    catalog.with_suffix(".json.sig").write_bytes(base64.b64encode(key.sign(body)))
    monkeypatch.setattr(map_packs.MapPacks, "_usage", staticmethod(lambda _: Disk(1000, 0, 1000)))
    sections = {**settings.sections, "map": MapSettings(root, catalog, public)}
    with make_client(settings, clock, sections=sections) as client:
        client.app.state.actions.spawn = lambda fn: fn()
        yield client, root, catalog


def request_pack(client, clock, kind, params, *, headers=AGENT):
    body = action_body(clock, type_=f"map.pack.{kind}", key=f"{kind}-{next(iter(params.values()))}")
    body["params"] = params
    return client.post("/v1/actions", json=body, headers=headers)


def test_agent_requests_but_owner_approves_verified_add_and_remove(box, clock, monkeypatch):
    client, root, _ = box
    downloads = []

    def download(region):
        downloads.append(region.id)
        return io.BytesIO(ARCHIVE)

    monkeypatch.setattr(map_packs, "_open_download", download)
    response = request_pack(client, clock, "add", {"region_id": REGION_ID})
    assert response.status_code == 201, response.text
    action = f"/v1/actions/{response.json()['id']}/approve"
    assert client.post(action, headers=AGENT).status_code == 403
    assert downloads == [] and list(root.iterdir()) == []
    done = client.post(action, headers=OWNER)
    assert done.json()["state"] == "succeeded", done.text
    assert (root / REGION_ID / "archive.pmtiles").read_bytes() == ARCHIVE
    assert (root / REGION_ID).stat().st_mode & 0o777 == 0o755
    assert all(entry.stat().st_mode & 0o777 == 0o644 for entry in (root / REGION_ID).iterdir())
    rows = client.get("/v1/map/packs", headers=OWNER).json()["packs"]
    assert [(r["id"], r["bytes"]) for r in rows] == [(REGION_ID, len(ARCHIVE))]
    response = request_pack(client, clock, "remove", {"pack_id": REGION_ID})
    assert response.status_code == 201, response.text
    done = client.post(f"/v1/actions/{response.json()['id']}/approve", headers=OWNER)
    assert done.json()["state"] == "succeeded", done.text
    assert list(root.iterdir()) == []
    assert client.get("/v1/map/packs", headers=OWNER).json()["packs"] == []
    assert request_pack(client, clock, "remove", {"pack_id": "missing"}).status_code == 404


def test_checksum_mismatch_leaves_no_pack_or_staging_file(box, clock, monkeypatch):
    client, root, _ = box
    monkeypatch.setattr(map_packs, "_open_download", lambda _: io.BytesIO(b"x" * len(ARCHIVE)))
    offered = request_pack(client, clock, "add", {"region_id": REGION_ID})
    assert offered.status_code == 201, offered.text
    result = client.post(f"/v1/actions/{offered.json()['id']}/approve", headers=OWNER)
    assert result.json()["state"] == "failed", result.text
    assert list(root.iterdir()) == []


def test_full_disk_and_unsigned_catalog_never_download(box, clock, monkeypatch):
    client, root, catalog = box

    def unexpected(_):
        raise AssertionError("refused requests cannot open a download")

    monkeypatch.setattr(map_packs, "_open_download", unexpected)
    monkeypatch.setattr(map_packs.MapPacks, "_usage", staticmethod(lambda _: Disk(1000, 900, 100)))
    response = request_pack(client, clock, "add", {"region_id": REGION_ID})
    assert response.status_code == 409 and response.json()["reason"] == "map_disk_reserve", response.text
    assert request_pack(client, clock, "add", {"region_id": REGION_ID, "url": "https://example.test"}).status_code == 422
    catalog.write_bytes(catalog.read_bytes() + b" ")
    response = request_pack(client, clock, "add", {"region_id": REGION_ID})
    assert response.status_code == 503 and response.json()["reason"] == "map_catalog_unavailable", response.text
    assert list(root.iterdir()) == []


def test_missing_key_keeps_the_configured_pack_volume_dormant(box, clock):
    client, root, catalog = box
    catalog.with_suffix(".pub").unlink()
    for response in (client.get("/v1/map/packs", headers=OWNER),
                     request_pack(client, clock, "add", {"region_id": REGION_ID}),
                     request_pack(client, clock, "remove", {"pack_id": REGION_ID})):
        assert response.status_code == 503 and response.json()["reason"] == "map_catalog_unavailable", response.text
    assert list(root.iterdir()) == []
