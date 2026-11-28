# SPDX-License-Identifier: Apache-2.0
"""CI-14: image.yml runs the full matrix only for PRs that touch the OS (scripts/ci-image-scope.py)."""
import importlib.util
import pathlib
import re
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci-image-scope.py"
spec = importlib.util.spec_from_file_location("ci_image_scope", SCRIPT)
scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope)


class ImageScope(unittest.TestCase):
    def test_payload_only_prs_get_the_smoke_only(self):
        for files in (["core/onemind_core/routers/agents.py"],
                      ["dashboard/src/App.tsx", "core/tests/sec_policy.py", "docs/x.md", "sdk/ts/src/gen/schema.ts"],
                      ["apps/ntfy/scan.json"], ["ui/src/button.tsx"], ["changes/x.md"],
                      ["sdk/go/internal/gen/types.gen.go", "sdk/schema/app.json"]):
            self.assertFalse(scope.needs_full_image(files), files)

    def test_printing_fixture_changes_trigger_smoke_only(self):
        text = (ROOT / ".github/workflows/image.yml").read_text()
        for event in ("pull_request", "push"):
            paths = re.search(rf"\n  {event}:\n(?:    .*\n)*?    paths: \[(.*)\]", text).group(1)
            self.assertIn("'test/printing/**'", paths)
        self.assertFalse(scope.needs_full_image(["test/printing/check.py"]))

    def test_os_prs_get_the_full_matrix(self):
        for files in (["os/rootfs/Containerfile"], ["test/qemu/run.sh"], ["internal/rescue/unit.go"],
                      ["cmd/onemindd/main.go"], ["go.sum"], ["Makefile"], [".dockerignore"],
                      [".github/workflows/image.yml"], [".github/workflows/battery.yml"],
                      ["scripts/ci-image-scope.py"], ["core/x.py", "os/gate/onemind-health-gate"],
                      ["core/uv.lock"], ["core/pyproject.toml"], ["core/onemind_core/serve.py"],
                      ["core/onemind_core/netconf.py"], ["core/onemind_core/routers/onboarding.py"],
                      ["brand/generated/os/plymouth/onemind/x.png"], ["brand/logo/png/white/a.png"]):
            self.assertTrue(scope.needs_full_image(files), files)

    def test_any_doubt_runs_everything(self):
        self.assertTrue(scope.needs_full_image([]))
        self.assertTrue(scope.needs_full_image(["", "  "]))
        self.assertTrue(scope.needs_full_image(["core/a.py"] * scope.API_CAP))

    def test_cli_prints_a_github_output_line(self):
        run = lambda text: subprocess.run([sys.executable, "-I", str(SCRIPT)], input=text, text=True,
                                          capture_output=True, check=True).stdout.strip()
        self.assertEqual(run("core/a.py\ndashboard/b.tsx\n"), "os=false")
        self.assertEqual(run("os/x\n"), "os=true")
        self.assertEqual(run(""), "os=true")

    def test_every_trigger_path_is_classified(self):
        # A new path in image.yml's `paths:` must be either payload or OS in the script, never silently neither.
        text = (ROOT / ".github/workflows/image.yml").read_text()
        paths = re.search(r"pull_request:\n(?:.*\n)*?\s+paths: \[(.*)\]", text).group(1)
        for p in re.findall(r"'([^']+)'", paths):
            sample = p.replace("/**", "/x")
            self.assertTrue(sample.startswith(scope.PAYLOAD) or scope.is_os(sample), p)

    def test_every_build_context_path_is_classified(self):
        # Everything .dockerignore lets into the image build is payload or OS, never unclassified.
        for line in (ROOT / ".dockerignore").read_text().splitlines():
            if line.startswith("!"):
                sample = line[1:].rstrip("/") + ("/x" if line.endswith("/") else "")
                self.assertTrue(sample.startswith(scope.PAYLOAD) or scope.is_os(sample), line)

    def test_workflow_fails_closed_and_sees_renames(self):
        text = (ROOT / ".github/workflows/image.yml").read_text()
        self.assertIn("previous_filename", text)
        self.assertNotIn("|| true; } > files.txt", text)
        self.assertRegex(text, r"if ! gh api [^\n]*files")

    def test_heavy_jobs_wait_for_the_scope(self):
        text = (ROOT / ".github/workflows/image.yml").read_text()
        for job in ("image", "battery", "cloud", "installer"):
            block = re.search(rf"\n  {job}:\n((?:    .*\n|\n)*)", text).group(1)
            self.assertIn("needs.scope.outputs.os == 'true'", block, job)
        smoke = re.search(r"\n  smoke:\n((?:    .*\n|\n)*)", text).group(1)
        self.assertNotIn("needs.scope.outputs.os", smoke)

    def test_the_smoke_has_room_to_pass_on_a_busy_runner(self):
        # A passing smoke took about 44 minutes on a loaded KVM host (2026-11-21); at 45 half of them were
        # cancelled. Keep at least double the usual time so load never turns a pass into a red check.
        text = (ROOT / ".github/workflows/image.yml").read_text()
        smoke = re.search(r"\n  smoke:\n((?:    .*\n|\n)*)", text).group(1)
        limit = int(re.search(r"^    timeout-minutes: (\d+)$", smoke, re.M).group(1))
        self.assertGreaterEqual(limit, 90)


if __name__ == "__main__":
    unittest.main()
