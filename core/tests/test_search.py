# SPDX-License-Identifier: Apache-2.0
"""GET /v1/search: one local FTS5 index, providers switched on by descriptors, hits filtered by grants (#611)."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import replace

from onemind_core.search import Asker
from onemind_core.search.index import match_expression

from files_support import ADULT, AGENT, GUEST, OWNER, audit_events, fc, files_root, files_settings, mkdir, ok, rename, upload  # noqa: F401


def search(c, headers, q, **params):
    """The hits (the JSON array body) and the providers searched (the OneMind-Search-Providers header)."""
    r = c.get("/v1/search", headers=headers, params={"q": q, **params})
    hits = ok(r)
    assert isinstance(hits, list), hits
    providers = r.headers["OneMind-Search-Providers"]
    return {"hits": hits, "providers": providers.split(",") if providers else []}


def titles(c, headers, q, **params) -> set[str]:
    return {h["title"] for h in search(c, headers, q, **params)["hits"]}


def seed(c):
    mkdir(c, OWNER, "home:owner", "/Docs")
    ok(upload(c, OWNER, "home:owner", "/Docs", "quarterly-report.txt", b"numbers"), 204)
    mkdir(c, OWNER, "shared", "/Media")
    ok(upload(c, OWNER, "shared", "/Media", "summer-song.txt", b"la la"), 204)
    mkdir(c, OWNER, "shared", "/Private")
    ok(upload(c, OWNER, "shared", "/Private", "summer-plans.txt", b"x"), 204)


def test_files_and_settings_providers_return_hits_with_deep_links(fc):
    seed(fc)
    out = search(fc, OWNER, "quarterly")
    assert out["providers"] == ["files", "settings"]
    [hit] = out["hits"]
    assert (hit["provider"], hit["app_id"], hit["type"], hit["title"]) == ("files", "files", "file", "quarterly-report.txt")
    assert hit["link"] == "onemind://app/files/open?root=home%3Aowner&path=%2FDocs%2Fquarterly-report.txt"
    assert hit["subtitle"] == "Home /Docs" and hit["id"].startswith("fil_")
    media = [(h["type"], h["title"]) for h in search(fc, OWNER, "Media")["hits"]]
    assert media == [("folder", "Media"), ("file", "summer-song.txt")]  # a name match ranks above a path match
    assert titles(fc, OWNER, "summer", types="file") == {"summer-song.txt", "summer-plans.txt"}
    assert titles(fc, OWNER, "summer", types="folder") == set()

    [page] = search(fc, OWNER, "storage quotas")["hits"]
    assert (page["provider"], page["app_id"], page["type"], page["id"]) == ("settings", "files", "page", "files.quotas")
    assert page["link"] == "onemind://app/settings/files/quotas" and page["subtitle"] == "Files settings"
    notes = {h["id"] for h in search(fc, OWNER, "notification")["hits"]}
    assert {"notifications.preferences", "notifications.channels"} <= notes  # every page the descriptor declares
    declared = {f"notifications.{pg['id']}" for pg in fc.app.state.builtins.descriptors["notifications"].spec["settingsPages"]}
    assert notes == declared


def test_index_follows_renames_and_trash(fc):
    seed(fc)
    assert titles(fc, OWNER, "quarterly") == {"quarterly-report.txt"}
    rename(fc, OWNER, "home:owner", "/Docs/quarterly-report.txt", "annual-report.txt")
    assert titles(fc, OWNER, "quarterly") == set()
    assert titles(fc, OWNER, "annual") == {"annual-report.txt"}
    ok(fc.post("/v1/files/ops", headers=OWNER, json={"op": "trash", "root": "home:owner", "path": "/Docs/annual-report.txt"}))
    assert titles(fc, OWNER, "annual") == set()


def test_a_person_or_agent_without_a_folder_grant_sees_no_hit(fc, settings):
    seed(fc)
    assert titles(fc, ADULT, "quarterly") == set()               # another person's Home is private, even to search
    assert titles(fc, ADULT, "summer") == {"summer-song.txt", "summer-plans.txt"}
    assert titles(fc, GUEST, "summer") == {"summer-song.txt", "summer-plans.txt"}  # Shared is readable by guests
    assert titles(fc, AGENT, "summer") == set()                  # no grant, no hit
    assert titles(fc, AGENT, "quarterly") == set()

    r = fc.post("/v1/files/grants", headers=OWNER, json={"subject": {"kind": "agent", "id": "hermes"}, "root": "shared",
                                                         "path": "/Media", "access": "r", "approve": True})
    grant = ok(r, 202)["result"]["grant_id"]
    # The AI app policy (gw.app_filters) keeps every built-in out of an agent's view, as in GET /v1/builtins:
    # a grant alone does not open search to it.
    assert search(fc, AGENT, "summer") == {"hits": [], "providers": []}
    # Under it, the Files provider shows an agent only what its grants cover.
    files = fc.app.state.search.providers()[0]
    agent = next(p for p in fc.app.state.gateway.tokens.principals() if p.kind == "agent")
    hits = list(fc.app.state.search.index.matches('"summer"*', ["files"]))
    seen = files.visible(Asker(agent, None, lambda app_id: True))
    assert {h.title for h in hits if seen(h)} == {"summer-song.txt"}  # inside the granted folder only
    ok(fc.delete(f"/v1/files/grants/{grant}", headers=AGENT))
    seen = files.visible(Asker(agent, None, lambda app_id: True))
    assert not any(seen(h) for h in hits)                         # a revoked grant hides them again

    lines = [e for e in audit_events(settings) if e["event"] == "search.query"]
    assert lines and {e["principal"]["kind"] for e in lines} == {"agent"}  # people's searches are not audited
    assert "summer" not in json.dumps(lines) and "quarterly" not in json.dumps(lines)  # the query text never is
    assert {e["data"]["q_chars"] for e in lines} == {6, 9} and {e["data"]["hits"] for e in lines} == {0}


def test_settings_pages_follow_the_askers_scopes(fc):
    owner = {h["id"] for h in search(fc, OWNER, "settings")["hits"]}
    assert {"files.quotas", "settings.box", "backups.destinations", "updates.update-policy"} <= owner
    guest = {h["id"] for h in search(fc, GUEST, "settings")["hits"]}
    assert guest < owner                                          # only pages whose route the guest's role may read
    assert search(fc, AGENT, "settings")["hits"] == []            # agents do not browse Settings


def test_a_disabled_apps_items_disappear_and_come_back(fc):
    seed(fc)
    registry = fc.app.state.builtins
    assert titles(fc, OWNER, "quarterly") == {"quarterly-report.txt"}
    on = registry.disabled
    registry.disabled = lambda: frozenset({"files"})
    try:
        out = search(fc, OWNER, "quarterly")
        assert out == {"hits": [], "providers": ["settings"]}
        assert search(fc, OWNER, "storage quotas")["hits"] == []  # its Settings page goes with it
    finally:
        registry.disabled = on
    assert titles(fc, OWNER, "quarterly") == {"quarterly-report.txt"}
    assert titles(fc, OWNER, "storage quotas") == {"Storage quotas"}


def test_only_a_descriptor_switches_a_provider_on(fc):
    seed(fc)
    registry = fc.app.state.builtins
    files = registry.descriptors["files"]
    registry.descriptors["files"] = replace(files, spec={k: v for k, v in files.spec.items() if k != "search"})
    try:
        assert search(fc, OWNER, "quarterly") == {"hits": [], "providers": ["settings"]}
    finally:
        registry.descriptors["files"] = files
    narrowed = {**files.spec, "search": {"provider": "files", "types": ["folder"]}}
    registry.descriptors["files"] = replace(files, spec=narrowed)
    fc.app.state.search._built.clear()
    try:
        assert titles(fc, OWNER, "Docs") == {"Docs"}
        assert titles(fc, OWNER, "quarterly") == set()            # files are not a declared type any more
    finally:
        registry.descriptors["files"] = files
        fc.app.state.search._built.clear()


def test_the_index_stays_on_the_box_and_is_rebuilt_from_scratch(fc, settings):
    seed(fc)
    assert titles(fc, OWNER, "quarterly") == {"quarterly-report.txt"}
    path = settings.audit_path.parent / "cache" / "search" / "index.sqlite3"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600 and stat.S_IMODE(os.stat(path.parent).st_mode) == 0o700
    os.unlink(path)
    assert titles(fc, OWNER, "quarterly") == {"quarterly-report.txt"}  # a removed index is filled again
    fc.app.state.search.index.close()
    path.write_bytes(b"not a database at all")
    assert titles(fc, OWNER, "quarterly") == {"quarterly-report.txt"}  # so is a corrupt one


def test_hits_page_with_a_cursor_and_a_link_header(fc):
    mkdir(fc, OWNER, "shared", "/Pages")
    for i in range(5):
        ok(upload(fc, OWNER, "shared", "/Pages", f"paged-{i}.txt", b"p"), 204)
    everything = [h["id"] for h in search(fc, OWNER, "paged", types="file")["hits"]]
    assert len(everything) == 5
    r = fc.get("/v1/search", headers=OWNER, params={"q": "paged", "types": "file", "limit": 2})
    seen = [h["id"] for h in ok(r)]
    pages = 1
    while "link" in r.headers:
        link = r.headers["link"]
        assert link.startswith("</v1/search?") and link.endswith('>; rel="next"') and "q=paged" in link
        r = fc.get(link[1:link.index(">")], headers=OWNER)
        seen += [h["id"] for h in ok(r)]
        pages += 1
    assert seen == everything and pages == 3                     # the same hits, in order, two at a time
    for bad in ["nope", "bzotMQ", "eDox", "bzo5OTk5OQ"]:  # not base64 text; "o:-1"; "x:1"; "o:99999" (too deep)
        r = fc.get("/v1/search", headers=OWNER, params={"q": "paged", "cursor": bad})
        assert r.status_code == 422 and r.json()["reason"] == "invalid_cursor", (bad, r.text)


def test_query_text_is_never_fts_syntax(fc):
    seed(fc)
    for q in ['"', "NEAR(", "summer OR quarterly", "a* -b", "^col:x", "'; DROP TABLE items; --"]:
        r = fc.get("/v1/search", headers=OWNER, params={"q": q})
        assert r.status_code == 200, (q, r.text)
    assert titles(fc, OWNER, "summer OR quarterly") == set()      # OR is a word here, not an operator
    assert match_expression('sum "x" NEAR(') == '"sum"* "x"* "NEAR"*'
    assert match_expression("!!!") is None
    assert fc.get("/v1/search", headers=OWNER, params={"q": "x", "types": "Bad Type"}).status_code == 422
    assert fc.get("/v1/search", params={"q": "summer"}).status_code == 401
