# SPDX-License-Identifier: Apache-2.0
"""Unit tests for sdk/tools/ci: gate_summary.py (apps-gate-all issue body) and the pins in
install-tools.sh, which must equal os/versions.lock.yaml tools.app_gate for amd64 and arm64.

Run: python3 -I -m unittest discover -s sdk/tools/tests -v
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

import yaml

CI = Path(__file__).resolve().parents[1] / "ci"
ROOT = Path(__file__).resolve().parents[3]

_spec = importlib.util.spec_from_file_location("gate_summary", CI / "gate_summary.py")
gs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gs)


def report(app: str, result: str, tier: str, failing: dict[str, list[str]] | None = None) -> list[dict]:
    checks = {"licence": {"ok": True, "notes": ["MIT"]}}
    for name, notes in (failing or {}).items():
        checks[name] = {"ok": False, "notes": notes}
    return [{"app": app, "checks": checks, "result": result, "computed_tier": tier}]


def write_cell(root: Path, app: str, arch: str, rc: int | None, rep: list[dict] | None, log: str = "") -> None:
    d = root / f"apps-gate-{app}-{arch}"
    d.mkdir(parents=True)
    (d / "status.json").write_text(json.dumps({"app": app, "arch": arch, "runner": "x", "rc": rc}))
    if rep is not None:
        (d / "report.json").write_text(json.dumps(rep))
    (d / "gate.log").write_text(log)


class GateSummaryTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def run_main(self, apps):
        out = self.dir / "body.md"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = gs.main([str(self.dir), "--apps", *apps, "--archs", "amd64", "arm64",
                          "--run-url", "https://example.invalid/run/1", "--sha", "0123456789abcdef", "--out", str(out)])
        return rc, out.read_text(), buf.getvalue()

    def test_every_kind_of_cell(self):
        write_cell(self.dir, "ntfy", "amd64", 0, report("ntfy", "pass", "verified"))
        write_cell(self.dir, "ntfy", "arm64", 1, report("ntfy", "fail", "community", {
            "smoke": ["FAIL: deployment/ntfy not ready: timed out", "pod ntfy-1 on 192.0.2.7 CrashLoopBackOff",
                      "FAIL: second ```fence``` attempt"]}))
        write_cell(self.dir, "mosquitto", "amd64", 2, None,
                   log="\n".join(f"line {i}" for i in range(30)) + "\nerror: crane: 198.51.100.20 unreachable\x1b[31m!\x1b[0m")
        # mosquitto arm64: no artifact at all
        (self.dir / "unrelated").mkdir()  # a folder without status.json is ignored
        rc, body, stdout = self.run_main(["mosquitto", "ntfy"])
        self.assertEqual(rc, 0)
        self.assertIn("problems=3", stdout)
        self.assertTrue(body.startswith(gs.MARKER))
        self.assertIn("3 of 4 runs not passing", body)
        self.assertIn("| `ntfy` | pass (verified) | **FAIL**: smoke (tier community) |", body)
        self.assertIn("| `mosquitto` | **ERROR** (exit 2) | **NO RESULT** |", body)
        self.assertIn("No artifact: the job was cancelled", body)
        self.assertIn("deployment/ntfy not ready", body)
        self.assertNotIn("CrashLoopBackOff", body)   # only FAIL notes are listed for a failing check
        self.assertIn("'''fence'''", body)            # fences in notes cannot break the Markdown
        self.assertIn("line 29", body)
        self.assertNotIn("line 14", body)             # only the log tail
        self.assertIn("crane: <ip> unreachable!", body)
        self.assertNotRegex(body, r"\d+\.\d+\.\d+\.\d+")
        self.assertNotIn("\x1b", body)
        self.assertIn("commit `0123456789ab`", body)

    def test_all_pass(self):
        for arch in ("amd64", "arm64"):
            write_cell(self.dir, "ntfy", arch, 0, report("ntfy", "pass", "verified"))
        rc, body, stdout = self.run_main(["ntfy"])
        self.assertEqual((rc, stdout.strip()), (0, "problems=0"))
        self.assertIn("0 of 2 runs not passing", body)
        self.assertNotIn("## Details", body)

    def test_setup_failure(self):
        write_cell(self.dir, "ntfy", "amd64", None, None)  # status.json written before setup, never updated
        write_cell(self.dir, "ntfy", "arm64", 0, report("ntfy", "pass", "verified"))
        _, body, stdout = self.run_main(["ntfy"])
        self.assertIn("problems=1", stdout)
        self.assertIn("| `ntfy` | **ERROR** (setup) | pass (verified) |", body)
        self.assertIn("stopped before app-gate finished", body)

    def test_tier_overclaim_is_listed(self):
        rep = report("ntfy", "fail", "community", {"tier": ["metadata.tier is 'verified' but the gate computes 'community'"]})
        write_cell(self.dir, "ntfy", "amd64", 1, rep)
        write_cell(self.dir, "ntfy", "arm64", 0, report("ntfy", "pass", "verified"))
        _, body, _ = self.run_main(["ntfy"])
        self.assertIn("**FAIL**: tier (tier community)", body)
        self.assertIn("metadata.tier is 'verified'", body)

    def test_body_is_capped(self):
        notes = [f"FAIL: {'x' * 1000} {i}" for i in range(50)]
        apps = [f"app{i:02d}" for i in range(80)]
        for app in apps:
            write_cell(self.dir, app, "amd64", 1, report(app, "fail", "blocked", {f"c{j}": notes for j in range(5)}))
        _, body, _ = self.run_main(apps)
        self.assertLessEqual(len(body), gs.MAX_BODY)
        self.assertIn("Truncated", body)

    def test_bad_input(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(gs.main([str(self.dir / "missing"), "--apps", "a"]), 2)


class InstallToolsPins(unittest.TestCase):
    """Every sha256 in install-tools.sh is the os/versions.lock.yaml value for that tool and arch."""

    def test_pins_match_lock(self):
        lock = yaml.safe_load((ROOT / "os" / "versions.lock.yaml").read_text())["tools"]
        script = (CI / "install-tools.sh").read_text()
        expected = {}
        for tool, pin in lock["app_gate"].items():
            if tool == "k3s_image":
                continue
            expected[tool] = {pin["sha256"], pin["arm64_sha256"]}
            self.assertIn(pin["version"].lstrip("v"), script, tool)
        expected["gitleaks"] = {lock["gitleaks"]["sha256"], lock["gitleaks"]["linux_arm64_sha256"]}
        blocks = re.split(r"\n    (?=[a-z0-9]+\)\s)", script)
        found = {}
        for b in blocks:
            m = re.match(r"([a-z0-9]+)\)", b)
            if m and m.group(1) in expected:
                found[m.group(1)] = set(re.findall(r"\b[0-9a-f]{64}\b", b))
        self.assertEqual(found, expected)

    def test_k3s_image_matches_workflows(self):
        image = yaml.safe_load((ROOT / "os" / "versions.lock.yaml").read_text())["tools"]["app_gate"]["k3s_image"]
        for wf in ("ci-apps.yml", "apps-rescan.yml", "apps-gate-all.yml"):
            text = (ROOT / ".github" / "workflows" / wf).read_text()
            refs = set(re.findall(r"docker\.io/rancher/k3s:\S+", text))
            self.assertEqual(refs, {image}, wf)


if __name__ == "__main__":
    unittest.main()
