---
pr: 965
branch: claude/e-virtual-fleet
---
Virtual fleet test (#864): `test/fleet/fleet.py` makes one hub and three node VMs from a release's vm-do image on the Proxmox lab (VM ids 500-509 only, a three-VM memory budget, an 8 GiB host floor, lab addresses from the environment), joins each node with a QR v2 code through `onemind fabric join`, and checks the Nodes list, the bus, the dashboard, app placement, failover, a staged update and a forced-bad rollback. It writes a plain report and counts green runs in a row; `--broken-node-image` proves the join check can fail. The judge and guards are unit-tested in `test/unit/test_virtual_fleet.py`.
