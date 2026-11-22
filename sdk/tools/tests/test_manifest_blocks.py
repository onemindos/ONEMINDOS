# SPDX-License-Identifier: Apache-2.0
"""Manifest v1 (#604): the golden manifest covers every block, and the shared cases get the same verdict
from the gateway's Catalog.validate here as from the Go validator (internal/plugin/validate/blocks_test.go)."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "core"))
from onemind_core.catalog import Catalog  # noqa: E402

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
              "roles", "continue", "needs", "terms"}
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

    def test_every_app_in_the_repo_still_validates(self):
        found = self.catalog.load()
        self.assertTrue(found)
        self.assertEqual(self.catalog.errors, {})


if __name__ == "__main__":
    unittest.main()
