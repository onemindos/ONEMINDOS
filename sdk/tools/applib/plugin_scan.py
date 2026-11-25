# SPDX-License-Identifier: Apache-2.0
"""Scan frozen unpacked plugin bytes; OCI/referrer verification is a separate gate."""
from __future__ import annotations

import hashlib
from pathlib import Path
import stat
import tempfile

from . import common


def scan_bundle(root: Path, *, scanner: str, database: Path | None = None) -> dict:
    root = root.resolve()
    if not root.is_dir():
        raise common.ToolError("plugin bundle is not a directory")
    files, total = [], 0
    for count, path in enumerate(root.rglob("*"), 1):
        if count > 8192:
            raise common.ToolError("plugin bundle exceeds entry limit")
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise common.ToolError("plugin bundle contains a symlink or special file")
        if len(files) >= 4096:
            raise common.ToolError("plugin bundle exceeds 4096 files")
        if stat.S_ISREG(mode):
            files.append(path)
    if not files:
        raise common.ToolError("plugin bundle contains no files")
    files.sort()
    digest = hashlib.sha256()
    with tempfile.TemporaryDirectory(prefix="onemind-plugin-scan-") as tmp:
        frozen = Path(tmp)
        for source in files:
            relative = source.relative_to(root)
            with source.open("rb") as stream:
                data = stream.read(8 * 1024**2 + 1)
            total += len(data)
            if len(data) > 8 * 1024**2 or total > 64 * 1024**2:
                raise common.ToolError("plugin bundle exceeds scan byte limits")
            digest.update(relative.as_posix().encode() + b"\0" + hashlib.sha256(data).digest())
            target = frozen / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        db = ["--database", str(database)] if database else []
        result = common.run([scanner, *db, "--recursive", "--infected", "--no-summary",
                             "--follow-dir-symlinks=0", "--follow-file-symlinks=0",
                             "--max-filesize=8M", "--max-scansize=128M", "--max-files=10000",
                             "--alert-exceeds-max=yes", str(frozen)], timeout=300)
        hits = [line.replace(str(frozen), "bundle") for line in result.stdout.splitlines() if line.endswith(" FOUND")]
        if result.returncode not in (0, 1) or (result.returncode == 1 and not hits):
            raise common.ToolError("plugin bundle scanner failed; no passing scan can be recorded")
        return {"sha256": "sha256:" + digest.hexdigest(), "files": len(files), "bytes": total,
                "infected": len(hits), "findings": hits}
