# SPDX-License-Identifier: Apache-2.0
"""CI-10 and CI-13 (issue 299): the Mac runner pools take trusted, secret-free, arm64-safe jobs only.

Two labels pick the Mac: `onemind-local` (worker VMs, one fresh clone per job) and `onemind-gate` (the small
gate VM for API-only jobs). A job may pick either only if (1) the choice is behind the LOCAL_RUNNER switch
with a GitHub-hosted fallback, (2) a pull request from a fork can never select it, (3) nothing in the job,
or in its workflow's top level, can read a secret or an environment or write to the repo, and (4) the job
needs nothing the Mac's Debian 13 arm64 VMs lack: x86_64, KVM, Docker or GitHub's preinstalled SDKs.
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
MAC_LABELS = ("onemind-local", "onemind-gate")
TRUSTED = ("(vars.LOCAL_RUNNER == 'on' && (github.event_name != 'pull_request' || "
           "github.event.pull_request.head.repo.full_name == github.repository))")
# The gate pool is one small VM shared by several runner processes and reused between jobs: only jobs that
# just poll the GitHub API belong there.
GATE_JOBS = {("gate.yml", "merge-gate")}
# What the Mac's VMs cannot do: x86_64 binaries, KVM, QEMU for x86, Docker (and service containers),
# GitHub's preinstalled Android SDK, macOS or Windows tools.
NEEDS_HOSTED = re.compile(
    r"/dev/kvm|\bkvm\b|qemu-system-x86|setup-qemu-action|setup-buildx-action|docker[ /]|docker\b\s+compose|"
    r"linux_x64|linux-amd64\b|-amd64 -version|_X64\b|ANDROID_HOME|xcodebuild|make image|make battery|"
    r"battery\.yml|\bk3d\b", re.I)
# Workflows that build or test the OS image, need KVM or sign/publish: never on the Mac.
HOSTED_ONLY_WORKFLOWS = {"image.yml", "battery.yml", "nightly.yml", "net-2vm.yml", "perf-smoke.yml",
                         "release.yml", "security-nightly.yml", "apps-rescan.yml", "changes-collect.yml",
                         "dev-build.yml", "apps-gate-all.yml", "ci-desktop.yml"}
# setup-python has no Python 3.13 build for Debian 13 arm64. PR #352 moves ci-apps `validate` to a venv;
# until it merges, that one job is the known exception.
SETUP_PYTHON_PENDING = {("ci-apps.yml", "validate")}


def workflows():
    for p in sorted(WF.glob("*.yml")):
        yield p.name, yaml.safe_load(p.read_text())


def mac_jobs(label=None):
    for wf, d in workflows():
        for name, job in d["jobs"].items():
            ro = str(job.get("runs-on", ""))
            if any(lab in ro for lab in ((label,) if label else MAC_LABELS)):
                yield wf, d, name, job


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
            ro = job["runs-on"]
            where = f"{wf}:{name}"
            label = next(lab for lab in MAC_LABELS if lab in ro)
            want = "${{ %s && fromJSON('[\"self-hosted\",\"%s\"]') || 'ubuntu-24.04' }}" % (TRUSTED, label)
            self.assertEqual(ro, want, where)

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

    def test_needs_only_python_and_the_api(self):
        steps = json.dumps(self.job["steps"])
        self.assertIn("python3 -I scripts/ci-gate.py", steps)
        self.assertNotIn("sudo", steps)            # the gate VM gives its runner no root
        self.assertNotIn("setup-", steps)


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
            self.assertIn("GATE_RUNNERS:-6", text, f"{f}: the gate pool defaults to 6 runners")
            self.assertIn("GATE_RUNNERS must be a number from 0 to 12", text, f)

    def test_pool_size_checks_reject_bad_values(self):
        for env, ok in ((("INSTANCES", "4"), False), (("INSTANCES", "0"), False), (("GATE_RUNNERS", "x"), False),
                        (("GATE_RUNNERS", "13"), False)):
            r = subprocess.run(["bash", str(KIT / "cycle")], env={"PATH": "/usr/bin:/bin", env[0]: env[1]},
                               capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 2, f"{env}: {r.stderr}")

    def test_the_gate_vm_gives_its_jobs_no_root(self):
        text = (KIT / "provision.sh").read_text()
        self.assertIn("rm -f /etc/sudoers.d/runner", text)
        self.assertIn("ROLE=${ROLE:-worker}", text)
        self.assertIn("ROLE=\"$2\"", (KIT / "up").read_text())
        self.assertIn("install_kit \"$GATE_VM\" gate", (KIT / "up").read_text())

    def test_tokens_go_on_stdin_only(self):
        text = (KIT / "cycle").read_text()
        self.assertIn("printf '%s\\n' \"$token\" | limactl shell", text)
        self.assertNotRegex(text, r">\s*\S*token|token\S*\s*>", "a token is written to a file")

    def test_every_job_gets_a_fresh_vm_and_the_switch_goes_off_on_exit(self):
        text = (KIT / "cycle").read_text()
        self.assertIn("limactl clone", text)
        self.assertIn('limactl delete --force "$run"', text)
        self.assertIn("LOCAL_RUNNER --body off", text)
        self.assertIn("trap cleanup EXIT INT TERM", text)

    def test_vm_shares_nothing_with_the_mac(self):
        self.assertRegex((KIT / "lima.yaml").read_text(), r"(?m)^mounts: \[\]$")

    def test_launchd_plist_has_no_host_path(self):
        text = (KIT / "dev.onemind.ci-runner.plist").read_text()
        self.assertNotRegex(text, r"/Users/|/home/")
        self.assertIn("__CYCLE__", text)
        for ph in ("__INSTANCES__", "__GATE_RUNNERS__", "__CPUS__", "__MEMORY__"):
            self.assertIn(ph, text)
            self.assertIn(ph, (KIT / "up").read_text(), f"up does not fill {ph}")

    def test_down_stops_and_wipes_the_gate_vm_too(self):
        text = (KIT / "down").read_text()
        self.assertIn('limactl stop "$GATE_VM"', text)
        self.assertIn('limactl delete --force "$GATE_VM"', text)


if __name__ == "__main__":
    unittest.main()
