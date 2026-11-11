# Lab spike LAB-secureboot-1152: Secure Boot + RAUC A/B re-run on RAUC 1.15.2 (critic N8)

**Status:** PRE-REGISTERED. Goal, hypotheses, design and pass/fail criteria (sections 1–5) were written 2026-11-11 12:11 UTC, before any build or test of this spike ran. The sha256 of this file at that moment is in `../PREREGISTRATION.md`. Results are added only below the line "Results"; nothing above it changes afterwards except this status line, and any other change is logged in the deviations section.

> **Explain it like I'm the founder.** We already showed (spike `../secureboot-rauc/`) that our A/B update design works with Secure Boot switched on and our own keys. But that test used Debian's older RAUC 1.13, and the decision document asks for RAUC 1.15.2 with "verity-only" update files. Between 1.13 and 1.15.2, RAUC changed **how it works out which copy of the OS is running**: it now also asks the PC firmware ("which boot entry did you just start?") instead of only reading the kernel's command line. That is exactly the part Secure Boot touches. So we re-run the same "break it on purpose" tests on 1.15.2, add the verity-only rule, and write down anything that behaves differently.

## 1. Goal

Re-run the X-2R suite of `../secureboot-rauc/` (T0–T7 and the E1 factory-fallback probe) with **RAUC v1.15.2 built from the pinned upstream tag** (commit `4fb7c798d6ae412344fb8f8d310d773046af3441`, the build method of `../rauc-1152/`) instead of Debian's `rauc 1.13-3+deb13u1`, and with `bundle-formats=verity` on the device. Setup as before: QEMU q35 + OVMF Secure Boot build with **custom lab PK/KEK/db enrolled** (no Microsoft keys), **one signed UKI per slot** booted by RAUC's `efi` backend, **verity bundles**, health-gated **rollback**, LUKS2 data sealed to an emulated TPM 2.0. Record every behaviour change from the 1.13 run.

## 2. Hypotheses

- **H1 (drop-in).** RAUC 1.15.2 replaces the Debian package in the image with no change to the gate, the units, the UKIs or `system.conf` other than adding `bundle-formats=verity`.
- **H2 (same outcomes).** Every T0–T7 outcome of `../secureboot-rauc/` repeats on 1.15.2: BootNext set to the new slot on install, `mark-good` puts the slot first in BootOrder, `mark-bad` removes it, a tampered or unsigned UKI is refused by the firmware and the same power-on falls through to the committed slot.
- **H3 (slot detection).** 1.15 added EFI `BootCurrent`-based booted-slot detection (PR 1696) and put the backend's answer above `root=` (PR 1712), but an explicit `rauc.slot=` on the command line is still checked first (`rauc@4fb7c79:src/context.c#L69-L91`, `get_bootname()`). Because our signed UKIs carry `rauc.slot=`, 1.15.2 reports the same booted slot as 1.13 in every test, **including E1** (the factory loader, booted through a firmware auto-entry, still identifies as slot A). The E1 downgrade gap therefore **persists** on 1.15.2.
- **H4 (BootCurrent path works).** With `rauc.slot=` removed from the command line RAUC sees (bind-mounted copy of `/proc/cmdline`), 1.15.2 still reports the correct booted slot on a normal boot, now from `BootCurrent`; when the boot came through a firmware auto-entry (E1 state), it cannot match `BootCurrent` to a slot and falls back to `root=`.
- **H5 (verity-only).** A validly signed **plain** bundle is refused on the device with a bundle-format error, before any slot is written: BootNext is not set and BootOrder is unchanged.

## 3. Design (fixed before the run)

- **Unchanged from `../secureboot-rauc/scripts/`:** disk layout (01 §4.3), keys and enrolment (`virt-fw-vars`), UKIs (`ukify` + `sbsign`, both per-slot UKIs in each `boot` vfat image), first-boot EFI entries, LUKS2 + TPM2 (PCR 7; signed PCR 11 bonus container), health gate, the bundle set (`good` v2, `bad-health` v3, `tampered` v4, `unsigned` v5), the test driver logic and E1.
- **Changed:** (a) RAUC 1.15.2 is built by `scripts/build-rauc.sh` (the `../rauc-1152/` script without its T12 section): arm64 natively in the Lima VM (used to create bundles), amd64 in an `mmdebstrap` build chroot via qemu-user, installed into the image with `--destdir`; the image gets RAUC's runtime libraries from Debian but **not** Debian's `rauc` / `rauc-service`. (b) `system.conf` adds `bundle-formats=verity`. (c) One extra bundle, `plain-good` (v2, `format=plain`, signed by the same lab signer). (d) The driver adds T8 (plain refused) right after T1, T9 (slot-detection probe) after T2, records `rauc --version` on the guest, and runs E1 as a pre-registered test at the end (in the 1.13 spike it was exploratory).
- **Environment:** disposable Debian 13 arm64 Lima VM (`vz`), only the lab work folder mounted; x86_64 guest under QEMU TCG with no network device; VM deleted at the end.

## 4. Pass / fail criteria (frozen before the run)

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| T0 | Build | Scripts run unattended; checked-out `HEAD` = `4fb7c798…`; `rauc --version` prints 1.15.2 for arm64 and amd64; Debian `rauc` package absent from the image; `sbverify --cert db.crt` OK for v1–v3 UKIs and fails for v4 (tampered) and v5 (unsigned); 4 verity bundles + 1 plain bundle verify against the lab CA | Any manual step, wrong commit, Debian RAUC in the image, or the signature split differs |
| T1 | First boot under SB | As in `../secureboot-rauc/` T1 (`SecureBoot=1 SetupMode=0`, kernel SB on, lab PK, LUKS2 with `systemd-tpm2` token unlocked with no prompt, gate `mark-good slot=A version=1`), **plus** guest `rauc --version` = 1.15.2 | Any missing, or another RAUC version on the guest |
| T8 | Verity-only policy | `rauc install plain-good.raucb` fails with a bundle-format error; BootNext absent and BootOrder identical before and after | Installs, starts writing, or changes BootNext/BootOrder |
| T2 | Good update A→B | As in the 1.13 spike T2 | As there |
| T9 | Slot-detection probe (H4) | Informational; recorded, does not affect the verdict | n/a |
| T3 | Health-gated rollback | As in the 1.13 spike T3 | As there |
| T4 | Tampered UKI refused | As in the 1.13 spike T4 | As there |
| T5 | Unsigned UKI refused | As in the 1.13 spike T5 | As there |
| T6 | TPM fails closed with SB off | As in the 1.13 spike T6 | As there |
| T7 (bonus) | Signed PCR 11 policy | As in the 1.13 spike T7; does not affect the verdict | |
| E1 | Factory-fallback probe | Recorded; **expected** (H3) to repeat the 1.13 gap (v1 kernel boots on newer root, data unlocks, gate commits slot A). Does not affect the verdict | n/a |

**Spike verdict:** PASS if T0–T6 and T8 pass in at least one full run. A second full run is the target and is reported either way. Behaviour changes from 1.13 are listed whatever the verdict. A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS. A permission denial is recorded and not worked around; the rest becomes a founder-runnable test.

## 5. Requirement IDs served

M-2 (security baseline), R-1 (safe updates), R-3 (maintainability), U-4 (data safety), P-7 (bring-your-own x86), F-14. Feeds REC-DEC-08 / DC-18 and the RAUC version floor in `01-…` §4.2; closes critic N8 (Secure Boot on the recommended RAUC).

## 6. Glossary

| Term | Meaning |
|---|---|
| `BootCurrent` | EFI variable the firmware sets to the boot entry it actually started this time |
| `rauc.slot=` | Kernel command-line word that tells RAUC which slot is running; inside a signed UKI it cannot be changed without breaking the signature |
| Verity-only (`bundle-formats=verity`) | Device setting: refuse any update file not in RAUC's block-by-block-checked verity format |
| Firmware auto-entry | A boot entry the firmware creates by itself (e.g. "UEFI Misc Device") for a disk's removable-media path `\EFI\BOOT\BOOTX64.EFI` |
| Other terms | See `../secureboot-rauc/` §6 and `../rauc-1152/` §6 |

---

## Results

**Verdict: PASS (2 of 2 full runs).** T0–T6 and T8 passed in run 1 (1540 s, 2026-11-11 12:34–13:00 UTC) and run 2 (1323 s, 13:03–13:25 UTC) on one build. Bonus T7 passed in both. E1 was run on the end state of each run and gave the same result both times. **No behaviour change from 1.13 was seen in install, commit, rollback or firmware refusal.** The one new behaviour is internal: when `rauc.slot=` is missing, RAUC now finds the running slot from the firmware's `BootCurrent` (T9). It makes no difference with our signed UKIs, which always carry `rauc.slot=`. **The E1 downgrade gap persists on 1.15.2** (H3 confirmed). Claims: [C-LAB-secureboot-1152-001…011].

> **Explain the result like I'm the founder.** The exact combination the decision document asks for now works under Secure Boot: RAUC 1.15.2, verity-only update files, our own firmware keys, and one signed kernel per slot. Every test from the 1.13 run gave the same answer. Good updates stick, bad ones roll back by themselves, and the firmware refuses a tampered or unsigned kernel and quietly boots the good copy. The encrypted data unlocks only while Secure Boot is on. An old-format update file is now refused before anything is written. The surprise from the first spike is still there: if the firmware ever falls back to the factory kernel in the boot partition, that old but properly signed kernel runs. Upgrading RAUC does not fix this, because it is about which kernels the firmware will start, not about RAUC. The fixes SB-3 and SB-4 from the earlier spike are still needed.

### R.1 Test results

| ID | Run 1 | Run 2 | Evidence (run 1 unless noted) |
|---|---|---|---|
| T0 | **PASS** | (same build) | `logs/build-rauc.log`: `HEAD=4fb7c798…`, `rauc v1.15.2` (arm64), `rauc 1.15.2` (amd64). `logs/build.log`: `image rauc: rauc 1.15.2`, `Debian rauc package: not installed (expected)`, `SecureBootEnable: ON`; v1–v3 UKIs `Signature verification OK`, v4/v5 `failed`; 4 bundles `Verified inline signature … Bundle Format: verity`, `plain-good` `Verified detached signature … Bundle Format: plain` [C-LAB-secureboot-1152-001, -004] |
| T1 | **PASS** | **PASS** | All 1.13 checks plus `guest rauc 1.15.2`; first boot 181 s (run 2: 98 s; 1.13 run: 75 s) |
| T8 | **PASS** | **PASS** | `LastError: Bundle format 'plain' not allowed`, rc=1; `BootOrder: 0003,0004` before and after, no `BootNext` [C-LAB-secureboot-1152-007] |
| T2 | **PASS** | **PASS** | `BootNext=OneMind-B`, gate `mark-good/B/v2`, `BootOrder[0]=OneMind-B`, second reboot `mark-good/B/v2` |
| T9 (info) | recorded | recorded | `rauc.slot=` hidden (`PROBE-CMDLINE: root=PARTUUID=…5b`): `Booted from: rootfs.1 (OneMind-B)`, `BootCurrent: 0004`, no detection error [C-LAB-secureboot-1152-008] |
| T3 | **PASS** | **PASS** | `BootNext=OneMind-A`, gate1 `mark-bad A v3`, gate2 `mark-good B v2`, 2 TPM unlocks, `BootOrder[0]=OneMind-B` |
| T4 | **PASS** | **PASS** | `BdsDxe: failed to load Boot0003 "OneMind-A" … \EFI\Linux\onemind-A.efi: Access Denied`, no v4 kernel ran, gate `mark-good B v2` |
| T5 | **PASS** | **PASS** | Same as T4 for the unsigned v5 UKI |
| T6 | **PASS** | **PASS** | `DATA: UNLOCK FAILED (tpm2 unseal refused): Password querying disabled via 'headless' option.`, gate `no-commit B v2`; T6b (SB back on) `mark-good`, unlock OK |
| T7 (bonus) | **PASS** | **PASS** | `BONUS-PCR11: UNLOCK OK` on A, B, the bad A v3 and B after rollback [C-LAB-secureboot-1152-005] |
| E1 | gap repeats | gap repeats | `kernel(UKI) version=1 rootfs version=5 SecureBoot=enabled data=UNLOCKED gate=('mark-good', 'A', 5)`; `BootCurrent: 0001`, `BootOrder: 0003,0004,0000,0001,0002` (`logs/driver-e1.log`, `driver-e1-run2.log`) [C-LAB-secureboot-1152-009] |
| E1 probe | recorded | recorded | `rauc.slot=` hidden: `Failed to get bootname: efi backend: Current EFI bootentry not known to rauc!`, then `Booted from: rootfs.0 (/dev/vda4)` (fallback to `root=`) |

### R.2 Hypotheses

| | Verdict | Why |
|---|---|---|
| H1 drop-in | **Confirmed** | Image changed only in RAUC binaries and `bundle-formats=verity`; gate, units, UKIs and slot config unchanged (`scripts/build.sh` vs `../secureboot-rauc/scripts/build.sh`) |
| H2 same outcomes | **Confirmed** | Every T1–T7 verdict repeated in 2 runs. The BootNext/BootOrder sequence matches the 1.13 console logs step for step [C-LAB-secureboot-1152-006] |
| H3 slot detection, E1 persists | **Confirmed** | `rauc.slot=` is checked before the backend in 1.15.2 [C-LAB-secureboot-1152-003]; E1 shows `Booted from: rootfs.0 (OneMind-A)` and the same commit as on 1.13 |
| H4 BootCurrent path | **Confirmed** | The label tells the paths apart: the backend path names the slot by bootname (`(OneMind-B)`), while the `root=` fallback names the device (`(/dev/vda4)`) and logs the efi backend error |
| H5 verity-only | **Confirmed** | T8 |

### R.3 Behaviour changes from 1.13 (the N8 question)

| Area | 1.13 (Debian) | 1.15.2 (this lab) | Matters for OneMind? |
|---|---|---|---|
| Install, BootNext, mark-good/-bad, rollback, firmware refusal | as `../secureboot-rauc/` | **identical** | No change |
| Booted-slot detection without `rauc.slot=` | `root=` only | `BootCurrent` first, then `root=` [C-LAB-secureboot-1152-003, -008] | Not with our UKIs (they carry `rauc.slot=`). It would matter for a UKI without `rauc.slot=`: booting through a firmware auto-entry then makes RAUC log an efi-backend error and fall back to `root=`. **Keep `rauc.slot=` in the signed command line.** |
| Plain bundles | accepted unless configured | refused with `bundle-formats=verity` before any write (T8) | Yes: required by 01 §4.2 |
| `prevent-late-fallback` (new in 1.14) | n/a | available, **not tested** [C-LAB-secureboot-1152-010] | Candidate part of SB-4 (below) |
| Speed | 781 / 818 s per suite | 1540 / 1323 s | Host load, not RAUC: T6, which does not exercise RAUC, was also 1.4× slower [C-LAB-secureboot-1152-011] |

### R.4 Recommendations (with requirement IDs)

| # | Recommendation | Requirement IDs |
|---|---|---|
| SB-1′ | SB-1 of `../secureboot-rauc/` now holds for the **recommended** RAUC: RAUC ≥ 1.15.2 (or Debian ≥ 1.13-3+deb13u1 [C-LAB-rauc-1152-004]) with `bootloader=efi`, signed per-slot UKIs and `bundle-formats=verity`. DC-18/REC-DEC-08 can cite this spike as lab-confirmed (emulation) for the exact configuration. | M-2, R-1, R-3, P-7, F-14 |
| SB-2′ | **Always put `rauc.slot=<bootname>` inside the signed UKI command line.** With it, slot detection is the same on every RAUC version and on every boot path; without it, 1.15.2 depends on `BootCurrent`, which a firmware auto-entry breaks. | R-1, R-3 |
| SB-3/SB-4 (unchanged) | E1 is still open on 1.15.2: replace the slot-pinned factory UKI with a recovery-only UKI, check that the kernel's `onemind.version` matches the root's `/etc/onemind-release` before `mark-good`, and add signed-kernel anti-rollback (SBAT generation or db rotation + dbx). | M-2, R-1, R-3, U-4 |
| SB-8 (new, candidate) | Evaluate `prevent-late-fallback=true` in a follow-up spike. It shrinks the "boot an older committed slot" window after a commit, but it does not touch firmware auto-entries, and it removes the post-commit fallback. Decide only after measuring it together with SB-3. | R-1, M-2 |

### R.5 Deviations (honest log)

1. **T9 placement:** the probe ran inside T2, after the first boot of B and before the second reboot. The README said "after T2". It is informational and does not affect T2's checks.
2. **Bundles disk** grew from 1500 MiB to 2200 MiB to fit the fifth (`plain-good`) bundle. This is a build detail.
3. **E1 repeated** on run 2's end state (not planned; adds a repeat).
4. **Driver fix before any run:** the probe's BEGIN/END markers were split (`'PROBE-STATUS-''BEGIN'`) so the serial console's echo of the command could not match them. This was fixed before run 1; no run used the broken version.
5. **amd64 build not byte-identical** to `../rauc-1152/`: the install tarball hash differs (`7ec9ecf0…` vs `0c241e9c…`). The source archive and the arm64 binary match exactly. The cause (tar timestamps or a compiler difference under qemu-user) was not investigated before the VM was deleted.
6. **Load:** the host was shared with other agents' lab VMs (host load 5–9 during the runs), so timings are not comparable with the 1.13 runs.

### R.6 Limits and founder-runnable tests

The limits of `../secureboot-rauc/` §11 still apply: OVMF is not vendor firmware, and there were no option ROMs, no power cut under Secure Boot, no dm-verity root and no k3s gate. **F-SB-1…3** in `../secureboot-rauc/` stay the hardware tests. Run them with this spike's `scripts/` so the device runs 1.15.2 with `bundle-formats=verity`. Add one step to F-SB-1: after the first boot, run `efibootmgr` and `rauc status`, and check that `Booted from` names `OneMind-A`. Real firmware may create its own auto-entries, which is the E1 path. **PASS:** same outcomes as here. **FAIL:** any difference; record the firmware model and BIOS version.

### R.7 How to re-run

```bash
LAB=<lab-dir>/secureboot-1152          # outside the repo
mkdir -p $LAB/scripts $LAB/logs && cp research-output/evidence/lab/secureboot-1152/scripts/* $LAB/scripts/
limactl create --name lab-sb1152 --tty=false --vm-type vz --cpus 10 --memory 16 --disk 80 \
  --mount-only $LAB:w --mount-type virtiofs template:debian-13 && limactl start lab-sb1152
limactl shell lab-sb1152 -- sudo apt-get install -y mmdebstrap qemu-user-binfmt qemu-system-x86 ovmf rauc gdisk \
  dosfstools mtools e2fsprogs squashfs-tools openssl python3 sbsigntool efitools swtpm swtpm-tools \
  python3-virt-firmware systemd-ukify tpm2-tools python3-pefile git build-essential meson ninja-build pkgconf \
  libglib2.0-dev libssl-dev libjson-glib-dev libdbus-1-dev libfdisk-dev libcurl4-openssl-dev libnl-genl-3-dev
limactl shell lab-sb1152 -- sudo bash -c "OUT=/var/lab/sbout bash $LAB/scripts/build-rauc.sh"     # RAUC 1.15.2 (~6 min)
limactl shell lab-sb1152 -- sudo bash -c "OUT=/var/lab/sbout bash $LAB/scripts/build.sh"          # T0 (~12 min)
limactl shell lab-sb1152 -- sudo python3 -I $LAB/scripts/run-tests.py --out /var/lab/sbout --run /var/lab/sbrun1 --log $LAB/logs/serial-run1.log
limactl shell lab-sb1152 -- sudo python3 -I $LAB/scripts/e1-factory-fallback.py --run /var/lab/sbrun1 --log $LAB/logs/serial-e1.log
bash research-output/evidence/lab/secureboot-1152/scripts/trim-logs.sh $LAB/logs/serial-run1.log > serial-run1-trimmed.log
limactl delete -f lab-sb1152
```

The Debian `rauc` package in the build VM is used only to satisfy the old install list. Every bundle operation uses the 1.15.2 binary (`$OUT/rauc-arm64`). `run-tests.py` exits 0 only if T1–T6 and T8 pass.

### R.8 Pinned versions

| Item | Version |
|---|---|
| Host | macOS on Apple M5 Max, Lima 2.3, QEMU 11.1 (host QEMU not used for the guest) |
| Lab VM | Debian 13.7 arm64 (`template:debian-13`, vz), kernel 6.12.115+deb13.1-cloud-arm64 |
| RAUC | v1.15.2, rauc/rauc@`4fb7c798d6ae412344fb8f8d310d773046af3441` (tag object `f1ceebd6…`); source `git archive` sha256 `0332ba2a…cf75`; arm64 binary `7f076b8b…9d1f`; amd64 install tar `7ec9ecf0…0ff4` |
| VM tools | qemu-system-x86 10.0.13, ovmf 2025.02-8+deb13u1, swtpm 0.7.1-1.5, systemd/ukify 257.13-1~deb13u1, sbsigntool 0.9.4, efitools 1.9.2, python3-virt-firmware 24.11-2, meson 1.7.0 (full list: `logs/versions.txt`) |
| Guest image | Debian 13 amd64 minbase, linux-image 6.12.116+deb13-amd64, systemd 257.13, RAUC 1.15.2 from `/usr` (not dpkg) with Debian runtime libraries (`rauc-amd64-runtime-pkgs.txt`); package list `image-packages.txt` |
| Firmware | `OVMF_CODE_4M.secboot.fd` sha256 `1a462955…9dc1` (same as the 1.13 spike) |
| Upstream code read | rauc/rauc@`4fb7c798` (1.15.2), rauc/rauc@`1183a396` (1.13) |

### R.9 Files

- `scripts/`: `build-rauc.sh` (from `../rauc-1152/`, T12 removed), `build.sh`, `run-tests.py`, `e1-factory-fallback.py` (each derived from `../secureboot-rauc/scripts/`, with the changes listed in §3), `trim-logs.sh`.
- `logs/`: `build-rauc.log`, `build.log` (shell trace lines removed), `driver-run{1,2}.log`, `driver-e1{,-run2}.log`, `serial-{run1,run2,e1,e1-run2}-trimmed.log`, `versions.txt`. The guest has no network; host paths are masked; the LUKS recovery key was never printed.
- `SHA256SUMS` (tested artefacts from the VM, then the files in this folder), `PREREGISTRATION.sha256`, `image-packages.txt`, `rauc-amd64-files.txt`, `rauc-amd64-runtime-pkgs.txt`.
- Not committed (deleted with the VM): disk images, bundles, UKIs, every private key, the full serial logs.
- Claims: `../../claims/LAB-secureboot-1152.csv`; sources: `../../sources/LAB-secureboot-1152.md`.
