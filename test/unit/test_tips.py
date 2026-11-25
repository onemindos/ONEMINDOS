# SPDX-License-Identifier: Apache-2.0
"""The always-running CI unit job checks the actual tips pack, including content-only PRs."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "cmd/onemind/cli/tips_author.py"


class TipsTest(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.repo = Path(work.name) / "checkout"
        shutil.copytree(ROOT / "tips", self.repo / "tips")
        shutil.copytree(ROOT / "dashboard/src/screens", self.repo / "dashboard/src/screens")
        (self.repo / "mobile").mkdir()
        shutil.copy(ROOT / "mobile/App.tsx", self.repo / "mobile")
        self.files = self.repo / "tips/entries"
        self.seed = self.files / "start-on-home.md"

    def author(self, command, *args, stdin="", env=None):
        return subprocess.run([sys.executable, "-I", TOOL, command, "--root", self.repo, *args],
                              cwd=self.repo.parent, input=stdin, text=True, capture_output=True, env=env)

    def test_seed_pack_and_preview(self):
        result = self.author("check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertGreaterEqual(len(list(self.files.glob("*.md"))), 12)
        self.seed.write_text(self.seed.read_text().replace("On Home,", "On **Home**, read <script> literally and"))
        page = self.author("preview")
        self.assertEqual(page.returncode, 0, page.stderr)
        self.assertIn("<strong>Home</strong>", page.stdout)
        self.assertIn("&lt;script&gt;", page.stdout)

    def test_new_and_collision(self):
        answers = "First steps\n1\n1\n1\n0.1.0\nRead the request.\n"
        result = self.author("new", stdin=answers)
        self.assertEqual(result.returncode, 0, result.stderr)
        draft = self.files / "first-steps.md"
        self.assertIn("Read the request.", draft.read_text())
        self.assertEqual(self.author("check").returncode, 0)
        self.assertNotEqual(self.author("new", stdin=answers).returncode, 0)

    def test_refusals_through_checker(self):
        original = self.seed.read_text()
        metadata, body = original.split("---\n")[1:]
        for changed, text, error in [
                ({"collection": "missing"}, body, "unknown collection"),
                ({"opens": {"dashboard": "/bad", "phone": "onemind://home"}}, body, "dead dashboard"),
                ({"opens": {"dashboard": "/", "phone": "onemind://bad"}}, body, "dead phone"),
                ({"clip": {"release": "v1"}}, body, "caption"),
                ({}, "One. Two! Three? Four. Five.", "four sentences")]:
            with self.subTest(error=error):
                self.seed.write_text("---\n" + yaml.safe_dump({**yaml.safe_load(metadata), **changed}) + "---\n" + text)
                result = self.author("check")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(error, result.stderr)

    def test_real_sizes_and_probe_limits(self):
        self.seed.write_text(self.seed.read_text().replace("from: ", "clip: {release: v1, caption: Read the plan.}\nfrom: "))
        assets = self.repo.parent / "assets"
        directory = assets / "v1"
        directory.mkdir(parents=True)
        for ext in ("mp4", "webm", "jpg"):
            (directory / f"start-on-home.{ext}").write_bytes(b"\xff\xd8\xff")
        tools = self.repo.parent / "bin"
        tools.mkdir()
        env = {**os.environ, "PATH": str(tools)}
        def check():
            return self.author("check", "--assets", assets, env=env)
        self.assertIn("install ffmpeg", check().stderr)
        for command in ("ffmpeg", "ffprobe"):
            fixture = tools / command
            fixture.write_text('#!/bin/sh\necho \'{"streams":[{"codec_type":"video"}],"format":{"duration":"31"}}\'\n')
            fixture.chmod(0o755)
        self.assertIn("30 seconds", check().stderr)
        fixture.write_text(fixture.read_text().replace('"31"', '"30"'))
        self.assertEqual(check().returncode, 0)
        page = self.author("preview", "--assets", assets, env=env)
        self.assertIn('kind="captions"', page.stdout)
        self.assertIn('canPlayType("video/webm")', page.stdout)
        fixture.write_text(fixture.read_text().replace('{"codec_type":"video"}', '{"codec_type":"video"},{"codec_type":"audio"}'))
        self.assertIn("silent", check().stderr)
        (directory / "start-on-home.mp4").write_bytes(bytes(3_100_000))
        self.assertIn("3 MB", check().stderr)
