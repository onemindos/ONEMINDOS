---
pr: 266
branch: fix/nightly-battery
---
The nightly image battery can pass again. The bad-image test fixtures (T6 broken init, T7 hung init) write their marker to the kernel log, because the boot splash holds the console and swallowed it. BIOS GRUB (vm-do) now also writes to the serial port, so T9 sees its GRUB-RAUC line. The Ubuntu CI hedge builds again: the build stage configures apt for its own leg instead of always Debian (CI-01, issue 226).
