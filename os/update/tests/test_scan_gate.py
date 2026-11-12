# SPDX-License-Identifier: Apache-2.0
"""os/update/scan-gate.py: malware or an unpicked CRITICAL fix blocks; the rest is reported."""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

sg = load("scan-gate")
CLEAN = "----------- SCAN SUMMARY -----------\nKnown viruses: 3627000\nScanned files: 21000\nInfected files: 0\n"
HIT = "/scan/usr/bin/evil: Eicar-Signature FOUND\n\n----------- SCAN SUMMARY -----------\nInfected files: 1\n"


def trivy(*vulns):
    return {"Results": [{"Target": "rootfs (debian 13.1)", "Vulnerabilities": [
        {"VulnerabilityID": i, "PkgName": p, "InstalledVersion": "1", "FixedVersion": f, "Severity": s, "Status": st}
        for i, p, f, s, st in vulns]}]}


class Gate(unittest.TestCase):
    def test_clean_pass(self):
        g = sg.gate(trivy(("CVE-1", "a", "", "CRITICAL", "affected"), ("CVE-2", "b", "2", "HIGH", "fixed")), CLEAN)
        self.assertTrue(g["pass"], g["reasons"])
        self.assertEqual(g["trivy"]["fixable"], 1)
        self.assertEqual(g["trivy"]["by_severity"], {"CRITICAL": 1, "HIGH": 1})

    def test_unscanned_files_are_reported(self):
        log = "WARNING: Can't open file /scan/etc/shadow: Permission denied\n" + CLEAN + "Total errors: 1\n"
        c = sg.gate(trivy(), log)["clamav"]
        self.assertEqual((c["pass"], c["errors"], c["unscanned"]), (True, 1, ["/scan/etc/shadow"]))

    def test_malware_fails(self):
        g = sg.gate(trivy(), HIT)
        self.assertFalse(g["pass"])
        self.assertEqual(g["clamav"]["hits"], [{"file": "/scan/usr/bin/evil", "signature": "Eicar-Signature"}])

    def test_scan_that_did_not_run_fails(self):
        self.assertFalse(sg.gate(trivy(), "")["pass"])
        self.assertFalse(sg.gate(trivy(), "freshclam: connection failed")["pass"])

    def test_unpicked_critical_fix_fails(self):
        g = sg.gate(trivy(("CVE-3", "zlib1g", "2", "CRITICAL", "fixed")), CLEAN)
        self.assertFalse(g["pass"])
        self.assertEqual(g["trivy"]["blocking"][0]["id"], "CVE-3")

    def test_check_report_is_informational(self):
        chk = {"fixes": [{"source": "zlib", "installed": "1", "fixed_version": "2", "available": True,
                          "cves": [{"id": "CVE-4"}]}, {"source": "glibc", "installed": "1",
                          "fixed_version": "2", "available": False, "cves": []}]}
        g = sg.gate({"Results": None}, CLEAN, chk, "vm")
        self.assertTrue(g["pass"])
        self.assertEqual([b["source"] for b in g["sources_behind_archive_fix"]], ["zlib"])


if __name__ == "__main__":
    unittest.main()
