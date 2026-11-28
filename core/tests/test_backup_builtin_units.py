# SPDX-License-Identifier: Apache-2.0
"""Backup units of the native built-ins (#616): the set, the export and the restore on a fresh box.

Each built-in's descriptor names its tables and folders (`spec.backup.units`). The backup set is every
switched-on built-in's units plus the gateway database; the export writes them in a portable form and the
restore replays them on a fresh box. The acceptance test backs up Photos and Approvals, wipes the box,
restores and reads the same rows and the same photo back (Work and Notes join when they land).
Runs on SQLite, and on PostgreSQL with ONEMIND_TEST_DB_URL.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from conftest import AGENT, OWNER, action_body
from onemind_core.app import create_app
from onemind_core.backups import units as bu
from onemind_core.backups.settings import BackupsSettings
from onemind_core.ledger import Base
from onemind_core.photos import PhotosSettings
from onemind_core.sections import load_section
from test_appstore import run
from test_backups import FakeAgent
from test_photos import Phone, blob, photos_settings

PHOTO_TABLES = {"photos_sources", "photos_assets", "photos_blobs", "photos_receipts", "photos_snapshots", "photos_uploads"}


def handles(c: TestClient):
    return c.app.state.gateway, c.app.state.builtins


def rows(gw, tables) -> dict[str, list[dict]]:
    out = {}
    with gw.db.engine.connect() as conn:
        for name in sorted(tables):
            t = Base.metadata.tables[name]
            out[name] = sorted((dict(r._mapping) for r in conn.execute(select(t))), key=repr)
    return out


@pytest.fixture
def box_a(settings, clock, tmp_path):
    """A box with a photo backed up from a phone and an approval waiting: the data to carry over."""
    with TestClient(create_app(photos_settings(settings, tmp_path / "photos-a"), clock=clock)) as c:
        phone = Phone(c, OWNER)
        data = blob(7, 300 * 1024)
        assert phone.upload(phone.key("asset-1"), data)["deduped"] is False
        r = c.post("/v1/actions", json=action_body(clock, key="carry-over"), headers=OWNER)
        assert r.status_code == 201, r.text
        yield c, phone, data, r.json()


def fresh_box(settings, clock, tmp_path, name="b"):
    """The same image on a wiped disk: an empty database and an empty photos folder."""
    if os.environ.get("ONEMIND_TEST_DB_URL"):
        pytest.skip("two boxes need two databases; the PostgreSQL leg shares one")
    db = f"sqlite:///{tmp_path / f'onemind-{name}.db'}"
    s = replace(photos_settings(settings, tmp_path / f"photos-{name}"), db_url=db,
                audit_path=tmp_path / name / "audit.jsonl")
    return create_app(s, clock=clock)


# ---- the set ---------------------------------------------------------------------------------------------

def test_the_set_is_every_switched_on_built_in_plus_the_gateway_database(box_a, tmp_path):
    c, *_ = box_a
    gw, reg = handles(c)
    units = {u["unit"]: u for u in bu.unit_set(gw, reg)}
    assert units["gateway"]["kind"] == "database" and units["gateway"]["snapshot_unit"] == "system"
    photos = units["builtin:photos"]
    assert set(photos["tables"]) == PHOTO_TABLES and photos["problems"] == []
    assert photos["dirs"] == [{"name": "ONEMIND_PHOTOS_DIR", "path": str(tmp_path / "photos-a"), "carried": False}]
    assert "actions" in units["builtin:approvals"]["tables"]
    assert {f"builtin:{d.id}" for d in reg.enabled()} == set(units) - {"gateway"}

    st = c.get("/v1/backups/status", headers=AGENT).json()
    shown = {u["unit"]: u for u in st["builtin_units"]}
    assert set(shown) == set(units)
    assert shown["builtin:photos"]["dirs"] == [{"name": "ONEMIND_PHOTOS_DIR", "configured": True, "carried": False}]
    assert str(tmp_path) not in json.dumps(st)  # no host path leaves the box through the API


def test_no_built_in_reads_as_in_a_snapshot_until_an_agent_unit_carries_it(box_a, clock):
    """The status must not read as "photos are backed up": with no export folder set, no agent unit
    carries a built-in's export, so every built-in says snapshot_unit null, in_snapshot false, even after
    a good run."""
    c, *_ = box_a
    svc = c.app.state.backups

    def shown():
        return {u["unit"]: u for u in c.get("/v1/backups/status", headers=OWNER).json()["builtin_units"]}

    before = shown()  # backups off: nothing is in a snapshot
    assert all(u["in_snapshot"] is False for u in before.values())
    assert all(u["snapshot_unit"] is None for n, u in before.items() if n != "gateway")

    svc.agent = FakeAgent(clock)
    assert all(u["in_snapshot"] is False for u in shown().values())  # agent on, no snapshot yet
    assert svc.run_backup("manual", "box", None, None)["state"] == "succeeded"
    after = shown()
    assert after["gateway"]["snapshot_unit"] == "system" and after["gateway"]["in_snapshot"] is True
    for name in ("builtin:photos", "builtin:approvals", "builtin:files"):
        if name in after:
            assert after[name]["snapshot_unit"] is None and after[name]["in_snapshot"] is False, after[name]
    assert after["builtin:photos"]["in_snapshot"] is False


# ---- on a box: the export lands in the agent's system unit --------------------------------------------

def wired(c, tmp_path, agent_dirs="", agent_paths=""):
    """The settings onemind-firstboot writes: an export folder the system unit copies, and its folders."""
    svc = c.app.state.backups
    svc.s = replace(svc.s, export_dir=tmp_path / "backup-export", agent_dirs=agent_dirs, agent_paths=agent_paths)
    return svc


def builtins_shown(c):
    return {u["unit"]: u for u in c.get("/v1/backups/status", headers=OWNER).json()["builtin_units"]}


def test_a_box_run_writes_the_export_and_then_the_built_ins_are_in_the_snapshot(box_a, settings, clock, tmp_path):
    c, phone, data, action = box_a
    svc = wired(c, tmp_path)  # the photos folder is set but not carried by the system unit
    svc.agent = FakeAgent(clock)
    assert all(u["in_snapshot"] is False for u in builtins_shown(c).values())

    run_out = svc.run_backup("scheduled", "box", None, None)
    assert run_out["state"] == "succeeded", run_out
    assert {"unit": "builtins", "phase": "pre", "command": bu.EXPORT_FILE, "ok": True,
            "carried": {}} in run_out["hooks"]
    tar = tmp_path / "backup-export" / bu.EXPORT_FILE
    assert oct(tar.stat().st_mode & 0o777) == "0o600" and list(tar.parent.iterdir()) == [tar]

    after = builtins_shown(c)
    assert after["builtin:approvals"]["snapshot_unit"] == "system" and after["builtin:approvals"]["in_snapshot"] is True
    # Photos' rows are in the export, but its folder is in no snapshot: not shown as backed up.
    assert after["builtin:photos"]["in_snapshot"] is False
    assert after["builtin:photos"]["dirs"] == [{"name": "ONEMIND_PHOTOS_DIR", "configured": True, "carried": False}]

    # Carrying the folder from now on does not put it into the snapshot already taken (D-028): only the
    # next run's snapshot holds it.
    wired(c, tmp_path, agent_dirs="ONEMIND_PHOTOS_DIR, ONEMIND_FILES_ROOT")
    assert builtins_shown(c)["builtin:photos"]["in_snapshot"] is False
    clock.advance(3600)
    assert svc.run_backup("scheduled", "box", None, None)["state"] == "succeeded"
    assert builtins_shown(c)["builtin:photos"]["in_snapshot"] is True

    # What the snapshot holds is a working export: it restores on a wiped box.
    with TestClient(fresh_box(settings, clock, tmp_path)) as b:
        assert bu.restore(*handles(b), tar)["rows"] > 0
        assert b.get(f"/v1/actions/{action['id']}", headers=OWNER).status_code == 200


def test_a_library_moved_after_the_snapshot_is_not_reported_in_it(box_a, clock, tmp_path):
    c, *_ = box_a
    svc = wired(c, tmp_path, agent_dirs="ONEMIND_PHOTOS_DIR ONEMIND_FILES_ROOT")
    svc.agent = FakeAgent(clock)
    assert svc.run_backup("scheduled", "box", None, None)["state"] == "succeeded"
    assert builtins_shown(c)["builtin:photos"]["in_snapshot"] is True
    gw = c.app.state.gateway
    gw.settings.sections["photos"] = replace(gw.settings.section(PhotosSettings), dir=tmp_path / "photos-moved")
    assert builtins_shown(c)["builtin:photos"]["in_snapshot"] is False  # the snapshot holds the old folder


def test_a_library_outside_the_agent_paths_is_not_carried(box_a, clock, tmp_path):
    """A relocated library (ONEMIND_PHOTOS_DIR outside every folder the agent copies) is outside the
    backup: shown as not carried and never in a snapshot, even with its name in AGENT_DIRS."""
    c, *_ = box_a
    svc = wired(c, tmp_path, agent_dirs="ONEMIND_PHOTOS_DIR ONEMIND_FILES_ROOT",
                agent_paths=f"{tmp_path / 'backup-export'},{tmp_path / 'gateway' / 'photos'}")
    svc.agent = FakeAgent(clock)
    assert svc.run_backup("scheduled", "box", None, None)["state"] == "succeeded"
    photos = builtins_shown(c)["builtin:photos"]
    assert photos["dirs"] == [{"name": "ONEMIND_PHOTOS_DIR", "configured": True, "carried": False}]
    assert photos["in_snapshot"] is False
    wired(c, tmp_path, agent_dirs="ONEMIND_PHOTOS_DIR", agent_paths=str(tmp_path))  # a parent folder carries it
    clock.advance(3600)
    assert svc.run_backup("scheduled", "box", None, None)["state"] == "succeeded"
    assert builtins_shown(c)["builtin:photos"]["in_snapshot"] is True


def test_a_failed_export_fails_the_built_ins_but_not_the_agent_run(box_a, clock, tmp_path, monkeypatch):
    c, *_ = box_a
    svc = wired(c, tmp_path, agent_dirs="ONEMIND_PHOTOS_DIR ONEMIND_FILES_ROOT")
    svc.agent = FakeAgent(clock)

    def full(*a, **k):
        raise OSError("No space left on device")

    monkeypatch.setattr("onemind_core.backups.service.write_export", full)
    out = svc.run_backup("scheduled", "box", None, None)
    failed = {u["unit"]: u for u in out["units"] if u["state"] == "failed"}
    assert failed["builtin:approvals"]["error"] == "built-in export failed: No space left on device"
    assert out["state"] == "partial"
    sent = [p for k, p, _ in svc.agent.jobs if k == "backup.run"][0]
    assert not [u for u in sent.get("skip_units", []) if u.startswith("builtin:")]  # the system unit still ran
    assert all(u["in_snapshot"] is False for n, u in builtins_shown(c).items() if n != "gateway")


def test_backup_settings_check_the_export_folder_and_names():
    BackupsSettings(export_dir=Path("/data/onemind/gateway/backup-export"), agent_dirs="ONEMIND_FILES_ROOT").validate()
    with pytest.raises(ValueError, match="EXPORT_DIR"):
        BackupsSettings(export_dir=Path("relative")).validate()
    with pytest.raises(ValueError, match="AGENT_DIRS"):
        BackupsSettings(agent_dirs="/data/onemind/files").validate()
    BackupsSettings(agent_paths="/data/onemind/files, /data/onemind/gateway/photos").validate()
    with pytest.raises(ValueError, match="AGENT_PATHS"):
        BackupsSettings(agent_paths="data/onemind/files").validate()


def test_a_switched_off_built_in_leaves_the_set(box_a, clock):
    c, *_ = box_a
    assert run(c, clock, "app.disable", {"app_id": "photos"}).json()["state"] == "succeeded"
    assert "builtin:photos" not in {u["unit"] for u in bu.unit_set(*handles(c))}
    assert "builtin:photos" not in {u["unit"] for u in c.get("/v1/backups/status", headers=OWNER).json()["builtin_units"]}


def test_a_declared_table_the_database_lacks_is_a_problem_and_fails_its_unit_in_a_run(box_a, clock, monkeypatch):
    c, *_ = box_a
    gw, reg = handles(c)
    d = reg.descriptors["settings"]
    spec = {**d.spec, "backup": {"units": [*d.spec["backup"]["units"], {"kind": "table", "name": "settings_gone"}]}}
    monkeypatch.setitem(reg.descriptors, "settings", replace(d, spec=spec))
    unit = next(u for u in bu.unit_set(gw, reg) if u["unit"] == "builtin:settings")
    assert unit["problems"] == ["table settings_gone is not in the gateway database"]

    svc = c.app.state.backups
    svc.agent = FakeAgent(clock)
    out = svc.run_backup("manual", "box", None, None)
    failed = {u["unit"]: u for u in out["units"] if u["state"] == "failed"}
    assert failed["builtin:settings"]["error"] == "table settings_gone is not in the gateway database"
    assert out["state"] == "partial"
    sent = [p for k, p, _ in svc.agent.jobs if k == "backup.run"][0]
    assert "builtin:settings" not in sent.get("skip_units", [])  # the agent only knows its own units


# ---- back up, wipe, restore ------------------------------------------------------------------------------

def test_back_up_wipe_restore_reads_the_same_rows_and_photo(box_a, settings, clock, tmp_path):
    c, phone, data, action = box_a
    gw, reg = handles(c)
    tables = {t for u in bu.unit_set(gw, reg) for t in u.get("tables", [])}
    before = rows(gw, tables)
    assert before["photos_assets"] and any(r["id"] == action["id"] for r in before["actions"])
    out = bu.export(gw, reg, tmp_path / "export")
    by_unit = {u["unit"]: u for u in out["units"]}
    assert {t["name"]: t["rows"] for t in by_unit["builtin:photos"]["tables"]}["photos_assets"] == 1
    assert by_unit["builtin:photos"]["dirs"][0]["state"] == "copied"
    assert oct((tmp_path / "export").stat().st_mode & 0o777) == "0o700"

    app_b = fresh_box(settings, clock, tmp_path)
    gw_b, reg_b = app_b.state.gateway, app_b.state.builtins
    assert all(not v for v in rows(gw_b, tables).values())
    done = bu.restore(gw_b, reg_b, tmp_path / "export")
    assert done["rows"] == sum(len(v) for v in before.values())
    assert rows(gw_b, tables) == before

    with TestClient(app_b) as cb:
        got = cb.get(f"/v1/actions/{action['id']}", headers=OWNER)
        assert got.status_code == 200 and got.json()["state"] == action["state"]
        again = Phone(cb, OWNER)
        assert again.source == phone.source  # the same phone, known again
        assert again.check([(phone.key("asset-1"), data)]) == ["have"]
    library = [p for p in (tmp_path / "photos-b" / "library" / "owner").rglob("*") if p.is_file()]
    assert len(library) == 1 and library[0].read_bytes() == data
    stored = [p for p in (tmp_path / "photos-b" / "library" / ".shared-store").rglob("*") if p.is_file()]
    assert len(stored) == 1 and os.stat(stored[0]).st_ino == os.stat(library[0]).st_ino  # still one copy on disk


@pytest.mark.parametrize("owner_off", [False, True], ids=["photos-on", "photos-off"])
def test_default_hub_box_backup_restores_photo_bytes_and_records(settings, clock, tmp_path, monkeypatch, owner_off):
    app_b = fresh_box(settings, clock, tmp_path)
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "os/rootfs/layers/onemind/usr/lib/onemind"))
    import onemind_firstboot as fb

    paths = fb.Paths(str(tmp_path / "source"))
    system = fb.backup_agent_conf(paths, "box-a")["units"]["system"]
    photo_cfg = load_section(PhotosSettings, {"ONEMIND_DATA_DIR": paths.gateway})
    s = replace(settings, sections={**settings.sections, "photos": photo_cfg})
    snapshot = tmp_path / "snapshot"
    for path in system["paths"]:
        Path(path).mkdir(parents=True)

    class SystemSnapshot(FakeAgent):
        def job(self, kind, params, **kwargs):
            result = super().job(kind, params, **kwargs)
            if kind == "backup.run":
                assert any(u["unit"] == "system" for u in result["units"])
                for path in map(Path, system["paths"]):
                    bu.copy_tree(path, snapshot / path.relative_to(paths.root))
            return result

    with TestClient(create_app(s, clock=clock)) as a:
        phone = Phone(a, OWNER)
        data = blob(8, 7000)
        phone.upload(phone.key("asset-1"), data)
        asset_id = a.get("/v1/photos/library", headers=OWNER).json()["items"][0]["id"]
        before = rows(handles(a)[0], PHOTO_TABLES)
        if owner_off:
            assert run(a, clock, "app.disable", {"app_id": "photos"}).json()["state"] == "succeeded"
            assert a.get("/v1/photos/library", headers=OWNER).status_code == 409
        svc = a.app.state.backups
        svc.s = replace(svc.s, export_dir=Path(paths.backup_export))
        svc.agent = SystemSnapshot(clock)
        assert svc.run_backup("manual", "box", None, None)["state"] == "succeeded"

    shutil.rmtree(paths.root)
    gw_b, reg_b = app_b.state.gateway, app_b.state.builtins
    carried_export = snapshot / Path(paths.backup_export).relative_to(paths.root) / bu.EXPORT_FILE
    bu.restore(gw_b, reg_b, carried_export)
    assert rows(gw_b, PHOTO_TABLES) == before
    carried_photos = snapshot / photo_cfg.dir.relative_to(paths.root)
    assert carried_photos.is_dir(), "the generated system backup did not carry the default Photos folder"
    bu.copy_tree(carried_photos, gw_b.settings.section(PhotosSettings).dir)
    with TestClient(app_b) as b:
        if owner_off:
            assert b.get("/v1/photos/library", headers=OWNER).status_code == 409
            assert run(b, clock, "app.enable", {"app_id": "photos"}).json()["state"] == "succeeded"
        photo = b.get(f"/v1/photos/assets/{asset_id}/content", headers=OWNER)
        assert photo.status_code == 200 and photo.content == data


def test_a_box_that_already_has_rows_is_refused_unless_replace(box_a, settings, clock, tmp_path):
    c, *_ = box_a
    gw, reg = handles(c)
    tables = {t for u in bu.unit_set(gw, reg) for t in u.get("tables", [])}
    before = rows(gw, tables)
    bu.export(gw, reg, tmp_path / "export", include_dirs=False)
    with pytest.raises(bu.RestoreRefused) as e:
        bu.restore(gw, reg, tmp_path / "export")  # the same box: every table already holds rows
    assert any("photos_assets already holds rows" in p for p in e.value.problems)

    with gw.db.engine.begin() as conn:
        conn.execute(Base.metadata.tables["photos_assets"].delete())
    bu.restore(gw, reg, tmp_path / "export", replace=True)
    assert rows(gw, tables) == before


def test_a_damaged_export_is_refused_and_nothing_is_written(box_a, settings, clock, tmp_path):
    c, *_ = box_a
    bu.export(*handles(c), tmp_path / "export")
    f = tmp_path / "export" / "tables" / "photos_assets.jsonl"
    f.write_bytes(f.read_bytes() + b'{"id":"ast_planted"}\n')
    app_b = fresh_box(settings, clock, tmp_path)
    gw_b, reg_b = app_b.state.gateway, app_b.state.builtins
    with pytest.raises(bu.RestoreRefused) as e:
        bu.restore(gw_b, reg_b, tmp_path / "export")
    assert e.value.problems == ["tables/photos_assets.jsonl does not match its checksum"]
    assert not rows(gw_b, {"photos_assets", "actions"})["actions"]
    assert not any(p.is_file() for p in (tmp_path / "photos-b").rglob("*"))


def test_a_table_no_built_in_declares_is_refused(box_a, settings, clock, tmp_path):
    c, *_ = box_a
    bu.export(*handles(c), tmp_path / "export", include_dirs=False)
    m = json.loads((tmp_path / "export" / "manifest.json").read_text())
    src = tmp_path / "export" / "tables" / "photos_blobs.jsonl"
    (tmp_path / "export" / "tables" / "agent_tokens.jsonl").write_bytes(src.read_bytes())
    unit = next(u for u in m["units"] if u["unit"] == "builtin:photos")
    unit["tables"].append({**next(t for t in unit["tables"] if t["name"] == "photos_blobs"), "name": "agent_tokens"})
    (tmp_path / "export" / "manifest.json").write_text(json.dumps(m))
    app_b = fresh_box(settings, clock, tmp_path)
    with pytest.raises(bu.RestoreRefused) as e:
        bu.restore(app_b.state.gateway, app_b.state.builtins, tmp_path / "export")
    assert "photos does not declare table agent_tokens" in e.value.problems


def test_a_folder_that_is_not_empty_is_refused(box_a, settings, clock, tmp_path):
    c, *_ = box_a
    bu.export(*handles(c), tmp_path / "export")
    (tmp_path / "photos-b").mkdir()
    (tmp_path / "photos-b" / "keep.jpg").write_bytes(b"x")
    app_b = fresh_box(settings, clock, tmp_path)
    with pytest.raises(bu.RestoreRefused) as e:
        bu.restore(app_b.state.gateway, app_b.state.builtins, tmp_path / "export")
    assert any("ONEMIND_PHOTOS_DIR" in p and "not empty" in p for p in e.value.problems)
    assert (tmp_path / "photos-b" / "keep.jpg").read_bytes() == b"x"


def test_an_export_from_another_schema_version_is_refused(box_a, settings, clock, tmp_path):
    c, *_ = box_a
    bu.export(*handles(c), tmp_path / "export", include_dirs=False)
    m = json.loads((tmp_path / "export" / "manifest.json").read_text())
    m["schema_versions"]["photos"] += 1
    (tmp_path / "export" / "manifest.json").write_text(json.dumps(m))
    app_b = fresh_box(settings, clock, tmp_path)
    with pytest.raises(bu.RestoreRefused) as e:
        bu.restore(app_b.state.gateway, app_b.state.builtins, tmp_path / "export")
    assert any(p.startswith("photos schema is v") for p in e.value.problems)


def test_export_refuses_a_folder_that_is_not_empty(box_a, tmp_path):
    c, *_ = box_a
    (tmp_path / "export").mkdir()
    (tmp_path / "export" / "x").write_text("x")
    with pytest.raises(ValueError):
        bu.export(*handles(c), tmp_path / "export")


def test_the_tar_stream_round_trips(box_a, settings, clock, tmp_path):
    """The agent's command hook keeps one file: the export as a tar on stdout, replayed from that file."""
    c, *_ = box_a
    gw, reg = handles(c)
    tables = {t for u in bu.unit_set(gw, reg) for t in u.get("tables", [])}
    before = rows(gw, tables)
    with open(tmp_path / "builtin-units.tar", "wb") as f:
        bu.export_tar(gw, reg, f, include_dirs=False)
    app_b = fresh_box(settings, clock, tmp_path)
    bu.restore(app_b.state.gateway, app_b.state.builtins, tmp_path / "builtin-units.tar")
    assert rows(app_b.state.gateway, tables) == before
