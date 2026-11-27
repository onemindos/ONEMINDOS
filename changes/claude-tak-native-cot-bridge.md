---
pr: 1260
branch: claude/tak-native-cot-bridge
---
TAK native, first slice (D-032). Adds the CoT bridge design (docs/architecture/TAK-NATIVE-COT-BRIDGE.md, with primary sources), a plain-language founder note, the D-032 decision entry, and internal/cot, a Go package that encodes, decodes and validates Cursor on Target XML events, maps OneMind positions to CoT and back (people only with the owner's opt-in, children never, no echo loops) and sends and receives them over LAN UDP multicast. Off by default and not wired into onemindd or the image yet.

Review fixes (#1260): CoT point and track numbers are written as plain decimals (never 1e-05 or 9.999999e+06, which the schema's xs:decimal forbids); Validate refuses NaN, infinite and out-of-range track course and speed; NewSender refuses a multicast TTL outside 0..1 (ErrTTL) so packets stay on the LAN; unknown detail elements are read but never re-emitted, and the testdata README and design doc now say so. Refs #1257, Refs #234.
