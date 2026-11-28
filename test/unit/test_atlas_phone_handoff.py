# SPDX-License-Identifier: Apache-2.0
"""Guard the Atlas phone implementation handoff for issues #1225–#1227."""

from pathlib import Path
import unittest


HANDOFF = Path(__file__).resolve().parents[2] / "docs/design/atlas-phone"


class AtlasPhoneHandoffTest(unittest.TestCase):
    def test_approval_card_controls_all_three_surfaces(self):
        for filename in ("README.md", "CODEX-PROMPT.md"):
            with self.subTest(filename=filename):
                text = (HANDOFF / filename).read_text(encoding="utf-8")
                for instruction in (
                    "approval-card object with explicit `hold: false` permits normal signed approval",
                    "missing or null card, a legacy string, or a card without an explicit boolean",
                    "Home shows the hold note",
                    "Approvals uses the hold control",
                    "App page sends the owner to Approvals",
                ):
                    self.assertIn(instruction, text, instruction)

        readme = (HANDOFF / "README.md").read_text(encoding="utf-8")
        self.assertIn("**Hold required** when the card is unavailable or incomplete", readme)
        self.assertIn("When the shared rule permits normal approval, show the signed", readme)
        self.assertNotIn("for a physical or irreversible request the note", readme)

    def test_held_request_supports_planless_actions_and_binds_physical_approval(self):
        for filename in ("README.md", "CODEX-PROMPT.md"):
            with self.subTest(filename=filename):
                text = (HANDOFF / filename).read_text(encoding="utf-8")
                for instruction in (
                    "fetch bound approval options before sending",
                    "generated SDK approve body",
                    "`hold_ms` even when it is the only field",
                    "When the action has a plan, require the bound `plan_sha256` to match the displayed plan",
                    "requires both the matching plan hash and a WebAuthn assertion",
                    "`webauthn` or `device_signature`",
                ):
                    self.assertIn(instruction, text, instruction)
                self.assertNotRegex(text, r"must send(?:\*\*)? `hold_ms` and `plan_sha256`")
                self.assertNotIn("send only `plan_sha256`", text)

    def test_prompt_uses_issue_branch_and_linux_worker_checks(self):
        prompt = (HANDOFF / "CODEX-PROMPT.md").read_text(encoding="utf-8")
        self.assertIn('git switch -c "feat/$issue_key" origin/release/next', prompt)
        self.assertNotIn("git switch -c feat/phone-atlas-home", prompt)
        self.assertIn("current issue's `om-remote` command", prompt)
        self.assertIn("Linux and Node 22 before generating the SDK", prompt)
        self.assertNotIn("npm ci", prompt)
        self.assertNotIn("npx jest", prompt)
