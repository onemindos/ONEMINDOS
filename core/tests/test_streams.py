# SPDX-License-Identifier: Apache-2.0
"""Hub JetStream and app event streams (`spec.streams`): validation, the approved plan, the hub account
limit and the degraded state. Creating the streams on the hub is the next slice (core/README.md)."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from onemind_core import streams
from onemind_core.appstore.service import AppStore
from onemind_core.catalog import AppEntry
from onemind_core.errors import ApiError
from onemind_core.lifecycle import render_plan
from onemind_core.natsconf import NodeAccount, render_accounts
from onemind_core.netconf import FabricSettings

PUB_A = "UBBUEVU3RVFLTSYWTDDLUC2TLY3YDZKKYWVTUOW4UFVUY6BICGH55O2Y"
GOOD = {"name": "readings", "subjects": ["readings.>"], "maxBytes": 64 << 20, "maxAgeSeconds": 86400}
SCHEMA = Path(__file__).resolve().parents[2] / "sdk" / "schema" / "onemind.app.schema.json"


def m(*entries):
    return {"spec": {"streams": list(entries)}}


def test_no_streams_declared_is_fine():
    assert streams.validate({}) == [] and streams.declared({"spec": {}}) == []


def test_good_declaration_becomes_exact_plan_parameters():
    (entry,) = streams.plan_entries("sensor-hub", m(GOOD))
    assert entry == {"name": "APP_SENSOR_HUB_READINGS", "subjects": ["onemind.plugin.sensor-hub.readings.>"],
                     "storage": "file", "replicas": 1, "retention": "limits", "discard": "old",
                     "max_bytes": 64 << 20, "max_age_s": 86400}


@pytest.mark.parametrize("change,needle", [
    ({"maxBytes": None}, "maxBytes"), ({"maxBytes": 5}, "maxBytes"), ({"maxBytes": (1 << 30) + 1}, "maxBytes"),
    ({"maxBytes": True}, "maxBytes"), ({"maxAgeSeconds": None}, "maxAgeSeconds"),
    ({"maxAgeSeconds": 30 * 86400 + 1}, "maxAgeSeconds"), ({"name": "Bad_Name"}, "name"),
    ({"subjects": []}, "subjects"), ({"subjects": [">"]}, None),
    ({"subjects": ["$JS.API.>"]}, "subjects"), ({"subjects": ["a b"]}, "subjects"), ({"subjects": ["a..b"]}, "subjects"),
    ({"replicas": 3}, "unknown field"),
])
def test_bad_declarations_are_named(change, needle):
    entry = {**GOOD, **change}
    entry = {k: v for k, v in entry.items() if v is not None}
    problems = streams.validate(m(entry))
    if needle is None:  # ">" alone is legal here: it is relative, so it stays inside onemind.plugin.<id>.
        assert problems == [] and streams.plan_entries("a", m(entry))[0]["subjects"] == ["onemind.plugin.a.>"]
    else:
        assert problems and any(needle in p["field"] or needle in p["problem"] for p in problems)


def test_limits_on_count_and_duplicates():
    assert streams.validate(m(*[{**GOOD, "name": f"s{i}", "subjects": [f"s{i}.>"]} for i in range(5)]))
    assert streams.validate(m(GOOD, GOOD))
    assert streams.validate(m(GOOD, {**GOOD, "name": "other"}))  # same subject twice
    assert streams.validate({"spec": {"streams": "x"}})


def test_an_app_cannot_name_a_subject_outside_its_prefix():
    # A subject like a core one is only ever relative: it lands under onemind.plugin.notes., never on it.
    (e,) = streams.plan_entries("notes", m({**GOOD, "subjects": ["onemind.node.abc.status"]}))
    assert e["subjects"] == ["onemind.plugin.notes.onemind.node.abc.status"]
    assert streams.plan_entries("notes", m({**GOOD, "subjects": ["$SYS.>"]})) == []  # refused outright


def entry_for(manifest):
    return AppEntry(id="notes", dir=Path("."), manifest={"metadata": {"name": "Notes", "version": "1.0.0"}, **manifest})


def test_plan_lists_the_streams_and_a_changed_limit_is_a_different_plan():
    app = entry_for(m(GOOD))
    a = render_plan("app.install", {"app_id": "notes"}, app, None, None, None, streams.plan_entries("notes", app.manifest))
    bigger = entry_for(m({**GOOD, "maxBytes": 128 << 20}))
    b = render_plan("app.install", {"app_id": "notes"}, bigger, None, None, None, streams.plan_entries("notes", bigger.manifest))
    assert a["plan"]["objects"][0]["streams"][0]["max_bytes"] == 64 << 20
    assert any("event stream" in w and "67108864 bytes" in w for w in a["plan"]["warnings"])
    assert a["plan_sha256"] != b["plan_sha256"]
    plain = render_plan("app.install", {"app_id": "notes"}, entry_for({}), None, None, None, [])
    assert "streams" not in plain["plan"]["objects"][0]


def test_app_remove_plan_does_not_claim_a_stream():
    app = entry_for(m(GOOD))
    r = render_plan("app.remove", {"app_id": "notes"}, app, None, "running", None, streams.plan_entries("notes", app.manifest))
    assert "streams" not in r["plan"]["objects"][0]


def test_schema_accepts_the_good_shape_and_refuses_the_bad():
    schema = json.loads(SCHEMA.read_text())
    sub = {"$schema": schema["$schema"], **schema["properties"]["spec"]["properties"]["streams"]}
    v = Draft202012Validator(sub)
    assert not list(v.iter_errors([GOOD]))
    for bad in ({**GOOD, "maxBytes": 1}, {k: x for k, x in GOOD.items() if k != "maxAgeSeconds"},
                {**GOOD, "subjects": ["$JS.>"]}, {**GOOD, "extra": 1}):
        assert list(v.iter_errors([bad])), bad


def test_hub_account_gets_a_file_only_capped_jetstream_and_nodes_do_not():
    off = render_accounts([NodeAccount("aaa111", PUB_A)])
    assert "jetstream" not in off  # unchanged for the dev stack and old boxes
    on = render_accounts([NodeAccount("aaa111", PUB_A)], jetstream_max_bytes=4 << 30)
    assert on.count("jetstream:") == 1
    assert "jetstream: {max_mem: 0, max_file: 4294967296, max_streams: 32, max_consumers: 128}" in on
    assert on.index("jetstream:") < on.index("NODE_aaa111")
    assert render_accounts([NodeAccount("aaa111", PUB_A)], jetstream_max_bytes=4 << 30) == on  # deterministic


def test_store_state_ok_degraded_unavailable(tmp_path):
    assert streams.store_state(None)["state"] == "unavailable"
    assert streams.store_state(tmp_path / "missing")["state"] == "unavailable"
    ok = streams.store_state(tmp_path, min_free_bytes=1, min_free_fraction=0.0)
    assert ok["state"] == "ok" and ok["free_bytes"] > 0
    full = streams.store_state(tmp_path, min_free_bytes=1 << 62)
    assert full["state"] == "degraded" and "nearly full" in full["reason"]


def fake_store(tmp_path, max_bytes=4 << 30, floor=1):
    store = object.__new__(AppStore)
    fab = FabricSettings(jetstream_max_bytes=max_bytes, jetstream_path=tmp_path)
    store.gw = SimpleNamespace(settings=SimpleNamespace(section=lambda cls: fab))
    return store


def test_install_is_refused_for_a_bad_declaration(tmp_path):
    with pytest.raises(ApiError) as e:
        fake_store(tmp_path)._check_streams(entry_for(m({**GOOD, "maxBytes": 1})), "app.install")
    assert e.value.status == 409 and e.value.reason == "invalid_stream"


def test_install_is_refused_when_jetstream_is_off_or_degraded(tmp_path, monkeypatch):
    app = entry_for(m(GOOD))
    with pytest.raises(ApiError) as e:
        fake_store(tmp_path, max_bytes=0)._check_streams(app, "app.install")
    assert e.value.reason == "jetstream_unavailable"
    monkeypatch.setattr(streams, "MIN_FREE_BYTES", 1 << 62)
    with pytest.raises(ApiError) as e:
        fake_store(tmp_path)._check_streams(app, "app.install")
    assert e.value.reason == "jetstream_degraded"


def test_apps_without_streams_never_need_jetstream(tmp_path):
    fake_store(tmp_path, max_bytes=0)._check_streams(entry_for({}), "app.install")
