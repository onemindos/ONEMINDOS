# SPDX-License-Identifier: Apache-2.0
"""Renewing the TUF root (REL-03, #302): scripts/tuf-bootstrap-root.sh renew and tuf-repo.py renew-root.

Throwaway keys in a temp directory. Needs the pinned python-tuf (os/update/requirements-tuf.txt)."""
import copy, json, os, shutil, subprocess, sys, tempfile, unittest
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import UPDATE, load  # noqa: E402

try:
    tr = load("tuf-repo")
except ImportError:          # pragma: no cover
    tr = None

SCRIPT = os.path.normpath(os.path.join(os.path.dirname(UPDATE), "..", "scripts", "tuf-bootstrap-root.sh"))
PASS = "throwaway-test-passphrase"


def run_script(*args, **extra):
    env = {k: v for k, v in os.environ.items() if k not in ("CI", "GITHUB_ACTIONS", "ONEMIND_TUF_PASSPHRASE")}
    env["PYTHON"] = sys.executable
    env.update(extra)
    return subprocess.run(["sh", SCRIPT, *args], env=env, capture_output=True, text=True)


@unittest.skipIf(tr is None, "python-tuf not installed (pip install --require-hashes -r os/update/requirements-tuf.txt)")
class Renewal(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        env = unittest.mock.patch.dict(os.environ, {tr.PASSPHRASE_ENV: PASS})
        env.start()
        self.addCleanup(env.stop)
        self.p = lambda *a: os.path.join(self.d, *a)
        for h in "abc":
            tr.keygen(self.p("sticks", h), ["root"], encrypt=True)
        tr.keygen(self.p("online"), ["targets", "snapshot", "timestamp"])
        self.key = {h: self.p("sticks", h, "root.key") for h in "abc"}
        tr.init_root([self.key["a"], self.key["b"]], [self.p("sticks", "c", "root.pub")], 2,
                     self.p("online", "targets.pub"), self.p("online", "snapshot.pub"),
                     self.p("online", "timestamp.pub"), self.p("v1"))
        self.v1 = self.p("v1", "root.json")

    def renew(self, holders, out="v2", **kw):
        return tr.renew_root(self.v1, [self.key[h] for h in holders], self.p(out), **kw)

    def md(self, path):
        return tr.Metadata[tr.Root].from_file(path)

    # ---- Done when: a box on version 1 accepts version 2, refuses one signed by one holder
    def test_a_box_on_version_1_accepts_a_renewed_version_2(self):
        later = (tr.now() + tr.datetime.timedelta(days=300)).isoformat()    # renewed 300 days on
        with unittest.mock.patch.dict(os.environ, {"ONEMIND_TUF_NOW": later}):
            self.renew("bc")                                # a different pair than at the ceremony
        old, new = self.md(self.v1), self.md(self.p("v2", "root.json"))
        self.assertEqual(tr.box_accepts(old, new), [])
        self.assertEqual(new.signed.version, 2)
        self.assertEqual(new.signed.roles["root"].keyids, old.signed.roles["root"].keyids)   # same keys
        self.assertEqual(new.signed.roles["root"].threshold, 2)
        self.assertGreater(new.signed.expires, old.signed.expires)
        self.assertTrue(os.path.exists(self.p("v2", "2.root.json")))
        self.assertEqual(tr.inspect_root(self.p("v2", "root.json"), 2, 3)[1], [])

    def test_a_real_client_follows_the_chain_from_version_1_to_2(self):
        self._channel()
        self.renew("ab")
        shutil.copy(self.p("v2", "2.root.json"), self.p("chan", "2.root.json"))
        checked, problems = tr.verify(self.p("chan"), self.v1)       # the client trusts only version 1
        self.assertEqual(problems, [])
        self.assertTrue(checked)

    def test_a_version_2_signed_by_one_holder_is_refused_by_the_tool_and_by_a_client(self):
        with self.assertRaises(SystemExit) as e:
            self.renew("c")
        self.assertIn("need 2", str(e.exception))
        self.assertFalse(os.path.exists(self.p("v2", "root.json")))
        # Forge it anyway (one holder's signature only): a box must not follow it.
        self._channel()
        forged = tr.Root.from_dict(self.md(self.v1).signed.to_dict())
        forged.version = 2
        forged.expires = tr.now() + tr.datetime.timedelta(days=365)
        bad = tr.Metadata(forged)
        bad.sign(tr.load_signer(self.key["c"]), append=True)
        self.assertTrue(tr.box_accepts(self.md(self.v1), bad))        # the rule names the problem
        bad.to_file(self.p("chan", "2.root.json"), tr.SER)
        with self.assertRaises(Exception):
            tr.verify(self.p("chan"), self.v1, metadata_only=True)

    def test_the_same_holder_twice_or_a_stranger_does_not_count(self):
        with self.assertRaises(SystemExit) as e:
            tr.renew_root(self.v1, [self.key["a"], self.key["a"]], self.p("v2"))
        self.assertIn("twice", str(e.exception))
        tr.keygen(self.p("sticks", "x"), ["root"], encrypt=True)
        with self.assertRaises(SystemExit) as e:
            tr.renew_root(self.v1, [self.key["a"], self.p("sticks", "x", "root.key")], self.p("v2"))
        self.assertIn("not root keys", str(e.exception))
        self.assertFalse(os.path.exists(self.p("v2", "root.json")))

    def test_a_renewal_never_overwrites_and_can_be_chained(self):
        self.renew("ab")
        before = open(self.p("v2", "root.json"), "rb").read()
        with self.assertRaises(SystemExit):
            self.renew("ab")
        self.assertEqual(open(self.p("v2", "root.json"), "rb").read(), before)
        tr.renew_root(self.p("v2", "root.json"), [self.key["a"], self.key["c"]], self.p("v3"))
        self.assertEqual(self.md(self.p("v3", "root.json")).signed.version, 3)

    def test_a_current_root_without_valid_signatures_is_not_renewed(self):
        doc = json.load(open(self.v1))
        doc["signatures"] = doc["signatures"][:1]
        json.dump(doc, open(self.p("broken.json"), "w"))
        with self.assertRaises(SystemExit) as e:
            tr.renew_root(self.p("broken.json"), [self.key["a"], self.key["b"]], self.p("v2"))
        self.assertIn("not validly signed", str(e.exception))

    def test_the_tool_refuses_in_ci(self):
        r = subprocess.run([sys.executable, "-I", os.path.join(UPDATE, "tuf-repo.py"), "renew-root", "--current", self.v1,
                            "--root-key", self.key["a"], "--out", self.p("ci")],
                           env={**os.environ, "GITHUB_ACTIONS": "true", tr.PASSPHRASE_ENV: PASS}, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("never in CI", r.stderr)
        self.assertFalse(os.path.exists(self.p("ci")))

    # ---- the script, as the founder will run it
    def test_the_script_renews_and_prints_the_sheet(self):
        r = run_script("renew", self.v1, self.p("out"), self.key["b"], self.key["c"], ONEMIND_TUF_PASSPHRASE=PASS)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("a box holding v1 accepts it", r.stderr)
        self.assertIn("root      threshold 2", r.stdout)
        self.assertIn("expires", r.stdout)
        one = run_script("renew", self.v1, self.p("out1"), self.key["b"], ONEMIND_TUF_PASSPHRASE=PASS)
        self.assertNotEqual(one.returncode, 0)
        self.assertFalse(os.path.exists(self.p("out1", "root.json")))
        ci = run_script("renew", self.v1, self.p("out2"), self.key["a"], self.key["b"], CI="true", ONEMIND_TUF_PASSPHRASE=PASS)
        self.assertEqual(ci.returncode, 1)
        self.assertIn("never in CI", ci.stderr)

    def test_the_renewal_rehearsal_passes_on_throwaway_keys(self):
        r = run_script("rehearse-renewal", self.p("rehearsal"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("REHEARSAL PASSED: root v2 signed by B and C", r.stderr)
        self.assertIn("tuf verify: 3 target(s) checked, 0 problem(s)", r.stdout)
        self.assertEqual(tr.inspect_root(self.p("rehearsal", "renewed", "root.json"), 2, 3)[1], [])
        self.assertEqual(run_script("rehearse-renewal", self.p("rehearsal")).returncode, 2)   # never reuse a directory
        self.assertEqual(run_script("rehearse-renewal", self.p("ci-run"), CI="true").returncode, 1)

    def _channel(self):
        rel = self.p("rel")
        os.makedirs(rel)
        for n, c in (("onemind-vm-0.0.0.raucb", "x"), ("onemind-vm-0.0.0.spdx.json", "{}"), ("onemind-vm-0.0.0.cve-report.json", "{}")):
            open(os.path.join(rel, n), "w").write(c)
        json.dump({"board": "vm", "version": "0.0.0", "compatible": "onemind-vm", "snapshot": "20261115T000000Z",
                   "security": True, "dry_run": False,
                   "files": {"bundle": "onemind-vm-0.0.0.raucb", "sbom": "onemind-vm-0.0.0.spdx.json",
                             "cve_report": "onemind-vm-0.0.0.cve-report.json"}}, open(self.p("rel", "release-vm-0.0.0.json"), "w"))
        tr.build(self.p("chan"), self.v1, None, [self.p("rel", "release-vm-0.0.0.json")], self.p("online", "targets.key"),
                 self.p("online", "snapshot.key"), self.p("online", "timestamp.key"))


class Expiry(unittest.TestCase):
    """The nightly warns 60 days before the root expires (stdlib only: no python-tuf needed)."""

    def setUp(self):
        self.mod = load("root-expiry")
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)

    def root(self, expires, version=1):
        p = os.path.join(self.d, f"root{version}.json")
        json.dump({"signed": {"_type": "root", "version": version, "expires": expires}, "signatures": []}, open(p, "w"))
        return p

    def at(self, now, *paths, warn=60):
        with unittest.mock.patch.dict(os.environ, {"ONEMIND_TUF_NOW": now}):
            return self.mod.check(list(paths), warn)

    def test_quiet_until_60_days_before_expiry(self):
        r = self.root("2027-11-16T00:00:00Z")
        self.assertEqual(self.at("2026-11-16T00:00:00", r)[1], [])           # 365 days left
        self.assertEqual(self.at("2027-09-16T00:00:00", r)[1], [])           # 61 days left
        warn = self.at("2027-09-17T00:00:00", r)[1]                          # 60 days left: red
        self.assertEqual(len(warn), 1)
        self.assertIn("expires in 60 days", warn[0])
        self.assertIn("Renewing the root", warn[0])

    def test_an_expired_root_is_an_error_too(self):
        problems = self.at("2027-12-01T00:00:00", self.root("2027-11-16T00:00:00Z"))[1]
        self.assertIn("EXPIRED", problems[0])

    def test_the_exit_code_and_the_github_annotation(self):
        r = self.root("2027-11-16T00:00:00Z")
        env = {**os.environ, "ONEMIND_TUF_NOW": "2027-10-30T00:00:00"}
        out = subprocess.run([sys.executable, "-I", os.path.join(UPDATE, "root-expiry.py"), r], env=env, capture_output=True, text=True)
        self.assertEqual(out.returncode, 1)
        self.assertIn("::error::", out.stdout)
        env["ONEMIND_TUF_NOW"] = "2026-12-01T00:00:00"
        ok = subprocess.run([sys.executable, "-I", os.path.join(UPDATE, "root-expiry.py"), r], env=env, capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stdout)

    def test_no_committed_root_is_not_an_error(self):
        with unittest.mock.patch.object(self.mod, "ROOTS", os.path.join(self.d, "none", "*", "root.json")):
            self.assertEqual(self.mod.main(["--warn-days", "60"]), 0)

    def test_the_nightly_runs_it(self):
        wf = open(os.path.join(UPDATE, "..", "..", ".github", "workflows", "security-nightly.yml")).read()
        self.assertIn("root-expiry.py --warn-days 60", wf)


if __name__ == "__main__":
    unittest.main()
