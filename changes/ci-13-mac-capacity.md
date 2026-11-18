---
pr: pending
branch: ci/13-mac-capacity
---
CI-13: the founder's Mac now carries every CI job it can, so GitHub's runners only do the x86, KVM and Docker work. A new small gate pool (one 2-CPU, 3 GB Lima VM running 6 ephemeral runner processes, label onemind-gate) takes merge-gate, which only polls the GitHub API and used to hold most hosted slots. The worker pool grows to up to 3 fresh-clone VMs (3 CPU and 7 GB each on a 12-core, 32 GB Mac) and also takes ci changes and dco, hygiene, the ci-core plan and its 3 SQLite shards (now a job of their own, without service containers), ci-mobile typecheck and jest, e2e-unit, brand, the ui-quality build and the site build. Every moved job keeps the LOCAL_RUNNER switch, never runs a fork PR and falls back to ubuntu-24.04; a policy test keeps x86, KVM, Docker, secret and write jobs off the Mac and keeps merge-gate always reporting. Switch-on steps are in docs/learning/self-hosted-runner.md.
