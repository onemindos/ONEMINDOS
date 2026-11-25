# SPDX-License-Identifier: Apache-2.0
"""App factory images (sdk/tools/app-factory) ride the existing safe upgrade path, unchanged: the owner approves a
plan bound to the exact bundle (so a swapped image digest is a different plan), the update is health-gated and a
bad rebuild is rolled back. The Market also learns that OneMind, not upstream, built the image."""

from __future__ import annotations

import yaml
from conftest import GUEST, OWNER, make_client
from test_app_lifecycle import APP, Cluster, run, status

from onemind_core.catalog import Catalog, build_summary
from onemind_core.executors import KubernetesExecutor

OLD = "ghcr.io/onemindos/apps/uptime-kuma:2.0.2-om1@sha256:" + "a" * 64
NEW = "ghcr.io/onemindos/apps/uptime-kuma:2.0.2-om2@sha256:" + "b" * 64
BASE = "docker.io/louislam/uptime-kuma@sha256:" + "c" * 64
BUILD = {"builder": "onemind-app-factory", "recipe": "factory.yaml", "revision": 1, "upstreamTag": "2.0.2", "base": BASE,
         "patched": ["libc6"], "builtAt": "2026-11-21T10:00:00Z", "image": OLD}


def pin(settings, image: str, build: dict | None = BUILD, version: str = "2.0.2"):
    d = settings.apps_dir / APP
    (d / "manifests" / "image.yaml").write_text(f"image: {image}\n")
    path = d / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["metadata"]["version"] = version
    doc["metadata"]["build"] = None if build is None else dict(build, image=image)
    if build is None:
        del doc["metadata"]["build"]
    path.write_text(yaml.safe_dump(doc))


def plan(c):
    return c.get(f"/v1/apps/{APP}/plan?type=app.update", headers=OWNER).json()


def test_the_market_lists_who_built_the_image(settings, clock):
    pin(settings, OLD)
    with make_client(settings, clock) as c:
        row = next(a for a in c.get("/v1/apps", headers=GUEST).json() if a["id"] == APP)
        assert row["build"] == {"builder": "onemind-app-factory", "revision": 1, "upstream_tag": "2.0.2", "base": BASE,
                                "patched": ["libc6"], "built_at": "2026-11-21T10:00:00Z", "image": OLD}
        other = next(a for a in c.get("/v1/apps", headers=GUEST).json() if a["id"] == "whoami")
        assert other["build"] is None  # upstream's own image: nothing claimed


def test_a_build_record_that_is_not_ours_or_is_broken_shows_nothing():
    assert build_summary({**BUILD, "builder": "someone-else"}) is None
    assert build_summary({k: v for k, v in BUILD.items() if k != "base"}) is None
    assert build_summary("x") is None and build_summary(None) is None


def test_a_swapped_image_digest_is_a_different_plan_the_owner_must_approve(settings, clock):
    pin(settings, OLD)
    with make_client(settings, clock) as c:
        run(c, clock, "app.install", "i")
        before = plan(c)
        pin(settings, NEW, version="2.0.2")  # same upstream version, new OneMind rebuild: only the digest moved
        after = plan(c)
        assert before["plan_sha256"] != after["plan_sha256"]
        assert not any("nothing would change" in w for w in after["plan"]["warnings"])
        assert any("Health-gated" in w for w in after["plan"]["warnings"])
        done = run(c, clock, "app.update", "u")
        assert done["state"] == "succeeded" and status(c)[0] == "installed"


def test_an_unhealthy_rebuild_is_rolled_back_like_any_update(settings):
    pin(settings, NEW)
    app = Catalog(settings.apps_dir).get(APP)
    cluster = Cluster(unhealthy_first=1)
    res = KubernetesExecutor(runner=cluster).run("app.update", app)
    assert res.outcome == "failed" and res.reverted is True
    assert cluster.verbs().count("rollout undo") == 2
