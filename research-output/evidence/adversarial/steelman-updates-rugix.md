# Steelman: keep Rugix as OneMind OS's update engine

- **Role:** runner-up steelman (RESEARCH-MISSION.md §2 rule 7). Told to argue *for* Rugix, as strongly as the evidence honestly allows.
- **Decision under test:** S2 / ADR-001 D3. `01-FOUNDATION-DECISION.md` §3.2 changed the lead engine from Rugix to RAUC (corrected RAUC 58.0, Mender 57.0, Rugix 52.0), mainly on the bus factor (C-W3-001) and on revocation/multi-signer gaps (C-W3-009).
- **Date:** 2026-11-11 (sources opened 2026-11-10/11 UTC). Re-check by: 2027-05-11.
- **Verdict:** `steelman`. New primary evidence lifts Rugix to **56.0 vs RAUC 58.0**, inside the 3-point tie band. The tie-break then turns on one item, maintainer depth (DC-06), and that item still favours RAUC. Rugix is a fully defensible founder choice, not a runner-up by a wide margin.
- **Ledger:** `evidence/claims/STEEL-updates-rugix.csv` (C-STEEL-updates-rugix-001 … 024).

> **Explain it like I'm the founder.** The update engine is the piece of software on each box that installs a new OS copy into the spare slot, reboots into it, and goes back to the old copy if the new one is unhealthy. We picked RAUC because Rugix is mostly written by one person. This file makes the best honest case that Rugix is still the better fit for *us*. Short version: Rugix does more of the work a solo founder would otherwise build by hand (an image builder that runs on a Mac, Pi 5 support built in, encrypted data unlocked by the TPM chip, and the Secure Boot boot method our security plan assumed), and an industrial IoT framework backed by Cumulocity chose it too. Its one serious weakness is still one person. On our own scorecard the two engines now tie, so this comes down to what you value more: less work now, or more maintainers in 2032.

---

## 1. What changed since the W3 verdict (new primary evidence)

The W3 verdict and its refuters were right on the facts they had. This pass looked for evidence they did not have.

| # | New fact | Why it matters | Claim |
|---|---|---|---|
| 1 | Since 1.3.0, Rugix Ctrl **accepts bundle signatures from any configured root and checks every signature** rather than stopping at the first invalid one. `signatures.roots` is an array. | That is multi-root trust and a key-rotation path (ship the new root, sign with both, then drop the old). W3 scored Rugix as lacking multi-signer support (C-W3-009). It still has no **revocation** list. | 001, 002 |
| 2 | The v1.4.0 source has a **`luks2-tpm2` data-partition driver**: `systemd-cryptenroll` seals the key to the TPM, and the code calls it "production-grade". An upstream integration test (swtpm-backed) checks that the **TPM still unlocks the data partition after an A/B update**. | This is OneMind's DC-18 / SEC requirement (LUKS2 data that survives update and rollback). With RAUC it is OneMind's own integration work, still unproven until spike X-2R. | 003, 004 |
| 3 | Rugix has a **native systemd-boot boot flow** (`LoaderEntryOneShot` / `LoaderEntryDefault` via `bootctl`), and a cross-flow compatibility test for the `rauc-grub` and `mender-uboot` flows. | W6's Secure Boot design (SEC-01, signed UKIs) assumed Rugix's systemd-boot flow (C-W6-049). RAUC has **no** native systemd-boot backend (C-DEC-001), which is why 01 §4.3 had to redesign the boot partitions and add spike X-2R. | 005, 006 |
| 4 | **Anti-downgrade:** on issue #121, the maintainer replied that downgrades "can already be prevented through `Runtime` and `Local` component constraints" (a `min-version` component that conflicts with older versions). The component schema has `requires` / `conflicts`. | W3 recorded "no anti-downgrade" (C-W3-009). There is a mechanism. It is a constraint system rather than a monotonic counter, and its documentation is only a maintainer's issue comment. | 007, 008 |
| 5 | **thin-edge.io** (Apache-2.0, Cumulocity's open IIoT edge framework) documents Rugix in its official firmware-management docs. Its only non-Yocto image route is Rugix, and its official Yocto layer `meta-tedge` ships a `tedge-rugix-tpm2` Raspberry Pi project. It also ships RAUC and Mender layers. | A second, independent, industrial-IoT organisation chose Rugix for exactly OneMind's pattern (a distro image built outside Yocto) and keeps it current in 2026. This is primary code evidence, not a vendor testimonial. | 009, 010, 011 |
| 6 | Industrial hardware: official Rugix integrations for **Revolution Pi** (KUNBUS) and **Strato Pi Max** (Sfera Labs, dual-SD hardware failover), plus an Aug-2026 trade article co-authored by Sfera Labs' co-founder. | Shows the IIoT gateway class (F-11) is a real target. Vendor-authored, so it is `SECONDARY` for adoption. | 012, 013, 014 |
| 7 | Silitics publishes an **Open Source Commitment** (Rugix tools "will remain open-source under their current permissive licenses (MIT and Apache 2.0)") and sells an enterprise subscription with "long-term support for selected Rugix versions". No price, duration or succession is stated. | Partly answers the refuters' "governance statement" flip condition (licence), but not the continuity half. | 015, 016 |
| 8 | Umbrel pins Rugix Bakery by digest, builds with `SOURCE_DATE_EPOCH`, and moved to the patched Rugix Ctrl **v1.3.2** (the advisory fix of 2026-10-29) within days. | The constraint-matched competitor is not a passive user: it tracks security releases fast and reported one of the two High advisories itself. | 017, 018 |
| 9 | Re-measured: 168 of 169 default-branch commits since 2026-05-10 are by `koehlma`. About 47k lines of Rust in 15 crates. | The bus factor is **unchanged** (it is not improving). A fork is realistic but would be a large job. | 019, 020 |

## 2. The case for Rugix, lens by lens

### 2.1 F-14: one OS from a Pi to the enterprise
- **Pi 5 is native, not a custom backend.** Rugix ships an `rpi-tryboot` boot flow (Pi 4 and newer) that Umbrel runs in the field (C-W3-011, C-W3-071). In the RAUC plan, Pi 5 uses a **custom tryboot backend** modelled on HAOS's script (01 §4.2 item 1), and "Pi 5 tryboot with RAUC" is on 01's **not proven** list (01 §8). For F-14 the Pi end is the hard end: it is the first box most users touch.
- **x86 is covered both ways.** GRUB (proven in our lab on amd64 and arm64, C-LAB-debian-rugix-022) and systemd-boot (native, item 3). The same `rugix-ctrl` binary, CLI, bundle format and state model run on both.
- **One image builder for every board the engine covers.** Rugix Bakery built Debian 13 images for **both** architectures on the founder's Mac in about 5 and 12 minutes (C-LAB-debian-rugix-020). RAUC is only the device side, so OneMind still has to choose and maintain a separate image builder (debos, mkosi, or a Dockerfile pipeline).
- **The enterprise end is neutral.** GPU servers and cluster nodes run the same image family; neither engine adds anything for multi-node k3s/RKE2, because fleet orchestration sits above the engine either way.

### 2.2 F-11: IoT and Industrial IoT
- **An independent IIoT framework chose it** (item 5). thin-edge.io is the closest open-source analogue of an IIoT device-management agent OneMind would host or compete with. Its Rugix image covers Raspberry Pi 0 through 5 plus Debian 12 EFI on amd64 and arm64: the Edge/Lite tiers exactly.
- **Industrial gateways:** RevPi and Strato Pi Max integrations exist upstream (item 6). Revolution Pi is one of the gateway classes W8 names.
- **Fleets of thousands:** Rugix is fleet-neutral, and it has a documented Nexigon backend, a thin-edge/Cumulocity backend and a Memfault example. RAUC needs hawkBit or similar too. Neither engine alone gives a 10k-device control plane.
- **CRA and IEC 62443 evidence:** CycloneDX SBOMs come with every binary, there is a 3-business-day disclosure SLA, and both 2026 High advisories were disclosed the same day as their fixes (W3-P0-W3-1-technical). Silitics sells CRA-focused engineering. The gap: GHSAs without CVE IDs (see §4).

### 2.3 Robotics (Jetson)
- **The Jetson gap is not a differentiator.** OneMind's chosen Jetson flavor uses **NVIDIA's own rootfs A/B and image-based OTA**, with OneMind's gate in NVIDIA's validation hook, *whatever engine runs on x86/Pi* (01 §4.2 item 1, C-W3-049). RAUC scored C2 = 2 as well. Both engines have a `custom` boot-flow hook that could drive `nvbootctrl`. Neither has done it.
- **Robot application updates:** Rugix Apps adds versioned app/config pairs with rollback and staged activation (`--no-activate`) in 1.4 (C-STEEL-updates-rugix-021). It is marked experimental, and OneMind's apps run on k3s, so this is an option rather than a dependency.

### 2.4 Security
- **Where Rugix is ahead of the RAUC plan:** TPM-sealed LUKS2 data tested across an update upstream (item 2); a native systemd-boot flow for the signed-UKI Secure Boot route W6 designed (item 3); signatures **mandatory unless opted out** since 1.0 (CHANGELOG); no "plain vs verity" format trap like RAUC's CVE-2026-34155 (C-DEC-004), so there is no `bundle-formats` setting to get wrong.
- **Where it is level:** both have automatic rollback with a gate hook, a documented interruption-safe install (Rugix's upstream `test_forced_reboot_during_update_keeps_active_system`), power-cut survival in **our** lab (C-LAB-debian-rugix-022, C-LAB-rauc-017), and multi-root trust (item 1).
- **Where RAUC is ahead:** CRL / signer revocation (C-W3-018), `use-bundle-signing-time` for boxes with dead clocks, encrypted bundles (Rugix #120 is open), dm-verity bundle format, and more maintainers to review security code.

### 2.5 Solo-developer operability (the strongest lens)
- **Bakery is a declarative recipe system** (the C5 anchor-4 example names "a Bakery recipe"). It builds from a Mac via containers and is measured under 30 minutes per image in our lab (an anchor-5 element).
- **Declared persistent state, bootstrapping and data encryption are built in.** With RAUC these are OneMind code: overlay and state layout, first-boot partition growth, and LUKS/TPM enrolment.
- **Umbrel is a solo-scale proof.** A small team took a Debian appliance across Debian 12 → 13 and Mender → Rugix over the air without reflashing (C-W3-039, C-W3-040). That is the exact migration OneMind must do in 2029–2030.
- **Docs and response speed:** maintainer replies on #120–#122 the same day they were filed. Note, though, that the issues are still open three months later.

### 2.6 Longevity to 2036
- **The exit does not depend on the vendor.** Apache-2.0/MIT, a public commitment to keep those licences (item 7), documented bundle and boot formats, and **RAUC- and Mender-compatible boot flows** with a cross-flow test (item 3). If Silitics stopped in 2030, OneMind could move to RAUC with an update, which is the same exit 01 relies on in the other direction.
- **Interested parties beyond Silitics:** Umbrel (consumer appliance, reporter of GHSA-f8wx), thin-edge.io/Cumulocity (IIoT), Nexigon and NixOS integrations. A fork would have users to share the cost.
- **Paid LTS exists** for "selected versions", which is more than a pure community project offers. It has no price and no duration yet.

## 3. Steelman re-score (frozen S2 anchors, weights C1 20 · C2 20 · C3 15 · C4 15 · C5 10 · C6 10 · C7 10)

| Criterion | 01 corrected | Steelman | Reason (anchor test) |
|---|---|---|---|
| C1 Longevity | 2 | **2** | One maintainer, LTS unpriced. Anchor 3 needs a bounded-cost path to 2032+. Not met. *Conceded.* |
| C2 Hardware/robotics | 2 | **2** | x86 + Pi 5 native; Jetson via NVIDIA for both engines. Equal to RAUC. |
| C3 Security/update safety | 3 | **3** | Anchor 4 needs revocation. Rugix has rotation (multi-root) and a native systemd-boot + TPM path, but **no revocation**. Stays 3, now *closer* to 4 than RAUC on the Secure Boot/TPM item. |
| C4 Proven in production | 3 | **3** (4 arguable) | umbrelOS (constraint-matched, code-pinned) + thin-edge.io (independent IIoT, code-pinned) + industrial integrations; ≥3 failure reports read (#2153, #117, #136). Anchor 4 needs **three shipping products** confirmed. thin-edge is a framework, and enmo / Strato Pi are vendor-stated. One more code-confirmed industrial product makes it 4. |
| C5 Solo-dev operability | 3 | **4** | Declarative Bakery recipes, one toolchain for x86 + Pi, Mac build in 5–12 min in our lab, built-in state and encryption. Anchor 4 literally names "a Bakery recipe". RAUC needs a second tool for the same job. |
| C6 Cost/licence | 4 | **4** | Apache-2.0/MIT, free delta updates. |
| C7 Ecosystem | 2 | **3** (contested) | thin-edge.io/Cumulocity, Nexigon, Memfault, RevPi, Strato Pi, Yocto and NixOS integrations. The community is still small (171 stars), so 3 is the generous reading. |
| **Weighted total** | **52.0** | **56.0** | vs RAUC **58.0**, Mender 57.0 (01 §3.2) |

With C7 held at 2 the total is 54.0, still inside the band against Mender and 4 points behind RAUC. Under 01's protocol a gap of 3 points or less is a **tie**, settled by the decision-critical evidence:

| Tie-break item (01 §3.2) | RAUC vs Rugix |
|---|---|
| DC-09 Jetson base | Neutral: NVIDIA A/B for both |
| DC-06 Maintainers | **RAUC.** Re-measured 168/169 commits by one author (item 9) |
| Cost (C6) | Neutral: both have free deltas |
| Proof (constraint-matched appliance) | Neutral: HAOS ↔ umbrelOS; Rugix also has an IIoT adopter and our lab ran it with a real k3s gate, which RAUC has not done (01 §8) |
| Not in 01's list but decision-relevant | **Rugix:** Pi 5 tryboot native; TPM data + systemd-boot native (removes spike X-2R risk) |

**Honest conclusion:** Rugix ties RAUC, and wins every engineering tie-break except maintainer depth. Whether RAUC stays the lead depends on how much weight the founder gives to bus factor over build effort. 01's choice of RAUC is defensible. So is Rugix.

## 4. Genuine weaknesses (stated without spin)

1. **Bus factor ≈ 1, and not improving.** 168/169 commits in the last 6 months; all PRs self-merged; review appears to be by AI ("Address GPT-5.6 review"). No named second engineer at Silitics.
2. **No continuity guarantee.** The Support Commitment and Open Source Commitment pages say nothing about succession, escrow or a foundation. LTS is "selected versions" with no price or term.
3. **Latest-minor-only security support**, and SECURITY.md still lists 1.0.0 as the supported version while 1.4.0 is current. OneMind must follow every minor release, and 1.x minors do carry breaking changes (e.g. 1.4's Compose store format).
4. **Advisories are GHSAs without CVE IDs.** CVE-feed scanners miss them. Two High trust-path flaws in October 2026 (bundled WebPKI roots; unverified execute payloads).
5. **Missing security features:** no revocation (CRL or signer list), no encrypted bundles (#120 open), and anti-downgrade only through component constraints described in an issue comment (#121), not a documented monotonic floor.
6. **Silent hang, still open:** getumbrel/umbrel#2153 (update stuck at 93% with no timeout) still reproduced on umbrelOS 2.0.1 on 2026-11-03.
7. **Default boot flows have no boot counter** (C-W3-005). A watchdog and gate are needed whatever engine is used, but RAUC's GRUB setup gives counted tries out of the box.
8. **CLI only, no D-Bus/REST API** (C-W3-016); Rugix Apps and Rugix BSPs are experimental.
9. **Fork cost is real:** about 47k lines of Rust written by one person.

## 5. What evidence would make Rugix the winner

Any **one** of A–C flips the DC-06 tie-break to Rugix (it then wins the tie on Pi 5, TPM and solo-dev cost). D and E add points but do not decide it alone.

- **A. A second maintainer:** a second human with merge rights who lands ≥10% of default-branch commits, or approves the maintainer's PRs, over 6 months.
- **B. Continuity in writing:** Silitics publishes named Rugix staff, a succession or escrow commitment, or a priced LTS with a stated term (e.g. a 3-year branch).
- **C. Shared ownership:** Umbrel, Cumulocity/thin-edge.io or another adopter commits code upstream on a sustained basis, or Rugix joins a foundation (LF Edge, Eclipse IoT, OpenSSF).
- **D. Security features close:** native signer revocation **and** a documented anti-downgrade floor ship in a release (lifts C3 to 4: +3.0). Advisories begin to receive CVE IDs.
- **E. RAUC stumbles in our lab:** the RAUC Pi 5 custom tryboot backend or spike X-2R (signed UKIs + LUKS2/TPM after update and rollback) fails or needs a layout change, while Rugix's native flows pass the same test (T-W3-01 / X-2R run on both engines).

Any one of these makes Rugix less likely: no commits for 90 days; a licence or ownership change; a third verification-bypass advisory; #2153-class hangs left unfixed upstream.

## 6. What OneMind loses nothing by doing now (either engine)

Keep the engine-neutral layout from 01 §4.3; run X-2R and the Pi 5 tryboot spike on **both** engines; watch GHSAs as well as CVEs; and keep the OneMind release contract (manifest, monotonic counter, signing, gate) above the engine, so that this decision stays reversible by update.

## Sources opened for this file

- rugix/rugix@6d7fc277 (v1.4.0): `CHANGELOG.md#L75-L95`, `#L150-L156`; `SECURITY.md#L13-L23`; `schemas/rugix-ctrl-config.schema.json#L40-L52`; `schemas/rugix-ctrl-component.schema.json#L25-L36`; `crates/apps/rugix-ctrl/schemas/system.sidex#L52-L70`; `crates/apps/rugix-ctrl/src/system/boot_flows/systemd_boot.rs#L1-L5`, `#L128-L147`; `tests/test_data_encryption_tpm.py#L48-L66`; `tests/test_boot_flow_compatibility.py#L22`, `#L60`; `tests/test_update_interruption.py#L18`
- GitHub API (2026-11-11): rugix/rugix commits since 2026-05-10, contributors, releases, issues #117 #120 #121 #122 #136 and their comments, security advisories
- https://github.com/rugix/rugix/releases/tag/v1.4.0 (release notes)
- thin-edge/thin-edge.io@5d3ac4a7: `docs/src/extend/firmware-management/building-image/rugix/index.md`, and the `building-image/` listing (`rugix`, `yocto` only)
- thin-edge/meta-tedge@ac9b42bf: repo root (meta-tedge-rugix, -rauc, -mender), `kas/projects/tedge-rugix-tpm2.yaml`, `kas/config/rugix.yaml`
- thin-edge/tedge-rugix-image@00ace2ea: `README.md`
- getumbrel/umbrel@c43beed9: `packages/os/build.sh#L5-L8`, `#L37-L40`; `packages/os/rugix/layers/umbrelos-pi.toml`; `packages/umbreld/source/modules/update/rugix.ts`; issue #2153
- rugix/rugix-example-revpi@366dc643, rugix/rugix-example-stratopi@5c5ece23, rugix/meta-rugix@2e501d93, rugix/rugix-bsps@37c62d8b (READMEs)
- https://rugix.org/commercial-support, https://rugix.org/support-commitment, https://rugix.org/open-source-commitment
- https://www.automationworld.com/cybersecurity/article/55399785/industrial-iot-security-designing-ota-updates-that-recover-from-failure (2026-08-21, vendor co-authored: SECONDARY)
