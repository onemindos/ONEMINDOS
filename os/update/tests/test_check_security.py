# SPDX-License-Identifier: Apache-2.0
"""os/update/check-security.py: dpkg version order and debsecan-style matching (recorded fixture)."""
import json, os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load, fixture  # noqa: E402

cs = load("check-security")


class Vercmp(unittest.TestCase):
    def test_dpkg_order(self):
        # pairs from deb-version(7) and dpkg's own test suite: a < b
        for a, b in [("1.0", "1.1"), ("1.0~rc1", "1.0"), ("1.0", "1.0+b1"), ("1:0.1", "2:0.0"),
                     ("2.41-12+deb13u4", "2.41-12+deb13u5"), ("3.5.7-1~deb13u2", "3.5.7-1~deb13u3"),
                     ("1:1.3.dfsg+really1.3.1-1", "1:1.3.dfsg+really1.3.1-1+deb13u1"), ("1.0-1", "1.0-1.1"),
                     ("1.0a", "1.0b"), ("1.0", "1.0a"), ("1.9", "1.10"), ("0~", "0"), ("1.0-1", "1.0.1-1"),
                     ("5.2.37-2", "5.2.37-2+b10"), ("9", "1:0")]:
            self.assertLess(cs.vercmp(a, b), 0, f"{a} < {b}")
            self.assertGreater(cs.vercmp(b, a), 0, f"{b} > {a}")
        for a, b in [("1.0", "1.0-0"), ("0:1.0", "1.0"), ("1.0", "1.00"), ("1.0-1", "1.0-01")]:
            self.assertEqual(cs.vercmp(a, b), 0, f"{a} == {b}")


class Matching(unittest.TestCase):
    def setUp(self):
        self.pk = cs.parse_packages_txt(open(fixture("packages-small.txt")).read())
        self.st = cs.parse_status(open(fixture("status-small.txt")).read())
        self.tr = json.load(open(fixture("tracker-small.json")))

    def test_status_maps_sources(self):
        self.assertEqual(self.st["zlib1g"]["source"], "zlib")
        self.assertEqual(self.st["zlib1g"]["source_version"], "1:1.3.dfsg+really1.3.1-1")
        self.assertEqual(self.st["libc6"]["source"], "glibc")
        self.assertEqual(self.st["openssl"]["source"], "openssl")
        self.assertNotIn("removed-pkg", self.st)      # only installed packages count

    def test_report_with_status(self):
        r = cs.report(self.pk, self.st, self.tr, now="2026-11-12T00:00:00Z")
        by = {f["source"]: f for f in r["fixes"]}
        self.assertEqual(set(by), {"zlib", "glibc"})
        z = by["zlib"]
        self.assertTrue(z["available"])
        self.assertEqual(z["binaries"], ["zlib1g"])
        self.assertEqual([c["id"] for c in z["cves"]], ["CVE-2026-27171", "CVE-2026-76844"])
        self.assertEqual(z["fixed_version"], "1:1.3.dfsg+really1.3.1-1+deb13u1")
        g = by["glibc"]                               # resolved, but the fix is not in the archive yet
        self.assertFalse(g["available"])
        self.assertEqual([c["id"] for c in g["cves"]], ["CVE-2099-0004"])
        self.assertTrue(r["needs_rebuild"])
        self.assertEqual(r["source_map"], "dpkg-status")
        # not-affected ("0"), already-fixed, open and no-dsa entries never count as fixes
        ids = {c["id"] for f in r["fixes"] for c in f["cves"]}
        self.assertFalse(ids & {"CVE-2010-0002", "CVE-2009-0591", "CVE-2099-0001", "CVE-2099-0002",
                                "TEMP-0841856-B18BAF", "CVE-2099-0005"})

    def test_heuristic_without_status(self):
        # without dpkg status the binary name stands in for the source: zlib1g != zlib, so it is missed;
        # this is why CI always passes --status
        r = cs.report(self.pk, None, self.tr)
        self.assertEqual(r["source_map"], "heuristic")
        self.assertEqual([f["source"] for f in r["fixes"]], [])
        srcs = cs.installed_sources(self.pk)
        self.assertEqual(srcs["bash"]["version"], "5.2.37-2")   # binNMU suffix stripped

    def test_cli(self):
        import io, contextlib, tempfile
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "r.json")
            with contextlib.redirect_stderr(io.StringIO()):
                rc = cs.main(["--packages", fixture("packages-small.txt"), "--status", fixture("status-small.txt"),
                              "--tracker", fixture("tracker-small.json"), "--out", out, "--fail-on-fix"])
            self.assertEqual(rc, 3)
            self.assertEqual(json.load(open(out))["schema"], "onemind.security-check/v1")


if __name__ == "__main__":
    unittest.main()
