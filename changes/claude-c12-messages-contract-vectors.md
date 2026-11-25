---
pr: 929
branch: claude/c12-messages-contract-vectors
---
Shared MeshCore test vectors for the LoRa messenger (#855, part 2 of 2). frames.json holds MeshCore companion frames with their decoded fields and the opcode allowlist and deny list, so the Go codec in onemindd and the TypeScript codec on the phone decode and encode the same bytes and neither can ever encode a radio-settings, power, key, reboot or raw-data command. guard.json holds the send-guard cases both the hub and the phone guard must pass: the whole channel inside 902-928 MHz, power at or below the radio's FCC grant (the ThinkNode M2's 19 dBm, not its 22 dBm build default), UTF-8 byte caps, time on air from the Semtech formula, and the 60 s and 30 sends per hour budget with every retry counted. MeshCore's MIT notice is kept beside them. A licence test now fails if any package file, lockfile, Meshtastic proto or generated stub brings Meshtastic (GPL-3.0) into this Apache-2.0 repo.
