# SPDX-License-Identifier: Apache-2.0
"""D-010: the online TUF keys are secrets of the GitHub Environment `tuf-signing`, and nothing else reads them.

Run: python3 -I -m unittest test/unit/test_tuf_secrets.py (stdlib only, runs on every PR).
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKFLOWS = os.path.join(ROOT, ".github", "workflows")
NIGHTLY = "security-nightly.yml"
ENVIRONMENT = "tuf-signing"
TUF_SECRET = re.compile(r"ONEMIND_TUF_[A-Z_]*KEY")


def jobs(text):
    """{job id: its text} for a workflow file (two-space-indented keys under `jobs:`)."""
    body = text.split("\njobs:\n", 1)[1]
    parts = re.split(r"(?m)^  ([a-z][a-z0-9_-]*):\s*$", body)
    return dict(zip(parts[1::2], parts[2::2]))


class TufSecrets(unittest.TestCase):
    def test_no_workflow_but_the_nightly_reads_the_tuf_keys(self):
        for name in sorted(os.listdir(WORKFLOWS)):
            if name == NIGHTLY or not name.endswith((".yml", ".yaml")):
                continue
            with open(os.path.join(WORKFLOWS, name)) as f:
                hits = [i + 1 for i, line in enumerate(f) if TUF_SECRET.search(line)]
            self.assertEqual(hits, [], f"{name} mentions an online TUF key at line(s) {hits}: only {NIGHTLY} may, "
                                       f"inside the {ENVIRONMENT} environment (D-010)")

    def test_every_nightly_job_that_reads_a_tuf_key_is_in_the_environment(self):
        with open(os.path.join(WORKFLOWS, NIGHTLY)) as f:
            found = jobs(f.read())
        readers = {j for j, t in found.items() if re.search(r"secrets\.ONEMIND_TUF_[A-Z_]*KEY", t)}
        self.assertEqual(readers, {"decide", "tuf", "timestamp"}, "a job started or stopped reading the TUF keys: review it")
        for job in sorted(readers):
            self.assertRegex(found[job], rf"(?m)^    environment: {ENVIRONMENT}\b", f"job {job} reads the TUF keys outside {ENVIRONMENT}")

    def test_the_root_key_is_never_a_secret(self):
        for name in sorted(os.listdir(WORKFLOWS)):
            with open(os.path.join(WORKFLOWS, name)) as f:
                self.assertNotRegex(f.read().replace("**Deliberately", ""), r"secrets\.ONEMIND_TUF_ROOT", name)

    def test_the_job_splitter_finds_the_nightly_jobs(self):
        with open(os.path.join(WORKFLOWS, NIGHTLY)) as f:
            self.assertTrue({"unit", "check", "decide", "build", "tuf", "publish", "timestamp"} <= set(jobs(f.read())))


if __name__ == "__main__":
    unittest.main()
