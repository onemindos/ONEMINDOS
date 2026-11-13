---
pr: 78
branch: feat/deploy-port27
---
The good parts of PR #27 on the deploy kit (PR #27 itself stays open for Zeus): an offline bundle (deploy/bundle.sh, with restic and NATS, and install.sh --bundle checked against SHA256SUMS, k3s airgap images); install.sh --dry-run and --target debian13, rpi5, jetson or do (Pi 5 memory cgroup, DigitalOcean firewall reminder); an agent API token stored as a hash only and a check that no raw token is on disk; node-check.sh and natscheck.py for the NATS auth; verify.sh tests against a mock hub (15 broken hubs, the eval-injection case) and a systemd end-to-end test as a CI job; simulated Raspberry Pi 5 and Jetson machines in compose. Merged with main so the backup setup, the shared PostgreSQL and the Secrets-rewrite retry all stay in.
