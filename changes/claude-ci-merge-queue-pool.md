---
pr: pending
branch: claude/ci-merge-queue-pool
---
CI: a dedicated runner pool for merge-queue runs. Every job that can use the `onemind-local` pool now tries `onemind-mq` first, only when the repo variable `MQ_RUNNER` is `on` and the event is `merge_group` (always trusted: it runs code already approved into the queue). With `MQ_RUNNER` unset, routing is unchanged. gate.yml and the image/battery jobs are untouched. The runner policy tests now check that every local-pool job can reach the mq pool on merge_group and that no pull_request run ever can; `scripts/ci-runner/README.md` lists the hosted-image tools a pool runner needs.
