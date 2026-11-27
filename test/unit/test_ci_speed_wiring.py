# SPDX-License-Identifier: Apache-2.0
"""CI speed wiring (CI-03, issue 228): the gateway shards really run in parallel, stay inside their
timeout, and the non-blocking Secure Boot step can never hold up the required battery steps.

Why: until 2026-11-25 `make -C core test` dropped PYTEST_ARGS, so every ci-core shard ran on one core
(PostgreSQL shard 3/4: 2262 tests in 3441 s against a 60-minute timeout), and the Secure Boot step ran
for about 50 minutes before the required firewall and battery steps.
"""
import importlib.util
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"
spec = importlib.util.spec_from_file_location("ci_core_matrix", ROOT / "scripts" / "ci-core-matrix.py")
cm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cm)

SHARD_TIMEOUT_MAX = 30   # minutes: a shard takes well under 20 (CI-03 target); the timeout only catches a hang


def load(name):
    return yaml.safe_load((WF / name).read_text(encoding="utf-8"))


def step(steps, prefix):
    hits = [i for i, s in enumerate(steps) if s.get("name", "").startswith(prefix)]
    if len(hits) != 1:
        raise AssertionError(f"expected one step named {prefix!r}, found {len(hits)}")
    return hits[0], steps[hits[0]]


class CoreShards(unittest.TestCase):
    def test_make_test_passes_pytest_args(self):
        mk = (ROOT / "core" / "Makefile").read_text(encoding="utf-8")
        recipe = re.search(r"^test: sync\n((?:\t.*\n)+)", mk, re.M)
        self.assertIsNotNone(recipe, "core/Makefile has no `test: sync` target")
        self.assertIn("pytest", recipe.group(1))
        self.assertIn("$(PYTEST_ARGS)", recipe.group(1), "ci-core's -n auto would be dropped again")

    def test_both_backends_run_xdist_on_their_shard(self):
        jobs = load("ci-core.yml")["jobs"]
        for name in ("test", "test-postgresql"):
            job = jobs[name]
            _, suite = step(job["steps"], "Core suite")
            self.assertRegex(suite["run"], r"^make -C core test PYTEST_ARGS=\"[^\"]*-n auto", name)
            self.assertIn("--dist loadgroup", suite["run"], name)   # keeps the real-NATS group on one worker
            self.assertIn("--durations=", suite["run"], name)       # the slowest tests show in every log
            self.assertEqual(suite["env"]["ONEMIND_TEST_SHARD"], "${{ matrix.shard }}", name)
            self.assertLessEqual(job["timeout-minutes"], SHARD_TIMEOUT_MAX, name)

    def test_shard_counts_match_the_matrix(self):
        for backend in ("sqlite", "postgresql"):
            shards = [j["shard"] for j in cm.shards("push") if j["backend"] == backend]
            n = len(shards)
            self.assertGreaterEqual(n, 3, backend)
            self.assertEqual(sorted(shards), sorted(f"{k}/{n}" for k in range(1, n + 1)), backend)

    def test_runner_routing_is_unchanged(self):
        jobs = load("ci-core.yml")["jobs"]
        for name in ("plan", "test"):
            ro = jobs[name]["runs-on"]
            for var in ("MQ_RUNNER", "LOCAL_RUNNER"):
                self.assertIn(f"vars.{var} == 'on'", ro, name)
        self.assertIn("vars.DO_RUNNER == 'on'", jobs["test"]["runs-on"])
        self.assertIn("merge_group", load("ci-core.yml")[True])   # yaml reads `on:` as True


class SecureBootStep(unittest.TestCase):
    def setUp(self):
        self.steps = load("battery.yml")["jobs"]["battery"]["steps"]

    def test_secure_boot_runs_after_the_required_steps(self):
        sb, sb_step = step(self.steps, "Secure Boot and signed UKI")
        bat, _ = step(self.steps, "Battery up to")
        fw, _ = step(self.steps, "Host firewall scan")
        fb, _ = step(self.steps, "First boot into OneMind")
        self.assertGreater(sb, bat)
        self.assertGreater(bat, fw)
        self.assertGreater(fw, fb)
        trim, _ = step(self.steps, "Trim and mask the serial log")
        self.assertLess(sb, trim, "its serial log and verdicts are collected by the trim step")

    def test_secure_boot_is_bounded_and_non_blocking(self):
        _, sb = step(self.steps, "Secure Boot and signed UKI")
        self.assertIs(sb["continue-on-error"], True)
        self.assertEqual(sb["timeout-minutes"], 20)
        self.assertEqual(sb["if"], "inputs.secureboot")
        m = re.search(r"timeout --signal=INT --kill-after=\S+ (\d+)m make secureboot-test", sb["run"])
        self.assertIsNotNone(m, "SIGINT first, so secureboot.py writes partial verdicts and stops QEMU")
        self.assertLess(int(m.group(1)), sb["timeout-minutes"])

    def test_rootfs_tar_survives_the_battery_cleanup(self):
        _, bat = step(self.steps, "Battery up to")
        run = bat["run"]
        keep = run.index("out/sb-keep/")
        self.assertLess(keep, run.index("sudo rm -f out/rootfs-*.tar"), "the tar is kept before it is deleted")
        self.assertLess(run.index("sudo rm -f out/rootfs-*.tar"), run.index("make battery"))
        self.assertEqual(bat["env"]["SECUREBOOT"], "${{ inputs.secureboot }}")
        _, sb = step(self.steps, "Secure Boot and signed UKI")
        self.assertLess(sb["run"].index("out/sb-keep/rootfs-*.tar out/"), sb["run"].index("make secureboot-test"))


if __name__ == "__main__":
    unittest.main()
