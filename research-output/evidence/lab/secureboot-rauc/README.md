# Lab spike LAB-secureboot-rauc (X-2R): RAUC A/B under UEFI Secure Boot with custom keys, TPM2-sealed LUKS2 data

**Status:** COMPLETE: **X-2R PASS** (T0–T6 pass in 2 full runs, bonus T7 passes; an exploratory test found a downgrade gap, section 9). Goal, hypotheses, design and pass/fail criteria (sections 1–5) were pre-registered at 2026-11-11 04:22 UTC, before any build or test ran. `PREREGISTRATION.sha256` records the file's sha256 and timestamp as it stood then; since then only this status line and everything below "Results" have changed. Pre-registration is self-attested.

> **Explain it like I'm the founder.** Secure Boot is a lock on the front door of the computer. The motherboard firmware holds a short list of keys (PK, KEK, db), and it refuses to start any boot program that is not signed by a key on that list. We want OneMind boxes to use **our own keys** and to keep the A/B safety net we already proved (two copies of the OS, update the idle one, fall back if it fails). The worry in `01-FOUNDATION-DECISION.md` §4.3 was that turning on Secure Boot later might force a different disk layout, which would mean wiping customers' boxes. This spike builds the layout we chose, turns Secure Boot on with our own keys, and tests the lot inside a virtual PC: does an update still work, does a bad update still roll back, is a tampered or unsigned kernel refused, and does the encrypted data disk still unlock by itself (using the TPM security chip) on both copies of the OS? If all of that holds, the layout is safe to ship on day one, and Secure Boot can be switched on later without a reflash.

## 1. Goal

Prove or disprove spike **X-2R** from `01-FOUNDATION-DECISION.md` §4.3 and `07-security-compliance.md` §12 (X-2, re-run with RAUC instead of Rugix):

> A RAUC A/B layout, as specified in 01 §4.3 (1 GiB ESP, FAT32 ESP-type `boot-a/b`, `system-a/b` with verity headroom, recovery, LUKS2 data), boots on x86_64 under **enforced UEFI Secure Boot with custom PK/KEK/db**, performs an A→B update and an automatic rollback, refuses a tampered and an unsigned kernel, and unlocks a **LUKS2 data partition sealed to a TPM2** without a prompt on slot A, on slot B and after rollback.

Platform: QEMU `q35` + OVMF (Secure Boot build, SMM on) + `swtpm` TPM 2.0, x86_64 guest under TCG emulation, everything inside a disposable Debian 13 Lima VM on the Apple M5 Mac.

## 2. Hypotheses

- **H1 (boot route).** RAUC's stock `efi` backend (Debian's RAUC 1.13, no patches) works under Secure Boot with signed **unified kernel images (UKIs)** stored directly in `boot-a`/`boot-b`, with one EFI boot entry per slot. No GRUB, no shim and no systemd-boot are needed. RAUC's `efi` backend sets a one-shot `BootNext` for a new slot, puts a slot at the front of `BootOrder` on `mark-good` and removes it on `mark-bad` (code: `rauc@4fb7c79:src/bootloaders/efi.c`).
- **H2 (refusal and fallback).** Because `BootNext` is one-shot, a new slot whose UKI the firmware refuses (tampered after signing, or never signed) falls back to the committed slot on the same power-on with no human input.
- **H3 (TPM2 data unlock).** A LUKS2 data partition enrolled with `systemd-cryptenroll --tpm2-pcrs=7` (PCR 7 records the Secure Boot state and keys) unlocks without a prompt on A, on B and after rollback, because both slots' UKIs are signed by the same db key. It **fails closed** (no unlock) when the same disk boots with Secure Boot off.
- **H4 (layout).** The 01 §4.3 layout needs **no change** for this route: FAT32 ESP-type 512 MiB `boot-a/b` hold the slot's UKIs; the 1 GiB ESP only needs a factory first-boot loader.

## 3. Design (fixed before the run)

- **Disk (GPT), 01 §4.3 layout:** p1 `onemind-esp` 1 GiB FAT32 (ESP) · p2/p3 `onemind-boot-a/b` 512 MiB FAT32 with the ESP type GUID · p4/p5 `onemind-system-a/b` 10 GiB each (the ext4 root image written into them is ~1.6 GiB, leaving well over 10 % verity headroom; dm-verity itself is **not** enabled in this spike) · p6 `onemind-recovery` 1 GiB, empty · p7 `onemind-data` 2 GiB, **LUKS2 created on first boot**. Fixed PARTUUIDs.
- **Kernel:** Debian 13 `linux-image-amd64` and `initramfs-tools` initrd, wrapped with `ukify` (systemd 257 stub) into a UKI. **Each `boot` slot image holds two UKIs**, `EFI/Linux/onemind-A.efi` (`root=PARTUUID=<system-a> rauc.slot=A`) and `onemind-B.efi` (`…system-b… rauc.slot=B`), so the kernel command line stays inside the signed image and the same vfat image can go into either slot. EFI entry `OneMind-A` → `boot-a:\EFI\Linux\onemind-A.efi`, `OneMind-B` → `boot-b:\EFI\Linux\onemind-B.efi`.
- **Keys:** throwaway lab PK, KEK and db (RSA-2048, self-signed, 30 days), generated inside the VM and never committed. db signs the UKIs with `sbsign`. The keys are enrolled into a copy of `OVMF_VARS_4M.fd` with `virt-fw-vars`, with Secure Boot enabled. RAUC bundles are signed by a separate lab CA (as in `../rauc/`).
- **First boot:** the ESP holds a signed copy of UKI-A at the removable-media path `\EFI\BOOT\BOOTX64.EFI` (factory loader). A first-boot service creates the two EFI boot entries with `efibootmgr`, sets `BootOrder` to A then B, formats `onemind-data` as LUKS2 with a random key held only in `/run`, enrolls the TPM2 (PCR 7), adds a recovery key, then wipes the temporary key slot.
- **Data unlock on every boot:** `systemd-cryptsetup attach … tpm2-device=auto,headless=true`, so a failed TPM unseal never waits for a prompt. Mounted at `/data`.
- **RAUC:** `bootloader=efi`, `efi-use-bootnext` default (true), slot groups `efi.N` (vfat, parent `rootfs.N`) + `rootfs.N` (ext4, bootname `OneMind-A/B`), verity bundle format, lab CA keyring.
- **Health gate** (from `../rauc/`, adapted): commits with `rauc status mark-good booted` only if the core stand-in service is healthy **and** `/data` is unlocked and mounted; otherwise `mark-bad` and reboot (only when the other slot is in `BootOrder`). k3s is not used (see `../rauc/` §8 F1 for the k3s-gate founder test).
- **Bundles (all RAUC-signed by the lab CA):** `good` (v2), `bad-health` (v3, core service fails), `tampered` (v4: UKIs signed, then 1 byte of the embedded command line changed, e.g. `panic=5` → `panic=6`, after signing), `unsigned` (v5: UKIs never signed).
- **TPM:** `swtpm` 0.10 (Debian) socket, `tpm-tis` device. Its state directory persists across all reboots of one run.
- **Logs:** serial console to a file; OVMF's own console output also goes to serial.

## 4. Pass / fail criteria (frozen before the run)

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| T0 | Build | One script inside the Lima VM produces `disk.img`, `OVMF_VARS` with lab PK/KEK/db and Secure Boot enabled, 4 RAUC bundles; `sbverify --cert db.crt` passes for the `good`/`bad-health` UKIs and **fails** for `tampered` and `unsigned` UKIs | Any manual step, or the signature checks do not split as stated |
| T1 | First boot under Secure Boot | Guest boots; `SecureBoot=1` and `SetupMode=0` read from efivars; kernel log says Secure Boot is enabled; `efi-readvar -v PK` (or `mokutil --pk`) shows the lab PK subject; data partition is LUKS2 with a `systemd-tpm2` token, opened without a prompt, mounted; gate logs `mark-good slot=A` | Any of these missing, or a prompt appears |
| T2 | Good update A→B under SB | `rauc install good.raucb` sets `BootNext` to OneMind-B; reboot runs B with `ONEMIND_VERSION=2`, Secure Boot still on, data unlocks by TPM with no prompt, gate `mark-good slot=B`, `BootOrder` starts with OneMind-B; one more reboot lands on B again | Ends anywhere but committed B, or data needs a prompt |
| T3 | Health-gated rollback under SB | From committed B install `bad-health` (into A), reboot: A (v3) boots under SB, **data unlocks by TPM**, gate `mark-bad slot=A` and reboots; guest ends on B (v2) with data unlocked, no human input, within 2 boots | Stays on A, needs input, or data fails to unlock on any boot |
| T4 | Tampered kernel refused | Install `tampered` (into A), reboot: firmware does **not** start the A UKI (no kernel log from v4; OVMF reports a load failure such as `Access Denied` / `Security Violation` if it prints one), and the same power-on continues to B (v2), data unlocked, no human input | The tampered UKI runs, or the guest stops/loops |
| T5 | Unsigned kernel refused | Same as T4 with `unsigned` (v5) | Same as T4 |
| T6 | TPM fails closed without Secure Boot | Boot the same disk (current state) with OVMF vars that have **no** custom keys / Secure Boot off and the same TPM state: `SecureBoot=0`, the TPM2 unseal of `onemind-data` **fails**, `/data` is not mounted, no passphrase prompt blocks boot (headless), the gate does not commit | Data unlocks with Secure Boot off, or boot hangs on a prompt |
| T7 (bonus) | Signed PCR 11 policy | Data also enrolled with `--tpm2-public-key` (PCR 11 policy signed by a lab key, per 07 SEC-01 / X-2) and unlocks on A, B and after rollback | Recorded as PASS / FAIL / BLOCKED with the reason; does not affect the overall verdict |

**Overall verdict:** X-2R **PASS** if T0–T6 pass. A test that cannot run because of an environment limit is recorded as **BLOCKED** with the exact reason, never as PASS. A permission denial is recorded and not worked around; the remaining steps become a founder-runnable test.

## 5. Requirement IDs served

M-2 (security baseline), R-1 (safe updates), R-3 (long-term maintainability of sold hardware), U-4 (data safety), P-7 (bring-your-own x86 install), F-14 (one OS at every scale). Feeds REC-DEC-08 and DC-18 in `01-…`, SEC-01 and X-2 in `07-…`.

## 6. Glossary

| Term | Meaning |
|---|---|
| UEFI Secure Boot | Firmware feature: only boot programs signed by a key in the firmware's `db` list may run |
| PK / KEK / db | Platform Key (owner of the firmware's key store), Key Exchange Key (may change db), signature database (keys that may sign boot programs) |
| Setup mode / user mode | With no PK enrolled the firmware is in setup mode (anything boots, keys can be written); enrolling a PK switches to user mode |
| OVMF | The UEFI firmware build for QEMU virtual machines (from the EDK II project) |
| UKI | Unified kernel image: kernel, initrd and command line in one signed EFI program |
| `ukify` / `sbsign` / `sbverify` | Tools to build a UKI / sign an EFI program / check its signature |
| shim | Small Microsoft-signed first-stage loader used by distributions to boot on PCs that only trust Microsoft's keys; not needed when the owner enrolls their own keys |
| `BootNext` / `BootOrder` | EFI variables: the one-time next boot entry, and the persistent list of boot entries tried in order |
| TPM2 / swtpm | Trusted Platform Module (security chip that can hold a secret until the boot measurements match); `swtpm` is its software emulator for VMs |
| PCR 7 | TPM register that records the Secure Boot state and the keys in use; a secret sealed to it unlocks only under the same Secure Boot configuration |
| Signed PCR 11 policy | systemd mechanism: the UKI carries a signature over its expected PCR 11 values, so a TPM secret bound to the signing key survives kernel updates |
| LUKS2 | Linux disk-encryption format; can hold several key slots (TPM, recovery key) |
| dm-verity / verity headroom | Kernel feature that checks every block of a read-only root against a hash tree; "headroom" is free space in the slot reserved for that tree |
| TCG | QEMU's software CPU emulator (the Mac is Arm, the guest is x86_64) |

---

## Results

**Verdict: X-2R PASS.** T0–T6 passed in **2 full runs** (run 1: 781 s, run 2: 818 s, 2026-11-11), and bonus T7 passed in both. H1–H4 are confirmed in emulation. One exploratory test added after run 1 (**E1**, not pre-registered) found a **downgrade gap** that the design must close before the first image ships (section 9). Claims: [C-LAB-secureboot-rauc-011…020].

> **Explain the result like I'm the founder.** The layout we picked works with Secure Boot switched on and our own keys, with no reflash needed. Updates went from A to B. A bad update rolled back by itself. A kernel that someone tampered with was refused by the firmware, and so was a kernel nobody signed; the box quietly carried on with the good copy. The encrypted data disk unlocked by itself on both copies of the OS and after the rollback, and it stayed locked when someone turned Secure Boot off. One thing surprised us. If both OS copies ever fail, the PC's firmware falls back to the original factory kernel in the boot partition. That kernel is old, but it is properly signed, so Secure Boot lets it run, and it ran against newer system files. Secure Boot answers "is this kernel ours?", not "is this our *latest* kernel?". OneMind needs an extra rule for that second question (recommendations SB-3 and SB-4).

### 7.1 Test results

Both runs gave the same outcome on every test. Line evidence is from `logs/serial-run1-trimmed.log` and `logs/driver-run1.log` unless noted; run 2 is in `logs/*-run2*`.

| ID | Result | Evidence |
|---|---|---|
| T0 | **PASS** | `logs/build-run2.log`: v1–v3 UKIs `sbverify: Signature verification OK`; v4 (tampered) and v5 (unsigned) `Signature verification failed`; 4 bundles show `Verified inline signature by 'O = OneMind LAB, CN = rauc-lab-signer'`. `virt-fw-vars --print` lists PK, KEK, db (no Microsoft keys) and `SecureBootEnable: ON`. Build run 1 failed (section 10, item 1) [C-LAB-secureboot-rauc-011]. |
| T1 | **PASS** | `secureboot: Secure boot enabled`; `SB-REPORT: … SecureBoot=1 SetupMode=0`; `Kernel is locked down from EFI Secure Boot`; `efi-readvar` shows `CN=OneMind LAB PK`; `DATA: tokens: systemd-tpm2 systemd-recovery`, `DATA: UNLOCK OK method=tpm2 (no prompt)`; `HEALTH-GATE: RESULT mark-good slot=A version=1`. First boot 75 s (run 2: 74 s) [C-LAB-secureboot-rauc-012]. |
| T2 | **PASS** | After install, `BootNext: 0004` (OneMind-B) and `BootOrder: 0003` (RAUC removed B while writing it); B boots `onemind.version=2`, SB on, `UNLOCK OK`, `mark-good slot=B version=2`, `BootOrder: 0004,0003,…`; second reboot `mark-good slot=B version=2` [C-LAB-secureboot-rauc-013]. |
| T3 | **PASS** | `BootNext=OneMind-A`; A (v3) boots under SB, `UNLOCK OK`, `RESULT mark-bad slot=A version=3 core-unhealthy -> reboot to B`; then `RESULT mark-good slot=B version=2`, 2 TPM unlocks in the sequence; `rauc status`: A `boot status: bad`, B `good` [C-LAB-secureboot-rauc-014]. |
| T4 | **PASS** | `BdsDxe: failed to load Boot0003 "OneMind-A" from HD(2,GPT,…)/\EFI\Linux\onemind-A.efi: Access Denied`, then `BdsDxe: loading Boot0004 "OneMind-B"` in the same power-on; no `onemind.version=4` kernel line; `mark-good slot=B version=2` with data unlocked [C-LAB-secureboot-rauc-015]. |
| T5 | **PASS** | Same as T4 for the unsigned v5 UKI (`Access Denied`, fell through to B, no v5 kernel ran) [C-LAB-secureboot-rauc-015]. |
| T6 | **PASS** | Secure Boot off (same keys, same TPM): `secureboot: Secure boot disabled`, `SecureBoot=0`; `DATA: UNLOCK FAILED (tpm2 unseal refused): Password querying disabled via 'headless' option.`; `RESULT no-commit slot=B version=2 data-locked`. No prompt. T6b: Secure Boot back on → `UNLOCK OK`, `mark-good` [C-LAB-secureboot-rauc-016]. |
| T7 (bonus) | **PASS** | `BONUS-PCR11: UNLOCK OK` on A (T1), B (T2), the unhealthy A v3 and B after rollback (T3). Caveat in section 10, item 3 [C-LAB-secureboot-rauc-017]. |
| E1 (exploratory, added after run 1) | **Gap found** | `logs/serial-e1-trimmed.log`: BootNext → firmware auto entry 0001 → `BdsDxe: starting Boot0001 "UEFI Misc Device"` → `onemind.version=1` kernel, `Secure boot enabled`, root filesystem `ONEMIND_VERSION=5`, `DATA: UNLOCK OK`, `HEALTH-GATE: RESULT mark-good slot=A version=5`; `BONUS-PCR11: UNLOCK FAILED slot=A` [C-LAB-secureboot-rauc-018]. |

### 7.2 Hypotheses

| | Verdict | Why |
|---|---|---|
| H1 boot route | **Confirmed** | Debian's unpatched RAUC 1.13 with `bootloader=efi` drove A/B under enforced Secure Boot with signed UKIs straight from `boot-a/b`; no GRUB, shim or systemd-boot. It works because RAUC only manipulates `BootNext`/`BootOrder` [C-LAB-secureboot-rauc-001], and the firmware does the signature check. |
| H2 refusal → fallback | **Confirmed** | edk2 deletes `BootNext` before trying it, then walks `BootOrder` [C-LAB-secureboot-rauc-003]; T4/T5 show a refused UKI costs no extra reboot. |
| H3 TPM2 data | **Confirmed** | PCR 7 holds the Secure Boot state and keys, not the kernel [C-LAB-secureboot-rauc-006], so A, B and rollback all unlock, and switching Secure Boot off locks the data. **But** E1 shows the flip side: PCR 7 alone also unlocks for *any* older kernel signed by the same db key. |
| H4 layout | **Confirmed** | 01 §4.3 used unchanged; each 512 MiB `boot` slot holds a 200 MiB vfat image with both per-slot UKIs [C-LAB-secureboot-rauc-020]. The 1 GiB ESP only needed the factory loader, and E1 shows that loader is itself a risk. |

### 7.3 What this means for 01 §4.3 and 07 SEC-01

- **DC-18 / REC-DEC-08 can move from "design inference" to "lab-confirmed (emulation)"** for the x86 route: RAUC `efi` backend + signed UKIs in FAT32 ESP-type `boot-a/b`. RAUC needs no systemd-boot or `custom` backend for Secure Boot. 01 §4.3 says the ESP holds "first-stage GRUB + grubenv at launch". With this route, GRUB is not needed at all (see SB-1).
- **07 X-2 is answered for RAUC:** a TPM-sealed key survives A→B and rollback (PCR 7, and signed PCR 11 as the bonus). The signed-PCR-11 route works with Debian's tools, but it needs a systemd-based initrd to be clean (section 10, item 3).
- **Secure Boot is not anti-rollback.** It answers "is this ours?", not "is this current?" (E1). The manifest's monotonic counter (01 §5, P0-W3-2 response) protects installs only. A firmware fallback path bypasses it.

## 8. Recommendations (with requirement IDs)

| # | Recommendation | Requirement IDs |
|---|---|---|
| SB-1 | Adopt the **RAUC `efi` backend + one signed UKI per slot** (signed command line containing `root=PARTUUID=…` and `rauc.slot=…`) as the x86 Secure Boot route, keeping 01 §4.3 unchanged. GRUB, shim and systemd-boot stay unneeded on owner-keyed boxes. Ship each `boot` slot image with both per-slot UKIs, so one vfat image fits either slot. | M-2, R-1, R-3, P-7, F-14 |
| SB-2 | **Installer:** create the two EFI entries, put **only slot A** in `BootOrder`, and remove firmware auto-entries that point at the OneMind disk, because RAUC's `efi` backend reports any slot listed in BootOrder as "good", even an empty one [C-LAB-secureboot-rauc-019]. Re-check on every boot: OVMF re-adds its auto-entries, and real firmware may too. | R-1, U-4 |
| SB-3 | **Do not leave a slot-pinned signed kernel at the ESP's removable path.** Put a **recovery UKI** there (and in `onemind-recovery`) that boots a rescue environment, never a slot's root filesystem directly. Make the health gate refuse `mark-good` when the kernel's `onemind.version` differs from the root filesystem's `/etc/onemind-release` (E1 committed a v1 kernel on a v5 root). | R-1, R-3, M-2, U-4 |
| SB-4 | **Anti-rollback for signed kernels:** bump the UKI's **SBAT** generation, or rotate the db signing key on security releases (revoking old UKIs through `dbx` where the firmware allows it), in addition to the manifest's monotonic counter. Add a rotation drill to the release process. | M-2, R-3 |
| SB-5 | **Bind data to PCR 7 + a signed PCR 11 policy** (07 SEC-01's design) instead of PCR 7 alone, and build the initrd with systemd (mkosi or dracut) so systemd-stub's `/.extra/tpm2-pcr-signature.json` is used natively [C-LAB-secureboot-rauc-005]. Keep `headless=true` so a failed unseal never waits for a keyboard, and surface "data locked, enter recovery key" in the dashboard. | M-2, U-4, R-1 |
| SB-6 | Treat the bundle's own UKI signature as a **pre-install check**: run `sbverify` against the device's db before RAUC writes the slot (a RAUC install hook). T4/T5 show the firmware would refuse anyway, but a pre-check saves a wasted install and a reboot. | R-1, M-6 |
| SB-7 | Run founder tests **F-SB-1…3** (below) on the Dell 5540 (and the Beelink if it has a TPM) before the week-4 update gate in `20-PLAN-180-DAYS.md`. | P-7, R-1, M-2 |

## 9. Gap found by exploratory test E1 (not pre-registered)

E1 was added after run 1, when the logs showed that OVMF re-adds its own entries to `BootOrder`, including entry 0001, the disk's removable-media path that loads the ESP's `\EFI\BOOT\BOOTX64.EFI` (the factory UKI-A v1). E1 points `BootNext` at that entry, simulating "both OneMind entries fail". Result: the old, validly signed v1 kernel booted under Secure Boot against slot A's v5 root filesystem, the PCR 7-bound data unlocked, and the gate committed `slot=A version=5`. That put OneMind-A back in BootOrder, although A's own UKI is unsigned. The next normal boot would still refuse A and fall through to B, so the box would not brick. The bonus signed-PCR-11 container did refuse, but only because the root filesystem carried v5's policy signature. A matching *old* signed policy would have unlocked it, so signed PCR 11 alone is not anti-rollback either. SB-3 and SB-4 close the gap. This is one run, so it is labelled `medium` confidence [C-LAB-secureboot-rauc-018].

## 10. Deviations and problems found during the run (honest log)

1. **Build run 1 failed:** `systemd-measure` (called by `ukify --pcr-private-key`) printed `Could not calculate PolicyPCR digest: Operation not supported` because the TPM2 TSS libraries were missing in the build VM (`logs/build-run1-failed.log`). Fixed by installing `tpm2-tools` (pulls `libtss2-*`) [C-LAB-secureboot-rauc-009]. A OneMind image builder needs them even without a TPM.
2. **Package version:** the README planned swtpm 0.10; Debian 13 ships **swtpm 0.7.1-1.5**, which was used. The arm64 `systemd-boot-efi` package has no x86_64 stub, so `linuxx64.efi.stub` was taken from the amd64 image's own `systemd-boot-efi 257.13-1~deb13u1`.
3. **Signed PCR 11 with initramfs-tools (T7 caveat):** systemd-stub hands the policy signature to the initrd as `/.extra/…` [C-LAB-secureboot-rauc-005]. Debian's initramfs-tools initrd does not carry it into the booted system, so the build extracted each UKI's `.pcrsig` and placed it in the root filesystem (`/etc/onemind/pcrsig-{A,B}.json`). The phases signed included `sysinit` and `sysinit:ready`, because no `enter-initrd` phase is measured without a systemd initrd [C-LAB-secureboot-rauc-008]. This works, but it is a lab workaround, hence SB-5.
4. **Design addition (not a deviation from criteria):** the T7 container is a separate 32 MiB LUKS2 file on `/data`, so the bonus could not mask the main PCR 7 result.
5. Minor: `systemd-logind` is masked in this minimal image (as in `../rauc/`), so `systemctl poweroff` prints a login1 warning; shutdown still completed (`reboot: Power down` in the logs).
6. Driver waits: in the first monitoring attempt, a wait pattern matched `rc=` inside a result line. This was an observer error only; the driver itself was unaffected and exited `rc=0` both times.

## 11. What this lab did NOT prove (limits) and founder-runnable tests

| Gap | Why | Status |
|---|---|---|
| Real PC firmware | OVMF is the reference EDK II; vendor firmware differs in BootNext handling, auto-entries and key enrolment UI. RAUC's own docs warn that EFI implementations differ [C-LAB-secureboot-rauc-001] | **Founder hardware** → F-SB-1 |
| Option ROMs and Microsoft keys | Only lab keys were enrolled. On real PCs, GPU/NIC option ROMs are commonly signed by Microsoft's third-party UEFI CA, so removing Microsoft keys may stop them loading (UNVERIFIED here) | **Founder hardware** → F-SB-2 |
| Power cut during install under Secure Boot | Covered without Secure Boot in `../rauc/` (T6/T7); the efi backend writes EFI variables instead of a FAT grubenv | → F-SB-3 |
| dm-verity root | Slots keep >10 % headroom, but verity was not enabled | Not tested (follow-up spike) |
| shim + GRUB route | Not needed with owner keys; the UKI route passed | Not tested (only needed for boxes that must trust Microsoft-signed shim) |
| k3s readiness gate | Stand-in service, as in `../rauc/` | Founder test F1 in `../rauc/` |
| Repetition | 2 full runs; E1 once | — |

**F-SB-1: Secure Boot A/B on the Dell 5540 (or another x86 box with TPM 2.0).**
1. Rebuild with `scripts/build.sh` (section 13) and `limactl copy` out `disk.img`, `PK.crt`, `KEK.crt`, `db.crt` and the `.auth`/`.esl` files you create with `cert-to-efi-sig-list` + `sign-efi-sig-list` (efitools) inside the VM.
2. `dd` the image to a spare USB SSD (see `../rauc/` F1 step 4). In the firmware setup: **back up the current keys**, clear them (setup mode), then enroll db, KEK and PK from the USB stick (or boot once with Secure Boot off and run `efi-updatevar -f db.auth db`, then KEK, then PK last). Enable Secure Boot.
3. Boot; run T1–T5 by hand: `rauc install /mnt/bundles/<bundle>.raucb && systemctl reboot`, then `efibootmgr`, `rauc status`, `mokutil --sb-state`, and `journalctl -b | grep -E 'DATA:|HEALTH-GATE'`.
4. **PASS:** same outcomes as T1–T5 above with no keyboard input, and the firmware refuses v4/v5 (screen message or fallback to B). **FAIL:** any outcome differs; record the firmware's model and BIOS version. **Undo:** restore the backed-up keys or "Restore factory keys" in setup.

**F-SB-2: option ROMs with owner-only keys (same box, with a discrete GPU or add-in NIC if available).** Boot with only lab keys enrolled. **PASS:** display and network firmware work before the OS starts. **FAIL:** no display or PXE before the OS, which means the Microsoft third-party UEFI CA must be kept in db (decision for `26-…`).

**F-SB-3: power pull under Secure Boot.** Pull the cable at 10 points during `rauc install` and the first boot of the new slot, as in `../rauc/` F2. **PASS:** 10/10 end on a booting, Secure-Boot-verified, committed slot with data unlocked by the TPM. **FAIL:** a corrupted EFI variable store, a refused boot with no fallback, or a recovery-key prompt.

## 12. What competitors do

| Product | Secure Boot / TPM in the shipped OS | Update + boot integration | Constraint fit for OneMind |
|---|---|---|---|
| Home Assistant OS | No Secure Boot key enrolment, TPM sealing or LUKS data encryption found in the image [C-W6-053] | RAUC + GRUB on x86 (grubenv), verity bundles | **High** for the update engine (same RAUC, same x86 class); **low** for Secure Boot, which HAOS does not do, so it gives OneMind no pattern to copy here. |
| umbrelOS 2.0 / Rugix | Rugix has a systemd-boot boot flow and a 512 MiB EFI partition schema [C-W6-049]; its `luks2-tpm2` data driver is marked unstable, with a signed-policy mode only planned [C-W6-048] | Rugix A/B | **Medium**: Debian + x86 + Pi like OneMind, but the Secure Boot/TPM parts are not production-ready upstream; PolyForm-Noncommercial umbrelOS code is patterns only. |
| systemd's documented design (UKI + signed PCR 11) | Signed PCR policy so the key survives kernel updates [C-W6-047, C-LAB-secureboot-rauc-007] | Any A/B engine | **High**: this lab shows it works with RAUC's `efi` backend; it needs a systemd initrd (SB-5). |
| This lab (OneMind candidate) | Owner PK/KEK/db, signed UKIs, LUKS2 + TPM2 PCR 7 (+ signed PCR 11 bonus) | RAUC `efi` backend (BootNext/BootOrder) | Proven in emulation; needs F-SB-1…3 and SB-2…SB-5 before shipping. |

## 13. How to re-run

From the Mac (Lima ≥ 2.0; every upstream tool runs inside the VM; about 4 min to build and 14 min to test):

```bash
LAB=<lab-dir>/secureboot-rauc                      # outside the repo
mkdir -p $LAB/scripts $LAB/logs && cp research-output/evidence/lab/secureboot-rauc/scripts/* $LAB/scripts/
limactl create --name lab-sbrauc --tty=false --vm-type vz --cpus 10 --memory 16 --disk 80 \
  --mount-only $LAB:w --mount-type virtiofs template:debian-13 && limactl start lab-sbrauc
limactl shell lab-sbrauc -- sudo apt-get install -y mmdebstrap qemu-user-binfmt qemu-system-x86 ovmf rauc gdisk \
  dosfstools mtools e2fsprogs squashfs-tools openssl python3 sbsigntool efitools swtpm swtpm-tools \
  python3-virt-firmware systemd-ukify tpm2-tools python3-pefile
limactl shell lab-sbrauc -- sudo bash -c "OUT=/var/lab/sbout bash $LAB/scripts/build.sh"                     # T0
limactl shell lab-sbrauc -- sudo python3 -I $LAB/scripts/run-tests.py --out /var/lab/sbout --run /var/lab/sbrun \
  --log $LAB/logs/serial.log                                                                                 # T1–T7
limactl shell lab-sbrauc -- sudo python3 -I $LAB/scripts/e1-factory-fallback.py --run /var/lab/sbrun --log $LAB/logs/e1.log
limactl delete -f lab-sbrauc                                                                                 # clean up
```

`run-tests.py` exits 0 only if T1–T6 pass. Builds are not byte-reproducible (keys, UUIDs and timestamps are random each time); the hashes of the tested artefacts are in `SHA256SUMS`.

## 14. Pinned versions

| Item | Version |
|---|---|
| Host | macOS 27.2 on Apple M5 Max, Lima 2.3.0, QEMU 11.1.3 (host QEMU not used for the guest) |
| Lab VM | Debian 13.7 arm64 (Lima `template:debian-13`, vz), kernel 6.12.115+deb13.1-cloud-arm64 |
| VM tools | qemu-system-x86 10.0.13+ds-0+deb13u1, ovmf 2025.02-8+deb13u1, swtpm 0.7.1-1.5, rauc 1.13-3+deb13u1, systemd-ukify / systemd 257.13-1~deb13u1, sbsigntool 0.9.4-3.2+deb13u1, efitools 1.9.2-3.5, python3-virt-firmware 24.11-2, tpm2-tools 5.7-1+b1, mmdebstrap 1.5.7-1+deb13u1 (full list: `logs/versions.txt`) [C-LAB-secureboot-rauc-010] |
| Guest image | Debian 13 amd64 minbase; linux-image 6.12.116+deb13-amd64; systemd / systemd-boot-efi / systemd-cryptsetup 257.13-1~deb13u1; cryptsetup-bin 2.7.5-2; rauc + rauc-service 1.13-3+deb13u1; efibootmgr 18-2; initramfs-tools 0.148.4 (full list: `image-packages.txt`) |
| Firmware | `OVMF_CODE_4M.secboot.fd` sha256 `1a462955…9dc1`; `OVMF_VARS_4M.fd` `5d2ac383…5d1e`; lab vars with keys `7f3d27a3…0cb2` |
| Upstream source read | rauc/rauc @ `4fb7c79` (v1.15.2 tree), tianocore/edk2 @ `fbe0805` (edk2-stable202502) |
| Artefacts | `SHA256SUMS`: 4 bundles, 10 UKIs, `disk.img`, `bundles.img`, vars files, public lab certificates |

## 15. Files

- `scripts/build.sh` (image, keys, UKIs, bundles; runs as root in the Lima VM), `scripts/run-tests.py` (T1–T7), `scripts/e1-factory-fallback.py` (E1).
- `logs/driver-run{1,2}.log`, `logs/serial-run{1,2}-trimmed.log`, `logs/driver-e1.log`, `logs/serial-e1-trimmed.log`, `logs/build-run2.log`, `logs/build-run1-failed.log`, `logs/versions.txt`. Serial logs are trimmed to the lines the verdicts use. The guest has no network, so it has no IP addresses; host paths are masked to `~/`; the LUKS recovery key was never printed.
- `PREREGISTRATION.sha256` (hash and UTC time of the README as pre-registered, before any build), `SHA256SUMS`, `image-packages.txt`.
- Claims: `../../claims/LAB-secureboot-rauc.csv`; sources: `../../sources/LAB-secureboot-rauc.md`.
- Not committed (deleted with the VM): disk images, bundles, UKIs, every private key (PK, KEK, db, RAUC CA, PCR policy) and the full serial logs.
