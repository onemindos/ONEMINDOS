# SPDX-License-Identifier: Apache-2.0
"""Real ClamAV detects EICAR in plugin UI bytes; scan failures stay closed."""
import hashlib
import argparse
import json
import os
import runpy
import subprocess
from unittest.mock import patch

import yaml
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from applib import common, plugin_scan

# Standard harmless AV test vector, assembled so repository secret/malware greps
# do not mistake this test module itself for the file submitted to the scanner.
EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$" + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


class PluginScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "plugin"
        (self.root / "ui").mkdir(parents=True)
        (self.root / "onemind.app.yaml").write_text("kind: App\n")

    @unittest.skipUnless(shutil.which("clamscan"), "real ClamAV engine is required")
    def test_real_engine_blocks_eicar_in_ui(self):
        # A tiny custom test database exercises the genuine engine without a network
        # signature download. Production CI uses its freshclam-managed database.
        database = Path(self.tmp.name) / "test.hdb"
        database.write_text(f"{hashlib.md5(EICAR).hexdigest()}:{len(EICAR)}:OneMind.EICAR.Test\n")
        scanner = shutil.which("clamscan")
        clean = plugin_scan.scan_bundle(self.root, scanner=scanner, database=database)
        self.assertEqual(clean["infected"], 0)
        payload = self.root / "ui" / "payload.txt"
        payload.write_bytes(EICAR)
        infected = plugin_scan.scan_bundle(self.root, scanner=scanner, database=database)
        self.assertEqual(infected["infected"], 1)
        self.assertNotEqual(infected["sha256"], clean["sha256"])
        self.assertIn("bundle/ui/payload.txt", infected["findings"][0])
        self.assertNotIn(str(self.root), infected["findings"][0])

    def test_symlink_is_refused_before_scanning(self):
        (self.root / "ui" / "linked").symlink_to(self.root / "onemind.app.yaml")
        with self.assertRaisesRegex(common.ToolError, "symlink"):
            plugin_scan.scan_bundle(self.root, scanner="missing-scanner")

    def test_failed_scanner_cannot_produce_a_passing_scan(self):
        with self.assertRaises(common.ToolError):
            plugin_scan.scan_bundle(self.root, scanner=sys.executable)

    def test_oversized_bundle_file_is_refused(self):
        with (self.root / "ui" / "huge").open("wb") as stream:
            stream.truncate(8 * 1024**2 + 1)
        with self.assertRaisesRegex(common.ToolError, "byte limits"):
            plugin_scan.scan_bundle(self.root, scanner="missing-scanner")


    @unittest.skipUnless(shutil.which("clamscan"), "real ClamAV engine is required")
    def test_real_gate_blocks_infected_declarative_bundle(self):
        repo = Path(__file__).resolve().parents[3]
        binary = Path(self.tmp.name) / "onemind"
        subprocess.run(["go", "build", "-trimpath", "-buildvcs=false", "-o", str(binary), "./cmd/onemind"], cwd=repo,
                       check=True, capture_output=True, timeout=180)
        doc = yaml.safe_load((repo / "apps/uptime-kuma/onemind.app.yaml").read_text())
        doc["metadata"]["id"] = self.root.name
        doc["metadata"].pop("source", None); doc["metadata"].pop("links", None)
        doc["spec"].pop("manifests"); doc["spec"].pop("web", None)
        doc["spec"]["compat"] = {"onemind": ">=0.3 <1.0"}
        doc["spec"]["extensions"] = {"settings": {"schema": "settings.schema.json"}}
        (self.root / "onemind.app.yaml").write_text(yaml.safe_dump(doc))
        (self.root / doc["metadata"]["icon"]).write_text("<svg/>")
        (self.root / "settings.schema.json").write_text(json.dumps({"type": "object"}))
        (self.root / "ui/payload.txt").write_bytes(EICAR)
        database = Path(self.tmp.name) / "test.hdb"
        database.write_text(f"{hashlib.md5(EICAR).hexdigest()}:{len(EICAR)}:OneMind.EICAR.Test\n")
        Gate = runpy.run_path(str(repo / "sdk/tools/app-gate"))["Gate"]
        with patch.dict(os.environ, ONEMIND_PLUGIN_VALIDATOR=str(binary)):
            scan, tier = Gate(self.root, argparse.Namespace(clamav_db=database, smoke=False), None, None).run()
        self.assertEqual(scan["result"], "fail")
        self.assertEqual(tier, "blocked")
        self.assertEqual(scan["plugin_bundle"]["infected"], 1)
