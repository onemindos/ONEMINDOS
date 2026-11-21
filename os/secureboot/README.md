# Secure Boot and signed UKI (S-13, first slice)

**What this is, in plain words.** When a PC starts, its firmware (UEFI) can refuse to run any program that is not
signed by a key the owner put in the firmware ("Secure Boot"). OneMind OS adds two signed files to its boot path:
the GRUB boot program and one **UKI** (unified kernel image) per slot. A UKI is a single EFI file that holds the
kernel, the initrd and the kernel command line. Because the command line is inside the signed file, nobody at the
boot menu can add `init=/bin/sh` to get a root shell. Without Secure Boot, anyone with a keyboard can.

Boot chain after this slice (`--sb-key/--sb-cert` build only; the normal dev image is unchanged and keeps GRUB):

    UEFI firmware (db = owner key)  ->  signed slot-A UKI as the fallback boot file (EFI/BOOT/BOOTX64.EFI)
      -> kernel + initrd + signed command line (root=PARTUUID=..., ro, rauc.slot=A)

There is no boot loader to attack: the firmware starts the signed UKI itself. Per-slot UKIs also sit in
`EFI/Linux/` on `onemind-boot-a` and `onemind-boot-b`, ready for slot selection (see "Left").

**Why not keep GRUB as the slot picker?** Tried under OVMF Secure Boot on 2026-11-21 with Debian's GRUB 2.12, signed
and with its modules built in. Chainloading a signed UKI fails twice over: `error: shim_lock protocol not found`,
and with `--disable-shim-lock` `error: verification requested but nobody cares`. GRUB only chain-loads under Secure
Boot through shim (Microsoft-signed, a different trust story than owner-held keys). So the selector must be the
firmware (RAUC's efi backend, as the hardware lab proved) or systemd-boot, not GRUB.

## What the code does today
- `os/assemble/uki.py`: build a UKI with `ukify` (systemd 257 in Debian 13) and sign it with `sbsign`.
- `os/assemble/assemble.py disk or image --sb-key K --sb-cert C`: one signed UKI per slot; slot A is the ESP boot file.
- `make secureboot-test` (`test/qemu/secureboot.py`, criteria `test/qemu/CRITERIA-SECUREBOOT.md`): boots under
  OVMF Secure Boot with **throwaway test keys made inside the run** and checks SB1 (signed chain boots), SB2 (changed
  UKI refused), SB3 (UKI signed by an unknown key refused), SB4 (unsigned boot file refused). The first CI run is the
  image workflow on a KVM runner; the build workers cannot run QEMU boots.

## What the founder's signing ceremony must add (nothing here creates or stores a real key)
1. **Make the keys offline**: a UKI/boot signing key and certificate (the `db` key) and, separately, PK and KEK.
   Keep them on a hardware token or an offline machine, with two backups in two places. Talos asks its owner for
   the same: a UKI signing key, a separate PCR signing key, and an optional PK/KEK/db enrollment set
   (docs.siderolabs.com/talos/v1.10/platform-specific-installations/bare-metal-platforms/secureboot).
2. **Sign in the release pipeline, not on the build workers**: the release job calls `assemble.py --sb-key/--sb-cert`
   (or a signing service) so the key never sits in a CI runner. Decide HSM or token (a Z-xx decision for Zeus).
3. **Ship the UKI inside the update bundle** (left, see below): the new slot's UKI must be built and signed at
   release time, because the box never holds the key.
4. **Firmware enrollment, two modes**: (a) OneMind-keyed boxes: enroll our `db` certificate (setup mode + `.auth`
   files on the ESP, as Talos does); (b) **sovereign mode**: the owner enrolls their own keys and re-signs
   (D-009 note, Z-19 #148). Either way no Microsoft keys are needed because there is no shim.
5. **Revocation and rotation**: a `dbx` plan for a leaked key, a yearly `db` rotation rehearsal, and a minimum-version
   rule so an old, validly signed UKI cannot boot on a newer root (SB-4, the gate's kernel/root version match).
6. **Real hardware check** on the Dell all-in-one and the R530 (their firmware may need setup mode toggled).

## Left after this slice (follow-ups, not hidden)
- **Slot B and A/B rollback under Secure Boot** (the main gap): choose the slot with RAUC's `efi` bootloader backend
  (firmware `BootOrder` entries pointing at each slot's signed UKI; lab-proven with RAUC 1.15.2) and keep the health
  gate's trial counting on it. The RAUC bundle must carry a signed UKI per slot and write it to `onemind-boot-a/b`.
  Then a rollback test that boots B, fails the gate and falls back to A under Secure Boot. Today a Secure Boot image
  always boots slot A, and it still reads and writes `grubenv`, so the gate's commit works.
- dm-verity on the booted root (audit item 10): today the root is mounted `ro` but not hash-verified (only the bundle is
  verity-protected). The root hash then goes into the signed command line, which is what completes "firmware to root".
- TPM: seal the `/data` key to PCR 7 and a signed PCR 11 policy (audit item 11; IMG-LUKS-01 is open as PR 577).
- The GRUB menu lock (PR 575) stays the protection for boxes without Secure Boot.
