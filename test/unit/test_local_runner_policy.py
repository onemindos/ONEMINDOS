# SPDX-License-Identifier: Apache-2.0
"""CI-10 (issue 299): the local Mac runner takes trusted, secret-free jobs only.

A job may pick the `onemind-local` runner only if (1) the choice is behind the LOCAL_RUNNER switch with a
GitHub-hosted fallback, (2) a pull request from a fork can never select it, and (3) nothing in the job,
or in its workflow's top level, can read a secret or an environment.
"""
import json
import re
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"
KIT = ROOT / "scripts" / "ci-runner"
SECRET_USE = re.compile(r"secrets\.(?!GITHUB_TOKEN\b)|secrets:\s*inherit|toJSON\(secrets\)", re.I)


def local_jobs():
    for p in sorted(WF.glob("*.yml")):
        d = yaml.safe_load(p.read_text())
        for name, job in d["jobs"].items():
            if "onemind-local" in str(job.get("runs-on", "")):
                yield p.name, d, name, job


class LocalRunnerPolicy(unittest.TestCase):
    def test_some_jobs_use_the_local_runner(self):
        self.assertTrue(list(local_jobs()), "CI-10 moved no job to the local runner")

    def test_selection_is_switchable_fork_safe_and_has_a_hosted_fallback(self):
        for wf, d, name, job in local_jobs():
            ro = job["runs-on"]
            where = f"{wf}:{name}"
            self.assertIn("vars.LOCAL_RUNNER == 'on'", ro, where)
            self.assertIn("github.event.pull_request.head.repo.full_name == github.repository", ro, where)
            self.assertIn("github.event_name != 'pull_request'", ro, where)
            self.assertRegex(ro, r"\|\| 'ubuntu-24\.04' \}\}$", where)

    def test_no_job_that_can_pick_the_local_runner_can_read_a_secret(self):
        for wf, d, name, job in local_jobs():
            where = f"{wf}:{name}"
            self.assertNotRegex(json.dumps(job), SECRET_USE, where)
            self.assertNotRegex(json.dumps(d.get("env", {})), SECRET_USE, f"{wf} top-level env")
            self.assertNotIn("environment", job, where)
            self.assertNotIn("docker/login-action", json.dumps(job), where)
            self.assertNotIn("uses", job, f"{where} calls a reusable workflow that could use secrets")

    def test_the_local_runner_is_never_used_by_release_signing_or_deploy_workflows(self):
        for wf, d, name, job in local_jobs():
            self.assertNotIn(wf, {"release.yml", "security-nightly.yml", "apps-rescan.yml", "changes-collect.yml"})

    def test_jobs_with_secrets_stay_hosted(self):
        for p in sorted(WF.glob("*.yml")):
            for name, job in yaml.safe_load(p.read_text())["jobs"].items():
                if SECRET_USE.search(json.dumps(job)):
                    self.assertNotIn("onemind-local", str(job.get("runs-on", "")), f"{p.name}:{name}")


class Kit(unittest.TestCase):
    def test_scripts_exist_and_parse(self):
        for f in ("up", "down", "status", "cycle", "provision.sh", "run-one.sh"):
            path = KIT / f
            self.assertTrue(path.is_file(), f)
            self.assertTrue(path.stat().st_mode & 0o111, f"{f} is not executable")
            subprocess.run(["bash", "-n", str(path)], check=True)

    def test_no_token_is_stored_in_the_kit(self):
        for p in KIT.iterdir():
            text = p.read_text()
            self.assertNotRegex(text, r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_|AAAA[A-Z0-9]{20,}", p.name)

    def test_runners_are_ephemeral_and_labelled(self):
        text = (KIT / "run-one.sh").read_text()
        self.assertIn("--ephemeral", text)
        self.assertIn("--labels onemind-local", text)

    def test_vm_shares_nothing_with_the_mac(self):
        self.assertRegex((KIT / "lima.yaml").read_text(), r"(?m)^mounts: \[\]$")

    def test_launchd_plist_has_no_host_path(self):
        text = (KIT / "dev.onemind.ci-runner.plist").read_text()
        self.assertNotRegex(text, r"/Users/|/home/")
        self.assertIn("__CYCLE__", text)


if __name__ == "__main__":
    unittest.main()
