---
pr: pending
branch: claude/p0-host-firewall-nftables
---
Host firewall: the box now drops everything that arrives unless it is on the list. `onemind-firewall.service` loads `host.nft` (nftables, default-deny input) before the network comes up. From the LAN only: HTTPS 443 and 8443, Headscale join 8444, rescue console 7443, mDNS, STUN and the mesh port 41641. The k3s API 6443, kubelet 10250, flannel 8472 and NATS leaf 7422 answer on loopback, the mesh and the pod network only. A port scan from a second network namespace (`test/net/host_firewall_scan.py`) proves a LAN client sees exactly those ports and a public client sees none. Optional services add rules in `/etc/onemind/host.local.nft`.
