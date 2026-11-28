# QEMU battery, encrypted data: pass/fail criteria (pre-registered)

**Status:** PRE-REGISTERED. Written 2026-11-21 before `os/rootfs/layers/base/usr/lib/onemind/data_encrypt.py` was booted anywhere. Its sha256 at that moment is in `PREREGISTRATION.sha256`. Nothing here may change afterwards except typo fixes; any other change is a new, dated section at the end. Results never live here (they go to the harness's `results.json` and CI logs).

**Serves:** IMG-LUKS-01 (LUKS2 on `/data`, TPM2 unlock, recovery key), H-11, SB-5, finding F-04, `docs/leap/core/SECURITY.md` §3.6; unblocks the factory-reset PR #549, which refuses to wipe a `/data` that is not LUKS2. Harness: `test/qemu/dataenc.py` (`make dataenc`).

## 1. Starting state and rules

- Image: `make fixtures DATA_FS=luks2`. The `onemind-data` partition is **blank** (all zero, no signature). Boot slot A, version 1, the test overlay (serial shell).
- A software TPM 2.0 (swtpm) is attached to the VM unless the test says "no TPM". "TPM #1" and "TPM #2" are two swtpm instances with separate state, so TPM #2 does not know any key that TPM #1 sealed. Booting with TPM #2 is how a disk that moved to another machine looks.
- "Marker" means a file `/data/onemind/e-marker` of 32 random bytes written in E1; "marker kept" means its sha256 is unchanged.
- No human input except what a test sends on the serial console (the recovery key, a wrong key). A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS.

## 2. Tests

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| E1 | First boot, blank data, TPM #1 | The console prints `ONEMIND-DATA-CRYPT: RECOVERY KEY` with a key of eight groups of eight modhex letters; the gate commits slot A; `/data` is mounted from `/dev/mapper/onemind-data`; the raw partition's signature is `crypto_LUKS`; `cryptsetup luksDump` lists a `systemd-tpm2` token and a `systemd-recovery` token; `/run/onemind/data-recovery-key` exists with mode 600; the recovery key does not appear in the journal of this boot | Any item missing, the key in the journal, `/data` still on the plain partition, or the box not reaching the gate |
| E2 | Reboot, same disk, TPM #1 | With nobody typing: the console shows `data disk unlocked (tpm2)`, no passphrase prompt appears, the gate commits, and the marker is kept | A prompt, an unlock by any other means, a new recovery key, or the marker changed |
| E3 | Moved disk: same disk, TPM #2 | A passphrase prompt for `onemind-data` appears; sending the E1 recovery key unlocks it (`data disk unlocked (recovery-key)`), the box reaches the gate and the marker is kept | No prompt, the TPM #2 unlocking the disk, the recovery key refused, or the marker changed |
| E4 | No TPM, wrong key | A prompt appears; three wrong keys end with `the data disk is locked`; the box enters recovery mode (`ONEMIND-RECOVERY: entered ...`); `/data` is not mounted and the raw partition is still `crypto_LUKS` (nothing was formatted) | `/data` mounted, the partition re-formatted or its signature changed, or no recovery mode |

## 3. What these tests do not cover (reported, never claimed)

- Real TPM hardware, a Secure Boot chain, and firmware updates that change PCR 7. PCR 7 alone is a weak binding without Secure Boot; the recovery key is the strong fallback.
- Migration of boxes installed before this change (their `/data` is plain ext4 and is left untouched on purpose).
- Growing an encrypted `/data` to a bigger disk (`data_extend.py` skips it and says so), and boards other than `x86_64-efi`.
- Showing the recovery key in the first-run recovery-kit step (PR #551). Here the key is on the console and in RAM only.

## 4. Amendment 2026-11-28 (#1118): the recovery key never reaches a serial console by default

Written before the matching change to `data_encrypt.py` and `dataenc.py` was booted anywhere. Why: a serial console is often logged on another machine (a hypervisor serial log, a terminal server, QEMU `-serial file:`), so a key printed there can end up in a file other people read. The key is now shown on the screen's own terminals only (`tty0`, `tty1` ...), on a serial console only when the first boot had the kernel command line word `onemind.recovery_key=serial`, and it stays in `/run/onemind/data-recovery-key` (RAM, mode 600) for the recovery-kit step. The test VM boots without that word (the default).

- **E1, first PASS clause replaced.** Instead of "the console prints `ONEMIND-DATA-CRYPT: RECOVERY KEY` with a key of eight groups of eight modhex letters": the console prints `ONEMIND-DATA-CRYPT: recovery key made`; `/run/onemind/data-recovery-key` holds a key of eight groups of eight modhex letters; and the serial console output of this boot, from power-on until the gate commits (before the harness runs any shell command), contains neither that key nor a `RECOVERY KEY` line. All other E1 clauses stay.
- **E1 FAIL also if** the key or a `RECOVERY KEY` line appears on the serial console in that window.
- **E3** sends the key the harness read from `/run/onemind/data-recovery-key` in E1.
- Not covered: that the key is drawn on the screen (`tty0`); the battery captures the serial port only. The unit tests (`test/unit/test_data_encrypt.py`) check which terminals get the key.
