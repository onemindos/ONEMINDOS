# SPDX-License-Identifier: Apache-2.0
"""scripts/release/check-image-run.py (#880): the release android job builds a commit with the Android upload key
in its environment, so it trusts an image.yml run only when it is this repo's own successful push or manual run
and its commit is on origin/main or origin/release/next. One test per refusal, against a throwaway git repo."""
import json, os, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "release", "check-image-run.py")
REPO = "onemindos/ONEMINDOS"
RUN_ID = "4242"


def git_env():
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@example.invalid", GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    return env


class CheckImageRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.git = os.path.join(cls.tmp.name, "clone")

        def g(*args):
            return subprocess.run(["git", "-C", cls.git, *args], check=True, capture_output=True, text=True,
                                  env=git_env()).stdout.strip()

        os.makedirs(cls.git)
        g("init", "-q", "-b", "work")

        def commit(msg):
            g("commit", "-q", "--allow-empty", "--no-gpg-sign", "-m", msg)
            return g("rev-parse", "HEAD")

        cls.on_main = commit("reviewed on main")
        g("update-ref", "refs/remotes/origin/main", cls.on_main)
        cls.on_next = commit("reviewed on release/next")
        g("update-ref", "refs/remotes/origin/release/next", cls.on_next)
        cls.unmerged = commit("a branch nobody merged")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_json(self, **over):
        run = {"id": int(RUN_ID), "name": "image", "path": ".github/workflows/image.yml", "event": "push",
               "status": "completed", "conclusion": "success", "head_sha": self.on_main,
               "head_repository": {"full_name": REPO}}
        run.update(over)
        return run

    def check(self, run, run_id=RUN_ID, repo=REPO):
        p = os.path.join(self.tmp.name, "run.json")
        with open(p, "w", encoding="utf-8") as f:
            f.write(run if isinstance(run, str) else json.dumps(run))
        return subprocess.run([sys.executable, "-I", SCRIPT, "--run-json", p, "--run-id", run_id, "--repo", repo,
                               "--git", self.git], capture_output=True, text=True)

    def assertRefused(self, r, why):
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(r.stdout, "")                      # no commit is handed to the build
        self.assertIn("REFUSED", r.stderr)
        self.assertIn(why, r.stderr)

    # accepted

    def test_push_run_on_main_passes_and_prints_its_commit(self):
        r = self.check(self.run_json())
        self.assertEqual((r.returncode, r.stdout.strip()), (0, self.on_main), r.stderr)

    def test_manual_run_on_release_next_passes(self):
        r = self.check(self.run_json(event="workflow_dispatch", head_sha=self.on_next))
        self.assertEqual((r.returncode, r.stdout.strip()), (0, self.on_next), r.stderr)

    def test_path_with_a_ref_suffix_is_still_image_yml(self):
        self.assertEqual(self.check(self.run_json(path=".github/workflows/image.yml@refs/heads/main")).returncode, 0)

    # refused

    def test_pull_request_run_is_refused(self):
        self.assertRefused(self.check(self.run_json(event="pull_request")), "'pull_request'")

    def test_pull_request_target_run_is_refused(self):
        self.assertRefused(self.check(self.run_json(event="pull_request_target")), "'pull_request_target'")

    def test_fork_run_is_refused(self):
        r = self.check(self.run_json(head_repository={"full_name": "someone/ONEMINDOS"}))
        self.assertRefused(r, "someone/ONEMINDOS")

    def test_missing_head_repository_is_refused(self):
        self.assertRefused(self.check(self.run_json(head_repository=None)), "unknown repository")

    def test_another_workflow_is_refused(self):
        self.assertRefused(self.check(self.run_json(name="ci", path=".github/workflows/ci.yml")), "not the image")

    def test_a_workflow_only_named_image_is_refused(self):
        self.assertRefused(self.check(self.run_json(path=".github/workflows/evil.yml")), "not the image")

    def test_image_yml_under_another_name_is_refused(self):
        self.assertRefused(self.check(self.run_json(name="images")), "not the image")

    def test_failed_run_is_refused(self):
        self.assertRefused(self.check(self.run_json(conclusion="failure")), "completed/failure")

    def test_cancelled_run_is_refused(self):
        self.assertRefused(self.check(self.run_json(conclusion="cancelled")), "completed/cancelled")

    def test_unfinished_run_is_refused(self):
        self.assertRefused(self.check(self.run_json(status="in_progress", conclusion=None)), "in_progress/None")

    def test_commit_on_no_reviewed_branch_is_refused(self):
        self.assertRefused(self.check(self.run_json(head_sha=self.unmerged)), "not on origin/main or origin/release/next")

    def test_unknown_commit_is_refused(self):
        self.assertRefused(self.check(self.run_json(head_sha="a" * 40)), "not on origin/main")

    def test_short_or_missing_commit_is_refused(self):
        self.assertRefused(self.check(self.run_json(head_sha=self.on_main[:12])), "no full commit")
        self.assertRefused(self.check(self.run_json(head_sha=None)), "no full commit")

    def test_branch_name_instead_of_commit_is_refused(self):
        self.assertRefused(self.check(self.run_json(head_sha="origin/main")), "no full commit")

    def test_non_numeric_run_id_is_refused(self):
        self.assertRefused(self.check(self.run_json(), run_id="4242/../../other"), "not a number")

    def test_details_for_another_run_are_refused(self):
        self.assertRefused(self.check(self.run_json(id=9999)), "not for run 4242")

    def test_unreadable_details_are_refused(self):
        self.assertRefused(self.check("{not json"), "cannot read the run details")

    def test_caller_git_dir_is_ignored(self):
        # A GIT_DIR set by the caller must not point the reachability check at another repository.
        p = os.path.join(self.tmp.name, "run.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.run_json(), f)
        env = dict(os.environ, GIT_DIR=os.path.join(self.tmp.name, "nowhere"))
        r = subprocess.run([sys.executable, "-I", SCRIPT, "--run-json", p, "--run-id", RUN_ID, "--repo", REPO,
                            "--git", self.git], capture_output=True, text=True, env=env)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, self.on_main), r.stderr)


if __name__ == "__main__":
    unittest.main()
