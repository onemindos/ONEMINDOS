---
pr: pending
branch: ci/gate-drafts-pass-fast
---
The merge gate no longer holds a CI runner on draft PRs. A draft cannot merge, and the only checks it runs (dco, hygiene, lint, unit) are required on their own, so its gate now passes at once instead of polling for hours while the shared runner pool was full. On 2026-11-18, 9 of about 13 GitHub-hosted runners were merge gates waiting, three of them on drafts. Marking a PR ready still starts a gate that waits for every workflow, and the merge queue gates again.
