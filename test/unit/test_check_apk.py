# SPDX-License-Identifier: Apache-2.0
"""Phone APK on every release (#880): scripts/check-apk, scripts/release/apk-assets.py and the android job of
release.yml. aapt2 and apksigner are replaced by small fake tools that print what the real ones print, so the
checks run on any machine; the signing keys are throwaway, made in a temp dir and never committed."""
import hashlib, os, stat, subprocess, sys, tempfile, unittest, zipfile
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHECK = os.path.join(ROOT, "scripts", "check-apk")
ASSETS = os.path.join(ROOT, "scripts", "release", "apk-assets.py")
WF = os.path.join(ROOT, ".github", "workflows", "release.yml")
ANDROID_SECRETS = ("ANDROID_KEYSTORE_BASE64", "ANDROID_KEYSTORE_PASSWORD", "ANDROID_KEY_ALIAS", "ANDROID_KEY_PASSWORD")

RELEASE_CERT = "Signer #1 certificate DN: CN=OneMind, O=OneMind OS\nSigner #1 certificate SHA-256 digest: ab12\n"
DEBUG_CERT = "Signer #1 certificate DN: C=US, O=Android, CN=Android Debug\n"


def badging(package="com.onemindos.mobile", name="1.2.0", code="102000017", debuggable=False):
    out = (f"package: name='{package}' versionCode='{code}' versionName='{name}' platformBuildVersionName='15'\n"
           "sdkVersion:'24'\ntargetSdkVersion:'35'\napplication-label:'OneMind'\n")
    return out + ("application-debuggable\n" if debuggable else "") + "launchable-activity: name='com.onemindos.mobile.MainActivity'\n"


def tool(d, name, text, rc=0):
    """A stand-in for aapt2/apksigner: prints `text` for any arguments, exits `rc`."""
    with open(os.path.join(d, name + ".out"), "w") as f:
        f.write(text)
    p = os.path.join(d, name)
    with open(p, "w") as f:
        f.write(f'#!/bin/sh\ncat "$(dirname "$0")/{name}.out"\nexit {rc}\n')
    os.chmod(p, 0o755)
    return p


def apk(path, bundle=b"__d(function(){var t='Connect to your box';})", with_bundle=True):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("AndroidManifest.xml", b"\x03\x00\x08\x00binary-manifest")
        if with_bundle:
            z.writestr("assets/index.android.bundle", bundle)
    return path


def keypair(base):
    key, pub = base + "-k.pem", base + "-p.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256", "-out", key],
                   check=True, capture_output=True)
    subprocess.run(["openssl", "pkey", "-in", key, "-pubout", "-out", pub], check=True, capture_output=True)
    return key, pub


class CheckApk(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.d = t.name
        self.apk = apk(os.path.join(self.d, "onemind-android-1.2.0.apk"))
        self.signer = tool(self.d, "apksigner", RELEASE_CERT)

    def run_check(self, version="1.2.0", aapt=None, *extra, apk_path=None):
        aapt = aapt or tool(self.d, "aapt2", badging())
        return subprocess.run([sys.executable, "-I", CHECK, "--apk", apk_path or self.apk, "--version", version,
                               "--aapt2", aapt, "--apksigner", self.signer, *extra], capture_output=True, text=True)

    def test_executable(self):
        self.assertTrue(os.stat(CHECK).st_mode & stat.S_IXUSR)

    def test_release_build_passes(self):
        r = self.run_check("1.2.0")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("com.onemindos.mobile", r.stdout)

    def test_tag_with_a_leading_v_passes(self):
        self.assertEqual(self.run_check("v1.2.0").returncode, 0)

    def test_debug_build_fails(self):
        r = self.run_check("1.2.0", tool(self.d, "aapt2", badging(debuggable=True)))
        self.assertEqual(r.returncode, 1)
        self.assertIn("debuggable", r.stderr)

    def test_debug_signing_key_fails(self):
        self.signer = tool(self.d, "apksigner", DEBUG_CERT)
        r = self.run_check("1.2.0")
        self.assertEqual(r.returncode, 1)
        self.assertIn("debug key", r.stderr)

    def test_unsigned_or_broken_signature_fails(self):
        self.signer = tool(self.d, "apksigner", "DOES NOT VERIFY\n", rc=1)
        self.assertEqual(self.run_check("1.2.0").returncode, 1)

    def test_version_mismatch_fails(self):
        r = self.run_check("1.3.0")
        self.assertEqual(r.returncode, 1)
        self.assertIn("1.3.0", r.stderr)

    def test_prerelease_tag_matches_only_its_x_y_z(self):
        # The stamper drops "-rc.1" (the stores reject it), so the app says 1.2.0 for tag 1.2.0-rc.1.
        self.assertEqual(self.run_check("1.2.0-rc.1").returncode, 0)
        self.assertEqual(self.run_check("1.2.1-rc.1").returncode, 1)

    def test_version_code_mismatch_fails(self):
        self.assertEqual(self.run_check("1.2.0", None, "--version-code", "102000017").returncode, 0)
        self.assertEqual(self.run_check("1.2.0", None, "--version-code", "102000018").returncode, 1)

    def test_package_outside_com_onemindos_fails(self):
        for bad in ("com.example.mobile", "com.onemindos", "com.onemindosx.mobile"):
            r = self.run_check("1.2.0", tool(self.d, "aapt2", badging(package=bad)))
            self.assertEqual(r.returncode, 1, bad)

    def test_demo_module_in_the_bundle_fails(self):
        for marker in (b"owner-demo", b"agent-demo", b"photos.demo.invalid", b"Or try the demo"):
            p = apk(os.path.join(self.d, "demo.apk"), bundle=b"var a=1;" + marker + b";")
            r = self.run_check("1.2.0", None, apk_path=p)
            self.assertEqual(r.returncode, 1, marker)
            self.assertIn("demo", r.stderr)

    def test_no_js_bundle_fails(self):
        p = apk(os.path.join(self.d, "nobundle.apk"), with_bundle=False)
        self.assertEqual(self.run_check("1.2.0", None, apk_path=p).returncode, 1)

    def test_not_an_apk_fails(self):
        p = os.path.join(self.d, "junk.apk")
        with open(p, "wb") as f:
            f.write(b"not a zip")
        self.assertEqual(self.run_check("1.2.0", None, apk_path=p).returncode, 1)

    def test_missing_tool_or_bad_version_is_a_usage_error(self):
        self.assertEqual(self.run_check("1.2.0", os.path.join(self.d, "no-aapt2")).returncode, 2)
        self.assertEqual(self.run_check("latest").returncode, 2)


class ApkAssets(unittest.TestCase):
    """The dry run of the publish step on a test tag: exactly three files, and the signature verifies."""

    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.d = t.name
        self.key, self.pub = keypair(os.path.join(self.d, "rel"))
        self.apk = os.path.join(self.d, "in", "onemind-android-9.9.9.apk")
        os.makedirs(os.path.dirname(self.apk))
        with open(self.apk, "wb") as f:
            f.write(b"PK-apk-bytes")
        self.out = os.path.join(self.d, "apk")
        with open(self.key) as f:
            self.key_pem = f.read()

    def assets(self, *extra, key=True, pub=None):
        env = {k: v for k, v in os.environ.items() if k != "RELEASE_SIGNING_KEY"}
        if key:
            env["RELEASE_SIGNING_KEY"] = self.key_pem
        return subprocess.run([sys.executable, "-I", ASSETS, "--apk", self.apk, "--version", "9.9.9", "--out", self.out,
                               "--pubkey", pub or self.pub, *extra], capture_output=True, text=True, env=env)

    def test_dry_run_on_a_test_tag_yields_three_files(self):
        r = self.assets()
        self.assertEqual(r.returncode, 0, r.stderr)
        names = sorted(os.listdir(self.out))
        self.assertEqual(names, ["onemind-9.9.9.apk", "onemind-9.9.9.apk.sha256", "onemind-9.9.9.apk.sha256.sig"])
        digest = hashlib.sha256(b"PK-apk-bytes").hexdigest()
        with open(os.path.join(self.out, "onemind-9.9.9.apk.sha256")) as f:
            self.assertEqual(f.read(), f"{digest}  onemind-9.9.9.apk\n")    # `sha256sum -c` reads this
        s = os.path.join(self.out, "onemind-9.9.9.apk.sha256")
        v = subprocess.run(["openssl", "dgst", "-sha256", "-verify", self.pub, "-signature", s + ".sig", s],
                           capture_output=True, text=True)
        self.assertEqual(v.returncode, 0, v.stdout + v.stderr)

    def test_never_prints_the_key(self):
        r = self.assets()
        body = self.key_pem.split("-----")[2].strip().splitlines()[0]
        self.assertNotIn(body, r.stdout + r.stderr)
        self.assertNotIn("PRIVATE KEY", r.stdout + r.stderr)

    def test_no_signing_key_refuses_and_writes_nothing(self):
        r = self.assets(key=False)
        self.assertEqual(r.returncode, 2)
        self.assertIn("RELEASE_SIGNING_KEY", r.stderr)
        self.assertFalse(os.path.exists(self.out) and os.listdir(self.out))

    def test_key_that_does_not_match_the_public_key_refuses(self):
        _, other = keypair(os.path.join(self.d, "other"))
        r = self.assets(pub=other)
        self.assertEqual(r.returncode, 2)
        self.assertFalse(os.path.exists(self.out) and os.listdir(self.out))

    def test_apk_changed_after_the_check_refuses(self):
        self.assertEqual(self.assets("--expect-sha256", hashlib.sha256(b"PK-apk-bytes").hexdigest()).returncode, 0)
        self.assertEqual(self.assets("--expect-sha256", "0" * 64).returncode, 2)


class Workflow(unittest.TestCase):
    def setUp(self):
        with open(WF, encoding="utf-8") as f:
            self.text = f.read()
        self.wf = yaml.safe_load(self.text)
        self.jobs = self.wf["jobs"]

    def test_triggers_unchanged(self):
        on = self.wf.get("on", self.wf.get(True))
        self.assertEqual(list(on), ["workflow_dispatch"])
        self.assertEqual(sorted(on["workflow_dispatch"]["inputs"]), ["image_run_id", "version"])

    def test_android_job_is_gated_read_only_and_builds_the_image_commit(self):
        a = self.jobs["android"]
        self.assertEqual(a["needs"], "gate")
        self.assertEqual(a["environment"], "release")
        self.assertEqual(a["permissions"], {"contents": "read", "actions": "read"})
        self.assertEqual(a["runs-on"], "ubuntu-24.04")
        steps = a["steps"]
        checkouts = [s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@")]
        self.assertEqual([c["with"].get("path") for c in checkouts], ["trusted", "app"])
        trusted, app = (c["with"] for c in checkouts)
        self.assertNotIn("ref", trusted)                      # the workflow's own ref
        self.assertEqual(trusted["fetch-depth"], 0)           # origin/main and origin/release/next for the check
        self.assertEqual(app["ref"], "${{ steps.commit.outputs.sha }}")
        for c in (trusted, app):
            self.assertIs(c["persist-credentials"], False)

    def test_image_run_is_checked_before_its_commit_or_any_secret_is_used(self):
        steps = self.jobs["android"]["steps"]
        names = [s.get("name", s.get("uses", "")) for s in steps]
        i = next(n for n, s in enumerate(steps) if s.get("id") == "commit")
        run = steps[i]["run"]
        self.assertIn("trusted/scripts/release/check-image-run.py", run)
        self.assertIn('--run-id "$RUN_ID"', run)
        self.assertIn("--git trusted", run)
        self.assertIn("actions/runs/$RUN_ID", run)
        self.assertRegex(run, r"\[\[ \"\$RUN_ID\" =~ \^\[1-9\]\[0-9\]\*\$ \]\]")
        self.assertEqual(steps[i - 1]["with"].get("path"), "trusted", names)
        self.assertEqual(steps[i + 1]["with"].get("path"), "app", names)
        for s in steps[:i + 2]:
            self.assertNotIn("secrets.", yaml.dump(s), s.get("name"))

    def test_checks_run_from_the_workflow_ref_not_the_image_commit(self):
        a = self.text.split("\n  android:\n")[1].split("\n  publish:\n")[0]
        self.assertIn("python3 -I trusted/scripts/check-apk --apk", a)
        self.assertIn("python3 -I trusted/scripts/release/stamp-client-versions.py --root app", a)
        self.assertNotRegex(a, r"python3 -I (\./)?scripts/")          # nothing from the image commit's scripts/
        for s in self.jobs["android"]["steps"]:
            wd = s.get("working-directory")
            if wd:
                self.assertEqual(wd, "app/mobile", s.get("name"))

    def test_android_signing_secrets_only_in_the_android_job(self):
        for s in ANDROID_SECRETS:
            self.assertIn("secrets." + s, yaml.dump(self.jobs["android"]))
        for name, job in self.jobs.items():
            if name != "android":
                for s in ANDROID_SECRETS:
                    self.assertNotIn(s, yaml.dump(job), name)
        self.assertNotIn("RELEASE_SIGNING_KEY", yaml.dump(self.jobs["android"]))

    def test_refuses_an_unsigned_build_then_stamps_builds_and_checks(self):
        a = self.text.split("\n  android:\n")[1].split("\n  publish:\n")[0]     # the job's own text, in order
        order = [a.index(s) for s in ("REFUSED: Android signing secrets", "stamp-client-versions.py",
                                      "android-release-build.sh", "python3 -I trusted/scripts/check-apk")]
        self.assertEqual(order, sorted(order))
        self.assertIn('--version "$VERSION"', a)
        self.assertIn('--version-code "$CODE"', a)

    def test_publish_signs_the_checksum_and_attaches_three_files_with_the_guide(self):
        p = self.jobs["publish"]
        self.assertEqual(sorted(p["needs"]), ["android", "gate"])
        body = yaml.dump(p, width=1000)
        self.assertIn("apk-assets.py", body)
        self.assertIn("--expect-sha256", body)
        create = self.text.split("gh release create")[1]
        self.assertIn("apk/*", create)
        self.assertIn("mobile/docs/install-android.md", create)
        self.assertIn('--target "$TARGET"', create)
        self.assertLess(self.text.index("apk-assets.py"), self.text.index("gh release create"))

    def test_gate_runs_the_apk_and_image_run_self_tests(self):
        self.assertIn("test_check_apk.py", yaml.dump(self.jobs["gate"]))
        self.assertIn("test_check_image_run.py", yaml.dump(self.jobs["gate"]))

    def test_never_echoes_a_secret(self):
        for s in ANDROID_SECRETS + ("RELEASE_SIGNING_KEY",):
            self.assertNotRegex(self.text, r"(echo|cat)[^\n]*\$\{?%s" % s)


if __name__ == "__main__":
    unittest.main()
