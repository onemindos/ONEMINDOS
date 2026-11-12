# W3 runner-up steelman: Buildroot + RAUC, the Home Assistant OS way

- **Role:** runner-up steelman (RESEARCH-MISSION.md §2 rule 7). This agent was told to argue **for** the runner-up. It is advocacy held to the evidence rules: every fact below is primary-sourced and opened on 2026-11-10, or labelled SECONDARY, vendor-stated or UNVERIFIED. The honest weaknesses are in §8.
- **Date:** 2026-11-10 · **Re-check by:** 2027-05-10 (Buildroot, kernel and CI facts: 6 months); 2027-11-10 (LTS policy, adoption figures: 12 months)
- **Verdict:** `steelman`
- **Decision under test:** ADR-001 **D1/D2/D3** for W3. The ADR proposal is *Debian 13 (pinned snapshot) + Rugix A/B*. The W3 draft (`04-image-install-updates-rollback.md` V1) already swaps the update engine to RAUC, which gives *Debian 13 + RAUC*. The runner-up argued here is the **whole HAOS pattern**: a Buildroot-built appliance OS from source, plus RAUC A/B, a read-only EROFS root and verity bundles.
- **Serves requirements:** F-11, F-14, F-1, F-7, M-6, M-7, R-1, R-3, H-1, H-3, N-2, U-4, RS-2, D-001

> ### Explain it like I'm the founder
> There are two ways to make an appliance OS. **Way 1 (the ADR):** take a full general-purpose distribution (Debian), delete what you don't need, freeze it and ship it as an image. **Way 2 (Home Assistant):** start from nothing and *compile* only what the box needs (kernel, systemd, Docker or k3s, the update agent) with a tool called **Buildroot**, so the whole OS is about 250 MB and you know every line in it.
> Home Assistant has run Way 2 for eight years, on 14 board types, with what is in effect a two-person OS team, and about **578,000** opted-in households run it today. The best case for Way 2 is this: OneMind's apps live in containers anyway, so the base only has to boot, update safely and run k3s. A small base you fully control is easier to secure, easier to put through the EU Cyber Resilience Act paperwork, and has **no big Debian 13 → 14 → 15 migrations** to survive before 2036.
> The catch, covered in §8, is real. You compile everything yourself (75 to 160 minutes per board on CI), NVIDIA's container tooling isn't packaged for Buildroot, and the Jetson robot tier still has to be NVIDIA's Ubuntu either way.

---

## 1. The claim this steelman makes

> **For OneMind's core image (x86 and Pi 5/CM5 tiers), a Buildroot + RAUC appliance OS (HAOS pattern) is at least as good a ten-year foundation as Debian 13 + Rugix/RAUC, and better on four axes the scorecard weighs: production proof at constraint-matched scale (C4), security surface and CRA evidence (C3, G3), the absence of distro major-version rebases to 2036 (C1, DC-05), and the Pi-to-enterprise footprint (G5/F-14). Its robotics position is no worse than the ADR's, because both stacks put Jetson on NVIDIA's L4T Ubuntu flavor.**

## 2. Strongest arguments (each with primary evidence)

### 2.1 It's the most proven appliance stack of the three reference competitors, by a wide margin (C4, RS-2)

| Fact | Evidence (opened 2026-11-10) |
|---|---|
| Home Assistant's opt-in analytics: **727,219** active installations, of which **577,922 (79.5%) run HAOS** (`installation_types.os`). Container is 129,629, Core 7,072, Supervised 7,321. | `https://analytics.home-assistant.io/data.json`, `current.installation_types` (last_updated 1794315298662 = 2026-11-10 12:54 UTC). Opt-in, so it's a **lower bound** on the fleet. |
| HAOS boards by install count: ova 152,778 · generic-x86-64 94,605 · **green (RK3566) 78,470** · rpi4-64 78,086 · **rpi5-64 47,615** · rpi3-64 10,136 · yellow (CM4/CM5) 9,353 · generic-aarch64 6,060 · odroid-n2 4,146 | same file, `operating_system.boards` |
| HAOS has shipped on Buildroot since **release 0.1 on 2018-04-17** (repo created 2018-01-02). There are 42 non-prerelease releases on the latest API page, and the current one is 18.5. | `gh api repos/home-assistant/operating-system/releases` (pages 1–5) |
| HAOS ships **its own hardware** on this stack (Home Assistant Green, Yellow) | 14 defconfigs at `home-assistant/operating-system@fc301f5:buildroot-external/configs/` (`green_defconfig`, `yellow_defconfig`) [C-TD-home-assistant-os-003] |
| RAUC runs the **Steam Deck** (A/B, RAUC + casync/desync) | Collabora, L. de Nittis, 2024-05-10: "The actual OS images are atomic and applied using RAUC and Casync." [C-W18-044] |
| Pengutronix (RAUC maintainer) names Valve Steam Deck, **Deutsche Bahn ICE trains (Linux4ICE)** and the **IKEA Dirigera** hub as RAUC users, with "more than 100 external developers" | `https://pengutronix.de/de/blog/2025-04-22-10-years-of-rauc.html` (2025-04-22). **Vendor-stated:** counts as SECONDARY for adopters. |
| ZimaOS (an IceWhale NAS appliance) is **Buildroot + RAUC** too (a `.raucb` asset in 1.8.0, 2026-10-15) | [C-W3-047] |

**Why it matters:** the frozen rule (RESEARCH-MISSION §2 rule 2) says to copy proven competitors when their constraints match. HAOS is the constraint-matched consumer appliance: a Pi and x86 consumer box, its own hardware line, a tiny core team and a browser-first UX. By install count it's about two orders of magnitude larger than anything else in the comparison set. Debian + Rugix has one code-confirmed product (umbrelOS). **Debian + RAUC, the W3 draft's new combination, has no code-confirmed shipping appliance in the evidence base:** HAOS and ZimaOS use RAUC on Buildroot, and SteamOS uses it on Arch. So the W3 draft has already moved halfway to the HAOS pattern while giving up the part of it that is actually proven.

### 2.2 A very small team can maintain it across many boards (C5, M-6)

| Fact | Evidence |
|---|---|
| HAOS repo, 2025-11-10 → 2026-11-10: **429 commits**. Top authors: Jan Čermák **213**, dependabot 91, Stefan Agner **54**, renovate 28, then nobody over 10 | shallow clone `home-assistant/operating-system` since 2025-11-10, `git log --format=%an` (scratch measurement 2026-11-10) |
| The generic-x86-64 kernel was bumped **51 times in a year (about weekly)**: 38 by one maintainer, 7 by Renovate, 6 by a second maintainer. A typical bump PR touches 11 files | [C-W18-010] |
| Only **3 kernel patches** are carried; the kernel is upstream LTS 6.18.58 plus config fragments | [C-W18-011], [C-W18-008] |
| Buildroot base moves are routine PRs: "Bump Buildroot to 2025.02.18" (#5009, 2026-09-14), "Bump Buildroot to 2025.02.19" (#5110, 2026-10-22) | `git log -- buildroot .gitmodules` on the same clone |
| Fork branches show **four LTS-to-LTS base migrations** done in the field by OTA: `2022.02.x-haos`, `2023.02.x-haos`, `2024.02.x-haos`, `2025.02.x-haos` | `gh api repos/home-assistant/buildroot/branches` |

**Reading it:** in effect **two people** (one doing most of it, plus bots) keep 14 board images, the kernel, the Buildroot LTS line, Docker/containerd and the RAUC chain current every week for a fleet of more than 578k. This is the strongest available evidence that a from-source appliance does **not** need "a dedicated team" (C5 anchor 0). It's the closest real-world match to M-6, "give one developer guard rails".

### 2.3 No distro major-version rebases before 2036 (C1, DC-05, R-3)

- The ADR stack must cross **Debian 13 → 14 → 15** (or buy ELTS) to reach 2036 [04 §5.1]. Each crossing is a whole-userspace ABI jump, and the W3 draft makes slot sizing (10 GiB x86, 6 GiB Pi) a day-one bet on how big Debian 15 will be [W3-REC-06].
- Buildroot has **no "major release" event for the device**. Every quarterly or LTS bump rebuilds the same minimal package set from source into the same slot. HAOS has kept **256 MB system slots** for years [C-W3-023] and has crossed four Buildroot LTS lines OTA (§2.2). It even changed the root filesystem format in the field (squashfs → EROFS) through a hook [C-W3-022].
- **Buildroot LTS is now 3 years**: "Starting with version 2025.02, the LTS support has been extended to 3 years … the first release of every odd-numbered year is a long-term support (LTS) release" (`https://buildroot.org/lts.html`, opened 2026-11-10) [C-W2-035]. It's funded by a sponsorship program with "LTS stewards" and weekly vulnerability analysis, and per-branch tracking is at `security.buildroot.org` (2025.02.x, 2026.08.x and master views, generated 2026-11-10). FOSDEM 2026 talk "Longer-Term Support releases for Buildroot" (T. Perale; `archive.fosdem.org/2026/schedule/event/3XV7CP-1y-of-buildroot-lts/`).
- The path to 2036 is then a **sequence of overlapping 3-year LTS lines** (2025.02 → 2027.02 → 2029.02 → 2031.02 → 2033.02 → 2035.02, the last one supported to about 2038 under the stated policy). Each is a small, routine OTA, as HAOS's branch history shows. **Correction for the ledger:** C-W2-047 says HAOS builds on `2024.02.x-haos`. That's the stale `branch =` line in `.gitmodules`. The pinned submodule commit `home-assistant/buildroot@5c344b37` is `BR2_VERSION := 2025.02.19`, the same as the `2025.02.x-haos` tip (compare API: "identical").
- **The kernel isn't tied to the distro.** HAOS runs upstream LTS 6.18.y on x86 and Raspberry Pi's 6.18.y fork on Pi 5 [C-W18-008, C-W18-009]. A OneMind Buildroot image can follow CIP SLTS 6.12-cip (to mid-2035 [C-W2-032]) or any upstream LTS on its own schedule. Debian couples the kernel to the release.

### 2.4 Security and CRA: a smaller, fully enumerated, verity-checked base (C3, G3, U-4)

- **Read-only EROFS root, verity bundles, x.509 keyring with dev/release CA split and an in-place root rotation drill** (new P-384 root to 2046, old root cross-signed until 2028-05-14) are all already running in production [C-TD-home-assistant-os-004, -009, -012, -014; C-W3-024]. The W3 draft's signing design (§8 there) asks OneMind to build what HAOS has already run in the field.
- **The attack surface is the package list you wrote.** There's no apt, no Perl and no unneeded daemons. Every binary on the device was selected in a defconfig. This is the property the CRA's Annex I ("minimise attack surfaces", "no known exploitable vulnerabilities" at release) rewards (Regulation (EU) 2024/2847; dates per [C-W6]/07-security-compliance.md).
- **The SBOM is first-class and exact:** Buildroot ships `utils/generate-cyclonedx` (added 2025-02-22, `buildroot@dbab39e2d908`), plus `make legal-info` for licenses and source archives. Because nothing enters the image except through a package recipe, the SBOM covers 100% of what ships. A debootstrapped Debian SBOM inherits Debian's dependency closure and its CVE noise (DC-20 states this rationale).
- **The security building blocks are packaged upstream** (Buildroot master `dc55155c`): `apparmor`, `libselinux`/`refpolicy`, `tpm2-tss`/`tpm2-tools`, `cryptsetup`, `systemd` and `openssl` are all present. The Secure Boot/TPM/LUKS phase 2 (ADR D6) needs no new base.
- **RAUC itself** (also packaged upstream at **1.15.2**, `package/rauc/rauc.mk`) brings CRL, signing-time validation for wrong clocks, HSM/PKCS#11, encrypted bundles and adaptive updates [C-W3-018, C-W3-019]. These are the features the W3 draft chose RAUC for.

### 2.5 F-14, one OS from Pi to enterprise: the small end is where Debian costs most

- HAOS's whole OS slot is **256 MB**, and its kernel slot is 24 MB [C-W3-023]. The W3 draft budgets **6 GiB per Pi slot and 10 GiB per x86 slot** for Debian [W3-REC-06]. On a 32 GB SD card or eMMC CM5 that's 12 GB of A/B overhead against about 0.5 GB.
- The same `onemind.app.yaml` apps run in containers on k3s on both ends. The base never shows up in the UX, which is exactly the F-14 promise ("the user never switches products"). HAOS proves one build tree can span a Pi 3 and an x86 VM fleet (`ova` 152,778 installs).
- The large end (GPU servers, clusters) depends on k3s/RKE2 and the NVIDIA driver, not on Debian (see §3 and §8 for the driver gap).

### 2.6 F-11 IoT/IIoT: the industrial protocol stack is in-tree, and the pedigree is industrial

- Buildroot master `dc55155c` packages **open62541 1.5.10 (OPC UA)**, **mosquitto** and **paho-mqtt-c (MQTT)**, **libmodbus**, **can-utils (SocketCAN)**, **batman-adv (mesh)**, **wireguard-tools** and **tailscale**. BACnet (`bacnet-stack`) is **absent**, which is a gap but containerizable. Under the OneMind design these protocols run as apps in containers anyway (G4a), so the base only needs kernel options, which Buildroot sets per board.
- **Real time:** mainline Linux has carried PREEMPT_RT since 6.12 [C-W18-005]. Our lab enabled `CONFIG_PREEMPT_RT=y` on 6.18.62 for arm64 and x86_64 with **no out-of-tree patch** [C-W18-067]. A Buildroot image can ship an RT kernel variant as a defconfig fragment, which is the same config-fragment discipline HAOS already uses [C-W18-008]. That matches Debian's `linux-image-rt-*` packages [C-W2-033] without depending on Debian's kernel cadence.
- **Pedigree:** RAUC comes from Pengutronix, an industrial embedded consultancy. Its named field uses include Deutsche Bahn trains and hawkBit fleet back ends (`rauc-hawkbit-updater`, Pengutronix blog 2021-09-20), the zero-touch and fleet scale pieces of F-11 (vendor-stated, SECONDARY). Debian + Rugix has no comparable industrial track record in the evidence base.
- **IEC 62443:** neither stack holds a certification today. The cited certified bases are RHEL/MicroShift [C-W2-042], Moxa MIL4 on Debian [C-W8-033] and CIP [C-W8-034]. A minimal, fully enumerated Buildroot image with a defined SBOM is a *smaller* thing to bring through 62443-4-1/4-2 than a Debian userspace. **This is argued, not demonstrated.**

### 2.7 Robotics (M-7, F-2): the ADR has no advantage here

- **Both stacks put Jetson on NVIDIA's L4T Ubuntu flavor.** ADR-001 D2 does ("NVIDIA ships Jetson and DGX only on its Ubuntu-based L4T"), and so does the W3 draft V2 (NVIDIA rootfs A/B on Jetson). So the "two flavors" cost (C5/G5) is **identical** for Debian and Buildroot. Debian buys nothing on the Robotics tier.
- **ROS 2 runs in containers** on k3s under both plans (W7). Buildroot has no ROS 2 package, and none is needed on the host.
- **RK3588 and other non-NVIDIA accelerators:** Buildroot has `configs/rock5b_defconfig` (RK3588) upstream, and Batocera ships RK3588 on Buildroot (`batocera-rk3588.board`, `batocera-rk3588-mainline.board` at `batocera-linux/batocera.linux@26a53157`). HAOS already ships an RK3566 board (Green). That's the C2 anchor-5 "non-NVIDIA accelerator path".
- **Modern NVIDIA desktop drivers are proven on Buildroot in production:** Batocera ships `nvidia-open-driver` **615.71.09** plus 580/470 legacy branches as Buildroot packages (`batocera.linux@26a53157:package/batocera/gpu/nvidia-open-driver/nvidia-open-driver.mk`). Umbrel's Debian path, by contrast, uses Debian's 550 DKMS with a carried patch [C-W2-045].
- The founder's hardest robotics need is **Jetson software longevity**. Neither base fixes it. The W7 refuter shows NVIDIA BSP branches end before the module EOL (`W7-FF-1 (DC-08)-robotics.md`). The suggested bridges (RidgeRun CIP 5.10 on Xavier) are **kernel-from-source** work, the Buildroot/Yocto skill set, not Debian packaging.

### 2.8 Solo-developer path from the Mac (F-8)

- Buildroot "is designed to run on Linux systems", so on a Mac it runs in a VM [C-W18-051]. The same is true of debos, mkosi and Rugix Bakery (all Linux-host tools; [C-W18-048..050]). The project's own P0-9 already makes the toolchain a Lima Linux VM plus native CI runners [28 §P0-9], so Buildroot adds no new Mac constraint.
- HAOS's CI shows the whole pipeline is **fully automatable**: one workflow builds 14 boards in parallel, signs digests, boots the image in QEMU and bumps the dev channel (run 42901724881, 2026-11-10). That's C5 anchor 5's "AI agents can drive the whole pipeline from the CLI" in spirit. A OneMind fork of `buildroot-external` (HAOS is Apache-2.0, D-001 compatible) starts from that working pipeline rather than from scratch.

### 2.9 License fit (G1, C6, D-001)

- **HAOS's whole build tree is Apache-2.0**, which is the one competitor codebase OneMind may legally *copy*, not just study. umbrelOS is PolyForm-NC, and Olares is AGPL plus a non-commercial license (ADR-001 §1, D-001 guardrail). Buildroot (the tool, GPL-2.0) doesn't license its output. `make legal-info` gathers the license texts and corresponding source for GPL source-offer duties. RAUC is LGPL-2.1 as a separate program [C-W3-017].

## 3. Steelman re-score on the frozen S1 card (estimates; W2 owns the official S1 scores)

Strict anchors, lower anchor when in doubt. The Debian + RAUC column is this agent's reading of the same anchors for comparison only.

| Criterion | Buildroot + RAUC | Debian 13 + RAUC (W3 draft) | Why |
|---|---|---|---|
| G1 | PASS | PASS | Apache-2.0 HAOS tree; legal-info; LGPL RAUC |
| G2 | CONDITIONAL (Jetson = L4T flavor) | CONDITIONAL (same) | identical Jetson split |
| G3 | CONDITIONAL: chained 3-yr LTS lines, free; sponsorship price unpublished | CONDITIONAL/PASS: LTS 2030, paid ELTS 2035, then rebase | |
| G4 | CONDITIONAL (RT via mainline config, BACnet absent, no 62443 cert) | CONDITIONAL (no 62443 cert) | |
| G5 | CONDITIONAL (Jetson flavor) | CONDITIONAL (same) | |
| C1 (20) | **3**: documented in-place LTS-to-LTS path, demonstrated four times by HAOS | 3 | 4 needs a published price |
| C2 (20) | **2**: no NVIDIA container toolkit packaged; driver only via BR2_EXTERNAL (Batocera precedent) | 3 | **real loss** (§8) |
| C3 (15) | **4** doc-only (EROFS, verity, PKI rotation in prod) | 4 doc-only | same engine; Buildroot's surface is smaller but the anchors don't count that |
| C4 (15) | **3**, arguably 4 (HAOS + ZimaOS by code; DB/IKEA/Steam Deck RAUC vendor-stated) | **2** (no Debian + RAUC appliance found) | **real win** |
| C5 (10) | **2**: per-board CI 75–160 min (§8) | 3 | **real loss** |
| C6 (10) | 4 | 4 | |
| C7 (10) | **2**: nothing targets Buildroot natively | 3 | apps are containers, so the anchor mismeasures an appliance |
| **Total** | **57.0** (60.0 if C4 = 4) | **59.0** | inside or just outside the 3-point tie band |

**What this shows:** on the frozen anchors, Buildroot + RAUC trails Debian + RAUC by about **2 points (a tie under §3's rule)**, or 5 if Debian's C4 is scored 3. Under the tie rule, the decision goes to the decision-critical evidence (DC-20, DC-05, DC-06), where §2.1–2.3 favour the HAOS pattern. Under the C4 +5 perturbation (proof weighted higher), Buildroot + RAUC gains. Under C2 +5 or C7 +5 it loses. **The honest summary: it's a near-tie that the frozen weights break against Buildroot on NVIDIA x86 GPU packaging and ecosystem, not on safety or longevity.**

## 4. What OneMind would actually build (the runner-up made concrete)

1. Fork HAOS's Apache-2.0 `buildroot-external` structure (not its Supervisor): defconfigs per board (`generic_x86_64`, `rpi5_64`, `yellow`-style CM5, later `rock5b`), RAUC system.conf by partlabel, GRUB counter on x86, the Pi 5 tryboot backend [C-W3-029] (with the volatile-arming fix from C-TD-home-assistant-os-017).
2. Add OneMind packages as BR2_EXTERNAL recipes: **k3s** (static Apache-2.0 binary; *not* in upstream Buildroot master `dc55155c`), **nvidia-open-driver** (Batocera's recipe pattern) plus **nvidia-container-toolkit/libnvidia-container** (absent upstream, so must be written), and `nats-server` (absent).
3. Keep everything else from the W3 draft unchanged: health gate on k3s and core pods, k3s inside the slot, trial datastore copy, signed manifest with expiry, one release contract over per-board backends, NVIDIA L4T A/B on Jetson.
4. Track Buildroot LTS (2025.02.x now, 2027.02 next) with Renovate, the HAOS cadence.

## 5. New sources opened for this steelman (2026-11-10)

1. Home Assistant analytics data: `https://analytics.home-assistant.io/data.json` (installation_types, operating_system.boards)
2. Buildroot LTS policy: `https://buildroot.org/lts.html`
3. Buildroot security tracker: `https://security.buildroot.org/`
4. FOSDEM 2026, "Longer-Term Support releases for Buildroot": `https://archive.fosdem.org/2026/schedule/event/3XV7CP-1y-of-buildroot-lts/`
5. Pengutronix, "RAUC – 10 Years of Updating" (2025-04-22): `https://pengutronix.de/de/blog/2025-04-22-10-years-of-rauc.html` (vendor-stated adopters)
6. Collabora, "SteamOS 3.6: how the Steam Deck atomic updates are improving" (2024-05-10): `https://www.collabora.com/news-and-blog/news-and-events/steamos-3-6-how-the-steam-deck-atomic-updates-are-improving.html`
7. Code at pinned SHAs:
   - `home-assistant/operating-system@fc301f556647b53281e853b9ce7f44915b3c7b14:.gitmodules` (branch label `2024.02.x-haos`, stale) and submodule `home-assistant/buildroot@5c344b3789e3f6d620cf11ffab60e522a875cc79:Makefile` (`BR2_VERSION := 2025.02.19`)
   - `buildroot/buildroot@dc55155cbd8b2ca6f3344895944207014b69b969`: `package/{rauc,open62541,mosquitto,libmodbus,can-utils,tailscale,apparmor,tpm2-tss,cryptsetup,nvidia-driver}` present; `package/{k3s,nats-server,bacnet-stack,nvidia-container-toolkit,libnvidia-container}` absent; `configs/{raspberrypi5,rock5b,pc_x86_64_efi}_defconfig`; `board/nvidia/` holds only `bf3`; `package/nvidia-driver` at **390.151**
   - `buildroot/buildroot@dbab39e2d908` (CycloneDX SBOM script, 2025-02-22)
   - `batocera-linux/batocera.linux@26a5315773250e736d1e9884a190dc43c425ee2e:package/batocera/gpu/nvidia-open-driver/nvidia-open-driver.mk` (615.71.09). The repo's GitHub license is NOASSERTION, so **study only, don't copy**.
8. GitHub metadata: HAOS releases (0.1 on 2018-04-17), `home-assistant/buildroot` branches, HAOS "OS build" run 42901724881 job timings, and shallow-clone author counts for HAOS and Buildroot (Buildroot: 5,529 commits from 211 author emails in the 12 months to 2026-11-10; 598 commit subjects mention security/CVE).

## 6. Corrections this steelman found

- **C-W2-047** (and anything citing it): HAOS builds on **Buildroot 2025.02.19**, not 2024.02.x. The `.gitmodules` `branch =` line is stale, and the pinned submodule commit is authoritative.
- **Upstream Buildroot's `nvidia-driver` is the 390.151 legacy branch.** Any claim that "Buildroot packages the NVIDIA driver" needs that qualifier. A current driver requires an external recipe (Batocera precedent).

## 7. What would flip W3 toward Buildroot + RAUC

- **Lab (DC-20):** the same minimal image (kernel, systemd, containerd, k3s, RAUC) built both ways shows Buildroot with a materially lower CVE count and SBOM size, **and** an incremental rebuild (ccache/per-package dirs) under 1 h per board in our CI. That lifts C5 to 3 and makes C3's surface argument measurable.
- **Debian slot risk:** T-W3-04 shows a Debian 14 image that won't fit the chosen slot, or a rebase needing a bootloader change. DC-05 then flips, and HAOS's 256 MB slots become decisive.
- **A working BR2_EXTERNAL `nvidia-container-toolkit` + k3s device plugin on an RTX box** (spike 5 in ADR-001 §4, run on Buildroot). That lifts C2 to 3 and removes the main technical gap.
- **Evidence that no Debian + RAUC appliance ships at scale** after a dedicated search (it would confirm C4 = 2 for the W3 draft's combination).
- The founder weighting **proof (C4) and update safety above ecosystem (C7)**, a defensible reading of "use the proven competitors".

## 8. Genuine weaknesses (stated plainly)

1. **NVIDIA x86 GPU path is the biggest gap.** Upstream Buildroot has no `nvidia-container-toolkit`/`libnvidia-container`, and its `nvidia-driver` is 390.151. Batocera proves a current open driver builds, but **nobody has shown CUDA containers on k3s on a Buildroot host.** HAOS has no GPU compute story at all. NVIDIA validates Ubuntu/RHEL, not Buildroot (and not Debian for the GPU Operator either). For the Pro/Omni GPU tiers (N-8, F-2), that's original engineering for OneMind to own.
2. **You own the whole distribution.** No Debian Security Team issues DSAs for you. Buildroot LTS backports fixes, but OneMind must rebuild, test and ship every image, and under the CRA OneMind is the manufacturer for every component. HAOS manages this weekly, but only with about two dedicated maintainers. A solo founder who is *also* building the platform, dashboard and apps has less slack.
3. **Build cost is real.** HAOS CI per board is **75 min (x86) to 159 min (odroid-m1)**, about 94 min for Pi 5, with the full matrix taking about 2 h 50 min wall time (run 42901724881). That's below C5 anchor 3 (<1 h). Debian/Rugix images assemble from prebuilt packages in minutes.
4. **No package manager on the device and a thin ecosystem.** Nothing vendor-certified targets Buildroot. Debugging on the device and adding a host tool means a rebuild. Vendors such as NVIDIA, Canonical, Red Hat and ROS ship `.deb`/`.rpm`, not Buildroot recipes. The containers-only answer covers apps but not host drivers or agents.
5. **k3s and nats-server aren't in upstream Buildroot,** so OneMind maintains these recipes itself. HAOS runs Docker plus the Supervisor, not Kubernetes, so the k3s-on-Buildroot combination itself has **no production precedent** in the evidence.
6. **Buildroot LTS to 2036 is a policy, not a contract.** It's 3 years per line, funded by sponsorship with unpublished prices, and 2025.02 is the first 3-year line, so the record is less than 2 years old. Debian's LTS/ELTS has a longer funded history.
7. **The bus factor moves from Rugix to OneMind's own build tree.** HAOS's operating-system repo depends heavily on one maintainer (213/429 commits). A OneMind fork would depend even more on one person until hires arrive.
8. **The Jetson tier is unchanged:** NVIDIA L4T Ubuntu plus NVIDIA A/B. Buildroot doesn't help F-2 or the Jetson software-longevity risk. Buildroot has no Orin board support (`board/nvidia` has only BlueField-3, and searches found only 2020 TX2/Nano patch proposals). Meta-tegra (Yocto) is the from-source Jetson route, so a "from source everywhere" ambition points to **Yocto**, not Buildroot.
9. **The HAOS commit timing is not a model to copy.** HAOS marks slots good even when unhealthy [C-W3-025], and its Pi 5 tryboot arming is volatile [C-TD-home-assistant-os-017]. OneMind's health gate is needed with either base.
10. **The F-12 founder priority is unaddressed.** Buildroot is the farthest option from the Fedora IoT/bootc lineage the founder flagged. It offers no in-place BYO conversion (bootc does [C-W3-059]) and no Red Hat 62443 certificate path [C-W2-042].

**Bottom line for the orchestrator:** Buildroot + RAUC is the best-proven appliance pattern in the comparison and a defensible near-tie for the x86 and Pi tiers. It doesn't win on the frozen card because of NVIDIA GPU packaging (C2), build cost (C5) and ecosystem (C7). Its strongest practical lesson for the ADR is to **keep RAUC (as W3 V1 already does), copy HAOS's Apache-2.0 signing, PKI rotation, slot and EROFS/verity patterns directly, and size the Debian slots with the DC-05 risk in mind.**
