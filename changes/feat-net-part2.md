---
pr: 88
branch: feat/net-part2
---
2-VM network proof (CI): `test/net/two_vm.py` boots a hub and a node (Debian 13, QEMU/KVM) on a private network, installs the hub with `deploy/install.sh`, joins the node with an owner-approved ticket, and reports PASS, FAIL or BLOCKED per pre-registered criterion (`test/net/CRITERIA-2VM.md`): fabric status, mesh reachability, NATS leaf over TLS with per-node credentials (H-06), no plain HTTP on the LAN (H-05), and HTTPS through the app proxy with identity cookies stripped (H-34). New workflow `net-2vm.yml`.

Mesh, HTTPS and join (CORE-NET-11/12/13): `onemind fabric join|ticket|approve|status`, per-node NATS accounts, the box CA with HTTPS on :443 and :8443, app names, and the per-app reverse proxy. Security fixes in this PR: with HTTPS on, the gateway's plain-HTTP listener binds to loopback only (H-05); the proxy strips every `onemind_*` and `__Host-onemind_*` cookie before a request reaches an app and refuses apps' `Set-Cookie` for those names (H-34); `onemindd` supervises the NATS leaf from a persisted `leaf.Config` (reload on change, restart after repeated failed checks; CS2-06). The 2-VM job is strict on pull requests (BLOCKED fails).
