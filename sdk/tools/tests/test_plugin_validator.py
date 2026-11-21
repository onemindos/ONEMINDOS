# SPDX-License-Identifier: Apache-2.0
"""CI executes the built box validator, including checks absent from JSON Schema."""
from __future__ import annotations

import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
VALIDATE = runpy.run_path(str(ROOT / "sdk/tools/validate-apps"))
AppChecker = VALIDATE["AppChecker"]
SCHEMA = json.loads((ROOT / "sdk/schema/onemind.app.schema.json").read_text())


class PluginValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix="onemind-plugin-validator-")
        cls.addClassCleanup(cls.build.cleanup)
        cls.binary = Path(os.environ.get("ONEMIND_PLUGIN_VALIDATOR", str(Path(cls.build.name) / "onemind")))
        if "ONEMIND_PLUGIN_VALIDATOR" not in os.environ:
            # Build real production CLI code once; there is no success stub.
            subprocess.run(["go", "build", "-trimpath", "-buildvcs=false", "-o", str(cls.binary),
                            "./cmd/onemind"], cwd=ROOT, check=True, capture_output=True, timeout=180)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="onemind-plugin-ci-")
        self.addCleanup(self.temp.cleanup)
        self.app = Path(self.temp.name) / "uptime-kuma"
        self.app.mkdir()
        self.doc = yaml.safe_load((ROOT / "apps/uptime-kuma/onemind.app.yaml").read_text())
        self.doc["metadata"]["publisher"] = {"id": "example-dev", "name": "Example Dev"}
        self.doc["spec"].pop("manifests")
        self.doc["spec"].pop("web", None)
        self.doc["spec"]["compat"] = {"onemind": ">=0.3 <1.0"}
        self.doc["spec"]["extensions"] = {"settings": {"schema": "settings.schema.json"}}
        (self.app / "icon.svg").write_text("<svg/>")
        (self.app / "settings.schema.json").write_text('{"type":"object","additionalProperties":false}')
        self.write_manifest()

    def write_manifest(self):
        (self.app / "onemind.app.yaml").write_text(yaml.safe_dump(self.doc))

    def checker(self, binary):
        # A declarative bundle must never invoke these workload tools.
        return AppChecker(Draft202012Validator(SCHEMA), "/no-workload/kustomize",
                          "/no-workload/kubeconform", binary)

    def test_real_box_validator_accepts_declarative_bundle(self):
        app_id, errors = self.checker(self.binary).check(self.app)
        self.assertEqual(app_id, "uptime-kuma")
        self.assertEqual(errors, [])

    def test_cli_uses_explicit_binary_and_inherited_ci_environment(self):
        command = [sys.executable, "-I", str(ROOT / "sdk/tools/validate-apps"),
                   "--apps-dir", self.temp.name]
        for flag in (True, False):
            with self.subTest(flag=flag):
                env = dict(os.environ)
                env.pop("ONEMIND_PLUGIN_VALIDATOR", None)
                args = command + (["--plugin-validator", str(self.binary)] if flag else [])
                if not flag:
                    env["ONEMIND_PLUGIN_VALIDATOR"] = str(self.binary)
                result = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("1 passed, 0 failed", result.stdout)

    def test_schema_valid_manifest_with_invalid_settings_schema_is_rejected(self):
        self.assertEqual(list(Draft202012Validator(SCHEMA).iter_errors(self.doc)), [])
        (self.app / "settings.schema.json").write_text('{"type":"not-a-json-schema-type"}')
        _, errors = self.checker(self.binary).check(self.app)
        self.assertTrue(any("shared validator failed" in e for e in errors), errors)

    def test_missing_bundle_reference_is_rejected_by_box_validator(self):
        (self.app / "settings.schema.json").unlink()
        _, errors = self.checker(self.binary).check(self.app)
        self.assertTrue(any("shared validator failed" in e for e in errors), errors)

    def test_plugin_validation_fails_closed_without_explicit_binary(self):
        for binary in (None, Path("onemind"), self.app / "missing-onemind"):
            with self.subTest(binary=binary):
                _, errors = self.checker(binary).check(self.app)
                self.assertTrue(any("shared validator" in e for e in errors), errors)

    def test_ordinary_app_does_not_require_plugin_binary(self):
        # Retain the normal workload checks and do not invent a plugin dependency.
        for field in ("extensions", "plugin", "permissions", "compat"):
            self.doc["spec"].pop(field, None)
        self.doc["spec"]["manifests"] = "manifests/"
        self.write_manifest()
        _, errors = self.checker(None).check(self.app)
        self.assertTrue(any("spec.manifests directory" in e for e in errors), errors)
        self.assertFalse(any("shared validator" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
