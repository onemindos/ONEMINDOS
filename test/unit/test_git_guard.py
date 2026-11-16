# SPDX-License-Identifier: Apache-2.0
"""scripts/git-guard.sh refuses a commit when core.worktree redirects the checkout (shared-config hazard)."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

GUARD = Path(__file__).resolve().parents[2] / "scripts" / "git-guard.sh"


def git(cwd, *a, env=None):
    e = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    e.update({"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t" + chr(64) + "t.invalid", "GIT_COMMITTER_NAME": "t",
              "GIT_COMMITTER_EMAIL": "t" + chr(64) + "t.invalid", **(env or {})})
    return subprocess.run(["git", *a], cwd=cwd, env=e, capture_output=True, text=True, check=True)


def guard(cwd):
    e = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(["sh", str(GUARD)], cwd=cwd, env=e, capture_output=True, text=True)


class GitGuard(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        root = Path(self.t.name).resolve()
        self.main, self.wt, self.other = root / "main", root / "wt", root / "other"
        self.main.mkdir(); self.other.mkdir()
        git(self.main, "init", "-q", "-b", "main")
        (self.main / "f").write_text("x")
        git(self.main, "add", "f"); git(self.main, "commit", "-q", "-m", "i")
        git(self.main, "worktree", "add", "-q", "-b", "side", str(self.wt))

    def test_clean_main_checkout_and_linked_worktree_pass(self):
        for d in (self.main, self.wt):
            r = guard(d)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_subfolder_passes(self):
        (self.wt / "sub").mkdir()
        self.assertEqual(guard(self.wt / "sub").returncode, 0)

    def test_core_worktree_in_the_shared_config_fails_every_worktree_with_the_fix(self):
        # What happened: the common config says every worktree lives in some other agent's folder.
        git(self.main, "config", "core.worktree", str(self.other))
        for d in (self.main, self.wt):
            r = guard(d)
            self.assertEqual(r.returncode, 1, (d, r.stderr))
            self.assertIn("core.worktree is set in the shared config", r.stderr)
            self.assertIn("--unset core.worktree", r.stderr)
        self.assertIn(str(self.other), guard(self.wt).stderr)

    def test_unsetting_it_makes_the_guard_pass_again(self):
        git(self.main, "config", "core.worktree", str(self.other))
        self.assertEqual(guard(self.wt).returncode, 1)
        git(self.main, "config", "--unset", "core.worktree")
        self.assertEqual(guard(self.wt).returncode, 0)

    def test_outside_a_checkout_fails(self):
        self.assertEqual(guard(self.other).returncode, 1)


class Documented(unittest.TestCase):
    def test_the_hook_one_liner_is_in_the_mac_dev_loop(self):
        doc = (GUARD.parents[1] / "docs" / "learning" / "mac-dev-loop.md").read_text()
        self.assertIn("scripts/git-guard.sh", doc)
        self.assertIn(".git/hooks/pre-commit", doc)


if __name__ == "__main__":
    unittest.main()
