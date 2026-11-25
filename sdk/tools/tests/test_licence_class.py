# SPDX-License-Identifier: Apache-2.0
"""metadata.licenceClass (issue #173): required by the schema, checked by validate-apps, filled by app-licence-class."""
import copy
import runpy
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parents[1]
VALIDATOR = runpy.run_path(str(TOOLS / "validate-apps"))
sys.path.insert(0, str(TOOLS))
from applib.licence import declared_class  # noqa: E402


def manifest(app_id="actual-budget"):
    return yaml.safe_load((REPO / "apps" / app_id / "onemind.app.yaml").read_text(encoding="utf-8"))


class LicenceClassTests(unittest.TestCase):
    def setUp(self):
        self.catalog = VALIDATOR["Catalog"](REPO / "apps", VALIDATOR["SCHEMA_PATH"])

    def test_schema_requires_the_field(self):
        doc = manifest()
        self.assertEqual(self.catalog.check_manifest(doc), [])
        del doc["metadata"]["licenceClass"]
        self.assertTrue(any("licenceClass" in e for e in self.catalog.check_manifest(doc)))

    def test_schema_refuses_an_unknown_class(self):
        doc = manifest()
        doc["metadata"]["licenceClass"] = "L3"
        self.assertTrue(any("licenceClass" in e for e in self.catalog.check_manifest(doc)))

    def test_a_green_claim_must_match_the_spdx_class(self):
        check = VALIDATOR["licence_class_errors"]
        meta = copy.deepcopy(manifest()["metadata"])
        self.assertEqual(check(meta), [])
        meta["license"] = "BUSL-1.1"  # source-available: blocked
        self.assertTrue(check(meta) and "classifies as blocked" in check(meta)[0])
        meta["licenceClass"] = "L2"  # a copyleft claim on a permissive licence is also a mismatch
        meta["license"] = "MIT"
        self.assertTrue(check(meta))

    def test_blocked_and_unknown_are_always_allowed(self):
        check = VALIDATOR["licence_class_errors"]
        for cls in ("blocked", "unknown"):
            meta = {**manifest()["metadata"], "licenceClass": cls}
            self.assertEqual(check(meta), [])

    def test_declared_class_never_turns_a_missing_licence_green(self):
        self.assertEqual(declared_class("MIT"), "L1")
        self.assertEqual(declared_class("AGPL-3.0"), "L2")
        self.assertEqual(declared_class("BUSL-1.1"), "blocked")
        for value in (None, "", "UNVERIFIED", "NOASSERTION"):
            self.assertEqual(declared_class(value), "unknown")

    def test_every_app_in_the_repo_declares_a_class_that_checks_out(self):
        check = VALIDATOR["licence_class_errors"]
        seen = {"L1": 0, "L2": 0, "blocked": 0, "unknown": 0}
        for path in sorted((REPO / "apps").glob("*/onemind.app.yaml")):
            meta = yaml.safe_load(path.read_text(encoding="utf-8"))["metadata"]
            self.assertIn(meta.get("licenceClass"), seen, path.parent.name)
            self.assertEqual(check(meta), [], path.parent.name)
            seen[meta["licenceClass"]] += 1
        self.assertGreater(seen["L1"], 0)
        self.assertGreater(seen["unknown"], 0)  # esphome and chromium stay out of the green class

    def test_migration_tool_has_nothing_left_to_do(self):
        result = subprocess.run([sys.executable, "-I", str(TOOLS / "app-licence-class"), "--check"],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
