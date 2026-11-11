# 26 · Open questions for Zeus

**Created:** 2026-11-10 by DEC (Tier A). Later workstreams **append** sections; don't reorder the IDs.
**How to use this file:** each item gives the question, the options, a recommendation, and what is blocked until you answer. Where the brief told us to assume an answer (rule 8), the assumption is stated and the work proceeds on it. Items marked **(legal)** need counsel, which is not legal advice from this research.
**Serves requirements:** RS-6, R-1, R-3, D-001, H-1, M-8, F-11, F-12, N-9, U-4

> ### Explain it like I'm the founder
> The research could decide most things from evidence. These are the ones it can't: they depend on your money, your risk appetite, a lawyer, or access we didn't have. Each has a recommendation, so you can say "yes" and move on, or pick another option. The first six matter before any code ships; the rest can wait weeks.

---

## A. Founder decisions from the Tier A foundation work

### Z-01 · Ask Canonical and counsel about redistributing modified Ubuntu (legal) · Q-W2-1, Q168, Q57
**Why it matters:** Canonical's policy says modified Ubuntu may be redistributed only if "approved, certified or provided by Canonical"; otherwise trademarks must be removed **and** binaries recompiled [C-W2-050]. This decides whether Ubuntu can become the core (it led the raw scorecard) and affects the GPU-server flavor and possibly the Jetson flavor (NVIDIA's L4T Ubuntu, modified by OneMind). Ubuntu Pro for Devices has no public price [C-W2-006].
**Options:** (a) ask counsel for a reading and Canonical for terms plus a Pro for Devices quote at 1k/10k units; (b) don't ask; ship only Debian and NVIDIA's own images; (c) ship Ubuntu flavors with trademarks stripped and accept the recompile risk.
**Recommendation: (a), now.** It costs little, and the answer either re-opens Ubuntu as the core or confirms Debian. A draft for Canonical belongs in `evidence/outreach-drafts.md` (not yet written).
**Blocked until answered:** shipping any Ubuntu-based OneMind image (GPU-server flavor; check the Jetson flavor too). **Assumption meanwhile:** Debian core; Jetson stays on NVIDIA's L4T.

### Z-02 · Security updates on by default? (CRA vs R-1) · SEC-05, Q221
**Why it matters:** the EU Cyber Resilience Act expects automatic security updates by default, with an easy opt-out [C-W6-008]; the draft OS standard makes that testable [C-W6-019]. ADR-001 and R-1 say "never auto-install".
**Options:** (a) the security channel installs automatically by default (opt-out, postpone, maintenance window, health-gated, rolls back by itself); feature updates stay manual; (b) keep manual by default everywhere and accept EU compliance risk; (c) auto only for EU-sold SKUs.
**Recommendation: (a).** Rollback makes it safe, and R-1's intent (the owner stays in control) is kept by the opt-out and window. Robots and field kits get a "mission-safe reboot" rule.
**Blocked:** the update UX spec and the CRA technical file.

### Z-03 · Update engine: RAUC (recommended) or Rugix
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
| 4 | First hardware tier and customer segment | (a) Lite x86 mini PC for homesteaders/self-hosters; (b) Pi 5 Edge greenhouse/TAK profile; (c) Pro GPU box | **(a) first** (most lab-proven path: x86 + RAUC + k3s), **(b) as the second profile** in the same release (D-002 keeps all tiers in design). Final call needs W10/W16, which haven't started |
| 5 | First OneMind internal app | (a) the Blueprint's first vertical slice (sign-in, site status, Legacy summary, an approved HA light toggle, TAK observation, offline sync, restore); (b) a single module | **(a)**: it exercises identity, the capability gateway, approvals, NATS, TAK and restore, i.e. the foundation itself |

## C. Recurring Blueprint questions (`context/02` §21)

| Question | Options | Recommendation |
|---|---|---|
| Is Google/Pixel hardware acceptable (GrapheneOS as the security baseline)? | yes / no / Pixel for field devices only | Not researched yet (W14, Tier C). Provisional: acceptable for field EUDs if an OEM-unlockable SKU is used; decide after the GrapheneOS + ATAK test |
| What state is the Dell 5540 in? | Known: i5-1345U, 16 GB, Windows. Unknown: BIOS, TPM/Secure Boot state, SSD | Run W6 test X-1 and W2-HW-5 (`mokutil --sb-state`, `systemd-analyze has-tpm2`, `ld.so --help` for x86-64-v3) and record the results |
| What is the first vertical slice? | see B-5 | The Blueprint's seven-step slice |
| Which task system? | Not researched in Tier A | Open; no evidence gathered |

## D. Access and inputs we needed but couldn't get (RS-6)

| Needed | Why | What Zeus can do |
|---|---|---|
| Live DOKS cluster (read-only) | Verify storage, LB, ingress and Helm/Argo ownership before the conversion plan | Run the read-only commands in `05-…` §9.2 (kubectl/doctl/argocd) |
| Founder hardware: Pi 5 (4 and 8 GB, NVMe), Jetson Orin Nano Super, RTX box | Pi 5 tryboot, Jetson A/B gate (T-W3-06), k3s soak, GPU driver on Debian, real-time latency | Buy the Pi 5 and Orin Nano; run the tests listed in each workstream file |
| Real power pulls on the Beelink U55 / Dell 5540 | QEMU's kill doesn't drop disk write caches | Run T-W3-01 (10 pulls per engine) |
| Vendor quotes: Canonical Pro for Devices, Freexian ELTS (arm64, redistribution), Red Hat RHEL/RHDE | Cost to 2036 (DC-03) | Approve outreach drafts (to be written in `evidence/outreach-drafts.md`) |
| Counsel | CRA classification, FOSS route with firmware blobs, Ubuntu redistribution, repackaging upstream apps, UK PSTI | Brief counsel with Z-01, Z-05 and 07 §13 |
| Blueprint originals (Nov 3–4) | Only the summary in `context/02` was available | Share the originals for the plan (A01–A24 tests) |
| Paywalled standards (EN 18031 clause text, IEC 62443) | Only catalogue metadata could be cited | Buy if a certification route is chosen (Z-11) |
| CIP wiki (reference hardware, SLTS table) | Behind a bot challenge; not bypassed | Check it in a browser if CIP becomes the industrial kernel |
| New Wayback captures | Blocked by the run's permission policy | Optional: save the ARCHIVE-GAP pages listed in `evidence/sources/*.md` |
