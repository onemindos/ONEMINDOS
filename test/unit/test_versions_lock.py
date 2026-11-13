# SPDX-License-Identifier: Apache-2.0
"""Brief 30 rule 2: every pin used by the build files equals os/versions.lock.yaml."""
import os, re, unittest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOCK = yaml.safe_load(open(os.path.join(ROOT, "os", "versions.lock.yaml")))
read = lambda p: open(os.path.join(ROOT, p)).read()


class Pins(unittest.TestCase):
    def test_base_digests(self):
        for leg in ("debian", "ubuntu"):
            b = LOCK["base"][leg]
            self.assertIn(f"{b['image']}@{b['digest']}", read(f"os/rootfs/{leg}.args"))
        self.assertIn(f"SNAPSHOT={LOCK['base']['debian']['snapshot']}", read("os/rootfs/debian.args"))
        self.assertIn(LOCK["base"]["debian"]["digest"], read("os/rootfs/Containerfile"))

    def test_rauc_commit(self):
        s = read("os/rauc/build-rauc.sh")
        self.assertIn(f"COMMIT={LOCK['rauc']['commit']}", s)
        self.assertIn(f"TAG={LOCK['rauc']['tag']}", s)

    def test_k3s_hashes(self):
        s = read("os/rootfs/fetch-k3s.sh")
        for arch in ("amd64", "arm64"):
            for sha in LOCK["k3s"][arch].values():
                self.assertIn(sha, s)
        self.assertIn(LOCK["k3s"]["version"].replace("+", "%2B"), s)

    def test_actions_pinned_by_commit(self):
        wf = os.path.join(ROOT, ".github", "workflows")
        pins = LOCK["tools"]["github_actions"]
        for f in os.listdir(wf):
            for action, ref in re.findall(r"uses:\s*([\w./-]+)@(\S+)", read(f".github/workflows/{f}")):
                if action.startswith("./"):
                    continue
                self.assertEqual(ref, pins[action], f"{f}: {action}@{ref}")

    def test_onemind_layer_pins(self):
        s = read("os/rootfs/fetch-onemind.sh")
        L = LOCK["onemind_layer"]
        for tool in ("go", "node", "uv"):
            self.assertIn(f"{tool.upper()}_VERSION={L[tool]['version']}", s)
            for arch in ("amd64", "arm64"):
                self.assertIn(L[tool][arch], s, f"{tool} {arch}")
        n = L["nats_server"]
        self.assertIn(f"NATS_VERSION={n['version']}", s)
        for arch in ("amd64", "arm64"):
            self.assertIn(n[arch]["tarball"], s)
            self.assertIn(n[arch]["binary"], s)

    def test_gitleaks_pin(self):
        g = LOCK["tools"]["gitleaks"]
        s = read(".github/workflows/hygiene.yml")
        self.assertIn(g["sha256"], s)
        self.assertIn(g["version"], s)


if __name__ == "__main__":
    unittest.main()
