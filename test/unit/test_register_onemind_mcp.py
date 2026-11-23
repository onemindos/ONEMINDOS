# SPDX-License-Identifier: Apache-2.0
"""The MCP registration script uses the saved OneMind context for each client."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "register-onemind-mcp.sh"


class MCPRegistrationTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.log = root / "calls"
        self.env = {
            **os.environ,
            "PATH": str(root),
            "REGISTRATION_LOG": str(self.log),
            "ONEMIND_TOKEN": "dummy-inherited-token",
            "ONEMIND_HUB": "dummy-inherited-hub",
        }
        for command in ("onemind", "claude", "codex"):
            path = root / command
            path.write_text(
                '#!/bin/sh\n'
                '[ -z "${ONEMIND_TOKEN+x}${ONEMIND_HUB+x}" ] || exit 90\n'
                'printf "%s\\n" "${0##*/} $*" >> "$REGISTRATION_LOG"\n'
                '[ "${0##*/}" != onemind ] || exit "${DOCTOR_RESULT:-0}"\n',
                encoding="utf-8",
            )
            path.chmod(0o755)

    def register(self, client, context="workstation-agent"):
        return subprocess.run([SCRIPT, client, context], env=self.env, capture_output=True)

    def test_registration_uses_saved_agent_context_for_both_clients(self):
        self.assertEqual(self.register("claude").returncode, 0)
        self.assertEqual(self.register("codex").returncode, 0)
        self.assertEqual(
            self.log.read_text(encoding="utf-8").splitlines(),
            [
                "onemind mcp doctor --context workstation-agent",
                "claude mcp add --scope user onemind -- onemind mcp --context workstation-agent",
                "onemind mcp doctor --context workstation-agent",
                "codex mcp add onemind -- onemind mcp --context workstation-agent",
            ],
        )

    def test_failed_doctor_prevents_registration(self):
        self.env["DOCTOR_RESULT"] = "4"
        self.assertEqual(self.register("codex").returncode, 4)
        self.assertEqual(
            self.log.read_text(encoding="utf-8"),
            "onemind mcp doctor --context workstation-agent\n",
        )

    def test_invalid_context_prevents_registration(self):
        self.assertEqual(self.register("claude", "--invalid").returncode, 2)
        self.assertFalse(self.log.exists())
