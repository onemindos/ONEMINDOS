# 26 · Open questions for Zeus

**Created:** 2026-11-10 by DEC (Tier A). Later workstreams **append** sections; don't reorder the IDs. **Final for this run (2026-11-11, tag FINAL):** §F adds the revision-3 updates and Z-28…Z-37, and §G maps every `blocked: founder-decision` item in `24-…` to a Z-ID, so this file now covers all of brief §6 (REQUIREMENTS open questions 2–5 in §B, the Blueprint questions in §C, RS-6 access in §D, §E and §F). The approval boxes are in [`REVIEW-CHECKLIST.md`](REVIEW-CHECKLIST.md); the week each decision is due is in `20-…` §2.3.
**Revision 4 (2026-11-11, DEC4):** §H re-states the base-OS question under the frozen scorecard rules and adds **Z-38…Z-40**; it also updates Z-01 and Z-10 (IDs unchanged, appended, not reordered).
**Revision 4.1 sync (2026-11-11, SYNC5-a):** follows `01` rev. 4.1 (no score or ranking change; D stays the decision of record). §I adds **Z-41** (run the Ubuntu Secure Boot test LT-VM-20 yourself, or approve an Ubuntu mirror for the lab), an RS-6 row for the Ubuntu archive block, and the blind refuters' additions to Z-01. Z-10 and Z-38 now name U-SB as a deciding event, §G maps Q288, and Z-28 names every pushed commit.
**How to use this file:** each item gives the question, the options, a recommendation, and what is blocked until you answer. Where the brief told us to assume an answer (rule 8), the assumption is stated and the work proceeds on it. Items marked **(legal)** need counsel, which is not legal advice from this research.
**Serves requirements:** RS-6, R-1, R-3, D-001, H-1, M-8, F-11, F-12, N-9, U-4

> ### Explain it like I'm the founder
> The research could decide most things from evidence. These are the ones it can't: they depend on your money, your risk appetite, a lawyer, or access we didn't have. Each has a recommendation, so you can say "yes" and move on, or pick another option. The first six matter before any code ships; the rest can wait weeks.

---

## A. Founder decisions from the Tier A foundation work

### Z-01 · Ask Canonical and counsel about redistributing modified Ubuntu (legal) · Q-W2-1, Q168, Q57
**Why it matters:** Canonical's policy says modified Ubuntu may be redistributed only if "approved, certified or provided by Canonical"; otherwise trademarks must be removed **and** binaries recompiled [C-W2-050]. This decides whether Ubuntu can become the core (it led the raw scorecard) and affects the GPU-server flavor and possibly the Jetson flavor (NVIDIA's L4T Ubuntu, modified by OneMind). Ubuntu Pro for Devices has no public price [C-W2-006].
**Options:** (a) ask counsel for a reading and Canonical for terms plus a Pro for Devices quote at 1k/10k units (*FIX4:* also ask whether trademark use for a modified image is sold only inside Ubuntu Pro for Devices, whose contents list "Trademark use" [C-FIX4-001], and whether it requires a Canonical kernel, as Canonical's device certification does [C-FIX4-002]); (b) don't ask; ship only Debian and NVIDIA's own images; (c) ship Ubuntu flavors with trademarks stripped and accept the recompile risk.
**Recommendation: (a), now.** It costs little, and the answer either re-opens Ubuntu as the core or confirms Debian. A draft for Canonical is in `evidence/outreach-drafts.md` (O-1).
**Blocked until answered:** shipping any Ubuntu-based OneMind image (GPU-server flavor; check the Jetson flavor too). **Assumption meanwhile:** Debian core; Jetson stays on NVIDIA's L4T.

### Z-02 · Security updates on by default? (CRA vs R-1) · SEC-05, Q221
**Why it matters:** the EU Cyber Resilience Act expects automatic security updates by default, with an easy opt-out [C-W6-008]; the draft OS standard makes that testable [C-W6-019]. ADR-001 and R-1 say "never auto-install".
**Options:** (a) the security channel installs automatically by default (opt-out, postpone, maintenance window, health-gated, rolls back by itself); feature updates stay manual; (b) keep manual by default everywhere and accept EU compliance risk; (c) auto only for EU-sold SKUs.
**Recommendation: (a).** Rollback makes it safe, and R-1's intent (the owner stays in control) is kept by the opt-out and window. Robots and field kits get a "mission-safe reboot" rule.
**Blocked:** the update UX spec and the CRA technical file.

### Z-03 · Update engine: RAUC (recommended), Mender or Rugix (see §E and §F for the rev. 2–3 updates)
**Why it matters:** Rugix is the most convenient fit (Umbrel's tool, builds images from a Mac, free deltas) but has one active developer (303/304 commits) [C-W3-001]. RAUC runs Home Assistant OS. Both passed our lab [C-LAB-rauc-015, C-LAB-debian-rugix-022].
**Options:** (a) RAUC lead, Rugix-compatible layout; (b) Rugix lead with the same layout and signing design; (c) decide after the Beelink/Dell power-pull test.
**Recommendation: (a)**, keeping the layout engine-neutral so the switch stays an update, not a reflash.

### Z-04 · Signing-key custody and ceremony · Q35, Q235
**Options:** (a) offline root in a hardware key/HSM held by you, 2-of-3 release signers (one can be your Mac's Secure Enclave), a written succession/escrow plan; (b) cloud KMS; (c) a single key in CI (Home Assistant's release key lives in CI secrets).
**Recommendation: (a)**, plus a CA rotation drill before the first box ships. Also decide whether owners can take over their box's Secure Boot keys ("sovereign mode").

### Z-05 · Open-core boundary vs the CRA self-assessment route (legal) · D-001, SEC-06
**Why it matters:** an OS is a CRA "important, Class I" product [C-W6-011]; without a cited standard, Class I needs an outside auditor unless the product qualifies as free and open-source software [C-W6-012, C-W6-013]. Refuters showed a fully FOSS image is not achievable on Pi 5 or Jetson (non-free firmware), and that the boxes may not count as "operating systems" at all.
**Options:** (a) keep every OneMind-authored part of the base image Apache-2.0 and keep paid features as separate apps; get counsel's opinion on classification and firmware blobs; decide the route by 2027-Q2; (b) put paid closed features in the base image and budget a notified body; (c) wait for EN 304 626 to be cited.
**Recommendation: (a)**, which also keeps D-001's promise.

### Z-06 · Support period per SKU · DC-04, SEC-07
**Options:** (a) declare at least 5 years from end of sale per SKU, capped by that board's kernel window (Jetson SKUs shortest), met by in-place Debian rebases; (b) one fixed period for all SKUs; (c) buy paid extensions (ELTS, which is quote-only and own-use-only as written [C-W2-004]).
**Recommendation: (a).** Also approve outreach for a Freexian ELTS quote that covers arm64 and redistribution.

### Z-07 · k3s floor for small boxes · N-9 (REQUIREMENTS open question 2)
**Options:** (a) k3s server on ≥ 8 GB, 4 GB + SSD as a limited profile, SD-only or smaller = NATS leaf; (b) k3s on every ≥ 4 GB box; (c) Compose/Quadlet on Lite and k3s above (breaks "one OS", F-14).
**Recommendation: (a)**, confirmed by a Pi 5 4 GB/8 GB soak on NVMe. This answers REQUIREMENTS open question 2: "Kubernetes on every box OneMind sells; NATS leaf on devices it only connects".

### Z-08 · When to add RKE2 (and the public-safety tier) · DC-24, Q215
**Options:** (a) one distribution (k3s) until a buyer needs FIPS/STIG or an AI-conformant GPU cluster; (b) build RKE2 alongside from day one; (c) k0s instead of RKE2 for the AI-conformant slot.
**Recommendation: (a)**, with k0s in the hardware bake-off. If you keep public safety in year-1 scope, say so: it pulls FIPS 140-3 work forward [C-W6-028].

### Z-09 · GPU-server (Omni/Cluster) flavor on Ubuntu + RKE2
**Options:** (a) allow it once Z-01 is answered; (b) Debian everywhere and accept NVIDIA friction (no GPU Operator lifecycle, no AI-conformance listing) [C-W4-022, C-W4-038]; (c) defer Omni.
**Recommendation: (a).**

### Z-10 · Fund the bootc Industrial profile? · F-12, F-11
**Options:** (a) year-2 Industrial profile on CentOS Stream/AlmaLinux/RHEL image mode, with Fedora IoT as a CI canary now; (b) no Red Hat track; (c) make bootc the base (needs a proven Pi 5 path first).
**Recommendation: (a).** Answers your Fedora IoT question: valuable as a profile, not the base today.

### Z-11 · Industrial certification route · W8 P0-2, F-11
**Options:** (a) partner with an already-certified platform (CIP members, Moxa-class vendors, Red Hat Device Edge) for the first industrial SKU; (b) build OneMind's own IEC 62443-4-1 process (a security response team plus a certified development process) first.
**Recommendation: (a)** until there is revenue to fund (b).

### Z-12 · Default TAK server, and where TAK lives after the DOKS conversion · Q259
**Options:** (a) TAK Server container (GPL-3.0; 8 GB Pi minimum per TAK); (b) OpenTAKServer (GPL-3.0, lighter); (c) CloudTAK only. After conversion: TAK at home, or cloud as a relay.
**Recommendation:** (a) on 8 GB+ boxes, (b) on 4 GB profiles; keep the cloud TAK as a relay until the home bus becomes the authority.

### Z-13 · What "mirror" (UX-6) means · Q300
**Options:** (a) backup to another box; (b) warm standby (continuous restore, fencing, one-click promote); (c) live HA (needs 3+ nodes).
**Recommendation: (b)** as the default meaning, with (c) only on 3+ node households.

### Z-14 · Platform first or image first? · Q286, DC-22
**Options:** (a) platform first inside an image-first plan (core as a script install on Debian weeks 1–4, image from the same layers from about week 3); (b) image first; (c) platform only, image later.
**Recommendation: (a).** Evidence is mixed: Home Assistant shipped its platform years before its OS [C-W18-062]; Umbrel shipped a Pi image first [C-W18-063].

### Z-15 · Fusing policy for Pi 5 and Jetson
**Options:** (a) fuse only OneMind-built hardware, after a soak on test-fused units, with HSM-held keys; (b) never fuse; (c) fuse all.
**Recommendation: (a).** Fusing is irreversible.

---

## B. REQUIREMENTS open questions 2–5 (`docs/REQUIREMENTS.md`)

| # | Question | Options | Recommendation |
|---|---|---|---|
| 2 | Kubernetes everywhere, or a hybrid? | see Z-07 | Kubernetes on every box sold; NATS leaf on connected devices |
| 3 | Licence model for OneMind's own code | Settled by D-001 (Apache-2.0 open core). Still open: which features are "pro" | Write the pro/open ADR before the first paid feature, consistent with Z-05 |
| 4 | First hardware tier and customer segment | (a) Lite x86 mini PC for homesteaders/self-hosters; (b) Pi 5 Edge greenhouse/TAK profile; (c) Pro GPU box | **(a) first** (most lab-proven path: x86 + RAUC + k3s), **(b) as the second profile** in the same release (D-002 keeps all tiers in design). **Final pass:** W10 and W16 now agree. Year 1 sells no OneMind-branded box, only a certified-hardware list (`11`, `20` D-P6.6). The first segments are homestead/greenhouse and self-hosting families on Edge/Lite, then TAK field teams (REC-W16-08). The segment is confirmed by interviews (LT-BIZ-04). See Z-31 |
| 5 | First OneMind internal app | (a) the Blueprint's first vertical slice (sign-in, site status, Legacy summary, an approved HA light toggle, TAK observation, offline sync, restore); (b) a single module | **(a)**: it exercises identity, the capability gateway, approvals, NATS, TAK and restore, i.e. the foundation itself |

## C. Recurring Blueprint questions (`context/02` §21)

| Question | Options | Recommendation |
|---|---|---|
| Is Google/Pixel hardware acceptable (GrapheneOS as the security baseline)? | yes / no / Pixel for field devices only | **Yes, for field EUDs (W14, final):** a carrier-unlocked Pixel 9a or 10a with GrapheneOS, which lists 21 supported Pixels [C-W14-001] (REC-W14-01). The Pixel Tablet is a base-station display only, because it has no GPS (REC-W14-02). This becomes the default only after the GrapheneOS + ATAK test (`15` Appendix A, REC-W14-03) passes. Q-W14-2 |
| What state is the Dell 5540 in? | Known: i5-1345U, 16 GB, Windows, and its BIOS supports custom Secure Boot keys and TPM 2.0 [C-W10-043]. Unknown: whether those are enabled on your unit, and the SSD | Run **LT-X86-00** (`22` §3; 30 min from a Debian 13 live USB, `20` day 2) and record the result. Boot the OneMind tests from a spare USB SSD so the Omarchy pilot install is never wiped (`22` §1) |
| What is the first vertical slice? | see B-5 | The Blueprint's seven-step slice |
| Which task system? | (a) Todoist kept; (b) self-hosted Vikunja (AGPL-3.0 [C-W12-114]) or Plane (AGPL-3.0, amd64-only [C-W12-113]); (c) a thin OneMind Tasks module | **(c), with Vikunja as an optional Market app (W12, `13` §8):** build a thin Tasks module over Markdown/SQLite, with a Todoist import, exposed to AI as `tasks.read` / `tasks.create`; deleting a task needs approval. Keep Todoist until the module ships (wave 2 in Q267) |

## D. Access and inputs we needed but couldn't get (RS-6)

| Needed | Why | What Zeus can do |
|---|---|---|
| Live DOKS cluster (read-only) | Verify storage, LB, ingress and Helm/Argo ownership before the conversion plan | Run the read-only commands in `05-…` §9.2 (kubectl/doctl/argocd) |
| Founder hardware: Pi 5 (4 and 8 GB, NVMe), Jetson Orin Nano Super, RTX box | Pi 5 tryboot, Jetson A/B gate (T-W3-06), k3s soak, GPU driver on Debian, real-time latency | Buy the Pi 5 and Orin Nano; run the tests listed in each workstream file |
| Real power pulls on the Beelink U55 / Dell 5540 | QEMU's kill doesn't drop disk write caches | Run T-W3-01 (10 pulls per engine) |
| Vendor quotes: Canonical Pro for Devices, Freexian ELTS (arm64, redistribution), Red Hat RHEL/RHDE | Cost to 2036 (DC-03) | Approve the outreach drafts already written in `evidence/outreach-drafts.md` (O-1 Canonical, O-2 Freexian, O-3 Red Hat, O-4 NVIDIA) |
| Counsel | CRA classification, FOSS route with firmware blobs, Ubuntu redistribution, repackaging upstream apps, UK PSTI | Brief counsel with Z-01, Z-05 and 07 §13 |
| Blueprint originals (Nov 3–4) | Only the summary in `context/02` was available | Share the originals for the plan (A01–A24 tests) |
| Paywalled standards (EN 18031 clause text, IEC 62443) | Only catalogue metadata could be cited | Buy if a certification route is chosen (Z-11) |
| CIP wiki (reference hardware, SLTS table) | Behind a bot challenge; not bypassed | Check it in a browser if CIP becomes the industrial kernel |
| New Wayback captures | Blocked by the run's permission policy | Optional: save the ARCHIVE-GAP pages listed in `evidence/sources/*.md` |

---

## E. Founder decisions from the wave-2 adversarial pass (added 2026-11-11 by DEC, revision 2 of `01-…`)

> ### Explain it like I'm the founder
> The second round of attacks on the plan didn't knock anything over, but it showed where the plan leans on *your* choices rather than on evidence. Three earlier items grew: Z-01 now covers your Jetson robots, Z-03 now has Mender as a serious runner-up, and Z-04 now includes the keys that sign drivers and plugins. Twelve new items follow. Each has a recommendation you can accept as is.

**Updates to earlier items (IDs unchanged):**
- **Z-01 now covers the Jetson flavor.** A OneMind Jetson image is a modified L4T Ubuntu, and NVIDIA's forum defers its Ubuntu rootfs to Canonical's terms [C-REF-DC-cost-007, C-LIC-011]. Ask Canonical about **both** the Jetson image and a possible Ubuntu core. NVIDIA's own BSP licence is now verified: the unmodified BSP may be shipped on NVIDIA hardware with the licence attached [C-LIC-001…003]. The Canonical and Freexian quote requests are drafted in [`evidence/outreach-drafts.md`](evidence/outreach-drafts.md) (not sent; the brief forbids contacting vendors).
- **Z-03 now has three options:** (a) RAUC (recommended; wins the tie-break on Secure Boot, revocation, free deltas, Pi 5 and lab proof), (b) **Mender** (corrected raw score 62.0 vs RAUC 61.0, a tie; strongest on MCU-to-Jetson breadth and a self-hostable fleet server, but deltas and phased rollouts are paid [C-STEEL-updates-mender-015]), (c) Rugix (56.0 at best; one maintainer). **Recommendation: (a), and fund Mender's two tests (a lab spike and a stock-L4T Jetson test) in the 180 days.**
- **Z-04 now includes** the kernel-module signing key (driver packs), the extension (sysext) verity key and the plugin countersigning key, all under the same offline root as RAUC [01 §4.8].
- **Z-05 now distinguishes image and box:** ask counsel whether a OneMind box is classified as an "operating system" or by its own core function, and screen it against the router, VPN, smart-home assistant and identity-management entries [C-REF-W6-technical-008].

### Z-16 · Jetson base: stay on L4T Ubuntu, or move to Yocto meta-tegra? · DC-09, F-2, M-7
**Why it matters:** L4T Ubuntu is easiest for a solo founder and has NVIDIA's full SDK, but it needs Canonical's permission (Z-01) and its life ends with each JetPack branch (JetPack 5 ended on 2026-10-30 [C-REF-W7L-001]). meta-tegra builds Orin and Thor images on a 6.18 LTS kernel with NVIDIA's own out-of-tree modules, and balenaOS ships Orin on it [C-STEEL-jb-002, C-STEEL-jb-010]. Its kernel route is only about four months old and depends on very few maintainers [C-STEEL-jb-004, C-STEEL-jb-006].
**Options:** (a) L4T Ubuntu for the launch beta **and** a meta-tegra lab (LAB-W7-6) within 180 days that decides the default; (b) L4T only; (c) meta-tegra from day one.
**Recommendation: (a).** Buy the Orin Nano Super early; the lab needs it. Flash every Jetson A/B from the start so a later switch is an update.
**Blocked until answered:** the Robotics edition's long-term image; the S2 tie-break (meta-tegra favours Mender).

### Z-17 · Robotics simulation/training GPU boxes: Debian or Ubuntu? · DC-13, N-8
**Why it matters:** Isaac Sim lists only Ubuntu (and Windows) hosts [C-REF-DC-robotics-013], and NVIDIA's driver build has broken on routine Debian kernels [C-REF-DC-cost-009].
**Options:** (a) robotics sim/training boxes on the Ubuntu GPU flavor after Z-01, unless a lab runs Isaac Sim headless on Debian 13 and passes NVIDIA's checker; (b) Debian everywhere; (c) Ubuntu for every GPU box.
**Recommendation: (a).** The general Pro box (local AI, time-sliced) stays Debian.

### Z-18 · x86 boot route for the first image · DC-18, R-1
**Why it matters:** the lab proved two routes. RAUC's GRUB backend gives 3 counted tries and passed with real k3s [C-LAB-rauc-k3s-gate-009]. RAUC's `efi` backend with signed per-slot kernels passed under Secure Boot with no GRUB at all [C-LAB-secureboot-rauc-013], but gives one try per boot attempt [C-LAB-secureboot-rauc-003]. Switching routes on boxes already sold is costly.
**Options:** (a) `efi` + signed UKIs from the first image, if a combined spike (efi + real k3s gate + power cut during the trial boot) passes, else GRUB; (b) GRUB at launch, migrate later; (c) `efi` regardless.
**Recommendation: (a).**

### Z-19 · Secure Boot key model and the kernel it implies · F-7, M-2
**Why it matters:** a key in UEFI db cannot sign kernel modules for a stock kernel; only a key built into the kernel, or a MOK key confirmed at the console, can [C-DEC-008…010]. Driver plugins and NVIDIA modules need one of those under Secure Boot.
**Options:** (a) OneMind's db key enrolled at the factory (setup mode), and for the enforcing release a OneMind-built LTS kernel with the module key built in (K2-hybrid; Jetson keeps NVIDIA's kernel); (b) shim + a OneMind MOK enrolled at the factory, stock Debian kernel (BYO boxes need a console step each); (c) no out-of-tree modules under Secure Boot.
**Recommendation: (a)**, unless test T-W19-03 finds a console-free route on a stock kernel. Also decide whether owners can take over their box's keys ("sovereign mode"), which GPL-3 Installation Information may require on locked consumer boxes [C-LIC-019].

### Z-20 · Fleet server for updates · F-11, N-6
**Why it matters:** RAUC has no fleet server; Mender OSS has one (heavy: 11+ containers plus MongoDB [C-STEEL-updates-mender-003]); Flight Control serves the Red Hat lineage [C-STEEL-IIOT-005].
**Options:** (a) OneMind's own release service on NATS (manifest, channels, revocation) for RAUC, with the W8 10k fleet test choosing a fleet plane in year 1; (b) adopt Mender OSS server now; (c) hawkBit.
**Recommendation: (a)**, and include Mender OSS server and Flight Control in that fleet test.

### Z-21 · Plugin contracts, review staffing and money · DC-16, F-5 (also 29 §20 items 1–2)
**Options:** (a) freeze E1, E2, E3, E4, E7, E9, E10 at v1 and ship E5, E6, E8 as v1-beta; Community tier only for sandboxed plugin types; host-grant plugins Verified or higher; a costed review plan before the Community tier opens; paid-plugin share 0% on the first USD 1M lifetime, then 15% (W19's proposal); (b) freeze all ten now; (c) no third-party plugins in release 1.
**Recommendation: (a).** Review is staffing: Open VSX says its model "cannot continue indefinitely" without funding [C-REF-W19-cost-004]. Also decide whether the Community tier is enabled on the Robotics edition at all (recommended: Verified and higher only).

### Z-22 · Third-party host-level plugins in release 1? · DC-16, U-4
**Why it matters:** host extensions live on the data partition, which A/B never resets. If a test shows that someone with root once can make an unsigned extension merge after a reboot or slot switch, the safe fallback is Flatcar's model: host extensions only inside the signed OS slot [C-W19-005, C-REF-W19-security-004].
**Options:** (a) allow them if T-W19-01's security variant passes, otherwise OneMind-built only; (b) OneMind-built host extensions only in release 1; (c) allow them regardless.
**Recommendation: (a).** Apps, widgets, AI tools and automations are unaffected either way.

### Z-23 · k3s on robots and field kits · N-9, U-4
**Why it matters:** a k3s server holds every Secret and an admin kubeconfig; Kubernetes assumes nodes are physically secure [C-REF-W4-security-008].
**Options:** (a) capturable nodes run the k3s **agent** only, enrolled with TPM-bound or short-lived credentials; servers only on hub-class boxes; (b) servers wherever there are ≥ 4 GB.
**Recommendation: (a).** A single-box home Lite is a server by necessity and relies on its encrypted data partition.

### Z-24 · Sunset the script install · P-7, DC-22
**Why it matters:** Home Assistant, Umbrel and CasaOS each dropped or stalled their script/BYO path [C-REF-DC-longevity-004, C-REF-DC-longevity-005, C-REF-DC-longevity-006].
**Options:** (a) script install is a developer loop, unsupported after image GA; BYO hardware means "flash our image"; (b) keep a supported script path.
**Recommendation: (a).**

### Z-25 · Is FIPS/STIG compliance a P0 product property? · W4 P0-2, DC-24
**Why it matters:** if yes, the k3s/RKE2 tie breaks to **RKE2 on every node with 8 GB or more** (RKE2 has an active FIPS 140-3 certificate, Canal CNI only [C-REF-W4-security-006, C-REF-W4-security-007]); k3s also crashes in Go's FIPS-only mode today [C-REF-DC-longevity-010].
**Options:** (a) no FIPS/STIG requirement before the public-safety tier is sold; CJIS AES-256 under FIPS 197 as the day-1 answer; (b) compliance is P0 from year 1.
**Recommendation: (a)**, unless a named public-safety buyer is in year-1 scope.

### Z-26 · Desktop (Hyprland) edition plugins · UX-10, A-6 (29 §20 item 3)
**Options:** (a) accept Omarchy's manifest shape, Verified publishers only, off by default; (b) a OneMind fork of the manifest; (c) no desktop plugins.
**Recommendation: (a)**, as W19 proposes.

### Z-27 · Pull two industrial tests forward? · F-11, F-12
**Why it matters:** the EL10 bootc steelman would flip the industrial recommendation if FDO onboarding and fleet simulation clearly favour it [C-STEEL-IIOT-001, C-STEEL-IIOT-007].
**Options:** (a) run LAB-W8-4 (FDO onboarding with TPM) on **both** Debian and AlmaLinux 10 bootc, and a Flight Control `devicesimulator` run, within 180 days; (b) leave them for the year-2 Industrial profile.
**Recommendation: (a).** Both are cheap VM tests and could change which base the first industrial SKU uses.

### Access and inputs added in revision 2 (RS-6)

| Needed | Why | What Zeus can do |
|---|---|---|
| Jetson Orin Nano Super (and later a second Orin module) | meta-tegra LAB-W7-6; Mender stock-L4T test; RT variance between two modules [C-REF-DC-robotics-005] | Buy early in the 180 days |
| Dell 5540 in firmware setup mode | Secure Boot on real firmware, option ROMs, power cut under Secure Boot (F-SB-1…3) | Run the tests in `evidence/lab/secureboot-rauc/README.md` §11; back up the factory keys first |
| A RAUC ≥ 1.15.2 package for Debian 13 | Every RAUC lab ran Debian's 1.13 [C-LAB-rauc-k3s-gate-005] | Approve building it from upstream in CI |
| Counsel time | Image vs box CRA classes, Ubuntu for Jetson, GPL-3 Installation Information on locked boxes | Brief counsel with Z-01, Z-05 and Z-19 |

---

## F. Final pass: revision-3 updates and the remaining founder decisions (added 2026-11-11, tag FINAL)

> ### Explain it like I'm the founder
> Revision 3 of `01` ran the fair fight the reviewer asked for: Ubuntu and Mender sat the same lab exam that Debian and RAUC had passed. All four passed, so the leads held but got narrower. That changes the evidence behind four earlier items, listed first below. After that come ten new items (Z-28…Z-37). They gather every question in the answer sheet (`24-…`) that only you can settle. Most are small; **Z-28 is the urgent one**, because personal data from an early commit is still readable in the public branch history.

**Updates to earlier items (IDs unchanged):**
- **Z-03 (engine):** Mender now has a lab pass on the same battery. Stock Mender gives a new version **one** trial boot where RAUC gives three, and a power cut during that boot discarded a good update [C-LAB-mender-013]. RAUC wins the recount 5–3 (`01` §3.2). Whichever engine you pick, OneMind ships **its own RAUC built from a pinned upstream tag** (today v1.15.2), because Debian's RAUC 1.13 cannot install any update on kernels 6.19 or newer [C-LAB-ubuntu-2604-leg-010, C-LAB-rauc-1152-011] (REC-DEC-31). No shipped product combines Debian or Ubuntu with RAUC [C-DEC-013], so the hardware tests are release gates (REC-DEC-34). **Recommendation unchanged: (a) RAUC, decided at gate G1 (week 4).**
- **Z-05 (CRA route):** add a **notified-body pre-assessment as a parallel track from 2027-Q1**, with the FOSS self-assessment route still primary (`01` §6.13, REC-DEC-39). Also ask counsel **Q-COST-1**: does a major Debian rebase count as a "substantial modification"? (See Z-36.)
- **Z-06 (support period):** Freexian's ELTS contract is own-use only, so shipping ELTS packages to customers' boxes needs an OEM-style agreement (**Q-W2-2**, [C-W2-004]). The quote request is part of Z-37.
- **Z-10 (bootc):** on the fully cited scorecard, RHEL-family bootc is the raw S1 leader (64 vs 62 vs 60), on one documentation-only Pi 5 cell [C-SCORE-025]. **Approve running W2-HW-3 (bootc on a real Pi 5, `22` LT-PI5-02) early, at gate G2.** It decides whether that lead is real (REC-DEC-33).

### Z-28 · Purge leaked personal data from the public branch history? · Q-P2-5, critic N1/N2 · **urgent**
**Why it matters:** all four commits on the public research branch are pushed (`414d60a`, `ee98bc7`, `7836316`, `b933b86`) [C-SYNC5-a-001]. A per-commit scan (`evidence/hygiene-log.md` §3) found [C-SYNC5-a-002]:
- **`414d60a`** contains the lab computer's home path and **account name** in 17 files, VM-internal **private addresses** in 11 files, and the host's folder layout in 16 files.
- **`ee98bc7`** adds the host folder layout (no account name) in 3 files, and its snapshot holds it in 11.
- **`7836316`** adds it in 2 more (a critic file and the hygiene log's grep pattern); its snapshot holds it in 13.
- **`b933b86`** (rev. 4, the branch head) holds it in 3 files: two critic files and the hygiene log. These are masked in the working tree (SYNC5-a), but the pushed commit keeps them.

No commit contains a tailnet name or a CGNAT address. The working tree is masked, but git history still serves the old text. A rewrite that only fixes `414d60a` removes the account name; removing the folder layout too means rebuilding all four commits. Removing it requires rewriting history, and the brief forbids force-push (§8) unless you allow it.
**Options:** (a) allow a one-time history rewrite of `research/ultracode-foundation` (rebuild **all four** pushed commits from masked trees, force-push once, then ask GitHub support to purge cached views); (b) squash-merge the PR and delete the branch, which leaves `414d60a` reachable on GitHub until it is garbage-collected; (c) accept the exposure (the data is a username and throwaway VM addresses, not credentials).
**Recommendation: (a), before the PR is marked ready or merged.** It is the only option that actually removes the data. The exposure is low-harm, but rule 5 is absolute. **Blocked until answered:** marking the PR ready for review.

### Z-29 · Trademark clearance for "OneMind" / "OneMind OS" (legal) · Q174
**Why it matters:** the search could not run. The USPTO API and its mirrors refused scripted access, and a similar AI brand ("1mind") reportedly has filings [C-W16-054, UNVERIFIED].
**Options:** (a) a trademark attorney clears the name (US classes 9, 42, 38, 35; EU and UK) before any public beta branding; (b) proceed and rebrand if challenged.
**Recommendation: (a)**, scheduled as LT-BIZ-02 in weeks 2–3 (`20` §5). Debian's marks may only be used for factual compatibility statements, never in a product name [C-W16-011]. **Blocked:** packaging, domains and the beta's public name.

### Z-30 · Company entity and jurisdiction (legal/tax) · Q197
**Why it matters:** NVIDIA Inception requires an incorporated company and its incorporation date [C-W16-031], so D-006 waits on this. Home Assistant's long-term model is a Swiss non-profit foundation funded by commercial partners [C-W16-012]. Some grants depend on the applicant's country, for example NLnet [C-W16-047].
**Options:** (a) incorporate now (counsel chooses US C-corp or LLC), and consider an EU entity later for CRA representation and a foundation in years 3–5; (b) stay unincorporated until revenue.
**Recommendation: (a)**, because Inception, vendor agreements (Z-01, Z-37) and CRA manufacturer duties all need a legal entity. Not tax or legal advice.

### Z-31 · First segment and the first 100 customers · Q282, REQUIREMENTS open question 4
**Options:** (a) homestead/greenhouse and self-hosting families on Edge/Lite first, with TAK field teams second (REC-W16-08); (b) TAK and public safety first; (c) robotics developers first.
**Recommendation: (a)**, tested before any money is spent: run about 30 interviews (LT-BIZ-04, weeks 3–16), then a pre-order test after the 180 days. Hypothesis: a Greenhouse + TAK field kit (a Lite hub plus Pi leaves), sold direct with a year of support. Olares One raised USD 2.34M on Kickstarter, which shows crowdfunding works in this category [C-W16-018]. Public safety (b) pulls FIPS, NDAA and TAA work forward (Z-08, Z-25, REC-QB-01).

### Z-32 · Desktop (Omarchy/Hyprland) edition: client or its own OS image? · Q284, Q-W11-2 (pairs with Z-26)
**Options:** (a) a OneMind client and plugin pack for stock Omarchy; (b) a OneMind Arch image; (c) later, a bootc desktop node, only if users ask for it.
**Recommendation: (a) now, (c) only on demand.** Omarchy ships about 32 releases a year, its Arch mirror runs a month behind, and its plugins are unsandboxed (`12`, C-W11-047…050). Owning that image would be a second OS to maintain.

### Z-33 · Run a minimal OneMind APNs relay now? · Q-W11-1 (D-005 vs M-1)
**Why it matters:** APNs only accepts pushes signed with the app developer's key [C-W11-027], so instant iOS alerts need a relay that OneMind operates. M-1 says a OneMind cloud comes "later".
**Options:** (a) yes: content-free and open source; (b) no: iOS fetches alerts when the app opens; (c) use a third-party upstream (ntfy.sh).
**Recommendation: (a)** (`12` §19). It carries no content, and D-005 already chose APNs.

### Z-34 · Default remote access: Tailscale or Headscale? · Q-W11-3
**Options:** (a) Tailscale's hosted control plane; (b) Headscale on the box; (c) the user chooses at setup.
**Recommendation: (c)**, defaulting to Headscale on Pro boxes and Tailscale for the simplest setup (`12`).

### Z-35 · Sell a pre-provisioned kids' tablet bundle? · W13-N3, U-3
**Why it matters:** an Android device-owner tablet must be provisioned at first setup or after a factory reset [C-W13-008]. On iOS, an outside app needs Apple's Family Controls entitlement and a guardian's approval [C-W13-004].
**Options:** (a) document bring-your-own on the child-device ladder only (levels L1–L3, REC-W13-04) in year 1; (b) also sell an L4 managed kids' tablet (Headwind MDM, QR provisioning) once T-W13-2 passes; (c) sell the bundle from launch.
**Recommendation: (a) in year 1, then (b) if T-W13-2 passes** (W13-N2 is blocked on founder hardware). A bundle also adds hardware, support and COPPA scope (Q228).

### Z-36 · Extend the counsel brief (legal) · Q-COST-1, W12-N1, W12-N2, W13-N1 (adds to Z-01, Z-05, Z-19)
Four more questions only a lawyer can answer. Recommendation: put them in the same counsel engagement as Z-01/Z-05/Z-19.
1. **Q-COST-1:** is a major Debian rebase (13 → 14) a CRA "substantial modification"?
2. **W12-N1:** may OneMind offer a runtime converter for a user-supplied Umbrel store URL? umbrel-apps has no licence [C-W12-002]. Until counsel answers: no converter, and nothing copied from umbrel-apps.
3. **W12-N2:** does a self-hosted wellness module make OneMind a "vendor of personal health records" under 16 CFR 318? Until counsel answers: data stays on the box, and OneMind receives none.
4. **W13-N1:** is a box seller an "operating system provider" under California AB 1043/AB 1856, and is the Market an "app store" under Texas SB 2420?

### Z-37 · Approve vendor outreach (quotes and programmes) · W16-N1, Q-W2-2, Q-COST-2, RS-6
**Why it matters:** the brief forbade the research from contacting vendors, so several costs remain unpriced: Ubuntu Pro for Devices, Freexian ELTS for arm64 with redistribution, Red Hat RHDE, a partner to maintain Orin after its last JetPack branch, and whether NVIDIA Inception pricing covers Jetson modules and dev kits.
**Options:** (a) approve and send the drafts as written (`evidence/outreach-drafts.md` O-1…O-4, `evidence/outreach-drafts-W16.md`); (b) send only Canonical (O-1) now.
**Recommendation: (a)**, in week 1, with Z-01 (`20` D-P1.7). The answers feed the lifecycle cost model (`evidence/lifecycle-cost-2036.md`) and the S1 re-open triggers.

### Access and inputs added in the final pass (RS-6)

| Needed | Why | What Zeus can do |
|---|---|---|
| Read-only access to the live cluster and its private repo | Q80 and Q220 are `blocked: live-cluster`; W12-N3 needs the data sources and licences of the live aircraft/ship/hazard workers; the DOKS conversion plan rests on reported state (context/01) | Run `22` LT-CLU-01…11 (read-only, `20` days 2–3) and share the outputs |
| Where you saw the GrapheneOS Pixel Tablet ATAK crash (Q-W14-1) | No public report exists [C-W14-018] | Point to the source, or run `15` Appendix A and capture the tombstone if it reproduces |
| Your ATAK version, plugins and radios (Q-W14-3) | `15` Appendix A needs the real loadout | List them |
| Sites that blocked automated reading: openinventionnetwork.com, the FCC Covered List, the DIU Blue UAS page, EUR-Lex (AI Act annexes, Product Liability Directive), USPTO search | Claims that depend on them are UNVERIFIED (C-QBANK-013, C-W16-054 and others in `24` §10) | Check them in a browser, or give counsel the list |
| KubeCon NA 2026 days 3–4 (after 2026-11-12) | The NVIDIA-on-k3s answer was checked mid-event (critic N12) | Nothing; a re-check is scheduled in `20` |

## G. Every `blocked: founder-decision` item in `24-…`, mapped

`24-…` §9 lists 7 bank questions as `blocked: founder-decision` (rev. 4 moved Q288 there), and §6 lists 15 added questions. Each is decided under the Z-ID shown.

| Item in 24 | Question (short) | Decided under |
|---|---|---|
| Q57 | Ubuntu Core / Ubuntu RT as the robot base, once Pro for Devices is priced | Z-01, Z-37 (price), Z-17 |
| Q167 | CRA support period vs Debian LTS and board kernels | Z-06, Z-05 |
| Q174 | Trademark registrability | Z-29 |
| Q197 | Entity and jurisdiction | Z-30 |
| Q282 | First 100 customers and segment | Z-31 |
| Q284 | Omarchy desktop edition shape | Z-32, Z-26 |
| Q288 | Fedora IoT / bootc vs the Debian or Ubuntu base (DC-01), now a frozen-protocol finalist | Z-38 (base OS), Z-10 (W2-HW-3), Z-40 (scoring rules); U-SB evidence via Z-41 |
| Q-W2-1 | Modified Ubuntu without a Canonical agreement | Z-01 |
| Q-W2-2 | Redistributing Freexian ELTS packages | Z-06, Z-37 |
| Q-COST-1 | Is a Debian rebase a CRA substantial modification | Z-36, Z-05 |
| Q-W11-1 | APNs relay | Z-33 |
| Q-W11-2 | Omarchy pack or Arch image | Z-32 |
| Q-W11-3 | Tailscale or Headscale default | Z-34 |
| Q-W11-4 | What "mirror" means | Z-13 |
| W12-N1 | Umbrel store converter | Z-36 |
| W12-N2 | Wellness module under 16 CFR 318 | Z-36 |
| W13-N1 | CA AB 1043/1856, TX SB 2420 | Z-36 |
| W13-N3 | Kids' tablet bundle | Z-35 |
| Q-W14-1 | Where the Pixel Tablet crash was seen | §F access table (information, not a choice) |
| Q-W14-2 | Is Google/Pixel hardware acceptable | §C (yes, for field EUDs) |
| W16-N1 | Inception pricing for Jetson | Z-37, Z-30 |
| Q-P2-5 | Purge personal data from history | Z-28 |

Questions that are `partial` with a founder-decision blocker (for example Q35/Q200 → Z-04, Q215/Q182 → Z-08/Z-25, Q259 → Z-12, Q300 → Z-13, Q335 → Z-21/Z-22, Q289/Q235 → Z-19, Q165/Q212 → Z-05) are already covered by the Z-IDs named in their rows in `24-…`.

## H. Revision 4: the base-OS result under the frozen rules (added 2026-11-11 by DEC4)

> ### Explain it like I'm the founder
> Before scoring, we locked the contest rules. Revision 3 broke one of them: it brought Debian into a tie it was not part of, after the scores were known, and Debian then won. Revision 4 applies the rules as locked. With two evidence corrections applied equally to everyone, the card is **Ubuntu 26.04 65 · bootc 64 · Debian 63**, and the locked tie-break gives the base to **Ubuntu, 6 rows to 4 over bootc** (`01` §3.1.6). That is a narrow win, and it carries a condition you do not control: Canonical must allow OneMind to ship a modified Ubuntu, or OneMind must strip the brand and rebuild the binaries [C-W2-050]. The rules do not stop you choosing differently. But if you do, it is **your** decision, written down as yours, not "what the scorecard says". Three short decisions follow.

**Updates to earlier items (IDs unchanged):**
- **Z-01 (Canonical and counsel):** this now gates the **decision of record**, not only a re-open. **Assumption meanwhile (rule 8) changes** from "Debian core" to: the protocol result (Ubuntu 26.04 + RAUC) is the default; nothing Ubuntu-based ships before Z-01 is answered; one image definition builds a Debian leg and an Ubuntu leg (`01` REC-DEC-17); and the shipping base is locked at a named gate before the first box ships, using the pre-registered map in `01` §3.1.6 (h). Under that map, a refusal that leaves only debrand-and-recompile, which you reject, gives **bootc**. If W2-HW-3 has also failed, it gives **Debian**, but too narrowly to be settled, so it comes back to you. **Recommendation unchanged: (a), now (week 1)**, and ask for a written price so the risk register's missing cost (RR-09) can be filled [C-DEC4-010].
- **Z-10 (bootc):** **approve W2-HW-3 before gate G1 (week 4)**, not "early in the 180 days". It now decides between the protocol result and Debian. If it fails, the card becomes Ubuntu 65 · Debian 63 · bootc 60, and the locked tie-break gives **Debian** (6–5) [C-DEC4-007]. It also has to come first because a box shipped on Debian/Ubuntu + RAUC cannot move to bootc without a reflash [C-STEEL4-bootc-025]. **Rev. 4.1 sync (critic P5-4):** W2-HW-3 is not the only deciding event. The Ubuntu Secure Boot VM test **U-SB (LT-VM-20)** is the other one, and it needs no hardware. If U-SB fails, or passes only after a partition or bootloader change, the map gives **bootc** (C 64 · A 63 · D 62); if U-SB **and** W2-HW-3 both fail, it gives **Debian** (`01` §3.1.6 h). U-SB was attempted and is BLOCKED here, so it has produced no map event yet [C-FIX5-002]; see Z-41.

### Z-38 · Base OS: accept the frozen-protocol result (Ubuntu 26.04), or override it as your own decision? · Q-P3-1, critic P3-1, ADR-001 D2
**Why it matters:** this is the hardest decision to undo. The disk layout, update engine and signing work are the same for Debian and Ubuntu, but every shipped box carries its base for years. The locked rules give Ubuntu 26.04 + RAUC (D), but only **fragilely**: D wins 11 of 14 weight-shake runs, Debian 2 and bootc 1, and every run is a tie settled by a 6–4 row count [C-DEC4-006]. Rev. 3's case for Debian was real, but it reached the verdict through a rule invented after scoring [C-PROTO4-018].
**Options:**
- **(a) Accept the protocol result as the default, with its conditions** (Z-01 first; both CI legs; base locked at a named gate before the first shipment; the pre-registered map decides on W2-HW-3, Z-01 **and U-SB / LT-VM-20**: U-SB failing gives bootc, `01` §3.1.6 h). Rev. 4.1: three **blind** refuters all returned *weakened*, none refuted, and gate G4 is CONDITIONAL with no failing sub-check, so the result is unchanged [C-G4U-001…011].
- **(b) Choose Debian 13 now, as a founder decision** logged in `evidence/scorecard-weights.md` §8 with the ranking under both rules. *For:* the core image ships without anyone's permission; umbrelOS is a constraint-matched Debian appliance on Pi 5 and x86 [C-W2-043, C-W3-039]; every lab ran on it, now including native arm64 and Secure Boot on RAUC 1.15.2 [C-LAB-aarch64-gate-004, C-LAB-secureboot-1152-005]; it is cheapest at 10k units ($40 vs $120 per device, `lifecycle-cost-2036.md`). *Against:* it loses the locked tie-break to both rivals; it needs the most in-place rebases to 2036; Debian security after 2028 rests on one paid team (Freexian) [C-REF-DC-cost-003]; there are recent Pi 5 trixie boot regressions [C-REF4-S1R4-technical-004, C-REF4-S1R4-technical-005]; and OneMind must sign its own GPU and driver modules under Secure Boot [C-REF4-S1R4-security-005].
- **(c) Choose RHEL-family bootc now.** *For:* raw leader on the rev-3 card, rebase built in, no permission needed [C-STEEL4-bootc-014]. *Against:* its Pi 5 path is one person's experimental repo [C-STEEL4-bootc-001], and the power-cut downgrade is unfixed upstream [C-STEEL4-bootc-024].
- **(d) Defer all choice to the map** at the lock gate. This is the same as (a), but without stating a default.

**Recommendation: (a).** It is the only option the locked rules produce, and it already contains the hedge: the Debian leg is built anyway, and the map sends S1 to Debian if bootc's Pi 5 test fails. Choose (b) only for a reason the rules do not capture, for example that you will not sign any Canonical terms at any price. In that case answer Z-01 "no", and the map, not a fresh argument, decides.
**Blocked until answered:** the base-lock gate in `20-…`, the default base in `30-…`, and the PDF's base-OS chapter. **Assumption meanwhile:** (a).

### Z-39 · Does an unmet, third-party-dependent condition disqualify a candidate? · Q-P3-1 (second half)
**Why it matters:** the locked rules rank a CONDITIONAL candidate and send its mitigation to the plan; only a FAIL removes it [C-PROTO4-002]. Ubuntu's licence condition waits on Canonical, and the risk register gives that mitigation an owner but **no cost**, which the rules require [C-DEC4-010]. The same Canonical condition also sits on the Jetson flavor of Debian and bootc (it is NVIDIA's modified Ubuntu) [C-REF-DC-cost-007].
**Options:** (a) **literal reading (current):** COND stays ranked; fill RR-09's cost when Canonical answers. (b) An uncosted third-party COND counts as FAIL **for every candidate**: Debian, bootc and Ubuntu all drop out through their Jetson flavor, leaving Yocto 54 · Fedora IoT 52 · Ubuntu Core 52 and no rule for a shared second place [C-DEC4-007]. (c) The same reading, **applied per mitigation**: Ubuntu's core has no route except Canonical or a debranded rebuild, while Debian's and bootc's cores need none and their Jetson flavor has the meta-tegra route. Ubuntu drops out, and the rules give **bootc** (6–5 over Debian).
**Recommendation: (a)**, and close the cost gap (REC-DEC-43). Option (c) is a defensible reading, but adopting it is a rule change, so it needs a §8 row. Written now, before Canonical answers, it would be fair. Written after, it would look like fitting the rule to the result.
**Blocked until answered:** nothing immediately. It matters the day Canonical answers, or does not answer by the lock gate.

### Z-40 · Write down four scoring rules before the next tests · Q-P3-2, critic P3-9, protocol ruling REC-PROTO4-04/06
**Why it matters:** four choices the locked file never wrote down each decide S1 on their own (`01` §3.1.6 f–g):
1. **The tie-break counting method:** which rows count, and what settles a draw. The full table gives Ubuntu over bootc 6–4; decision-critical questions only, 4–3; the same plus the licence row, a 4–4 draw.
2. **How "experimental" vendor support scores** in hardware fit (C2): bootc at 3 or 2. At 2, Debian wins.
3. **Whether "proven in production" (C4) in S1 is scored on the base or on the whole stack** including the update engine. Whole stack: bootc wins outright.
4. **Whether a third candidate may ever enter a tie.** The rev-3 rule; recommended: no.

**Options:** (a) adopt the readings `01` rev. 4 used: full-table row count, a draw goes to you, "experimental" with a documented path = 3 `doc-only` until W2-HW-3 measures it, C4 scored on the base layer, no third finalist. Log them as your decision in `scorecard-weights.md` §8 **before W2-HW-3 runs**. (b) Pick different readings, under the same timing. (c) Leave them unwritten: every close result then comes back to you.
**Recommendation: (a), before gate G1.** Any choice made after the Pi 5 result is known looks like fitting the rules to it, which is exactly what the freeze exists to stop.
**Blocked until answered:** a clean protocol result for the "W2-HW-3 passes" branch of the map (`01` §3.1.6 h), which can end in a 4–4 draw.

**Critic pass-3 questions, mapped:** Q-P3-1 → Z-38, Z-39 · Q-P3-2 → Z-40 · Q-P3-3 (OneMind's own RAUC permanent or stop-gap) → Z-03, with RAUC's own concentration now recorded (`01` §5.9.2) · Q-P3-4 (bus factor of AlmaLinux's Pi images) → answered by the bootc steelman: 75 commits, one contributor, 12 stars [C-STEEL4-bootc-001]; it feeds W2-HW-3 and Z-38 (c) · Q-P3-5 (non-primary rows in 01) → answered by `evidence/critic/cit4-mapping.md`: no scorecard cell or tie-break verdict rests only on a SECONDARY row.

### What competitors do (Z-38, constraint fit)

| Competitor | Base and update stack | Their constraints | Fit for OneMind |
|---|---|---|---|
| umbrelOS 2.0 | Debian 13 + Rugix A/B (earlier Mender) [C-W2-043, C-W3-040] | Small company, Pi 5 + x86 consumer appliance, no Kubernetes | **High** for Debian as an appliance base; its engine differs, and post-rebase updates were unreliable in the field [C-REF4-DC-technical-006] |
| Home Assistant OS | Buildroot + RAUC [C-TD-home-assistant-os-003] | Funded team, many SBCs, no Kubernetes | High for the engine; it builds from source rather than on a distribution |
| Bosch ctrlX OS | Ubuntu **Core** (snaps), IEC 62443-4-2 SL 2 per vendor statement [C-SCORE-023, C-CIT4-012] | Large industrial vendor with a Canonical partnership | **Low** for a solo founder: the Canonical relationship is the very thing Z-01 asks about |
| Red Hat Device Edge | RHEL image mode (bootc) + MicroShift, Orin paid [C-W2-041] | Large vendor, enterprise edge, no Pi | Partial: same update model as option (c), not the same market |
| IronFlockOS | Debian 13 + RAUC + Docker, pre-1.0 [C-CIT4-001, C-CIT4-002] | Small company, industrial, no hardware acceptance yet | Watch item: the closest design precedent to Debian + RAUC, not yet proof |

## I. Revision 4.1 additions (added 2026-11-11, tag SYNC5-a)

> ### Explain it like I'm the founder
> Revision 4.1 changed no score. Three new critics who saw only the one-line decision all said "weakened", none "wrong". The test most likely to change the base, the Ubuntu Secure Boot check in a virtual machine (U-SB, lab test LT-VM-20), could not run here: this research computer cannot reach Ubuntu's download servers, and the rules forbid working around that. You can run it on your Mac in about two hours, unattended. That is Z-41.

**Updates to earlier items (IDs unchanged):**
- **Z-01 (Canonical and counsel):** the blind refuters sharpen the question, not the score (`01` §5.1.3). Ask that the permission be **written, for the 10-year life, and not revocable at Canonical's sole discretion**, because the policy says permission "can be revoked at any time" [C-REF5-S1L-001, C-REF5-S1L-002]. Ask which branch ships: Canonical's signed binaries with Pro, or a debranded rebuild. **The rev-4 scores assume the permission branch.** If Z-01 ends on the rebuild branch, OneMind loses Canonical's signed packages and security notices, the D cells must be re-checked under rule 6 before the base lock, and the choice comes back to you under Z-38/Z-39.
- **Z-38 (base OS):** see the U-SB note under Z-10 in §H. Until U-SB runs, the lock record must say "U-SB not run" (`01` §3.1.6 i).

### Z-41 · Run the Ubuntu Secure Boot test (LT-VM-20) yourself, or approve an Ubuntu mirror for the lab? · critic P6-2, P5-1, RS-6
**Why it matters:** U-SB is the one event in the pre-registered base-OS map that needs **no hardware and no vendor**. If it fails, the base of record moves from Ubuntu to bootc (`01` §3.1.6 h). The kit is frozen and ready: its pass/fail rule was registered before any build [C-FIX5-002], and it is the Secure Boot battery that already passed on Debian, with only the pre-registered changes [C-FIX5-003]. It could not run in the research environment because the Ubuntu archive names stopped resolving there during 2026-11-11 [C-FIX5-001, C-FIX5-004]; whether that block is deliberate is not known (README §R.5).
**Options:**
- **(a) Run it on your Mac on day 1** (`20` D1): a Lima/QEMU VM with normal internet, about 1.5–2 hours unattended, from `evidence/lab/ubuntu-secureboot/` (README §R.3; access item LT-ACC-01 in `22`). Run it twice, as the map requires two clean passes.
- **(b) Approve an Ubuntu archive mirror for the research lab** (name the mirror you trust), so the next research pass can run it under the same rules.
- **(c) Leave it for gate G1 (week 4).** The decision of record then keeps resting on a documentation-only Secure Boot score (D·C3 = 4 `doc-only`).
**Recommendation: (a), on day 1.** It is the cheapest test that can change the base. Also say whether the Ubuntu block in the research environment is deliberate (for example, to keep the run from contacting Canonical while Z-01 is open): if it is, (b) is not available.
**Also for you to judge (critic P6-4):** two reads went past that block, and both are disclosed. During U-SB the agent read Ubuntu's 26.04 `Release` file once by IP, through a public resolver, before it recognised the failures as a block. A blind refuter read ubuntu.com through Wayback captures. **Neither is used as evidence** (`evidence/hygiene-log.md` §7). Whether that was acceptable is your call.
**Blocked until answered:** a U-SB map event, and so a clean base lock at G6.

### Access and inputs added in revision 4.1 (RS-6)

| Needed | Why | What Zeus can do |
|---|---|---|
| The Ubuntu archive (`archive.ubuntu.com`, `security.ubuntu.com`) from a lab machine | U-SB / LT-VM-20 decides D·C3 and is a row of the S1 decision map; the research environment cannot resolve Ubuntu or Canonical names, and the run did not bypass that [C-FIX5-001, C-FIX5-004] | Run LT-VM-20 on a networked Mac (Z-41 a), or approve a mirror (Z-41 b) |

## What competitors do (for the new items, constraint fit)

| Item | Competitor | What they did | Their constraints | Fit for OneMind |
|---|---|---|---|---|
| Z-30 entity | Home Assistant / Open Home Foundation | A Swiss non-profit Stiftung funded by partner fees; Nabu Casa, the company, licenses its brands [C-W16-012] | Large community; years of revenue before the foundation | **Low now, high in years 3–5**: incorporate first, consider a foundation later |
| Z-31 first customers | Olares | Olares One raised USD 2.34M on Kickstarter; all backer orders fulfilled [C-W16-018] | Venture-funded (more than USD 100M), with hardware partners | **Medium**: pre-orders validate demand, but a solo founder must not take on fulfilment risk in year 1 |
| Z-31 first customers | ZimaCube | Kickstarter with about 1,252 backers [C-W16-027, UNVERIFIED] | Hardware company (IceWhale) | **Medium**, same caution |
| Z-29 name | Debian (as a mark OneMind uses) | Allows factual compatibility statements only, never in a product name [C-W16-011] | Community trademark policy | **High**: "based on Debian" yes, "Debian" in the name no |

## Glossary (sections F and G)

| Term | Meaning |
|---|---|
| **History rewrite / force-push** | Replacing commits that are already on GitHub. It is the only way to remove text from git history, and it breaks other people's copies of the branch. |
| **Counsel** | An outside lawyer engaged by Zeus. Nothing in this research is legal advice. |
| **APNs** | Apple Push Notification service, the only way to wake an iOS app instantly. |
| **Headscale** | An open-source, self-hosted control server for Tailscale clients. |
| **Device owner (Android)** | A fully managed device mode, set up only at first boot or after a factory reset. |
| **ELTS** | Freexian's paid Extended Long Term Support for old Debian releases. |
| **Notified body** | An independent organisation the EU authorises to assess a product's conformity under the CRA. |
| **Frozen protocol** *(§H)* | The scoring rules in `evidence/scorecard-weights.md`, locked before any option was scored; a change needs a logged row and an allowed reason. |
| **Pre-registered decision map** *(§H)* | A table written before a test runs, saying which option each outcome produces under the locked rules. |
| **Debrand-and-recompile** *(§H)* | Canonical's alternative to its approval: remove Ubuntu's trademarks and rebuild the binaries yourself before redistributing a modified image [C-W2-050]. |
| **Substantial modification** | A CRA term: a change after sale that makes the changer responsible as if they were the manufacturer of a new product. |
