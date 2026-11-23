# SPDX-License-Identifier: Apache-2.0
"""Bridge intake (#610): POST /v1/bridges/<id>/events, quotas, auto-pause and the reads behind
`onemind bridge list|status`. Real plugin tokens through the real identity repository."""

from __future__ import annotations

import copy
import json
import threading
import time
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, GUEST, OWNER, action_body
from onemind_core.app import create_app
from onemind_core.bridges import BridgeSettings
from onemind_core.catalog import AppEntry
from onemind_core.identity.crypto import new_secret, sha256_hex
from onemind_core.identity.models import TokenRow
from onemind_core.notify import NotifySettings
from onemind_core.plugins.auth import allows_bridge_intake
from onemind_core.plugins.models import PluginInstallRow
from onemind_core.plugins.workload import declaration

APP = "quake-feed"
MANIFEST = {
    "apiVersion": "onemind.io/v1", "kind": "App", "metadata": {"id": APP, "name": "Quake feed", "license": "Apache-2.0"},
    "spec": {
        "manifests": "manifests/", "egress": ["earthquake.usgs.gov"], "plugin": {"principal": True, "secret": "quake-token"},
        "extensions": {"bridge": {
            "provider": "usgs", "mode": "poll", "everySeconds": 60, "hosts": ["earthquake.usgs.gov"],
            "dataClass": "public", "emits": [{"kind": "intel", "name": "quakes"}, {"kind": "asset", "name": "sensor"}],
            "limits": {"eventsPerSecond": 10, "burst": 20, "maxEventBytes": 2048}}},
        "terms": {"personData": False, "providers": [{
            "id": "usgs", "name": "USGS", "url": "https://www.usgs.gov/information-policies-and-instructions",
            "readOn": "2026-11-20", "use": "commercial", "keyNeeded": False, "store": "keep",
            "redistribute": {"mesh": True, "tak": True, "publicShare": True}, "display": "full",
            "personScoped": False, "attribution": "U.S. Geological Survey"}]},
    },
}


def install(client, clock, app_id=APP, manifest=MANIFEST, scopes=("actions:read:own", "events:write:own"), status="installed"):
    token = new_secret("plg")
    row = TokenRow(id=f"tok_{app_id}", prefix=token[:11], name=f"Plugin {app_id}", hash=sha256_hex(token),
                   kind="plugin", principal_id=f"plugin:{app_id}", owner_user_id=None, scopes=list(scopes),
                   source="app-install", created_by="owner", created_at=clock(), expires_at=clock() + timedelta(days=1))
    identity = client.app.state.identity
    identity.repo.add(row)
    with identity.repo.db.session.begin() as s:
        s.merge(PluginInstallRow(app_id=app_id, secret_name="quake-token", bundle_sha256="sha256:" + "a" * 64,
                                 manifest=copy.deepcopy(manifest)))
    client.app.state.repo.set_app_state(app_id, status, clock())
    return {"Authorization": "Bearer " + token}, row


@pytest.fixture
def sent(client):
    """Every NATS publish the gateway makes, in order."""
    out = []
    client.app.state.bus.publish_threadsafe = lambda subject, data: out.append((subject, json.loads(data)))
    return out


def ev(i="us7000abcd", rev=0, kind="intel", name="quakes", **extra):
    return {"id": i, "revision": rev, "kind": kind, "name": name, "time": "2026-11-11T21:59:00Z",
            "value": {"mag": 4.2}, **extra}


def post(client, headers, *events, app_id=APP):
    return client.post(f"/v1/bridges/{app_id}/events", headers=headers, json={"events": list(events)})


def test_events_are_stamped_deduped_coalesced_and_kept_latest(client, clock, sent):
    headers, _ = install(client, clock)
    asset = ev("pump-7", kind="asset", name="sensor", value=21.5, unit="Cel", field="temp")
    r = post(client, headers, ev(rev=1), ev(rev=2), asset)
    assert r.status_code == 200, r.text
    assert r.json() == {"accepted": 2, "duplicates": 1, "rejected": [], "paused": False}
    subjects = [s for s, _ in sent]
    assert subjects == [f"onemind.plugin.{APP}.in.intel.quakes", f"onemind.plugin.{APP}.in.asset.sensor",
                        "onemind.asset.sensor.pump-7.temp", "$KV.asset-state.sensor.pump-7.temp"]
    intel = sent[0][1]
    assert intel["schema"] == "onemind.event/v1" and intel["source_id"] == APP
    assert intel["data"]["seq"] == 2, "latest-wins inside the batch publishes revision 2 only"
    assert intel["data"]["source"] == {"kind": "bridge", "id": APP}
    assert intel["data"]["licence"]["id"] == "usgs" and intel["data"]["licence"]["attribution"] == "U.S. Geological Survey"
    assert sent[2][1]["schema"] == "onemind.datapoint/v1" and sent[2][1]["value"] == 21.5
    # Retrying the same batch is safe; an older revision never overwrites a newer one.
    again = post(client, headers, ev(rev=2), ev(rev=1), asset).json()
    assert again == {"accepted": 0, "duplicates": 3, "rejected": [], "paused": False}
    assert post(client, headers, ev(rev=3)).json()["accepted"] == 1
    latest = client.get(f"/v1/bridges/{APP}/latest", headers=OWNER)
    assert latest.status_code == 200
    assert {(v["kind"], v["id"], v["revision"]) for v in latest.json()} == {("intel", "us7000abcd", 3), ("asset", "pump-7", 0)}


def test_a_bridge_cannot_publish_under_another_source(client, clock, sent):
    headers, _ = install(client, clock)
    other, _ = install(client, clock, app_id="weather-feed")
    assert post(client, headers, ev(), app_id="weather-feed").status_code == 403
    assert post(client, other, ev()).status_code == 403
    # The event names no source: the gateway stamps it, a field to forge one is refused.
    r = post(client, headers, ev(source={"kind": "bridge", "id": "weather-feed"})).json()
    assert r["accepted"] == 0 and r["rejected"][0]["reason"] == "source: extra_forbidden"
    # An asset id one bridge publishes is not another bridge's to overwrite.
    assert post(client, headers, ev("pump-7", kind="asset", name="sensor", value=1, unit="Cel")).json()["accepted"] == 1
    taken = post(client, other, ev("pump-7", kind="asset", name="sensor", value=2, unit="Cel"), app_id="weather-feed")
    assert taken.json()["rejected"][0]["reason"] == "asset sensor/pump-7 belongs to another source"
    assert [s for s, _ in sent if s.startswith("onemind.asset.")] == ["onemind.asset.sensor.pump-7.state"]


@pytest.mark.parametrize("bad,reason", [
    (ev(kind="layer", name="quakes"), "layer quakes is not one of this bridge's emits"),
    (ev(name="robot", kind="asset"), "asset robot is not one of this bridge's emits"),
    (ev(value=1.5), "unit"),                         # a number needs a unit (datapoint envelope)
    (ev(value="x" * 3000), "this bridge's limit is 2048"),
    (ev(position={"lat": 0, "lon": 0}), "position 0,0 is refused"),
    ({"id": "a.b", "kind": "intel", "name": "quakes", "time": "2026-11-11T21:59:00Z"}, "id: string_pattern_mismatch"),
])
def test_bad_events_are_refused_with_a_reason_and_sent_to_the_reject_subject(client, clock, sent, bad, reason):
    headers, _ = install(client, clock)
    r = post(client, headers, bad, ev("good-one"))
    assert r.status_code == 200 and r.json()["accepted"] == 1
    assert reason in r.json()["rejected"][0]["reason"] and r.json()["rejected"][0]["index"] == 0
    assert (f"onemind.plugin.{APP}.reject", "bridge.rejected") in [(s, d.get("type")) for s, d in sent]


def test_robot_channels_stay_reserved_even_when_declared(client, clock):
    manifest = copy.deepcopy(MANIFEST)
    manifest["spec"]["extensions"]["bridge"]["emits"].append({"kind": "asset", "name": "robot"})
    headers, _ = install(client, clock, manifest=manifest)
    r = post(client, headers, ev("r1", kind="asset", name="robot", value="ok")).json()
    assert r["rejected"][0]["reason"] == "robot channels are reserved: no bridge publishes them"


@pytest.mark.parametrize("change", ["no_grant", "revoked", "stopped", "no_bridge", "removed"])
def test_unapproved_or_revoked_principals_are_refused(client, clock, change):
    manifest = copy.deepcopy(MANIFEST)
    if change == "no_bridge":
        del manifest["spec"]["extensions"]["bridge"]
    scopes = ("actions:read:own",) if change == "no_grant" else ("actions:read:own", "events:write:own")
    status = {"stopped": "stopped", "removed": "removed"}.get(change, "installed")
    headers, row = install(client, clock, manifest=manifest, scopes=scopes, status=status)
    if change == "revoked":
        client.app.state.identity.repo.update(TokenRow, [TokenRow.id == row.id], {"revoked_at": clock()})
    r = post(client, headers, ev())
    assert r.status_code == (401 if change == "revoked" else 403), r.text


def test_people_and_agents_never_post_bridge_events(client, clock):
    install(client, clock)
    for headers in (OWNER, ADULT, AGENT):
        assert post(client, headers, ev()).status_code == 403


def test_nats_down_never_fails_the_caller(client, clock):
    headers, _ = install(client, clock)

    def down(subject, data):
        raise ConnectionError("nats down")

    client.app.state.bus.publish_threadsafe = down
    r = post(client, headers, ev(), ev("pump-1", kind="asset", name="sensor", value=3, unit="Cel"))
    assert r.status_code == 200 and r.json()["accepted"] == 2
    assert len(client.get(f"/v1/bridges/{APP}/latest", headers=OWNER).json()) == 2


@pytest.fixture
def nclient(settings, clock, executor, tmp_path):
    s = replace(settings, sections={**settings.sections, "notify": NotifySettings(worker=False, dir=tmp_path / "keys")})
    with TestClient(create_app(s, clock=clock, executor=executor)) as c:
        yield c


def test_a_flooding_bridge_is_throttled_while_an_approval_arrives_within_a_second(nclient, clock):
    """The acceptance test: a bridge sending 1,000 events a second is held to its rate (10/s, burst 20)
    while an agent's approval request reaches the owner's open alerts within 1 s."""
    headers, _ = install(nclient, clock)
    codes, stop = [], threading.Event()

    def flood():
        n = 0
        while not stop.is_set():
            batch = [ev(f"q{n}-{i}") for i in range(20)]
            n += 1
            codes.append(post(nclient, headers, *batch).status_code)

    t = threading.Thread(target=flood)
    t.start()
    try:
        while len(codes) < 5:
            time.sleep(0.01)
        started = time.monotonic()
        a = nclient.post("/v1/actions", headers=AGENT, json=action_body(clock)).json()
        seen = None
        while time.monotonic() - started < 1.0 and seen is None:
            alerts = nclient.get("/v1/alerts", headers=OWNER, params={"state": "open"}).json()
            seen = next((x for x in alerts if x["dedupe_key"] == f"approval:{a['id']}"), None)
        elapsed = time.monotonic() - started
    finally:
        stop.set()
        t.join()
    assert seen is not None and elapsed < 1.0, f"approval alert after {elapsed:.2f}s"
    assert codes.count(200) == 1 and codes.count(429) == len(codes) - 1, "one burst in, then throttled"
    status = nclient.get(f"/v1/bridges/{APP}", headers=OWNER).json()
    assert status["accepted"] == 20 and status["throttled"] >= 20 * (len(codes) - 1)
    r = post(nclient, headers, ev("late"))
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    clock.advance(2)  # the bucket refills at 10 events a second
    assert post(nclient, headers, ev("late")).status_code == 200


def test_twenty_rejects_in_five_minutes_pause_the_bridge_with_one_notification(nclient, clock):
    headers, _ = install(nclient, clock)
    assert post(nclient, headers, *[ev(f"x{i}", kind="layer") for i in range(19)]).json()["paused"] is False
    clock.advance(301)  # older rejects leave the window
    assert post(nclient, headers, *[ev(f"y{i}", kind="layer") for i in range(19)]).json()["paused"] is False
    r = post(nclient, headers, ev("z", kind="layer")).json()
    assert r["paused"] is True
    refused = post(nclient, headers, ev("fine"))
    assert refused.status_code == 409 and refused.json()["reason"] == "bridge_paused"
    alerts = [a for a in nclient.get("/v1/alerts", headers=OWNER, params={"state": "open"}).json()
              if a["type"] == "bridge.paused"]
    assert len(alerts) == 1 and alerts[0]["dedupe_key"] == f"bridge:{APP}:paused"
    status = nclient.get(f"/v1/bridges/{APP}", headers=OWNER).json()
    assert status["state"] == "paused" and "not one of this bridge's emits" in status["paused_reason"]
    assert nclient.post(f"/v1/bridges/{APP}/resume", headers=ADULT).status_code == 403
    resumed = nclient.post(f"/v1/bridges/{APP}/resume", headers=OWNER)
    assert resumed.status_code == 200 and resumed.json()["state"] == "active"
    assert not [a for a in nclient.get("/v1/alerts", headers=OWNER, params={"state": "open"}).json()
                if a["type"] == "bridge.paused"]
    clock.advance(1)
    assert post(nclient, headers, ev("fine")).json()["accepted"] == 1


def test_list_and_status_show_hub_capped_limits_to_people_only(settings, clock, executor):
    manifest = copy.deepcopy(MANIFEST)
    manifest["spec"]["extensions"]["bridge"]["limits"] = {"eventsPerSecond": 100, "burst": 1000, "maxEventBytes": 16384}
    s = replace(settings, sections={**settings.sections, "bridges": BridgeSettings(max_events_per_second=40, max_burst=80)})
    with TestClient(create_app(s, clock=clock, executor=executor)) as c:
        install(c, clock, manifest=manifest)
        install(c, clock, app_id="no-bridge", manifest={"spec": {"plugin": {"principal": True, "secret": "x"}}})
        listed = c.get("/v1/bridges", headers=ADULT)
        assert listed.status_code == 200 and [b["id"] for b in listed.json()] == [APP]
        b = listed.json()[0]
        assert (b["events_per_second"], b["burst"], b["max_event_bytes"], b["state"]) == (40, 80, 16384, "active")
        assert b["emits"] == [{"kind": "asset", "name": "sensor"}, {"kind": "intel", "name": "quakes"}]
        for who in (GUEST, AGENT):
            assert c.get("/v1/bridges", headers=who).status_code == 403
        assert c.get("/v1/bridges/no-bridge", headers=OWNER).status_code == 404


@pytest.mark.parametrize("data_class,adult", [("public", 200), ("private", 403), ("location", 403)])
def test_reading_values_checks_the_data_class_when_a_reader_subscribes(client, clock, data_class, adult):
    manifest = copy.deepcopy(MANIFEST)
    manifest["spec"]["extensions"]["bridge"]["dataClass"] = data_class
    headers, _ = install(client, clock, manifest=manifest)
    post(client, headers, ev())
    assert client.get(f"/v1/bridges/{APP}/latest", headers=OWNER).status_code == 200
    assert client.get(f"/v1/bridges/{APP}/latest", headers=ADULT).status_code == adult
    for who in (GUEST, AGENT, headers):
        assert client.get(f"/v1/bridges/{APP}/latest", headers=who).status_code == 403


def test_revision_is_required_so_readings_are_never_silently_dropped(client, clock, sent):
    """Latest-wins keeps only a strictly higher revision: a default of 0 would count every reading
    after the first as a duplicate. A missing revision is refused out loud instead."""
    headers, _ = install(client, clock)
    reading = {"id": "pump-9", "kind": "asset", "name": "sensor", "field": "temp", "time": "2026-11-11T21:59:00Z",
               "value": 20.0, "unit": "Cel"}
    for value in (20.0, 21.0):
        r = post(client, headers, reading | {"value": value}).json()
        assert r["accepted"] == 0 and r["duplicates"] == 0 and r["rejected"][0]["reason"] == "revision: missing"
    assert not [s for s, _ in sent if s.startswith("onemind.asset.")]
    # A sensor sending its reading time in ms as the revision gets every new value through.
    for n, value in enumerate((20.0, 21.0, 22.5)):
        assert post(client, headers, reading | {"value": value, "revision": 1763000000000 + n}).json()["accepted"] == 1
    assert [d["value"] for s, d in sent if s == "onemind.asset.sensor.pump-9.temp"] == [20.0, 21.0, 22.5]


@pytest.mark.parametrize("data_class", ["owner", "private", "location", "activity"])
def test_only_a_public_bridge_feeds_the_shared_asset_state(client, clock, sent, data_class):
    """The asset-state bucket and onemind.asset.* reach every adult and asset-reading agent on
    GET /v1/events (#606), which never asks the bridge's data class: a non-public bridge's asset
    events are refused, so nothing it sends lands there; its other kinds stay owner-only on /latest."""
    manifest = copy.deepcopy(MANIFEST)
    manifest["spec"]["extensions"]["bridge"]["dataClass"] = data_class
    headers, _ = install(client, clock, manifest=manifest)
    r = post(client, headers, ev("pump-3", kind="asset", name="sensor", value=1, unit="Cel"), ev()).json()
    assert r["accepted"] == 1 and r["rejected"][0]["index"] == 0
    assert f"dataClass {data_class} cannot emit them" in r["rejected"][0]["reason"]
    assert not [s for s, _ in sent if s.startswith(("onemind.asset.", "$KV."))]
    assert [v["kind"] for v in client.get(f"/v1/bridges/{APP}/latest", headers=OWNER).json()] == ["intel"]
    assert client.get(f"/v1/bridges/{APP}/latest", headers=ADULT).status_code == 403


def test_show_only_terms_keep_nothing(client, clock, sent):
    manifest = copy.deepcopy(MANIFEST)
    manifest["spec"]["terms"]["providers"][0]["store"] = "none"
    headers, _ = install(client, clock, manifest=manifest)
    post(client, headers, ev("pump-2", kind="asset", name="sensor", value=1, unit="Cel"))
    assert not [s for s, _ in sent if s.startswith("$KV.")]
    assert client.get(f"/v1/bridges/{APP}/latest", headers=OWNER).json()[0]["datapoint"] is None


def test_only_an_approved_bridge_block_mints_the_intake_grant(tmp_path: Path):
    _, scopes = declaration(AppEntry(APP, tmp_path, MANIFEST))
    assert "events:write:own" in scopes
    plain = copy.deepcopy(MANIFEST)
    del plain["spec"]["extensions"]
    assert "events:write:own" not in declaration(AppEntry(APP, tmp_path, plain))[1]
    asks = copy.deepcopy(plain)
    asks["spec"]["permissions"] = ["events:write:own"]
    with pytest.raises(ValueError, match="unsupported runtime permissions"):
        declaration(AppEntry(APP, tmp_path, asks))


@pytest.mark.parametrize("change", [
    {"path": "/v1/bridges/other-app/events"}, {"method": "GET"}, {"operation_id": "bridges.get"},
    {"source": "api"}, {"app_status": "stopped"}, {"principal_id": f"agent:{APP}"},
    {"scopes": ["actions:read:own"]}, {"scopes": ["events:write:own", "*"]},
])
def test_intake_policy_does_not_widen(change):
    policy = dict(method="POST", path=f"/v1/bridges/{APP}/events", operation_id="bridges.events.post",
                  principal_id=f"plugin:{APP}", source="app-install", scopes=["events:write:own"], app_status="installed")
    assert allows_bridge_intake(**policy)
    assert not allows_bridge_intake(**(policy | change))
