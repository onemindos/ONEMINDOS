# SPDX-License-Identifier: Apache-2.0
"""api-fuzz seeds (founder decision 2026-11-25): gated runs are deterministic, the nightly explores.

Locks in .github/workflows/api-fuzz.yml so nobody silently drops a part of it:
  - pull_request, merge_group and push to main fuzz with the committed API_FUZZ_SEED, one worker and
    no example database, with today's budgets, both roles, every check and the custom hooks;
  - the nightly schedule and a manual run draw a random seed (or replay a given one), print it, fuzz
    the larger budget, and on a failure ONE "api-fuzz nightly finding" issue is opened or commented
    on, by the only job that may write issues;
  - scripts/api-fuzz-finding.py writes that issue's seed, endpoint, check and reproduce commands;
  - each job's `if:` is evaluated for each event (GitHub's expression rules, status functions included),
    so a condition, a removed trigger or a cron that never fires cannot switch the nightly off unseen.
"""
import importlib.util
import json
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


TOKEN = re.compile(r"\s*(?:(?P<str>'[^']*')|(?P<num>\d+)|(?P<op>==|!=|&&|\|\||!|\(|\))"
                   r"|(?P<fn>always|success|failure|cancelled)\(\)|(?P<ref>[A-Za-z_][\w.-]*))")
STATUS_FUNCTIONS = ("always()", "success()", "failure()", "cancelled()")


def evaluate(expr, event: str, *, ctx: dict | None = None, needs: dict | None = None,
             job_if: bool = False, workflow_cancelled: bool = False):
    """Evaluate a GitHub Actions expression the way the runner does, for one event.

    Supports literals, context references, the four status functions, !, ==, !=, && and || with GitHub's
    precedence and value semantics (`a && b || c` yields a value, strings compare case-insensitively).
    `needs` maps a needed job to {"result": ..., "outputs": {...}}. A job-level `if:` (job_if) without a
    status function gets GitHub's implicit `success() &&`. An unknown reference fails the test, so a new
    condition must be taught here, and checked, before it can pass.
    """
    text = str(expr).strip()
    m = re.fullmatch(r"\$\{\{(.*)\}\}", text, re.S)
    body = m.group(1) if m else text
    needs = needs or {}
    values = {"github.event_name": event, "github.event.pull_request.draft": None, **(ctx or {})}
    for job, n in needs.items():
        values[f"needs.{job}.result"] = n["result"]
        for k, v in n.get("outputs", {}).items():
            values[f"needs.{job}.outputs.{k}"] = v
    results = [n["result"] for n in needs.values()]
    status = {"always": True, "cancelled": workflow_cancelled,
              "success": not workflow_cancelled and all(r == "success" for r in results),
              "failure": any(r == "failure" for r in results)}

    tokens, pos = [], 0
    while pos < len(body):
        t = TOKEN.match(body, pos)
        if not t or t.end() == pos:
            if body[pos:].strip() == "":
                break
            raise AssertionError(f"evaluator does not understand {body[pos:]!r} in {body!r}")
        pos = t.end()
        tokens.append((t.lastgroup, t.group(t.lastgroup)))
    i = 0

    def peek():
        return tokens[i] if i < len(tokens) else (None, None)

    def take():
        nonlocal i
        i += 1
        return tokens[i - 1]

    def truthy(v):
        return v not in (None, False, 0, "")

    def primary():
        kind, val = take()
        if kind == "op" and val == "!":
            return not truthy(primary())
        if kind == "op" and val == "(":
            v = disjunction()
            assert take() == ("op", ")"), body
            return v
        if kind == "str":
            return val[1:-1]
        if kind == "num":
            return int(val)
        if kind == "fn":
            return status[val]
        if kind == "ref":
            literal = {"true": True, "false": False, "null": None}
            if val in literal:
                return literal[val]
            assert val in values, f"unknown context {val!r} in {body!r}: teach the test what it means"
            return values[val]
        raise AssertionError(f"unexpected {val!r} in {body!r}")

    def comparison():
        v = primary()
        while peek() in (("op", "=="), ("op", "!=")):
            op = take()[1]
            w = primary()
            a, b = (x.lower() if isinstance(x, str) else x for x in (v, w))
            v = (a == b) if op == "==" else (a != b)
        return v

    def conjunction():
        v = comparison()
        while peek() == ("op", "&&"):
            take()
            w = comparison()
            v = w if truthy(v) else v
        return v

    def disjunction():
        v = conjunction()
        while peek() == ("op", "||"):
            take()
            w = conjunction()
            v = v if truthy(v) else w
        return v

    v = disjunction()
    assert i == len(tokens), f"trailing tokens in {body!r}"
    if job_if and not any(f in body.replace(" ", "") for f in STATUS_FUNCTIONS):
        v = status["success"] and truthy(v)
    return truthy(v) if job_if else v


def job_runs(job: dict, event: str, **kw) -> bool:
    """Would GitHub start this job for this event? A job without `if:` runs when its needs succeeded."""
    return evaluate(job.get("if", "true"), event, job_if=True, **kw)


def cron_fires_daily(cron: str) -> bool:
    """A five-field cron that fires at least once every day: fixed minute and hour, every day/month/weekday."""
    fields = cron.split()
    if len(fields) != 5:
        return False
    minute, hour, dom, month, dow = fields
    return (minute.isdigit() and int(minute) < 60 and hour.isdigit() and int(hour) < 24
            and (dom, month, dow) == ("*", "*", "*"))


class Triggers(unittest.TestCase):
    def test_gated_and_exploring_events_are_all_wired(self):
        _, on = load()
        for event in (*GATED, *EXPLORE):
            self.assertIn(event, on, f"api-fuzz no longer runs on {event}")
        self.assertEqual(on["push"]["branches"], ["main"])
        self.assertTrue(on["schedule"] and on["schedule"][0]["cron"], "the nightly schedule is gone")
        self.assertTrue(any(cron_fires_daily(c["cron"]) for c in on["schedule"]),
                        f"no schedule fires every night: {on['schedule']}")
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


class JobsRunOnTheirEvents(unittest.TestCase):
    """The job-level `if:` of every job, evaluated per event: nothing can switch a run off by condition."""

    def setUp(self):
        d, on = load()
        self.jobs, self.on = d["jobs"], on

    def changes_needs(self, event: str, fuzz: str = "true", result: str = "success") -> dict:
        if event != "merge_group":  # the changes job is merge-queue only, so it is skipped
            self.assertFalse(job_runs(self.jobs["changes"], event), f"changes runs on {event}")
            return {"changes": {"result": "skipped", "outputs": {"fuzz": ""}}}
        self.assertTrue(job_runs(self.jobs["changes"], event))
        return {"changes": {"result": result, "outputs": {"fuzz": fuzz}}}

    def test_schemathesis_runs_on_every_event(self):
        job = self.jobs["schemathesis"]
        for event in (*GATED, *EXPLORE):
            ctx = {"github.event.pull_request.draft": False} if event == "pull_request" else {}
            self.assertTrue(job_runs(job, event, ctx=ctx, needs=self.changes_needs(event)),
                            f"the fuzz job no longer runs on {event}")
        self.assertFalse(job_runs(job, "pull_request", ctx={"github.event.pull_request.draft": True},
                                  needs=self.changes_needs("pull_request")), "draft PRs stay quiet")
        self.assertFalse(job_runs(job, "schedule", needs=self.changes_needs("schedule"), workflow_cancelled=True))

    def test_the_queue_skips_only_merge_groups_that_touch_nothing_fuzzed(self):
        job = self.jobs["schemathesis"]
        self.assertFalse(job_runs(job, "merge_group", needs=self.changes_needs("merge_group", fuzz="false")))
        # A changes job that failed or wrote nothing counts as a change: the fuzz still runs.
        self.assertTrue(job_runs(job, "merge_group", needs=self.changes_needs("merge_group", fuzz="", result="failure")))

    def test_changes_job_matches_the_push_paths_and_fails_safe(self):
        step = self.jobs["changes"]["steps"][0]
        paths = json.loads(step["env"]["FUZZ_PATHS"])
        self.assertEqual(paths, self.on["push"]["paths"], "the queue filter must equal on.push.paths")
        self.assertEqual(self.jobs["changes"]["outputs"]["fuzz"], "${{ steps.diff.outputs.fuzz }}")
        cases = {
            "docs/README.md\nchanges/x.md\n": "false",
            "docs/README.md\ncore/onemind_core/app.py\n": "true",
            "apps/freshrss/onemind.app.yaml\n": "true",
            "sdk/schema/app.schema.json\n": "true",
            ".github/workflows/api-fuzz.yml\n": "true",
            "".join(f"docs/f{n}.md\n" for n in range(300)): "true",  # the compare API's 300-file cap
            None: "true",  # the compare call failed
        }
        for files, want in cases.items():
            with tempfile.TemporaryDirectory() as tmp:
                gh = Path(tmp, "gh")
                if files is None:
                    gh.write_text("#!/bin/sh\nexit 1\n")
                else:
                    Path(tmp, "files").write_text(files)
                    gh.write_text(f"#!/bin/sh\ncat '{tmp}/files'\n")
                gh.chmod(0o755)
                out = Path(tmp, "out")
                env = {**os.environ, **step["env"], "PATH": f"{tmp}:{os.environ['PATH']}",
                       "GITHUB_OUTPUT": str(out), "GITHUB_REPOSITORY": "o/r", "BASE_SHA": "a", "HEAD_SHA": "b"}
                p = subprocess.run(["bash", "-e", "-c", step["run"]], env=env, capture_output=True, text=True)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(out.read_text().strip(), f"fuzz={want}", (files or "")[:80])

    def test_properties_runs_on_main_nightly_and_manual(self):
        job = self.jobs["properties"]
        for event in ("push", *EXPLORE):
            self.assertTrue(job_runs(job, event), f"the deep property run no longer runs on {event}")
        for event in ("pull_request", "merge_group"):
            self.assertFalse(job_runs(job, event, ctx={"github.event.pull_request.draft": False}), event)

    def test_report_files_on_a_failed_or_timed_out_exploration_only(self):
        job = self.jobs["report"]
        for event in EXPLORE:
            for result in ("failure", "cancelled"):  # a job stopped by timeout-minutes may read as cancelled
                self.assertTrue(job_runs(job, event, needs={"schemathesis": {"result": result}}), (event, result))
            for result in ("success", "skipped"):
                self.assertFalse(job_runs(job, event, needs={"schemathesis": {"result": result}}), (event, result))
        for event in GATED:
            self.assertFalse(job_runs(job, event, needs={"schemathesis": {"result": "failure"}}),
                             "gated runs report on the PR, never as an issue")

    def test_the_evaluator_follows_github_rules(self):
        self.assertTrue(job_runs({"if": "${{ !github.event.pull_request.draft }}"}, "push"))
        self.assertFalse(job_runs({"if": "github.event_name == 'push'"}, "push", needs={"a": {"result": "failure"}}),
                         "a job-level if without a status function gets success() &&")
        self.assertTrue(job_runs({"if": "failure()"}, "push", needs={"a": {"result": "failure"}}))
        self.assertEqual(evaluate("${{ github.event_name == 'push' && '4' || '9' }}", "PUSH"), "4")
        self.assertFalse(job_runs({"if": "false"}, "schedule"))
        with self.assertRaises(AssertionError):
            evaluate("${{ github.actor == 'x' }}", "push")
        for bad in ("0 0 31 2 *", "*/5 * * * *", "0 3 * * 1", "17 3 * *"):
            self.assertFalse(cron_fires_daily(bad), bad)
        self.assertTrue(cron_fires_daily("17 3 * * *"))


class GatedRunsAreDeterministic(unittest.TestCase):
    def setUp(self):
        d, _ = load()
        self.job = d["jobs"]["schemathesis"]
        self.steps = self.job["steps"]
        self.runs = "\n".join(s.get("run", "") for s in self.steps)

    def test_committed_seed_is_a_number(self):
        self.assertRegex(str(self.job["env"]["API_FUZZ_SEED"]), r"^\d{1,19}$")

    def test_fuzz_job_runs_hook_regression_after_installing_locked_group(self):
        install = next(i for i, step in enumerate(self.steps)
                       if "uv sync --locked --python 3.12 --group fuzz" in step.get("run", ""))
        hook_test = ("tests/test_fuzz_landing_regressions.py::"
                     "test_the_fuzz_hook_lists_these_reasons_and_still_fails_any_other")
        step = next((step for step in self.steps[install + 1:] if hook_test in step.get("run", "")), None)
        self.assertIsNotNone(step, "run the hook test in the job that installs Schemathesis")
        self.assertEqual(step.get("working-directory"), "core")
        self.assertNotIn("if", step)
        self.assertNotIn("continue-on-error", step)

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
        for event in EXPLORE:  # exploration fuzzes more than any gated run, with time to finish
            self.assertGreater(int(evaluate(examples, event)), int(evaluate(examples, "push")))
            # 400 cases take ~80 of main's 180 minutes; a larger budget needs a longer timeout.
            self.assertGreater(int(evaluate(timeout, event)), int(evaluate(timeout, "push")), event)
            self.assertLessEqual(int(evaluate(timeout, event)), 360, "a GitHub-hosted job stops at 360 minutes")

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
        self.assertEqual(job["needs"], "schemathesis")  # when it runs: JobsRunOnTheirEvents
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
        (self.dir / "check-owner.log").write_text("owner phase: audit 9 lines\nFAIL: owner run never exercised action.denied\n"
                                                    "FAIL: decided by @mallory, see #42\n")

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
        # Audit FAIL lines are generated data too: no @-mention, no #NNN cross-link in the issue.
        self.assertIn("owner: FAIL: decided by @\u200bmallory, see #\u200b42", text)
        self.assertNotRegex(text, r"[@#][\w-]", "a mention or cross-link reached the issue body")
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
