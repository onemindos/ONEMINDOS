# SPDX-License-Identifier: Apache-2.0
"""Which apps does a change to research-output/evidence/license-matrix.csv affect?

The matrix feeds only the licence check (applib/licence.py: matrix_rows). An app's check reads the rows
that cite its upstream repository, so a changed, added or removed row can change an app's result only
if it cites that app's repository. Rows about the kernel, Debian or other apps change nothing for it.
The mapping row -> app is the same function the gate uses (licence.matrix_rows_from_text), so the two
cannot drift apart. Any doubt (unreadable CSV, missing header) selects every app: slower, never unsafe.
"""
from __future__ import annotations

import csv
import io
import re
import tarfile
from pathlib import Path, PurePosixPath

from . import common, licence

SYSTEM_PREFIX = "system."
APP_ID = re.compile(r"[a-z0-9][a-z0-9-]*")
RESULT_FILES = frozenset({common.MANIFEST_NAME, "scan.json", "README.md"})


def app_path(key: str) -> PurePosixPath:
    system = key.startswith(SYSTEM_PREFIX)
    app_id = key.removeprefix(SYSTEM_PREFIX)
    if not APP_ID.fullmatch(app_id):
        raise ValueError(f"invalid gate app key: {key!r}")
    root = PurePosixPath("apps/_system" if system else "apps")
    return root / app_id


def inventory(apps_dir: Path) -> list[str]:
    keys = []
    for root, prefix in ((apps_dir, ""), (apps_dir / "_system", SYSTEM_PREFIX)):
        for directory in root.glob(f"*/{common.MANIFEST_NAME}"):
            app_id = directory.parent.name
            if not APP_ID.fullmatch(app_id):
                continue
            if prefix:
                spec = common.load_manifest(directory.parent)["spec"]
                if spec.get("runtime") != "container" and "manifests" not in spec:
                    continue
            keys.append(prefix + app_id)
    return sorted(keys)


def changed_apps(keys: list[str], paths: str) -> list[str]:
    folders = {PurePosixPath(path).parts[:depth] for path in paths.splitlines() for depth in (2, 3)}
    return [key for key in keys if app_path(key).parts in folders]


def apply_scan(key: str, files: str, archive: Path, repo: Path) -> None:
    target = app_path(key)
    permitted = {str(target / name) for name in RESULT_FILES}
    paths = files.splitlines()
    if len(paths) != len(set(paths)) or not set(paths) <= permitted:
        raise ValueError(f"unexpected refreshed file for {key}")
    # Read only the named regular members. No archive path is extracted by tarfile.
    with tarfile.open(archive, "r:") as tar:
        members = tar.getmembers()
        if sorted(member.name for member in members) != sorted(paths):
            raise ValueError(f"unexpected archive member for {key}")
        for member in members:
            if not member.isfile():
                raise ValueError(f"not a regular file: {member.name}")
            destination = repo / member.name
            if destination.resolve() != repo.resolve() / member.name:
                raise ValueError(f"refusing linked destination for {key}")
        for member in members:
            with tar.extractfile(member) as source:
                (repo / member.name).write_bytes(source.read())


def app_repos(apps_dir: Path) -> dict[str, str | None]:
    """{app id: 'owner/repo' the gate would read matrix rows for (None when it has no GitHub repo)}."""
    out = {}
    for key in inventory(apps_dir):
        directory = apps_dir.joinpath(*app_path(key).parts[1:])
        out[key] = common.owner_repo(common.load_manifest(directory))
    return out


def _canonical(rows: list[dict]) -> list[tuple]:
    return sorted(tuple(sorted((k or "", v or "") for k, v in r.items())) for r in rows)


def apps_with_changed_rows(old_csv: str, new_csv: str, repos: dict[str, str | None]) -> list[str]:
    """Ids whose matrix rows differ between old_csv and new_csv. Raises ValueError for an unusable CSV."""
    for text in (old_csv, new_csv):
        if text.strip():
            header = next(csv.reader(io.StringIO(text, newline="")), [])
            if not {"component", "SPDX", "source", "license_file_permalink"} <= set(header):
                raise ValueError("license-matrix.csv header is not the expected one")
    changed = []
    for app_id, repo in repos.items():
        if not repo:
            continue
        before = _canonical(licence.matrix_rows_from_text(old_csv, repo)) if old_csv.strip() else []
        after = _canonical(licence.matrix_rows_from_text(new_csv, repo)) if new_csv.strip() else []
        if before != after:
            changed.append(app_id)
    return changed
