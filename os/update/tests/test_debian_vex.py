# SPDX-License-Identifier: Apache-2.0
"""os/update/debian-vex.py: tracker states -> OpenVEX statements."""
import json, os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load, fixture  # noqa: E402

vex = load("debian-vex")


class Vex(unittest.TestCase):
    def setUp(self):
        self.st = vex.cs.parse_status(open(fixture("status-small.txt")).read())
        self.tr = json.load(open(fixture("tracker-small.json")))
        self.stm = vex.statements(self.st, self.tr)
        self.by = {s["vulnerability"]["name"]: s for s in self.stm}

    def test_states(self):
        self.assertEqual(self.by["CVE-2010-0002"]["status"], "not_affected")
        self.assertEqual(self.by["CVE-2010-0002"]["justification"], "vulnerable_code_not_present")
        self.assertEqual(self.by["CVE-2009-0591"]["status"], "not_affected")
        self.assertEqual(self.by["CVE-2099-0001"]["status"], "fixed")
        self.assertEqual(self.by["CVE-2099-0002"]["status"], "affected")
        self.assertIn("ignored", self.by["CVE-2099-0002"]["action_statement"])
        self.assertIn("postponed", self.by["CVE-2099-0003"]["action_statement"])
        # vulnerable and fixable (zlib), fix not yet in the archive (glibc 0004), TEMP ids: no statement
        for cve in ("CVE-2026-27171", "CVE-2099-0004", "TEMP-0841856-B18BAF", "CVE-2099-0005"):
            self.assertNotIn(cve, self.by)

    def test_products_cover_every_binary_of_the_source(self):
        ids = sorted(p["@id"] for p in self.by["CVE-2009-0591"]["products"])
        self.assertEqual(ids, ["pkg:deb/debian/libssl3t64@3.5.7-1~deb13u3?arch=arm64",
                               "pkg:deb/debian/openssl@3.5.7-1~deb13u3?arch=arm64"])
        self.assertEqual(vex.purl("zlib1g", "1:1.3.dfsg+really1.3.1-1+b1", "arm64"),
                         "pkg:deb/debian/zlib1g" + "@1.3.dfsg%2Breally1.3.1-1%2Bb1?arch=arm64&epoch=1")
        g = sorted(p["@id"] for p in self.by["CVE-2099-0002"]["products"])
        self.assertEqual(len(g), 2)

    def test_fixed_only_for_binaries_built_from_the_fixed_source(self):
        # libfoo1 still comes from foo 1.0-1 while foo-bin was upgraded to 1.0-2 (the fix): only
        # foo-bin may be suppressed; the older binary stays visible to the scanner.
        st = {"foo-bin": {"version": "1.0-2", "arch": "amd64", "source": "foo", "source_version": "1.0-2"},
              "libfoo1": {"version": "1.0-1", "arch": "amd64", "source": "foo", "source_version": "1.0-1"}}
        tr = {"foo": {"CVE-2099-0100": {"releases": {"trixie": {"status": "resolved", "fixed_version": "1.0-2"}}}}}
        (s,) = vex.statements(st, tr)
        self.assertEqual(s["status"], "fixed")
        self.assertEqual([p["@id"] for p in s["products"]], ["pkg:deb/debian/foo-bin@1.0-2?arch=amd64"])
        st["foo-bin"].update(version="1.0-1", source_version="1.0-1")
        self.assertEqual(vex.statements(st, tr), [])

    def test_document_is_deterministic_openvex(self):
        a = vex.document(self.stm, "2026-11-12T00:00:00Z", "vm")
        b = vex.document(vex.statements(self.st, self.tr), "2026-11-12T00:00:00Z", "vm")
        self.assertEqual(a, b)
        self.assertEqual(a["@context"], "https://openvex.dev/ns/v0.2.0")
        self.assertTrue(a["@id"].endswith("-vm"))
        self.assertTrue(all(s["timestamp"] == "2026-11-12T00:00:00Z" for s in a["statements"]))
        self.assertNotRegex(json.dumps(a), r"[\w.+-]+@[\w-]+\.[a-z]{2,}")   # no e-mail-shaped author


if __name__ == "__main__":
    unittest.main()
