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

## D-015 · F-34: Kanidm runs as a host service on the hub OS
**Date:** 2026-11-19 · **Decided by:** Zeus
> "F34 YES ON THE HUB OS" (in chat, while lane 4 was being finished)
- **F-34 = host service:** Kanidm (BD-03) runs as a systemd service in the hub's OS image, not as a chart inside k3s. This settles ACCT-D2 in `docs/umbrel2/accounts.md`; the `kanidm` chart listed in research 30's file tree is not built.
- **Why:** sign-in must keep working when k3s is down or being updated, which is when the owner most needs to get in.
- **Unblocks:** UMB-ACCT-1 (the Kanidm lab test) and CORE-SEC-10. #236 (SEC-SSO-01) still waits on UMB-ACCT-1 and #139. Background: `docs/learning/founder/06-kanidm-and-single-sign-on.md` (PR #399).

## D-016 · The dashboard is a desktop, not a console: wallpaper, windows, dock
**Date:** 2026-11-20 · **Decided by:** Zeus
> "what if we wanted to change this immediately to this particular layout?" · "Do it now !" (said in a Claude session after comparing OneMind with umbrelOS 2.0.1 in a lab VM; [docs/learning/umbrelos-2-teardown.md](learning/umbrelos-2-teardown.md))
- **Desktop is the default frame.** `/` is the wallpaper desktop: greeting, "Needs you", widgets, your apps. Every other screen (Market, Approvals, Settings, Nodes, …) opens as a window over the wallpaper, keeps its own URL, and closes with ✕ or Esc back to the desktop.
- **The dock is the main navigation.** The same items, roles and badges as the old sidebar, plus the apps pinned on Home. On phones it replaces the bottom tab bar.
- **The sidebar stays as the "Console" view,** one click away in the top bar and remembered per person.
- **This replaces** IA §1 "sidebar on desktop, bottom tabs on phones" and `docs/strategy/umbrel-parity.md` PU-04 "a dock is not proposed".
- **Unchanged:** every action is still a request, approvals still come first on Home, and freshness pills still show. umbrelOS is studied for the pattern only (PolyForm NC): no code, asset or text is copied.
- **Why:** umbrelOS 2.0.1 runs on the same base as OneMind (Debian 13, A/B updates). What makes it feel like an operating system is its desktop frame. OneMind's sidebar made it read as an admin dashboard.

## D-017 · F-45: Samba file sharing is built into the OS image
**Date:** 2026-11-20 · **Decided by:** Zeus
> "Built into OS" (said in a Claude session, answering F-45 after the File sharing screen landed as PR #443)
- **Samba ships in the OneMind OS image** (Debian 13 package, GPL-3.0, a separate program; OneMind does not link to it). It is masked and off until an owner approves the first share.
- **The root host service runs it** (`onemindd host serve`, docs/leap/core/HOST-ACTIONS.md): it renders the config under `/data`, checks it, and reloads. It updates with the OS through RAUC, not through the Market.
- **Unchanged guardrails:** every share is an owner-approved action and AI can never request one; SMB2 or newer only, no guest access, one person's own credentials per share; reachable on the LAN and the OneMind mesh only, never from the internet.
- **This replaces** F-45's proposed default, a separately updatable system app `apps/samba`.
- **Why:** file sharing is a basic OS feature (umbrelOS treats it the same way). Built in, the box shows up in Finder and File Explorer reliably, and shares map directly to OneMind people without routing an app's network through k3s.

## D-018 · The D-016 desktop is the only front door; Backstage is retired
**Date:** 2026-11-21 · **Decided by:** Zeus
> "Backstage is retired everywhere; the D-016 desktop is the only front door, including developer and cluster tiers." (approved by Zeus in a Claude session on 2026-11-21, after the portal-to-OneMind front-door study)
- **One front door.** The D-016 desktop (wallpaper Home, windows, dock, Launchpad) is the only front door on every tier, including developer and cluster. Nothing ships a second portal with its own sidebar, theme or sign-in.
- **Typed lists, not a generic catalog.** What the old portal listed comes in as typed lists: apps, plugins, nodes, links, devices and people. Anything else goes to a private archive, outside this repo.
- **Dropped from core:** the Ops globe, OpenCost, the DigitalOcean page, GitHub cards, Tech Radar, Tech Insights, the Visualizer and DevTools. Any of them may return later as an optional plugin; none is built in core.
- **OneMind supersedes the portal, it does not copy it.** Only Backstage's open formats are reused (Apache-2.0, with attribution under D-001): the entity YAML for a one-time import and the docs-build approach.
- **Every change stays an approval request.** Agents read and request; only a person approves.
- **This supersedes** "Backstage stays a developer portal" in `docs/ARCHITECTURE.md` (Dashboard row) and `docs/APPS.md` (Infrastructure tier row), and the same wording in `research-output/24` Q141 and Q255 (those files are left as written; this entry is the pointer).
- **Tracking:** the front-door issues FD-00 to FD-20 (parent: FD-00).
- **Why:** two front doors break D-016 and the "every change is an approval" rule, and the portal's cloud-only pages do not serve a home or small-business box.

## D-019 · Z-18 / Z-19: Secure Boot uses the `efi` route with signed UKIs, plus an owner "sovereign mode"
**Date:** 2026-11-22 · **Decided by:** Zeus
> Recorded as the founder decision on [#148](https://github.com/onemindos/ONEMINDOS/issues/148) (IMG-01), answering Z-18 and Z-19.
- **The research recommendation stands:** x86 boxes boot through RAUC's `efi` route with signed unified kernel images (UKIs, the kernel, initrd and command line in one signed file), and OneMind's key is enrolled at the factory.
- **Sovereign mode:** an owner may take over their box's Secure Boot keys, with guard rails:
  - it needs physical presence at the machine;
  - it shows a clear warning first;
  - the key state is shown in the dashboard;
  - OneMind updates keep working when OneMind's key stays enrolled next to the owner's.
- **Test keys until the key ceremony.** Build and test with throwaway keys now; real keys come after the ceremony ([#153](https://github.com/onemindos/ONEMINDOS/issues/153), D-010).
- **What it changes:** #148 is no longer waiting on Zeus. Slot choice under Secure Boot, anti-downgrade and sovereign mode land as separate PRs on #148.
- **Why:** a signed boot chain is the default that protects most owners; sovereign mode keeps the box the owner's own without breaking updates.

## D-020 · Disk encryption: on by default with a TPM, opt-in with a passphrase without one
**Date:** 2026-11-22 · **Decided by:** Zeus
> Recorded as the founder decision on [#152](https://github.com/onemindos/ONEMINDOS/issues/152) (IMG-05, LUKS2 + btrfs).
- **With a TPM** (the chip that stores keys inside the machine): the data partition is encrypted by default and unlocks by itself after a restart. The recovery key goes into the emergency kit.
- **Without a TPM** (for example a Raspberry Pi 5): the data partition stays unencrypted unless the owner turns encryption on and accepts typing a passphrase at every restart. The setup screen says that plainly.
- **What it changes:** #152 is no longer waiting on Zeus; the TPM / no-TPM rule and the opt-in passphrase backend are built on it.
- **Why:** a home hub has to come back by itself after a power cut or an update restart.

## D-021 · iPhone push moves to 1.1; 1.0 ships with Android
**Date:** 2026-11-22 · **Decided by:** Zeus
> Recorded as the founder decision on [#208](https://github.com/onemindos/ONEMINDOS/issues/208) (UX-03).
- **1.0 ships with the Android app** (the founder's phone). The Apple Developer account, the push key and the content-free relay are 1.1 work.
- **What it changes:** #208 and the issues that wait on it move to 1.1. D-005 (content-free Apple push) still holds for when it is built.
- **Why:** the founder's phone is Android, and the Apple Developer account and push signing identity (F-4) are not in place.

## D-022 · An app's own tokens pass through the gateway; Fleetbase is packaged after that
**Date:** 2026-11-22 · **Decided by:** Zeus
> Recorded as the founder decision on [#824](https://github.com/onemindos/ONEMINDOS/issues/824) (Market: Fleetbase).
- **Fix the gateway first.** The app proxy treated an app's own `Authorization: Bearer` header as a OneMind token and rejected it, which breaks any app that uses its own tokens.
- **The rule (security-reviewed):** once the person is signed in to OneMind (a valid session cookie), the app proxy passes the app's own Authorization header through to that app only.
- **Then package Fleetbase** as #824 specifies.
- **Why:** the blocker is in OneMind, not in Fleetbase, and the same fix unblocks every app that brings its own sign-in tokens.

## D-023 · OpenVitals moves to 1.1, as a OneMind-built on-box copy
**Date:** 2026-11-22 · **Decided by:** Zeus
> Recorded as the founder decision on [#826](https://github.com/onemindos/ONEMINDOS/issues/826) (Market: OpenVitals).
- **Not part of 1.0.** The upstream code (GPL-3.0) sends document text to a hosted AI service and expects hosted email, storage and a worker.
- **Plan for 1.1:** once the local model router is in, build a OneMind copy from a pinned upstream commit with those parts replaced by on-box ones.
- **Nothing that sends health data off the box is ever packaged.**
- **Why:** so no health data leaves the box; packaging the upstream code as it is would send document text to a hosted service.

## D-024 · LoRa messaging: MeshCore in 1.0, the Meshtastic bridge in 1.1
**Date:** 2026-11-22 · **Decided by:** Zeus
> Recorded on [#131](https://github.com/onemindos/ONEMINDOS/issues/131) (NMD-06) and its LoRa messenger issues, and in the 1.0 plan's founder additions.
- **1.0 messenger is MeshCore** (MIT licence): in OneMind and in the Android app, both dock mode (a USB radio on the hub, [#740](https://github.com/onemindos/ONEMINDOS/issues/740)) and direct mode (the phone talks to its own radio over Bluetooth LE, [#865](https://github.com/onemindos/ONEMINDOS/issues/865)). The two-way proof needs a second radio ([#860](https://github.com/onemindos/ONEMINDOS/issues/860)).
- **Meshtastic is 1.1:** a bridge in its own GPL-3.0 repo feeding the Messages module ([#739](https://github.com/onemindos/ONEMINDOS/issues/739)).
- **Guard rails:** a radio only ever transmits on the owner's tap; agents only draft. OneMind never writes RF settings (region, frequency, power) in 1.0; the owner sets them once in MeshCore's own tools.
- **This replaces** D-011's "radios when TAK is unparked" for a radio the owner already has.
- **Why:** Zeus owns a LoRa radio, so D-011's reason to wait is gone. MeshCore's MIT licence fits D-001; Meshtastic is GPL-3.0, so its bridge lives in its own repo.

## D-025 · Service picks: Backblaze B2 behind neutral S3, Headscale, and no SMS provider yet
**Date:** 2026-11-22 · **Decided by:** Zeus
> Recorded in the 1.0 plan's founder additions ("Picks"), answering the B2-checkpoint picks.
- **Off-site backup: Backblaze B2**, reached through a provider-neutral S3 layer ([#870](https://github.com/onemindos/ONEMINDOS/issues/870)). restic already speaks S3; tests use a local S3-compatible stand-in, and the owner types the bucket keys himself.
- **Remote access: Headscale** (already on the hub in the image, #292). The neutral mesh layer in the gateway ([#876](https://github.com/onemindos/ONEMINDOS/issues/876)) serves Headscale; NetBird is not built.
- **SMS: no provider now.** The SMS alert channel is built behind a provider-neutral adapter and tested with a fake transport only ([#869](https://github.com/onemindos/ONEMINDOS/issues/869)). Twilio may come later; the real text proof waits for that pick.
- **Why:** the code stays provider-neutral so an owner can switch providers, and the picks let the B2 services wave build without waiting.

## D-026 · Backstage is kept and runs on OneMind; custom apps are first-class
**Date:** 2026-11-25 · **Decided by:** Zeus
> "no we are not going to retire we are acually going to move it over after we have it stable not removing" and "for the move it over; when the OS is done I want to run it on the OS, also keep in mind I want to be able to run custom apps in OneMindOS not just marketplace apps so people can deploy anything they want through our process, etc" (founder, in a Claude session on 2026-11-25; quoted as written).
- **Backstage is not retired or removed.** When the OS is done, the founder's Backstage portal runs on OneMind OS. This amends D-018: its "Backstage is retired" part no longer holds. The rest of D-018 and D-016 is unchanged.
- **FD-00 ([#518](https://github.com/onemindos/ONEMINDOS/issues/518)):** its retirement and shutdown steps no longer apply.
- **The move comes after the OS is done.** It is not a 1.0 gate.
- **Custom apps are first-class.** People can deploy any app they want, not only Market apps, through OneMind's own gated process (every install is an owner approval). That path is built in [#643](https://github.com/onemindos/ONEMINDOS/issues/643) (pack, sideload and publish) and [#252](https://github.com/onemindos/ONEMINDOS/issues/252) (deploy a custom app from a Git repo).
- **Why:** the founder wants to run Backstage on the founder's own OS, and wants people to be able to deploy anything they want through OneMind's process, not only what the Market lists.

## D-027 · Permission modes: approve in advance, bypass only for low-risk digital actions, physical actions keep a person or a certified safety control, biometrics for certain actions
**Date:** 2026-11-25 · **Decided by:** Zeus
> "i agree with the assement of your flagging and i agree ; approve in advance, bypass only for low risk digital actions and robotics and anything physical always keep a person or a certified safey control. make sure the gateway is prep for this we also need add biomertics something up for certain actions we need to keep face id and finger printing,etc whatever the device provides in the future we will add our own custom devices but certain actions will require thismetc" (founder, in a Claude session on 2026-11-25; quoted as written). It answers a flag raised on his earlier request: "i thinking for the gateway and permissions we should have settings for that like always ask, bypass permissions like claude has,etc the agent can be automatcally approved for certain actions once in the future the same thing for the robotics and humans,etc." (quoted as written).
- **The flag he agreed with said:** a standing approval is a human approval given in advance, and it is scoped, limited, expiring, revocable, audited and notified; bypass is only for low-risk digital actions inside a sandbox; robotics and anything physical keep a person or a certified safety control in the loop.
- **Approve in advance.** An owner can approve a kind of action ahead of time. That standing approval is still a human approval. D-027 confirms the standing pre-approval design already in `docs/architecture/AUTOMATION.md` (§3.2 to 3.3: owner-only `policy.create` with a passkey, a count per period, a required expiry, a never list; the code caps the expiry at 90 days) and [#771](https://github.com/onemindos/ONEMINDOS/issues/771).
- **Bypass only for low-risk digital actions,** inside a sandbox. Bypassed actions stay in the audit log, as every auto-approved action already does (`docs/architecture/AUTOMATION.md` §3.4).
- **Robotics and anything physical always keep a person or a certified safety control.** Bypass never covers a physical action. The existing rule that a physical action is approved by a person each time and never by a standing approval ([#723](https://github.com/onemindos/ONEMINDOS/issues/723); build brief) is unchanged. Whether a certified safety control may ever stand in for that per-command approval is an open question for the founder.
- **Biometrics for certain actions.** Certain actions require the verification the person's device provides (for example Face ID or a fingerprint), and later OneMind's own devices. This builds on the passkey (WebAuthn) step-up the gateway enforces today for physical actions and identity approvals, which the contract makes required for high and critical risk once passkeys exist ([#528](https://github.com/onemindos/ONEMINDOS/issues/528)). WebAuthn tells the gateway that the person was verified on the device, not whether by face, fingerprint or the device PIN.
- **Earlier owner-approval rules are unchanged:** D-008, D-014, D-017 and D-026, and the never list (for example restore, key rotation, `policy.*`, removing a node). "Low-risk" never covers them.
- **The gateway must be prepared for all of this.**
- **This refines the locked rule "AI never actuates without human approval":** approvals given in advance count as human approval, and the one exception is bypass for low-risk digital actions.
- **Still to define (design in progress):** which actions are low-risk, and which actions need biometrics.
