---
pr: 1251
branch: claude/parity-ratchet
---
Surface parity ratchet (#1232): a unit test (test/unit/test_surface_parity.py running sdk/tools/surface-parity) reads the OpenAPI spec and requires, for every operation, a dashboard caller found by SDK method or by a call with its HTTP method, an onemind command for every write, and a phone caller for the phone's 1.0 scope. Today's real gaps are seeded in sdk/tools/surface-parity/exemptions.txt with a reason and an owner issue (#1232, #1213, #1214, #1244); a new operation without a screen or command fails, and so does a stale exemption, so the list only shrinks. BUILDER-BRIEFING item 6 points at it and records the mobile 1.0 scope for the founder to confirm.
