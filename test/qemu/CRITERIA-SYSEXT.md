# QEMU battery, signed host extensions only (T-W19-01): pass/fail criteria (pre-registered)

**Status:** PRE-REGISTERED. Written 2026-11-22 before the signed-only extension policy (`os/rootfs/layers/base/usr/lib/systemd/system/systemd-sysext.service.d/`, `systemd-confext.service.d/`, `/usr/lib/onemind/sysext-guard`) was booted in any image and before `sysextguard.py` existed. Its sha256 at that moment is in `PREREGISTRATION.sha256` and in the commit that adds it, which comes before the code. Nothing here may change afterwards except typo fixes; any other change is a new, dated section at the end. Results never live here (they go to the run's `results.json`, the PR and issue #186).

**Serves:** T-W19-01 of issue #186 (PLG-SOCK-01, plugin sockets E2-E4), which decides founder decision **Z-22**: other developers may publish signed host-level plugins in release 1 only if an unsigned or wrongly signed extension never merges after a reboot or an A/B slot switch. If this test fails, only OneMind-built host extensions ship. Also serves Z-21 (E3 frozen at v1), D-007 (Debian 13 base) and the read-only image with RAUC A/B. **Does not replace** `CRITERIA.md` or `CRITERIA-FIRSTBOOT.md`; those keep their own criteria and must still pass on the same image.

## 1. Words used here

- **sysext / confext:** systemd's system extensions (add files under `/usr` and `/opt`) and configuration extensions (add files under `/etc`). systemd merges them with overlayfs at boot. They are how OneMind host add-ons (socket E3) reach the read-only image.
- **Signed image:** a GPT disk image (DDI) with a data partition, its dm-verity hash partition and a signature partition holding a PKCS#7 signature of the verity root hash. dm-verity checks every block read against that root hash, so a signed root hash pins the whole content.
- **Trusted test key:** a throwaway key pair made inside the guest's `/run` for one run. Its certificate is copied into `/usr/lib/verity.d/` of the booted slot by remounting that slot's root read-write for that one copy. This stands in for the OneMind signing certificate a release image carries in its read-only `/usr`. The private key never leaves the guest's `/run` and is never in git.
- **Wrong test key:** a second throwaway key pair. Its certificate is never placed in `/usr`.
- **One-time root:** an attacker who had a root shell once, while the box ran, and wants an extension of their choice to merge on later boots. The plain one-time root (X3, X4) writes wherever the running box lets root write without rewriting the slot: the data partition (where `/var/lib/extensions` and `/var/lib/confexts` live), `/run`, and any `/etc` path. The slot-rewriting one-time root (X5, O2) also remounts the slot root read-write.
- **Merged:** the extension's marker file is visible on the running system and `systemd-sysext status` / `systemd-confext status` lists it.

## 2. Starting state and rules

- The fixture is the slot-A disk and `bundles.img` of `make fixtures` (the same as `CRITERIA-FIRSTBOOT.md` §1, NoCloud seed with `onemind: {role: hub}`). The harness copies the disk; the battery's own fixture is not changed.
- Test extension images are built **inside the guest** with the image's own tools (`mksquashfs`, `veritysetup`, `openssl`, `sfdisk`) by a script the harness puts on the seed disk. Every image carries an extension-release file with `ID=debian` and `SYSEXT_LEVEL=1` (sysext) or `CONFEXT_LEVEL=1` (confext), and one marker file: `/usr/lib/onemind-tw19/<name>` (sysext) or `/etc/onemind-tw19/<name>` (confext).
- The images: `good.raw` (usr + usr-verity + usr-verity-sig, signed with the trusted test key), `wrong.raw` (the same layout, signed with the wrong test key), `unsigned.raw` (usr + usr-verity, no signature partition), `naked.raw` (a bare squashfs, no partition table), `plaindir/` (a plain directory with the same tree); confext: `confgood.raw` (root + root-verity + root-verity-sig, trusted key), `confunsigned.raw` (root + root-verity, no signature), `confdir/` (a plain directory).
- Only throwaway keys are used. No key or certificate is written to the repository, the fixtures or the logs.
- A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS. A harness bug may be re-run once and is named as such.
- Every verdict records the board, KVM or TCG, and the host CPU count.
- Timeouts (wall clock): first-boot configuration line 900 s; gate result as in `CRITERIA.md`; root shell after each boot 300 s.

## 3. Tests

Why the signed images get their own boots (X1, X6): systemd may either skip one refused image and merge the rest, or refuse the whole set when one image fails. Both are safe; so the positive control runs with only signed images present, and the negative tests judge only the images that must never merge.

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| X0 | The image is wired for signed-only extensions (first boot, slot A) | `/usr/lib/os-release` has `SYSEXT_LEVEL=1` and `CONFEXT_LEVEL=1`; `systemd-sysext.service` and `systemd-confext.service` are enabled; `systemctl cat` of each shows an `ExecStartPre=` running `/usr/lib/onemind/sysext-guard` and an `ExecStart=` with `--image-policy=root=signed+absent:usr=signed+absent` (sysext) or `--image-policy=root=signed+absent` (confext); `/var/lib/extensions` and `/var/lib/confexts` resolve to directories under `/data/state/`; `systemd-sysext.service` lists `k3s.service` in `Before=`; no `/etc/verity.d` and no `/run/verity.d` exist | Any item missing |
| X1 | Signed images merge (positive control, reboot, slot A) | With the trusted certificate in `/usr/lib/verity.d/` and only `good` in `/var/lib/extensions` and `confgood` in `/var/lib/confexts`, after `systemctl reboot`: both are merged; at least one dm-verity device is active; `systemd-sysext.service` became active before `k3s.service` first started (monotonic timestamps) | Either is not merged, no verity device, or k3s started first |
| X2 | Wrongly signed, unsigned and naked raw images never merge (reboot, slot A) | `wrong`, `unsigned`, `naked` added to `/var/lib/extensions` and `confunsigned` to `/var/lib/confexts`; after `systemctl reboot` none of these four is merged (what happens to `good` and `confgood` in this boot is recorded) | Any of the four merged |
| X3 | A planted key and drop-in do not survive a reboot (plain one-time root, slot A) | Root writes the wrong certificate to `/run/verity.d/` and a drop-in `/run/systemd/system/systemd-sysext.service.d/99-tw19-plant.conf` that clears `ExecStartPre=` and runs `systemd-sysext refresh` with no policy, and tries the same under `/etc/verity.d/` and `/etc/systemd/system/systemd-sysext.service.d/`. PASS if both `/etc` writes are refused, and after `systemctl reboot` neither planted file exists and `wrong`, `unsigned`, `naked` and `confunsigned` are **not** merged | An `/etc` write succeeds, a planted file survives, or one of the four merged |
| X4 | A plain directory never merges (reboot, slot A) | With `plaindir/` added to `/var/lib/extensions` and `confdir/` to `/var/lib/confexts`, after `systemctl reboot`: neither directory is merged, the journal of each unit shows an `ONEMIND-SYSEXT-GUARD: refused` line naming it, and **nothing** is merged in that boot (the guard fails closed) | A directory merged, no refusal line, or any extension merged |
| X5 | A slot switch drops everything the old slot was given (slot-rewriting one-time root, A to B) | The directories from X4 are removed. Root remounts slot A's root read-write and writes the wrong certificate to `/etc/verity.d/` and the X3 drop-in to `/etc/systemd/system/systemd-sysext.service.d/`, then installs `good.raucb` and reboots. PASS if the gate logs `RESULT mark-good slot=B`, slot B has no `/etc/verity.d`, no planted drop-in and no `/usr/lib/verity.d` certificate, and **none** of `good`, `wrong`, `unsigned`, `naked`, `confgood`, `confunsigned` is merged (trust comes only from the booted slot's `/usr`) | Install or commit fails, a planted file is on B, or any extension merged |
| X6 | The signed images merge on the new slot once that slot trusts its key (reboot, slot B) | `wrong`, `unsigned`, `naked`, `confunsigned` moved out of the extension folders; the trusted certificate copied into slot B's `/usr/lib/verity.d/`; after `systemctl reboot` `good` and `confgood` are merged | Either is not merged |
| X7 | Wrongly signed, unsigned and naked raw images never merge on the new slot (reboot, slot B) | The four moved back; after `systemctl reboot` none of `wrong`, `unsigned`, `naked`, `confunsigned` is merged | Any of the four merged |

Observations (recorded, never pass or fail):

| ID | What is recorded |
|---|---|
| O1 | During X3, before the reboot: whether `systemctl daemon-reload` plus a restart of `systemd-sysext.service` merges `wrong` while the plant is in place. This shows the plant was real; root at run time is outside this test. |
| O2 | After X7, on slot B: root remounts the slot root read-write, writes the X3 drop-in to `/etc/systemd/system/systemd-sysext.service.d/` and the wrong certificate to `/etc/verity.d/`, and reboots. Whether `wrong` merges is recorded. A root that rewrites the running slot can change `/usr` itself; stopping that is the job of a dm-verity protected root and Secure Boot (#148), not of this guard. |

## 4. Boards and verdicts for this task

- **x86_64-efi** (OVMF) runs X0-X7, O1 and O2. Other boards are reported, never required.
- On a host without KVM the run uses TCG and says so; a timeout missed only because TCG is slower is **BLOCKED (TCG timing)**, and the test must then pass on a KVM host before it counts.
- **T-W19-01 passes** when X0-X7 are all PASS on x86_64-efi. Any FAIL in X1-X7 is a T-W19-01 failure and goes to the founder for Z-22 as is.
