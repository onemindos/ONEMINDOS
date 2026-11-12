# CIT4: citation repair for critic pass-3 gaps P3-4 and P3-12

**Date:** 2026-11-11 · **Scope:** every claim ID cited in `01-FOUNDATION-DECISION.md` (rev. 3) whose ledger row is not `PRIMARY` or not `verified`, plus the re-check windows in P3-12. **New rows:** `evidence/claims/CIT4.csv` (C-CIT4-001…017). **Sources:** `evidence/sources/CIT4.md`. This file does not edit 01. It lists the exact wording 01 should use.

> **Explain it like I'm the founder.** Every fact in the decision document points to a row in the claims ledger, and each row says how good its source is. A **PRIMARY** source is the vendor's own documentation, code, data or a measured paper. A **SECONDARY** source is someone else reporting on it: a forum post, a news article, a blog. The critic counted 64 non-PRIMARY and 15 non-verified rows in 01 (74 distinct rows in all) that were not primary or not fully verified. For each one this file either found a primary source and wrote a new row, or wrote the label 01 should show, so you can see what a sentence rests on. Most of these rows are **failure reports**: a user on a forum saying "this broke for me". Failure reports are SECONDARY by nature. They are still useful, because a vendor rarely documents its own failures, but they show that something *can* happen, not how often. Two findings change wording in 01: a Debian + RAUC appliance OS **does** now exist (pre-1.0), and NVIDIA calls its Jetson real-time kernel "Developer-Preview quality".

## 1. Result in numbers

The scan found **558 distinct claim IDs** in 01. Seven are false positives: they are adversarial file names such as `W19-C-W19-011-028-technical.md`, not citations. **74 rows** are not PRIMARY or not verified (pass 3 counted 64 non-PRIMARY and 15 non-verified; some rows are both).

| Outcome | Rows |
|---|---|
| Fully superseded by a new primary row, old row marked `superseded` in its own fragment | 3: C-W18-027 → C-CIT4-003, C-STEEL-ubu-011 → C-CIT4-012, C-REF3-DC-technical-020 → C-CIT4-016 |
| Partly superseded: the primary row covers the fact 01 relies on, and the rest stays labelled (old row left as is) | 8: C-DEC-013, C-DEC-014, C-REF3-DC-cost-001, C-REF3-DC-cost-002, C-REF-W8-longevity-009, C-REF-W19-security-002, C-REF3-DC-technical-024, C-STEEL-cra-nb-017 (context only) |
| Complemented by new primary evidence, still needed as a failure report (DC-14 real time) | 4: C-REF-DC-robotics-005/006, C-REF-DC-technical-001/002 |
| Should be re-typed PRIMARY (first-party statement already ledgered as SECONDARY) | 2: C-W3-016, C-REF-W3-longevity-007 |
| PRIMARY-METADATA that is the right type (package indexes, GitHub metadata) | 11 |
| PRIMARY but `partial` by design (desk test, legal interpretation, doc caveat) | 4 |
| Conclusions ledgered as PRIMARY facts | 3: C-W19-047…049 (§5) |
| Already `superseded`, still cited | 1: C-W7-005 |
| SECONDARY failure reports, press, vendor-staff forum posts or research blogs with no primary equivalent: keep, label | 38 |

**No scorecard cell or tie-break verdict changes** as a result of this pass. One tie-break row (S1 "Proven competitor", S2 "Debian precedent") keeps its verdict but its wording becomes false and must change (§2.1).

**Proposed §9 statement for 01** (replaces "every claim resolves to a PRIMARY row"):

> **Definition of done, citations: met with listed exceptions.** Every claim ID in this file resolves to a row in `evidence/claims/`. As of 2026-11-11, the rows that are not PRIMARY, or not verified, are listed in [`evidence/critic/cit4-mapping.md`](evidence/critic/cit4-mapping.md) with their role. They are failure reports (forum posts, incident write-ups) that support a risk or a refuter's counter-argument, not a scorecard cell; package-index and repository metadata (PRIMARY-METADATA); two negative-search or blocked results (C-DEC-013, C-STEEL-cra-nb-017); and three DC-16 conclusions that are derived, not sourced (C-W19-047…049). No scorecard cell rests only on a SECONDARY or UNVERIFIED row.

## 2. Load-bearing rows (named by the critic)

### 2.1 C-DEC-013: "no Debian or Ubuntu + RAUC product" (S1 and S2 tie-break rows)

**What changed.** A search with GitHub code search found **IronFlockOS** (IronFlock GmbH, Apache-2.0): "a Debian-based appliance OS" whose updates RAUC writes into "the inactive one of two slots", with targets for x86 and arm64 UEFI, Raspberry Pi 4/5 (firmware tryboot) and Jetson Orin (Ubuntu 24.04 + `nvbootctrl`, in progress) [C-CIT4-001]. It runs Docker, not Kubernetes. It is **pre-1.0**: "No target has passed its hardware acceptance yet". Six releases (v0.10.0 to v0.15.0) were published in the six days before access, and it installs Debian's own RAUC 1.13 package [C-CIT4-002].

**Role.** C-DEC-013 is a negative-search result (UNVERIFIED by nature: you cannot cite the absence of something). The tie-break rows use it as "precedent for the combination".

**Does the verdict change?** No. IronFlockOS is a design precedent, not a production one, so:
- S1 "Proven competitor" row still favours **A** on the base layer (umbrelOS), and nobody ships the full Debian + RAUC + k3s stack.
- S2 "Debian precedent" row still goes to **Mender** (umbrelOS shipped Mender on Debian in the field [C-W3-040]); a pre-1.0 Docker appliance does not outweigh that.

What does change: the sentence "no Debian + RAUC product exists" is now false as written. It is also worth noting for D2/D3 that IronFlockOS made the same flavor split OneMind made (Debian on x86 and Pi, Ubuntu 24.04 on Jetson) and the same engine choice.

**Exact text for 01:**
- L29 (finding 13): "**Nobody ships exactly our combination in production.** We found no field-proven product running Debian or Ubuntu with RAUC, and none with Kubernetes on top [C-DEC-013, UNVERIFIED: negative search]. The closest is IronFlockOS, a pre-1.0 open-source industrial OS on Debian 13 + RAUC + Docker that has not yet passed hardware acceptance [C-CIT4-001, C-CIT4-002]. Each piece is proven somewhere (…)" (rest unchanged).
- L209 (A cell): "…but on **Rugix**, not RAUC. No field-proven Debian + RAUC product; one pre-1.0 project (IronFlockOS, Docker, no hardware acceptance yet) [C-DEC-013 (UNVERIFIED: negative search), C-CIT4-001]".
- L265: "no field-proven product runs Debian or Ubuntu with RAUC [C-DEC-013, UNVERIFIED: negative search]; the only public Debian 13 + RAUC appliance OS found, IronFlockOS, is pre-1.0 [C-CIT4-001]; umbrelOS, the constraint-matched Debian appliance, shipped on Mender (…)".
- L796 (R3-5) and L860 (§9.1 answer): replace "None was found" with "No field-proven one was found. One pre-1.0 public project exists: IronFlockOS (Debian 13 + RAUC + Docker; Pi 4/5 and x86 images; Jetson on Ubuntu 24.04 in progress; no target past hardware acceptance on 2026-11-11) [C-CIT4-001, C-CIT4-002]. Watch it as the nearest precedent: if it reaches 1.0 on hardware, the S2 'Debian precedent' row should be re-scored."

### 2.2 C-W18-027: CUDA 13.5 on Debian 13 (S5 K1·C7 cell, K5 gate)

**Superseded** by C-CIT4-003 (row status set to `superseded` in `W18.csv`). The CUDA 13.5 guide lists Debian 13 for x86_64 and arm64 SBSA servers; its only Jetson rows are Ubuntu 24.04 (JetPack 7.2), and Jetson cross-development is Ubuntu 24.04 only. **Cell change: none.** K1 includes the NVIDIA L4T kernel, and CUDA is supported there, so C7 = 4 stands; K5 still fails G2–G5. **Text for 01:** replace `[C-W18-027]` with `[C-CIT4-003]` on L311, L315 and L545; L951's follow-up item ("28 and C-W18-027 should say that CUDA's Debian 13 support excludes Jetson") is done in the ledger, and 28 should cite C-CIT4-003.

### 2.3 Real-time latency rows (DC-14): C-REF-DC-robotics-005/006, C-REF-DC-technical-001/002

**Search result.** OSADL's QA Farm is the reference for long-term PREEMPT_RT data. Its only Pi 5 runs a **non-RT** Raspberry Pi kernel (6.12.109, `SMP PREEMPT`), and it has no Jetson [C-CIT4-005]. NVIDIA publishes no latency figures and calls its Jetson RT kernel **"Developer-Preview quality"**, adding that UEFI runtime services "may increase latency" [C-CIT4-006]. The only primary measurement found for Pi 5 is a peer-reviewed workshop paper: PREEMPT_RT 6.6.21 under extreme stress for 1 hour gave a **124 µs** maximum, against 36,802 µs for the stock kernel [C-CIT4-004]. An integrator blog (SECONDARY) measured Jetson AGX Orin on JetPack 6.2 at 6–15 µs with CPU isolation and 113–159 µs without [C-CIT4-007].

**Role of the four forum rows.** They are failure reports: what can go wrong (a >1 ms overnight spike on a 6.13-rc RT kernel; two identical Orin modules at ~10 vs 90+ µs). Nothing primary contradicts them: the 1-hour paper on an older kernel cannot rule out a rare overnight spike. They carry no scorecard cell. They justify the per-unit acceptance test, and that design does not change.

**Exact text for 01, L443:**
> **Real time (rev. 2, DC-14; citations revised by CIT4):** an RT kernel exists on every flavor, but no board vendor publishes a worst-case latency, and NVIDIA ships its Jetson RT kernel at "Developer-Preview quality" [C-CIT4-006]. On the Pi 5, the one peer-reviewed measurement found (PREEMPT_RT 6.6.21, 1 h, extreme stress) peaked at 124 µs [C-CIT4-004], while community reports on 6.13-rc RT kernels saw spikes over 1 ms overnight under memory stress [C-REF-DC-technical-001, SECONDARY: forum report]. On Jetson, two identical Orin modules differed by about 10 µs vs 90+ µs with full CPU isolation, which NVIDIA staff called "not expected" [C-REF-DC-technical-002, SECONDARY: forum report]; an integrator measured 6–15 µs with isolation and over 100 µs without [C-CIT4-007, SECONDARY]. OSADL's long-term latency farm has no PREEMPT_RT Pi 5 or Jetson [C-CIT4-005], so no independent long-run figure exists for either board. So the RT profile ships with a **per-unit acceptance test** (…)

L602–L603 (refuter rows): append "(SECONDARY: forum reports; primary context C-CIT4-004…006)". The DC-14 technical flip condition ("a supported Pi 5 RT kernel elsewhere under 100 µs while Raspberry Pi's stays above 500 µs") is **not met** by C-CIT4-004: 124 µs is above 100 µs, on a hand-patched kernel that is not a supported product.

### 2.4 C-REF3-DC-cost-001 / -002: Pi 5 and Jetson price rises (DC-17, §4.5)

Partly superseded. Raspberry Pi's own post confirms the 16 GB Pi 5 at **$385 (+$80)** and 16 GB CM5 variants **+$40** from 2026-11-02 [C-CIT4-008]. NVIDIA's FAQ gives today's list prices: Orin Nano Super devkit **$399**, AGX Orin devkit **$3,499**, AGX Thor devkit **$5,499**, AGX Orin 32 GB module **$1,799** [C-CIT4-009]. With NVIDIA's $249 launch price for the Orin Nano Super [C-W10-025], the +60% on that kit is primary-sourced. The "up to 101%" figure and the earlier Pi steps stay press-only. Note that Raspberry Pi's product page still showed "$305" for the 16 GB model on the same day, and no official source gave the 4 GB / 8 GB prices that matter for the entry SKU.

**Exact text for 01, L418:** "**Entry SKU price check (rev. 3, DC-17 cost refuter):** 2026 memory-driven price rises (Raspberry Pi: 16 GB Pi 5 to $385 [C-CIT4-008]; NVIDIA list prices now $399 for the Orin Nano Super kit that launched at $249 and $3,499 for the AGX Orin kit [C-CIT4-009, C-W10-025]; rises of up to 101% on other Jetson SKUs per press [C-REF3-DC-cost-002, SECONDARY: press]) make the fixed ~1 GiB k3s overhead dearer. (…)" The DC-17 cost refuter row (L627) keeps its SECONDARY IDs and should add C-CIT4-008/009.

### 2.5 C-STEEL-cra-nb-017: CRA notified bodies in NANDO (§4.7)

**No primary source reachable.** NANDO is a single-page app, and a scripted query of its back end was refused by this environment's access policy, so it was not tried again. The Commission's CRA page (last updated 2026-07-31) only says NANDO will list CRA bodies "once available" [C-CIT4-010, partial]. Text for 01, L444: "…no CRA notified body could be confirmed in NANDO (the count could not be read: UNVERIFIED, blocked) [C-STEEL-cra-nb-017]; the Commission's page still said CRA listings would appear 'once available' on 2026-07-31 [C-CIT4-010]." Founder action: open NANDO → Notified bodies → by legislation → Regulation (EU) 2024/2847 in a browser and record the count in `22-…`.

### 2.6 C-REF-W8-longevity-009: EN IEC 62443-4-2 draft amendment (refuter table L585)

Partly superseded. CEN-CENELEC's own page confirms a draft amendment "EN IEC 62443-4-2: prAA" exists and is being positioned for the CRA [C-CIT4-011]. Its content ("updated and new requirements and an evaluation methodology") is still from a search snippet. Text for 01: "a 62443-4-2 amendment (prAA) is in draft [C-CIT4-011; content per C-REF-W8-longevity-009, UNVERIFIED: catalogue snippet]".

### 2.7 C-STEEL-ubu-011, C-DEC-014, C-REF-W19-security-002, C-REF3-DC-technical-020/-024

| Old row | New row | What moves to primary | What stays as it was | 01 text |
|---|---|---|---|---|
| C-STEEL-ubu-011 (PRIMARY, partial, search extract) | **C-CIT4-012** (superseded) | Bosch press release 2025-03-18: ctrlX OS "certified according to IEC 62443-4-2 Security Level 2 by TÜV Rheinland" | The certificate itself and its version scope ("3.6 LTS" in the old row) are not seen | Replace the ID on L152, L702, L853; add "(vendor statement; certificate not seen)" |
| C-DEC-014 (SonarSource) | C-CIT4-013 | CVE-2023-37265/37266, CVSS 9.8, fixed in 0.4.4 (vendor-repo advisories) | "Public exploits 10 days after the release" (SonarSource, SECONDARY) | Cite both: `[C-CIT4-013, C-DEC-014]` |
| C-REF-W19-security-002 (Wiz) | C-CIT4-014 | CVE-2025-23266, CVSS 9.0; affected toolkit < 1.17.8, GPU Operator < 25.3.2 (GitHub-reviewed advisory, PRIMARY-METADATA) | The LD_PRELOAD mechanism (Wiz, SECONDARY); NVIDIA's bulletin returned HTTP 429 | Cite both on L459 |
| C-REF3-DC-technical-020 (forum) | **C-CIT4-016** (superseded) | NVIDIA's debian13 repo offers branches 590–620, **still no 580 or 570** | — | Replace the ID on L445 and say "590 and newer branches only" |
| C-REF3-DC-technical-024 (vendor-staff forum) | C-CIT4-015 | Raspberry Pi OS trixie installs kernel 6.18.60 on Pi 5; `raspberrypi/linux` default branch is `rpi-6.18.y` | "The only recommended way to upgrade to trixie is a reinstall" (staff forum post) | Cite both on L200 |

## 3. Every other non-PRIMARY or non-verified row in 01

**Role** says what the row does in 01. **Cell?** says whether a scorecard cell or tie-break verdict depends on it alone. **Label** is the text 01 should add after the ID. "Refuter" means the row is a counter-argument quoted in a §5 adversarial table, recorded as the refuter cited it.

### 3.1 SECONDARY failure reports, press and blogs (no primary equivalent found or expected)

| Claim | Role | Where in 01 | Cell? | Label for 01 |
|---|---|---|---|---|
| C-REF-DC-cost-004 | Failure report (OTA bricked an AGX Xavier Industrial) | §4.2 L368; refuter L597 | No | SECONDARY: forum report |
| C-REF-DC-cost-005 | Vendor-staff statement: rootfs A/B cannot be enabled by OTA | Answer table L61; §4.1 L358; refuter L597 | No cell; it is the **only** source for "flash every Jetson A/B at the factory". NVIDIA's r36.4.3 guide neither confirms nor refutes it [C-CIT4-017] | SECONDARY: NVIDIA staff on forum; the developer guide is silent [C-CIT4-017] |
| C-REF-DC-cost-007 | Vendor-staff statement on L4T rootfs redistribution | Finding L23; answer L57; S1 G1 row L195; §4.1; refuter; ADR table L758 | Narrows the G1 A cell for Jetson SKUs only; G1 still favours A ≈ C > D for the core image | SECONDARY: NVIDIA staff on forum. Founder/counsel should confirm against the Jetson software licence (already in `license-matrix.csv`) |
| C-REF-DC-cost-008 | Vendor non-answer | Refuter L598 | No | SECONDARY: forum |
| C-REF-DC-cost-010 | Failure report (DKMS build on a Proxmox kernel) | Refuter L600 | No | SECONDARY: forum report |
| C-REF-DC-robotics-002 | Vendor-staff non-answer on a CVE fix package | Refuter L596 | No | SECONDARY: forum |
| C-REF-DC-robotics-009 | Vendor-staff statement: bookworm legacy gets security fixes | S1 DC-03 rev-2 row L197 (no ranking) and DC-19 A cell L200; §4.1 L363; refuter | One of five points in the DC-19 A cell; not the sole basis | SECONDARY: Raspberry Pi engineer on forum |
| C-REF-DC-technical-004 | Failure report (Isaac ROS container after OTA) | §4.7 L442; refuter | No | SECONDARY: forum report |
| C-REF-DC-technical-005 | Failure report (containerd GPU on Orin) | Corrections log L151; refuter | No | SECONDARY: forum report |
| C-REF-W18-robotics-004 | Press (Fuchsia team cuts) | Refuter L550 | No | SECONDARY: press |
| C-REF-W19-cost-007 | Press (Snap Store scam snaps) | §4.8 L466; refuter | No | SECONDARY: press |
| C-REF-W19-longevity-006 | Security vendor blog (partial) | Refuter L674 | No | SECONDARY, partial: security vendor blog |
| C-REF-W19-security-009, -010 | Press reporting security research | §4.8 L466 | No | SECONDARY: press |
| C-REF-W19-security-011 | Security vendor blog | §4.8 L466 | No | SECONDARY: security vendor blog |
| C-REF-W19-technical-007, -008 | Press (VS Code Marketplace incidents) | §4.8 L466; refuter L648 | No | SECONDARY: press |
| C-REF-W19-technical-009 | Forum: no NVIDIA module-signing guide (partial, low) | §4.8 L461; refuter L651 | No; it is an absence-of-documentation finding | SECONDARY, partial: forum; no NVIDIA guide found |
| C-REF-W2-robotics-008 | Failure report (Fedora on Orin, 2023) | Refuter L496 | No | SECONDARY: forum report (2023) |
| C-REF-W3-longevity-009 | Failure report (Orin NX OTA) | Refuter L510 | No | SECONDARY: forum report |
| C-REF-W6-technical-003 | Jetson partner guide (Xavier tops out at JetPack 5.1.5) | §4.7 L446; refuter L561 | No | SECONDARY: NVIDIA partner |
| C-REF-W6-technical-007 | Standards tracker blog (CRA harmonised standards status) | §4.7 L446 | No | SECONDARY: tracker; re-check against CEN-CENELEC after the mid-November 2026 vote |
| C-REF-W7-T-006 | Security researcher advisory (Jetson Secure Boot bypass) | Refuter L570 | No | SECONDARY: researcher advisory (NVIDIA bulletin not opened) |
| C-REF3-DC-longevity-006 | Wikipedia (RealSense ownership) | §4.7 L442 | No | SECONDARY: encyclopedia; weakest source in 01 |
| C-REF3-DC-longevity-008, -009 | LWN reporting (Secure Boot CA expiry) | §4.3 L395; refuter L629 | No | SECONDARY: LWN |
| C-REF3-DC-security-009 | Security research blog (TPM2 unlock attack) | §4.3 L394; refuter L630 | No | SECONDARY: research blog |
| C-REF3-DC-technical-001, -002 | Failure reports (Jetson A/B no fallback, vendor-staff replies) | §4.2 L368; refuter L621 | No | SECONDARY: forum report |
| C-REF3-DC-technical-003 | Integrator blog (low) | §4.2 L368 | No | SECONDARY: integrator blog |
| C-REF3-DC-technical-007 | Community discussion (Talos on Orin) | Refuter L635 | No | SECONDARY: community discussion |
| C-REF3-DC-technical-014 | Failure reports (JetPack 7.2 ISO installer) | Refuter L622 | No | SECONDARY: forum report |
| C-REF3-W19-technical-008 | Community PSA (custom integration reboot loop) | Refuter L670 | No | SECONDARY: community |
| C-REF3-W19-technical-010 | Press | §4.8 L471; refuter L671 | No | SECONDARY: press |
| C-REF3-W19-technical-012 | Security vendor blog | §4.8 L470 | No | SECONDARY: security vendor blog |
| C-SCORE-027 | Fedora ARM/IoT lead's personal blog (Pi 5 status) | Corrections log L155 | No | SECONDARY: maintainer's blog |
| C-STEEL-ubu-002 | Software Freedom Conservancy statement (2015) | Corrections log L153 | No | SECONDARY: SFC statement |
| C-STEEL-updates-mender-012 | Community tutorial (Mender on stock L4T) | §3.2 L266; §6.6 L708 | No | SECONDARY: community tutorial |

### 3.2 Re-type to PRIMARY (first-party statements about the speaker's own project)

| Claim | Why | Proposed row change |
|---|---|---|
| C-W3-016 | Rugix's own blog describing Rugix's limits (newer, less deployed, CLI only). A project's statement about itself is first-party. It carries the Rugix C7 = 2 cell in S2 (L241); the cell is unchanged | `source_type` SECONDARY → PRIMARY, with the note "[vendor self-statement]" |
| C-REF-W3-longevity-007 | Pengutronix maintains RAUC; its 10-year retrospective is the maintainer's own account | SECONDARY → PRIMARY "[maintainer self-statement]" |

These are proposals for the W3 / REF-W3 owners. CIT4 did not edit those fragments.

### 3.3 PRIMARY-METADATA that is the right type (no action)

Package indexes and repository metadata are primary data, not prose, so PRIMARY-METADATA is the correct type: C-LAB-rauc-002, C-LAB-rauc-k3s-gate-005, C-LAB-ubuntu-2604-leg-002, C-LAB-ubuntu-2604-leg-004, C-REF-DC-longevity-006, C-REF3-W19-technical-001, C-REF3-W19-technical-002, C-W18-062, C-W18-063, C-W18-064, C-W19-004. Suggested §9 wording treats them as meeting the rule (above).

### 3.4 PRIMARY but `partial` by design

| Claim | Why partial | Label for 01 |
|---|---|---|
| C-LAB-rauc-1152-017 | Desk pre-flight on a loop device in an arm64 VM, not a Pi 5 boot (S1 DC-19 row L200; §3.2 L261; ADR table L782) | "partial: desk pre-flight, no Pi 5 boot; founder test LT-PI5-01" |
| C-LAB-secureboot-rauc-005 | systemd-stub documentation; not exercised in the lab | "partial: documentation, not lab-tested" |
| C-REF-W6-technical-008 | Reading of the CRA guidance (a box is classified by its core function) | "partial: interpretation, needs counsel" (S1 DC-04 row L206 favours A only "small") |
| C-SCORE-024 | ctrlX OS page; corrections log only | "partial" |

### 3.5 Already superseded

C-W7-005 ("r35 still active") was superseded by C-REF-W7L-001 (JetPack 5 EOL 2026-10-30). It is still cited on L569 and L571 inside refuter rows, where it records what the refuter saw. Add "(superseded by C-REF-W7L-001)" after it, and drop it from L951's open-items list, since W7 has marked it.

## 4. Supersession map (for the master-ledger re-merge)

| Old row | Status set here | New row |
|---|---|---|
| C-W18-027 (`W18.csv`) | **superseded** (edited in its fragment, with a `[LEDGER 2026-11-11 CIT4 …]` note) | C-CIT4-003 |
| C-STEEL-ubu-011 (`STEEL-base-ubuntu.csv`) | **superseded** (same) | C-CIT4-012 |
| C-REF3-DC-technical-020 (`REF3-DC-technical.csv`) | **superseded** (same) | C-CIT4-016 |
| C-DEC-013 | left as is (UNVERIFIED negative search; its wording needs narrowing) | C-CIT4-001, -002 (partial) |
| C-DEC-014 | left as is | C-CIT4-013 (CVE facts) |
| C-REF-W19-security-002 | left as is | C-CIT4-014 (version facts) |
| C-REF3-DC-technical-024 | left as is | C-CIT4-015 (kernel version) |
| C-REF3-DC-cost-001 | left as is | C-CIT4-008 (16 GB and CM5 facts) |
| C-REF3-DC-cost-002 | left as is | C-CIT4-009 + C-W10-025 (current prices, Orin Nano Super +60%) |
| C-REF-W8-longevity-009 | left as is | C-CIT4-011 (existence of prAA) |
| C-STEEL-cra-nb-017 | left as is (UNVERIFIED, blocked) | C-CIT4-010 (context only) |
| C-W10-025 ($249 launch price) | left as is; still true as a launch fact | C-CIT4-009 gives the current $399; any sentence using $249 as *today's* price should cite C-CIT4-009 |

The three fragments edited here were clean in git and untouched for about five hours, so only their `status` field and a note were changed. The master `evidence/claims.csv` was not edited; the re-merge (pass-1 #3) should pick up these statuses.

## 5. Conclusions ledgered as facts: C-W19-047, -048, -049

All three rows are `PRIMARY` / `partial`, with `source_url` = `29-PLATFORM-ECOSYSTEM-MARKETPLACE.md` and `commit_or_tag` = "synthesis of …". They record the **DC-16 answer, constraint and flip condition**, which are the agent's own conclusions. A conclusion is not a source, and the PRIMARY type makes 01's §4.8 and §5.10 look as if a vendor said it.

| Row | What it is | Proposed status |
|---|---|---|
| C-W19-047 "DC-16 ANSWER: no plugin type needs an OS fork … PROVIDED nine extension points" | Derived conclusion from C-W19-001…009, 015, 017, 034, 035 and competitor rows; weakened by three refuters and since extended to ten points (E10) | Move out of the claims ledger into `decision-critical.md` (DC-16 Result) as **DC-16-R1**. If it must stay in the ledger: `source_type` = `DERIVED` (a new type, to be logged in `scorecard-weights.md` §8), `status` = `partial`, `claim` reworded to "ten extension points (E1–E10)" to match 01 rev. 2 |
| C-W19-048 "DC-16 CONSTRAINT: kernel drivers … must be built and signed per OneMind kernel" | Derived from C-W19-005, -008, -009 and C-STEEL-KRU-013. Its factual core (a module needs `modules.dep` for the exact kernel; Secure Boot lockdown needs a trusted signature) is already sourced in those rows | Same: **DC-16-R2**, or `DERIVED` / `partial`. Wherever 01 cites it for a *fact*, cite C-W19-005/008/009 and C-DEC-008/009 directly |
| C-W19-049 "DC-16 FLIP CONDITION not met … reserve SYSEXT_LEVEL …" | A verdict ("not met") plus a recommendation (four image reservations) | Same: **DC-16-R3**, or `DERIVED` / `partial`. A verdict cannot be `verified` by a source; it can only be upheld or weakened by refuters, which §5.10 already records |

Until `DERIVED` is accepted into the protocol, the nearest allowed value is the status, not the type: keep `partial`, and 01 should label each citation "(DC-16 conclusion, derived)". In 01 that applies to L67, L454, L649–L657 and L756. A similar but harmless case outside 01's scope: C-STEEL-backup-kopia-021 records a citation defect found in 06 as a PRIMARY fact. It is an observation of a repository file, so PRIMARY is defensible.

## 6. P3-12: re-check windows

**Fixed in their fragments** (rule 10: kernel, BSP and Kubernetes facts are re-checked after 6 months):

| Row | Fragment | Old `recheck_by` | New |
|---|---|---|---|
| C-W7-040 (Spot CORE I/O on JetPack 5.1.2 / L4T R35.4.1) | `W7.csv` | 2027-11-10 | **2027-05-10** |
| C-W7-041 (VOXL 2, kernel 4.19) | `W7.csv` | 2027-11-10 | **2027-05-10** |
| C-TD-talos-009 (Image Factory schematic) | `TD-talos.csv` | 2027-11-11 | **2027-05-11** |
| C-TD-talos-038 (Omni on Talos at the edge) | `TD-talos.csv` | 2027-11-11 | **2027-05-11** |

**Re-scan.** The critic asked for a scan by component class, not keyword. No ledger has a component-class column, so two scans were run on every non-superseded row with a window over 200 days: (1) the `component` field matched against kernel/BSP/L4T/JetPack/Kubernetes/k3s/RKE2/k0s/MicroK8s/Talos/PREEMPT names; (2) the claim text matched against kernel and BSP version patterns. After removing false positives (app version numbers in Project N.O.M.A.D. and Market-seed rows, licence files, the HarmonyOS and Kubernetes-the-Hard-Way rows, launch prices), these rows are **still on 12 months and should move to 6**. They are listed for their owners and were **not edited** here:

| Row | Fragment | Why it is a kernel / BSP / Kubernetes fact |
|---|---|---|
| C-REF-W8-security-004 | `REF-W8-security.csv` | CIP picked Debian 12 + CIP kernel 6.1 for its 62443 work |
| C-SCORE-004 | `SCORE.csv` | k0s production adopters (Kubernetes distribution) |
| C-STEEL-updates-mender-013 | `STEEL-updates-mender.csv` | Mender supports Jetson on JetPack 4.6+ / L4T |
| C-STEEL-updates-mender-018 | `STEEL-updates-mender.csv` | Mender on Orin / JetPack 6 |
| C-STEEL4-bootc-016 | `STEEL4-bootc.csv` | AlmaLinux 10.x kernel 6.12 and aarch64 support |
| C-TD-balenaos-034 | `TD-balenaos.csv` | balena release contracts on `sw.l4t` |

A component-class column (`kernel`, `bsp`, `kubernetes`, `lifecycle`, `pricing`, `licence`, `other`) in the ledger header would make this check exact; that is a protocol change for the ledger owner.

## 7. What is still open

- **NANDO count** (C-STEEL-cra-nb-017): blocked here; one browser visit by the founder closes it.
- **Jetson rootfs A/B by OTA** (C-REF-DC-cost-005): NVIDIA's guide is silent; the founder Jetson test in `22-…` should include "flash without A/B, then OTA to an A/B layout" as a check.
- **Pi 5 4 GB and 8 GB list prices:** no official source found on 2026-11-11 (the product page shows no price for them, and a stale $305 for 16 GB).
- **IronFlockOS** (C-CIT4-001): re-check at its 1.0, or by 2027-05-11. If a target passes hardware acceptance, re-score the S2 "Debian precedent" row and add it to `02-competitors/` as a Tier C entry. Its code is Apache-2.0, so patterns may be studied freely.
- **Rows here that could not be archived byte-for-byte:** C-CIT4-008 (bot challenge; read with a web fetch).

## 8. Revision 4.1 appendix: the rest of the exception list (critic P4-4)

**Date:** 2026-11-11 · **By:** DEC5 · **Scope:** `01-FOUNDATION-DECISION.md` revision 4.1.

01's §12 says that every cited row that is not PRIMARY, or not `verified`, is listed in this file. §1–§7 above were written for revision 3. Revisions 4 and 4.1 cite more rows. This section completes the list, so the statement in 01 is true again.

**Method.** Every claim ID in 01 was resolved against `evidence/claims/*.csv`, with ranges such as `C-DEC5-022…025` expanded. Result: **827 distinct ledger IDs**, of which **132 are not PRIMARY or not verified**. 72 of them already appear in §1–§7 by their full ID. **The 60 below are the rest.** A few §2 rows list IDs in shorthand (for example "C-REF3-DC-technical-001, -002"); those IDs are repeated here so that a full-ID search finds every one. The three DC-16 conclusions C-W19-047…049 are covered in §5 and are now typed `DERIVED` in `claims/W19.csv` (P3-4 residual). The rule for reading the last two columns is the same as in §3: a failure report or press item can show that something happened, not how often.

**Result.** No scorecard cell rests on any of these rows alone. Two rows each support one S1 tie-break cell (C-REF4-S1R4-security-007, C-STEEL4-bootc-013). Removing either moves one D–C cell, which narrows the count to 6–5 or 5–4; **D still wins S1**. Two rows support sub-checks of the S1 gate cell D·G4 (C-FIX7-004, -005). Removing them leaves G4 CONDITIONAL.

| Claim | Type · status | Where in 01 | What it supports | Does a cell or tie-break row change without it? | Label |
|---|---|---|---|---|---|
| C-DEC5-005 | SECONDARY · verified | §12 open items; §5.9.2 refuter row; header | Buildroot mailing list series '[PATCH v2 0/2] Linux kernel CVE filtering improvements' (F. Lehoussel; v1 2026-… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-DEC5-014 | VENDOR-FORUM · verified | §12 open items; §5.9.2 refuter row; header | NVIDIA forum 'Unable to get capsule updates to work with A/B updates' (2026-03-12, Orin NX custom carrier, Sec… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | VENDOR-FORUM: vendor staff on forum |
| C-DEC5-015 | SECONDARY · verified | §12 open items; §5.9.2 refuter row; header | NVIDIA forum 'Update stops overlay applying' (2025-11-12, Orin Nano): after a routine update the jetson-io DT… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-DEC5-017 | PRIMARY · partial | §12 open items; §5.9.2 refuter row; header | E10 longevity refuter row: Pi 5 Rev 1.1 fails on 2025 EEPROMs | No | partial: maintainer called it a duplicate and pointed to the reseller (possible board defect) |
| C-DEC5-018 | SECONDARY · verified | §12 open items; §5.9.2 refuter row; header | RidgeRun wiki 'JetPack 6 Migration and Developer Guide: Versions and Support' (last edited 2025-06-07) reprodu… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-DEC5-019 | VENDOR-FORUM · verified | §12 open items; §5.9.2 refuter row; header | NVIDIA forum 'Updating major Jetpack releases OTA' (2025-12-04, Orin NX fleet of about 2,000 units): NVIDIA st… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | VENDOR-FORUM: vendor staff on forum |
| C-DEC5-026 | SECONDARY · verified | §12 open items; §5.9.1 refuter row; header | Spectro Cloud Palette VerteX 4.2 FIPS docs: RKE2 is designated FIPS-compliant; 'K3s is not available as a FIPS… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-DEC5-027 | SECONDARY · verified | §12 open items; §5.9.1 refuter row; header | Geomys 'Go and FIPS 140 September update' (2025-09-07): proposes a limited bypass of GODEBUG=fips140=only enfo… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-DEC5-028 | SECONDARY · verified | §12 open items; §5.9.1 refuter row; header | Compyl CJIS compliance guide: CJI leaving a physically secure location must be protected by cryptographic modu… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-FIX4-006 | SECONDARY · verified | §5.1.2 refuter row | Raspberry Pi forum thread 'Update Ubuntu and EEPROM' (2026-05-22): a Pi 5 on Ubuntu 24.04 is told by the relea… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-FIX4-009 | SECONDARY · partial | §5.1.2 refuter row | uutils/coreutils issue #15254 (open, filed 2026-10-11): a differential fuzzer run of GNU coreutils 9.12 agains… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY, partial |
| C-FIX4-012 | SECONDARY · partial | §5.1.2 refuter row | Third-party guide (updated 2026-05-08): 'Ubuntu 26.04 LTS is the first Ubuntu release where the initramfs on d… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY, partial |
| C-FIX4-013 | SECONDARY · verified | §5.1.2 refuter row | LWN (2014-02-14) reports the Ubuntu Community Council statement on 'Canonical's requirement that binary redist… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-FIX7-004 | SECONDARY · partial | §3.1.1 S1 gate cell D·G4 | Sub-check (a): 26.04 universe ships the protocol stacks (Repology) | No. (a) also rests on C-G4U-003 (primary: the MQTT 5 broker version); without the package listing, the stacks ship as app images and (a) stays PASS or at worst COND. D·G4 stays COND. Networked re-check: F-2 in `adversarial/G4-ubuntu-rev5.md` | SECONDARY, partial: package index aggregator (archive blocked here) |
| C-FIX7-005 | SECONDARY · partial | §3.1.1 S1 gate cell D·G4 | Sub-check (e): `rauc-hawkbit-updater` not packaged for 26.04 | No. If wrong, G4-M5 is dropped; (e) stays COND (no 10k run) | SECONDARY, partial: package index aggregator (archive blocked here) |
| C-LAB-aarch64-gate-006 | PRIMARY · partial | §10 lab summary | Nested KVM inside a Lima vz VM on Apple M5 Max gave erratic guest speed for this workload: in run 2 the gate's… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | PRIMARY, partial |
| C-LAB-aarch64-gate-008 | PRIMARY · partial | §10 lab summary | Debian AAVMF 2025.02-8+deb13u1 (AAVMF_CODE.fd sha256 5d3147294c56...52d3) hung after its banner when used with… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | PRIMARY, partial |
| C-LAB-aarch64-gate-011 | PRIMARY · partial | §10 lab summary; §3.1.6 S1 re-derivation | S1-13 ruling and §10: RAUC on the Pi 5 gets one trial boot by firmware design (arm64 VM, not a Pi) | No cell | partial: VM evidence, no Pi 5 boot |
| C-LAB-minimal-image-dc20-004 | PRIMARY-METADATA · verified | §10 lab summary | kernel.org lists 6.12.117 (released 2026-11-10) as the current 6.12 longterm point release; Debian 13.7 ships… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | PRIMARY-METADATA (right type: index or repository metadata) |
| C-LAB-minimal-image-dc20-005 | PRIMARY-METADATA · verified | §10 lab summary | Debian 13 (trixie) ships mkosi 25.3-7; forky/sid have 27.1-1. | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | PRIMARY-METADATA (right type: index or repository metadata) |
| C-LAB-minimal-image-dc20-006 | PRIMARY-METADATA · verified | §10 lab summary | k3s v1.37.2+k3s1 (published 2026-11-03) is the k3s stable channel release on 2026-11-11. | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | PRIMARY-METADATA (right type: index or repository metadata) |
| C-LAB-minimal-image-dc20-007 | PRIMARY-METADATA · verified | §10 lab summary | syft v1.57.1 and grype v0.121.3 were both published 2026-11-09; the grype vulnerability DB used for every scan… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | PRIMARY-METADATA (right type: index or repository metadata) |
| C-REF-DC-robotics-006 | SECONDARY · verified | §5.9 refuter row | Pi 5 PREEMPT_RT (6.13-rc v8 rt kernels) under stress (4 vm + 4 cpu workers): per-thread cyclictest maxima 196-… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-REF-W19-longevity-003 | SECONDARY · verified | §5.10.1 refuter row | Microsoft's C/C++ extension v1.24.5 (2025-04-03) refuses to run in VS Code forks such as VSCodium and Cursor (… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-REF-W19-security-010 | SECONDARY · verified | §4.8 recommendation text; §5.10 refuter row | Datadog (reported by Help Net Security 2025-05-21): three malicious Solidity-tool extensions (Solaibot, among-… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-REF-W19-technical-008 | SECONDARY · verified | §4.8 recommendation text; §5.10 refuter row | BleepingComputer 2025-02-26: Microsoft removed Material Theme Free and Material Theme Icons Free (~9M installs… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-REF3-DC-longevity-009 | SECONDARY · verified | §4.3 recommendation text; §5.9.1 refuter row | LWN 2025-07-16: a KEK update 'has never happened before' so BIOS vendors may have 'messed up things'; 'the old… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-REF3-DC-longevity-010 | SECONDARY · verified | §5.9.1 refuter row | PKfail (Binarly BRLY-2024-005): AMI 'DO NOT TRUST' test Platform Key shipped in production firmware of hundred… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-REF3-DC-security-007 | SECONDARY · verified | §5.9.1 refuter row | Wiz (2025-07-17) NVIDIAScape CVE-2025-23266, CVSS 9.0: NVIDIA Container Toolkit createContainer hook inherits… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-REF3-DC-technical-002 | SECONDARY · verified | §4.2 recommendation text; §5.9.1 refuter row | NVIDIA forum (2024-05-10..22, custom Orin Nano carrier): after 3 boot failures the bootloader printed 'Switchi… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-REF3-DC-technical-008 | SECONDARY · verified | §5.9.1 refuter row | Talos discussion #7821 (Raspberry Pi 5), closed: maintainer (2025-03-14) Pi 5 'not fully supported until the u… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-REF3-DC-technical-010 | SECONDARY · verified | §5.9.1 refuter row | NVIDIA forum (2024-10-08): an Orin NX (JetPack 5.1.1 / L4T 35.3.1) flashed to NVMe with Kairos completes flash… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-REF3-DC-technical-015 | SECONDARY · verified | §5.9.1 refuter row | NVIDIA forum (2026-10-06..09): new Orin Nano Super P3767-0005 cannot be flashed with JetPack 7.2.1 via SDK Man… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-REF3-DC-technical-017 | SECONDARY · verified | §5.9.1 refuter row | NVIDIA forum (2026-04-20): asked which package in Jetson Linux 36.5 fixes CVE-2026-24148 and whether a partial… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-REF3-W19-technical-003 | PRIMARY-METADATA · verified | §5.10.1 refuter row | omacom/omarchy-plugin-marketplace was created 2026-07-28 and its issue/PR numbers reached #14677 by 2026-11-11… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | PRIMARY-METADATA (right type: index or repository metadata) |
| C-REF3-W19-technical-006 | PRIMARY-METADATA · verified | §5.10.1 refuter row | hacs/default had 829 open pull requests (inclusion requests) on 2026-11-11 | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | PRIMARY-METADATA (right type: index or repository metadata) |
| C-REF3-W19-technical-013 | SECONDARY · verified | §5.10.1 refuter row | LWN: a preliminary injunction granted 2024-12-10 requires Automattic to restore WP Engine's control of the ACF… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-REF4-DC-longevity-006 | COMMUNITY · verified | §3.1.6 S1 re-derivation; §5.9.2 refuter row | Tie-break row DC-05 (A–D → ≈): Umbrel field reports of stranding after the trixie rebase | No. The row also rests on C-REF4-DC-technical-008 (PRIMARY, getumbrel #2153) and on the absence of any RAUC major-rebase precedent | COMMUNITY: user report |
| C-REF4-DC-longevity-007 | COMMUNITY · verified | §5.9.2 refuter row | Umbrel community thread (2026-04-29 to 2026-05-10): umbrelOS 1.5 -> 1.7.1 OTA fails on several Intel NUCs ('Up… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | COMMUNITY: user report |
| C-REF4-DC-longevity-011 | VENDOR-FORUM · verified | §5.9.2 refuter row | NVIDIA forum (2026-05-06): user cites roadmap 'Jetpack 7 being released with Orin support in Q2 2026'; reply… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | VENDOR-FORUM: vendor staff on forum |
| C-REF4-DC-longevity-015 | SECONDARY · verified | §5.9.2 refuter row | Techzine (2026-03-11, citing Reuters): EQT is exploring a sale of SUSE (k3s/RKE2/Rancher steward) at up to abo… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-REF4-DC-longevity-019 | SECONDARY · verified | §5.9.2 refuter row | Linuxiac (2023-09-20): Jonathan Corbet at OSS Europe said LTS kernel support is expected to drop from six year… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-REF4-DC-longevity-020 | SECONDARY · verified | §5.9.2 refuter row | noze.it (2026-07-26): linux-cve-announce published 432 CVE IDs on 2026-07-19/20; kernel CNA published 4,325 CV… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-REF4-DC-longevity-021 | SECONDARY · verified | §5.9.2 refuter row | Linuxiac (2026-06-19): the June Raspberry Pi OS update ships Linux 6.18.34 LTS (moving the Pi kernel off the 6… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-REF4-DC-longevity-022 | SECONDARY · verified | §5.9.2 refuter row | CNCF news (2024-08-22, republished ZDNet): the Linux kernel security team issues about 60 CVEs in an average w… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-REF4-DC-security-002 | SECONDARY · verified | §5.9.2 refuter row | heise (38C3, Dec 2024): Thomas Lambertz's bitpixie attack downgrades the boot chain to an outdated Windows boo… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-REF4-DC-security-003 | SECONDARY · verified | §5.9.2 refuter row | The Hacker News (Aug 2024): SafeBreach's Windows Downdate (Black Hat USA 2024) abuses the OS's own update proc… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY |
| C-REF4-DC-technical-006 | SECONDARY · verified | §3.1.6 S1 re-derivation; §5.9.2 refuter row | Same DC-05 row: Umbrel user report, no update offered beyond 1.5.0 | No (as above) | SECONDARY: forum report |
| C-REF4-DC-technical-007 | SECONDARY · verified | §3.1.6 S1 re-derivation; §5.9.2 refuter row | Same DC-05 row: Umbrel 1.5 → 1.7.1 OTA failures | No (as above) | SECONDARY: forum report |
| C-REF4-S1R4-longevity-002 | SECONDARY · verified | §3.1.6 S1 re-derivation; §5.1.1 refuter row | S1-15 ruling (A·C1 not re-scored): Debian-packaged Mender stranding | No; S1-15 was not re-scored | SECONDARY: forum report |
| C-REF4-S1R4-security-007 | INFERRED · unverified | §3.1.6 S1 re-derivation; §5.1.1 refuter row | Tie-break row "signed GPU/driver modules": the free RHEL-family variant is inferred not to get Red Hat-signed NVIDIA modules | Possibly one cell: without it D vs C could move ≈ → C, making D–C 6–5; **the S1 winner is unchanged** (D) | INFERRED, unverified: refuter's inference |
| C-REF4-S1R4-technical-002 | PRIMARY · unverified | §5.1.1 refuter row | Debian trixie release page: life cycle includes LTS to 2030-06-30, during which the set of supported architect… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | PRIMARY, unverified |
| C-REF5-S1-technical-009 | PRIMARY · UNVERIFIED (blocked) | §5.1.3 refuter row | §5.1.3 response: Ubuntu's own Pi A/B boot mechanism may compete with RAUC | No; it becomes a founder check beside F-1 | UNVERIFIED (blocked): Ubuntu docs host does not resolve here |
| C-STEEL-etcd-every-box-011 | PRIMARY-METADATA · verified | §6.12 steelman summary | etcd released patches for three minor lines on 2026-10-22: v3.7.3, v3.6.16 and v3.5.35 (previous set v3.7.2/v3… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | PRIMARY-METADATA (right type: index or repository metadata) |
| C-STEEL4-bootc-001 | PRIMARY-METADATA · verified | §6.14 steelman summary | AlmaLinux/bootc-images-rpi (the only Pi 5 bootc route ledgered for candidate C): repo created 2025-07-09, 12 s… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | PRIMARY-METADATA (right type: index or repository metadata) |
| C-STEEL4-bootc-013 | PRIMARY · partial | §3.1.6 S1 re-derivation; §6.14 steelman summary | Tie-break row "NVIDIA trajectory": the free bootc Jetson route is frozen | Possibly one cell: without it D vs C could move D → ≈, making D–C 5–4; **the S1 winner is unchanged** (D) | partial: steelman's reading of a repository state |
| C-STEEL4-bootc-024 | PRIMARY-METADATA · verified | §6.14 steelman summary | Issue states on 2026-11-11: greenboot-rs #219 (healthy host rolled back after a failed finalize) is open, last… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | PRIMARY-METADATA (right type: index or repository metadata) |
| C-STEEL4-bootc-025 | PRIMARY · partial | §1 answer table; §3.1.6 S1 re-derivation; §6.14 steelman summary; §What changed in revision 4 | A shipped box cannot move to bootc without a reflash (sequencing argument for W2-HW-3 before G1) | No cell; it orders tests (R4-7, REC-DEC-44) | partial: steelman's inference from documented rebase limits |
| C-W19-022 | PRIMARY · partial | §12 open items; §5.10 refuter row; §5.10.1 refuter row | Obsidian: 'Due to technical limitations, Obsidian cannot reliably restrict plugins to specific permissions or… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | PRIMARY, partial |
| C-W19-027 | SECONDARY · partial | §12 open items; §5.10 refuter row; §5.10.1 refuter row | AUR (July 2025): three packages (librewolf-fix-bin, firefox-patch-bin, zen-browser-patched-bin) uploaded 2025-… | No (refuter, steelman, lab-summary or risk text; no scorecard cell or tie-break row cites it) | SECONDARY, partial |
| C-LAB-secureboot-1152-010 | PRIMARY · partial | §3.1.6 S2 / Secure Boot rows (rev. 4) | RAUC prevent-late-fallback=true (since 1.14) marks the other slot bad after a commit; behaviour observed in the secureboot-1152 lab, upstream docs not separately saved | Keep the label from its ledger row; cite with the lab qualifier |


## Glossary

- **PREEMPT_RT:** the Linux patch set (now mostly mainline) that makes the kernel preemptible almost everywhere, so a high-priority task waits less.
- **cyclictest:** the standard tool for measuring how late a periodic real-time thread wakes up. Its "max" is the worst case seen in that run, not a guarantee.
- **CPU isolation (`isolcpus`, `nohz_full`):** keeping chosen CPU cores free of normal work so real-time threads on them are not disturbed.
- **Failure report:** a source whose value is showing that something went wrong at least once. It cannot show how often.
- **Negative search:** "we looked and found none". It can be disproved by one example, so it is never `verified`.
- **NANDO:** the European Commission's database of notified bodies (third-party assessors) per EU law.
- **Superseded:** a ledger row replaced by a newer or better-sourced row. It stays in the ledger for history.
