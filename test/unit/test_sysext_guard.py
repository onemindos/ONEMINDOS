# SPDX-License-Identifier: Apache-2.0
"""Signed host extensions only (T-W19-01, #186): the image wiring under os/rootfs, the guard script that runs
before every merge, and the pure parts of the QEMU harness (test/qemu/sysextguard.py, CRITERIA-SYSEXT.md).
The boot test itself needs QEMU (`make sysextguard`)."""
import base64, configparser, hashlib, importlib.util, json, os, shutil, subprocess, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.path.join(ROOT, "os", "rootfs", "layers", "base")
UNITS = os.path.join(BASE, "usr", "lib", "systemd", "system")
GUARD = os.path.join(BASE, "usr", "lib", "onemind", "sysext-guard")


def read(*p):
    with open(os.path.join(ROOT, *p)) as f:
        return f.read()


def dropin(kind):
    with open(os.path.join(UNITS, f"systemd-{kind}.service.d", "10-onemind-signed-only.conf")) as f:
        text = f.read()
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("#")]
    c = configparser.ConfigParser(strict=False, interpolation=None)
    c.optionxform = str
    c.read_string(text)
    return c, lines


def harness():
    spec = importlib.util.spec_from_file_location("sysextguard", os.path.join(ROOT, "test", "qemu", "sysextguard.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class DropIns(unittest.TestCase):
    POLICY = {"sysext": "root=signed+absent:usr=signed+absent", "confext": "root=signed+absent"}

    def test_merge_runs_with_the_signed_only_policy_and_the_guard_first(self):
        for kind, pol in self.POLICY.items():
            _, lines = dropin(kind)
            run = f"systemd-{kind} refresh --mutable=no --image-policy={pol}"
            # ExecStart is cleared first (a drop-in adds to the list otherwise), then set to the policy run.
            self.assertEqual(lines[lines.index("[Service]") + 1:], [
                f"ExecStartPre=/usr/lib/onemind/sysext-guard {kind}", "ExecStart=", f"ExecStart={run}",
                "ExecReload=", f"ExecReload=/usr/lib/onemind/sysext-guard {kind}", f"ExecReload={run}"], kind)

    def test_merge_waits_for_the_data_partition_and_comes_before_k3s(self):
        for kind, d in (("sysext", "var-lib-extensions"), ("confext", "var-lib-confexts")):
            c, _ = dropin(kind)
            self.assertEqual(c["Unit"]["RequiresMountsFor"], f"/data/state/{d}")
            self.assertEqual(c["Unit"]["Before"], "k3s.service")

    def test_units_are_enabled_in_the_image(self):
        cf = read("os/rootfs/Containerfile")
        line = next(l for l in cf.splitlines() if "onemind-factory-reset.service" in l and "systemctl" not in l and ">/dev/null" in l)
        self.assertIn("systemd-sysext.service systemd-confext.service", line)


class ImageLayout(unittest.TestCase):
    def test_extension_folders_point_at_the_data_partition(self):
        for name, d in (("extensions", "var-lib-extensions"), ("confexts", "var-lib-confexts")):
            p = os.path.join(BASE, "var", "lib", name)
            self.assertTrue(os.path.islink(p), p)
            self.assertEqual(os.readlink(p), f"/data/state/{d}")
            self.assertIn(f" {d}", read("os/rootfs/layers/base/usr/lib/systemd/system/onemind-data-layout.service"))

    def test_os_release_gets_the_extension_levels(self):
        frag = read("os/rootfs/layers/base/usr/lib/onemind/os-release.sysext")
        keys = [l for l in frag.splitlines() if l and not l.startswith("#")]
        self.assertEqual(keys, ["SYSEXT_LEVEL=1", "CONFEXT_LEVEL=1"])
        self.assertIn("/usr/lib/onemind/os-release.sysext >> /usr/lib/os-release", read("os/rootfs/Containerfile"))

    def test_no_trusted_key_ships_outside_usr(self):
        for p in ("etc/verity.d", "run/verity.d"):
            self.assertFalse(os.path.exists(os.path.join(BASE, p)), p)


@unittest.skipUnless(shutil.which("sh"), "needs sh")
class Guard(unittest.TestCase):
    def setUp(self):
        self.r = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.r)
        for d in ("var/lib/extensions", "var/lib/confexts", "etc/extensions", "run/extensions", "usr/lib/verity.d"):
            os.makedirs(os.path.join(self.r, d))

    def put(self, rel, content="x"):
        p = os.path.join(self.r, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(content)
        return p

    def run_guard(self, kind):
        return subprocess.run(["sh", GUARD, kind, self.r], capture_output=True, text=True)

    def test_empty_and_disk_images_pass(self):
        self.put("var/lib/extensions/good.raw")
        self.put("var/lib/confexts/conf.raw")
        self.put("usr/lib/verity.d/onemind.crt")
        for kind in ("sysext", "confext"):
            r = self.run_guard(kind)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(f"ONEMIND-SYSEXT-GUARD: {kind} ok", r.stderr)

    def test_a_plain_directory_is_refused_and_named(self):
        for kind, rel in (("sysext", "var/lib/extensions/plaindir"), ("sysext", "etc/extensions/x"),
                          ("sysext", "run/extensions/.hidden"), ("confext", "var/lib/confexts/confdir")):
            os.makedirs(os.path.join(self.r, rel))
            r = self.run_guard(kind)
            self.assertEqual(r.returncode, 1, rel)
            self.assertIn(f"ONEMIND-SYSEXT-GUARD: refused {kind} path=/{rel} reason=directory-extension", r.stderr)
            shutil.rmtree(os.path.join(self.r, rel))

    def test_a_directory_whose_name_starts_with_two_dots_is_refused(self):
        # PR 972 review: "$d"/* and "$d"/.[!.]* both miss "..evil", and systemd-sysext merges such a directory.
        for kind, rel in (("sysext", "var/lib/extensions/..evil"), ("sysext", "etc/extensions/...x"),
                          ("confext", "var/lib/confexts/..evil")):
            os.makedirs(os.path.join(self.r, rel))
            r = self.run_guard(kind)
            self.assertEqual(r.returncode, 1, rel)
            self.assertIn(f"ONEMIND-SYSEXT-GUARD: refused {kind} path=/{rel} reason=directory-extension", r.stderr)
            shutil.rmtree(os.path.join(self.r, rel))

    def test_two_dot_disk_images_pass_and_dot_entries_are_never_judged(self):
        self.put("var/lib/extensions/..x.raw")
        self.put("var/lib/confexts/..y.raw")
        for kind in ("sysext", "confext"):
            r = self.run_guard(kind)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn("refused", r.stderr, "'.' and '..' are never extension entries")

    def test_a_symlink_to_a_directory_is_refused(self):
        os.makedirs(os.path.join(self.r, "data/tree"))
        os.symlink(os.path.join(self.r, "data/tree"), os.path.join(self.r, "var/lib/extensions/link.raw"))
        self.assertEqual(self.run_guard("sysext").returncode, 1)

    def test_keys_outside_usr_are_refused(self):
        for rel in ("etc/verity.d/evil.crt", "run/verity.d/evil.crt"):
            self.put(rel)
            for kind in ("sysext", "confext"):
                r = self.run_guard(kind)
                self.assertEqual(r.returncode, 1, rel)
                self.assertIn(f"path=/{os.path.dirname(rel)} reason=key-outside-usr", r.stderr)
            shutil.rmtree(os.path.join(self.r, os.path.dirname(rel)))

    def test_each_kind_looks_only_at_its_own_folders(self):
        os.makedirs(os.path.join(self.r, "var/lib/confexts/confdir"))
        self.assertEqual(self.run_guard("sysext").returncode, 0)
        self.assertEqual(self.run_guard("confext").returncode, 1)

    def test_unknown_kind_is_a_usage_error(self):
        self.assertEqual(self.run_guard("portable").returncode, 2)


class Harness(unittest.TestCase):
    def test_criteria_are_preregistered_with_their_current_hash(self):
        with open(os.path.join(ROOT, "test", "qemu", "CRITERIA-SYSEXT.md"), "rb") as f:
            crit = f.read()
        lines = [l for l in read("test/qemu/PREREGISTRATION.sha256").splitlines() if "  CRITERIA-SYSEXT.md  " in l]
        self.assertEqual(lines[-1].split()[0], hashlib.sha256(crit).hexdigest())

    def test_merged_needs_the_marker_and_the_status_listing(self):
        h = harness()
        sx = base64.b64encode(json.dumps([{"hierarchy": "/usr", "extensions": ["good"]},
                                          {"hierarchy": "/opt", "extensions": "none"}]).encode()).decode()
        cx = base64.b64encode(json.dumps([{"hierarchy": "/etc", "extensions": "none"}]).encode()).decode()
        out = f"M_good=1\nM_wrong=1\nM_confgood=1\nSXJ={sx}\nCXJ={cx}\n"
        m = h.merged_from(out)
        self.assertTrue(m["good"])
        self.assertFalse(m["wrong"], "a marker without a status listing is not a merge")
        self.assertFalse(m["confgood"])
        dx = base64.b64encode(json.dumps([{"hierarchy": "/usr", "extensions": ["..evil"]}]).encode()).decode()
        self.assertTrue(h.merged_from(f"M_..evil=1\nSXJ={dx}\n")["..evil"], "X8 reads two-dot names too")
        self.assertEqual(h.listed("not base64!"), set())
        self.assertEqual(h.listed(""), set())

    def test_tag_ignores_the_echoed_command(self):
        h = harness()
        self.assertEqual(h.tag('echo "M_good=$(test -e x && echo 1)"\nM_good=1\n', "M_good"), "1")
        self.assertEqual(h.tag('echo "VERITY=$(cat x)"\n', "VERITY"), "")

    def test_verdict_needs_x0_to_x8_and_no_fail(self):
        h = harness()
        ok = [{"test": f"X{i}", "verdict": "PASS"} for i in range(9)] + [{"test": "O1", "verdict": "OBSERVED"}]
        self.assertTrue(h.verdict_ok(ok))
        self.assertFalse(h.verdict_ok(ok[:-2]))
        self.assertFalse(h.verdict_ok([r for r in ok if r["test"] != "X8"]), "X8 counts from section 5 on")
        self.assertFalse(h.verdict_ok(ok + [{"test": "HARNESS", "verdict": "FAIL"}]))

    def test_kit_script_signs_the_root_hash_and_uses_the_right_partition_types(self):
        h = harness()
        s = h.kit_script("x86-64")
        self.assertIn("openssl smime -sign -nocerts -noattr -binary", s)
        self.assertIn('printf \'{"rootHash":"%s","signature":"%s"}\'', s)
        for t in ("8484680c-9521-48c6-9c11-b0720656f69e", "77ff5f63-e7b6-4633-acf4-1565b864c0e6",
                  "e7bb33fb-06cf-4e81-8273-e543b413e2e2", "4f68bce3-e8cd-4db1-96e7-fbcaf984b709",
                  "2c7357ed-ebd2-46d9-aec1-23d437ec2bf5", "41092b05-9fc8-4523-994f-2def0408b176"):
            self.assertIn(t, s)
        for name in ("good sysext trusted", "wrong sysext wrong", "unsigned sysext none",
                     "confgood confext trusted", "confunsigned confext none"):
            self.assertIn(f"ddi {name}", s)
        self.assertIn('if [ "$2" = sysext ]; then fsroot="$t/usr"', s, "a usr partition holds the /usr tree itself")
        self.assertIn('tree ..evil sysext; rm -rf "$O/img/..evil"; cp -a "$W/tree-..evil" "$O/img/..evil"', s)
        self.assertIn('tree ..confevil confext; rm -rf "$O/img/..confevil"; cp -a "$W/tree-..confevil" "$O/img/..confevil"', s)
        self.assertNotIn("BEGIN", s, "no key material in the script")
        if shutil.which("sh"):
            f = tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False)
            f.write(s); f.close()
            self.addCleanup(os.unlink, f.name)
            self.assertEqual(subprocess.run(["sh", "-n", f.name]).returncode, 0)

    def test_the_harness_is_wired_into_make(self):
        mk = read("Makefile")
        self.assertIn("sysextguard:", mk)
        self.assertIn("/src/test/qemu/sysextguard.py --board $(BOARD)", mk)
        self.assertIn("sysextguard.py", read("test/qemu/README.md"))


if __name__ == "__main__":
    unittest.main()
