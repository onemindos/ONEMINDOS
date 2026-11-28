---
pr: 1352
branch: claude/atlas-boot-splash
---
The boot splash now follows the Atlas boot screen (design-v2 screen 12, #763): the colour mark on black (the existing on-dark logo file, unchanged), the "OneMind OS" wordmark, a thin progress bar in the button red, up to three boot steps (data disk opened, /data prepared, data disk checked, starting OneMind) taken from the units systemd reports to Plymouth, and a footer saying a failed update rolls back by itself. It also draws the data disk's recovery-key or password prompt, which the old splash did not. Everything is generated from brand/brand.json by scripts/brand-sync.py; the logo red stays reserved for the logo files.
