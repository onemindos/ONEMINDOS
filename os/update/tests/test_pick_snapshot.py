# SPDX-License-Identifier: Apache-2.0
"""os/update/pick-snapshot.py: timestamp choice, fix coverage per arch, and the generated change."""
import json, lzma, os, shutil, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load, UPDATE  # noqa: E402

ps = load("pick-snapshot")
REPO = os.path.dirname(os.path.dirname(UPDATE))

OLD, NEW = "20261111T000000Z", "20261112T025704Z"
PKGS = {   # (timestamp, suite) -> Packages paragraphs (same for both arches here)
    (OLD, "trixie"): "Package: zlib1g\nSource: zlib (1:1.3.dfsg+really1.3.1-1)\nVersion: 1:1.3.dfsg+really1.3.1-1+b1\n\n"
                     "Package: libc6\nSource: glibc\nVersion: 2.41-12+deb13u4\n",
    (OLD, "trixie-security"): "Package: zlib1g\nSource: zlib\nVersion: 1:1.3.dfsg+really1.3.1-1+deb13u1\n",
    (NEW, "trixie"): "Package: libc6\nSource: glibc\nVersion: 2.41-12+deb13u5\n",
    (NEW, "trixie-security"): "Package: zlib1g\nSource: zlib\nVersion: 1:1.3.dfsg+really1.3.1-1+deb13u1\n\n"
                              "Package: openssl\nVersion: 3.5.7-1~deb13u3\n",
}


def fake_fetch(url):
    if url.endswith("/mr/timestamp/"):
        return json.dumps({"result": {"debian": ["20261101T000000Z", NEW], "debian-security": ["20261112T010000Z"]}}).encode()
    for (ts, suite), text in PKGS.items():
        if f"/{ts}/dists/{suite}/main/" in url:
            return lzma.compress(text.encode())
    raise OSError("404 " + url)


def report(*fixes):
    return {"fixes": [{"source": s, "fixed_version": v, "available": a} for s, v, a in fixes]}


class Pick(unittest.TestCase):
    def test_latest_timestamp(self):
        self.assertEqual(ps.latest_timestamp(json.loads(fake_fetch("x/mr/timestamp/"))), NEW)

    def test_source_versions(self):
        sv = ps.source_versions(PKGS[(OLD, "trixie")])
        self.assertEqual(sv, {"zlib": "1:1.3.dfsg+really1.3.1-1", "glibc": "2.41-12+deb13u4"})

    def test_pick_new_fix_and_stale_base_package(self):
        r = ps.pick([report(("glibc", "2.41-12+deb13u5", True), ("zlib", "1:1.3.dfsg+really1.3.1-1+deb13u1", True),
                            ("nginx", "9", False))],
                    current=OLD, archs=["amd64", "arm64"], fetch=fake_fetch)
        self.assertEqual(r["snapshot"], NEW)
        self.assertEqual([c["source"] for c in r["covered"]], ["glibc", "zlib"])
        self.assertEqual(r["missing"], [])
        self.assertEqual(r["not_picked_by_build"], ["zlib"])   # was already in OLD: the build never upgraded it
        self.assertEqual(r["new_fixes"], ["glibc"])
        self.assertTrue(r["rebuild_useful"])
        self.assertNotIn("nginx", r["needed"])                  # not in the archive: nothing to pick

    def test_missing_fix_and_never_go_backwards(self):
        r = ps.pick([report(("openssl", "3.5.8-1", True))], current=NEW, archs=["amd64"],
                    override="20261101T000000Z", fetch=fake_fetch)
        self.assertEqual(r["snapshot"], NEW)                     # older override clamps to the current one
        self.assertEqual([m["source"] for m in r["missing"]], ["openssl"])
        self.assertFalse(r["rebuild_useful"])

    def test_apply_and_version(self):
        with tempfile.TemporaryDirectory() as d:
            for f in ("os/rootfs/debian.args", "os/versions.lock.yaml", "os/update/channel.json"):
                os.makedirs(os.path.join(d, os.path.dirname(f)), exist_ok=True)
                shutil.copyfile(os.path.join(REPO, f), os.path.join(d, f))
            self.assertTrue(ps.apply(NEW, d))
            self.assertFalse(ps.apply(NEW, d))
            self.assertIn(f"SNAPSHOT={NEW}\n", open(os.path.join(d, "os/rootfs/debian.args")).read())
            lock = open(os.path.join(d, "os/versions.lock.yaml")).read()
            self.assertIn(f'snapshot: "{NEW}"', lock)
            self.assertIn("snapshot: none", lock)                # the ubuntu entry is untouched
            self.assertEqual(ps.release_version(d), "0.1.20261112025704")
            with self.assertRaises(ValueError):
                ps.apply("latest", d)


if __name__ == "__main__":
    unittest.main()
