---
pr: pending
branch: claude/s13-secure-boot-signed-uki
---
S-13, first slice of Secure Boot with a signed UKI: `assemble.py disk or image --sb-key/--sb-cert` builds one signed unified kernel image per slot (kernel, initrd and command line in one file) and boots slot A from it with no boot loader; the tools image gains ukify, the systemd stub, sbsigntool and virt-firmware. A new QEMU test (SB1 to SB4, pre-registered criteria) boots it under OVMF Secure Boot with throwaway keys and checks that a changed, wrongly signed or unsigned file is refused (GRUB cannot do this under Secure Boot without shim, which was tried and is written down). The signing ceremony and the follow-ups (UKI in the update bundle, verity root, TPM) are written down in `os/secureboot/README.md`. The normal image is unchanged.
