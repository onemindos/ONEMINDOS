---
pr: pending
branch: ci/net2vm-lan-range
status_rows: []
---
Moves the two-VM network test link from a documentation range to a private LAN range that the gateway already counts as LAN. Since the exposure-tier check (#285) the gateway refuses requests from addresses it cannot classify, so the test saw 404 instead of 200 on the vaultwarden bearer check. Test harness and its criteria only, no production behaviour change.
