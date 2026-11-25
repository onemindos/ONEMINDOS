---
pr: pending
branch: claude/s2-secureboot-uki
---
#148, Secure Boot as a board option on x86_64-efi (off by default): `make image BOARD=x86_64-efi SECUREBOOT=1` builds the efi route with a signed UKI per slot (throwaway dev key); the GRUB image stays the default. Two new pre-registered QEMU tests under OVMF Secure Boot prove rollback: SB6 (the health gate rejects a bad slot B and the box returns to A) and SB7 (a slot B that panics gets one try, then A). `os/secureboot/README.md` now holds the TPM policy for /data (PCR 7 moves with Secure Boot state), what the founder key ceremony must hand over, and the switch-over steps. Dev keys only.
