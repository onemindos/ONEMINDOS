# SPDX-License-Identifier: Apache-2.0
"""VM.expect_line: a match must wait for the end of its serial line (#324, TD3 read decision='f')."""
import importlib.util, os, threading, time, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("run_tests", os.path.join(HERE, "..", "qemu", "run-tests.py"))
rt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rt)


class FakeProc:
    returncode = None
    def poll(self):
        return None


def make_vm():
    vm = rt.VM.__new__(rt.VM)
    vm.buf, vm.pos, vm.lock, vm.proc = "", 0, threading.Lock(), FakeProc()
    vm.failfast, vm._watch = False, None
    return vm


def feed(vm, chunks, gap=0.15):
    def run():
        for c in chunks:
            time.sleep(gap)
            with vm.lock:
                vm.buf += c
    t = threading.Thread(target=run, daemon=True); t.start(); return t


class ExpectLine(unittest.TestCase):
    LINE = "ONEMIND-RECOVERY: entered slot=A version=2 reason=gate-failed decision=fell-back\n"
    CHUNKS = ["boot noise\nONEMIND-RECOVERY: entered slot=A version=2 reason=gate-failed decision=f",
              "ell-", "back", "\nroot@onemind:~# "]

    def test_plain_expect_reads_the_cut_off_value(self):
        vm = make_vm(); feed(vm, self.CHUNKS)
        self.assertEqual(vm.expect(rt.RECOV, 5).group(4), "f")   # the bug

    def test_expect_line_waits_for_the_newline(self):
        vm = make_vm(); t = feed(vm, self.CHUNKS)
        m = vm.expect_line(rt.RECOV, 5)
        self.assertEqual(m.groups(), ("A", "2", "gate-failed", "fell-back"))
        t.join(); self.assertEqual(vm.pos, vm.buf.index("\n", vm.buf.index("fell-back")))

    def test_gate_line_split_in_chunks(self):
        vm = make_vm()
        feed(vm, ["HEALTH-GATE: x RESULT environment-b", "ad slot=B version=3; slot B marked bad", "\n"])
        self.assertEqual(vm.wait_gate(5), ("environment-bad", "B", "3"))

    def test_no_newline_falls_back_after_eol_timeout(self):
        vm = make_vm(); vm.buf = "ONEMIND-RECOVERY: entered slot=A version=2 reason=r decision=ok"
        self.assertEqual(vm.expect_line(rt.RECOV, 2, eol_timeout=0.2).group(4), "ok")


if __name__ == "__main__":
    unittest.main()
