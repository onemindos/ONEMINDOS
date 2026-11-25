---
pr: pending
branch: claude/storage-reset-token
status_rows:
---
Makes the factory reset work on the new btrfs data layout (stacked on #975). A box with a TPM now gets the OneMind LUKS2 token (id 30) written at first boot, so the reset finds its encrypted data disk. A box without a TPM keeps plain btrfs, and the reset now accepts exactly that case (system disk, GPT name and btrfs label onemind-data), tells the owner the data is not encrypted, and clears the signatures and the first 16 MiB. A foreign disk is still never listed or wiped. The wipe also zeroes the head so first boot makes a fresh data disk. The storage plans and the STORAGE-ACT patch notes now describe the layout @ at /data, @storage at /data/storage and @storage/.snapshots, with set-default @.
