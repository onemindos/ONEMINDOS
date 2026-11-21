# SPDX-License-Identifier: Apache-2.0
"""CI-15: DigitalOcean droplets as ephemeral runners (label onemind-do) for trusted, secret-free, non-KVM jobs.

A job may pick the `onemind-do` pool only if (1) the choice is behind the DO_RUNNER switch and falls back
to the Mac pool or GitHub-hosted, (2) a pull request from a fork can never select it, and no event that runs
untrusted code with repo context can start its workflow, (3) nothing in the job or its workflow's top level
can read a secret, an environment or write to the repo, and (4) the job needs no KVM and no Docker (droplets
have neither /dev/kvm nor Docker inside the job container). The kit must give every job a fresh container,
keep tokens off the droplets, and guard the cost. Nothing here creates a droplet or spends money: doctl and
gh are stubs.
"""
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"
KIT = ROOT / "scripts" / "ci-runner-do"
SECRET_USE = re.compile(r"secrets\.(?!GITHUB_TOKEN\b)|secrets:\s*inherit|toJSON\(secrets\)", re.I)
LABEL = "onemind-do"
UNTRUSTED_TRIGGERS = {"pull_request_target", "workflow_run", "issue_comment"}
# The first safe set (lint, unit, hygiene, the SQLite core shards): no secrets, no Docker, no KVM.
DO_JOBS = {("ci.yml", "lint"), ("ci.yml", "unit"), ("hygiene.yml", "hygiene"), ("ci-core.yml", "test")}
TRUST = ("(github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository)")
MAC = f"(vars.LOCAL_RUNNER == 'on' && {TRUST}) && fromJSON('[\"self-hosted\",\"onemind-local\"]') || 'ubuntu-24.04'"
WANT = f"${{{{ (vars.DO_RUNNER == 'on' && {TRUST}) && fromJSON('[\"self-hosted\",\"onemind-do\"]') || {MAC} }}}}"
NEEDS_HOSTED = re.compile(
    r"/dev/kvm|\bkvm\b|qemu-system|setup-qemu-action|setup-buildx-action|docker[ /]|docker\b\s+compose|"
    r"ANDROID_HOME|xcodebuild|make image|make battery|battery\.yml|\bk3d\b", re.I)


def workflows():
    for p in sorted(WF.glob("*.yml")):
        yield p.name, yaml.safe_load(p.read_text())


def do_jobs():
    for wf, d in workflows():
        for name, job in d["jobs"].items():
            if LABEL in str(job.get("runs-on", "")):
                yield wf, d, name, job


def triggers(d):
    on = d.get(True, d.get("on"))   # PyYAML reads the bare key `on` as True
    if isinstance(on, str):
        return {on}
    return set(on or ())


class DoRunnerPolicy(unittest.TestCase):
    def test_exactly_the_first_safe_set_uses_it(self):
        self.assertEqual({(wf, name) for wf, _, name, _ in do_jobs()}, DO_JOBS)

    def test_selection_is_exactly_the_reviewed_expression(self):
        # Whole-string match: dropping the fork guard, the switch, or the fallback fails here.
        for wf, _, name, job in do_jobs():
            self.assertEqual(job["runs-on"], WANT, f"{wf}:{name}")

    def test_off_by_default_the_expression_falls_through_to_mac_then_hosted(self):
        # DO_RUNNER unset or off: the first operand is false, so the Mac / hosted tail decides, as before.
        for wf, _, name, job in do_jobs():
            self.assertIn("vars.DO_RUNNER == 'on' &&", job["runs-on"])
            self.assertTrue(job["runs-on"].endswith(MAC + " }}"), f"{wf}:{name}")

    def test_every_self_hosted_job_is_a_reviewed_one(self):
        for wf, d in workflows():
            for name, job in d["jobs"].items():
                ro = str(job.get("runs-on", ""))
                if "self-hosted" in ro:
                    self.assertTrue(any(x in ro for x in (LABEL, "onemind-local", "onemind-gate", "onemind-kvm")),
                                    f"{wf}:{name} asks for an unreviewed self-hosted runner")

    def test_no_untrusted_trigger_reaches_it(self):
        for wf, d, name, _ in do_jobs():
            self.assertFalse(triggers(d) & UNTRUSTED_TRIGGERS, f"{wf}:{name}")

    def test_no_job_that_can_pick_it_can_read_a_secret_or_write(self):
        for wf, d, name, job in do_jobs():
            where = f"{wf}:{name}"
            self.assertNotRegex(json.dumps(job), SECRET_USE, where)
            self.assertNotRegex(json.dumps(d.get("env", {})), SECRET_USE, f"{wf} top-level env")
            self.assertNotIn("environment", job, where)
            self.assertNotIn("uses", job, where)
            self.assertNotIn("docker/login-action", json.dumps(job), where)
            for perms in (job.get("permissions"), d.get("permissions") if "permissions" not in job else None):
                if isinstance(perms, dict):
                    self.assertNotIn("write", perms.values(), where)
                self.assertNotEqual(perms, "write-all", where)

    def test_no_job_that_can_pick_it_needs_kvm_or_docker(self):
        for wf, d, name, job in do_jobs():
            where = f"{wf}:{name}"
            self.assertNotIn("services", job, where)
            self.assertNotIn("container", job, where)
            self.assertNotRegex(json.dumps({k: v for k, v in job.items() if k != "runs-on"}), NEEDS_HOSTED, where)

    def test_signing_release_and_image_workflows_stay_off_it(self):
        for wf, _, name, _ in do_jobs():
            self.assertNotIn(wf, {"release.yml", "security-nightly.yml", "apps-rescan.yml", "changes-collect.yml",
                                  "image.yml", "battery.yml", "dev-build.yml"})

    def test_jobs_with_secrets_stay_off_it(self):
        for wf, d in workflows():
            for name, job in d["jobs"].items():
                if SECRET_USE.search(json.dumps(job)):
                    self.assertNotIn(LABEL, str(job.get("runs-on", "")), f"{wf}:{name}")


class Kit(unittest.TestCase):
    FILES = (("up", "bash"), ("down", "bash"), ("status", "bash"), ("cycle", "bash"), ("lib.sh", "bash"),
             ("provision.sh", "sh"), ("start-job.sh", "sh"), ("run-one.sh", "sh"), ("job-started.sh", "sh"))

    def test_scripts_exist_and_parse(self):
        for f, sh in self.FILES:
            path = KIT / f
            self.assertTrue(path.is_file(), f)
            if f != "lib.sh":
                self.assertTrue(path.stat().st_mode & 0o111, f"{f} is not executable")
            subprocess.run([sh, "-n", str(path)], check=True)

    def test_no_token_and_no_host_path_in_the_kit(self):
        for p in KIT.iterdir():
            text = p.read_text()
            self.assertNotRegex(text, r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_|dop_v1_[0-9a-f]{20,}", p.name)
            self.assertNotRegex(text, r"/Users/|/home/(?!runner)\w", p.name)

    def test_downloads_are_pinned_and_checked(self):
        pin = (KIT / "runner.pin").read_text()
        self.assertRegex(pin, r"(?m)^RUNNER_SHA256=[0-9a-f]{64}$")
        kvm = ROOT / "scripts" / "ci-runner-kvm" / "runner.pin"
        if kvm.exists():   # same runner build as the KVM kit, once that lands
            for key in ("RUNNER_VERSION", "RUNNER_SHA256"):
                self.assertEqual(re.search(rf"(?m)^{key}=(.*)$", pin).group(1), re.search(rf"(?m)^{key}=(.*)$", kvm.read_text()).group(1))
        self.assertIn('echo "${RUNNER_SHA256}  /tmp/runner.tgz" | sha256sum -c -', (KIT / "Dockerfile").read_text())
        self.assertIn("--build-arg \"RUNNER_SHA256=$RUNNER_SHA256\"", (KIT / "provision.sh").read_text())

    def test_runners_are_single_use_jit_with_fixed_labels_and_never_see_a_github_token(self):
        cycle = (KIT / "cycle").read_text()
        self.assertIn("actions/runners/generate-jitconfig", cycle)
        self.assertIn('\\"labels\\":[\\"self-hosted\\",\\"onemind-do\\"]'.replace('\\"', '"'), cycle)
        self.assertNotIn("registration-token", cycle)   # never the org-wide registration token
        self.assertIn('gh api -X DELETE "orgs/$ORG/actions/runners/$rid"', cycle)
        self.assertIn("| sshd \"$IP\"", cycle)            # the config goes to the droplet on stdin
        run = (KIT / "run-one.sh").read_text()
        self.assertIn("IFS= read -r ACTIONS_RUNNER_INPUT_JITCONFIG", run)
        self.assertNotIn("config.sh", run)
        for f in ("up", "start-job.sh", "provision.sh", "Dockerfile"):
            self.assertNotRegex((KIT / f).read_text(), r"GH_TOKEN|GITHUB_TOKEN|gh auth token", f)
        self.assertNotRegex(cycle, r"printf[^\n]*\$cfg[^\n]*\|[^\n]*\bsshd\b[^\n]*\$cfg", "config in argv")

    def test_every_job_gets_a_fresh_container(self):
        text = (KIT / "start-job.sh").read_text()
        self.assertIn("docker run --rm -i", text)
        self.assertIn("--pull never", text)
        self.assertNotIn("docker.sock", text)
        self.assertNotIn(" -v ", text)                 # no host mounts
        self.assertNotIn("--privileged", text)
        self.assertIn("timeout -s KILL", text)         # a job cannot outlive MAX_JOB_MIN
        self.assertIn('docker rm -f "$name"', text)

    def test_containers_cannot_reach_metadata_vpc_or_the_droplet(self):
        prov = (KIT / "provision.sh").read_text()
        for rng in ("169.254.0.0/16", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10"):
            self.assertIn(rng, prov)
        self.assertIn('iptables -I DOCKER-USER 1 -i docker0 -d "$d" -j DROP', prov)
        self.assertIn("iptables -I INPUT 1 -i docker0 -j DROP", prov)
        start = (KIT / "start-job.sh").read_text()
        self.assertIn("container firewall missing", start)   # no job without the rules
        self.assertIn("DOCKER-USER -i docker0 -d 169.254.0.0/16 -j DROP", start)
        self.assertIn("DOCKER-USER -i docker0 -d 172.16.0.0/12 -j DROP", start)
        self.assertIn("DOCKER-USER -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN", start)
        self.assertIn("INPUT -i docker0 -j DROP", start)

    def test_firewall_keeps_replies_flowing(self):
        # Docker's bridge is 172.17.0.0/16, inside the 172.16.0.0/12 drop. Replies reach DOCKER-USER with the
        # container as destination, so the drops must be limited to traffic from the bridge, and the
        # ESTABLISHED,RELATED return must be inserted AFTER the drops (each -I 1 lands first), i.e. end up first.
        prov = (KIT / "provision.sh").read_text()
        for line in prov.splitlines():
            if "-j DROP" in line and "DOCKER-USER" in line:
                self.assertIn("-i docker0", line, line)
        ret = prov.index("iptables -I DOCKER-USER 1 -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN")
        self.assertGreater(ret, prov.index('iptables -I DOCKER-USER 1 -i docker0 -d "$d" -j DROP'))
        self.assertLess(ret, prov.index("docker build"))

    def test_cost_guards_exist(self):
        up = (KIT / "up").read_text()
        for needle in ("MAX_DROPLETS=${MAX_DROPLETS:-4}", "HARD_MAX_DROPLETS", "MAX_USD_HOUR=${MAX_USD_HOUR:-2.00}",
                       "COST: $", "doctl compute size list", "Create them? [y/N]"):
            self.assertIn(needle, up + (KIT / "lib.sh").read_text(), needle)
        cycle = (KIT / "cycle").read_text()
        self.assertIn("IDLE_HOURS=${IDLE_HOURS:-2}", cycle)
        self.assertIn("MAX_HOURS=${MAX_HOURS:-12}", cycle)
        self.assertIn(".busy", cycle)                    # idle time comes from GitHub's busy flag
        self.assertIn("trap cleanup EXIT INT TERM", cycle)
        self.assertIn("DO_RUNNER --body off", cycle)
        self.assertIn("destroy_all", cycle)

    def test_ssh_is_locked_to_the_operator_and_the_whole_internet_is_refused(self):
        up = (KIT / "up").read_text()
        self.assertIn("ports:22,address:$DO_ADMIN_CIDR", up)
        self.assertIn("must not be the whole internet", up)
        self.assertNotIn("address:0.0.0.0/0 --outbound", up)

    def test_it_only_touches_its_own_droplets(self):
        lib = (KIT / "lib.sh").read_text()
        self.assertIn('--tag-name "$TAG"', lib)
        self.assertIn(r"$2 ~ /^onemind-do-[0-9]+$/", lib)
        self.assertNotIn("--tag-name", (KIT / "down").read_text().replace("destroy_all", ""))

    # Stubs: doctl keeps its droplets in <state>/droplets (one "ID NAME IP" per line) and logs every call; gh logs.
    DOCTL = r"""#!/bin/sh
d=%(d)s
echo "$*" >> "$d/doctl.log"
case "$*" in
  "account get") ;;
  "compute size list --format Slug,PriceHourly --no-header") printf 'c-16 0.50000\ns-1vcpu-1gb 0.00900\n' ;;
  "compute size list --format Slug,VCPUs --no-header") printf 'c-16 16\ns-1vcpu-1gb 1\n' ;;
  "compute region list --format Slug --no-header") echo nyc3 ;;
  "compute droplet create "*) shift 3; n=1; for a in "$@"; do case $a in --*) break ;; *) echo "$((900+n)) $a 203.0.113.$n" >> "$d/droplets"; n=$((n+1)) ;; esac; done ;;
  "compute droplet list "*) cat "$d/droplets" 2>/dev/null ;;
  "compute droplet delete --force "*) id=${5}; grep -v "^$id " "$d/droplets" > "$d/droplets.new"; mv "$d/droplets.new" "$d/droplets" ;;
  "compute firewall list "*) echo "fw1 onemind-ci-do" ;;
esac
exit 0
"""
    GH = "#!/bin/sh\necho \"$*\" >> %(d)s/gh.log\nexit 0\n"

    def run_kit(self, script, args, env_extra=None, droplets="", stdin=""):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "doctl").write_text(self.DOCTL % {"d": tmp})
            (d / "gh").write_text(self.GH % {"d": tmp})
            (d / "droplets").write_text(droplets)
            (d / "sleep").write_text("#!/bin/sh\nexit 0\n")      # the ssh retry loop must not really wait
            (d / "sleep").chmod(0o755)
            for tool in ("doctl", "gh", "ssh"):
                if tool == "ssh":
                    (d / tool).write_text("#!/bin/sh\nexit 1\n")
                (d / tool).chmod(0o755)
            env = {"PATH": f"{tmp}:/usr/bin:/bin:/opt/homebrew/bin:/usr/local/bin", "TMPDIR": tmp, **(env_extra or {})}
            r = subprocess.run(["bash", str(KIT / script), *args], env=env, input=stdin, capture_output=True, text=True,
                               timeout=60)
            doctl = (d / "doctl.log").read_text() if (d / "doctl.log").exists() else ""
            gh = (d / "gh.log").read_text() if (d / "gh.log").exists() else ""
            return r, doctl, gh

    OK_ENV = {"DO_SSH_KEY": "key-1", "DO_ADMIN_CIDR": "198.51.100.7/32"}

    def test_up_refuses_bad_input_and_creates_nothing(self):
        for args, env in ((["0", "c-16", "nyc3"], {}), (["5", "c-16", "nyc3"], {}), (["x", "c-16", "nyc3"], {}),
                          (["2", "c-16", "nyc3"], {"DO_SSH_KEY": ""}),
                          (["2", "c-16", "nyc3"], {"DO_ADMIN_CIDR": "0.0.0.0/0"}),
                          (["2", "c-16", "nyc3"], {"DO_ADMIN_CIDR": "not-a-cidr"}),
                          (["2", "c-16;x", "nyc3"], {}), (["2", "c-16", "nyc3"], {"MAX_DROPLETS": "9"}),
                          (["2", "nosuch", "nyc3"], {}), (["2", "c-16", "mars1"], {})):
            r, doctl, _ = self.run_kit("up", args, {**self.OK_ENV, **env}, stdin="y\n")
            self.assertNotEqual(r.returncode, 0, (args, env, r.stdout))
            self.assertNotIn("droplet create", doctl, (args, env))
            self.assertNotIn("firewall create", doctl, (args, env))

    def test_up_refuses_when_the_hourly_cost_is_over_the_cap(self):
        r, doctl, _ = self.run_kit("up", ["4", "c-16", "nyc3"], {**self.OK_ENV, "MAX_USD_HOUR": "1.50"}, stdin="y\n")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("over MAX_USD_HOUR", r.stderr)
        self.assertNotIn("droplet create", doctl)

    def test_up_prints_the_cost_and_a_no_creates_nothing(self):
        r, doctl, _ = self.run_kit("up", ["2", "c-16", "nyc3"], self.OK_ENV, stdin="n\n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("COST: $1.0000 per hour, $24.00 per day", r.stdout)
        self.assertNotIn("droplet create", doctl)
        self.assertNotIn("firewall create", doctl)

    def test_up_refuses_if_droplets_already_exist(self):
        r, doctl, _ = self.run_kit("up", ["1", "c-16", "nyc3"], self.OK_ENV, droplets="1 onemind-do-1 host-a\n", stdin="y\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("droplet create", doctl)

    def test_a_failed_up_destroys_what_it_created(self):
        # ssh always fails (stub): up must clean up, not leave billing droplets behind.
        r, doctl, _ = self.run_kit("up", ["1", "c-16", "nyc3"], {**self.OK_ENV, "ASSUME_YES": "1"})
        self.assertIn("compute droplet create onemind-do-1 ", doctl)
        self.assertIn("--tag-name onemind-ci-do", doctl)
        self.assertIn("ports:22,address:198.51.100.7/32", doctl)
        # ssh never answers: `up` exits 1 (not an ERR), and the droplet it made must still be deleted, then the firewall
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("no ssh on onemind-do-1", r.stderr)
        self.assertIn("compute droplet delete --force 901", doctl)
        self.assertIn("compute firewall delete --force fw1", doctl)

    def test_a_signal_during_up_destroys_what_it_created(self):
        up = (KIT / "up").read_text()
        self.assertIn("trap cleanup_failed_up EXIT", up)
        self.assertIn("trap 'exit 130' INT", up)
        self.assertIn("trap 'exit 143' TERM", up)
        self.assertNotRegex(up, r"(?m)^trap .* ERR$")      # an ERR-only trap misses `exit 1` and signals

    def test_down_destroys_only_our_droplets_and_switches_off(self):
        r, doctl, gh = self.run_kit("down", [], droplets="1 onemind-do-1 host-a\n2 other-box host-b\n3 onemind-do-x host-c\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("compute droplet delete --force 1", doctl)
        self.assertNotIn("delete --force 2", doctl)
        self.assertNotIn("delete --force 3", doctl)
        self.assertIn("variable set DO_RUNNER --body off", gh)
        self.assertIn("compute firewall delete --force fw1", doctl)

    def test_cycle_validates_slots_and_needs_droplets(self):
        r, *_ = self.run_kit("cycle", [], {"SLOTS": "9"})
        self.assertEqual(r.returncode, 2)
        r, *_ = self.run_kit("cycle", [], {"SLOTS": "x"})
        self.assertEqual(r.returncode, 2)
        r, _, gh = self.run_kit("cycle", [], {"SLOTS": "2"})
        self.assertEqual(r.returncode, 2, r.stderr)           # no droplets of ours: it must not switch DO_RUNNER on
        self.assertNotIn("DO_RUNNER --body on", gh)

    def test_status_is_read_only(self):
        r, doctl, gh = self.run_kit("status", [], droplets="1 onemind-do-1 host-a\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("delete", doctl)
        self.assertNotIn("create", doctl)
        self.assertNotIn("variable set", gh)


class JobStartedHook(unittest.TestCase):
    """The on-machine guard: a fork PR that hard-codes the onemind-do label is refused here."""

    def run_hook(self, event, repo, name):
        env = {"PATH": os.environ["PATH"], "GITHUB_REPOSITORY": repo, "GITHUB_EVENT_NAME": name}
        path = None
        if event is not None:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
                json.dump(event, f)
            path = env["GITHUB_EVENT_PATH"] = f.name
        try:
            return subprocess.run(["sh", str(KIT / "job-started.sh")], env=env, capture_output=True, text=True)
        finally:
            if path:
                os.unlink(path)

    def test_fork_pull_requests_and_odd_events_are_refused_on_the_machine(self):
        fork = {"head": {"repo": {"full_name": "someone/ONEMINDOS"}}}
        same = {"head": {"repo": {"full_name": "onemindos/ONEMINDOS"}}}
        repo = "onemindos/ONEMINDOS"
        cases = [
            ({"pull_request": fork}, repo, "pull_request", 1),
            ({"pull_request": fork, "action": "submitted", "review": {}}, repo, "pull_request", 1),
            ({"pull_request": {"head": {"repo": None}}}, repo, "pull_request", 1),     # deleted fork
            ({"pull_request": same}, repo, "pull_request", 0),
            ({"pull_request": same}, repo, "pull_request_target", 1),
            ({"ref": "refs/heads/main"}, repo, "push", 0),
            ({"ref": "refs/heads/main"}, repo, "schedule", 0),
            ({"merge_group": {}}, repo, "merge_group", 0),
            ({"ref": "refs/heads/main"}, repo, "workflow_dispatch", 0),
            ({"ref": "refs/heads/main"}, repo, "issue_comment", 1),
            ({"workflow_run": {}}, repo, "workflow_run", 1),
            ({}, repo, "pull_request", 1),                                              # PR event, no payload
            ({"ref": "refs/heads/main"}, repo, "", 1),                                  # no event name: fail closed
            ({"ref": "refs/heads/main"}, "", "push", 1),                                # no repository: fail closed
            (None, repo, "push", 1),                                                    # no event file: fail closed
        ]
        for event, r, name, rc in cases:
            res = self.run_hook(event, r, name)
            self.assertEqual(res.returncode, rc, (event, r, name, res.stderr))
            self.assertIn("onemind-do guard:", res.stdout + res.stderr)   # every job log shows the guard ran

    def test_the_hook_is_wired_into_the_image(self):
        df = (KIT / "Dockerfile").read_text()
        self.assertIn("ENV ACTIONS_RUNNER_HOOK_JOB_STARTED=/usr/local/bin/onemind-ci-job-started.sh", df)
        self.assertIn("COPY job-started.sh /usr/local/bin/onemind-ci-job-started.sh", df)   # the runner wants a .sh path
        kvm = ROOT / "scripts" / "ci-runner-kvm" / "job-started.sh"
        if kvm.exists():   # one policy for both kits
            norm = lambda p: p.read_text().replace("onemind-kvm", "onemind-do")
            self.assertEqual(norm(kvm).split("set -eu", 1)[1], (KIT / "job-started.sh").read_text().split("set -eu", 1)[1])


if __name__ == "__main__":
    unittest.main()
