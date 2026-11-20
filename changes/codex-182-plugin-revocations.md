---
pr: pending
branch: codex/182-plugin-revocations
---
The plugin revocations command fetches a bounded, expiring list through a trusted TUF plugins delegation. Persistent metadata and list-version/hash floors refuse rollback or same-version replacement. Exact plugin/version/digest matching reports delist, disable, remove and per-tool revocations without granting installation approval or changing running workloads.
