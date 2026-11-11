# Lab spike LAB-minimal-image-dc20: the same minimal image, built from a distro and from source

**Status:** PRE-REGISTERED. Goal, hypotheses, method and pass/fail criteria were written on 2026-11-11 before any build, scan or boot ran. The "Results" part below the line is filled in after the run. Nothing above that line is changed after the run, except to add links.

**Decision-critical question:** DC-20 (bank Q3, Q15) · closes critic gap **N14** (`evidence/critic/pass-2.md`) · **Serves:** F-7, M-6, R-3, RS-4 (and the CRA/SBOM evidence for W6)

> **Explain it like I'm the founder.** There are two ways to make your own operating system image. **(a) Start from a distribution**, like Debian: you pick ready-made packages that Debian's volunteers build and patch, and a tool (here **mkosi**) assembles them into a disk image. **(b) Build everything from source**, like Home Assistant OS does with **Buildroot**: you compile the compiler, the kernel and every program yourself, and only what you list goes in. Option (b) should give a smaller image with fewer known security holes ("CVEs") on the scanner report, which the EU Cyber Resilience Act will reward. But you then own every patch, and builds take much longer. Earlier research argued both sides from documents only. This spike measures it: the same small "OneMind-like" core (Linux kernel, systemd, networking tools, and everything k3s needs), built both ways on your Mac, then weighed, scanned and timed with the same tools on the same day.

## 1. Goal

Build a minimal **x86_64** OneMind-like core image two ways and measure four numbers for each, on the same build host, on the same day:

| Leg | How | Tool |
|---|---|---|
| **A: distro-based** | Debian 13 "trixie" packages assembled into a bootable UEFI disk image | **mkosi** (Debian package from trixie; fallback: mmdebstrap, recorded as a deviation) |
| **B: from source** | Cross-compiled toolchain, kernel and userspace, HAOS-style | **Buildroot 2026.02.3** (the 2026 LTS branch), starting from its `pc_x86_64_efi_defconfig` |

**Same functional content in both** ("k3s-ready userspace"): UEFI boot, Linux kernel with the container features k3s needs (cgroup v2, namespaces, overlayfs, netfilter/nftables, bridge, br_netfilter, VXLAN, veth), systemd as init, udev, util-linux mount tools, kmod, iproute2, iptables (nft backend), ca-certificates, OpenSSH server, e2fsprogs. The same pinned **k3s v1.37.2+k3s1** binary is copied into both images at `/usr/local/bin/k3s` (k3s brings its own containerd, runc, flannel and CNI plugins).

**Measured for each leg:**

| ID | Metric | Exact method |
|---|---|---|
| M1 | Image size | (i) installed root filesystem bytes (`du -sb`, with and without k3s); (ii) the bootable disk image's used bytes; (iii) the root filesystem as `tar | zstd -19` bytes (an update-bundle proxy) |
| M2 | SBOM component count | **syft v1.57.1** on the root filesystem directory, total artifacts and by type. For Buildroot also Buildroot's own CycloneDX SBOM (`utils/generate-cyclonedx` from `make show-info`), because Buildroot images carry no package database and a filesystem scanner is expected to miss most components |
| M3 | Known-CVE count at build date | **grype v0.121.3** with one vulnerability DB pinned for both legs (DB build timestamp recorded). Count unique (CVE, package) matches and unique CVE IDs, by severity, with and without the k3s binary, and with `--only-fixed`. Leg B is scanned two ways: syft-on-rootfs (what a customer's scanner sees) and Buildroot's CycloneDX SBOM (what is actually inside) |
| M4 | Build time | Wall clock on the same Lima VM (Debian 13 arm64, Apple M5 Max host): (i) clean build including all downloads, (ii) clean build with downloads cached, (iii) **incremental rebuild** after one package change (Buildroot: rebuild one package + regenerate image; Debian: change one package + re-run mkosi with its package cache) |

Plus one function check (F1): each image boots under QEMU x86_64 (TCG, UEFI/OVMF) to multi-user, `k3s check-config` reports no missing required items, and `k3s server` brings its node to `Ready`.

## 2. Hypotheses (written before the run)

- **H1 (size):** Buildroot's root filesystem without k3s is at least **4x smaller** than Debian's (expected: Buildroot about 40-80 MB, Debian about 250-450 MB). With the ~70 MB k3s binary added to both, the gap shrinks to under 3x.
- **H2 (SBOM):** syft finds **at least 3x fewer components** in Buildroot than in Debian, and a large part of the Buildroot difference is *invisibility*, not absence: Buildroot's own CycloneDX SBOM lists more components than syft finds in the Buildroot rootfs.
- **H3 (CVEs):** grype reports **at least 50% fewer** unique CVE IDs for Buildroot (its own SBOM) than for Debian, excluding the shared k3s binary. Most Debian matches are low/negligible or "won't fix" entries; with `--only-fixed` the gap is smaller.
- **H4 (CVE noise from k3s):** the shared k3s binary contributes the same CVE set to both images, and it is a material share of the total for the Buildroot leg (shown by scanning with and without it).
- **H5 (build time):** Buildroot's clean build takes **at least 5x longer** than mkosi's (expected: Buildroot 25-90 min, mkosi under 10 min); Buildroot's incremental rebuild is **under 15 minutes**.
- **H6 (method):** Both images can be built from one script each, from an Apple Silicon Mac, inside a Lima VM, with no x86 hardware.

## 3. Pass / fail criteria (frozen before the run)

The spike **passes as a measurement** only if T0 to T4 all pass. A test that cannot run is recorded as **BLOCKED** with the reason, never as PASS.

| ID | Test | PASS if | FAIL if |
|---|---|---|---|
| T0 | Build A | One script inside the Lima VM produces a bootable x86_64 UEFI disk image from Debian 13 packages with no manual edits | Manual steps needed, or no image |
| T1 | Build B | One script inside the Lima VM produces a bootable x86_64 UEFI disk image from Buildroot 2026.02.3 with no manual edits | Same |
| T2 | Function (F1) | Both images boot in QEMU to multi-user; `k3s check-config` shows no missing *required* item; `k3s server` node reaches `Ready` within 15 min under TCG | Either image fails to boot, or k3s cannot start on it |
| T3 | Measure | M1-M4 recorded for both legs with tool versions, the grype DB timestamp and the exact commands | Any metric missing for either leg |
| T4 | Reproducible record | Scripts, configs, `SHA256SUMS` of inputs and outputs, and masked trimmed logs are in this folder; no compiled caches committed | Missing |

**How the result is read for DC-20 (decided now, not after seeing numbers).** The W3 steelman's flip condition is "materially fewer CVEs **and** an incremental rebuild under 1 h per board, **plus** a working CUDA path on a Buildroot host" (`01-FOUNDATION-DECISION.md` §6.2, `evidence/adversarial/W3-steelman.md`).

- "Materially fewer CVEs" means: **at least 50% fewer unique CVE IDs** (all severities) **and** at least 50% fewer High+Critical, Buildroot (own SBOM) vs Debian, both excluding k3s.
- If both CVE thresholds and the < 1 h incremental rebuild hold, the spike **supports** the Buildroot steelman on C3/C5 evidence. The CUDA clause is **not tested** here (no NVIDIA hardware, x86_64 only), so the spike alone **cannot flip** ADR-001 D1; it can only move DC-20 from "partial, no measurement" to "measured".
- If either CVE threshold fails, the CRA/SBOM argument for Buildroot is **weakened** in the decision record.
- If Buildroot's incremental rebuild exceeds 1 h, the C5 (solo-developer operability) score of 2 for Buildroot stands.
- Hypotheses H1-H6 are each reported as **held / not held**, with the number.

## 4. Design

- **Build host:** a disposable Lima VM (`vz`, Debian 13 arm64, 12 vCPU, 24 GiB RAM, 100 GiB disk) on the Mac. All upstream code (mkosi, apt, Buildroot, its downloads, syft, grype, k3s, QEMU guests) runs only inside it. The VM has no host home mount; the output folder is copied out at the end.
- **Leg A cross-architecture:** the VM is arm64 and the image is amd64. Maintainer scripts run through `qemu-user-static` binfmt, as in the earlier `rauc` spike.
- **Leg B cross-architecture:** Buildroot builds its own cross toolchain (internal toolchain, glibc), so the arm64 host does not matter. Buildroot downloads are cached in `dl/` (not committed).
- **Kernel:** leg A uses Debian's stock `linux-image-amd64` (generic, large module set). Leg B uses the Linux version Buildroot 2026.02.3 defaults to, with `pc_x86_64_efi_defconfig`'s kernel config plus a fragment for k3s. This difference is deliberate: it is exactly the trade-off DC-20 asks about, and it is reported, not hidden.
- **Scanning:** syft and grype run in the same VM on the same day; one grype DB is downloaded once and used offline for every scan (`GRYPE_DB_AUTO_UPDATE=false`).
- **Fairness guards:** the same k3s binary in both; size and CVE numbers reported with and without it; no `apt` docs/man pages trimmed beyond mkosi defaults unless also stated (a second "trimmed Debian" number may be reported, labelled).

## 5. Requirement IDs served

**F-7** (decide whether to own kernel/image), **M-6** (solo-developer operability), **R-3** (long-term maintainability), **RS-4** (evidence for the base OS decision). Feeds `03-base-os.md` §11, `28-KERNEL-IMAGE-OWNERSHIP-AND-DEV-TOOLCHAIN.md`, `evidence/qbank/W2.md` Q3/Q15 and `01-FOUNDATION-DECISION.md` §6.2.

## 6. Glossary

| Term | Meaning |
|---|---|
| Distro-based image | An OS image assembled from a Linux distribution's pre-built packages (Debian `.deb` files) |
| From-source image | An OS image where every program is compiled from source by your own build system |
| mkosi | systemd's "make operating system image" tool; turns a list of distro packages into a disk image |
| Buildroot | A from-source embedded Linux build system (Makefiles + Kconfig); Home Assistant OS uses a fork of it |
| LTS | Long-term support release line (Buildroot's February release each year) |
| SBOM | Software Bill of Materials: the list of every component in the image, with versions |
| CycloneDX | A standard SBOM file format |
| syft / grype | Anchore's open-source SBOM generator and vulnerability scanner |
| CVE | A public ID for one known security vulnerability |
| TCG | QEMU's software CPU emulation (here: an x86_64 PC emulated on an Arm Mac) |
| binfmt / qemu-user | Lets an arm64 Linux run single amd64 programs, used during cross-architecture package installs |

---

## Results

**Run:** 2026-11-11, 07:12–08:55 UTC, one Lima VM, one grype DB (built 2026-11-11T06:21:32Z). Pre-registration hash: `evidence/lab/PREREGISTRATION.md`. Pinned versions: [`versions.md`](versions.md). Hashes: [`SHA256SUMS`](SHA256SUMS). Claims: `evidence/claims/LAB-minimal-image-dc20.csv` (C-LAB-minimal-image-dc20-001…021).

**Verdict:** the measurement is **complete** (T0, T1, T3, T4 PASS), but **T2 FAILS for leg A as built**. The Debian image boots and k3s reaches `Ready`, but `k3s check-config` returns `STATUS: fail` because Debian's kernel enables AppArmor and the image lacks `apparmor_parser`. A labelled variant with one extra package (`apparmor`) passes. Under the frozen rule the spike does not pass cleanly. The DC-20 reading is: **the "materially fewer CVEs" threshold fails clearly** (7–18% fewer IDs, not 50%), so the CRA/SBOM argument for Buildroot is **weakened**. Buildroot's incremental builds are well under 1 h, so the build-time argument against Buildroot is also weaker than the steelman's "75–160 min per board". ADR-001 D1 (distro base) is **unchanged**, and the reasons shift (see 7.7).

> **Explain the result like I'm the founder.** We built the same small k3s-ready OS twice: once from Debian's ready-made packages, once from source like Home Assistant OS. Both booted and both ran Kubernetes. The from-source image is about **4–6 times smaller**. That is real, and it matters for update downloads and small boards. But the security scanner found **almost the same number of known holes** in both (589 vs 498–549). The reason is that about three-quarters of them are in the **Linux kernel**, and the kernel is the same code whichever way you build it. Outside the kernel the from-source image has fewer holes (58–109 vs 161). But Debian's security team has already looked at every one of its 161 and said "nothing to patch yet" or "not worth patching", while **32–53 of Buildroot's have a fix upstream that nobody has applied yet**. With Buildroot, that patch work would be yours. So the small image is nice, but it doesn't make you safer for free. It moves the security work from Debian's team onto you. Keep Debian. Spend the effort on **updating the kernel quickly**, because that is where most of the risk is either way.

### 7.1 Pre-registered tests

| ID | Result | Evidence |
|---|---|---|
| T0 Build A | **PASS**: `scripts/build-a.sh` builds a bootable UEFI image from Debian 13.7 packages; no manual edits to the image. (Script run 1 failed only at copying the output because mkosi 25.3 writes it to the config folder; the path was fixed and a full clean run repeated. Times below are from that run.) | `results/times-legA.txt`, `logs/legA-build-clean.tail.log` |
| T1 Build B | **PASS**: `scripts/build-b.sh` builds a bootable UEFI image from Buildroot 2025.02.19, first try | `results/times-legB.txt`, `logs/legB-build-clean.tail.log` |
| T2 Function | **Leg B PASS**: boots, `check-config` `STATUS: pass`, node `Ready` 40 s after k3s start (uptime 102 s). **Leg A FAIL as built**: boots, node `Ready` 40 s after start (uptime 152 s), but `check-config` `STATUS: 1 (fail)`, cause `apparmor: enabled, but apparmor_parser missing (fail)`. Labelled variant **A2 (+`apparmor`) PASS** (`STATUS: pass`, `Ready`) | `logs/f1-*-dc20-f1.out`, `logs/f1-*-dc20-check-config.txt`, `logs/f1-serial-*.trimmed.log` |
| T3 Measure | **PASS**: M1–M4 for both legs, tool versions and DB timestamp recorded | `results/`, `sbom/` |
| T4 Record | **PASS**: scripts, configs, hashes and masked, trimmed logs; no images, caches or compiled files committed | this folder |

### 7.2 M1 · Size (bytes; MB = 10^6)

| | Debian 13 (mkosi) | Buildroot 2025.02.19 | Debian ÷ Buildroot |
|---|---|---|---|
| Root filesystem, **without** k3s (pre-registered M1(i)) | 293.6 MB | 82.4 MB | **3.6x** |
| Root filesystem, with k3s (81.7 MB binary) | 375.3 MB | 164.1 MB | 2.3x |
| ESP (kernel + initrd + bootloader) | 155.6 MB (UKI with a 130.6 MB generic initrd) | 9.8 MB (bzImage + GRUB, no initrd) | 15.9x |
| Root + ESP, without k3s | 449.1 MB | 92.2 MB | **4.9x** |
| Root as `tar \| zstd -19`, without k3s (update-bundle proxy) | 154.5 MB | 27.1 MB | **5.7x** |
| Root as `tar \| zstd -19`, with k3s | 230.0 MB | 102.8 MB | 2.2x |
| Disk image, allocated (M1(ii)) | 801.6 MB | 215.9 MB | 3.7x |
| Files in root | 10,645 | 2,764 | 3.9x |
| Kernel modules shipped | 4,230 | 59 | 72x |
| Variant A2 (+apparmor) root without k3s | 296.4 MB (+2.8 MB) | — | — |

Source: `results/size-*.txt` [C-LAB-minimal-image-dc20-009].

### 7.3 M2 · SBOM component count

| | Debian 13 (mkosi) | Buildroot 2025.02.19 |
|---|---|---|
| syft on the root filesystem, total (with k3s) | 4,388 | 80 |
| … distro packages | 139 `deb` (85 source packages) | 0 (no package database) |
| … kernel + modules | 1 + 4,230 | 1 + 59 |
| … other binaries found by syft | 0 | 2 |
| … Go modules inside the k3s binary | 18 | 18 |
| Build system's own SBOM | — (dpkg database *is* the SBOM) | CycloneDX from `utils/generate-cyclonedx`: **27 target packages** + 60 build-host tools marked `scope: excluded` |
| k3s payload unpacked at first start (not visible pre-boot) | 515 (514 Go modules) | 515 (same) |

A filesystem scanner is nearly blind on a Buildroot image: it sees 3 of 27 shipped packages. Only the build system's SBOM is complete [C-LAB-minimal-image-dc20-010]. The k3s binary hides 515 components that pre-boot scans miss in both legs [C-LAB-minimal-image-dc20-014].

### 7.4 M3 · Known CVEs at build date (grype 0.121.3, DB 2026-11-11T06:21:32Z, without k3s)

Unique vulnerability IDs (all are CVE IDs), with Critical+High in brackets. "BR-resolved" removes matches that Buildroot's SBOM itself marks resolved (patched or ignored by Buildroot, 71 entries).

| Scan | All | Kernel | Userspace | Userspace with a fix available |
|---|---|---|---|---|
| **Debian** (syft → grype; distro tracker data) | **589 (186)** | 428 (149) | 161 (37): 74 `not-fixed`, 87 `wont-fix` | **0** |
| **Buildroot**, own target SBOM | **549 (195)** | 440 (154) | 109 (41) | 53 |
| **Buildroot**, own target SBOM minus BR-resolved | **498 (175)** | 440 (154) | 58 (21) | **32** |
| Buildroot, what a customer's scanner sees (syft on rootfs) | 451 (159) | 440 (154) | 11 (5) | 6 |
| Buildroot variant, kernel 6.12.117, target SBOM minus BR-resolved | 486 (170) | 428 (149) | 58 (21) | 32 |
| `--only-fixed`: Debian / Buildroot target / Buildroot minus BR-resolved | 361 (132) / 426 (154) / 405 (148) | 361 / 373 / 373 | 0 / 53 / 32 | — |
| k3s binary (same in both) | +1 | — | — | 1 |
| k3s payload unpacked at first start (same in both) | +22 (8 High) | — | — | 13 |

Where the userspace numbers come from (`results/userspace-by-package.txt`):
- **Debian:** krb5 (23, pulled in by OpenSSH's GSSAPI), OpenSSH (30), glibc (22), sqlite3 (14), elfutils (7), gcc-14 (6), util-linux (5), OpenSSL (5), and others. Every one is triaged by Debian as `not-fixed` or `wont-fix`.
- **Buildroot:** OpenSSH 9.9p2 (25; fixes in 10.x), glibc 2.41 (12; fixes in 2.45), util-linux 2.40.4 (11), GRUB 2.12 (4), systemd 256.17 (3; fixes in 257.11+), expat 2.9.0 (4). Some CPE matches are false positives: OpenSSH is reported "fixed in 9.9p2" against 9.9p2 itself.

**Reading.**
1. **The kernel is 73–80% of all IDs in both legs, and its count follows the kernel version, not the build method.** Debian 6.12.116 and Buildroot 6.12.117 both match 428 kernel IDs; Buildroot's 6.12.112 matches 440 [C-LAB-minimal-image-dc20-012].
2. **Pre-registered threshold (≥ 50% fewer IDs and ≥ 50% fewer C+H): not met.** Buildroot has 6.8% / 15.4% / 17.5% fewer IDs (target / minus BR-resolved / kernel 6.12.117) and +4.8% / −5.9% / −8.6% C+H [C-LAB-minimal-image-dc20-011].
3. **Userspace is where the two differ:** Buildroot has 32–64% fewer IDs, but a third to a half of them are fixable upstream and unapplied in the LTS branch. Debian's are all triaged. The number is lower; the work is higher [C-LAB-minimal-image-dc20-013].
4. **Method caveat:** Debian's userspace is matched against Debian's security tracker (with triage), and Buildroot's against NVD CPE ranges (no triage, some false positives). The kernel is matched by NVD CPE in both legs, so the kernel rows are directly comparable.

### 7.5 M4 · Build time (Lima VM, 12 vCPU / 24 GiB on Apple M5 Max, arm64 host building x86_64)

| | Debian 13 (mkosi 25.3) | Buildroot 2025.02.19 | Buildroot ÷ Debian |
|---|---|---|---|
| (i) Clean, all downloads | **180 s** | **1,716 s (28.6 min)** | 9.5x |
| (ii) Clean, downloads cached | 203 s | 779 s (13.0 min) | 3.8x |
| (iii) Incremental | 49 s (mkosi `--incremental`, one file changed) | **29 s** (OpenSSH rebuilt + image regenerated); **102 s** (kernel 6.12.112 → 6.12.117) | — |
| Cache / work space | 751 MB package cache | 1.1 GB downloads + 14 GB build tree | — |

The biggest Buildroot steps (`results/buildroot-time-by-package.txt`) were the kernel, host-cmake, the two GCC stages, OpenSSL (host + target) and GRUB. Leg A spends most of its time in qemu-user emulating amd64 maintainer scripts and building the initrd, which is why its cached run is no faster than its first.

### 7.6 Hypotheses

| | Held? | Number |
|---|---|---|
| H1 size ≥ 4x (root, no k3s); < 3x with k3s | **Not held** on the pre-registered metric (3.6x); held on root+ESP (4.9x) and compressed (5.7x). With-k3s part held (2.3x) | 7.2 |
| H2 ≥ 3x fewer components; Buildroot SBOM > syft view | **Held**: 139 debs / 85 source packages vs 27 target packages (5.1x / 3.1x); syft sees 3 of 27 | 7.3 |
| H3 ≥ 50% fewer CVE IDs | **Not held**: 7–18% fewer | 7.4 |
| H4 k3s CVEs identical in both and material for Buildroot | **Partly**: identical (held); the binary adds 1 ID (not material); the unpacked payload adds 22 IDs (about 4% of Buildroot's total, about a quarter of its userspace), invisible to pre-boot scans | 7.3, 7.4 |
| H5 Buildroot clean ≥ 5x slower; incremental < 15 min | **Partly**: 9.5x with downloads, 3.8x cached; Buildroot clean 28.6 min (inside the 25–90 min guess); incremental 29 s / 102 s (held) | 7.5 |
| H6 both from one script each, on a Mac, in Lima | **Held** | 7.1 |

### 7.7 What this means for DC-20 and ADR-001

- **The flip condition is not met.** The steelman needed "materially fewer CVEs **and** < 1 h incremental builds **plus** a CUDA path" (01 §6.2). The < 1 h clause holds easily. The CVE clause fails. The CUDA clause was not tested. **ADR-001 D1 (distro base) stands.**
- **The reasons change.** 01 §6.2 says Buildroot loses partly on "per-board CI of 75–160 minutes" (W3 steelman §8, a full HAOS-scale build). For a minimal OneMind core, a clean Buildroot build was 13–29 min and an incremental one under 2 min on the founder's Mac. Build time is not the barrier. **The barrier is owning the userspace patch backlog** (32–53 fixable CVEs in a current LTS point release), plus no NVIDIA userland (unchanged).
- **The CRA/SBOM argument for Buildroot is weakened, with one strength confirmed.** The build-system SBOM is complete and the image is 4–6x smaller. But the CVE count barely moves, because the kernel dominates. Debian's triaged `wont-fix`/`not-fixed` states are exactly the kind of documented vulnerability handling the CRA asks for, and the distro does that work.
- **The kernel is the security lever in either design.** It carries three-quarters of all IDs, and one LTS point release moved the count by 12. The plan's kernel-update cadence (DC-21, W18) matters more than the base choice.

### 7.8 Other findings (product-relevant)

1. **mkosi's Debian image blocks at first boot** on `systemd-firstboot` (it waits for locale, timezone and root input on `tty1`) unless the config sets them [C-LAB-minimal-image-dc20-016] (`logs/f1-run1-firstboot-journal.txt`).
2. **A Debian kernel needs the `apparmor` package for k3s's check** (A2 adds 2.8 MB and 0 CVEs) [C-LAB-minimal-image-dc20-017].
3. **Buildroot incremental builds leave stale files.** The kernel bump left `/lib/modules/6.12.112` (7.7 MB) in the image, so release images need clean builds [C-LAB-minimal-image-dc20-015].
4. **Buildroot defaults to a passwordless root console** (`BR2_TARGET_GENERIC_ROOT_PASSWD=""`), and its kernel banner embeds the build user and host unless `KBUILD_BUILD_USER`/`HOST` or reproducible-build options are set. Debian/mkosi locks root (`*`) [C-LAB-minimal-image-dc20-018].
5. **Board defconfigs are demos, not products.** Buildroot 2025.02.19's x86_64 EFI defconfig pins kernel 6.1.24 (2023). Its newest 6.12 hash is 6.12.112, five point releases behind kernel.org on the build date [C-LAB-minimal-image-dc20-002, -003, -004].
6. **2026.02 is not a Buildroot LTS.** The LTS line is 2025.02.x to March 2028 [C-LAB-minimal-image-dc20-001].
7. **Boot and RAM (single sample, TCG emulation):** Buildroot reached the test unit at uptime 8.6 s vs Debian 43 s (the 130 MB generic initrd). After k3s reached `Ready`, used RAM was 381 MB vs 653 MB in a 4 GiB guest [C-LAB-minimal-image-dc20-019].

### 7.9 Deviations from the pre-registration (all disclosed; none changes a frozen criterion)

| # | Planned | Done | Why |
|---|---|---|---|
| D1 | Buildroot 2026.02.3 "the 2026 LTS branch" | **Buildroot 2025.02.19**, the actual LTS | The README's premise was wrong: buildroot.org lists 2025.02.x as LTS; 2026.02 is a short-lived stable [C-…-001]. A product would use LTS. Found before any leg-B build ran. |
| D2 | "The Linux version Buildroot defaults to" with the EFI defconfig | **6.12.112** (newest 6.12 hash in that release) + labelled 6.12.117 variant | The defconfig pins 6.1.24 (2023), a demo pin no product would ship; 6.12.x matches Debian's 6.12.116 [C-…-002, -003] |
| D3 | M1(ii) "used bytes" of the disk image | allocated bytes of the sparse image | Equivalent for a sparse raw image |
| D4 | M4(iii) Debian "change one package + re-run" | mkosi `--incremental` rebuild after one changed file (Debian packages are not rebuilt locally) | Nearest Debian equivalent |
| D5 | F1 harness | Test copies mask `systemd-firstboot` and get the kernel config in `/boot`; results written to disk (run 2 lost output to a serial getty, `logs/f1-run2-ttylost.summary.log`) | Harness fixes; the first-boot block is reported as a finding |
| D6 | — | Added variant A2 (+apparmor) and a scan of the unpacked k3s payload | Post hoc, labelled; to show the T2 fix and measure H4 properly |
| D7 | Commit the CycloneDX | Committed CSV extracts (`sbom/legB-buildroot-cdx-*.csv`) | The CycloneDX embeds upstream patch headers with personal email addresses |

### 7.10 Limits

- x86_64 only. No Pi 5, Jetson or aarch64 leg. No NVIDIA/CUDA leg (the steelman's third clause).
- **Shared host.** Three other lab VMs (other spikes in this run, 8–12 vCPU each) were running on the same Mac during these builds, so absolute build times may be inflated. The two legs never built at the same time as each other, so their ratio is less affected, but it is not controlled.
- One run per leg. Build times are from an arm64 VM building amd64 (leg A pays a qemu-user tax; leg B cross-compiles natively), so a native x86_64 CI runner will give different absolute times.
- CVE matching differs by design between legs (7.4 item 4). Counts are a snapshot of one DB build and will drift daily.
- Content parity is close but not exact. Debian pulls in its dependency closure (krb5, sqlite3, perl, dracut, coreutils, and more), while Buildroot uses BusyBox for the base utilities. That difference *is* the trade-off DC-20 asks about.
- k3s was run with Traefik, metrics-server, local-storage and network policy disabled, and no workloads.

### 7.11 Recommendations (with requirement IDs)

| ID | Recommendation | Serves |
|---|---|---|
| DC20-R1 | Keep the **distro base** (ADR-001 D1). Record that DC-20 is now *measured*: Buildroot wins on size (4–6x) and SBOM completeness, not on CVE count (−7 to −18%), and it moves the userspace patch backlog onto OneMind. | F-7, M-6, R-3, RS-4 |
| DC20-R2 | Treat the **kernel update cadence as the main CVE lever** (73–80% of IDs either way). Track kernel CVEs separately in the release dashboard; target the latest LTS point release within a fixed window (feeds DC-21/W18). | F-7, R-3, M-6 |
| DC20-R3 | **Ship the image's SBOM and VEX from the build**: dpkg-based SBOM plus Debian tracker states as VEX-style evidence for the CRA. **Scan k3s after its first start** (or its unpacked payload in CI), because a pre-boot scan misses 515 components. | R-3, M-6, RS-4 |
| DC20-R4 | mkosi image config must set `Locale=`, `Timezone=` and a root/first-boot policy (no interactive `systemd-firstboot`), include `apparmor`, and build a host-only or minimal initrd (the generic one is 130 MB). | R-1, P-7, F-14 |
| DC20-R5 | If a from-source image is ever used (e.g. a tiny sensor/gateway profile), set from day one: own kernel pin tracking LTS, **clean release builds**, reproducible-build settings, a root-password policy, and CVE triage using Buildroot's SBOM `vulnerabilities` list. | M-6, R-3, F-11 |
| DC20-R6 | Re-run this spike (same scripts) on a native x86_64 CI runner and add an aarch64 (Pi 5) leg before any profile decision that depends on image size. | M-6, F-14 |

### 7.12 What competitors do (constraint-fit)

| Product | Image method (prior-verified) | Constraint fit with OneMind | What this lab adds |
|---|---|---|---|
| Home Assistant OS | Buildroot fork (2024.02.x-haos) + RAUC, own kernel configs, pinned Pi kernel [C-W2-047] | Medium: appliance UX matches; no Kubernetes or NVIDIA; funded team owns the patch backlog | A minimal Buildroot core builds in 13–29 min and is 4–6x smaller, but its CVE count is close to Debian's; HAOS's advantage is a team, not lower exposure |
| umbrelOS 2.0 | Debian trixie defined in a Dockerfile, snapshot-pinned, Rugix A/B [C-W2-043, C-W2-044] | High for Lite/Edge appliances | Confirms a Debian core is buildable in about 3 min from a Mac VM; Debian's tracker gives triage for free |
| balenaOS | Yocto A/B across Pi 5, Orin, amd64 [C-W2-040] | Medium | Not measured here; Yocto would share Buildroot's backlog trade-off |
| Olares | Installer on Ubuntu/Debian, no own image (context/03 §1.3) | Medium | The base choice barely moves CVE exposure, because the kernel dominates |

### 7.13 Founder-runnable re-run

On any Linux x86_64 or arm64 machine or VM (Debian 13), with no host credentials. Expect about 45 min end to end on 12 cores:

```bash
# in a disposable Debian 13 VM, as a normal user with sudo
sudo apt-get install -y build-essential file wget cpio unzip rsync bc python3 git libncurses-dev \
  mkosi qemu-user-binfmt qemu-system-x86 ovmf systemd-repart systemd-ukify bubblewrap mmdebstrap \
  dosfstools mtools e2fsprogs zstd cloud-guest-utils gdisk jq curl
sudo mkdir -p /var/lab/dc20/{in,out,logs} && sudo chown -R "$USER" /var/lab/dc20
git clone --depth 1 --branch 2025.02.19 https://gitlab.com/buildroot.org/buildroot.git /var/lab/dc20/in/buildroot-2025.02.19
# k3s v1.37.2+k3s1 amd64, syft 1.57.1, grype 0.121.3: download from GitHub releases and check against SHA256SUMS
cp -r <repo>/research-output/evidence/lab/minimal-image-dc20/scripts/{legA,legB,f1} /var/lab/dc20/   # f1 -> /var/lab/dc20/f1-payload
cp <repo>/research-output/evidence/lab/minimal-image-dc20/scripts/*.sh <repo>/research-output/evidence/lab/minimal-image-dc20/scripts/*.py /var/lab/dc20/
sudo bash /var/lab/dc20/build-a.sh          # leg A, timed
bash /var/lab/dc20/build-b.sh               # leg B, timed (~30 min)
bash /var/lab/dc20/build-b-kernelbump.sh 6.12.117
sudo /opt/grype/grype db update             # then record `grype db status`
sudo bash /var/lab/dc20/measure.sh legA-debian /var/lab/dc20/out/legA/disk.img
sudo bash /var/lab/dc20/measure.sh legB-buildroot /var/lab/dc20/out/legB/disk.img /var/lab/dc20/out/legB/buildroot.cdx.json
sudo python3 -I /var/lab/dc20/split.py /var/lab/dc20/out/measure/*
sudo bash /var/lab/dc20/f1run.sh            # boots both under QEMU, k3s Ready check
```

**Pass:** same as section 3. **Re-read the decision if** Buildroot's target-SBOM IDs fall ≥ 50% below Debian's (both without k3s), or Debian's userspace shows any `fixed` (fix available, not applied) entries.
