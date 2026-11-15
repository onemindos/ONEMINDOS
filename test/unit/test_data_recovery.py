# SPDX-License-Identifier: Apache-2.0
"""Recovery mode when the data partition fails (os/recovery/README.md): static checks of the fstab and
unit wiring, and the status page responder. The boot behaviour itself is TD1-TD3 in the QEMU battery
(test/qemu/CRITERIA-DATAFAIL.md)."""
import configparser, os, re, shutil, subprocess, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REC = os.path.join(ROOT, "os", "recovery")
FSTABS = ["os/rootfs/layers/base/etc/fstab", "os/boards/rpi5/rootfs/etc/fstab"]


def read(p):
    return open(os.path.join(ROOT, p)).read()


def entries(text):
    return [l.split() for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]


def unit(name):
    c = configparser.ConfigParser(strict=False, interpolation=None)
    c.optionxform = str
    c.read_string(read(f"os/recovery/{name}"))
    return c


def mount_unit(path):
    # systemd path escaping: "/" becomes "-" and a literal "-" becomes \\x2d (systemd-escape --path).
    return path.strip("/").replace("-", "\\x2d").replace("/", "-") + ".mount"


class Wiring(unittest.TestCase):
    def test_data_and_its_binds_are_nofail(self):
        for f in FSTABS:
            rows = entries(read(f))
            data = [r for r in rows if r[1] == "/data"]
            self.assertEqual(len(data), 1, f)
            self.assertIn("nofail", data[0][3].split(","), f)
            self.assertIn("x-systemd.device-timeout=30s", data[0][3].split(","), f)
            binds = [r for r in rows if r[0].startswith("/data/")]
            self.assertGreater(len(binds), 0, f)
            for r in binds:
                self.assertIn("nofail", r[3].split(","), f"{f}: {r[1]}")
            esp = [r for r in rows if r[1] == "/boot/efi"]
            self.assertNotIn("nofail", esp[0][3], "the ESP stays required: it holds the bootloader and grubenv")

    def test_check_waits_for_every_data_mount(self):
        u = unit("onemind-data-check.service")["Unit"]
        after = u["After"].split()
        for f in FSTABS:
            for r in entries(read(f)):
                if r[1] == "/data" or r[0].startswith("/data/"):
                    self.assertIn(mount_unit(r[1]), after, f"{f}: {r[1]}")
        self.assertIn("onemind-data-layout.service", after)
        self.assertEqual(u["Before"], "local-fs.target")
        self.assertEqual(u["DefaultDependencies"], "no")
        self.assertEqual(u["OnFailure"], "onemind-recovery.target")
        self.assertEqual(u["OnFailureJobMode"], "isolate")
        # The isolate re-pulls local-fs.target; without this the check reruns, fails and isolates forever
        # (found in CI: TD1 never saw the recovery line). The check writes the status file before it exits 1.
        self.assertEqual(u["ConditionPathExists"], "!/run/onemind-recovery/status")
        script = read("os/recovery/onemind-data-check")
        self.assertLess(script.index("$RUN/status.new"), script.index("exit 1"))

    def test_recovery_target_is_minimal(self):
        u = unit("onemind-recovery.target")["Unit"]
        self.assertEqual(u["AllowIsolate"], "yes")
        # A running plymouth splash swallows /dev/console writes; the ONEMIND-RECOVERY lines must be seen.
        self.assertIn("plymouth-quit.service", u["Wants"].split())
        self.assertIn("plymouth-quit.service", unit("onemind-recovery.service")["Unit"]["After"].split())
        wants = u["Wants"].split()
        for w in ("systemd-networkd.service", "avahi-daemon.service", "getty.target",
                  "onemind-recovery.service", "onemind-recovery-web.service"):
            self.assertIn(w, wants)
        for never in ("k3s", "onemind-gateway", "onemind-health-gate", "onemindd", "onemind-nats"):
            self.assertNotIn(never, u["Wants"])

    def test_image_installs_and_enables_the_check(self):
        c = read("os/rootfs/Containerfile")
        for f in ("onemind-data-check", "onemind-recovery", "onemind-recovery-respond", "onemind-data-check.service",
                  "onemind-recovery.target", "onemind-recovery.service", "onemind-recovery-web.service"):
            self.assertIn(f"os/recovery/{f}", c)
        self.assertTrue(re.search(r"systemctl enable [^;]*onemind-data-check\.service", c), "onemind-data-check not enabled")

    def test_nothing_formats_or_repairs(self):
        for f in ("onemind-data-check", "onemind-recovery", "onemind-recovery-respond"):
            code = "\n".join(l for l in read(f"os/recovery/{f}").splitlines() if not l.lstrip().startswith("#"))
            hit = re.search(r"\b(mkfs|mke2fs|e2fsck|fsck|wipefs|sgdisk|parted|resize2fs)\b|\bdd\s+if=|rauc status mark-bad", code)
            self.assertIsNone(hit, f"{f}: {hit and hit.group(0)}")

    def test_marker_copy_and_gate_verdict(self):
        pre = read("os/rauc/handlers/rauc-pre-install")
        self.assertIn("/boot/efi/onemind/pending", pre)
        self.assertLess(pre.index("/data/onemind/pending"), pre.index("/boot/efi/onemind/pending"))
        gate = read("os/gate/onemind-health-gate")
        self.assertIn('verdict=environment-bad; again=', gate)
        self.assertIn('decision=trial', gate)
        self.assertNotIn('rm -f "$PENDING"; sync', gate, "every clear goes through clear_pending (ESP copy too)")
        rec = read("os/recovery/onemind-recovery")
        self.assertIn("decision=$DECISION", rec)   # the note the gate greps for


class Harness(unittest.TestCase):
    def test_gate_regex_reads_the_fell_back_line(self):
        # TD3 (and T6/T7) compare the version the gate logs; "version=2;" must parse as "2".
        import importlib.util
        spec = importlib.util.spec_from_file_location("rt", os.path.join(ROOT, "test", "qemu", "run-tests.py"))
        rt = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rt)
        line = ("HEALTH-GATE: 21:37:34 RESULT fell-back slot=A version=2; slot B (v2) marked bad "
                "verdict=environment-bad, re-offered (REC-DEC-45) (why)")
        m = re.search(rt.GATE, line)
        self.assertEqual(m.groups()[:3], ("fell-back", "A", "2"))
        m = re.search(rt.GATE, "HEALTH-GATE: 19:58:46 RESULT committed-boot slot=A version=1")
        self.assertEqual(m.groups()[:3], ("committed-boot", "A", "1"))


@unittest.skipUnless(shutil.which("bash"), "needs bash")
class Page(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        open(os.path.join(self.d, "index.html"), "w").write("<p>data disk</p>\n")
        open(os.path.join(self.d, "status.json"), "w").write('{"state": "recovery"}\n')

    def tearDown(self):
        shutil.rmtree(self.d)

    def ask(self, req):
        r = subprocess.run(["bash", os.path.join(REC, "onemind-recovery-respond")], input=req.encode(),
                           capture_output=True, timeout=20, env={"ONEMIND_RECOVERY_RUN": self.d, "PATH": os.environ["PATH"]})
        self.assertEqual(r.returncode, 0, r.stderr)
        head, _, body = r.stdout.decode().partition("\r\n\r\n")
        return head, body

    def test_html_and_json_are_503(self):
        head, body = self.ask("GET / HTTP/1.1\r\nHost: onemind.local\r\n\r\n")
        self.assertTrue(head.startswith("HTTP/1.0 503 "))
        self.assertIn("text/html", head)
        self.assertIn("data disk", body)
        self.assertIn(f"Content-Length: {len(body)}", head)
        head, body = self.ask("GET /status.json HTTP/1.1\r\n\r\n")
        self.assertIn("application/json", head)
        self.assertEqual(body, '{"state": "recovery"}\n')

    def test_head_and_hostile_requests(self):
        head, body = self.ask("HEAD / HTTP/1.0\r\n\r\n")
        self.assertTrue(head.startswith("HTTP/1.0 503 ") and body == "")
        head, body = self.ask("GET /../../etc/passwd?<script>* HTTP/1.0\r\nX: $(id)\r\n\r\n")
        self.assertIn("data disk", body)
        self.assertNotIn("<script>", head + body)
        self.assertNotIn("root:", body)
        head, body = self.ask("")
        self.assertEqual(head + body, "")


if __name__ == "__main__":
    unittest.main()
