# SPDX-License-Identifier: Apache-2.0
"""The one NATS subject tree (issue #600): sdk/schema/onemind.subjects.json, its checker and its routes.

Acceptance: an app publishing onemind.audit, an unknown kind, or a position of exactly 0,0 or
outside WGS-84 is refused with a reason. Must refuse: any grammar that lets a plugin name a core
subject. Every subject the code uses today (contract 12.9) stays valid for its publisher.
"""

from __future__ import annotations

import json
import math

import pytest

from conftest import AGENT, OWNER
from onemind_core import streams, subjects
from onemind_core.natsconf import policy_check_subject


@pytest.fixture(scope="module")
def reg() -> subjects.Registry:
    return subjects.load()


KINDS = ["node", "audit", "event", "alert", "asset", "intel", "metric", "plugin", "layer", "notification", "request"]


def point(**changes):
    return {"schema": "onemind.datapoint/v1", "nats_subject": "onemind.asset.sensor.greenhouse-1.temp",
            "time": "2026-11-21T10:00:00Z", "seq": 7, "value": 21.5, "unit": "Cel", "quality": "live",
            "source": {"kind": "bridge", "id": "meshtastic"}, "licence": {"id": "Apache-2.0"},
            "position": {"lat": 40.7128, "lon": -74.006}, **changes}


def test_the_registry_has_every_kind_with_publisher_stream_retention_and_envelope(reg):
    assert list(reg.kinds) == KINDS
    for name, kind in reg.kinds.items():
        assert kind["retention"]["policy"] in ("limits", "workqueue", "latest", "none"), name
        assert kind["envelope"] in reg.raw["envelopes"], name
        assert [p for p in reg.patterns if p.kind == name], name


# --- acceptance -----------------------------------------------------------------------------

def test_an_app_publishing_onemind_audit_is_refused_with_a_reason(reg):
    v = reg.check("onemind.audit", "app", "notes")
    assert not v.ok and "core" in v.reason and "gateway" in v.reason


def test_an_unknown_kind_is_refused_with_a_reason(reg):
    v = reg.check("onemind.weather.city.nyc.temp", "gateway")
    assert not v.ok and "unknown kind 'weather'" in v.reason
    assert not reg.covers("onemind.weather.>").ok


@pytest.mark.parametrize("position,needle", [
    ({"lat": 0, "lon": 0}, "0,0 is refused"),
    ({"lat": 0.0, "lon": 0.0}, "0,0 is refused"),
    ({"lat": 90.5, "lon": 10}, "position.lat 90.5 is outside WGS-84"),
    ({"lat": 10, "lon": -180.01}, "position.lon -180.01 is outside WGS-84"),
    ({"lat": math.nan, "lon": 10}, "position.lat must be a finite number"),
    ({"lat": "40", "lon": 10}, "position.lat must be a finite number"),
])
def test_a_position_at_0_0_or_outside_wgs84_is_refused_with_a_reason(reg, position, needle):
    problems = reg.envelope_problems("onemind.datapoint/v1", point(position=position))
    assert any(needle in p for p in problems), problems


def test_the_schema_file_itself_also_refuses_0_0():
    # A Go or TypeScript validator reading only the JSON schema must refuse it too.
    from jsonschema import Draft202012Validator

    schema = json.loads((subjects.registry_path().parent / "onemind.datapoint.schema.json").read_text())
    v = Draft202012Validator(schema)
    assert not v.is_valid(point(position={"lat": 0, "lon": 0}))
    assert not v.is_valid(point(position={"lat": -91, "lon": 0.5}))
    assert v.is_valid(point(position={"lat": 0, "lon": 0.5}))  # the equator alone is a real place


def test_a_good_datapoint_passes_and_its_rules_bite(reg):
    assert reg.envelope_problems("onemind.datapoint/v1", point()) == []
    no_unit = {k: v for k, v in point().items() if k != "unit"}
    assert any("unit" in p for p in reg.envelope_problems("onemind.datapoint/v1", no_unit))
    no_licence = {k: v for k, v in point().items() if k != "licence"}
    assert any("licence" in p for p in reg.envelope_problems("onemind.datapoint/v1", no_licence))
    assert any("quality" in p for p in reg.envelope_problems("onemind.datapoint/v1", point(quality="great")))
    big = point(value="x" * 1000, source={"kind": "bridge", "id": "b"}, extra="y" * 17000)
    assert any("limit is 16384" in p for p in reg.envelope_problems("onemind.datapoint/v1", big))


# --- must refuse: a plugin naming a core subject ------------------------------------------

CORE_SUBJECTS = ["onemind.audit", "onemind.event.app.installed", "onemind.alert.disk.budget_near",
                 "onemind.node.aaa111.status", "onemind.node.aaa111.job.restore", "onemind.asset.camera.door.state",
                 "onemind.intel.world.gdelt.event", "onemind.metric.node.aaa111.cpu", "onemind.layer.core.roads.meta",
                 "onemind.notification.person.p1.created", "onemind.request.agent.hermes.action"]


@pytest.mark.parametrize("subject", CORE_SUBJECTS)
def test_an_app_can_never_publish_a_core_subject(reg, subject):
    assert not reg.check(subject, "app", "notes").ok


def test_an_app_publishes_only_under_its_own_id(reg):
    assert reg.check("onemind.plugin.notes.saved", "app", "notes").ok
    assert reg.check("onemind.request.app.notes.share", "app", "notes").ok
    v = reg.check("onemind.plugin.photos.saved", "app", "notes")
    assert not v.ok and "own app_id (notes)" in v.reason
    assert not reg.check("onemind.plugin.notes.saved", "app", None).ok
    # Its own prefix can carry core-looking words, but it stays inside the plugin kind.
    v = reg.check("onemind.plugin.notes.onemind.audit", "app", "notes")
    assert v.ok and v.kind == "plugin"


def test_reserved_kinds_are_refused_with_the_place_to_go(reg):
    v = reg.check("onemind.app.notes.saved", "app", "notes")
    assert not v.ok and "onemind.plugin.<app_id>" in v.reason
    assert "request" in reg.check("onemind.cmd.light.on", "gateway").reason
    assert "onemind.asset.device" in reg.check("onemind.device.d1.state", "gateway").reason


def test_robot_channels_are_reserved_names_only(reg):
    assert reg.check("onemind.asset.robot.r1.estop", "gateway").ok
    assert not reg.check("onemind.asset.robot.r1.dance", "gateway").ok
    assert not reg.check("onemind.asset.robot.r1.pose", "app", "r1").ok


def test_an_agent_only_asks_under_its_own_id(reg):
    assert reg.check("onemind.request.agent.hermes.action", "agent", "hermes").ok
    assert not reg.check("onemind.request.agent.hermes.action", "agent", "other").ok
    for s in ("onemind.event.action.approved", "onemind.asset.camera.door.state", "onemind.node.a.status"):
        assert not reg.check(s, "agent", "hermes").ok


# --- contract 12.9 and the code today stay valid ------------------------------------------

@pytest.mark.parametrize("subject,publisher,owner", [
    ("onemind.node.aaa111.status", "node", "aaa111"),
    ("onemind.node.aaa111.event.update.staged", "node", "aaa111"),
    ("onemind.node.aaa111.jobresult.j-1", "node", "aaa111"),
    ("onemind.node.aaa111.job.backup.run", "gateway", None),
    ("onemind.node.aaa111.job.system.restart_unit", "gateway", None),
    ("onemind.audit", "gateway", None),
    ("onemind.event.backup.run.finished", "gateway", None),
    ("onemind.alert.storage.disk_budget_near", "gateway", None),
    ("onemind.plugin.hello.greeted", "gateway", None),
])
def test_every_contract_12_9_subject_is_valid_for_its_publisher(reg, subject, publisher, owner):
    assert reg.check(subject, publisher, owner).ok, reg.check(subject, publisher, owner).reason


def test_live_policy_check_is_an_ephemeral_request_scoped_to_its_node(reg):
    subject = policy_check_subject("aaa111")
    verdict = reg.check(subject, "node", "aaa111")
    assert verdict.ok, verdict.reason
    pattern = next(p for p in reg.patterns if p.text == verdict.pattern)
    assert pattern.stream is None and pattern.retention["policy"] == "none"
    assert pattern.envelope == "dispatch-challenge"
    assert not reg.check(subject, "node", "bbb222").ok
    assert not reg.check(subject, "agent", "aaa111").ok


# --- review of #791: real job kinds, real 12.1 ids, agent principals, one meaning of "subject" ---

JOB_KINDS_12_11 = ["backup.run", "backup.restore", "backup.verify", "backup.prune", "backup.snapshot.delete",
                   "update.check", "update.apply", "update.postpone", "update.settings", "os.rollback",
                   "node.leave", "node.renew", "host.check", "system.restart_unit"]


@pytest.mark.parametrize("kind", JOB_KINDS_12_11)
def test_every_contract_12_11_job_kind_has_a_job_subject(reg, kind):
    v = reg.check(f"onemind.node.aaa111.job.{kind}", "gateway")
    assert v.ok, v.reason
    assert v.pattern == "onemind.node.{node_id:node_id}.job.{job_kind:type}"
    assert not reg.check(f"onemind.node.aaa111.job.{kind}", "node", "aaa111").ok


@pytest.mark.parametrize("subject,publisher,owner", [
    ("onemind.node.aaa111.jobresult.job_01HXA7Q2M3K4N5P6R7S8T9V0WX", "node", "aaa111"),
    ("onemind.node.aaa111.jobresult.3f2b8c1e-4d5a-4b6c-8d7e-9f0a1b2c3d4e", "node", "aaa111"),
    ("onemind.notification.person.usr_01HXA7Q2M3K4N5P6R7S8T9V0WX.created", "gateway", None),
    ("onemind.asset.camera.dev_01HXA7Q2M3K4N5P6R7S8T9V0WX.state", "gateway", None),
    ("onemind.asset.robot.dev_01HXA7Q2M3K4N5P6R7S8T9V0WX.pose", "gateway", None),
])
def test_contract_12_1_ids_ride_the_tree_as_they_are(reg, subject, publisher, owner):
    v = reg.check(subject, publisher, owner)
    assert v.ok, v.reason


def test_an_id_slot_still_refuses_what_is_not_an_id(reg):
    assert not reg.check("onemind.node.aaa111.jobresult._job", "node", "aaa111").ok
    assert not reg.check("onemind.notification.person.usr_" + "A" * 130 + ".created", "gateway").ok
    # Names chosen by OneMind (fields, sources) stay lowercase.
    assert not reg.check("onemind.notification.person.usr_01HX.Created", "gateway").ok


def test_an_agent_principal_with_dots_maps_to_its_subject(reg):
    owner = reg.agent_owner_id("agent:hermes.v2")
    assert owner == "hermes.v2"
    v = reg.check("onemind.request.agent.hermes.v2.action", "agent", owner)
    assert v.ok, v.reason
    assert reg.check("onemind.request.agent.hermes.action", "agent", reg.agent_owner_id("agent:hermes")).ok
    # hermes may not ask as hermes.v2, and hermes.v2 may not ask as hermes.
    assert not reg.check("onemind.request.agent.hermes.v2.action", "agent", "hermes").ok
    assert not reg.check("onemind.request.agent.hermes.action", "agent", "hermes.v2").ok
    # request_type is exactly one last token, so a name cannot borrow a part of it.
    assert not reg.check("onemind.request.agent.hermes.v2", "agent", "hermes.v2").ok


@pytest.mark.parametrize("principal", ["agent:a..b", "agent:a.", "person:hermes", "hermes", "agent:", None])
def test_an_agent_name_without_a_subject_maps_to_nothing(reg, principal):
    assert reg.agent_owner_id(principal) is None


def test_every_agent_id_the_identity_service_accepts_maps_or_is_named_unmappable(reg):
    from onemind_core.identity.service import AGENT_ID_RE

    for pid in ("agent:hermes", "agent:hermes.v2", "agent:a-b_c.d-1", "agent:" + "a" * 63):
        assert AGENT_ID_RE.fullmatch(pid), pid
        assert reg.agent_owner_id(pid) == pid[len("agent:"):], pid
    assert AGENT_ID_RE.fullmatch("agent:a..b") and reg.agent_owner_id("agent:a..b") is None


def test_the_datapoint_names_the_nats_subject_apart_from_the_event_subject(reg):
    dp = json.loads((subjects.registry_path().parent / "onemind.datapoint.schema.json").read_text())
    ev = json.loads((subjects.registry_path().parent / "onemind.event.schema.json").read_text())
    assert ev["properties"]["subject"]["type"] == "object"
    assert "subject" not in dp["properties"] and dp["properties"]["nats_subject"]["type"] == "string"
    assert "nats_subject" in dp["required"]
    old = {("subject" if k == "nats_subject" else k): v for k, v in point().items()}
    assert any("nats_subject" in p for p in reg.envelope_problems("onemind.datapoint/v1", old))


def test_a_node_names_only_itself(reg):
    v = reg.check("onemind.node.bbb222.status", "node", "aaa111")
    assert not v.ok and "own node_id" in v.reason
    assert not reg.check("onemind.node.aaa111.job.backup", "node", "aaa111").ok  # jobs come from the gateway


@pytest.mark.parametrize("subject_filter", [
    "onemind.node.*.status", "onemind.node.*.event.>", "onemind.node.*.jobresult.>", "onemind.node.aaa.job.>",
    "onemind.audit", "onemind.event.>", "onemind.alert.>", "onemind.plugin.notes.>", "onemind.>",
])
def test_the_filters_the_gateway_and_nats_accounts_use_are_registered(reg, subject_filter):
    assert reg.covers(subject_filter).ok


def test_a_real_gateway_event_matches_its_subject_and_envelope(client, reg):
    sent = []
    hub = client.app.state.gateway.events
    hub.publish = lambda subject, data: sent.append((subject, json.loads(data)))
    hub.publish_event("backup", "run.finished", {"run_id": "r1"}, resource={"kind": "job", "id": "r1"})
    [(subject, envelope)] = sent
    assert reg.check(subject, "gateway").ok
    assert reg.pattern_for(subject).envelope == "onemind.event/v1"
    assert reg.envelope_problems("onemind.event/v1", envelope) == []


def test_app_streams_land_under_the_plugin_kind(reg):
    manifest = {"spec": {"streams": [{"name": "readings", "subjects": ["readings.>", "sensor.*.temp"],
                                      "maxBytes": 1 << 20, "maxAgeSeconds": 3600}]}}
    (entry,) = streams.plan_entries("sensor-hub", manifest)
    for s in entry["subjects"]:
        v = reg.covers(s)
        assert v.ok and v.kind == "plugin", s


# --- the registry fails closed -------------------------------------------------------------

def test_a_malformed_registry_is_refused(tmp_path, reg):
    raw = json.loads(subjects.registry_path().read_text())
    raw["kinds"]["plugin"]["subjects"][0]["owner"] = "nobody"
    bad = tmp_path / "onemind.subjects.json"
    bad.write_text(json.dumps(raw))
    with pytest.raises(subjects.RegistryError, match="no placeholder 'nobody'"):
        subjects.load(bad)
    raw = json.loads(subjects.registry_path().read_text())
    raw["reserved_kinds"]["audit"] = "x"
    bad.write_text(json.dumps(raw))
    with pytest.raises(subjects.RegistryError, match="both registered and reserved"):
        subjects.load(bad)


# --- routes ---------------------------------------------------------------------------------

def test_get_subjects_lists_the_tree(client):
    r = client.get("/v1/subjects", headers=OWNER)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version"] == "onemind.subjects/v1" and body["grammar"] == "onemind.<kind>.<scope>.<id>.<field>"
    assert [k["kind"] for k in body["kinds"]] == KINDS
    audit = next(k for k in body["kinds"] if k["kind"] == "audit")
    assert audit["core"] and audit["stream"] == "ONEMIND_AUDIT" and audit["retention"]["deny_purge"] is True
    assert {"kind": "app", "reason": subjects.load().reserved["app"]} in body["reserved"]
    assert any(m["old"] == "evt.app.<app_id>.<event>" for m in body["mappings"])


def test_check_route_answers_with_a_reason(client):
    r = client.get("/v1/subjects/check", params={"subject": "onemind.audit", "publisher": "app", "owner_id": "notes"},
                   headers=AGENT)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is False and "core" in r.json()["reason"]
    ok = client.get("/v1/subjects/check", params={"subject": "onemind.plugin.notes.saved", "owner_id": "notes"},
                    headers=OWNER).json()
    assert ok["ok"] is True and ok["kind"] == "plugin"


def test_subject_routes_need_a_login(client):
    assert client.get("/v1/subjects").status_code == 401
    assert client.get("/v1/subjects/check", params={"subject": "onemind.audit"}).status_code == 401
