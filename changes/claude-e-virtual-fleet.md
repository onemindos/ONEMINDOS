---
pr: 965
branch: claude/e-virtual-fleet
---
Virtual fleet test (#864): `test/fleet/fleet.py` makes one hub and three node VMs from a release's vm-do image on the Proxmox lab (VM ids 500-509 only, a three-VM memory budget, an 8 GiB host floor, lab addresses from the environment), joins each node with the hub's QR code (v2, else v1) through the image's own enrolment flow (`onemind fabric join`), and checks the Nodes list, the bus, the dashboard, app placement, failover (where the placed app's work goes when its node stops), a staged update and a forced-bad rollback. It writes a plain report and counts green runs in a row; `--broken-node-image` gives node 1 a broken `onemind` CLI so the join check itself must refuse it. The judge and guards are unit-tested in `test/unit/test_virtual_fleet.py`. Not green yet: #943 (one machine-id per image), #391 in the dev releases, and no k3s agent on workers.
