---
pr: pending
branch: claude/278-rescue-console-enable
---
The first-boot QEMU battery now checks the rescue console on the booted image hub (F10): the unit is enabled and running, and with k3s stopped the page on :7443 answers 401 without the owner token and 200 with it (the box CA certificate verifies by name). Install and image wiring for the console came earlier (#334); this closes the image half of the issue's "Done when". The criteria are pre-registered in CRITERIA-FIRSTBOOT.md section 6 with their hash.
