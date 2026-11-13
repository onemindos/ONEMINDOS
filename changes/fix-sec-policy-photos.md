---
pr: pending
branch: fix/sec-policy-photos
---
Test-only: adds the seven missing `/v1/photos/*` rows to the route policy table (`core/tests/sec_policy.py`) so `test_every_route_has_a_policy_row` passes again on main after the photos and policy-table PRs merged together. The rows record what the code returns on the matrix gateway, where Photos is switched off: 404 for every caller holding a credential and the scope, 403 for a child.
