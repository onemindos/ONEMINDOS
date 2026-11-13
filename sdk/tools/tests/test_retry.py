# SPDX-License-Identifier: Apache-2.0
"""Unit tests for applib/retry.py (bounded retry with backoff, registry credentials) and
applib/selection.py (licence-matrix row comparison). No network, no real sleeping."""
from __future__ import annotations

import base64
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from applib import common, retry, selection  # noqa: E402


def proc(rc: int, stderr: str = "", stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], rc, stdout, stderr)


class Scripted:
    """A runner that returns the scripted results in order and counts calls."""

    def __init__(self, *results):
        self.results, self.calls = list(results), 0

    def __call__(self, argv, **kw):
        self.calls += 1
        return self.results.pop(0)


class TransientTests(unittest.TestCase):
    def test_transient_errors(self):
        for text in (
            "TOOMANYREQUESTS: You have reached your unauthenticated pull rate limit",
            "GET https://ghcr.io/v2/x/manifests/y: toomanyrequests: retry-after: 30",
            "unexpected status code 429 Too Many Requests",
            "unexpected status code 503 Service Unavailable",
            "Error: HTTP 502 Bad Gateway",
            "read tcp: read: connection reset by peer",
            "dial tcp: i/o timeout", "unexpected EOF", "net/http: TLS handshake timeout",
        ):
            with self.subTest(text=text):
                self.assertTrue(retry.is_transient(text))

    def test_real_answers_are_not_retried(self):
        for text in ("MANIFEST_UNKNOWN: manifest unknown", "NAME_UNKNOWN", "UNAUTHORIZED: authentication required",
                     "denied: requested access to the resource is denied", "no matching signatures",
                     "CRITICAL CVE-2026-1234", "image sha256:5000abc", "port 5000"):
            with self.subTest(text=text):
                self.assertFalse(retry.is_transient(text))

    def test_retry_after_is_read(self):
        self.assertEqual(retry.retry_after("429 Too Many Requests; Retry-After: 17"), 17.0)
        self.assertEqual(retry.retry_after("retry-after=3"), 3.0)
        self.assertIsNone(retry.retry_after("TOOMANYREQUESTS"))


class BackoffTests(unittest.TestCase):
    def test_exponential_with_jitter_and_cap(self):
        zero, one = (lambda: 0.0), (lambda: 1.0)
        self.assertEqual([retry.delay_for(i, rand=zero) for i in range(4)], [2, 4, 8, 16])
        self.assertEqual(retry.delay_for(2, rand=one), 8 * 1.5)
        self.assertEqual(retry.delay_for(20, rand=zero), retry.MAX_DELAY)

    def test_retry_after_wins_and_is_capped(self):
        self.assertEqual(retry.delay_for(0, "Retry-After: 30", rand=lambda: 0.0), 30)
        self.assertEqual(retry.delay_for(0, "Retry-After: 99999", rand=lambda: 0.0), retry.MAX_DELAY)


class RunRetryTests(unittest.TestCase):
    def run_it(self, runner, **kw):
        sleeps = []
        out = retry.run_retry(runner, ["crane", "digest", "x"], sleep=sleeps.append, rand=lambda: 0.0, **kw)
        return out, sleeps

    def test_success_first_try_never_sleeps(self):
        r = Scripted(proc(0, stdout="ok"))
        out, sleeps = self.run_it(r)
        self.assertEqual((out.stdout, r.calls, sleeps), ("ok", 1, []))

    def test_retries_transient_then_succeeds(self):
        r = Scripted(proc(1, "TOOMANYREQUESTS"), proc(1, "unexpected status code 503"), proc(0, stdout="ok"))
        out, sleeps = self.run_it(r)
        self.assertEqual((out.returncode, r.calls, sleeps), (0, 3, [2, 4]))

    def test_honours_retry_after(self):
        r = Scripted(proc(1, "429 Too Many Requests Retry-After: 11"), proc(0))
        _, sleeps = self.run_it(r)
        self.assertEqual(sleeps, [11])

    def test_gives_up_after_five_attempts(self):
        r = Scripted(*[proc(1, "TOOMANYREQUESTS")] * 5)
        out, sleeps = self.run_it(r)
        self.assertEqual((out.returncode, r.calls, len(sleeps)), (1, 5, 4))

    def test_permanent_errors_are_returned_at_once(self):
        r = Scripted(proc(1, "MANIFEST_UNKNOWN"))
        out, sleeps = self.run_it(r)
        self.assertEqual((out.returncode, r.calls, sleeps), (1, 1, []))

    def test_registry_wrapper_retries_then_reports(self):
        calls = []

        def fake(argv, **kw):
            calls.append(argv)
            return proc(1, "TOOMANYREQUESTS") if len(calls) < 3 else proc(0, stdout="sha256:abc\n")

        orig, retry_sleep = common.run, retry.time.sleep
        common.run, retry.time.sleep = fake, lambda s: None
        try:
            self.assertEqual(common.Registry(crane="crane").digest("x"), "sha256:abc")
        finally:
            common.run, retry.time.sleep = orig, retry_sleep
        self.assertEqual(len(calls), 3)


class RetryCallTests(unittest.TestCase):
    def test_transient_tool_error_is_repeated(self):
        n, sleeps = [], []

        def fn():
            n.append(1)
            if len(n) < 3:
                raise common.ToolError("crane export x: connection reset by peer")
            return 42
        self.assertEqual(retry.retry_call(fn, (common.ToolError,), sleep=sleeps.append, rand=lambda: 0.0), 42)
        self.assertEqual(sleeps, [2, 4])

    def test_permanent_tool_error_propagates(self):
        def fn():
            raise common.ToolError("crane export x: MANIFEST_UNKNOWN")
        with self.assertRaises(common.ToolError):
            retry.retry_call(fn, (common.ToolError,), sleep=lambda s: self.fail("slept"))


class AuthTests(unittest.TestCase):
    def test_no_credentials_no_config(self):
        env = {}
        self.assertIsNone(retry.setup_registry_auth(env))
        self.assertNotIn("DOCKER_CONFIG", env)
        self.assertEqual(retry.docker_auths({"DOCKERHUB_USERNAME": "u"}), {})  # needs both

    def test_github_token_logs_in_to_ghcr_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"GITHUB_TOKEN": "ghs_secret", "GITHUB_ACTOR": "octo"}
            d = retry.setup_registry_auth(env, parent=tmp)
            self.assertEqual(env["DOCKER_CONFIG"], str(d))
            cfg = d / "config.json"
            self.assertEqual(stat.S_IMODE(cfg.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(d.stat().st_mode), 0o700)
            auths = json.loads(cfg.read_text())["auths"]
            self.assertEqual(list(auths), ["ghcr.io"])
            self.assertEqual(base64.b64decode(auths["ghcr.io"]["auth"]), b"octo:ghs_secret")

    def test_dockerhub_only_when_both_secrets_exist(self):
        auths = retry.docker_auths({"DOCKERHUB_USERNAME": "u", "DOCKERHUB_TOKEN": "t"})
        self.assertEqual(list(auths), ["https://index.docker.io/v1/"])


class SelectionTests(unittest.TestCase):
    HEADER = "component,version,SPDX,license_file_permalink,source,x\n"
    REPOS = {"alpha": "own/alpha", "beta": "own/beta", "nogh": None}

    def row(self, repo, spdx="MIT"):
        return f"c-{repo},v1,{spdx},https://github.com/{repo}/blob/a/LICENSE,github.com/{repo}@a,y\n"

    def pick(self, old, new):
        return selection.apps_with_changed_rows(self.HEADER + old, self.HEADER + new, self.REPOS)

    def test_added_changed_and_removed_rows(self):
        self.assertEqual(self.pick("", self.row("own/alpha")), ["alpha"])
        self.assertEqual(self.pick(self.row("own/alpha"), self.row("own/alpha", "Apache-2.0")), ["alpha"])
        self.assertEqual(self.pick(self.row("own/beta"), ""), ["beta"])

    def test_unrelated_and_reordered_rows_select_nothing(self):
        self.assertEqual(self.pick(self.row("own/alpha"), self.row("own/alpha") + self.row("kernel/linux")), [])
        self.assertEqual(self.pick(self.row("own/alpha") + self.row("own/beta"),
                                   self.row("own/beta") + self.row("own/alpha")), [])

    def test_repo_prefix_is_not_a_match(self):
        self.assertEqual(self.pick("", self.row("own/alpha-extras")), [])

    def test_new_file_and_bad_header(self):
        self.assertEqual(selection.apps_with_changed_rows("", self.HEADER + self.row("own/beta"), self.REPOS), ["beta"])
        with self.assertRaises(ValueError):
            selection.apps_with_changed_rows("", "a,b\n1,2\n", self.REPOS)


if __name__ == "__main__":
    unittest.main()
