<!-- SPDX-License-Identifier: Apache-2.0 -->
# App intake queue

One file per app (contract §9.1, `sdk/contracts/poc-v0.md`), named `<owner>--<repo>.yaml` after the upstream GitHub repo, in lower case. One file each means two PRs that add or move different apps never edit the same file (CI-06, issue 231). It replaced the single `queue.yaml` list.

```yaml
# SPDX-License-Identifier: Apache-2.0
name: Uptime Kuma
github: louislam/uptime-kuma
priority: 2          # optional
status: queued       # queued | in-pr | verified | blocked: <reason> | skipped: <reason>
notes: market batch 7  # optional
```

Only `name` and `github` are required. `sdk/tools/app-scaffold owner/repo` reads the entry and sets `status: queued` to `in-pr`; the PR that adds the app sets the final status.
