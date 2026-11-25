# SPDX-License-Identifier: Apache-2.0
"""Build cache for the image builds (#234, faster OS iteration): os/rootfs/buildx-cache.sh, its wiring in the image,
battery and reproducible-build workflows and in the Makefile.

The cache may only make builds faster. These tests fail if (1) an image-workflow build bypasses the cache script or
goes back to inline type=gha flags (inert in a `run:` step: buildx drops them without the runtime token), (2) a job
that builds loses the step that exposes that token, (3) pull requests start writing the shared cache, (4) a test step
disappears from a job while the cache wiring is edited, (5) the reproducible-build check starts using a cache, or
(6) the script changes the build command or loses a cache it was given. The script tests use a stub instead of
Docker, so they run anywhere.
"""
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"
SCRIPT = ROOT / "os" / "rootfs" / "buildx-cache.sh"
RUNTIME = "crazy-max/ghaction-github-runtime@04d248b84655b509d8c44dc1d6f990c879747487"
BUILDX = "docker/setup-buildx-action@"
WRITE_EXPR = "${{ contains(fromJSON('[\"push\",\"schedule\",\"workflow_dispatch\"]'), github.event_name) }}"
CACHED_WORKFLOWS = ("image.yml", "battery.yml", "reproducible.yml")
# Every test target each job ran when the cache went in. Removing one is a test-coverage change: it needs its own PR.
TEST_STEPS = {
    ("image.yml", "image"): ["image", "convert", "rpi5-check", "imager-json"],
    ("image.yml", "smoke"): ["fixtures", "firstboot", "bootlock", "rollback"],
    ("image.yml", "dataenc"): ["fixtures", "dataenc"],
    ("image.yml", "cloud"): ["cloud-image", "cloud-test"],
    ("image.yml", "installer"): ["image", "installer", "installer-test"],
    ("battery.yml", "battery"): ["fixtures", "firstboot", "secureboot-test", "firewall", "battery"],
    ("reproducible.yml", "repro"): ["repro-check"],
}
# Read-only jobs: they share a scope with a job that already writes it in the same run.
READ_ONLY = {("image.yml", "dataenc"), ("image.yml", "installer")}


def text(path):
    return pathlib.Path(path).read_text()


def load(name):
    return yaml.safe_load((WF / name).read_text())


def builds(job):
    """(step index, command) for every `docker buildx build` of the OS Containerfile in a job."""
    out = []
    for i, st in enumerate(job.get("steps") or []):
        run = st.get("run") or ""
        joined = re.sub(r"\\\n\s*", " ", run)
        for line in joined.splitlines():
            if "docker buildx build" in line and "os/rootfs/Containerfile" in line:
                out.append((i, line.strip()))
    return out


class WorkflowWiring(unittest.TestCase):
    def test_every_os_build_goes_through_the_cache_script(self):
        seen = 0
        for wf in CACHED_WORKFLOWS:
            for name, job in load(wf)["jobs"].items():
                for _, cmd in builds(job):
                    seen += 1
                    self.assertRegex(cmd, r"^sh os/rootfs/buildx-cache\.sh [A-Za-z0-9._${}\- ]+?( --read-only)? -- docker buildx build ",
                                     f"{wf}:{name}: {cmd[:120]}")
                    self.assertNotIn("type=gha", cmd, f"{wf}:{name}: inline gha flags are inert in a run step")
                    ro = "--read-only" in cmd.split(" -- ")[0]
                    self.assertEqual(ro, (wf, name) in READ_ONLY, f"{wf}:{name}: read-only mode changed")
        self.assertGreaterEqual(seen, 12)

    def test_the_scopes_stay_per_board_and_runner(self):
        img = (WF / "image.yml").read_text()
        for scope in ("rootfs-debian-${{ matrix.board }}", "tools-${{ matrix.runner }}", "rootfs-debian-x86_64-efi",
                      "tools-ubuntu-24.04", "rootfs-debian-cloud"):
            self.assertIn(f"buildx-cache.sh {scope} ", img)
        bat = (WF / "battery.yml").read_text()
        self.assertIn("buildx-cache.sh rootfs-${{ inputs.leg }}-${{ inputs.board }} --", bat)
        self.assertIn("buildx-cache.sh tools-${{ inputs.runner }} --", bat)

    def test_each_building_job_exposes_the_cache_token_first(self):
        for wf in CACHED_WORKFLOWS:
            for name, job in load(wf)["jobs"].items():
                b = builds(job)
                if not b:
                    continue
                uses = [st.get("uses", "") for st in job["steps"]]
                rt = [i for i, u in enumerate(uses) if u.startswith(RUNTIME)]
                bx = [i for i, u in enumerate(uses) if u.startswith(BUILDX)]
                self.assertEqual(len(rt), 1, f"{wf}:{name}: one runtime-token step")
                self.assertTrue(bx and bx[0] < rt[0] < b[0][0], f"{wf}:{name}: setup-buildx, then the token, then builds")

    def test_pull_requests_read_but_never_write_the_shared_cache(self):
        for wf in CACHED_WORKFLOWS:
            self.assertEqual(load(wf).get("env", {}).get("BUILDX_CACHE_WRITE"), WRITE_EXPR, wf)

    def test_no_test_step_was_dropped(self):
        for (wf, name), want in TEST_STEPS.items():
            job = load(wf)["jobs"][name]
            got = []
            for st in job["steps"]:
                got += re.findall(r"\bmake ([a-z0-9-]+)", st.get("run") or "")
            for target in want:
                self.assertIn(target, got, f"{wf}:{name} lost `make {target}`")

    def test_the_image_workflow_still_calls_the_battery(self):
        uses = [j.get("uses", "") for j in load("image.yml")["jobs"].values()]
        self.assertIn("./.github/workflows/battery.yml", uses)

    def test_the_runtime_action_is_pinned_in_the_lock(self):
        lock = yaml.safe_load((ROOT / "os" / "versions.lock.yaml").read_text())
        self.assertEqual(lock["tools"]["github_actions"]["crazy-max/ghaction-github-runtime"], RUNTIME.split("@")[1])


class MakefileWiring(unittest.TestCase):
    def make_n(self, *args):
        r = subprocess.run(["make", "-n", *args], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_tools_rootfs_and_installer_builds_use_the_cache_script(self):
        mk = (ROOT / "Makefile").read_text()
        self.assertRegex(mk, r"(?m)^BUILDX_CACHE \?=\s*$", "the cache is off unless asked for")
        for scope in ("tools-$(ARCH_OF)", "rootfs-$(LEG)-$(BOARD)", "installer-$(LEG)-$(BOARD)"):
            self.assertIn(f"$(CACHED) {scope} -- docker buildx build", mk)
        raw = [l for l in mk.splitlines() if re.match(r"\s+docker buildx build -f os/(rootfs|boards/\$\(BOARD\))/Containerfile", l)]
        self.assertEqual(raw, [], "a tools, rootfs or installer build bypasses $(CACHED)")

    def test_make_passes_the_cache_dir_through(self):
        out = self.make_n("rootfs", "BOARD=x86_64-efi", "BUILDX_CACHE=/var/cache/omtest")
        self.assertIn('BUILDX_CACHE="/var/cache/omtest" sh os/rootfs/buildx-cache.sh rootfs-debian-x86_64-efi -- docker buildx build', out)
        self.assertIn("--build-arg SOURCE_DATE_EPOCH=", out, "the build itself is unchanged")
        off = self.make_n("rootfs", "BOARD=x86_64-efi", "BUILDX_CACHE=")
        self.assertIn('BUILDX_CACHE="" sh os/rootfs/buildx-cache.sh rootfs-debian-x86_64-efi --', off)

    def test_the_reproducible_check_never_uses_a_cache(self):
        s = (ROOT / "os" / "rootfs" / "repro-check.sh").read_text()
        self.assertIn("docker buildx build --no-cache", s)
        self.assertNotIn("cache-from", s)
        self.assertNotIn("buildx-cache.sh", s)


STUB = """#!/bin/sh
# Stands in for `docker`: records its arguments, writes a local cache where --cache-to asks, exits $STUB_RC.
printf '%s\\n' "$@" > "$STUB_LOG"
for a in "$@"; do
  case "$a" in type=local,dest=*) d=${a#type=local,dest=}; d=${d%%,*}; mkdir -p "$d"; echo "{\\"run\\": \\"$STUB_TAG\\"}" > "$d/index.json" ;; esac
done
exit "${STUB_RC:-0}"
"""


class Script(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.stub = os.path.join(self.tmp, "docker")
        with open(self.stub, "w") as f:
            f.write(STUB)
        os.chmod(self.stub, 0o755)
        self.log = os.path.join(self.tmp, "args")
        self.cache = os.path.join(self.tmp, "cache")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_it(self, scope="rootfs-debian-x86_64-efi", ro=False, rc=0, tag="1", **env):
        e = {"PATH": os.environ["PATH"], "STUB_LOG": self.log, "STUB_RC": str(rc), "STUB_TAG": tag, **env}
        cmd = ["sh", str(SCRIPT), scope] + (["--read-only"] if ro else []) + \
              ["--", self.stub, "buildx", "build", "-f", "os/rootfs/Containerfile", "--target", "rootfs", "."]
        r = subprocess.run(cmd, capture_output=True, text=True, env=e)
        args = text(self.log).splitlines() if os.path.exists(self.log) else []
        return r, args

    BASE = ["buildx", "build", "-f", "os/rootfs/Containerfile", "--target", "rootfs", "."]
    GHA = {"ACTIONS_RUNTIME_TOKEN": "t", "ACTIONS_RESULTS_URL": "https://results.example/"}

    def test_no_cache_set_up_runs_the_command_unchanged(self):
        r, args = self.run_it()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(args, self.BASE)

    def test_gha_without_the_token_adds_nothing(self):
        # What every old inline-flag step really did: no token, no cache. The script says so by adding nothing.
        r, args = self.run_it(BUILDX_CACHE_WRITE="true", ACTIONS_RESULTS_URL="https://results.example/")
        self.assertEqual(args, self.BASE)

    def test_gha_reads_on_pull_requests_and_writes_on_pushes(self):
        _, args = self.run_it(**self.GHA, BUILDX_CACHE_WRITE="false")
        self.assertEqual(args, self.BASE + ["--cache-from", "type=gha,scope=rootfs-debian-x86_64-efi"])
        _, args = self.run_it(**self.GHA, BUILDX_CACHE_WRITE="true")
        self.assertEqual(args, self.BASE + ["--cache-from", "type=gha,scope=rootfs-debian-x86_64-efi",
                                            "--cache-to", "type=gha,mode=max,scope=rootfs-debian-x86_64-efi"])
        _, args = self.run_it(ro=True, **self.GHA, BUILDX_CACHE_WRITE="true")
        self.assertEqual(args, self.BASE + ["--cache-from", "type=gha,scope=rootfs-debian-x86_64-efi"])

    def test_local_cache_cold_then_warm_then_swapped(self):
        r, args = self.run_it(BUILDX_CACHE=self.cache, tag="first")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(args[:len(self.BASE)], self.BASE)
        self.assertNotIn("--cache-from", args, "a cold cache is not read")
        self.assertTrue(args[-1].startswith("type=local,dest=") and args[-1].endswith(",mode=max"))
        cur = os.path.join(self.cache, "rootfs-debian-x86_64-efi", "index.json")
        self.assertIn("first", text(cur))
        r, args = self.run_it(BUILDX_CACHE=self.cache, tag="second")
        self.assertIn("type=local,src=" + os.path.join(self.cache, "rootfs-debian-x86_64-efi"), args)
        self.assertIn("second", text(cur), "the fresh copy replaced the old one")
        left = [n for n in os.listdir(self.cache) if ".new." in n]
        self.assertEqual(left, [], "no half-written copy is left")

    def test_a_failed_build_keeps_the_old_cache_and_its_exit_code(self):
        self.run_it(BUILDX_CACHE=self.cache, tag="good")
        r, _ = self.run_it(BUILDX_CACHE=self.cache, tag="broken", rc=7)
        self.assertEqual(r.returncode, 7)
        cur = os.path.join(self.cache, "rootfs-debian-x86_64-efi", "index.json")
        self.assertIn("good", text(cur))
        self.assertEqual([n for n in os.listdir(self.cache) if ".new." in n], [])

    def test_read_only_local_cache_writes_nothing(self):
        self.run_it(BUILDX_CACHE=self.cache, tag="good")
        r, args = self.run_it(ro=True, BUILDX_CACHE=self.cache, tag="other")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(any(a.startswith("type=local,dest=") for a in args))
        self.assertIn("good", text(os.path.join(self.cache, "rootfs-debian-x86_64-efi", "index.json")))

    def test_bad_usage_is_refused(self):
        for scope in ("", "../etc", "a b", "x;rm"):
            r, _ = self.run_it(scope=scope)
            self.assertEqual(r.returncode, 2, scope)
        r = subprocess.run(["sh", str(SCRIPT), "tools", "docker", "buildx", "build"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, "the -- separator is required")


if __name__ == "__main__":
    unittest.main()
