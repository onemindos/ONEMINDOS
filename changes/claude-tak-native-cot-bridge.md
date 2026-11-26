---
pr: pending
branch: claude/tak-native-cot-bridge
---
TAK native, first slice (D-032). Adds the CoT bridge design (docs/architecture/TAK-NATIVE-COT-BRIDGE.md, with primary sources), a plain-language founder note, the D-032 decision entry, and internal/cot, a Go package that encodes, decodes and validates Cursor on Target XML events, maps OneMind positions to CoT and back (people only with the owner's opt-in, children never, no echo loops) and sends and receives them over LAN UDP multicast. Off by default and not wired into onemindd or the image yet.
