# SPDX-License-Identifier: Apache-2.0
"""PLAN-E6 (#175): one manifest validator for CI, the CLI and the box; v1alpha1 -> v1 converter."""
from __future__ import annotations

import copy
import importlib.machinery
import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
import sys  # noqa: E402

sys.path.insert(0, str(REPO / "core"))
from onemind_core.catalog import Catalog  # noqa: E402
from onemind_core.manifest_convert import convert_manifest  # noqa: E402

SCHEMA = REPO / "sdk" / "schema" / "onemind.app.schema.json"
TOOLS = REPO / "sdk" / "tools"


def load(name: str):
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), str(TOOLS / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def sample() -> dict:
    return yaml.safe_load((REPO / "apps" / "ntfy" / "onemind.app.yaml").read_text())


class ManifestV1Tests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog(REPO / "apps", SCHEMA)

    def test_both_api_versions_validate(self):
        doc = sample()
        self.assertEqual(self.catalog.validate(doc), [])
        doc["apiVersion"] = "onemind.app/v1"
        self.assertEqual(self.catalog.validate(doc), [])

    def test_unknown_api_version_is_refused(self):
        doc = sample()
        doc["apiVersion"] = "onemind.app/v2"
        self.assertTrue(self.catalog.validate(doc))

    def test_builtin_check_agrees_on_api_version(self):
        plain = Catalog(REPO / "apps", None)
        doc = sample()
        doc["apiVersion"] = "onemind.app/v1"
        self.assertFalse(any("apiVersion" in e for e in plain.validate(doc)))
        doc["apiVersion"] = "onemind.app/v9"
        self.assertTrue(any("apiVersion" in e for e in plain.validate(doc)))

    def test_convert_changes_only_api_version(self):
        old = sample()
        new, notes = convert_manifest(old)
        self.assertEqual(old["apiVersion"], "onemind.app/v1alpha1")  # input untouched
        self.assertEqual(new["apiVersion"], "onemind.app/v1")
        rest = copy.deepcopy(new)
        rest["apiVersion"] = old["apiVersion"]
        self.assertEqual(rest, old)
        self.assertEqual(len(notes), 1)
        self.assertEqual(self.catalog.validate(new), [])

    def test_convert_is_idempotent_and_refuses_unknown(self):
        once, _ = convert_manifest(sample())
        twice, notes = convert_manifest(once)
        self.assertEqual(twice, once)
        self.assertEqual(notes, [])
        _, notes = convert_manifest({"apiVersion": "other/v1"})
        self.assertTrue(notes[0].startswith("cannot convert"))
        _, notes = convert_manifest("text")
        self.assertTrue(notes[0].startswith("cannot convert"))

    def test_ci_and_box_run_the_same_validator(self):
        """validate-apps must call Catalog.validate, not its own schema walk."""
        checker = load("validate-apps").AppChecker(self.catalog, "kustomize", "kubeconform")
        self.assertIs(type(checker.catalog), Catalog)
        # A spec.agent mistake is caught by the gateway's extra rules; CI now sees it too.
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "ntfy"
            shutil.copytree(REPO / "apps" / "ntfy", app)
            doc = sample()
            doc["spec"]["agent"] = {"principal": True, "secret": "Not A Name"}
            (app / "onemind.app.yaml").write_text(yaml.safe_dump(doc))
            _, errors = checker.check(app)
        self.assertTrue(any("spec.agent.secret" in e for e in errors), errors)

    def test_cli_convert_rewrites_one_line_and_keeps_comments(self):
        cli = load("app-manifest")
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "app" / "onemind.app.yaml"
            f.parent.mkdir()
            text = (REPO / "apps" / "ntfy" / "onemind.app.yaml").read_text()
            f.write_text(text)
            self.assertEqual(cli.main(["convert", "--check", str(f)]), 1)
            self.assertEqual(f.read_text(), text)  # --check writes nothing
            self.assertEqual(cli.main(["convert", str(f)]), 0)
            out = f.read_text()
            self.assertEqual(out, text.replace("onemind.app/v1alpha1", "onemind.app/v1", 1))
            self.assertEqual(cli.main(["convert", "--check", str(f)]), 0)
            self.assertEqual(cli.main(["validate", str(f)]), 0)

    def test_cli_convert_fails_when_the_key_cannot_be_rewritten(self):
        cli = load("app-manifest")
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "app" / "onemind.app.yaml"
            f.parent.mkdir()
            text = (REPO / "apps" / "ntfy" / "onemind.app.yaml").read_text()
            odd = text.replace("apiVersion: onemind.app/v1alpha1", '"apiVersion": onemind.app/v1alpha1', 1)
            self.assertNotEqual(odd, text)
            f.write_text(odd)
            self.assertEqual(cli.main(["convert", str(f)]), 1)  # not "done" with exit 0
            self.assertEqual(f.read_text(), odd)  # nothing half-written

    def test_every_app_passes_the_shared_validator(self):
        failed = {}
        for path in sorted((REPO / "apps").glob("*/onemind.app.yaml")):
            errs = self.catalog.validate(yaml.safe_load(path.read_text()))
            if errs:
                failed[path.parent.name] = errs
        self.assertEqual(failed, {})


if __name__ == "__main__":
    unittest.main()
