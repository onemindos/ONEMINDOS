<!-- SPDX-License-Identifier: Apache-2.0 -->
# Audit chain test vectors

Shared by `core/tests/test_devsurface_api.py` (Python, `auditread.verify_file`) and `sdk/go` (`onemind audit verify --file`), so the two implementations of the rule in `core/onemind_core/audit.py` can never disagree. `expected.json` gives `ok`, `records` (verified before the first bad one) and `first_bad_seq` per file. Regenerate only together with a change to the rule.
