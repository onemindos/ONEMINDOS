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

## D-008 · Rescue console sign-in: the owner token until passkeys
**Date:** 2026-11-15 · **Decided by:** Zeus
> "keep the owner token for the rescue console"
- The rescue console in onemindd (CORE-UPDATE-8, #157, PR #268) signs the owner in with the **existing owner token**. It checks the token against the gateway's hash-only tokens file (`/etc/onemind/tokens.yaml`), so it works with k3s and the gateway down. **No separate rescue credential.**
- Only a person with role owner passes; agent tokens never do (AI never actuates without human approval).
- **Why:**
  - nothing new to provision or lose;
  - no new secret on disk (the file stores only hashes);
  - no new privilege: the same token already controls the gateway.
- **Until:** owner passkeys land with Kanidm (BD-03; UPDATES §3.5 plans a locally cached owner passkey). Then the console moves to the passkey.

## D-009 · Z-41: the Ubuntu Secure Boot test is dropped
**Date:** 2026-11-14 · **Decided by:** Zeus
> "Accept all six" (the recommendations in [`learning/founder/05-decision-briefs-nov-2026.md`](learning/founder/05-decision-briefs-nov-2026.md); applies to D-009 to D-014). Confirmed to the Opus gate on 2026-11-15: "everything else is correct"; D-014 was then changed (see below).
- **Z-41 = (d):** LT-VM-20 (U-SB) is not run. The lock record says "U-SB not run; not needed under D-007".
- **Why:** D-007 reopens only for a bootc pass on a real Pi 5 or a Canonical agreement, so no U-SB result can change the base.
- If the Ubuntu CI hedge ever needs Secure Boot, the kit can join that CI leg later.

## D-010 · Z-04 / F-27: the signing-key ceremony runs now, on key files, then rotates onto hardware keys
**Date:** 2026-11-14 · **Decided by:** Zeus
- **Z-04 = (a′):** the offline TUF root has three keys, each on its own encrypted USB stick, with a **2-of-3** threshold. The keys are made offline with `scripts/tuf-bootstrap-root.sh`: rehearse first, then `create`.
- The sticks are kept in three places: home, off-site, and a trusted person. The succession note stays in a sealed envelope, never in the repo.
- `root.json` (public) is committed. Only the three online role keys become GitHub environment secrets; the root never touches CI.
- **Later:** a root rotation moves the root onto hardware keys once the token signer exists (#272). That rotation counts as Z-04's required drill.
- **Sovereign mode** (owners replace their box's Secure Boot keys): yes in principle, designed under Z-19 (#148), not built now.
- **Why:** the hardware-token signer isn't built yet (`os/update/README.md`). This unblocks signed releases now and keeps the 2-of-3 and offline rules.

## D-011 · F-25 / #214: the hardware order is phased
**Date:** 2026-11-14 · **Decided by:** Zeus
- **Now:** a Raspberry Pi 5 16 GB and a Pi 5 4 GB, each with an NVMe HAT, the official 27 W PSU and a case, plus a spare SSD for the bootc test.
- **Jetson Orin Nano Super:** once NVIDIA Inception (D-006) answers, or by G2.
- **Meshtastic/LoRa radios and the Zigbee/Thread dongle:** when TAK is unparked.
- Serials go in the inventory (LT-X86-00), never in the public repo.
- **Why:** the smallest order that meets the Pi soak start (2026-12-11) and the bootc test.

## D-012 · Z-40: four scoring rules are fixed before the bootc Pi test
**Date:** 2026-11-14 · **Decided by:** Zeus
- **Z-40 = (a):**
  1. The tie-break counts rows across the full table, and a draw comes back to Zeus.
  2. "Experimental" vendor support with a documented path scores 3 (`doc-only`) until W2-HW-3 measures it.
  3. "Proven in production" (C4) is scored on the base layer.
  4. No third candidate may enter a tie.
- To be copied into `research-output/evidence/scorecard-weights.md` §8 before LT-PI5-02 runs.
- **Why:** under D-007 these rules only decide how a bootc pass is read. Fixing them before the result is known keeps the reading fair.

## D-013 · Z-10: the bootc test on a real Pi 5 (W2-HW-3) is approved
**Date:** 2026-11-14 · **Decided by:** Zeus
- **Z-10 = (a):** LT-PI5-02 runs before G1 (2026-12-13), on the 16 GB Pi with its own SSD or card, after D-012 is logged. bootc stays the year-2 Industrial profile (D-007).
- **Why:** this is the test for D-007's own reopen condition. A fail confirms Debian; a pass reopens D-007, read under D-012.

## D-014 · #253: VMs, a web terminal and Tor (as an optional app) are built now
**Date:** 2026-11-15 · **Decided by:** Zeus
> "i want the 013 now and its needs to be something we build now" · "lets do it as optional please but lets add it now" (said to the Opus gate, recorded on PR #271; this replaces the 2026-11-14 "later" answer for VMs and Tor)
- **Virtual machines: build now (#281).** Measure on real KVM hardware first (LT-MACH-2 on the Beelink). The runtime follows F-56's default, with KubeVirt as an optional signed extension; it goes back to Zeus if LT-MACH-2 fails. Off by default; x86 hubs with KVM and ≥ 16 GB only, never on a Pi. Every machine action waits for owner approval; agents may only request.
- **Web terminal: build now (#273).** Owner-only, behind a passkey with re-auth, inside the rescue console, with every session audited. Off by default and never reachable by agents, the SDK or AI tools. It stays disabled until passkey sign-in exists (#236).
- **Tor: build now, as an optional Market app, never in the core OS (#284).** A remote-access fallback for homes behind CGNAT.
  - An onion service for the dashboard only, with Tor client authorization required (per-device keys) and normal sign-in behind it.
  - Never an outbound proxy for apps, agents or AI (`SocksPort 0`).
  - Installed and removed only by owner-approved actions. Its egress lives in the app's own NetworkPolicy, so the core keeps default-deny egress.
- **Why:** Zeus wants all three in the product now. The guardrails keep the locked rules: small boxes, AI never actuates without approval, default-deny egress.

## D-016 · The dashboard is a desktop, not a console: wallpaper, windows, dock
**Date:** 2026-11-20 · **Decided by:** Zeus
> "what if we wanted to change this immediately to this particular layout?" · "Do it now !" (said in a Claude session after comparing OneMind with umbrelOS 2.0.1 in a lab VM; [docs/learning/umbrelos-2-teardown.md](learning/umbrelos-2-teardown.md))
- **Desktop is the default frame.** `/` is the wallpaper desktop: greeting, "Needs you", widgets, your apps. Every other screen (Market, Approvals, Settings, Nodes, …) opens as a window over the wallpaper, keeps its own URL, and closes with ✕ or Esc back to the desktop.
- **The dock is the main navigation.** The same items, roles and badges as the old sidebar, plus the apps pinned on Home. On phones it replaces the bottom tab bar.
- **The sidebar stays as the "Console" view,** one click away in the top bar and remembered per person.
- **This replaces** IA §1 "sidebar on desktop, bottom tabs on phones" and `docs/strategy/umbrel-parity.md` PU-04 "a dock is not proposed".
- **Unchanged:** every action is still a request, approvals still come first on Home, and freshness pills still show. umbrelOS is studied for the pattern only (PolyForm NC): no code, asset or text is copied.
- **Why:** umbrelOS 2.0.1 runs on the same base as OneMind (Debian 13, A/B updates). What makes it feel like an operating system is its desktop frame. OneMind's sidebar made it read as an admin dashboard.
