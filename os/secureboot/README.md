# Secure Boot and signed UKI (S-13; #148 slice 1: both slots)

**What this is, in plain words.** When a PC starts, its firmware (UEFI) can refuse to run any program that is not
signed by a key the owner put in the firmware ("Secure Boot"). OneMind OS adds two signed files to its boot path:
the GRUB boot program and one **UKI** (unified kernel image) per slot. A UKI is a single EFI file that holds the
kernel, the initrd and the kernel command line. Because the command line is inside the signed file, nobody at the
boot menu can add `init=/bin/sh` to get a root shell. Without Secure Boot, anyone with a keyboard can.

Boot chain (`--boot efi` + `--sb-key/--sb-cert` build only; the normal dev image is unchanged and keeps GRUB):

    UEFI firmware (db = owner key)
      -> BootNext (one trial boot of a new slot) or else the first good entry in BootOrder:
         entry "A" -> \EFI\Linux\onemind-A.efi on onemind-boot-a   (signed UKI: root=PARTUUID of system-a, rauc.slot=A)
         entry "B" -> \EFI\Linux\onemind-B.efi on onemind-boot-b   (signed UKI: root=PARTUUID of system-b, rauc.slot=B)
      -> no entries yet (new box, firmware reset): the fallback file EFI/BOOT/BOOTX64.EFI = the signed slot-A UKI

There is no boot loader to attack: the firmware starts the signed UKI itself, and the firmware's boot entries are
the slot switch. **How a slot gets chosen, in plain words.** RAUC (the update tool) has an `efi` backend
(`bootloader=efi` in `/etc/rauc/system.conf`): it does not write a GRUB file, it edits the firmware's list of boot
entries with `efibootmgr`. After `rauc install` it sets **BootNext** to the new slot: the firmware starts that entry
once and then forgets it. If that boot comes up healthy, the health gate runs `rauc status mark-good`, which moves
the entry to the front of **BootOrder** (the permanent list). If the new slot crashes, hangs (the watchdog resets
the box) or the power goes, BootNext is already used up, so the next start goes to the old slot at the front of
BootOrder, and the gate's "fell-back" mode marks the trial bad. A slot counts as good while its entry is in
BootOrder. Under GRUB a new slot gets three tries; under the efi backend it gets one.

**Why not keep GRUB as the slot picker?** Tried under OVMF Secure Boot on 2026-11-21 with Debian's GRUB 2.12, signed
and with its modules built in. Chainloading a signed UKI fails twice over: `error: shim_lock protocol not found`,
and with `--disable-shim-lock` `error: verification requested but nobody cares`. GRUB only chain-loads under Secure
Boot through shim (Microsoft-signed, a different trust story than owner-held keys). So the selector must be the
firmware (RAUC's efi backend, as the hardware lab proved) or systemd-boot, not GRUB.

## What the code does today
- `os/assemble/uki.py`: build a UKI with `ukify` (systemd 257 in Debian 13) and sign it with `sbsign`.
- `os/assemble/assemble.py tree --boot efi`: RAUC's `efi` backend in `/etc/rauc/system.conf` (no `grubenv`,
  `efi-use-bootnext=true`, boot partitions as `[slot.efi.N]` with `parent=rootfs.N`, from `os/rauc/efi-slots.conf.in`),
  the first-boot unit `onemind-efi-entries` (`os/rauc/`) that creates the firmware entries `A` and `B` before the
  health gate, and the gate's reader for slot state in firmware variables (`os/gate/gate-slot-env-efi`, installed as
  `/usr/lib/onemind/gate-slot-env`). The gate's trial logic is unchanged. `efibootmgr` is in the amd64 package list.
- `assemble.py disk --sb-key K --sb-cert C` (needs a `--boot efi` tree): one signed UKI per slot, both in one boot
  image on `onemind-boot-a`; `onemind-boot-b` stays empty until the first update (a stray entry "B" then fails to
  load instead of starting a kernel with no root); slot A's UKI is also the ESP fallback file.
- `assemble.py bundle --sb-key K --sb-cert C --work W`: the bundle carries the release's signed UKIs as
  `[image.efi]` (`efi.vfat`), which RAUC writes to the target slot's boot partition together with its root.
  `assemble.py image --sb-key/--sb-cert` does all of this in one go.
- `make secureboot-test` (`test/qemu/secureboot.py`, criteria `test/qemu/CRITERIA-SECUREBOOT.md`): boots under
  OVMF Secure Boot with **throwaway test keys made inside the run** and checks SB1 (signed chain boots), SB2 (changed
  UKI refused), SB3 (UKI signed by an unknown key refused), SB4 (unsigned boot file refused) and SB5 (after
  `rauc install` of a bundle with signed UKIs, slot B boots its own UKI with Secure Boot on and the gate commits it).
  CI runs it in the image workflow on a KVM runner.

## What the founder's signing ceremony must add (nothing here creates or stores a real key)
1. **Make the keys offline**: a UKI/boot signing key and certificate (the `db` key) and, separately, PK and KEK.
   Keep them on a hardware token or an offline machine, with two backups in two places. Talos asks its owner for
   the same: a UKI signing key, a separate PCR signing key, and an optional PK/KEK/db enrollment set
   (docs.siderolabs.com/talos/v1.10/platform-specific-installations/bare-metal-platforms/secureboot).
2. **Sign in the release pipeline, not on the build workers**: the release job calls `assemble.py --sb-key/--sb-cert`
   (or a signing service) so the key never sits in a CI runner. Decide HSM or token (a Z-xx decision for Zeus).
3. **Sign the UKIs that ride in the update bundle** at release time (`assemble.py bundle --sb-key/--sb-cert`),
   because the box never holds the key.
4. **Firmware enrollment, two modes**: (a) OneMind-keyed boxes: enroll our `db` certificate (setup mode + `.auth`
   files on the ESP, as Talos does); (b) **sovereign mode**: the owner enrolls their own keys and re-signs
   (D-009 note, Z-19 #148). Either way no Microsoft keys are needed because there is no shim.
5. **Revocation and rotation**: a `dbx` plan for a leaked key, a yearly `db` rotation rehearsal, and a minimum-version
   rule so an old, validly signed UKI cannot boot on a newer root (SB-4, the gate's kernel/root version match).
6. **Real hardware check** on the Dell all-in-one and the R530 (their firmware may need setup mode toggled).

## Left after this slice (follow-ups on #148, not hidden)
- **Rollback under Secure Boot**: a test that boots B, fails the gate and falls back to A with Secure Boot on (issue
  #881, wave E; the lab proved it in `research-output/evidence/lab/secureboot-1152`, T3).
- **Anti-downgrade** (lab finding E1, SB-3/SB-4): the ESP fallback file is a slot-A UKI pinned to `rauc.slot=A`, and
  any older UKI signed by the same key still boots. Replace the fallback with a recovery-only UKI, check the kernel's
  version against the root's before `mark-good`, and add SBAT or db/dbx rotation.
- **Sovereign mode** (founder decision 2026-11-22): the owner can take over the box's Secure Boot keys, with physical
  presence, a clear warning, the key state on the dashboard, and OneMind's key kept enrolled next to the owner's so
  updates keep working.
- **One image for both routes**: today the Secure Boot image is its own build (`--boot efi`); the dev image keeps
  GRUB. Choosing the route on the box at first boot is a later step.
- dm-verity on the booted root (audit item 10): today the root is mounted `ro` but not hash-verified (only the bundle is
  verity-protected). The root hash then goes into the signed command line, which is what completes "firmware to root".
- TPM: seal the `/data` key to PCR 7 and a signed PCR 11 policy (audit item 11; IMG-LUKS-01 is open as PR 577).
- The GRUB menu lock (PR 575) stays the protection for boxes without Secure Boot.
