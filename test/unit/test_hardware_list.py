# SPDX-License-Identifier: Apache-2.0
"""Certified hardware list (scripts/hardware_list.py, S-11): the shipped data is valid and current, and the
validator refuses a claim of support that no recorded test backs."""
import copy, importlib.util, os, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("hardware_list", os.path.join(ROOT, "scripts", "hardware_list.py"))
hl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hl)


class Shipped(unittest.TestCase):
    def test_data_valid(self):
        ms = hl.machines()
        self.assertGreaterEqual(len(ms), 4)
        for n, m in ms:
            self.assertEqual(hl.check_machine(n, m), [], n)
        self.assertEqual(hl.check_reference()[0], [])

    def test_table_is_current(self):
        with open(os.path.join(hl.HW, "CERTIFIED.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), hl.render())

    def test_nothing_certified_without_a_result(self):
        for n, m in hl.machines():
            if m["status"] == "proven":
                self.assertTrue(os.path.isfile(os.path.join(ROOT, m["result"])), n)


class Rules(unittest.TestCase):
    def base(self):
        return copy.deepcopy(dict(hl.machines())["beelink-u55.yaml"])

    def errs(self, m):
        return hl.check_machine("beelink-u55.yaml", m)

    def test_baseline_ok(self):
        self.assertEqual(self.errs(self.base()), [])

    def test_unproven_cannot_claim_support(self):
        m = self.base()
        m["what_works"] = ["boots"]
        self.assertTrue(any("no claim without a test" in e for e in self.errs(m)))

    def test_proven_needs_result_date_and_version(self):
        m = self.base()
        m["status"] = "proven"
        m["what_works"] = ["boots"]
        e = " ".join(self.errs(m))
        self.assertIn("result must be an existing file", e)
        self.assertIn("proven_on", e)
        self.assertIn("image_version", e)

    def test_proven_cannot_keep_unverified_specs(self):
        m = self.base()
        m.update(status="proven", what_works=["x"], result="lab-kits/hardware/reference-box.yaml",
                 proven_on="2026-12-13", image_version="0.1.0")
        self.assertTrue(any("UNVERIFIED" in e for e in self.errs(m)))

    def test_unknown_board_and_kit(self):
        m = self.base()
        m["board"], m["kit"] = "nope", "LT-NOPE"
        e = " ".join(self.errs(m))
        self.assertIn("not in os/boards", e)
        self.assertIn("not in lab-kits", e)

    def test_private_data_refused(self):
        m = self.base()
        m["network"] = "wired, " + ".".join(["192", "168", "1", "5"])
        self.assertTrue(any("private address" in e for e in self.errs(m)))

    def test_id_must_match_file(self):
        m = self.base()
        m["id"] = "other"
        self.assertTrue(any("id must equal" in e for e in self.errs(m)))


if __name__ == "__main__":
    unittest.main()
