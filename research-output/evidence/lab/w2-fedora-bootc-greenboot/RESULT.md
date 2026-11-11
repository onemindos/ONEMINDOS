# Result: W2-L1 Fedora bootc + greenboot, health-gated rollback with k3s

**Run:** 2026-11-10 (UTC 2026-11-11 01:16–02:07) · **Pre-registration:** [README.md](README.md) (written before any test) · **Versions and digests:** [versions.txt](versions.txt) · **Raw logs:** `h1.log` … `h4.log` (lab registry and device addresses redacted for the public repo)

| ID | Pre-registered pass criterion | Observed | Verdict |
|---|---|---|---|
| H1 | greenboot succeeds; node Ready; `bootc status` shows the digest | Fedora Linux 45 (IoT Edition), kernel 7.3.3-300.fc45.aarch64, root = composefs (read-only), SELinux Enforcing. k3s v1.37.2+k3s1 with `--selinux` and k3s-selinux 1.6 (coreos build). greenboot's `50-k3s-ready.sh` passed after 25 s, then `boot_success=1`. SSH up 161 s after power-on (first boot) | **PASS** |
| H2 | back on the good digest within **15 min** and **0 manual commands** after the first reboot | Back on the good digest, GREEN, with **0 manual commands**. Sequence: first failure → `boot_counter=3` → boots with counter 2, 1, 0 → "Rollback successful" (`bootc rollback`) → "FALLBACK BOOT DETECTED… rolled back" → health check passed. **1,926 s** total (4 failed boots, about 7 min each) | **Automation PASS / time FAIL** |
| H3 | after kill -9 during staging, next boot = good digest, GREEN | (a) kill during the pull of a 729 MB update (`bootc switch quay.io/fedora/fedora-bootc:45`): booted good, nothing staged, GREEN. (b) staged the bad image, `systemctl reboot`, kill 2 s later, while `ostree-finalize-staged` had started (journal shows the unit starting): booted good, staged update discarded, GREEN | **PASS** (1 trial each) |
| H4 | measurement recorded with method | After 5 min idle, 4 GiB RAM, 4 vCPU, k3s default add-ons (3 Completed helm-install jobs, 5 Running pods): `free` used 1,097 MiB of 3,880; k3s-server RSS 674 MiB; containerd RSS 176 MiB; `systemctl show k3s -p MemoryCurrent` = 1.69 GiB (includes page cache) | **Recorded** |

## Why H2 took 32 minutes (and how to shorten it)
- Our own check waits up to 300 s for k3s before it declares failure (`files/50-k3s-ready.sh`). With a broken k3s, every boot pays the full 300 s plus about 90 s of boot.
- greenboot's default `GREENBOOT_MAX_BOOT_ATTEMPTS=3` means 1 + 3 failed boots before rollback (greenboot-rs@6efc3c1 `src/main.rs` failure branch).
- To be tested, not measured: a 90 s timeout and `MAX_BOOT_ATTEMPTS=1` would give about 2 failed boots of about 3 min each. For a robot, the right number is a product decision (W3: retries protect against transient failures such as no network at first boot).

## What this proves for the decision (DC-01, DC-12)
1. The "commit only when k3s is healthy" rule in ADR-001 D3 is **already implemented upstream** by greenboot + bootc, needing one ~20-line check script.
2. Rolling back the OS slot did **not** break the k3s datastore in this test. Both images carried the **same** k3s version. The cross-minor case (DC-12: a newer k3s migrates the datastore, then the OS rolls back to an older k3s) was **not** tested and remains the main open risk for any "k3s inside the image" design (W3/W4).
3. The power-cut behaviour of ostree/bootc staging matched the design (old deployment kept until finalization completes) in 2 of 2 trials.

## Limits
- QEMU/KVM aarch64 on Apple Silicon, virtio disk with writeback cache: not a Raspberry Pi, not eMMC/SD, not Jetson. The Pi bootc boot bug (#82) cannot be reproduced here.
- Single runs; no statistics.
- Lab-only conveniences, which a product image must not ship: passwordless sudo for the `lab` user, a plain-HTTP registry on the QEMU gateway, and image signature verification not enforced (`containers-policy` default).

## Reproduce
In a disposable Fedora 45 VM with podman, qemu-kvm and edk2-aarch64: `REG=<QEMU user-net gateway>:5000 ./run-build.sh`, then `./dut.sh boot`, then `REG=… ./run-h2.sh` and `REG=… ./run-h3.sh`. The lab VM was deleted after the run.
