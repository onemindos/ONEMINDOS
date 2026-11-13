# QEMU battery, USB installer: pass/fail criteria (pre-registered)

**Status:** PRE-REGISTERED. Written 2026-11-12 before the USB installer (`os/boards/installer-x86_64/`) was written, built or booted. Its sha256 at that moment is in `PREREGISTRATION.sha256` and in the commit that adds it, which comes before the code it judges. Nothing here may change afterwards except typo fixes; any other change is a new, dated section at the end. Results never live here (they go to the run's `results.json` and CI logs).

**Serves:** the founder's request of 2026-11-12 (every deployment boots straight into OneMind), D-007, brief 30 B2. **Does not replace** `CRITERIA.md` or `CRITERIA-FIRSTBOOT.md`; the image the installer writes must still pass those on its own.

## 1. Starting state and rules

- Two virtual disks and nothing else: the **installer stick** (attached as USB mass storage, first in the boot order, opened copy-on-write so the run cannot change the file) and an **empty target disk** (NVMe, a fresh all-zero sparse file of 40 GiB, larger than the 32 GiB image). No NoCloud seed, no test overlay, no serial autologin on either system.
- The payload on the stick is a **development image** built by `make image BOARD=x86_64-efi` (throwaway signing CA). The expected image sha256 is the one in that build's `SHA256SUMS`.
- Every input the test gives goes through the installer's own console menu (serial console, plain text mode) or its LAN web page, as a person would. Nothing is written to the target from outside the guest.
- The owner token of the installed box is read only from the guest's console.
- A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS. A harness bug may be re-run once and is named as such.
- Every verdict records KVM or TCG and the host CPU count.
- Timeouts (wall clock): installer menu 600 s from QEMU start; write + verify 3600 s from the confirmation; installed system first-boot line 900 s from the reboot; gateway `/healthz` 900 s; node listed 600 s after `/healthz`.

## 2. Tests

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| I1 | Installer boots and lists the target | Within the timeout the console shows the installer menu listing the NVMe target with its size, and does **not** list the installer stick itself; the LAN page (`GET /` on :8080) returns HTTP 200, names the same target and says the disk will be erased | No menu, the stick offered as a target, or no page |
| I2 | Erase needs explicit confirmation | Choosing the target and answering the confirmation with anything other than the exact confirmation word leaves the target untouched (the sparse file still has no allocated blocks) and returns to the menu; a web install request without the one-time code shown on the console is refused (HTTP 403) and the target is still untouched | Any byte written to the target without the confirmation word, or a web install accepted without the code |
| I3 | Write with verification | After the confirmation (role `hub`), the console reports the payload checksum verified, then the written disk read back and its sha256 **equal to the dev image's `SHA256SUMS` entry**, then `done`, then the machine reboots with no further input | Mismatch, no read-back verification, an error, or no reboot |
| I4 | Installed disk layout | After the run, the target's GPT has the image's partition labels and partition UUIDs, its backup header is at the end of the 40 GiB disk, `onemind-data` extends to the end of the disk, and its ESP holds `onemind.conf` (or `onemind.conf.applied`) with `role = hub` | Any label or UUID differs, the backup header is not at the end, data not grown, or the role not set |
| I5 | Installed disk boots into OneMind | Booting the target (the stick removed, or left in when the installer set the firmware's next boot to the target) with no input: the console shows `ONEMIND-FIRSTBOOT: configured role=hub source=esp` and exactly one `ONEMIND OWNER TOKEN: <64 hex>` line; the gate logs `RESULT committed-boot slot=A`; from outside the guest, `/healthz` returns HTTP 200, `GET /v1/nodes` with that token lists a node with role `hub`, without a token gets 401, and `GET /` returns HTTP 200 with an HTML page | Any item missing, the token absent or printed more than once, or the node never listed |

## 3. Verdicts for this task

- **x86_64** (OVMF) runs I1–I5. On a host without x86 KVM the run uses TCG and says so; a timeout missed only because TCG is slower is **BLOCKED (TCG timing)** with measured times, and must then pass on a KVM host (CI) before it counts.
- Required for this task's "done": I1–I5 PASS on x86_64. An arm64 installer, if built, is reported, never required.
