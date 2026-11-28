# SPDX-License-Identifier: Apache-2.0
"""Every module under onemind_core/ has a production importer, or is listed here with its epic.

Slop audit CS-04: three finished-looking modules (about 1,300 lines) sat on main with passing
tests, and nobody called them. A new module that nothing imports now fails this test.
"""

from __future__ import annotations

import re
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "onemind_core"

# module (dotted, relative to onemind_core) -> the epic that mounts it. Delete the line when wired.
NOT_MOUNTED_YET: dict[str, str] = {
    "boxbundle": "#1285 box export and import: the package; mounted with the phase 3 routes",
    "boxbundle.box_config": "#1285 box export and import: phase 1 is data only; the export and import routes are phase 3 and 4",
}
ENTRY_POINTS = {"__init__", "__main__", "openapi", "cli"}  # run by `python -m`, a console script (pyproject [project.scripts]), or imported as a package


def _modules() -> dict[str, str]:
    mods = {}
    for p in PKG.rglob("*.py"):
        rel = p.relative_to(PKG).with_suffix("")
        name = ".".join(rel.parts)
        mods[name.removesuffix(".__init__")] = p.read_text(encoding="utf-8")
    return mods


def _imported(name: str, mods: dict[str, str]) -> bool:
    leaf = name.rsplit(".", 1)[-1]
    # Lenient on purpose (a leaf name like "service" exists in several packages): any
    # `from ...<leaf> import`, `from ... import ..<leaf>` or `import ...<leaf>` counts.
    pats = [
        rf"from\s+[\w.]*\b{re.escape(leaf)}\s+import",
        # A submodule import loads its package too: `from ..appstore.service import X` wires appstore.
        rf"from\s+[\w.]*\b{re.escape(leaf)}\.[\w.]+\s+import",
        rf"from\s+[\w.]+\s+import[^\n]*\b{re.escape(leaf)}\b",
        rf"^\s*import\s+[\w.]*\b{re.escape(leaf)}\b",
        rf"from\s+[\w.]+\s+import\s*\([^)]*\b{re.escape(leaf)}\b",
    ]
    for other, text in mods.items():
        if other == name:
            continue
        if any(re.search(p, text, re.M) for p in pats):
            return True
    return False


def _discovered_routers() -> set[str]:
    """Router modules app.py mounts through routers.discover() (CI-06, #231), not through imports."""
    from onemind_core.routers import discover

    return {"routers." + r.__module__.rsplit(".", 1)[1] for r in discover()}


def test_every_module_is_imported_or_listed():
    mods = _modules()
    mounted = _discovered_routers()
    orphans = sorted(
        n for n in mods
        if n.split(".")[-1] not in ENTRY_POINTS and n not in NOT_MOUNTED_YET and n not in mounted
        and not _imported(n, mods)
    )
    assert not orphans, f"modules nothing imports: {orphans}. Wire them, or list them in NOT_MOUNTED_YET with the epic."


def test_discovered_routers_are_real_modules():
    mods = _modules()
    mounted = _discovered_routers()
    assert "routers.static" in mounted and "routers.guard" in mounted
    assert mounted <= set(mods)


def test_not_mounted_list_is_still_true():
    mods = _modules()
    wired = [n for n in NOT_MOUNTED_YET if _imported(n, mods)]
    assert not wired, f"{wired} are imported now; delete them from NOT_MOUNTED_YET"
