# SPDX-License-Identifier: Apache-2.0
"""test/qemu/failfast.py: the fatal-sign detector of the QEMU boot harnesses (no VM needed)."""
import importlib.util, os, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("failfast", os.path.join(HERE, "..", "qemu", "failfast.py"))
ff = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ff)

OK_BOOT = """[  OK  ] Started onemind-nats.service - OneMind NATS.
[  OK  ] Started onemind-gateway.service - OneMind Core gateway (:8080).
ONEMIND-FIRSTBOOT: configured role=hub source=nocloud
HEALTH-GATE: x RESULT committed-boot slot=A version=1
cloud-init[612]: Traceback (most recent call last):
cloud-init[612]:   File "/usr/lib/python3/dist-packages/cloudinit/util.py", line 1, in x
"""


class Scan(unittest.TestCase):
    def test_healthy_boot_is_not_fatal(self):
        self.assertIsNone(ff.scan(OK_BOOT))

    def test_kernel_panic(self):
        self.assertIn("kernel-panic", ff.scan("[ 1.2] Kernel panic - not syncing: VFS: Unable to mount root fs"))

    def test_emergency_mode(self):
        self.assertIn("emergency-mode", ff.scan("You are in emergency mode. After logging in, type \"journalctl -xb\""))
        self.assertIn("emergency-mode", ff.scan("Welcome to emergency mode!"))

    def test_onemind_unit_failed_to_start(self):
        self.assertIn("unit-failed-to-start", ff.scan("[FAILED] Failed to start onemind-gateway.service - OneMind Core gateway."))
        self.assertIn("unit-failed-to-start", ff.scan("onemind-nats.service: Failed with result 'exit-code'."))

    def test_other_unit_failure_is_not_fatal(self):
        self.assertIsNone(ff.scan("[FAILED] Failed to start systemd-networkd-wait-online.service."))
        self.assertIsNone(ff.scan("onemind-update.service: Failed with result 'success'."))

    def test_restart_loop_needs_the_limit(self):
        low = f"onemind-gateway.service: Scheduled restart job, restart counter is at {ff.RESTART_LIMIT - 1}."
        high = f"onemind-gateway.service: Scheduled restart job, restart counter is at {ff.RESTART_LIMIT}."
        self.assertIsNone(ff.scan(low))
        self.assertIn("unit-restart-loop", ff.scan(high))
        self.assertIn("unit-restart-loop", ff.scan(low + "\n" + high.replace(str(ff.RESTART_LIMIT), "40")))

    def test_traceback_only_from_onemind(self):
        tb = ("Traceback (most recent call last):\n"
              '  File "/usr/lib/onemind/gateway/venv/lib/python3.13/site-packages/onemind_core/__main__.py", line 9\n'
              "FileNotFoundError: sdk/policy/app-objects.yaml\n")
        self.assertIn("python-traceback", ff.scan(tb))
        self.assertIn("python-traceback", ff.scan("python3[41]: " + tb.replace("\n  ", "\npython3[41]:   ")))
        self.assertIsNone(ff.scan('Traceback (most recent call last):\n  File "/usr/lib/python3/dist-packages/cloudinit/x.py", line 3\n'))

    def test_restarts_exceeded(self):
        self.assertTrue(ff.restarts_exceeded(str(ff.RESTART_LIMIT)))
        self.assertFalse(ff.restarts_exceeded("0"))
        self.assertFalse(ff.restarts_exceeded(""))
        self.assertFalse(ff.restarts_exceeded("[not set]"))


class WatchTail(unittest.TestCase):
    def test_incremental_and_split_across_reads(self):
        w, buf = ff.Watch(), "boot ok\n"
        self.assertIsNone(w.check(buf))
        buf += "Kernel panic - not "
        self.assertIsNone(w.check(buf))
        buf += "syncing: oops\n"
        self.assertIn("kernel-panic", w.check(buf))

    def test_buffer_reset_after_vm_restart(self):
        w = ff.Watch()
        w.check("x" * 5000)
        self.assertIn("kernel-panic", w.check("Kernel panic - not syncing"))

    def test_dump_cmd_names_the_gateway_journal(self):
        c = ff.dump_cmd()
        self.assertIn("journalctl -u onemind-gateway.service", c)
        self.assertIn("-n 200", c)


class Wiring(unittest.TestCase):
    def test_harnesses_opt_in_and_battery_does_not(self):
        q = os.path.join(HERE, "..", "qemu")
        def rd(f):
            with open(os.path.join(q, f), encoding="utf-8") as fh:
                return fh.read()
        for f in ("firstboot.py", "installer.py", "cloudboot.py"):
            self.assertIn("failfast = True", rd(f), f)
        self.assertNotIn("failfast = True", rd("run-tests.py"))   # T6/T7 panic on purpose


if __name__ == "__main__":
    unittest.main()
