---
pr: 1356
branch: claude/fix-1118-recovery-key-console
---
The disk recovery key made at first boot is no longer printed on a serial console, where a hypervisor or terminal-server log could keep a copy. It is drawn once on the screen's own terminals, goes to a serial console only when the first boot had the kernel word onemind.recovery_key=serial, never goes to /dev/console or the journal, and stays in RAM (/run/onemind/data-recovery-key, root only) for the recovery-kit step until the next restart. The console and journal now say only that a key was made. The QEMU battery reads the key from RAM and checks that the boot's serial output carries none (E1 and R2 amendments pre-registered first).
