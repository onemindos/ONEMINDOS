# SPDX-License-Identifier: Apache-2.0
"""Send to (#612): the share type registry, POST /v1/share and per-object deep links.

Map and Work are not built-ins yet, so the hand-off is proven with the two real built-ins that accept
a file (Files opens it, Photos adds it) and refused for an app without the accept or the grant.
The Map place to Work task test follows when those apps land.
"""

from __future__ import annotations

import json

import pytest

from conftest import ADULT, AGENT, GUEST, OWNER
from files_support import audit_events
from onemind_core import builtins
from onemind_core.share import TYPES, deep_link

REF = "home:owner/Documents/tax return 2026.pdf"


@pytest.fixture
def gw(client):
    return client.app.state.gateway


def add_app(client, app_id: str, accepts: list[str], owns: list[str], verbs=("open", "add")) -> None:
    """A descriptor as builtins.load would give it, for an app that is not on the signed list yet."""
    spec = {"routes": {"owns": [], "calls": []}, "share": {"accepts": accepts, "verbs": list(verbs)},
            "backup": {"units": []}, "data": {"owns": owns, "reads": []}, "phone": {"entry": "none"}}
    client.app.state.builtins.descriptors[app_id] = builtins.Descriptor(app_id, app_id.title(), None, spec)


def send(client, to: str, type_="file", ref=REF, verb="add", who=OWNER, **extra):
    return client.post("/v1/share", headers=who, json={"to": to, "verb": verb, "object": {"type": type_, "ref": ref, **extra}})


def test_the_registry_is_the_descriptor_share_type_enum():
    schema = json.loads(builtins.REPO_SCHEMA.read_text())
    assert list(TYPES) == schema["$defs"]["shareType"]["enum"]
    classes = set(schema["$defs"]["dataClass"]["enum"])
    assert all(t.data_class in classes for t in TYPES.values())
    assert TYPES["place"].data_class == "location" and TYPES["file"].data_class == "private"


def test_types_route_lists_every_type(client):
    r = client.get("/v1/share/types", headers=AGENT)
    assert r.status_code == 200
    assert [t["name"] for t in r.json()["types"]] == list(TYPES)


def test_send_to_lists_files_and_photos_for_a_file(client):
    r = client.get("/v1/share/targets", params={"type": "file"}, headers=OWNER)
    assert r.status_code == 200
    assert r.json() == {"type": "file", "targets": [
        {"app_id": "files", "name": "Files", "verbs": ["open", "add"]},
        {"app_id": "photos", "name": "Photos", "verbs": ["add"]},
    ]}
    assert client.get("/v1/share/targets", params={"type": "place"}, headers=OWNER).json()["targets"] == []
    assert client.get("/v1/share/targets", params={"type": "parcel"}, headers=OWNER).status_code == 422


def test_a_file_shared_to_photos_is_handed_over(client, gw, settings):
    seen = []
    gw.events.subscribe("share.sent", seen.append)
    r = send(client, "photos")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["to"] == "photos" and body["verb"] == "add"
    assert body["object"] == {"type": "file", "ref": REF, "source": None}
    assert body["link"] == "onemind://photos/file/home%3Aowner%2FDocuments%2Ftax%20return%202026.pdf"
    assert [e["id"] for e in seen] == [body["id"]]
    assert seen[0]["subject"] == {"app_id": "photos"}
    assert seen[0]["data"] == {"to": "photos", "verb": "add", "type": "file", "ref": REF, "source": None,
                               "link": body["link"]}
    line = [e for e in audit_events(settings) if e["event"] == "share.sent"][-1]
    assert line["principal"]["id"] == "owner"


def test_files_opens_a_shared_file_from_photos(client):
    r = send(client, "files", verb="open", who=ADULT, source="photos")
    assert r.status_code == 201, r.text
    assert r.json()["object"]["source"] == "photos"


def test_an_app_without_the_accept_is_refused(client, settings):
    r = send(client, "settings")
    assert r.status_code == 409 and r.json()["reason"] == "type_not_accepted"
    r = send(client, "photos", verb="open")
    assert r.status_code == 409 and r.json()["reason"] == "verb_not_accepted"
    refused = [e for e in audit_events(settings) if e["event"] == "share.refused"]
    assert [e["data"]["reason"] for e in refused] == ["type_not_accepted", "verb_not_accepted"]
    assert not [e for e in audit_events(settings) if e["event"] == "share.sent"]


def test_an_app_without_the_grant_is_refused(client):
    add_app(client, "atlas", accepts=["place"], owns=["private"])
    add_app(client, "map", accepts=["place"], owns=["private", "location"])
    r = send(client, "atlas", type_="place", ref="plc_01")
    assert r.status_code == 409 and r.json()["reason"] == "no_grant"
    assert "location" in r.json()["message"]
    targets = client.get("/v1/share/targets", params={"type": "place"}, headers=OWNER).json()["targets"]
    assert [t["app_id"] for t in targets] == ["map"]
    assert send(client, "map", type_="place", ref="plc_01").status_code == 201


def test_a_switched_off_or_unknown_app_is_refused(client):
    client.app.state.builtins.disabled = lambda: frozenset({"photos"})
    r = send(client, "photos")
    assert r.status_code == 409 and r.json()["reason"] == "app_disabled"
    targets = client.get("/v1/share/targets", params={"type": "file"}, headers=OWNER).json()["targets"]
    assert [t["app_id"] for t in targets] == ["files"]
    assert send(client, "nope").status_code == 404
    assert send(client, "../files").status_code == 404


@pytest.mark.parametrize("who", [AGENT, GUEST])
def test_only_an_owner_or_adult_sends(client, settings, who):
    assert send(client, "photos", who=who).status_code == 403
    assert not [e for e in audit_events(settings) if e["event"] == "share.sent"]
    assert client.get("/v1/share/targets", params={"type": "file"}, headers=who).status_code == 200


def test_a_retried_send_with_the_same_key_hands_over_once(client, gw, clock):
    seen = []
    gw.events.subscribe("share.sent", seen.append)
    key = {**OWNER, "Idempotency-Key": "send-1"}
    first = send(client, "photos", who=key)
    assert first.status_code == 201 and "OneMind-Idempotent-Replay" not in first.headers
    again = send(client, "photos", who=key)
    assert again.status_code == 200 and again.headers["OneMind-Idempotent-Replay"] == "true"
    assert again.json() == first.json()
    assert len(seen) == 1
    other = send(client, "photos", who={**ADULT, "Idempotency-Key": "send-1"})  # another person: another key
    assert other.status_code == 201 and other.json()["id"] != first.json()["id"]
    r = send(client, "files", verb="open", who=key)
    assert r.status_code == 409 and r.json()["reason"] == "idempotency_mismatch"
    clock.advance(24 * 3600)
    assert send(client, "photos", who=key).status_code == 201  # kept for 24 hours
    assert len(seen) == 3


def test_a_key_never_lets_a_refused_sender_through(client, settings):
    assert send(client, "photos", who={**OWNER, "Idempotency-Key": "k"}).status_code == 201
    assert send(client, "photos", who={**AGENT, "Idempotency-Key": "k"}).status_code == 403
    assert send(client, "photos", who={**OWNER, "Idempotency-Key": ""}).status_code == 422


@pytest.mark.parametrize("bad", [
    {"to": "photos", "object": {"type": "parcel", "ref": "x"}},
    {"to": "photos", "object": {"type": "file", "ref": ""}},
    {"to": "photos", "object": {"type": "file", "ref": "a\nb"}},
    {"to": "photos", "object": {"type": "file", "ref": "x", "title": "content is never shared"}},
    {"to": "photos", "verb": "delete", "object": {"type": "file", "ref": "x"}},
])
def test_a_malformed_share_is_422(client, bad):
    assert client.post("/v1/share", headers=OWNER, json=bad).status_code == 422


def test_deep_links_keep_the_ref_in_one_segment():
    assert deep_link("files", "file", "shared/a/b.txt") == "onemind://files/file/shared%2Fa%2Fb.txt"
    assert deep_link("work", "task", "tsk_01") == "onemind://work/task/tsk_01"
