# SPDX-License-Identifier: Apache-2.0
"""Which apps does the ci-apps gate run for? (plan, below) And which apps does a change to
research-output/evidence/license-matrix.csv affect?

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
from collections.abc import Callable, Iterable
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


# --- ci-apps plan: which apps a run gates --------------------------------------------------------
# Founder decision 2026-11-25: a pull request gates only the apps it changes, so a PR that touches no
# app does not queue ~80 gate jobs on the free runners. Nothing is weakened:
#   - every run (every PR too) still validates EVERY manifest in the `validate` job (checks 1 + 8);
#   - a landing (a PR into main), the merge queue, the nightly schedule and a manual run gate every app.
# The files the `gate` job runs or reads besides apps/<id>/. A change to one can change any app's gate
# result, so a pull request that touches one gates every app. An entry ending in "/" is a folder.
# test/unit/test_ci_apps_plan.py checks that every sdk/tools path the gate job names is listed here.
# Not listed on purpose: what validate-apps imports or reads (core/onemind_core/catalog.py and its
# imports, the Go plugin validator built from cmd/onemind and internal/plugin, go.mod, sdk/policy,
# renovate.json). Those change only validate-apps' verdict, and the `validate` job gives that verdict
# for every app on every run. validate-apps itself is listed because app-gate calls it by its command line.
SHARED_GATE_INPUTS = (
    ".github/workflows/ci-apps.yml",       # the gate job itself, with the pinned k3s node image
    "sdk/tools/app-gate",                  # checks 2-9
    "sdk/tools/app-select",                # this plan and the app path the gate job resolves
    "sdk/tools/applib/",                   # the gate's library (licence, quality, readme, retry, plugin scan)
    "sdk/tools/validate-apps",             # checks 1 + 8 for the one app, called by app-gate
    "sdk/tools/requirements.txt",          # the gate's pinned Python packages
    "sdk/tools/ci/install-tools.sh",       # pinned trivy, crane, cosign, k3d, kubectl, kustomize, kubeconform
    "sdk/tools/ci/map-packs-volume.sh",    # the Offline Maps packs volume the hub provisions, made in the gate cluster
    "sdk/schema/onemind.app.schema.json",  # the app schema every manifest is checked against
)
LICENCE_MATRIX = "research-output/evidence/license-matrix.csv"
# Pull requests into these branches are landings: they gate every app.
LANDING_BASES = frozenset({"main"})


def is_shared_gate_input(path: str) -> bool:
    return any(path.startswith(entry) if entry.endswith("/") else path == entry for entry in SHARED_GATE_INPUTS)


def plan(event: str, base_ref: str, changed: Iterable[str], keys: list[str],
         matrix_apps: Callable[[], list[str]]) -> tuple[list[str], str]:
    """(gate keys, reason) for one ci-apps run.

    Only a pull_request into a branch that is not a landing base can narrow the list; every other event
    (schedule, workflow_dispatch, merge_group, or one this code does not know) gates every app.
    matrix_apps() returns the apps whose licence-matrix rows changed and raises ValueError when the rows
    cannot be compared (then every app is gated: slower, never unsafe).
    """
    if event != "pull_request":
        return list(keys), f"{event or 'unknown'} run: every app"
    if base_ref in LANDING_BASES:
        return list(keys), f"pull request into {base_ref} (a landing): every app"
    changed = sorted({p for p in changed if p})
    touched = changed_apps(keys, "\n".join(changed))
    shared = [p for p in changed if is_shared_gate_input(p)]
    if shared:
        # Every app, the ones the PR touches first: with max-parallel 4 their results come back first.
        first = [key for key in keys if key in touched]
        return first + [key for key in keys if key not in touched], \
            "shared gate input changed (" + ", ".join(shared) + "): every app"
    picked = set(touched)
    reason = "apps the pull request changes"
    if LICENCE_MATRIX in changed:
        try:
            rows = set(matrix_apps())
        except ValueError as exc:
            return list(keys), f"licence matrix rows could not be compared ({exc}): every app"
        picked |= rows & set(keys)
        reason += ", and apps whose licence-matrix rows changed (" + (", ".join(sorted(rows)) or "none") + ")"
    return [key for key in keys if key in picked], reason
