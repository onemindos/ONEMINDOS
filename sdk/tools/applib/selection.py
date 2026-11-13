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
from pathlib import Path

from . import common, licence


def app_repos(apps_dir: Path) -> dict[str, str | None]:
    """{app id: 'owner/repo' the gate would read matrix rows for (None when it has no GitHub repo)}."""
    out = {}
    for d in sorted(apps_dir.iterdir()):
        if d.name.startswith(("_", ".")) or not (d / common.MANIFEST_NAME).is_file():
            continue
        out[d.name] = common.owner_repo(common.load_manifest(d))
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
