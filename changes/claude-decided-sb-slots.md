---
pr: pending
branch: claude/decided-sb-slots
---
Secure Boot slice 1 of #148: under Secure Boot both slots now boot their own signed UKI. A `--boot efi` image switches slots with RAUC's efi backend (firmware boot entries A and B, BootNext for the one trial boot of an update, BootOrder for committed slots), creates those entries on first boot before the health gate, and the gate reads slot state from firmware variables with its trial logic unchanged. The update bundle now carries the release's signed UKIs and RAUC writes them to the target slot's boot partition with its root. New QEMU test SB5 (pre-registered) installs such a bundle under OVMF Secure Boot with throwaway keys and checks slot B boots its own UKI and is committed. Rollback under Secure Boot (#881), anti-downgrade and sovereign mode are later PRs.
