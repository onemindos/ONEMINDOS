# SPDX-License-Identifier: Apache-2.0
"""Manifest v1 (#604): the golden manifest covers every block, and the shared cases get the same verdict
from the gateway's Catalog.validate here as from the Go validator (internal/plugin/validate/blocks_test.go)."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "core"))
from onemind_core.catalog import Catalog  # noqa: E402
from onemind_core.manifest_rules import ManifestRules, block_errors  # noqa: E402

SCHEMA_PATH = REPO / "sdk" / "schema" / "onemind.app.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text())
GOLDEN = REPO / "sdk" / "testdata" / "manifest-v1"
BASE = yaml.safe_load((GOLDEN / "base.yaml").read_text())
CASES = yaml.safe_load((GOLDEN / "cases.yaml").read_text())

# Blocks older than #604 that a container plugin cannot also carry, each covered by its own tests.
NOT_IN_GOLDEN_SPEC = {"agent", "system", "credentials", "web", "browser", "settings", "dependencies", "hostPorts",
                      "streams", "secrets", "database"}
NOT_IN_GOLDEN_EXT = {"widgets", "settings", "alerts", "tiles", "events"}
ADDED_SPEC = {"runtime", "placement", "data", "services", "search", "share", "notifications", "mapLayers", "jobs",
              "roles", "continue", "needs", "terms", "recommends", "supports"}
ADDED_EXT = {"bridge", "connector", "videoSource", "nats"}


def apply(doc: dict, ops: list[dict]) -> dict:
    """The tiny JSON-pointer patcher both test suites implement: set (value or join) and remove."""
    doc = copy.deepcopy(doc)
    for op in ops:
        *parents, last = op["path"].lstrip("/").split("/")
        node = doc
        for part in parents:
            node = node[int(part)] if isinstance(node, list) else node[part]
        key = int(last) if isinstance(node, list) else last
        if op["op"] == "remove":
            del node[key]
        else:
            node[key] = "".join(op["join"]) if "join" in op else op["value"]
    return doc


class ManifestBlocksTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog(REPO / "apps", SCHEMA_PATH)

    def test_the_golden_manifest_covers_every_block(self):
        spec = SCHEMA["properties"]["spec"]["properties"]
        ext = spec["extensions"]["properties"]
        self.assertLessEqual(ADDED_SPEC, set(spec))
        self.assertLessEqual(ADDED_EXT, set(ext))
        self.assertEqual(set(spec) - set(BASE["spec"]), NOT_IN_GOLDEN_SPEC)
        self.assertEqual(set(ext) - set(BASE["spec"]["extensions"]), NOT_IN_GOLDEN_EXT)
        for name in ("pre", "post", "restore", "verify"):  # the backup hooks
            self.assertIn(name, BASE["spec"]["backup"])

    def test_valid_cases_pass(self):
        self.assertTrue(CASES["valid"])
        for case in CASES["valid"]:
            with self.subTest(case["name"]):
                self.assertEqual(self.catalog.validate(apply(BASE, case["ops"])), [])

    def test_invalid_cases_fail_for_their_rule(self):
        self.assertGreaterEqual(len(CASES["invalid"]), 40)
        for case in CASES["invalid"]:
            with self.subTest(case["name"]):
                errs = self.catalog.validate(apply(BASE, case["ops"]))
                self.assertTrue(errs, "accepted")
                if "expect" in case:
                    self.assertTrue(any(case["expect"] in e for e in errs), errs)

    def test_errors_never_repeat_a_credential(self):
        for case in CASES["invalid"]:
            joined = [op for op in case["ops"] if "join" in op]
            for op in joined:
                secret = "".join(op["join"])
                with self.subTest(case["name"]):
                    errs = self.catalog.validate(apply(BASE, case["ops"]))
                    self.assertFalse([e for e in errs if secret in e or op["join"][-1] in e], errs)
        doc = apply(BASE, [{"op": "set", "path": "/spec/extensions/bridge/hosts/0", "join": ["AKIA", "ABCDEFGHIJKLMNOP"]}])
        errs = self.catalog.validate(doc)
        self.assertTrue(errs)
        self.assertFalse([e for e in errs if "ABCDEFGHIJKLMNOP" in e], errs)

    def test_a_credential_returns_only_the_credential_errors_like_go(self):
        # A schema message can quote a whole block (not, oneOf, maxItems), so with a credential-named field
        # inside it the gateway returns the credential errors alone, as validateCredentials does in Go.
        for case in CASES["invalid"]:
            if case.get("expect") != "holds a credential value":
                continue
            with self.subTest(case["name"]):
                errs = self.catalog.check_manifest(apply(BASE, case["ops"]))
                self.assertTrue(errs)
                self.assertEqual([e for e in errs if "holds a credential value" not in e], [], errs)

    def test_the_credential_scan_stays_fast_on_a_hostile_string(self):
        # Python's re backtracks; every repeat in credentialValue is bounded, so a long string costs linear time.
        import time
        for probe in ("https://" + "a" * 200000 + ":" + "b" * 2000, "a+" * 100000, "-----BEGIN " + "A " * 100000):
            doc = apply(BASE, [{"op": "set", "path": "/spec/notifications/topics/0/actions/0/args/note", "value": probe}])
            started = time.monotonic()
            self.catalog.validate(doc)
            self.assertLess(time.monotonic() - started, 5)

    def test_every_app_in_the_repo_still_validates(self):
        found = self.catalog.load()
        self.assertTrue(found)
        self.assertEqual(self.catalog.errors, {})

    # A map or list where the cross-field rules expect a name: before the fix each raised TypeError
    # (unhashable type) out of Catalog.validate instead of returning an error.
    UNHASHABLE = (
        ("a host that is a map", "/spec/extensions/bridge/hosts/0", {"name": "earthquake.usgs.gov"}),
        ("a provider id that is a list", "/spec/terms/providers/0/id", ["usgs"]),
        ("a block provider that is a list", "/spec/extensions/bridge/provider", ["usgs"]),
        ("a job tool that is a map", "/spec/jobs/0/tool", {"name": "recent"}),
        ("an emit name that is a list", "/spec/extensions/bridge/emits/0/name", ["quakes"]),
        ("a notification action tool that is a list", "/spec/notifications/topics/0/actions/0/tool", ["recent"]),
        ("a tool name that is a map", "/spec/extensions/tools/0/name", {"name": "recent"}),
        ("a map layer id that is a list", "/spec/mapLayers/0/id", ["quakes"]),
    )

    def _bad(self, path, value):
        return apply(BASE, [{"op": "set", "path": path, "value": value}])

    def test_a_map_or_list_where_a_name_belongs_is_an_error_not_a_crash(self):
        for name, path, value in self.UNHASHABLE:
            with self.subTest(name):
                self.assertTrue(self.catalog.validate(self._bad(path, value)))
                self.assertTrue(self.catalog.check_manifest(self._bad(path, value)))
                # They are golden cases too, so the Go validator is held to the same verdict.
                self.assertIn(name, {c["name"] for c in CASES["invalid"]})

    def test_the_cross_field_rules_never_hash_an_unchecked_value(self):
        # block_errors is public: called on a spec the schema never saw, it names the bad field.
        for name, path, value in self.UNHASHABLE:
            with self.subTest(name):
                spec = self._bad(path, value)["spec"]
                self.assertTrue(block_errors(spec), name)

    def test_one_malformed_manifest_names_its_folder_and_the_catalog_still_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            good = copy.deepcopy(BASE)
            (root / good["metadata"]["id"]).mkdir()
            (root / good["metadata"]["id"] / "onemind.app.yaml").write_text(yaml.safe_dump(good))
            bad = self._bad("/spec/extensions/bridge/hosts/0", {"name": "earthquake.usgs.gov"})
            bad["metadata"]["id"] = "broken-app"
            (root / "broken-app").mkdir()
            (root / "broken-app" / "onemind.app.yaml").write_text(yaml.safe_dump(bad))
            catalog = Catalog(root, SCHEMA_PATH)
            found = catalog.load()
            self.assertIn(good["metadata"]["id"], found)
            self.assertIn("broken-app", catalog.errors)

    def test_v1_rules_run_for_the_app_schema_and_skip_a_schema_without_its_patterns(self):
        # The real schema always carries the credential patterns, so the v1 rules are on in CI and on the box;
        # a hand-written schema without them (tests, an older channel) still loads instead of crashing the catalog.
        self.assertIsNotNone(ManifestRules.for_schema(SCHEMA))
        self.assertIsNotNone(self.catalog._rules)
        self.assertIsNone(ManifestRules.for_schema({"type": "object"}))
        self.assertIsNone(ManifestRules.for_schema({"$defs": {"credentialValue": {"pattern": "x"}}}))


if __name__ == "__main__":
    unittest.main()
