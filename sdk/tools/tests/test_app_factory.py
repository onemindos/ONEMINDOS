# SPDX-License-Identifier: Apache-2.0
"""App factory: recipes, the generated Dockerfile, the rebuild decision, the changelog and the manifest pin.
No network and no docker. Run: python3 -I -m unittest discover -s sdk/tools/tests -v"""
from __future__ import annotations

import copy
import datetime as dt
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402
from jsonschema import Draft202012Validator  # noqa: E402

from applib import common  # noqa: E402
from factorylib import factory  # noqa: E402
from test_app_tools import SCHEMA, load_tool  # noqa: E402

cli = load_tool("app-factory")
APPS = TOOLS.parents[1] / "apps"
DIGEST = "sha256:" + "a" * 64
BASE = f"docker.io/nousresearch/hermes-agent:v0.23.0@{DIGEST}"
BUILT = f"ghcr.io/onemindos/apps/hermes-agent:0.23.0-om1@sha256:{'b' * 64}"
NOW = dt.datetime(2026, 11, 21, tzinfo=dt.timezone.utc)


def trivy(*findings):
    return {"Results": [{"Vulnerabilities": [
        {"VulnerabilityID": i, "PkgName": p, "Severity": s, "FixedVersion": f, "InstalledVersion": "1"} for i, p, s, f in findings]}]}


class RecipeTests(unittest.TestCase):
    def test_the_two_shipped_recipes_are_valid(self):
        ids = sorted(d.name for d in APPS.iterdir() if (d / factory.RECIPE_NAME).is_file())
        self.assertEqual(ids, ["hermes-agent", "syncthing"])
        for i in ids:
            self.assertEqual(factory.validate_recipe(factory.load_recipe(APPS / i), APPS / i), [], i)

    def problems(self, mutate):
        recipe = copy.deepcopy(factory.load_recipe(APPS / "hermes-agent"))
        mutate(recipe)
        return factory.validate_recipe(recipe, APPS / "hermes-agent")

    def test_package_names_cannot_carry_shell_syntax(self):
        for bad in ("x; curl evil | sh", "$(id)", "a b", "-o"):
            self.assertTrue(self.problems(lambda r, b=bad: r["build"]["patch"].update(apt=[b])), bad)

    def test_other_mistakes_are_refused(self):
        self.assertTrue(self.problems(lambda r: r["target"].update(image="ghcr.io/someone/else")))
        self.assertTrue(self.problems(lambda r: r["build"].update(strategy="script")))
        self.assertTrue(self.problems(lambda r: r["build"]["patch"].update(apk=["x"])))  # apt and apk together
        self.assertTrue(self.problems(lambda r: r["build"].update(restore_user="root; rm")))
        self.assertTrue(self.problems(lambda r: r["upstream"].update(image="docker.io/other/image")))  # changes nothing
        self.assertTrue(self.problems(lambda r: r.update(app="syncthing")))


class DockerfileTests(unittest.TestCase):
    def test_apt_overlay_is_pinned_and_restores_the_user(self):
        text = factory.render_dockerfile(factory.load_recipe(APPS / "hermes-agent"), BASE)
        self.assertIn(f"FROM {BASE}\n", text)
        self.assertIn("--only-upgrade linux-libc-dev", text)
        self.assertTrue(text.rstrip().endswith("USER root"))

    def test_apk_overlay(self):
        text = factory.render_dockerfile(factory.load_recipe(APPS / "syncthing"), f"docker.io/syncthing/syncthing:2.1.7@{DIGEST}")
        self.assertIn("apk upgrade --no-cache brotli-libs", text)

    def test_a_base_without_a_digest_is_refused(self):
        with self.assertRaises(ValueError):
            factory.render_dockerfile(factory.load_recipe(APPS / "hermes-agent"), "docker.io/nousresearch/hermes-agent:v0.23.0")

    def test_image_tag_template(self):
        r = factory.load_recipe(APPS / "syncthing")
        self.assertEqual(factory.upstream_ref(r, "v2.1.7"), "docker.io/syncthing/syncthing:2.1.7")
        self.assertEqual(factory.upstream_ref(factory.load_recipe(APPS / "hermes-agent"), "v0.23.0"),
                         "docker.io/nousresearch/hermes-agent:v0.23.0")


class DecideTests(unittest.TestCase):
    recipe = {"rebuild_after_days": 7}

    def manifest(self, tag="v0.23.0", base=DIGEST, built="2026-11-20T00:00:00Z"):
        md = {"upstream": {"release": tag}}
        if built:
            md["build"] = {"upstreamTag": tag, "base": f"x@{base}", "builtAt": built, "revision": 1}
        return {"metadata": md}

    def test_decisions(self):
        d = lambda m, tag="v0.23.0", base=DIGEST, force=False: factory.decide(self.recipe, m, tag, base, NOW, force)
        self.assertEqual(d(self.manifest())[0], "skip")
        self.assertIn("new upstream release", d(self.manifest(), tag="v0.24.0")[1])
        self.assertIn("different image", d(self.manifest(), base="sha256:" + "c" * 64)[1])
        self.assertIn("8 days", d(self.manifest(built="2026-11-13T00:00:00Z"))[1])
        self.assertEqual(d(self.manifest(built=None))[0], "rebuild")  # never built by the factory
        self.assertEqual(d(self.manifest(), force=True), ("rebuild", "forced"))

    def test_a_failed_read_never_rebuilds(self):
        self.assertEqual(factory.decide(self.recipe, self.manifest(), None, DIGEST, NOW, True)[0], "skip")
        self.assertEqual(factory.decide(self.recipe, self.manifest(), "v1", None, NOW, True)[0], "skip")


class ChangelogTests(unittest.TestCase):
    def test_closed_new_and_still_open(self):
        old = trivy(("CVE-1", "linux-libc-dev", "CRITICAL", "6.12.115"), ("CVE-2", "libx", "HIGH", None), ("CVE-3", "foo", "CRITICAL", "9"))
        new = trivy(("CVE-2", "libx", "HIGH", None), ("CVE-3", "foo", "CRITICAL", "9"), ("CVE-4", "bar", "HIGH", None))
        text = factory.changelog("hermes-agent", "v0.23.0", "v0.23.0", old, new, "weekly", ["linux-libc-dev"], BASE, BUILT)
        closed, rest = text.split("### Closed")[1].split("### New in this build")
        self.assertIn("CVE-1", closed)
        self.assertNotIn("CVE-2", closed)
        self.assertIn("CVE-4", rest.split("### Still open")[0])
        self.assertIn("CVE-3", rest.split("### Still open")[1])  # a critical with a fix is called out
        self.assertIn("merging this pull request is the human approval", text)

    def test_critical_free_build_says_so(self):
        text = factory.changelog("a", "v1", "v1", trivy(("CVE-1", "p", "CRITICAL", "2")), trivy(), "x", ["p"], BASE, BUILT)
        self.assertIn("no critical finding with a fix: the gate can pass", text)


class ApplyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name) / "hermes-agent"
        shutil.copytree(APPS / "hermes-agent", self.dir)
        self.recipe = factory.load_recipe(self.dir)

    def apply(self, tag="v0.23.0", revision=1, built=BUILT):
        factory.apply_build(self.dir, self.recipe, upstream_tag=tag, released_at="2026-11-05T21:32:33Z", base_ref=BASE,
                            built_ref=built, built_at="2026-11-21T10:00:00Z", revision=revision)

    def test_every_image_use_is_repinned_and_provenance_recorded(self):
        self.apply()
        refs = factory.manifest_images(self.dir)
        self.assertTrue(refs and set(refs) == {BUILT}, refs)  # init container and main container
        doc = common.load_manifest(self.dir)
        self.assertEqual(doc["metadata"]["version"], "0.23.0+om.1")
        build = doc["metadata"]["build"]
        self.assertEqual((build["builder"], build["revision"], build["base"], build["image"]),
                         ("onemind-app-factory", 1, BASE, BUILT))
        self.assertEqual(build["patched"], ["linux-libc-dev"])
        self.assertEqual(doc["metadata"]["tier"], "blocked")  # the factory never raises a tier by itself
        errors = list(Draft202012Validator(SCHEMA).iter_errors(doc))
        self.assertEqual([e.message for e in errors], [])

    def test_a_second_build_replaces_the_record_and_repins_our_own_image(self):
        self.apply()
        newer = BUILT.replace("-om1@", "-om2@").replace("b" * 64, "c" * 64)
        self.apply(revision=2, built=newer)
        text = (self.dir / common.MANIFEST_NAME).read_text()
        self.assertEqual(text.count("\n  build:"), 1)
        self.assertEqual(set(factory.manifest_images(self.dir)), {newer})
        self.assertEqual(common.load_manifest(self.dir)["metadata"]["version"], "0.23.0+om.2")
        self.assertEqual(factory.current_pin(common.load_manifest(self.dir)),
                         {"tag": "v0.23.0", "base_digest": DIGEST, "built_at": "2026-11-21T10:00:00Z", "revision": 2})

    def test_comments_survive(self):
        before = (self.dir / common.MANIFEST_NAME).read_text()
        self.apply()
        after = (self.dir / common.MANIFEST_NAME).read_text()
        for line in before.splitlines():
            if line.lstrip().startswith("#"):
                self.assertIn(line, after)


class LiftTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.dir = self.root / "hermes-agent"
        shutil.copytree(APPS / "hermes-agent", self.dir)

    def lift(self, *, built=True, result="pass", smoke="pass", tier="community"):
        if built:
            factory.apply_build(self.dir, factory.load_recipe(self.dir), upstream_tag="v0.23.0", released_at=None,
                                base_ref=BASE, built_ref=BUILT, built_at="2026-11-21T10:00:00Z", revision=1)
        (self.dir / "scan.json").write_text(json.dumps({"result": result, "smoke": smoke}))
        report = self.root / "report.json"
        report.write_text(json.dumps([{"app": "hermes-agent", "computed_tier": tier, "result": result}]))
        rc = cli.main(["--apps-dir", str(self.root), "lift", "hermes-agent", "--report", str(report)])
        return rc, common.load_manifest(self.dir)["metadata"]["tier"]

    def test_lifts_only_on_a_clean_gate_verdict(self):
        self.assertEqual(self.lift(), (0, "community"))

    def test_never_lifts_when_anything_is_short(self):
        self.assertEqual(self.lift(result="fail"), (1, "blocked"))
        self.assertEqual(self.lift(smoke="fail"), (1, "blocked"))
        self.assertEqual(self.lift(tier="blocked"), (1, "blocked"))

    def test_upstream_images_are_not_the_factorys_to_lift(self):
        self.assertEqual(self.lift(built=False), (1, "blocked"))


WORKFLOW = yaml.safe_load((TOOLS.parents[1] / ".github/workflows/app-factory.yml").read_text())
JOBS = WORKFLOW["jobs"]


class WorkflowTests(unittest.TestCase):
    def test_only_the_build_job_can_write_packages_and_only_publish_can_write_the_repo(self):
        self.assertEqual(JOBS["build"]["permissions"], {"contents": "read", "packages": "write"})
        self.assertEqual(JOBS["verify"]["permissions"], {"contents": "read"})  # runs the app's image: read-only token
        self.assertEqual(JOBS["plan"]["permissions"], {"contents": "read"})
        self.assertEqual(JOBS["publish"]["permissions"], {"contents": "write", "pull-requests": "write"})
        self.assertEqual(WORKFLOW["permissions"], {"contents": "read"})

    def test_runs_on_our_runners_with_a_hosted_fallback(self):
        for name in ("plan", "build", "verify"):
            runs_on = JOBS[name]["runs-on"]
            self.assertIn("self-hosted", runs_on, name)
            self.assertIn("ubuntu-24.04", runs_on, name)
            self.assertIn("LOCAL_RUNNER", runs_on, name)

    def test_only_the_workflow_token_and_optional_dockerhub_are_used(self):
        import re
        text = (TOOLS.parents[1] / ".github/workflows/app-factory.yml").read_text()
        self.assertEqual(sorted(set(re.findall(r"secrets\.([A-Z0-9_]+)", text))), ["DOCKERHUB_TOKEN", "DOCKERHUB_USERNAME"])

    def test_the_gate_runs_unchanged_and_a_human_reviews_every_pull_request(self):
        gate = next(s["run"] for s in JOBS["verify"]["steps"] if s.get("name") == "Gate the rebuilt image")
        self.assertIn("app-gate", gate)
        self.assertIn("--smoke --tier check", gate)  # check mode: the gate never has its tier lifted by --tier write
        self.assertNotIn("--tier write", gate)
        self.assertNotIn("--tier ignore", gate)
        publish = next(s["run"] for s in JOBS["publish"]["steps"] if s.get("name") == "One pull request per rebuilt app")
        self.assertIn("gh pr create", publish)
        self.assertNotIn("gh pr merge", publish)
        self.assertNotIn("--auto", publish)
        self.assertIn("Refs #234", publish)


if __name__ == "__main__":
    unittest.main()
