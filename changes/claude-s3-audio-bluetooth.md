---
pr: 1103
branch: claude/s3-audio-bluetooth
---
OS image: sound and Bluetooth on the boards with a screen (x86_64-efi, rpi5). Adds PipeWire (pipewire, pipewire-pulse, wireplumber, libspa-0.2-bluetooth) with an always-present virtual sink for the screen session and streamed apps, and BlueZ with the adapter off until the owner turns it on, no pairing without an agent, and discoverable and pairable windows that close after two minutes. Pairings live in /var/lib/bluetooth, a bind mount of /data/state/var-lib-bluetooth, so they survive a reboot and an A/B update. Cloud boards get none of it. New first-boot checks F16, F16r and F16u (pre-registered in CRITERIA-FIRSTBOOT.md section 10); real radio and sound output are proven on the Dell all-in-one.
