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

    def test_selection_is_switchable_fork_safe_and_has_a_hosted_fallback(self):
        for wf, _, name, job in kvm_jobs():
            ro, where = job["runs-on"], f"{wf}:{name}"
            self.assertIn("vars.KVM_RUNNER == 'on'", ro, where)
            self.assertIn("github.event.pull_request.head.repo.full_name == github.repository", ro, where)
            self.assertIn("github.event_name != 'pull_request'", ro, where)
            self.assertRegex(ro, r"\|\| ('ubuntu-24\.04'|matrix\.runner|inputs\.runner) \}\}$", where)
            if "matrix.runner" in ro or "inputs.runner" in ro:   # arm64 legs must never land on an x86 host
                self.assertRegex(ro, r"(matrix|inputs)\.runner == 'ubuntu-24\.04'", where)

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
                      ("template.sh", "sh"), ("net.sh", "sh"), ("provision.sh", "sh"), ("run-one.sh", "sh")):
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

    def test_runners_are_ephemeral_and_labelled(self):
        text = (KIT / "run-one.sh").read_text()
        self.assertIn("--ephemeral", text)
        self.assertIn(f"--labels {LABEL}", text)
        self.assertIn('rm -f "$f"', text)   # the token file is gone before the job starts

    def test_every_job_gets_a_fresh_vm_and_the_switch_goes_off_on_exit(self):
        text = (KIT / "cycle").read_text()
        self.assertIn('qm clone "$TID" "$id"', text)
        self.assertIn('qm destroy "$id" --purge', text)
        self.assertIn("switch off", text)
        self.assertIn("trap cleanup EXIT INT TERM", text)
        self.assertIn("ExecStopPost=+/usr/bin/systemctl --no-block poweroff", (KIT / "provision.sh").read_text())

    def test_the_github_token_never_reaches_a_command_line(self):
        text = (KIT / "cycle").read_text()
        self.assertIn("curl -fsS -K -", text)
        self.assertNotRegex(text, r"curl[^\n]*Authorization")
        self.assertIn("--pass-stdin 1", text)   # the registration token goes to the VM on stdin

    def test_job_network_has_no_lan_and_no_host(self):
        text = (KIT / "net.sh").read_text()
        for rng in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "169.254.0.0/16"):
            self.assertIn(rng, text)
        self.assertIn('-i $BR -d $d -j DROP', text)
        self.assertIn("INPUT -i $BR -j DROP", text)
        self.assertIn("bridge-ports none", text)
        self.assertIn('--net0 "virtio,bridge=$BR"', (KIT / "template.sh").read_text())


if __name__ == "__main__":
    unittest.main()
