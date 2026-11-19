---
pr: 359
branch: ci/gate-drafts-pass-fast
---
The merge gate no longer holds a CI runner on draft PRs. A draft cannot merge, and the only checks it runs (dco, hygiene, lint, unit) are required on their own, so its gate now passes at once instead of polling for hours while the shared runner pool was full. On 2026-11-18, 9 of about 13 GitHub-hosted runners were merge gates waiting, three of them on drafts. The gate asks GitHub whether the PR is a draft at that moment, so a re-run of an old draft gate or a late event cannot pass a PR that is now ready; ready PRs and merge-queue entries always wait for every workflow.
