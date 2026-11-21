# SPDX-License-Identifier: Apache-2.0
"""scripts/ceremony-guide.py (REL-01, D-010): the refusals. They need no python-tuf and no keys.
The end-to-end rehearsal and the no-secret-in-the-log test are in os/update/tests/test_ceremony_guide.py."""
import importlib.util, os, subprocess, sys, tempfile, unittest
import unittest.mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GUIDE = os.path.join(ROOT, "scripts", "ceremony-guide.py")
spec = importlib.util.spec_from_file_location("ceremony_guide", GUIDE)
cg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cg)


def run(*args, **env):
    e = {k: v for k, v in os.environ.items() if k not in ("CI", "GITHUB_ACTIONS", cg.PASSPHRASE_ENV)}
    e.update(env)
    return subprocess.run([sys.executable, GUIDE, *args], env=e, capture_output=True, text=True, stdin=subprocess.DEVNULL)


class Refusals(unittest.TestCase):
    def test_refuses_in_ci(self):
        for var in ("CI", "GITHUB_ACTIONS"):
            for args in ([], ["--rehearsal"]):
                r = run(*args, **{var: "true"})
                self.assertEqual(r.returncode, 1, r.stderr)
                self.assertIn("never in CI", r.stderr)

    def test_real_run_needs_a_terminal(self):
        r = run()
        self.assertEqual(r.returncode, 1)
        self.assertIn("terminal", r.stderr)

    def test_real_run_refuses_a_passphrase_in_the_environment(self):
        r = run(**{cg.PASSPHRASE_ENV: "x" * 20})
        self.assertEqual(r.returncode, 1)
        self.assertIn("unset it", r.stderr)

    def test_solo_cannot_be_mixed_with_rehearsal(self):
        r = run("--rehearsal", cg.SOLO_FLAG)
        self.assertEqual(r.returncode, 1)

    def guide(self, work, **kw):
        return cg.Guide(cg.Io(auto=True), work, **kw)

    def test_refuses_with_a_default_route(self):
        with tempfile.TemporaryDirectory() as d:
            with unittest.mock.patch.dict(os.environ, {"ONEMIND_GUIDE_TEST_ROUTE": "present"}):
                with self.assertRaises(cg.Stop) as c:
                    self.guide(d).preflight()
        self.assertIn("default route", str(c.exception))
        self.assertIn("NO network", str(c.exception))

    def test_rehearsal_only_notes_the_route(self):
        with tempfile.TemporaryDirectory() as d:
            with unittest.mock.patch.dict(os.environ, {"ONEMIND_GUIDE_TEST_ROUTE": "present"}):
                g = self.guide(d, rehearsal=True)
                try:
                    g.preflight()
                except cg.Stop as e:                      # python-tuf may be missing here; not the route
                    self.assertNotIn("default route", str(e))

    def make_repo(self, d, dirty):
        repo = os.path.join(d, "repo")
        os.mkdir(repo)
        for a in (["init", "-q"], ["-c", "user.name=t", "-c", "user.email=ci", "commit", "-q", "--allow-empty", "-m", "x"]):
            subprocess.run(["git", "-C", repo, *a], check=True, capture_output=True)
        if dirty:
            open(os.path.join(repo, "f"), "w").write("x")
        return repo

    def test_refuses_a_dirty_tree_and_a_wrong_commit(self):
        with tempfile.TemporaryDirectory() as d, unittest.mock.patch.object(cg, "default_route", lambda: False):
            dirty = self.make_repo(d, True)
            with self.assertRaises(cg.Stop) as c:
                self.guide(os.path.join(d, "w1"), repo=dirty).preflight()
            self.assertIn("uncommitted", str(c.exception))
            os.makedirs(os.path.join(d, "clean"))
            clean = self.make_repo(os.path.join(d, "clean"), False)
            with self.assertRaises(cg.Stop) as c:
                self.guide(os.path.join(d, "w2"), repo=clean, expect_commit="0" * 12).preflight()
            self.assertIn("does not match", str(c.exception))

    def test_work_folder_must_be_outside_the_repo(self):
        with tempfile.TemporaryDirectory() as d, unittest.mock.patch.object(cg, "default_route", lambda: False):
            repo = self.make_repo(d, False)
            with self.assertRaises(cg.Stop) as c:
                self.guide(os.path.join(repo, "work"), repo=repo).preflight()
            self.assertIn("OUTSIDE", str(c.exception))

    def test_three_distinct_holders_unless_solo(self):
        with tempfile.TemporaryDirectory() as d:
            g = cg.Guide(cg.Io(answers=["Ann", "ann", "Cy"]), d)
            with self.assertRaises(cg.Stop) as c:
                g.holders()
            self.assertIn("cannot be the same person", str(c.exception))
            self.assertIn(cg.SOLO_FLAG, str(c.exception))
            self.assertIn("D-010", cg.D010)
            solo = cg.Guide(cg.Io(answers=["Ann"]), d, solo=True)
            solo.holders()
            self.assertEqual(set(solo.state["holders"].values()), {"Ann"})

    def test_solo_says_it_differs_from_d010(self):
        self.assertIn("NOT the ceremony D-010 requires", cg.SOLO_WARNING)
        self.assertIn("founder has to decide", cg.SOLO_WARNING)

    def test_a_stick_must_not_be_on_the_work_disk(self):
        with tempfile.TemporaryDirectory() as d:
            work = os.path.join(d, "work"); os.mkdir(work)
            g = cg.Guide(cg.Io(answers=[os.path.join(d, "fake-stick")]), work, repo=ROOT)
            g.state["holders"] = {"A": "Ann", "B": "Bo", "C": "Cy"}
            os.mkdir(os.path.join(d, "fake-stick"))
            with self.assertRaises(cg.Stop):
                g.stick_path("A", need_key=False)


if __name__ == "__main__":
    unittest.main()
