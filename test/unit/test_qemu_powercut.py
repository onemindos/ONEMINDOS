# SPDX-License-Identifier: Apache-2.0
"""The power-cut battery's helper logic (test/qemu/powercut.py, CRITERIA-FIRSTBOOT.md §12), fed canned guest output.

No VM: a fake `vm.run` returns what the booted image prints, so these tests pin how F17 reads "k3s healthy" and
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
        sec = text[text.index("## 12. Amendment (2026-11-25)"):]
        self.assertIn(f"**{self.pc.CUT_AFTER_S} s**", sec)
        self.assertIn(f"**{self.pc.HEALTHY_S} s**", sec)
        for path in ("/data/k3s/server/token", "/data/k3s/server/tls", "/data/k3s/agent/kubelet.kubeconfig",
                     "/etc/rancher/node/password", "/data/k3s/agent/etc/containerd/config.toml"):
            self.assertIn(path, sec)
            self.assertIn(path, self.pc.K3S_FILES)

    def test_recovery_line_and_node_id_patterns(self):
        self.assertTrue(self.pc.RECOVERY.search("x ONEMIND-K3S-RECOVERY: repaired k3s state: 11 item(s)\n"))
        self.assertEqual(self.pc.NODE_ID.findall("ONEMIND-FIRSTBOOT: already configured role=hub node_id=ab12cd34ef56"), ["ab12cd34ef56"])


class PreRegistered(unittest.TestCase):
    def test_amendment_hash_is_registered(self):
        import hashlib
        d = os.path.join(ROOT, "test", "qemu")
        got = hashlib.sha256(open(os.path.join(d, "CRITERIA-FIRSTBOOT.md"), "rb").read()).hexdigest()
        lines = open(os.path.join(d, "PREREGISTRATION.sha256")).read().splitlines()
        # The power-cut sections are §12/§13 (F17-F19) since they met release/next (first registered as §9/§10, F13-F15).
        self.assertTrue([l for l in lines if l.startswith(got) and "CRITERIA-FIRSTBOOT.md" in l and "§13" in l],
                        "CRITERIA-FIRSTBOOT.md changed after its §13 hash was registered")
        # the hashes registered before the code (§9, then §10) are still in the file, so the history is intact
        for h in ("0adac04da0caa9dff936e6d0937fd2f76387c85dff493de2155a426261b07b88",
                  "60166bfb5bae78b8b865f5ce3e3059dbdd3d530232ed40ae196e9f955ebc5ab0"):
            self.assertTrue([l for l in lines if l.startswith(h) and "CRITERIA-FIRSTBOOT.md" in l], h)


if __name__ == "__main__":
    unittest.main()
