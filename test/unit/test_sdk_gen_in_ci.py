# SPDX-License-Identifier: Apache-2.0
"""CI-16: the SDK code generated from sdk/openapi/onemind-v1.json is not committed, and everything
that builds or tests code importing it generates it first (sdk/scripts/gen-code.sh)."""
import re
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
GENERATED = (
    "sdk/go/internal/gen/types.gen.go",
    "sdk/python/src/onemind_sdk/_gen/models.py",
    "sdk/python/src/onemind_sdk/aio.py",
    "sdk/ts/src/gen/schema.ts",
)
ACTION = "./.github/actions/sdk-gen"


def rd(*parts):
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def needs(step, job_wd):
    """The languages a workflow step needs generated, from what it runs."""
    run = step.get("run") or ""
    wd = step.get("working-directory") or job_wd or ""
    langs = set()
    if re.search(r"go (vet|test -race -count=1) \./(\.\.\.|cmd/onemind)", run) or "make -C sdk test" in run:
        langs.add("go")
    if "make -C core test" in run:   # test_sdk_conformance / test_mcp: the Python SDK and the onemind CLI
        langs |= {"go", "py"}
    if (wd in ("dashboard", "mobile") and "npm run" in run) or "docker compose up" in run:
        langs.add("ts")
    if "make -C sdk test" in run:
        langs |= {"ts", "py"}
    return langs


def generated(step):
    """The languages a step generates."""
    if step.get("uses") == ACTION:
        return set(str((step.get("with") or {}).get("langs", "go ts py")).split())
    run = step.get("run") or ""
    if "make -C sdk gen" in run or "make -C sdk check-stale" in run:
        return {"go", "ts", "py"}
    m = re.search(r"gen-code\.sh((?: (?:go|ts|py))*)", run)
    return set(m.group(1).split()) if m else set()


class GeneratedCodeIsNotCommitted(unittest.TestCase):
    def test_generated_paths_are_ignored(self):
        ignore = rd(".gitignore").splitlines()
        for path in GENERATED:
            self.assertIn("/" + path, ignore, path + " must be in .gitignore")

    def test_generated_paths_are_untracked_but_the_spec_is_tracked(self):
        try:
            tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--", *GENERATED, "sdk/openapi/onemind-v1.json"],
                                     capture_output=True, text=True, check=True).stdout.split()
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("not a git checkout")
        self.assertEqual(tracked, ["sdk/openapi/onemind-v1.json"])

    def test_check_stale_checks_the_spec_and_generation_not_a_git_diff(self):
        mk = rd("sdk", "Makefile")
        recipe = mk[mk.index("check-stale:"):mk.index("test: test-go")]
        self.assertIn("onemind_core.openapi --check", recipe)
        self.assertIn("gen-code", recipe)
        self.assertNotIn("git diff", recipe)
        for t in ("go", "py", "ts"):   # the SDK tests always run on freshly generated code
            self.assertIn(f"test-{t}: gen-{t}", mk)

    def test_generator_pins_match_the_stamped_versions(self):
        sh = rd("sdk", "scripts", "gen-code.sh")
        go = re.search(r"oapi-codegen@(v[\d.]+)", sh).group(1)
        py = re.search(r"datamodel-code-generator==([\d.]+)", sh).group(1)
        self.assertIn(f'"oapi-codegen {go}"', sh)
        self.assertIn(f'"datamodel-code-generator {py}"', sh)


class EveryConsumerGeneratesFirst(unittest.TestCase):
    def test_every_workflow_job_generates_before_it_uses_the_sdk(self):
        checked = 0
        for wf in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
            data = yaml.safe_load(wf.read_text(encoding="utf-8")) or {}
            for name, job in (data.get("jobs") or {}).items():
                job_wd = ((job.get("defaults") or {}).get("run") or {}).get("working-directory")
                have = set()
                for step in job.get("steps") or []:
                    missing = needs(step, job_wd) - have
                    if needs(step, job_wd):
                        checked += 1
                    self.assertFalse(missing, f"{wf.name} job {name}: step {step.get('name') or step.get('run')!r} "
                                              f"needs the SDK code for {sorted(missing)}; add {ACTION} before it")
                    have |= generated(step)
        self.assertGreaterEqual(checked, 8, "the consumer detection found too few steps to be meaningful")

    def test_mobile_typecheck_generates_the_ts_sdk(self):
        wf = yaml.safe_load(rd(".github", "workflows", "ci-mobile.yml"))
        steps = wf["jobs"]["test"]["steps"]
        gen = next(i for i, s in enumerate(steps) if s.get("uses") == ACTION and "ts" in s["with"]["langs"])
        check = next(i for i, s in enumerate(steps) if "npm run typecheck" in (s.get("run") or ""))
        self.assertLess(gen, check)
        paths = wf[True]["pull_request"]["paths"]
        for p in ("sdk/ts/src/**", ".github/actions/sdk-gen/**"):
            self.assertIn(p, paths)

    def test_the_action_runs_the_shared_script(self):
        action = yaml.safe_load(rd(".github", "actions", "sdk-gen", "action.yml"))
        runs = " ".join(s.get("run", "") for s in action["runs"]["steps"])
        self.assertIn("sdk/scripts/gen-code.sh", runs)

    def test_installer_bundle_and_dev_scripts_generate_before_go_build(self):
        install = rd("deploy", "install.sh")
        fn = install[install.index("onemindd_install() {"):install.index("\n}\n", install.index("onemindd_install() {"))]
        self.assertLess(fn.index("gen-code.sh go"), fn.index('"$GO_DIR/bin/go" build'))
        # never root, never into the checkout, never an "only if missing" (a stale ignored copy)
        self.assertIn("runuser -u nobody", fn)
        self.assertIn('-overlay "$gen/overlay.json"', fn)
        self.assertNotIn('[ ! -f "$gen" ]', fn)
        bundle = rd("deploy", "bundle.sh")
        self.assertLess(bundle.index("gen-code.sh go"), bundle.index("go build"))
        self.assertNotIn('[ -f "$REPO/sdk/go/internal/gen', bundle)
        self.assertIn('"$BUNDLE_GO_IMAGE" sh /sdk/scripts/gen-code.sh go', bundle)   # a Docker-only host
        for script in (("test", "net", "two_vm.py"), ("test", "migrate", "lima-e2e.sh")):
            text = rd(*script)
            self.assertLess(text.index("gen-code.sh"), text.index("./cmd/onemind"), "/".join(script))
        mk = rd("cmd", "onemindd", "Makefile")
        for target in ("build:", "test:"):
            body = mk[mk.index("\n" + target):]
            self.assertIn("gen-code.sh go", body.split("\n\n")[0], "cmd/onemindd make " + target)


if __name__ == "__main__":
    unittest.main()
