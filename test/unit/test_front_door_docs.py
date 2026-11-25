# SPDX-License-Identifier: Apache-2.0
"""The front-door docs must not claim a repository visibility they cannot know."""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CLAIM = re.compile(r"(access: private repository|this repository is private|repository is private today|clone it\.)", re.I)


class FrontDoorDocs(unittest.TestCase):
    def read(self, name):
        return (ROOT / name).read_text(encoding="utf-8")

    def test_no_private_repository_claim(self):
        for name in ("README.md", "SECURITY.md", "CONTRIBUTING.md"):
            self.assertIsNone(CLAIM.search(self.read(name)), name)

    def test_security_has_public_reporting_path(self):
        text = self.read("SECURITY.md")
        self.assertIn("private vulnerability reporting", text.lower())
        self.assertIn("Report a vulnerability", text)
        self.assertNotIn("works only on public repositories", text)


if __name__ == "__main__":
    unittest.main()
