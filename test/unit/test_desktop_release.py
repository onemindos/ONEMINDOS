# SPDX-License-Identifier: Apache-2.0
"""CLIENT-12: the desktop release workflow builds every platform, pins actions, and signs only with secrets."""
import json, os, re, unittest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WF_PATH = os.path.join(ROOT, ".github", "workflows", "desktop-release.yml")
TEXT = open(WF_PATH).read()
WF = yaml.safe_load(TEXT)
TRIGGERS = WF.get("on", WF.get(True))
SECRETS = ["APPLE_CERTIFICATE", "APPLE_CERTIFICATE_PASSWORD", "APPLE_ID", "APPLE_TEAM_ID",
           "APPLE_APP_SPECIFIC_PASSWORD", "WINDOWS_CERTIFICATE", "WINDOWS_CERTIFICATE_PASSWORD"]


class DesktopRelease(unittest.TestCase):
    def test_never_runs_on_a_pull_request(self):
        self.assertFalse({"pull_request", "pull_request_target"} & set(TRIGGERS))
        self.assertEqual(set(TRIGGERS), {"push", "workflow_run", "workflow_dispatch"})
        self.assertEqual(TRIGGERS["workflow_run"]["workflows"], ["dev-build", "release"])

    def test_every_action_is_pinned_by_sha(self):
        uses = re.findall(r"uses:\s*(\S+)", TEXT)
        self.assertTrue(uses)
        for u in uses:
            self.assertRegex(u, r"@[0-9a-f]{40}$", u)

    def test_matrix_covers_three_platforms_and_the_bundles(self):
        inc = {m["platform"]: m for m in WF["jobs"]["build"]["strategy"]["matrix"]["include"]}
        self.assertEqual(set(inc), {"macos", "windows", "linux"})
        self.assertEqual(inc["macos"]["target"], "universal-apple-darwin")
        self.assertIn("dmg", inc["macos"]["bundles"])
        self.assertEqual(set(inc["windows"]["bundles"].split(",")), {"nsis", "msi"})
        self.assertEqual(set(inc["linux"]["bundles"].split(",")), {"appimage", "deb"})

    def test_tauri_config_lists_every_bundle(self):
        conf = json.load(open(os.path.join(ROOT, "desktop", "src-tauri", "tauri.conf.json")))
        self.assertTrue({"dmg", "nsis", "msi", "deb", "appimage"} <= set(conf["bundle"]["targets"]))

    def test_secrets_only_reach_gated_steps_and_never_a_command_line(self):
        for s in SECRETS:
            self.assertIn("secrets." + s, TEXT, s)
        # Signing steps are conditional on the presence flags.
        self.assertIn("env.HAVE_APPLE == 'true'", TEXT)
        self.assertIn("env.HAVE_WINDOWS == 'true'", TEXT)
        # A secret is only ever assigned to an env variable (a `NAME: ${{ secrets.X }}` line).
        for line in TEXT.splitlines():
            if "secrets." in line and not line.lstrip().startswith("#"):
                self.assertRegex(line, r"^\s+[A-Z_]+: .*\$\{\{ secrets\.", line)

    def test_unsigned_files_are_labelled_and_checksummed(self):
        self.assertIn("-UNSIGNED", TEXT)
        self.assertIn("SHA256SUMS-desktop", TEXT)   # SHA256SUMS belongs to the image release
        self.assertIn("--clobber", TEXT)

    def test_only_publish_job_can_write(self):
        jobs = WF["jobs"]
        self.assertEqual(WF["permissions"], {"contents": "read"})
        self.assertEqual(jobs["publish"]["permissions"], {"contents": "write"})
        self.assertNotIn("permissions", jobs["build"])

    def test_dry_run_builds_without_publishing(self):
        self.assertEqual(WF["jobs"]["publish"]["if"], "needs.plan.outputs.tag != ''")
        self.assertIn("workflow_dispatch", WF["jobs"]["build"]["if"])


if __name__ == "__main__":
    unittest.main()
