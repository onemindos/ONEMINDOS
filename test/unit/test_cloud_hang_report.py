# SPDX-License-Identifier: Apache-2.0
"""Leap run Day 1: evidence for the AWS cloud-boot flake (C1 silent after GRUB, cause unknown).

cloudboot.py's hang report says whether the guest still answers SSH and dumps what systemd waits on;
trim-log.sh --tail keeps the last lines of the serial log, masked like the evidence trim."""
import importlib.util
import io
import os
import subprocess
import tempfile
import threading
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location("cloudboot", os.path.join(ROOT, "test", "qemu", "cloudboot.py"))
cb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cb)
TRIM = os.path.join(ROOT, "test", "qemu", "trim-log.sh")


class FakeVM:
    def __init__(self):
        self.buf, self.lock, self.marks = "GRUB-RAUC: ORDER=A B\n", threading.Lock(), []

    def mark(self, msg):
        self.marks.append(msg)


def fake_run(ssh):
    r = cb.Run.__new__(cb.Run)
    r.vm, r.logf, r.ssh = FakeVM(), io.StringIO(), ssh
    return r


class HangReport(unittest.TestCase):
    def test_alive_guest_dumps_systemd_state_into_the_log(self):
        seen = []
        r = fake_run(lambda cmd, timeout: (seen.append(cmd), (0, "--- jobs\n1 rauc.service start running\n"))[1])
        why = cb.Run.hang_report(r, "ONEMIND-FIRSTBOOT")
        self.assertIn("answers SSH", why)
        self.assertIn("rauc.service start running", r.logf.getvalue())
        for part in ("list-jobs", "--failed", "onemind-firstboot.service", "rauc.service", "journalctl -b -p warning"):
            self.assertIn(part, seen[0])
        self.assertTrue(any("guest_ssh=alive" in m for m in r.vm.marks))

    def test_silent_guest_is_an_early_boot_hang_and_never_raises(self):
        def boom(cmd, timeout):
            raise subprocess.TimeoutExpired(cmd, timeout)
        why = cb.Run.hang_report(fake_run(boom), "ONEMIND-FIRSTBOOT")
        self.assertIn("early-boot hang", why)
        why = cb.Run.hang_report(fake_run(lambda cmd, timeout: (255, "Connection refused")), "X")
        self.assertIn("no SSH", why)

    def test_c1_timeout_carries_the_hang_report(self):
        class VM(FakeVM):
            def expect(self, pattern, timeout):
                raise TimeoutError(f"timeout {timeout}s waiting for {pattern!r}")
        r = types.SimpleNamespace(prepare=lambda *a: ("d", "s", []), boot=lambda *a: VM(),
                                  hang_report=lambda what: "guest silent and no SSH (early-boot hang)")
        with self.assertRaises(TimeoutError) as e:
            cb.boot_main(r, "base", ["C1"], [])
        self.assertIn("timeout 900s", str(e.exception))
        self.assertIn("early-boot hang", str(e.exception))


class TrimTail(unittest.TestCase):
    def test_tail_keeps_unfiltered_lines_and_masks_addresses(self):
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as f:
            f.write("old line\n[    1.2] nvme nvme0: I/O 12 QID 0 timeout\r\n"
                    "ip 10.0.2.15 lan 192.168.1.4 pod 10.42.0.7 other 10.9.8.7 kept v1.15.2\n")
        try:
            out = subprocess.run(["sh", TRIM, "--tail", "2", f.name], capture_output=True, text=True, check=True).stdout
        finally:
            os.unlink(f.name)
        self.assertNotIn("old line", out)
        self.assertIn("nvme nvme0: I/O 12 QID 0 timeout", out)   # not an evidence line: kept by --tail only
        self.assertNotIn("\r", out)
        for ip in ("10.0.2.15", "192.168.1.4", "10.42.0.7", "10.9.8.7"):
            self.assertNotIn(ip, out)
        self.assertIn("v1.15.2", out)

    def test_workflow_keeps_the_masked_tail_for_cloud_runs(self):
        with open(os.path.join(ROOT, ".github", "workflows", "image.yml")) as f:
            text = f.read()
        self.assertIn("trim-log.sh --tail 400 $d/serial.log > $d/serial-tail.log", text)


if __name__ == "__main__":
    unittest.main()
