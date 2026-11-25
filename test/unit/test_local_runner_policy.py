# SPDX-License-Identifier: Apache-2.0
"""CI-10 and CI-13 (issue 299): the Mac runner pools take trusted, secret-free, arm64-safe jobs only.

Two labels pick the Mac: `onemind-local` (worker VMs, one fresh clone per job) and `onemind-gate` (small
gate VMs for API-only jobs, also one fresh clone per job). A job may pick either only if (1) the choice is
behind that pool's own switch (LOCAL_RUNNER for workers, LOCAL_GATE for the gate) with a GitHub-hosted
fallback, (2) a pull request from a fork can never select it, and no event that runs untrusted code with
repo context (pull_request_target, workflow_run, issue_comment) can start its workflow, (3) nothing in the job,
or in its workflow's top level, can read a secret or an environment or write to the repo, and (4) the job
needs nothing the Mac's Debian 13 arm64 VMs lack: x86_64, KVM, Docker or GitHub's preinstalled SDKs.
"""
import json
import os
import re
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"
KIT = ROOT / "scripts" / "ci-runner"
SECRET_USE = re.compile(r"secrets\.(?!GITHUB_TOKEN\b)|secrets:\s*inherit|toJSON\(secrets\)", re.I)
MAC_LABELS = ("onemind-local", "onemind-gate")
# Each pool has its own switch: merge-gate must not follow LOCAL_RUNNER, or an empty gate pool stalls merges.
SWITCH = {"onemind-local": "LOCAL_RUNNER", "onemind-gate": "LOCAL_GATE"}
TRUSTED = ("(vars.%s == 'on' && (github.event_name != 'pull_request' || "
           "github.event.pull_request.head.repo.full_name == github.repository))")
# The merge-queue pool (MQ_RUNNER): merge_group runs only code already approved into the queue, so it is always
# trusted and needs no fork check. It sits FIRST in the expression and only for merge_group.
MQ_FIRST = ("(vars.MQ_RUNNER == 'on' && github.event_name == 'merge_group') && "
            "fromJSON('[\"self-hosted\",\"onemind-mq\"]') || ")
# Triggers that run with the base repo's context on behalf of someone else's code or comment: a workflow
# with any of them must never send a job to the Mac.
UNTRUSTED_TRIGGERS = {"pull_request_target", "workflow_run", "issue_comment"}
# The gate pool's clones are small (1 CPU, 1 GB) and give the runner no sudo: only jobs that just poll the
# GitHub API belong there.
GATE_JOBS = {("gate.yml", "merge-gate")}
# What the Mac's VMs cannot do: x86_64 binaries, KVM, QEMU for x86, Docker (and service containers),
# GitHub's preinstalled Android SDK, macOS or Windows tools.
NEEDS_HOSTED = re.compile(
    r"/dev/kvm|\bkvm\b|qemu-system-x86|setup-qemu-action|setup-buildx-action|docker[ /]|docker\b\s+compose|"
    r"linux_x64|linux-amd64\b|-amd64 -version|_X64\b|ANDROID_HOME|xcodebuild|make image|make battery|"
    r"battery\.yml|\bk3d\b", re.I)
# Workflows that build or test the OS image, need KVM or sign/publish: never on the Mac.
HOSTED_ONLY_WORKFLOWS = {"image.yml", "battery.yml", "nightly.yml", "net-2vm.yml", "restore-drill.yml", "perf-smoke.yml",
                         "release.yml", "security-nightly.yml", "apps-rescan.yml", "changes-collect.yml",
                         "dev-build.yml", "apps-gate-all.yml", "ci-desktop.yml", "desktop-release.yml"}
# setup-python has no Python 3.13 build for Debian 13 arm64. PR #352 moves ci-apps `validate` to a venv;
# until it merges, that one job is the known exception.
SETUP_PYTHON_PENDING = {("ci-apps.yml", "validate")}


# CI-15: the first safe jobs may try the DigitalOcean pool (onemind-do, switch DO_RUNNER) before the Mac; that
# prefix is reviewed by test_do_runner_policy.py, so the Mac check below compares the rest of the expression.
DO_PREFIX = ("(vars.DO_RUNNER == 'on' && (github.event_name != 'pull_request' || "
             "github.event.pull_request.head.repo.full_name == github.repository)) && "
             "fromJSON('[\"self-hosted\",\"onemind-do\"]') || ")


def workflows():
    for p in sorted(WF.glob("*.yml")):
        yield p.name, yaml.safe_load(p.read_text())


def mac_jobs(label=None):
    for wf, d in workflows():
        for name, job in d["jobs"].items():
            ro = str(job.get("runs-on", ""))
            if any(lab in ro for lab in ((label,) if label else MAC_LABELS)):
                yield wf, d, name, job


def triggers(d):
    on = d.get(True, d.get("on"))   # PyYAML reads the bare key `on` as True
    if isinstance(on, str):
        return {on}
    return set(on or ())


def writes(perms):
    if isinstance(perms, str):
        return perms == "write-all"
    return isinstance(perms, dict) and "write" in perms.values()


class LocalRunnerPolicy(unittest.TestCase):
    def test_some_jobs_use_each_pool(self):
        self.assertTrue(list(mac_jobs("onemind-local")), "no job uses the worker pool")
        self.assertTrue(list(mac_jobs("onemind-gate")), "no job uses the gate pool")

    def test_selection_is_switchable_fork_safe_and_has_a_hosted_fallback(self):
        for wf, d, name, job in mac_jobs():
            ro = job["runs-on"].replace(DO_PREFIX, "", 1)
            where = f"{wf}:{name}"
            label = next(lab for lab in MAC_LABELS if lab in ro)
            mq = MQ_FIRST if label == "onemind-local" else ""     # the gate pool has no merge-queue branch
            want = "${{ %s%s && fromJSON('[\"self-hosted\",\"%s\"]') || 'ubuntu-24.04' }}" % (
                mq, TRUSTED % SWITCH[label], label)
            self.assertEqual(ro, want, where)

    def test_every_local_job_can_use_the_merge_queue_pool_on_merge_group_only(self):
        for wf, d, name, job in mac_jobs("onemind-local"):
            # the DO prefix (CI-15) sits between the merge-queue branch and the Mac branch on its four jobs
            ro, where = job["runs-on"].replace(DO_PREFIX, "", 1), f"{wf}:{name}"
            self.assertTrue(ro.startswith("${{ " + MQ_FIRST), where)
            self.assertEqual(ro.count("onemind-mq"), 1, where)
            self.assertLess(ro.index("onemind-mq"), ro.index("onemind-local"), where)
            # only merge_group can reach it, and it is off unless MQ_RUNNER is on
            self.assertEqual(ro.count("github.event_name == 'merge_group'"), 1, where)
            self.assertNotIn("pull_request", ro.split("||")[0], where)
            # with MQ_RUNNER unset the first branch is false: the rest is the unchanged LOCAL_RUNNER routing
            self.assertTrue(ro[len("${{ " + MQ_FIRST):].startswith(TRUSTED % "LOCAL_RUNNER"), where)

    def test_no_job_outside_the_local_pool_can_reach_the_merge_queue_pool(self):
        for wf, d in workflows():
            for name, job in d["jobs"].items():
                ro = str(job.get("runs-on", ""))
                if "onemind-mq" in ro:
                    self.assertIn("onemind-local", ro, f"{wf}:{name}")
                    self.assertNotIn("onemind-gate", ro, f"{wf}:{name}")

    def test_merge_queue_pool_is_not_a_pull_request_pool(self):
        """Evaluate the routing: a pull_request event never lands on onemind-mq, whatever the variables say."""
        for wf, d, name, job in mac_jobs("onemind-local"):
            first = job["runs-on"].split("||")[0]
            self.assertIn("github.event_name == 'merge_group'", first)
            self.assertNotIn("github.event_name != ", first, f"{wf}:{name}")

    def test_each_pool_has_its_own_switch(self):
        for wf, d, name, job in mac_jobs("onemind-gate"):
            self.assertIn("vars.LOCAL_GATE == 'on'", job["runs-on"], f"{wf}:{name}")
            self.assertNotIn("LOCAL_RUNNER", job["runs-on"], f"{wf}:{name}: an empty gate pool would stall merges")
        for wf, d, name, job in mac_jobs("onemind-local"):
            self.assertIn("vars.LOCAL_RUNNER == 'on'", job["runs-on"], f"{wf}:{name}")
            self.assertNotIn("LOCAL_GATE", job["runs-on"], f"{wf}:{name}")

    def test_no_untrusted_trigger_reaches_the_mac(self):
        for wf, d, name, job in mac_jobs():
            self.assertFalse(triggers(d) & UNTRUSTED_TRIGGERS, f"{wf}:{name}: {sorted(triggers(d) & UNTRUSTED_TRIGGERS)}")

    def test_trigger_reader_sees_every_form(self):
        self.assertEqual(triggers({True: "workflow_run"}), {"workflow_run"})
        self.assertEqual(triggers({True: ["push", "issue_comment"]}), {"push", "issue_comment"})
        self.assertEqual(triggers({"on": {"pull_request_target": None}}), {"pull_request_target"})

    def test_only_api_only_jobs_use_the_gate_pool(self):
        self.assertEqual({(wf, name) for wf, _, name, _ in mac_jobs("onemind-gate")}, GATE_JOBS)

    def test_no_job_that_can_pick_the_mac_can_read_a_secret(self):
        for wf, d, name, job in mac_jobs():
            where = f"{wf}:{name}"
            self.assertNotRegex(json.dumps(job), SECRET_USE, where)
            self.assertNotRegex(json.dumps(d.get("env", {})), SECRET_USE, f"{wf} top-level env")
            self.assertNotIn("environment", job, where)
            self.assertNotIn("docker/login-action", json.dumps(job), where)
            self.assertNotIn("uses", job, f"{where} calls a reusable workflow that could use secrets")

    def test_no_job_that_can_pick_the_mac_can_write_to_the_repo(self):
        for wf, d, name, job in mac_jobs():
            self.assertFalse(writes(job.get("permissions")), f"{wf}:{name}")
            if "permissions" not in job:
                self.assertFalse(writes(d.get("permissions")), f"{wf}: top-level permissions write")

    def test_no_job_that_needs_x86_kvm_or_docker_targets_the_mac(self):
        for wf, d, name, job in mac_jobs():
            where = f"{wf}:{name}"
            self.assertNotIn(wf, HOSTED_ONLY_WORKFLOWS, where)
            self.assertNotIn("services", job, f"{where}: service containers need Docker")
            self.assertNotIn("container", job, f"{where}: job containers need Docker")
            body = json.dumps({k: v for k, v in job.items() if k != "runs-on"})
            self.assertNotRegex(body, NEEDS_HOSTED, where)
            if (wf, name) not in SETUP_PYTHON_PENDING:
                self.assertNotIn("actions/setup-python", body, f"{where}: no Python 3.13 build for Debian 13 arm64")

    def test_x86_and_kvm_jobs_stay_hosted(self):
        """The reverse check: every job that needs x86_64, KVM or Docker names a GitHub-hosted runner."""
        for wf, d in workflows():
            for name, job in d["jobs"].items():
                body = json.dumps({k: v for k, v in job.items() if k != "runs-on"})
                if wf in HOSTED_ONLY_WORKFLOWS or "services" in job or NEEDS_HOSTED.search(body):
                    self.assertFalse(any(lab in str(job.get("runs-on", "")) for lab in MAC_LABELS), f"{wf}:{name}")

    def test_the_mac_is_never_used_by_release_signing_or_deploy_workflows(self):
        for wf, d, name, job in mac_jobs():
            self.assertNotIn(wf, {"release.yml", "security-nightly.yml", "apps-rescan.yml", "changes-collect.yml",
                                  "dev-build.yml"})

    def test_jobs_with_secrets_stay_hosted(self):
        for wf, d in workflows():
            for name, job in d["jobs"].items():
                if SECRET_USE.search(json.dumps(job)):
                    self.assertFalse(any(lab in str(job.get("runs-on", "")) for lab in MAC_LABELS), f"{wf}:{name}")


class MergeGate(unittest.TestCase):
    """merge-gate is main's one required check: moving it to the gate pool must not change how it reports."""

    def setUp(self):
        self.wf = yaml.safe_load((WF / "gate.yml").read_text())
        self.job = self.wf["jobs"]["merge-gate"]

    def test_name_trigger_and_always_reporting(self):
        self.assertEqual(self.wf["name"], "merge-gate")
        self.assertEqual(list(self.wf["jobs"]), ["merge-gate"])
        self.assertNotIn("name", self.job)          # the check is matched by name: keep it `merge-gate`
        self.assertNotIn("if", self.job)            # a skipped required check would count as passed
        self.assertNotIn("needs", self.job)
        self.assertNotIn("continue-on-error", self.job)
        on = self.wf.get(True) or self.wf["on"]
        self.assertIn("merge_group", on)
        self.assertIn("pull_request", on)
        self.assertNotIn("paths", on["pull_request"] or {})
        self.assertGreaterEqual(self.job["timeout-minutes"], 180)

    def test_runs_on_the_gate_pool_with_a_hosted_fallback(self):
        ro = self.job["runs-on"]
        self.assertIn("onemind-gate", ro)
        self.assertNotIn("onemind-local", ro)
        self.assertTrue(ro.endswith("|| 'ubuntu-24.04' }}"), ro)

    def test_follows_local_gate_not_local_runner_and_stays_trusted_only(self):
        ro = self.job["runs-on"]
        self.assertIn("vars.LOCAL_GATE == 'on'", ro)
        self.assertNotIn("LOCAL_RUNNER", ro)       # a gate pool with no runners must not stall every merge
        self.assertIn(TRUSTED % "LOCAL_GATE", ro)  # never a fork PR
        self.assertTrue(ro.endswith("|| 'ubuntu-24.04' }}"), ro)
        self.assertFalse(triggers(self.wf) & UNTRUSTED_TRIGGERS)

    def test_needs_only_python_and_the_api(self):
        steps = json.dumps(self.job["steps"])
        self.assertIn("python3 -I scripts/ci-gate.py", steps)
        self.assertNotIn("sudo", steps)            # the gate VM gives its runner no root
        self.assertNotIn("setup-", steps)


class Kit(unittest.TestCase):
    def test_scripts_exist_and_parse(self):
        for f in ("up", "down", "status", "cycle", "provision.sh", "run-one.sh", "job-started.sh"):
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
        self.assertIn('--labels "$label"', text)
        self.assertIn("onemind-local|onemind-gate)", text)   # no other label can be registered
        cycle = (KIT / "cycle").read_text()
        self.assertIn("label=onemind-gate", cycle)
        self.assertIn("label=onemind-local", cycle)

    def test_pool_sizes_are_validated(self):
        for f in ("up", "cycle"):
            text = (KIT / f).read_text()
            self.assertIn("1|2|3) ;;", text, f"{f}: INSTANCES must be 1 to 3")
            self.assertIn("INSTANCES must be 1, 2 or 3", text, f)
            self.assertIn("GATE_RUNNERS:-4", text, f"{f}: the gate pool defaults to 4 slots")
            self.assertIn("GATE_RUNNERS must be a number from 0 to 8", text, f)

    def test_pool_size_checks_reject_bad_values(self):
        for env, ok in ((("INSTANCES", "4"), False), (("INSTANCES", "0"), False), (("GATE_RUNNERS", "x"), False),
                        (("GATE_RUNNERS", "9"), False)):
            r = subprocess.run(["bash", str(KIT / "cycle")], env={"PATH": "/usr/bin:/bin", env[0]: env[1]},
                               capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 2, f"{env}: {r.stderr}")

    def test_the_gate_vm_gives_its_jobs_no_root(self):
        text = (KIT / "provision.sh").read_text()
        self.assertIn("rm -f /etc/sudoers.d/runner", text)
        self.assertIn("ROLE=${ROLE:-worker}", text)
        self.assertIn("ROLE=\"$2\"", (KIT / "up").read_text())
        self.assertIn("install_kit \"$GATE_VM\" gate 1", (KIT / "up").read_text())

    def test_tokens_go_on_stdin_only(self):
        text = (KIT / "cycle").read_text()
        self.assertIn("printf '%s\\n' \"$token\" | limactl shell", text)
        self.assertNotRegex(text, r">\s*\S*token|token\S*\s*>", "a token is written to a file")

    def test_tokens_never_reach_config_sh_argv(self):
        # argv is world-readable in /proc/<pid>/cmdline: config.sh gets the token from its environment input.
        text = (KIT / "run-one.sh").read_text()
        self.assertIn("ACTIONS_RUNNER_INPUT_TOKEN=$token ./config.sh", text)
        self.assertNotIn("--token", text)
        self.assertNotRegex((KIT / "cycle").read_text(), r"onemind-ci-run-one[^\n]*\$token")

    def test_every_job_gets_a_fresh_vm_and_the_switch_goes_off_on_exit(self):
        text = (KIT / "cycle").read_text()
        self.assertIn("limactl clone", text)
        self.assertIn('limactl delete --force "$run"', text)
        self.assertIn("setvar LOCAL_RUNNER off", text)
        self.assertIn("setvar LOCAL_GATE off", text)
        self.assertIn("trap cleanup EXIT INT TERM", text)

    def test_gate_slots_clone_per_job(self):
        text = (KIT / "cycle").read_text()
        # both pools go through the same clone-start-delete path; only FRESH=none workers reuse the base VM
        self.assertIn('if [ "$pool" = gate ] || [ "$FRESH" = clone ]; then', text)
        self.assertIn("base=$GATE_VM", text)
        self.assertIn("cpus=${GATE_CPUS:-1} mem=${GATE_MEMORY:-1}", text)
        self.assertNotIn("run=$GATE_VM\n", text)

    def test_local_gate_is_never_switched_on_at_start(self):
        cycle = (KIT / "cycle").read_text()
        parent = cycle[:cycle.index("wait; exit")]
        self.assertNotIn("setvar LOCAL_GATE on", parent)        # only a slot whose runner is online turns it on
        self.assertIn('setvar LOCAL_GATE off "until a gate runner is online"', parent)
        self.assertIn('touch "$unhealthy"; setvar LOCAL_GATE off', cycle)          # 3 failures switch it off
        self.assertIn("switchvar=LOCAL_GATE", cycle)
        up = (KIT / "up").read_text()
        self.assertIn('if [ "$GATE_RUNNERS" -eq 0 ]; then gh variable set LOCAL_GATE --body off', up)
        self.assertNotIn("LOCAL_GATE --body on", up)
        down = (KIT / "down").read_text()
        self.assertIn("gh variable set LOCAL_GATE --body off", down)
        self.assertIn("gh variable set LOCAL_RUNNER --body off", down)

    # Stub gh: repo variables live in files (a missing one reads like a 404), the registration token can be
    # made to fail, and the runner list prints the names in <state>/online. Stub limactl: every VM call works
    # (unless <state>/clone-fails exists); `shell` into a gate clone runs <state>/round with the round number,
    # and a worker round just waits.
    GH = r"""#!/bin/sh
d=%(d)s
echo "$*" >> "$d/gh.log"
case "$*" in
  "variable set "*) printf '%%s' "$5" > "$d/var.$3" ;;
  *registration-token*) [ -e "$d/token-fails" ] && exit 1; echo tok ;;
  *actions/runners*) cat "$d/online" 2>/dev/null ;;
  *actions/variables/*) v=${2##*/}; [ -e "$d/var.$v" ] || exit 1; cat "$d/var.$v"; echo ;;
esac
exit 0
"""
    LIMACTL = r"""#!/bin/sh
d=%(d)s
case $1 in
  list) printf '%(vms)s' ;;
  clone) [ -e "$d/clone-fails" ] && exit 1 ;;
  shell) cat >/dev/null
    case $2 in *-gate-run-*) ;; *) exec sleep 60 ;; esac
    n=$(( $(cat "$d/rounds" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$d/rounds"
    exec sh "$d/round" "$n" "$d" ;;
esac
exit 0
"""
    GATE_RUNNER = "onemind-gate-lima-onemind-ci-gate-run-1-gate-1"   # run-one.sh: <label>-<hostname>-<slot>

    def run_cycle(self, gate_runners, vms, round_script="exec sleep 60\n", until=None, files=(), timeout=1.5,
                  env_extra=None):
        """Start `cycle` with stub gh and limactl, wait until `until(sets)` is true (or `timeout` seconds),
        stop it, and return the switch changes it made, in order, and its output."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "gh").write_text(self.GH % {"d": tmp})
            (d / "limactl").write_text(self.LIMACTL % {"d": tmp, "vms": "".join(v + "\\n" for v in vms)})
            (d / "round").write_text(round_script)
            for f in ("gh", "limactl"):
                (d / f).chmod(0o755)
            for f in files:
                (d / f).touch()
            env = {"PATH": f"{tmp}:/usr/bin:/bin", "TMPDIR": tmp, "INSTANCES": "1", "GATE_RUNNERS": gate_runners,
                   "CYCLE_NAP": "0.05", "GATE_ONLINE_WAIT": "20", **(env_extra or {})}
            out = d / "out.log"
            with out.open("w") as fh:
                p = subprocess.Popen(["bash", str(KIT / "cycle")], env=env, stdout=fh, stderr=subprocess.STDOUT,
                                     start_new_session=True)

            def sets():
                log = d / "gh.log"
                lines = log.read_text().splitlines() if log.exists() else []
                return [line.split()[2:5:2] for line in lines if line.startswith("variable set")]
            try:
                end = time.monotonic() + (20 if until else timeout)
                while time.monotonic() < end and not (until and until(sets())):
                    time.sleep(0.1)
                os.killpg(p.pid, signal.SIGTERM)
                p.wait(timeout=20)
            finally:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            return sets(), out.read_text()

    @staticmethod
    def gate_sets(sets):
        return [v for k, v in sets if k == "LOCAL_GATE"]

    def test_no_gate_vm_means_local_gate_off(self):
        sets, _ = self.run_cycle("4", ["onemind-ci"])
        self.assertNotIn(["LOCAL_GATE", "on"], sets)
        self.assertEqual(sets[:2], [["LOCAL_RUNNER", "on"], ["LOCAL_GATE", "off"]])
        self.assertEqual(sets[-2:], [["LOCAL_GATE", "off"], ["LOCAL_RUNNER", "off"]])   # trap on exit

    def test_zero_gate_slots_means_local_gate_off(self):
        sets, _ = self.run_cycle("0", ["onemind-ci", "onemind-ci-gate"])
        self.assertNotIn(["LOCAL_GATE", "on"], sets)

    def test_local_gate_stays_off_until_a_gate_runner_is_online(self):
        # the clone is up and the round runs, but no runner is online: merge-gate must not pick the gate pool
        sets, out = self.run_cycle("1", ["onemind-ci", "onemind-ci-gate"], timeout=2)
        self.assertIn("waiting for one job (onemind-gate)", out)
        self.assertEqual(self.gate_sets(sets), ["off", "off"])               # start, then the trap on exit
        self.assertEqual(sets[-2:], [["LOCAL_GATE", "off"], ["LOCAL_RUNNER", "off"]])

    def test_local_gate_goes_on_once_the_gate_runner_is_online(self):
        online = f'echo {self.GATE_RUNNER} > "$2/online"; exec sleep 60\n'
        sets, _ = self.run_cycle("1", ["onemind-ci", "onemind-ci-gate"], online, until=lambda s: ["LOCAL_GATE", "on"] in s)
        self.assertEqual(self.gate_sets(sets), ["off", "on", "off"])          # start, runner online, exit
        self.assertEqual(sets[-2:], [["LOCAL_GATE", "off"], ["LOCAL_RUNNER", "off"]])

    def test_another_slots_runner_does_not_count(self):
        other = 'echo onemind-gate-lima-onemind-ci-gate-run-2-gate-1 > "$2/online"; exec sleep 60\n'
        sets, _ = self.run_cycle("1", ["onemind-ci", "onemind-ci-gate"], other, timeout=2)
        self.assertNotIn("on", self.gate_sets(sets))

    def strikes_off(self, sets):
        return self.gate_sets(sets).count("off") >= 2    # the start sets off once; the third failure again

    def test_three_failed_runner_rounds_switch_local_gate_off(self):
        # clone and start work; config.sh (or the runner) fails in every round
        sets, out = self.run_cycle("1", ["onemind-ci", "onemind-ci-gate"], "exit 1\n", until=self.strikes_off)
        self.assertNotIn("on", self.gate_sets(sets))
        self.assertIn("LOCAL_GATE=off ([gate-1] 3 gate failures in a row: runner round failed)", out)

    def test_three_failed_tokens_switch_local_gate_off(self):
        sets, out = self.run_cycle("1", ["onemind-ci", "onemind-ci-gate"], until=self.strikes_off,
                                   files=("token-fails",))
        self.assertIn("LOCAL_GATE=off ([gate-1] 3 gate failures in a row: could not get a registration token", out)

    def test_three_failed_clones_switch_local_gate_off(self):
        _, out = self.run_cycle("1", ["onemind-ci", "onemind-ci-gate"], until=self.strikes_off,
                                files=("clone-fails",))
        self.assertIn("LOCAL_GATE=off ([gate-1] 3 gate failures in a row: could not clone and start", out)

    def test_a_runner_that_never_comes_online_is_a_failure(self):
        sets, out = self.run_cycle("1", ["onemind-ci", "onemind-ci-gate"], until=self.strikes_off,
                                   env_extra={"GATE_ONLINE_WAIT": "0"})
        self.assertIn("3 gate failures in a row: runner never came online in 0s", out)

    def test_after_switch_off_a_probe_whose_runner_is_online_switches_it_back_on(self):
        recover = f'[ "$1" -le 3 ] && exit 1\necho {self.GATE_RUNNER} > "$2/online"; exec sleep 60\n'
        sets, out = self.run_cycle("1", ["onemind-ci", "onemind-ci-gate"], recover,
                                   until=lambda s: self.gate_sets(s)[-1:] == ["on"])
        self.assertEqual(self.gate_sets(sets), ["off", "off", "on", "off"])   # start, 3 strikes, probe, exit
        self.assertIn("3 gate failures in a row: runner round failed", out)

    def test_mq_pool_kit_is_documented_and_lists_hosted_image_tools(self):
        text = (KIT / "README.md").read_text()
        for needle in ("MQ_RUNNER", "onemind-mq", "merge_group", "sudo", "gitleaks"):
            self.assertIn(needle, text)

    def test_vm_shares_nothing_with_the_mac(self):
        self.assertRegex((KIT / "lima.yaml").read_text(), r"(?m)^mounts: \[\]$")

    def test_launchd_plist_has_no_host_path(self):
        text = (KIT / "dev.onemind.ci-runner.plist").read_text()
        self.assertNotRegex(text, r"/Users/|/home/")
        self.assertIn("__CYCLE__", text)
        for ph in ("__INSTANCES__", "__GATE_RUNNERS__", "__GATE_CPUS__", "__GATE_MEMORY__", "__CPUS__", "__MEMORY__"):
            self.assertIn(ph, text)
            self.assertIn(ph, (KIT / "up").read_text(), f"up does not fill {ph}")

    def test_down_stops_and_wipes_the_gate_vm_too(self):
        text = (KIT / "down").read_text()
        self.assertIn('grep -e "^$VM-run-" -e "^$GATE_VM-run-"', text)   # gate clones are deleted too
        self.assertIn('limactl stop "$GATE_VM"', text)
        self.assertIn('limactl delete --force "$GATE_VM"', text)


class JobStartedHook(unittest.TestCase):
    """The fail-closed guard the runner runs before every job: fork and deleted-fork PRs are refused."""
    HOOK = KIT / "job-started.sh"
    REPO = "onemindos/ONEMINDOS"

    def run_hook(self, payload, repo=REPO, event_file=True):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
            if repo is not None:
                env["GITHUB_REPOSITORY"] = repo
            if event_file:
                path = Path(tmp) / "event.json"
                path.write_text(payload if isinstance(payload, str) else json.dumps(payload))
                env["GITHUB_EVENT_PATH"] = str(path)
            return subprocess.run(["sh", str(self.HOOK)], env=env, capture_output=True, text=True, timeout=30)

    def pr(self, head):
        return {"pull_request": {"head": {"repo": head}}}

    def test_same_repo_pull_request_runs(self):
        r = self.run_hook(self.pr({"full_name": self.REPO}))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("onemind-local guard: ok", r.stdout)

    def test_fork_pull_request_is_refused(self):
        r = self.run_hook(self.pr({"full_name": "someone/ONEMINDOS"}))
        self.assertEqual(r.returncode, 1)
        self.assertIn("onemind-local guard: REFUSED", r.stderr)

    def test_deleted_fork_pull_request_is_refused(self):
        for head in (None, {}):
            r = self.run_hook(self.pr(head))
            self.assertEqual(r.returncode, 1, head)
            self.assertIn("REFUSED", r.stderr)
        r = self.run_hook({"pull_request": {}})
        self.assertEqual(r.returncode, 1)

    def test_push_runs(self):
        r = self.run_hook({"ref": "refs/heads/main"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("onemind-local guard: ok", r.stdout)

    def test_missing_environment_is_refused(self):
        for r in (self.run_hook({}, repo=None), self.run_hook({}, event_file=False),
                  self.run_hook("not json"), self.run_hook({}, repo="")):
            self.assertEqual(r.returncode, 1)
            self.assertIn("onemind-local guard: REFUSED", r.stderr)

    def test_provision_installs_the_hook_for_every_runner(self):
        text = (KIT / "provision.sh").read_text()
        self.assertIn("/usr/local/bin/onemind-ci-job-started.sh", text)   # the runner needs the .sh suffix
        self.assertIn("ACTIONS_RUNNER_HOOK_JOB_STARTED=/usr/local/bin/onemind-ci-job-started.sh", text)
        self.assertIn('"$R/.env', text)
        self.assertIn("job-started.sh", (KIT / "up").read_text())


class AppsNode(unittest.TestCase):
    """#299 (CI-10 leftover): ci-apps `validate` runs JS regression tests in Node 22 on both pools.

    The job sets Node up itself with the same pinned setup-node as ci-sdk (the Debian arm64 VM is a supported
    setup-node platform, unlike setup-python), and the worker VM also carries a pinned Node 22 of its own.
    """

    SETUP_NODE = re.compile(r"^actions/setup-node@[0-9a-f]{40}$")

    def setup_node_steps(self, wf, job):
        steps = yaml.safe_load((WF / wf).read_text())["jobs"][job]["steps"]
        return steps, [i for i, s in enumerate(steps) if str(s.get("uses", "")).startswith("actions/setup-node@")]

    def test_validate_sets_up_node_22_with_the_ci_sdk_pin(self):
        sdk = yaml.safe_load((WF / "ci-sdk.yml").read_text())
        pins = {s["uses"] for job in sdk["jobs"].values() for s in job.get("steps", [])
                if str(s.get("uses", "")).startswith("actions/setup-node@")}
        self.assertEqual(len(pins), 1, pins)
        steps, idx = self.setup_node_steps("ci-apps.yml", "validate")
        self.assertEqual(len(idx), 1, "ci-apps validate needs exactly one setup-node step")
        step = steps[idx[0]]
        self.assertRegex(step["uses"], self.SETUP_NODE)
        self.assertEqual({step["uses"]}, pins, "same setup-node pin as ci-sdk")
        self.assertEqual(str(step["with"]["node-version"]), "22")
        self.assertNotIn("if", step, "Node 22 on the hosted and the local runner alike")

    def test_node_is_ready_before_the_unit_tests_and_checked(self):
        steps, idx = self.setup_node_steps("ci-apps.yml", "validate")
        names = [s.get("name", "") for s in steps]
        unit = names.index("Unit tests (sdk/tools)")
        self.assertLess(idx[0], unit)
        check = [i for i, s in enumerate(steps) if "node --version" in str(s.get("run", ""))]
        self.assertTrue(check and idx[0] < check[0] < unit, "validate prints and checks the Node major")
        self.assertIn("grep -q '^v22\\.'", steps[check[0]]["run"])

    def test_worker_vm_gets_a_pinned_node_22(self):
        pin = dict(line.split("=", 1) for line in (KIT / "runner.pin").read_text().splitlines()
                   if line and not line.startswith("#"))
        self.assertRegex(pin.get("NODE_VERSION", ""), r"^22\.\d+\.\d+$")
        self.assertRegex(pin.get("NODE_SHA256", ""), r"^[0-9a-f]{64}$")
        text = (KIT / "provision.sh").read_text()
        self.assertIn("https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-arm64.tar.xz", text)
        self.assertIn('echo "${NODE_SHA256}  /tmp/node.txz" | sha256sum -c -', text)
        # Only the worker VM runs ci-apps; the gate VM stays minimal.
        self.assertRegex(text, r'if \[ "\$ROLE" = worker \] && ! node --version 2>/dev/null \| grep -q "\^v\$\{NODE_VERSION\}\$"')


if __name__ == "__main__":
    unittest.main()
