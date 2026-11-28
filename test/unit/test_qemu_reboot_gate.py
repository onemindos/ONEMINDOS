# SPDX-License-Identifier: Apache-2.0
"""firstboot.py F3's reboot: the gate line may come before "already configured" (#1159).

On a committed boot the health gate decides at once and is not ordered against onemind-firstboot.service, so on a
fast host its line is printed first. The harness used to wait for ALREADY, then for the gate from after ALREADY,
and hung for 1800 s on a box that had booted fine. These tests feed both orders to the real harness code."""
import importlib.util, os, threading, time, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location("firstboot_harness", os.path.join(ROOT, "test", "qemu", "firstboot.py"))
fb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fb)

GATE = "HEALTH-GATE: onemind-health-gate RESULT committed-boot slot=A version=1\n"
ALREADY = "ONEMIND-FIRSTBOOT: already configured role=hub node_id=0123456789ab\n"
BEFORE = ("boot one\n" + GATE + "ONEMIND-FIRSTBOOT: configured role=hub source=nocloud node_id=0123456789ab\n"
          "root@onemind:~# true; echo __RC=0__\n")


class FakeProc:
    returncode = None

    def __init__(self, vm, after_reboot):
        def emit():
            with vm.lock:
                vm.buf += after_reboot

        class Stdin:
            def write(self, b):
                if b.decode().strip() == "systemctl reboot":    # the guest reboots and prints the next boot
                    threading.Timer(0.1, emit).start()

            def flush(self):
                pass
        self.stdin = Stdin()

    def poll(self):
        return None


def make_vm(after_reboot):
    vm = fb.battery.VM.__new__(fb.battery.VM)
    vm.buf, vm.lock, vm.failfast, vm._watch = BEFORE, threading.Lock(), False, None
    vm.pos = len(BEFORE)                       # the earlier boot's gate line was read already (F1)
    vm.proc = FakeProc(vm, after_reboot)
    return vm


class RebootGate(unittest.TestCase):
    def test_gate_line_before_already_is_found(self):
        vm = make_vm("reboot\n" + GATE + "noise\n" + ALREADY)
        t = time.time()
        seg, al, gate = fb.reboot_and_wait(vm, timeout=5, gate_timeout=5)
        self.assertEqual(gate, ("committed-boot", "A", "1"))
        self.assertTrue(al.startswith("ONEMIND-FIRSTBOOT: already configured role=hub"))
        self.assertEqual(seg, len(BEFORE))
        self.assertLess(time.time() - t, 4)

    def test_gate_line_after_already_is_found(self):
        vm = make_vm("reboot\n" + ALREADY + GATE)
        self.assertEqual(fb.reboot_and_wait(vm, timeout=5, gate_timeout=5)[2], ("committed-boot", "A", "1"))

    def test_the_old_order_of_waits_misses_an_early_gate_line(self):
        """What the harness did before #1159: the gate after ALREADY. Times out although the gate line is there."""
        vm = make_vm("reboot\n" + GATE + ALREADY)
        vm.send("systemctl reboot")
        vm.expect(fb.ALREADY, 5)
        with self.assertRaises(TimeoutError):
            vm.wait_gate(1)

    def test_an_earlier_boots_gate_line_does_not_count(self):
        """Not weakened: the gate line must come from the boot after the reboot."""
        vm = make_vm("reboot\n" + ALREADY)
        with self.assertRaises(TimeoutError):
            fb.reboot_and_wait(vm, timeout=5, gate_timeout=1)

    def test_already_configured_is_still_required(self):
        vm = make_vm("reboot\n" + GATE)
        with self.assertRaises(TimeoutError):
            fb.reboot_and_wait(vm, timeout=1, gate_timeout=1)

    def test_f3_uses_the_helper(self):
        with open(os.path.join(ROOT, "test", "qemu", "firstboot.py")) as f:
            src = f.read()
        f3 = src[src.index('vm.mark("F3 reboot keeps state")'):src.index('record("F3"')]
        self.assertIn("reboot_and_wait(vm)", f3)
        self.assertNotIn("vm.expect(ALREADY", f3)


if __name__ == "__main__":
    unittest.main()
