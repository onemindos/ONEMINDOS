---
pr: pending
branch: claude/p0-luks2-data-tpm2
---
First slice of LUKS2 on `/data` with TPM2 unlock and a recovery key (finding F-04, H-11, SB-5; unblocks factory reset). A layout whose data partition says `fs: luks2` (or an image built with `assemble.py disk --data-fs luks2`) ships that partition blank; `onemind-data-encrypt.service` makes a LUKS2 volume on the box's first boot with a key that only exists in RAM, adds a recovery key (printed once on the console, left in RAM for the recovery-kit step) and a TPM2 key bound to PCR 7 when a TPM is present, and unlocks it on every later boot, asking for the recovery key on the console when the TPM is missing or does not match (a moved disk). Boxes whose `/data` is plain ext4 are never touched. The shipped x86 layout is still ext4: the default flips after the new QEMU battery E1-E4 (software TPM, `test/qemu/CRITERIA-DATAENC.md`, `make dataenc`, manual dispatch of the image workflow) passes for the first time.
