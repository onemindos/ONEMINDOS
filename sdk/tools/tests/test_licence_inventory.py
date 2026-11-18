# SPDX-License-Identifier: Apache-2.0
"""Nondestructive computed SPDX inventory tests; fixtures stay in memory."""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1]
VALIDATOR = runpy.run_path(str(TOOLS / "validate-apps"))


class LicenceInventoryTests(unittest.TestCase):
    def check_in_memory(self, text):
        schema = json.loads(VALIDATOR["SCHEMA_PATH"].read_text(encoding="utf-8"))
        checker = VALIDATOR["AppChecker"](
            VALIDATOR["Draft202012Validator"](schema), "unused", "unused")
        output = io.StringIO()
        with patch.object(Path, "is_file", return_value=True), \
                patch.object(Path, "read_text", side_effect=text if isinstance(text, Exception) else None,
                             return_value=text), contextlib.redirect_stdout(output):
            result = checker.check(Path("apps/example"))
        return result, output.getvalue()

    def test_schema_errors_still_emit_actual_inventory(self):
        (app_id, errors), output = self.check_in_memory(
            '{"metadata": {"id": "example", "license": "GPL-3.0-only"}}')
        self.assertEqual(app_id, "example")
        self.assertTrue(errors)
        self.assertTrue(all(error.startswith("schema:") for error in errors))
        self.assertEqual(output, "licence apps/example/ computed_spdx_class=L2\n")

    def test_malformed_document_still_reports_schema_errors(self):
        for text in ("null", "[]", '"MIT"', '{"metadata": []}'):
            with self.subTest(text=text):
                (app_id, errors), output = self.check_in_memory(text)
                self.assertIsNone(app_id)
                self.assertTrue(errors)
                self.assertIn("schema:", errors[0])
                self.assertIn("computed_spdx_class=unavailable", output)

    def run_in_memory(self, app_ids=(), documents=None):
        root = Path("/inventory-test-apps")
        documents = documents or {"zeta": {"metadata": {"id": "same", "license": "GPL-2.0-only"}},
                                  "alpha": {"metadata": {"id": "same", "license": "MIT"}}}
        real_read = Path.read_text
        def read(path, *args, **kwargs):
            if path.parent.parent == root:
                doc = documents[path.parent.name]
                if isinstance(doc, Exception):
                    raise doc
                return json.dumps(doc)
            return real_read(path, *args, **kwargs)
        output = io.StringIO()
        # Both main's selected-app loop and its all-app host-port check read this directory.
        with patch.object(Path, "iterdir", lambda path: iter(root / name for name in documents)), \
                patch.object(Path, "is_dir", return_value=True), \
                patch.object(Path, "is_file", return_value=True), \
                patch.object(Path, "read_text", read), \
                patch("shutil.which", return_value="unused"), contextlib.redirect_stdout(output):
            code = VALIDATOR["main"](["--apps-dir", str(root), *app_ids])
        return code, output.getvalue()

    def test_main_orders_rows_preserves_duplicates_and_failure_count(self):
        code, output = self.run_in_memory()
        rows = [line for line in output.splitlines() if line.startswith("licence apps/")]
        self.assertEqual(rows, ["licence apps/alpha/ computed_spdx_class=L1",
                                "licence apps/zeta/ computed_spdx_class=L2"])
        self.assertEqual(code, 1)
        self.assertIn("duplicate metadata.id 'same'", output)
        self.assertIn("validate-apps: 0 passed, 2 failed", output)
        self.assertIn("ok   host ports", output)
        self.assertIn("SPDX-derived", output)
        self.assertIn("not declared metadata.licenceClass", output)
        self.assertIn("not primary-source verification, scan pass, or preinstall permission", output)

    def test_main_target_filter_and_repeat_are_stable(self):
        first = self.run_in_memory(("zeta",))
        self.assertEqual(first, self.run_in_memory(("zeta",)))
        code, output = first
        self.assertEqual(code, 1)
        self.assertIn("licence apps/zeta/ computed_spdx_class=L2", output)
        self.assertNotIn("apps/alpha/", output)
        self.assertNotIn("duplicate", output)
        self.assertIn("validate-apps: 0 passed, 1 failed", output)

    def test_unreadable_and_bad_yaml_are_errors_without_inventory(self):
        for text in (OSError("read failed"), UnicodeError("decode failed"), "metadata: ["):
            with self.subTest(text=str(text)):
                try:
                    (app_id, errors), output = self.check_in_memory(text)
                except (OSError, UnicodeError) as exc:
                    self.fail(f"unreadable manifest must return an error, not raise: {exc}")
                self.assertIsNone(app_id)
                self.assertTrue(errors)
                self.assertIn("onemind.app.yaml", errors[0])
                self.assertEqual(output, "")

    def test_main_unreadable_manifest_remains_an_error_in_all_app_checks(self):
        try:
            code, output = self.run_in_memory(documents={"broken": UnicodeError("decode failed")})
        except UnicodeError as exc:
            self.fail(f"all-app checks must preserve the unreadable error: {exc}")
        self.assertEqual(code, 1)
        self.assertIn("cannot be read", output)
        self.assertNotIn("licence apps/broken/", output)

    def test_main_invalid_host_ports_structure_still_reports_schema_error(self):
        try:
            code, output = self.run_in_memory(documents={"broken": {"spec": {"hostPorts": 1}}})
        except TypeError as exc:
            self.fail(f"invalid manifest must report schema errors, not crash: {exc}")
        self.assertEqual(code, 1)
        self.assertIn("schema: spec/hostPorts:", output)
        self.assertIn("computed_spdx_class=unavailable", output)

    def test_main_target_filter_keeps_all_app_host_port_checks(self):
        docs = {name: {"metadata": {"id": name, "license": "MIT"},
                       "spec": {"hostPorts": [{"port": 65534, "protocol": "TCP"}]}}
                for name in ("zeta", "alpha")}
        code, output = self.run_in_memory(("zeta",), docs)
        self.assertEqual(code, 1)
        self.assertIn("FAIL host ports", output)
        self.assertIn("both declare host port 65534/TCP", output)
        self.assertNotIn("licence apps/alpha/", output)

    def test_real_catalogue_coverage(self):
        # Optional retained CLI output proves integration without running subprocesses in this suite.
        root = TOOLS.parents[1] / "apps"
        app_dirs = sorted(path for path in root.iterdir()
                          if path.is_dir() and not path.name.startswith(("_", ".")))
        expected = []
        for app_dir in app_dirs:
            doc = VALIDATOR["yaml"].safe_load((app_dir / "onemind.app.yaml").read_text(encoding="utf-8"))
            expression = doc["metadata"]["license"]
            self.assertIsInstance(expression, str)
            computed = VALIDATOR["classify"](expression)
            expected.append(f"licence apps/{app_dir.name}/ computed_spdx_class={computed}")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            for app_dir in app_dirs:
                doc = VALIDATOR["yaml"].safe_load((app_dir / "onemind.app.yaml").read_text(encoding="utf-8"))
                VALIDATOR["licence_inventory"](doc, app_dir)
        self.assertTrue(expected)
        self.assertEqual(output.getvalue().splitlines(), expected)
        if os.environ.get("LICENCE_INVENTORY_LOG"):
            actual = Path(os.environ["LICENCE_INVENTORY_LOG"]).read_text(encoding="utf-8")
            self.assertEqual([line for line in actual.splitlines() if line.startswith("licence apps/")], expected)
            self.assertIn(f"validate-apps: {len(app_dirs)} passed, 0 failed", actual)
            self.assertIn("ok   renovate.json", actual)
        print(f"catalogue inventory coverage: {len(expected)} real manifests, exact computed classes")

    def test_existing_policy_is_used_unchanged(self):
        cases = {
            "GPL-2.0-only": "L2", "GPL-3.0-or-later": "L2",
            "BUSL-1.1": "blocked", "LicenseRef-unknown": "blocked",
            "MIT!": "blocked", "MIT OR": "blocked",
            "MIT OR (GPL-2.0-only WITH)": "blocked",
            "MIT AND (Apache-2.0 OR GPL-3.0-only)": "L1",
            "MIT AND GPL-3.0-only": "L2", "": "blocked",
        }
        for expression, expected in cases.items():
            with self.subTest(expression=expression):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    VALIDATOR["licence_inventory"](
                        {"metadata": {"license": expression, "licenceClass": "not-used"}},
                        Path("apps/example"))
                self.assertEqual(output.getvalue(),
                                 f"licence apps/example/ computed_spdx_class={expected}\n")

    def test_invalid_structures_have_no_fabricated_class(self):
        for doc in (None, [], "MIT", {}, {"metadata": []},
                    {"metadata": {"license": 3}}, {"metadata": {"license": ["MIT"]}}):
            with self.subTest(doc=doc):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    VALIDATOR["licence_inventory"](doc, Path("apps/example"))
                self.assertEqual(output.getvalue(),
                                 "licence apps/example/ computed_spdx_class=unavailable "
                                 "(metadata.license missing or not a string)\n")

    def test_mit_row_is_explicitly_computed(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            VALIDATOR["licence_inventory"]({"metadata": {"license": "MIT"}}, Path("apps/example"))
        self.assertEqual(output.getvalue(),
                         "licence apps/example/ computed_spdx_class=L1\n")
