# Lab spike: Debian 13 + Rugix A/B image, health-gated commit, power cut

**Spike tag:** `LAB-debian-rugix` · **Mission ref:** RESEARCH-MISSION.md §7 items 1–3 · **Serves:** R-1, R-3, F-7, F-8, P-4, H-1
**Status:** see [Result](#7-result). Sections 1–4 were written **before** any build or test ran (2026-11-10).

> **Explain it like I'm the founder**
> A OneMind box keeps two copies of its operating system on disk, called **A** and **B**. It runs from one and installs the next version onto the other. After the update it restarts into the new copy *on trial*. A small OneMind program, the **health gate**, then waits for Kubernetes (k3s) to come up healthy. Only when it does, the gate tells Rugix to **commit**: "keep this copy". If k3s never gets healthy, the gate restarts the box, and because nothing was committed the bootloader goes straight back to the old, working copy. That is **automatic rollback**.
> This spike proves that on a virtual machine, on purpose, three ways: a good update (must commit), a broken update (must roll back by itself), and pulling the plug halfway through writing an update (the box must still boot the old copy and accept the update again).

## 1. Goal

Build a Debian 13 ("trixie") image with Rugix Bakery for **x86_64** (aarch64 if feasible), boot it in QEMU, and show with logs:

1. A **good update** (v2-good) boots on trial and is **committed** by a health gate that requires k3s readiness.
2. A **bad update** (v2-bad, k3s deliberately broken) boots on trial, fails the gate, and the system **rolls back automatically** to v1 with no human action.
3. A **power cut mid-update** (QEMU killed with SIGKILL while Rugix is writing the spare system slot) leaves v1 booting and committed, and the same update installs cleanly afterwards.

## 2. Hypotheses

- **H1 (build):** Rugix Bakery v0.9.4 (container `ghcr.io/rugix/rugix-bakery:v0.9`) running in a Linux VM on the Mac builds a bootable `generic-grub-efi` Debian 13 image and Rugix update bundles, for amd64 via user-mode CPU emulation (binfmt) and for arm64 natively.
- **H2 (rollback):** Because Rugix's GRUB boot flow clears the "boot spare" flag *before* it boots the trial slot (`boot/grub/cfg/first.grub.cfg` in rugix-bakery@c43fdc1), any reboot before `rugix-ctrl system commit` returns to the old slot. So a gate that reboots on failure is enough for automatic rollback, provided the trial system boots far enough to run the gate (or panics and reboots).
- **H3 (commit):** Rugix Ctrl 1.4.0 never commits by itself (docs: "Rugix Ctrl will not automatically mark boot groups as good or bad"), so the slot is committed only by our gate, and a `system-commit/pre-commit` hook can refuse a manual commit of an unhealthy slot.
- **H4 (power cut):** Rugix writes only the inactive slot and changes the boot selection only after all payloads are synced (docs `updates/update-reliability.md`), so killing QEMU mid-write leaves the active slot as default and the device bootable.

## 3. Pass/fail criteria (fixed before running)

`info` = `rugix-ctrl system info` on the VM; `release` = `/etc/onemind-release` baked into each image.

| Test | Pass when all of these hold | Fail when any holds |
|---|---|---|
| T0 build | Image + 3 bundles (v1, v2-good, v2-bad) built for amd64; first boot reaches SSH; `info` shows active=a, default=a; k3s node `Ready` and CoreDNS available within 10 min | Build error, no boot, or k3s not Ready in 10 min on v1 |
| T1 good update | After install + reboot: `release`=v2-good, gate log shows `COMMIT`, `info` active=b, default=b; still b after one more reboot | Gate does not commit, or a later reboot lands on a |
| T2 bad update | After install + reboot into b: gate log shows `ROLLBACK` after its timeout; VM reboots by itself; `release`=v1 (or v2-good if T1 ran first, i.e. the previously committed version), `info` default unchanged; k3s Ready again; no human command between install and verification | System stays on b, needs manual action, or the default group changes |
| T2b commit refusal | On the bad slot, a manual `rugix-ctrl system commit` exits non-zero because the pre-commit hook rejects it | Manual commit succeeds |
| T3 power cut | QEMU SIGKILLed after ≥ 256 MiB written to the spare system slot; next boot: active = default = the old slot, `release` unchanged, k3s Ready; reinstalling the same bundle then boots and commits | Unbootable VM, boot lands on the half-written slot, or reinstall fails |
| T4 arm64 (stretch) | T0–T2 pass on arm64 under HVF | Recorded as not run or failed with the reason |

### 3.1 Added after run 1, before run 2 (2026-11-11 01:55 UTC)

Run 1 (see §7) showed two things: (a) the v2-bad image was not actually broken (a recipe-ordering bug in my project, fixed); (b) the gate committed a trial slot "HEALTHY after 0s", which means the persisted k3s status from the previous boot can satisfy a check that only reads the API. So the gate gets a **freshness** check (local kubelet `/healthz` answers, and the node's Ready heartbeat is newer than this boot), switchable with `ONEMIND_GATE_FRESHNESS`, and one test is added:

| Test | Pass when | Fail when |
|---|---|---|
| T2c stale-status probe | `v2-noagent` (API server up, kubelet disabled with `--disable-agent`) with the hardened gate: `ROLLBACK`, back on the previous release. The same image with freshness **off** (`v2-noagent-naive`) is run too, to see whether the naive check wrongly commits (this half is an observation, not pass/fail). | Hardened gate commits `v2-noagent` |

All tests (T0–T3, T2c) rerun from a fresh disk with the rebuilt images in run 2.

### 3.2 Added after run 3, before run 4 (2026-11-11 02:50 UTC)

Run 3 on amd64 failed T1: a **good** update was rolled back (details in §7). The gate gets three changes; the pass/fail criteria above are unchanged, and run 4 repeats T0–T3 and T2c on both architectures:
1. CoreDNS must have a pod whose Ready condition turned True **since this boot** (not just `availableReplicas ≥ 1`, which can be stale).
2. The check must pass **3 times in a row, 10 s apart** before the gate tries to commit.
3. If the pre-commit hook refuses the commit, the gate **keeps retrying until the deadline** instead of rolling back at once.

Timeout (set before running): health gate 300 s on both architectures (one shared base layer).

## 4. Method

- **Isolation (mission §2 rule 5):** Bakery, Docker and all downloads run inside a disposable Lima VM (`vz`, Debian 13 arm64) whose only host mount is the lab work folder (no home mount, no SSH agent forwarding). Test VMs are QEMU processes with user-mode networking `restrict=on` (no route to the host LAN or internet; only a forwarded SSH port on 127.0.0.1). k3s runs air-gapped from the bundled image tarball.
- **Images:** a Bakery project with a shared base layer (Debian trixie, `core/debian-grub-setup`, `core/ssh`, networking, k3s + air-gap images, health gate, `panic=10`) and thin release layers that differ by `/etc/onemind-release`: v1, v2-good, v2-bad (k3s gets an invalid flag, so it can never become Ready), and from run 2 v2-noagent and v2-noagent-naive (§3.1). The `run-bakery` wrapper is upstream's, with its default image pinned to `v0.9.4` instead of the floating `v0.9` tag.
- **State:** `/var/lib/rancher`, `/etc/rancher/node` and `/var/log/onemind` (gate log) persist on the Rugix data partition, so k3s state survives slot switches; everything else in `/etc` comes from the image.
- **Gate:** `onemind-health-gate.service` runs on every boot. If active group = default group, it does nothing. Otherwise it polls `/readyz`, node `Ready` and CoreDNS available until the timeout; success → `rugix-ctrl system commit`; timeout → `systemctl reboot`. A pre-commit hook repeats the k3s check.
- **Power cut:** the bundle is copied into the VM, `rugix-ctrl update install --reboot set` runs in the background, and the host sends SIGKILL to QEMU once `/proc/<pid>/io` `write_bytes` of `rugix-ctrl` passes 384 MiB (planned as "256 MiB after Rugix reports writing `system-b`"; changed before the first T3 run because the log line is not reliably flushed. The boot slot is only 256 MiB, so a cut at ≥384 MiB is inside the system slot) (pattern from upstream `tests/test_update_interruption.py`, which does a soft `reboot -f` instead of a power cut).

## 5. Pinned versions and hashes

See [`versions.md`](versions.md). In short: Rugix Bakery **v0.9.4** (container digest pinned) [C-LAB-debian-rugix-002], Rugix Ctrl **v1.4.0** in the image [C-LAB-debian-rugix-001], Debian 13 from snapshot **20261109T000000Z** [C-LAB-debian-rugix-016], kernel 6.12.107+deb13, k3s **v1.37.2+k3s1** (binaries and air-gap images checked against the release's sha256 files) [C-LAB-debian-rugix-014], host QEMU 11.1.3, Lima 2.3.0.

## 6. How to run it yourself (founder-runnable)

Everything is in [`scripts/`](scripts/). You need a Mac with Lima and QEMU (`brew install lima qemu`), about 40 GB free and about 1.5 hours for both architectures. All build tools run inside the Lima VM. The test VMs are QEMU with networking that cannot reach your LAN or the internet.

```bash
export LAB=~/onemind-lab/debian-rugix          # any folder OUTSIDE the repo
cd research-output/evidence/lab/debian-rugix/scripts
./00-create-builder.sh                          # Debian 13 arm64 build VM (Docker + binfmt inside)
./10-build.sh arm64                             # ~5 min: image + 5 update bundles
./10-build.sh amd64                             # ~12 min (amd64 is emulated during the build)
ARCH=arm64 PORT=22623 ./20-test.sh all          # ~20 min under HVF
ARCH=amd64 PORT=22622 ./20-test.sh all          # ~40 min (x86 emulation, TCG)
./30-collect-logs.sh run-arm64 my-arm64         # trimmed + redacted logs into ../logs/
limactl delete -f dr                            # with LIMA_HOME=$LAB/lima; then rm -rf "$LAB"
```

`20-test.sh` prints `PASS`/`FAIL` lines and writes `$LAB/run-<arch>/events.log` and `serial.log`. A run passes when every line is `PASS` (T2c-naive prints only an outcome, by design).

**On real hardware (still to do; belongs in `22-HARDWARE-LAB-TEST-PLAN.md`):** flash `build/v1-amd64/system.img` to a USB/NVMe disk on the Beelink or Dell, then repeat T1–T3 with a **real power pull** (unplug the power during `rugix-ctrl update install`, at least 10 times at different points). Pass: every boot comes up on the old release, and the update reinstalls and commits. This covers what the QEMU kill cannot (§7.4).

## 7. Result

Runs: 1 (both arches, 01:24–01:50 UTC), 2 (aborted), 3 (both), 4 (both, 03:04–03:49 UTC, 2026-11-11). Lab VMs deleted afterwards.

**Bottom line: PASS on both x86_64 and aarch64 (run 4) for build, good-update commit, automatic rollback of a bad update, refusal of a manual commit, and power cut mid-write** [C-LAB-debian-rugix-022]. It took four runs. Each earlier failure was in **my** test image or **my** health gate, never in Rugix. Two of those failures are the most useful findings of the spike, because they show how a naive health gate can either certify a broken system or roll back a healthy one.

### 7.1 Results by run

| Test | Run 1 (both) | Run 3 arm64 | Run 3 amd64 | **Run 4 arm64** | **Run 4 amd64** |
|---|---|---|---|---|---|
| T0 build + first boot | PASS | PASS | PASS | PASS | PASS |
| T1 good update commits | PASS* | PASS | **FAIL** (false rollback) | PASS (3× healthy after 30 s) | PASS (3× healthy after 47 s) |
| T2 bad update rolls back | **invalid** (bad image not bad) | PASS | PASS | PASS (rolled back at 300 s) | PASS (rolled back at 300 s) |
| T2b manual commit refused | PASS | PASS | PASS | PASS | PASS |
| T3 power cut mid-write | not run | PASS (cut at 456 MiB) | PASS (cut at 390 MiB) | PASS (cut at 440 MiB) | PASS (cut at 406 MiB) |
| T2c hardened gate, kubelet dead | — | PASS (rolled back) | PASS (rolled back) | PASS (rolled back) | PASS (rolled back) |
| T2c naive gate, kubelet dead (observation) | — | **committed a broken system in 0 s** | **committed in 3 s** | **committed in 20 s** (3× "healthy" on stale data) | **committed in 28 s** (3× "healthy" on stale data) |

\* Run 1 committed, but "HEALTHY after 0 s" was the first sign of the stale-status problem. Run 2 was aborted: the new freshness check probed `127.0.0.1:10248`, and the kubelet listened only on `[::1]` (see 7.3). Logs: [`logs/`](logs/) (`run1-*-invalid`, `run3-*`, `run4-*`).

### 7.2 What happened, in order

1. **Build (H1 confirmed).** Bakery v0.9.4 built a bootable Debian 13 `generic-grub-efi` image plus update bundles in about 4–5 min on arm64 (native) and about 12 min on amd64 (emulated with binfmt inside an arm64 VM) [C-LAB-debian-rugix-020]. Factory image about 2 GB; each full bundle about 600–640 MB. On first boot, Rugix bootstrapping grew the 2 GB image on a 24 GB disk into: config 256 MiB, boot-a/boot-b 256 MiB each, system-a/system-b **4 GiB each**, data 15.2 GiB [C-LAB-debian-rugix-021]. This matches Rugix's default 4 GiB slot size [C-LAB-debian-rugix-008] and Bakery's default GPT layout [C-LAB-debian-rugix-009]. SSH came up in about 20 s (arm64, HVF) and about 25 s (amd64, TCG). k3s was healthy about 20 s (arm64) and about 60–90 s (amd64) after that.
2. **Run 1: an invalid bad-update test.** The bad image booted, and the gate committed it, because `/etc/default/k3s` in the image was **empty**. My `break-k3s` recipe declared a dependency on `k3s`, so Bakery re-ran the k3s recipe *after* it in the same layer and reset the file (build log: `[3/5] break k3s` then `[4/5] install k3s`). Lesson for OneMind's own recipes: **a Bakery recipe dependency re-applies that recipe in the child layer.** Use priorities, not dependencies, for "override" recipes [C-LAB-debian-rugix-026].
3. **The stale-status trap (T2c).** k3s keeps its datastore on the persistent data partition, so after a reboot into a new slot the API server immediately serves the **previous boot's** node status (`Ready=True`) and CoreDNS status (`availableReplicas=1`). A gate that only asks the API "is the node Ready and is CoreDNS available?" passes in 0–3 s. That is before the new system's kubelet has proven anything. T2c showed this directly: an update whose kubelet never runs (`--disable-agent`) was **committed** by the naive gate on both architectures [C-LAB-debian-rugix-023]. The hardened gate checks the local kubelet `/healthz`, a node heartbeat newer than this boot, and (from run 4) a CoreDNS pod that turned Ready since this boot. It **rolled back** the same update after its 300 s timeout ("node not Ready"). Requiring 3 healthy checks in a row does **not** fix this by itself: in run 4 the naive check still passed 3× on stale data and committed in 20 s (arm64) and 28 s (amd64). Freshness is the part that matters.
4. **The false rollback (run 3 amd64 T1).** Under slow x86 emulation the gate saw "HEALTHY after 5 s" (stale CoreDNS status). Then the pre-commit hook, run 4 s later, saw CoreDNS *unavailable*, because the pod was being recreated, and refused the commit. My gate rolled back on the first refusal, so a **good update was reverted** [C-LAB-debian-rugix-024]. That is safe, because the device stayed on a working release, but it is wrong. Fixed in run 4 (§3.2): CoreDNS freshness, 3 consecutive healthy checks, and retrying until the deadline.
5. **Rollback mechanics (H2 confirmed).** In every rollback the serial log shows the same sequence. GRUB prints `Booting to spare partition set...` once. The gate logs `TRIAL`, then `ROLLBACK ... rebooting to default group`. The next boot has no spare line and comes up on the default group. This is Rugix's one-shot trial: the spare flag is reset before the trial boots [C-LAB-debian-rugix-003]. Rugix never commits by itself [C-LAB-debian-rugix-004]; only our gate did.
6. **Commit refusal (H3 confirmed).** On the bad slot, `rugix-ctrl system commit` failed with `hook "system-commit/pre-commit/k3s-healthy" failed` ("apiserver not ready") on both architectures. So even a human or a script cannot make a broken slot permanent while the hook is installed. Rugix documents this pattern [C-LAB-debian-rugix-005].
7. **Power cut (H4 confirmed, within the VM's limits).** QEMU was SIGKILLed while `rugix-ctrl` was writing (390–456 MiB into a roughly 600 MB bundle). The next boot came up on the old release with active = default, the data partition mounted cleanly (no ext4 errors), and reinstalling the same bundle then committed normally. This matches Rugix's documented rule that boot selection changes only after all payloads are synced [C-LAB-debian-rugix-007], and it is a harsher test than Rugix's own interruption test, which uses a soft `reboot -f` [C-LAB-debian-rugix-010].

### 7.3 Smaller findings

- **The k3s kubelet health port bound only to `[::1]:10248`** in this VM, because the node took QEMU's IPv6 address as its node IP. A probe of `127.0.0.1` fails, so probe `localhost` [C-LAB-debian-rugix-025]. Expect dual-stack surprises like this on real networks.
- **`rugix-ctrl system info` prints camelCase JSON** (`.boot.activeGroup`, `.boot.defaultGroup`, `.boot.bootFlow`); the schema file names them in snake_case [C-LAB-debian-rugix-027]. Umbrel reads `bootFlow` the same way [C-LAB-debian-rugix-018].
- **The Bakery docs and code disagree on a name**: the docs say `core/rugix-auto-commit`, Bakery v0.9.4 ships `core/rugpi-auto-commit`. Either way it commits unconditionally, so **do not use it for OneMind** [C-LAB-debian-rugix-005], [C-LAB-debian-rugix-006].
- **Both system slots carry the same ext4 UUID** (`12341234-…`, fixed by Bakery for reproducibility) [C-LAB-debian-rugix-009]. Rugix boots by PARTUUID, so this was harmless here. Never mount slots by filesystem UUID.
- **Unsigned bundles:** every install used `--insecure-skip-bundle-verification`, because signatures are mandatory by default since Rugix 1.0 [C-LAB-debian-rugix-013]. **Signing was not tested here** and is the next spike to run.
- **Reproducibility was not tested** (see `versions.md`).

### 7.4 Limits of this evidence

- **Not a real power loss.** Killing QEMU discards everything in guest RAM, including the guest page cache. But data that QEMU already handed to macOS (`cache=writeback`) survives in the host page cache. A real SSD can also lose or reorder its own volatile cache. The hardware power-pull test in §6 is still required before H-1 hardware ships.
- **One bad-update shape per kind:** k3s refusing to start (T2) and the API up with the kubelet dead (T2c). A kernel that panics would reboot through `panic=10`. A hung userspace would rely on the systemd hardware watchdog (`RuntimeWatchdogSec=30s`, i6300esb on amd64; there is no watchdog device on the arm64 `virt` machine). Neither was exercised.
- **GRUB/EFI only.** Pi 5 (`rpi-tryboot`) and Jetson (L4T UEFI) boot flows were not tested; they need hardware.
- **Single-node k3s with SQLite.** The gate logic for etcd or multi-node clusters was not tested.

### 7.5 What this means for OneMind (recommendations, with requirement IDs)

| # | Recommendation | Serves |
|---|---|---|
| L-1 | Keep **Debian 13 + Rugix Bakery/Ctrl** as the image and update path for x86 and arm64 EFI boxes; it worked end to end in a day on a laptop. Next spike: Pi 5 `rpi-tryboot` and signed bundles. | R-1, R-3, P-4, F-7 |
| L-2 | Ship OneMind's **own health gate**, never `rugpi-auto-commit` and never an "on daemon start" commit like Umbrel's. It needs: (a) a pre-commit hook; (b) **freshness checks** (local kubelet `/healthz`, node heartbeat and CoreDNS Ready newer than this boot); (c) **N consecutive healthy checks**; (d) **retry until the deadline**, then reboot to roll back; (e) a hardware watchdog for hangs. | R-1, R-2, N-9 |
| L-3 | Make the gate's deadline and checks **per box tier**. At 300 s with x86 emulation the margin was thin, and slow hardware such as a Pi on an SD card may need more. Measure on real boards. | R-1, H-3 |
| L-4 | Write OneMind's Bakery recipes with **priorities, not dependencies**, for anything that overrides another recipe, and add a CI check that reads the baked config back out of the layer tarball (as done in §7.2 step 2). | F-8, R-3 |
| L-5 | Use this spike's scripts as the **seed of image CI**: build arm64 natively and amd64 under binfmt in a Linux VM or runner; boot-test every release in QEMU (T0–T3, T2c) before signing. | F-8, R-3 |

## 8. What competitors do (health-gated commit)

| Product | Updater / boot flow | When the new slot is marked good | Constraint fit with OneMind |
|---|---|---|---|
| umbrelOS 2.x | Rugix Ctrl (pins v1.3.2 on amd64 [C-LAB-debian-rugix-019]), `--reboot set` [C-LAB-debian-rugix-018] | As soon as `umbreld` starts: "If we've successfully booted then commit" [C-LAB-debian-rugix-017]. Nothing checks app health first. (This settles a point the phase-1 research left UNVERIFIED.) | **High** (same tool, Debian base, x86 + Pi). But Umbrel runs Docker, not k3s, so its early commit would not catch a broken k3s. OneMind must gate later. |
| Home Assistant OS | RAUC + GRUB/U-Boot, 3 boot tries | When the Supervisor starts (phase-1 research, `research/platform/verify-updates-rollback-backups-security.md` §1, SECONDARY for this spike) | Medium: Buildroot appliance, no Kubernetes. Same "early good" gap. |
| Kairos | kairos-agent, GRUB sentinels | At a cloud-init boot stage, explicitly not workload health (same phase-1 file, SECONDARY) | Medium: k3s-native, but no Pi 5. |
| Fedora IoT / bootc | rpm-ostree/bootc + greenboot | Automated health-check rollback is greenboot's job, not bootc's (phase-1 `fedora-iot-and-redhat-edge-deep-dive.md` line 104, SECONDARY for this spike) | Medium–high: the closest to L-2 because the health scripts are the integrator's job. Red Hat lineage, not Debian. |
| **This spike** | Rugix Ctrl 1.4 + GRUB | After k3s **fresh** health passes 3× in a row, enforced again by a pre-commit hook; reboot on deadline | The target design (L-2) |

## Glossary

- **A/B slots:** two copies of the operating system on disk. The box runs one and updates the other.
- **Boot group / slot:** Rugix's names for "copy A or B" (a group is the set of boot and system partitions of one copy).
- **Trial boot / spare:** the first boot into a freshly updated copy. It is not permanent until committed.
- **Commit:** telling Rugix "keep this copy as the default from now on" (`rugix-ctrl system commit`).
- **Rollback (automatic fallback):** rebooting without a commit, so the bootloader returns to the old default copy.
- **Health gate:** OneMind's program that decides whether to commit or roll back.
- **Pre-commit hook:** a script Rugix runs before any commit; if it fails, the commit is refused.
- **Stale status:** information in Kubernetes that was true *before* the reboot but has not been re-checked since.
- **kubelet:** the Kubernetes agent on each machine that actually runs containers and reports node health.
- **CoreDNS:** the cluster's internal name service, used here as the "core pod" that must come up.
- **Bundle (`.rugixb`):** a Rugix update file with the new boot and system partitions.
- **Rugix Bakery:** the tool that builds images and bundles from recipes and layers, inside a container.
- **Layer / recipe:** a Bakery layer is a filesystem built from a parent plus recipes (steps that install or configure things).
- **binfmt / TCG / HVF:** ways to run code for another CPU. binfmt runs single x86 programs on ARM, TCG emulates a whole x86 machine, and HVF is Apple's hardware virtualization for ARM guests (fast).
- **Power cut (here):** SIGKILL of the QEMU process, the closest a VM gets to pulling the plug.
