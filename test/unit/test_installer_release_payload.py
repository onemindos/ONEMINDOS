# SPDX-License-Identifier: Apache-2.0
"""The installer stick built from the release-signed image (#234, D-010, D-031; os/boards/installer-x86_64/UPDATES.md).

Selection: scripts/release/installer-payload.py turns the security build's release record into "release" (the public
release keyring, never a key) or "dev" (a dry run). Release image: os/assemble/release-image.sh assembles with that
keyring only. Dry run: without keys the dev path is exactly what image.yml runs today (make -n shows the commands).
Run: python3 -I -m unittest discover -s test/unit -p test_installer_release_payload.py
"""
import base64, contextlib, importlib.util, io, json, os, re, shutil, subprocess, sys, tempfile, unittest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("installer_payload", os.path.join(ROOT, "scripts", "release", "installer-payload.py"))
ip = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ip)


def read(*p):
    with open(os.path.join(ROOT, *p)) as f:
        return f.read()


RELEASE_IMAGE = os.path.join(ROOT, "os", "assemble", "release-image.sh")
V = "0.1.20261112025704"
MARK = "NEVER-PRINT-THIS-MARKER"
KEY = f"-----BEGIN PRIVATE KEY-----\n{MARK}\n-----END PRIVATE KEY-----\n"     # stands in for a key: must never be echoed


def pem(kind="CERTIFICATE", der=b"\x30\x03\x02\x01\x01"):
    return f"-----BEGIN {kind}-----\n{base64.b64encode(der).decode()}\n-----END {kind}-----\n"


def record(d, dry_run, version=V, board="x86_64-efi", keyring=None, **extra):
    rec = {"schema": "onemind.release/v1", "board": board, "version": version, "compatible": "onemind-" + board,
           "min_from_version": "", "security": True, "snapshot": "20261112T025704Z", "dry_run": dry_run}
    rec.update(extra)
    with open(os.path.join(d, f"release-{board}.json"), "w") as f:
        json.dump(rec, f)
    if keyring is not None:
        with open(os.path.join(d, f"onemind-{board}-{version}.keyring.pem"), "w") as f:
            f.write(keyring)


class Selection(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.rel, self.trust = os.path.join(t.name, "rel"), os.path.join(t.name, "trust")
        os.makedirs(self.rel)

    def run_main(self, version=V, publish="true"):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ip.main(["--release-dir", self.rel, "--version", version, "--publish", publish, "--trust-dir", self.trust])
        return out.getvalue()

    def test_the_target_board_comes_from_the_installer_board_file(self):
        self.assertEqual(ip.target_board(), yaml.safe_load(read("os", "boards", "installer-x86_64", "board.yaml"))["target_board"])
        self.assertEqual(ip.target_board(), "x86_64-efi")

    def test_a_release_signed_build_gives_the_release_keyring_and_nothing_else(self):
        ring = pem() + pem(der=b"\x30\x01\x00")       # a keyring may hold two CAs (rotation)
        record(self.rel, False, keyring=ring)
        self.assertEqual(self.run_main(), "mode=release\n")
        self.assertEqual(os.listdir(self.trust), ["keyring.pem"])
        self.assertEqual(read(self.trust, "keyring.pem"), ring)

    def test_a_dry_run_gives_the_dev_path_and_no_trust_folder(self):
        record(self.rel, True, keyring=pem())
        self.assertEqual(self.run_main(publish="false"), "mode=dev\n")
        self.assertFalse(os.path.exists(self.trust))
        self.assertEqual(ip.select(self.rel, V, False), ("dev", None))

    def test_publish_and_dry_run_must_agree(self):
        record(self.rel, True, keyring=pem())
        with self.assertRaisesRegex(SystemExit, "dev-keyed"):
            ip.select(self.rel, V, True)
        record(self.rel, False, keyring=pem())
        with self.assertRaisesRegex(SystemExit, "does not publish"):
            ip.select(self.rel, V, False)

    def test_the_record_must_match_this_run(self):
        with self.assertRaisesRegex(SystemExit, "missing"):
            ip.select(self.rel, V, True)
        record(self.rel, False, keyring=pem())
        with self.assertRaisesRegex(SystemExit, "version"):
            ip.select(self.rel, V + "1", True)
        record(self.rel, False, keyring=pem(), schema="other")
        with self.assertRaisesRegex(SystemExit, "record"):
            ip.select(self.rel, V, True)
        record(self.rel, False, keyring=pem())
        path = os.path.join(self.rel, "release-x86_64-efi.json")
        with open(path) as f:
            rec = json.load(f)
        rec["board"] = "vm-do"
        with open(path, "w") as f:
            json.dump(rec, f)
        with self.assertRaisesRegex(SystemExit, "board"):
            ip.select(self.rel, V, True)
        record(self.rel, "false", keyring=pem())
        with self.assertRaisesRegex(SystemExit, "dry_run"):
            ip.select(self.rel, V, True)

    def test_a_release_with_a_dev_version_or_without_its_keyring_is_refused(self):
        record(self.rel, False, version="0.1.0-dev.7", keyring=pem())
        with self.assertRaisesRegex(SystemExit, "development version"):
            ip.select(self.rel, "0.1.0-dev.7", True)
        record(self.rel, False)
        with self.assertRaisesRegex(SystemExit, "keyring.pem is missing"):
            ip.select(self.rel, V, True)

    def test_a_keyring_with_anything_but_certificates_is_refused_and_never_printed(self):
        bad = [pem() + KEY, KEY.replace("PRIVATE", "ENCRYPTED PRIVATE"),
               pem("PUBLIC KEY"), "", "junk " + MARK, pem(der=b"\x02\x01"),
               "-----BEGIN CERTIFICATE-----\n!!!\n-----END CERTIFICATE-----\n", pem() + "-----BEGIN CERTIFICATE-----\nAAAA\n"]
        for text in bad:
            record(self.rel, False, keyring=text)
            err = io.StringIO()
            with self.subTest(text=text[:40]), contextlib.redirect_stdout(err), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as cm:
                    self.run_main()
                self.assertNotIn(MARK, str(cm.exception) + err.getvalue())
                self.assertFalse(os.path.exists(self.trust))

    def test_publish_must_be_a_plain_flag_and_the_trust_folder_must_be_new(self):
        record(self.rel, False, keyring=pem())
        with self.assertRaisesRegex(SystemExit, "true or false"):
            self.run_main(publish="yes")
        os.makedirs(self.trust)
        open(os.path.join(self.trust, "signer.key"), "w").close()
        with self.assertRaisesRegex(SystemExit, "not empty"):
            self.run_main()

    def test_the_selector_never_signs_or_runs_tools(self):
        src = read("scripts", "release", "installer-payload.py")
        self.assertNotRegex(src, r"subprocess|openssl|signer|\.key['\"]|os\.system")


class ReleaseImage(unittest.TestCase):
    """os/assemble/release-image.sh in a scratch tree whose assembler only records how it was called."""

    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = t.name
        for d in ("os/assemble", "os/boards/x86_64-efi"):
            os.makedirs(os.path.join(self.root, d))
        shutil.copy(RELEASE_IMAGE, os.path.join(self.root, "os", "assemble"))
        shutil.copy(os.path.join(ROOT, "os", "boards", "x86_64-efi", "board.yaml"), os.path.join(self.root, "os", "boards", "x86_64-efi"))
        with open(os.path.join(self.root, "os", "assemble", "assemble.py"), "w") as f:
            f.write("import json, os, sys\na = sys.argv[1:]\nout = a[a.index('--out-dir') + 1]\nos.makedirs(out, exist_ok=True)\n"
                    "json.dump(a, open(os.path.join(out, 'assemble-args.json'), 'w'))\n"
                    "open(os.path.join(out, 'SHA256SUMS'), 'a').write('0' * 64 + '  onemind-x86_64-efi-v.img\\n')\n")
        self.trust, self.out = os.path.join(self.root, "trust"), os.path.join(self.root, "out", "image-x86_64-efi")
        os.makedirs(self.trust)

    def run_script(self, keyring=pem(), version=V, **env):
        if keyring is not None:
            with open(os.path.join(self.trust, "keyring.pem"), "w") as f:
                f.write(keyring)
        e = {"PATH": os.environ["PATH"], "BOARD": "x86_64-efi", "ROOTFS": "/out/rootfs.tar", "VERSION": version,
             "TRUSTDIR": self.trust}
        e.update(env)
        e = {k: v for k, v in e.items() if v is not None}
        return subprocess.run(["sh", os.path.join(self.root, "os", "assemble", "release-image.sh"), self.out],
                              env=e, capture_output=True, text=True)

    def test_assembles_with_the_release_keyring_and_no_key(self):
        os.makedirs(self.out)
        with open(os.path.join(self.out, "SHA256SUMS"), "w") as f:
            f.write("stale line from an older build\n")
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.out, "assemble-args.json")) as f:
            args = json.load(f)
        self.assertEqual(args[0], "image")
        self.assertEqual(args[args.index("--keyring") + 1], os.path.join(self.trust, "keyring.pem"))
        self.assertEqual((args[args.index("--board") + 1], args[args.index("--version") + 1]), ("x86_64-efi", V))
        for flag in ("--cert", "--key", "--sb-key", "--sb-cert"):
            self.assertNotIn(flag, args)
        self.assertEqual(read(self.out, "release-ca.cert.pem"), pem())
        self.assertFalse(os.path.exists(os.path.join(self.out, "dev-ca.cert.pem")))
        self.assertNotIn("stale", read(self.out, "SHA256SUMS"))

    def refused(self, r, why):
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(why, r.stderr)
        self.assertNotIn(MARK, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.out, "assemble-args.json")), "the assembler ran")

    def test_refusals(self):
        self.refused(self.run_script(TRUSTDIR=None), "TRUSTDIR")
        self.refused(self.run_script(TRUSTDIR=""), "TRUSTDIR")
        self.refused(self.run_script(version="0.1.0-dev.7"), "development version")
        self.refused(self.run_script(SECUREBOOT="1"), "SECUREBOOT")
        self.refused(self.run_script(keyring=pem() + KEY), "private key")
        self.refused(self.run_script(keyring=pem() + pem("PUBLIC KEY")), "not a certificate")
        self.refused(self.run_script(keyring="junk\n"), "no certificate")
        os.remove(os.path.join(self.trust, "keyring.pem"))
        self.refused(self.run_script(keyring=None), "no keyring.pem")

    def test_a_key_file_next_to_the_keyring_is_refused_by_name(self):
        for name in ("signer.key", "signer.pem", ".hidden"):
            with self.subTest(name=name):
                p = os.path.join(self.trust, name)
                with open(p, "w") as f:
                    f.write(MARK)
                self.refused(self.run_script(), name)
                os.remove(p)

    def test_the_script_never_takes_a_signing_key(self):
        code = "\n".join(l for l in read(RELEASE_IMAGE).splitlines() if not l.lstrip().startswith("#"))
        self.assertNotRegex(code, r"--cert|--key\b|signer|KEYDIR|openssl")


def make_n(*args):
    """make's own dry run (-n): prints the commands, runs none (recursive make only prints too)."""
    env = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp")}
    r = subprocess.run(["make", "-n", "-C", ROOT, *args], env=env, capture_output=True, text=True)
    if r.returncode:
        raise AssertionError(r.stdout + r.stderr)
    return r.stdout


def docker_runs(out):
    return [l for l in out.replace("\\\n", " ").splitlines() if l.startswith("docker run ")]


class DryRunDevPathIsUnchanged(unittest.TestCase):
    """Without release keys the stick's image is `make image` with dev-image.sh, exactly as image.yml runs it."""

    DEV = (r'docker run --rm --platform linux/amd64 -v "{root}":/src:ro -v "{root}/out":/out -e VERSION={v} '
           r'-e BOARD=x86_64-efi -e SECUREBOOT=0 -e ROOTFS=/out/rootfs-debian-x86_64-efi.tar -e SOURCE_DATE_EPOCH=\d* '
           r'onemind-tools:ci\s+/src/os/assemble/dev-image.sh /out/image-x86_64-efi')

    def dev_line(self, v):
        return re.compile(self.DEV.format(root=re.escape(ROOT), v=re.escape(v)))

    def test_make_image_is_the_dev_image_with_a_throwaway_ca(self):
        out = make_n("image", "BOARD=x86_64-efi", "TOOLS=onemind-tools:ci", "VERSION=0.1.0-dev.7")
        runs = docker_runs(out)
        self.assertEqual(len(runs), 1, out)
        self.assertRegex(runs[0], self.dev_line("0.1.0-dev.7"))
        self.assertNotRegex(out, r"TRUSTDIR|/trust|release-image|KEYDIR|\.key\b")

    def test_make_installer_without_trust_still_builds_the_dev_image(self):
        out = make_n("installer", "BOARD=installer-x86_64", "TOOLS=onemind-tools:ci")
        runs = docker_runs(out)
        self.assertRegex(runs[0], self.dev_line("0.1.0-dev"))
        self.assertTrue(runs[-1].endswith("/src/os/boards/installer-x86_64/build.sh /out/rootfs-installer-x86_64.tar "
                                          "/out/image-x86_64-efi /out/installer-x86_64"), runs[-1])
        self.assertNotRegex(out, r"TRUSTDIR|release-image")

    def test_make_release_image_mounts_only_the_trust_folder(self):
        out = make_n("release-image", "BOARD=x86_64-efi", "TOOLS=onemind-tools:ci", f"VERSION={V}", "TRUST=/tmp/trust-x")
        runs = docker_runs(out)
        self.assertEqual(len(runs), 1, out)
        self.assertIn('-v "/tmp/trust-x":/trust:ro -e TRUSTDIR=/trust', runs[0])
        self.assertRegex(runs[0], r"onemind-tools:ci\s+/src/os/assemble/release-image.sh /out/image-x86_64-efi$")
        self.assertNotRegex(runs[0], r"KEYDIR|SECUREBOOT=1|\.key\b|dev-image")

    def test_the_dry_run_record_maps_to_that_dev_command_in_the_workflow(self):
        with tempfile.TemporaryDirectory() as d:
            record(d, True, keyring=pem())
            self.assertEqual(ip.select(d, V, False), ("dev", None))
        img = yaml.safe_load(read(".github", "workflows", "image.yml"))["jobs"]["installer"]
        step = next(s for s in img["steps"] if s.get("name", "").startswith("Image, then the installer stick"))
        self.assertEqual(step["run"].splitlines(), [
            "make image BOARD=x86_64-efi TOOLS=onemind-tools:ci VERSION=0.1.0-dev.${{ github.run_number }}",
            "sudo rm -f out/rootfs-debian-*.tar",
            "make installer BOARD=installer-x86_64 TOOLS=onemind-tools:ci"])
        sec = nightly_installer()
        stick = next(s for s in sec["steps"] if s.get("name") == "The image the stick carries, then the stick")["run"]
        dev = re.search(r"(?ms)^else$(.*?)^fi$", stick).group(1)
        self.assertIn(step["run"].splitlines()[0].replace("VERSION=0.1.0-dev.${{ github.run_number }}", 'VERSION="$VERSION"'), dev)
        self.assertNotRegex(dev, r"TRUST|release-image")
        for line in step["run"].splitlines()[1:]:
            self.assertIn(line, stick)


def nightly_installer():
    return yaml.safe_load(read(".github", "workflows", "security-nightly.yml"))["jobs"]["installer"]


class Wiring(unittest.TestCase):
    def test_the_dev_stick_job_in_image_yml_holds_no_keys(self):
        text = read(".github", "workflows", "image.yml")
        job = yaml.safe_load(text)["jobs"]["installer"]
        self.assertNotIn("environment", job)
        self.assertNotRegex(json.dumps(job), r"secrets\.|TRUST|release-image|installer-payload")

    def test_the_security_stick_job_reads_no_secret_and_stays_hosted(self):
        job = nightly_installer()
        self.assertNotIn("environment", job)
        self.assertNotRegex(json.dumps(job), r"secrets\.|KEYDIR|signer\.key")
        self.assertEqual(job["runs-on"], "ubuntu-24.04")
        self.assertEqual(set(job["needs"]), {"decide", "build"})
        self.assertEqual(job["if"], "needs.decide.outputs.rebuild == 'true'")

    def test_the_security_stick_job_selects_then_checks_the_keyring(self):
        steps = nightly_installer()["steps"]
        dl = next(s for s in steps if "download-artifact" in s.get("uses", ""))
        self.assertEqual(dl["with"]["name"], "release-x86_64-efi")
        sel = next(s for s in steps if s.get("id") == "payload")["run"]
        self.assertIn("scripts/release/installer-payload.py --release-dir rel", sel)
        self.assertIn('--publish "$PUBLISH"', sel)
        stick = next(s for s in steps if s.get("name") == "The image the stick carries, then the stick")
        self.assertEqual(stick["env"]["MODE"], "${{ steps.payload.outputs.mode }}")
        rel = re.search(r'(?ms)^if \[ "\$MODE" = release \]; then$(.*?)^else$', stick["run"]).group(1)
        self.assertIn('make release-image BOARD=x86_64-efi TOOLS=onemind-tools:ci VERSION="$VERSION" TRUST="$RUNNER_TEMP/trust"', rel)
        self.assertIn('cmp out/image-x86_64-efi/release-ca.cert.pem "rel/onemind-x86_64-efi-$VERSION.keyring.pem"', rel)
        self.assertIn("publishing run produced a dev-keyed installer image", stick["run"])
        names = [s.get("name", "") for s in steps]
        self.assertIn("Installer test (I1-I5)", names)

    def test_a_red_stick_never_holds_back_a_security_fix(self):
        jobs = yaml.safe_load(read(".github", "workflows", "security-nightly.yml"))["jobs"]
        for j in ("tuf", "publish"):
            self.assertNotIn("installer", jobs[j]["needs"], j)

    def test_the_doc_says_install_once_update_forever(self):
        doc = read("os", "boards", "installer-x86_64", "UPDATES.md")
        for needle in ("Install once, update forever", "installer-payload.py", "make release-image", "NOT done yet",
                       "test_installer_release_payload.py"):
            self.assertIn(needle, doc)
        self.assertNotIn("The stick still installs a dev-signed image", doc)


if __name__ == "__main__":
    unittest.main()
