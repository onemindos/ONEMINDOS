# SPDX-License-Identifier: Apache-2.0
"""Market unblock (issue #147, UMB-P10): bumped pins carry a committed scan of exactly those pins.

An app leaves tier 'blocked' only when the committed CI scan (sdk/tools/app-gate, run by ci-apps) of
the images it pins has no CRITICAL with a fix, no ClamAV hit and no blocked licence. An app whose
newer pin still fails keeps tier 'blocked' with the real reason. These tests read only files in the
repository (no registry, no scanner); the scans themselves come from the PR's own ci-apps gate run.
"""
import json
import re
import unittest
from pathlib import Path

from test_app_tiers import pinned_refs, scan_tier_ceiling, declared_tier

APPS = Path(__file__).resolve().parents[3] / "apps"

# app id -> (image repository, tag pinned after the bump), newest upstream release on 2026-11-23
BUMPED = {
    "home-assistant": ("ghcr.io/home-assistant/home-assistant", "2026.11.2"),
    "audiobookshelf": ("ghcr.io/advplyr/audiobookshelf", "2.38.0"),
    "copyparty": ("docker.io/copyparty/ac", "1.20.27"),
}
# Scanned clean of fixable CRITICALs on linux/amd64 and linux/arm64 after the bump.
UNBLOCKED = {"copyparty"}


def scan(app):
    return json.loads((APPS / app / "scan.json").read_text(encoding="utf-8"))


class MarketUnblockTests(unittest.TestCase):
    def test_bumped_apps_pin_the_new_release_by_digest(self):
        for app, (repo, tag) in BUMPED.items():
            with self.subTest(app=app):
                refs = pinned_refs(APPS / app)
                self.assertTrue(refs, f"{app}: no digest-pinned image")
                self.assertIn(f"{repo}:{tag}", {r.split("@")[0] for r in refs})
                manifest = (APPS / app / "onemind.app.yaml").read_text(encoding="utf-8")
                self.assertRegex(manifest, rf'(?m)^  version: "{re.escape(tag)}"$')

    def test_committed_scan_covers_exactly_the_pinned_images(self):
        for app in BUMPED:
            with self.subTest(app=app):
                self.assertEqual({i["ref"] for i in scan(app)["images"]}, pinned_refs(APPS / app),
                                 f"{app}: scan.json is not the gate's scan of the pinned images")
                for image in scan(app)["images"]:
                    self.assertEqual(sorted(image["archs"]), ["amd64", "arm64"])

    def test_unblocked_apps_have_a_clean_scan_and_leave_blocked(self):
        for app in UNBLOCKED:
            with self.subTest(app=app):
                self.assertNotEqual(scan_tier_ceiling(scan(app)), "blocked")
                self.assertNotEqual(declared_tier(APPS / app), "blocked")

    def test_apps_whose_new_pin_still_fails_stay_blocked_with_the_reason(self):
        for app in set(BUMPED) - UNBLOCKED:
            with self.subTest(app=app):
                self.assertEqual(scan_tier_ceiling(scan(app)), "blocked")
                self.assertEqual(declared_tier(APPS / app), "blocked")
                readme = (APPS / app / "README.md").read_text(encoding="utf-8")
                self.assertIn("## Why this app is blocked", readme)
                for image in scan(app)["images"]:
                    if image["trivy"]["critical_fixable"]:
                        self.assertIn(image["ref"].split("@")[0], readme)


if __name__ == "__main__":
    unittest.main()
