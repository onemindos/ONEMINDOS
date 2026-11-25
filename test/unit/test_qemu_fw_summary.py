# SPDX-License-Identifier: Apache-2.0
"""Battery T5 fixes (#234): firewall FW3 waits for k3s to listen; summary.py tolerates every results.json shape."""
import importlib.util, os, unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def load(fn):
    s = importlib.util.spec_from_file_location(fn, os.path.join(HERE, "..", "qemu", fn))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


fw, sm = load("firewall.py"), load("summary.py")


class FakeBox:
    def __init__(self, outs):
        self.outs, self.calls = list(outs), 0

    def run(self, cmd):
        self.calls += 1
        return 0, self.outs.pop(0) if len(self.outs) > 1 else self.outs[0]


class Clock:
    t = 0.0
    def now(self): return self.t
    def sleep(self, s): self.t += s


class WaitK3s(unittest.TestCase):
    def test_parse_wildcard_only(self):
        ss = "LISTEN 127.0.0.1:6443\nLISTEN *:10250\nLISTEN [::]:22\nLISTEN 0.0.0.0:80\n"
        self.assertEqual(fw.wildcard_listening(ss), {10250, 22, 80})

    def test_waits_until_both_listen(self):
        c = Clock()
        box = FakeBox(["LISTEN *:22\n", "LISTEN *:22\nLISTEN *:6443\n", "LISTEN *:6443\nLISTEN *:10250\n"])
        have, _ = fw.wait_k3s_listening(box, timeout=60, step=5, clock=c.now, sleep=c.sleep)
        self.assertLessEqual(fw.K3S_PORTS, have)
        self.assertEqual((box.calls, c.t), (3, 10))

    def test_bounded_when_never_listening(self):
        c = Clock()
        box = FakeBox(["LISTEN *:22\n"])
        have, _ = fw.wait_k3s_listening(box, timeout=20, step=5, clock=c.now, sleep=c.sleep)
        self.assertEqual(have, {22})
        self.assertLessEqual(c.t, 25)


class Summary(unittest.TestCase):
    def test_full(self):
        r = {"env": {"board": "b", "upto": "T5", "accel": "kvm", "host_cpus": 4}, "minutes": 1.5,
             "results": [{"test": "X", "verdict": "PASS", "detail": "a|b"}]}
        out = sm.render(r)
        self.assertIn("Battery b up to T5: accel=kvm, host CPUs=4, 1.5 min", out)
        self.assertIn("a/b", out)

    def test_env_without_upto(self):
        out = sm.render({"env": {"board": "b", "accel": "tcg", "host_cpus": 2}, "minutes": 1, "results": []})
        self.assertIn("Battery b: accel=tcg", out)

    def test_no_env_secureboot_shape(self):
        out = sm.render({"board": "x86_64-efi", "accel": "kvm", "cpus": 8, "results": [{"test": "SB1", "verdict": "PASS"}]})
        self.assertIn("Battery x86_64-efi: accel=kvm, host CPUs=8", out)
        self.assertIn("SB1", out)

    def test_empty(self):
        self.assertIn("Battery ?", sm.render({}))


if __name__ == "__main__":
    unittest.main()
