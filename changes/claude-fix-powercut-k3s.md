---
pr: 1155
branch: claude/fix-powercut-k3s
---
A hub whose k3s state was damaged by a power cut repairs it, or asks the owner first (VM 501 test, bug 1, part 2 of 2: recovery, stacked on the durability PR). Before every k3s start, damaged k3s state (empty or torn certificates, tokens, node password or config) is moved aside under /data/onemind/k3s-recovery, never deleted, and k3s makes it again. The owner's data, the apps' volumes, the image store and the gateway database are not touched, and every repair is logged, shown on the console and recorded. If the owner's apps are in the cluster, or it was repaired three times in an hour, nothing moves: the box alerts, and the rescue console (port 7443) shows the state and offers Reset k3s state, which needs the owner token and a typed confirmation. New pre-registered QEMU criteria F14 (damaged state repaired, owner data intact) and F15 (owner's app present: no automatic repair, then the approved reset) run in make powercut. Refs #234.
