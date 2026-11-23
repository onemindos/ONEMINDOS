---
pr: 964
branch: claude/roots-device-card-go
---
Device capability card contract, part 2 (Refs #727): the Go validator in sdk/schema (ValidateDeviceCard, DeviceCardClassRisk, HoldRequired) applies the same rules as the Python one of part 1, by the same names and over the same failing fixtures, with the class-to-risk table read from the schema so the two cannot disagree. `onemind plugin card validate FILE...` checks cards offline (with --json for machines) and exits non-zero on any refused rule.
