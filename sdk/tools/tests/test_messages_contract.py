# SPDX-License-Identifier: Apache-2.0
"""The Messages contract on MeshCore (issue #855): schemas, signed radio jobs, ids-only events, the import
body, the subject tree, the action specs and the built-in descriptor. The shared MeshCore frame and guard
vectors have their own test (test_meshcore_vectors.py).

Must refuse: a subject an app or agent could publish to make a radio transmit; text in any event; an
RF-setting job kind; transport lora-mt (Meshtastic) in 1.0.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_DIR = ROOT / "sdk" / "schema"
MESSAGES = ROOT / "core" / "onemind_core" / "messages"
sys.path.insert(0, str(ROOT / "core"))
from onemind_core import subjects  # noqa: E402
from onemind_core.audit import AuditLog  # noqa: E402
from onemind_core.events import EventHub  # noqa: E402

RF_WORDS = ("freq", "bw", "bandwidth", "sf", "spreading", "cr", "coding", "power", "dbm", "preset", "region_code")
UUID = "6f1c9e0a-1b2c-4d3e-8f40-5a6b7c8d9e0f"
REF = "sec_" + "x" * 10  # a secret-store reference, never a secret


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def validator(name: str, ref: str | None = None) -> Draft202012Validator:
    schema = load(SCHEMA_DIR / name)
    if ref:
        schema = {"$defs": schema["$defs"], "$ref": f"#/$defs/{ref}"}
    return Draft202012Validator(schema, format_checker=FormatChecker())


def errors(v: Draft202012Validator, obj: object) -> list[str]:
    return [e.message for e in v.iter_errors(obj)]


def walk_keys(obj, out=None) -> set[str]:
    out = set() if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "properties" and isinstance(v, dict):
                out.update(v)
            walk_keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            walk_keys(v, out)
    return out


def message(**changes) -> dict:
    m = {"schema": "onemind.message/v1", "id": "msg_01JABCDEFG", "thread_id": "thr_01JABCDEFG", "direction": "out",
         "kind": "direct", "transport": "lora-mc", "origin": "hub", "peer": "ctc_01JABCDEFG", "channel_index": None,
         "text": "hello", "sender_ts": 1234567890, "rx_at": None, "snr_db": None, "path_len": None, "attempts": 1,
         "state": "acked", "action_id": UUID, "reason": None}
    return {**m, **changes}


def job(kind: str, params: dict, action_id: str | None = UUID) -> dict:
    return {"schema": "onemind.job/v1", "job_id": "job_0123456789abcdef", "action_id": action_id, "kind": kind,
            "params": params, "params_sha256": "sha256:" + "0" * 64, "issued_at": "2026-11-22T10:00:00Z",
            "expires_at": "2026-11-22T10:10:00Z", "sig": "c2ln"}


SEND = {"action_id": UUID, "kind": "direct", "to": "a1b2c3d4e5f6", "text": "hello", "max_attempts": 3}


class MessageSchema(unittest.TestCase):
    v = validator("onemind.message.schema.json")

    def test_valid_direct_channel_and_inbound_messages(self):
        self.assertEqual(errors(self.v, message()), [])
        self.assertEqual(errors(self.v, message(kind="channel", peer=None, channel_index=1, state="sent")), [])
        inbound = message(direction="in", state=None, action_id=None, attempts=0, rx_at="2026-11-22T10:00:00Z",
                          snr_db=-7.25, path_len=2, origin="phone-direct")
        self.assertEqual(errors(self.v, inbound), [])

    def test_text_over_the_lora_mc_cap_is_refused(self):
        self.assertEqual(errors(self.v, message(text="x" * 160)), [])
        self.assertTrue(errors(self.v, message(text="x" * 161)))

    def test_meshtastic_transport_unknown_state_and_acked_channel_are_refused(self):
        self.assertTrue(errors(self.v, message(transport="lora-mt")))
        self.assertTrue(errors(self.v, message(state="delivered")))
        self.assertTrue(errors(self.v, message(kind="channel", peer=None, channel_index=0, state="acked")))
        self.assertTrue(errors(self.v, message(kind="channel", channel_index=0)))  # a channel message names no peer
        self.assertTrue(errors(self.v, message(direction="in", rx_at="2026-11-22T10:00:00Z", attempts=0)))  # inbound has no state


class RadioStatusSchema(unittest.TestCase):
    v = validator("onemind.radio.status.schema.json")
    ok = {"schema": "onemind.radio.status/v1", "radio_id": "rad_01JABCDEFG", "transport": "lora-mc", "model": "Elecrow ThinkNode M2",
          "firmware": "v1.18.0", "freq_mhz": 910.525, "bw_khz": 62.5, "sf": 7, "cr": 5, "tx_power_dbm": 19, "max_tx_power_dbm": 22,
          "battery_mv": 4100, "name": "OneMind Hub", "public_key": "opaque-id", "read_at": "2026-11-22T10:00:00Z"}

    def test_physical_units_only(self):
        self.assertEqual(errors(self.v, self.ok), [])
        self.assertTrue(errors(self.v, {**self.ok, "cr": 4}))
        self.assertTrue(errors(self.v, {**self.ok, "region": "US"}))  # no vendor region tables
        self.assertTrue(errors(self.v, {k: v for k, v in self.ok.items() if k != "freq_mhz"}))


class LoraJobs(unittest.TestCase):
    v = validator("onemind.job.lora.schema.json")

    def test_the_five_job_kinds_validate(self):
        for j in (job("lora.inbox", {"after": None}, None), job("lora.status", {}, None), job("lora.send", SEND),
                  job("lora.send", {"action_id": UUID, "kind": "channel", "channel_index": 1, "text": "hi", "max_attempts": 1}),
                  job("lora.advert", {"action_id": UUID, "scope": "zero_hop"}),
                  job("lora.channel.set", {"action_id": UUID, "index": 1, "name": "family", "secret_ref": REF})):
            self.assertEqual(errors(self.v, j), [], j["kind"])

    def test_rf_settings_unknown_kinds_and_unapproved_sends_are_refused(self):
        self.assertTrue(errors(self.v, job("lora.radio.set", {"freq_mhz": 910})))
        self.assertTrue(errors(self.v, job("lora.send", {**SEND, "tx_power_dbm": 30})))
        self.assertTrue(errors(self.v, job("lora.send", SEND, None)))                 # a send carries its approved action
        self.assertTrue(errors(self.v, job("lora.send", {**SEND, "max_attempts": 4})))
        self.assertTrue(errors(self.v, job("lora.send", {**SEND, "kind": "channel", "channel_index": 1})))  # channel names no contact
        self.assertTrue(errors(self.v, job("lora.advert", {"action_id": UUID, "scope": "flood"})))
        self.assertTrue(errors(self.v, job("lora.channel.set", {"action_id": UUID, "index": 1, "name": "x", "secret_ref": REF,
                                                                 "secret": "00" * 16})))
        self.assertTrue(errors(self.v, job("lora.inbox", {"after": None})))           # a read files no action
        schema = load(SCHEMA_DIR / "onemind.job.lora.schema.json")
        params = {k: walk_keys(schema["$defs"][k]) for k in ("inbox", "status", "send", "advert", "channel_set")}
        for kind, keys in params.items():
            self.assertFalse({k for k in keys if any(w == k or k.startswith(w + "_") for w in RF_WORDS)}, kind)

    def test_job_results(self):
        send = validator("onemind.job.lora.schema.json", "result_send")
        for r in ({"state": "sent", "expected_ack": 287454020, "est_timeout_ms": 5000}, {"state": "sent", "expected_ack": None, "est_timeout_ms": 0},
                  {"state": "acked", "trip_ms": 1200}, {"state": "failed", "reason": "out_of_band"}):
            self.assertEqual(errors(send, r), [], r)
        self.assertTrue(errors(send, {"state": "failed", "reason": "The radio said no"}))
        inbox = validator("onemind.job.lora.schema.json", "result_inbox")
        reply = {"state": "succeeded", "next": "c42", "more": False, "acks": [{"expected_ack": 1, "trip_ms": 900}],
                 "messages": [{"kind": "direct", "from": "a1b2c3d4e5f6", "text": "Hi", "sender_ts": 1234567890,
                               "rx_at": "2026-11-22T10:00:00Z", "snr_db": -7.25, "path_len": 2}]}
        self.assertEqual(errors(inbox, reply), [])
        reply["messages"][0].pop("from")
        self.assertTrue(errors(inbox, reply))


def event(type_: str, data: dict) -> dict:
    return {"schema": "onemind.event/v1", "id": "evt_1", "type": type_, "ts": "2026-11-22T10:00:00Z",
            "subject": {"message_id": "msg_01JABCDEFG"}, "data": data}


RECEIVED = {"message_id": "msg_01JABCDEFG", "thread_id": "thr_01JABCDEFG", "kind": "direct", "transport": "lora-mc", "origin": "hub"}
STATUS = {"message_id": "msg_01JABCDEFG", "thread_id": "thr_01JABCDEFG", "action_id": UUID, "state": "acked", "attempts": 1}


def gateway_event(name: str, data: dict, **kw) -> dict:
    """The envelope exactly as the gateway's only publish path (EventHub.publish_event) puts it on NATS."""
    clock = lambda: datetime(2026, 11, 22, 10, tzinfo=timezone.utc)  # noqa: E731
    sent: list[tuple[str, bytes]] = []
    with tempfile.TemporaryDirectory() as tmp:
        hub = EventHub(AuditLog(Path(tmp) / "audit.jsonl", clock), clock, lambda s, b: sent.append((s, b)), "inst_01JABCDEFG")
        hub.publish_event("message", name, data, principal={"id": "agent:hermes"}, **kw)
    assert [s for s, _ in sent] == [f"onemind.event.message.{name}"], sent
    return json.loads(sent[0][1])


def leaks(ok: dict) -> list[tuple[str, dict]]:
    """Ways text could ride a valid message event outside data: every one must be refused."""
    out = []
    for where, change in (("top-level text", {"text": "hello"}), ("text in resource", {"resource": {"kind": "message", "id": "msg_01JABCDEFG", "text": "hello"}}),
                          ("resource as a bag", {"resource": {"text": "hello"}}), ("text in subject", {"subject": {**ok["subject"], "text": "hello"}}),
                          ("peer in subject", {"subject": {"peer_id": "a1b2c3d4e5f6"}}), ("another resource kind", {"resource": {"kind": "contact", "id": "ctc_01JABCDEFG"}}),
                          ("text in an id field", {"dedupe_key": "see you at noon"}), ("text in source_id", {"source_id": "meet me at the gate"}),
                          # format date-time is only enforced when rfc3339-validator is installed; the pattern must refuse text without it
                          ("text in ts", {"ts": "meet me at the gate"}), ("text in observed_at", {"observed_at": "meet me at the gate"}),
                          ("text in occurred_at", {"occurred_at": "meet me at the gate"}), ("one word in ts", {"ts": "hello"}),
                          ("text after a time", {"occurred_at": "2026-11-22T10:00:00Z meet me at the gate"})):
        out.append((where, {**ok, **change}))
    return out


class EventsAndImport(unittest.TestCase):
    v = validator("onemind.message.event.schema.json")

    def test_the_gateway_publisher_shape_validates(self):
        # message.status for an approved send: publish_event writes subject.action_id and correlation_id from the action.
        cases = (gateway_event("status", STATUS, action_id=UUID, resource={"kind": "message", "id": "msg_01JABCDEFG"}),
                 gateway_event("status", {**STATUS, "state": "failed", "reason": "no_ack", "action_id": None}, severity="warning"),
                 gateway_event("received", RECEIVED, resource={"kind": "thread", "id": "thr_01JABCDEFG"}, dedupe_key="a1b2c3d4e5f6:1234567890:" + "0" * 64),
                 gateway_event("received", RECEIVED))
        for env in cases:
            self.assertEqual(errors(self.v, env), [], env)
        self.assertEqual(cases[0]["subject"], {"action_id": UUID, "message_id": "msg_01JABCDEFG"})
        self.assertEqual(cases[2]["subject"], {"thread_id": "thr_01JABCDEFG"})
        for where, bad in leaks(cases[0]):
            self.assertTrue(errors(self.v, bad), where)
        for when in ({"observed_at": None, "occurred_at": None}, {"ts": "2026-11-22T10:00:00.123456+00:00"}):
            self.assertEqual(errors(self.v, {**cases[0], **when}), [], when)
        self.assertTrue(errors(self.v, gateway_event("status", STATUS, action_id="not-a-uuid")))

    def test_events_carry_ids_and_metadata_never_text(self):
        received, status = RECEIVED, STATUS
        self.assertEqual(errors(self.v, event("message.received", received)), [])
        self.assertEqual(errors(self.v, event("message.status", status)), [])
        for leak in ({"text": "hello"}, {"peer": "a1b2c3d4e5f6"}, {"public_key": "x"}):
            self.assertTrue(errors(self.v, event("message.received", {**received, **leak})), leak)
            self.assertTrue(errors(self.v, event("message.status", {**status, **leak})), leak)
        self.assertTrue(errors(self.v, event("message.sent", status)))

    def test_import_body_and_its_dedupe_key(self):
        imp = validator("onemind.message.import.schema.json")
        item = {"direction": "in", "kind": "direct", "sender": "a1b2c3d4e5f6", "peer": "a1b2c3d4e5f6", "sender_ts": 1234567890, "text": "Hi"}
        body = {"radio": "0f0e0d0c0b0a", "messages": [item, {"direction": "out", "kind": "channel", "sender": "ch1", "channel_index": 1,
                                                             "sender_ts": 1234567891, "text": "hi all", "state": "sent"}]}
        self.assertEqual(errors(imp, body), [])
        self.assertTrue(errors(imp, {**body, "messages": [item] * 501}))
        self.assertTrue(errors(imp, {**body, "messages": [{**item, "kind": "channel", "channel_index": 1, "state": "acked"}]}))
        self.assertTrue(errors(imp, {**body, "messages": [{**item, "transport": "lora-mt"}]}))
        key = load(SCHEMA_DIR / "onemind.message.import.schema.json")["$defs"]["dedupe_key"]
        ex = key["examples"][0]
        self.assertEqual(ex["key"], f"{ex['sender']}:{ex['sender_ts']}:{hashlib.sha256(ex['text'].encode()).hexdigest()}")
        self.assertEqual(errors(Draft202012Validator(key), ex["key"]), [])


class SubjectTree(unittest.TestCase):
    reg = subjects.load(SCHEMA_DIR / subjects.REGISTRY_FILE)
    NEW = ("onemind.event.message.received", "onemind.event.message.status")

    def test_the_new_event_subjects_are_gateway_only(self):
        for s in self.NEW:
            p = self.reg.pattern_for(s)
            self.assertEqual((p.text, p.publishers, p.envelope), (s, ("gateway",), "onemind.message.event/v1"))
            self.assertTrue(self.reg.check(s, "gateway").ok)
            for who, own in (("app", "messages"), ("agent", "hermes"), ("node", "hub1")):
                self.assertFalse(self.reg.check(s, who, own).ok, (s, who))

    def test_nothing_new_under_cmd_and_no_subject_makes_a_radio_transmit(self):
        for kind in ("cmd", "lora", "radio", "message"):
            self.assertIn(kind, self.reg.reserved)
            self.assertNotIn(kind, self.reg.kinds)
        for s in ("onemind.cmd.lora.send", "onemind.lora.hub.send", "onemind.radio.rad_1.advert", "onemind.message.thr_1.text"):
            for who in ("gateway", "app", "agent", "node"):
                self.assertFalse(self.reg.check(s, who, "x").ok, (s, who))
        for p in self.reg.patterns:  # an app or agent may only publish its own plugin or request subjects
            if {"app", "agent"} & set(p.publishers):
                self.assertIn(p.kind, ("plugin", "request"), p.text)

    def test_no_subject_carries_text(self):
        for env_id, spec in self.reg.raw["envelopes"].items():
            if "file" in spec:
                self.assertNotIn("text", walk_keys(load(SCHEMA_DIR / spec["file"])), env_id)
        ok = event("message.status", {"message_id": "msg_01JABCDEFG", "thread_id": "thr_01JABCDEFG",
                                                            "state": "sent", "attempts": 1})
        self.assertEqual(self.reg.envelope_problems("onemind.message.event/v1", ok), [])
        leak = copy.deepcopy(ok)
        leak["data"]["text"] = "hello"
        self.assertTrue(self.reg.envelope_problems("onemind.message.event/v1", leak))
        # A property named text is not the only way in: the registry must refuse text anywhere in the envelope.
        for where, bad in leaks(ok):
            self.assertTrue(self.reg.envelope_problems("onemind.message.event/v1", bad), where)
        gw = gateway_event("status", STATUS, action_id=UUID, resource={"kind": "message", "id": "msg_01JABCDEFG"})
        self.assertEqual(self.reg.envelope_problems("onemind.message.event/v1", gw), [])

    def test_subject_lint_knows_the_message_events_and_refuses_radio_kinds(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "svc").mkdir()
            (Path(tmp) / "svc" / "ok.py").write_text('MESSAGE_SUBJECT = "onemind.event.message.received"\n')
            (Path(tmp) / "svc" / "bad.go").write_text('nc.Publish("onemind.lora.hub.send", b)\n')
            r = subprocess.run([sys.executable, "-I", str(ROOT / "sdk" / "tools" / "subject-lint"), "--root", tmp, "svc"],
                               capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("kind 'lora' is reserved", r.stdout)
        self.assertNotIn("ok.py", r.stdout)


class ActionsAndDescriptor(unittest.TestCase):
    actions = load(MESSAGES / "actions.json")["actions"]
    doc = yaml.safe_load((MESSAGES / "onemind.app.yaml").read_text())

    def test_the_descriptor_is_a_valid_built_in_with_send_as_its_only_mcp_tool(self):
        v = Draft202012Validator(load(SCHEMA_DIR / "onemind.builtin.schema.json"))
        self.assertEqual(errors(v, self.doc), [])
        self.assertEqual(self.doc["metadata"]["id"], MESSAGES.name)
        self.assertEqual([a["type"] for a in self.doc["spec"]["actions"] if a["mcp"]], ["message.send"])
        self.assertEqual({(a["type"], a["title"], a["mcp"]) for a in self.doc["spec"]["actions"]},
                         {(a["type"], a["title"], a["mcp"]) for a in self.actions})
        owns = self.doc["spec"]["routes"]["owns"]
        self.assertIn("/v1/messages", owns)  # the switch-off gate covers every Messages route
        for call in self.doc["spec"]["routes"]["calls"]:
            path = call.split(" ", 1)[1]
            self.assertTrue(any(path == o or path.startswith(o + "/") for o in owns), call)

    def test_action_specs_keep_a_person_on_every_transmission(self):
        by = {a["type"]: a for a in self.actions}
        self.assertEqual(set(by), {"message.send", "radio.advert", "radio.grant", "radio.revoke", "radio.region.confirm"})
        jobs = set(load(SCHEMA_DIR / "onemind.job.lora.schema.json")["properties"]["kind"]["enum"])
        for a in self.actions:
            Draft202012Validator.check_schema(a["params"])
            self.assertFalse(a["physical"] or a["policy_approval"], a["type"])
            self.assertTrue(set(a["requesters"]) <= {"person", "agent"}, a["type"])  # never automation, plugin or policy
            self.assertFalse({k for k in walk_keys(a["params"]) if any(w == k or k.startswith(w + "_") for w in RF_WORDS)}, a["type"])
            self.assertTrue(a["job"] is None or a["job"] in jobs, a["type"])
        for t in ("message.send", "radio.advert"):
            self.assertEqual((by[t]["risk"], by[t]["requesters"], by[t]["transmits"]), ("write", ["person", "agent"], True))
        self.assertEqual((by["message.send"]["job"], by["radio.advert"]["job"]), ("lora.send", "lora.advert"))
        self.assertEqual((by["radio.region.confirm"]["requesters"], by["radio.region.confirm"]["owner_only"]), (["person"], True))
        self.assertEqual(by["radio.grant"]["params"]["properties"]["holder"]["const"], "builtin:messages")


if __name__ == "__main__":
    unittest.main()
