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

    def setUp(self):
        # preflight refuses in CI first; these tests must behave the same on a CI runner.
        env = {k: v for k, v in os.environ.items() if k not in ("CI", "GITHUB_ACTIONS")}
        p = unittest.mock.patch.dict(os.environ, env, clear=True)
        p.start()
        self.addCleanup(p.stop)

    def guide(self, work, **kw):
        return cg.Guide(cg.Io(auto=True), work, **kw)

    def test_refuses_with_a_default_route(self):
        with tempfile.TemporaryDirectory() as d:
            with unittest.mock.patch.dict(os.environ, {"ONEMIND_GUIDE_TEST_ROUTE": "present"}):
                with self.assertRaises(cg.Stop) as c:
                    self.guide(d).preflight()
        self.assertIn("default route", str(c.exception))
        self.assertIn("NO network", str(c.exception))

    def _linux_probe(self, v4, v6):
        """Stub for cg._probe on Linux: each of v4 / v6 is stdout text, or None for 'could not run'."""
        def probe(cmd):
            out = v4 if "-4" in cmd else v6
            return (False, "", "") if out is None else (True, out, "")
        return probe

    def _route(self, v4, v6):
        env = {k: v for k, v in os.environ.items() if k != "ONEMIND_GUIDE_TEST_ROUTE"}
        with unittest.mock.patch.dict(os.environ, env, clear=True), \
                unittest.mock.patch.object(cg.sys, "platform", "linux"), \
                unittest.mock.patch.object(cg, "_probe", self._linux_probe(v4, v6)):
            return cg.default_route()

    def test_route_probe_that_cannot_run_refuses(self):
        self.assertTrue(self._route(None, None))        # no ip binary
        self.assertTrue(self._route("", None))          # IPv6 probe fails: unknown
        self.assertTrue(self._route(None, ""))

    def test_ipv6_only_default_route_refuses(self):
        self.assertTrue(self._route("", "default via fe80::1 dev wlan0 proto ra metric 600\n"))

    def test_ipv4_default_route_refuses(self):
        self.assertTrue(self._route("default via 192.0.2.1 dev eth0\n", ""))

    def test_no_route_in_either_family_passes(self):
        self.assertFalse(self._route("", ""))

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


class SigningSticks(unittest.TestCase):
    """The signing step with two separate stick folders (throwaway files; no keys, no passphrases)."""

    class Talk(cg.Io):
        def __init__(self, answers, after=None):
            super().__init__(answers=answers)
            self.lines, self.after, self.n = [], after, 0

        def say(self, text="", err=False):
            self.lines.append(text)

        def ask(self, prompt, auto=None):
            r = super().ask(prompt, auto)
            self.n += 1
            if self.after:
                self.after(self.n)
            return r

    def setup_guide(self, d, after=None):
        work = os.path.join(d, "work"); os.mkdir(work)
        self.a, self.b = os.path.join(d, "stick-a"), os.path.join(d, "stick-b")
        for p in (self.a, self.b):
            os.mkdir(p)
            open(os.path.join(p, "root.key"), "w").write("throwaway")
        answers = [self.a, "ENCRYPTED", self.b, "ENCRYPTED"]
        io = self.Talk(answers, after and (lambda n: after(n)))
        g = cg.Guide(io, work, repo=ROOT)
        g.state["holders"] = {"A": "Ann", "B": "Bo", "C": "Cy"}
        g.state["signers"] = ["A", "B"]
        self.calls = []
        g.run_script = lambda *a, **k: (self.calls.append(a), os.makedirs(a[1]), open(os.path.join(a[1], "root.json"), "w").write("{}"), 0)[3]
        return g, io

    def patches(self):
        ids = iter(["uuid-a", "uuid-b"])
        return (unittest.mock.patch.object(cg.Guide, "on_work_disk", lambda self, p: False),
                unittest.mock.patch.object(cg, "stick_identity", lambda p: (next(ids), None)))

    def test_second_signer_is_told_to_keep_the_first_stick(self):
        with tempfile.TemporaryDirectory() as d:
            g, io = self.setup_guide(d)
            p1, p2 = self.patches()
            with p1, p2:
                g.sign()
            text = "\n".join(io.lines)
            second = text.split("signer B")[1]
            self.assertIn("KEEP holder A (Ann)'s stick PLUGGED IN", second)
            self.assertNotIn("remove any other stick", second)
            self.assertIn("remove any other stick", text.split("signer B")[0])    # fine for the first signer
            create = self.calls[0]
            self.assertIn(os.path.join(os.path.realpath(self.a), "root.key"), create)
            self.assertIn(os.path.join(os.path.realpath(self.b), "root.key"), create)

    def test_a_missing_key_names_the_holder_not_the_passphrase(self):
        with tempfile.TemporaryDirectory() as d:
            g, io = self.setup_guide(d, after=lambda n: n == 4 and os.remove(os.path.join(self.a, "root.key")))
            p1, p2 = self.patches()
            with p1, p2, self.assertRaises(cg.Stop) as c:
                g.sign()
            msg = str(c.exception)
            self.assertIn("holder A (Ann)'s stick is not plugged in", msg)
            self.assertIn("KEEP the other signer's stick", msg)
            self.assertNotIn("passphrase", msg)
            self.assertEqual(self.calls, [])

    def test_failed_create_with_both_keys_present_still_says_how_to_retry(self):
        with tempfile.TemporaryDirectory() as d:
            g, io = self.setup_guide(d)
            g.run_script = lambda *a, **k: 1
            p1, p2 = self.patches()
            with p1, p2, self.assertRaises(cg.Stop) as c:
                g.sign()
            self.assertIn("plug in their sticks together", str(c.exception))

    def test_same_label_sticks_are_different_by_volume_id_same_stick_refused(self):
        with tempfile.TemporaryDirectory() as d:
            work = os.path.join(d, "work"); os.mkdir(work)
            s = os.path.join(d, "STICK"); os.mkdir(s)
            for ids, ok in ((["u1", "u2"], True), (["u1", "u1"], False)):
                it = iter(ids)
                g = cg.Guide(cg.Io(answers=[s, "ENCRYPTED", s, "ENCRYPTED"]), work, repo=ROOT)
                g.state["holders"] = {"A": "Ann", "B": "Bo", "C": "Cy"}
                with unittest.mock.patch.object(cg.Guide, "on_work_disk", lambda self, p: False), \
                        unittest.mock.patch.object(cg, "stick_identity", lambda p: (next(it), None)):
                    g.stick_path("A", need_key=False)
                    if ok:
                        g.stick_path("B", need_key=False)
                    else:
                        with self.assertRaises(cg.Stop):
                            g.stick_path("B", need_key=False)

    def test_no_identifier_says_what_could_not_be_done(self):
        sid, note = (None, None)
        with unittest.mock.patch.object(cg, "_probe", lambda cmd: (False, "", "")):
            sid, note = cg.stick_identity(tempfile.gettempdir())
        self.assertIsNone(sid)
        self.assertIn(sys.platform, note)

    def test_ipv6_off_in_kernel_refuses_and_says_why(self):
        env = {k: v for k, v in os.environ.items() if k != "ONEMIND_GUIDE_TEST_ROUTE"}
        probe = lambda cmd: (False, "", "") if "-6" in cmd else (True, "", "")
        with unittest.mock.patch.dict(os.environ, env, clear=True), \
                unittest.mock.patch.object(cg.sys, "platform", "linux"), \
                unittest.mock.patch.object(cg, "_probe", probe), \
                unittest.mock.patch.object(cg.os.path, "exists", lambda p: False if p == "/proc/net/if_inet6" else True):
            self.assertTrue(cg.default_route())
            self.assertIn("IPv6 is switched off", cg._ROUTE_REASON)


if __name__ == "__main__":
    unittest.main()
