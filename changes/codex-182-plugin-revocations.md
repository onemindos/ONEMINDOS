---
pr: 427
branch: codex/182-plugin-revocations
---
The plugin revocations command fetches a bounded, expiring list through a trusted TUF plugins delegation. Persistent metadata and list-version/hash floors refuse rollback or same-version replacement. Exact plugin/version/digest matching reports delist, disable, remove and per-tool revocations without granting installation approval or changing running workloads.
Retargeted onto the folded #451 stack. Root rotation can no longer be rolled back: each run starts from the cached TUF root, with the operator root only bootstrapping. Prerelease versions now match version-range revocations.
