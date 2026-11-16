# SPDX-License-Identifier: Apache-2.0
"""Main's required checks match by job name (dco, hygiene, lint, unit, merge-gate).

A job with one of those names in another workflow, when it fails or is cancelled, blocks every PR the
same way the real one does (security-nightly's `unit` blocked #300; ci-deploy and e2e had the same problem). Only the workflow that
owns each required check may use its name.
"""
import unittest
from pathlib import Path

import yaml

WF = Path(__file__).resolve().parents[2] / ".github" / "workflows"
OWNER = {"dco": "ci.yml", "lint": "ci.yml", "unit": "ci.yml", "hygiene": "hygiene.yml", "merge-gate": "gate.yml"}


class RequiredNames(unittest.TestCase):
    def test_only_the_owner_uses_a_required_check_name(self):
        for p in sorted(WF.glob("*.yml")):
            for job, spec in (yaml.safe_load(p.read_text()).get("jobs") or {}).items():
                for name in {job, str((spec or {}).get("name", job))}:
                    if name in OWNER:
                        self.assertEqual(p.name, OWNER[name], f"{p.name}: job {job!r} is named like required check {name!r}")

    def test_owners_still_have_their_jobs(self):
        for name, owner in OWNER.items():
            self.assertIn(name, yaml.safe_load((WF / owner).read_text())["jobs"], f"{owner} lost {name}")


if __name__ == "__main__":
    unittest.main()
