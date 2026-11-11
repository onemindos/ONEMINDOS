# 04 · Image, Install, Updates and Rollback (W3)

**Workstream:** W3 (Tier A, P0) · **Date:** 2026-11-10 · **Status:** draft for adversarial review (refuter rows pending, lab spikes pending)
**Decision under test:** ADR-001 **D1** (ship our own image) and **D3** (A/B updates with Rugix, RAUC as alternative, "commit only after k3s is healthy")
**Decision-critical questions owned here:** DC-05 (rebase without reflash), DC-06 (Rugix bus factor), DC-07 (one framework across x86, Pi 5 and Jetson), DC-12 (A/B layer and k3s). Inputs given to DC-01, DC-18, DC-19.
**Evidence:** `evidence/claims/W3.csv` (C-W3-001 … 073) · `evidence/sources/W3.md` · scoring uses the frozen `evidence/scorecard-weights.md` v1.0
**Serves requirements:** R-1, R-2, R-3, M-2, M-6, M-7, N-2, N-6, P-7, P-8, H-1, H-3, U-4, AI-4, F-11, F-12, F-14

> ### Explain it like I'm the founder
> Your box keeps **two copies of its operating system**, A and B. It runs one and writes updates into the other. On the next boot it *tries* the new copy once. If the new copy proves it is healthy, the box **commits** to it. If it doesn't, the box quietly goes back to the old copy. That is how Home Assistant OS and Umbrel never brick a box, and it's what ADR-001 proposed.
>
> This report checks the details that decide whether that works for ten years on a Pi, a mini PC and a Jetson robot. What we found:
> 1. **Swap the update engine from Rugix to RAUC.** Rugix is good, but one person writes almost all of it (303 of 304 commits in the last year), and it reached version 1.0 only in February 2026. RAUC has run Home Assistant OS for years, has 16 active authors, and already has the security features we would otherwise build ourselves (revocation, key rotation, checks that survive a wrong clock). On our frozen scorecard RAUC scores 61, Mender 57 and Rugix 52, and RAUC stays first under every weight change. We keep the disk layout Rugix-compatible, so we can switch engines later with an update, not a reflash.
> 2. **"Healthy" has to mean healthy.** Both competitors commit too early. Umbrel commits the moment its daemon starts. Home Assistant commits even when it has just logged "unhealthy". We commit only after k3s and the core platform pods pass checks, with a timeout and a hardware watchdog. That is our real improvement.
> 3. **k3s must live *inside* the OS image.** k3s cannot be downgraded without restoring its database. So the box keeps a copy of the k3s database for each trial and restores it automatically if the OS rolls back.
> 4. **Jetson needs NVIDIA's own A/B mechanism.** No open-source engine has a maintained integration for stock NVIDIA Jetson Linux. We wrap NVIDIA's mechanism behind the same OneMind release format, signing and health gate, so the user sees one update system.
> 5. **Moving to Debian 14 and 15 later does not need a reflash** if we size the partitions generously now. Umbrel already moved from Debian 12 to 13 over the air.
> 6. **Sign releases from day one.** Umbrel's *stable* release still runs an unsigned script from its server; signing exists only in its beta. We copy the beta's design and add an expiry rule for offline boxes.
> 7. **Install paths:** a flashable image for Pi, a USB installer for PCs, VM images, and preinstalled boxes. A script on an existing Linux is for developers only, because it can't roll back. Home Assistant dropped that mode in 2025 for exactly this reason.

---

## Contents

1. Verdicts at a glance (and what changes in ADR-001)
2. Glossary
3. What competitors actually do (constraint-matched)
4. Framework comparison (Q5)
5. Decision-critical questions: DC-05, DC-06, DC-07, DC-12
6. Scorecard S2 (update framework) and sensitivity
7. The health-gated commit, designed (with k3s)
8. Signing chain, key rotation, revocation and offline devices
9. Delta updates, channels, user-controlled timing, pre-update backup
10. Recovery, factory reset and power loss
11. Disk layout per board
12. Install paths (P-7): matrix per path and per tier
13. Real-world failure reports and what they teach
14. Steelman for the runner-up (Rugix) and the refuter table
15. Lab spikes and founder-runnable tests
16. Recommendations with requirement IDs
17. Corrections to earlier files, open items, blocked items

---

## 1. Verdicts at a glance

| # | Question | Verdict | ADR-001 effect | Confidence |
|---|---|---|---|---|
| V1 | Which A/B update client? (S2, DC-06) | **RAUC** is the lead update client. Rugix becomes the documented alternative. The disk layout and boot state stay compatible with both, so the switch is reversible by update. | **D3 changed** (lead tool swapped) | Medium-high: robust in 14/14 weight runs; C3 and C4 cells are documentation-only until the lab runs (§6) |
| V2 | One update framework for x86, Pi 5 and Jetson? (DC-07) | **No off-the-shelf engine covers all three with stock NVIDIA Jetson Linux** [C-W3-013, C-W3-021, C-W3-052, C-W3-053]. Use **one OneMind release contract** (one manifest, one signing chain, one health gate, one UI) over **per-board backends**: RAUC on x86 and Pi 5, NVIDIA's rootfs A/B plus image-based OTA on Jetson [C-W3-049, C-W3-050]. | **D3 refined** (Jetson method decided) | Medium: the Jetson wrapper is unbuilt; needs a founder-hardware spike |
| V3 | Can the OS roll back safely with k3s inside? (DC-12) | **Yes, with a design.** k3s ships inside the image; its datastore lives on the data partition; each trial boot runs k3s against a **copy** of the datastore taken at install time; a k3s-minor guard restores the matching snapshot if the OS falls back [C-W3-063, C-W3-064]. The k3s system-upgrade-controller is **not** used on image-based nodes, because it writes into the host root [C-W3-065]. | **D3/D4 refined** ("k3s updates separately via SUC" dropped for image nodes) | Medium: design from primary docs; lab pending |
| V4 | Rebase Debian 13 → 14 → 15 without a reflash? (DC-05) | **Yes**, if slot sizes, the ESP and the first-stage bootloader are planned for 2036 now. Evidence: Umbrel moved from Debian 12 to 13 by OTA bundle [C-W3-039]; HAOS has kept fixed 256 MB slots for years [C-W3-023]. A partition-table change *does* need special handling, and Umbrel's cost of one is a permanent extra image variant [C-W3-040]. | **D3 kept**, with layout rules (§11) | Medium-high (documents + competitor code); Debian 14 lab spike pending |
| V5 | Install paths (P-7) | Flash image (Pi), USB installer ISO (x86, also the rescue disk), VM images (qcow2/vhdx/vmdk/ova), preinstalled boxes, NVIDIA flash for Jetson. A script on an existing distro is **developer mode only** [C-W3-028, C-W3-045]. | **D1 confirmed** | High |
| V6 | Signing | Offline root, M-of-N online signers, signed release manifest pinning bundle hashes, revocation, root handover (Umbrel 2.1-beta design [C-W3-035]) **plus** a manifest expiry with a long offline grace (TUF lesson [C-W3-067]) **plus** RAUC's signing-time validation for wrong clocks [C-W3-018]. Signed from release 1. | **D3 kept and tightened** | High (design); key ceremony is a founder decision |
| V7 | Who commits, when? | Commit only after the platform gate passes (k3s Ready, core pods Ready, data partition mounted read-write, OneMind API answers locally). App failures never block the OS commit. | **D3 kept** (made concrete) | High |

**Corrections to earlier repo facts** (details in §17): umbrelOS **stable** 2.0.1 does not verify release signatures; that code is beta-only [C-W3-034, C-W3-035]. umbreld commits the slot at daemon start, before apps [C-W3-036] (open item closed). HAOS commits even when unhealthy [C-W3-025]. The RAUC Tegra community layer was removed in 2024 [C-W3-021]. `kairos-agent` is archived only because it moved into the Kairos monorepo [C-W3-062].

---

## 2. Glossary

- **A/B update:** two copies (slots) of the OS. Updates go into the one not running.
- **Slot / boot group:** one complete OS copy (kernel, root filesystem). Rugix calls a set of slots a "boot group".
- **Trial boot (tryboot):** booting the new slot once, without making it the default. Raspberry Pi firmware has this built in [C-W3-066].
- **Commit / mark good:** making the trial slot the default. If it never happens, the next reboot returns to the old slot.
- **Dead man's switch / boot counter:** the bootloader counts failed boot attempts and falls back after N tries. RAUC's GRUB setup uses this [C-W3-020]; Rugix's default flows don't [C-W3-005].
- **Health gate:** the checks that must pass before commit.
- **Bundle:** the signed update file (RAUC `.raucb`, Rugix `.rugixb`, Mender `.mender`, SWUpdate `.swu`).
- **Delta / adaptive update:** download only the blocks that changed.
- **ESP:** EFI System Partition, the small FAT partition UEFI firmware boots from.
- **UKI:** Unified Kernel Image, kernel + initrd + command line in one signed EFI file (relevant to Secure Boot later).
- **Rebase:** moving a device to a new major OS version (Debian 13 → 14) in place.
- **Reflash:** erasing the disk and writing a new image, which loses the "update in place" property.
- **OTA:** over-the-air update.
- **Capsule update:** UEFI's standard way to update firmware/bootloader; NVIDIA Jetson uses it for the QSPI bootloader.
- **L4T / Jetson Linux:** NVIDIA's board support package for Jetson (kernel, bootloader, Ubuntu root filesystem).
- **Datastore (k3s):** where Kubernetes keeps cluster state: SQLite on a single node, embedded etcd on HA clusters.
- **system-upgrade-controller (SUC):** a Kubernetes controller that upgrades k3s on nodes by running a privileged job.
- **TUF:** The Update Framework, a specification for secure software update metadata (roles, expiry, freeze and rollback attack defences) [C-W3-067].
- **Freeze attack:** an attacker keeps showing a device old metadata so it never learns of a security update.
- **CRL:** certificate revocation list.
- **Cross-signing:** an old root key signs a new certificate so devices that trust only the old root accept the new chain (HAOS did this in 2026 [C-W3-024]).

---

## 3. What competitors actually do (from code at pinned SHAs)

| Product | Update engine | When it commits ("healthy" means) | Signing | Rollback for "booted but broken" | Install paths | Constraint fit with OneMind |
|---|---|---|---|---|---|---|
| **Home Assistant OS 18.5** | RAUC, verity bundles, GRUB (x86), U-Boot (SBCs), custom tryboot backend (Pi 5) [C-W3-029] | When the Supervisor starts, **even if it has just logged "unhealthy"**, before Core and apps [C-W3-025] | RAUC x.509 keyring; dev/release CAs; root rotated 2026-06 with cross-signing until 2028-05-14 [C-W3-024] | Manual: `ha os boot-slot A` (users do this, e.g. #5098 [C-W3-033]) | Board images; x86 flashed from live Ubuntu or another PC, **no installer**, UEFI with Secure Boot off [C-W3-027]; VM images vmdk/vhdx/vdi/qcow2/ova [C-W3-026]. Core/Supervised script installs deprecated 2025 [C-W3-028] | **High** for appliance UX, board spread and RAUC; **low** for k8s and robotics. Funded team. Buildroot (tiny rootfs) |
| **umbrelOS 2.0.1 / 2.1.0-beta.1** | Rugix (amd64 GRUB, Pi tryboot); legacy Mender devices on a Mender-compatible Rugix variant [C-W3-040] | At umbreld start, before migrations and apps [C-W3-036] | **Stable 2.0.1: none at release level** (server-supplied bash script [C-W3-034]). **2.1-beta:** offline root, approved signers, revocation, root handover, lists never expire [C-W3-035]; anti-downgrade [C-W3-037] | Not found in code (umbreld only commits) | USB-resident image, installer ISO, Pi image, VM via ISO [C-W3-042]; NixOS live installer [C-W3-043] | **High**: Debian appliance, Pi 5 + x86, small team. **Low** for k8s, Jetson, IIoT |
| **Olares 1.12.x** | None at OS level (in-place upgrade on Ubuntu/Debian) | n/a (no OS A/B) | n/a at OS level | None | ISO installs **Ubuntu** then Olares; script on Ubuntu/Debian; Docker; Pi, Mac, Windows, LXC "not for production" [C-W3-045] | **High** for k3s; **low** for update safety (no OS rollback) |
| **ZimaOS 1.8.0** | RAUC (`.raucb` release asset) [C-W3-047] | Not read | RAUC (details not read) | Not read | USB installer IMG/ISO, erases disk [C-W3-047] | Medium: x86 appliance on Buildroot + RAUC; no k8s; no license file (study only) |
| **CasaOS** | None (piped install/update scripts) [C-W3-046] | n/a | n/a | None | `curl | sudo bash` on Debian/Ubuntu/RPi OS/Armbian [C-W3-046] | Low: script-on-distro, the model HA abandoned |
| **StartOS 0.4.x** | Whole rootfs image files on a data partition, `current.rootfs` symlink [C-W3-048] | Not verified | Signed release assets (`signatures.tar.gz`); details not read | Older images kept until pruned; automatic rollback **not verified** | ISO/IMG for x86_64, Pi, Rockchip, riscv64 [C-W3-048] | Medium: Debian appliance, small team, MIT; no k8s |
| **NVIDIA Jetson Linux r39.2** | Rootfs A/B linked to bootloader A/B; image-based OTA across majors [C-W3-049, C-W3-050] | After a customer validation hook, then `nvbootctrl verify`; 3 tries default [C-W3-049] | NVIDIA tooling; Secure Boot state preserved by OTA | Recovery kernel if both slots fail [C-W3-049] | NVIDIA flash tools from an x86 host (W18) | **High** for the Robotics tier (it's the vendor path) |
| **Fedora IoT / bootc** | OSTree deployments (no extra partitions); greenboot-rs health checks [C-W3-061] | When greenboot `required.d` checks pass (GRUB counter) | Container signatures (W2/W6) | Automatic via greenboot; manual `bootc rollback` | `bootc install to-existing-root` converts an existing Linux in place [C-W3-059]; offline OCI dir on USB [C-W3-060] | High for IIoT/industrial and BYO conversion; **GRUB-only** today, so no Pi tryboot path [C-W3-058] |

**What the table teaches:**
1. Both constraint-matched appliances (HAOS, Umbrel) ship **their own image with A/B**, and both **commit too early**. Our health gate is a real improvement, not a copy.
2. The two products that install on a normal distro (Olares, CasaOS) have **no OS rollback**. HA, which had both modes, dropped the script modes in 2025, citing support burden [C-W3-028].
3. Only bootc can convert an existing Linux in place and keep rollback [C-W3-059]. That is the strongest BYO argument for the Fedora/bootc track (input to DC-01), but bootc fails the Pi 5 gate today (§6).

---

## 4. Framework comparison (answers Q5)

One row per capability. "Doc" means documented at the pinned SHA; "code" means read in source.

| Capability | **RAUC 1.15.2** | **Rugix 1.4** | **Mender OSS 5.2** | **SWUpdate 2026.05** | **OSTree/bootc + greenboot-rs** | **Kairos 4.4** | **NVIDIA L4T A/B (Jetson only)** |
|---|---|---|---|---|---|---|---|
| License | LGPL-2.1 [C-W3-017] | MIT or Apache-2.0 | Apache-2.0 client and server [C-W3-055] | GPL-2.0-only [C-W3-056] | LGPL (OSTree), Apache/MIT (bootc), BSD-3 (greenboot-rs) [C-W3-061] | Apache-2.0 | NVIDIA license (EULA) |
| Signature model | x.509 CMS, CRL, signing-time validation, signer CN allow-list, HSM [C-W3-018] | CMS, single signer only, or bundle hash; HSM via external signing [C-W3-008] | Optional artifact signing (vendor comparison, SECONDARY [C-W3-016]) | CMS/RSA (CIP default uses snake-oil keys until replaced [C-W3-057]) | Container image signatures (W6) | OCI images; Trusted Boot keys | NVIDIA tooling |
| Revocation / anti-downgrade | CRL (expiry caveat) [C-W3-018] | **Not documented** [C-W3-009] | Server-side | Not checked | Registry-level | Not checked | Not checked |
| Delta updates | Adaptive `block-hash-index` + HTTP streaming, open source [C-W3-019] | Dynamic block + static xdelta, open source [C-W3-016] | **Commercial only** [C-W3-055] | zchunk/rdiff (external integration) [C-W3-057] | Native static and dynamic deltas | Image pull | Image-based OTA payload |
| Health gate hook | `rauc status mark-good` from any systemd unit; boot counters [C-W3-020] | `system-commit/pre-commit` hook; no boot counter by default [C-W3-005, C-W3-007] | State scripts; commit after reboot | `ustate` TESTING + confirm (CIP) [C-W3-057] | greenboot `required.d` [C-W3-061] | cloud-init stage (VUPD) | `l4t-rootfs-validation-config.service` [C-W3-049] |
| Bootloaders | GRUB, U-Boot, Barebox, EFI, custom (HAOS Pi 5 tryboot) [C-W3-029] | GRUB, U-Boot, systemd-boot, Pi tryboot, RAUC/Mender-compat, custom [C-W3-011] | GRUB, U-Boot | EFI Boot Guard, U-Boot, GRUB [C-W3-056] | GRUB+shim; systemd-boot only with composefs [C-W3-058] | GRUB; systemd-boot (Trusted Boot) | NVIDIA UEFI + QSPI |
| x86 UEFI | Yes (HAOS) | Yes (Umbrel) | Yes (mender-convert) [C-W3-054] | Yes (CIP) | Yes | Yes | n/a |
| Raspberry Pi 5 | Yes (HAOS, custom tryboot backend) [C-W3-029] | Yes (Umbrel) [C-W3-071] | Yes (mender-convert U-Boot, trixie) [C-W3-054] | Not shown | Not shown (W2) | No (VUPD) | n/a |
| Jetson Orin/Thor on stock L4T | No maintained layer (removed 2024) [C-W3-021] | No integration [C-W3-013] | Only via Yocto meta-tegra rebuild [C-W3-053] | Only via Yocto meta-tegra rebuild [C-W3-052] | No | Orin NX/AGX/Thor via kairos-init (VUPD) | **Yes (native)** [C-W3-049] |
| Offline USB update | Yes (local bundle) | Yes (file/stdin/HTTP) | Yes (standalone mode) | Yes | Yes (OCI dir) [C-W3-060] | Yes (`ocifile:`) | Yes (OTA payload) |
| On-device API | D-Bus | CLI only [C-W3-016] | Daemon API | IPC/REST | CLI/D-Bus (rpm-ostree) | CLI/operator | CLI scripts |
| Rebase without new partitions | Rewrites whole slots | Rewrites whole slots | Rewrites whole slots | Rewrites whole slots | **By design** (deployments in one filesystem) | Image files | Image-based OTA can change layout (from 35.5) [C-W3-050] |
| Active human authors, last 12 months | 16 [C-W3-017] | **2** (one writes 303/304) [C-W3-001] | 18 [C-W3-069] | 44 [C-W3-056] | 30 / 59 [C-W3-068] | 35 (monorepo) | NVIDIA |

---

## 5. Decision-critical questions

Each block gives the question, the evidence, the verdict, and what would flip it. Refuters see only the P0 claims and sources (returned to the orchestrator); their verdicts go in §14.

### 5.1 DC-05 · Rebasing a fielded device to a new major OS without a reflash (Q2)

**What "rebase" touches.** An A/B engine rewrites a whole slot, so a new Debian major version is just new slot content. The risks are what the slot does **not** contain: the partition table, slot sizes, the first-stage bootloader on the ESP or config partition, firmware, and the data partition's format.

**Evidence:**
- **Umbrel did it.** umbrelOS 1.4.0 was built on Debian bookworm; 1.5.0 (2025-11-05) on trixie, shipped as `.update` OTA artifacts for amd64 and Pi [C-W3-039]. Same slots, no reflash.
- **Umbrel also shows the cost of a layout change.** Devices first provisioned with Mender keep Mender's partition numbering forever and need a separate `umbrelos-mender-amd64` image plus a state-migration hook [C-W3-040]. One early layout decision became a permanent second build target.
- **HAOS avoids layout changes by over-provisioning a tiny OS.** Slots are fixed at 256 MB for a Buildroot rootfs [C-W3-023]. HAOS changed its root filesystem format in the field (squashfs to EROFS) by patching `cmdline.txt` from the update hook, with a note that the patch "can be removed in HAOS 19.0" [C-W3-022]. Format changes are survivable; partition changes are avoided.
- **Rugix creates the layout only at first boot** (bootstrapping) [C-W3-014]. Nothing documents repartitioning a fielded device. RAUC is the same: it writes slots, and the slot map is configuration.
- **Jetson is different.** NVIDIA's image-based OTA moves Orin from 35.5/36.x to 39.2 and handles layout changes (from 35.5) [C-W3-050]; apt can't cross majors [C-W3-050]. So the Jetson flavor rebases through NVIDIA's tool.
- **bootc rebases by design** (`bootc switch`, deployments share one filesystem) [C-W3-060], which is why DC-05 is part of the Fedora/bootc case.

**How many rebases to 2036?** If the box launches on Debian 13 in 2027 and must be supported to 2036, it needs either two rebases (to Debian 14 and 15) or one rebase plus paid extended support. W2 owns the release and support dates (`03-base-os.md`); this answer doesn't depend on the exact years. Each rebase is a normal A/B update if the layout rules in §11 hold.

**Verdict: flip condition NOT met.** Neither Rugix nor RAUC needs a reflash for a Debian major rebase, provided we (a) size slots for 2036 now, (b) keep the kernel and initrd inside the A/B pair, and (c) treat the ESP/first-stage bootloader as a rarely updated, separately guarded component. A partition-table change would need a reflash or a risky in-place migration with either tool, so the layout in §11 is a **day-one decision**.
**What would flip it:** a Debian 14 image that cannot fit the slot size chosen in §11, or a required bootloader change that cannot be shipped safely in-band. Lab: build a Debian 14 (testing) bundle and install it over a Debian 13 slot (pending, §15 T-W3-04).

### 5.2 DC-06 · Rugix's bus factor, maturity and exit plan (Q4)

| Metric (2025-11-10 → 2026-11-10 unless noted) | Rugix | RAUC | Mender client | SWUpdate | OSTree / bootc |
|---|---|---|---|---|---|
| Commits | 304 | 512 | 276 | 317 | 231 / 923 |
| Human authors | **2** | 16 | 18 | 44 | 30 / 59 |
| Share of top author | **99.7%** (303/304) [C-W3-001] | 56% (287/512) [C-W3-017] | 44% | 50% | 43% / 25% |
| All-time #2 contributor | 4 contributions [C-W3-002] | 155 commits in the year | 42 | 35 | 37 / 215 |
| 1.0 release | **2026-02-25** [C-W3-003] | years earlier (v1.15.2 now) | 5.x | yearly releases | v2026.6 / v1.17.4 |
| Security policy | Latest minor only [C-W3-004] | (not read) | (not read) | (not read) | (not read) |
| Backer | Silitics GmbH, founder-owned per its own description (SECONDARY) [C-W3-015] | Pengutronix (not verified here) | Northern.tech | Stefano Babic + CIP users | Red Hat; bootc is CNCF Sandbox |
| Named adopters | Umbrel (code); Enmo, eChecker, Aqa (vendor claim only) [C-W3-015] | HAOS (code), ZimaOS (release asset) [C-W3-047] | Umbrel, formerly [C-W3-040] | CIP Core [C-W3-057] | Fedora IoT/CoreOS, RHEL image mode |
| Issue response | Fast: most issues closed within 1–7 days (API sample) | not measured | not measured | not measured | not measured |

**Reading it plainly:** Rugix is well run and responsive, and its docs are the best of the group. But it is effectively **one engineer at one small company**, it has been at 1.0 for nine months, and its only code-confirmed adopter is Umbrel. The update engine is the hardest part to replace after boxes ship.

**Exit plan (needed whichever engine we pick):** Rugix ships **RAUC-compatible boot flows** (`rauc-grub`, `rauc-uboot`) designed for in-field migration from RAUC [C-W3-011]. RAUC reads its slot map from configuration. So if OneMind uses **RAUC's GRUB variables and a partition-label slot map from day one**, either engine can drive the same disk, and switching is an update (Umbrel did exactly this from Mender to Rugix [C-W3-040]).

**Verdict: flip condition MET on primary evidence → D3 lead moves to RAUC.** The DC-06 flip rule was "single-maintainer bus factor with no second adopter, while RAUC is comparable on features". The single maintainer is primary-verified [C-W3-001]. Second adopters exist only as a vendor claim [C-W3-015], which the frozen rules cap and cannot count as proof. RAUC is comparable or better on every feature we need except Rugix's built-in state management and image builder (§4). The scorecard agrees (§6).
**What would flip it back:** a second named maintainer with commit rights and sustained commits at Rugix, or a primary-verified second appliance/industrial adopter **and** native revocation + multi-signer support in Rugix, **or** RAUC failing the Pi 5/x86 lab spikes that Rugix passes.

### 5.3 DC-07 · One update framework across x86, Pi 5 and Jetson (Q6, Q47)

**Evidence:**
- **Rugix:** x86 and Pi 5 proven by Umbrel; **no Jetson/Tegra code** in rugix, rugix-bsps (NXP i.MX and Rockchip only), meta-rugix or the docs [C-W3-013]. A `custom` boot flow could drive `nvbootctrl`, but nobody has built it.
- **RAUC:** x86 and Pi 5 proven by HAOS [C-W3-029]; the community Tegra layer was **removed** in August 2024 [C-W3-021].
- **Mender:** x86 and Pi 5 (Debian trixie via mender-convert) [C-W3-054]; Jetson Thor/AGX Orin/Orin Nano/Orin NX on L4T 39.2, but **only in a Yocto build** with meta-tegra; its "native" scheme drives `nvbootctrl` and the UEFI capsule directly [C-W3-053]. Delta updates are commercial [C-W3-055].
- **SWUpdate:** Jetson via the OE4T demo (Orin Nano NVMe, L4T 39.2) in a Yocto build [C-W3-052]; Pi 5 not shown.
- **NVIDIA:** stock Jetson Linux has its own rootfs A/B on Orin with a **customer validation hook**, fixed APP/APP_b partitions, 3 tries and a recovery kernel [C-W3-049], plus image-based OTA across BSP majors [C-W3-050] that resumes after power loss [C-W3-051].

**Verdict: no single open-source engine covers all three on stock L4T today.** Mender comes closest, but only if the Jetson flavor becomes a Yocto build, which is a large change to DC-09 and costs us NVIDIA's stock Ubuntu userspace.
**Recommended architecture: "one contract, per-board backends".**
- **One release contract:** one signed manifest per release listing a bundle per board family, one key hierarchy, one health gate, one UI flow, one `onemind update` CLI and API.
- **Backends:** RAUC with the GRUB backend (x86) and the tryboot custom backend (Pi 5, HAOS's Apache-2.0 script as the reference [C-W3-029]); on Jetson, NVIDIA's rootfs A/B and image-based OTA, with OneMind's gate plugged into `l4t-rootfs-validation-config.service` [C-W3-049].
- **Cost:** two backends to maintain, but the Jetson one is NVIDIA's code; we write a wrapper. That is cheaper than moving Jetson to Yocto.
**What would flip it:** (1) if DC-09 moves the Jetson flavor to Yocto/meta-tegra, re-score Mender as the single framework; (2) if NVIDIA's validation hook can't call our gate, or image-based OTA can't run unattended on Orin Nano (founder-hardware test T-W3-06), RAUC with a custom `nvbootctrl` backend becomes the fallback.

### 5.4 DC-12 · How the A/B layer and k3s interact (Q128, Q21)

**The hard facts:**
- k3s cannot go back a minor version without restoring a datastore snapshot taken **on that older minor** [C-W3-063].
- On a single node the datastore is SQLite, backed up by copying `/var/lib/rancher/k3s/server/db/` plus the token; `k3s etcd-snapshot` is documented for etcd only [C-W3-064].
- The system-upgrade-controller upgrades k3s with a privileged job that mounts the host root at `/host`, and refuses downgrades [C-W3-065]. On a read-only image root that model doesn't fit.
- Competitors don't solve it: Olares has no OS rollback; Umbrel and HAOS run Docker and commit before apps run [C-W3-025, C-W3-036].

**The danger, in one sentence:** if release N+1 bumps k3s from 1.35 to 1.36, the trial boot migrates the database, then fails the gate and falls back to release N, whose k3s 1.35 now faces a 1.36 database.

**Verdict: a safe design exists → flip condition NOT met.** The design is in §7. In short: k3s lives inside the image (so OS and k3s roll back together), the datastore lives on the data partition, the trial boot runs against a **copy**, and a minor-version guard restores the right snapshot before k3s starts. Multi-server etcd clusters never auto-roll back across a k3s minor (§7.4).
**What would flip it:** the lab showing that k3s 1.N cannot start on a datastore copy taken while 1.N was running (for example, kine/SQLite needs a quiesced copy we can't take quickly), or that the copy step makes updates too slow on a Pi 5 SD card. Lab: §15 T-W3-02, T-W3-03.

---

## 6. Scorecard S2: image build, A/B update and rollback framework

Frozen weights v1.0. **S2 interpretation of the anchors** (stated before scoring, per §5 of the weights file): C1 = the project's own release policy, maintainer base and backing; C2 = board coverage of the *update path* (x86, Pi 5, Jetson); C3 = update safety features; C4 = shipping products confirmed from code; C5 = effort for one developer; C6 = license and paid features; C7 = integrations, community, fleet servers. Gates G3–G5 are checked only against what an update framework controls.

| Candidate | G1 | G2 | G3 | G4 | G5 | C1 (20) | C2 (20) | C3 (15) | C4 (15) | C5 (10) | C6 (10) | C7 (10) | Total | Rank |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **RAUC** | PASS (LGPL-2.1, separate program) [C-W3-017] | CONDITIONAL: x86, Pi 5 PASS [C-W3-029]; Jetson via NVIDIA backend [C-W3-049] | PASS: 16 authors, long history [C-W3-017] | PASS: offline bundles, no protocol limits [C-W3-018] | CONDITIONAL: same engine all tiers except Jetson backend [C-W3-049] | 3 [C-W3-017] | 2 [C-W3-021] | 4 doc-only, pending-lab [C-W3-018, C-W3-024] | 3 [C-W3-029, C-W3-047] | 3 [C-W3-020] | 4 [C-W3-017] | 3 [C-W3-019] | **61.0** | **1** |
| **Mender OSS** | PASS (Apache-2.0) [C-W3-055] | CONDITIONAL: Jetson only via Yocto rebuild [C-W3-053] | PASS [C-W3-069] | PASS: standalone install from a USB/file path, no server [C-SCORE-021] | CONDITIONAL [C-W3-053] | 3 [C-W3-069] | 3 [C-W3-053, C-W3-054] | 3 [C-W3-055] | 2 [C-W3-040] | 3 [C-W3-054] | 3 (delta commercial) [C-W3-055] | 3 [C-W3-053] | **57.0** | 2 |
| **Rugix** | PASS (MIT/Apache-2.0) [C-W2-048] | CONDITIONAL: x86, Pi 5 PASS [C-W3-071]; no Jetson [C-W3-013] | CONDITIONAL: single maintainer, latest-minor-only support [C-W3-001, C-W3-004] | PASS: locally verified signed bundles [C-W3-008] | CONDITIONAL [C-W3-013] | 2 [C-W3-001, C-W3-004] | 2 [C-W3-013] | 3 doc-only, pending-lab [C-W3-005, C-W3-009] | 3 [C-W3-036] | 3 [C-W3-014] | 4 [C-W2-048] | 2 [C-W3-016] (SECONDARY; the cap of 3 is respected) | **52.0** | 3 |
| SWUpdate | PASS (GPL-2.0 program) [C-W3-056] | **FAIL**: Pi 5 not shown (unproven counts as FAIL) [C-W3-056] | PASS [C-W3-056] | not assessed (G2 FAIL) | — | 4 [C-W3-056, C-W3-057] | **1** (rev. 3; was 2: anchor 2 needs Pi 5; x86 via CIP EFI Boot Guard and Jetson via the OE4T demo only) [C-W3-057, C-W7-017] | 3 [C-W3-057, C-SCORE-020] | 3 [C-W3-057] | 2 [C-W3-057] | 3 [C-W3-056] | 3 [C-W3-057, C-STEEL-jb-020] | (54.0 unranked, rev. 3; was 58.0) | — |
| OSTree/bootc + greenboot-rs | PASS [C-W3-061] | **CONDITIONAL** (rev. 3; was FAIL): x86 GRUB+shim [C-W3-058]; Pi 5 only through a community tryboot port that needs a manual commit [C-SCORE-026]; Jetson through paid RHDE bootc images [C-W2-041] | PASS [C-W3-068] | PASS: Flight Control fleet agent [C-W8-048] | — | 4 [C-W3-068, C-W2-024] | 1 (between anchors 1 and 2; the Pi 5 path is a 1-star community port) [C-W3-058, C-SCORE-026] | 3 lab [C-W2-054, C-LAB-fedora-bootc-011] | 3 [C-W2-025] | 3 [C-W2-056] | 4 [C-W2-024, C-LIC-040] | 3 [C-W8-048, C-W11-051] | **58.0** (ranked from rev. 3) | 3rd at rev. 2/3 totals |
| Kairos agent | PASS [C-W2-049] | **FAIL**: no Pi 5 model [C-W2-039, C-REF3-DC-cost-005] | PASS [C-W3-062] | not assessed (G2 FAIL) | — | — | — | — | — | — | — | — | (unranked) | — |
| NVIDIA L4T A/B | CONDITIONAL (EULA) [C-LIC-001] | Jetson only: scored as the Jetson backend, not standalone [C-W3-049] | — | — | — | — | — | — | — | — | — | — | n/a | backend |

**CONDITIONAL mitigations (carry into `20-PLAN-180-DAYS.md` and `23-RISK-REGISTER.md`):**
- *G2 Jetson (all ranked candidates):* build the NVIDIA-backend wrapper (§5.3). Owner: founder. Cost: about 2–3 weeks of work after the Orin Nano arrives (estimate). Gate: T-W3-06.
- *G3 Rugix:* only applies if Rugix is chosen; escrow the source (already open), and keep the RAUC-compatible layout so the engine can be swapped.
- *G5:* the Robotics tier uses the same release contract but a different backend; this is the "additional flavor of the same family" case the gate allows.

**pending-lab cells:** C3 for RAUC and Rugix (anchor 5 needs our power-cut and forced-rollback results; spikes `evidence/lab/rauc/` and `evidence/lab/debian-rugix/` are pre-registered, results pending).

**Sensitivity (each weight ±5, others rescaled; 14 runs):**

| Perturbation | Winner | Margin over #2 (Mender) |
|---|---|---|
| Base | RAUC | 4.0 |
| C1 +5 / −5 | RAUC / RAUC | 3.8 / 4.2 |
| C2 +5 / −5 | RAUC / RAUC | **2.5** / 5.5 |
| C3 +5 / −5 | RAUC / RAUC | 4.9 / 3.1 |
| C4 +5 / −5 | RAUC / RAUC | 4.9 / 3.1 |
| C5 +5 / −5 | RAUC / RAUC | 3.8 / 4.2 |
| C6 +5 / −5 | RAUC / RAUC | 4.9 / 3.1 |
| C7 +5 / −5 | RAUC / RAUC | 3.8 / 4.2 |

**Robust:** same winner in 14/14. Under C2 +5 the margin (2.5) falls inside the 3-point tie band; the tie-break rule sends it to the decision-critical evidence, which favours RAUC: Mender's C2 edge depends on a Yocto Jetson flavor that DC-09 has not chosen, and its delta updates are paid [C-W3-055].
**Gates relaxed one at a time:** if SWUpdate's Pi 5 gate were proven, it would score 58.0, still below RAUC. bootc would stay below on C2 even with the gate relaxed.

**Rev. 3 (2026-11-11, `evidence/scorecard-rev3.md` §4):** every cell above now cites a claim. The totals in this table are the **frozen W3 scores**. The current S2 totals apply 01's rev. 1 and rev. 2 corrections plus rev. 3: **Mender 62.0 · RAUC 61.0 · OSTree/bootc 58.0 · Rugix 52.0**. bootc's G2 moved from FAIL to CONDITIONAL because the community `rpi-bootc-bootloader` tryboot port [C-SCORE-026] and RHDE on Orin [C-W2-041] are now ledgered, so bootc is ranked. Its C2 stays 1, and it wins none of the 14 ±5 runs (Mender 12, RAUC 2; all 14 inside the tie band). SWUpdate's C2 fell from 2 to 1 because anchor 2 requires Pi 5. Nothing changes the S2 verdict, which rests on the tie-break in `01-…` §3.2.

---

## 7. The health-gated commit, designed (with k3s)

### 7.1 Where things live

| Thing | Location | Why |
|---|---|---|
| k3s binary, containerd, OneMind core manifests (pinned versions) | **Inside the read-only OS slot** | OS and k3s roll back together; no host-root writes (rules out SUC on image nodes [C-W3-065]) |
| k3s datastore (`/var/lib/rancher/k3s/server/db`), token | Data partition | Survives updates; copied per trial [C-W3-064] |
| Container images, volumes (local-path), logs | Data partition | Large and mutable |
| `/etc` host settings (network, hostname, SSH keys) | Overlay/state on data partition (HAOS overlay pattern [C-W3-023]) | Small, survives updates |

### 7.2 The update sequence

```mermaid
sequenceDiagram
    autonumber
    participant U as User / UI
    participant D as onemindd (update agent)
    participant R as RAUC (or NVIDIA OTA on Jetson)
    participant B as Bootloader (GRUB / Pi tryboot / Jetson UEFI)
    participant G as onemind-gate.service (new slot)
    participant K as k3s (new slot)
    U->>D: "Install update" (never automatic by default)
    D->>D: Verify signed manifest (root→signers→manifest, not revoked, newer, not expired-beyond-grace)
    D->>D: Pre-update backup: k3s datastore snapshot + config (+ restic if configured)
    D->>R: install bundle (hash pinned from manifest)
    R->>R: Verify bundle signature, write INACTIVE slot only, fsync
    R->>B: set trial boot for new slot (one-shot / attempts=3)
    U->>D: "Restart now" (or at the user's chosen time)
    D->>D: Copy datastore → trial copy, record k3s minor
    B->>G: boot new slot (trial)
    G->>G: Start hardware watchdog + gate timeout (e.g. 15 min)
    G->>K: start k3s on the TRIAL COPY
    K-->>G: node Ready, core pods Ready, local API answers
    alt all platform checks pass
        G->>R: mark-good (commit)
        G->>D: promote trial copy to canonical datastore
        D-->>U: "Updated to N+1"
    else check fails, k3s hangs, or kernel panics
        G->>B: mark-bad + reboot (or watchdog/panic reboots)
        B->>B: fall back to old slot
        D->>D: old slot starts k3s on the ORIGINAL datastore (untouched)
        D-->>U: "Update failed, back on N" + logs; release N+1 marked bad locally
    end
```

### 7.3 Gate rules (answers Q21)

1. **Checks (all local, no internet needed):** data partition mounted read-write; k3s API answers; the node is `Ready`; pods in `kube-system` and `onemind-system` are `Ready`; the OneMind API answers on localhost. **User apps are not in the gate.** An app that fails after an update gets a per-app rollback (Helm), not an OS rollback. Lesson from HAOS and Umbrel, which commit before anything runs [C-W3-025, C-W3-036].
2. **Timeouts:** gate timeout of about 15 minutes on Pi 5 (image pulls can be slow on SD; measure in T-W3-02), shorter on x86. Timeout means mark-bad and reboot.
3. **Hangs:** systemd hardware watchdog plus `panic=10` so a hung or panicking kernel reboots on its own. Rugix's default flows and Pi tryboot are one-shot, so any reboot before commit returns to the old slot [C-W3-006, C-W3-066]; RAUC's GRUB setup also counts attempts [C-W3-020].
4. **No rollback loops:** after a fallback, the agent records release N+1 as bad on this device and never retries it automatically. It shows the error and a "try again" button.
5. **Network down at first boot:** the gate never checks internet reachability. (greenboot's default checks *do* test repository DNS [C-W3-061]; we deliberately don't.)
6. **Never "auto-commit at boot".** Rugix's auto-commit recipe commits whatever boots, even the old slot after a fallback [C-W3-006]. We only commit from the gate.
7. **Delayed failures** (daily freezes like HAOS #5098 [C-W3-033]) can't be caught by any gate. Keep the previous slot bootable and give the UI a one-click "go back to the previous version" until the next update overwrites it.

### 7.4 The k3s version rules

| Release type | What changes | Allowed rollback | How |
|---|---|---|---|
| **OS-only** (same k3s minor, any patch) | Debian packages, kernel, k3s patch | Automatic, any time | Trial copy discarded on fallback; old k3s patch reads the original datastore |
| **k3s-minor** (1.N → 1.N+1), single node | k3s minor bumps | Automatic during the trial; after commit only by restoring the pre-update snapshot [C-W3-063] | Never combine with other risky changes; snapshot taken on 1.N before install; never skip a minor [C-W3-065] |
| **k3s-minor**, multi-server (etcd) cluster | k3s minor bumps | **No automatic OS rollback after the first server commits** | Rolling node by node, servers first [C-W3-065]; gate includes cluster health; operator-confirmed "point of no return" |

The node-level guard: before k3s starts, `onemind-k3s-guard.service` compares the slot's k3s minor with the minor recorded next to the datastore. If the datastore is newer (a rollback after commit), it refuses to start k3s and offers the snapshot restore. It never starts an older k3s on a newer database.

---

## 8. Signing chain, key rotation, revocation and offline devices (Q35, part of Q34)

**What competitors teach:**
- **Umbrel stable 2.0.1 has no release signature**: it runs a server-supplied script [C-W3-034]. The parallel teardown also found `--insecure-skip-bundle-verification` in the stable path (`02-competitors/umbrelos.md`). The **2.1-beta** design is excellent: an offline hardware-wallet root signs an approved-signer list; M-of-N Secure Enclave signers sign a manifest pinning every file hash; revocation by manifest hash; root handover; anti-downgrade [C-W3-035, C-W3-037]. But its lists "don't expire" [C-W3-035], so a device cut off from the internet trusts its last list forever.
- **HAOS proves key rotation in the field**: a new root valid to 2046 plus a release certificate cross-signed by the old root, so old devices accept new bundles; the old chain is accepted until 2028-05-14 [C-W3-024].
- **RAUC has the knobs for offline boxes**: validate certificates at the bundle's signing time instead of the device clock, optional CRLs (with a warning that an expired CRL blocks updates), and a signer allow-list [C-W3-018].
- **TUF** says clients must not trust expired metadata, and treats wrong clocks as an unsolved future topic [C-W3-067].

**OneMind design (ship in release 1):**
1. **Root key** offline (hardware security key or HSM; ceremony and custody are a founder decision, listed in `26-…`). It signs only (a) the approved-signer list and (b) root handovers.
2. **Release signers:** 2-of-3 hardware-backed keys (one can be the founder's Mac Secure Enclave, as Umbrel does). They sign the **release manifest**: version, channel, per-board bundle hashes, minimum version, expiry.
3. **RAUC bundle certificates** chain to a OneMind update CA; `use-bundle-signing-time=true` so a box with a dead RTC battery can still install an offline bundle [C-W3-018]. Keep CRLs off at first (expiry risk) and revoke at the manifest level instead.
4. **Expiry with a grace period:** manifests and signer lists carry an expiry (for example 1 year). An expired manifest still installs from USB **if** the user confirms on the device ("this update is older than a year, install anyway?"). This answers TUF's freeze concern without bricking off-grid boxes.
5. **Revocation:** by manifest hash and by signer key in the root-signed list (Umbrel pattern), fetched from two sources and also carried inside every newer manifest so offline USB updates deliver revocations too.
6. **Rotation drill:** before the first box ships, rotate the update CA once in the lab using HAOS's cross-signing method [C-W3-024].
7. **Never sign script payloads** that run before verification (Umbrel's own warning, VUPD §2).

---

## 9. Delta updates, channels, user-controlled timing, pre-update backup (Q34 part, R-1)

- **Delta:** RAUC adaptive updates (`block-hash-index`) over HTTP streaming, open source [C-W3-019]. Measure the saving in the lab (Q5's 64 kbps / 10% loss test belongs in T-W3-05). Mender's equivalent is paid [C-W3-055].
- **Channels:** `stable`, `beta`, plus an internal `dev` channel, as HAOS and Umbrel do (VUPD). The manifest names its channel; the device refuses a manifest for another channel unless the user switches.
- **Timing (R-1):** the default never installs or reboots by itself (Umbrel and HAOS pattern, VUPD). Options: "download in background", "install now, restart later", "restart in a window (e.g. 03:00–05:00)". For unattended field devices (robots, off-grid sensors) the owner can opt in to "auto-install security releases in my window". Off by default.
- **Pre-update backup:** always take the k3s datastore snapshot and config backup locally before install (§7.2). If a backup target is configured (W5), run an incremental restic backup first and show its result. HAOS offers "automatic backup before update" (VUPD §1).
- **Offline and mesh (Q34, N-6):** a release is a folder (manifest + bundles + signatures) that works from a USB stick, from another OneMind box on the LAN acting as a mirror, or from the internet. Same verification path for all three.

---

## 10. Recovery, factory reset and power loss

**Power loss mid-update.** RAUC describes itself as fail-safe and atomic (VUPD §5). Rugix documents that an interrupted install leaves only the inactive slot partly written and never selects it [C-W3-010], and keeps two checksummed copies of its GRUB variable [C-W3-012]. NVIDIA's OTA resumes from a recovery kernel [C-W3-051]. The weak spot in competitors is **any shared partition updated in place**: HAOS overwrites its single boot partition during updates [C-W3-022], and a corrupted grubenv once blocked updates (#3995 [C-W3-032]). **Rule:** the only non-A/B bootloader content is the ESP's first-stage GRUB and its environment; it changes rarely, is written via temp-file-and-rename, and keeps two copies.

**Factory reset.** Copy Umbrel's approach: reset the *state* but keep a backup (`rugix-ctrl state reset --backup` [C-W3-041]; with RAUC we implement the same on the data partition). **Never** implement reset as a flag on a shared boot command line: HAOS's data wipe is a boot-time flag [C-W3-072], and in #4995 a routine update somehow booted with it set and erased a user's data [C-W3-030]. Our reset needs a signed request from the running agent, a nonce, and a second confirmation.

**Recovery when both slots fail.**
- x86: the **USB installer ISO doubles as a rescue disk** (repair boot, reinstall OS keeping data, export data). Reserve a 1 GiB partition for a later on-disk recovery system (RAUC supports asymmetric recovery setups, VUPD §5); adding it later would mean repartitioning.
- Pi 5: reflash the boot medium; data on NVMe survives if the OS boots from SD/USB (Umbrel's USB-boot pattern [C-W3-042]).
- Jetson: NVIDIA's recovery kernel [C-W3-049, C-W3-051].

---

## 11. Disk layout per board (decide now; changing it later needs a reflash)

Principles: GPT everywhere; kernel and initrd inside the A/B pair; generous slots (Debian rootfs plus room for Debian 15 and dm-verity hash trees later); data on its own partition; labels, not numbers, so either engine can drive the disk (§5.2).

**x86_64 UEFI (Lite, Pro, Omni, VM images)**

| # | Label | Size | Content | A/B? | Evidence for size |
|---|---|---|---|---|---|
| 1 | `onemind-esp` | **1 GiB** FAT32 | GRUB EFI, grubenv (two copies), room for signed UKIs/systemd-boot later (DC-18) | No (rarely updated, guarded) | HAOS 32 MB, Umbrel 256 MB, Rugix systemd-boot schema 512 MB [C-W3-023, C-W3-038]; we take more to keep the UKI path open |
| 2 | `onemind-boot-a` | 512 MiB ext4 | kernel, initrd, cmdline | A | Umbrel 512 MiB [C-W3-038] |
| 3 | `onemind-boot-b` | 512 MiB ext4 | same | B | — |
| 4 | `onemind-system-a` | **10 GiB** | read-only root (EROFS or squashfs; ext4 RO as fallback) | A | Umbrel 10 GiB [C-W3-038] |
| 5 | `onemind-system-b` | 10 GiB | same | B | — |
| 6 | `onemind-recovery` | 1 GiB | reserved, empty at launch | No | §10 |
| 7 | `onemind-data` | rest | ext4 (ZFS optional on multi-disk Pro), LUKS-ready (W6) | No | HAOS/Umbrel data partition |

Firmware: UEFI only. HAOS shows legacy BIOS breaks slot switching (#5036 [C-W3-031]). Also check for 4Kn-sector disks, which HAOS can't boot [C-W3-027].

**Raspberry Pi 5 / CM5 (Edge tier; SD, USB or NVMe)**

| # | Label | Size | Content | A/B? |
|---|---|---|---|---|
| 1 | `config` | 256 MiB FAT32 | `autoboot.txt` with `tryboot_a_b=1` [C-W3-066] | No |
| 2 | `boot-a` | 256 MiB FAT32 | firmware, kernel, DTBs, `config.txt`, `cmdline.txt` | A |
| 3 | `boot-b` | 256 MiB FAT32 | same | B |
| 4 | `system-a` | **6 GiB** squashfs/EROFS | root | A |
| 5 | `system-b` | 6 GiB | root | B |
| 6 | `data` | rest | ext4 (F2FS is an option on SD; W5/W18) | No |

Umbrel uses 128 MiB boot and 5 GiB system slots on Pi [C-W3-038]; we add headroom because a Pi 5 kernel plus firmware grows, and Debian 15 will be larger. The Pi EEPROM bootloader is a separate firmware layer with its own update path (Q36, W6/W10).

**Jetson Orin / Thor (Robotics tier)** — follow NVIDIA's `ROOTFS_AB=1` layout: QSPI bootloader A/B, `APP` and `APP_b` rootfs slots (names fixed by NVIDIA [C-W3-049]), plus a OneMind data partition. NVIDIA reserves the end-of-disk UDA partition in some layouts; Mender's Tegra layer adds a dedicated persistent partition instead (`meta-mender-tegra` README [C-W3-053]). Exact sizes: founder-hardware test T-W3-06.

**VM appliance** — the x86 layout, shipped as qcow2, vhdx, vmdk, vdi and ova (HAOS ships all five [C-W3-026]), with a 32 GiB virtual disk by default.

**RK3588 (year 2+)** — U-Boot with RAUC's U-Boot backend (`BOOT_x_LEFT` counters [C-W3-020]); same labels. Rugix's BSP repo already has Rockchip boards [C-W3-013] if we stay engine-flexible.

Sizes marked bold are estimates to be confirmed by measuring the OneMind rootfs in the lab (`evidence/lab/debian-rugix/`, `evidence/lab/rauc/`).

---

## 12. Install paths (P-7)

### 12.1 What competitors offer

| Product | Flash image | USB installer | VM appliance | Script on existing Linux | Preinstalled box | Update + rollback on BYO hardware? |
|---|---|---|---|---|---|---|
| HAOS | Yes (per board) | **No** (use live Ubuntu or Etcher) [C-W3-027] | Yes, 5 formats [C-W3-026] | Deprecated 2025 [C-W3-028] | HA Green/Yellow | Yes (same image) |
| umbrelOS | Yes (Pi; x86 runs from USB) | Yes (NixOS ISO) [C-W3-043] | Yes (same ISO, any EFI VM) [C-W3-042] | Not offered on the downloads page [C-W3-042] (history UNVERIFIED) | Home, Pro | Yes |
| Olares | No | ISO (installs Ubuntu + Olares) [C-W3-045] | PVE ISO/script, LXC (not prod) | **Yes** (recommended alternative) [C-W3-045] | Olares One | **No OS rollback** |
| CasaOS | No | No | No | **Only path** [C-W3-046] | ZimaBoard (as ZimaOS) | No |
| ZimaOS | No | Yes [C-W3-047] | Not checked | No | ZimaBoard/Cube | Yes (RAUC) |
| StartOS | Yes (Pi, Rockchip) | Yes (ISO) [C-W3-048] | Not checked | No | Server One | Image switch; rollback not verified |

### 12.2 OneMind install-path matrix

| Path | Who | How | OS updates | OS rollback | Supported at launch? | Requirement |
|---|---|---|---|---|---|---|
| **P1 Preinstalled box** | Buyers of OneMind boxes | Factory-flashed with the installer ISO in auto mode (Umbrel's auto-flash on its own hardware [C-W3-043]) | Full A/B | Yes | Yes (when boxes ship) | H-1, P-7 |
| **P2 Flash image** | Pi 5/CM5 owners | Raspberry Pi Imager or Etcher writes `onemind-pi.img`; first boot grows data | Full A/B | Yes | **Yes** | P-7, P-8, N-2 |
| **P3 USB installer ISO** | x86 BYO (mini PCs, GPU boxes, laptops) | Boot the ISO, pick a disk, confirm erase; also the rescue disk | Full A/B | Yes | **Yes** | P-7, R-1 |
| **P4 VM appliance** | Try-before-buy, homelab, Proxmox/UTM/Hyper-V | qcow2/vhdx/vmdk/vdi/ova images or the ISO in any EFI VM | Full A/B inside the VM | Yes | **Yes** | P-7, F-8 |
| **P5 Jetson flash** | Robotics tier | NVIDIA flash from an x86 Ubuntu host (W18), then the OneMind layer | NVIDIA A/B + OneMind wrapper | Yes (NVIDIA) | Beta (after T-W3-06) | M-7, N-8 |
| **P6 Platform mode (script)** | Developers, people who must keep their distro | Installs k3s + OneMind platform on Debian/Ubuntu | Platform and apps only; the OS stays theirs (apt) | **No OS rollback**; app/platform rollback via Helm | Developer preview only, clearly labelled | P-9, F-8 |
| **P7 Fleet/PXE** | 100+ devices | Network boot of the installer with a provisioning token | Full A/B | Yes | Year 2 (W8 zero-touch) | F-11, N-4 |

**Why P6 stays developer-only:** a script on someone else's OS cannot give A/B rollback (Olares and CasaOS have none [C-W3-045, C-W3-046]), and HA dropped its script modes because they caused a disproportionate share of support issues [C-W3-028]. **Fedora/bootc note (F-12):** bootc can convert an existing Linux in place and keep rollback [C-W3-059]. If W2 adopts a bootc Industrial track, that track gets a real BYO-conversion path that Debian + RAUC can't offer.

### 12.3 Install matrix per tier

| Tier | Default path | Also supported | Update backend |
|---|---|---|---|
| Edge (Pi 5/CM5) | P2 | P1 (kits) | RAUC + tryboot |
| Lite (mini PC) | P3 | P1, P4 | RAUC + GRUB |
| Pro (GPU) | P3 | P1 | RAUC + GRUB (NVIDIA driver inside the image; W4) |
| Robotics (Jetson) | P5 | P1 | NVIDIA A/B + OneMind wrapper |
| Omni (sim/training) | P3 | P1 | RAUC + GRUB |
| Cluster | P3 on each node + join token | P7 | RAUC per node; k3s-minor rules in §7.4 |
| Developer | P4 | P6 | Image A/B in VM; or platform-only |

---

## 13. Real-world failure reports and what they teach

| Report | What happened | Lesson for OneMind |
|---|---|---|
| HAOS #4995 [C-W3-030] | A routine update booted with `haos.wipe=1` and erased the data partition; cause never found | No destructive flags on shared boot config; reset needs a signed request, a nonce and a confirmation (§10) |
| HAOS #5036 [C-W3-031] | Legacy-BIOS installs read a different grubenv, so slot switching silently fails | UEFI-only for x86; one well-defined env file |
| HAOS #3995 [C-W3-032] | Corrupted grubenv blocked an update | Two checksummed copies of boot state (Rugix pattern [C-W3-012]); write via temp file and rename |
| HAOS #5098 [C-W3-033] | Pi 5 froze daily after an update; user rolled back by hand | Gates can't catch delayed failures; keep one-click "previous version" in the UI (§7.3) |
| HAOS [#5143](https://github.com/home-assistant/operating-system/issues/5143) (title read via API only) | Bluetooth regression fixed by rolling back | Same as above |
| Umbrel #2297 [C-W3-044] | UI unreachable after an update; the box had already committed at daemon start | Commit only after the platform gate (§7.3) |
| Rugix [#117](https://github.com/rugix/rugix/issues/117) (title read via API only) | `rugix-ctrl` couldn't find the active partition with an encrypted root (closed) | Test the encrypted-data path (DC-18) in the lab before shipping LUKS |
| Rugix [#136](https://github.com/rugix/rugix/issues/136) (title read via API only) | Dynamic delta opened a new TLS connection per 64 KiB block, no socket timeout (closed) | Test delta over bad links (T-W3-05) whatever engine we choose |

---

## 14. Steelman for the runner-up, and the refuter table

### 14.1 Steelman: keep Rugix as the lead (written to argue *for* Rugix)

Rugix is the only engine whose author designed it around exactly our problem: a Debian-based appliance image with a read-only root and **declared persistent state**, built from a Mac in containers by Rugix Bakery. Umbrel, the closest product to OneMind (small team, Debian, Pi 5 + x86, consumer UX), runs it today on Pi and x86, and moved its whole installed base from Debian 12 to 13 and from Mender to Rugix without reflashing [C-W3-039, C-W3-040]. Rugix's docs are the clearest of any engine, its issues are answered in days, it is MIT/Apache (no LGPL relinking questions), its deltas are free and fast, and its `rauc-*` and `mender-*` boot flows mean **nothing is lost** by starting with Rugix: if Silitics disappears, we move to RAUC with an update. Many embedded tools start with one main maintainer; what matters is whether the code and format outlive them, and Rugix's are open and permissive. Using RAUC means picking a separate image builder and re-creating state management that Rugix gives us for free, which costs a solo founder weeks.

**Response:** the steelman is strong on C5 and is why the layout stays Rugix-compatible. It doesn't overturn the verdict because (a) the frozen evidence rules can't count vendor-claimed adopters, (b) Rugix lacks revocation and multi-signer support that we would build ourselves, while RAUC has them [C-W3-009, C-W3-018], and (c) the "exit by update" argument applies in both directions, so choosing the engine with more maintainers costs nothing in flexibility. If the founder weighs build convenience above maintainer risk, Rugix is an acceptable choice **with the same layout and signing design**; that is listed as a founder decision in `26-…`.

### 14.2 Refuter table (P0 conclusions; filled by independent refuters)

| Conclusion | Technical | Longevity/vendor | Security | Cost/business | Robotics fit | Response |
|---|---|---|---|---|---|---|
| P0-1 Rugix has a bus factor of 1 | pending | pending | — | — | — | — |
| P0-2 RAUC leads S2 | pending | pending | pending | pending | pending | — |
| P0-3 No engine covers stock L4T Jetson | pending | — | — | — | pending | — |
| P0-4 k3s inside the image with a trial copy is safe | pending | — | pending | — | pending | — |
| P0-5 Debian major rebases don't need a reflash | pending | pending | — | — | — | — |
| P0-6 Competitors commit before the platform is healthy | pending | — | pending | — | — | — |
| P0-7 Umbrel stable releases are not release-signed | pending | — | pending | — | — | — |
| P0-8 Script-on-distro is developer-only | pending | — | — | pending | — | — |

---

## 15. Lab spikes and founder-runnable tests

The repo already has pre-registered spikes run by the lab agent: `evidence/lab/debian-rugix/` (Rugix A/B, health gate, power cut) and `evidence/lab/rauc/` (RAUC A/B, forced bad update, unbootable update, power cut). **Results were pending when this file was written**; C3 stays at "doc-only" until they land. Tests below go into `22-HARDWARE-LAB-TEST-PLAN.md`.

| ID | Test | Pass | Fail | Decision it informs |
|---|---|---|---|---|
| T-W3-01 | RAUC vs Rugix on the Beelink U55 and Dell 5540: install, forced bad update, power cut during write (pull the plug) | Both return to the old slot with no human action; data intact | Any brick or data loss | S2 confirmation (V1) |
| T-W3-02 | k3s health gate on Pi 5 (SD and NVMe): good update, k3s broken update, gate timeout | Bad update rolls back within timeout + 1 boot; good update commits; time to commit recorded | Commit of a broken k3s, or rollback loop | DC-12, gate timeout value |
| T-W3-03 | k3s-minor trial copy: release N (k3s 1.N) → N+1 (1.N+1) fails gate → fallback | Old slot's k3s starts on the untouched datastore; workloads intact | k3s refuses to start or datastore corrupt | DC-12 flip condition |
| T-W3-04 | Debian 13 → Debian 14 (testing) bundle on the x86 layout of §11 | Fits the 10 GiB slot, boots, commits, data intact | Doesn't fit or needs a bootloader change | DC-05 flip condition |
| T-W3-05 | Delta update over a throttled link (64 kbps, 10% loss) | Completes or resumes; size and time recorded | Hangs without timeout | Q5 delta |
| T-W3-06 | Jetson Orin Nano: NVIDIA rootfs A/B with a OneMind gate in `l4t-rootfs-validation-config`; image-based OTA with a power cut | Gate failure falls back; OTA resumes after power cut | Hook can't block commit, or device needs reflash | DC-07 flip condition (blocked: founder-hardware) |
| T-W3-07 | Offline USB update with RTC set to 2020 and to 2040 | Installs with signing-time validation; expiry prompt shown | Refused outright or installed silently past expiry | §8 |

---

## 16. Recommendations (each traced to requirement IDs)

| ID | Recommendation | Requirement IDs |
|---|---|---|
| W3-REC-01 | Make **RAUC** the A/B update client for x86 and Pi 5; keep Rugix as the documented alternative | R-1, R-3, M-6, M-8 |
| W3-REC-02 | Use label-based slots and RAUC's GRUB variables (Rugix `rauc-grub` compatible) so the engine can be swapped by update | R-3, M-6 |
| W3-REC-03 | One release contract (manifest, signing, gate, UI, CLI/API) over per-board backends; NVIDIA rootfs A/B + image-based OTA on Jetson | M-7, N-2, N-8, F-2, F-14 |
| W3-REC-04 | k3s inside the read-only image; datastore on data; trial copy per update; k3s-minor guard; no SUC on image nodes | R-1, R-2, N-9, AI-4 |
| W3-REC-05 | Commit only after the platform gate (k3s Ready, core pods Ready, data RW, local API); apps excluded; watchdog + timeout; no auto-retry of a failed release | R-1, R-2, AI-4 |
| W3-REC-06 | Fix the disk layouts in §11 now (1 GiB ESP, 10 GiB x86 slots, 6 GiB Pi slots, reserved recovery, UEFI-only) | R-3, H-1, H-3, U-4 |
| W3-REC-07 | Release signing from release 1: offline root, 2-of-3 signers, signed manifest with expiry + offline grace, revocation in-band, CA rotation drill before first box | R-1, U-4, M-2, H-1 |
| W3-REC-08 | User-controlled timing by default; opt-in maintenance windows for unattended devices; stable/beta/dev channels | R-1, N-6, F-11 |
| W3-REC-09 | Pre-update datastore + config snapshot always; restic run if configured | R-1, R-2, M-2 |
| W3-REC-10 | Offline/mesh delivery: the same release folder from USB, a LAN mirror box or the internet | N-6, F-11, F-13 |
| W3-REC-11 | Factory reset = state reset with backup, signed request + confirmation; USB installer doubles as rescue disk | R-2, M-2 |
| W3-REC-12 | Install paths P1–P5 supported; P6 script = developer preview without OS rollback; P7 fleet in year 2 | P-7, P-8, P-9, H-1, F-8 |
| W3-REC-13 | Give W2's Fedora/bootc track credit for BYO in-place conversion and rebase-by-design; re-score S2 if bootc gains a Pi 5 boot path | F-12, F-11 |

---

## 17. Corrections, open items, blocked items

**Corrections to earlier repo files (evidence attached):**
1. `context/03` §1 says umbrelOS has release signing (offline root, revocation, anti-downgrade). **True for 2.1.0-beta.1 only.** Stable 2.0.1 runs a server-supplied script [C-W3-034, C-W3-035]. (Same finding in `02-competitors/umbrelos.md`.)
2. `context/03` §3 open item "How umbreld commits a Rugix slot": **closed.** It runs `rugix-ctrl system commit` at umbreld start [C-W3-036].
3. VUPD §4 "Rugix Jetson: UNVERIFIED": now a **verified absence** across four Rugix repos [C-W3-013].
4. ADR-001 D3 "k3s via system-upgrade-controller": doesn't fit a read-only image root [C-W3-065]; replaced by §7.
5. `kairos-io/kairos-agent` shows as archived on GitHub; that is a monorepo move, not abandonment [C-W3-062].
6. Kairos remained "a candidate for the Jetson flavor" in ADR-001; it is outscored here by NVIDIA's native mechanism, which needs no extra OS layer.

**Open (UNVERIFIED) items:** RAUC maintainer affiliation and funding (not read); StartOS automatic rollback behaviour; Umbrel's reason for leaving Mender; exact OneMind rootfs size (drives §11 sizes); whether NVIDIA's validation hook can block commit long enough for k3s (T-W3-06); EROFS support in the GRUB version we ship (affects whether kernels must stay in boot-a/b).

**Blocked:** T-W3-06 (blocked: founder-hardware, Jetson Orin Nano); T-W3-01/02 on real Beelink, Dell and Pi 5 (blocked: founder-hardware; QEMU substitutes in `evidence/lab/`); key-ceremony custody and whether the founder prefers Rugix's build convenience over RAUC's maintainer depth (blocked: founder-decision, listed for `26-OPEN-QUESTIONS-FOR-ZEUS.md`).
