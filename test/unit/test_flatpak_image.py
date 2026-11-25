# SPDX-License-Identifier: Apache-2.0
"""Flathub desktop apps (issue #1097, D-007, D-026): how the image and the streaming runtime carry Flatpak.

The host calls and the sandbox are tested in Go (internal/flatpak, internal/host) and the approvals in core. This pins
the places that must live on /data (the root is read-only, and an A/B update replaces it), the package in both image
legs, and the one script that runs an app in the streamed session, against a stub flatpak.
"""
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LAYER = os.path.join(ROOT, "os", "rootfs", "layers", "onemind")
BASE = os.path.join(ROOT, "apps", "_bases", "desktop")


def read(*p):
    with open(os.path.join(ROOT, *p)) as f:
        return f.read()


class FlatpakImage(unittest.TestCase):
    def test_flatpak_is_in_both_image_legs(self):
        for leg in ("debian", "ubuntu"):
            pkgs = re.sub(r"#.*", "", read("os", "rootfs", "packages", f"{leg}-common.txt")).split()
            self.assertIn("flatpak", pkgs, leg)

    def test_the_installation_and_every_folder_live_on_data(self):
        conf = read("os", "rootfs", "layers", "onemind", "etc", "flatpak", "installations.d", "onemind.conf")
        self.assertIn('[Installation "onemind"]', conf)
        self.assertIn("Path=/data/onemind/flatpak", conf)
        tmp = read("os", "rootfs", "layers", "onemind", "usr", "lib", "tmpfiles.d", "onemind-flatpak.conf")
        for d in ("/data/onemind/flatpak", "/data/onemind/desktop-apps", "/data/onemind/desktop-session"):
            self.assertRegex(tmp, r"(?m)^d %s " % re.escape(d))

    def test_the_go_side_uses_the_same_installation_and_folders(self):
        go = read("internal", "flatpak", "flatpak.go")
        self.assertIn('Installation = "onemind"', go)
        for d in ("/data/onemind/flatpak", "/data/onemind/desktop-apps", "/data/onemind/desktop-session"):
            self.assertIn(d, go)

    def test_the_host_unit_can_write_data_and_the_base_keeps_the_session_off_until_asked(self):
        self.assertIn("ReadWritePaths=/data", read("os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system", "onemind-host.service"))
        dockerfile = read("apps", "_bases", "desktop", "Dockerfile")
        self.assertRegex(dockerfile, r"install -y --no-install-recommends flatpak")
        self.assertIn("flatpak-session.conf.disabled", dockerfile)  # the base alone starts nothing extra


@unittest.skipUnless(shutil.which("sh"), "needs sh")
class SessionScript(unittest.TestCase):
    SCRIPT = os.path.join(BASE, "onemind-desktop-session")

    def run_script(self, content):
        with tempfile.TemporaryDirectory() as d:
            launch, log = os.path.join(d, "launch"), os.path.join(d, "ran")
            if content is not None:
                with open(launch, "w") as f:
                    f.write(content)
            stub = os.path.join(d, "flatpak")
            with open(stub, "w") as f:
                f.write('#!/bin/sh\necho "$@" >> "%s"\n' % log)
            os.chmod(stub, os.stat(stub).st_mode | stat.S_IXUSR)
            env = {**os.environ, "PATH": d + os.pathsep + os.environ["PATH"], "ONEMIND_LAUNCH_FILE": launch,
                   "ONEMIND_SESSION_ONCE": "1", "TMPDIR": d}
            if content in (None, "", "--user\n", "a b.c.D\n", "x;rm -rf.y.z\n"):
                # nothing valid to run: the script would wait for a launch; stop it after a moment
                p = subprocess.Popen(["sh", self.SCRIPT], env=env)
                try:
                    p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()
            else:
                subprocess.run(["sh", self.SCRIPT], env=env, check=True, timeout=30)
            if not os.path.exists(log):
                return ""
            with open(log) as f:
                return f.read()

    def test_runs_the_app_in_the_launch_file_from_the_box_installation(self):
        self.assertEqual(self.run_script("md.obsidian.Obsidian\n"), "run --installation=onemind md.obsidian.Obsidian\n")

    def test_runs_nothing_that_is_not_an_application_id(self):
        for bad in (None, "", "--user\n", "a b.c.D\n", "x;rm -rf.y.z\n"):
            self.assertEqual(self.run_script(bad), "", repr(bad))

    def test_the_script_is_executable_and_shell_clean(self):
        self.assertTrue(os.stat(self.SCRIPT).st_mode & stat.S_IXUSR)
        if shutil.which("shellcheck"):
            subprocess.run(["shellcheck", self.SCRIPT], check=True)


if __name__ == "__main__":
    unittest.main()
