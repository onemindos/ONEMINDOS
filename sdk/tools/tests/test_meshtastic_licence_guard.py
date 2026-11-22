# SPDX-License-Identifier: Apache-2.0
"""Licence guard (issue #855): no Meshtastic in this Apache-2.0 repo.

Meshtastic's protobufs are GPL-3.0, so the 1.1 Meshtastic bridge (#739) lives in its own GPL repo. This
fails if any dependency file under core/ mobile/ dashboard/ desktop/ sdk/ cmd/ internal/ names a
Meshtastic package, or if a Meshtastic .proto file or code generated from one appears. MeshCore (MIT) is
allowed. Stdlib only.
"""
from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
AREAS = ("core", "mobile", "dashboard", "desktop", "sdk", "cmd", "internal")
SKIP_DIRS = {"node_modules", ".venv", "__pycache__", ".git", "dist", "build", "target", ".pytest_cache"}
DEPENDENCY_FILE = re.compile(r"^(package\.json|package-lock\.json|npm-shrinkwrap\.json|yarn\.lock|pnpm-lock\.yaml|"
                             r"requirements[^/]*\.txt|pyproject\.toml|uv\.lock|poetry\.lock|go\.mod|go\.sum)$")
GENERATED = re.compile(r"(\.proto|_pb2\.pyi?|_pb2_grpc\.py|\.pb\.go|_pb\.(js|ts|d\.ts)|\.pb\.(js|ts))$")
MESHTASTIC = re.compile(r"@meshtastic/|meshtastic-sdk|meshtastic", re.IGNORECASE)


def offenders(root: Path, areas: tuple[str, ...] = AREAS) -> list[str]:
    """Each file that brings Meshtastic in, as 'path: why'."""
    out = []
    for area in areas:
        for dirpath, dirnames, filenames in os.walk(root / area):
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
            "go.mod": "require github.com/meshtastic/go v1.0.0\n",  # outside the areas: not scanned
        })
        found = offenders(root)
        self.assertEqual([f.split(":")[0] for f in found],
                         ["core/requirements-radio.txt", "dashboard/pnpm-lock.yaml", "mobile/package.json"])
        self.assertIn("'@meshtastic/'", found[2])

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
