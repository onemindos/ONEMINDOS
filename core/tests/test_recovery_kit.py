# SPDX-License-Identifier: Apache-2.0
"""Design 25a (gateway permissions design 3.13, D-020): an emergency kit for every owner, with the disk key in it.

- A box with no backup destination still gets a kit; destinations added later get the owner key by typing it back
  (POST /v1/backups/kit/attach), never because the box kept a copy.
- When /data is encrypted, the kit takes the disk recovery key from onemindd once and prints it. It is in the kit's
  one-time answer and nowhere else: not the database, the ledger, the audit log or an event.
- A re-issue only adds a key (backup.key.add), so snapshots the old kit opens stay openable.
"""

from __future__ import annotations

import json
from datetime import timedelta

from onemind_core.backups.kit import kit_text, new_owner_key

from conftest import ADULT, OWNER
from test_backups import add_usb, approve, bk, notes_app  # noqa: F401  (fixtures)

DISK_KEY = "cbdefghi-jklnrtuv-cbdefghi-jklnrtuv-cbdefghi-jklnrtuv-cbdefghi-jklnrtuv"


class FakeStorage:
    """onemindd storage serve: a pending /data recovery key that can be taken once."""

    def __init__(self, key: str | None = DISK_KEY, encrypted: bool = True):
        self.key, self.encrypted, self.calls = key, encrypted, []

    def __call__(self):
        self.calls.append("take")
        if not self.encrypted:
            return "not_encrypted", None
        key, self.key = self.key, None
        return ("included", key) if key else ("not_available", None)


def add_second(client):
    r = client.post("/v1/backups/destinations", headers=OWNER,
                    json={"kind": "usb", "label": "Second disk", "config": {"usb_uuid": "5678-EF01"}})
    assert r.status_code == 202, r.text
    return approve(client, r.json()["id"])


def everything_but_the_kit(client, settings) -> str:
    blobs = [json.dumps(client.get("/v1/actions", headers=OWNER).json()), settings.audit_path.read_text(),
             json.dumps(client.get("/v1/backups/kit", headers=OWNER).json())]
    if settings.db_url.startswith("sqlite:///"):
        blobs.append(open(settings.db_url[len("sqlite:///"):], "rb").read().decode("latin-1"))
    return "\n".join(blobs)


def test_a_box_without_a_destination_gets_a_kit_with_the_disk_key(client, bk, settings):
    bk.disk_key_source = storage = FakeStorage()
    r = client.post("/v1/backups/kit", headers=OWNER)
    assert r.status_code == 201, r.text
    one = r.json()["one_time"]
    assert one["disk_key"] == DISK_KEY and one["disk_key_state"] == "included"
    assert DISK_KEY in one["text"] and one["owner_key"] in one["text"]
    assert not [k for k, _, _ in bk.agent.jobs if k == "backup.key.add"], "no destination: nothing to add the key to"
    kit = client.get("/v1/backups/kit", headers=OWNER).json()
    assert kit["state"] == "issued" and kit["disk_key"] == "included" and kit["missing_on"] == []
    assert storage.calls == ["take"]
    # The disk key is in the one-time answer only.
    assert DISK_KEY not in everything_but_the_kit(client, settings)


def test_a_destination_added_later_gets_the_owner_key_by_typing_it_back(client, bk, settings):
    one = client.post("/v1/backups/kit", headers=OWNER).json()["one_time"]
    add_usb(client, bk)
    kit = client.get("/v1/backups/kit", headers=OWNER).json()
    assert kit["missing_on"] == [d["id"] for d in client.get("/v1/backups/destinations", headers=OWNER).json()]
    assert len(kit["missing_on"]) == 1
    body = {"groups": one["groups"], "check": one["check"]}
    assert client.post("/v1/backups/kit/attach", headers=ADULT, json=body).status_code == 403
    wrong = dict(body, groups=list(reversed(one["groups"])))
    assert client.post("/v1/backups/kit/attach", headers=OWNER, json=wrong).status_code == 422, "the check group catches typos"
    other = new_owner_key()
    r = client.post("/v1/backups/kit/attach", headers=OWNER, json={"groups": list(other.groups), "check": other.check})
    assert r.status_code == 409, "a well-formed key of another kit is refused"
    r = client.post("/v1/backups/kit/attach", headers=OWNER, json=body)
    assert r.status_code == 200, r.text
    assert r.json()["action"]["state"] == "succeeded" and r.json()["kit"]["missing_on"] == []
    kind, params, _ = bk.agent.jobs[-1]
    assert kind == "backup.key.add" and params["target_ids"] == kit["missing_on"] and params["key"] == one["owner_key"]
    # a second destination: only it gets the key
    add_second(client)
    missing = client.get("/v1/backups/kit", headers=OWNER).json()["missing_on"]
    assert len(missing) == 1 and missing != kit["missing_on"]
    client.post("/v1/backups/kit/attach", headers=OWNER, json=body)
    assert bk.agent.jobs[-1][1]["target_ids"] == missing
    assert one["owner_key"] not in everything_but_the_kit(client, settings)


def test_a_reissue_only_adds_a_key_and_remembers_the_disk_key_was_printed(client, bk):
    add_usb(client, bk)
    bk.disk_key_source = FakeStorage()
    first = client.post("/v1/backups/kit", headers=OWNER).json()["one_time"]
    second = client.post("/v1/backups/kit", headers=OWNER)
    assert second.status_code == 201, second.text
    two = second.json()["one_time"]
    keys = [(k, p["key"]) for k, p, _ in bk.agent.jobs if k.startswith("backup.key")]
    assert keys == [("backup.key.add", first["owner_key"]), ("backup.key.add", two["owner_key"])], \
        "a re-issue adds the new key and removes nothing: old snapshots stay openable with the first kit"
    assert two["disk_key"] is None and two["disk_key_state"] == "earlier_kit"
    assert "earlier kit" in two["text"] and DISK_KEY not in two["text"]
    assert client.get("/v1/backups/kit", headers=OWNER).json()["disk_key"] == "earlier_kit"


def test_kit_text_says_what_happened_to_the_disk_key():
    key = new_owner_key()
    import datetime as dt
    now = dt.datetime(2026, 11, 25, tzinfo=dt.UTC)
    plain = kit_text(box_name="b", instance_id="i", key=key, destinations=[], issued_at=now, disk_key_state="not_encrypted")
    assert "not encrypted" in plain and "none yet" in plain
    missing = kit_text(box_name="b", instance_id="i", key=key, destinations=[], issued_at=now, disk_key_state="not_available")
    assert "could not be added" in missing


def test_a_kit_approved_where_nobody_sees_it_leaves_the_disk_key_alone(client, bk, clock):
    bk.disk_key_source = storage = FakeStorage()

    p = client.app.state.gateway.tokens.lookup("dev-owner-token-change-me")
    action, _ = bk.gw.actions.request_feature(p, "backup.kit.issue", {}, idempotency_key="elsewhere",
                                              expires_at=clock.now + timedelta(minutes=10))
    assert approve(client, action["id"])["state"] == "succeeded"
    assert storage.calls == [] and storage.key == DISK_KEY, "the disk key is taken only for an answer that shows it"
    assert client.get("/v1/backups/kit", headers=OWNER).json()["disk_key"] == "not_available"
    assert client.post("/v1/backups/kit", headers=OWNER).json()["one_time"]["disk_key"] == DISK_KEY


def test_a_storage_failure_never_blocks_the_kit(client, bk):
    def broken():
        raise RuntimeError("socket gone")

    bk.disk_key_source = broken
    r = client.post("/v1/backups/kit", headers=OWNER)
    assert r.status_code == 201 and r.json()["one_time"]["disk_key_state"] == "not_available"


# ---- the storage side: onemindd hands the disk key to the kit once, the general route stays off -------------
from test_storage import booted, no_poller, node  # noqa: E402,F401  (fixtures of the storage tests)


def test_the_storage_service_hands_the_disk_key_to_the_kit_once(settings, clock, node, no_poller):
    with booted(settings, clock, node) as c:
        source = c.app.state.backups.disk_key_source
        assert source == c.app.state.storage.kit_disk_key, "routers/storage.py wires the kit to onemindd"
        assert source() == ("included", "FAKE-RECOVERY-KEY-FOR-TESTS-ONLY")
        assert node.recovery_key is None, "onemindd destroyed its copy"
        assert source() == ("not_available", None), "shown once"
        assert c.post("/v1/storage/recovery-key", headers=OWNER).status_code == 404, "the general route stays off (N-4)"
        node.mirror = {"encrypted": False}
        assert source() == ("not_encrypted", None)
