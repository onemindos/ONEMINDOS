# SPDX-License-Identifier: Apache-2.0
"""Offline content manager (NMD-02, #127): packs and Wikipedia sizes from the Kiwix catalogue, the
size shown before every download, owner-approved changes, and the auto-update in the maintenance
window. The catalogue answers are real: fixtures/kiwix-opds/*.xml were fetched from
https://opds.library.kiwix.org/catalog/v2/entries?name=<name>&count=50 on 2026-11-19."""

from __future__ import annotations

import itertools
import shutil
import urllib.parse
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, OWNER, ScriptedExecutor, action_body, write_scan
from onemind_core.app import create_app
from onemind_core.content.kiwix import CatalogError, KiwixCatalog, book_key, parse_feed
from onemind_core.content.service import split_stem

REPO = Path(__file__).resolve().parents[2]
OPDS = Path(__file__).parent / "fixtures" / "kiwix-opds"
EMPTY_FEED = b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
HAM = "stack_exchange/ham.stackexchange.com_en_all_2026-10.zim"
MED_MAXI = "wikipedia/wikipedia_en_medicine_maxi_2026-10.zim"
MED_MAXI_OLD = "wikipedia/wikipedia_en_medicine_maxi_2026-06.zim"
DEFAULT_BOOK = "wikipedia/wikipedia_en_climate-change_mini_2026-10.zim"
HAM_BYTES, MED_MAXI_BYTES = 77109248, 1864210432
_keys = itertools.count()


class Feeds:
    """The catalogue, answered from the recorded feeds; `down` makes it unreachable."""

    def __init__(self):
        self.down = False
        self.calls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        if self.down:
            raise CatalogError("the Kiwix catalogue cannot be reached (test)")
        name = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["name"][0]
        f = OPDS / f"{name}.xml"
        return f.read_bytes() if f.exists() else EMPTY_FEED


@pytest.fixture
def box(settings, clock):
    shutil.copytree(REPO / "apps" / "kiwix", settings.apps_dir / "kiwix")
    write_scan(settings.apps_dir / "kiwix", clock.now - timedelta(days=1))
    app = create_app(settings, clock=clock, executor=ScriptedExecutor())
    feeds = Feeds()
    app.state.content.catalog = KiwixCatalog(fetch=feeds)
    with TestClient(app) as c:
        c.feeds = feeds
        yield c


def approve(client, action_id: str) -> dict:
    r = client.post(f"/v1/actions/{action_id}/approve", headers=OWNER)
    assert r.status_code == 200, r.text
    return r.json()


def file_action(client, clock, type_: str, params: dict) -> dict:
    body = action_body(clock, key=f"t-{next(_keys)}")
    body["type"], body["params"] = type_, params
    r = client.post("/v1/actions", json=body, headers=OWNER)
    assert r.status_code == 201, r.text
    return approve(client, r.json()["id"])


def install_kiwix(client, clock) -> None:
    assert file_action(client, clock, "app.install", {"app_id": "kiwix"})["state"] == "succeeded"


def zims(client) -> list[str]:
    return [b["path"] for b in client.get("/v1/content", headers=OWNER).json()["library"]]


def change(client, add=(), remove=(), size=None):
    body = {"add": list(add), "remove": list(remove)}
    plan = client.post("/v1/content/plan", json=body, headers=OWNER)
    assert plan.status_code == 200, plan.text
    shown = plan.json()["download_bytes"] if size is None else size
    return plan.json(), client.post("/v1/content/changes", headers=OWNER,
                                    json={**body, "download_bytes": shown, "idempotency_key": f"c-{next(_keys)}"})


def test_view_lists_library_and_packs_without_network(box):
    r = box.get("/v1/content", headers=OWNER)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["app"] == {"id": "kiwix", "in_catalog": True, "status": "not_installed"}
    assert v["library"] == [{"path": DEFAULT_BOOK, "name": "wikipedia_en_climate-change", "flavour": "mini", "date": "2026-10"}]
    assert {p["id"] for p in v["packs"]} == {"medical", "survival", "education", "radio"}
    assert v["auto_update"]["enabled"] is False and v["auto_update"]["window_id"] == "win_nightly"
    assert box.feeds.calls == []
    for who in (ADULT, AGENT):
        assert box.get("/v1/content", headers=who).status_code == 403


def test_wikipedia_sizes_per_language(box):
    r = box.get("/v1/content/wikipedia", params={"lang": "en"}, headers=OWNER)
    assert r.status_code == 200, r.text
    books = r.json()["books"]
    assert [b["flavour"] for b in books] == ["mini", "nopic", "maxi"]  # smallest first
    assert all(b["size_bytes"] > 0 and b["path"].startswith("wikipedia/wikipedia_en_all_") for b in books)
    assert box.get("/v1/content/wikipedia", params={"lang": "EN/../x"}, headers=OWNER).status_code == 422


def test_pack_downloads_updates_and_is_removed(box, clock):
    install_kiwix(box, clock)
    radio = {"name": "ham.stackexchange.com_en_all", "flavour": ""}
    med = {"name": "wikipedia_en_medicine", "flavour": "maxi"}

    # Size before the download, and a change sent with a stale size is refused.
    plan, r = change(box, add=[radio, med], size=1)
    assert plan["download_bytes"] == HAM_BYTES + MED_MAXI_BYTES
    assert [d["path"] for d in plan["downloads"]] == [HAM, MED_MAXI]
    assert r.status_code == 409 and r.json()["reason"] == "size_changed"

    # Download: the change is an app.configure of Kiwix waiting for the owner.
    _, r = change(box, add=[radio, med])
    assert r.status_code == 201, r.text
    action = r.json()["action"]
    assert action["type"] == "app.configure" and action["state"] == "awaiting_approval"
    assert box.get("/v1/content", headers=OWNER).json()["pending_action_id"] == action["id"]
    approve(box, action["id"])
    assert zims(box) == [DEFAULT_BOOK, HAM, MED_MAXI]
    settings = box.get("/v1/apps/kiwix/settings", headers=OWNER).json()["values"]
    assert settings["zims"] == f"{DEFAULT_BOOK} {HAM} {MED_MAXI}"
    radio_pack = next(p for p in box.get("/v1/content", headers=OWNER).json()["packs"] if p["id"] == "radio")
    assert [b["in_library"] for b in radio_pack["books"]] == [True, False, False]
    plan, r = change(box, add=[radio])
    assert plan["changed"] is False and r.status_code == 409  # already there: nothing to download

    # Update: an older release in the library is replaced in place by the catalogue's newest.
    file_action(box, clock, "app.configure", {"app_id": "kiwix", "settings": {"zims": f"{HAM} {MED_MAXI_OLD}"}})
    up = box.get("/v1/content/updates", headers=OWNER).json()
    assert up["zims_after"] == [HAM, MED_MAXI] and up["removed"] == [MED_MAXI_OLD]
    assert up["download_bytes"] == MED_MAXI_BYTES

    # Remove: the book stops being served; nothing to download.
    plan, r = change(box, remove=[radio])
    assert plan["download_bytes"] == 0 and plan["removed"] == [HAM]
    approve(box, r.json()["action"]["id"])
    assert zims(box) == [MED_MAXI_OLD]


def test_auto_update_requests_inside_the_window_and_never_approves(box, clock):
    install_kiwix(box, clock)
    file_action(box, clock, "app.configure", {"app_id": "kiwix", "settings": {"zims": MED_MAXI_OLD}})
    svc = box.app.state.content
    assert box.put("/v1/content/auto-update", json={"enabled": True, "window_id": "win_nope"}, headers=OWNER).status_code == 422
    assert box.put("/v1/content/auto-update", json={"enabled": True}, headers=ADULT).status_code == 403
    r = box.put("/v1/content/auto-update", json={"enabled": True, "window_id": "win_nightly"}, headers=OWNER)
    assert r.status_code == 200 and r.json()["enabled"] is True

    assert svc.tick() is None  # 22:00 UTC: outside the nightly 02:00-05:00 window
    clock.advance(5 * 3600)  # 03:00
    assert "waiting for the owner" in svc.tick()
    au = box.get("/v1/content", headers=OWNER).json()["auto_update"]
    assert au["last_download_bytes"] == MED_MAXI_BYTES and au["window_open"] is True
    action = box.get(f"/v1/actions/{au['last_action_id']}", headers=OWNER).json()
    assert action["state"] == "awaiting_approval"
    assert action["requested_by"] == {"id": "automation:content-update", "kind": "automation"}
    assert action["params"]["settings"] == {"zims": MED_MAXI}
    clock.advance(600)
    assert svc.tick() is None  # once per window
    approve(box, action["id"])
    assert zims(box) == [MED_MAXI]


def _auto_update_on(box, clock):
    install_kiwix(box, clock)
    file_action(box, clock, "app.configure", {"app_id": "kiwix", "settings": {"zims": MED_MAXI_OLD}})
    r = box.put("/v1/content/auto-update", json={"enabled": True, "window_id": "win_nightly"}, headers=OWNER)
    assert r.status_code == 200
    clock.advance(5 * 3600)  # 03:00, inside the window
    return box.app.state.content


def test_auto_update_does_not_refile_after_the_owner_declines(box, clock):
    svc = _auto_update_on(box, clock)
    assert "waiting for the owner" in svc.tick()
    first = box.get("/v1/content", headers=OWNER).json()["auto_update"]["last_action_id"]
    assert box.post(f"/v1/actions/{first}/deny", headers=OWNER).status_code == 200
    clock.advance(24 * 3600)  # next nightly window
    result = svc.tick()
    assert "declined" in result and "idempotency_key" not in result
    au = box.get("/v1/content", headers=OWNER).json()["auto_update"]
    assert au["last_action_id"] is None
    clock.advance(24 * 3600)
    assert "declined" in svc.tick()
    filed = [a for a in box.get("/v1/actions", headers=OWNER).json() if a["requested_by"]["id"] == "automation:content-update"]
    assert len(filed) == 1


def test_auto_update_files_again_after_a_request_expires(box, clock):
    svc = _auto_update_on(box, clock)
    assert "waiting for the owner" in svc.tick()
    first = box.get("/v1/content", headers=OWNER).json()["auto_update"]["last_action_id"]
    clock.advance(24 * 3600)  # the 24 h request expires unanswered
    result = svc.tick()
    assert "waiting for the owner" in result, result
    second = box.get("/v1/content", headers=OWNER).json()["auto_update"]["last_action_id"]
    assert second and second != first
    assert box.get(f"/v1/actions/{first}", headers=OWNER).json()["state"] == "expired"
    assert box.get(f"/v1/actions/{second}", headers=OWNER).json()["state"] == "awaiting_approval"
    clock.advance(24 * 3600)  # expires again: still not stuck
    assert "waiting for the owner" in svc.tick()


def test_catalogue_down_blocks_downloads_not_removals(box, clock):
    install_kiwix(box, clock)
    box.feeds.down = True
    r = box.post("/v1/content/plan", json={"add": [{"name": "phet_en_all"}]}, headers=OWNER)
    assert r.status_code == 503 and r.json()["reason"] == "catalog_unreachable"
    r = box.post("/v1/content/plan", json={"remove": [{"name": "wikipedia_en_climate-change", "flavour": "mini"}]},
                 headers=OWNER)
    assert r.status_code == 200 and r.json()["zims_after"] == []
    r = box.post("/v1/content/plan", json={"add": [{"name": "not_a_real_book"}]}, headers=OWNER)
    assert r.status_code == 503
    box.feeds.down = False
    r = box.post("/v1/content/plan", json={"add": [{"name": "not_a_real_book"}]}, headers=OWNER)
    assert r.status_code == 422 and r.json()["reason"] == "not_in_catalog"


def test_without_kiwix_in_the_catalogue(client):
    assert client.get("/v1/content", headers=OWNER).json()["app"]["in_catalog"] is False
    r = client.post("/v1/content/plan", json={"add": []}, headers=OWNER)
    assert r.status_code == 409 and r.json()["reason"] == "kiwix_missing"


def test_feed_parsing_and_book_keys():
    books = parse_feed((OPDS / "wikipedia_en_medicine.xml").read_bytes())
    assert {(b.flavour, b.path) for b in books} >= {("maxi", MED_MAXI)}
    with pytest.raises(CatalogError):
        parse_feed(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><feed/>')
    with pytest.raises(CatalogError):
        parse_feed(b"<html>moved</html>")
    assert book_key(MED_MAXI) == book_key(MED_MAXI_OLD) == "wikipedia/wikipedia_en_medicine_maxi"
    assert split_stem("wikipedia_en_medicine_maxi") == ("wikipedia_en_medicine", "maxi")
    assert split_stem("ham.stackexchange.com_en_all") == ("ham.stackexchange.com_en_all", "")
