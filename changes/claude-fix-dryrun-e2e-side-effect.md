---
pr: pending
branch: claude/fix-dryrun-e2e-side-effect
---
The systemd end-to-end test no longer blames the installer's --dry-run for the hub's own token renewal. onemind-gateway-token.timer rewrites /etc/onemind/gateway.kubeconfig once at a random time 1 to 6 minutes after boot, which is when the test measures the dry run, so a renewal landing in that window failed the check "--dry-run changed no file" (ci-deploy run 45746568282 on landing/2026-11-25). The test now holds that timer while it hashes every file before and after the dry run, starts it again afterwards, and prints the files that changed if the check ever fails. The dry run itself writes nothing (rerun on a build machine, identical hashes).
