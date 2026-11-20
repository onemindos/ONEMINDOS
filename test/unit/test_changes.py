# SPDX-License-Identifier: Apache-2.0
"""scripts/changes.py: fragment parsing, validation and collect (idempotent)."""
import importlib.util
import contextlib
import io
import json
import os
import subprocess
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
PAGE = """# Status

**Last updated:** 2000-01-01 (stale).

## Summary

| State | Epics |
|---|---|
| todo | 999 |

(Counted from the rows below on 2000-01-01. Re-count after editing rows; do not edit these numbers by hand.)

## Every epic

""" + ST + "| EPIC-1 | Duplicate | todo | old | old |\n"


class T(unittest.TestCase):
    def setUp(self):
        # Retain isolated fixtures for inspection; never delete test artifacts.
        r = Path(tempfile.mkdtemp(prefix="changes-test-"))
        self.original_paths = changes.CHANGES, changes.CHANGELOG, changes.STATUS
        self.original_root = changes.ROOT
        (r / "changes").mkdir()
        (r / "docs" / "leap").mkdir(parents=True)
        (r / "CHANGELOG.md").write_text(CL)
        (r / "docs" / "leap" / "STATUS.md").write_text(ST)
        changes.CHANGES = str(r / "changes")
        changes.CHANGELOG = str(r / "CHANGELOG.md")
        changes.STATUS = str(r / "docs" / "leap" / "STATUS.md")
        self.r = r

    def tearDown(self):
        changes.CHANGES, changes.CHANGELOG, changes.STATUS = self.original_paths
        changes.ROOT = self.original_root

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-C", str(self.r), "-c", "user.name=Test builder",
             "-c", "user.email=builder.invalid", *args], text=True).strip()

    def snapshot(self):
        (self.r / "docs/leap/STATUS.md").write_text(PAGE)
        self.put("feat-x.md", GOOD)
        self.git("init", "-b", "main")
        self.git("add", ".")
        self.git("commit", "-s", "-m", "test source snapshot")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        changes.ROOT = str(self.r)
        return self.git("rev-parse", "HEAD")

    def test_preview_uses_committed_main_and_reports_row_counts_not_audit(self):
        sha = self.snapshot()
        # Neither uncommitted edits nor a committed unmerged branch may leak in.
        self.git("checkout", "-b", "feature")
        self.put("feat-x.md", GOOD.replace("in-review", "done"))
        self.git("add", ".")
        self.git("commit", "-s", "-m", "unmerged change")
        (self.r / "docs/leap/STATUS.md").write_text("dirty source, preserve me")
        before = {p: p.read_bytes() for p in self.r.rglob("*.md")}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(changes.main(["changes.py", "preview"]), 0)
        data = json.loads(out.getvalue())
        self.assertEqual(data["source"], sha)
        self.assertEqual(data["counts"], {"in-review": 2})
        self.assertEqual(data["rows"], 2)
        self.assertEqual(data["unique_ids"], 1)
        self.assertEqual(data["updated_rows"], 2)
        self.assertIn("| in-review | 2 |", data["status"])
        self.assertIn("not a full row truth audit", data["status"])
        self.assertIn(sha, data["status"])
        self.assertNotIn("2000-01-01", data["status"])
        # The stale summary row of the fixture, not the bare digits: a random commit SHA can hold "999".
        self.assertNotIn("| todo | 999 |", data["status"])
        self.assertEqual(before, {p: p.read_bytes() for p in self.r.rglob("*.md")})

    def test_status_updates_every_duplicate_without_removing_rows(self):
        text = ST + "| EPIC-1 | Duplicate | todo | old | old |\n"
        result = changes.apply_status(text, [changes.parse(GOOD)])
        self.assertEqual(result.count("| EPIC-1 |"), 2)
        self.assertEqual(result.count("| in-review |"), 2)
        self.assertNotIn("| todo |", result)

    def test_pending_pr_does_not_keep_an_unrelated_old_pr(self):
        text = ST.replace("| – | – |", "| old | [#99](old) |")
        result = changes.apply_status(text, [changes.parse(GOOD.replace("pr: 12", "pr: pending"))])
        self.assertIn("| PR pending |", result)
        self.assertNotIn("[#99]", result)

    def test_preview_rejects_same_landing_conflicting_row_declarations(self):
        self.snapshot()
        self.put("aaa-other.md", GOOD.replace("feat/x", "aaa/other").replace("in-review", "done"))
        self.put("feat-x.md", GOOD.replace("note here", "same landing edit"))
        self.git("add", ".")
        self.git("commit", "-s", "-m", "ambiguous declarations")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.assertEqual(changes.main(["changes.py", "preview"]), 1)

    def test_generate_retains_fragments_and_is_idempotent(self):
        self.snapshot()
        fragments = {p: p.read_bytes() for p in (self.r / "changes").glob("*.md")}
        self.assertEqual(changes.main(["changes.py", "generate"]), 0)
        status = (self.r / "docs/leap/STATUS.md").read_text()
        self.assertIn("| in-review | 2 |", status)
        self.assertEqual(changes.main(["changes.py", "generate"]), 0)
        self.assertEqual(status, (self.r / "docs/leap/STATUS.md").read_text())
        self.assertEqual(fragments, {p: p.read_bytes() for p in (self.r / "changes").glob("*.md")})

    def test_preview_newest_main_fragment_wins_not_filename(self):
        self.snapshot()
        self.put("aaa-newer.md", GOOD.replace("feat/x", "aaa/newer").replace("in-review", "in-progress"))
        self.git("add", ".")
        self.git("commit", "-s", "-m", "newer partial slice")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(changes.main(["changes.py", "preview"]), 0)
        self.assertEqual(json.loads(out.getvalue())["counts"], {"in-progress": 2})

    def test_nightly_workflow_preserves_sources_and_waits_for_gate(self):
        workflow = (ROOT / ".github/workflows/changes-collect.yml").read_text()
        self.assertIn("cron: '23 5 * * *'", workflow)
        self.assertIn("if: github.ref == 'refs/heads/main'", workflow)
        self.assertIn("run: python3 -I scripts/changes.py generate", workflow)
        self.assertIn("git add CHANGELOG.md docs/leap/STATUS.md", workflow)
        self.assertIn("git merge-base --is-ancestor", workflow)
        self.assertNotIn("scripts/changes.py collect", workflow)
        self.assertNotIn("git merge --", workflow)

    def test_generate_refuses_dirty_targets_before_any_write(self):
        self.snapshot()
        target = self.r / "docs/leap/STATUS.md"
        target.write_text("preserve foreign edit")
        before = {p: p.read_bytes() for p in self.r.rglob("*.md")}
        self.assertEqual(changes.main(["changes.py", "generate"]), 1)
        self.assertEqual(before, {p: p.read_bytes() for p in self.r.rglob("*.md")})

    def test_generate_refuses_feature_checkout(self):
        self.snapshot()
        self.put("feat-x.md", GOOD.replace("in-review", "done"))
        self.git("add", ".")
        self.git("commit", "-s", "-m", "unmerged change")
        before = {p: p.read_bytes() for p in self.r.rglob("*.md")}
        self.assertEqual(changes.main(["changes.py", "generate"]), 1)
        self.assertEqual(before, {p: p.read_bytes() for p in self.r.rglob("*.md")})

    def test_counts_include_suffixes_review_alias_and_untouched_rows(self):
        text = PAGE + "| OTHER | Untouched | done (partial) | old | old |\n"
        text += "| THIRD | Untouched | review | old | old |\n"
        text += "| FOURTH | Untouched | parked | old | old |\n"
        self.assertEqual(changes.epic_rows(text), [
            ("EPIC-1", "todo"), ("EPIC-1", "todo"),
            ("OTHER", "done"), ("THIRD", "in-review"), ("FOURTH", "parked")])

    def test_preview_rejects_unknown_states_and_invalid_main_fragments(self):
        self.snapshot()
        with self.assertRaises(changes.FragmentError):
            changes.epic_rows(PAGE.replace("| todo |", "| invented |"))
        self.put("feat-x.md", GOOD.replace("EPIC-1", "UNKNOWN"))
        self.git("add", ".")
        self.git("commit", "-s", "-m", "invalid source")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.assertEqual(changes.main(["changes.py", "preview"]), 1)

    def test_preview_missing_main_fails_closed(self):
        self.git("init", "-b", "main")
        changes.ROOT = str(self.r)
        self.assertEqual(changes.main(["changes.py", "preview"]), 1)

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
        self.assertEqual(changes.main(["changes.py", "collect", "--preserve"]), 0)
        cl = (self.r / "CHANGELOG.md").read_text()
        self.assertIn("| `feat/x` | [#12](", cl)
        self.assertLess(cl.index("`feat/x`"), cl.index("`old/one`"))
        st = (self.r / "docs" / "leap" / "STATUS.md").read_text()
        self.assertIn("in-review", st)
        self.assertIn("note here", st)
        self.assertEqual((self.r / "changes" / "feat-x.md").read_text(), GOOD)
        self.assertEqual(changes.main(["changes.py", "collect", "--preserve"]), 0)
        self.assertEqual((self.r / "CHANGELOG.md").read_text(), cl)

    def test_collect_replaces_same_branch(self):
        self.put("old-one.md", "---\npr: pending\nbranch: old/one\n---\nNew text.\n")
        self.assertEqual(changes.main(["changes.py", "collect", "--preserve"]), 0)
        cl = (self.r / "CHANGELOG.md").read_text()
        self.assertEqual(cl.count("`old/one`"), 1)
        self.assertIn("New text.", cl)

    def test_real_fragments_valid(self):
        changes.CHANGES = str(ROOT / "changes")
        changes.STATUS = str(ROOT / "docs" / "leap" / "STATUS.md")
        self.assertEqual(changes.cmd_check(), 0)


if __name__ == "__main__":
    unittest.main()
