# SPDX-License-Identifier: Apache-2.0
"""A committed app tier must agree with the committed scan.json (issue #117).

The CI gate (sdk/tools/app-gate) computes the tier from a scan: licence class blocked, a ClamAV hit or
a CRITICAL with a fix gives blocked; otherwise a failed scan gives community and a passed one can be
verified. `--tier write` never lifts a human 'blocked', so a stale 'blocked' stays forever unless a
person moves it. These tests read only files in the repository (no registry, no kustomize).
"""
import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
APPS = REPO / "apps"
RANK = {"blocked": 0, "community": 1, "verified": 2}
# Blocked on purpose by a founder decision, not by the scan (docs/DECISIONS.md D21-D26: PrivateBin
# stays blocked until login gating). Add an app here only with the decision that holds it.
HUMAN_HOLDS = {"privatebin"}


def declared_tier(app_dir):
    m = re.search(r"(?m)^  tier:\s*(verified|community|blocked)\b",
                  (app_dir / "onemind.app.yaml").read_text(encoding="utf-8"))
    return m.group(1) if m else None


def pinned_refs(app_dir):
    refs = set()
    for f in (app_dir / "manifests").glob("*.y*ml"):
        refs.update(re.findall(r"image:\s*[\"']?(\S+@sha256:[0-9a-f]{64})", f.read_text(encoding="utf-8")))
    return refs


def scan_tier_ceiling(scan):
    """The highest tier this scan allows, as the gate computes it (health and UNVERIFIED aside)."""
    images = scan["images"]
    if scan["licence"]["class"] == "blocked" or any(
            i["clamav"]["infected"] or i["trivy"]["critical_fixable"] for i in images):
        return "blocked"
    return "verified" if scan["result"] == "pass" else "community"


def current_scans():
    """(app id, declared tier, scan) for every app whose committed scan covers exactly the pinned images."""
    for app_dir in sorted(APPS.glob("*/onemind.app.yaml")):
        app_dir = app_dir.parent
        scan_file = app_dir / "scan.json"
        if not scan_file.is_file():
            continue
        scan = json.loads(scan_file.read_text(encoding="utf-8"))
        if {i["ref"] for i in scan["images"]} != pinned_refs(app_dir):
            continue  # stale scan: the daily rescan refreshes it, nothing to compare yet
        yield app_dir.name, declared_tier(app_dir), scan


class AppTierTests(unittest.TestCase):
    def test_there_are_scans_to_compare(self):
        self.assertGreater(len(list(current_scans())), 20)

    def test_tier_never_claims_more_than_the_scan_allows(self):
        for app, tier, scan in current_scans():
            with self.subTest(app=app):
                self.assertLessEqual(RANK[tier], RANK[scan_tier_ceiling(scan)],
                                     f"{app}: tier {tier} but the committed scan allows {scan_tier_ceiling(scan)}")

    def test_blocked_needs_a_blocking_finding_or_a_recorded_hold(self):
        for app, tier, scan in current_scans():
            if tier != "blocked" or app in HUMAN_HOLDS:
                continue
            with self.subTest(app=app):
                self.assertEqual(scan_tier_ceiling(scan), "blocked",
                                 f"{app} is tier blocked, but its committed scan has no CRITICAL with a fix, no "
                                 "ClamAV hit and no blocked licence: move the tier to what the scan allows")

    def test_a_scan_that_passes_is_not_blocked(self):
        for app, tier, scan in current_scans():
            if scan["result"] == "pass" and app not in HUMAN_HOLDS:
                with self.subTest(app=app):
                    self.assertNotEqual(tier, "blocked")


if __name__ == "__main__":
    unittest.main()
