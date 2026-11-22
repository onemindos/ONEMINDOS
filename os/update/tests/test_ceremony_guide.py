# SPDX-License-Identifier: Apache-2.0
"""scripts/ceremony-guide.py end to end on throwaway keys (REL-01, D-010). Needs the pinned python-tuf
(os/update/requirements-tuf.txt); skipped when it is not installed. The refusals are in test/unit/."""
import json, os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
GUIDE = os.path.join(ROOT, "scripts", "ceremony-guide.py")
THROWAWAY = "rehearsal-throwaway-passphrase"
try:
    import tuf, securesystemslib  # noqa: F401
    HAVE = True
except ImportError:
    HAVE = False


def run(*args, **env):
    e = {k: v for k, v in os.environ.items() if k not in ("CI", "GITHUB_ACTIONS", "ONEMIND_TUF_PASSPHRASE")}
    e["PYTHON"] = sys.executable
    e.update(env)
    return subprocess.run([sys.executable, GUIDE, *args], env=e, capture_output=True, text=True, stdin=subprocess.DEVNULL)


@unittest.skipUnless(HAVE, "python-tuf not installed (pip install --require-hashes -r os/update/requirements-tuf.txt)")
class Rehearsal(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.work = os.path.join(self.d, "work")

    def test_rehearsal_end_to_end(self):
        r = run("--rehearsal", "--work", self.work)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("REHEARSAL PASSED", r.stdout)
        self.assertIn("WHAT YOU NEED AND HOW LONG IT TAKES", r.stdout)
        self.assertIn("THE SHEET", r.stdout)
        self.assertIn("D-010", r.stdout)
        root = json.load(open(os.path.join(self.work, "out-security", "root.json")))["signed"]
        self.assertEqual(root["roles"]["root"]["threshold"], 2)
        self.assertEqual(len(set(root["roles"]["root"]["keyids"])), 3)
        for h in ("a", "b", "c"):                      # each holder's private key is encrypted
            self.assertIn(b"ENCRYPTED PRIVATE KEY", open(os.path.join(self.work, "sticks", f"holder-{h}", "root.key"), "rb").read())

    def test_no_passphrase_in_any_log_state_or_output(self):
        r = run("--rehearsal", "--work", self.work)
        self.assertEqual(r.returncode, 0, r.stderr)
        texts = [r.stdout, r.stderr]
        for dp, _, fs in os.walk(self.work):
            for f in fs:
                if f in ("guide.log", "state.json", "SHEET.txt"):
                    texts.append(open(os.path.join(dp, f)).read())
        self.assertEqual(len(texts), 5)
        for t in texts:
            self.assertNotIn(THROWAWAY, t)
            self.assertNotIn("PASSPHRASE=", t)
        mode = os.stat(os.path.join(self.work, "guide.log")).st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_resume_after_an_interruption(self):
        r1 = run("--rehearsal", "--work", self.work, "--stop-after", "keys")
        self.assertEqual(r1.returncode, 1)
        self.assertIn("stopped after keys", r1.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.work, "out-security")))
        r2 = run("--rehearsal", "--work", self.work)
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertIn("Resuming an earlier run", r2.stdout)
        self.assertIn("[skip] keys", r2.stdout)
        self.assertIn("REHEARSAL PASSED", r2.stdout)

    def test_a_different_commit_blocks_the_resume(self):
        run("--rehearsal", "--work", self.work, "--stop-after", "holders")
        sp = os.path.join(self.work, "state.json")
        s = json.load(open(sp)); s["commit"] = "0" * 40
        json.dump(s, open(sp, "w"))
        r = run("--rehearsal", "--work", self.work)
        self.assertEqual(r.returncode, 1)
        self.assertIn("started at commit", r.stderr)

    def test_default_route_refusal_in_real_mode_comes_before_any_key(self):
        r = run("--work", self.work, ONEMIND_GUIDE_TEST_ROUTE="present")
        self.assertEqual(r.returncode, 1)            # no terminal here, so it stops even earlier: still no key made
        self.assertFalse(os.path.exists(os.path.join(self.work, "sticks")))


if __name__ == "__main__":
    unittest.main()
