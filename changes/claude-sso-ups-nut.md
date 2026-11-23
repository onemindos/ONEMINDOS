---
pr: pending
branch: claude/sso-ups-nut
---
UPS support in the image (IMG-06, part 1 of 2). A UPS plugged into the box by USB is found at boot with NUT's nut-scanner and watched by NUT's upsmon, with its config on the data disk and the Debian NUT units masked. When the power is out and the battery runs low, the box shuts down in order: the apps (each gets 30 seconds to save its work), then Kubernetes, then the data disk (journal moved off, synced, unmounted and the encrypted disk closed), then poweroff. A failing step never stops the poweroff. A box without a UPS skips the service quietly. Tested with NUT's dummy-ups driver going from on mains to on battery and low; pulling the mains on a real UPS stays a device proof for the founder.
