# SPDX-License-Identifier: Apache-2.0
"""Convert an older app manifest to the frozen v1 form (PLAN-E6, issue #175).

v1 keeps every v1alpha1 field, so the converter only moves `apiVersion` and says what it did. It
never invents a field or drops one. Anything it cannot convert is returned as an error, not guessed.
Standard library only, so the CI tool, the CLI and the gateway all load the same file.
"""
from __future__ import annotations

import copy

CURRENT = "onemind.app/v1"
OLDER = ("onemind.app/v1alpha1",)


def convert_manifest(doc: object) -> tuple[object, list[str]]:
    """Return (converted copy, notes). A doc that is not a known manifest comes back unchanged
    with a note starting "cannot convert"."""
    if not isinstance(doc, dict):
        return doc, ["cannot convert: manifest is not a mapping"]
    version = doc.get("apiVersion")
    if version == CURRENT:
        return copy.deepcopy(doc), []
    if version not in OLDER:
        return copy.deepcopy(doc), [f"cannot convert: unknown apiVersion {version!r}"]
    out = copy.deepcopy(doc)
    out["apiVersion"] = CURRENT
    return out, [f"apiVersion {version} -> {CURRENT}"]
