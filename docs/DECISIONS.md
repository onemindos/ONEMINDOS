# OneMind OS: Decision Log

Founder decisions. Each entry is final until Zeus changes it. Reference these IDs from other docs.

---

## D-001 · License: open core, Apache-2.0
**Date:** 2026-11-10 · **Decided by:** Zeus
- **Apache-2.0:** the core OS, SDK, `onemind.app.yaml` format, CLI, and capability gateway.
- **Revenue:** hardware (OneMind boxes), support plans, pro/enterprise features, the OEM program ("Manufacture with OneMind"), education (Circle), and later an optional cloud.
- **Why:** trust and adoption are needed to become the industry standard for sovereign operations, and OEM partners can build on it. The brand, the Market, signed updates and certified hardware stay under OneMind's control.
- **Guardrail:** never copy code from PolyForm-NC (Umbrel), AGPL (Olares, Glance), GPL (Homepage) or unlicensed (umbrel-apps) sources into Apache code. Patterns are fine; code is not.
- **Still to decide:** which features are "pro" (closed or commercial) vs open. Write that ADR before the first paid feature.

## D-002 · Tiers: build all of them together, with one design
**Date:** 2026-11-10 · **Decided by:** Zeus
> "I want them all in mind in development, not leaving anything behind, so it makes sense combined."
- **One image pipeline, many profiles.** Edge (Pi), Lite (mini PC), Pro (GPU), Robotics (Jetson), Omni (sim/training) and Cluster are all built by the same CI from the same layers. Each tier is a profile, not a fork.
- **One app layer.** Every app declares requirements, and NodeCapabilities decides where it can run. Tiers are emergent, not hard-coded.
- **Release readiness is per tier, design is unified.** A tier ships when it passes its acceptance tests, but nothing is designed for one tier alone.
- **Implication for the bake-off:** test x86, ARM (Pi) and Jetson from the start.

## D-003 · Apps: one unified OneMind app with modules, all scaffolded
**Date:** 2026-11-10 · **Decided by:** Zeus
> "All of them … either combined into one, or as the core, or individual ones, but at least scaffold what we need."
- **Approach (hybrid):** one **OneMind app shell** (the dashboard/desktop) that hosts **modules**. Each module is also a normal Market app with its own `onemind.app.yaml`, so it can be installed, removed or used on its own, and other apps and AI can use its capabilities.
- **Scaffold all modules now** (spec + manifest stub). Build depth in order of daily use. See [APPS.md](APPS.md).

## D-004 · Test hardware: use what exists, buy in phases
**Date:** 2026-11-10 · **Decided by:** Zeus
- **Available now:** Mac (dev + client), Android phone (client), Beelink U55, Dell Latitude 5540, cloud access (existing DigitalOcean account/cluster).
- **To buy when needed:** the Jetson and the rest of the phased list in [HARDWARE.md](HARDWARE.md).
- **OneMind box design:** based on competitor specs (also in HARDWARE.md).

## D-005 · iOS alerts: Apple push carrying minimal data only
**Date:** 2026-11-10 · **Decided by:** Zeus
- The iOS app uses APNs for instant alerts. The push payload is **only an opaque/encrypted "new alert" signal**. The app then fetches the real alert content directly from the user's own box.
- Apple sees *that* an alert arrived, never *what* it was.
- Android, desktop and web are fully self-hosted (ntfy/UnifiedPush or in-app).

## D-006 · Partner programs: apply to NVIDIA Inception and the Anthropic MHS preview
**Date:** 2026-11-10 · **Decided by:** Zeus
- Drafts are in [`applications/`](applications/). Zeus submits them himself.
- **Why:** Jetson/GPU discounts and technical access for the Robotics, Pro and Omni tiers, and early access to the Model Hardware Standard for AI-driven robots and IoT.

## D-007 · Base OS: Debian 13 is the shipping base (Z-38 = b)
**Date:** 2026-11-11 · **Decided by:** Zeus
> "Yes, lock Debian."
- **Shipping base for the OneMind image:** Debian 13 "trixie": Debian's kernel on x86_64 and arm64, Raspberry Pi's kernel on Pi 5. A/B updates with RAUC, k3s, restic and E1–E10 are unchanged.
- **Overrides** the research's frozen-protocol result (Ubuntu 26.04 + RAUC: 65 vs bootc 64 vs Debian 63, a statistical tie, conditional on Canonical's permission). Logged in `research-output/evidence/scorecard-weights.md` §8 and `26` Z-38.
- **Other flavors:**
  - Ubuntu 26.04 stays a light CI hedge.
  - Jetson stays on NVIDIA L4T Ubuntu 24.04 (dev kits; Z-01 still needed; Yocto meta-tegra is the test to remove Ubuntu).
  - GPU servers may use Ubuntu + RKE2 after Z-01.
  - Industrial = AlmaLinux/RHEL bootc in year 2.
  - Machines OneMind doesn't own get OneMind installed on top of their unmodified OS.
- **Why:**
  - it ships without anyone's permission
  - it beats Ubuntu 6–5 head-to-head on the rows that hit the first boxes (Pi 5, x86 mini PC)
  - it is the base of the proven competitors that ship their own image (umbrelOS, StartOS, Proxmox, TrueNAS)
  - every lab ran on it
  - it costs about $40 vs $120 per device at 10k units
  - it cannot be revoked: "the operating system for sovereignty"
- **Reopen only if:** bootc passes on a real Pi 5 (W2-HW-3), or Canonical offers a written, non-revocable, affordable agreement.
- Explained in [`learning/03-base-os-debian-vs-ubuntu.md`](learning/03-base-os-debian-vs-ubuntu.md) and [`learning/05-official-route-and-why-not-fedora-arch.md`](learning/05-official-route-and-why-not-fedora-arch.md).
