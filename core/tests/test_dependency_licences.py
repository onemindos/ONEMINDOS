# SPDX-License-Identifier: Apache-2.0
"""Licence check of every installed Python distribution (repo rule: pinned dependencies with a
licence check). uv.lock pins each version and file hash; this test checks what those pins installed.

It runs on whatever dependency groups are installed: `make -C core test` checks the runtime and
`dev` groups (Hypothesis among them); .github/workflows/api-fuzz.yml runs it again after
`uv sync --group fuzz`, which adds Schemathesis and its dependencies.

The licence of a distribution, first that applies:
1. its License-Expression metadata (PEP 639);
2. its License field, when that is an SPDX expression;
3. its one License classifier, when that classifier names exactly one licence;
4. the REVIEWED table below, with the licence read from the project's own licence file.
The class comes from the Market licence classifier (sdk/tools/applib/licence.py, contract §9.4):
L1 (permissive) passes; L2 (copyleft) and anything else pass only with a REVIEWED entry that says
why it is acceptable. Records: docs/testing/PROPERTY-AND-FUZZ.md "Test-only dependencies".
"""

from __future__ import annotations

import importlib.metadata as md
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sdk" / "tools"))
from applib.licence import classify  # noqa: E402

# Classifiers that name a single licence and version. "BSD License" or "Apache Software License"
# do not say which version, so they never count on their own.
CLASSIFIERS = {
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "License :: OSI Approved :: ISC License (ISCL)": "ISC",
    "License :: OSI Approved :: The Unlicense (Unlicense)": "Unlicense",
    "License :: OSI Approved :: Zero-Clause BSD (0BSD)": "0BSD",
}

# name -> (SPDX expression, why it is acceptable, primary source read 2026-11-12)
REVIEWED = {
    "psycopg": (
        "LGPL-3.0-only",
        "PostgreSQL driver (BD-04), used unmodified as a separate library: the gateway's `postgres` extra and the dev group",
        "https://github.com/psycopg/psycopg/blob/master/LICENSE.txt",
    ),
    "psycopg-binary": (
        "LGPL-3.0-only",
        "the same driver's prebuilt wheel, used unmodified as a separate library",
        "https://github.com/psycopg/psycopg/blob/master/LICENSE.txt",
    ),
    "typing-extensions": (
        "PSF-2.0",
        "permissive (OSI approved); the Market list is for app licences and does not name it",
        "https://github.com/python/typing_extensions/blob/main/LICENSE",
    ),
    "pyasn1-modules": (
        "BSD-2-Clause",
        "no SPDX in metadata (webauthn dependency); the licence file is the 2-clause BSD text, permissive",
        "https://github.com/pyasn1/pyasn1-modules/blob/master/LICENSE.txt",
    ),
    "pyopenssl": (
        "Apache-2.0",
        "metadata says 'Apache License, Version 2.0' (free text, no SPDX); the licence file is the Apache License 2.0",
        "https://github.com/pyca/pyopenssl/blob/main/LICENSE",
    ),
    "sortedcontainers": (
        "Apache-2.0",
        "metadata says 'Apache 2.0'; the licence file is the Apache License 2.0. Test-only (Hypothesis)",
        "https://github.com/grantjenks/python-sortedcontainers/blob/master/LICENSE",
    ),
    "uvloop": (
        "MIT OR Apache-2.0",
        "metadata says 'MIT License' with both classifiers; the README says dual-licensed MIT and Apache 2.0",
        "https://github.com/MagicStack/uvloop/blob/master/README.rst",
    ),
}


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def licence_of(dist: md.Distribution) -> tuple[str | None, str]:
    """(SPDX expression or None, where it came from)."""
    meta = dist.metadata
    if expr := (meta.get("License-Expression") or "").strip():
        return expr, "License-Expression"
    field = (meta.get("License") or "").strip()
    if field and "\n" not in field and classify(field) != "blocked":
        return field, "License"
    licence_classifiers = [c for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
    if len(licence_classifiers) == 1 and licence_classifiers[0] in CLASSIFIERS:
        return CLASSIFIERS[licence_classifiers[0]], "classifier"
    return None, "unknown"


DISTS = sorted({norm(d.metadata["Name"]): d for d in md.distributions() if norm(d.metadata["Name"]) != "onemind-core"}.items())


@pytest.mark.parametrize("name,dist", DISTS, ids=[n for n, _ in DISTS])
def test_installed_distribution_has_an_accepted_licence(name, dist):
    expr, source = licence_of(dist)
    reviewed = REVIEWED.get(name)
    if reviewed is not None:
        spdx, why, url = reviewed
        assert why and url.startswith("https://"), name
        if source == "License-Expression":  # the review must match what the package now declares
            assert expr == spdx, f"{name} {dist.version} now declares {expr!r}, reviewed as {spdx!r}"
        return
    assert expr is not None, (
        f"{name} {dist.version}: no SPDX licence in its metadata; read its licence file and add a "
        f"REVIEWED entry (tests/test_dependency_licences.py)"
    )
    cls = classify(expr)
    assert cls == "L1", f"{name} {dist.version}: {expr} ({source}) is {cls}; add a reviewed entry or drop it"
