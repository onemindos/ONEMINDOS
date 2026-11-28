---
pr: pending
branch: claude/fix-plugin-validate-test
---
`onemind plugin validate` (and every manifest check that uses the app schema) could reject a valid manifest with a false "does not match pattern" error, which made `TestPluginValidateRequiresBundleFiles` fail at random in CI (run 45729613811 rejected the service name `uptime-kuma`). The cause is a bug in regexp2 v1.11.0, which runs the schema patterns: its 100 ms match timeout uses a background clock that stops after a second of idle time, and the first match after it restarts got a deadline from the stale clock, so the clock's first tick expired it at once. regexp2 v1.11.5 fixes the clock. The dependency is bumped and a new test lets the clock stop and then matches across the restart; it fails three out of three times on v1.11.0 and passes on v1.11.5.
