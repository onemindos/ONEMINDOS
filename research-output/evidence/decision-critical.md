# Decision-critical questions (could flip ADR-001)

**Selected:** 2026-11-10, before any scoring · **Count:** 24 · **Sources:** `context/05-research-questions.md` (bank IDs Q1–Q335), RESEARCH-MISSION.md §4 examples, `docs/ADR-001-foundation.md`
**Method required for each one (brief §2 rule 7 and §4):** primary sources only, at least 3 refuters with different lenses, a steelman of the runner-up, a verdict table, and a statement of what evidence would flip the decision. Results go in `24-QUESTION-BANK-ANSWERS.md` (status plus claim IDs) and feed the scorecard in `evidence/scorecard-weights.md`.
**Serves requirements:** RS-1, RS-4, R-3, M-6, M-7, F-1, F-2, F-7, F-11, F-12, F-14, N-9, A-5, A-6

> ### Explain it like I'm the founder
> ADR-001 is a proposal: Debian 13 plus Rugix A/B updates, k3s everywhere, a separate NVIDIA flavor for Jetson, and restic backups. Most of the 335 research questions refine that plan. These 24 are different: **depending on their answer, the plan itself could change.** For example, if Fedora IoT's built-in health-checked rollback (greenboot) works on a Pi 5 and Debian's free support ends too early for the boxes we sell, the base could move. So these get researched first and hardest, and each one says up front what answer would change the decision. That way nobody can move the goalposts later.

**Key to the table:**
- **Flips:** the ADR-001 decision (D1–D6) that a different answer would change.
- **Owner:** the workstream (brief §5) responsible for the answer. A second workstream in brackets supplies inputs.
- **Gate / criterion:** where the answer lands in the frozen scorecard.
- **Prior-verified** facts are taken from `context/03-repo-findings-index.md`, which records them as VERIFIED in the phase-1 reports. The owning workstream re-opens the primary source and records it as a claim ID before relying on it.

## Summary table

| DC | Bank IDs | Question (short) | Flips | Owner | Gate / criterion |
|---|---|---|---|---|---|
| DC-01 | **Q288**, Q14, Q13 | Fedora IoT / bootc vs Debian 13 + Rugix as the base, a profile, or both (F-12) | D2, D3 | W2 (W3) | G2–G5, C1–C7 |
| DC-02 | *new (F-11, brief §4)*, Q206 | Does any part of the stack block IIoT: protocols, real time, IEC 62443 path, zero-touch onboarding, 10k fleet? | D2, D3, D4 | W8 (W6) | G4 |
| DC-03 | **Q1**, Q213, Q168 | 10-year lifecycle cost to 2036 per base, per device, at 1k and 10k units | D2 | W2 (W16) | G3, C1, C6 |
| DC-04 | **Q167**, Q17, Q165, Q212 | The CRA support-period obligation versus the base's support window | D2, D6 | W6 | G3, C1 |
| DC-05 | **Q2** | Rebasing a fielded device to a new major OS without a reflash | D2, D3 | W3 | G3, C1 |
| DC-06 | **Q4** | Rugix's bus factor, maturity and exit plan | D3 | W3 | C1, C4 |
| DC-07 | **Q6**, Q47, Q144 | One update framework across x86, Pi 5 and Jetson | D2, D3 | W3 (W7) | G2, C2, C5 |
| DC-08 | **Q8**, Q45, Q179 | The Jetson BSP and module lifecycle | D2 | W7 | G2, G3, C1 |
| DC-09 | **Q7**, Q46, Q59 | Jetson flavor base: stock L4T Ubuntu vs Yocto meta-tegra vs Debian rootfs on the BSP | D2, D3 | W7 (W2) | G1, G2, C2 |
| DC-10 | **Q125**, Q19, Q44, Q18 | Is k3s justified on every tier, versus Compose/Quadlet on small nodes? | D4 | W4 | G5, C5 |
| DC-11 | **Q129**, Q136 | Backup and restore coverage, including single-node k3s on SQLite | D5 | W5 | C3 |
| DC-12 | **Q128**, Q21 | How the OS A/B layer and k3s interact on update and rollback (health-gated commit) | D3, D4 | W3 (W4) | C3 |
| DC-13 | **Q16**, Q55, Q92, Q101 | NVIDIA GPU drivers on Debian (no GPU Operator listing) and drivers on a read-only root | D2 | W4 (W2) | C2, C7 |
| DC-14 | **Q11**, Q48 | Real-time kernel needs of robotics on each board | D2, D4 | W7 (W18) | G4, C2 |
| DC-15 | **Q20**, Q42, Q43, Q56 | ROS 2 tier support on the host OS (Debian is Tier 3) | D2 | W7 | C2, C7 |
| DC-16 | **Q335**, Q254, Q86 | Which plugin extension points the base OS must expose on day one (A-5, A-6) | D1, D3 | W19 | C7 |
| DC-17 | **Q334**, Q98 | One OS, simple from a Pi 5 greenhouse to a GPU cluster (F-14) | D1, D2, D4 | W2 (W4) | G5 |
| DC-18 | **Q206**, Q207, Q208, Q209 | Can Secure Boot / TPM / verified root be added later without changing the layout now? | D3, D6 | W6 (W3) | C3 |
| DC-19 | **Q9** | The Pi 5 / CM5 pipeline on Debian (Raspberry Pi kernel/firmware, tryboot) | D2, D3 | W2 (W3) | G2, C2 |
| DC-20 | **Q3**, Q15 | A distro base vs a build-from-source appliance (Buildroot like HAOS, or Yocto) | D1, D2 | W2 (W18) | C1, C5, C3 |
| DC-21 | **Q324**, Q10 | The kernel route: stock, upstream LTS with a OneMind config, CIP SLTS, vendor BSP or patched | D2, D6 | W18 | C1, C2, C5 |
| DC-22 | **Q286** | Platform first (Core + Client + SDK) or own image first? | D1 | W18 (W4) | C5 |
| DC-23 | **Q127**, Q13 | A Kubernetes-native immutable OS (Talos, Kairos) instead of Debian + Rugix + k3s | D2, D3, D4 | W2 (W4) | C3, C5, G2 |
| DC-24 | **Q215**, Q183 | FIPS 140-3 for the public-safety tier: possible on Debian, or does it force RHEL/Ubuntu Pro/SLE? | D2, D4 | W6 | G5, C6 |

Coverage of the brief's §4 examples: Fedora IoT/bootc vs Debian + Rugix (DC-01) · plugin extension points (DC-16) · lifecycle cost to 2036 (DC-03) · rebasing without a reflash (DC-05) · Rugix bus factor (DC-06) · one update framework (DC-07) · Jetson BSP lifecycle (DC-08) · k3s vs Compose (DC-10) · backup coverage including SQLite (DC-11) · CRA support period (DC-04) · GPU drivers on Debian (DC-13) · real-time kernel (DC-14). All 12 are included.

Coverage of ADR-001: D1 (DC-16, 17, 20, 22) · D2 (DC-01, 02, 03, 04, 05, 07, 08, 09, 13, 14, 15, 17, 19, 20, 21, 23, 24) · D3 (DC-01, 02, 05, 06, 07, 09, 12, 16, 18, 19, 23) · D4 (DC-02, 10, 12, 14, 17, 23, 24) · D5 (DC-11) · D6 (DC-04, 18, 21).

---

## Detail per question

### DC-01 · Fedora IoT / bootc vs Debian 13 + Rugix (F-12)
- **Bank IDs:** Q288 (primary), Q14, Q13. **Owner:** W2, with W3 for update mechanics. **Requirements:** F-12, F-11, F-14, R-1, R-3.
- **Why it can flip ADR-001:** greenboot already implements health-checked commit with automatic rollback, which is ADR-001's claimed improvement (Q288). bootc ships the OS as an OCI image, so the same registry, signing and GitOps tooling would cover both the OS and the apps (Q14). If Fedora IoT/bootc passes G2 (Pi 5) and has a credible 2036 path through CentOS Stream → RHEL image mode, it could become the base or the Industrial track, and D2/D3 would change.
- **Prior-verified (context/03 and the Fedora deep dive):** Fedora IoT has no hold-back tree; the bug "bootc image does not boot on rpi" is open; Pi 5 boots Fedora 44/45 Workstation, but IoT/bootc on Pi 5 is unproven. The deep dive recommends bootc as a strategic Industrial/Enterprise track, not the consumer default.
- **Evidence needed:** the Fedora IoT and bootc docs and issue trackers at pinned commits (Pi 5 status, bootupd PR, greenboot behaviour); Fedora and CentOS Stream 10 lifecycle pages; the RHEL image-mode lifecycle and subscription terms; NVIDIA on Fedora/RHEL (akmods on ostree, RHEL in the GPU Operator matrix); Jetson on RHEL/Fedora; the VM lab (brief §7) with a Fedora IoT/bootc image next to Debian + Rugix doing a forced bad update and rollback; a written steelman for Fedora IoT/bootc.
- **Flip condition:** bootc/Fedora IoT passes G2 and G3 and outscores Debian + Rugix by 3 or more points robustly (scorecard §6). A weaker result (it passes the gates but doesn't win) adds it as a supported profile or track.

### DC-02 · Is there a blocking limitation for IoT/IIoT? (F-11)
- **Bank IDs:** no single bank question. Built from the brief (§4, §6 gate G4, W8). W8 adds it to `24-…` as a new question. Related: Q206 (chain of trust). **Owner:** W8, with W6 for IEC 62443. **Requirements:** F-11, F-13, AI-7, N-4, N-6.
- **Why it can flip ADR-001:** gate G4 is a must-pass. If the Debian + Rugix stack can't reach an IEC 62443-4-2 path, zero-touch onboarding (FDO, IDevID) or fleet scale of about 10k devices, while CIP Core (Isar) or RHEL image mode can, then D2 gains an Industrial track or changes outright.
- **Prior-verified (IIoT report):** "supervise, not control": hard real time belongs on PLCs, RTOS or MCUs. The NATS MQTT listener implements MQTT 3.1.1 only and rejects MQTT 5 clients. RHEL 9.6 and MicroShift 4.21 have 62443-4-2 SL-C 2 precedents. CIP Core is the best candidate for an Industrial track.
- **Evidence needed:** the IEC 62443-4-1/4-2 catalogue pages (PRIMARY-METADATA) and published vendor certificates; CIP Core and Isar docs; the FIDO Device Onboard spec and its implementations (Fedora's fdo-rs, others) on Debian; IEEE 802.1AR on the target boards' TPMs; fleet-manager limits; OPC UA (open62541) and Sparkplug B on arm64; an MQTT 5 broker decision.
- **Flip condition:** any G4 sub-check FAILs for Debian + Rugix and PASSes for an alternative.

### DC-03 · Lifecycle cost to 2036
- **Bank IDs:** Q1 (primary), Q213, Q168. **Owner:** W2, with W16 for pricing. **Requirements:** R-3, H-1, M-8, F-1.
- **Why it can flip ADR-001:** ADR-001 picked Debian partly because it's free. **Prior-verified:** Debian 13 LTS ends 2030-06-30 and Freexian ELTS (paid) runs to 2035-06-30. Ubuntu 24.04 ESM runs to May 2034 and Ubuntu Core 26 to May 2036, but the Ubuntu Pro for Devices price is unpublished. If Debian's 10-year cost (ELTS plus rebases) exceeds a paid alternative's, or if ELTS doesn't cover the packages OneMind uses, D2 changes.
- **Evidence needed:** primary lifecycle pages for every S1 candidate; Freexian ELTS pricing and package-coverage policy; Ubuntu Pro for Devices terms (or a bounded estimate labelled SECONDARY with ≥2 sources); the RHEL for Edge / Device Edge subscription; SUSE SL Micro; the CIP SLTS schedule; a cost model per device per year at 1k and 10k units through 2036.
- **Flip condition:** Debian's bounded cost to 2036 exceeds the cheapest gate-passing alternative's by more than 25%, or its G3 result is FAIL.

### DC-04 · The CRA support-period obligation
- **Bank IDs:** Q167 (primary), Q17, Q165, Q212. **Owner:** W6. **Requirements:** R-3, H-1, M-8.
- **Why it can flip ADR-001:** a box sold in late 2027 on Debian 13 needs security support well past the free LTS end (2030-06-30). If the CRA's minimum support period (Art. 13(8)) plus the box's product class (default, important Class I/II) forces a support window that only a paid or longer-lived base can meet affordably, D2 changes. The product class also decides whether a third-party conformity assessment is needed (D6).
- **Prior-verified:** CRA vulnerability reporting has applied since 2026-09-11; the main obligations apply from 2027-12-11.
- **Evidence needed:** the official text of Regulation (EU) 2024/2847 on EUR-Lex (Art. 13(8), Art. 14, Annexes I, III, IV) with its application dates; Commission implementing acts or guidance on product categories; the open-source steward provisions; how competitors declare support periods (published security policies).
- **Flip condition:** the declared period plus the box's sales window runs past the base's bounded, affordable support, with no rebase path (DC-05).

### DC-05 · Rebasing without a reflash
- **Bank IDs:** Q2. **Owner:** W3. **Requirements:** R-1, R-3, F-1.
- **Why it can flip ADR-001:** choosing a distro for 10 years really means choosing a rebase strategy. If Rugix can't move a fielded device from Debian 13 to 14 to 15 (partition-table, bootloader or slot-size changes) without a reflash, field devices are stranded, and OSTree/bootc (which rebase by design) gain a decisive edge (D2, D3).
- **Evidence needed:** code-level study of how Umbrel (1.x → 2.0), HAOS (partition-resize migrations, RAUC hooks), Proxmox 8 → 9 and TrueNAS 24 → 25 handle base jumps, at pinned SHAs; Rugix docs on slot sizes and repartitioning; bootc and rpm-ostree rebase docs; a lab spike doing an A/B update from a Debian 13 image to a Debian 14 testing image.
- **Flip condition:** Rugix needs a reflash for a major rebase, and a gate-passing alternative doesn't.

### DC-06 · Rugix's bus factor and maturity
- **Bank IDs:** Q4. **Owner:** W3. **Requirements:** R-1, R-3, M-6.
- **Why it can flip ADR-001:** D3 makes Rugix the core update mechanism on the strength of one adopter (Umbrel). The update framework is the hardest part to replace after devices ship. **Prior-verified:** Rugix v1.4.0 (2026-11-02), MIT or Apache-2.0; it doesn't mark boots good or bad by itself (the integrator must call `rugix-ctrl`); Umbrel moved from Mender to Rugix.
- **Evidence needed:** the GitHub API for rugix/rugix (contributors and commits in the last 12 months, release cadence, issue response times, the share of commits from the top contributor); the same metrics for RAUC, Mender, SWUpdate, OSTree/bootc and Kairos; public adopters other than Umbrel; the maintainer's company and funding; LICENSE files at a pinned tag; an exit plan (Rugix's RAUC/Mender compatibility boot flows).
- **Flip condition:** a single-maintainer bus factor with no second adopter, while RAUC is comparable on features (it's HAOS-proven). The likely flip is D3 → RAUC.

### DC-07 · One update framework across x86, Pi 5 and Jetson
- **Bank IDs:** Q6 (primary), Q47, Q144. **Owner:** W3, with W7 for Jetson. **Requirements:** M-6, M-7, R-1, N-2.
- **Why it can flip ADR-001:** ADR-001 leaves the Jetson A/B method open. If the robot flavor needs a different update system, the moat platform gets the weakest updates, and a sole developer maintains two or three update stacks. A framework that covers all three (for example RAUC through meta-tegra) could replace Rugix (D3) or change the flavor plan (D2). **Prior-verified:** Rugix has no Jetson or Tegra support in its repo (UNVERIFIED as a positive); Kairos supports AGX Orin, Orin NX and Thor but not Pi 5; balenaOS covers Pi 5, Orin and amd64.
- **Evidence needed:** the NVIDIA Jetson Linux developer guide (rootfs A/B, UEFI capsule update, OTA tools); OE4T meta-tegra integrations with RAUC, Mender and SWUpdate at pinned commits; Rugix boot flows; the Kairos Jetson docs; a founder-hardware test plan for an Orin Nano.
- **Flip condition:** no candidate can be one framework for all three, and a per-flavor framework costs more than switching the core framework.

### DC-08 · The Jetson BSP and module lifecycle
- **Bank IDs:** Q8 (primary), Q45, Q179. **Owner:** W7. **Requirements:** M-7, N-8, F-2, R-3.
- **Why it can flip ADR-001:** robots sold as long-term products must not be stranded on a frozen vendor kernel. **Prior-verified:** JetPack 7.x is Ubuntu 24.04 with kernel 6.8 and supports Orin and Thor; Jetson Linux 38.4 doesn't support the Orin family. If NVIDIA's per-release security support is short, and mainline Linux covers too little of Orin/Thor, the Jetson flavor needs a different base (DC-09) or a support contract, which changes D2 and the CRA math (DC-04).
- **Evidence needed:** the NVIDIA Jetson product lifecycle page (module EOL dates); the L4T release history (r35/r36/r38/r39) with security-update cadence; NVIDIA's support statements per JetPack release; the upstream kernel tree (arch/arm64/boot/dts/nvidia, the tegra drivers) against the OE4T linux-tegra diff.
- **Flip condition:** the security-update window per L4T release is shorter than the support period OneMind must declare, with no affordable bridge.

### DC-09 · Which base for the Jetson flavor
- **Bank IDs:** Q7 (primary), Q46, Q59. **Owner:** W7, with W2. **Requirements:** M-7, N-8, F-2, D-001.
- **Why it can flip ADR-001:** the L4T Ubuntu flavor inherits Ubuntu's userspace and Canonical's terms, which undercuts why Debian was chosen. A Yocto meta-tegra build or a Debian rootfs on the BSP could unify the image family (F-14) or make Yocto the cross-board system (DC-20). The NVIDIA license terms for redistributing L4T, CUDA and TensorRT in an image (G1) can also rule options in or out.
- **Evidence needed:** the JetPack 6/7 component matrix (CUDA, TensorRT, VPI, DeepStream, Isaac ROS, Holoscan) per rootfs option; OE4T meta-tegra's supported-release table; the NVIDIA Jetson software license and CUDA EULA redistribution clauses; Isaac ROS container host requirements; how robotics firms ship Jetson images (Q50).
- **Flip condition:** a non-Ubuntu Jetson rootfs keeps full JetPack capability and passes G1, which unifies the family; or stock L4T fails G1 for redistribution.

### DC-10 · Is k3s justified on every tier?
- **Bank IDs:** Q125 (primary), Q19, Q44, Q18. **Owner:** W4. **Requirements:** N-9, N-2, F-14, M-6.
- **Why it can flip ADR-001:** HAOS and Umbrel, the two most proven appliances, use Docker. N-9 says the question is still open. If k3s's idle footprint and flash-write volume are too high for a 4 GB Pi 5 or a robot, D4 becomes tiered (Compose/Quadlet on small nodes), which in turn affects the app format and F-14. **Prior-verified:** k3s's server minimum is 2 cores/2 GB; it measures about 1.6 GB with a workload (k3s v1.26.5 profile); an agent uses about 270 MB.
- **Evidence needed:** the k3s resource-profiling docs at the current version; the VM lab's measured idle and loaded footprint (brief §7 item 4), flash writes in bytes per day, and boot-to-ready time for k3s (SQLite), k0s and Podman + Quadlet running the same reference apps; Olares's k3s footprint on its minimum hardware; SUSE's k3s/RKE2 lifecycle (Q18).
- **Flip condition:** k3s on a 4 GB Pi 5 leaves less than about 2 GB for apps, or writes enough per day to threaten SD/eMMC life over 5 years, while a Compose/Quadlet node can still join the same app platform.

### DC-11 · Backup and restore coverage, including single-node SQLite
- **Bank IDs:** Q129 (primary), Q136. **Owner:** W5. **Requirements:** R-1, R-2, M-2, UX-6.
- **Why it can flip ADR-001:** D5 assumes `k3s etcd-snapshot` plus restic. **Prior-verified:** k3s's default datastore is SQLite (single server only); etcd snapshots run twice a day and keep 5; k3s rollback means a binary downgrade plus a restore from a snapshot taken on the older minor; SQLite snapshot coverage is UNVERIFIED. If SQLite isn't covered, single boxes need embedded etcd from day one (more RAM and flash wear) or another backup path, which changes D4/D5 defaults.
- **Evidence needed:** the k3s datastore and backup docs, and the source at a pinned tag (etcd-snapshot behaviour with kine/SQLite); a lab restore onto a fresh VM (brief §7 item 5) for SQLite and etcd; whether SQLite can migrate to embedded etcd in place; what HAOS, Umbrel and Olares back up, from code.
- **Flip condition:** no supported SQLite backup/restore, and no in-place migration to etcd, so the single-box default must change.

### DC-12 · How the A/B layer and k3s interact (health-gated commit)
- **Bank IDs:** Q128 (primary), Q21. **Owner:** W3, with W4. **Requirements:** R-1, R-2, AI-4.
- **Why it can flip ADR-001:** "commit only after k3s and the core pods are healthy" is ADR-001's main improvement. Rolling the OS back to a slot with an older k3s against a newer datastore could brick the cluster (k3s refuses downgrades). If this can't be made safe with k3s inside the image, D3/D4 change: k3s lives outside the A/B image, or the update model changes (for example OSTree/bootc with greenboot, or Talos).
- **Evidence needed:** k3s upgrade and downgrade docs and source; Rugix and RAUC commit hooks; how greenboot, Kairos, Talos, Flatcar and HAOS define health, from code; a lab spike doing a forced bad update with automatic rollback, gated on k3s readiness (brief §7 item 2), including the case of a rollback across a k3s minor version.
- **Flip condition:** no safe design exists for rollback across a k3s minor version with k3s in the A/B image.

### DC-13 · NVIDIA GPU drivers on Debian
- **Bank IDs:** Q16 (primary), Q55, Q92, Q101. **Owner:** W4, with W2. **Requirements:** N-8, F-2, AI-8.
- **Why it can flip ADR-001:** **Prior-verified:** the GPU Operator's OS list doesn't mention Debian; the Container Toolkit lists only Debian 11 as tested; CUDA 13.5 lists Debian 12/13; NVIDIA runs a `debian13` apt repo; Debian's own driver (550) predates RTX 50. If NVIDIA validates only Ubuntu and RHEL, the Pro and Omni tiers fight NVIDIA on every release, and N-8/F-2 push those tiers to Ubuntu or RHEL (D2). Kernel modules on a signed read-only root (DKMS) could favour bootc or sysext designs (Q101).
- **Evidence needed:** the current GPU Operator platform support page; Container Toolkit install docs; CUDA release notes; NVIDIA driver docs for nvidia-open module signing with Secure Boot; DRA driver status; a lab or cloud-GPU spike: Debian 13 + NVIDIA driver repo + toolkit + device plugin on k3s, testing time-slicing and a driver upgrade.
- **Flip condition:** a needed feature (time-slicing, MIG, CDI, DRA, Secure Boot-signed modules) fails on Debian 13 but works on a validated base.

### DC-14 · Real-time kernel needs of robotics
- **Bank IDs:** Q11 (primary), Q48. **Owner:** W7, with W18. **Requirements:** M-7, N-7, F-11, F-7.
- **Why it can flip ADR-001:** if control loops can't share a node with k3s even with PREEMPT_RT, CPU isolation and the static CPU manager, the node architecture changes (a separate MCU/RTOS, or a partitioning hypervisor), and the kernel route changes (DC-21). It also affects G4 sub-check (b).
- **Evidence needed:** the kernel.org and LWN record of PREEMPT_RT's merge into 6.12; Debian `linux-image-rt` packages for amd64 and arm64; Raspberry Pi RT kernel notes; NVIDIA's L4T RT kernel docs; ros2_control real-time requirements; a founder-runnable cyclictest test under load (QEMU timing isn't meaningful).
- **Flip condition:** an RT kernel isn't available on a target flavor (for example the Pi kernel or L4T), and the alternative base provides one.

### DC-15 · ROS 2 tier support on the host OS
- **Bank IDs:** Q20 (primary), Q42, Q43, Q56. **Owner:** W7. **Requirements:** M-7, N-7, F-3, F-4.
- **Why it can flip ADR-001:** **Prior-verified:** ROS 2 Lyrical (LTS to May 2031) is Tier 1 on Ubuntu 26.04 and Windows 11 only; Jazzy is Tier 1 on Ubuntu 24.04; Debian is not Tier 1. If running ROS 2 in Ubuntu containers on a Debian host loses something a robot needs (DDS/Zenoh discovery across pod networks, shared memory, devices, real time), or proprietary SDKs (ZED, RealSense) need an Ubuntu host, the robot tier moves to Ubuntu, which changes D2.
- **Evidence needed:** REP 2000 (the ROS 2 platform tiers) for Jazzy, Kilted and Lyrical; containerized ROS 2 docs (Isaac ROS dev containers, rmw_zenoh router needs); vendor SDK OS-support pages; how robot companies ship (Q50).
- **Flip condition:** a capability needed on the robot only works on an Ubuntu host.

### DC-16 · Plugin extension points on day one (A-5, A-6)
- **Bank IDs:** Q335 (primary), Q254, Q86. **Owner:** W19. **Requirements:** A-5, A-6, F-3, F-4, F-5, AI-3.
- **Why it can flip ADR-001:** some plugin types need OS-level hooks: device and driver adapters (kernel modules, udev rules), OS/image profiles (P-8), and desktop/shell plugins. If a read-only, image-based root can't load drivers or profiles without forking the image, D1/D3 must change (for example to system extensions like sysext, bootc layering, or a profile layer in the image design).
- **Evidence needed:** code-level study of how HAOS (add-ons, the hardware-access model), Olares (OAC and its linter), Umbrel, Omarchy, systemd-sysext and bootc layering add host-level capability; the plugin-type list in W19 mapped to the OS hooks each one needs.
- **Flip condition:** a day-one plugin type needs host changes that the ADR-001 image design can't provide without a fork.

### DC-17 · One OS from Pi to enterprise (F-14)
- **Bank IDs:** Q334 (primary), Q98. **Owner:** W2, with W4. **Requirements:** F-14, M-4, N-2, P-5, H-3.
- **Why it can flip ADR-001:** gate G5 is a must-pass. If the same image family can't serve both a 4–8 GB Pi 5 and a multi-node GPU cluster, the stack fails the founder's core promise. A base that does (balena, Talos/Omni, Red Hat Device Edge → OpenShift, Ubuntu Core → Ubuntu Pro) would win (D1, D2, D4).
- **Evidence needed:** the measured footprint on the smallest node (shared with DC-10); a documented scale-out path for each candidate, from single node to HA to GPU cluster; how competitors achieve "the same product at every scale", from their docs and code.
- **Flip condition:** G5 FAILs for the proposal and PASSes for an alternative.

### DC-18 · Adding the chain of trust later without a layout change
- **Bank IDs:** Q206 (primary), Q207, Q208, Q209. **Owner:** W6, with W3. **Requirements:** M-2, R-1, U-4.
- **Why it can flip ADR-001:** D6 puts Secure Boot and TPM in phase 2. If adding a UKI, TPM-sealed LUKS or dm-verity to a Rugix/Debian image later needs a different partition layout or bootloader, the layout has to be chosen now, and the update tool might change (D3). Pi 5 OTP secure boot and Jetson fuses are irreversible, so their compatibility with the A/B flow must be known before any box ships.
- **Evidence needed:** Rugix boot-flow docs for systemd-boot and UKI; systemd-cryptenroll TPM2 docs; Raspberry Pi secure-boot docs (rpi-eeprom signing) against tryboot; the NVIDIA Jetson secure-boot and disk-encryption guide; how Kairos Trusted Boot, bootc and HAOS lay out disks.
- **Flip condition:** retrofitting a verified boot chain needs a reflash on the proposal's layout.

### DC-19 · The Pi 5 / CM5 pipeline on Debian
- **Bank IDs:** Q9. **Owner:** W2, with W3. **Requirements:** P-8, N-2, H-3.
- **Why it can flip ADR-001:** **Prior-verified:** stock Debian 13 doesn't officially support Pi 5; Umbrel ships Pi 5 using Raspberry Pi's kernel and firmware on Debian; Raspberry Pi OS is Debian trixie. The Lite tier depends on a pipeline that is undocumented. If it relies on fragile third-party repos, G2 becomes CONDITIONAL, which shifts the score toward bases with first-class Pi 5 support (Ubuntu, which is certified).
- **Evidence needed:** Umbrel's image build at a pinned SHA (the Pi layers in its Rugix Bakery recipes); the Raspberry Pi kernel and firmware repos and their support policy; rpi-eeprom and tryboot docs; Raspberry Pi product-lifetime statements for Pi 5 and CM5.
- **Flip condition:** the Pi 5 path can't be maintained for the support period without carrying a fork.

### DC-20 · A distro base vs a build-from-source appliance
- **Bank IDs:** Q3 (primary), Q15. **Owner:** W2, with W18. **Requirements:** F-7, M-6, R-3, RS-4.
- **Why it can flip ADR-001:** HAOS (Buildroot) and most commercial embedded and robotics products (Yocto) build from source. That gives smaller images, a more complete SBOM and less CVE noise, which the CRA will reward. Yocto is the only option with BSP layers for every target board. Buildroot + RAUC (HAOS) is the mandatory runner-up steelman candidate.
- **Evidence needed:** HAOS's build at a pinned SHA; the Yocto LTS policy (Scarthgap to April 2028, Wrynose to April 2030 per context/03); the layer index for meta-tegra, meta-raspberrypi and meta-rockchip; a lab measurement of the same minimal image (kernel, systemd, containerd, k3s) built both ways: size, SBOM, CVE count, build time.
- **Flip condition:** the from-source build is maintainable by one developer (within the C5 anchors) and scores higher on C1 and C3.

### DC-21 · The kernel route (F-7)
- **Bank IDs:** Q324 (primary), Q10. **Owner:** W18. **Requirements:** F-7, F-15, R-3, M-6.
- **Why it can flip ADR-001:** the kernel is the biggest long-term cost and the source of most security fixes. If a CIP SLTS kernel or an upstream LTS with a OneMind config (the HAOS/ChromeOS approach) gives 10-year coverage that Debian's stock kernel doesn't, D2's "stock Debian kernel" premise changes, and so may the base (CIP Core/Isar).
- **Evidence needed:** the kernel.org LTS release schedule; the CIP SLTS schedule, reference hardware and membership tiers; the Debian kernel team's policy; how HAOS and ChromeOS configure and update their kernels (from code); the board-to-kernel map (mainline, CIP, vendor).
- **Flip condition:** stock Debian kernels can't cover the declared support period for the target boards, but a CIP or OneMind-configured LTS can at solo-developer cost.

### DC-22 · Platform first, or own image first?
- **Bank IDs:** Q286. **Owner:** W18, with W4 (input to `20-PLAN-180-DAYS.md`). **Requirements:** M-6, F-9, P-7, P-9.
- **Why it can flip ADR-001:** the canonical Blueprint (context/02) says to build the portable platform (Core + Client + SDK) first, then package an appliance. ADR-001 D1 says to ship our own image, including on bring-your-own hardware. If the evidence favours platform first, D1 becomes a later phase and the first 180 days change.
- **Evidence needed:** how Umbrel (Docker installer, then umbrelOS), Home Assistant (Core, then Supervised, then HAOS), Olares (script installer, no image) and Start9 (an image from day one) actually sequenced platform and image, from release history and repos; what each sequence cost them.
- **Flip condition:** proven competitors that match OneMind's constraints all went platform first, and image first measurably delays the first usable release.

### DC-23 · A Kubernetes-native immutable OS (Talos, Kairos)
- **Bank IDs:** Q127 (primary), Q13. **Owner:** W2, with W4. **Requirements:** R-1, M-6, N-9.
- **Why it can flip ADR-001:** Talos has A/B updates and Kubernetes built in, and an API instead of a shell, which removes the OS-versus-k3s interaction problem (DC-12). **Prior-verified:** Talos v1.14.5 (MPL-2.0; Omni is BSL 1.1) has SBC overlays for Pi 4/CM4, Pi 5 and Jetson Nano only, and Orin support is an unmerged PR; Kairos v4.4.0 (Apache-2.0) doesn't support Pi 5 and commits after cloud-init.
- **Evidence needed:** current Talos and Kairos support matrices and release notes; the status of the Talos Orin PR; how host-level services (NATS leaf, Tailscale, mesh radios) run on each; Omni and Kairos licensing for a fleet plane; production adopters.
- **Flip condition:** one of them passes G2 (Pi 5 and Jetson Orin) and G5 and outscores the proposal.

### DC-24 · FIPS 140-3 for the public-safety tier
- **Bank IDs:** Q215 (primary), Q183. **Owner:** W6. **Requirements:** P-5, M-4, H-3, F-14.
- **Why it can flip ADR-001:** D4 names RKE2 for the hardened tier and cites FIPS 140-2. **Prior-verified:** RKE2 has FIPS 140-2 builds (BoringCrypto). The question bank (Q183) says FIPS 140-2 sunsets in 2026; that is **UNVERIFIED** until W6 opens the NIST CMVP notice. If a FIPS/CJIS-capable tier needs a validated module that only exists on Ubuntu Pro, RHEL or SLE, the hardened tier needs a different base. That breaks "one OS" (G5) unless the main base changes too.
- **Evidence needed:** the NIST CMVP validated-modules search (the current certificates for BoringCrypto, Ubuntu Pro FIPS, the RHEL and SLE modules, and any Debian-usable module); the CMVP 140-2 sunset notice; RKE2 FIPS docs; the CJIS Security Policy's encryption section (official text).
- **Flip condition:** no validated module can run on a Debian base, and the public-safety tier is kept in scope.

---

## Questions considered and not selected (why)

| Bank IDs | Topic | Why not decision-critical |
|---|---|---|
| Q84–Q102 (except Q101) | AI capability layer, MCP, agents | These shape layers above the OS. They don't change the base, the update framework or the runtime. Q101's driver and model-store point is folded into DC-13. |
| Q133, Q134, Q249 | App package format, GitOps alongside the Market | They depend on D4 (DC-10). The format is a W12/W19 decision on top of whichever runtime wins. |
| Q135, Q137, Q138, Q139 | Storage, networking, mesh, NATS topology | These are choices inside the Kubernetes platform. They don't flip it. |
| Q165–Q187 (except Q167, Q168, Q183) | Certification, BOM, tariffs, ODMs, market | These affect the hardware line and go-to-market, not the software foundation. Q167 and Q168 are in DC-03/DC-04, and Q183 is in DC-24. |
| Q49–Q54, Q57–Q58 | Robot middleware, drones, safety standards, Ubuntu Core for robots | Robot-plan questions (P1). Q57's Ubuntu Core comparison is scored under S1, and Q58's power-loss realities are covered by the lab spikes in DC-12. |
| Q325 | Non-Linux kernels | Phase-1 evidence and the driver, NVIDIA and Kubernetes ecosystems make a non-Linux route very unlikely to win. W18 still answers it, with sources. If W18 finds a credible non-Linux path, it is promoted here and logged. |

## Change log

| Date | Change | Reason | By |
|---|---|---|---|
| 2026-11-10 | Initial selection: 24 questions | Brief §4; selected before any scoring | FRAME agent |

## Glossary

- **ADR-001:** the architecture decision record proposing the foundation (Debian 13 + Rugix + k3s/RKE2 + L4T flavor). Status: proposed, not approved.
- **Flip:** a research answer that changes one of ADR-001's decisions D1–D6.
- **Refuter:** an independent agent told to disprove a conclusion, given only the claim and its sources.
- **Steelman:** the strongest honest case for the runner-up option.
- **greenboot:** the Fedora/RHEL tool that runs health checks after an update and rolls back automatically if they fail.
- **bootc:** a tool that ships and updates the whole OS as a container (OCI) image.
- **BSP (board support package):** the vendor's kernel, drivers and firmware for a specific board, such as NVIDIA's Linux for Tegra (L4T) for Jetson.
- **CIP SLTS:** the Civil Infrastructure Platform's super-long-term-support kernels (about 10 years), aimed at industrial devices.
- **FDO:** FIDO Device Onboard, a standard for zero-touch device onboarding.
- **FIPS 140-3:** the US standard for validated cryptographic modules, required by many government buyers.
- **REP 2000:** the ROS document that lists which operating systems each ROS 2 release supports, and at which tier.
