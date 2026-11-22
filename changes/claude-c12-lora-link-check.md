---
pr: pending
branch: claude/c12-lora-link-check
---
LoRa link-check lab kit (#853) in test/lora/link-check/: a passive check of the ThinkNode-M2 flashed MeshCore Companion (USB) on the hub. It checks that the ch341 driver claims the radio's USB chip, that the radio gets a serial port, sends only the MeshCore APP_START, DEVICE_QUERY and GET_STATS reads (an allowlist encoder refuses every other command, so it cannot transmit or change frequency or power), reads the sent-packet count before, after and at 10 minutes idle, and saves the reply frames with the radio's key, name, location and PIN replaced as vectors for #855. README with the founder's flash and US preset steps, a RESULTS.md template, and unit tests against a simulated radio on a pseudo-terminal.
