# SPDX-License-Identifier: Apache-2.0
"""Quality tiers (issue #174): Bronze, Silver, Gold are computed from the gate's evidence, never typed.

Reads only files in the repository (no registry, no kustomize).
"""
import copy
import json
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "sdk" / "tools"))
from applib import quality  # noqa: E402

GOOD_IMAGE = {"ref": "ghcr.io/x/y:1@sha256:" + "a" * 64, "archs": ["amd64"],
              "trivy": {"critical_fixable": 0, "critical": 0, "high": 3},
              "clamav": {"signatures": "daily-28190", "infected": 0}, "secrets": 0, "cosign": "verified"}
SCAN = {"scanned_at": "2026-11-21T00:00:00Z", "result": "pass", "images": [GOOD_IMAGE],
        "licence": {"spdx": "MIT", "class": "L1"}, "smoke": "pass"}
MANIFEST = {"metadata": {"links": {"docs": "https://d.example/", "github": "https://github.com/x/y",
                                   "website": "UNVERIFIED", "support": "https://s.example/"}},
            "spec": {"updates": {"channel": "security", "automerge": "patch"}, "backup": {"mode": "hot"}}}
FACTS = {"upstream_alive": True, "non_root": True, "nothing_unverified": True}


def run(scan=None, manifest=None, facts=None):
    return quality.compute(scan or copy.deepcopy(SCAN), manifest or copy.deepcopy(MANIFEST), facts or dict(FACTS))


class TierRules(unittest.TestCase):
    def test_everything_true_is_gold(self):
        self.assertEqual(run()["tier"], "gold")

    def test_missing_gold_checks_cap_at_silver(self):
        for change in ("unsigned", "critical", "automerge", "backup"):
            scan, man = copy.deepcopy(SCAN), copy.deepcopy(MANIFEST)
            if change == "unsigned":
                scan["images"][0]["cosign"] = "unsigned"
            elif change == "critical":
                scan["images"][0]["trivy"]["critical"] = 1
            elif change == "automerge":
                man["spec"]["updates"]["automerge"] = "none"
            else:
                del man["spec"]["backup"]
            self.assertEqual(run(scan, man)["tier"], "silver", change)

    def test_missing_silver_checks_cap_at_bronze(self):
        scan = copy.deepcopy(SCAN)
        scan["smoke"] = "skipped"  # a skipped smoke test is no test
        self.assertEqual(run(scan)["tier"], "bronze")
        self.assertEqual(run(facts={**FACTS, "non_root": False})["tier"], "bronze")
        man = copy.deepcopy(MANIFEST)
        man["metadata"]["links"]["support"] = "UNVERIFIED"
        self.assertEqual(run(manifest=man)["tier"], "bronze")
        man = copy.deepcopy(MANIFEST)
        man["spec"]["updates"]["channel"] = "stable"
        self.assertEqual(run(manifest=man)["tier"], "bronze")

    def test_a_higher_level_never_lifts_a_failed_lower_one(self):
        # Gold checks all true but a Bronze check false: the tier is none.
        scan = copy.deepcopy(SCAN)
        scan["result"] = "fail"
        self.assertEqual(run(scan)["tier"], "none")
        self.assertEqual(run(facts={**FACTS, "upstream_alive": False})["tier"], "none")
        self.assertEqual(run(facts={**FACTS, "nothing_unverified": False})["tier"], "none")

    def test_bronze_needs_green_licence_and_clean_images(self):
        scan = copy.deepcopy(SCAN)
        scan["licence"]["class"] = "blocked"
        self.assertEqual(run(scan)["tier"], "none")
        for mutate in (lambda i: i["trivy"].update(critical_fixable=1), lambda i: i["clamav"].update(infected=1),
                       lambda i: i.update(secrets=1), lambda i: i["clamav"].update(signatures="daily-unknown")):
            scan = copy.deepcopy(SCAN)
            mutate(scan["images"][0])
            self.assertEqual(run(scan)["tier"], "none")
        scan = copy.deepcopy(SCAN)
        scan["images"] = []
        self.assertEqual(run(scan)["tier"], "none")

    def test_missing_facts_count_as_no(self):
        self.assertEqual(run(facts={"upstream_alive": True})["tier"], "none")

    def test_every_check_has_a_label(self):
        names = [n for lvl in quality.LEVELS for n in quality.CHECKS[lvl]]
        self.assertEqual(sorted(names), sorted(quality.LABELS))

    def test_manifest_cannot_set_the_tier(self):
        # Nothing in the manifest feeds a tier: a hand-typed field changes nothing here ...
        man = copy.deepcopy(MANIFEST)
        man["metadata"]["quality"] = "gold"
        scan = copy.deepcopy(SCAN)
        scan["images"][0]["cosign"] = "unsigned"
        self.assertEqual(run(scan, man)["tier"], "silver")
        # ... and the closed schema rejects the field outright.
        schema = json.loads((REPO / "sdk" / "schema" / "onemind.app.schema.json").read_text(encoding="utf-8"))
        self.assertNotIn("quality", schema["properties"]["metadata"]["properties"])
        self.assertIs(schema["properties"]["metadata"].get("additionalProperties"), False)


class ClaimsAndRecords(unittest.TestCase):
    def test_claim_error_only_for_an_overclaim(self):
        self.assertIsNone(quality.claim_error(None, "none"))
        self.assertIsNone(quality.claim_error({"result": "pass"}, "none"))
        self.assertIsNone(quality.claim_error({"quality": {"tier": "silver"}}, "gold"))
        self.assertIsNone(quality.claim_error({"quality": {"tier": "silver"}}, "silver"))
        self.assertIn("gold", quality.claim_error({"quality": {"tier": "gold"}}, "bronze"))

    def test_tier_of_is_defensive(self):
        for bad in (None, "gold", [], {}, {"bronze": "yes"}, {"bronze": {n: 1 for n in quality.CHECKS["bronze"]}}):
            self.assertEqual(quality.tier_of(bad), "none")

    def test_verify_record(self):
        scan = copy.deepcopy(SCAN)
        scan["quality"] = run()
        self.assertIsNone(quality.verify_record(scan, MANIFEST))
        scan["quality"]["tier"] = "gold"
        scan["images"][0]["cosign"] = "unsigned"  # evidence no longer matches the scan
        self.assertIn("images_signed", quality.verify_record(scan, MANIFEST))
        forged = copy.deepcopy(SCAN)
        forged["quality"] = {"tier": "gold", "evidence": {"bronze": {n: True for n in quality.CHECKS["bronze"]}}}
        self.assertIn("does not follow", quality.verify_record(forged, MANIFEST))


class CommittedScans(unittest.TestCase):
    """Every quality record committed under apps/ must follow from its own evidence."""

    def test_committed_records_verify(self):
        yaml = __import__("yaml")
        checked = 0
        for scan_file in sorted((REPO / "apps").glob("*/scan.json")):
            scan = json.loads(scan_file.read_text(encoding="utf-8"))
            if "quality" not in scan:
                continue
            manifest = yaml.safe_load((scan_file.parent / "onemind.app.yaml").read_text(encoding="utf-8"))
            self.assertIsNone(quality.verify_record(scan, manifest), scan_file.parent.name)
            checked += 1
        self.assertGreaterEqual(checked, 0)

    def test_no_manifest_types_a_quality_field(self):
        for f in (REPO / "apps").glob("*/onemind.app.yaml"):
            self.assertIsNone(re.search(r"(?m)^\s+quality\s*:", f.read_text(encoding="utf-8")), f.parent.name)


if __name__ == "__main__":
    unittest.main()
