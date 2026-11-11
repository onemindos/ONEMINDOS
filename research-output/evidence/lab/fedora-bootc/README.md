# Lab spike: Fedora bootc upgrade, greenboot rollback, power cut, rebase

Status: **PRE-REGISTERED** (written 2026-11-11T01:03Z, before any command ran). Results are appended below the line "Results" and never edit the criteria above it.

Requirement IDs served: R-1 (safe, user-controlled updates), R-3 (long-term maintainability), F-12 (fair test of Fedora IoT / bootc), M-6 (guard rails for one developer), F-8 (build from the founder's Mac), N-2 (runs on simple computers).

## Goal

Prove or disprove, on the founder's Apple Silicon Mac, that a Fedora bootc image built from a Containerfile can:

1. be built into a bootable disk and boot in QEMU;
2. upgrade with `bootc upgrade` from a registry;
3. **roll back automatically** (greenboot) when a deliberately broken update fails its health check;
4. survive a **power cut** (QEMU killed) in the middle of staging an update, and still boot the old, good system;
5. **rebase** to a different image (`bootc switch`) without reflashing the disk.

## Hypothesis

bootc keeps the running system read-only and stages the new one as a separate deployment, so: (a) a bad update that fails greenboot is reverted after the configured number of failed boots with no human action; (b) killing the VM mid-pull/stage leaves the booted deployment untouched; (c) `bootc switch` to another image works in place. Expectation from the desk research (research/platform/fedora-iot-and-redhat-edge-deep-dive.md §4): all five pass on aarch64 UEFI in QEMU; greenboot is a separate package, so it must be installed and wired into the image ourselves.

## Method (planned)

- Host: Apple M5 Max, macOS 27.2, 128 GB. Lima 2.3.0, QEMU 11.1.3 (Homebrew).
- **Build VM:** a disposable Lima VM (Fedora, aarch64, vz). All upstream build tools (podman, bootc-image-builder, a local `registry:2`) run inside it only.
- **Test VM:** host QEMU (`qemu-system-aarch64 -accel hvf`, UEFI edk2) boots the qcow2 disk built in the build VM. QEMU is the hypervisor only; nothing from the image runs on the host.
- Image: `FROM quay.io/fedora/fedora-bootc:<pinned digest>` plus greenboot, a test user (SSH key only, generated per run, never committed), and an insecure-registry entry for the lab registry.
- Images tagged in the lab registry: `v1` (good), `v2` (good, upgrade target), `v3-bad` (greenboot required check that always fails), `alt` (different content, rebase target).

## Pass / fail criteria (fixed before running)

| # | Test | PASS if | FAIL if |
|---|---|---|---|
| T1 | Build + boot | qcow2 from `v1` boots to SSH in under 5 min; `bootc status` shows `v1` booted | no boot, or build tool cannot run on aarch64 |
| T2 | Upgrade | `bootc upgrade` (registry now points to `v2`) then reboot; `bootc status` booted = v2 digest, rollback = v1; marker file `/usr/share/onemind/version` = `v2` | upgrade errors, or v1 lost |
| T3 | Bad update auto-rollback | after upgrading to `v3-bad` and rebooting, with **no manual commands**, the system ends up booted on the previous good deployment within the greenboot retry budget; journal shows greenboot failure + rollback | stays on the bad image, boot loops forever, or needs console action |
| T4 | Power cut mid-update | QEMU killed (SIGKILL) while `bootc upgrade` is pulling/staging; on restart the VM boots the previously booted deployment, `bootc status` is consistent, and a later `bootc upgrade` succeeds | VM does not boot, filesystem/ostree repo corrupted, or a half-staged deployment is booted |
| T5 | Rebase without reflash | `bootc switch <registry>/alt` + reboot; booted image = `alt`, marker file = `alt`; `/var` data written before the switch still present | switch errors or data in `/var` lost |
| T6 | Data survives | a file written in `/var/lib/onemind-test` at T1 is present after T2–T5 | file missing |

If a step is blocked (permission denial, no nested virt, tool fails on arm64), it is recorded verbatim in "Blocked" and turned into a founder-runnable test below. Permission denials are not worked around.

---

## Results

**Run:** 2026-11-11 01:03–01:34 UTC. **Outcome: T1, T2, T3, T5 and T6 PASS. T4 PASS for power cuts during download and deploy, but FAIL for a power cut during shutdown finalization:** after that cut, the next reboot silently downgraded the system by one version, and this reproduced in 2 of 2 runs. The root cause is a known, unfixed greenboot bug (upstream #219). One more finding: after an automatic rollback, nothing stops the default auto-update timer from re-installing the same bad image.

> ### Explain it like I'm the founder
> Think of a bootc device as having a **current** system and a **spare** (the previous version), both kept on disk. An update is downloaded next to them, and the device switches to it on the next reboot. **greenboot** is a watchdog that runs after each boot. If the new version fails its checks, it retries a few times and then switches back to the spare by itself.
>
> We built this on your Mac and broke it on purpose:
> - **Normal update:** it worked. Only the changed 13 MB downloaded, not the whole 1 GB.
> - **A broken update:** the device fixed itself in about a minute with nobody touching it.
> - **Pulling the plug while downloading or installing:** nothing broke, and the old version came back.
> - **Switching to a completely different OS image without reflashing:** it worked, and user data was kept.
>
> **Two catches matter for a product:**
> 1. If the power dies at one exact moment (the few seconds while the device shuts down to apply an update), the device boots fine but has quietly *armed itself to boot the older version next time*. This is a real greenboot bug, already reported upstream and not yet fixed.
> 2. After the device rolls back from a bad update, the built-in auto-updater will happily install that same bad update again within hours, unless the update channel is fixed or the timer is turned off.
>
> Both are fixable in OneMind's own layer, but OneMind would have to own those fixes. "Fedora gives you safe updates for free" is about 90 % true, not 100 %.

### Pinned versions and hashes

| Item | Value |
|---|---|
| Base image | `quay.io/fedora/fedora-bootc@sha256:a2e3dea74c6ba8b9c8dbdfd1a2e63fccc1d446cfce20e1efbeb567b63e9e940d` (tag 44, version 44.20261110.0, created 2026-11-10) [C-LAB-fedora-bootc-001] |
| Packages in the image | bootc 1.17.1, kernel 7.3.3-200.fc44, ostree 2026.4, bootupd 0.3.2, grub2-efi-aa64 2.12-66.fc44, systemd 259.10, greenboot 0.16.4-0.fc44 (added by us) [C-LAB-fedora-bootc-002, -003] |
| greenboot source read | greenboot-rs v0.16.4 `438eb9645f08dee53c3c766126f307d94847395a`; v0.16.5 `6efc3c109b54fec5e8a0ab575721258d28a85d9d` |
| Disk builder | `quay.io/centos-bootc/bootc-image-builder@sha256:dab86ee6b46dcade411b37f4e70b07d93b6a06da0dbfec6fe89247a220e0d9f8` (osbuild 193, image-builder 87.0.0) [C-LAB-fedora-bootc-016] |
| Lab registry | `docker.io/library/registry@sha256:a3d8aaa63ed8681a604f1dea0aa03f100d5895b6a58ace528858a7b332415373` |
| Build VM | Lima 2.3.0 `template:fedora-44`, vz, aarch64, 8 vCPU, 16 GiB, podman 5.8.1 |
| Test VM | QEMU 11.1.3 `-machine virt -accel hvf -cpu host`, 4 vCPU, 4 GiB, edk2-aarch64 UEFI, disk resized to 20 GiB |
| v1 disk (qcow2) | sha256 `0650c58fb68cf67431f279b9e61ac20685fd11429a110b820019227e51ad6517` (deleted after the run; rebuild it with the script) |
| Registry digests | v1 `sha256:98c97af1…19c7` · v2 `sha256:18807cd1…6e28` · v3-bad `sha256:e5c9cf58…75f1` · alt `sha256:c8abdb61…1be2` · v4-big (rebuilt 4×, random ballast) `4d653883…`, `ba3902dc…`, `42c741fb…`, `8d4a07df…` |

v1 boots with digest `9a6054d3…`, not the registry's `98c97af1…`, because the disk was built from local container storage, whose manifest differs from the pushed (recompressed) one. This is expected.

### How to rerun

Files are in `scripts/`. Everything upstream runs inside the Lima VM; the host only runs QEMU and ssh.

```bash
LAB=~/<lab-dir>/fedora-bootc; export LIMA_HOME=$LAB/lima; S=<this dir>/scripts
limactl create --name=bootc-build --tty=false --cpus=8 --memory=16 --disk=120 --vm-type=vz --mount-none \
  --set '.portForwards=[{"guestPort":5000,"hostPort":5000,"hostIP":"127.0.0.1"}]' template:fedora-44
limactl start bootc-build
limactl shell bootc-build -- sudo dnf -y install podman skopeo jq
ssh-keygen -t ed25519 -N '' -f $LAB/vm/lab_ed25519           # per-run key, never committed
limactl shell bootc-build -- mkdir -p /tmp/lab/src
limactl copy $S/Containerfile $S/10-onemind-marker.sh $S/build-in-vm.sh $LAB/vm/lab_ed25519.pub bootc-build:/tmp/lab/src/
limactl shell bootc-build -- bash -c 'cd /tmp/lab/src && ./build-in-vm.sh /tmp/lab/src /tmp/lab/src/lab_ed25519.pub /var/tmp/lab-out'
limactl copy bootc-build:/var/tmp/lab-out/qcow2/disk.qcow2 $LAB/vm/disk-v1.qcow2
$S/run-vm.sh start; source $S/lab.sh; wait_up; state           # T1
$S/run-tests.sh t2; $S/run-tests.sh t3                         # T2, T3
# for T4: build+push VARIANT=v4-big (see log 04a header), then:
$S/run-tests.sh t4 pull; $S/run-tests.sh t4 deploy; $S/run-tests.sh t4 finalize noupgrade
# T5: see the commands at the top of logs/05-rebase-and-data.log
$S/run-vm.sh stop; limactl delete -f bootc-build                # clean up
```

Networking: QEMU user networking is set to `net=198.18.0.0/24` (RFC 2544 benchmark range, not a real network), so the guest reaches the host's `127.0.0.1:5000` (the Lima-forwarded registry) at `198.18.0.2:5000`.

### Results per test

| # | Result | Evidence |
|---|---|---|
| T1 Build + boot | **PASS.** The container builds and bootc-image-builder writes a qcow2 on Apple Silicon inside Lima. First boot reaches SSH in 17 s; greenboot is green; `bootc status` shows v1 booted. Every later boot also took 16–20 s. | `logs/01-build.log`; [C-LAB-fedora-bootc-006, -016] |
| T2 Upgrade | **PASS.** `bootc upgrade` fetched 5 layers (13.1 MB of a 1.0 GB image) and staged in 2 s. After reboot, v2 is booted with v1 as the rollback deployment. | `logs/02-upgrade.log` [C-LAB-fedora-bootc-007] |
| T3 Bad update auto-rollback | **PASS.** After reboot into v3-bad: boot 1 fails and greenboot sets `boot_counter=3`; GRUB counts down over 3 more boots; at exhaustion greenboot runs `bootc rollback` and reboots. **71 s** from `reboot` to SSH on v2, and **4 boots of the bad image**, with no human action. The MOTD then says "FALLBACK BOOT DETECTED! Default bootc deployment has been rolled back." | `logs/03-bad-update-rollback.log`, `logs/03b-after-rollback.log` [C-LAB-fedora-bootc-004, -005, -008] |
| T3 follow-up | **RISK.** The channel tag still pointed at v3-bad. `bootc upgrade --check` printed "No changes", but plain `bootc upgrade` **re-staged v3-bad**. `bootc-fetch-apply-updates.timer` is enabled by default (`bootc upgrade --apply`, every ~8 h, plus a 2 h random delay), so an unattended device would loop: install bad → 4 failed boots → roll back → repeat. | `logs/03b-after-rollback.log` [C-LAB-fedora-bootc-009] |
| T4a Power cut during download | **PASS.** SIGKILL 4 s into a 1.6 GB pull. The device boots the old v2 image; `ostree fsck`: "no errors found"; retry succeeded. The previously staged (bad) deployment was also discarded, because staged deployments are only finalized at clean shutdown. | `logs/04a-powercut-pull.log` [C-LAB-fedora-bootc-010] |
| T4b Power cut during deploy | **PASS.** SIGKILL right after `Deploying...` was printed. Old image boots, fsck clean, retry succeeded. | `logs/04b-powercut-deploy.log` [C-LAB-fedora-bootc-010] |
| T4c Power cut during shutdown finalization | **FAIL (on the next boot).** SIGKILL 1 s after `systemctl reboot` with an update staged. The healthy unchanged image boots (good), but greenboot logs `GRUB kernel fallback detected: expected deployment sha256:8d4a…, booted sha256:42c7…` and runs `bootc rollback`. The **next plain reboot boots the older deployment** (`ba39…`). Reproduced 2/2. Root cause: on shutdown the trigger writes `greenboot_next_deployment_id` *before* ostree finishes finalizing. If power dies between the two, greenboot 0.16.4 misreads the mismatch as a GRUB fallback. | `logs/04c-…`, `logs/04d-…`, `logs/04e-finalize-root-cause.log` [C-LAB-fedora-bootc-011] |
| T5 Rebase | **PASS.** `bootc switch …/onemind/lab-alt:latest` plus one reboot: the alt image is booted (marker `alt`, tmux present); switching back to `…/lab:stable` also worked. No reflash. | `logs/05-rebase-and-data.log` [C-LAB-fedora-bootc-015] |
| T6 Data survives | **PASS.** `/var/lib/onemind-test/data.txt` written at T1 is intact after T2–T5, including 4 power cuts and 2 rebases. | `logs/05-rebase-and-data.log` |

### What upstream says about T4c (independent confirmation)

- greenboot-rs issue **#219** (open, filed 2026-10-11) describes the same downgrade, the same root cause and a proposed fix: treat a mismatch as a fallback only when the booted deployment is not the default [C-LAB-fedora-bootc-012].
- The newest release, **v0.16.5 (2026-11-04)**, which is also main HEAD on 2026-11-10, still uses the bare `booted_id != expected_id` test, so the bug is unfixed upstream [C-LAB-fedora-bootc-013].
- Issue **#218** (open) says the rollback trigger never runs at shutdown. It **did not reproduce here**: with stock units on fedora-bootc 44.20261110.0 and systemd 259.10, the trigger ran and T3 worked [C-LAB-fedora-bootc-014]. It may depend on systemd or image version; one environment cannot rule it out.

### Smaller observations

- The `greenboot-default-health-checks` *wanted* check `01_update_platforms_check.sh` logs an ERROR on every boot of a plain bootc image (it looks for `/etc/ostree/remotes.d`). It is harmless but noisy, so OneMind should disable it in its image [C-LAB-fedora-bootc-017].
- `bootc container lint` gives 3 warnings when `dnf install` runs in the Containerfile (`/var/log`, `/run`, `/var` tmpfiles). The image still works. A production Containerfile should clean these.
- Cost per update: a code-only change downloads only the changed layers (13 MB here). Ballast tests show a 1.6 GB layer change downloads 1.6 GB, so layer layout matters for update size over cellular or mesh links.

### What competitors do (rollback and power-loss safety)

| Who | Mechanism | Bad-update handling | Power-cut handling | Their constraints | Constraint fit for OneMind |
|---|---|---|---|---|---|
| **Fedora IoT / fedora-bootc** (this lab) | ostree/bootc deployments plus greenboot | Auto-rollback after N failed boots (PASS, measured) | Safe during download and deploy; **bug at finalize** (#219) | Fedora team, 13-month release life; x86_64 and UEFI aarch64 | **Medium-high:** works on x86 and UEFI arm, k3s-capable; OneMind must patch #219 and own the channel discipline |
| **RHEL image mode / Device Edge** | same bootc + greenboot-rs (RHEL 10.2, per desk research) | same | same code path, so #219 likely applies until fixed (UNVERIFIED on RHEL) | Paid subscription, x86-64-v3 floor on RHEL 10 | Medium: industrial tier only |
| **Home Assistant OS** | RAUC A/B, GRUB tries the new slot 3×, slot marked good once Supervisor starts (context/03 row "HAOS RAUC flow") | A/B fallback | A/B writes the inactive slot, so the active one is untouched | Single-purpose appliance, Docker, no k8s | High as a *pattern* (commit after the app layer is up) |
| **umbrelOS** | Rugix A/B, never auto-installs (context/03 rows "umbrelOS image/updates", "update UX") | Auto rollback on failure | A/B | Consumer box, Docker, small team | High for UX: no auto-install, which also avoids the T3 re-apply loop |
| **Olares** | In-place update, no OS rollback found (context/03) | None at OS level | n/a | k3s, AGPL | Low: the gap OneMind must not copy |
| **ADR-001 path (Debian 13 + Rugix)** | A/B partitions plus a health-gated commit OneMind writes | DIY gate (see `lab/debian-rugix`) | A/B | One developer | The comparison baseline; see the sibling labs `debian-rugix` and `rauc` |

The sibling spike `lab/w2-fedora-bootc-greenboot` tests the same lineage with a **k3s readiness** greenboot check. This spike does not repeat that; it covers upgrade, power cut and rebase.

### Recommendations (with requirement IDs)

1. **Treat bootc + greenboot as a proven update engine for the Fedora/RHEL profile**: atomic, small layer-only downloads, automatic rollback, rebase without reflash. (R-1, R-3, F-12, M-6, F-8)
2. **If OneMind ships greenboot, carry a fix for #219.** For example, a pre-start check that clears a stale `greenboot_next_deployment_id` when the booted deployment is already the default, as #219 proposes, or upstream the fix. Re-run T4c as a release gate. (R-1, R-3)
3. **Never let the auto-update timer re-install a rolled-back image.** Either disable `bootc-fetch-apply-updates.timer` and drive updates from OneMind's own updater (matches R-1 "update when they want" and the umbrelOS/HAOS no-auto-install pattern), or have the updater record rolled-back digests and refuse them. The release pipeline must also move the channel tag off a bad digest. (R-1, R-2, M-6)
4. **Use `bootc switch` for edition or profile changes** (for example Lite → TAK profile, or Fedora → CentOS Stream/RHEL tracks) instead of reflashing. It worked in place with data intact. (P-5, P-8, F-14, F-12)
5. **Disable `01_update_platforms_check.sh`** in OneMind images and add OneMind's own required checks (k3s readiness, as in the W2 spike). (R-2)

### Blocked or not covered

- **Wayback archiving:** `web.archive.org/save/...` was **denied by the permission classifier** ("Public Data-Sharing Upload"). I did not work around it. The two load-bearing issue pages are saved as text plus SHA-256 in `evidence/sources/LAB-fedora-bootc/`. Zeus can save `github.com/fedora-iot/greenboot-rs/issues/219` and `/218` manually.
- **Not tested here:** x86_64 (it would need TCG emulation on this Mac), real hardware (Pi 5, which has an open bootc boot bug per the desk research; Jetson Orin), CentOS Stream 10 bootc, signed images (`sigstore`/`containers-policy`), and a k3s health gate (W2 spike). Founder-runnable tests follow.

### Founder-runnable tests (real hardware)

Run these on the Dell 5540 or Beelink (x86_64 UEFI) with a USB stick. Build the same `scripts/Containerfile` with `--platform linux/amd64` in a Linux VM, and write the disk with bootc-image-builder `--type raw` (or `anaconda-iso` to install).

| # | Commands | PASS if |
|---|---|---|
| H1 | Flash, boot, then `sudo bootc status` | Booted image = your registry ref; `journalctl -u greenboot-healthcheck` shows "passed" |
| H2 | Push v3-bad to `:stable`, then `sudo bootc upgrade && sudo reboot`. Touch nothing for 5 min. | `cat /usr/share/onemind/version` = previous good version; journal of boot -1 shows "Rollback successful" |
| H3 | Push a big update, run `sudo bootc upgrade`, and pull the **power cord** while it prints layer progress | Boots the old version; `sudo ostree fsck` shows no errors |
| H4 | `sudo bootc upgrade` (staged), `sudo reboot`, and pull the cord within 1–2 s of the screen going dark. Power on. Then run `sudo ostree admin status` and reboot once more. | PASS = still on the same version after the second reboot. **Expected FAIL with stock greenboot 0.16.4/0.16.5** (it downgrades), which confirms #219 on hardware. |
| H5 | `sudo bootc switch <registry>/onemind/lab-alt:latest && sudo reboot` | Marker = `alt`, `/var` data intact |

### Glossary

- **bootc:** a tool that installs and updates a whole Linux OS from a container image (the same format Docker uses).
- **Deployment:** one complete, read-only copy of the OS on disk. bootc keeps the *booted* one, a *rollback* one and, during an update, a *staged* one.
- **Staged / finalize:** an update is prepared (staged) while the system runs, and only made bootable (finalized) during the next clean shutdown.
- **greenboot:** a health-check service. It runs checks after boot; if required checks fail it retries and then rolls back.
- **grubenv / boot_counter:** a small file the bootloader (GRUB) reads before Linux starts. greenboot stores the retry counter there.
- **Rebase (`bootc switch`):** point the device at a different OS image and switch to it on the next reboot, with no reflashing.
- **Channel tag:** the image tag a device follows (here `:stable`). Moving it is how a release is published.
- **ostree fsck:** an integrity check of every stored OS file.
- **HVF:** Apple's Hypervisor.framework, which lets QEMU run arm64 VMs at near-native speed on Apple Silicon.
