# SPDX-License-Identifier: Apache-2.0
"""The gateway's managed Python gets its standard library compiled at install time (perf-smoke
idle_memory_mib.gateway, Refs #234).

uv's managed Python ships the standard library almost without .pyc files, and the gateway (user
onemind, ProtectSystem=strict) cannot write them under /opt/onemind/python. Without this step every
gateway start compiled about 200 stdlib modules from source: slower cold start and about 4 MiB more
private memory for as long as the process runs. The image already compiles it (os/rootfs/Containerfile);
deploy/install.sh (both paths) and deploy/bundle.sh must too.
"""
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSTALL = ROOT / "deploy" / "install.sh"
BUNDLE = ROOT / "deploy" / "bundle.sh"


def function_body(script: str, name: str) -> str:
    m = re.search(rf"^{name}\(\) \{{\n(.*?)^\}}", script, re.S | re.M)
    assert m, f"{name}() not found"
    return m.group(1)


class InstallWiring(unittest.TestCase):
    def test_both_install_paths_compile_the_stdlib(self):
        script = INSTALL.read_text(encoding="utf-8")
        built = function_body(script, "gateway_python")
        # After uv has put Python in place (the sync), not before.
        sync = built.index('"$UV" sync')
        self.assertGreater(built.find('compile_gateway_stdlib "$PREFIX/venv/bin/python"'), sync)
        self.assertIn('compile_gateway_stdlib "$PREFIX/venv/bin/python"',
                      function_body(script, "gateway_runtime_from_bundle"))

    def test_bundle_compiles_the_stdlib_into_the_runtime_tarball(self):
        script = BUNDLE.read_text(encoding="utf-8")
        comp = script.find("-m compileall")
        self.assertGreater(comp, script.index("uv sync --frozen --no-dev --no-editable --managed-python"))
        self.assertLess(comp, script.index("-czf /work/gateway-runtime.tar.gz"))
        self.assertIn('get_paths()[\\"stdlib\\"]', script)

    def test_image_still_compiles_it(self):
        self.assertIn("-m compileall", (ROOT / "os" / "rootfs" / "Containerfile").read_text(encoding="utf-8"))


@unittest.skipIf(os.name != "posix", "runs the shell function")
class CompileFunction(unittest.TestCase):
    """Runs install.sh's compile_gateway_stdlib against a stand-in stdlib directory."""

    def test_compiles_modules_and_skips_test_folders(self):
        body = function_body(INSTALL.read_text(encoding="utf-8"), "compile_gateway_stdlib")
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            std = t / "lib" / "python3.12"
            (std / "json").mkdir(parents=True)
            (std / "test").mkdir()
            (std / "json" / "__init__.py").write_text("X = 1\n")
            (std / "abc_mod.py").write_text("Y = 2\n")
            (std / "test" / "bad.py").write_text("this is not python (\n")  # excluded, so no failure
            # A stand-in for $PREFIX/venv/bin/python: reports `std` as its stdlib, runs the real compileall.
            py = t / "python"
            py.write_text(f"#!/bin/sh\nif [ \"$2\" = -c ]; then echo '{std}'; exit 0; fi\n"
                          f"exec '{sys.executable}' \"$@\"\n")
            py.chmod(py.stat().st_mode | stat.S_IXUSR)
            sh = f'die() {{ echo "DIE: $*" >&2; exit 1; }}\ncompile_gateway_stdlib() {{\n{body}}}\n' \
                 f'compile_gateway_stdlib "{py}"\n'
            r = subprocess.run(["bash", "-c", sh], capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(list((std / "json" / "__pycache__").glob("__init__.*.pyc")))
            self.assertTrue(list((std / "__pycache__").glob("abc_mod.*.pyc")))
            self.assertFalse((std / "test" / "__pycache__").exists())

    def test_a_compile_error_stops_the_install(self):
        body = function_body(INSTALL.read_text(encoding="utf-8"), "compile_gateway_stdlib")
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            std = t / "lib"
            std.mkdir()
            (std / "broken.py").write_text("def (\n")
            py = t / "python"
            py.write_text(f"#!/bin/sh\nif [ \"$2\" = -c ]; then echo '{std}'; exit 0; fi\n"
                          f"exec '{sys.executable}' \"$@\"\n")
            py.chmod(py.stat().st_mode | stat.S_IXUSR)
            sh = f'die() {{ echo "DIE: $*" >&2; exit 1; }}\ncompile_gateway_stdlib() {{\n{body}}}\n' \
                 f'compile_gateway_stdlib "{py}"\n'
            r = subprocess.run(["bash", "-c", sh], capture_output=True, text=True, timeout=60)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("DIE: could not compile", r.stderr)


if __name__ == "__main__":
    unittest.main()
