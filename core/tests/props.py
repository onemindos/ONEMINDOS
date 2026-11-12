# SPDX-License-Identifier: Apache-2.0
"""Shared settings and strategies for the Hypothesis property tests (test_properties_*.py).

How to run them, and what each one proves: docs/testing/PROPERTY-AND-FUZZ.md.

ONEMIND_PROPERTY_DEPTH picks the example budget:
  (unset)  every `make -C core test` and every PR; a few seconds in total
  deep     the nightly run in .github/workflows/api-fuzz.yml; 20 times as many examples

A failing example is printed with a `@reproduce_failure` blob and saved in core/.hypothesis/
(gitignored), so the next run tries it first.
"""

from __future__ import annotations

import os

from hypothesis import HealthCheck, settings
from hypothesis import strategies as st

DEPTH = os.environ.get("ONEMIND_PROPERTY_DEPTH", "").strip().lower()
if DEPTH not in ("", "deep"):
    raise ValueError("ONEMIND_PROPERTY_DEPTH must be unset or 'deep'")
SCALE = 20 if DEPTH == "deep" else 1


def budget(examples: int, **kw) -> settings:
    """@budget(n): n examples per run (20n when deep), no per-example deadline.

    The deadline is off because the stateful tests touch SQLite and fsync the audit file, whose
    speed depends on the runner, not on the code under test.
    """
    if os.environ.get("ONEMIND_PROPERTY_ARTIFACTS"):
        # Retained diagnostic runs must not mutate/delete Hypothesis cache entries.
        # This changes persistence only, never examples, shrinking or assertions.
        kw.setdefault("database", None)
    return settings(
        max_examples=examples * SCALE,
        deadline=None,
        print_blob=True,
        suppress_health_check=[HealthCheck.too_slow],
        **kw,
    )


# Any JSON value Python's json module writes and reads back unchanged (no NaN or infinity, which
# json.dumps writes but strict readers refuse).
json_scalars = st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False, allow_infinity=False) | st.text()
json_values = st.recursive(
    json_scalars,
    lambda inner: st.lists(inner, max_size=4) | st.dictionaries(st.text(max_size=8), inner, max_size=4),
    max_leaves=12,
)
