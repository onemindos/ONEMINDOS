# SPDX-License-Identifier: Apache-2.0
"""One version for desktop and mobile (scripts/release/stamp-client-versions.py): no drift, correct stamping."""
import importlib.util, os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "release", "stamp-client-versions.py")
spec = importlib.util.spec_from_file_location("stamp", SCRIPT)
stamp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stamp)

FILES = ["desktop/package.json", "desktop/package-lock.json", "desktop/src-tauri/tauri.conf.json",
         "desktop/src-tauri/Cargo.toml", "desktop/src-tauri/Cargo.lock", "mobile/package.json",
         "mobile/package-lock.json", "mobile/app.json"]


def run(*args):
    return subprocess.run([sys.executable, "-I", SCRIPT, *args], capture_output=True, text=True)


class Committed(unittest.TestCase):
    def test_every_client_file_has_the_same_version(self):
        versions, code, build = stamp.read_versions(ROOT)
        self.assertEqual(len(set(versions.values())), 1, f"client versions drifted: {versions}")

    def test_store_counters_match_the_version(self):
        versions, code, build = stamp.read_versions(ROOT)
        v = next(iter(versions.values()))
        self.assertTrue(str(build).isdigit(), build)
        self.assertEqual(code, stamp.version_code(v, int(build)))

    def test_check_passes_on_the_repo(self):
        versions, _, build = stamp.read_versions(ROOT)
        r = run("--version", next(iter(versions.values())), "--build", str(build), "--check")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_identifiers_are_flagged_not_changed(self):
        # The founder must pick one domain before the first store upload (see the PR). This only pins
        # that the stamper never rewrites them, so a stamp cannot silently change a store identity.
        for rel in ("mobile/app.json", "desktop/src-tauri/tauri.conf.json"):
            before = open(os.path.join(ROOT, rel)).read()
            self.assertIn("onemind", before)


class Stamping(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        for f in FILES:
            os.makedirs(os.path.dirname(os.path.join(self.t.name, f)), exist_ok=True)
            shutil.copy(os.path.join(ROOT, f), os.path.join(self.t.name, f))

    def test_stamp_then_no_drift(self):
        r = run("--root", self.t.name, "--version", "1.4.2-dev.7", "--build", "42")
        self.assertEqual(r.returncode, 0, r.stderr)
        versions, code, build = stamp.read_versions(self.t.name)
        self.assertEqual(set(versions.values()), {"1.4.2"})     # pre-release suffix never reaches a store
        self.assertEqual(code, 100_000_000 + 4_000_000 + 20_000 + 42)
        self.assertEqual(build, "42")
        self.assertEqual(run("--root", self.t.name, "--version", "1.4.2", "--build", "42", "--check").returncode, 0)

    def test_check_detects_drift(self):
        p = os.path.join(self.t.name, "mobile/app.json")
        s = open(p).read().replace('"version": "0.1.0"', '"version": "0.1.1"')
        open(p, "w").write(s)
        r = run("--root", self.t.name, "--version", "0.1.0", "--build", "1", "--check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("mobile/app.json", r.stderr)

    def test_only_our_own_crate_changes_in_cargo_lock(self):
        run("--root", self.t.name, "--version", "2.0.0")
        old = open(os.path.join(ROOT, "desktop/src-tauri/Cargo.lock")).read().splitlines()
        new = open(os.path.join(self.t.name, "desktop/src-tauri/Cargo.lock")).read().splitlines()
        self.assertEqual(sum(a != b for a, b in zip(old, new)), 1)

    def test_identifiers_untouched(self):
        run("--root", self.t.name, "--version", "3.0.0")
        self.assertIn('"bundleIdentifier": "com.onemindos.mobile"', open(os.path.join(self.t.name, "mobile/app.json")).read())
        self.assertIn('"identifier": "com.onemindos.desktop"', open(os.path.join(self.t.name, "desktop/src-tauri/tauri.conf.json")).read())

    def test_bad_versions_refused(self):
        for v in ("", "1.2", "v1.2.3", "300.0.0", "1.100.0"):
            self.assertEqual(run("--root", self.t.name, "--version", v).returncode, 2, v)
        self.assertEqual(run("--root", self.t.name, "--version", "1.0.0", "--build", "10000").returncode, 2)

    def test_versioncode_rises_with_version_and_build(self):
        c = stamp.version_code
        self.assertLess(c("0.1.0", 9999), c("0.1.1", 0))
        self.assertLess(c("0.99.99", 9999), c("1.0.0", 0))
        self.assertLess(c("1.0.0", 1), c("1.0.0", 2))


class Workflow(unittest.TestCase):
    def test_release_gate_runs_the_stamp_check(self):
        s = open(os.path.join(ROOT, ".github/workflows/release.yml")).read()
        self.assertIn("stamp-client-versions.py", s)
        self.assertIn("test_client_versions.py", s)


if __name__ == "__main__":
    unittest.main()
