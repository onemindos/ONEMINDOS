---
pr: pending
branch: claude/p0-grub-menu-lock
---
The GRUB boot menu is locked: editing a kernel command line or opening the GRUB shell now asks for a login, so someone at the keyboard can no longer add init=/bin/sh and get a root shell. The Slot A, Slot B and fallback entries stay unrestricted, so a normal or unattended boot needs no password. Each box makes its own password at first boot (shown once on the console, only its PBKDF2 hash stored on the boot partition), and a new QEMU test (B1 to B6) plays the attacker at the menu.
