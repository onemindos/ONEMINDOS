---
pr: pending
branch: ci/local-runner
---
CI-10: an ephemeral self-hosted runner in a Lima Debian 13 arm64 VM on the founder's Mac. scripts/ci-runner/ has up, down, status, the job loop and a launchd agent; lint, unit, ci-sdk, ci-ui, ci-dashboard and the ci-apps validate job pick it only when LOCAL_RUNNER is on and the event is not a fork PR, else GitHub-hosted. A unit test fails the build if a job that can pick the local runner reads a secret. Founder steps are in docs/learning/self-hosted-runner.md.
