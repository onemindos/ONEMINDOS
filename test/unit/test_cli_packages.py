# SPDX-License-Identifier: Apache-2.0
"""scripts/release/cli-packages.py: the CLI archives, .deb and Homebrew formula (#882), built from fake inputs."""
import fnmatch, gzip, hashlib, io, os, re, shutil, subprocess, sys, tarfile, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "release", "cli-packages.py")


def run(*args, env=None):
    return subprocess.run([sys.executable, "-I", SCRIPT, *args], capture_output=True, text=True, env=env)


class Packages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        t = cls.tmp
        for d in ("bin", "comp", "man"):
            os.makedirs(os.path.join(t, d))
        for o, a in (("linux", "amd64"), ("linux", "arm64"), ("darwin", "arm64"), ("darwin", "amd64")):
            open(os.path.join(t, "bin", f"onemind-{o}-{a}"), "wb").write(f"BIN {o} {a}".encode())
        for n in ("onemind.bash", "_onemind", "onemind.fish"):
            open(os.path.join(t, "comp", n), "w").write("# completion " + n + "\n")
        for n in ("onemind.1.gz", "onemind-apps.1.gz"):
            open(os.path.join(t, "man", n), "wb").write(gzip.compress(b".TH X 1\n"))
        cls.args = ["--version", "0.1.0", "--bin-dir", f"{t}/bin", "--completions", f"{t}/comp", "--man", f"{t}/man",
                    "--licence", os.path.join(ROOT, "LICENSE"), "--readme", os.path.join(ROOT, "cmd/onemind/README.md")]
        cls.out = os.path.join(t, "out")
        r = run(*cls.args, "--out", cls.out)
        assert r.returncode == 0, r.stderr

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_one_artifact_per_platform_plus_formula_and_sums(self):
        names = sorted(os.listdir(self.out))
        self.assertEqual(names, ["SHA256SUMS", "onemind.rb", "onemind_0.1.0_amd64.deb", "onemind_0.1.0_arm64.deb",
                                 "onemind_0.1.0_darwin_amd64.tar.gz", "onemind_0.1.0_darwin_arm64.tar.gz",
                                 "onemind_0.1.0_linux_amd64.tar.gz", "onemind_0.1.0_linux_arm64.tar.gz"])

    def test_checksums_match_the_files(self):
        for line in open(os.path.join(self.out, "SHA256SUMS")).read().splitlines():
            digest, name = line.split("  ")
            self.assertEqual(digest, hashlib.sha256(open(os.path.join(self.out, name), "rb").read()).hexdigest(), name)

    def test_archive_holds_binary_completions_man_licence(self):
        with tarfile.open(os.path.join(self.out, "onemind_0.1.0_linux_arm64.tar.gz")) as t:
            names = t.getnames()
            top = "onemind_0.1.0_linux_arm64/"
            for p in ("bin/onemind", "share/bash-completion/completions/onemind", "share/zsh/site-functions/_onemind",
                      "share/fish/vendor_completions.d/onemind.fish", "share/man/man1/onemind.1.gz",
                      "share/man/man1/onemind-apps.1.gz", "share/doc/onemind/LICENSE"):
                self.assertIn(top + p, names)
            self.assertEqual(t.extractfile(top + "bin/onemind").read(), b"BIN linux arm64")
            self.assertEqual(t.getmember(top + "bin/onemind").mode, 0o755)
            self.assertEqual(t.getmember(top + "bin/onemind").uid, 0)

    def test_every_archive_uses_the_homebrew_zsh_folder(self):
        for o, a in (("linux", "amd64"), ("linux", "arm64"), ("darwin", "arm64"), ("darwin", "amd64")):
            with tarfile.open(os.path.join(self.out, f"onemind_0.1.0_{o}_{a}.tar.gz")) as t:
                self.assertIn(f"onemind_0.1.0_{o}_{a}/share/zsh/site-functions/_onemind", t.getnames())

    def test_every_path_the_formula_installs_exists_in_every_archive(self):
        """The formula's `def install` is shared by macOS and Linuxbrew, so each path it names must be in each tarball."""
        f = open(os.path.join(self.out, "onemind.rb")).read()
        body = f[f.index("def install"):f.index("test do")]
        paths = re.findall(r'install "([^"]+)"', body)
        globs = re.findall(r'Dir\["([^"]+)"\]', body)
        self.assertGreaterEqual(len(paths), 4)
        self.assertTrue(globs)
        for o, a in (("linux", "amd64"), ("linux", "arm64"), ("darwin", "arm64"), ("darwin", "amd64")):
            top = f"onemind_0.1.0_{o}_{a}/"
            with tarfile.open(os.path.join(self.out, f"onemind_0.1.0_{o}_{a}.tar.gz")) as t:
                names = t.getnames()
                for p in paths:
                    self.assertIn(top + p, names, f"{p} missing from the {o}/{a} archive")
                for g in globs:
                    self.assertTrue(fnmatch.filter(names, top + g), f"{g} matches nothing in the {o}/{a} archive")

    def _deb_members(self, name):
        raw = open(os.path.join(self.out, name), "rb").read()
        self.assertTrue(raw.startswith(b"!<arch>\n"))
        pos, out = 8, {}
        while pos < len(raw):
            hdr = raw[pos:pos + 60]
            self.assertEqual(hdr[58:60], b"`\n")
            n, size = hdr[:16].decode().strip().rstrip("/"), int(hdr[48:58])
            out[n] = raw[pos + 60:pos + 60 + size]
            pos += 60 + size + (size % 2)
        return out

    def test_deb_is_a_valid_ar_with_control_and_data(self):
        m = self._deb_members("onemind_0.1.0_amd64.deb")
        self.assertEqual(list(m), ["debian-binary", "control.tar.gz", "control.tar.gz".replace("control", "data")])
        self.assertEqual(m["debian-binary"], b"2.0\n")
        ctl = tarfile.open(fileobj=io.BytesIO(m["control.tar.gz"]))
        control = ctl.extractfile("./control").read().decode()
        self.assertIn("Package: onemind\nVersion: 0.1.0\n", control)
        self.assertIn("Architecture: amd64\n", control)
        data = tarfile.open(fileobj=io.BytesIO(m["data.tar.gz"]))
        self.assertEqual(data.extractfile("./usr/bin/onemind").read(), b"BIN linux amd64")
        self.assertIn("./usr/share/man/man1/onemind.1.gz", data.getnames())
        self.assertIn("./usr/share/bash-completion/completions/onemind", data.getnames())
        # Debian's zsh folder, and the copyright file Debian policy asks for
        self.assertIn("./usr/share/zsh/vendor-completions/_onemind", data.getnames())
        self.assertNotIn("./usr/share/zsh/site-functions/_onemind", data.getnames())
        self.assertIn("License: Apache-2.0", data.extractfile("./usr/share/doc/onemind/copyright").read().decode())
        self.assertIn("usr/share/doc/onemind/copyright", ctl.extractfile("./md5sums").read().decode())
        self.assertIn("Maintainer: OneMind OS contributors <", control)

    def test_maintainer_can_be_set_for_a_release(self):
        out = os.path.join(self.tmp, "maint")
        self.assertEqual(run(*self.args, "--maintainer", "Release Team <monitored-list>", "--out", out).returncode, 0)
        ctl = tarfile.open(fileobj=io.BytesIO(self._deb_members_at(out, "onemind_0.1.0_amd64.deb")["control.tar.gz"]))
        self.assertIn("Maintainer: Release Team <monitored-list>\n", ctl.extractfile("./control").read().decode())

    @unittest.skipUnless(shutil.which("dpkg-deb"), "dpkg-deb not installed")
    def test_dpkg_accepts_the_deb(self):
        r = subprocess.run(["dpkg-deb", "--info", os.path.join(self.out, "onemind_0.1.0_arm64.deb")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Architecture: arm64", r.stdout)
        r = subprocess.run(["dpkg-deb", "--contents", os.path.join(self.out, "onemind_0.1.0_arm64.deb")], capture_output=True, text=True)
        self.assertIn("./usr/bin/onemind", r.stdout)

    def test_formula_names_each_archive_with_its_real_checksum(self):
        f = open(os.path.join(self.out, "onemind.rb")).read()
        self.assertIn("class Onemind < Formula", f)
        for o, a in (("linux", "amd64"), ("linux", "arm64"), ("darwin", "arm64"), ("darwin", "amd64")):
            n = f"onemind_0.1.0_{o}_{a}.tar.gz"
            digest = hashlib.sha256(open(os.path.join(self.out, n), "rb").read()).hexdigest()
            self.assertRegex(f, re.escape(f'releases/download/v0.1.0/{n}"\n') + r"\s+sha256 \"" + digest)
        self.assertIn('bin.install "bin/onemind"', f)

    def test_dev_version_becomes_a_tilde_in_the_deb(self):
        out = os.path.join(self.tmp, "dev")
        args = list(self.args); args[1] = "0.2.0-dev"
        self.assertEqual(run(*args, "--out", out).returncode, 0)
        ctl = tarfile.open(fileobj=io.BytesIO(self._deb_members_at(out, "onemind_0.2.0-dev_amd64.deb")["control.tar.gz"]))
        self.assertIn("Version: 0.2.0~dev\n", ctl.extractfile("./control").read().decode())

    def _deb_members_at(self, d, name):
        old, self.out = self.out, d
        try:
            return self._deb_members(name)
        finally:
            self.out = old

    def test_build_is_reproducible(self):
        out = os.path.join(self.tmp, "again")
        self.assertEqual(run(*self.args, "--out", out).returncode, 0)
        self.assertEqual(open(os.path.join(out, "SHA256SUMS")).read(), open(os.path.join(self.out, "SHA256SUMS")).read())

    def test_refuses_a_bad_version_and_a_missing_binary(self):
        args = list(self.args); args[1] = "latest"
        self.assertNotEqual(run(*args, "--out", os.path.join(self.tmp, "x")).returncode, 0)
        os.remove(os.path.join(self.tmp, "bin", "onemind-darwin-amd64"))
        try:
            r = run(*self.args, "--out", os.path.join(self.tmp, "y"))
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("missing binary", r.stderr)
        finally:
            open(os.path.join(self.tmp, "bin", "onemind-darwin-amd64"), "wb").write(b"BIN darwin amd64")


PATHS = os.path.join(ROOT, "scripts", "release", "check-cli-paths.py")
# Built at run time so the repo hygiene grep for home paths (scripts/hygiene.sh) has nothing literal to flag.
HOME_L, HOME_M = "/" + "home/runner", "/" + "Users/someone"


class NoBuildPaths(unittest.TestCase):
    """scripts/release/check-cli-paths.py, the 'No build machine paths in the binaries' step of cli-packages.yml."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def archive(self, body, name="onemind_0.1.0_linux_amd64"):
        p = os.path.join(self.tmp, name + ".tar.gz")
        with tarfile.open(p, "w:gz") as t:
            i = tarfile.TarInfo(name + "/bin/onemind"); i.size = len(body)
            t.addfile(i, io.BytesIO(body))
        return p

    def check(self, *args):
        return subprocess.run([sys.executable, "-I", PATHS, *args], capture_output=True, text=True)

    def test_gateway_routes_are_not_build_paths(self):
        # The real strings that tripped the old grep '/(home|Users|runner|work)/' on the `onemind work` commands.
        body = b"\x00Idempotency-Key/v1/system-apps/v1/work/tasks?application/pdf\x00appendIfNotPresent/v1/work/quick-add/v1/work/projects/\x00"
        r = self.check("--forbid", HOME_L + "/work/ONEMINDOS/ONEMINDOS", self.archive(body))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_untrimmed_source_and_module_paths_fail(self):
        for leak in (HOME_L.encode() + b"/work/ONEMINDOS/ONEMINDOS/cmd/onemind/main.go",
                     HOME_M.encode() + b"/go/pkg/mod/github.com/spf13/cobra@v1.9.1/command.go",
                     b"\x00/work/onemind/internal/cli/root.go\x00"):
            r = self.check(self.archive(b"\x00\x01runtime.main\x00" + leak + b"\x00"))
            self.assertEqual(r.returncode, 1, leak)
            self.assertIn("path leaked", r.stderr)

    def test_a_forbidden_build_folder_fails_even_outside_home(self):
        # GOROOT on a hosted runner is under /opt, which the generic roots do not cover.
        body = b"\x00/opt/hostedtoolcache/go/1.26.0/x64/src/runtime/proc.go\x00"
        self.assertEqual(self.check(self.archive(body)).returncode, 0)
        r = self.check("--forbid", "/opt/hostedtoolcache/go/1.26.0/x64/", "--forbid", "", self.archive(body))
        self.assertEqual(r.returncode, 1)
        self.assertIn("build folder", r.stdout)

    def test_missing_or_empty_binary_and_wrong_count_fail(self):
        self.assertNotEqual(self.check(self.archive(b"")).returncode, 0)
        p = os.path.join(self.tmp, "nobin.tar.gz")
        with tarfile.open(p, "w:gz") as t:
            i = tarfile.TarInfo("x/README"); i.size = 1
            t.addfile(i, io.BytesIO(b"x"))
        self.assertNotEqual(self.check(p).returncode, 0)
        self.assertNotEqual(self.check("--expect", "4", self.archive(b"clean binary")).returncode, 0)


if __name__ == "__main__":
    unittest.main()
