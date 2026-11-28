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
                     ("image.yml", "installer"), ("battery.yml", "battery"), ("ci-apps.yml", "gate-kvm")]:
            self.assertIn(want, found)

    def test_selection_is_exactly_the_reviewed_expression(self):
        # Whole-string match, not fragments: swapping && for || or dropping the fork guard fails here.
        trust = ("(contains(fromJSON('[\"push\",\"schedule\",\"workflow_dispatch\",\"merge_group\"]'), github.event_name) || "
                 "(github.event_name == 'pull_request' && github.event.pull_request.head.repo.full_name == github.repository))")
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
        # ci-apps gate-kvm: a fixed runner list, with the whole trust expression in its `if` (and the hosted twin
        # `gate` taking exactly the opposite), so the KVM job and the hosted job can never both run or both skip.
        got = {(wf, name): job["runs-on"] for wf, _, name, job in kvm_jobs()}
        apps = yaml.safe_load((WF / "ci-apps.yml").read_text())["jobs"]
        self.assertEqual(got.pop(("ci-apps.yml", "gate-kvm")), ["self-hosted", "onemind-kvm"])
        self.assertTrue(apps["gate-kvm"]["if"].endswith(f"&& ({kvm}) }}}}"), apps["gate-kvm"]["if"])
        self.assertTrue(apps["gate"]["if"].endswith(f"&& !({kvm}) }}}}"), apps["gate"]["if"])
        self.assertEqual(apps["gate"]["runs-on"], "ubuntu-24.04")
        self.assertEqual(got, want)

    def test_gate_kvm_is_the_hosted_gate_without_its_secret(self):
        apps = yaml.safe_load((WF / "ci-apps.yml").read_text())["jobs"]
        hosted, kvm = apps["gate"], apps["gate-kvm"]
        # The hosted twin keeps the Docker Hub login (D18); the KVM job must not mention a secret at all, because a
        # job that mentions one gets it delivered to its runner even when the step is skipped.
        self.assertTrue(any("docker/login-action" in str(s.get("uses", "")) for s in hosted["steps"]))
        self.assertNotIn("HAS_DOCKERHUB", kvm.get("env", {}))
        self.assertNotRegex(json.dumps(kvm), SECRET_USE)
        # Same work: the KVM steps are the hosted steps minus the login, plus the host clean-up bookends.
        steps = [s for s in hosted["steps"] if "docker/login-action" not in str(s.get("uses", ""))]
        core = [s for s in kvm["steps"] if "k3d-gate" not in s.get("run", "")]
        self.assertEqual(core, steps)
        self.assertEqual(kvm["strategy"]["max-parallel"], 12)
        self.assertEqual(hosted["strategy"]["max-parallel"], 4)
        self.assertEqual(kvm["strategy"]["matrix"], hosted["strategy"]["matrix"])
        self.assertEqual(kvm["needs"], hosted["needs"])

    def test_every_self_hosted_job_is_a_reviewed_one(self):
        # Runners carry only self-hosted + their own label, but a job asking for [self-hosted] alone
        # would still match; every self-hosted job must be one this test or CI-10/CI-13 (test_local_runner_policy.py) reviews.
        for wf, d in workflows():
            for name, job in d["jobs"].items():
                ro = str(job.get("runs-on", ""))
                if "self-hosted" in ro:
                    self.assertTrue(LABEL in ro or "onemind-local" in ro or "onemind-gate" in ro, f"{wf}:{name} asks for an unreviewed self-hosted runner")

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

    def test_only_allow_listed_events_can_reach_a_kvm_job(self):
        # A new workflow that calls battery.yml (or a kvm job's own workflow) from issue_comment,
        # workflow_run, pull_request_target... would otherwise be routed by an expression it inherits.
        allowed = {"push", "schedule", "workflow_dispatch", "merge_group", "pull_request", "workflow_call"}
        kvm_wfs = {wf for wf, *_ in kvm_jobs()}
        for wf, d in workflows():
            calls = any(str(j.get("uses", "")).endswith("workflows/battery.yml") for j in d["jobs"].values())
            if wf in kvm_wfs or calls:
                on = d.get(True, d.get("on"))   # YAML 1.1 reads the key `on` as True
                events = set(on) if isinstance(on, (dict, list)) else {on}
                self.assertLessEqual(events, allowed, f"{wf} has triggers {sorted(events - allowed)}")

    def test_the_release_path_stays_hosted(self):
        for wf, _, name, _ in kvm_jobs():
            self.assertNotIn(wf, {"release.yml", "security-nightly.yml", "apps-rescan.yml", "changes-collect.yml"})
        battery = yaml.safe_load((WF / "battery.yml").read_text())["jobs"]["battery"]["runs-on"]
        self.assertIn("github.workflow != 'security-nightly'", battery)
        self.assertEqual(yaml.safe_load((WF / "security-nightly.yml").read_text())["name"], "security-nightly")


class Kit(unittest.TestCase):
    def test_scripts_exist_and_parse(self):
        for f, sh in (("up", "bash"), ("down", "bash"), ("status", "bash"), ("cycle", "bash"),
                      ("instances-check", "bash"), ("template.sh", "sh"), ("net.sh", "sh"), ("provision.sh", "sh"), ("run-one.sh", "sh"),
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
        self.assertIn("ACTIONS_RUNNER_HOOK_JOB_STARTED=/usr/local/bin/onemind-ci-job-started.sh", prov)
        # the runner accepts only paths ending in .sh/.ps1/.js, and the file installed must be that path
        self.assertIn("job-started.sh /usr/local/bin/onemind-ci-job-started.sh", prov)
        hook = KIT / "job-started.sh"
        import os, tempfile
        fork = {"head": {"repo": {"full_name": "someone/ONEMINDOS"}}}
        same = {"head": {"repo": {"full_name": "onemindos/ONEMINDOS"}}}
        cases = [   # (event payload or None for "no event file", GITHUB_REPOSITORY, expected rc)
            ({"pull_request": fork}, "onemindos/ONEMINDOS", 1),                        # pull_request from a fork
            ({"pull_request": fork, "action": "submitted", "review": {}}, "onemindos/ONEMINDOS", 1),  # pull_request_review
            ({"pull_request": fork, "action": "opened"}, "onemindos/ONEMINDOS", 1),    # pull_request_target shape
            ({"pull_request": {"head": {"repo": None}}}, "onemindos/ONEMINDOS", 1),    # deleted fork
            ({"pull_request": same}, "onemindos/ONEMINDOS", 0),
            ({"ref": "refs/heads/main"}, "onemindos/ONEMINDOS", 0),                   # push / dispatch / schedule
            ({"ref": "refs/heads/main"}, "onemindos/ONEMINDOS", 1, "issue_comment"),  # not on the allow-list
            ({"workflow_run": {}}, "onemindos/ONEMINDOS", 1, "workflow_run"),
            ({"pull_request": same}, "onemindos/ONEMINDOS", 1, "pull_request_target"),
            ({"ref": "refs/heads/main"}, "onemindos/ONEMINDOS", 1, ""),               # no event name: fail closed
            ({"merge_group": {}}, "onemindos/ONEMINDOS", 0, "merge_group"),
            ({"ref": "refs/heads/main"}, "", 1),                                       # no GITHUB_REPOSITORY: fail closed
            (None, "onemindos/ONEMINDOS", 1),                                          # no event file: fail closed
        ]
        for event, repo, rc, *name in cases:
            ev_name = name[0] if name else ("pull_request" if event and "pull_request" in event else "push")
            env = {"PATH": os.environ["PATH"], "GITHUB_REPOSITORY": repo, "GITHUB_EVENT_NAME": ev_name}
            path = None
            if event is not None:
                with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
                    json.dump(event, f)
                path = env["GITHUB_EVENT_PATH"] = f.name
            try:
                r = subprocess.run(["sh", str(hook)], env=env, capture_output=True, text=True)
                self.assertEqual(r.returncode, rc, (event, repo, r.stderr))
                self.assertIn("onemind-kvm guard:", r.stdout + r.stderr)   # every job log shows the guard ran
            finally:
                if path:
                    os.unlink(path)

    def test_it_never_touches_vms_that_are_not_its_own(self):
        cycle = (KIT / "cycle").read_text()
        self.assertIn("[[ $n == onemind-kvm-[0-9]* ]]", cycle)
        self.assertIn('if ! ours "$1"; then', cycle)
        self.assertIn("grep -qx 'name: onemind-kvm-template'", cycle)
        for f in ("up", "down"):
            self.assertIn("grep -qx 'name: onemind-kvm-template'", (KIT / f).read_text(), f)
        self.assertIn('exit "$rc"', cycle)                  # a failed loop exits non-zero, so systemd restarts it
        self.assertIn('if [ -n "$tj" ]; then fail=0; else', cycle)   # a round with no job backs off

    def test_net_rules_generate_valid_idempotent_commands(self):
        # Run net.sh's own rule generator (not a text search) and check the exact commands.
        text = (KIT / "net.sh").read_text()
        funcs = text[text.index("rules() {"):text.index("{\n  echo \"# OneMind CI job network")]
        out = subprocess.run(["sh", "-c", "BR=vmbr1; NET=10.10.0; UP=vmbr0\n" + funcs + "\nadd; echo ---; del"],
                             capture_output=True, text=True, check=True).stdout
        add, dele = out.split("---\n")
        self.assertIn("iptables -t nat -C POSTROUTING -s 10.10.0.0/24 -o vmbr0 -j MASQUERADE 2>/dev/null || "
                      "iptables -t nat -I POSTROUTING 1 -s 10.10.0.0/24 -o vmbr0 -j MASQUERADE", add)
        self.assertIn("iptables  -I FORWARD 1 -i vmbr1 ! -s 10.10.0.0/24 -j DROP", add)
        self.assertIn("iptables  -I FORWARD 1 -i vmbr1 -d 192.168.0.0/16 -j DROP", add)
        self.assertIn("ip6tables  -I INPUT 1 -i vmbr1 -j DROP", add)
        self.assertIn("iptables  -I FORWARD 1 -i vmbr1 ! -o vmbr0 -j DROP", add)   # internet only, allow-list
        self.assertEqual(len(add.strip().splitlines()), 12)
        self.assertEqual(len(dele.strip().splitlines()), 12)
        for line in dele.strip().splitlines():
            self.assertRegex(line, r"^ip6?tables +(-t nat )?-D \S+ .* 2>/dev/null \|\| true$")

    def test_job_network_has_no_lan_no_host_no_ipv6_no_spoofing(self):
        text = (KIT / "net.sh").read_text()
        for rng in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "169.254.0.0/16"):
            self.assertIn(rng, text)
        self.assertIn("iptables FORWARD -i $BR -d $d -j DROP", text)
        self.assertIn("iptables INPUT -i $BR -j DROP", text)
        self.assertIn("iptables FORWARD -i $BR ! -s $NET.0/24 -j DROP", text)
        self.assertIn("ip6tables INPUT -i $BR -j DROP", text)
        self.assertIn("iptables FORWARD -i $BR ! -o $UP -j DROP", text)
        self.assertIn("iptables -S FORWARD 1", text)      # --check also wants our rules first, not just present
        cycle = (KIT / "cycle").read_text()
        self.assertIn('net.sh" --check', cycle)          # no clone without the firewall rules in place
        self.assertIn("not isolated: not starting", cycle)
        self.assertIn(".busy", cycle)                    # the job clock starts from GitHub's view, not the guest's
        self.assertIn("ip6tables FORWARD -i $BR -j DROP", text)
        self.assertIn("net.ipv6.conf.$BR.disable_ipv6=1", text)
        self.assertIn(" -C $chain $spec 2>/dev/null || ", text)   # no duplicate rules on ifreload
        self.assertIn("is not ours", text)                         # never takes over someone else's bridge
        self.assertIn("bridge-ports none", text)
        self.assertIn('--net0 "virtio,bridge=$BR"', (KIT / "template.sh").read_text())


if __name__ == "__main__":
    unittest.main()


class InstancesCap(unittest.TestCase):
    def check(self, n, gib=78, threads=32, **env):
        import os
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".meminfo") as f:
            f.write(f"MemTotal: {gib * 1048576} kB\n")
            f.flush()
            e = {**os.environ, "MEMINFO": f.name, "THREADS": str(threads), **env}
            return subprocess.run(["bash", str(KIT / "instances-check"), str(n)], env=e,
                                  capture_output=True, text=True)

    def test_seven_and_sixteen_are_allowed_on_a_big_enough_host(self):
        self.assertEqual(self.check(7).returncode, 0)          # the R530 today: 78 GB, 32 threads
        self.assertEqual(self.check(16, gib=256).returncode, 0)  # after the RAM upgrade

    def test_out_of_range_counts_are_refused(self):
        for n in ("0", "17", "-1", "x", ""):
            self.assertEqual(self.check(n, gib=512, threads=64).returncode, 2, n)

    def test_ram_is_checked_against_host_memory_minus_16_gib(self):
        self.assertEqual(self.check(7, gib=72).returncode, 0)   # 56 + 16 = 72
        r = self.check(7, gib=71)
        self.assertEqual(r.returncode, 2)
        self.assertIn("GiB", r.stderr)
        self.assertEqual(self.check(8, gib=78).returncode, 2)   # 64 + 16 > 78

    def test_cpu_overcommit_is_capped_at_2x(self):
        self.assertEqual(self.check(8, gib=256, threads=16).returncode, 0)
        self.assertEqual(self.check(9, gib=256, threads=16).returncode, 2)

    def test_ids_cannot_collide_with_the_template(self):
        self.assertEqual(self.check(2, BASE="9099").returncode, 2)
        self.assertEqual(self.check(2, BASE="9100").returncode, 0)

    def test_cycle_uses_it_and_the_old_cap_is_gone(self):
        text = (KIT / "cycle").read_text()
        self.assertIn('instances-check" "$n"', text)
        self.assertNotIn("1 to 6", text)
