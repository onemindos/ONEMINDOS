---
pr: pending
branch: fix/318-firstboot-order
---
First-boot setup no longer waits for the data partition to grow, so it finishes before the health gate again. Waiting made the smoke F1 boot test fail on main after #318. The grow is online, so nothing needs to wait for it except k3s.
