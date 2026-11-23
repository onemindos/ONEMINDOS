---
pr: 915
branch: claude/e-runner-node
---
CI-10 leftover (Refs #299): ci-apps `validate` now sets up Node 22 with the same pinned `actions/setup-node` as ci-sdk and checks the major before the sdk/tools unit tests, so the offline-map JS regression tests (#126) have Node on the hosted and the local Debian runner alike. The local runner's worker VM also gets a pinned, checksum-verified Node 22 (`runner.pin`, `provision.sh`), since Debian 13 ships Node 20. Both ci-apps jobs now generate the Go SDK code (`.github/actions/sdk-gen`, langs: go) before building `cmd/onemind`, which has imported the uncommitted generated types since CI-16; without it `validate` failed at the plugin-validator build. No trigger, `runs-on` or protection change; no test skipped.
