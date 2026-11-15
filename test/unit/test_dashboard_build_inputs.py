# SPDX-License-Identifier: Apache-2.0
"""Exercise the installer's dashboard input hashing and relative source layout, not root install."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class DashboardBuildInputs(unittest.TestCase):
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
            for path in ("dashboard/main.ts", "ui/src/index.ts", "sdk/ts/src/index.ts"):
                file = src / path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("before\n")
            def digest():
                return subprocess.check_output(["bash", "-ec", command + 'printf "%s" "$sum"'], env={**os.environ, "SRC": str(src)}, text=True)
            before = digest()
            (src / "sdk/ts/src/index.ts").write_text("after\n")
            self.assertNotEqual(before, digest(), "an SDK-only change must rebuild the dashboard")

    def test_installer_stages_the_entire_sdk_tree_next_to_dashboard(self):
        commands = "\n".join(re.findall(r'^\s*copy_src_tree .*$', self.function, re.M))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            src, cache = root / "src", root / "cache"
            for path in ("dashboard/main.ts", "ui/src/index.ts", "sdk/ts/src/index.ts", "sdk/ts/src/gen/schema.ts"):
                file = src / path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(path)
            subprocess.run(["bash", "-ec", 'copy_src_tree() { mkdir -p "$2"; cp -R "$1/." "$2/"; };\n' + commands], env={**os.environ, "SRC": str(src), "CACHE": str(cache)}, check=True)
            for relative in ("index.ts", "gen/schema.ts"):
                copied = cache / "sdk/ts/src" / relative
                self.assertTrue(copied.is_file(), "installer must stage SDK source: " + relative)
                self.assertEqual(copied.read_text(), "sdk/ts/src/" + relative)
        self.assertRegex(self.function, r'chown -R onemind:onemind[^\n]*"\$CACHE/sdk"')


if __name__ == "__main__":
    unittest.main()
