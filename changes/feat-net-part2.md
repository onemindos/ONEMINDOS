---
pr: 88
branch: feat/net-part2
---
2-VM network proof (CI): `test/net/two_vm.py` boots a hub and a node (Debian 13, QEMU/KVM) on a private network, installs the hub with `deploy/install.sh`, joins the node with an owner-approved ticket, and reports PASS, FAIL or BLOCKED per pre-registered criterion (`test/net/CRITERIA-2VM.md`): fabric status, mesh reachability, NATS leaf over TLS with per-node credentials (H-06), no plain HTTP on the LAN (H-05), and HTTPS through the app proxy with identity cookies stripped (H-34). New workflow `net-2vm.yml`.
