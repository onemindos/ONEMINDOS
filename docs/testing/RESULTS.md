<!-- SPDX-License-Identifier: Apache-2.0 -->
# Test results log

**Append-only.** One line per test run, newest at the bottom. Never edit or delete a line; a rerun gets a new line. Field meanings and how to redact logs: [README.md](README.md#3-record-the-result). The tests themselves: [TEST-REGISTER.md](TEST-REGISTER.md).

| Date (UTC) | TR | Commit | Tester | Environment | Outcome | Evidence |
|---|---|---|---|---|---|---|
| 2026-11-12 | TR-064 | f616293 | agent | GitHub ubuntu-24.04 (`ci-core` on PR #38) | pass | [run](https://github.com/onemindos/ONEMINDOS/actions/runs/43192364745); `main` after merge: [run](https://github.com/onemindos/ONEMINDOS/actions/runs/43192749943) |
| 2026-11-12 | TR-080, TR-081, TR-088 | a39b559 | agent | GitHub ubuntu-24.04 (`ci-apps` on PR #25: gate of all 9 apps with k3d smoke) | pass | [run](https://github.com/onemindos/ONEMINDOS/actions/runs/43181362650); smoke `pass` for uptime-kuma, ntfy and home-assistant and amd64 + arm64 for every image in `apps/*/scan.json` |
| 2026-11-14 | TR-287 | 8c6e7f5 | agent | GitHub ubuntu-24.04 (`api-fuzz` on `main`, manual run: Schemathesis 400 cases per operation as agent, owner and on /mcp, plus Hypothesis properties at 20x) | pass | [run](https://github.com/onemindos/ONEMINDOS/actions/runs/43568028350); the first full run was cancelled at the old 45-minute limit ([run](https://github.com/onemindos/ONEMINDOS/actions/runs/43558739985)), fixed in #120. Findings fixed earlier on PR #101 (5xx and schema mismatches, quota bound published as minimum/maximum) |
