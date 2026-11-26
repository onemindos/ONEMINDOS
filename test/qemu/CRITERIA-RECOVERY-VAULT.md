# QEMU spike, personal vault mechanism: pass/fail criteria (pre-registered)

**Status:** PRE-REGISTERED. Written 2026-11-25 before `test/qemu/vaultspike/` was run anywhere. Its sha256 at that moment is in `PREREGISTRATION.sha256`. Nothing here may change afterwards except typo fixes; any other change is a new, dated section at the end. Results never live here (they go to the spike's `results.json` and to the design note `docs/learning/personal-vault-spike.md`).

**Serves:** gateway permissions design PR 25g (spike, no product code): how Advanced protection (D-028) locks an owner's personal files so the box cannot open them alone, on the shipping base (D-007, Debian 13, kernel 6.12) with `/data` on btrfs (#152, D-020). Decision question N-10 (a: a personal vault layer). Harness: `test/qemu/vaultspike/run.sh`.

## 1. Starting state and rules

- A QEMU/KVM guest booted from the **Debian 13 (trixie) `linux-image-amd64` kernel** with a minimal Debian 13 root (debootstrap) holding `btrfs-progs`, `cryptsetup`, `fscrypt`, `e2fsprogs`, `restic` and `xxd`. Two virtio disks: the root, and a blank 4 GiB disk formatted btrfs and mounted at `/data` (the stand-in for the box's `/data`).
- Prefix **RC** (recovery checks). The guest runs every check itself (as root) and prints one `RESULT <id> PASS|FAIL|BLOCKED|MEASURED <detail>` line per check; the host collects them into `results.json`.
- "Marker" means a file of 64 random bytes written inside the vault; its hex appears in no command line or log.
- "Vault key" is 64 random bytes in a key file on tmpfs (`/run`), never on `/data`.
- `--naive` runs the same checks with a plain directory as the "vault" (no encryption). It exists to show the checks can fail: in `--naive` mode RC2, RC3 and RC5 must FAIL. A check that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS.

## 2. Checks

| ID | Check | PASS if | FAIL if |
|---|---|---|---|
| RC0 | The guest kernel is the Debian 13 kernel | `uname -r` starts with `6.12.` and `/data` is btrfs | another kernel, or `/data` not btrfs |
| RC1 | fscrypt directly on btrfs `/data` (probe) | MEASURED: the outcome of `fscrypt setup` plus `fscrypt encrypt` on a directory of the btrfs `/data` is recorded (supported, or the kernel's refusal) | never FAIL; recorded either way |
| RC2 | A per-owner LUKS2 vault file on btrfs | A 512 MiB file on `/data` with `chattr +C` (no copy-on-write), `cryptsetup luksFormat --type luks2` with the vault key, opened, ext4 inside, marker written, closed: the marker's hex is **absent** from the raw vault file, and reopening with the key reads the marker back unchanged | the marker's hex is found in the raw file, or the reopened marker differs |
| RC3 | Locked after a restart | After a guest reboot (second boot, same disks, no key on any disk): no `/dev/mapper` vault is active, the marker is not readable at any path, and opening with the vault key reads it back | the vault is open or the marker readable before the key is given |
| RC4 | More than one way in, and a wrong key fails | A second keyslot is added for a second 64-byte key ("recovery key"); each key alone opens the vault; a random wrong key is refused; `luksDump` shows two keyslots; no keyslot is ever removed by the check | a wrong key opens, a right key fails, or a keyslot was removed |
| RC5 | Ciphertext-only backup with restic | `restic backup` of the **closed** vault file; the marker's hex is absent from every file of the restic repository; after changing 1 MiB inside the vault and closing it, a second backup **adds less than 64 MiB** to the repository; `restic restore` of the second snapshot gives a vault file that opens with the vault key and holds the changed data | the marker found in the repository, the second backup adds 64 MiB or more, or the restored vault does not open |
| RC6 | fscrypt on ext4 (the other candidate) | MEASURED: an ext4 loop file with the `encrypt` feature on `/data`, a directory encrypted with `fscrypt` (raw key), marker written, key removed (`fscrypt lock`): whether the marker's name and content are unreadable, and the steps needed | never FAIL; recorded |
| RC7 | Throughput | MEASURED: sequential write and read of 256 MiB with `dd` (`conv=fsync`, caches dropped before reads) on plain btrfs `/data`, inside the LUKS2 vault file, and inside the fscrypt ext4 loop | never FAIL; recorded |

## 3. What this spike does not cover (reported, never claimed)

- The OneMind image itself (its own `/data` layout, RAUC, the gateway). The mechanism is tested on the same kernel and file system, not wired into the product (that is PR 25h).
- TPM 2.0 with a PIN (`systemd-cryptenroll --tpm2-with-pin`) and the TPM's dictionary-attack lockout figures, which are vendor-specific; WebAuthn PRF support per browser and phone. The design note records these as follow-ups with sources, labelled UNVERIFIED where nobody ran them.
- Performance on the reference hardware (Dell AIO, R530); the figures here are from a KVM guest.
