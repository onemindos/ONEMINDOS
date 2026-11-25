# SPDX-License-Identifier: Apache-2.0
"""sdk/tools/subject-lint (issue #600): code may only name subjects that are in the subject tree.

Runs the real tool as CI does (python3 -I), on small trees written here and on the repo itself.
Stdlib only, so it runs under `python3 -I -m unittest discover -s sdk/tools/tests`.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TOOL = REPO / "sdk" / "tools" / "subject-lint"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", str(TOOL), *args], capture_output=True, text=True, timeout=120)


class SubjectLint(unittest.TestCase):
    def tree(self, files: dict[str, str]) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for rel, body in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(body)
        return root

    def test_the_repo_names_only_registered_subjects(self):
        r = run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("subject-lint: ok", r.stdout)

    def test_unregistered_subjects_fail_with_file_line_and_reason(self):
        root = self.tree({
            "svc/bad.py": 'AUDIT_SUBJECT = "onemind.audit"\nASSET_SUBJECT = "onemind.assets.camera.x.state"\n',
            "svc/bad.go": 'func Subject(id string) string { return fmt.Sprintf("onemind.app.%s.events", id) }\n',
            "svc/bad.ts": 'const subject = `onemind.cmd.${id}.reboot`;\n',
        })
        r = run("--root", str(root), "svc")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("svc/bad.py:2: 'onemind.assets.camera.x.state': unknown kind 'assets'", r.stdout)
        self.assertIn("svc/bad.go:1: 'onemind.app.%s.events': kind 'app' is reserved", r.stdout)
        self.assertIn("svc/bad.ts:1: 'onemind.cmd.${id}.reboot': kind 'cmd' is reserved", r.stdout)
        self.assertNotIn("bad.py:1", r.stdout)  # onemind.audit is registered

    def test_holes_prefixes_schema_ids_comments_and_tests_are_understood(self):
        root = self.tree({
            "svc/ok.py": ('NODE_SUBJECT = f"onemind.node.{node_id}.status"\n'
                          'SUBJECT_PREFIX = "onemind.event."\n'
                          'SUBJECT_ROOT = "onemind.plugin"\n'
                          'SCHEMA = "onemind.event/v1"  # subject envelope id, not a subject\n'
                          '# a comment about subject "onemind.nope.x"\n'
                          'REGISTRY = "onemind.subjects.json"  # subject registry file\n'),
            "svc/ok.go": 'nc.Subscribe("onemind.node.*.event.>", h)\n',
            "svc/test_x.py": 'SUBJECT = "onemind.nope.x"\n',
            "svc/x_test.go": 'subject := "onemind.nope.x"\n',
        })
        r = run("--root", str(root), "svc")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
