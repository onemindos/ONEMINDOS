# SPDX-License-Identifier: Apache-2.0
"""Exercise the installer's dashboard input hashing and relative source layout, not root install."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]


class DashboardBuildInputs(unittest.TestCase):
    def test_bundle_dashboard_stages_sdk_source(self):
        script = (ROOT / "deploy/bundle.sh").read_text()
        self.assertIn('-v "$REPO/sdk/ts:/src/sdk/ts:ro"', script)
        self.assertIn('-v "$REPO/sdk/openapi:/src/sdk/openapi:ro"', script)
        # CI-16: schema.ts is generated from the spec in the container, before the build
        self.assertLess(script.index("sh /work/sdk/scripts/gen-code.sh ts"), script.index("npm run build"))

    def test_compose_dashboard_mounts_sdk_relative_to_its_build_directory(self):
        data = yaml.safe_load((ROOT / "deploy/compose/compose.yaml").read_text())
        dashboard = data['services']['dashboard']
        self.assertEqual(dashboard['working_dir'], '/build')
        self.assertIn('../../sdk/ts/src:/sdk/ts/src:ro', dashboard['volumes'])

    def setUp(self):
        script = (ROOT / "deploy/install.sh").read_text()
        match = re.search(r"(?ms)^dashboard_build\(\) \{.*?^\}", script)
        assert match is not None, "installer dashboard build function is missing"
        self.function = match.group(0)

    def test_sdk_edit_invalidates_the_installer_build_stamp(self):
        match = re.search(r"(?s)sum=\$\(.*?\)\n", self.function)
        assert match is not None, "installer dashboard input hash is missing"
        command = match.group(0)
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory)
            for path in ("dashboard/main.ts", "ui/src/index.ts", "sdk/ts/src/index.ts", "sdk/openapi/onemind-v1.json",
                         "sdk/ts/package.json", "sdk/ts/package-lock.json"):
                file = src / path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("before\n")
            def digest():
                return subprocess.check_output(["bash", "-ec", command + 'printf "%s" "$sum"'], env={**os.environ, "SRC": str(src)}, text=True)
            before = digest()
            (src / "sdk/ts/src/index.ts").write_text("after\n")
            self.assertNotEqual(before, digest(), "an SDK-only change must rebuild the dashboard")
            spec_before = digest()
            (src / "sdk/openapi/onemind-v1.json").write_text("after\n")
            self.assertNotEqual(spec_before, digest(), "a spec-only change must rebuild the dashboard (CI-16)")
            pin_before = digest()
            (src / "sdk/ts/package-lock.json").write_text("after\n")
            self.assertNotEqual(pin_before, digest(), "a generator pin change must rebuild the dashboard (CI-16)")

    def test_installer_stages_the_entire_sdk_tree_next_to_dashboard(self):
        commands = "\n".join(re.findall(r'^\s*copy_src_tree .*$', self.function, re.M))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            src, cache = root / "src", root / "cache"
            for path in ("dashboard/main.ts", "ui/src/index.ts", "sdk/ts/src/index.ts", "sdk/ts/src/gen/schema.ts",
                         "sdk/ts/package.json", "sdk/openapi/onemind-v1.json", "sdk/scripts/gen-code.sh"):
                file = src / path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(path)
            subprocess.run(["bash", "-ec", 'copy_src_tree() { mkdir -p "$2"; cp -R "$1/." "$2/"; };\n' + commands], env={**os.environ, "SRC": str(src), "CACHE": str(cache)}, check=True)
            for relative in ("index.ts", "gen/schema.ts"):
                copied = cache / "sdk/ts/src" / relative
                self.assertTrue(copied.is_file(), "installer must stage SDK source: " + relative)
                self.assertEqual(copied.read_text(), "sdk/ts/src/" + relative)
            # CI-16: what generating src/gen/schema.ts from the spec needs, staged beside it
            for relative in ("sdk/ts/package.json", "sdk/openapi/onemind-v1.json", "sdk/scripts/gen-code.sh"):
                self.assertTrue((cache / relative).is_file(), "installer must stage " + relative)
        self.assertRegex(self.function, r'chown -R onemind:onemind[^\n]*"\$CACHE/sdk"')
        self.assertLess(self.function.index("gen-code.sh ts"), self.function.index("npm run build >/dev/null"))


if __name__ == "__main__":
    unittest.main()
