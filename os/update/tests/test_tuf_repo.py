# SPDX-License-Identifier: Apache-2.0
"""os/update/tuf-repo.py: offline root, signed channel metadata, client-side verification, refresh.
Needs the pinned python-tuf (os/update/requirements-tuf.txt); skipped when it is not installed."""
import contextlib, io, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load  # noqa: E402

try:
    tr = load("tuf-repo")
except ImportError as e:          # pragma: no cover
    tr = None
    WHY = str(e)


def release(d, board, ver, payload=b"bundle", dry_run=False):
    b = f"onemind-{board}-{ver}"
    for ext, data in ((".raucb", payload), (".spdx.json", b"{}"), (".cve-report.json", b"{}")):
        open(os.path.join(d, b + ext), "wb").write(data)
    p = os.path.join(d, f"release-{board}-{ver}.json")
    json.dump({"board": board, "version": ver, "compatible": f"onemind-{board}", "snapshot": "20261112T025704Z",
               "security": True, "dry_run": dry_run, "files": {"bundle": b + ".raucb", "sbom": b + ".spdx.json",
                                           "cve_report": b + ".cve-report.json"}}, open(p, "w"))
    return p


@unittest.skipIf(tr is None, "python-tuf not installed (pip install --require-hashes -r os/update/requirements-tuf.txt)")
class Channel(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.k = os.path.join(self.d, "keys")
        tr.keygen(self.k, ["root", "root2", "targets", "snapshot", "timestamp", "rogue"])
        self.key = lambda r: os.path.join(self.k, r + ".key")
        self.pub = lambda r: os.path.join(self.k, r + ".pub")
        tr.init_root([self.key("root"), self.key("root2")], [], 2, self.pub("targets"), self.pub("snapshot"),
                     self.pub("timestamp"), os.path.join(self.d, "root"))
        self.root = os.path.join(self.d, "root", "root.json")
        self.rel = os.path.join(self.d, "rel")
        os.makedirs(self.rel)

    def build(self, repo, rels, prev=None, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return tr.build(os.path.join(self.d, repo), self.root, prev and os.path.join(self.d, prev), rels,
                            kw.get("tk", self.key("targets")), self.key("snapshot"), self.key("timestamp"), kw.get("keep"),
                            kw.get("allow_dry_run", False))

    def test_dry_run_release_needs_allow_flag(self):
        rel = release(self.rel, "vm", "0.1.1", dry_run=True)
        with self.assertRaises(SystemExit):
            self.build("repo", [rel])
        p = os.path.join(self.rel, "release-vm-0.1.1.json")
        r = json.load(open(p)); del r["dry_run"]; json.dump(r, open(p, "w"))     # missing field = dry run
        with self.assertRaises(SystemExit):
            self.build("repo", [p])
        self.assertEqual(self.build("repo", [p], allow_dry_run=True)["targets"], 1)

    def forge(self, repo, name, mutate, key="rogue"):
        """Rewrite one role file in repo, re-signed with `key` (rogue = not trusted by root)."""
        from tuf.api.metadata import Metadata
        p = os.path.join(self.d, repo, name)
        md = Metadata.from_file(p)
        mutate(md.signed)
        md.signatures.clear()
        md.sign(tr.load_signer(self.key(key)))
        md.to_file(p, tr.SER)

    def test_previous_metadata_must_verify(self):
        self.build("r1", [release(self.rel, "vm", "0.1.1")])
        evil = tr.TargetFile.from_data("vm/9.9.9/onemind-vm-9.9.9.raucb", b"evil", ["sha256"])
        self.forge("r1", "targets.json", lambda t: t.targets.__setitem__(evil.path, evil))
        with self.assertRaises(SystemExit):                       # planted targets.json is not re-signed
            self.build("r2", [release(self.rel, "vm", "0.1.2")], prev="r1")
        self.build("r3", [release(self.rel, "vm", "0.1.1")])
        os.remove(os.path.join(self.d, "r3", "timestamp.json"))
        with self.assertRaises(SystemExit):                       # partial previous channel
            self.build("r4", [release(self.rel, "vm", "0.1.2")], prev="r3")

    def test_refresh_refuses_forged_metadata(self):
        self.build("repo", [release(self.rel, "vm", "0.1.1")])
        repo = os.path.join(self.d, "repo")
        # targets.json swapped for one signed by the real targets key but not matching snapshot.json
        self.forge("repo", "targets.json", lambda t: setattr(t, "version", t.version + 5), key="targets")
        with self.assertRaises(SystemExit):
            tr.refresh(repo, self.key("timestamp"), self.key("snapshot"), self.key("targets"), force=True,
                       root_path=self.root)
        # a root.json planted next to the metadata is not trusted: the committed root is
        self.build("repo2", [release(self.rel, "vm", "0.1.1")])
        repo2 = os.path.join(self.d, "repo2")
        self.forge("repo2", "snapshot.json", lambda s: None)       # rogue-signed snapshot
        with self.assertRaises(SystemExit):
            tr.refresh(repo2, self.key("timestamp"), root_path=self.root)

    def test_root_threshold(self):
        r = json.load(open(self.root))
        self.assertEqual(r["signed"]["roles"]["root"]["threshold"], 2)
        self.assertEqual(len(r["signatures"]), 2)
        self.assertFalse(r["signed"]["consistent_snapshot"])
        self.assertTrue(os.path.exists(os.path.join(self.d, "root", "1.root.json")))
        with self.assertRaises(SystemExit):
            tr.init_root([self.key("root")], [], 2, self.pub("targets"), self.pub("snapshot"), self.pub("timestamp"),
                         os.path.join(self.d, "r2"))

    def test_build_verify_and_shape(self):
        res = self.build("repo", [release(self.rel, "vm", "0.1.20261112025704")])
        self.assertEqual((res["targets"], res["snapshot"], res["timestamp"]), (1, 1, 1))
        checked, problems = tr.verify(os.path.join(self.d, "repo"), self.root)
        self.assertEqual(problems, [])
        self.assertEqual(len(checked), 3)
        t = json.load(open(os.path.join(self.d, "repo", "targets.json")))["signed"]
        c = t["targets"]["vm/0.1.20261112025704/onemind-vm-0.1.20261112025704.raucb"]["custom"]
        self.assertEqual(sorted(c), sorted(tr.BUNDLE_FIELDS))
        self.assertEqual(c["compatible"], "onemind-vm")
        self.assertIs(c["security"], True)
        # expiry per CHANNEL.md: timestamp 1 d, snapshot 7 d, targets 30 d
        x = json.load(open(os.path.join(self.d, "repo", "timestamp.json")))["signed"]
        s = json.load(open(os.path.join(self.d, "repo", "snapshot.json")))["signed"]
        left = lambda m: (tr.datetime.datetime.fromisoformat(m["expires"].replace("Z", "+00:00")) - tr.now()).total_seconds()
        for m, d in ((x, 1), (s, 7), (t, 30)):
            self.assertAlmostEqual(left(m), d * 86400, delta=120)

    def test_tamper_detected(self):
        self.build("repo", [release(self.rel, "vm", "0.1.1")])
        with open(os.path.join(self.d, "repo", "onemind-vm-0.1.1.raucb"), "ab") as f:
            f.write(b"x")
        _, problems = tr.verify(os.path.join(self.d, "repo"), self.root)
        self.assertEqual(len(problems), 1)

    def test_untrusted_key_refused(self):
        with self.assertRaises(SystemExit):
            self.build("repo", [release(self.rel, "vm", "0.1.1")], tk=self.key("rogue"))

    def test_next_build_keeps_and_prunes(self):
        self.build("r1", [release(self.rel, "vm", "0.1.1")])
        self.build("r2", [release(self.rel, "vm", "0.1.2")], prev="r1")
        res = self.build("r3", [release(self.rel, "vm", "0.1.3"), release(self.rel, "vm-do", "0.1.3")], prev="r2", keep=2)
        self.assertEqual(res["targets"], 3)
        raucb = sorted(p for p in res["files"] if p.endswith(".raucb"))
        self.assertEqual(raucb, ["vm-do/0.1.3/onemind-vm-do-0.1.3.raucb", "vm/0.1.2/onemind-vm-0.1.2.raucb",
                                 "vm/0.1.3/onemind-vm-0.1.3.raucb"])
        checked, problems = tr.verify(os.path.join(self.d, "r3"), self.root, allow_absent=True)
        self.assertEqual(problems, [])
        with self.assertRaises(SystemExit):                       # anti-rollback: not older than listed
            self.build("r4", [release(self.rel, "vm", "0.1.2")], prev="r3")

    def test_refresh_timestamp_then_snapshot(self):
        self.build("repo", [release(self.rel, "vm", "0.1.1")])
        repo = os.path.join(self.d, "repo")
        self.assertEqual(tr.refresh(repo, self.key("timestamp")), ["timestamp"])
        os.environ["ONEMIND_TUF_NOW"] = (tr.now() + tr.datetime.timedelta(days=5)).isoformat()
        try:
            done = tr.refresh(repo, self.key("timestamp"), self.key("snapshot"), self.key("targets"),
                              root_path=self.root)
            self.assertEqual(done, ["snapshot", "timestamp"])
            _, problems = tr.verify(repo, self.root)
            self.assertEqual(problems, [])
        finally:
            del os.environ["ONEMIND_TUF_NOW"]
        x = json.load(open(os.path.join(repo, "timestamp.json")))["signed"]
        self.assertEqual(x["version"], 3)


if __name__ == "__main__":
    unittest.main()
