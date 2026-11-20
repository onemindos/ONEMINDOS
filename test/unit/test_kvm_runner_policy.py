# SPDX-License-Identifier: Apache-2.0
"""CI-14: the x86 KVM runner (a Proxmox VE host) takes trusted, secret-free x86 jobs only.

A job may pick the `onemind-kvm` runner only if (1) the choice is behind the KVM_RUNNER switch with a
GitHub-hosted fallback, (2) a pull request from a fork can never select it, (3) nothing in the job, its
workflow's top level, or any caller of it can read a secret or an environment, and (4) the release-signing
path stays GitHub-hosted. The kit must give every job a fresh, destroyed VM on a network with no LAN access.
"""
import json
import re
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"
KIT = ROOT / "scripts" / "ci-runner-kvm"
SECRET_USE = re.compile(r"secrets\.(?!GITHUB_TOKEN\b)|secrets:\s*inherit|toJSON\(secrets\)", re.I)
LABEL = "onemind-kvm"


def workflows():
    for p in sorted(WF.glob("*.yml")):
        yield p.name, yaml.safe_load(p.read_text())


def kvm_jobs():
    for wf, d in workflows():
        for name, job in d["jobs"].items():
            if LABEL in str(job.get("runs-on", "")):
                yield wf, d, name, job


class KvmRunnerPolicy(unittest.TestCase):
    def test_the_x86_kvm_jobs_use_it(self):
        found = {(wf, name) for wf, _, name, _ in kvm_jobs()}
        for want in [("image.yml", "image"), ("image.yml", "smoke"), ("image.yml", "cloud"),
                     ("image.yml", "installer"), ("battery.yml", "battery")]:
            self.assertIn(want, found)

    def test_selection_is_exactly_the_reviewed_expression(self):
        # Whole-string match, not fragments: swapping && for || or dropping the fork guard fails here.
        trust = ("(github.event_name != 'pull_request' || "
                 "github.event.pull_request.head.repo.full_name == github.repository)")
        kvm = f"vars.KVM_RUNNER == 'on' && {trust}"
        sel = "fromJSON('[\"self-hosted\",\"onemind-kvm\"]')"
        want = {
            ("image.yml", "image"): f"${{{{ (matrix.runner == 'ubuntu-24.04' && {kvm}) && {sel} || matrix.runner }}}}",
            ("image.yml", "smoke"): f"${{{{ ({kvm}) && {sel} || 'ubuntu-24.04' }}}}",
            ("image.yml", "cloud"): f"${{{{ ({kvm}) && {sel} || 'ubuntu-24.04' }}}}",
            ("image.yml", "installer"): f"${{{{ ({kvm}) && {sel} || 'ubuntu-24.04' }}}}",
            ("battery.yml", "battery"): (f"${{{{ (inputs.runner == 'ubuntu-24.04' && github.workflow != 'security-nightly' && "
                                         f"{kvm}) && {sel} || inputs.runner }}}}"),
        }
        got = {(wf, name): job["runs-on"] for wf, _, name, job in kvm_jobs()}
        self.assertEqual(got, want)

    def test_every_self_hosted_job_is_a_reviewed_one(self):
        # Runners carry only self-hosted + their own label, but a job asking for [self-hosted] alone
        # would still match; every self-hosted job must be one this test or CI-10's test reviews.
        for wf, d in workflows():
            for name, job in d["jobs"].items():
                ro = str(job.get("runs-on", ""))
                if "self-hosted" in ro:
                    self.assertTrue(LABEL in ro or "onemind-local" in ro, f"{wf}:{name} asks for an unreviewed self-hosted runner")

    def test_no_job_that_can_pick_it_can_read_a_secret(self):
        for wf, d, name, job in kvm_jobs():
            where = f"{wf}:{name}"
            self.assertNotRegex(json.dumps(job), SECRET_USE, where)
            self.assertNotRegex(json.dumps(d.get("env", {})), SECRET_USE, f"{wf} top-level env")
            self.assertNotIn("environment", job, where)
            self.assertNotIn("docker/login-action", json.dumps(job), where)

    def test_no_caller_hands_the_battery_a_secret(self):
        for wf, d in workflows():
            for name, job in d["jobs"].items():
                if str(job.get("uses", "")).endswith("workflows/battery.yml"):
                    self.assertNotIn("secrets", job, f"{wf}:{name}")

    def test_the_release_path_stays_hosted(self):
        for wf, _, name, _ in kvm_jobs():
            self.assertNotIn(wf, {"release.yml", "security-nightly.yml", "apps-rescan.yml", "changes-collect.yml"})
        battery = yaml.safe_load((WF / "battery.yml").read_text())["jobs"]["battery"]["runs-on"]
        self.assertIn("github.workflow != 'security-nightly'", battery)
        self.assertEqual(yaml.safe_load((WF / "security-nightly.yml").read_text())["name"], "security-nightly")


class Kit(unittest.TestCase):
    def test_scripts_exist_and_parse(self):
        for f, sh in (("up", "bash"), ("down", "bash"), ("status", "bash"), ("cycle", "bash"),
                      ("template.sh", "sh"), ("net.sh", "sh"), ("provision.sh", "sh"), ("run-one.sh", "sh"),
                      ("job-started.sh", "sh")):
            path = KIT / f
            self.assertTrue(path.is_file(), f)
            self.assertTrue(path.stat().st_mode & 0o111, f"{f} is not executable")
            subprocess.run([sh, "-n", str(path)], check=True)

    def test_no_token_and_no_host_path_in_the_kit(self):
        for p in KIT.iterdir():
            text = p.read_text()
            self.assertNotRegex(text, r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_", p.name)
            self.assertNotRegex(text, r"/Users/|192\.168\.(?!0\.0/16)\d+\.\d+", p.name)

    def test_downloads_are_pinned_and_checked(self):
        pin = (KIT / "runner.pin").read_text()
        self.assertRegex(pin, r"(?m)^RUNNER_SHA256=[0-9a-f]{64}$")
        self.assertRegex(pin, r"(?m)^UBUNTU_IMAGE_SHA256=[0-9a-f]{64}$")
        self.assertRegex(pin, r"(?m)^UBUNTU_IMAGE_URL=https://cloud-images\.ubuntu\.com/noble/\d{8}/")
        self.assertIn('"${RUNNER_SHA256}  /tmp/runner.tgz" | sha256sum -c -', (KIT / "provision.sh").read_text())
        self.assertIn('"$UBUNTU_IMAGE_SHA256  $img" | sha256sum -c -', (KIT / "template.sh").read_text())

    def test_runners_are_single_use_jit_with_fixed_labels(self):
        cycle = (KIT / "cycle").read_text()
        self.assertIn("actions/runners/generate-jitconfig", cycle)
        self.assertIn('\\"labels\\":[\\"self-hosted\\",\\"onemind-kvm\\"]', cycle)
        self.assertNotIn("registration-token", cycle)   # never the org-wide registration token
        self.assertIn('api DELETE "orgs/$ORG/actions/runners/$rid"', cycle)
        run = (KIT / "run-one.sh").read_text()
        self.assertIn("ACTIONS_RUNNER_INPUT_JITCONFIG", run)
        self.assertIn('rm -f "$f"', run)   # the config file is gone before the runner starts
        self.assertNotIn("config.sh", run)

    def test_every_job_gets_a_fresh_isolated_vm_and_the_switch_goes_off_on_exit(self):
        text = (KIT / "cycle").read_text()
        self.assertIn('qm clone "$TID" "$id"', text)
        self.assertIn('qm destroy "$1" --purge', text)
        self.assertIn('qm unlock "$1"', text)          # a killed clone's lock cannot wedge the loop
        self.assertIn('bridge link set dev "tap${id}i0" isolated on', text)   # job VMs cannot see each other
        self.assertIn("switch off", text)
        self.assertIn("trap cleanup EXIT INT TERM", text)
        self.assertIn("pgrep -f Runner.Worker", text)  # the job limit counts from the job's start, not idle time
        self.assertIn("ExecStopPost=+/usr/bin/systemctl --no-block poweroff", (KIT / "provision.sh").read_text())

    def test_the_github_token_never_reaches_a_command_line(self):
        text = (KIT / "cycle").read_text()
        self.assertIn("curl -fsS -K -", text)
        self.assertNotRegex(text, r"curl[^\n]*Authorization")
        self.assertIn("--pass-stdin 1", text)   # the JIT config goes to the VM on stdin

    def test_clones_do_not_change_under_a_job(self):
        self.assertIn("--ciupgrade 0", (KIT / "template.sh").read_text())
        prov = (KIT / "provision.sh").read_text()
        self.assertIn("apt-daily.timer apt-daily-upgrade.timer", prov)
        self.assertIn("purge -y -qq unattended-upgrades", prov)

    def test_fork_pull_requests_are_refused_on_the_machine(self):
        prov = (KIT / "provision.sh").read_text()
        self.assertIn("ACTIONS_RUNNER_HOOK_JOB_STARTED=/usr/local/bin/onemind-ci-job-started", prov)
        hook = KIT / "job-started.sh"
        for event, repo, rc in (
            ({"pull_request": {"head": {"repo": {"full_name": "someone/ONEMINDOS"}}}}, "onemindos/ONEMINDOS", 1),
            ({"pull_request": {"head": {"repo": None}}}, "onemindos/ONEMINDOS", 1),
            ({"pull_request": {"head": {"repo": {"full_name": "onemindos/ONEMINDOS"}}}}, "onemindos/ONEMINDOS", 0),
            ({"ref": "refs/heads/main"}, "onemindos/ONEMINDOS", 0),
        ):
            import os, tempfile
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
                json.dump(event, f)
            try:
                r = subprocess.run(["sh", str(hook)], env={"PATH": os.environ["PATH"], "GITHUB_EVENT_PATH": f.name,
                                                          "GITHUB_REPOSITORY": repo}, capture_output=True)
                self.assertEqual(r.returncode, rc, (event, r.stderr))
            finally:
                os.unlink(f.name)

    def test_job_network_has_no_lan_no_host_no_ipv6_no_spoofing(self):
        text = (KIT / "net.sh").read_text()
        for rng in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "169.254.0.0/16"):
            self.assertIn(rng, text)
        self.assertIn("iptables FORWARD -i $BR -d $d -j DROP", text)
        self.assertIn("iptables INPUT -i $BR -j DROP", text)
        self.assertIn("iptables FORWARD -i $BR ! -s $NET.0/24 -j DROP", text)
        self.assertIn("ip6tables INPUT -i $BR -j DROP", text)
        self.assertIn("ip6tables FORWARD -i $BR -j DROP", text)
        self.assertIn("net.ipv6.conf.$BR.disable_ipv6=1", text)
        self.assertIn(" -C $chain $spec 2>/dev/null || ", text)   # no duplicate rules on ifreload
        self.assertIn("is not ours", text)                         # never takes over someone else's bridge
        self.assertIn("bridge-ports none", text)
        self.assertIn('--net0 "virtio,bridge=$BR"', (KIT / "template.sh").read_text())


if __name__ == "__main__":
    unittest.main()
