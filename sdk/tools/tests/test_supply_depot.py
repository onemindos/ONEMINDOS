# SPDX-License-Identifier: Apache-2.0
"""Issue 129 (Supply Depot): tier claims are honest and the progress file has no merge leftovers.

No registry or scan is run here; the committed claims are checked against what evidence is
committed. A package may claim `verified` only with a committed scan.json that says "pass".
"""
from __future__ import annotations

import json
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[3]
DEPOT = ["archivebox", "collabora-code", "cyberchef", "it-tools", "libretranslate"]


class SupplyDepotTests(unittest.TestCase):
    def manifest(self, app):
        return yaml.safe_load((ROOT / "apps" / app / "onemind.app.yaml").read_text())

    def test_five_packages_exist(self):
        for app in DEPOT:
            self.assertTrue((ROOT / "apps" / app / "manifests/kustomization.yaml").is_file(), app)

    def test_no_verified_claim_without_passing_scan(self):
        for app in DEPOT:
            tier = self.manifest(app)["metadata"]["tier"]
            self.assertIn(tier, {"community", "blocked"} | ({"verified"} if self._passes(app) else set()), app)

    def test_collabora_stays_blocked(self):
        self.assertEqual(self.manifest("collabora-code")["metadata"]["tier"], "blocked")

    def test_tier_comment_does_not_claim_ci_set_it_by_hand(self):
        for app in DEPOT:
            text = (ROOT / "apps" / app / "onemind.app.yaml").read_text()
            self.assertNotIn("set by CI (sdk/tools/app-gate --tier write), not by hand", text, app)

    def test_libretranslate_model_licence_is_unverified(self):
        self.assertIn("UNVERIFIED", (ROOT / "apps/libretranslate/README.md").read_text())

    def test_progress_file_has_no_conflict_markers(self):
        text = (ROOT / "docs/leap/run-2026-11-19/progress/lane-6-apps.md").read_text()
        for marker in ("<<<<<<<", "=======\n", ">>>>>>>"):
            self.assertNotIn(marker, text)
        self.assertIn("## Draft (pushed, not ready yet)", text)
        self.assertIn("## #129", text)

    @staticmethod
    def _passes(app):
        p = ROOT / "apps" / app / "scan.json"
        return p.is_file() and json.loads(p.read_text()).get("result") == "pass"


if __name__ == "__main__":
    unittest.main()
