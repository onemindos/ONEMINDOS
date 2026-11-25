# SPDX-License-Identifier: Apache-2.0
"""Bind approved plans to plugin UI/settings files as well as the workload."""
from pathlib import Path
import stat


def fingerprint_files(app) -> list[Path]:
    spec = app.manifest.get("spec") or {}
    if "extensions" not in spec:
        return []
    ext = spec["extensions"]
    if not isinstance(ext, dict):
        raise ValueError("invalid extensions")
    base = app.dir.resolve()
    references = [app.manifest.get("metadata", {}).get("icon")]
    if "settings" in ext:
        references.append(ext["settings"].get("schema") if isinstance(ext["settings"], dict) else None)
    for tile in ext.get("tiles", []):
        if isinstance(tile, dict) and "icon" in tile:
            references.append(tile["icon"])
    files = set()

    def checked(relative):
        if not isinstance(relative, str) or not relative or "\\" in relative:
            raise ValueError("invalid plugin file reference")
        parts = Path(relative).parts
        if Path(relative).is_absolute() or any(p in {".", ".."} for p in parts):
            raise ValueError("plugin file escapes bundle")
        path = base
        for part in parts:
            path = path / part
            if path.is_symlink():
                raise ValueError("symlink in plugin bundle")
        if not path.resolve().is_relative_to(base) or not stat.S_ISREG(path.stat().st_mode):
            raise ValueError("plugin reference is not a regular bundle file")
        return path

    for relative in references:
        files.add(checked(relative))
    ui = base / "ui"
    if ui.is_symlink():
        raise ValueError("symlink in plugin UI")
    if ui.exists():
        if not ui.is_dir():
            raise ValueError("plugin UI root is not a directory")
        count = 0
        for path in ui.rglob("*"):
            count += 1
            if count > 4096 or path.is_symlink():
                raise ValueError("unsafe or oversized plugin UI tree")
            if not path.is_dir():
                files.add(checked(path.relative_to(base).as_posix()))
    sizes = [p.stat().st_size for p in files]
    if len(files) > 4096 or any(size > 4 * 1024**2 for size in sizes) or sum(sizes) > 32 * 1024**2:
        raise ValueError("plugin UI/settings exceed bundle bounds")
    return sorted(files)
