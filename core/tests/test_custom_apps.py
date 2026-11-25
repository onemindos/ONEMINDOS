# SPDX-License-Identifier: Apache-2.0
"""PLG-GIT-01 (D-026): a custom app from a Git repo. Plan (owner only) -> revision -> the ordinary
app.install / app.update an owner approves -> rollback to the previous revision."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from conftest import AGENT, OWNER, ScriptedExecutor, make_client
from onemind_core.appstore.sources import FetchError, GitFetcher
from test_appstore import DIGEST, PassScanner, run, source_app, store_of

URL = "https://git.example.org/me/notes"
C1, C2, C3 = "1" * 40, "2" * 40, "3" * 40


def tree(root: Path, app_id="notes", *, version="1.0.0", host_network=False, extra_files=()) -> Path:
    source_app(root, app_id, version=version, host_network=host_network)
    # a repository holds the app at its top level, not in a folder named after it
    for item in (root / app_id).iterdir():
        item.rename(root / item.name)
    (root / app_id).rmdir()
    for name in extra_files:
        (root / name).write_text("FROM scratch\n")
    return root


class FakeFetcher(GitFetcher):
    """refs: {"main": commit}; trees: {commit: folder}. No network, no DNS."""

    def __init__(self, root: Path, refs: dict[str, str], trees: dict[str, Path]):
        super().__init__(root)
        self.refs, self.trees, self.fetches = refs, trees, 0

    def check_url(self, url):
        return None

    def resolve_ref(self, url, ref):
        if ref in self.refs:
            return self.refs[ref]
        raise FetchError(f"the repository has no branch or tag named {ref!r}")

    def fetch(self, source_id, url, commit):
        import shutil
        if commit not in self.trees:
            raise FetchError("no such commit")
        dst = self.path(source_id, commit)
        if not dst.exists():
            self.fetches += 1
            shutil.copytree(self.trees[commit], dst)
        return dst


@pytest.fixture
def world(settings, clock, tmp_path):
    t1, t2, t3 = (tree(tmp_path / n, version=v) for n, v in (("t1", "1.0.0"), ("t2", "1.1.0"), ("t3", "1.2.0")))
    ex = ScriptedExecutor()
    with make_client(settings, clock, ex) as c:
        store = store_of(c)
        store.fetcher = FakeFetcher(tmp_path / "cache", {"main": C1, "v2": C2, "v3": C3}, {C1: t1, C2: t2, C3: t3})
        store.image_scanner = PassScanner()
        yield c, store, ex, tmp_path


def plan(c, ref="main", url=URL, headers=OWNER):
    return c.post("/v1/custom-apps/plan", json={"url": url, "ref": ref}, headers=headers)


def deploy(c, clock, app_id="notes", kind="app.install"):
    r = run(c, clock, kind, {"app_id": app_id})
    assert r.status_code == 200 and r.json()["state"] == "succeeded", r.text


def test_plan_records_a_revision_and_serves_it_capped_at_community(world):
    c, *_ = world
    r = plan(c)
    assert r.status_code == 200, r.text
    p = r.json()
    assert (p["app_id"], p["revision"], p["commit"], p["verdict"], p["action_type"]) == ("notes", 1, C1, "ready", "app.install")
    assert p["scan"]["result"] == "pass" and p["signature"]["policy"] == "undecided" and p["signature"]["status"] == "not_checked"
    row = next(a for a in c.get("/v1/apps", headers=OWNER).json() if a["id"] == "notes")
    assert row["tier"] == "community" and row["custom_source"]["commit"] == C1 and row["scan"]["result"] == "pass"


def test_nothing_is_installed_until_an_owner_approves(world, clock):
    c, store, ex, _ = world
    plan(c)
    assert ex.calls == []
    from test_appstore import request
    r = request(c, clock, "app.install", {"app_id": "notes"}, headers=AGENT)  # an agent may only request
    assert r.status_code == 201 and r.json()["state"] == "awaiting_approval"
    assert ex.calls == []
    assert c.post(f"/v1/actions/{r.json()['id']}/approve", headers=AGENT).status_code == 403
    assert ex.calls == []
    assert c.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER).json()["state"] == "succeeded"
    assert ex.calls == [("app.install", "notes")]


def test_agents_and_guests_cannot_plan_or_roll_back(world):
    c, *_ = world
    assert plan(c, headers=AGENT).status_code == 403
    assert c.post("/v1/custom-apps/notes/rollback", json={}, headers=AGENT).status_code == 403
    assert c.get("/v1/custom-apps", headers=AGENT).status_code in (200, 403)  # reads follow the app list scope


@pytest.mark.parametrize("url,ref", [
    ("http://git.example.org/r", "main"), ("https://u:" + "x" + "@git.example.org/r", "main"), ("https://git.example.org/r?x=1", "main"),
    ("ext::sh -c id", "main"), (URL, "no-such-branch"), (URL, "--upload-pack=x"), (URL, "a..b"),
])
def test_bad_urls_and_refs_are_refused(world, url, ref):
    c, *_ = world
    assert plan(c, ref=ref, url=url).status_code == 422


def test_a_repository_with_a_failing_scan_is_recorded_but_never_served(world):
    c, store, _, tmp = world
    bad = tree(tmp / "bad", host_network=True)
    store.fetcher.refs["bad"], store.fetcher.trees[C3] = C3, bad
    p = plan(c, "bad").json()
    assert p["verdict"] == "blocked" and p["action_type"] is None and any("F-01" in x for x in p["problems"])
    assert "notes" not in {a["id"] for a in c.get("/v1/apps", headers=OWNER).json()}
    assert c.get("/v1/custom-apps/notes", headers=OWNER).json()["revisions"][0]["scan"]["result"] == "fail"


def test_missing_or_invalid_manifest_is_blocked_and_records_nothing(world):
    c, store, _, tmp = world
    empty = tmp / "empty"
    empty.mkdir()
    store.fetcher.refs["empty"], store.fetcher.trees[C3] = C3, empty
    p = plan(c, "empty").json()
    assert p["verdict"] == "blocked" and "onemind.app.yaml" in p["problems"][0] and p["revision"] is None
    assert c.get("/v1/custom-apps", headers=OWNER).json() == []


def test_a_custom_app_cannot_take_an_official_id_or_another_repos_id(world):
    c, store, _, tmp = world
    clash = tree(tmp / "clash", app_id="uptime-kuma")
    store.fetcher.refs["clash"], store.fetcher.trees[C3] = C3, clash
    r = plan(c, "clash")
    assert r.status_code == 409 and r.json()["reason"] == "app_id_taken"
    assert plan(c).status_code == 200
    assert plan(c, url="https://git.example.org/someone/else").status_code == 409


def test_a_claimed_tier_and_a_shipped_scan_json_are_ignored(world):
    c, store, _, tmp = world
    t = tree(tmp / "claim")
    doc = yaml.safe_load((t / "onemind.app.yaml").read_text())
    doc["metadata"]["tier"] = "verified"
    (t / "onemind.app.yaml").write_text(yaml.safe_dump(doc))
    (t / "scan.json").write_text(json.dumps({"scanned_at": "2026-11-11T21:00:00Z", "result": "pass"}))
    store.image_scanner = type("Fail", (), {"name": "f", "scan": lambda self, images: ("fail", "found a CVE")})()
    store.fetcher.refs["claim"], store.fetcher.trees[C3] = C3, t
    p = plan(c, "claim").json()
    assert p["verdict"] == "blocked" and p["scan"]["result"] == "fail"
    assert "notes" not in {a["id"] for a in c.get("/v1/apps", headers=OWNER).json()}


def test_each_deploy_is_a_revision_and_rollback_goes_back_to_the_previous_one(world, clock):
    c, store, ex, _ = world
    plan(c)
    deploy(c, clock)
    assert c.get("/v1/custom-apps/notes", headers=OWNER).json()["deployed_revision"] == 1
    assert plan(c, "v2").json()["revision"] == 2
    deploy(c, clock, kind="app.update")
    view = c.get("/v1/custom-apps/notes", headers=OWNER).json()
    assert view["deployed_revision"] == 2 and view["rollback_to"] == 1 and view["status"] == "installed"
    assert [r["revision"] for r in view["revisions"]] == [2, 1]
    rb = c.post("/v1/custom-apps/notes/rollback", json={}, headers=OWNER)
    assert rb.status_code == 200, rb.text
    assert (rb.json()["from_revision"], rb.json()["to_revision"], rb.json()["action_type"]) == (2, 1, "app.update")
    served = next(a for a in c.get("/v1/apps", headers=OWNER).json() if a["id"] == "notes")
    assert served["custom_source"]["commit"] == C1 and served["version"] == "1.0.0"
    assert ex.calls == [("app.install", "notes"), ("app.update", "notes")]  # the rollback itself is still waiting
    deploy(c, clock, kind="app.update")
    view = c.get("/v1/custom-apps/notes", headers=OWNER).json()
    assert view["deployed_revision"] == 1 and view["rollback_to"] == 2


def test_the_same_commit_is_not_a_second_revision(world):
    c, *_ = world
    plan(c)
    assert plan(c).json()["revision"] == 1
    assert len(c.get("/v1/custom-apps/notes", headers=OWNER).json()["revisions"]) == 1


def test_a_denied_or_failed_deploy_does_not_count_as_deployed(world, clock):
    c, store, ex, _ = world
    plan(c)
    ex.outcome = "failed"
    r = run(c, clock, "app.install", {"app_id": "notes"})
    assert r.json()["state"] == "failed"
    assert c.get("/v1/custom-apps/notes", headers=OWNER).json()["deployed_revision"] is None
    assert c.post("/v1/custom-apps/notes/rollback", json={}, headers=OWNER).status_code == 409


def test_rollback_refusals(world, clock):
    c, store, *_ = world
    assert c.post("/v1/custom-apps/nope/rollback", json={}, headers=OWNER).status_code == 404
    plan(c)
    deploy(c, clock)
    assert c.post("/v1/custom-apps/notes/rollback", json={}, headers=OWNER).json()["reason"] == "no_previous_revision"
    plan(c, "v2")
    assert c.post("/v1/custom-apps/notes/rollback", json={"revision": 2}, headers=OWNER).status_code == 422  # never deployed
    assert c.post("/v1/custom-apps/notes/rollback", json={"revision": 1}, headers=OWNER).json()["reason"] == "already_deployed"


def test_rollback_is_refused_when_the_old_revision_no_longer_passes(world, clock):
    c, store, *_ = world
    plan(c)
    deploy(c, clock)
    plan(c, "v2")
    deploy(c, clock, kind="app.update")
    store.image_scanner = type("Fail", (), {"name": "f", "scan": lambda self, images: ("fail", "new CVE")})()
    r = c.post("/v1/custom-apps/notes/rollback", json={}, headers=OWNER)
    assert r.status_code == 409 and r.json()["reason"] == "scan_failed"
    assert next(a for a in c.get("/v1/apps", headers=OWNER).json() if a["id"] == "notes")["custom_source"]["revision"] == 2


def test_rollback_refetches_a_pruned_checkout_and_refuses_a_changed_one(world, clock):
    c, store, *_ = world
    plan(c)
    deploy(c, clock)
    plan(c, "v2")
    deploy(c, clock, kind="app.update")
    import shutil
    shutil.rmtree(store.fetcher.path(store.custom.key(URL), C1))
    assert c.post("/v1/custom-apps/notes/rollback", json={}, headers=OWNER).status_code == 200
    changed = store.fetcher.path(store.custom.key(URL), C1) / "onemind.app.yaml"
    changed.write_text(changed.read_text() + "# edited after the scan\n")
    store.repo.set_custom_current("notes", 2)
    assert c.post("/v1/custom-apps/notes/rollback", json={}, headers=OWNER).json()["reason"] == "revision_changed"


def test_an_edited_checkout_is_not_served(world):
    c, store, *_ = world
    plan(c)
    path = store.fetcher.path(store.custom.key(URL), C1) / "onemind.app.yaml"
    path.write_text(path.read_text().replace("1.0.0", "9.9.9"))
    assert "notes" not in {a["id"] for a in c.get("/v1/apps", headers=OWNER).json()}


def test_a_containerfile_is_noted_not_built(world):
    c, store, _, tmp = world
    t = tree(tmp / "cf", extra_files=("Containerfile",))
    store.fetcher.refs["cf"], store.fetcher.trees[C3] = C3, t
    p = plan(c, "cf").json()
    assert p["verdict"] == "ready" and "not part of this release" in p["notes"][0]


def test_old_checkouts_are_pruned_but_history_stays(world, clock):
    c, store, _, tmp = world
    plan(c)
    deploy(c, clock)
    for i in range(7):
        commit = f"{i + 4:x}" * 40
        store.fetcher.refs[f"b{i}"], store.fetcher.trees[commit] = commit, tree(tmp / f"x{i}", version=f"2.0.{i}")
        plan(c, f"b{i}")
    base = store.fetcher.path(store.custom.key(URL), "x").parent
    assert C1 in {d.name for d in base.iterdir()}  # the deployed one stays
    assert len([d for d in base.iterdir()]) <= 7
    assert len(c.get("/v1/custom-apps/notes", headers=OWNER).json()["revisions"]) == 8


def test_the_resolver_follows_refs_with_real_git(tmp_path):
    def git(*args, cwd):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=ci", *args], cwd=cwd, check=True,
                       capture_output=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    git("init", "-q", "-b", "main", cwd=repo)
    (repo / "onemind.app.yaml").write_text("a: 1\n")
    git("add", ".", cwd=repo)
    git("commit", "-q", "-m", "one", cwd=repo)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
    git("tag", "-a", "v1", "-m", "v1", cwd=repo)
    f = GitFetcher(tmp_path / "cache", allow_file_urls=True)
    url = repo.as_uri()
    assert f.resolve_ref(url, "main") == head and f.resolve_ref(url, "v1") == head and f.resolve_ref(url, head) == head
    with pytest.raises(FetchError):
        f.resolve_ref(url, "missing")
    with pytest.raises(FetchError):
        f.resolve_ref(url, "-x")
    assert f.fetch("custom-t", url, head).joinpath("onemind.app.yaml").is_file()
    assert not list((tmp_path / "cache" / "_resolve").iterdir())  # no scratch left behind


def test_no_credential_or_url_secret_reaches_the_audit_log(world, settings):
    c, *_ = world
    plan(c)
    log = settings.audit_path.read_text()
    assert "customapp.planned" in log and URL in log
    assert "@git.example.org" not in log and "token" not in log.lower().replace("token_hash", "")
