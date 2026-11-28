---
pr: pending
branch: claude/ci-hosted-jobs-to-kvm
---
Eighteen more PR, push and merge-queue jobs that ran on GitHub-hosted `ubuntu-24.04` now run on the single-use `onemind-kvm` runners for trusted events (same expression as the image jobs; fork PRs and a switched-off `KVM_RUNNER` stay hosted), so they stop queuing behind the free plan's hosted-job cap: the Mosquitto bridge, the RAUC x86 build, the core PostgreSQL shards and image build, deploy lint, compose and systemd e2e, the CLI packages, the onemindd Go job, the image scope and data-encryption jobs, the apps plan, the golden path, Go fuzzing, the reproducible build, the 2-VM and restore drills, and the XR emulator suite. Jobs that need a tool GitHub's image preinstalls (shellcheck, the compose plugin, psql, ruby, file) install it first on self-hosted runners only. The KVM runner policy test lists every moved job.
