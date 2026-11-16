# SPDX-License-Identifier: Apache-2.0
"""Fail-closed SPDX syntax regressions; no network or filesystem cleanup."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
from applib import licence  # noqa: E402


def load_gate():
    loader = importlib.machinery.SourceFileLoader("licence_gate_tool", str(TOOLS / "app-gate"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class LicenceExpressionTests(unittest.TestCase):
    def test_missing_exception_cannot_hide_behind_or(self):
        for expr in ("MIT OR GPL-2.0-only WITH", "MIT OR (GPL-2.0-only WITH)"):
            with self.subTest(expr=expr):
                self.assertEqual(licence.classify(expr), "blocked")

    def test_exception_requires_single_license_not_group(self):
        for expr in ("(MIT OR GPL-2.0-only) WITH Linux-syscall-note",
                     "(MIT) WITH LLVM-exception",
                     "MIT OR (GPL-2.0-only) WITH Linux-syscall-note"):
            with self.subTest(expr=expr):
                self.assertEqual(licence.classify(expr), "blocked")

    def test_valid_exceptions_keep_existing_policy(self):
        for expr, want in (("GPL-2.0-only WITH Linux-syscall-note", "L2"),
                           ("MIT OR GPL-2.0-only WITH Linux-syscall-note", "L1"),
                           ("(MIT OR GPL-2.0-only WITH Linux-syscall-note) AND BSD-2-Clause", "L1"),
                           ("GPL-2.0-only WITH LicenseRef-unknown", "blocked"),
                           ("MIT OR GPL-2.0-only WITH LicenseRef-unknown", "L1")):
            with self.subTest(expr=expr):
                self.assertEqual(licence.classify(expr), want)

    def test_app_gate_rejects_malformed_confirmed_expression(self):
        # Exercise the real gate consumer without scans, cluster writes or fake passes.
        module = load_gate()
        expr = "(MIT OR GPL-2.0-only) WITH Linux-syscall-note"
        consumer = module.Gate(TOOLS.parents[1] / "apps" / "uptime-kuma", None, None, None)
        consumer.meta["license"] = expr
        result = consumer.licence_gate({"license": {"spdx_id": "MIT"}}, None)
        self.assertEqual(result, {"spdx": expr, "class": "blocked"})
        self.assertFalse(consumer.checks["licence"].ok)
        self.assertTrue(any("not allowed" in n for n in consumer.checks["licence"].notes))


if __name__ == "__main__":
    unittest.main()
