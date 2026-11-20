---
pr: pending
branch: ci/r530-kvm-runner
---
CI-14: an x86 KVM runner on a Proxmox VE host for the heaviest jobs (image x86 legs, smoke, battery, cloud, installer), which need x86 and KVM and so could not move to the Mac runner. scripts/ci-runner-kvm/ builds an Ubuntu 24.04 template (Docker, pinned x64 Actions runner, checksums checked) and runs one linked-clone VM per job as an ephemeral runner, destroyed afterwards, on its own NATed bridge that blocks every private range and the host. The host hands each VM a single-use JIT runner config through the guest agent (no SSH); a job-started hook in each VM refuses fork pull requests, and IPv6, spoofing and the host are blocked. Jobs pick it only when the KVM_RUNNER variable is on and the event is not a fork PR, else GitHub-hosted; the release-signing battery in security-nightly always stays hosted. test/unit/test_kvm_runner_policy.py enforces the routing, no secrets, and the kit's isolation.
