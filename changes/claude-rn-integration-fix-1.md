---
pr: 1304
branch: claude/rn-integration-fix-1
---
Integration fix after 13 UI PRs merged into release/next together (Refs #1232, #234): the CLI package compiles again (one `radiosCommands` in radios.go; `data_radios.go` keeps only `data`; the plugins `host-grants` helper is renamed `pluginHostGrantsCmd` so it no longer collides with the `grants host` helper), `TestDataGrantsAndRadios` follows the kept `radios confirm` behaviour, and 55 surface-parity exemptions whose screens and commands have now landed are deleted (with four empty groups).
