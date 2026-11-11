# Decisions for Zeus {#sec-decisions}

> **Explain it like I'm the founder.** The research could decide most things from evidence. These are the ones it couldn't: they depend on your money, your risk appetite, a lawyer, or access we didn't have. Each one has a recommendation, so you can say "yes" and move on, or pick another option. **The first six matter before any code ships**; the rest can wait weeks. Full options, reasoning and what each blocks are in `26-OPEN-QUESTIONS-FOR-ZEUS.md`. Items marked *(legal)* need counsel.

## Decide before code ships {#sec-decide-now}

| ID | Question | Recommendation | Why |
|---|---|---|---|
| **Z-01** *(legal)* | Ask Canonical and counsel about redistributing a modified Ubuntu? | **Yes, now**: counsel's reading plus Canonical's terms and a Pro for Devices quote at 1k/10k units | The answer re-opens Ubuntu as the core or confirms Debian, and it now also governs Jetson [C-W2-050, C-REF-DC-cost-007] |
| **Z-02** | Security updates on by default? | **Yes for the security channel**, with opt-out, postpone, a window, health gate and auto-rollback; feature updates stay manual; robots get a "mission-safe reboot" rule | The CRA expects it [C-W6-008]; rollback makes it safe; R-1's intent (you stay in control) is kept |
| **Z-03** | Update engine | **RAUC**, with the layout engine-neutral (Mender runner-up, Rugix alternative) | Tie on score; RAUC wins on Secure Boot, revocation, free deltas, Pi 5, 3 tries [C-LAB-rauc-1152-011] |
| **Z-04** | Signing-key custody | **Offline root in a hardware key/HSM you hold, 2-of-3 release signers, a written succession/escrow plan**, plus a rotation drill before the first box | Home Assistant's release key lives in CI secrets [C-TD-home-assistant-os-013]; umbrelOS's beta shows the better design [C-TD-umbrelos-013] |
| **Z-05** *(legal)* | Open-core boundary vs the CRA route | **Keep every OneMind-authored part of the base image Apache-2.0; paid features as separate apps**; counsel on classification and firmware blobs; route decided by 2027-Q2 | Keeps the FOSS self-assessment route open and D-001's promise |
| **Z-06** | Support period per SKU | **At least 5 years from end of sale**, capped by each board's kernel window (Jetson shortest), met by in-place rebases | CRA support-period duty [C-W6-002]; ELTS is quote-only and own-use-only [C-W2-004] |

## Platform and product decisions {#sec-decide-platform}

| ID | Question | Recommendation |
|---|---|---|
| Z-07 | k3s floor for small boxes (REQUIREMENTS open question 2) | k3s server on ≥ 8 GB; 4 GB + SSD as a limited profile; SD-only or smaller = NATS leaf; confirm with the Pi 5 soak |
| Z-08 | When to add RKE2 | One distribution (k3s) until a buyer needs FIPS/STIG or an AI-conformant GPU cluster [C-W4-038]; k0s in the bake-off |
| Z-09 | GPU-server flavor on Ubuntu + RKE2 | Allow it once Z-01 is answered |
| Z-10 | Fund the bootc Industrial profile | **Yes, year 2**, with Fedora IoT as a CI canary now: your Fedora IoT answer |
| Z-11 | Industrial certification route | Partner with an already-certified platform for the first industrial SKU [C-W8-033, C-W2-042] |
| Z-12 | Default TAK server; where TAK lives | TAK Server container on ≥ 8 GB boxes [C-W8-018], OpenTAKServer on 4 GB profiles; cloud TAK as relay until the home bus is the authority |
| Z-13 | What "mirror" means | Warm standby (continuous restore, one-click promote) by default; live HA only on 3+ nodes |
| Z-14 | Platform first or image first | Platform first inside an image-first plan; precedent is mixed (Home Assistant platform first [C-W18-062], Umbrel image first [C-W18-063]) |
| Z-15 | Fusing Pi 5 / Jetson | Only OneMind-built hardware, after a soak on test-fused units; fusing is irreversible |
| Z-16 | Jetson base | L4T Ubuntu for the beta **and** the meta-tegra lab within 180 days decides the default [C-STEEL-jb-002] |
| Z-17 | Simulation GPU boxes | Ubuntu GPU flavor after Z-01, unless Isaac Sim passes on Debian [C-REF-DC-robotics-013] |
| Z-18 | x86 boot route | `efi` + signed UKIs from the first image if the combined power-cut spike passes, else GRUB |
| Z-19 | Secure Boot key model | Factory-enrolled db key; OneMind-built LTS kernel for the enforcing release [C-DEC-008]; decide whether owners may take over their box's keys ("sovereign mode") |
| Z-20 | Fleet server for updates | OneMind's own release service on NATS for RAUC; the 10k fleet test picks a fleet plane in year 1 |
| Z-21 | Plugin contracts, review staffing, money | Freeze E1–E4, E7, E9, E10; E5, E6, E8 as beta; Community tier only for sandboxed types; costed review plan first [C-REF-W19-cost-004] |
| Z-22 | Third-party host-level plugins in release 1 | Allow only if the sysext security test passes; otherwise OneMind-built only |
| Z-23 | k3s on robots and field kits | Agent only [C-REF-W4-security-008] |
| Z-24 | Sunset the script install | Developer loop only after image GA [C-REF-DC-longevity-004] |
| Z-25 | FIPS/STIG as a P0 property | No, unless a named public-safety buyer is in year-1 scope; k3s fails a FIPS-only gate today [C-REF-DC-longevity-010] |
| Z-26 | Desktop edition plugins | Accept Omarchy's manifest shape, Verified publishers only, off by default |
| Z-27 | Pull two industrial tests forward | Yes: FDO on Debian and AlmaLinux bootc, plus a Flight Control fleet simulation, within 180 days |

## The REQUIREMENTS open questions and the recurring Blueprint questions {#sec-decide-blueprint}

| Question | Recommendation |
|---|---|
| Kubernetes everywhere, or a hybrid? (REQ Q2) | Kubernetes on every box sold; NATS leaf on devices it only connects (Z-07) |
| Licence model for OneMind's own code (REQ Q3) | Settled by D-001; write the pro/open ADR before the first paid feature, consistent with Z-05 |
| First hardware tier and segment (REQ Q4) | **Lite x86 mini PC for homesteaders and self-hosters first** (most lab-proven path); Pi 5 Edge greenhouse/TAK profile second, in the same release |
| First internal app (REQ Q5) | **The Blueprint's first vertical slice**: sign-in, site status, Legacy summary, an approved Home Assistant light toggle, TAK observation, offline sync, restore. It exercises the whole foundation |
| Is Google/Pixel hardware acceptable? | Yes for field EUDs: Pixel 8 or newer with GrapheneOS [C-W14-002], after the GrapheneOS + ATAK test |
| What state is the Dell 5540 in? | Run the inventory on day 2: Secure Boot custom-key mode is supported in its BIOS [C-W10-043]; record TPM and CPU level |
| What is the first vertical slice? | As REQ Q5 |
| Which task system? | Still open: no evidence was gathered; pick what you already use and expose it through the capability layer |

## Access the research needed but could not get {#sec-access}

The live DOKS cluster (read-only commands are in `22-HARDWARE-LAB-TEST-PLAN.md`); founder hardware (Pi 5, Jetson Orin Nano Super, an RTX box) for the bake-off; real power pulls on the Beelink and Dell; vendor quotes (Canonical Pro for Devices, Freexian ELTS for arm64 and redistribution, Red Hat, NVIDIA), with drafts written but **not sent**, because the brief forbids contacting vendors; counsel; the Blueprint originals; paywalled standard texts (EN 18031, IEC 62443); a bot-walled CIP wiki; and new Wayback captures. Each is listed with what you can do in `26-…` §D.
