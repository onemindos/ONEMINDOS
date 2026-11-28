# QEMU battery, Secure Boot and signed UKI: pass/fail criteria (pre-registered)

**Status:** PRE-REGISTERED. Written 2026-11-21 before the full-image run; the harness `test/qemu/secureboot.py` was self-tested on a rootless image first (SB2-SB4 and the harness self-test), so SB1 on the full image had not run. Its sha256 is in `PREREGISTRATION.sha256` and in the commit that adds it. Nothing here may change afterwards except typo fixes; any other change is a new, dated section at the end. Results never live here (they go to the run's `results.json` and CI logs).

**Serves:** S-13 (verified boot chain), D-007, the finish audit `07-image-security` item 11. **Does not replace** `CRITERIA.md` or `CRITERIA-FIRSTBOOT.md`; the normal image is unchanged and still passes those on its own.

## 1. Starting state and rules

- One disk: an x86_64-efi image built with `--sb-key/--sb-cert` (`make secureboot-image`), opened as a fresh copy for every test. Firmware: OVMF with Secure Boot **on** and a variable store whose only keys are three **throwaway test keys** (PK, KEK, db) made inside the run (`uki.make_test_keys`). The db holds one certificate, the image signing certificate. No Microsoft keys. No real key is ever used or stored by this test.
- Every disk change a test makes is made from outside the guest, on the copy.
- A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS. A harness bug may be re-run once and is named as such.
- Every verdict records KVM or TCG and the host CPU count.
- Timeouts (wall clock): gate line 1500 s from QEMU start; a refusal test watches the console for 240 s.

## 2. Tests

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| SB1 | Signed UKI boots | With the enrolled keys, the untouched image boots (the firmware starts the signed slot-A UKI from the ESP's fallback boot file), the kernel's EFI stub prints `EFI stub: UEFI Secure Boot is enabled.`, and the gate logs `RESULT committed-boot slot=A` | No `Secure Boot is enabled` line, no gate line, or a firmware refusal on the console |
| SB2 | A changed UKI is refused | One byte of the boot file `EFI/BOOT/BOOTX64.EFI` (the slot-A UKI) is changed in the disk copy. Within the watch time the console shows a refusal (`Access Denied`, `Security Violation` or `Image .* failed to load`) and shows **no** sign of the kernel or system starting (`EFI stub:`, `Loading, please wait`, `Welcome to`, `systemd[1]`, `Kernel panic`, `ONEMIND-FIRSTBOOT` or a gate line; the image boots at `loglevel=4`, which hides the kernel's own banner, so these are the first lines that do show; the EFI stub line was seen on a self-test image on 2026-11-21 before this file was committed) | The kernel starts, or no refusal text appears |
| SB3 | A UKI signed by an unknown key is refused | `EFI/BOOT/BOOTX64.EFI` is re-signed with a key that is not in db. Same observation as SB2 | The kernel starts, or no refusal text appears |
| SB4 | An unsigned boot file is refused | `EFI/BOOT/BOOTX64.EFI` is replaced by its unsigned version. Same observation as SB2 | The kernel starts, or no refusal text appears |

## 3. Verdicts for this task

- **x86_64** (OVMF) runs SB1-SB4. On TCG, a timeout missed only because TCG is slower is **BLOCKED (TCG timing)** and must pass on a KVM host (CI) before it counts.
- **Not covered by this slice (listed, not hidden):** starting slot B and the A/B rollback under Secure Boot (needs the update bundle to carry a signed UKI and a RAUC efi-backend or BootOrder switch; GRUB cannot select slots under Secure Boot without shim), dm-verity on the booted root, TPM measurement, the real signing ceremony.

## 4. Amendment 2026-11-22: SB5, slot B boots its own signed UKI (#148, slice 1)

**Written before SB5 or the efi route was booted.** SB1-SB4 and their PASS/FAIL text are unchanged. What changes for every test is the starting state:

- The image is built on the **efi route** (`assemble.py tree --boot efi`): RAUC's `efi` bootloader backend picks the slot by switching firmware boot entries labelled `A` and `B` (their RAUC bootnames), each starting that slot's signed UKI (`\EFI\Linux\onemind-<slot>.efi`) on its own boot partition. The box creates the two entries on its first boot, before the health gate (`onemind-efi-entries`). A fresh disk carries the UKIs on `onemind-boot-a` only; `onemind-boot-b` stays empty until the first update. The ESP's fallback boot file is still the signed slot-A UKI, so SB1-SB4 (fresh variable store, no entries yet) start the same file as before.
- The image carries the battery's test overlay (`test/qemu/overlay`: a root shell on the serial console) and the run gets a second, read-only disk `bundles.img` (ext4 label `onemind-test`) holding one bundle, `good.raucb`: version 2, verity format, signed by the run's throwaway RAUC CA, carrying a signed UKI per slot (`[image.efi]`, signed with the image's throwaway db key).

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| SB5 | Slot B boots its own signed UKI | Fresh copy, the enrolled keys, the bundles disk attached. The console shows `EFI stub: UEFI Secure Boot is enabled.` and the gate logs `RESULT committed-boot slot=A`. Then, in the guest: `rauc install good.raucb` exits 0, and `efibootmgr` shows `BootNext` = the entry labelled `B`. After `systemctl reboot`: the console shows `EFI stub: UEFI Secure Boot is enabled.` again, the gate logs `RESULT mark-good slot=B version=2`, and `efibootmgr` shows `BootCurrent` = the `B` entry, that entry's loader is `onemind-B.efi`, and it is first in `BootOrder` | A does not commit first, the install fails, `BootNext` is not `B`, a firmware refusal, no Secure Boot line after the reboot, any other gate line (`fell-back`, `mark-bad`, `unhealthy`), or `BootCurrent`/`BootOrder` not `B` |

- Timeouts (wall clock): each gate line 1500 s from the boot that prints it; the install 2400 s; the Secure Boot line 600 s.
- SB5 without the bundles disk is **BLOCKED**, never PASS.
- **Still not covered (listed, not hidden):** rollback under Secure Boot (slot B fails the gate and the firmware returns to A: issue #881, wave E), anti-downgrade of an older signed UKI, owner-held keys ("sovereign mode", founder decision 2026-11-22), dm-verity on the booted root, TPM measurement, the real signing ceremony.

## 5. Amendment 2026-11-25: SB6 and SB7, a bad update rolls back under Secure Boot (#148, rollback slice)

**Written before SB6 or SB7 was booted.** SB1-SB5 and their PASS/FAIL text are unchanged. The starting state is SB5's (efi route image, throwaway keys, Secure Boot on, the bundles disk attached), except that the bundles disk now also carries two bad bundles signed by the same throwaway keys, each with its own signed UKI per slot: `bad-k3s.raucb` (version 3, k3s exits at start, the same fixture as T4) and `bad-boot.raucb` (version 5, PID 1 exits so the kernel panics, the same fixture as T6). Each test starts from a fresh copy of the disk, boots slot A, installs the bundle and reboots.

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| SB6 | The health gate rejects a bad slot B and the box returns to A | A commits first (`committed-boot slot=A version=1`) and `rauc install` exits 0 with `BootNext` = the entry labelled `B`. After the reboot the console shows `EFI stub: UEFI Secure Boot is enabled.` and the gate logs `RESULT mark-bad slot=B version=3`. The gate reboots; the console shows the Secure Boot line again and the gate logs `RESULT committed-boot slot=A version=1`. Then `efibootmgr` shows `BootCurrent` = the `A` entry and the `A` entry first in `BootOrder` | A does not commit first, the install fails, `BootNext` is not `B`, a firmware refusal, a missing Secure Boot line in any boot, any other gate line, or `BootCurrent`/`BootOrder` not `A` at the end |
| SB7 | A slot B that panics gets one try and the box returns to A | Same start. After the reboot the console shows the Secure Boot line and the marker `BAD-BOOT: broken init exiting` **exactly once** (the firmware used `BootNext` up, so there is no second try). The next boot shows the Secure Boot line and the gate logs `RESULT fell-back slot=A version=1`. `BootCurrent` = the `A` entry and `A` leads `BootOrder` | The marker appears more than once or never, no `fell-back` line, a firmware refusal, a missing Secure Boot line, or `BootCurrent`/`BootOrder` not `A` |

- Timeouts (wall clock): each gate line 1500 s from the boot that prints it (3000 s for the `mark-bad` line, which waits out the gate's k3s checks); the install 2400 s; each Secure Boot line 600 s (900 s after a reset).
- SB6 and SB7 without the bundles disk are **BLOCKED**, never PASS.
- **Still not covered (listed, not hidden):** anti-downgrade of an older signed UKI, owner-held keys ("sovereign mode"), dm-verity on the booted root, TPM measurement and the PCR 7 re-seal on the switch-over (policy written in `os/secureboot/README.md`; the data-encryption lane tests the unlock), the real signing ceremony.
