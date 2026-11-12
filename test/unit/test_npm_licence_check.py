# SPDX-License-Identifier: Apache-2.0
"""scripts/npm-licence-check.py: SPDX expressions, exact pins, and the committed ui/test lockfile."""
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_loader = importlib.machinery.SourceFileLoader("npm_licence_check", str(ROOT / "scripts" / "npm-licence-check.py"))
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
nlc = importlib.util.module_from_spec(_spec)
_loader.exec_module(nlc)

# The allowlist .github/workflows/ui-quality.yml passes for ui/test (axe-core is MPL-2.0, test-only).
UI_TEST_ALLOW = {"Apache-2.0", "MIT", "MPL-2.0"}


def project(pkg: dict, packages: dict) -> Path:
    d = Path(tempfile.mkdtemp())
    (d / "package.json").write_text(json.dumps(pkg))
    (d / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3, "packages": {"": {}, **packages}}))
    return d


class Expressions(unittest.TestCase):
    def test_simple_and_compound(self):
        allow = {"MIT", "Apache-2.0"}
        self.assertTrue(nlc.satisfied("MIT", allow))
        self.assertFalse(nlc.satisfied("GPL-3.0-only", allow))
        self.assertTrue(nlc.satisfied("BSD-3-Clause OR MIT", allow))
        self.assertTrue(nlc.satisfied("(MIT OR GPL-2.0) AND Apache-2.0", allow))
        self.assertFalse(nlc.satisfied("MIT AND GPL-2.0", allow))
        self.assertFalse(nlc.satisfied("(MIT AND GPL-2.0) OR LGPL-3.0", allow))

    def test_malformed(self):
        for bad in ("MIT OR", "(MIT", "MIT)", "AND MIT", "MIT WITH Classpath-exception-2.0"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                nlc.satisfied(bad, {"MIT"})


class Projects(unittest.TestCase):
    def test_clean(self):
        d = project({"devDependencies": {"a": "1.2.3"}},
                    {"node_modules/a": {"version": "1.2.3", "license": "MIT"},
                     "node_modules/a/node_modules/b": {"version": "0.1.0-rc.1", "license": "Apache-2.0"}})
        self.assertEqual(nlc.check(d, {"MIT", "Apache-2.0"}), [])

    def test_findings(self):
        d = project({"dependencies": {"a": "^1.2.3", "b": "latest"}, "devDependencies": {"c": "~2.0.0"}},
                    {"node_modules/a": {"version": "1.2.3", "license": "GPL-3.0-only"},
                     "node_modules/b": {"version": "2.0.0"},
                     "node_modules/c": {"version": "2.0.0", "license": "MIT"}})
        got = nlc.check(d, {"MIT"})
        self.assertEqual(len(got), 5, got)
        self.assertTrue(any("'^1.2.3' is not an exact version" in p for p in got))
        self.assertTrue(any("a@1.2.3: licence 'GPL-3.0-only' is not allowed" in p for p in got))
        self.assertTrue(any("b@2.0.0: no licence" in p for p in got))

    def test_exit_codes(self):
        ok = project({}, {"node_modules/a": {"version": "1.0.0", "license": "MIT"}})
        bad = project({}, {"node_modules/a": {"version": "1.0.0", "license": "SSPL-1.0"}})
        with open(os.devnull, "w") as null:
            import contextlib
            with contextlib.redirect_stdout(null), contextlib.redirect_stderr(null):
                self.assertEqual(nlc.main([str(ok), "--allow", "MIT"]), 0)
                self.assertEqual(nlc.main([str(bad), "--allow", "MIT"]), 1)
                self.assertEqual(nlc.main([str(ok.parent / "does-not-exist"), "--allow", "MIT"]), 2)

    def test_committed_ui_browser_tests(self):
        """ui/test (Playwright + axe) is pinned exactly and stays within its allowlist."""
        self.assertEqual(nlc.check(ROOT / "ui" / "test", UI_TEST_ALLOW), [])


if __name__ == "__main__":
    unittest.main()
