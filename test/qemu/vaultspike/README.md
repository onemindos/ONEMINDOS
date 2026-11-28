<!-- SPDX-License-Identifier: Apache-2.0 -->
# Personal vault spike (gateway permissions design 25g): what locks an owner's files

**Question (N-10, D-028 "Advanced protection").** When an owner turns on Advanced protection, their personal files must sit behind keys the box cannot open alone, while the disk itself still unlocks by itself at power-on (D-020). Which mechanism does that on the shipping base, Debian 13 (D-007) with `/data` on btrfs (#152)?

**Answer: a per-owner LUKS2 vault *file* on `/data`, created with `chattr +C` (no copy-on-write), with ext4 inside.** fscrypt is not an option on btrfs today: Debian 13's kernel refuses it (measured below). This is a spike: no product code. PR 25h builds the real thing.

## Plain words first

- **LUKS2** is Linux's standard disk-encryption format. Normally it wraps a whole partition (that is how `/data` is encrypted, D-020). It can also wrap a single big file, which then behaves like a small private disk: you "open" it with a key, use it, and "close" it.
- **A keyslot** is one copy of the vault's real key, locked by a different secret. LUKS2 has up to 32 of them. That is exactly the "key wrapping" the design needs: one slot for the owner's passkey (WebAuthn PRF), one for the Advanced recovery key, one for TPM plus PIN, one per recovery contact. Losing one secret never loses the vault while another slot works.
- **fscrypt** is the kernel's per-folder encryption (what Android uses). It would be neater, because it encrypts folders in place, but it needs the file system to support it, and btrfs does not on this kernel.
- **nocow** (`chattr +C`) tells btrfs to overwrite the vault file in place instead of copying each changed block. Without it a big encrypted file fragments badly on btrfs.

## How it was tested

`run.sh` builds a minimal Debian 13 root with debootstrap and boots it twice under QEMU/KVM on the **Debian 13 kernel `6.12.117+deb13-amd64`**, with a blank 4 GiB disk formatted btrfs as `/data`. The vault and recovery keys are made on the host and reach the guest only through QEMU `fw_cfg`, so no key is ever on a disk. The pass/fail rules were written and hashed before the first run: [`../CRITERIA-RECOVERY-VAULT.md`](../CRITERIA-RECOVERY-VAULT.md) (RC0-RC7, with a dated amendment also made before any run).

```
test/qemu/vaultspike/run.sh <out-dir>            # the LUKS2 vault file
test/qemu/vaultspike/run.sh --naive <out-dir>    # a plain folder as the "vault": must fail RC2, RC3, RC5
```

Needs Docker and a writable `/dev/kvm` on a Linux host (the CI build machines have both); no root on the host.

## Results (2026-11-25 ET, KVM guest, 2 vCPU, 2 GiB)

| ID | Check | Vault file | `--naive` (plain folder) |
|---|---|---|---|
| RC0 | Debian 13 kernel, btrfs `/data` | PASS (6.12.117+deb13-amd64) | PASS |
| RC1 | fscrypt straight on btrfs | MEASURED: **refused** ("This kernel doesn't support encryption on btrfs filesystems") | same |
| RC2 | Vault file holds ciphertext only; reopens with the key | PASS (nocow set) | **FAIL**: marker found in plain `/data/vault` |
| RC3 | Locked after a restart | PASS: no mapping, marker unreadable, the key opens it | **FAIL**: marker readable with no key |
| RC4 | Two keyslots; each opens; a wrong key fails | PASS | **FAIL**: no keyslots |
| RC5 | Ciphertext-only restic backup; the kit's restic key reveals nothing; dedup | PASS: marker absent from the repository **and** from `restic dump` read with the kit key; a 1 MiB change inside a 512 MiB vault added **3 MiB** to the repository (2 MiB on the first run); the restored vault opens | **FAIL**: the kit's restic key reveals the marker |
| RC6 | fscrypt on an ext4 loop file (the other candidate) | MEASURED: works; locked names are scrambled, contents unreadable, marker absent from the raw file, but it needs its own ext4 file system on btrfs | same |
| RC7 | Throughput (256 MiB, `dd`, `conv=fsync`, caches dropped) | MEASURED: plain btrfs write 335 MB/s, read 1.7 GB/s; **LUKS2 vault file write 215 MB/s, read 932 MB/s**; fscrypt ext4 loop write 217 MB/s, read 762 MB/s | (vault n/a) |

**Honest record of the first run.** The first run reported RC4 as FAIL, but the cause was the harness: `cryptsetup` printed an Argon2 memory warning into the captured output, so the "y" checks compared the wrong text. The raw values in that run were correct (both keys opened, the wrong key did not, 2 keyslots). The harness was fixed to discard cryptsetup's own messages and run again; the table above is the second run. Both raw logs are in the PR description.

## Why the LUKS2 vault file, not fscrypt

1. **fscrypt does not work on btrfs on our kernel** (RC1). Using fscrypt would mean an ext4 loop file on btrfs anyway (RC6), which loses its one real advantage (encrypting folders in place on the same file system) and still leaves file sizes and counts visible.
2. **Keyslots are the key-wrap store.** The design's list (PRF passkey, Advanced recovery key, TPM plus PIN, one share per recovery contact) maps one-to-one onto LUKS2 keyslots and tokens, which `cryptsetup` and `systemd-cryptenroll` already manage. With fscrypt we would write our own wrapping format.
3. **Backups stay useful.** LUKS2 encrypts each 4 KiB sector on its own, so unchanged sectors keep the same ciphertext and restic's chunking deduplicates them: 2 to 3 MiB added for a 1 MiB change (RC5). And the printed kit's restic key opens the repository but not the vault (RC5), which is the promise in design §3.13.
4. **Speed is close enough.** Reads at about half of plain btrfs and writes at about two thirds in a small KVM guest (RC7). Home files (documents, photos) will not notice.

## What 25h must handle (found here)

- **Use a fast key-derivation setting for every slot.** In a 2 GiB guest `cryptsetup` warned that its default Argon2id memory cost was more than the guest had. None of our slots is a human-typed password: the vault key, the Advanced recovery key (256 bits) and PRF outputs are high-entropy, and TPM-plus-PIN is rate-limited by the TPM. So 25h should format with `--pbkdf pbkdf2 --pbkdf-force-iterations 1000` (or the Argon2 minimum) instead of the default, to unlock fast on small boards and never fail for memory.
- **nocow trade-off.** `chattr +C` turns off btrfs data checksums for the vault file. Corruption inside it is then caught only by ext4's metadata checksums and by restores, not by a btrfs scrub. Snapper snapshots of `/data` still work: a snapshot shares the file and btrfs copies a block once on the next write.
- **Size.** The vault file has a fixed size. Grow it online with `truncate`, `cryptsetup resize` and `resize2fs`; never shrink it in the product (shrinking is where data loss lives). Start it at a size the owner picks, with a quota warning.
- **Where.** One file per opting-in owner, for example `/data/onemind/vaults/<owner-id>.img`, opened to `/run/onemind/vault/<owner-id>` and bind-mounted under that person's Files home, Photos and Notes paths. The data-layout service creates the directory; the file system under `/data` is already encrypted by D-020, so the vault is a second, owner-held layer.

## Not covered (follow-ups, not claimed)

- **TPM 2.0 with a PIN** (`systemd-cryptenroll --tpm2-device=auto --tpm2-with-pin=yes` on the vault file) and the TPM's dictionary-attack lockout figures: not run here (no software TPM in this guest). The lockout numbers are vendor-specific (UNVERIFIED). The image already ships swtpm-based tests for `/data` (`make dataenc`); 25h should add an RC check there.
- **WebAuthn PRF** (the passkey extension that turns a passkey into a key-wrapping secret): defined in W3C WebAuthn Level 3 (`prf` extension, https://www.w3.org/TR/webauthn-3/). Which browsers, phones and password managers support it, per version, is UNVERIFIED here; 25h must check the platforms OneMind targets before relying on it for day-to-day unlocks.
- The OneMind image itself (RAUC, the gateway, the real `/data` layout): the mechanism is tested on the same kernel and file system, not wired in.
- Performance on the reference hardware (the Dell all-in-one, the R530).
