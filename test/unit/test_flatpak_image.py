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


class HostUnitCapabilities(unittest.TestCase):
    """The host service has no CAP_CHOWN and filters @privileged calls (which include chown), so the flatpak Manager,
    which runs inside it, must not chown or take a capability: that work goes to a systemd-run unit that has it."""

    UNIT = read("os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system", "onemind-host.service")

    def test_the_unit_still_lacks_chown_and_filters_privileged_calls(self):
        caps = re.search(r"(?m)^CapabilityBoundingSet=(.*)$", self.UNIT).group(1).split()
        self.assertNotIn("CAP_CHOWN", caps)
        self.assertIn("SystemCallFilter=~@privileged", self.UNIT)

    def test_the_manager_does_nothing_in_process_that_needs_what_the_unit_lacks(self):
        go = re.sub(r"//.*", "", read("internal", "flatpak", "flatpak.go"))
        needs = {"CAP_CHOWN": r"\b(os\.)?L?[Cc]hown\(|syscall\.(Fchown|Lchown|Chown)",
                 "CAP_SYS_ADMIN": r"syscall\.(Mount|Unshare)|unix\.(Mount|Unshare)",
                 "CAP_NET_ADMIN": r"netlink"}
        for cap, pattern in needs.items():
            if cap not in self.UNIT.split("CapabilityBoundingSet=")[1].split("\n")[0]:
                self.assertIsNone(re.search(pattern, go), f"flatpak.go needs {cap}, which onemind-host.service lacks")

    def test_the_folder_and_flatpak_steps_run_in_systemd_run_units(self):
        go = read("internal", "flatpak", "flatpak.go")
        self.assertIn("CapabilityBoundingSet=CAP_CHOWN", go)
        self.assertIn("/usr/bin/systemd-run", go)
        self.assertIn("systemd-run", self.UNIT)  # the header says so

    def test_the_unit_can_still_write_data(self):
        self.assertIn("ReadWritePaths=/data", self.UNIT)


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

    def test_flatpak_user_overrides_cannot_exist(self):
        # The stub writes the environment it was started with; the script must point FLATPAK_USER_DIR at the empty
        # read-only directory, not at a folder the session user can write.
        with tempfile.TemporaryDirectory() as d:
            launch, env_log = os.path.join(d, "launch"), os.path.join(d, "env")
            with open(launch, "w") as f:
                f.write("md.obsidian.Obsidian\n")
            stub = os.path.join(d, "flatpak")
            with open(stub, "w") as f:
                f.write('#!/bin/sh\necho "$FLATPAK_USER_DIR" > "%s"\n' % env_log)
            os.chmod(stub, 0o755)
            env = {**os.environ, "PATH": d + os.pathsep + os.environ["PATH"], "ONEMIND_LAUNCH_FILE": launch,
                   "ONEMIND_SESSION_ONCE": "1", "TMPDIR": d}
            env.pop("ONEMIND_FLATPAK_USER_DIR", None)
            subprocess.run(["sh", self.SCRIPT], env=env, check=True, timeout=30)
            with open(env_log) as f:
                self.assertEqual(f.read().strip(), "/usr/share/onemind-flatpak-user")
        dockerfile = read("apps", "_bases", "desktop", "Dockerfile")
        self.assertRegex(dockerfile, r"install -d -o root -g root -m 0555 /usr/share/onemind-flatpak-user")

    def test_the_script_avoids_the_non_posix_newer_than_test(self):
        with open(self.SCRIPT) as f:
            self.assertNotIn(" -nt ", f.read())  # SC3013: not POSIX, flagged by the CI runner's shellcheck

    def test_the_pod_has_the_installation_the_box_writes(self):
        base = read("apps", "_bases", "desktop", "onemind-installation.conf")
        box = read("os", "rootfs", "layers", "onemind", "etc", "flatpak", "installations.d", "onemind.conf")
        for conf in (base, box):
            self.assertIn('[Installation "onemind"]', conf)
            self.assertIn("Path=/data/onemind/flatpak", conf)
        self.assertIn("/etc/flatpak/installations.d/onemind.conf", read("apps", "_bases", "desktop", "Dockerfile"))

    def test_the_script_is_executable_and_shell_clean(self):
        self.assertTrue(os.stat(self.SCRIPT).st_mode & stat.S_IXUSR)
        if shutil.which("shellcheck"):
            subprocess.run(["shellcheck", self.SCRIPT], check=True)


if __name__ == "__main__":
    unittest.main()
