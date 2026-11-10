# Fedora IoT, bootc and the Red Hat edge lineage: a fair deep dive for OneMind OS

Date of research: 2026-11-10. Re-examines ADR-001 D2/D3 (Debian 13 + Rugix A/B + k3s; NVIDIA L4T/Ubuntu flavor for Jetson), which dismissed Fedora IoT on four grounds. Founder priority F-12: Fedora IoT is "super important" for the IoT/IIoT future; he does not want to hit limitations.

## 0. How to read the evidence tags

- **VERIFIED**: I opened the primary source (git clone / `gh api` / `curl` / WebFetch) in this run and read the text.
- **SECONDARY**: opened, but it is a news site, reseller, aggregator (endoflife.date) or personal blog, not the project or vendor.
- **SEARCH-ONLY**: the fact came from a search-result summary and I did not open the page. Treat as a lead, not a fact.
- **INFERRED**: my reasoning from verified facts (reasoning stated).
- **UNVERIFIED**: could not confirm. Background knowledge is labelled "background, UNVERIFIED". Do not treat as fact.

Access notes. docs.fedoraproject.org is behind Anubis (bot wall) for both WebFetch and curl, so I read the same pages from their source repos (`fedora-iot/iot-docs`, `fedora/bootc/docs` on GitLab) plus the Fedora wiki, forge/pagure/GitHub issue trackers and the `dl.fedoraproject.org` compose tree. docs.redhat.com returns 403 to WebFetch but returns 200 to plain `curl`, so Red Hat docs were read as raw HTML text. src.fedoraproject.org returned "Project not found" for `kernel-rt`.

---

## 1. Executive summary (read this if nothing else)

1. **The prior ADR's four objections are each partly right and partly out of date.** Details in section 2. The biggest correction: it is no longer true that the Red Hat lineage has "no Jetson story". Red Hat Device Edge went **GA on NVIDIA Jetson Orin on 2026-05-12** (RHEL 9.8, delivered as a bootc image, with MicroShift and Red Hat Edge Manager) [S27].
2. **Separate "Fedora IoT the edition" from "the bootc lineage".** The edition is a small-team product with a 13-month lifecycle, no "oldstable" tree, a stale reference-platform page, and a 2025 attempt to demote it from Edition status (withdrawn) [S3, S9, S15]. The lineage (Fedora -> CentOS Stream -> RHEL; bootc + greenboot + FDO + quadlet + SELinux + Flight Control fleet manager) is the strongest enterprise/IIoT story in Linux and is where OneMind's founder is right.
3. **Fedora IoT already ships bootc.** `bootc` has been in the IoT compose since Fedora 41, composefs by default since 42, and the Fedora 45 compose (2026-10-31) includes a `Fedora-IoT-bootc-aarch64` OCI archive next to the ostree ISO and raw image [S2, S3, S5]. The "mid-transition" (2026-08-26) item is a proposal to unify **CoreOS and bootc**, targeting Fedora 46, which is additive for IoT [S12].
4. **Real limits that remain on the Fedora edition:** only the current release tree, no hold-back tree ("We don't have the resources for that") [S3 #123]; Raspberry Pi bootc images do not boot out of the box (open bug, workaround PR in bootupd) [S3 #82]; Fedora IoT on Pi 5 is **not documented** (Pi 5 boots Fedora 44/45 per Peter Robinson but he demonstrates Workstation, not IoT) [S13]; Zezere (old zero-touch provisioner) is stale/deprecated [S4, S9].
5. **RHEL 10 has a hardware floor** (x86-64-v3) and RHEL for Edge on RHEL 10 only exists as image mode (bootc). Device Edge with MicroShift on RHEL 10.0 is **Technology Preview**; production is RHEL 9.6 + MicroShift 4.21/4.20 [S22, S25].
6. **NVIDIA:** GPU Operator officially supports Ubuntu, RHEL 8/9/10 and RHCOS, **not Fedora, not Debian, not Jetson** [S29]. For Red Hat Device Edge, NVIDIA documents the validated path as x86, RHEL 9.x, RPM-installed (not image mode), NVIDIA device plugin instead of GPU Operator [S29]. For Jetson Orin on RHEL, Red Hat's QE matrix shows AGX Orin on RHEL 9.8 + JetPack 6.2.2 passing most hardware suites; Jetson Thor with RHEL 10.2 / L4T 39 is being tested but I found no GA statement [S28].
7. **Robotics is the clearest loss.** ROS 2 Lyrical (LTS to May 2031) is Tier 1 on Ubuntu 26.04 only; RHEL 10 is Tier 2 amd64 only (no arm64); Debian Trixie is Tier 3 (source); Fedora is not in the tier table, and Open Robotics' Fedora RPMs cover Fedora 43 x86_64 in a "testing" tier as of 2026-10-28 [S32].
8. **Recommendation (section 9):** do **not** replace Debian as the consumer default today, but **adopt the bootc lineage as OneMind's strategic Industrial, Enterprise and Jetson-enterprise track**, and make Fedora IoT bootc a continuously-tested supported profile (not a promise of 10 years). Concretely: (a) keep Debian 13 + Rugix default for Pi 5 / Lite; (b) build a second image pipeline from a Containerfile on `fedora-bootc` / CentOS Stream 10 / AlmaLinux 10 (free 10-year clone) / RHEL image mode (paid, certified); (c) define a "host profile contract" so apps never see the difference; (d) run the ten gating tests in section 9.4 and revisit after Fedora 46 (about April-May 2027).

---

## 2. The prior ADR's four objections, checked

| ADR claim | Verdict | Evidence |
|---|---|---|
| "Official aarch64 list only Pi 3/4" | **Wrong as stated, but the list is stale.** The aarch64 reference list also names Jetson Xavier, Jetson Orin, Rock960, SolidRun HummingBoard-M, Pine64 Rockpro64/Rock64/A64-LTS, generic SystemReady-IR/ES/SR, and a TianoCore VM. Pi 5 is absent. The page was last edited 2024-02-16, and an open Fedora IoT issue (#118, Sep 2025) says QA does not have the hardware (explicitly "NVidia Jetson") so the list "could be construed" as tested when it is not. | VERIFIED [S1, S3] |
| "Fedora mid-transition to bootc (proposal 2026-08-26)" | **Partly right, mis-framed.** 2026-08-26 is `coreos/fedora-coreos-tracker#2214` "CoreOS and Image Mode/Bootc Unification", aimed at Fedora 46. IoT already has bootc images (F41 bootc in compose, F42 IoT bootc image composed automatically, composefs default F42); ostree remains the primary IoT delivery in the compose. The 2025-26 Image Mode initiative wants IoT artifacts built on official base images: beta by F44, production by F45. A F45 change proposal (Atomic Unified Pipeline) is *proposed*, not approved, per its wiki page (last updated 2026-06-30). | VERIFIED [S2, S3, S7, S8, S12] |
| "~13-month release support" | **Correct.** Fedora wiki: new release every 6 months, each maintained about 13 months. F44 EOL 2027-06-02, F45 EOL 2027-12-08 (endoflife.date; Phoronix quotes `SUPPORT_END=2027-11-24` for F45, a 2-week discrepancy). F43 EOL 2026-12-01. | VERIFIED wiki sentence [S15]; dates SECONDARY [S16, S17] |
| "NVIDIA tools target Ubuntu/RHEL" | **Mostly right for the K8s/GPU Operator layer, wrong for CUDA/driver packaging.** GPU Operator matrix: Ubuntu, RHEL, RHCOS. But NVIDIA's own CUDA repo has `fedora43` and `fedora44` for x86_64 and sbsa (arm64 server), and a `fedora45` repo exists; it also has `debian13`. Existence of a repo is not an official support statement. | VERIFIED [S29, S30] |

What the ADR **missed** (all VERIFIED unless noted):

- Red Hat Device Edge GA on Jetson Orin (May 2026), a bootc image, and a Red Hat QE hardware matrix for it [S27, S28].
- RHEL image mode GA (RHEL 9.6+ and 10, announced 2025-05-20) and a 62443-4-2 SL-C 2 certification for RHEL 9.6 and MicroShift 4.21 [S26, S31].
- Fleet management is open and shared: Flight Control (Red Hat Edge Manager upstream) has a page in the Fedora bootc docs and is GA at Red Hat as Edge Manager 1.x [S19, S26-search].
- Peter Robinson (Fedora IoT lead per the IoT docs) and the Red Hat Jetson enablement team publish Fedora/RHEL-on-Orin and Pi 5 guides [S13, S14, S1].

---

## 3. Fedora IoT today (item 1 of the brief)

### 3.1 Facts table

| Fact | Value | Status | Source |
|---|---|---|---|
| Current Fedora release | **Fedora 45**, GA 2026-11-03 (after two NO-GOs). IoT compose dated 2026-10-31; `f45-stable` merged in fedora-iot-bootc on 2026-10-30. | compose dir VERIFIED; GA date SECONDARY | [S2, S5, S16, S17] |
| Previous releases | F44 (2026-04-28, EOL 2027-06-02), F43 (EOL 2026-12-01) | SECONDARY | [S16] |
| Lifecycle | 6-month cadence, about 13 months support; EOL = 1 month after release X+2 | VERIFIED sentence | [S15] |
| "Rolling" wording | IoT docs call them "rolling releases" and PRD talks about monthly snapshots, but trees are per Fedora release; no oldstable tree | VERIFIED | [S1, S3 #123] |
| Architectures in F45 IoT compose | aarch64, x86_64, ppc64le, s390x. **No riscv64 directory.** | VERIFIED | [S5] |
| Artifacts (x86_64) | `Fedora-IoT-ostree-45-...iso` 2.3 GB; `Fedora-IoT-provisioner-45-...iso` 1.2 GB | VERIFIED | [S5] |
| Artifacts (aarch64) | raw disk image 909 MB (xz); `Fedora-IoT-bootc-aarch64` OCI archive 846 MB; `Fedora-base-bootc` 947 MB | VERIFIED | [S5] |
| Docs' own hardware statement | "Fedora IoT supports the aarch64 (arm64) and x86_64 architectures"; "We only actively support UEFI platforms"; tested on 1 GB RAM; image 4 GB | VERIFIED | [S1] |
| Reference aarch64 devices (doc, last edited 2024-02-16) | Pi 3, Pi 4 (4B/CM4), Jetson Xavier, Jetson Orin, Rock960, HummingBoard-M (i.MX8), Rockpro64/Rock64, Pine A64-LTS/SoPine, TianoCore VM, SystemReady-IR/ES/SR | VERIFIED | [S1] |
| Reference x86_64 devices | TianoCore VM, Compulab Fitlet2, UP Squared, generic UEFI Intel x86-64 | VERIFIED | [S1] |
| Pi 5 | Fedora 44 boots Pi 5B (microSD and NVMe) with a one-time `cma=` workaround; Fedora 45 needs none. Works: accelerated graphics, storage, wired+wireless, USB, thermal/fan, SPI/I2C. Not working: sound and "a number of other things"; CM5 and Pi 500 in progress. Example uses **Workstation**; IoT not mentioned. | VERIFIED post (personal blog of Fedora IoT lead) + LWN | [S13] |
| Pi 5 + bootc | Docs: "Using bootc with Fedora IoT currently requires that you have already provisioned a device with Fedora IoT" (i.e. you cannot bootc-install straight onto an SD card). Bug #82 "Bootc image does not boot on rpi" is OPEN: bootc-image-builder raw images lack Pi firmware and u-boot and use GPT; fix requires bootupd `extend-payload-to-esp` (coreos/bootupd PR #935, tracking #959). | VERIFIED | [S1, S3 #82] |
| Per-device ARM images | IoT WG agreed 2026-09-30 to *explore* per-device images (spike #141, open); Orin and RPi named. Lead dev says SystemReady means no device-specific images should be needed. | VERIFIED | [S3 #141] |
| RISC-V | Fedora RISC-V is an alternative (secondary) architecture; F44 rebuild about 99% done (May 2026); primary promotion not decided. **No Fedora IoT RISC-V image found.** | search + compose listing | [S5, S37] |
| Simplified provisioning | `Fedora-IoT-provisioner` ISO: zero-touch install via FDO or Ignition | VERIFIED | [S1] |
| zezere | Repo last pushed 2023-09-04, README "still under development"; QE called its tests "deprecated" in 2025. Treat as dead. | VERIFIED | [S4, S9] |
| greenboot | Included in IoT (`greenboot`, `greenboot-default-health-checks`). Rust rewrite (`greenboot-rs`) is current: v0.16.5 on 2026-11-04; F43 change moved IoT to it. | VERIFIED pkg list + releases; F43 change SEARCH-ONLY | [S2, S4] |
| Podman / quadlet | Podman, netavark, aardvark-dns, passt in image; container-first model in docs. (Quadlet itself is part of Podman, background, UNVERIFIED for this image.) | VERIFIED pkgs | [S2] |
| FDO | `fdo-client`, `fdo-owner-cli` in the image; docs cover manufacturing, rendezvous and owner servers; upstream `fido-device-onboard-rs` (Rust) last push 2026-08-09 | VERIFIED | [S1, S2, S4] |
| Ignition | `ignition` and `ignition-edge` in the image; docs page for Ignition device setup | VERIFIED | [S1, S2] |
| Security components in image | `clevis` + TPM2 pin, `usbguard`, `ima-evm-utils`, `tpm2-pkcs11`, `firewalld`, `setools-console`, `policycoreutils` (SELinux), `fwupd-efi`, `zram-generator` | VERIFIED | [S2] |
| aarch64 extras | `arm-image-installer`, `bcm283x-firmware`, `optee_client`, `uboot-images-armv8` | VERIFIED | [S2] |
| MicroShift on Fedora IoT | MicroShift upstream mentions Fedora IoT only in a design footnote and uses greenboot from `fedora-iot/greenboot`. All MicroShift docs/dev setup say RHEL (RHEL 9.8 for the dev env, with RHEL repos and a subscription). **No supported Fedora IoT + MicroShift path found.** | VERIFIED absence in repo | [S36] |
| k3s on this lineage | k3s docs have a "Red Hat Enterprise Linux / CentOS / Fedora" install tab, with an extra package on RHEL 10; `k3s-selinux` actively maintained (pushed 2026-10-28). Image-mode specifics (read-only `/usr`, /var/lib/rancher) not verified. | VERIFIED docs; image-mode UNVERIFIED | [S35] |

### 3.2 Project-health signals (important, and not flattering)

All VERIFIED from [S9] and [S3] unless noted.

- **July 2025 proposal to reconsider IoT's Edition status** (from Fedora Quality): about 4k weekly countme check-ins for IoT vs about 200k Workstation, 107k CoreOS, 49k Server (countme reliability for IoT was disputed); "the project has lost dedicated people, including the IoT owner"; the QA hardware matrix "has not been updated in a long time"; Zezere tests deprecated. **The proposal was withdrawn**; IoT remains an Edition. Paul Whalen (Fedora IoT team) said the team handles the release process and most manual testing.
- Issue #118 (open): the reference-platform section may overstate testing; #119 (open): update IoT test matrix; #139 and #141 (open, Sep-Oct 2026): proposals for VM-based hardware testing and per-device ARM images. Activity is real (greenboot-rs releases, bootc manifests bumped weekly, F45 compose delivered), but it is a **small team** working through a bootc migration and a Konflux pipeline migration at the same time.
- Issue #123 (open): request for an "oldstable" tree. Answer from the IoT lead: "We don't have the resources for that." Practical consequence: you cannot stay one release behind to wait for third-party drivers (the commenter's example was NVIDIA).

---

## 4. The bootc transition (item 2)

### 4.1 Facts table

| Fact | Value | Status | Source |
|---|---|---|---|
| bootc project | `bootc-dev/bootc`, CNCF-hosted, 2.3k stars, v1.17.4 released 2026-11-04, weekly releases. README: "The CLI and API are considered stable. We will ensure that every existing system can be upgraded in place seamlessly." | VERIFIED | [S18] |
| What it is | OCI/Docker container image *is* the OS update: kernel in `/usr/lib/modules`, systemd as PID 1, transactional in-place upgrade and rollback (`bootc upgrade`, `bootc switch`, `bootc rollback`). rpm-ostree remains underneath for ostree-based systems; bootc is stated as the successor. | VERIFIED | [S18, S19] |
| "Own image" model | Containerfile `FROM quay.io/fedora/fedora-bootc:...` (or `centos-bootc`, `rhel-bootc`), `podman build`, push to a registry, then `bootc switch <ref>` on a device, or build a disk image with bootc-image-builder / image-builder. Fedora IoT docs show exactly this for a Raspberry Pi (after first provisioning IoT the old way). | VERIFIED | [S1] |
| Fedora base images | `quay.io/fedora/fedora-bootc` ("full" image) and `quay.io/fedora/fedora-iot` (IoT-specific, manifests in `fedora-iot/fedora-iot-bootc`). A "minimal" image (kernel + systemd + bootc only) is a dev reference, not published to Quay. | VERIFIED | [S3 #53, S19] |
| CentOS Stream | `centos-bootc` stream9; stream10 listed "in development" in the Fedora bootc docs (docs commit 2026-04-07, may be stale). Fedora bootc docs say CentOS Stream is "the upstream for the RHEL product". | VERIFIED text; current status of c10s labelling UNVERIFIED | [S19] |
| RHEL image mode | **GA**, announced 2025-05-20: supported in RHEL 9.6 and 10+; included in all RHEL subscriptions (incl. no-cost Developer subscription for the base images); bootc-image-builder "fully supported"; EUS `rhel-bootc` images extend a minor to 24 months. A package-mode host cannot be converted to image mode (reinstall required). | VERIFIED | [S26] |
| Stale text to ignore | Fedora's bootc docs still say RHEL image mode is "Tech Preview". Red Hat's blog (2025-05-20) says GA. | VERIFIED conflict | [S19, S26] |
| bootc-image-builder (BIB) | Being deprecated in favor of a unified `image-builder` CLI; BIB container stays supported for the life of RHEL 10; RHEL 9.9/10.3 rebuild BIB on image-builder; RHEL 11 ships only image-builder. Anaconda ISO image type planned for deprecation in RHEL 11 in favor of container-based installer ISOs. Repo to be archived after migration. | VERIFIED | [S20] |
| Signed images | Fedora IoT ostree deployments are GPG signed per the docs. For bootc OCI images: the 2025 proposal to officially ship fedora-bootc says "signing needs investigation" and the thread shows no final decision; I did not verify current sigstore/cosign status for `quay.io/fedora/*`. Red Hat lists "cryptographic sealing of bootc images" as Technology Preview in RHEL 10. | ostree sig VERIFIED; OCI signing UNVERIFIED; RHEL sealing TP VERIFIED | [S1, S10, S23] |
| Rollback | `bootc rollback` swaps to previous deployment; previous deployment stays on disk; auto-update timer `bootc-fetch-apply-updates.timer`. Automated health-check rollback is greenboot (not part of bootc itself). | VERIFIED | [S19] |
| Who ships it | Adopters file: Red Hat (image mode, since 2024), AlmaLinux Atomic SIG (desktop respins, 2025), CIQ "Rocky Linux from CIQ" image-based (2026), Universal Blue (Bluefin/Bazzite/Aurora), HeliumOS, ALT Atomic, Caligra, Luft; indirect via ostree: Red Hat (RHCOS, 2015), Fedora, Endless, Apertis, Playtron, Fyra Labs. | VERIFIED | [S18] |
| Maturity caveats seen in the trackers | Pi boot (above); bootupd ESP payload work still PR-stage; CoreOS tracker has 2026 open items for composefs-native backend, UKI, soft reboots, "rpm-ostree upgrade --check" regressions; rawhide bootc 1.16.11 once broke disk-image building (issue #2219). | VERIFIED | [S3, S12] |
| CoreOS/bootc unification | #2214 (2026-08-26): form a working group to unify outputs "for Fedora 46"; community meeting 2026-09-02 said it is "worth pursuing" with concerns on details. Related: FCOS built on Konflux (F44 change), FCOS updates via OCI (F42 change), Containerfile build FROM fedora-bootc (F43). | #2214 VERIFIED; others SEARCH-ONLY | [S12, S37] |

### 4.2 Read-through

- bootc is **the** direction for the whole Red Hat family, and RHEL itself has already made it the only supported "edge image" mechanism on RHEL 10. Betting on it is low-risk. Betting on **today's Fedora IoT edition's packaging of it** is medium-risk, mostly because of team size, not technology.
- The Fedora IoT edition will probably keep an ostree ISO and a bootc image side by side through F45/F46. A "own image" Containerfile pipeline works **now** for x86_64 and for aarch64 UEFI/SystemReady boards (including Orin via Red Hat's work); it is **rough for Raspberry Pi** today.

---

## 5. The enterprise longevity path (item 3)

### 5.1 Lifecycles

| Product | Dates | Status | Source |
|---|---|---|---|
| RHEL life cycle policy | "ten-year life cycle across three production phases (Full Support, Maintenance Support, Extended Life Phase) followed by optional extended support". Even minors get 6 years under Extended Life Cycle Premium (ELCP), terminal .10 release gets 9 years; Long-Life add-on renews yearly. RHEL 10 ELCP-eligible: 10.2, 10.4, 10.6, 10.8, 10.10. | VERIFIED | [S21] |
| RHEL 10 | GA 2025-05-20; Full Support to 2030-05-31; Maintenance to 2035-05-31; extended to 2039-05-31. Current minor: 10.2 (named in NVIDIA and Red Hat docs). Red Hat's page says dates are "close approximations, non definitive". | dates SECONDARY (endoflife.date); policy VERIFIED | [S16, S21] |
| RHEL 9 | GA 2022-05-18; maintenance to 2032-05-31; current minor 9.8 (May 2026). | SECONDARY | [S16, S24] |
| CentOS Stream 10 | Released 2024-12-12; EOL 2030-05-31 (about 5 years, i.e. RHEL 10's full-support window, **not** 10 years). Stream is the *upstream* of RHEL minors, not a stable base. | SECONDARY | [S16] |
| AlmaLinux 10 / Rocky Linux 10 | GA 2025-05-27 / 2025-06-11; EOL 2035-05-31 for both (clones; no vendor contract). | SECONDARY | [S16] |
| Fedora 45 | GA 2026-11-03; EOL about 2027-12-08 | SECONDARY | [S16] |
| MicroShift | Lifecycle page exists but dates are rendered client-side; I could not read them. Compatibility table (4.21 docs): MicroShift 4.21 on RHEL 9.6 (supported) and RHEL 10.0 (**Technology Preview**); 4.20 and 4.19 on RHEL 9.6; 4.18-4.16 on 9.4. | table VERIFIED; dates UNVERIFIED | [S25] |
| Red Hat Edge Manager | Pre-GA TP May 2025; GA versions exist (advisories show 1.0.3 in July 2026 and 1.2.2 in November 2026). | SEARCH-ONLY | [S26-search] |

### 5.2 The Fedora -> CentOS Stream -> RHEL "10-year" story, honestly

- The pipeline is real and documented: Fedora bootc docs say the project "tightly integrate[s] with their underlying lifecycle... CentOS Stream versions are the upstream for the RHEL product" [S19]. The same `bootc`, `greenboot`, composefs and (now) `greenboot-rs` are used in Fedora IoT and RHEL 10.2 [S2, S4, S22].
- But a **device that must live 10 years does not run Fedora or CentOS Stream**. It runs RHEL (paid) or a RHEL rebuild (Alma/Rocky, free, no vendor SLA). Fedora IoT is the upstream and the test bed.
- **Gotchas inside the RHEL 10 edge path** (VERIFIED [S22, S23]): RHEL 10 cannot build "RHEL for Edge" ostree images with image builder; image mode is the only way. Standard bootc images omit some packages an ostree commit had. Migrating RHEL for Edge 9 -> image mode needs re-building initramfs (clevis packages) and "do not share a parent image" (UID/GID drift, from the 4.21 docs). **Ignition status is contradictory in Red Hat's own docs:** the RHEL 10 considerations chapter says Ignition "is no longer fully supported... has been removed and has no replacement" for Edge image types, while the RHEL 10 image-mode guide has a whole chapter (19) on Ignition for bootc with an `ignition-edge` dracut module. I could not reconcile this. Fedora IoT ships `ignition-edge` today.
- **FDO split:** RHEL 10.2 has a *new, fully supported* Go FDO implementation (`go-fdo-client`, `go-fdo-server`) and keeps the original FDO packages as Technology Preview. Fedora IoT's `fdo-client`/`fdo-owner-cli` map to the original (Rust) implementation (INFERRED from package names + `fido-device-onboard-rs` repo). So **FDO onboarding for a OneMind fleet is not the same code on Fedora and RHEL 10.2**. Test both, or pick the Go FDO stack on RHEL-family and verify interoperability.

### 5.3 Pricing (what is public)

- Red Hat does not publish a Device Edge list price; the product page says contact sales (VERIFIED [S26]).
- Structure: socket-based subscriptions; two levels (full: RHEL + MicroShift + Red Hat Edge Manager; "Essentials" for customers with Ansible Automation Platform/other tooling) (SEARCH-ONLY).
- Reseller listings (SECONDARY, not Red Hat): CDW listed "Red Hat Device Edge, Premium, 1 year, 1 socket (up to 32 cores)" at about $270 in search results; a 3-year premium at $666 to $807. A 3-year Standard SKU was marked discontinued in July 2024. **For a 10,000-device fleet the per-socket price and any volume deal are UNVERIFIED**; assume a sales conversation.
- AlmaLinux/Rocky 10 and Fedora/CentOS Stream are free.

### 5.4 Automotive (for credibility only)

RHIVOS (Red Hat In-Vehicle OS) is built downstream of CentOS Automotive SIG's AutoSD and RHEL; Red Hat states ISO 26262 ASIL-B SEooC certification for RHIVOS on predefined hardware (first on Renesas R-Car S4), while **AutoSD itself is not certified** (SEARCH-ONLY, one SIG page opened only as a snippet [S37]). It shows the lineage can carry functional safety, but it is not something OneMind can inherit by running Fedora.

---

## 6. NVIDIA on this lineage (item 4)

### 6.1 Facts table

| Fact | Value | Status | Source |
|---|---|---|---|
| GPU Operator OS matrix (docs repo HEAD 2026-11-09; 26.7.x Supported, 26.3.x Deprecated) | Ubuntu 22.04/24.04/26.04; **RHEL 10.0, 10.1, 10.2** (K8s 1.33-1.37; RKE2); **RHEL 9.2-9.8** (K8s, RKE2, Nutanix); RHEL 8.8/8.10; **RHCOS 4.18-4.22 via OpenShift**. **Fedora and Debian: not listed.** K3s column lists Ubuntu only; RHEL is under "Kubernetes" and "RKE2". | VERIFIED | [S29] |
| GPU Operator and ARM | Supports discrete GPUs only: A100X, A30X, IGX Orin (dGPU), DGX Spark, GB200/GB300 NVL72, AWS G5g. "NVIDIA Jetson, or other embedded products with integrated GPUs, are not supported." RHEL 9 non-precompiled driver containers: **x86 only**, not ARM. | VERIFIED | [S29] |
| NVIDIA-validated Red Hat Device Edge GPU guide | x86 PCIe GPU only; **RHEL 9.x** with MicroShift 4.19-4.21 (9.6) or 4.16-4.18 (9.4); driver R580 production branch; NVIDIA Container Toolkit 1.17.9+; **NVIDIA Device Plugin** (explicitly chosen over GPU Operator); **RPM-based installs only**; supported through NVIDIA Enterprise Support + Red Hat production support. Image mode not covered. | VERIFIED | [S29] |
| CUDA repos | `fedora43/{x86_64,sbsa}` (CUDA 13.2.x), `fedora44/{x86_64,sbsa}` (CUDA 13.4/13.5), `fedora45/{x86_64,sbsa}` present, `rhel10/{x86_64,sbsa}` (CUDA 13.5.0), `rhel9/*`. `debian13/{x86_64,sbsa}` also present. | VERIFIED (directory listings, 2026-10/11) | [S30] |
| Drivers on ostree/bootc | RHEL image-mode guide, chapter 17: third-party kmods must be built **into** the image; recommended = multi-stage build compiled against the base image's kernel headers (rebuilds on every kernel bump); "copying a pre-built RPM: do not use for automated pipelines". Fedora: RPM Fusion documents `akmod-nvidia` layered with rpm-ostree + MOK signing for Secure Boot (SEARCH-ONLY, page not opened). The Fedora CoreOS WG's `fedora-bootc-nvidia` image is a proof of concept using NVIDIA DKMS, breaks Secure Boot (unsigned/self-signed), and states "There are currently no plans to take this proof of concept further." | RHEL ch.17 VERIFIED; Fedora PoC VERIFIED; RPM Fusion SEARCH-ONLY | [S11, S23, S37] |
| **Red Hat Device Edge on Jetson Orin** | **GA 2026-05-12**, aligned with RHEL 9.8: Orin Nano, Orin NX, AGX Orin; "RHEL running on the NVIDIA JetPack stack"; "a pre-built bootable container image"; bundle includes MicroShift and Red Hat Edge Manager; "Contact your Red Hat representative". Use cases named: robotics, drones, vision, industrial robots. Earlier TP blog (2024-07-18): RHEL 9.4, iGPU, X11, USB camera, NGC containers; IGX Orin too. | VERIFIED blogs | [S27] |
| How it is built | Stock RHEL aarch64 kernel (5.14.0-687.x.el9_8 in CI) + NVIDIA out-of-tree **`nvidia-jetpack-kmod`** and `nvidia-jetpack-all` userspace RPMs + `nvidia-container-toolkit` with a CDI spec. Flashing needs NVIDIA's `flash.sh` on an x86 host to put UEFI/QSPI firmware first. 2024 TP caveat: NVIDIA "is not shipping updated kmods for each kernel update", so kernel updates were excluded. GA-era policy on this is UNVERIFIED. | VERIFIED (TP doc + CI data) | [S27, S28] |
| Red Hat QE Jetson matrix | AGX Orin, RHEL 9.8, JetPack 6.2.2 (L4T 36.5.0), UEFI 36.5.2: 2 of 3 CI runs passed (Aug 2026); suites: CUDA, DLA, PVA, VIC, CSI camera, CAN, SPI/I2C, display, USB, PCIe, Ethernet. Repo HEAD (2026-11-05) adds JetPack 7.2.1 CUDA coverage and RHEL 10.2 / L4T 39 test paths, a Thor CUDA arch (`110`), and notes "On RHEL 10.2 / L4T 39, no matching NGC l4t-jetpack image is available". CUDA range on Orin Nano + JetPack 6.2.2 is **CUDA 12.x only**. | VERIFIED repo and data | [S28] |
| Jetson Thor on RHEL/Fedora | Test scaffolding exists (above). **No GA/support statement found.** NVIDIA's forum position on generic distros on Thor: bring-your-own-kernel exists but non-default combinations are not tested (search snippet). | UNVERIFIED support | [S28, S37] |
| Fedora on Orin | Fedora IoT reference list names Jetson Orin (stale list). Robinson's Dec 2023 post: JetPack 6 enables upstream kernels and non-L4T distros; RHEL 9.3+/Fedora 39+ install through UEFI; "developer preview, AKA public Beta". | VERIFIED posts | [S1, S14] |
| JetPack 7.x baseline | Ubuntu 24.04 + kernel 6.8, Orin and Thor (from earlier repo research) | VERIFIED earlier | [S38] |
| DGX | DGX OS is customized Ubuntu (earlier research). DGX Spark is in the GPU Operator ARM table. RHEL on DGX: not found. | UNVERIFIED | [S29, S38] |

### 6.2 What this means for each NVIDIA scenario

- **Jetson robotics tier:** Ubuntu/JetPack remains the zero-friction path (NVIDIA's own BSP, NGC l4t images, Isaac ROS). Red Hat's Orin offering is real and attractive for an *enterprise/industrial* customer who wants a vendor-supported OS with fleet management, but it pins you to RHEL 9.x's 5.14 kernel plus NVIDIA's kmod RPMs and CUDA 12.x, and depends on NVIDIA releasing matching kmods. Fedora's own kernel is far newer (6.x/7.x), which may help upstream-supported silicon but means NVIDIA's JetPack kmods would need to track it (UNVERIFIED).
- **x86 Pro (RTX box):** workable on RHEL 9/10 with NVIDIA's repos and the device plugin; GPU Operator is supported on RHEL 10.x. On Fedora the driver comes from RPM Fusion or NVIDIA's `fedora4x` repo, not covered by NVIDIA's operator matrix; and without an oldstable tree you must keep pace with kernel bumps.
- **Cluster/enterprise tier:** RHEL 9/10 or OpenShift/RHCOS are first-class in the GPU Operator; k3s on RHEL is workable (RKE2 is in the matrix for RHEL).

---

## 7. IIoT fit (item 5)

| Topic | Finding | Status | Source |
|---|---|---|---|
| Industrial security certification | **IEC 62443-4-2 SL-C 2** awarded by TUV Rheinland to **RHEL 9.6, OpenShift 4.20 and Red Hat build of MicroShift 4.21** (component level; Red Hat page lists identification & authentication, use control, system integrity, data confidentiality, timely response). RHEL 10 and Fedora are **not** listed. A product (device + OS + config) still needs its own assessment. | VERIFIED | [S31] |
| FIPS | RHEL 10: FIPS enabled at install via `fips=1`; image-mode guide has a chapter on enabling FIPS in a bootc image build; Fedora bootc docs have a FIPS page. Whether RHEL 10 modules hold a CMVP certificate today: not checked. | mechanism VERIFIED; validation status UNVERIFIED | [S19, S22, S23] |
| SELinux | Enforcing by default across the family; Fedora IoT includes `policycoreutils`, `setools-console`, `passt-selinux`; k3s has an SELinux policy RPM. | VERIFIED pkgs | [S2, S35] |
| Measured boot / disk encryption | Fedora IoT ships `clevis` + TPM2 pin, `tpm2-pkcs11`, `ima-evm-utils`, `usbguard`; RHEL 10.2 docs mention clevis in image-mode migration. | VERIFIED | [S2, S22] |
| Real-time kernel | **RHEL:** "Red Hat Enterprise Linux for Real Time" is a separate product with docs for RHEL 9 and 10; kernel-rt x86_64 and aarch64; **ARM64 real-time is a Technology Preview in RHEL 9.8** (4k and 64k kernels). **Fedora:** kernel-ark carries `CONFIG_PREEMPT_RT=y` in an `rt` config flavor but the spec comment says "we default realtime builds to off for fedora and on for rhel/centos/eln"; `kernel-rt` does not exist in Fedora dist-git (src.fedoraproject.org: project not found). MicroShift has a documented "Configuring low latency" chapter. PREEMPT_RT in mainline since 6.12 is background (also cited by earlier research). | VERIFIED (kernel-ark, RHEL notes); mainline claim background | [S24, S33, S34] |
| Fleet automation | Ansible Automation Platform is bundled in Device Edge (full tier). Red Hat Edge Manager (Flight Control) does declarative per-device or per-fleet OS version + config + app rollout with an on-device agent; the Fedora bootc docs include a Flight Control page, so the **fleet-manager layer works on Fedora bootc as well**. | VERIFIED docs; Edge Manager GA SEARCH-ONLY | [S19, S26] |
| Zero-touch onboarding | FDO in both (with the implementation split above). MicroShift/Device Edge and the Fedora IoT provisioner ISO give two onboarding paths. | VERIFIED | [S1, S22] |
| Use cases Red Hat names | rail anomaly detection, industrial robotics, drones, oil rigs, trains, POS (Red Hat marketing pages; no named Device Edge customers on the pages I opened) | VERIFIED text, claims not independently verified | [S26, S27] |
| Hardware floor | RHEL 10 supports x86-64-v3, ARMv8.0-A, POWER10+, z15. **x86-64-v3 means AVX2-class CPUs**; older Atoms/Celerons/Pentiums fail. N150/N300 (Gracemont) and the Beelink U55's Broadwell i3-5005U should qualify (INFERRED, check `/lib64/ld-linux-x86-64.so.2 --help` for "x86-64-v3 (supported, searched)"). | floor VERIFIED; per-CPU INFERRED | [S22] |
| MicroShift footprint | Minimum 2 CPU cores, 2 GB RAM, 10 GB disk, AArch64 or x86_64, active subscription | VERIFIED | [S25] |

---

## 8. Robotics fit (item 6) and the head-to-head

### 8.1 ROS 2 support tiers (REP 2000 / Lyrical docs)

| Distro (support window) | Ubuntu | RHEL | Debian | Fedora | Source |
|---|---|---|---|---|---|
| **Lyrical Luth** (May 2026 - May 2031, LTS) | Ubuntu 26.04: **Tier 1 amd64 + arm64** (debs + archive). Ubuntu 24.04: Tier 3 (source). | **RHEL 10: Tier 2 amd64 only** [d][a]; **no arm64** | Trixie: Tier 3 (source); EOL cut to 2028-08-09 | **Not in tier table.** Docs: RPMs "for RHEL 10 and supported Fedora releases"; copr text (2026-10-28): official Fedora packages cover **Fedora 43 x86_64** in a "ros2-testing tier"; community COPR for F44/45/CentOS Stream 10 x86_64+aarch64 is "development-only" | [S32] |
| Jazzy Jalisco (May 2024 - May 2029) | Noble Tier 1 amd64+arm64 | RHEL 9: Tier 2 amd64 only | Bookworm Tier 3 | community COPR (maintenance) | [S32] |
| Kilted Kaiju (to Nov 2026) | Noble Tier 1 | RHEL 9 Tier 2 amd64 | Bookworm Tier 3 | stale personal COPR | [S32] |

Reading: **ROS 2 binaries on an arm64 Red Hat-family host are not available from Open Robotics.** The practical pattern is ROS in a container (any userland) on any host with a working GPU/CDI path, which neutralizes the host OS for most nodes but not for host-level drivers, DDS tuning, or RT.

### 8.2 Head-to-head by OneMind tier

Legend: **++** strong, **+** fine, **0** workable with effort, **-** weak, **?** unverified. Debian/Ubuntu details come from `verify-ubuntu-vs-debian.md` and `base-os-and-orchestration.md` in this repo (already verified by prior runs); Fedora/RHEL columns from this document.

| Tier / criterion | Debian 13 + Rugix (ADR-001) | Ubuntu 24.04/26.04 (+Core, +JetPack) | Fedora IoT / fedora-bootc | RHEL image mode / Device Edge (+ Alma/Rocky/CentOS Stream bootc) |
|---|---|---|---|---|
| **Pi 5 edge** | 0: official Debian lacks Pi 5; works with Raspberry Pi's repo/kernel (Umbrel pattern) | ++: Pi 5 supported and "Certified" | 0: Pi 5B boots F44/45 (Workstation shown); IoT/bootc on Pi unproven, open bug | -: no official Pi support found for RHEL (UNVERIFIED); Alma 9.4/8.10 had Pi 5 images, Alma 10.1 booted on Pi 4, Rocky 10 Pi 4/5 with a Feb 2026 boot-failure report (SECONDARY) |
| **x86 Lite (N150/N300)** | ++ | ++ | + (x86_64 reference devices; UEFI) | + (**x86-64-v3 required**) |
| **x86 Pro (RTX, local AI)** | + (NVIDIA debian13 repo; GPU Operator not listed) | ++ (GPU Operator, NVIDIA's main target) | 0 (RPM Fusion/NVIDIA repo; no GPU Operator support; no oldstable) | ++ (GPU Operator RHEL 10.x; device plugin path validated) |
| **Jetson robotics** | - (JetPack is Ubuntu; ADR keeps L4T flavor) | ++ (JetPack 7.x Ubuntu 24.04, kernel 6.8, NGC, Isaac ROS) | 0-: listed in reference docs; Robinson's guide is a beta; no NVIDIA support | **+ (new)**: Red Hat Device Edge on Orin GA (RHEL 9.8 bootc, JetPack 6.2.2 kmods); Thor RHEL 10.2 in test only |
| **Cluster / enterprise** | + (k3s/RKE2) | + | 0 (13-month release trains) | ++ (RHEL 10 years, GPU Operator, OpenShift, RKE2 in matrix) |
| **Industrial gateways** | + (add CIP/Isar for 10-year kernels) | + (Ubuntu Core 10-15 yr with Pro) | 0 (no LTS) | ++ (SL-C 2 on RHEL 9.6/MicroShift 4.21, kernel-rt, FIPS, SELinux, 10-year) |
| **Lifecycle** | 5 yr (+ELTS to 2035 paid) | 5 yr (+Pro to 10, Legacy to 15) | **~13 months** | 10 yr (RHEL), 10 yr (Alma/Rocky, community), CentOS Stream 5 yr |
| **Atomic update + rollback** | A/B (Rugix) | A/B / snaps | ostree/bootc, `bootc rollback`, greenboot | same + EUS bootc images |
| **Auto health rollback** | DIY | DIY | **greenboot-rs** | **greenboot-rs** (RHEL 10.2) |
| **Zero-touch onboarding** | DIY | Ubuntu Core / Pro for Devices | **FDO + Ignition + provisioner ISO** | **FDO (Go, GA in 10.2)**; Ignition status unclear |
| **Fleet mgmt** | DIY / Rugix tooling | Landscape etc. | Flight Control works on bootc | Red Hat Edge Manager + AAP |
| **OCI image as the OS** | no (A/B images built by Rugix) | no | **yes** | **yes** |
| **Own-image workflow** | Rugix/debos | snaps/Ubuntu Core model | Containerfile -> bootc | Containerfile -> bootc |
| **ROS 2 (Lyrical)** | Tier 3 | **Tier 1** | not tiered; Fedora 43 x86_64 testing; containers | Tier 2 amd64 only; no arm64 |
| **Real-time kernel** | PREEMPT_RT in Debian (UNVERIFIED here) | Ubuntu Pro RT kernel (UNVERIFIED here) | no kernel-rt in Fedora | kernel-rt (RHEL for Real Time add-on), ARM64 TP in 9.8 |
| **Security certification** | none for OS; CIP precedent | Eurotech precedent (62443) | none | **62443-4-2 SL-C 2 (RHEL 9.6, MicroShift 4.21)** |
| **License cost** | free | Pro/Devices per-device | free | RHEL per-socket (Device Edge); clones free |
| **Commercial support** | none | Canonical | none (community) | Red Hat; Alma/Rocky vendors (CIQ etc.) |
| **MicroShift option** | n/a | n/a | not supported | **yes** (OneMind standard is k3s/RKE2; MicroShift is a different distro) |

### 8.3 Where the Fedora/RHEL lineage genuinely WINS

1. **Transactional health-checked updates built in:** greenboot-rs (shared Fedora/RHEL upstream, release v0.16.5 on 2026-11-04) plus bootc rollback. Debian + Rugix makes you build this.
2. **Zero-touch onboarding standard (FDO)**, shipped in Fedora IoT and in RHEL 10.2 as a fully supported implementation, plus the IoT provisioner ISO.
3. **OCI-native OS build and distribution:** the same registry, signing, scanning and CI tooling you use for app containers builds your OS. Fits OneMind's container-first model and the founder's "own image" requirement.
4. **A real 10-year path with a vendor behind it** and a **free RHEL-compatible fallback** (Alma/Rocky 10 to 2035, with CIQ already selling image-based Rocky).
5. **Industrial credibility:** 62443-4-2 SL-C 2 for RHEL 9.6/MicroShift 4.21, kernel-rt, FIPS, SELinux enforcing, TPM2 + clevis + IMA + usbguard in the IoT image.
6. **Fleet layer:** Flight Control / Red Hat Edge Manager + Ansible, usable on Fedora bootc and RHEL.
7. **GPU Operator and enterprise Kubernetes** on RHEL 9/10 and OpenShift/RHCOS; no equivalent first-class listing for Debian.
8. **A vendor-backed Jetson Orin path** (new in 2026) that Debian cannot match.

### 8.4 Where it LIMITS OneMind (the honest list)

1. Fedora IoT edition: 13-month trains, no oldstable, small team, stale hardware docs, edition-status risk, Zezere dead.
2. Pi 5: works on Fedora desktop images; **IoT/bootc on Pi is unproven and has an open boot bug**; RHEL has no Pi story.
3. ROS 2: no arm64 binaries on RHEL family; Fedora not a tier. Ubuntu is Tier 1.
4. Jetson: Red Hat Orin build pins a 5.14 kernel + NVIDIA kmods and CUDA 12.x; Thor unconfirmed; JetPack 7 is Ubuntu-based.
5. GPU Operator excludes Fedora and Jetson; NVIDIA's own Device Edge guide is **RPM-based RHEL 9.x on x86**, not image mode.
6. RHEL 10 needs x86-64-v3; image mode cannot convert from package mode; BIB is being replaced by image-builder; Ignition and FDO have two implementations/uncertain status between Fedora and RHEL.
7. RT kernel is a RHEL add-on only; ARM64 RT is TP.
8. MicroShift is not k3s and is RHEL-subscription-only.
9. Cost: RHEL Device Edge price is not public.

---

## 9. Recommendation

### 9.1 The decision

**Hybrid, bootc-first for Industrial/Enterprise/Jetson-enterprise; Debian + Rugix stays the consumer default until the gates in 9.4 pass; Fedora IoT is a supported, continuously tested profile and the upstream, not the 10-year promise.**

Why not "bootc primary now": Pi 5 + bootc is not proven, ROS 2 arm64 is weak, Fedora's cadence and team size are wrong for a consumer product with a multi-year warranty, and the GPU Operator excludes Fedora. Why not "Debian only": the founder is right that the Red Hat lineage owns the strongest IIoT and fleet story (greenboot-rs, FDO, bootc, 62443-4-2 precedent, kernel-rt, Orin GA), and RHEL 10's edge path is **only** bootc. Not building a bootc pipeline would mean OneMind cannot sell into the Red Hat world at all.

### 9.2 Proposed profiles (extends ADR-001 profile idea, additive)

| Profile | Base | Lifecycle promise | Targets |
|---|---|---|---|
| Home / Edge (default) | Debian 13 + Rugix A/B | follow Debian + own patching | Pi 5, N150 Lite |
| Pro | Debian 13 or Ubuntu 26.04 (decide by GPU test) | 5 yr | RTX box |
| Jetson | Ubuntu/JetPack (NVIDIA's) | NVIDIA cadence | Orin/Thor |
| **Industrial / Enterprise (new)** | **bootc: AlmaLinux 10 (free) or RHEL 10 image mode (paid, 62443)**; on Jetson Orin: Red Hat Device Edge | 10 yr | x86 gateways, servers, Orin (RHDE) |
| **Fedora Edition (new, community)** | `fedora-iot` / `fedora-bootc` | 13 months, rolling | dev/test, founder's lab, Pi 5/Orin experiments |

Single userland contract: every profile exposes the same host contract (cgroup v2, SELinux or AppArmor, containerd/CRI-O + CDI for GPUs, k3s, NATS leaf, update agent, RT option); apps are containers (ADR-001 D4), so apps do not care.

### 9.3 What would have to be true for Fedora IoT / bootc to be THE base

All of these, by about Fedora 46 (April-May 2027):

1. **Pi 5 + bootc boots from a clean image** (bootupd ESP-payload fix landed; no hand edits; bug #82 closed) and F45/46 Pi 5 hardware parity (sound, CM5) is acceptable for OneMind Edge.
2. A **hold-back or LTS answer**: either an oldstable tree, or OneMind accepts CentOS Stream/Alma/RHEL as the long-lived sibling.
3. **IoT team capacity**: IoT remains an Edition after F46, the Konflux pipeline lands, and per-device ARM images (spike #141) have an owner.
4. **ROS 2**: Open Robotics Fedora arm64 binaries, or OneMind containerizes all ROS (accepted).
5. **NVIDIA**: signed kmods on bootc (Secure Boot) for Fedora, or a documented RPM Fusion/NVIDIA-repo flow that survives kernel bumps, validated in CI.
6. **Support/commercial**: a customer-visible 10-year story exists *on the same bootc codebase* (RHEL/Alma), proven by building one Containerfile for both.

### 9.4 Tests to run (ordered, cheap first; hardware: Dell 5540, Beelink U55, Pi 5 16 GB, Orin Nano Super, DO droplets)

| # | Test | Pass criterion |
|---|---|---|
| 1 | `x86-64-v3` check on Dell 5540, Beelink U55 and the target N150 box (`ld.so --help`). | All "supported" or box is excluded from RHEL 10 profile |
| 2 | Build one Containerfile `FROM` fedora-bootc:45, centos-bootc:stream10 and AlmaLinux bootc 10; add k3s + k3s-selinux, greenboot checks, NATS leaf, quadlet service. `bootc switch` on a VM, upgrade, force a failed health check, confirm greenboot rolls back. | Same Containerfile works for all three; rollback in under 5 minutes |
| 3 | Fedora IoT 45 install on the Dell and Beelink from the provisioner ISO using FDO and, separately, Ignition. Then `bootc switch` to the OneMind image. | Unattended onboarding to a running node; no console |
| 4 | **Pi 5**: Fedora IoT 45 raw image (and the aarch64 bootc image via `bootc switch` after IoT provisioning); NVMe boot, Wi-Fi, USB, 24-hour soak, reboot x50, power-cut x20. | Boots with no workaround; rollback works; no data loss. Record kernel page size (4k vs 16k) |
| 5 | Pi 5 clean-image bootc path: image-builder raw + bootupd with extend-payload-to-esp build from PR #935 (or later). | Boots without manual file renames |
| 6 | **Jetson Orin Nano**: (a) JetPack 6/7 Ubuntu baseline benchmarks and CUDA/TensorRT/DeepStream samples; (b) Fedora 45 IoT via UEFI per Robinson's guide; (c) RHEL 9.8 Device Edge bootc image **only if Red Hat gives an eval** (contact `nvidia-orin-enablement@redhat.com` listed in the TP blog; GA says "contact your representative"). Compare camera, CAN, GPU container, kernel-update behavior. | A kernel update does not break the GPU; same CUDA container runs |
| 7 | **NVIDIA on x86**: RTX box on RHEL 10.x bootc (multi-stage kmod build per RHEL ch.17), on Fedora 45 bootc (NVIDIA fedora45 repo or RPM Fusion), and on Debian 13. Secure Boot on. Run device-plugin + CDI, then GPU Operator on RHEL. | Driver survives two kernel bumps in each flow with Secure Boot |
| 8 | **ROS 2 Lyrical in containers** on the RHEL-family bootc host with arm64 and the GPU: a Nav2/Isaac ROS container from an Ubuntu base; measure latency vs Ubuntu host. | Within 5% latency / no DDS issues |
| 9 | **RT**: cyclictest on RHEL for Real Time (needs subscription) vs Debian PREEMPT_RT vs Ubuntu RT, on Dell 5540, with k3s running. | 99.9th percentile latency under agreed budget (for example 200 us) |
| 10 | **Cost and procurement**: get a written Red Hat Device Edge quote (per-socket, 100/1000/10000 devices) and Edge Manager terms; ask CIQ about Rocky image-based support; check RHEL 10 + MicroShift 62443 status for 10.x. | Numbers recorded in HARDWARE.md |

### 9.5 Governance and communications for the founder

- Position Fedora IoT inside OneMind as **"the reference/upstream and community edition, our canary for the bootc pipeline"**, not as the thing customers will be asked to run for ten years. That is a strength, not a demotion: every pipeline fix lands upstream first, and RHEL customers get it a minor release later.
- Watch list (set reminders): `coreos/fedora-coreos-tracker#2214` (unification, F46), `fedora-iot/iot-distro#82` and `#141`, `coreos/bootupd#935/#959`, Fedora F45 "Atomic Unified Pipeline" change status, Flight Control/Edge Manager releases, RHDE-on-Thor announcements, ROS 2 Fedora arm64 packages, Red Hat MicroShift 4.22 compatibility table.

---

## 10. UNVERIFIED list (do not treat as fact)

1. Whether **Fedora IoT specifically** (not Workstation) boots and runs fully on **Pi 5**. Robinson's post uses Workstation; IoT not mentioned.
2. Any official **RHEL support for Raspberry Pi 5**. Not found.
3. **Jetson Thor** on RHEL 10.2 / L4T 39: support status. QE scaffolding exists; no GA statement.
4. Red Hat's **GA-era policy for NVIDIA kmods across RHEL kernel updates** on Orin (TP-era doc said NVIDIA did not ship updated kmods per kernel).
5. **MicroShift and Red Hat Edge Manager lifecycle dates** (JS-rendered lifecycle pages).
6. **Red Hat Device Edge price** (no public price; reseller figures are SECONDARY and may be stale).
7. **Ignition in RHEL 10 edge/image mode**: Red Hat's own docs conflict (removed vs documented).
8. Whether Fedora IoT's `fdo-client` is the Rust `fido-device-onboard-rs` (INFERRED) and interoperability with RHEL 10.2's Go FDO.
9. **Current signing status of `quay.io/fedora/*` bootc images** (sigstore/cosign). Only the 2025 proposal thread was read.
10. Whether **RHEL 10 / RHEL 10.x** carries a 62443-4-2 certificate (only RHEL 9.6, OpenShift 4.20, MicroShift 4.21 are listed).
11. **FIPS 140-3 CMVP validation** status for RHEL 10 modules.
12. **GA date and SUPPORT_END of Fedora 45** (Nov 3 2026 / 2027-12-08 vs 2027-11-24): SECONDARY sources disagree by two weeks.
13. **RPM Fusion/akmod flow on ostree/bootc**: only seen via search summaries, not opened.
14. **PREEMPT_RT mainline since 6.12** (background; also asserted in earlier repo research).
15. **Ubuntu RT kernel and Debian RT kernel** availability (not re-checked here).
16. k3s behavior on **bootc/image-mode** specifics (read-only `/usr`, `/var/lib/rancher`, SELinux labels) not tested.
17. Fedora's own `x86-64` baseline for the IoT image (v1 vs v2) not checked.
18. Whether **AlmaLinux/Rocky 10 on Pi 5** is stable (search snippets only; conflicting boot-failure report).
19. **RHEL on DGX / DGX Spark**: not found.
20. Red Hat **Developer subscription** terms for production use (base images "included"; commercial terms not read).
21. Fedora's current **CentOS Stream 10 bootc** label ("in development" text may be stale in docs dated 2026-04-07).
22. **Red Hat Edge Manager GA timeline** (advisory numbers seen in search only; one entry looked out of sequence).
23. **ROS 2 on Fedora aarch64** official binaries: the copr text says Fedora 43 x86_64 only as of 2026-10-28; Fedora tier table entry is absent from REP-2000.
24. **RHIVOS ASIL-B** details (search + vendor datasheet snippet).

---

## 11. Sources

All fetched 2026-11-10 unless noted. "clone" = `git clone --depth` into scratch, read locally; "curl" = fetched with plain `curl` and stripped to text.

**Fedora IoT, bootc, CoreOS**
- S1 fedora-iot/iot-docs (clone, HEAD 2026-09-30): `user-docs/modules/ROOT/pages/{reference-platforms,getting-started,index,prd,fedora-iot-bootc,fedora-iot-bootc-raspberry-pi-example,obtaining-images,physical-device-setup}.adoc`. The rendered pages at https://docs.fedoraproject.org/en-US/iot/ are Anubis-blocked.
- S2 https://github.com/fedora-iot/fedora-iot-bootc (clone, HEAD 2026-11-06): `iot-packages.yaml`, `fedora-iot-45.yaml`, `fedora-iot-bootc.yaml`, `fedora-iot-rawhide.yaml`.
- S3 https://github.com/fedora-iot/iot-distro issues #53, #82, #118, #119, #123, #139, #141 (via `gh issue view`; the project's tracker is on GitHub, not pagure).
- S4 `gh repo view`/`api`: fedora-iot/zezere (pushed 2023-09-04), fedora-iot/greenboot-rs (v0.16.5 2026-11-04), fedora-iot/fido-device-onboard-rs (pushed 2026-08-09), go-fdo (fido-device-onboard/go-fdo).
- S5 https://dl.fedoraproject.org/pub/alt/iot/45/IoT/ (directory listings, 2026-10-31 compose).
- S6 https://fedoraproject.org/wiki/Changes/Fedora_IoT_Bootable_Container (WebFetch; F40 accepted).
- S7 https://fedoraproject.org/wiki/Changes/AtomicUnifiedPipeline (WebFetch; F45 proposed, updated 2026-06-30).
- S8 https://discussion.fedoraproject.org/t/renewing-the-fedora-bootc-now-image-mode-initiative/167131 (WebFetch).
- S9 https://discussion.fedoraproject.org/t/proposal-re-consider-edition-status-for-iot/161178 (WebFetch).
- S10 https://discussion.fedoraproject.org/t/proposal-integrating-fedora-bootc-base-images-into-the-official-fedora-releases/153177 (WebFetch).
- S11 https://discussion.fedoraproject.org/t/enabling-gpus-on-fedora-with-image-mode-fedora-bootc/170247 (WebFetch).
- S12 https://github.com/coreos/fedora-coreos-tracker issues #2214 (opened 2026-08-26), #1726, bootc-related list (via `gh`).
- S13 https://nullr0ute.com/2026/10/raspberry-pi-5-on-fedora/ (WebFetch) and https://lwn.net/Articles/1103212/ (WebFetch, 2026-10-27).
- S14 https://nullr0ute.com/2023/12/any-linux-distro-on-nvidia-jetson-orin-with-jetpack-6/ (WebFetch).
- S15 https://fedoraproject.org/wiki/Fedora_Release_Life_Cycle/zh-tw (WebFetch; lifecycle sentence).
- S16 https://endoflife.date/api/{rhel,centos-stream,fedora,almalinux,rocky-linux,ubuntu,debian}.json (curl; SECONDARY aggregator).
- S17 WebSearch summaries for Fedora 45 release (Phoronix, linuxcompatible; SECONDARY/SEARCH-ONLY).
- S18 https://github.com/bootc-dev/bootc (README, ADOPTERS.md, releases via `gh api`).
- S19 https://gitlab.com/fedora/bootc/docs (clone, 2026-04-07): `base-images.adoc`, `flight-control.adoc`, `manual-rollbacks.adoc`, `fips-crypto-policies.adoc`.
- S20 https://osbuild.org/docs/bootc/deprecation-notice/ (WebFetch).

**Red Hat**
- S21 https://access.redhat.com/support/policy/updates/errata (curl; RHEL life-cycle policy text). https://access.redhat.com/support/policy/updates/microshift (curl; dates JS-rendered, unreadable).
- S22 https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/10/html-single/considerations_in_adopting_rhel_10/index (curl): Ch. 2 Architectures, Ch. 9 RHEL for Edge.
- S23 https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/10/html-single/using_image_mode_for_rhel_to_build_deploy_and_manage_operating_systems/index (curl): ch. 11 FIPS, 13 sealing (TP), 17 third-party drivers, 19 Ignition.
- S24 https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html-single/9.8_release_notes/index (curl): RT on ARM64 TP, RHEL for Edge items.
- S25 https://docs.redhat.com/en/documentation/red_hat_build_of_microshift/4.21/html/getting_ready_to_install_microshift/microshift-install-get-ready (curl): requirements and compatibility matrix.
- S26 https://www.redhat.com/en/blog/image-mode-for-red-hat-enterprise-linux-generally-available (WebFetch, 2025-05-20); https://developers.redhat.com/products/rhel-image-mode/faq (WebFetch); https://www.redhat.com/en/blog/what-image-mode-means-users-rhel-edge (WebFetch, older); https://www.redhat.com/en/technologies/linux-platforms/enterprise-linux/edge-computing (WebFetch, no pricing). Edge Manager GA and pricing items are WebSearch-only.
- S27 https://www.redhat.com/en/blog/red-hat-device-edge-now-available-run-nvidia-jetson-orin (WebFetch, 2026-05-12); https://www.redhat.com/en/blog/red-hat-device-edge-nvidia-jetson-orin-and-igx-orin-now-available-tech-preview (WebFetch, 2024-07-18); https://developers.redhat.com/learning/learn:rhel:install-red-hat-device-edge-nvidia-jetson-orin-and-igx-orin/resource/resources:jetpack-preparation-and-physical-cable-layout (WebFetch).
- S28 https://github.com/rh-ecosystem-edge/qe-rhel-jetson (clone, HEAD 2026-11-05): README, `tests_suites/README.md`, `ai-references-plans/*`, `matrix_data/ci_results.json`.
- S31 https://access.redhat.com/compliance/iec-62443-4-2 (curl).
- S34 https://docs.redhat.com/en/documentation/red_hat_enterprise_linux_for_real_time/{9,10} (curl; landing pages exist).
- S36 https://github.com/openshift/microshift (clone): `docs/user/getting_started.md`, `image_mode.md`, `docs/contributor/design.md`.

**NVIDIA**
- S29 https://github.com/NVIDIA/cloud-native-docs (clone, HEAD 2026-11-09): `gpu-operator/platform-support.rst`, `edge/nvidia-gpu-with-device-edge.rst`.
- S30 https://developer.download.nvidia.com/compute/cuda/repos/{fedora43,fedora44,fedora45,rhel9,rhel10,debian13}/... (curl directory indexes, generated 2026-10-28 to 2026-11-10).

**Robotics, kernel, k3s**
- S32 https://github.com/ros2/ros2_documentation (clone, 2026-11-10): `source/Releases/lyrical/supported-platforms.rst`, `Release-Lyrical-Luth.rst`, `Get-Started/Installation/RHEL-Install-RPMs.rst`; https://github.com/ros-infrastructure/rep (clone): `rep-2000.rst`; https://copr.fedorainfracloud.org/api_3/project/?ownername=hellaenergy&projectname=ros2 (curl; community COPR text).
- S33 https://gitlab.com/cki-project/kernel-ark (clone, 2026-11-10): `redhat/kernel.spec.template`, `redhat/configs/fedora/rt`, `redhat/configs/rhel/rt`; src.fedoraproject.org API for `kernel-rt` returned ENOPROJECT.
- S35 https://github.com/k3s-io/docs `docs/installation/requirements.md` and https://github.com/k3s-io/k3s-selinux (`gh api`).

**Search-only leads (not opened)**
- S37 WebSearch summaries: reseller pricing (CDW), RHIVOS ASIL-B (Red Hat datasheet, CentOS Automotive SIG), AlmaLinux/Rocky Pi 5, Fedora RISC-V (FOSDEM 2026, forge issues), RPM Fusion NVIDIA how-to, centos-bootc stream10, NVIDIA forum thread on Thor and generic distros.

**Repo documents used for Debian/Ubuntu/Hardware comparison**
- S38 `docs/ADR-001-foundation.md`, `docs/HARDWARE.md`, `research/platform/base-os-and-orchestration.md`, `research/platform/verify-ubuntu-vs-debian.md`, `research/platform/iiot-landscape-and-requirements.md` (earlier runs; claims quoted here are those they marked VERIFIED).
