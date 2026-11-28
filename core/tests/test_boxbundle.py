# SPDX-License-Identifier: Apache-2.0
"""Box export and import, phase 1 (docs/architecture/BOX-EXPORT-IMPORT.md): the manifest and layer a.

The round trip: box A's settings -> layer bytes -> manifest -> read back and checked -> written to an empty
box B -> box B's box settings and update policy equal box A's (destinations and the content tier are
left for the owner, so B has none). Plus the refusals that keep an import safe.
"""

import json
from copy import deepcopy
from datetime import UTC, datetime

import pytest
import yaml

from onemind_core.automation import updatepolicy
from onemind_core.backups import store as backups_store
from onemind_core.backups.store import BackupsRepository, ContentTierRow, DestinationRow
from onemind_core.boxbundle import box_config, config_export, manifest
from onemind_core.boxbundle.manifest import BundleRefused, Source
from onemind_core.ledger import make_engine
from onemind_core.onboarding import SCHEMA as ONBOARDING, OnboardingService
from onemind_core.store import Database, migrate

NOW = datetime(2026, 11, 26, 15, 0, tzinfo=UTC)
OWNER = {"id": "owner", "kind": "person", "role": "owner"}
YES = lambda window_id: True  # noqa: E731
SCHEMAS = [ONBOARDING, updatepolicy.SCHEMA, backups_store.SCHEMA]


@pytest.fixture
def make_box(tmp_path):
    engines = []

    def make(name: str) -> Database:
        engine = make_engine(f"sqlite:///{tmp_path / name}.db")
        engines.append(engine)
        migrate(engine, SCHEMAS)
        return Database(engine)

    yield make
    for engine in engines:
        engine.dispose()


def set_up(db: Database) -> None:
    OnboardingService(db).save({"box_name": "hub", "time_zone": "America/New_York", "backup_choice": "s3",
                                "backup_destination_id": "dst_0123456789abcdef"})
    body = updatepolicy.UpdatePolicyBody(cool_off_hours=72, same_major_only=False).model_dump()
    updatepolicy.UpdatePolicyRepository(db).put(now=NOW, doc=body, updated_by=OWNER)
    repo = BackupsRepository(db)
    repo.add_destination(DestinationRow(id="dst_0123456789abcdef", kind="s3", label="Offsite", is_primary=True,
                                        append_only=False, config={"endpoint": "s3.example.test", "bucket": "box",
                                                                   "secret_key": "must-not-travel",
                                                                   "Secret_Key": "must-not-travel",
                                                                   "auth": {"password": "must-not-travel"}},
                                        action_id=None, created_at=NOW))
    repo.add_destination(DestinationRow(id="dst_fedcba9876543210", kind="usb", label="USB disk", is_primary=False,
                                        append_only=False, config={"usb_uuid": "1234-ABCD"}, action_id=None,
                                        created_at=NOW))
    repo.set_content_tier(ContentTierRow(app_id="jellyfin", size_bytes=10, action_id="a1", enabled_at=NOW), "jellyfin")


def bundle_of(db: Database) -> tuple[dict, dict[str, bytes]]:
    layer, excluded = box_config.layer(db)
    doc = manifest.build_manifest(Source("box-a", "hub", "0.1.0", "amd64", 3), [layer], now=NOW, excluded=excluded)
    return doc, {layer.entry["path"]: layer.data}


def test_round_trip_to_an_empty_box(make_box):
    a, b = make_box("a"), make_box("b")
    set_up(a)
    doc, files = bundle_of(a)

    # What would travel: the manifest and the layer bytes, read back on box B.
    read = manifest.check_manifest(json.loads(json.dumps(doc)))
    assert not read.newer_minor and read.unknown_layers == []
    entry = read.manifest["layers"][0]
    manifest.check_layer(entry, files[entry["path"]])
    checked = box_config.check(json.loads(files[entry["path"]]))
    assert checked.skipped == []

    before = box_config.collect(b)[0]
    changes = {(c["section"], c["field"]): c["action"] for c in box_config.plan(before, checked)}
    assert changes[("box", "box_name")] == "change"
    assert changes[("updates", "policy")] == "change"
    assert changes[("backups", "destination dst_0123456789abcdef")] == "needs_owner"
    assert changes[("backups", "content_tier_apps")] == "needs_owner"

    written = box_config.apply(b, checked, now=NOW, by=OWNER, window_exists=YES)
    assert written == ["box.box_name", "box.time_zone", "updates.policy"]
    after = box_config.collect(b)[0]
    assert after["box"] == {"box_name": "hub", "time_zone": "America/New_York"}
    assert after["updates"] == checked.doc["updates"]
    assert after["backups"]["destinations"] == []  # credentials are typed again; never written by apply

    # Box B now exports the same box settings; a second apply writes nothing.
    assert box_config.apply(b, checked, now=NOW, by=OWNER, window_exists=YES) == []
    assert {(c["section"], c["field"]): c["action"] for c in box_config.plan(after, checked)}[("box", "box_name")] == "same"


def test_legacy_bundle_off_hours_compare_without_rewriting_the_policy(make_box):
    box = make_box("a")
    set_up(box)
    repo = updatepolicy.UpdatePolicyRepository(box)
    policy = repo.get()["doc"]
    policy["ai_schedule"]["off"][0]["days"] = None
    repo.put(now=NOW, doc=policy, updated_by=OWNER)
    current, _ = box_config.collect(box)
    legacy, _ = box_config.collect(box)
    legacy["updates"] = policy

    checked = box_config.check(legacy)
    assert checked.doc["updates"] == current["updates"]
    assert box_config.apply(box, checked, now=NOW, by=OWNER, window_exists=YES) == []
    assert repo.get()["doc"] == policy


def test_layer_bytes_are_canonical_and_never_hold_credentials(make_box):
    a = make_box("a")
    set_up(a)
    doc, files = bundle_of(a)
    data = files["layers/box_config.json"]
    assert b"must-not-travel" not in data and b"secret_key" not in data
    assert data == manifest.canonical(json.loads(data))
    left_out = {e["what"] for e in doc["excluded"]}
    assert {"backup destination dst_0123456789abcdef: secret_key", "backup destination dst_0123456789abcdef: Secret_Key",
            "backup destination dst_0123456789abcdef: auth"} <= left_out
    # Logically equal documents give the same bytes whatever the key order.
    assert manifest.canonical({"b": 1, "a": [2, {"d": 3, "c": 4}]}) == manifest.canonical({"a": [2, {"c": 4, "d": 3}], "b": 1})
    exclusions = {e["what"]: e["reason"] for e in doc["excluded"]}
    assert "gateway never holds or exports passkey private keys" in exclusions["passkey private keys"]
    assert "OneMind's release signing keys" in exclusions
    # Same box, same settings: same bytes and checksum, whatever the bundle id or time.
    assert box_config.layer(a)[0].entry["sha256"] == doc["layers"][0]["sha256"]


def test_empty_box_exports_a_valid_layer(make_box):
    layer, excluded = box_config.layer(make_box("fresh"))
    doc = json.loads(layer.data)
    assert doc["box"] == {"box_name": None, "time_zone": None}
    assert doc["updates"] is None and excluded == []
    checked = box_config.check(doc)
    assert all(c["action"] in ("keep", "same") for c in box_config.plan(doc, checked))


def test_a_changed_layer_is_refused(make_box):
    a = make_box("a")
    set_up(a)
    doc, files = bundle_of(a)
    entry = doc["layers"][0]
    tampered = files[entry["path"]].replace(b'"hub"', b'"hux"')
    with pytest.raises(BundleRefused, match="checksum"):
        manifest.check_layer(entry, tampered)
    with pytest.raises(BundleRefused, match="size"):
        manifest.check_layer(entry, files[entry["path"]] + b" ")


def test_versions_newer_minor_is_read_newer_major_is_refused(make_box):
    a = make_box("a")
    set_up(a)
    doc, _ = bundle_of(a)
    newer = json.loads(json.dumps(doc))
    newer["format"]["minor"] = 4
    newer["future_field"] = {"x": 1}
    newer["layers"].append({**newer["layers"][0], "id": "printers", "path": "layers/printers.json",
                            "schema": "onemind.io/box-bundle/printers/v1"})
    read = manifest.check_manifest(newer)
    assert read.newer_minor and read.unknown_layers == ["printers"] and read.unknown_fields == ["future_field"]
    assert [entry["id"] for entry in read.manifest["layers"]] == ["box_config"]

    newer["format"]["major"] = 2
    with pytest.raises(BundleRefused, match="format 2.x"):
        manifest.check_manifest(newer)
    with pytest.raises(BundleRefused, match="not a OneMind box bundle"):
        manifest.check_manifest({"schema": "something-else"})


def test_fields_from_a_newer_onemind_are_set_aside_not_applied(make_box):
    a, b = make_box("a"), make_box("b")
    set_up(a)
    doc = box_config.collect(a)[0]
    doc["box"]["hostname_suffix"] = "lan"
    doc["backups"]["destinations"][0]["tls_pin"] = "abc"
    doc["box"]["time_zone"] = "Mars/Olympus_Mons"
    checked = box_config.check(doc, newer_minor=True)
    assert checked.skipped == ["box/hostname_suffix", "backups/destinations/0/tls_pin",
                               "box/time_zone (Mars/Olympus_Mons is not installed on this box)"]
    actions = {(c["section"], c["field"]): c["action"] for c in box_config.plan(box_config.collect(b)[0], checked)}
    assert actions[("unknown", "box/hostname_suffix")] == "skipped"
    assert actions[("box", "time_zone")] == "keep"
    with pytest.raises(BundleRefused, match="box name and a time zone"):
        box_config.apply(b, checked, now=NOW, by=OWNER, window_exists=YES)  # an empty box B has no zone of its own to keep


def test_malformed_layers_are_refused():
    with pytest.raises(BundleRefused, match="not a onemind.io/box-bundle/box-config/v1 layer"):
        box_config.check({"schema": "onemind.io/box-bundle/people/v1"})
    bad = {"schema": box_config.LAYER_SCHEMA, "box": {"box_name": "Not A Hostname!", "time_zone": None},
           "updates": None, "backups": {"choice": "later", "destinations": [], "content_tier_apps": []}}
    with pytest.raises(BundleRefused, match="box/box_name"):
        box_config.check(bad)


def test_apply_only_writes_safe_sections(make_box):
    a = make_box("a")
    set_up(a)
    checked = box_config.check(box_config.collect(a)[0])
    with pytest.raises(ValueError, match="backups"):
        box_config.apply(a, checked, now=NOW, by=OWNER, window_exists=YES, sections=frozenset({"box", "backups"}))


def test_manifest_refuses_duplicate_layers_and_naive_times(make_box):
    layer, _ = box_config.layer(make_box("a"))
    with pytest.raises(ValueError, match="twice"):
        manifest.build_manifest(Source("box-a", None, "0.1.0"), [layer, layer], now=NOW)
    with pytest.raises(ValueError, match="time zone"):
        manifest.build_manifest(Source("box-a", None, "0.1.0"), [layer], now=datetime(2026, 1, 1))


def test_a_url_with_a_password_is_left_out(make_box):
    a = make_box("a")
    BackupsRepository(a).add_destination(DestinationRow(
        id="dst_1111111111111111", kind="rest", label="Peer", is_primary=True, append_only=True,
        config={"url": "https://backup:hunter2" + "@" + "peer.example.test/repo", "user": "backup"}, action_id=None, created_at=NOW))
    layer, excluded = box_config.layer(a)
    assert b"hunter2" not in layer.data
    assert json.loads(layer.data)["backups"]["destinations"][0]["config"] == {"user": "backup"}
    assert [e["what"] for e in excluded] == ["backup destination dst_1111111111111111: url"]


def test_a_refused_apply_writes_nothing(make_box):
    a, b = make_box("a"), make_box("b")
    set_up(a)
    checked = box_config.check(box_config.collect(a)[0])
    with pytest.raises(BundleRefused, match="no update window 'win_nightly'"):
        box_config.apply(b, checked, now=NOW, by=OWNER, window_exists=lambda window_id: False)
    bad = box_config.Checked({**checked.doc, "updates": {**checked.doc["updates"],
                                                         "ai_schedule": {"enabled": True, "tz": "box", "off": [{"days": ["mon"], "start": "25:00", "end": "07:00"}]}}}, [])
    with pytest.raises(BundleRefused, match="updates"):
        box_config.apply(b, bad, now=NOW, by=OWNER, window_exists=YES)
    after = box_config.collect(b)[0]
    assert after["box"] == {"box_name": None, "time_zone": None} and after["updates"] is None


def test_manifest_layer_ids_and_paths_must_line_up(make_box):
    a = make_box("a")
    set_up(a)
    doc, _ = bundle_of(a)
    twice = json.loads(json.dumps(doc))
    twice["layers"].append(dict(twice["layers"][0]))
    with pytest.raises(BundleRefused, match="appears twice"):
        manifest.check_manifest(twice)
    moved = json.loads(json.dumps(doc))
    moved["layers"][0]["path"] = "layers/people.json"
    with pytest.raises(BundleRefused, match="must be at layers/box_config.json"):
        manifest.check_manifest(moved)


def test_a_bundle_with_only_newer_layers_says_update_first(make_box):
    a = make_box("a")
    set_up(a)
    doc, _ = bundle_of(a)
    newer = json.loads(json.dumps(doc))
    newer["format"]["minor"] = 7
    newer["layers"] = [{**newer["layers"][0], "id": "printers", "path": "layers/printers.json"}]
    with pytest.raises(BundleRefused, match="update this box first"):
        manifest.check_manifest(newer)


def test_settings_yaml_is_deterministic_and_omits_destination_secrets(make_box):
    db = make_box("config")
    set_up(db)
    repo = updatepolicy.UpdatePolicyRepository(db)
    policy = repo.get()["doc"]
    policy["ai_schedule"]["off"][0]["future_credential"] = "must-not-travel"
    repo.put(now=NOW, doc=policy, updated_by=OWNER)
    text = config_export.export_settings(db)
    assert text == config_export.export_settings(db)
    doc = yaml.safe_load(text)
    assert doc["schema"] == config_export.SETTINGS_SCHEMA
    assert doc["box"] == {"box_name": "hub", "time_zone": "America/New_York"}
    assert doc["updates"]["cool_off_hours"] == 72
    assert doc["updates"]["ai_schedule"]["off"][0]["start"] == "23:00"
    assert doc["backups"] == {"choice": "s3", "content_tier_apps": ["jellyfin"]}
    assert "must-not-travel" not in text
    assert "secret_key" not in text
    assert "future_credential" not in text
    assert "s3.example.test" not in text


def test_secret_schema_marker_overrides_cleartext_permission(make_box, monkeypatch):
    db = make_box("marked")
    set_up(db)
    # Even if a later change opts these fields in, a secret marker takes precedence.
    rules = deepcopy(manifest.schema())
    backups = rules["$defs"]["boxConfig"]["properties"]["backups"]["properties"]
    destinations = backups["destinations"]
    destinations["x-config-export"] = True
    destinations["items"]["x-config-export"] = True
    fields = destinations["items"]["properties"]
    assert fields["config"]["x-secret"] is True
    fields["config"]["x-config-export"] = True
    fields["label"]["x-config-export"] = True
    fields["id"]["x-config-export"] = True
    fields["id"]["writeOnly"] = True
    monkeypatch.setattr(config_export, "schema", lambda: rules)

    doc = yaml.safe_load(config_export.export_settings(db))
    assert doc["backups"]["destinations"] == []

    # Test the field markers with a direct item schema after checking the composed case.
    del destinations["items"]["allOf"]
    doc = yaml.safe_load(config_export.export_settings(db))
    assert doc["backups"]["destinations"] == [{"label": "Offsite"}, {"label": "USB disk"}]


def test_real_schema_cleartext_annotations_and_secret_sentinels(make_box, monkeypatch):
    rules = manifest.schema()
    annotated = []

    def check(rule, ancestors_exported=True):
        exported = rule.get("x-config-export") is True
        marked = rule.get("x-secret") or rule.get("writeOnly")
        assert not (marked and exported)
        assert not exported or ancestors_exported
        if marked:
            annotated.append(rule)
        for keyword in ("properties", "patternProperties", "dependentSchemas"):
            for field in rule.get(keyword, {}).values():
                check(field, ancestors_exported and exported)
        for keyword in ("items", "additionalProperties", "contains", "if", "then", "else", "not"):
            if isinstance(child := rule.get(keyword), dict):
                check(child, ancestors_exported and exported)
        for keyword in ("oneOf", "anyOf", "allOf", "prefixItems"):
            for field in rule.get(keyword, ()):
                check(field, ancestors_exported and exported)
        for field in rule.get("$defs", {}).values():
            check(field)

    check(rules)
    assert annotated, "the invariant should exercise secret-marked fields"

    sentinel = "secret-schema-sentinel"
    injected = []

    def plant(node, rule):
        if rule.get("x-secret") or rule.get("writeOnly"):
            injected.append(rule)
            return sentinel
        if isinstance(node, dict):
            return {key: plant(node.get(key, {}), child)
                    for key, child in rule.get("properties", {}).items()}
        if isinstance(node, list):
            return [plant(item, rule.get("items", {})) for item in node]
        return node

    db = make_box("sentinels")
    set_up(db)
    doc, _ = box_config.collect(db)
    seeded = plant(doc, rules["$defs"]["boxConfig"])
    assert {id(rule) for rule in injected} == {id(rule) for rule in annotated}
    monkeypatch.setattr(config_export, "collect", lambda _: (seeded, []))
    assert sentinel in json.dumps(seeded)
    assert sentinel not in config_export.export_settings(db)


def test_unknown_fields_are_refused_at_this_version_and_set_aside_at_a_newer_one(make_box):
    a = make_box("a")
    set_up(a)
    doc, _ = bundle_of(a)
    for edit, match in ((lambda d: d.update(extra=1), "extra: not a field"),
                        (lambda d: d["source"].update(extra=1), "source/extra"),
                        (lambda d: d["layers"][0].update(extra=1), "layers/0/extra")):
        odd = json.loads(json.dumps(doc))
        edit(odd)
        with pytest.raises(BundleRefused, match=match):
            manifest.check_manifest(odd)
        odd["format"]["minor"] = 1
        assert manifest.check_manifest(odd).newer_minor
    layer = box_config.collect(a)[0]
    layer["box"]["hostname_suffix"] = "lan"
    with pytest.raises(BundleRefused, match="box/hostname_suffix: not a field"):
        box_config.check(layer)
    assert box_config.check(layer, newer_minor=True).skipped == ["box/hostname_suffix"]


@pytest.mark.parametrize("kind,config", [
    ("s3", {"endpoint": "s3.example.test", "password": "x"}),
    ("usb", {"usb_uuid": "1234-ABCD", "secret_key": "x"}),
    ("rest", {"url": "https://peer.example.test/repo", "token": "x"}),
    ("box", {"url": "https://backup:pw" + "@" + "peer.example.test/repo"}),
    ("s3", {"bucket": {"nested": "x"}}),
    ("usb", {"url": "https://peer.example.test"}),
])
def test_a_crafted_destination_config_is_refused_by_the_schema(make_box, kind, config):
    a = make_box("a")
    set_up(a)
    doc = box_config.collect(a)[0]
    doc["backups"]["destinations"][0].update(kind=kind, config=config)
    with pytest.raises(BundleRefused, match="config"):
        box_config.check(doc)
    for good_kind, good in (("s3", {"endpoint": "s3.example.test", "bucket": "b", "prefix": "p", "region": "r"}),
                         ("usb", {"usb_uuid": "1234-ABCD"}), ("rest", {"url": "https://peer.example.test", "user": "u", "append_only": True})):
        doc["backups"]["destinations"][0].update(kind=good_kind, config=good)
        assert box_config.check(doc).doc["backups"]["destinations"][0]["config"] == good
    doc["backups"]["destinations"][0].update(kind="box", config={"url": "https://peer.example.test", "user": "u"})
    assert box_config.check(doc).doc["backups"]["destinations"][0]["config"]["user"] == "u"


@pytest.mark.parametrize("kind,config,key", [
    ("s3", {"endpoint": "s3.example.test", "storage_class": "GLACIER"}, "storage_class"),
    ("usb", {"usb_uuid": "1234-ABCD", "label_hint": "x"}, "label_hint"),
    ("box", {"url": "https://peer.example.test", "tls_pin": "abc"}, "tls_pin"),
])
def test_a_newer_minor_config_key_is_set_aside_not_fatal(make_box, kind, config, key):
    a = make_box("a")
    set_up(a)
    doc = box_config.collect(a)[0]
    doc["backups"]["destinations"][0].update(kind=kind, config=config)
    with pytest.raises(BundleRefused, match=key):  # at the current minor nothing newer could have written it
        box_config.check(doc)
    checked = box_config.check(doc, newer_minor=True)
    assert checked.skipped == [f"backups/destinations/0/config/{key}"]
    assert key not in checked.doc["backups"]["destinations"][0]["config"]
    assert checked.doc["box"] == doc["box"]


def test_apply_writes_in_one_transaction(make_box, monkeypatch):
    a, b = make_box("a"), make_box("b")
    set_up(a)
    checked = box_config.check(box_config.collect(a)[0])
    real = b.insert()
    calls = []

    def failing_insert():
        def wrap(model):
            calls.append(model.__tablename__)
            if len(calls) == 2:  # the second write fails: the first must not stay
                raise RuntimeError("disk full")
            return real(model)
        return wrap

    monkeypatch.setattr(b, "insert", failing_insert)
    with pytest.raises(RuntimeError, match="disk full"):
        box_config.apply(b, checked, now=NOW, by=OWNER, window_exists=YES)
    monkeypatch.undo()
    assert len(calls) == 2
    after = box_config.collect(b)[0]
    assert after["box"] == {"box_name": None, "time_zone": None} and after["updates"] is None
    assert box_config.apply(b, checked, now=NOW, by=OWNER, window_exists=YES) == ["box.box_name", "box.time_zone", "updates.policy"]
