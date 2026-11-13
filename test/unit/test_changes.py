# SPDX-License-Identifier: Apache-2.0
"""scripts/changes.py: fragment parsing, validation and collect (idempotent)."""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("changes", ROOT / "scripts" / "changes.py")
changes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(changes)

GOOD = """---
pr: 12
branch: feat/x
status_rows:
  - EPIC-1 | in-review | note here
---
Adds x.
"""
CL = """# Changelog

## Unreleased / in progress

| Branch | PR | What it adds |
|---|---|---|
| `old/one` | – | Old. |

## 2026-11-12
"""
ST = """| ID | What | State | Branch | PR |
|---|---|---|---|---|
| EPIC-1 | Thing | todo | – | – |
"""


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        r = Path(self.d.name)
        (r / "changes").mkdir()
        (r / "docs" / "leap").mkdir(parents=True)
        (r / "CHANGELOG.md").write_text(CL)
        (r / "docs" / "leap" / "STATUS.md").write_text(ST)
        changes.CHANGES = str(r / "changes")
        changes.CHANGELOG = str(r / "CHANGELOG.md")
        changes.STATUS = str(r / "docs" / "leap" / "STATUS.md")
        self.r = r

    def tearDown(self):
        self.d.cleanup()

    def put(self, name, text):
        (self.r / "changes" / name).write_text(text)

    def test_parse(self):
        meta, body = changes.parse(GOOD)
        self.assertEqual(meta["branch"], "feat/x")
        self.assertEqual(meta["status_rows"], [("EPIC-1", "in-review", "note here")])
        self.assertEqual(body, "Adds x.")

    def test_validate_errors(self):
        self.put("wrong.md", GOOD)
        _, _, errs = changes.validate(str(self.r / "changes" / "wrong.md"), {"EPIC-1"})
        self.assertTrue(any("file name" in e for e in errs))
        self.put("feat-x.md", GOOD.replace("pr: 12", "pr: soon").replace("Adds x.", "a | b").replace("EPIC-1 | in-review", "NOPE | wat"))
        _, _, errs = changes.validate(str(self.r / "changes" / "feat-x.md"), {"EPIC-1"})
        text = " ".join(errs)
        for want in ("pr must", "'|'", "unknown state", "no such ID"):
            self.assertIn(want, text)

    def test_missing_front_matter(self):
        self.put("a.md", "no front matter")
        self.assertEqual(changes.cmd_check(), 1)

    def test_collect_idempotent(self):
        self.put("feat-x.md", GOOD)
        self.assertEqual(changes.cmd_check(), 0)
        self.assertEqual(changes.cmd_collect(), 0)
        cl = (self.r / "CHANGELOG.md").read_text()
        self.assertIn("| `feat/x` | [#12](", cl)
        self.assertLess(cl.index("`feat/x`"), cl.index("`old/one`"))
        st = (self.r / "docs" / "leap" / "STATUS.md").read_text()
        self.assertIn("in-review", st)
        self.assertIn("note here", st)
        self.assertFalse((self.r / "changes" / "feat-x.md").exists())
        self.assertEqual(changes.cmd_collect(), 0)
        self.assertEqual((self.r / "CHANGELOG.md").read_text(), cl)

    def test_collect_replaces_same_branch(self):
        self.put("old-one.md", "---\npr: pending\nbranch: old/one\n---\nNew text.\n")
        self.assertEqual(changes.cmd_collect(), 0)
        cl = (self.r / "CHANGELOG.md").read_text()
        self.assertEqual(cl.count("`old/one`"), 1)
        self.assertIn("New text.", cl)

    def test_real_fragments_valid(self):
        changes.CHANGES = str(ROOT / "changes")
        changes.STATUS = str(ROOT / "docs" / "leap" / "STATUS.md")
        self.assertEqual(changes.cmd_check(), 0)


if __name__ == "__main__":
    unittest.main()
