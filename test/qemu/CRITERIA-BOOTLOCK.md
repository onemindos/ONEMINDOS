# QEMU battery, boot menu lock: pass/fail criteria (pre-registered)

**Status:** PRE-REGISTERED. Written 2026-11-21 before the GRUB superuser lock (`os/assemble/grub.cfg.in`, `ensure_boot_lock` in `onemind_firstboot.py`) was booted in any image or `bootlock.py` was run. Its sha256 at that moment is in `PREREGISTRATION.sha256`. Nothing here may change afterwards except typo fixes; any other change is a new, dated section at the end. Results never live here (they go to the run's `results.json` and CI logs).

**Serves:** the image security review of 2026-11-21 (item 6, H-27 interim: until signed UKIs land, the console must not be able to edit the kernel command line), D-007, `docs/security/HARDENING-BACKLOG.md`. **Does not replace** `CRITERIA.md` or `CRITERIA-FIRSTBOOT.md`; those keep their own criteria and must still pass on the same image.

## 1. Starting state and rules

- The fixture is the same as `CRITERIA-FIRSTBOOT.md` §1 (slot-A disk of `make fixtures`, NoCloud seed with `onemind: {role: hub}`). The box is booted from scratch, so first boot creates the boot menu password.
- The password is read only from the guest's **console** (serial log), as the owner token is.
- The test types at GRUB through the serial console, as a person at the machine would. Firmware (OVMF) mirrors GRUB's console to the serial port; the keystroke is sent repeatedly from the moment the `GRUB-RAUC:` line appears until GRUB answers or the kernel starts.
- A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS. A harness bug may be re-run once and is named as such.
- Every verdict records the board, KVM or TCG, and the host CPU count.
- Timeouts (wall clock): first-boot configuration line 900 s; gate result as in `CRITERIA.md`; each GRUB prompt 60 s from the first keystroke.

## 2. Tests

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| B1 | A per-box password is created at first boot and only its hash is stored | The console shows exactly one `ONEMIND BOOT MENU PASSWORD (user onemind` line with a password of five groups of four characters; `/boot/efi/EFI/BOOT/user.cfg` exists, has exactly one line `password_pbkdf2 onemind grub.pbkdf2.sha512.`, and the password text appears **nowhere** in that file or in `/boot/efi/EFI/BOOT/grub.cfg`; `grub.cfg` has no `password_pbkdf2` line of its own | No line, more than one, the password stored in clear, or a hash baked into the image's `grub.cfg` |
| B2 | A normal boot needs nothing | After `systemctl reboot` with **no** keystroke at GRUB, the gate logs `RESULT committed-boot slot=A`, the console shows `already configured` and **no** second `BOOT MENU PASSWORD` line, and `user.cfg` is byte-identical to B1's | A prompt at GRUB, no boot, a new password, or a changed `user.cfg` |
| B3 | Editing an entry asks for a login | At the next boot, sending `e` at the menu makes GRUB print `Enter username:` and the kernel does **not** start while that prompt is open | The editor opens without a login, or the kernel boots past the keystroke without a prompt |
| B4 | A wrong password does not open the editor | Username `onemind` and a wrong password: GRUB prints `error: access denied` (or asks for a username again) and the editor text (`Minimum Emacs-like screen editing`) is not shown | The editor opens |
| B5 | The shell (`c`) is locked the same way | Sending `c` at the menu makes GRUB print `Enter username:` and the `grub>` prompt is not shown | A `grub>` prompt without a login |
| B6 | The box's own password opens the editor | Username `onemind` and the password from B1: the editor text (`Minimum Emacs-like screen editing`) is shown | Refused, or no editor |

## 3. Boards and verdicts for this task

- **x86_64-efi** (OVMF) runs B1-B6. Other boards are reported, never required.
- On a host without KVM the run uses TCG and says so; a timeout missed only because TCG is slower is **BLOCKED (TCG timing)**, and the test must then pass on a KVM host (CI) before it counts.
- Required for this task's "done": B1-B6 PASS on x86_64-efi.
