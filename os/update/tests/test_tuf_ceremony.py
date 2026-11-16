# SPDX-License-Identifier: Apache-2.0
"""The root-key ceremony (D-010, #153): scripts/tuf-bootstrap-root.sh and its tuf-repo.py commands.

Everything here uses throwaway keys in a temp directory. Needs the pinned python-tuf
(os/update/requirements-tuf.txt); skipped when it is not installed."""
import json, os, shutil, subprocess, sys, tempfile, unittest
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import UPDATE, load  # noqa: E402

try:
    tr = load("tuf-repo")
except ImportError as e:          # pragma: no cover
    tr = None

SCRIPT = os.path.join(os.path.dirname(UPDATE), "..", "scripts", "tuf-bootstrap-root.sh")
SCRIPT = os.path.normpath(SCRIPT)
PASS = "throwaway-test-passphrase"


def script_env(**extra):
    env = {k: v for k, v in os.environ.items() if k not in ("CI", "GITHUB_ACTIONS", "ONEMIND_TUF_PASSPHRASE")}
    env["PYTHON"] = sys.executable
    env.update(extra)
    return env


def run_script(*args, **env):
    return subprocess.run(["sh", SCRIPT, *args], env=script_env(**env), capture_output=True, text=True)


@unittest.skipIf(tr is None, "python-tuf not installed (pip install --require-hashes -r os/update/requirements-tuf.txt)")
class Ceremony(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.env = unittest.mock.patch.dict(os.environ, {tr.PASSPHRASE_ENV: PASS})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.p = lambda *a: os.path.join(self.d, *a)

    def sticks(self):
        for h in "abc":
            tr.keygen(self.p("sticks", h), ["root"], encrypt=True)
        tr.keygen(self.p("online"), ["targets", "snapshot", "timestamp"])
        return {"a": self.p("sticks", "a", "root.key"), "b": self.p("sticks", "b", "root.key"),
                "c_pub": self.p("sticks", "c", "root.pub")}

    def make_root(self, out="out", **kw):
        k = self.sticks() if not os.path.exists(self.p("sticks")) else {
            "a": self.p("sticks", "a", "root.key"), "b": self.p("sticks", "b", "root.key"),
            "c_pub": self.p("sticks", "c", "root.pub")}
        return tr.init_root([k["a"], k["b"]], [k["c_pub"]], 2, self.p("online", "targets.pub"),
                            self.p("online", "snapshot.pub"), self.p("online", "timestamp.pub"), self.p(out), **kw)

    # ---- keys on the sticks
    def test_root_keys_are_encrypted_and_never_overwritten(self):
        self.sticks()
        pem = open(self.p("sticks", "a", "root.key"), "rb").read()
        self.assertIn(b"ENCRYPTED PRIVATE KEY", pem)
        self.assertNotIn(b"ENCRYPTED PRIVATE KEY", open(self.p("online", "targets.key"), "rb").read())  # CI needs plain PEM
        self.assertEqual(os.stat(self.p("sticks", "a", "root.key")).st_mode & 0o077, 0)
        with self.assertRaises(SystemExit) as e:
            tr.keygen(self.p("sticks", "a"), ["root"], encrypt=True)
        self.assertIn("refusing to overwrite", str(e.exception))
        self.assertEqual(open(self.p("sticks", "a", "root.key"), "rb").read(), pem)

    def test_a_short_passphrase_is_refused_and_nothing_is_written(self):
        os.environ[tr.PASSPHRASE_ENV] = "short"
        with self.assertRaises(SystemExit):
            tr.keygen(self.p("s"), ["root"], encrypt=True)
        self.assertFalse(os.path.exists(self.p("s", "root.key")))

    def test_the_wrong_passphrase_does_not_sign(self):
        self.sticks()
        os.environ[tr.PASSPHRASE_ENV] = "not-the-right-passphrase"
        with self.assertRaises(SystemExit) as e:
            tr.load_signer(self.p("sticks", "a", "root.key"))
        self.assertIn("wrong passphrase", str(e.exception))

    # ---- 2-of-3 with one holder absent
    def test_two_of_three_with_one_holder_absent(self):
        md = self.make_root()
        root = md.signed
        self.assertEqual((root.roles["root"].threshold, len(root.roles["root"].keyids)), (2, 3))
        self.assertEqual(len(md.signatures), 2)         # holder C did not sign, their key is trusted
        lines, problems = tr.inspect_root(self.p("out", "root.json"), 2, 3)
        self.assertEqual(problems, [])
        self.assertIn("valid and trusted: 2", "\n".join(lines))

    def test_one_signer_is_not_enough(self):
        k = self.sticks()
        with self.assertRaises(SystemExit):
            tr.init_root([k["a"]], [k["b"].replace("root.key", "root.pub"), k["c_pub"]], 2, self.p("online", "targets.pub"),
                         self.p("online", "snapshot.pub"), self.p("online", "timestamp.pub"), self.p("out"))
        self.assertFalse(os.path.exists(self.p("out", "root.json")))

    def test_a_second_create_never_overwrites_the_root(self):
        self.make_root()
        before = open(self.p("out", "root.json"), "rb").read()
        with self.assertRaises(SystemExit) as e:
            self.make_root()
        self.assertIn("refusing to overwrite", str(e.exception))
        self.assertEqual(open(self.p("out", "root.json"), "rb").read(), before)

    # ---- the inspection catches what a box would reject
    def test_inspect_flags_a_wrong_shape_and_a_missing_signature(self):
        self.make_root()
        root = self.p("out", "root.json")
        self.assertTrue(tr.inspect_root(root, 3, 3)[1])             # expected 3-of-3, got 2-of-3
        self.assertTrue(tr.inspect_root(root, 2, 5)[1])
        doc = json.load(open(root))
        doc["signatures"] = doc["signatures"][:1]                    # one of the two needed signatures
        broken = self.p("one-sig.json")
        json.dump(doc, open(broken, "w"))
        problems = tr.inspect_root(broken, 2, 3)[1]
        self.assertTrue(any("threshold" in p for p in problems), problems)
        with self.assertRaises(Exception):                           # and a box refuses it as its trusted root
            os.makedirs(self.p("repo"))
            shutil.copy(broken, self.p("repo", "root.json"))
            tr.verify(self.p("repo"), broken, metadata_only=True)

    def test_inspect_flags_a_signature_that_was_changed(self):
        self.make_root()
        doc = json.load(open(self.p("out", "root.json")))
        doc["signed"]["expires"] = "2099-01-01T00:00:00Z"            # edited after signing
        tampered = self.p("tampered.json")
        json.dump(doc, open(tampered, "w"))
        self.assertTrue(tr.inspect_root(tampered, 2, 3)[1])

    def test_online_keys_must_differ_from_the_root_keys(self):
        k = self.sticks()
        tr.init_root([k["a"], k["b"]], [k["c_pub"]], 2, self.p("sticks", "a", "root.pub"),
                     self.p("online", "snapshot.pub"), self.p("online", "timestamp.pub"), self.p("reused"))
        problems = tr.inspect_root(self.p("reused", "root.json"), 2, 3)[1]
        self.assertTrue(any("own key" in p for p in problems), problems)

    # ---- the script, as the founder will run it
    def test_the_script_refuses_to_run_in_ci(self):
        for var in ("CI", "GITHUB_ACTIONS"):
            r = run_script("rehearse", self.p("nope"), **{var: "true"})
            self.assertEqual(r.returncode, 1)
            self.assertIn("never in CI", r.stderr)
            self.assertFalse(os.path.exists(self.p("nope")))

    def test_the_rehearsal_runs_the_whole_ceremony_on_throwaway_keys(self):
        r = run_script("rehearse", self.p("run"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("REHEARSAL PASSED", r.stderr)
        self.assertIn("threshold 2 of 3", r.stdout)
        self.assertIn("tuf verify: 3 target(s) checked, 0 problem(s)", r.stdout)
        self.assertEqual(tr.inspect_root(self.p("run", "out", "root.json"), 2, 3)[1], [])
        again = run_script("rehearse", self.p("run"))               # never reuse a rehearsal directory
        self.assertEqual(again.returncode, 2)

    def test_the_real_steps_in_order_with_a_holder_absent(self):
        for h in "abc":
            r = run_script("root-key", self.p("stick-" + h), "root", ONEMIND_TUF_PASSPHRASE=PASS)
            self.assertEqual(r.returncode, 0, r.stderr)
        r = run_script("online-keys", self.p("online"))
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_script("create", self.p("root"), "security", "2", self.p("stick-a", "root.key"), self.p("stick-b", "root.key"),
                       self.p("stick-c", "root.pub"), "--", self.p("online", "targets.pub"), self.p("online", "snapshot.pub"),
                       self.p("online", "timestamp.pub"), ONEMIND_TUF_PASSPHRASE=PASS)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("os/rootfs/layers/base/usr/lib/onemind/tuf/security/root.json", r.stdout)
        self.assertIn("root      threshold 2", r.stdout)
        chk = run_script("check", self.p("root"), "2", "3")
        self.assertEqual(chk.returncode, 0, chk.stdout + chk.stderr)
        self.assertIn("sha256 ", chk.stdout)
        self.assertEqual(run_script("check", self.p("root"), "3", "3").returncode, 1)   # wrong shape is loud
        no_dash = run_script("create", self.p("root2"), "security", "2", self.p("stick-a", "root.key"))
        self.assertEqual(no_dash.returncode, 2)
        # create over an existing root: refused
        again = run_script("create", self.p("root"), "security", "2", self.p("stick-a", "root.key"), self.p("stick-b", "root.key"),
                           self.p("stick-c", "root.pub"), "--", self.p("online", "targets.pub"), self.p("online", "snapshot.pub"),
                           self.p("online", "timestamp.pub"), ONEMIND_TUF_PASSPHRASE=PASS)
        self.assertNotEqual(again.returncode, 0)
        self.assertIn("refusing to overwrite", again.stderr)

    def test_a_stick_mounted_at_a_path_with_spaces_works(self):
        sticks = {h: self.p("STICK " + h.upper()) for h in "abc"}
        for h, path in sticks.items():
            self.assertEqual(run_script("root-key", path, "root", ONEMIND_TUF_PASSPHRASE=PASS).returncode, 0)
        run_script("online-keys", self.p("on line"))
        r = run_script("create", self.p("the root"), "security", "2", sticks["a"] + "/root.key", sticks["b"] + "/root.key",
                       sticks["c"] + "/root.pub", "--", self.p("on line", "targets.pub"), self.p("on line", "snapshot.pub"),
                       self.p("on line", "timestamp.pub"), ONEMIND_TUF_PASSPHRASE=PASS)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(run_script("check", self.p("the root"), "2", "3").returncode, 0)

    def test_the_wrong_passphrase_stops_the_real_create(self):
        for h in "abc":
            run_script("root-key", self.p("stick-" + h), "root", ONEMIND_TUF_PASSPHRASE=PASS)
        run_script("online-keys", self.p("online"))
        r = run_script("create", self.p("root"), "security", "2", self.p("stick-a", "root.key"), self.p("stick-b", "root.key"),
                       self.p("stick-c", "root.pub"), "--", self.p("online", "targets.pub"), self.p("online", "snapshot.pub"),
                       self.p("online", "timestamp.pub"), ONEMIND_TUF_PASSPHRASE="a-different-passphrase")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(self.p("root", "root.json")))


if __name__ == "__main__":
    unittest.main()
