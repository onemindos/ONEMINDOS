# QEMU battery, owner recovery on the box: pass/fail criteria (pre-registered)

**Status:** PRE-REGISTERED. Written 2026-11-25 before the step it judges (`recoveryconsole.py`, run by `firstboot.py`) was implemented or run. Its sha256 at that moment is in `PREREGISTRATION.sha256`. Nothing here may change afterwards except typo fixes; any other change is a new, dated section at the end. Results never live here (they go to the harness output and CI logs).

**Serves:** gateway permissions design 25c (recover owner access at the box with the printed emergency kit, in person), D-028 (wait times and recovery paths) and D-020 (the kit is the owner's way back in). The PR that adds the console menu (`onemindd recover-owner` on tty3, `onemind-recovery-console.service`) also changes logind (`NAutoVTs=2`, `ReserveVT=0`) so no login prompt takes tty3. This battery proves on the image that the menu is on tty3 and that the admin login on tty2 still works. **Does not replace** `CRITERIA-FIRSTBOOT.md` (F15 still judges the tty2 login with a password through `login(1)` on a pseudo-terminal).

## 1. Starting state and rules

- RC1 runs on the slot-A boot of the first-boot battery (`firstboot.py`, board x86_64-efi), right after F15 and before the F3 reboot, from the hub's root shell on the serial console.
- The battery's VM has no display (`-vga none`), so nobody looks at a screen. What a person at the box would see on a text console is read from the kernel's own copy of that console's screen, `/dev/vcsN` (root only). `chvt N` switches the visible console as the keys Ctrl+Alt+FN would.
- RC1 types nothing on any console, enters no key, signs nobody in and changes no setting. It switches the visible console back to tty1 at the end.
- Nothing leaves the VM (`-nic user,restrict=on`).

## 2. Tests

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| RC1 | The recovery menu is on tty3, the admin login is still on tty2, and no login prompt takes tty3 or the consoles after it | **(a) Unit:** `systemctl is-enabled onemind-recovery-console.service` prints `enabled`, and within 60 s `systemctl is-active` prints `active`; `systemctl show -p NRestarts --value` is `0` or `1` (not a crash loop hidden by `Restart=always`). **(b) Menu on tty3:** after `chvt 3`, within 30 s `/dev/vcs3` contains the text `Press Enter to start` and `OneMind owner recovery`. **(c) No getty on tty3:** `getty@tty3.service` and `autovt@tty3.service` are not `active`. **(d) logind:** `systemd-analyze cat-config systemd/logind.conf` shows `NAutoVTs=2` and `ReserveVT=0` as the last uncommented setting of each. **(e) tty2 login still there:** `getty@tty2.service` is `enabled` and `active`, and after `chvt 2`, within 30 s `/dev/vcs2` contains `login:`. **(f) No login on tty4:** after `chvt 4` and 5 s, `autovt@tty4.service` and `getty@tty4.service` are not `active`, and `/dev/vcs4` does not contain `login:`. Then `chvt 1` | Any sub-check false: the unit not enabled, not active within 60 s or restarted more than once; the menu text missing from tty3; a getty on tty3; logind not configured as stated; no login prompt on tty2; or a login prompt appearing on tty4 |

Required for 25c's "done": RC1 PASS on x86_64-efi. It is written before it was run; a harness bug found on the first run may be fixed and re-run once, named as such, as for the other batteries.

## 3. Not covered (reported, never claimed)

- Typing the kit key on tty3 and using the menu: the battery types nothing on a console. The menu's steps, the gateway routes behind it, the wrong-key wait and the notices are covered by the Go tests (`internal/kitrecovery`) and the gateway tests (`core/tests/test_recovery_kit_console.py`).
- A real screen and keyboard (`DevicePolicy=closed` with `DeviceAllow=/dev/tty3` and `StandardInput=tty-force` on hardware): for the hardware kit.
- The serial console (ttyS0): not wired to the menu; `onemind recovery kit` as root covers a serial shell.
