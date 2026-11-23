# SPDX-License-Identifier: Apache-2.0
"""Licence guard (issue #855): no Meshtastic in this Apache-2.0 repo.

Meshtastic's protobufs are GPL-3.0, so the 1.1 Meshtastic bridge (#739) lives in its own GPL repo. This
fails if any dependency file anywhere in the repo names a Meshtastic package (the root go.mod and go.sum
of cmd/ and internal/, where the onemindd LoRa driver #740 lives, the root requirements-dev.txt, ui/,
site/, tests/e2e, desktop's Cargo files and every app folder included), or if a Meshtastic .proto file or
code generated from one appears. Only dependency caches and build output are skipped. MeshCore (MIT) is
allowed. Stdlib only.
"""
from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
# Dependency caches and build output only: everything else, the repo root included, is scanned.
SKIP_DIRS = {"node_modules", ".venv", "venv", "__pycache__", ".git", "dist", "build", "target", ".pytest_cache", "work"}
DEPENDENCY_FILE = re.compile(r"^(package\.json|package-lock\.json|npm-shrinkwrap\.json|yarn\.lock|pnpm-lock\.yaml|"
                             r"requirements[^/]*\.txt|pyproject\.toml|uv\.lock|poetry\.lock|Pipfile(\.lock)?|setup\.(py|cfg)|"
                             r"go\.mod|go\.sum|go\.work|Cargo\.toml|Cargo\.lock)$")
GENERATED = re.compile(r"(\.proto|_pb2\.pyi?|_pb2_grpc\.py|\.pb\.go|_pb\.(js|ts|d\.ts)|\.pb\.(js|ts))$")
MESHTASTIC = re.compile(r"@meshtastic/|meshtastic-sdk|meshtastic", re.IGNORECASE)


def offenders(root: Path) -> list[str]:
    """Each file under root (the repo root itself included) that brings Meshtastic in, as 'path: why'."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            if DEPENDENCY_FILE.match(name):
                hit = MESHTASTIC.search(path.read_text(encoding="utf-8", errors="replace"))
                if hit:
                    out.append(f"{rel}: names {hit.group(0)!r} (GPL-3.0, not allowed in this repo)")
            elif GENERATED.search(name):
                text = path.read_text(encoding="utf-8", errors="replace")
                if MESHTASTIC.search(rel) or MESHTASTIC.search(text):
                    out.append(f"{rel}: Meshtastic protobuf or code generated from it (GPL-3.0)")
    return sorted(out)


class MeshtasticLicenceGuard(unittest.TestCase):
    def tree(self, files: dict[str, str]) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for rel, body in files.items():
            (Path(tmp.name) / rel).parent.mkdir(parents=True, exist_ok=True)
            (Path(tmp.name) / rel).write_text(body)
        return Path(tmp.name)

    def test_the_repo_is_clean(self):
        self.assertEqual(offenders(ROOT), [])

    def test_a_planted_meshtastic_dependency_fails(self):
        root = self.tree({
            "mobile/package.json": '{"dependencies": {"@meshtastic/protobufs": "2.7.0"}}\n',
            "core/requirements-radio.txt": "meshtastic==2.7.3\n",
            "dashboard/pnpm-lock.yaml": "packages:\n  /meshtastic-sdk@1.0.0: {}\n",
        })
        found = offenders(root)
        self.assertEqual([f.split(":")[0] for f in found],
                         ["core/requirements-radio.txt", "dashboard/pnpm-lock.yaml", "mobile/package.json"])
        self.assertIn("'@meshtastic/'", found[2])

    def test_the_repo_root_and_every_other_folder_are_scanned(self):
        # The root module is cmd/ and internal/ (the onemindd LoRa driver, #740): its go.mod and go.sum count.
        planted = {
            "go.mod": "module github.com/onemindos/ONEMINDOS\n\nrequire github.com/meshtastic/go v1.0.0\n",
            "go.sum": "github.com/meshtastic/go v1.0.0 h1:abc=\n",
            "requirements-dev.txt": "PyYAML==6.0.3\nmeshtastic==2.7.3\n",
            "ui/package.json": '{"dependencies": {"@meshtastic/js": "2.6.0"}}\n',
            "site/package-lock.json": '{"packages": {"node_modules/@meshtastic/core": {}}}\n',
            "tests/e2e/package.json": '{"devDependencies": {"@meshtastic/transport-http": "1.0.0"}}\n',
            "desktop/src-tauri/Cargo.toml": '[dependencies]\nmeshtastic = "0.1"\n',
            "apps/radio/pyproject.toml": '[project]\ndependencies = ["meshtastic"]\n',
            "os/tools/requirements.txt": "meshtastic\n",
        }
        root = self.tree({**planted, "ui/node_modules/@meshtastic/js/package.json": '{"name": "@meshtastic/js"}\n'})
        self.assertEqual([f.split(":")[0] for f in offenders(root)], sorted(planted))  # node_modules is a cache, not a dependency file

    def test_meshtastic_protos_and_generated_stubs_fail(self):
        root = self.tree({
            "internal/radio/proto/mesh.proto": 'syntax = "proto3";\npackage meshtastic;\n',
            "sdk/python/radio/mesh_pb2.py": "DESCRIPTOR = _descriptor.FileDescriptor(name='meshtastic/mesh.proto')\n",
            "mobile/src/meshtastic/admin_pb.ts": "export const x = 1;\n",
        })
        self.assertEqual(len(offenders(root)), 3)

    def test_meshcore_and_unrelated_files_pass(self):
        root = self.tree({
            "mobile/package.json": '{"dependencies": {"react-native-ble-plx": "3.5.1"}, "description": "MeshCore companion"}\n',
            "internal/meshcore/codec.go": "// talks to MeshCore, not Meshtastic\npackage meshcore\n",
            "sdk/schema/other.proto": 'syntax = "proto3";\npackage onemind;\n',
            "core/README.md": "Meshtastic is a 1.1 bridge in its own repo.\n",
        })
        self.assertEqual(offenders(root), [])


if __name__ == "__main__":
    unittest.main()
