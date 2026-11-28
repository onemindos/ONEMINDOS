# SPDX-License-Identifier: Apache-2.0
"""The power-cut battery's helper logic (test/qemu/powercut.py, CRITERIA-FIRSTBOOT.md §21), fed canned guest output.

No VM: a fake `vm.run` returns what the booted image prints, so these tests pin how F26 reads "k3s healthy" and
"no empty k3s file", and that the criteria text and the harness agree on the file list and the 25 s cut."""
import importlib.util, os, re, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load():
    spec = importlib.util.spec_from_file_location("powercut", os.path.join(ROOT, "test", "qemu", "powercut.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeVM:
    def __init__(self, out):
        self.out, self.cmds = out, []

    def run(self, cmd, timeout=None):
        self.cmds.append(cmd)
        return 0, self.out


class Helpers(unittest.TestCase):
    def setUp(self):
        self.pc = load()

    def test_healthy_needs_the_gates_ok(self):
        ok, last = self.pc.k3s_healthy(FakeVM("K3S=ok\nLAST=ok (fresh: kubelet)\n"))
        self.assertTrue(ok)
        ok, last = self.pc.k3s_healthy(FakeVM("K3S=timeout\nLAST=fail G1: no kubeconfig on this boot\n"))
        self.assertFalse(ok)
        self.assertIn("G1", last)

    def test_empty_files_are_reported_and_counted(self):
        bad, n = self.pc.empty_k3s_files(FakeVM("BAD /etc/rancher/node/password empty\nBAD /data/k3s/server/token missing\nCHECKED=9\n"))
        self.assertEqual(bad, ["/etc/rancher/node/password empty", "/data/k3s/server/token missing"])
        self.assertEqual(n, 9)
        self.assertEqual(self.pc.empty_k3s_files(FakeVM("CHECKED=12\n")), ([], 12))

    def test_criteria_and_harness_agree(self):
        text = open(os.path.join(ROOT, "test", "qemu", "CRITERIA-FIRSTBOOT.md")).read()
        sec = text[text.index("## 21. Amendment (2026-11-25): F26"):]
        self.assertIn(f"**{self.pc.CUT_AFTER_S} s**", sec)
        self.assertIn(f"**{self.pc.HEALTHY_S} s**", sec)
        for path in ("/data/k3s/server/token", "/data/k3s/server/tls", "/data/k3s/agent/kubelet.kubeconfig",
                     "/etc/rancher/node/password", "/data/k3s/agent/etc/containerd/config.toml"):
            self.assertIn(path, sec)
            self.assertIn(path, self.pc.K3S_FILES)
        for path in self.pc.MARKERS.values():
            self.assertIn(path, sec)

    def test_recovery_line_and_node_id_patterns(self):
        self.assertTrue(self.pc.RECOVERY.search("x ONEMIND-K3S-RECOVERY: repaired k3s state: 11 item(s)\n"))
        self.assertEqual(self.pc.NODE_ID.findall("ONEMIND-FIRSTBOOT: already configured role=hub node_id=ab12cd34ef56"), ["ab12cd34ef56"])

    def test_f19h_and_f20_helpers(self):
        h = self.pc.hold_state(FakeVM("ACTIVE=inactive\nRESULT=exec-condition\nNRESTARTS=0\nDB0=4096:ab\nDB1=absent\n"))
        self.assertEqual(h, {"active": "inactive", "result": "exec-condition", "nrestarts": "0", "db": ["4096:ab", "absent"]})
        dirs, last = self.pc.recovery_listing(FakeVM(
            "QDIR=/data/onemind/k3s-recovery/20261125T1/\nQDIR=/data/onemind/k3s-recovery/20261125T0/\n"
            'LAST={"action": "repaired", "scope": "agent", "moved": ["k3s/agent/client-kubelet.key"]}\n'))
        self.assertEqual(dirs, ["/data/onemind/k3s-recovery/20261125T0", "/data/onemind/k3s-recovery/20261125T1"])
        self.assertEqual(last["scope"], "agent")
        self.assertEqual(self.pc.recovery_listing(FakeVM("ls: no such file\n")), ([], {}))
        self.assertEqual(self.pc.app_uid(FakeVM("UID=1b2c-3d\n")), "1b2c-3d")

    def test_section_25_and_the_harness_agree(self):
        text = open(os.path.join(ROOT, "test", "qemu", "CRITERIA-FIRSTBOOT.md")).read()
        sec = text[text.index("## 25. Amendment (2026-11-25, evening): F28h"):]
        for path in self.pc.DB_FILES:
            self.assertIn(path, sec)
        self.assertIn("**60 s**", sec)
        self.assertIn("`/data/k3s/agent/kubelet.kubeconfig` (nothing else)", sec)
        self.assertEqual(self.pc.AGENT_FILES.split(), ["/data/k3s/agent/*.crt", "/data/k3s/agent/*.key",
                                                       "/data/k3s/agent/kubelet.kubeconfig"])
        src = open(os.path.join(ROOT, "test", "qemu", "powercut.py")).read()
        # F33 runs between F27 and F28, and F28h inside F28 before the refused POSTs
        self.assertLess(src.index('record("F27"'), src.index('record("F33"'))
        self.assertLess(src.index('record("F33"'), src.index('record("F28h"'))
        self.assertLess(src.index('record("F28h"'), src.index("no_token = rescue_post"))


class PreRegistered(unittest.TestCase):
    def test_amendment_hash_is_registered(self):
        import hashlib
        d = os.path.join(ROOT, "test", "qemu")
        got = hashlib.sha256(open(os.path.join(d, "CRITERIA-FIRSTBOOT.md"), "rb").read()).hexdigest()
        lines = open(os.path.join(d, "PREREGISTRATION.sha256")).read().splitlines()
        # the current file's hash is registered (each later amendment appends its own line, so the note varies)
        self.assertTrue([l for l in lines if l.startswith(got + " ") and "CRITERIA-FIRSTBOOT.md" in l],
                        "CRITERIA-FIRSTBOOT.md changed after its hash was last registered")
        # The power-cut sections are §21, §22 and §25 (F26-F28, F28h and F33; first registered as §9/§10 with F13-F15,
        # then §12-§14 with F17-F20 on PR 1157/1155's branches). The hashes registered before the code are still in
        # the file, so the history of what was registered when is intact.
        for h in ("0adac04da0caa9dff936e6d0937fd2f76387c85dff493de2155a426261b07b88",
                  "60166bfb5bae78b8b865f5ce3e3059dbdd3d530232ed40ae196e9f955ebc5ab0",
                  "505308250e58ca08b3ae2e5b2da893fe9a4b7765230720196bab0582326d1da9",
                  "3d79aac266493d38ae566d56c421bdd31eada953312adab3f4dff1ce2b546ec5"):
            self.assertTrue([l for l in lines if l.startswith(h + " ") and "CRITERIA-FIRSTBOOT.md" in l], h)

    def test_section_22_points_at_the_power_cut_section_21(self):
        # Section 22 amends the F27 row of section 21 (PR 1323 review: one of its three cross-references still said
        # "Section 9", the disk-and-admin-tools amendment, left over from #1157's own numbering).
        crit = open(os.path.join(ROOT, "test", "qemu", "CRITERIA-FIRSTBOOT.md"), encoding="utf-8").read()
        s21 = crit[crit.index("\n## 21. "):crit.index("\n## 22. ")]
        s22 = crit[crit.index("\n## 22. "):crit.index("\n## 23. ")]
        self.assertIn("F26 and F27, a power cut", s21.splitlines()[1])
        self.assertIn("On the healthy box of F26", s21)                  # the words section 22 quotes
        self.assertIn('Section 21 said "on the healthy box of F26"', s22)
        self.assertEqual(s22.count("section 21") + s22.count("Section 21"), 3)
        self.assertIsNone(re.search(r"\b[Ss]ection (9|12)\b", s22), "section 22 still names #1157's own numbering")


if __name__ == "__main__":
    unittest.main()
