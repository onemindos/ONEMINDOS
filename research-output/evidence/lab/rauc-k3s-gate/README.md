# Lab spike LAB-rauc-k3s-gate: RAUC A/B with a real k3s-readiness health gate

**Status:** COMPLETE: T0–T10 PASS in 2 full runs, T10 observation as expected (results below). Pre-registered: goal, hypotheses, design and pass/fail criteria were written 2026-11-11 04:22 UTC, before any build or test of this spike ran. Results are added below the line "Results" after the run; nothing above that line is changed afterwards except typo fixes, and any change is logged in §9.

> **Explain it like I'm the founder.** The earlier RAUC spike proved the update *mechanism*: two copies of the OS, write the idle one, try it, fall back if it fails. But the "is it healthy?" check in that spike was a toy service, not Kubernetes. This spike puts **real k3s** in the image and makes the check honest: it only commits a new version when k3s on *this* boot has proven itself, not when Kubernetes is still showing last boot's "all good" (the trap our Rugix spike found). Then it breaks things on purpose: k3s that will not start, a k3s that looks healthy from stale data, a kernel that crashes, a system that freezes, and power cuts. The box must always end on a working system with no keyboard.

## 1. Goal

Re-run the RAUC A/B spike (`../rauc/`) on **Debian 13 x86_64 in QEMU** with the **health gate defined in `01-FOUNDATION-DECISION.md` §4.2 item 5** instead of a stand-in, and with the **3 boot tries + watchdog** from §4.2 item 3:

- **Fresh post-boot signals only:** (1) the local kubelet `/healthz` answers on this boot; (2) the node's Ready heartbeat is newer than this boot; (3) every core pod (namespaces `kube-system` and `onemind-system`) has a Ready condition that turned True since this boot; (4) the data partition is mounted read-write and a write+fsync+read-back succeeds; (5) the local OneMind API (a lab stand-in) answers with this boot's ID. Plus the API server `/readyz`.
- **3 consecutive passes, 10 s apart**, then commit (`rauc status mark-good`). Retry a refused commit until the deadline.
- **Apps excluded:** a deliberately broken app in namespace `apps` must not block a commit.
- **3 boot tries** (Home Assistant OS GRUB logic) and a **hardware watchdog** (QEMU `i6300esb`, `-action watchdog=reset`; systemd `RuntimeWatchdogSec`), so a crash or a hang counts as a failed try.
- **Never auto-retry a failed release:** when the box comes back on the old slot after a failed trial, the gate marks the failed slot bad so GRUB never tries it again.

## 2. Hypotheses

- **H1** RAUC 1.13 (Debian) + HAOS-style GRUB script (3 tries) + a ~150-line shell gate implement 01's gate with no RAUC code changes.
- **H2** The trial marker must be written by RAUC's **pre-install** handler, not post-install: RAUC marks the new slot active *before* the post-install handler runs [rauc@2d17b27 `src/install.c` L1514 vs L1661], so a power cut between the two would otherwise boot the new slot without a gate. Writing it in pre-install closes that window.
- **H3** On RAUC, k3s's datastore on the shared data partition reproduces the **stale-Ready trap** found with Rugix [C-LAB-debian-rugix-023]: a k3s that never starts its kubelet (`--disable-agent`) is committed by a naive gate (API status only) and rolled back by the fresh-signal gate.
- **H4** With 3 tries, a power cut during the first boot of a good update no longer abandons it (the 1-try lab did [C-LAB-rauc-018]); the next attempt commits it.
- **H5** A hung boot is turned into a failed try by the watchdog, and after 3 failed tries GRUB returns to the old slot with no human action.

## 3. Pass / fail criteria (frozen before the run)

The box starts on slot A, version 1. "No human input" means the driver sends no command between the install's `reboot` and the end state, except where a test is defined as a power cut. Deadline for the gate: **300 s** per trial boot (TCG emulation is slow; the value is set now, not tuned later).

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| T0 | Build | One script inside a Lima VM builds `disk.img` and 7 bundles (`good` v2, `bad-k3s` v3, `bad-noagent` v4, `bad-boot` v5, `bad-hang` v6, `naive-noagent` v7, `wrong-key`); k3s artifacts verified against the release's `sha256sum-amd64.txt`; signed bundles verify, `wrong-key` does not | Manual edits, or a hash mismatch |
| T1 | First boot | Slot A v1 boots, gate logs `COMMITTED-BOOT`, k3s passes the fresh check, the broken app is visibly not Ready | No boot, or k3s never passes the fresh check on a clean install |
| T2 | Signature control | `wrong-key` refused, grubenv unchanged | Installs, or boot order changes |
| T3 | Good update | `good` (v2) to B; trial gate logs ≥ 3 consecutive fresh passes, then `COMMIT`; at commit time the `apps` pod is not Ready (apps excluded); a further reboot stays on B v2 | Commit without the fresh checks, or ends anywhere but B v2 committed |
| T4 | Bad update: k3s broken | `bad-k3s` (v3: k3s exits at start on an unknown flag) to A; gate logs `ROLLBACK` within deadline + 60 s, `mark-bad`, reboot; box ends on B v2, k3s fresh-healthy, A marked bad | Commits v3, stays on v3, or needs input |
| T5 | Stale-Ready trap | `bad-noagent` (v4: API server up, kubelet never starts) to A with the fresh gate: ends on B v2, A bad | Commits v4 |
| T6 | Unbootable (kernel panic) | `bad-boot` (v5) to A: exactly 3 panics, then GRUB boots B; gate on B logs `FELL-BACK` and marks A bad; A is not tried again on the next reboot | Boot loop, fewer/more than 3 attempts, or A tried again |
| T7 | Hang + watchdog | `bad-hang` (v6: init arms the watchdog and freezes) to A: 3 watchdog resets, then B; A marked bad | Box stays hung, or A tried again |
| T8 | Power cut mid-write | `SIGKILL` QEMU while RAUC copies `good` into A (log line seen before kill). Next boot: B v2; the stale marker is cleared; reinstall commits A v2 | No boot, half-written slot boots, or reinstall fails |
| T9 | Power cut in commit window | Install `good` to B, reboot, `SIGKILL` after the gate has started its trial on B but before `COMMIT`. Next boot retries B (try 2) and commits B v2 without a reinstall | Box abandons the good update (would mean 3 tries did not work), or boots an ungated slot |
| T10 | Naive gate (observation, not pass/fail) | `naive-noagent` (v7: same broken k3s, gate with freshness off). Expectation from Rugix: it **commits a broken system**. The driver then reinstalls `good` from that system; that recovery must commit (pass/fail: **T10r**) | T10r: recovery does not commit |

A test that cannot run because of an environment limit is **BLOCKED** with the reason, never PASS. Two full runs are the target; a run that fails because of a driver bug is kept in the logs and named as such.

## 4. Design

- **Host isolation:** everything upstream (mmdebstrap, RAUC, GRUB tools, k3s downloads, QEMU running the test guest) runs inside a disposable Lima VM (Debian 13 arm64, `vz`) whose only host mount is the lab work folder. The x86_64 guest runs under QEMU TCG inside that VM with **user-mode networking `restrict=on`** (k3s needs an interface and a default route; the guest cannot reach the LAN or internet). k3s is air-gapped from its bundled image tarball.
- **Disk (GPT, 14 GiB):** ESP 128 MiB · rootfs-A 2.5 GiB · rootfs-B 2.5 GiB · data (rest). k3s `--data-dir /data/k3s`; `/etc/rancher/node` bind-mounted from `/data` (node password must survive slot switches). Bundles are on the data partition.
- **GRUB:** HAOS PC script logic (`TRY -lt 3`, increment per boot) [C-LAB-rauc-010], adapted to the lab's partitions. RAUC `mark-good` resets `TRY=0`; `mark-bad` sets `OK=0` [C-LAB-rauc-004].
- **Trial marker:** RAUC `pre-install` handler writes `/data/onemind/pending` = target slot bootname + bundle version.
- **Gate modes (one systemd oneshot, `onemind-health-gate`):**
  - *trial* (marker names the booted slot): fresh checks, 3 passes → `mark-good`, clear marker; deadline → `mark-bad booted` (only if the other slot is good) + reboot.
  - *fell-back* (marker names the other slot): a trial failed before the gate decided (crash, hang, power cut) or the install was interrupted → `mark-bad other`, clear marker, `mark-good booted`.
  - *committed* (no marker): `mark-good booted` at once (resets the try counter, as HAOS's Supervisor does [C-LAB-rauc-011]); run the fresh check for a log line only; never roll back a committed OS.
- **Watchdog:** QEMU `-device i6300esb -action watchdog=reset`; images set systemd `RuntimeWatchdogSec=30s`. `bad-hang` replaces `/sbin/init` with a script that loads the driver, opens `/dev/watchdog` and sleeps forever (stands in for "PID 1 froze after arming the watchdog").
- **OneMind API stand-in:** busybox `httpd` on `127.0.0.1:7070` serving a file with this boot's `boot_id`.
- **Core pods:** k3s's `coredns` and `local-path-provisioner` (`kube-system`) plus a `onemind-core` Deployment (pause image from the air-gap tarball) in `onemind-system`. **App:** `apps/broken-app` with an image that cannot be pulled (air-gapped), never Ready.
- **Variants:** all from one rootfs; differences are `/etc/onemind-release`, `/etc/default/k3s`, `/etc/default/onemind-health-gate` and, for `bad-boot`/`bad-hang`, `/sbin/init`.

## 5. Requirement IDs served

R-1 (safe, user-controlled updates), R-2 (self-healing), R-3 (long-term maintainability), M-6 (guard rails for a solo developer), P-4 (OS image surface), P-7 (bring-your-own x86). Feeds REC-DEC-05 and REC-DEC-07 in `01-FOUNDATION-DECISION.md`, and closes the "RAUC with a real k3s gate" item in its "Not proven" list.

## 6. Glossary

| Term | Meaning |
|---|---|
| Slot A / B | The two copies of the OS on disk |
| RAUC | The update client Home Assistant OS uses; writes the idle slot and tells GRUB which one to try |
| grubenv | A 1 KiB file of variables (`ORDER`, `A_OK`, `A_TRY`, …) the bootloader reads and writes at every boot |
| Try counter | How many times GRUB has booted a slot without it being confirmed; at 3 it gives up on it |
| Trial boot | The first boot(s) of a new slot, before it is committed |
| Commit / `mark-good` | Tell GRUB "this slot is good, keep it"; `mark-bad` means "never boot it again" |
| Health gate | The boot-time program that decides commit or roll back |
| Fresh signal | Evidence produced on *this* boot (newer than the boot time), as opposed to status stored from the previous boot |
| Stale-Ready trap | k3s keeps cluster state on the data partition; after a reboot it reports the previous boot's "Ready" until something updates it |
| kubelet | The k3s component that actually runs pods on the node; `/healthz` is its local health URL |
| Watchdog | A hardware timer that reboots the machine if software stops "petting" it |
| TCG | QEMU's software CPU emulation (the guest is x86_64, the Mac is Arm) |
| SIGKILL | Instant kill of QEMU; for the guest, the same as pulling the plug |

---

## Results

**Verdict: PASS.** T0–T10r passed in two full runs on the same image (run 1: 41 min, 2026-11-11 05:01–05:42 UTC; run 2: 41 min, 05:42–06:23 UTC, from a fresh copy of the same disk; T6 113 s, T7 180 s, naive passes at 36, 49 and 62 s). T10 (the naive gate) committed a broken system in both runs, as expected. Before run 1, two integration problems were fixed (§9). Neither was in RAUC or in the gate logic. One of them, k3s on a read-only root, is a finding in its own right.

> **Explain the result like I'm the founder.** The safety net now uses real Kubernetes, and it held every time. A new version only became permanent after k3s had proved itself on *that* boot. A version whose k3s would not start went back to the old one by itself after five minutes. So did a version whose k3s *looked* fine from yesterday's records but never actually ran anything. That second one is the important trap. When we switched the "freshness" checks off, the same broken version was accepted in about a minute. A version that crashed, and a version that froze, were each tried three times and then dropped for good. Pulling the virtual plug while the update was being written did no harm. Pulling it during the new version's first boot did not throw the update away either: the next boot tried again and kept it. Nobody touched a keyboard in any of these cases. What is still not proven is the same set of tests on real hardware with a real power cord. That needs about an hour on the Beelink or Dell (§8).

### 7.1 Test results

Evidence is in `logs/serial-run1-trimmed.log` and `logs/serial-run2-trimmed.log`, with the driver verdicts in `logs/driver-run{1,2}.log`. Times are under QEMU TCG emulation of x86 on Arm, which is several times slower than real hardware.

| ID | Run 1 | Run 2 | What happened (run 1) |
|---|---|---|---|
| T0 | **PASS** | (same build) | `logs/build-run4.log`: k3s artifacts `OK` against `sha256sum-amd64.txt`; 6 signed bundles show "Verified inline signature" and `wrong-key` is rejected. The build takes about 8 min, about 3 of them for mmdebstrap through qemu-user. |
| T1 | **PASS** | **PASS** | Slot A v1: `RESULT committed-boot`, then `K3S-FRESH ok after 75s` (97–98 s after QEMU start); `apps/broken-app 0/1 ImagePullBackOff`. |
| T2 | **PASS** | **PASS** | `wrong-key` refused with a signature error; grubenv unchanged; **no trial marker written**, because signature verification comes before the pre-install handler. |
| T3 | **PASS** | **PASS** | Trial on B: `no kubeconfig on this boot` ×3, then `core pod kube-system/coredns-… not Ready`, then `CHECK pass 1/3, 2/3, 3/3` (51, 65, 79 s), `APPS (excluded from gate): broken-app 0/1 ErrImagePull`, `RESULT mark-good slot=B version=2 after 81s` [C-LAB-rauc-k3s-gate-006]. The next reboot gives `committed-boot B v2`. |
| T4 | **PASS** | **PASS** | k3s exits at start. The gate logged `no kubeconfig on this boot` for 300 s, then `RESULT mark-bad slot=A version=3` and rebooted (≈323 s after the reboot). Back on B v2 with `A_OK=0`; `K3S-FRESH ok after 41s` [C-LAB-rauc-k3s-gate-007]. |
| T5 | **PASS** | **PASS** | Stale trap with the hardened gate: the API server came up (the kubeconfig appeared after ≈20 s), then `kubelet /healthz not answering` for the rest of the 300 s; `RESULT mark-bad slot=A version=4`; back on B v2 [C-LAB-rauc-k3s-gate-007]. |
| T6 | **PASS** | **PASS** | `BAD-BOOT` and a kernel panic 3 times in 107 s. GRUB showed `A_TRY=1 → 2 → 3`, then `A_OK=1 A_TRY=3 … default=2` (B). Gate: `RESULT fell-back … slot A (v5) marked bad, never retried (trial boots used up … A_TRY=3)`. The next reboot shows `A_OK=0` and no attempt on A [C-LAB-rauc-k3s-gate-009]. |
| T7 | **PASS** | **PASS** | `BAD-HANG: arming watchdog, then freezing` 3 times in 178 s (≈60 s per attempt including boot; only the watchdog can end a sleeping init). Then the same fallback and `marked bad` as T6 [C-LAB-rauc-k3s-gate-009]. |
| T8 | **PASS** | **PASS** | Order on the console: `pre-install: trial marker slot=A version=2`, then `Marking target slot rootfs.0 as non-bootable`, then `Copying image … 50%`, then `POWER CUT`. Restart: `RESULT fell-back slot=B` cleared the marker; the reinstall committed `A v2` [C-LAB-rauc-k3s-gate-010]. |
| T9 | **PASS** | **PASS** | Killed after the trial gate on B had started and logged its first check. Restart: `GRUB-RAUC: … B_OK=1 B_TRY=2 default=2`, then `RESULT mark-good slot=B version=2` with no reinstall [C-LAB-rauc-k3s-gate-010]. |
| T10 (obs.) | **committed broken** | **committed broken** | Naive gate: `CHECK pass` at 37, 50 and 64 s, `RESULT mark-good slot=A version=7 after 66s`. On the committed slot `curl localhost:10248/healthz` → no kubelet [C-LAB-rauc-k3s-gate-008]. |
| T10r | **PASS** | **PASS** | Reinstalling `good` from the broken-but-committed slot committed B v2. |

### 7.2 Hypotheses

| | Verdict | Why |
|---|---|---|
| H1 | **Confirmed** | Stock Debian RAUC 1.13, the HAOS 3-try GRUB logic, and two shell scripts (`onemind-health-gate`, 75 lines, and `onemind-k3s-check`, 58 lines) implement every element of 01's gate. No RAUC code was changed. |
| H2 | **Confirmed (code + lab)** | The code order is pre-install, then write, then `mark_active`, then post-install, in both v1.13 and master [C-LAB-rauc-k3s-gate-001]. On the console, the marker appears before the slot is touched (T8). The handler cannot read `RAUC_MF_VERSION` (it is a hook-only variable) and reads the bundle manifest instead [C-LAB-rauc-k3s-gate-002]. |
| H3 | **Confirmed** | The trap is a property of k3s state on a shared data partition, not of Rugix. RAUC shows it the same way: the naive gate committed after 66 s (run 1) and 63 s (run 2), and the fresh gate rejected the same failure mode [C-LAB-rauc-k3s-gate-007, -008]. Three passes in a row did not help the naive gate. This matches the Rugix result [C-LAB-debian-rugix-023]. |
| H4 | **Confirmed** | T9: `B_TRY=2`, then commit. The 1-try lab abandoned the update in the same situation [C-LAB-rauc-018]. |
| H5 | **Confirmed (in emulation)** | T7: three watchdog resets, then fallback. On the good images, systemd had the watchdog open: the kernel prints `watchdog0: watchdog did not stop!` when systemd hands it over at reboot. |

### 7.3 What the numbers and findings mean for OneMind

1. **k3s does not run on a read-only root out of the box.** The first smoke boot failed: `mkdir /etc/rancher/k3s: read-only file system`. The fix is to bind-mount `/etc/rancher/node`, `/var/lib/rancher`, `/var/lib/kubelet`, `/var/lib/cni`, `/var/log/pods` and `/var/log/containers` from `/data`, and to write the kubeconfig to `/run` [C-LAB-rauc-k3s-gate-004]. This list belongs in the OneMind image spec. The Rugix spike did not hit this problem, because its root was writable. For the gate, putting the kubeconfig in `/run` has a side benefit: its existence is itself a "k3s started on this boot" signal. It does not replace the kubelet and heartbeat checks. In T5 and T10 the API server wrote a fresh kubeconfig while the node was still broken.
2. **Write the trial marker in pre-install, never in post-install** [C-LAB-rauc-k3s-gate-001]. HAOS has no such marker; its Supervisor marks every boot good. OneMind needs the marker because the gate has to tell three cases apart: a trial boot, a fall-back from a failed trial, and a normal boot.
3. **The gate must never be ordered after `k3s.service`.** k3s is `Type=notify` with no start timeout, so a k3s that hangs before reporting "ready" would stop the gate's deadline from ever starting. In this lab the gate starts after the local API and RAUC only, and k3s health is checked by polling.
4. **Time to a decision.** On TCG: a good update commits ≈80 s after the trial boot's gate starts, and a bad one is rejected at the 300 s deadline (≈5.5 min including boot). Real x86 hardware should be several times faster. Set the deadline on hardware (F1 below), not from these numbers.
5. **"Never auto-retry" works only with the fell-back mode.** Without it, a slot that used up its 3 tries keeps `OK=1`, and the next install or a manual GRUB edit could select it again. The gate marks it bad explicitly (T6, T7).

## 8. Limits and founder-runnable tests

| Gap | Status |
|---|---|
| Real hardware, real power pull (QEMU `SIGKILL` doesn't drop disk caches; a FAT `grubenv` write is the weak point) | **Founder hardware**: F1, F2 |
| RAUC ≥ 1.15.2 (01's floor); Debian ships 1.13 [C-LAB-rauc-k3s-gate-005] | Not tested: rebuild with an upstream RAUC 1.15.x package (F3) |
| Gate process crash during a trial boot: the box would keep running the uncommitted slot until the next reboot (safe, but the update stays pending) | **Not tested.** Proposed fix: `OnFailure=` reboot for the gate unit in trial mode, plus an alert |
| A committed slot that later fails 3 boots in a row falls back to the older OS, as HAOS does. If the newer release migrated data, the older one may not read it | Not tested (data-compatibility rule in 04 and 06) |
| One kill point per power-cut test per run (50 % of RAUC's progress counter, not 50 % of bytes) | F2b kill-point sweep |
| The hang is simulated (fake init that arms the watchdog), not a real PID 1 or kernel deadlock | Accepted lab substitution |
| x86_64 only; Pi 5 (tryboot) and Jetson (NVIDIA A/B) | Separate spikes |
| Secure Boot / signed UKI; read-only rootfs on erofs/squashfs with dm-verity (this lab used ext4 mounted read-only) | Out of scope (W6, X-2R) |
| Lab-only shortcuts: fixed machine-id in every slot, serial autologin, no network beyond a restricted user-net | Must not ship |

### F1: the same suite on an x86 box (Beelink or Dell 5540), about 1 hour

1. In the Lima VM: `sudo OUT=/var/lab/rkg-out DL=<k3s download dir> bash scripts/build.sh`. For hardware, add `console=tty0` before `console=ttyS0` in `scripts/guest/grub.cfg.in` and a `getty@tty1` autologin drop-in like the serial one (lab only; remove before any other use). The image needs a hardware watchdog driver for the box (for example `iTCO_wdt` on Intel) instead of `i6300esb` in `/etc/initramfs-tools/modules`. Check `dmesg | grep -i watchdog` on the box first.
2. Write `disk.img` to a **spare** USB SSD from the Mac: `diskutil list` (check the size twice), `diskutil unmountDisk /dev/diskN`, `sudo dd if=disk.img of=/dev/rdiskN bs=4m`. Boot it in UEFI mode with Secure Boot off.
3. Run by hand, reading `/data/onemind/gate.log` after each step: `rauc install /data/bundles/good.raucb && systemctl reboot` (expect `mark-good`), then `bad-k3s` and `bad-noagent` (expect `mark-bad` and a return), then `bad-boot` and `bad-hang` (expect 3 attempts, then `fell-back`).
4. **PASS:** all of the above with no keyboard input after `reboot`. Also record the commit time for `good` and the decision time for `bad-k3s`, and set the production gate deadline to about 3× the good-commit time. **FAIL:** any boot needs a keyboard, or a slot is committed while `curl -s localhost:10248/healthz` fails.

### F2: real power pulls (same box)

Pull the cord 10 times during an install of `good`: at the start, the middle and the end of `Copying image`, during the reboot, and during the trial gate (before `RESULT`). After each pull, record `rauc status`, `grub-editenv /boot/efi/EFI/BOOT/grubenv list`, `fsck.vfat -n /dev/disk/by-partlabel/esp` and the last gate line. **PASS:** 10/10 end on a working slot without a keyboard, and every half-written slot ends `OK=0`. A pull during the trial gate should end with that slot committed on the retry, as in T9. **FAIL:** a corrupt grubenv or ESP, or a box that does not boot.

### F3: RAUC 1.15.x

Build RAUC 1.15.2 or later from its signed tag inside the Lima VM. Install it into the rootfs in place of the Debian package, rebuild, and rerun `run-tests.py`. **PASS:** same results as runs 1 and 2.

## 9. Deviations and problems (honest log)

1. **API stand-in (design text in §4 changed in practice).** §4 says busybox `httpd`, but Debian's busybox has no httpd applet [C-LAB-rauc-k3s-gate-005] (`logs/build-run1-busybox-no-httpd.log`). Replaced by `socat` running a 3-line responder (`scripts/guest/onemind-api-respond`). The first socat attempt used quoting inside the unit file and returned an empty reply; it was fixed by moving the response into a script and tested in the Lima VM before rebuilding. The stand-in's role and the pass criteria did not change.
2. **Read-only root (found by the T1 smoke boot of build 2, before run 1).** k3s could not start; see §7.3 item 1 and `logs/debug-readonly-root.log`. The fix (bind mounts and `--write-kubeconfig /run/k3s/k3s.yaml`) was made before run 1. The smoke boot's gate did the right thing on a committed slot: it raised `K3S-FRESH ALERT … (no rollback)`.
3. Run 1 and run 2 used the same build (`build-run4`, disk sha256 in `SHA256SUMS`), each from a fresh copy of the disk.
4. **Slot size.** §4 says 2.5 GiB slots; the build used 2 GiB slots holding a 1.7 GiB ext4 image (the rootfs with k3s and its air-gap images was well under that), with the data partition taking the rest of the 14 GiB disk. No test depends on the slot size.
5. Minor: `systemd-logind` is masked (it restart-loops in this minimal image), and `systemd-networkd-persistent-storage` fails on the read-only root. Neither is on the update path.

## 10. What competitors do

| Product | Update engine and tries | When a new OS is committed | Kubernetes-aware? | Constraint fit for OneMind |
|---|---|---|---|---|
| Home Assistant OS | RAUC + GRUB, 3 tries [C-LAB-rauc-010] | Supervisor marks the booted slot good when it starts [C-LAB-rauc-011] | No (Docker) | **High** for the mechanism (same tool and layout as this lab). **Low** for the gate: "Supervisor started" would commit the T5 failure |
| umbrelOS 2.0 | Rugix (Debian trixie) | Not verified in prior work | No | Medium (same Debian base; PolyForm-NC: patterns only) |
| Olares | No OS A/B; host Ubuntu/Debian + k3s [C-TD-olares-007] | n/a | Yes, but no OS rollback | **None** for OS safety |
| Fedora IoT / bootc + greenboot | rpm-ostree/bootc, boot counter, health scripts [C-W2-052] | When greenboot's required checks pass | Possible with a k3s check (W2 lab) | Medium. Our lab saw greenboot downgrade a healthy box after a power cut during finalize [C-LAB-fedora-bootc-011] |
| OneMind lab, Rugix variant | Rugix, 1-shot trial [C-LAB-debian-rugix-003] | Fresh-signal k3s gate [C-LAB-debian-rugix-022] | Yes | High, same gate logic |
| **OneMind lab, this spike** | RAUC 1.13, 3 tries + watchdog | Fresh-signal k3s gate, pre-install trial marker, fell-back marking | Yes | **Direct**: this is 01's chosen design |

## 11. Recommendations (with requirement IDs)

| # | Recommendation | Requirement IDs |
|---|---|---|
| L-1 | Adopt this gate design as the reference for REC-DEC-07. It has three modes (trial, fell-back, committed), fresh signals only, 3 passes in a row, apps excluded, and the core-pod list is versioned with the OS release. RAUC passed with a real k3s gate, which closes the "RAUC with a real k3s gate" gap in 01. | R-1, R-2, M-6 |
| L-2 | Write the trial marker in RAUC's **pre-install** handler and read the version from the bundle manifest. Never use post-install for anything the next boot depends on. | R-1, R-3 |
| L-3 | Image spec: on the read-only root, bind-mount k3s state from `/data` (6 paths) and write the kubeconfig to `/run`. Add a CI test that boots the image read-only and checks that k3s starts. | R-3, P-4, M-6 |
| L-4 | Keep 3 tries and a hardware watchdog (`RuntimeWatchdogSec`), and mark a used-up slot bad on the fall-back boot. Do not order the gate after `k3s.service`. Add `OnFailure=` handling for a crashed gate. | R-1, R-2 |
| L-5 | Never ship a naive (API-status-only) gate, even as a debug mode. Both RAUC and Rugix committed a broken system with it. | R-1, AI-4 |
| L-6 | Run F1–F3 before the update-tool gate in the 180-day plan. Set the production deadline from F1's hardware timings. | R-1, P-7 |

## 12. How to re-run

```bash
LAB=~/<lab-dir>/rauc-k3s-gate        # outside the repo
mkdir -p $LAB/logs && cp -R research-output/evidence/lab/rauc-k3s-gate/scripts $LAB/scripts
limactl create --name lab-rkg --tty=false --vm-type vz --cpus 10 --memory 16 --disk 80 \
  --mount-only $LAB:w --mount-type virtiofs template:debian-13 && limactl start lab-rkg
limactl shell lab-rkg -- sudo apt-get install -y mmdebstrap qemu-user-binfmt qemu-system-x86 ovmf rauc \
  gdisk dosfstools mtools e2fsprogs squashfs-tools openssl grub-common python3 curl zstd
# k3s v1.37.2+k3s1: k3s, k3s-airgap-images-amd64.tar.zst, sha256sum-amd64.txt into $LAB/dl (inside the VM, with curl)
limactl shell lab-rkg -- sudo bash -c "OUT=/var/lab/rkg-out DL=$LAB/dl bash $LAB/scripts/build.sh"     # T0, ~8 min
limactl shell lab-rkg -- sudo bash -c "mkdir -p /var/lab/run && cp --sparse=always /var/lab/rkg-out/disk.img /var/lab/run/ && \
  python3 -I $LAB/scripts/run-tests.py --disk /var/lab/run/disk.img --log $LAB/logs/serial.log"     # T1–T10, ~41 min
scripts/trim-logs.sh $LAB/logs/serial.log > serial-trimmed.log
limactl delete -f lab-rkg
```

`run-tests.py` exits 0 only if every pass/fail test passes (T10 is an observation). `--upto T3` stops early. `scripts/debug-boot.py` boots the disk and runs ad-hoc commands; it was used for the §9 diagnosis.

## 13. Files

- `scripts/build.sh`: image and bundles. `scripts/guest/`: everything installed into the image (gate, check, RAUC pre-install handler, units, core and app manifests, GRUB template, bad-hang init, API stand-in). `scripts/grub.cfg.generated`: the boot script as built.
- `scripts/run-tests.py`: test driver (stdlib Python; run with `-I`). `scripts/trim-logs.sh`: log trimming and masking.
- `logs/`: build logs, driver verdicts and trimmed serial logs for both runs, plus the read-only-root diagnosis. VM-internal addresses are masked as `<vm-private-ip>`.
- `SHA256SUMS`, `image-packages.txt`, `versions.md`, `logs/versions.txt`: pins and hashes. The lab keys stayed inside the VM and were deleted with it; only the public lab CA certificate is hashed.
