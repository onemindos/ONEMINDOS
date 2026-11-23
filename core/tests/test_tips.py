# SPDX-License-Identifier: Apache-2.0
"""The Tips built-in (#669): the image tips pack, served by role, with each person's dismiss state.

Acceptance: the role filter works, a dismiss survives a restart, a bad or too-new pack is ignored
and a switched-off Tips app answers 409.
"""

from __future__ import annotations

import base64
import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from conftest import ADULT, AGENT, GUEST, OWNER, make_client
from onemind_core import tips
from onemind_core.ledger import Base
from onemind_core.store import registered_schemas
from test_appstore import run

KEY = Ed25519PrivateKey.generate()
OTHER_KEY = Ed25519PrivateKey.generate()


def tip(tip_id: str, collection: str, **extra) -> dict:
    return {"id": tip_id, "title": tip_id.replace("-", " ").capitalize(), "collection": collection,
            "body": f"How to {tip_id}.", "opens": {"dashboard": "/", "phone": "onemind://home"}, "from": "0.1.0", **extra}


PACK = {
    "schema": "onemind.io/tips-pack/v1",
    "version": "2026.11.1",
    "os": {"from": "0.1.0"},
    "collections": [{"id": "getting-started", "title": "Getting started"},
                    {"id": "requests", "title": "Requests and activity"}],
    "checklist": ["start-on-home", "review-access"],
    "tips": [
        tip("start-on-home", "getting-started"),
        tip("review-access", "requests", roles=["owner"]),
        tip("read-heartbeat", "getting-started", roles=["owner", "adult"], skip_if_done=["node.joined"]),
        tip("future-tip", "getting-started", **{"from": "0.3.0"}),
        tip("old-tip", "getting-started", until="0.1.5"),
    ],
    "whats_new": [{"version": "0.2.0", "title": "New in 0.2", "body": "Tips arrived."},
                  {"version": "0.1.0", "title": "New in 0.1", "body": "First release."}],
}


def write_key(path: Path, signer: Ed25519PrivateKey = KEY) -> Path:
    path.write_bytes(signer.public_key().public_bytes(serialization.Encoding.PEM,
                                                    serialization.PublicFormat.SubjectPublicKeyInfo))
    return path


def write_pack(folder: Path, doc: dict, signer: Ed25519PrivateKey | None = KEY, data: bytes | None = None) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    data = json.dumps(doc).encode() if data is None else data
    (folder / "pack.json").write_bytes(data)
    if signer is not None:
        (folder / "pack.json.sig").write_text(base64.b64encode(signer.sign(data)).decode() + "\n")
    return folder


@pytest.fixture
def box(tmp_path):
    """An image layout: the pack folder, the public key and os-release saying ONEMIND_VERSION 0.2.0."""
    root = tmp_path / "image"
    root.mkdir()
    osr = root / "os-release"
    osr.write_text('ID=debian\nONEMIND_VERSION="0.2.0"\n')
    return {"dir": root / "tips", "key_file": write_key(root / "tips.pub"), "os_release": osr}


def with_tips(settings, box):
    return replace(settings, sections={**settings.sections, "tips": tips.TipsSettings(**box)})


@pytest.fixture
def tc(settings, clock, box):
    write_pack(box["dir"], PACK)
    with make_client(with_tips(settings, box), clock) as c:
        yield c


def ids(r) -> list[str]:
    assert r.status_code == 200, r.text
    return [t["id"] for t in r.json()["tips"]]


# ---- role filter -----------------------------------------------------------------------------------------

def test_each_role_sees_only_its_tips(tc):
    assert ids(tc.get("/v1/tips", headers=OWNER)) == ["start-on-home", "review-access", "read-heartbeat"]
    assert ids(tc.get("/v1/tips", headers=ADULT)) == ["start-on-home", "read-heartbeat"]
    assert ids(tc.get("/v1/tips", headers=GUEST)) == ["start-on-home"]


def test_a_tip_for_another_role_is_not_found(tc):
    assert tc.get("/v1/tips/review-access", headers=OWNER).status_code == 200
    for who in (ADULT, GUEST):
        r = tc.get("/v1/tips/review-access", headers=who)
        assert r.status_code == 404 and r.json()["error"] == "not_found"
        assert tc.post("/v1/tips/review-access/state", json={"state": "dismissed"}, headers=who).status_code == 404


def test_collections_and_checklist_follow_the_role(tc):
    owner = tc.get("/v1/tips/collections", headers=OWNER).json()
    guest = tc.get("/v1/tips/collections", headers=GUEST).json()
    assert owner["collections"] == [{"id": "getting-started", "title": "Getting started", "count": 2},
                                    {"id": "requests", "title": "Requests and activity", "count": 1}]
    assert owner["checklist"] == ["start-on-home", "review-access"]
    assert guest["collections"] == [{"id": "getting-started", "title": "Getting started", "count": 1}]
    assert guest["checklist"] == ["start-on-home"]
    assert ids(tc.get("/v1/tips?collection=requests", headers=OWNER)) == ["review-access"]


def test_tips_outside_the_running_os_version_are_hidden(tc):
    for tip_id in ("future-tip", "old-tip"):
        assert tc.get(f"/v1/tips/{tip_id}", headers=OWNER).status_code == 404


def test_a_tip_carries_its_text_links_and_pack(tc):
    r = tc.get("/v1/tips/read-heartbeat", headers=ADULT)
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Read heartbeat" and body["opens"] == {"dashboard": "/", "phone": "onemind://home"}
    assert body["skip_if_done"] == ["node.joined"] and body["state"] == "new"
    assert tc.get("/v1/tips", headers=OWNER).json()["pack"] == {"version": "2026.11.1", "source": "image"}


def test_whats_new_is_the_running_version(tc):
    r = tc.get("/v1/tips/whats-new", headers=GUEST)
    assert r.status_code == 200
    assert r.json() == {"os_version": "0.2.0", "entries": [{"version": "0.2.0", "title": "New in 0.2", "body": "Tips arrived."}]}


@pytest.mark.parametrize("who,status", [({}, 401), (AGENT, 403)])
def test_only_a_person_reads_tips(tc, who, status):
    for path in ("/v1/tips", "/v1/tips/collections", "/v1/tips/whats-new", "/v1/tips/start-on-home"):
        assert tc.get(path, headers=who).status_code == status, path
    assert tc.post("/v1/tips/start-on-home/state", json={"state": "done"}, headers=who).status_code == status


# ---- dismiss state ---------------------------------------------------------------------------------------

def test_a_dismiss_survives_a_restart_and_is_per_person(settings, clock, box):
    write_pack(box["dir"], PACK)
    s = with_tips(settings, box)
    with make_client(s, clock) as c:
        r = c.post("/v1/tips/start-on-home/state", json={"state": "dismissed"}, headers=OWNER)
        assert r.status_code == 200 and r.json()["state"] == "dismissed" and r.json()["tip_id"] == "start-on-home"
    with make_client(s, clock) as c:  # a new gateway process on the same database
        by_id = {t["id"]: t["state"] for t in c.get("/v1/tips", headers=OWNER).json()["tips"]}
        assert by_id["start-on-home"] == "dismissed" and by_id["review-access"] == "new"
        assert c.get("/v1/tips/start-on-home", headers=ADULT).json()["state"] == "new"
        assert c.post("/v1/tips/start-on-home/state", json={"state": "new"}, headers=OWNER).json()["state"] == "new"
        assert c.get("/v1/tips/start-on-home", headers=OWNER).json()["state"] == "new"


@pytest.mark.parametrize("body", [{"state": "deleted"}, {}, {"state": "done", "extra": 1}])
def test_a_bad_state_body_is_422(tc, body):
    assert tc.post("/v1/tips/start-on-home/state", json=body, headers=OWNER).status_code == 422


def test_state_of_an_unknown_tip_is_404(tc):
    assert tc.post("/v1/tips/no-such-tip/state", json={"state": "done"}, headers=OWNER).status_code == 404


# ---- a bad or too-new pack is ignored --------------------------------------------------------------------

def tampered(folder: Path) -> None:
    write_pack(folder, PACK)
    doc = copy.deepcopy(PACK)
    doc["tips"][0]["body"] = "Something the signer never wrote."
    (folder / "pack.json").write_text(json.dumps(doc))


BAD = {
    "tampered": tampered,
    "unsigned": lambda f: write_pack(f, PACK, signer=None),
    "other key": lambda f: write_pack(f, PACK, signer=OTHER_KEY),
    "too new": lambda f: write_pack(f, {**PACK, "os": {"from": "0.3.0"}}),
    "too old": lambda f: write_pack(f, {**PACK, "os": {"from": "0.1.0", "until": "0.1.9"}}),
    "not json": lambda f: write_pack(f, PACK, data=b"{not json"),
    "bad schema": lambda f: write_pack(f, {**PACK, "schema": "onemind.io/tips-pack/v9"}),
    "unknown collection": lambda f: write_pack(f, {**PACK, "tips": [tip("lost", "nowhere")]}),
    "duplicate id": lambda f: write_pack(f, {**PACK, "tips": [tip("a", "requests"), tip("a", "requests")]}),
    "reserved id": lambda f: write_pack(f, {**PACK, "tips": [tip("collections", "requests")], "checklist": []}),
    "checklist names a missing tip": lambda f: write_pack(f, {**PACK, "checklist": ["nope"]}),
}


@pytest.mark.parametrize("make", list(BAD.values()), ids=list(BAD))
def test_a_bad_or_too_new_pack_is_ignored(settings, clock, box, make):
    make(box["dir"])
    with make_client(with_tips(settings, box), clock) as c:
        r = c.get("/v1/tips", headers=OWNER)
        assert r.status_code == 200 and r.json() == {"pack": None, "tips": []}
        assert c.get("/v1/tips/collections", headers=OWNER).json() == {"collections": [], "checklist": []}
        assert c.get("/v1/tips/start-on-home", headers=OWNER).status_code == 404


def test_no_key_or_no_pack_serves_no_tips(settings, clock, box):
    write_pack(box["dir"], PACK)
    box["key_file"].unlink()
    with make_client(with_tips(settings, box), clock) as c:
        assert c.get("/v1/tips", headers=OWNER).json() == {"pack": None, "tips": []}
    with make_client(settings, clock) as c:  # the image default path, absent on a test machine
        assert c.get("/v1/tips", headers=OWNER).json() == {"pack": None, "tips": []}


def test_the_loader_falls_back_to_the_next_good_pack(tmp_path, box):
    """#790 will put a newer /data/tips pack ahead of the image pack: a refused one falls through."""
    key = tips.load_key(box["key_file"])
    newer = tmp_path / "data-tips"
    write_pack(newer, {**PACK, "version": "2026.12.1", "os": {"from": "0.3.0"}})
    write_pack(box["dir"], PACK)
    got = tips.load_first([("data", newer), ("image", box["dir"])], key, (0, 2, 0))
    assert got.source == "image" and got.pack.version == "2026.11.1"
    assert got.refused == [("data", "too_new")]
    none = tips.load_first([("data", newer)], key, (0, 2, 0))
    assert none.pack is None and none.source is None


def test_the_running_version_comes_from_os_release(tmp_path):
    osr = tmp_path / "os-release"
    osr.write_text('ONEMIND_VERSION="0.1.20261112025704"\n')
    assert tips.running_version(osr) == (0, 1, 20261112025704)
    osr.write_text("ID=debian\n")
    assert tips.running_version(osr) == tips.running_version(tmp_path / "missing")


# ---- switched off: 409 from the one gate --------------------------------------------------------------------

def test_a_switched_off_tips_app_answers_409(tc, clock):
    assert run(tc, clock, "app.disable", {"app_id": "tips"}).json()["state"] == "succeeded"
    for method, path in (("GET", "/v1/tips"), ("GET", "/v1/tips/start-on-home"), ("GET", "/v1/tips/collections"),
                         ("GET", "/v1/tips/whats-new"), ("POST", "/v1/tips/start-on-home/state")):
        r = tc.request(method, path, headers=OWNER, json={"state": "done"} if method == "POST" else None)
        assert r.status_code == 409 and r.json()["reason"] == "app_disabled", (method, path, r.text)
    assert run(tc, clock, "app.enable", {"app_id": "tips"}).json()["state"] == "succeeded"
    assert ids(tc.get("/v1/tips", headers=OWNER))


def test_the_descriptor_backs_up_the_dismiss_state(tc):
    out = tc.get("/v1/builtins", headers=OWNER).json()
    assert "tips" in {a["id"] for a in out["apps"]}
    assert {"app_id": "tips", "kind": "table", "name": "tips_state"} in out["backup_units"]
    assert "tips" in {s.feature for s in registered_schemas()}
    assert [t for t in Base.metadata.tables if t.startswith("tips")] == ["tips_state"]
