# SPDX-License-Identifier: Apache-2.0
"""Lab finding: on an image-built hub the files roots route answered 503 storage_unavailable and storage
actions were off. The gateway's sandbox only let it write /data/onemind/gateway, ONEMIND_FILES_ROOT was never
set, and nothing ran `onemindd storage serve`. This pins the image wiring that fixes it."""
import os, re, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib")
sys.path.insert(0, os.path.join(LIB, "onemind"))
import onemind_firstboot as fb  # noqa: E402


def unit(name):
    return open(os.path.join(LIB, "systemd", "system", name)).read()


class FilesAndStorageOnTheImage(unittest.TestCase):
    def test_gateway_env_points_files_at_the_data_partition_and_turns_storage_on(self):
        with tempfile.TemporaryDirectory() as d:
            env = fb.gateway_env(fb.Paths(d), {"box": "home-box", "node_id": "abc", "name": "Home"})
        self.assertIn("ONEMIND_FILES_ROOT=/data/onemind/files\n", env)
        self.assertIn("ONEMIND_STORAGE_ENABLED=1\n", env)

    def test_gateway_may_write_the_files_root_and_it_exists_before_the_sandbox(self):
        gw = unit("onemind-gateway.service")
        self.assertRegex(gw, r"(?m)^ReadWritePaths=.*/data/onemind/files\b")
        self.assertRegex(gw, r"(?m)^ExecStartPre=\+.*install -d .*-o onemind .*/data/onemind/files$")
        self.assertLess(gw.index("ExecStartPre="), gw.index("ExecStart=/usr"))

    def test_storage_service_runs_on_the_hub_only_and_is_not_enabled_at_build(self):
        self.assertIn("onemind-storage.service", fb.ROLE_UNITS["hub"])
        for role in ("worker", "leaf"):
            self.assertNotIn("onemind-storage.service", fb.ROLE_UNITS[role])
        cf = open(os.path.join(ROOT, "os", "rootfs", "Containerfile")).read()
        for line in re.findall(r"systemctl enable [^;]*", cf):
            self.assertNotIn("onemind-storage", line)

    def test_storage_service_command_matches_the_gateway_socket(self):
        u = unit("onemind-storage.service")
        self.assertIn("ExecStart=/usr/bin/onemindd storage serve --group onemind", u)
        self.assertIn("RequiresMountsFor=/data", u)
        self.assertIn("ConditionPathExists=/data/onemind/firstboot/state.json", u)
        # the gateway default socket (core/onemind_core/storage.py) is the service default (cmd/onemindd/storage.go)
        self.assertIn("/run/onemind/storage.sock", open(os.path.join(ROOT, "core", "onemind_core", "storage.py")).read())
        self.assertIn("/run/onemind/storage.sock", open(os.path.join(ROOT, "cmd", "onemindd", "storage.go")).read())


if __name__ == "__main__":
    unittest.main()
