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
    """Approvals never shows a kit, so approving one there is refused before anything runs (Refs #1232: it used to say
    "succeeded" and hold a key nobody could read). A path past the route's guards fails in the handler instead."""
    bk.disk_key_source = storage = FakeStorage()

    p = client.app.state.gateway.tokens.lookup("dev-owner-token-change-me")
    action, _ = bk.gw.actions.request_feature(p, "backup.kit.issue", {}, idempotency_key="elsewhere",
                                              expires_at=clock.now + timedelta(minutes=10))
    r = client.post(f"/v1/actions/{action['id']}/approve", headers=OWNER)
    assert r.status_code == 409 and r.json()["reason"] == "kit_not_shown_here", r.text
    assert client.get(f"/v1/actions/{action['id']}", headers=OWNER).json()["state"] == "awaiting_approval"
    # an approval that skips the route's guards (as a standing approval would) issues nothing either
    assert bk.gw.actions.approve(p, action["id"])["state"] == "failed"
    assert storage.calls == [] and storage.key == DISK_KEY, "the disk key is taken only for an answer that shows it"
    assert bk._one_time == {} and not [k for k, _, _ in bk.agent.jobs if k == "backup.key.add"]
    assert client.get("/v1/backups/kit", headers=OWNER).json()["state"] == "missing", "no kit nobody saw"
    assert client.post("/v1/backups/kit", headers=OWNER).json()["one_time"]["disk_key"] == DISK_KEY


def test_a_kit_stopped_by_a_passkey_step_up_never_takes_the_disk_key_later(client, bk):
    """Review of #1191: with a passkey registered, POST /v1/backups/kit stops at the step-up. The action stays
    pending; approving it later in Approvals must not take the disk key (destroying onemindd's copy) into a one-time
    answer that no route returns."""
    bk.disk_key_source = storage = FakeStorage()
    client.app.state.identity.passkeys_active = lambda: True  # as if an owner had registered a passkey
    r = client.post("/v1/backups/kit", headers=OWNER)
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required", r.text
    assert bk._shown == set(), "the show mark ends with the request that set it"
    pending = [a for a in client.get("/v1/actions", headers=OWNER).json() if a["type"] == "backup.kit.issue"]
    assert [a["state"] for a in pending] == ["awaiting_approval"]
    assert r.json()["details"] == [{"action_id": pending[0]["id"]}], "the answer names the request to finish"
    client.app.state.identity.passkeys_active = lambda: False  # the approval passes its step-up elsewhere
    refused = client.post(f"/v1/actions/{pending[0]['id']}/approve", headers=OWNER)
    assert refused.status_code == 409 and refused.json()["reason"] == "kit_not_shown_here", refused.text
    assert storage.calls == [] and storage.key == DISK_KEY, "the disk key stays with onemindd"
    assert bk._one_time == {} and client.get("/v1/backups/kit", headers=OWNER).json()["state"] == "missing"
    assert client.post("/v1/backups/kit", headers=OWNER).json()["one_time"]["disk_key"] == DISK_KEY


def test_a_storage_failure_never_blocks_the_kit(client, bk):
    def broken():
        raise RuntimeError("socket gone")

    bk.disk_key_source = broken
    r = client.post("/v1/backups/kit", headers=OWNER)
    assert r.status_code == 201 and r.json()["one_time"]["disk_key_state"] == "not_available"


# ---- a box with an owner passkey (the lock-out found on a real hub, Refs #1232) -------------------------------
# A real gateway with identity on: the owner set up an account, registered a passkey, and signs in with it. The kit
# is approved with an assertion bound to its own action (approve-options), never with a bare session or token.
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from onemind_core.app import create_app  # noqa: E402
from test_backups import switch_on_backups  # noqa: E402
from test_identity import SoftAuthenticator, csrf, id_settings, new_session_client, register_passkey, setup_owner  # noqa: E402


@pytest.fixture
def pk_box(settings, clock, executor, notes_app):
    with TestClient(create_app(id_settings(settings), clock=clock, executor=executor)) as c:
        setup_owner(c)
        c.key = SoftAuthenticator()
        register_passkey(c, c.key)
        c.bk = switch_on_backups(c.app, clock)
        c.bk.disk_key_source = c.storage = FakeStorage()
        yield c


def passkey_session(box) -> TestClient:
    """A browser that has just signed in with the owner's passkey (as on the live hub)."""
    s = new_session_client(box)
    opts = s.post("/v1/auth/login/options").json()
    r = s.post("/v1/auth/login", json={"passkey": box.key.assert_(opts["publicKey"]["challenge"])})
    assert r.status_code == 200, r.text
    assert s.get("/v1/me").json()["session"]["auth_method"] == "passkey"
    return s


def kit_step_up(box, s) -> tuple[str, dict]:
    """POST /v1/backups/kit stops at the passkey step and names its action; sign that action's challenge."""
    r = s.post("/v1/backups/kit", headers=csrf(s))
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required", r.text
    [detail] = r.json()["details"]
    aid = detail["action_id"]
    opts = s.post(f"/v1/actions/{aid}/approve-options", headers=csrf(s))
    assert opts.status_code == 200, opts.text
    return aid, box.key.assert_(opts.json()["challenge"], flat=True)


def test_an_owner_signed_in_with_a_passkey_issues_the_kit_and_sees_it_exactly_once(pk_box, settings):
    s = passkey_session(pk_box)
    aid, assertion = kit_step_up(pk_box, s)
    assert pk_box.storage.calls == [], "nothing is taken before the passkey approves"
    r = s.post("/v1/backups/kit", headers=csrf(s), json={"action_id": aid, "webauthn": assertion})
    assert r.status_code == 201, r.text
    assert r.headers["Cache-Control"] == "no-store"
    one = r.json()["one_time"]
    assert one["disk_key"] == DISK_KEY and one["owner_key"] in one["text"] and DISK_KEY in one["text"]
    assert r.json()["action"]["id"] == aid and r.json()["action"]["state"] == "succeeded"
    assert pk_box.storage.calls == ["take"]
    # Exactly once: the same action (or the same assertion) never shows a key again.
    again = s.post("/v1/backups/kit", headers=csrf(s), json={"action_id": aid, "webauthn": assertion})
    assert again.status_code == 409 and "one_time" not in again.text, again.text
    assert DISK_KEY not in everything_but_the_kit(pk_box, settings)
    assert one["owner_key"] not in everything_but_the_kit(pk_box, settings)
    # The wizard can finish: the owner types two groups back.
    kit = s.get("/v1/backups/kit").json()
    answers = {str(i): one["groups"][i - 1] for i in kit["positions"]}
    assert s.post("/v1/backups/kit/confirm", headers=csrf(s), json={"answers": answers}).json()["state"] == "confirmed"


def test_a_kit_approved_with_a_passkey_in_approvals_takes_no_disk_key_and_replaces_no_kit(pk_box, settings):
    """Review of #1191, must-fix 1, with a real passkey: the shortcut stops at the step-up, then the owner approves the
    pending request in Approvals with a passkey. That answer shows nobody the kit, so it is refused before anything
    runs: onemindd keeps the disk key, the box keeps its old kit (no restic key nobody holds) and nothing is held."""
    s = passkey_session(pk_box)
    aid, assertion = kit_step_up(pk_box, s)
    assert pk_box.bk._shown == set(), "the show mark ends with the request that set it"
    r = s.post(f"/v1/actions/{aid}/approve", headers=csrf(s), json={"webauthn": assertion})
    assert r.status_code == 409 and r.json()["reason"] == "kit_not_shown_here", r.text
    assert pk_box.storage.calls == [] and pk_box.storage.key == DISK_KEY, "the disk key stays with onemindd"
    assert pk_box.bk._one_time == {}, "no kit is held in memory for an answer no route returns"
    assert s.get("/v1/backups/kit").json()["state"] == "missing"
    assert s.get(f"/v1/actions/{aid}").json()["state"] == "awaiting_approval"
    # The kit screen still finishes the same request, with a fresh challenge, and shows the disk key.
    opts = s.post(f"/v1/actions/{aid}/approve-options", headers=csrf(s)).json()
    done = s.post("/v1/backups/kit", headers=csrf(s),
                  json={"action_id": aid, "webauthn": pk_box.key.assert_(opts["challenge"], flat=True)})
    assert done.status_code == 201 and done.json()["one_time"]["disk_key"] == DISK_KEY, done.text
    assert pk_box.storage.calls == ["take"]


def test_the_kit_route_finishes_only_its_own_pending_kit_request(pk_box, clock):
    s = passkey_session(pk_box)
    # not a kit request: a destination waiting for approval
    dest = s.post("/v1/backups/destinations", headers=csrf(s),
                  json={"kind": "usb", "label": "USB disk", "config": {"usb_uuid": "1234-ABCD"}}).json()["id"]
    opts = s.post(f"/v1/actions/{dest}/approve-options", headers=csrf(s)).json()
    r = s.post("/v1/backups/kit", headers=csrf(s), json={"action_id": dest, "webauthn": pk_box.key.assert_(opts["challenge"], flat=True)})
    assert r.status_code == 409, r.text
    assert s.get(f"/v1/actions/{dest}").json()["state"] == "awaiting_approval"
    assert s.post("/v1/backups/kit", headers=csrf(s), json={"action_id": "nope", "webauthn": {}}).status_code == 404
    # a kit request filed by another principal (here the static owner token) is not finished by this session
    other = pk_box.post("/v1/backups/kit", headers=OWNER)
    assert other.status_code == 401, other.text
    theirs = other.json()["details"][0]["action_id"]
    opts = s.post(f"/v1/actions/{theirs}/approve-options", headers=csrf(s)).json()
    r = s.post("/v1/backups/kit", headers=csrf(s), json={"action_id": theirs, "webauthn": pk_box.key.assert_(opts["challenge"], flat=True)})
    assert r.status_code == 403, r.text
    # an assertion is required: a bare continuation is a step-up like any approval
    aid, _ = kit_step_up(pk_box, s)
    r = s.post("/v1/backups/kit", headers=csrf(s), json={"action_id": aid})
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required", r.text
    assert pk_box.storage.calls == [] and pk_box.bk._one_time == {}


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
