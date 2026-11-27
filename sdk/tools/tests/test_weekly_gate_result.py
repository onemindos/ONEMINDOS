# SPDX-License-Identifier: Apache-2.0
"""Exercise the weekly gate step under the same error handling as an Actions shell."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/apps-gate-all.yml").read_text())
STEP = next(step["run"] for step in WORKFLOW["jobs"]["gate"]["steps"]
            if step.get("name", "").startswith("App gate ("))


class GateResultTests(unittest.TestCase):
    def test_result_is_recorded_for_pass_failure_and_tool_error(self):
        for code in (0, 1, 2):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "out"
                out.mkdir()
                env = dict(os.environ, RUNNER_TEMP=tmp, APP="ntfy", ARCH="arm64", RUNNER_LABEL="ubuntu-24.04-arm",
                           CASE_CODE=str(code), TEST_PYTHON=sys.executable)
                stub = '''python3() {
                  if [ "$1" = "-I" ]; then echo "gate result"; return "$CASE_CODE"; fi
                  "$TEST_PYTHON" "$@"
                }
                '''
                run = subprocess.run(["bash", "-eo", "pipefail", "-c", stub + STEP], env=env,
                                     text=True, capture_output=True)
                self.assertEqual(run.returncode, code, run.stderr)
                self.assertEqual(json.loads((out / "status.json").read_text()),
                                 {"app": "ntfy", "arch": "arm64", "runner": "ubuntu-24.04-arm", "rc": code})
                self.assertEqual((out / "gate.log").read_text(), "gate result\n")
