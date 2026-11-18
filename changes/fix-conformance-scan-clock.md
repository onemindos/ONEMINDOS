---
pr: pending
branch: fix/conformance-scan-clock
---
The SDK conformance tests start a real gateway on the real wall clock, but the shared test fixtures dated every app scan one day before a frozen 2026-11-11 clock, so from 2026-11-17 the 7-day scan rule rejected the installs and the Python SDK, CLI and MCP bridge conformance tests failed on every core PR. The conformance gateway now re-dates its scans relative to the real current time, and a new test guards that they are fresh. The 7-day rule itself is unchanged.
