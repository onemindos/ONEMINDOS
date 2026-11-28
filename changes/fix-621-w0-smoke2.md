---
pr: 621
branch: fix-621/w0-smoke2
---
The QEMU first-boot test F10 no longer asks for the rescue console unit to be enabled in /etc. On the read-only image, first boot starts it at runtime on every boot (F0 requires that only onemind-firstboot is enabled), so F10 now checks that the console is not enabled yet running, then answers 401 and 200 with k3s stopped.
