---
pr: pending
branch: claude/ci-hosted-jobs-to-kvm
---
Fifteen more PR, push and merge-queue jobs that ran on GitHub-hosted `ubuntu-24.04` now run on the `onemind-kvm` runners for trusted events (same expression as the image jobs; fork PRs and a switched-off `KVM_RUNNER` stay hosted), so they stop queuing behind the free plan's hosted-job cap: the Mosquitto bridge, the RAUC x86 build, the core PostgreSQL shards and image build, deploy lint, the systemd e2e, the CLI packages, the onemindd Go job, the image scope and data-encryption jobs, the apps plan, Go fuzzing, the reproducible build, and the 2-VM and restore drills. Jobs that need a tool GitHub's image preinstalls (shellcheck, the compose plugin, psql, ruby, file) install it first on self-hosted runners only. The KVM runner policy test lists every moved job.
The golden path and the XR emulator suite stay hosted because their harness starts an 8 GiB QEMU guest that the smaller hosts cannot run, and compose-e2e stays hosted because the droplets' Docker refuses two bake targets that export the same image tag.
