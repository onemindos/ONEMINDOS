# SPDX-License-Identifier: Apache-2.0
"""api-fuzz seeds (founder decision 2026-11-25): gated runs are deterministic, the nightly explores.

Locks in .github/workflows/api-fuzz.yml so nobody silently drops a part of it:
  - pull_request, merge_group and push to main fuzz with the committed API_FUZZ_SEED, one worker and
    no example database, with today's budgets, both roles, every check and the custom hooks;
  - the nightly schedule and a manual run draw a random seed (or replay a given one), print it, fuzz
    the larger budget, and on a failure ONE "api-fuzz nightly finding" issue is opened or commented
    on, by the only job that may write issues;
  - scripts/api-fuzz-finding.py writes that issue's seed, endpoint, check and reproduce commands.
"""
import importlib.util
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows" / "api-fuzz.yml"
SCRIPT = ROOT / "scripts" / "api-fuzz-finding.py"
TITLE = "api-fuzz nightly finding"
GATED = ("pull_request", "merge_group", "push")
EXPLORE = ("schedule", "workflow_dispatch")


def load():
    d = yaml.safe_load(WF.read_text())
    return d, d.get(True) or d.get("on")  # PyYAML reads the bare key `on` as True


def finding_module():
    spec = importlib.util.spec_from_file_location("api_fuzz_finding", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def evaluate(expr: str, event: str):
    """Evaluate a `${{ }}` expression made only of github.event_name comparisons, && and || and literals."""
    m = re.fullmatch(r"\$\{\{(.*)\}\}", str(expr).strip())
    assert m, f"not a single expression: {expr}"
    body = m.group(1)
    pattern = r"github\.event_name|'[^']*'|\d+|==|!=|&&|\|\||\(|\)"
    rest = re.sub(pattern + r"|\s+", "", body)
    assert rest == "", f"evaluator does not understand {rest!r} in {body!r}"
    words = {"&&": " and ", "||": " or ", "github.event_name": repr(event)}
    py = "".join(words.get(t, f" {t} ") for t in re.findall(pattern, body))
    return eval(py, {"__builtins__": {}})  # noqa: S307 (tokens checked above: literals and operators only)


class Triggers(unittest.TestCase):
    def test_gated_and_exploring_events_are_all_wired(self):
        _, on = load()
        for event in (*GATED, *EXPLORE):
            self.assertIn(event, on, f"api-fuzz no longer runs on {event}")
        self.assertEqual(on["push"]["branches"], ["main"])
        self.assertTrue(on["schedule"] and on["schedule"][0]["cron"], "the nightly schedule is gone")
        seed = on["workflow_dispatch"]["inputs"]["seed"]
        self.assertFalse(seed.get("required", False), "a manual run must be able to draw a random seed")

    def test_only_the_report_job_writes_issues(self):
        d, _ = load()
        self.assertEqual(d["permissions"], {"contents": "read"})
        for name, job in d["jobs"].items():
            perms = job.get("permissions") or {}
            if name == "report":
                self.assertEqual(perms, {"issues": "write"})
            else:
                self.assertNotIn("issues", perms, name)


class GatedRunsAreDeterministic(unittest.TestCase):
    def setUp(self):
        d, _ = load()
        self.job = d["jobs"]["schemathesis"]
        self.steps = self.job["steps"]
        self.runs = "\n".join(s.get("run", "") for s in self.steps)

    def test_committed_seed_is_a_number(self):
        self.assertRegex(str(self.job["env"]["API_FUZZ_SEED"]), r"^\d{1,19}$")

    def test_every_fuzz_call_uses_the_picked_seed_one_worker_and_no_database(self):
        blocks = [s["run"] for s in self.steps if "bin/schemathesis" in s.get("run", "")]
        self.assertEqual(len(blocks), 3, "agent, owner and /mcp fuzz steps")
        for run in blocks:
            for call in re.split(r"\n(?=\s*\.venv/bin/schemathesis)", run):
                if "bin/schemathesis" not in call:
                    continue
                self.assertIn('--seed "$SEED"', call)
                self.assertIn("--workers 1", call)
                self.assertIn("--generation-database none", call)
                self.assertIn('--max-examples "$EXAMPLES"', call)
                self.assertIn('--config-file "$FUZZ/schemathesis.toml"', call)
                self.assertIn("--report junit", call)
                for weakener in ("--exclude-checks", "--phases", "--mode", "--max-time", "--no-shrink"):
                    self.assertNotIn(weakener, call)
        self.assertNotIn("run_id }}\"", self.runs.replace(" ", ""))
        self.assertNotIn("--seed \"${{", self.runs)

    def test_both_roles_every_check_and_the_hooks(self):
        by_id = {s.get("id"): s["run"] for s in self.steps if "id" in s}
        self.assertIn("$AGENT_TOKEN", by_id["fuzz-agent"])
        self.assertIn("--checks all --exclude-path /mcp", by_id["fuzz-agent"])
        self.assertIn("$OWNER_TOKEN", by_id["fuzz-owner"])
        self.assertIn("--checks all --exclude-path /mcp", by_id["fuzz-owner"])
        mcp = by_id["fuzz-mcp"]
        self.assertIn("for role in agent owner", mcp)
        self.assertIn("$AGENT_TOKEN", mcp)
        self.assertIn("$OWNER_TOKEN", mcp)
        self.assertIn("--include-path /mcp --checks not_a_server_error", mcp)
        self.assertEqual(self.job["env"]["SCHEMATHESIS_HOOKS"], "api_fuzz_hooks")
        for phase in ("prepare", "agent", "owner"):
            self.assertIn(f"api_fuzz_check.py --phase {phase}", self.runs)
        # A tee'd check must still fail its step: shell: bash brings pipefail.
        for sid in ("check-agent", "check-owner"):
            step = next(s for s in self.steps if s.get("id") == sid)
            self.assertEqual(step.get("shell"), "bash", sid)

    def test_budgets_are_today_or_more(self):
        examples, timeout = self.job["env"]["EXAMPLES"], self.job["timeout-minutes"]
        for event in ("pull_request", "merge_group"):
            self.assertGreaterEqual(int(evaluate(examples, event)), 40, event)
        for event in ("push", *EXPLORE):
            self.assertGreaterEqual(int(evaluate(examples, event)), 400, event)
            self.assertGreaterEqual(int(evaluate(timeout, event)), 180, event)
        for event in EXPLORE:
            self.assertGreater(int(evaluate(examples, event)), int(evaluate(examples, "pull_request")))

    def pick(self, event: str, input_seed: str = "") -> tuple[int, str, str]:
        step = next(s for s in self.steps if s.get("id") == "seed")
        with tempfile.TemporaryDirectory() as tmp:
            out, envf, summary = (Path(tmp, n) for n in ("out", "env", "summary"))
            env = {**os.environ, "EVENT": event, "INPUT_SEED": input_seed, "EXAMPLES": "40",
                   "API_FUZZ_SEED": str(self.job["env"]["API_FUZZ_SEED"]),
                   "GITHUB_OUTPUT": str(out), "GITHUB_ENV": str(envf), "GITHUB_STEP_SUMMARY": str(summary)}
            p = subprocess.run(["bash", "-e", "-c", step["run"]], env=env, capture_output=True, text=True)
            seed = out.read_text().strip().removeprefix("seed=") if out.exists() else ""
            if p.returncode == 0:
                self.assertEqual(envf.read_text().strip(), f"SEED={seed}")
                self.assertIn(seed, p.stdout)  # printed in the log
                self.assertIn(seed, summary.read_text())  # and in the job summary
            return p.returncode, seed, p.stdout + p.stderr

    def test_gated_events_use_the_committed_seed(self):
        fixed = str(self.job["env"]["API_FUZZ_SEED"])
        for event in GATED:
            rc, seed, log = self.pick(event, input_seed="999")  # an input never overrides a gated run
            self.assertEqual((rc, seed), (0, fixed), log)

    def test_nightly_draws_a_random_seed_and_manual_runs_can_replay_one(self):
        rc1, s1, _ = self.pick("schedule")
        rc2, s2, _ = self.pick("schedule")
        self.assertEqual((rc1, rc2), (0, 0))
        self.assertRegex(s1, r"^\d+$")
        self.assertNotEqual(s1, s2, "two nightly runs drew the same seed (1 in 2**32, or not random)")
        self.assertNotEqual(s1, str(self.job["env"]["API_FUZZ_SEED"]))
        rc, seed, _ = self.pick("workflow_dispatch")
        self.assertEqual(rc, 0)
        self.assertRegex(seed, r"^\d+$")
        self.assertEqual(self.pick("workflow_dispatch", "12345")[:2], (0, "12345"))
        self.assertNotEqual(self.pick("workflow_dispatch", "1; rm -rf /")[0], 0, "a non-numeric seed must fail")


class NightlyFindingIssue(unittest.TestCase):
    def setUp(self):
        d, _ = load()
        self.jobs = d["jobs"]

    def test_finding_is_written_and_kept(self):
        steps = self.jobs["schemathesis"]["steps"]
        write = next(s for s in steps if "api-fuzz-finding.py" in s.get("run", ""))
        for event in EXPLORE:
            self.assertIn(event, write["if"])
        self.assertIn("failure()", write["if"])
        self.assertIn('--seed "$SEED"', write["run"])
        upload = next(s for s in steps if "upload-artifact" in s.get("uses", ""))
        self.assertEqual(upload["if"], "always()")
        for path in ("fuzz-run/finding.md", "fuzz-run/report-*", "fuzz-run/check-*.log"):
            self.assertIn(path, upload["with"]["path"])
        self.assertEqual(self.jobs["schemathesis"]["outputs"]["seed"], "${{ steps.seed.outputs.seed }}")

    def test_report_job_opens_or_updates_one_issue_by_title(self):
        job = self.jobs["report"]
        self.assertEqual(job["needs"], "schemathesis")
        self.assertIn("failure()", job["if"])
        for event in EXPLORE:
            self.assertIn(event, job["if"])
        for event in GATED:
            self.assertNotIn(event, job["if"], "gated runs report on the PR, never as an issue")
        step = next(s for s in job["steps"] if "run" in s)
        self.assertEqual(step["env"]["TITLE"], TITLE)
        self.assertEqual(finding_module().TITLE, TITLE)
        self.assertEqual(step.get("shell"), "bash", "pipefail keeps a failed listing from opening a duplicate")
        run = step["run"]
        self.assertIn("state=open", run)
        self.assertIn(".title == env.TITLE", run)
        self.assertIn("/comments", run)  # an open issue gets a comment
        self.assertIn('"repos/$GITHUB_REPOSITORY/issues" -f "title=$TITLE"', run)  # otherwise one is opened
        self.assertFalse(any("checkout" in s.get("uses", "") for s in job["steps"]), "the issue job runs no repo code")


JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites failures="2" tests="3"><testsuite name="schemathesis" failures="2" tests="3">
<testcase name="GET /v1/custom-apps/{app_id}"><failure type="failure" message="ST103">1. Test Case ID: qUhYAY

- ST103 Undocumented status code

    Received: 403 @someone

Reproduce with:

    curl -X GET http://127.0.0.1:8080/v1/custom-apps/freshrss</failure></testcase>
<testcase name="POST /v1/sync/commit"><failure type="failure" message="ST901">1. Test Case ID: FtkjVQ

- ST901 Custom check failed: `semantic_refusal_names_its_reason`
</failure></testcase>
<testcase name="GET /healthz"/>
</testsuite></testsuites>
"""


class FindingScript(unittest.TestCase):
    def setUp(self):
        self.mod = finding_module()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "report-owner").mkdir()
        (self.dir / "report-owner" / "junit.xml").write_text(JUNIT)
        (self.dir / "check-owner.log").write_text("owner phase: audit 9 lines\nFAIL: owner run never exercised action.denied\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_body_has_seed_endpoint_check_and_reproduce_commands(self):
        text = self.mod.body(self.dir, "424242", "400", "c14f2c3a950e18232fbf", "main", "https://run", "fuzz-owner=failure,check-owner=skipped")
        self.assertIn("**Seed:** `424242`", text)
        self.assertIn("`GET /v1/custom-apps/{app_id}`** as the owner", text)
        self.assertIn("check: ST103 Undocumented status code", text)
        self.assertIn("check: ST901 Custom check failed: `semantic_refusal_names_its_reason`", text)
        self.assertIn("test case: qUhYAY", text)
        self.assertIn("gh workflow run api-fuzz.yml --ref main -f seed=424242", text)
        self.assertIn("owner: FAIL: owner run never exercised action.denied", text)
        self.assertIn("Failed steps:** fuzz-owner", text)
        self.assertNotIn("@someone", text.replace("@​someone", ""))  # no pings from generated data
        local = [ln for ln in text.splitlines() if ln.startswith(".venv/bin/schemathesis")]
        self.assertEqual(len(local), 2)
        self.assertIn("--include-path '/v1/custom-apps/{app_id}' --include-method GET", local[0])
        self.assertIn('-H "Authorization: Bearer $OWNER_TOKEN" --checks all --exclude-path /mcp', local[0])
        self.assertIn("--max-examples 400 --seed 424242 --workers 1 --generation-database none", local[0])

    def test_mcp_findings_reproduce_with_the_mcp_scope(self):
        f = {"kind": "mcp-agent", "endpoint": "POST /mcp", "checks": [], "case_ids": []}
        cmd = self.mod.reproduce(f, "7", "40")
        self.assertIn('"Authorization: Bearer $AGENT_TOKEN" --include-path /mcp --checks not_a_server_error', cmd)
        self.assertNotIn("--include-method", cmd)

    def test_a_failure_without_reports_still_names_seed_and_run(self):
        empty = Path(self.tmp.name, "empty")
        empty.mkdir()
        text = self.mod.body(empty, "5", "400", "abc", "main", "https://run", "gateway=failure")
        self.assertIn("**Seed:** `5`", text)
        self.assertIn("https://run", text)
        self.assertIn("No JUnit failure", text)

    def test_cli_refuses_a_non_numeric_seed(self):
        p = subprocess.run(["python3", "-I", str(SCRIPT), "--fuzz-dir", str(self.dir), "--seed", "x;y",
                            "--examples", "400", "--sha", "abc"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        p = subprocess.run(["python3", "-I", str(SCRIPT), "--fuzz-dir", str(self.dir), "--seed", "9",
                            "--examples", "400", "--sha", "abc"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("seed=9", p.stdout)


if __name__ == "__main__":
    unittest.main()
