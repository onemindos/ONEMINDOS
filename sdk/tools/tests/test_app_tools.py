# SPDX-License-Identifier: Apache-2.0
"""Unit tests for sdk/tools (app-scaffold, app-gate, app-readme, validate-apps helpers).

No network: GitHub and registry answers come from fixtures/uptime-kuma/, recorded on 2026-11-12
from api.github.com, raw.githubusercontent.com and `crane` (trimmed to the fields the tools read).
Run: python3 -I -m unittest discover -s sdk/tools/tests -v
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import yaml  # noqa: E402
from jsonschema import Draft202012Validator  # noqa: E402

from applib import common, licence, readme  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "uptime-kuma"
SCHEMA = json.loads((TOOLS.parent / "schema" / "onemind.app.schema.json").read_text())


def load_tool(name: str):
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), str(TOOLS / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


scaffold = load_tool("app-scaffold")
gate = load_tool("app-gate")
validate = load_tool("validate-apps")

REPO = "louislam/uptime-kuma"
IMAGE = "docker.io/louislam/uptime-kuma"
DIGEST = (FIX / "digest-2.5.10.txt").read_text().strip()


def fake_fetch(tree_file: str = "tree.json"):
    api = f"https://api.github.com/repos/{REPO}"
    routes = {
        api: "repo.json",
        f"{api}/releases/latest": "release.json",
        f"{api}/commits?per_page=1": "commits.json",
        f"{api}/git/trees/2.5.10?recursive=1": tree_file,
        f"https://raw.githubusercontent.com/{REPO}/2.5.10/compose.yaml": "compose.yaml",
    }

    def fetch(url: str):
        name = routes.get(url)
        return (FIX / name).read_bytes() if name else None
    return fetch


class FakeRegistry(common.Registry):
    def digest(self, ref):
        return DIGEST if ref == f"{IMAGE}:2.5.10" else None

    def manifest(self, ref):
        return json.loads((FIX / "index.json").read_text()) if ref == f"{IMAGE}@{DIGEST}" else None

    def config(self, ref, arch):
        return json.loads((FIX / "config-amd64.json").read_text())


class LicenceTests(unittest.TestCase):
    def test_classes(self):
        cases = {"MIT": "L1", "Apache-2.0 OR GPL-2.0": "L1", "AGPL-3.0": "L2", "EUPL-1.2": "L2",
                 "GPL-2.0-only WITH Linux-syscall-note": "L2", "(MIT OR GPL-3.0) AND BSD-2-Clause": "L1",
                 "MIT AND LicenseRef-x-EE": "blocked", "BUSL-1.1": "blocked", "Elastic-2.0": "blocked",
                 "PolyForm-Noncommercial-1.0.0": "blocked", "AGPL-3.0 WITH LicenseRef-Commons-Clause-1.0": "blocked",
                 "UNVERIFIED": "blocked", "": "blocked", "MIT OR": "blocked"}
        for expr, want in cases.items():
            self.assertEqual(licence.classify(expr), want, expr)

    def test_gate_needs_confirmation(self):
        row = [{"component": "x", "version": "1", "SPDX": "Apache-2.0 OR GPL-2.0"}]
        self.assertEqual(licence.gate("Apache-2.0 OR GPL-2.0", "Apache-2.0", [])[0], "L1")
        self.assertEqual(licence.gate("Apache-2.0 OR GPL-2.0", "NOASSERTION", row)[0], "L1")
        self.assertEqual(licence.gate("MIT", "GPL-3.0", [])[0], "blocked")
        self.assertEqual(licence.gate("MIT", None, [])[0], "blocked")
        # GitHub confirms one term only: an added "MIT OR" cannot lift a blocked or copyleft licence.
        self.assertEqual(licence.gate("MIT OR SSPL-1.0", "SSPL-1.0", [])[0], "blocked")
        self.assertEqual(licence.gate("MIT OR BUSL-1.1", "BUSL-1.1", [])[0], "blocked")
        self.assertEqual(licence.gate("MIT OR GPL-3.0", "GPL-3.0", [])[0], "L2")
        self.assertEqual(licence.gate("MIT AND Apache-2.0", "MIT", [])[0], "L1")
        # A matrix row for the whole expression confirms every term.
        self.assertEqual(licence.gate("Apache-2.0 OR GPL-2.0", "GPL-2.0", row)[0], "L1")

    def test_matrix_rows(self):
        rows = licence.matrix_rows(common.MATRIX_CSV, "binwiederhier/ntfy")
        self.assertTrue(rows and rows[0]["SPDX"] == "Apache-2.0 OR GPL-2.0")
        self.assertEqual(licence.matrix_rows(common.MATRIX_CSV, "binwiederhier/ntf"), [])


class ScaffoldTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def run_scaffold(self, tree="tree.json"):
        s = scaffold.Scaffold(REPO, common.GitHub(fake_fetch(tree)), FakeRegistry(), self.tmp,
                              name="Uptime Kuma")
        return s, s.write(s.build())

    def test_from_recorded_sources(self):
        s, app_dir = self.run_scaffold()
        m = yaml.safe_load((app_dir / "onemind.app.yaml").read_text())
        self.assertEqual(list(Draft202012Validator(SCHEMA).iter_errors(m)), [])
        self.assertEqual(m["metadata"]["id"], "uptime-kuma")
        self.assertEqual(m["metadata"]["version"], "2.5.10")
        self.assertEqual(m["metadata"]["license"], "MIT")
        self.assertEqual(m["metadata"]["links"]["website"], "https://uptime.kuma.pet")
        self.assertEqual(m["metadata"]["upstream"], {"release": "2.5.10", "released_at": "2026-11-12T03:53:19Z",
                                                     "archived": False})
        self.assertEqual(m["metadata"]["tier"], "community")
        self.assertEqual(m["spec"]["archs"], ["amd64", "arm64"])
        self.assertEqual(m["spec"]["web"], {"port": 3001})
        dep = yaml.safe_load((app_dir / "manifests" / "deployment.yaml").read_text())
        c = dep["spec"]["template"]["spec"]["containers"][0]
        # compose.yaml says louislam/uptime-kuma:2 (floating); the release tag is pinned instead.
        self.assertEqual(c["image"], f"{IMAGE}:2.5.10@{DIGEST}")
        self.assertEqual(c["volumeMounts"][0]["mountPath"], "/app/data")
        self.assertNotIn("&id", (app_dir / "manifests" / "deployment.yaml").read_text())
        text = (app_dir / "README.md").read_text()
        self.assertIn(readme.NOTES_BEGIN, text)
        self.assertIn("compose.yaml", text)
        self.assertIn("No scan yet", text)
        # category, sizing and first-run steps still need a person: capped at community.
        self.assertTrue(common.unverified_files(app_dir))

    def test_no_upstream_image_is_never_guessed(self):
        tree = self.tmp / "tree-empty.json"
        tree.write_text(json.dumps({"tree": [], "truncated": False}))
        fetch = fake_fetch()

        def fetch_empty(url):  # same upstream, but no compose file, chart or README
            return tree.read_bytes() if "/git/trees/" in url else fetch(url)
        s = scaffold.Scaffold(REPO, common.GitHub(fetch_empty), FakeRegistry(), self.tmp)
        app_dir = s.write(s.build())
        dep = yaml.safe_load((app_dir / "manifests" / "deployment.yaml").read_text())
        self.assertEqual(dep["spec"]["template"]["spec"]["containers"][0]["image"], "UNVERIFIED")
        self.assertTrue(any(u.startswith("image:") for u in s.unverified))

    def test_parsers(self):
        self.assertEqual(scaffold.expand_vars("ghcr.io/x/y:${TAG:-1.2}"), "ghcr.io/x/y:1.2")
        self.assertIsNone(scaffold.expand_vars("ghcr.io/x/y:${TAG}"))
        self.assertEqual(scaffold.container_port("127.0.0.1:8080:80/tcp"), 80)
        self.assertEqual(scaffold.normalise_image("nginx"), "docker.io/library/nginx")
        self.assertEqual(scaffold.normalise_image("ghcr.io/a/b"), "ghcr.io/a/b")
        self.assertEqual(scaffold.app_id_for("home-assistant/core"), "home-assistant")
        run = ("docker run --detach --name vaultwarden \\\n  --env DOMAIN=\"https://example.com\" \\\n"
               "  --volume /vw-data/:/data/ --publish 127.0.0.1:8000:80 vaultwarden/server:latest\n")
        got = scaffold.from_readme(run, "vaultwarden")
        self.assertEqual((got["image"], got["ports"], got["volumes"]), ("vaultwarden/server:latest", [80], ["/data/"]))
        compose = "services:\n  db:\n    image: postgres:16\n  app:\n    image: ghcr.io/acme/widget:${V:-2}\n    ports: ['8080:80']\n"
        got = scaffold.from_compose(compose, "widget")
        self.assertEqual((got["image"], got["ports"], got["other_services"]), ("ghcr.io/acme/widget:2", [80], ["db"]))

    def test_bad_input(self):
        self.assertEqual(scaffold.main(["owner/repo", "--id", "../../etc", "--apps-dir", str(self.tmp)]), 2)
        self.assertEqual(scaffold.main(["../..", "--apps-dir", str(self.tmp)]), 2)
        self.assertEqual(list(self.tmp.iterdir()), [])
        self.assertIsNone(scaffold.from_helm("- not a mapping\n", "image: {repository: x}\n"))
        self.assertIn(">&lt;x<", scaffold.icon_svg("x", "<script> x"))

    def test_queue_status(self):
        q = self.tmp / "queue.yaml"
        q.write_text("- {name: Uptime Kuma, github: louislam/uptime-kuma, priority: 1, status: queued}\n"
                     "- {name: Other, github: a/b, status: queued}\n")
        self.assertEqual(scaffold.queue_entry(q, REPO)["name"], "Uptime Kuma")
        self.assertTrue(scaffold.mark_in_pr(q, REPO))
        self.assertIn("uptime-kuma, priority: 1, status: in-pr}", q.read_text())
        self.assertIn("a/b, status: queued}", q.read_text())


class GateTests(unittest.TestCase):
    def test_tier_check_and_write(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        p = tmp / "onemind.app.yaml"
        p.write_text("metadata:\n  id: x\n  tier: verified   # comment kept\n")
        self.assertIsNotNone(gate.apply_tier(p, "verified", "community", "check"))
        self.assertIsNone(gate.apply_tier(p, "community", "verified", "check"))
        gate.apply_tier(p, "verified", "blocked", "write")
        self.assertEqual(p.read_text(), "metadata:\n  id: x\n  tier: blocked   # comment kept\n")
        gate.apply_tier(p, "blocked", "verified", "write")  # never lifts a block
        self.assertIn("tier: blocked", p.read_text())

    def test_scan_claim(self):
        self.assertIsNotNone(gate.scan_claim_error({"result": "pass"}, "fail"))
        self.assertIsNone(gate.scan_claim_error({"result": "fail"}, "fail"))
        self.assertIsNone(gate.scan_claim_error({"result": "pass"}, "pass"))
        self.assertIsNone(gate.scan_claim_error(None, "fail"))

    def test_nonroot(self):
        class G(gate.Gate):
            def __init__(self, user):
                self.checks, self.spec = {}, {"archs": ["amd64"]}
                self.reg = type("R", (), {"config": lambda s, ref, arch: {"config": {"User": user}}})()

        def pod(csc, psc=None):
            return [{"kind": "Deployment", "metadata": {"name": "a"}, "spec": {"template": {"spec": {
                "securityContext": psc or {}, "containers": [{"name": "c", "image": "i", "securityContext": csc}]}}}}]
        hardened = {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}}
        for user, objs, ok in [("", pod(hardened), True), ("", pod({}), False),
                               ("node", pod({}), True), ("node", pod({"runAsUser": 0}), False),
                               ("", pod({}, {"runAsNonRoot": True}), True)]:
            g = G(user)
            g.nonroot(objs)
            self.assertEqual(g.check("manifests").ok, ok, (user, objs))


class RenovateTests(unittest.TestCase):
    def test_automerge_list(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        for app, tier, am in [("a", "verified", "patch"), ("b", "community", "patch"), ("c", "verified", "none")]:
            (tmp / app).mkdir()
            (tmp / app / "onemind.app.yaml").write_text(
                f"metadata: {{tier: {tier}}}\nspec: {{updates: {{channel: stable, automerge: {am}}}}}\n")
        cfg = tmp / "renovate.json"
        dirs = sorted(d for d in tmp.iterdir() if d.is_dir())
        rule = {"automerge": True, "matchUpdateTypes": ["patch", "digest"], "matchFileNames": ["apps/a/manifests/**"]}
        cfg.write_text(json.dumps({"packageRules": [rule]}))
        self.assertEqual(validate.renovate_check(cfg, tmp, dirs), [])
        rule["matchFileNames"].append("apps/b/manifests/**")
        cfg.write_text(json.dumps({"packageRules": [rule]}))
        self.assertTrue(validate.renovate_check(cfg, tmp, dirs))


class IsolationTests(unittest.TestCase):
    def test_isolation(self):
        def errs(pod=None, **obj):
            o = {"kind": "Deployment", "metadata": {"name": "a"},
                 "spec": {"template": {"spec": pod or {"containers": [{"name": "c"}]}}}}
            o.update(obj)
            out: list[str] = []
            validate.AppChecker.isolation_checks([o], out)
            return out
        self.assertEqual(errs(), [])
        self.assertTrue(errs(kind="ClusterRoleBinding"))
        self.assertTrue(errs(kind="Secret"))
        self.assertTrue(errs(metadata={"name": "a", "namespace": "kube-system"}))
        self.assertTrue(errs({"hostNetwork": True, "containers": []}))
        self.assertTrue(errs({"volumes": [{"name": "r", "hostPath": {"path": "/"}}], "containers": []}))
        self.assertTrue(errs({"containers": [{"name": "c", "securityContext": {"privileged": True}}]}))
        self.assertTrue(errs({"containers": [{"name": "c", "ports": [{"containerPort": 1, "hostPort": 1}]}]}))


class ReadmeTests(unittest.TestCase):
    def test_notes_roundtrip(self):
        text = f"head\n{readme.NOTES_BEGIN}\n## First run\n\n1. Open it.\n{readme.NOTES_END}\ntail\n"
        self.assertEqual(readme.extract_notes(text), "## First run\n\n1. Open it.\n")
        self.assertIsNone(readme.extract_notes("no markers"))

    @unittest.skipUnless(shutil.which("kustomize"), "kustomize not on PATH")
    def test_committed_readmes_are_current(self):
        for app_dir in sorted(p for p in common.APPS_DIR.iterdir() if p.is_dir() and not p.name.startswith("_")):
            self.assertEqual(readme.render(app_dir), (app_dir / "README.md").read_text(), app_dir.name)


if __name__ == "__main__":
    unittest.main()
