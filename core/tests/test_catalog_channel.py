# SPDX-License-Identifier: Apache-2.0
"""The signed catalog channel in the gateway: a verified catalog under ONEMIND_CATALOG_DIR adds
and replaces apps without an OS update, and the image's apps stay the fallback.

`onemind catalog sync` (Go, internal/update/catalog.go) does the verifying and unpacking; here
the release folder is laid out by hand, exactly as that code leaves it.
"""

import shutil
from dataclasses import replace
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from conftest import OWNER, make_client
from onemind_core.catalog import Catalog


def _release(channel: Path, version: str, apps: dict[str, Path | None], *, version_label: str | None = None) -> Path:
    """Lay out channel/releases/<version>/apps/<id>/ (copy of a fixture app, or garbage) and point `current` at it."""
    rel = channel / "releases" / version
    for app_id, src in apps.items():
        dst = rel / "apps" / app_id
        if src is None:
            dst.mkdir(parents=True)
            (dst / "onemind.app.yaml").write_text("not: [valid")
            continue
        shutil.copytree(src, dst)
        doc = yaml.safe_load((dst / "onemind.app.yaml").read_text())
        doc["metadata"]["id"] = app_id
        if version_label:
            doc["metadata"]["version"] = version_label
        (dst / "onemind.app.yaml").write_text(yaml.safe_dump(doc, sort_keys=False))
    link = channel / "current"
    if link.is_symlink():
        link.unlink()
    link.symlink_to(Path("releases") / version)
    return rel


def test_channel_adds_an_app_and_replaces_one_without_touching_the_image(settings, tmp_path):
    channel = tmp_path / "chan"
    before = set(Catalog(settings.apps_dir).load())
    assert "brand-new" not in before
    _release(channel, "1.1", {"brand-new": settings.apps_dir / "whoami", "whoami": settings.apps_dir / "whoami"}, version_label="9.9.9")
    cat = Catalog(settings.apps_dir, channel_dir=channel)
    apps = cat.load()
    assert set(apps) == before | {"brand-new"}
    assert str(apps["whoami"].manifest["metadata"]["version"]) == "9.9.9"  # channel copy wins
    assert apps["whoami"].dir.is_relative_to((channel / "releases").resolve())
    # The image folder was not modified: without the channel the old copy is back.
    assert str(Catalog(settings.apps_dir).load()["whoami"].manifest["metadata"]["version"]) != "9.9.9"


def test_without_a_channel_the_image_catalog_is_used(settings, tmp_path):
    cat = Catalog(settings.apps_dir, channel_dir=tmp_path / "missing")
    assert set(cat.load()) == set(Catalog(settings.apps_dir).load())


def test_bad_channel_entry_never_hides_the_image_app(settings, tmp_path):
    channel = tmp_path / "chan"
    _release(channel, "1.1", {"whoami": None})
    cat = Catalog(settings.apps_dir, channel_dir=channel)
    apps = cat.load()
    assert "whoami" in apps and apps["whoami"].dir == settings.apps_dir / "whoami"
    assert "channel/whoami" in cat.errors


def test_current_link_cannot_leave_the_channel_folder(settings, tmp_path):
    channel = tmp_path / "chan"
    evil = tmp_path / "elsewhere"
    shutil.copytree(settings.apps_dir / "whoami", evil / "apps" / "intruder")
    channel.mkdir()
    (channel / "releases").mkdir()
    (channel / "current").symlink_to(evil)
    assert "intruder" not in Catalog(settings.apps_dir, channel_dir=channel).load()


def test_new_release_is_picked_up_without_restart(settings, tmp_path):
    channel = tmp_path / "chan"
    _release(channel, "1.1", {"first": settings.apps_dir / "whoami"})
    cat = Catalog(settings.apps_dir, channel_dir=channel)
    assert "first" in cat.load() and "second" not in cat.load()
    _release(channel, "1.2", {"first": settings.apps_dir / "whoami", "second": settings.apps_dir / "whoami"})
    assert "second" in cat.load()


def test_market_api_lists_a_channel_app(settings, clock, tmp_path):
    channel = tmp_path / "chan"
    _release(channel, "1.1", {"brand-new": settings.apps_dir / "whoami"})
    with make_client(replace(settings, catalog_dir=channel), clock) as client:
        r = client.get("/v1/apps", headers=OWNER)
        assert r.status_code == 200
        assert "brand-new" in {a["id"] for a in r.json()}
