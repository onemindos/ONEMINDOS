# Lab spike LAB-ubuntu-secureboot (U-SB / LT-VM-20): the Secure Boot + RAUC 1.15.2 suite on Ubuntu 26.04

**Status:** PRE-REGISTERED. Goal, hypotheses, design and pass/fail criteria (sections 1–6) were written 2026-11-11 before any build or test of this spike ran. The sha256 of this file at that moment is in `PREREGISTRATION.sha256` and in `../PREREGISTRATION.md`. Results are added only below the line "Results"; nothing above it changes afterwards except this status line, and any other change is logged in the deviations section.

> **Explain it like I'm the founder.** The base-OS decision (Ubuntu 26.04 by one point) rests on one score: "Secure Boot works with our update design". That score was earned by two lab runs that used **Debian** as the operating system inside the test machine, not Ubuntu. The critic said: the Ubuntu test needs no hardware, only the same virtual machine, so run it instead of leaving it to you. This spike does exactly that. It takes the Debian Secure Boot test kit (`../secureboot-1152/`), swaps the operating system inside the image for Ubuntu 26.04 (Ubuntu's kernel, Ubuntu's systemd, Ubuntu's default boot-time helper "dracut"), and runs the same "break it on purpose" tests. The answer was fixed in writing beforehand (01 §3.1.6 h): if Ubuntu passes unchanged twice, Ubuntu keeps its point; if it fails, or only passes after we change the disk layout or the boot chain, Ubuntu loses the point and the rules give the base-OS decision to bootc.

## 1. Goal

Run the `../secureboot-1152/` suite (T0–T6, T8 for the verdict; T7 bonus, T9 and E1 recorded) on an **Ubuntu 26.04 LTS ("resolute") amd64** image built the same way, as the U-SB event of the pre-registered S1 decision map (`01-FOUNDATION-DECISION.md` §3.1.6 h; `evidence/scorecard-weights.md` §8, FIX4 row; `22-HARDWARE-LAB-TEST-PLAN.md` LT-VM-20; critic pass-5 P5-1). The map's wording is the test: *"the `lab/secureboot-1152` battery on Ubuntu 26.04: Ubuntu kernel, systemd 259, Ubuntu's default initramfs generator, OneMind's RAUC `efi` + signed UKIs"*.

## 2. Hypotheses

- **HS1 (same verdicts).** Every T0–T6 and T8 verdict of `../secureboot-1152/` repeats on Ubuntu 26.04 in two runs, with the same BootNext/BootOrder sequence.
- **HS2 (dracut UKI boots).** A UKI built from Ubuntu's kernel and a **dracut** initramfs (Ubuntu's default generator) boots the `root=PARTUUID=…` slot with the unchanged signed command line.
- **HS3 (TPM path).** systemd-cryptsetup and systemd-cryptenroll from Ubuntu's systemd seal and unseal the LUKS2 data partition to PCR 7 as on Debian, and refuse with Secure Boot off (T6).
- **HS4 (E1 repeats).** The E1 factory-fallback gap repeats (it is firmware behaviour, not base behaviour).
- **HS5 (T9 repeats).** With `rauc.slot=` hidden, RAUC 1.15.2 finds the booted slot from `BootCurrent`, as on Debian.

## 3. Design (fixed before the run)

**Unchanged from `../secureboot-1152/scripts/` (the "kit"):** lab keys and OVMF enrolment (lab PK/KEK/db only, no Microsoft keys); the 01 §4.3 GPT layout; `system.conf` (`bootloader=efi`, `bundle-formats=verity`, the four slots); the UKI recipe (`ukify` from the build VM, `sbsign` with the lab db key, the stub taken from the **image's** `systemd-boot-efi`, the same signed command line including `rauc.slot=`); per-slot UKIs in each `boot` vfat image; the factory UKI on the ESP; the first-boot EFI-entry, data (LUKS2 + TPM2 PCR 7, bonus signed PCR 11), Secure Boot report, core stand-in and health-gate scripts and units; the bundle set (`good` v2, `bad-health` v3, `tampered` v4, `unsigned` v5, `plain-good`); RAUC **v1.15.2 at `4fb7c798d6ae412344fb8f8d310d773046af3441`** for bundle creation (arm64) and in the image (amd64); the QEMU q35 + OVMF Secure Boot + swtpm machine; the test logic of `run-tests.py` and `e1-factory-fallback.py`.

**Changed, and only these (allowed: none is a partition or bootloader change):**
1. **Bootstrap:** `mmdebstrap --variant=minbase --arch=amd64 resolute` from `archive.ubuntu.com/ubuntu` (`main universe`, plus `-updates` and `-security`), `ubuntu-archive-keyring.gpg`, as in `../ubuntu-2604-leg/`. Ubuntu package names: `linux-image-virtual` for `linux-image-amd64`; the rest of the Debian list by the same names where they exist.
2. **Initramfs generator: `dracut`** (Ubuntu 26.04's default [C-LAB-ubuntu-2604-leg-001]) instead of `initramfs-tools`, with Ubuntu's packaged dracut configuration. Because the image is built in a chroot on another machine, two build-environment settings are allowed and logged if needed: `hostonly="no"` and `add_drivers+=` lines. Nothing else in dracut is tuned.
3. **RAUC amd64 build chroot** is Ubuntu `resolute` (`buildd` variant) instead of Debian `trixie`, so the binary links against Ubuntu 26.04's libraries; the runtime-library package list is regenerated from it. Same tag, same commit check.
4. **Test driver:** the OSC-sequence stripping of `../ubuntu-2604-leg/scripts/run-tests.py` (systemd ≥ 258 wraps prompts in OSC 3008 sequences; that spike's D1/D6) is added before run 1. Timeouts may be raised for TCG speed. No check is relaxed.

**Counts as a partition or bootloader change (→ the map's "fail" branch even if tests then pass):** any change to the GPT layout or partition labels; to the `[system]` or slot sections of `system.conf`; to the files and paths on the ESP or the `boot-a`/`boot-b` images; to the UKI recipe or the **signed kernel command line** (adding, removing or changing any word); to the EFI-entry scheme; or any move to GRUB, shim or systemd-boot.

**Environment:** a disposable Debian 13 arm64 Lima VM (`vz`) whose only host mount is this spike's lab folder; amd64 rootfs and RAUC build through qemu-user binfmt; the x86_64 guest under QEMU TCG with **no network device**; VM deleted at the end. Lab keys stay in the VM and are never committed.

**Runs:** one build, then full run 1 and full run 2 (each a fresh copy of the built disk, OVMF vars and a new swtpm state), then E1 on each run's end state.

## 4. Pass / fail criteria (frozen before the run)

Per-test criteria are those of `../secureboot-1152/README.md` §4 (T0–T9, E1), with three Ubuntu substitutions in T0 and T1: "Debian `rauc` package absent" becomes "Ubuntu `rauc` package absent"; the image must show Ubuntu 26.04 in `/etc/os-release` and an Ubuntu kernel; and the initrd inside the UKI must be a dracut image (dracut installed, `initramfs-tools` not installed).

| Spike verdict | When | What it means for the S1 map (01 §3.1.6 h) |
|---|---|---|
| **PASS** | T0–T6 and T8 PASS in **two** full runs, with only the changes allowed in §3 | "U-SB passes unchanged in two runs": no cell moves; D·C3 loses its `doc-only` mark |
| **FAIL** | Any of T1–T6 or T8 fails on the guest side in any full run (a real Ubuntu behaviour, shown in the serial log), **or** a pass needs any change listed under "counts as a partition or bootloader change" | "U-SB fails": D·C3 4 → 3 (variant V3); the frozen result becomes **C (RHEL-family bootc)** |
| **BLOCKED** | The environment cannot run the suite (archive unreachable, VM denied, emulator limit) | No map event; reported as not run, stays a founder test |

Rules for faults that are not Ubuntu behaviour: a **harness** fault (driver regex, timeout, a console-echo match) where the serial log shows the guest did the right thing is logged as a deviation, fixed in the driver only, and the run is repeated; at most four full runs are made, and every run is reported. A failure that a dracut build-environment setting (§3 item 2) cures is a build fix, logged; any other dracut change is not allowed. If dracut cannot produce a bootable UKI with only those settings, the verdict is **FAIL** (the map names Ubuntu's default generator); an `initramfs-tools` re-run may then be made as a **diagnostic only** and does not change the verdict.

T7 (bonus), T9 and E1 are recorded and do not affect the verdict.

## 5. Requirement IDs served

M-2 (security baseline), R-1 (safe updates), R-3 (maintainability), U-4 (data safety), P-7 (bring-your-own x86), F-14. Settles the U-SB event of 01 §3.1.6 (h) and LT-VM-20; closes critic pass-5 P5-1; feeds DC-18 / REC-DEC-08.

## 6. Glossary

| Term | Meaning |
|---|---|
| UKI (unified kernel image) | One signed EFI file holding the kernel, the initramfs and the kernel command line, so the firmware checks all three with one signature |
| initramfs / dracut | The small boot-time filesystem that finds and mounts the real root; dracut is the tool Ubuntu 26.04 uses by default to build it (Debian uses initramfs-tools) |
| `doc-only` | A scorecard mark: the score rests on documentation, not on a lab run on that base |
| D·C3 | Row D (Ubuntu 26.04 + RAUC) of the S1 base-OS scorecard, criterion C3 (secure-boot and update-security path) |
| Other terms | See `../secureboot-1152/README.md` §6 and `../secureboot-rauc/` §6 |

---

## Results

**Verdict: BLOCKED (environment), not run.** Recorded 2026-11-11T15:56Z under the §4 BLOCKED rule. **No map event:** the S1 decision of record and every cell stay as they are, and U-SB stays open [C-FIX5-001, C-FIX5-002].

> **Explain the result like I'm the founder.** We set the test up exactly as promised and froze the rules first. But the test needs Ubuntu's software, and in this run's environment the Ubuntu and Canonical web addresses are blocked on purpose: every other site we tried still worked, including Debian, Fedora, kernel.org and GitHub. A block on exactly those two names looks deliberate, perhaps to enforce "never contact vendors" now that Canonical is a negotiation party (Z-01). We could have gone around it through another address book or another mirror, but going around a block is not ours to decide, so we did not. The test kit is finished and published here. Anyone with normal internet access can run it in about one and a half to two hours, unattended, with no hardware. Until it runs, the decision still reads "Ubuntu, if this one score holds".

### R.1 What happened

| Step | Result | Evidence |
|---|---|---|
| Pre-registration | Frozen 2026-11-11T15:51:12Z, sha256 `c98a09d1…f8db` | `PREREGISTRATION.sha256`, `../PREREGISTRATION.md` |
| Kit | Written: `scripts/` = the `../secureboot-1152/` kit with only the §3 changes (`build.sh` 44 diff lines: bootstrap, dracut, observations; `build-rauc.sh` 11: Ubuntu build chroot; `run-tests.py` 17: OSC stripping; `e1-factory-fallback.py`, `trim-logs.sh` byte-identical). **Not yet executed**, so it may still need a build fix of the kind §4 allows | `scripts/`, `SHA256SUMS` |
| Lab VM | Created (Debian 13.7 arm64, `vz`, lab folder only), tools installed, deleted at 15:56Z | `logs/env-probe.log` |
| Ubuntu archive | `archive.ubuntu.com` and `security.ubuntu.com` **do not resolve** on the host or in the VM. `ubuntu.com` and `canonical.com` do not resolve on the host; `example.org`, `kernel.org`, `fedoraproject.org`, `deb.debian.org` and `github.com` do [C-FIX5-001] | `logs/env-probe.log` |
| T0–T9, E1 | **Not run** (T0 needs the archive) | — |

### R.2 Deviations (honest log)

1. **One diagnostic read past the block (disclosed).** Before recognising the pattern as a deliberate block, the agent asked a public resolver from inside the VM for the archive's address and read the 26.04 `Release` file once by IP (it named `Suite: resolute`, `Version: 26.04`). Nothing was downloaded beyond that file and nothing was built from it. It is not cited as evidence. After the host probe showed that only the Ubuntu and Canonical names fail, the agent stopped and used no alternative resolver, `/etc/hosts` entry or third-party Ubuntu mirror.
2. **The kit is unexecuted.** The adapted scripts pass `bash -n` and a Python parse only. A first real build may need a build-environment fix (for example a dracut `hostonly="no"` setting) that §3 item 2 allows and the run must log.

### R.3 What decides it, and how to run it

The pre-registered map (01 §3.1.6 h) is unchanged: **PASS twice unchanged → D stays (D·C3 loses `doc-only`); FAIL, or a pass only after a partition or bootloader change → C.** Run it wherever `archive.ubuntu.com` resolves (the founder's Mac, any CI runner), or in this research environment once its operator allows the Ubuntu archive or names an approved mirror (open question for the run owner; the agent did not choose one):

```bash
LAB=<lab-dir>/ubuntu-secureboot          # outside the repo
mkdir -p $LAB/scripts $LAB/logs && cp research-output/evidence/lab/ubuntu-secureboot/scripts/* $LAB/scripts/
limactl create --name lab-usb --tty=false --vm-type vz --cpus 10 --memory 16 --disk 80 \
  --mount-only $LAB:w --mount-type virtiofs template:debian-13 && limactl start lab-usb
limactl shell lab-usb -- sudo apt-get install -y mmdebstrap qemu-user-binfmt qemu-system-x86 ovmf rauc gdisk \
  dosfstools mtools e2fsprogs squashfs-tools openssl python3 sbsigntool efitools swtpm swtpm-tools \
  python3-virt-firmware systemd-ukify tpm2-tools python3-pefile git build-essential meson ninja-build pkgconf \
  libglib2.0-dev libssl-dev libjson-glib-dev libdbus-1-dev libfdisk-dev libcurl4-openssl-dev libnl-genl-3-dev ubuntu-keyring
limactl shell lab-usb -- sudo bash -c "OUT=/var/lab/sbout bash $LAB/scripts/build-rauc.sh"   # RAUC 1.15.2, Ubuntu libs
limactl shell lab-usb -- sudo bash -c "OUT=/var/lab/sbout bash $LAB/scripts/build.sh"        # T0
for r in 1 2; do
  limactl shell lab-usb -- sudo python3 -I $LAB/scripts/run-tests.py --out /var/lab/sbout --run /var/lab/sbrun$r --log $LAB/logs/serial-run$r.log
  limactl shell lab-usb -- sudo python3 -I $LAB/scripts/e1-factory-fallback.py --run /var/lab/sbrun$r --log $LAB/logs/serial-e1-run$r.log
done
limactl delete -f lab-usb
```

**PASS:** `run-tests.py` exits 0 in both runs, and `build.log` shows Ubuntu 26.04, an Ubuntu kernel, dracut installed and `initramfs-tools` absent, RAUC 1.15.2 and the v4/v5 UKI signature split. **FAIL:** any T1–T6 or T8 failure the serial log shows is real, or any change from the §3 "counts as a partition or bootloader change" list. Append the results below this section and apply the map row in 01 §3.1.6 (h).

### R.4 Files

`README.md` (this file), `PREREGISTRATION.sha256`, `scripts/` (the kit), `logs/env-probe.log` (host paths masked), `SHA256SUMS`. Claims: `../../claims/FIX5.csv`; sources: `../../sources/FIX5.md`.
