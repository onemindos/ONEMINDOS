# SPDX-License-Identifier: Apache-2.0
"""Android release APK/AAB on every dev release: dev-android.yml, the build script, the signing plugin, the guide."""
import os, re, stat, unittest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
read = lambda *p: open(os.path.join(ROOT, *p)).read()
SECRETS = ("ANDROID_KEYSTORE_BASE64", "ANDROID_KEYSTORE_PASSWORD", "ANDROID_KEY_ALIAS", "ANDROID_KEY_PASSWORD")


class Workflow(unittest.TestCase):
    def setUp(self):
        self.text = read(".github", "workflows", "dev-android.yml")
        self.wf = yaml.safe_load(self.text)

    def test_runs_after_dev_build_or_by_hand_never_on_a_pull_request(self):
        on = self.wf.get("on", self.wf.get(True))
        self.assertEqual(sorted(on), ["workflow_dispatch", "workflow_run"])
        self.assertEqual(on["workflow_run"]["workflows"], ["dev-build"])
        self.assertIn("onemindos/ONEMINDOS", self.wf["jobs"]["pick"]["if"])

    def test_secrets_only_in_the_read_only_build_job(self):
        jobs = self.wf["jobs"]
        self.assertEqual(jobs["build"]["permissions"], {"contents": "read"})
        self.assertEqual(jobs["publish"]["permissions"], {"contents": "write"})
        publish = yaml.dump(jobs["publish"]) + yaml.dump(jobs["pick"])
        self.assertNotIn("secrets.", publish)
        for s in SECRETS:
            self.assertIn("secrets." + s, self.text)

    def test_dev_build_stays_secret_free(self):
        self.assertNotIn("secrets.", read(".github", "workflows", "dev-build.yml"))

    def test_build_number_is_the_version_code_and_the_commit_is_the_releases(self):
        self.assertIn("-dev\\.([0-9]+)", self.text)
        self.assertIn("0.1.0-dev.${{ needs.pick.outputs.code }}", self.text)
        self.assertIn("ref: ${{ needs.pick.outputs.sha }}", self.text)

    def test_attaches_to_a_dev_release_and_skips_when_already_there(self):
        self.assertIn("--clobber", self.text)
        self.assertIn("already has an Android APK", self.text)
        self.assertIn("^dev-[0-9]{8}-[0-9a-f]{7}$", self.text)

    def test_actions_are_pinned_to_a_commit(self):
        for line in self.text.splitlines():
            m = re.search(r"uses: (\S+)", line)
            if m:
                self.assertRegex(m.group(1), r"@[0-9a-f]{40}$", line)


class Script(unittest.TestCase):
    def setUp(self):
        self.text = read("mobile", "scripts", "android-release-build.sh")

    def test_executable(self):
        self.assertTrue(os.stat(os.path.join(ROOT, "mobile", "scripts", "android-release-build.sh")).st_mode & stat.S_IXUSR)

    def test_signed_and_unsigned_names_and_aab_only_when_signed(self):
        self.assertIn('onemind-android-$label.apk', self.text)
        self.assertIn('onemind-android-$label.aab', self.text)
        self.assertIn('onemind-android-$label-dev-unsigned.apk', self.text)
        self.assertIn("assembleRelease bundleRelease", self.text)
        self.assertIn("::notice::Android signing secrets are not set", self.text)

    def test_keeps_the_permission_check_and_checks_version_code(self):
        self.assertIn("blockedPermissions", self.text)
        self.assertIn("aapt2", self.text)
        self.assertIn("versionCode='$code'", self.text)

    def test_never_echoes_a_secret(self):
        for s in SECRETS:
            self.assertNotRegex(self.text, r"echo[^\n]*\$\{?%s" % s)

    def test_ci_mobile_runs_it_without_secrets(self):
        ci = read(".github", "workflows", "ci-mobile.yml")
        self.assertIn("scripts/android-release-build.sh", ci)
        self.assertNotIn("secrets.", ci)
        yaml.safe_load(ci)


class Plugin(unittest.TestCase):
    def test_registered_in_app_json_and_reads_env_only(self):
        self.assertIn("./plugins/withReleaseSigning", read("mobile", "app.json"))
        js = read("mobile", "plugins", "withReleaseSigning.js")
        for v in SECRETS + ("ONEMIND_VERSION_CODE", "ANDROID_KEYSTORE_PATH"):
            self.assertIn(v, js)


class Guide(unittest.TestCase):
    def test_guide_names_files_obtainium_and_unverified(self):
        g = read("mobile", "docs", "install-android.md")
        for needle in ("-dev-unsigned.apk", ".aab", "Obtainium", "Include prereleases", "UNVERIFIED", "Play Protect"):
            self.assertIn(needle, g)


if __name__ == "__main__":
    unittest.main()
