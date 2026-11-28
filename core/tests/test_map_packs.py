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


def signed_catalog(tmp_path):
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
    return catalog, public


@pytest.fixture
def box(settings, clock, tmp_path, monkeypatch):
    root = tmp_path / "packs"
    root.mkdir()
    catalog, public = signed_catalog(tmp_path)
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


def _installed_pack(root, pack_id=REGION_ID):
    folder = root / pack_id
    folder.mkdir()
    (folder / "archive.pmtiles").write_bytes(ARCHIVE)
    (folder / "pack.json").write_text(json.dumps({
        "id": pack_id, "region": "Test Region", "bytes": len(ARCHIVE),
        "sha256": hashlib.sha256(ARCHIVE).hexdigest(), "installed_at": "2026-11-01T00:00:00Z",
    }))


@pytest.mark.parametrize("missing", ["key", "catalog", "unset"])
def test_box_without_a_region_catalog_lists_and_removes_but_refuses_add(settings, clock, tmp_path, monkeypatch,
                                                                       missing):
    # A fresh hub ships neither the signed region catalogue nor its key (first boot only points at
    # them). Not set up is a state the owner can change, never a 503: installed packs stay listed and
    # removable, and adding one is a 409 that names why. No download is ever attempted.
    root = tmp_path / "packs"
    root.mkdir()
    catalog, key = signed_catalog(tmp_path)
    monkeypatch.setattr(map_packs.MapPacks, "_usage", staticmethod(lambda _: Disk(1000, 0, 1000)))
    monkeypatch.setattr(map_packs, "_open_download", lambda _: pytest.fail("no catalogue, no download"))
    if missing == "key":
        key.unlink()
    elif missing == "catalog":
        catalog.unlink()
    sections = {**settings.sections, "map": MapSettings(root, None if missing == "unset" else catalog, key)}
    _installed_pack(root)
    with make_client(settings, clock, sections=sections) as fresh:
        fresh.app.state.actions.spawn = lambda fn: fn()
        listed = fresh.get("/v1/map/packs", headers=OWNER)
        assert listed.status_code == 200, listed.text
        assert [p["id"] for p in listed.json()["packs"]] == [REGION_ID]
        refused = request_pack(fresh, clock, "add", {"region_id": "other-region"})
        assert refused.status_code == 409, refused.text
        assert refused.json()["reason"] == "map_catalog_not_configured", refused.text
        offered = request_pack(fresh, clock, "remove", {"pack_id": REGION_ID})
        assert offered.status_code == 201, offered.text
        done = fresh.post(f"/v1/actions/{offered.json()['id']}/approve", headers=OWNER)
        assert done.json()["state"] == "succeeded", done.text
        assert list(root.iterdir()) == []
        assert fresh.get("/v1/map/packs", headers=OWNER).json()["packs"] == []


def test_present_key_with_a_bad_signature_is_still_unavailable(box, clock):
    # A catalogue and key that exist but do not verify are a real fault on the box: 503, no install.
    client, root, catalog = box
    catalog.with_suffix(".json.sig").write_bytes(b"AAAA")
    response = request_pack(client, clock, "add", {"region_id": REGION_ID})
    assert response.status_code == 503 and response.json()["reason"] == "map_catalog_unavailable", response.text
    assert client.get("/v1/map/packs", headers=OWNER).status_code == 200
    assert list(root.iterdir()) == []


def test_box_without_offline_maps_lists_nothing_and_refuses_with_a_reason(settings, clock):
    # api-fuzz run 45729613634: GET /v1/map/packs answered 503 on a box with no packs volume configured.
    # Not set up is a state the owner can change, not a server fault: the list is empty and a pack
    # request is a 409 that names why.
    with make_client(settings, clock) as client:
        listed = client.get("/v1/map/packs", headers=AGENT)
        assert listed.status_code == 200, listed.text
        assert listed.json() == {"packs": [], "free_bytes": None}
        for kind, params in (("add", {"region_id": REGION_ID}), ("remove", {"pack_id": REGION_ID})):
            refused = request_pack(client, clock, kind, params)
            assert refused.status_code == 409, refused.text
            assert refused.json()["reason"] == "map_storage_not_configured", refused.text


def test_configured_volume_that_did_not_mount_is_still_unavailable(settings, clock, tmp_path):
    # A configured path that is missing (or a symlink) is a real fault on the box and stays 503.
    sections = {**settings.sections, "map": MapSettings(tmp_path / "absent", None)}
    with make_client(settings, clock, sections=sections) as client:
        response = client.get("/v1/map/packs", headers=OWNER)
        assert response.status_code == 503, response.text
        assert response.json()["reason"] == "map_storage_unavailable", response.text
