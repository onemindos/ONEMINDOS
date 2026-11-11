# Licence matrix: what OneMind OS may ship, and what it owes

**Owner:** LIC · **Date:** 2026-11-11 · **Status:** complete for every component recommended in 01, 03–09 and 28, plus the Market seed apps from `docs/APPS.md`, W8 and the competitor landscape (`13-apps-market-plugins.md` did not exist when this was written; re-run the method when it lands) · **Data:** [`license-matrix.csv`](license-matrix.csv) (153 rows) · **Claims:** [`claims/LIC.csv`](claims/LIC.csv) (C-LIC-001…055) · **Sources:** [`sources/LIC.md`](sources/LIC.md), archive [`sources/LIC/`](sources/LIC/)
**Serves requirements:** D-001, M-6, M-8, R-3, H-1, H-4, P-5, P-7, P-8, A-1, A-3, A-5, A-6, F-2, F-4, F-5, N-8, U-4, RS-1
**Not legal advice.** This file says what the licence texts say and where OneMind needs counsel. It does not replace a lawyer.

> ### Explain it like I'm the founder
> Every piece of software you put in a OneMind box comes with a licence: the rules for copying it, selling it and changing it. OneMind's own code is Apache-2.0 (D-001), which is very permissive. The question is whether everything **around** it lets you sell boxes and images. The short answer is **yes, with homework**:
>
> 1. **The core stack is clean.** Debian, k3s, RAUC, restic, NATS, Traefik, Longhorn and OpenBao are all open-source licences that allow commercial use. 94 of the 153 components can even be mixed into Apache-2.0 code.
> 2. **The kernel and many Debian programs are GPL.** You may sell them, but **every release must come with its source code** (or a written offer to send it, valid for three years). That is a build-pipeline job, not a legal risk, if it is done from day one [C-LIC-018].
> 3. **If you lock the boot chain on boxes you sell** (Secure Boot keys you alone hold, Jetson fuses), the GPL-3 programs in the image oblige you to let the owner install their own modified versions. The "owner takeover" procedure already planned (SEC-03) is how you meet that [C-LIC-019].
> 4. **NVIDIA's Jetson software can be redistributed.** The question left open earlier (C-W7-056) is now answered from NVIDIA's own licence file. You may ship the Jetson BSP **unmodified**, on NVIDIA hardware only, with the licence text attached. NVIDIA can revoke it, and it says the software is not certified for "critical" uses such as navigation, autonomous vehicles or military work [C-LIC-001…005].
> 5. **Two surprises:** NVIDIA's **Isaac ROS is not open source** (it uses a proprietary NVIDIA licence) [C-LIC-021], and **Open WebUI forbids removing its branding** once more than 50 people use it [C-LIC-022]. Both can be offered as Market apps, but they can't be part of the OneMind core or rebranded.
> 6. **Ubuntu is the real licensing blocker**, and it is a trademark policy, not a code licence: a *modified* Ubuntu image needs Canonical's approval, or a full rebuild with all Ubuntu branding removed [C-LIC-011]. That affects the Jetson flavor and the optional GPU-server flavor. A quote request to Canonical is drafted in [`outreach-drafts.md`](outreach-drafts.md).
> 7. **Never copy code** from umbrelOS (noncommercial licence), the Umbrel app store (no licence), Olares, Glance or VillageOS (AGPL). Reading it to learn is fine.

---

## Contents

1. Glossary
2. Method
3. The matrix at a glance
4. Licence gate (G1) per recommended layer
5. High-risk findings
6. Resolving C-W7-056: the Jetson BSP licence
7. What competitors do (constraint fit)
8. Recommendations with requirement IDs
9. Gaps, UNVERIFIED items and re-check dates
10. Hand-off notes (ledger supersessions, items for 01, 08 and 26)

---

## 1. Glossary

| Term | Meaning |
|---|---|
| **SPDX ID** | A standard short name for a licence, such as `Apache-2.0` or `GPL-2.0-only`. `LicenseRef-…` marks a custom licence with no standard name. |
| **Permissive** | MIT, BSD, Apache-2.0, Zlib, ISC: copy, change and sell, keeping the notices. |
| **Weak (file-level) copyleft** | LGPL, MPL, EPL, CDDL: if you change *those* files you must publish the changes, but your own code stays yours. |
| **Strong copyleft** | GPL: whoever receives a binary may ask for the full source of that program. |
| **AGPL** | GPL plus a rule that people using a *modified* version over a network can get its source. |
| **Source offer** | The GPL duty to ship source with a binary, or a written offer valid ≥ 3 years (GPL-2.0 s3). |
| **Installation Information** | GPL-3.0 s6: for consumer devices, the keys or methods needed to install a modified version. |
| **Aggregate** | Separate programs shipped side by side on one disk. Their licences do not mix. This is how an Apache-2.0 OS can carry GPL programs. |
| **EULA / proprietary licence** | A vendor contract (NVIDIA, Hailo, Rockchip). You follow its rules exactly. You can't relicense it, and usually can't modify it. |
| **Blob** | A binary-only file (firmware, driver library) with no source. |
| **Trademark policy** | The rules for using a *name* (Ubuntu, Debian, Red Hat). They are separate from the code licence and can block redistribution of a modified image. |
| **BSL (BUSL-1.1)** | Business Source License: you can read the source, but production use is restricted until a change date. Not open source. |
| **PolyForm Noncommercial** | Source-available for noncommercial use only (umbrelOS). |

## 2. Method

1. **The component list** is the union of every component that is *recommended* in [`01`](../01-FOUNDATION-DECISION.md) (§1 table), 03 (W2-R1…R7), 04 (W3-REC-01…13), 05 (§2.4, §3), 06 (W5-R1…R14), 07 (SEC-01…17), 08 (W7-R1…R13), 09 (W8-R1…R12) and 28 (REC-W18-1…11). The Market seeds are every product named in [`docs/APPS.md`](../../docs/APPS.md) §A–B, the N.O.M.A.D. bundle (`research/competitors/landscape.md`), the W8 apps and the founder-cluster apps that carry forward (AI-9). Transitive runtime pieces are added where the image would carry them: Kubernetes, etcd, CoreDNS, containerd, runc, kine, SQLite, linux-firmware and the Pi Wi-Fi firmware. Competitor code that must not be copied is listed too, so the rule is mechanical.
2. **Pinning.** For each GitHub project: the latest release tag (or the default-branch head where a repo has no releases), resolved to a full commit SHA with `gh api`. The licence file path came from the licence API at that SHA. Non-GitHub sources were pinned the same way through GitLab, Salsa and kernel.org commit IDs, or through the exact NVIDIA `.deb` with its sha256.
3. **SPDX came from the file text**, never from GitHub's detector. The detector returned `NOASSERTION` or nothing for 48 of the 137 repositories queried, among them Rugix, RAUC's peers, bootc, Tailscale, SQLite, OpenZFS, ESPHome, Mosquitto, TAK Server and the Linux kernel. Every row in the CSV links `blob/<sha>/<file>`.
4. **Link check:** all 135 GitHub permalinks and the 5 GitLab/Salsa ones returned HTTP 200 on 2026-11-11 ([`sources/LIC.md`](sources/LIC.md) §4).
5. **Vendor terms** (NVIDIA, Hailo, Rockchip, Canonical, Debian, Red Hat, CentOS) were read in full and archived as text with sha256. Emails were masked; see `sources/LIC/ORIGINAL-HASHES.txt`. The Fedora trademark page sat behind a bot wall and was **not** bypassed [C-LIC-049].
6. **Safety:** the NVIDIA packages were downloaded into an isolated scratch folder and unpacked with `bsdtar` as data. No package script or binary was run.
7. **Column meanings in the CSV.** `commercial_redistribution_allowed` says whether OneMind may sell or ship it, and on what condition. `source_offer_obligation` is what OneMind owes recipients. `patent_clause` is what the text grants. `apache2_compatible` uses one of five classes (next section). `blob_eula_terms` holds proprietary conditions. `notes` carries claim IDs and decisions.

## 3. The matrix at a glance

| Class (`apache2_compatible`) | Rows | Meaning for OneMind | Examples |
|---|---|---|---|
| **Can be combined into Apache-2.0 code** | 94 | Copy, modify, embed; keep notices (Apache-2.0 NOTICE files must travel) | k3s, RKE2, Rugix, restic, NATS, Traefik, Longhorn, Home Assistant Core, ROS 2 core, ChirpStack, Kolibri |
| **Separate component, file-level copyleft** | 7 | Ship as is; publish changes to *their* files | RAUC (LGPL-2.1), OpenBao (MPL-2.0), systemd (LGPL-2.1+), open62541 (MPL), Tahu (EPL), mkosi, greenboot (shell) |
| **Separate program only (GPL/AGPL)** | 25 + Debian/Ubuntu aggregates | Fine side by side in the image or as a Market app; never paste code into the Apache core; source duties apply | Linux kernels, GRUB, cryptsetup, AppArmor, TAK Server, OpenTAKServer, CloudTAK, Grafana, Immich, Jellyfin, ESPHome runtime |
| **Proprietary: ship unmodified under its own terms** | 12 + NVIDIA x86/NGC (UNVERIFIED) | Can't be relicensed or modified; conditions travel with the binary | Jetson BSP, CUDA, Isaac ROS, Raspberry Pi firmware/EEPROM, linux-firmware blobs, Hailo firmware, RKNN |
| **Never bundle / never copy** | 9 | Study only, or leave for users to install themselves | umbrelOS, umbrel-apps, Olares, Glance, VillageOS-API, Homepage (code), EMQX, Reticulum, Open WebUI (white-label) |

OpenZFS (CDDL-1.0) is in its own class; see H-9.

## 4. Licence gate (G1) per recommended layer

This updates the G1 column of 01 §3.1.1 with primary licence text. A layer passes G1 when every shipped component may be redistributed commercially next to an Apache-2.0 core.

| Layer (01 §1) | Components | G1 verdict | Conditions | Claims |
|---|---|---|---|---|
| Debian 13 core image (x86_64, arm64) | Debian packages, Debian kernel 6.12, systemd, cryptsetup, AppArmor, GRUB or systemd-boot | **PASS with obligations** | Publish the source of every GPL/LGPL package and the kernel for each release (LIC-R1). Do not name the product "Debian …" (LIC-R4). GPL-3 Installation Information if the boot chain is locked (LIC-R3) | C-LIC-012, 017, 018, 019, 052 |
| Pi 5 flavor | Raspberry Pi kernel, Pi boot firmware, EEPROM, Cypress Wi-Fi blob | **PASS with conditions** | Firmware is binary-only, unmodified, **Raspberry Pi devices only**; ship each licence file in the image | C-LIC-015, 016, 020 |
| Jetson flavor (L4T r39.2.1, JetPack 7.2) | L4T kernel, Jetson BSP, CUDA, Ubuntu 24.04 rootfs | **BSP: PASS with conditions (was UNVERIFIED). Rootfs: still CONDITIONAL** | BSP: unmodified binaries, NVIDIA hardware, Agreement attached, revocable. CUDA: Jetson clause allows the whole SDK. Rootfs: Canonical approval for a modified image, or a debranded rebuild (H-4) | C-LIC-001…010, 048, 011 |
| GPU-server flavor (Ubuntu LTS + RKE2) | Ubuntu 26.04, NVIDIA open kernel modules, proprietary user-space driver | **CONDITIONAL** | Canonical approval (same as above). The x86 user-space driver licence is UNVERIFIED (LIC-R8) | C-LIC-011, 032 |
| bootc Industrial profile (year 2) | CentOS Stream 10 / AlmaLinux 10 / RHEL 10 image mode, bootc, greenboot-rs, MicroShift, Flight Control | **PASS on CentOS/Alma, debranded; RHEL needs an agreement** | Remove CentOS and Red Hat marks; RHEL subscription terms not read (UNVERIFIED) | C-LIC-013, 014, 040 |
| Updates | RAUC (LGPL-2.1), Rugix (MIT/Apache), Mender (Apache), thin-edge.io | **PASS** | Publish any RAUC patches | C-LIC-034, 035, 039 |
| Kubernetes | k3s, RKE2, Kubernetes, etcd, kine, containerd, runc, Flannel, Traefik, Gateway API, local-path, Longhorn, Helm, Argo CD | **PASS** | Keep NOTICE files; check the k3s SBOM for statically linked LGPL (libseccomp) | C-LIC-033 |
| Backups | restic, rest-server, SQLite | **PASS** | — | C-LIC-036, 037 |
| Security | OpenBao, cosign, systemd-boot, shim, OpenSSL | **PASS** | MPL changes to OpenBao published | C-LIC-038, 043 |
| Bus | NATS server, NACK, NATS CLI | **PASS** | — | C-LIC-033 |
| Robotics | ROS 2 Jazzy, rmw_zenoh, Zenoh (Apache option), PX4, MAVLink generated code, Open-RMF, ONNX Runtime | **PASS** | **Isaac ROS is proprietary**: optional Market app only (H-3) | C-LIC-021, 045, 047, 051 |
| IoT / mesh / TAK | Home Assistant, Mosquitto, NanoMQ, ChirpStack, Node-RED, batman-adv, TAK Server, OpenTAKServer, CloudTAK, Meshtastic, ESPHome | **PASS as separate apps** | GPL/AGPL apps stay separate; EMQX and Reticulum never bundled | C-LIC-026, 044, 046, 047 |
| Non-NVIDIA accelerators | HailoRT, Hailo firmware, RKNN | **CONDITIONAL** | Vendor-only grants; the Hailo firmware EULA forbids publishing benchmarks (H-7) | C-LIC-024, 025 |

## 5. High-risk findings

### H-1 · GPL source-offer obligations for the image (all flavors)
**What the text says.** GPL-2.0 s3: anyone distributing object code must include the complete source, or a written offer valid for at least three years [C-LIC-018]. The Linux kernel on every board is GPL-2.0 with the syscall note (mainline 6.12, Raspberry Pi rpi-6.12.y, NVIDIA linux-noble 6.8 for r39.2.1, CIP) [C-LIC-017]. Debian's own kernel source already removes the non-free files it can't redistribute [C-LIC-052].
**What it means.** Each OneMind release (an A/B bundle or a flashable image) is a distribution of hundreds of GPL/LGPL programs. "It's on debian.org" is not enough after Debian moves on: the source must match the shipped binary for three years.
**Do this (LIC-R1):** for every release, publish next to it: (a) the exact Debian source packages, from the `snapshot.debian.org` timestamp the image was built against; (b) the kernel tree at the exact commit for each board (the Raspberry Pi branch head and the NVIDIA linux-noble commit, plus NVIDIA's out-of-tree module sources); (c) OneMind's build scripts; (d) an SBOM listing every package and licence. Keep it for ≥ 3 years after the last shipment of that release. A written-offer page is the fallback for offline USB installs.

### H-2 · GPL-3.0 "Installation Information" versus locked boot chains
**What the text says.** GPL-3.0 s6: object code shipped in a **User Product** (a consumer product) must come with the "Installation Information" needed to install modified versions. The only exception is when *no one*, including the distributor, can install modified code [C-LIC-019].
**Where it bites.** OneMind's plan locks the boot chain on boxes it sells: its own PK/KEK/db on x86 (SEC-03), and irreversible Pi OTP and Jetson fuses (SEC-04). OneMind keeps the ability to install updates, so the exception doesn't apply. GPL-3 programs in the Debian base (GRUB, if kept, plus the GPL-3 user-space tools that Debian ships) then trigger the duty.
**Interpretation (needs counsel):** the **owner-takeover procedure** in SEC-03 (enrol the owner's own keys) is the standard way to meet it on x86. For fused Pi and Jetson units, OneMind needs a documented path for the owner to enrol a key or sign their own image *before* any fused product ships (LIC-R3). Preferring systemd-boot (LGPL) over GRUB on x86, as SEC-01 already does, reduces but does not remove the exposure.

### H-3 · NVIDIA licence limits (Jetson BSP, CUDA, Isaac ROS)
- **Jetson BSP** ("NVIDIA Driver License Agreement", v. 2025-02-25): redistribution allowed for use with OSI-licensed kernels, **unmodified**, with the Agreement given to each recipient [C-LIC-002]. NVIDIA hardware only; no reverse engineering; must not become subject to an open-source licence [C-LIC-003]. **Not certified for Critical Applications**: the examples include navigation, autonomous vehicles, military and medical. OneMind **indemnifies NVIDIA** and NVIDIA's liability is capped at US$5 [C-LIC-004]. The licence is revocable and terminates automatically on breach or if OneMind sues NVIDIA over the software [C-LIC-005].
- **CUDA EULA** (2026-01-26): redistribution only of Attachment A files, inside an application with material additional functionality [C-LIC-007]. For Jetson running L4T, the **whole SDK may be redistributed** for Jetson SDKs [C-LIC-008]. NVIDIA GPUs only; same open-source-subjection ban; Critical Application disclaimer [C-LIC-009].
- **Isaac ROS is proprietary** (NVIDIA Isaac ROS Software License), not Apache-2.0. It is for NVIDIA GPU systems only, downstream terms must be "at least as protective", and NVIDIA may terminate if continued use "is no longer commercially viable" [C-LIC-021]. This narrows **W7-R8** ("Isaac ROS images for GPU"): ship them as an **optional Market app** that shows its licence, never in the base image, and keep an open alternative path (ROS 2 + ONNX Runtime/TensorRT) for every robot feature (N-8 lock-in guard).
- **What OneMind must do (LIC-R5):** put the BSP and CUDA licence texts in the Jetson image and on the download page; never patch NVIDIA binaries (patch around them); keep NVIDIA components out of the Apache-2.0 repositories; carry the Critical Application disclaimer into OneMind's own robotics, drone and public-safety terms (it overlaps W6's machinery and CRA work); budget for the indemnity in insurance (H-1, F-2).

### H-4 · Canonical redistribution policy (Jetson rootfs, GPU-server option)
The IPRights Policy allows redistribution of Ubuntu **only unmodified**. A modified image must be "approved, certified or provided by Canonical", or you must "remove and replace the Trademarks and … recompile the source code to create your own binaries". That is a licence agreement "for which you may be required to pay" [C-LIC-011]. NVIDIA's own staff say L4T's redistribution answer "does not extend to Ubuntu root file system" [C-REF-DC-cost-007]. An image-based OneMind Jetson flavor (W7-R2) is a modified Ubuntu.
**Options:** (a) a Canonical agreement, possibly bundled with Ubuntu Pro for Devices (draft O-1 in [`outreach-drafts.md`](outreach-drafts.md)); (b) a Debian or meta-tegra rootfs on the NVIDIA BSP (DC-09 options c and W7-R3), which the BSP licence permits because it only requires an OSI-licensed kernel [C-LIC-002]; (c) a debranded rebuild, which is costly. **Until (a) is answered, the Jetson flavor stays G1-conditional and DC-09 remains open** (LIC-R6).

### H-5 · Raspberry Pi firmware is Raspberry-Pi-only
Boot firmware and the Pi 5 EEPROM bootloader may be redistributed unmodified, in binary form, and "only … for … running or using a Raspberry Pi device" [C-LIC-015, C-LIC-016]. That is fine for the Pi image and Compute Module 5 boards. It means OneMind's Pi flavor can't be re-targeted to non-Pi Broadcom boards, and the licence texts must be in the image.

### H-6 · Code that must never be copied (D-001, brief rule 4)
| Project | Licence at the pinned SHA | Rule |
|---|---|---|
| umbrelOS | PolyForm Noncommercial 1.0.0 [C-LIC-029] | Study only; no code, no build scripts |
| umbrel-apps catalog | **No licence file** [C-LIC-029] | Don't import manifests; write OneMind manifests from each app's upstream |
| Olares | AGPL-3.0, plus a non-commercial clause in LICENSE.md [C-LIC-030, C-TD-olares-047] | Study only |
| VillageOS-API | AGPL-3.0 or paid; attribution required [C-LIC-030, C-TD-villageos-025] | Host as an app or partner; don't copy |
| Glance, Homepage | AGPL-3.0, GPL-3.0 | Ideas only |

**Do this (LIC-R7):** run a licence scanner (ScanCode or the REUSE tool) and a code-provenance check in CI on every OneMind repository. Fail the build on any AGPL, GPL, PolyForm or unlicensed file inside an Apache-2.0 package.

### H-7 · Restricted, non-OSI and "open-core" licences among the seeds
- **Open WebUI:** branding may not be removed when more than 50 end users access it in 30 days [C-LIC-022]. List it as a branded third-party app only; never white-label it as "OneMind Chat".
- **EMQX** (BSL 1.1) forbids offering it "on a hosted or embedded basis". Never bundle it (confirms W8-R1).
- **Reticulum** forbids use in systems able to harm humans and use in AI/ML training datasets. That conflicts with OneMind's AI-context promise (AI-1) and with public-safety and defence SKUs. Keep it user-installed only (confirms W8-R7).
- **Hailo firmware EULA:** revocable, binary-only, Hailo products only, and **no publishing benchmarks or comparative analyses** [C-LIC-025]. OneMind's "can my box run this" scores (N-3, A-8) must not publish Hailo benchmark figures without Hailo's permission.
- **Rockchip RKNN:** Rockchip products only; no patent licence [C-LIC-024].
- **Open-core directories:** AFFiNE backend, authentik `enterprise/`, Infisical `ee/` [C-LIC-053]. Never enable or redistribute those directories.

### H-8 · AGPL Market apps
Grafana (AGPL since v8; v13.3.1 confirmed [C-LIC-023]), Immich, Firefly III, Plane and CloudTAK [C-LIC-028], plus NetBird's server parts [C-LIC-027]. Shipping them **unmodified** as separate apps is fine. If OneMind **modifies** one and users reach it over a network, including a future OneMind-hosted cloud (M-1, F-6), AGPL s13 requires offering that modified source to those users (LIC-R9).

### H-9 · OpenZFS (CDDL) with a GPL kernel
OpenZFS is CDDL-1.0 [C-LIC-031]. Combining CDDL modules with the GPL-2.0 kernel in one distributed binary is a long-disputed question. Debian ships ZFS as DKMS source in `contrib` for this reason. Shipping a **prebuilt, signed `zfs.ko` inside a OneMind image** (which Secure Boot pushes toward) needs counsel first. Until then, keep ZFS an optional Pro feature built on the device (LIC-R10).

### H-10 · Trademarks are separate from code licences
Debian: never put "Debian" in the product name; "based on Debian" is fine [C-LIC-012]. Red Hat: rebuilt code is allowed, but all Red Hat marks must be removed [C-LIC-013]. CentOS: no marks with commercial redistribution or rebuilds without permission [C-LIC-014]. Fedora: UNVERIFIED (blocked) [C-LIC-049]. Home Assistant and other apps: list them under their upstream names. That is also what keeps OneMind a CRA *distributor* rather than a *manufacturer* for third-party apps (SEC-11) (LIC-R4).

## 6. Resolving C-W7-056: the Jetson BSP licence

**Gap.** C-W7-056 recorded only that meta-tegra names `Tegra_Software_License_Agreement-Tegra-Linux.txt` (md5 `376d20bd…`) and that the text was never opened. The 01 G1 gate for the Jetson flavor was therefore unproven (critic S2 #8).

**Evidence.** NVIDIA's public Jetson apt feed carries `nvidia-l4t-core_39.2.1-20260806224157_arm64.deb` (sha256 `277a6fb2…`). It contains `/usr/share/doc/nvidia-l4t-core/Tegra_Software_License_Agreement-Tegra-Linux.txt.gz`, and the unpacked text has **md5 `376d20bd5275442226fcdf54e4844ddf`, identical to meta-tegra's checksum for the r39.2.1 BSP tarball** [C-LIC-001]. So the file read here is the same text that ships in the BSP. Saved copy: [`sources/LIC/01-nvidia-tegra-sla-r39.2.1.txt`](sources/LIC/01-nvidia-tegra-sla-r39.2.1.txt).

**Answer.**

| Question | Answer from the text | Clause |
|---|---|---|
| May OneMind redistribute the BSP in its images? | **Yes**, for use with OSI-licensed kernels (Linux qualifies), if the binaries are unmodified and the Agreement goes to every recipient | s1.1(d) [C-LIC-002] |
| On any hardware? | **No.** Only NVIDIA-designed and NVIDIA-sold chips; firmware only on NVIDIA Platforms | s2.1 [C-LIC-003] |
| May OneMind modify NVIDIA binaries? | **No** (source-form parts may be modified) | s1.1(b), s2.3 [C-LIC-003] |
| Can it be combined with GPL code? | Shipping side by side is allowed (the grant itself presumes an OSI kernel). It must not be used "in any manner that would cause it to become subject to an open source software license" | s2.9 [C-LIC-003] |
| Is it stable? | **Revocable**, and terminates on breach or on a suit against NVIDIA; earlier distributions survive | s1.1, s7 [C-LIC-002, C-LIC-005] |
| Robots, drones, public safety? | Not tested or certified for Critical Applications; OneMind indemnifies NVIDIA | s2.10–2.11 [C-LIC-004] |
| Files without their own licence? | Covered by the same NVIDIA EULA | copyright file [C-LIC-006] |

**Verdict.** The **BSP part of G1 passes with conditions** [C-LIC-048]. C-W7-056 should be marked `superseded` by C-LIC-001…005 and C-LIC-048. The Jetson flavor as a whole stays **G1-conditional because of the Ubuntu rootfs (H-4)**, not because of the BSP. Re-check every 6 months, and at each new L4T release (compare the md5).

## 7. What competitors do (constraint fit)

| Product | Their licence model (verified) | Their constraints | Constraint fit with OneMind | What OneMind takes |
|---|---|---|---|---|
| Home Assistant OS | Apache-2.0 OS build repo; Buildroot image with GPL parts (matrix row `haos`, release 18.5). Their GPL source-offer practice was **not verified** | Foundation-backed, appliance, no Kubernetes | **High**: same licence family as D-001 | Apache-2.0 for the OS tooling; copyleft programs as separate components |
| umbrelOS | PolyForm Noncommercial [C-LIC-029]; Debian-based image [C-W2-043] | Venture-backed, sells hardware, single node | **Low**: noncommercial licence contradicts D-001 open core | Nothing from the code; the business lesson that the box is the product |
| umbrel-apps | No licence file [C-LIC-029] | Community-contributed manifests | **None** (legal grey zone) | Write OneMind manifests fresh from each upstream |
| Olares | AGPL-3.0 plus a non-commercial clause [C-LIC-030, C-TD-olares-047] | Venture-backed, Kubernetes | **Low** for code reuse; high for architecture ideas | Patterns only |
| CasaOS | Apache-2.0 (matrix row) | IceWhale hardware company | **High** | Patterns; code reuse legally possible with NOTICE |
| Project N.O.M.A.D. | Apache-2.0 core bundling GPL Kiwix and MIT Kolibri as separate apps (matrix rows) | Volunteer, offline education | **High**: the aggregate model OneMind needs | Core under Apache-2.0, copyleft apps as separate containers |
| VillageOS | AGPL-3.0 or paid licence with mandatory attribution [C-TD-villageos-025] | Small company, partly closed server | **Low** for code; partner/host model | Host as an app (W8-R12) |
| NVIDIA JetPack (as a distributor) | Ships an Ubuntu rootfs but tells users to check Canonical's policy themselves [C-REF-DC-cost-007, -008] | Silicon vendor | **Warning**: NVIDIA does not carry the Canonical question for you | Settle it directly (O-1) |

## 8. Recommendations with requirement IDs

| ID | Recommendation | Requirements | Evidence |
|---|---|---|---|
| **LIC-R1** | Every release ships a **source bundle** (Debian source packages at the build snapshot, per-board kernel commit plus NVIDIA OOT sources, build scripts) and an **SBOM with licences**; keep it ≥ 3 years after last shipment; a written-offer page covers offline installs | D-001, R-3, H-1, M-6, P-7 | H-1, C-LIC-018 |
| **LIC-R2** | Generate the licence and SBOM list **from the image build** (the package manifest plus linux-firmware WHENCE entries), never by hand; ship `/usr/share/onemind/licenses/` and show it in Settings › About | M-6, U-4, R-2 | C-LIC-055, C-LIC-020 |
| **LIC-R3** | Before any locked or fused box ships: publish an **owner key-enrolment (takeover) procedure** for x86, Pi and Jetson that meets GPL-3 Installation Information; prefer systemd-boot over GRUB on x86 | H-1, H-4, M-2, U-4 | H-2, C-LIC-019 |
| **LIC-R4** | Name and brand only as **OneMind OS**; say "based on Debian" truthfully; list Market apps under upstream names; debrand any CentOS, RHEL or Ubuntu rebuild | D-001, A-1, H-1 | H-10, C-LIC-012…014 |
| **LIC-R5** | NVIDIA components: ship unmodified, with their licences attached, only on NVIDIA hardware, outside OneMind's Apache repos; carry the Critical Application disclaimer into OneMind's robot, drone and public-safety terms | N-8, F-2, M-7, H-3 | H-3, C-LIC-001…010 |
| **LIC-R6** | Treat the **Ubuntu rootfs** as the open G1 item for the Jetson and GPU-server flavors: send O-1, and prototype a Debian or meta-tegra rootfs on the BSP as the fallback (W7-R3) | F-2, N-8, H-3, R-3 | H-4, C-LIC-011 |
| **LIC-R7** | CI licence gate on every OneMind repo (ScanCode/REUSE): fail on AGPL, GPL, PolyForm, unlicensed or BSL files in Apache-2.0 packages; an allow-list per app manifest | D-001, A-5, A-6, F-5, M-6 | H-6 |
| **LIC-R8** | Read and archive the **x86 NVIDIA user-space driver licence** and the **NGC container licence** before shipping a Pro/Omni GPU box or mirroring Isaac/JetPack images | N-8, H-3 | §9 gaps |
| **LIC-R9** | Market manifests (`onemind.app.yaml`) carry `license.spdx`, `license.class` (permissive / copyleft / AGPL / proprietary / restricted) and `license.url`; the installer shows proprietary and restricted terms and needs a click to accept; OneMind never modifies AGPL apps without publishing the source | A-1, A-3, A-5, F-5, W-8 | H-7, H-8 |
| **LIC-R10** | OpenZFS stays an optional, on-device DKMS build until counsel approves a prebuilt signed module | P-5, H-3 | H-9, C-LIC-031 |
| **LIC-R11** | Isaac ROS, Hailo and RKNN ship as **vendor accelerator packs** (optional Market apps with their EULAs shown); OneMind's own robotics features must also run on the open path (ROS 2 + ONNX Runtime) | N-8, N-3, F-2, F-4, M-7 | C-LIC-021, 024, 025 |
| **LIC-R12** | Re-run this matrix with every release train: re-pin SHAs, diff licence texts (compare the md5, as for the Tegra SLA), and re-check vendor terms every 6 months | R-3, M-8, RS-1 | §2 |

## 9. Gaps, UNVERIFIED items and re-check dates

- **UNVERIFIED:** the x86 NVIDIA proprietary user-space driver licence (it is expected to be the same "NVIDIA Driver License Agreement" family, but not opened); the NGC container licence for JetPack and Isaac images; RHEL and RHDE subscription redistribution terms; the Fedora trademark guidelines (blocked); AlmaLinux trademark terms (404); the AFFiNE backend licence text; Cilium's BPF dual licence (not re-read); per-package licences inside ROS 2 images (needs an SBOM).
- **Not checked:** codec patent licences (H.264/H.265 in GStreamer/NVENC). Both NVIDIA texts say these are the distributor's job [C-LIC-005, C-LIC-009]. Add this to 26 if OneMind ships camera/video features on boxes it sells.
- **Pins use branch heads** where no release exists (Raspberry Pi kernel and firmware, MAVLink, ArduPilot, TAK Server, SQLite mirror, ClickHouse, competitor repos). OneMind's build must record the exact commit it builds.
- **AppArmor** was pinned to its latest tag, which is an alpha. Re-pin to Debian 13's package version.
- **Re-check:** BSP, kernel and Kubernetes rows by **2027-05-11**; licence and policy rows by **2027-11-11** (see `recheck_by` in the ledger).
- **`13-apps-market-plugins.md`** did not exist yet. When it lands, add any new seed apps with the same method; the build is scripted (rows come from `gh api` plus a judgement table).

## 10. Hand-off notes (this workstream may not edit other files)

- **Ledger supersessions to apply:** C-W7-056 → superseded by C-LIC-001…005 and C-LIC-048. The RAUC part of C-W2-049 → superseded by C-LIC-034 (pinned). C-W4-075 (k3s, unpinned) → superseded by C-LIC-033. C-W8-011, -013, -014 and -031 are reconfirmed at pinned SHAs (matrix rows).
- **01 §3.1.1 G1 column:** for Jetson, replace "needs the NVIDIA EULA step" with "BSP licence verified, redistributable unmodified on NVIDIA hardware [C-LIC-048]; rootfs needs Canonical approval [C-LIC-011]".
- **08 line ~120 and W7-R8:** state that Isaac ROS is proprietary [C-LIC-021], and make the Isaac images an optional app.
- **07:** add LIC-R3 (GPL-3 Installation Information) next to SEC-03 and SEC-04.
- **26 (open questions for Zeus):** (1) send outreach O-1…O-4; (2) accept the owner-takeover requirement for locked or fused boxes; (3) counsel review of H-2 (GPL-3 and locked boot), H-4 (Ubuntu) and H-9 (ZFS).
