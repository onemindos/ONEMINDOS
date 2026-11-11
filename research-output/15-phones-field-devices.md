# 15 · Phones and field devices (W14)

**Workstream:** W14 (Tier C: brief; labelled secondary sources allowed, primary where load-bearing) · **Tag:** W14 · **Date:** 2026-11-11
**Claims:** `evidence/claims/W14.csv` (C-W14-001…041), plus reused rows cited by their own IDs (C-W8-015/020/021/023, C-W11-038…040) · **Sources:** `evidence/sources/W14.md`, archived text in `evidence/sources/W14/` · **Question statuses:** `evidence/qbank/W14.md` (Q298, Q316, Q317)
**Builds on:** `context/00-CONVERSATION-RECORD.md` §1 (phones and Android sovereignty), `context/02-prior-planning.md` §22 (Linux desktop and ATAK handoff), [`09-iot-mesh-offgrid-tak.md`](09-iot-mesh-offgrid-tak.md) (TAK server side, Meshtastic), [`12-dashboard-clients-xr.md`](12-dashboard-clients-xr.md) (the OneMind phone app: REC-W11-07, -09, -16).
**Covers mission items:** GrapheneOS on Pixel as a hardened ATAK device (supported devices, ATAK evidence), **the reported ATAK crash on a GrapheneOS Pixel Tablet**, the Samsung S24 Ultra as a no-root ATAK device, Fairphone with CalyxOS / iodéOS / /e/OS, Volla, Linux phones (postmarketOS, now Nura; Ubuntu Touch; Droidian; Mobian; Sailfish; Librem 5; PinePhone; FuriLabs FLX1), ATAK via Waydroid vs CloudTAK in a browser, Android's AVF Linux Terminal, the four "build your own OS" levels and when a "OneMind EUD" makes sense, and HarmonyOS lessons. **Appendix A is the GrapheneOS + ATAK founder test for `22-HARDWARE-LAB-TEST-PLAN.md`.**
**Serves requirements:** UX-5, UX-8, U-3, M-2, M-4, M-5, N-1, N-4, N-6, P-8, F-4, F-7, F-15, D-004, D-005

> ### Explain it like I'm the founder
> **The phone is a client, not the OS we build.** OneMind OS runs on boxes, Pis, Jetsons and servers ([`01`](01-FOUNDATION-DECISION.md)). Phones connect to it: the OneMind app for the dashboard and alerts, and ATAK/iTAK for the tactical map. Nothing in this file changes the foundation decision.
>
> **Your field phone: a Pixel 9a or Pixel 10a with GrapheneOS.** GrapheneOS is the most hardened Android you can install, but only on Pixels. Buy a Pixel 8 or newer, because those get 7 years of updates and a hardware anti-exploit feature (memory tagging) [C-W14-002, C-W14-003]. A 10a is covered until March 2033.
>
> **The Pixel Tablet crash.** We could not find the public report you remembered, anywhere: not in GrapheneOS's bug tracker, not in ATAK's, not on the web [C-W14-018]. What we did find matters more: **the Pixel Tablet has no GPS chip and no cellular modem** [C-W14-011]. On its own it can never be an ATAK field device; it is a base-station screen at best. We also read ATAK's location code: it does *not* crash when GPS is missing; it shows a warning [C-W14-015]. So the crash most likely came from one of three things, and the test in Appendix A tells them apart in about an hour: GrapheneOS's memory protection stopping a bug in ATAK's native code (fix: one per-app toggle), a known Pixel Tablet OS bug, or a plugin.
>
> **The real ATAK gotchas on GrapheneOS** are not crashes: multicast "mesh" position sharing over a VPN is blocked by GrapheneOS's leak protection [C-W14-010], location needs a couple of settings, and one blogger saw position sharing work only one way [C-W14-019]. All have workarounds; Appendix A checks each one.
>
> **Your S24 Ultra** stays a great *stock* ATAK phone and OneMind client. You cannot put GrapheneOS or any custom OS on a US S24 Ultra, and forcing it would permanently trip Samsung's Knox fuse [C-W14-021, C-W14-022]. Use no-root tools (Shizuku, UAD-ng, Obtainium, Shelter) instead.
>
> **Linux phones are not ATAK phones in 2026.** ATAK under Waydroid has no built-in GPS [C-W14-031]. On a Linux phone, the TAK answer is **CloudTAK in the browser**.
>
> **A "OneMind phone OS"? Not now.** GrapheneOS ships about 80 releases a year [C-W14-040]. A solo founder cannot keep a fork of that secure. The right first step is a OneMind app plus fleet provisioning with an open-source device manager, on top of GrapheneOS or stock Android.

---

## 1. Recommendations

| ID | Recommendation | Requirements | Evidence | Confidence |
|---|---|---|---|---|
| **REC-W14-01** | **Default field EUD = Pixel 9a or 10a (carrier-unlocked) + GrapheneOS.** Pixel 8/8a/9 family also acceptable. Do not buy Pixel 6/7 generation or the Pixel Fold/Tablet for new field kit (no MTE, support ends 2026–2028). | M-2, M-4, N-1 | C-W14-001…004 | High (lifecycle), Medium (ATAK fit, pending Appendix A) |
| **REC-W14-02** | **Pixel Tablet = base-station or vehicle display only**, paired with an external GNSS source (Bluetooth/USB GPS feeding ATAK's external-GPS input) or a phone as the position source. Never issue it as a standalone EUD. | N-1, P-8 | C-W14-011, C-W14-012 | High |
| **REC-W14-03** | **Run the GrapheneOS + ATAK test (Appendix A) before declaring GrapheneOS the OneMind-recommended EUD.** Gate: T-W14-01…05 pass on a Pixel 8+ phone. If the Pixel Tablet crash reproduces, capture the tombstone and file it upstream (GrapheneOS or TAK Product Center, as the trace dictates). | Q298 | C-W14-005, C-W14-006, C-W14-018 | — |
| **REC-W14-04** | **EUD loadout (provisional):** sandboxed Google Play in the *same* profile as ATAK only if a plugin needs Play; location "Allow all the time"; battery "Unrestricted"; GrapheneOS network location on (Wi-Fi scanning on) for indoor fixes; exploit-protection compatibility mode **only** if a memory-corruption abort is reported for ATAK; prefer **TAK Server (unicast TLS 8089)** over mesh multicast SA whenever a VPN is up. | N-6, P-8 | C-W14-005, -007, -008, -009, -010 | Medium |
| **REC-W14-05** | **S24 Ultra stays stock:** OneMind client + ATAK. Hardening with no-root tools (Shizuku-backed tools, UAD-ng for debloat, Obtainium for updates from source, Shelter for a work-profile sandbox). Never attempt a bootloader unlock on it. | UX-5, UX-8, M-5 | C-W14-021…026 | High (Knox), Medium (bootloader status, SECONDARY) |
| **REC-W14-06** | **De-Googled non-Pixel option = Fairphone Gen. 6 + CalyxOS or /e/OS**, for users who prioritise repairability over maximum hardening. Mark as "community-tested" for ATAK until Appendix A's matrix runs on one. | M-5 | C-W14-027, C-W14-028 | Medium |
| **REC-W14-07** | **Linux phones: CloudTAK (browser) is the TAK client; ATAK via Waydroid is unsupported.** Track Nura (ex-postmarketOS) and FuriLabs as watch items, not targets. | UX-8, M-5 | C-W14-029…032, C-W8-023 | High |
| **REC-W14-08** | **No OneMind phone OS before year 2.** Build level 1 first: the OneMind app (REC-W11-09) plus optional **fully-managed provisioning** with an open-source MDM (Headwind MDM, Apache-2.0) for EUD fleets and child devices; QR enrollment reuses N-4 flows. Revisit level 2 only as a partnership (GrapheneOS's stated OEM-partner plan) or reseller kit, never as a solo fork. | U-3, N-4, F-4, M-4 | C-W14-034, C-W14-035, C-W14-040, C-W14-041 | Medium |
| **REC-W14-09** | **Android AVF Terminal is a developer convenience**, not a OneMind node runtime: an experimental single-VM feature behind developer options [C-W14-033]. Do not plan a "phone as k3s node". | N-1, F-8 | C-W14-033 | Medium |
| **REC-W14-10** | **HarmonyOS lesson, written into the architecture:** no single store, push service or cloud dependency in the client path (already true: UnifiedPush/ntfy, APNs minimal per D-005, F-Droid/Accrescent channels in C-W11-038…040). Borrow DSoftBus *concepts* (unified discovery and session over any link) for the NATS/capability layer; do not import OpenHarmony code. | M-5, N-1, F-15 | C-W14-036, C-W14-037 | Medium |

**Consistency with 01:** these recommendations sit entirely in the client layer (L5 in [`01`](01-FOUNDATION-DECISION.md) §8). They do not touch the base OS, update engine, k3s or backups. The phone app is the one specified in REC-W11-09; push follows REC-W11-07 and D-005.

---

## 2. GrapheneOS on Pixel as a hardened ATAK device

### 2.1 Supported devices and how long they last

GrapheneOS officially supports 21 devices, all Google Pixels from the Pixel 6 to the Pixel 10a, including the Pixel Tablet [C-W14-001]. It **recommends only Pixel 8 and later**, because those have a 7-year minimum support guarantee and ARM hardware memory tagging (MTE), which GrapheneOS turns on by default for the OS and known-compatible apps [C-W14-002]. US carrier-locked units cannot be flashed [C-W14-004].

| Device | OEM minimum support end [C-W14-003] | MTE | GNSS / cellular | Fit as OneMind field EUD |
|---|---|---|---|---|
| Pixel 10a | Mar 2033 | yes (8th gen+) [C-W14-002] | yes / yes (assumed for phones; check unlockable SKU) | **Best value, longest life** |
| Pixel 10 / 10 Pro / 10 Pro XL | Aug 2032 | yes | yes / yes | Good; larger battery on XL |
| Pixel 9a | Apr 2032 | yes | yes / yes | **Default** (price/longevity) |
| Pixel 9 family | Aug 2031 | yes | yes / yes | Good |
| Pixel 8 / 8 Pro / 8a | Oct 2030 – May 2031 | yes | yes / yes | Acceptable (used market) |
| Pixel Fold | Jun 2028 | no | yes / yes | Avoid for new kit |
| **Pixel Tablet** | **Jun 2028** | **no** | **no / no** [C-W14-011] | **Base-station display only** |
| Pixel 7 / 7 Pro / 7a | Oct 2027 – May 2028 | no | yes / yes | Avoid (ends soon) |
| Pixel 6 / 6 Pro / 6a | Oct 2026 – Jul 2027 | no | yes / yes | Do not buy (Pixel 6/6 Pro support ends this month) |

*Note:* the 10a's carrier and eSIM-only questions raised in `context/02` §22 were not re-checked here (Tier C); verify the exact SKU is OEM-unlockable before buying (Appendix A.1, step 1).

### 2.2 Evidence that ATAK runs on GrapheneOS

- **Positive, but anecdotal or commercial:** a US vendor sells a GrapheneOS Pixel 9 preloaded with ATAK and plugins as a field EUD [C-W14-020]. That is evidence the combination ships, not independent test evidence.
- **Negative or friction reports:**
  - GrapheneOS blocks apps sending multicast outside the VPN tunnel [C-W14-009]. Users report that ATAK's multicast mesh situational awareness works on a stock Pixel 9a but not on a GrapheneOS Pixel 9a over a VPN, and that this affects all multicast over VPN interfaces (issue open since June 2026) [C-W14-010].
  - One blog (Oct 2024) reports one-way position sharing (GrapheneOS saw the Samsung; the Samsung did not see GrapheneOS), a broken Meshtastic plugin after editing the hop limit, and MAC randomisation tripping a Wi-Fi allowlist [C-W14-019]. Single source, not reproduced; the one-way symptom is consistent with the multicast leak blocking above if a VPN was active, but that is our inference.
- **Code evidence:** ATAK-CIV is GPL-3.0 with source at TAK-Product-Center/atak-civ [C-W8-020]. Its location providers catch a missing GPS or network provider and show a hint instead of crashing [C-W14-015]. Its default build ships 64-bit ARM code, so GrapheneOS's removal of 32-bit ARM support does not block it [C-W14-016, C-W14-017].

**Verdict:** ATAK-CIV is expected to work on GrapheneOS with configuration, but OneMind should not *recommend* it until Appendix A passes on a Pixel 8+ phone. Status of Q298: **partial (blocked: founder-hardware)**.

---

## 3. Investigation: the ATAK crash on a GrapheneOS Pixel Tablet

### 3.1 What we searched (2026-11-11)

| Where | Query | Result |
|---|---|---|
| GrapheneOS os-issue-tracker (GitHub search API) | `ATAK` | 1 hit: #8066, multicast over VPN (not a crash) [C-W14-010] |
| GrapheneOS os-issue-tracker | `"Pixel Tablet" crash` | Pixel Tablet OS bugs, none involving ATAK: #6727 system crash on user switch (open) [C-W14-013], #4306 vendor audio HAL crash (closed) [C-W14-014], #3949 kernel crashes diagnosed as faulty hardware, #5914 Settings crash, #2745 Play crash |
| TAK-Product-Center/atak-civ issues | `graphene OR "pixel tablet" OR tablet crash` | No GrapheneOS or tablet crash issue (2 unrelated issues) |
| All of GitHub | `GrapheneOS ATAK` | No crash report (Meshtastic and unrelated hits) |
| Web (extended search, 4 queries incl. Reddit and the GrapheneOS forum) | ATAK + GrapheneOS + tablet + crash | No crash report; only the Constellation Response blog [C-W14-019] and vendor pages |

The report the founder found in October 2026 research (`context/02` §22) is **not publicly locatable** [C-W14-018]. It may have been in a chat room (GrapheneOS's Matrix rooms are not searchable here), a deleted post, or the earlier handoff document itself, which is offline. It is listed for Zeus in §13 (Q-W14-1).

### 3.2 Facts that constrain the cause

1. **The Pixel Tablet has no GNSS receiver and no modem.** Google's spec page lists only Wi-Fi 6, Bluetooth 5.2, UWB and Cast under "Connectivity and location" [C-W14-011]. On stock Android, Google Play services' network location fills that gap; on GrapheneOS, network location is opt-in and Play location is rerouted to GrapheneOS's own implementation [C-W14-007, C-W14-008]. So on a fresh GrapheneOS Pixel Tablet, **an app may see no location provider at all**.
2. GrapheneOS fixed "Mock Location on devices without any standard location providers (only Pixel Tablet)" in release 2024111700 [C-W14-012]. ATAK users on a tablet often feed position from an external GPS via mock location; before that release, that path was broken on exactly this device.
3. ATAK's own location code (5.5.1.10) handles "no GPS provider" without crashing [C-W14-015]. A crash purely from missing GPS is therefore unlikely on current ATAK; older ATAK builds were not checked.
4. GrapheneOS deliberately turns latent memory bugs into crashes: hardened_malloc aborts on heap corruption, and the per-app compatibility mode switches the app back to Android's allocator [C-W14-005, C-W14-006]. The Pixel Tablet (Tensor G2) has no MTE [C-W14-002], so an MTE abort is ruled out there; a hardened_malloc abort is not. ATAK ships large native libraries (it packages per-ABI native code [C-W14-016]).
5. The Pixel Tablet has had its own GrapheneOS stability issues: a vendor audio HAL crash that led GrapheneOS to exempt that service from hardened_malloc [C-W14-012, C-W14-014], and an open bug where switching user profiles soft-reboots the system [C-W14-013]. A crash that looked like "ATAK crashed" could be the system restarting under ATAK, especially if ATAK ran in a secondary profile.

### 3.3 Ranked hypotheses

| # | Hypothesis | Supporting evidence | Against | Distinguishing test (Appendix A) |
|---|---|---|---|---|
| H1 | **hardened_malloc caught a memory bug in ATAK or a plugin's native code** (app aborts) | GrapheneOS design [C-W14-005, -006]; ATAK native code [C-W14-016] | No public trace | T-W14-03: GrapheneOS shows a "memory corruption detected" crash notice; enabling compatibility mode makes the crash disappear |
| H2 | **Pixel Tablet system-level bug** (system_server restart while switching profiles, or audio HAL crash during voice/video) | #6727 open [C-W14-013]; #4306 [C-W14-014] | Would affect any app | T-W14-04: crash only when switching users or starting audio; the GrapheneOS "system process crash" log names system_server or the audio HAL, not ATAK |
| H3 | **Location edge case on a device with no providers** (old ATAK or a plugin not catching the exception; mock-location bug before 2024111700) | [C-W14-011, -012] | Current ATAK catches it [C-W14-015] | T-W14-02: launch with location off, network location off, no external GPS; then with mock GPS |
| H4 | **Plugin incompatibility or wrong ATAK build** (e.g. a plugin built for a different ATAK version) | General ATAK plugin model; atak-civ issue #14 shows plugin loading edge cases | No specific report | T-W14-05: crash disappears with plugins removed |
| H5 | **Faulty hardware** | GrapheneOS diagnosed one Pixel Tablet's random kernel crashes as hardware [§3.1, #3949] | Rare | T-W14-04: kernel crash reports appear with other apps too |

**Most likely:** H1 or H2. **Least costly to check first:** H1 (one toggle). This is an inference from the evidence above, not a reproduction.

---

## 4. GrapheneOS + ATAK configuration notes (input to the loadout)

| Setting | Why | Evidence |
|---|---|---|
| Sandboxed Google Play: install only if a plugin needs it, in ATAK's profile | Play is a normal app limited to its profile; apps in other profiles cannot use it | C-W14-007 |
| Keep "Reroute location requests to OS APIs" on (default) | Play-using code gets location without granting Play anything | C-W14-007 |
| Location for ATAK: "Allow all the time" | ATAK requests background location (manifest declares ACCESS_BACKGROUND_LOCATION) | atak-civ@9f6893dd:AndroidManifest.xml#L85-L89 |
| Network location on + Wi-Fi scanning on (indoors, Tablet) | Gives fixes without GNSS; cached 15 min for brief offline use | C-W14-008 |
| Exploit protection compatibility mode: off unless a memory-corruption abort is shown | Keeps hardened_malloc protection; enable per app only after a confirmed abort | C-W14-005, C-W14-006 |
| Prefer TAK Server (unicast) over mesh SA multicast when a VPN is on | Multicast over VPN is blocked on GrapheneOS | C-W14-009, C-W14-010 |
| Meshtastic: separate radio + Meshtastic app + ATAK plugin; leave hop limit at default until T-W14-06 passes | Plugin needs the Meshtastic app; a blog reports a hop-limit edit breaking it | C-W8-015, C-W14-019 |
| Wi-Fi MAC: set "per-network" randomisation for the team AP if it allowlists by MAC | Avoids allowlist drop-outs the blog describes | C-W14-019 (inference) |

---

## 5. Samsung S24 Ultra as a no-root client and ATAK device

- **Bootloader:** US Snapdragon Galaxy models have no OEM-unlocking option, and One UI 8 was reported to remove the toggle on global models too [C-W14-022, SECONDARY]. Treat the S24 Ultra as **non-flashable**.
- **Knox fuse:** a one-time e-fuse is set when an unsigned kernel loads or SELinux is disabled; afterwards device-bound keys are lost and Knox functions such as work profiles and Samsung Pay may stop working, permanently [C-W14-021].
- **What still works without root:** Shizuku (Apache-2.0; repo quiet since June 2025) lets tools use ADB-level APIs [C-W14-023]; UAD-ng (GPL-3.0, active) removes preinstalled packages per user via ADB [C-W14-024]; Obtainium (GPL-3.0, active) updates apps straight from their releases [C-W14-025]; Shelter (GPL-3.0) puts apps in a work-profile sandbox [C-W14-026]. Tasker, Good Lock and DeX were discussed in the founding session; not re-verified here.
- **ATAK on the S24U:** stock Samsung with Google Play is the most-tested ATAK environment in the community; the one comparative blog recommends a stock Samsung over GrapheneOS for simplicity [C-W14-019, SECONDARY]. **Fit:** good daily driver and ATAK device; weaker than GrapheneOS on privacy (Google services) and on update longevity (not re-verified here).

---

## 6. De-Googled alternatives that are not Pixels

| Option | Status (2026-11) | ATAK evidence | Fit |
|---|---|---|---|
| **Fairphone Gen. 6 + CalyxOS** | CalyxOS 8.0.5.20 (2026-11-03), Android 17 rollout began 2026-10-01; also Pixel 6–10a and Pixel Tablet [C-W14-027] | None found | Repairable, relockable; ATAK untested |
| **Fairphone Gen. 6/6+ + /e/OS** | Official A16 build [C-W14-028]; sold preinstalled by Murena (`context/02`, not re-verified) | None found | Easiest de-Googled purchase; weaker hardening than GrapheneOS |
| **iodéOS** | Installer for "60+ officially supported devices" (vendor page, archived page did not list models) | None found | Not evaluated further (Tier C) |
| **Volla Phone Quintus/Plinius** | Volla OS or Ubuntu Touch [C-W14-039] | None found | Field chassis option; update lifetime not verified |

---

## 7. Linux phones, Waydroid, CloudTAK

### 7.1 Status

| Project | Status found | Source |
|---|---|---|
| **Nura** (formerly **postmarketOS**) | Renamed 2026-09-27; Alpine-based, mainline kernels; last stable v26.06 (2026-06-21); "not yet ready for everyone" | C-W14-029 |
| **Ubuntu Touch** | 111 devices listed; some ports stale | C-W14-032 |
| **FuriLabs FLX1s** | FuriOS on Dimensity 900, hardware kill switches incl. modem/GPS, USD 499 sale, out of stock | C-W14-030 |
| **Droidian, Mobian** | Debian-based mobile distributions (home pages opened; no lifecycle facts extracted) | sources/W14.md |
| **Sailfish, Librem 5, PinePhone** | Not re-verified (Tier C); founding-session notes stand as UNVERIFIED | — |

### 7.2 ATAK via Waydroid

Waydroid runs Android in a Linux container. Passing the phone's GPS into it is **not built in**: the GitHub issue asking for it has been open since November 2021 with 91 comments of user workarounds [C-W14-031]. ATAK without reliable GPS is not a field EUD. **Answer: no.**

### 7.3 CloudTAK in a browser

CloudTAK is AGPL-3.0 and its Docker Compose deployment exposes the core map; full ETL needs AWS [C-W8-023]. The founder already runs CloudTAK (`context/01`). A browser client works on any Linux phone and uses the browser's geolocation API. **Answer: yes, CloudTAK is the TAK client for Linux phones**, with the caveats that it needs a reachable server (no offline peer-to-peer like ATAK mesh) and is a lighter client than ATAK. AGPL obligations apply only if OneMind modifies and serves it (W8/W16 own the licensing call).

---

## 8. Android's AVF "Linux Terminal"

Android 15 QPR2 introduced an experimental virtual-machine app that runs one Debian VM through a terminal; GrapheneOS shipped it behind developer options from 2025030900 and has since backported tabs, port forwarding and GUI with optional GPU acceleration [C-W14-033]. Useful for a founder to run CLI tools (for example the `onemind` CLI or `ssh`) on a phone. Not a node runtime: one VM, experimental, developer options required. REC-W14-09.

---

## 9. "Build your own OS" levels and the OneMind EUD

### 9.1 The four levels

| Level | What it is | Who does it | Solo-founder cost (estimate, labelled) | When OneMind should |
|---|---|---|---|---|
| **1. App + device owner on an existing OS** | OneMind app; optional fully-managed provisioning (lock task mode, allowlisted apps) via a DPC/MDM [C-W14-034]; Headwind MDM is Apache-2.0 [C-W14-035] | Every MDM vendor; GoTAK-style resellers preload apps on GrapheneOS [C-W14-020] | Weeks to build; low monthly upkeep (app releases + MDM upgrades). *Estimate, not measured.* | **Year 1** for EUD fleets and child devices |
| **2. Own AOSP/GrapheneOS-based build with own keys** | Signed images, relocked bootloader with a custom key (Pixel AVB custom root; W6 Q235) | GrapheneOS (~80 releases/year, every device each time) [C-W14-040]; CalyxOS [C-W14-027] | A continuous security-release treadmill; GrapheneOS itself says device support needs dedicated resources per device [C-W14-041]. *Not sustainable solo.* | **Only via partnership** (GrapheneOS's stated OEM-partner plan [C-W14-041]) or reseller kit; year 2+ |
| **3. Linux-phone distribution** | Nura / Ubuntu Touch / FuriOS-style | Community projects [C-W14-029, -032], FuriLabs [C-W14-030] | High; no ATAK [C-W14-031] | Not planned |
| **4. From scratch** | New phone OS | Huawei (HarmonyOS NEXT) [C-W14-037] | Out of scope | Never |

### 9.2 When does a "OneMind EUD" make sense?

When a paying public-safety or community customer needs **identical, pre-enrolled field devices** in quantity. Then the product is a **kit**: a Pixel with GrapheneOS (installed with its official installer), the OneMind app, ATAK and plugins, enrolled by QR into the customer's OneMind box and MDM. That is level 1 on top of someone else's level 2, which is what the commercial competitor does [C-W14-020]. FirstNet device/app certification and Android Enterprise "recommended" status were **not researched** (Q316 partial).

### 9.3 Child devices (U-3, shared with W13)

A self-hosted box cannot control a child's phone without either the vendor's family system or device-owner provisioning on a dedicated device. Level 1 gives a OneMind path: a fully managed child phone with lock task mode / allowlisted apps [C-W14-034] through an open-source MDM [C-W14-035], plus the DNS-level controls W13 covers. GrapheneOS's per-profile model (Play only where installed [C-W14-007]) suits a "kids' profile" on a shared tablet. W13 owns the legal side (COPPA etc.).

---

## 10. HarmonyOS: lessons on platform sovereignty

- **The kill switch is real.** HarmonyOS NEXT dropped Android compatibility entirely; reaching a reported 100,000 native apps took years (SECONDARY, counts inconsistent) [C-W14-037]. Lesson for OneMind: keep every client path free of a single store, push or cloud dependency (REC-W14-10; C-W11-038…040 already provide F-Droid/Accrescent and self-hosted push channels).
- **"Super device" maps to OneMind's node model.** OpenHarmony's DSoftBus gives unified discovery, connection, topology and data channels over Wi-Fi and Bluetooth, and it is Apache-2.0 [C-W14-036]. OneMind gets the same outcome with NATS (bus), QR/mDNS onboarding (N-4) and the capability layer. DSoftBus code is tied to OpenHarmony system services, so borrowing concepts beats importing code.
- **Microkernel route:** covered by W18 (`28-…`); this file does not change it.
- OpenAtom Foundation governance and the 2022 FCC equipment-authorisation action were **not opened from primary sources** here.

---

## 11. What competitors and peers do

| Who | Phone/EUD approach | Constraints | Constraint fit with OneMind | What OneMind takes |
|---|---|---|---|---|
| **GoTAK** (EUD V3) | Pixel 9 + GrapheneOS + preloaded ATAK stack, USD 1,500 [C-W14-020] | Small vendor, TAK-only, hardware reseller | **High** for the field-EUD kit; low for the wider OS | The kit model (level 1 on GrapheneOS) |
| **GrapheneOS** | Own hardened AOSP, Pixels only; plans OEM partnerships [C-W14-001, -041] | Dedicated security team; ~80 releases/year [C-W14-040] | **Low** to copy (team size); high to build on | Build on it, don't fork it |
| **CalyxOS / Murena (/e/OS)** | Own AOSP builds on Pixels, Fairphones, motos; Murena sells preinstalled [C-W14-027, -028] | Funded non-profit / company teams | Medium (shows the reseller path) | Optional non-Pixel EUD tier |
| **Umbrel, Home Assistant, Olares** | Do not make phone OSes; ship companion apps (W11: Capacitor LarePass, native HA apps) | Small-to-mid teams, box-first | **High** (same box-first constraint) | App-not-OS default (REC-W11-09) |
| **Samsung (Knox)** | Locked bootloader + e-fuse + enterprise MDM [C-W14-021] | Global OEM | Low (cannot copy hardware fuses); medium as a client platform | Support stock Samsung as a client |
| **Huawei (HarmonyOS NEXT)** | Own phone OS from scratch [C-W14-037] | Tens of thousands of engineers, state-backed market | **None** | Lessons only |
| **FuriLabs** | Own Linux phone + FuriOS [C-W14-030] | Small hardware company | Low (no ATAK) | Watch item |

---

## 12. Risks

| Risk | Likelihood | Impact | Mitigation | Trigger to revisit |
|---|---|---|---|---|
| GrapheneOS + ATAK has an unfixable incompatibility (crash or SA) | Low–Medium | Medium | Appendix A gate; fall back to stock Pixel or Samsung for ATAK while keeping GrapheneOS for OneMind app users | Any T-W14-0x fail with no workaround |
| Multicast-over-VPN block persists | Medium | Medium for mesh SA | Use TAK Server unicast; or run SA multicast without the VPN on a trusted LAN | #8066 closed or still open at 6-month recheck |
| Pixel supply/region limits (US eSIM-only, carrier locks) | Medium | Low–Medium | Buy unlocked SKUs; keep a Fairphone/CalyxOS fallback | Pixel SKU changes |
| Google changes Pixel bootloader or AOSP policy | Low | High for the GrapheneOS path | Keep EUD advice OS-agnostic at level 1 | GrapheneOS announcements |
| Samsung locks all models (One UI 8) | Already true for US | Low (S24U stays a client) | No custom-OS plan on Samsung | — |

---

## 13. Open questions for Zeus (to add to `26-…`)

- **Q-W14-1:** Where did you see the GrapheneOS Pixel Tablet ATAK crash (link, chat room, screenshot)? We could not find it publicly. Assumption used: it was a real crash on a GrapheneOS Pixel Tablet with ATAK-CIV and possibly plugins.
- **Q-W14-2 (blocked: founder-decision):** Is Google/Pixel hardware acceptable? **Recommendation:** yes for field EUDs (Pixel 9a/10a + GrapheneOS), not required for anything else; keep Samsung and Fairphone as supported clients. This answers the open row in `26-…` §C.
- **Q-W14-3 (blocked: founder-hardware):** Which ATAK version, plugins and radios are in your loadout, and is the field phone a daily driver or a dedicated EUD? (`context/02` §22 lists these as unknowns.) The Appendix A matrix needs them.

---

## 14. Requirement traceability

| Requirement | Where served |
|---|---|
| UX-5, UX-8 | §1 REC-W14-05, -07; §5; §7.3 |
| U-3 | §9.3, REC-W14-08 |
| M-2, M-5 | §2, §6, §10, REC-W14-01, -06, -10 |
| M-4 | REC-W14-08, §9.2 |
| N-1, N-4, N-6 | REC-W14-02, -04, -08; §10 |
| P-8 | REC-W14-02, -04 (TAK-node profile clients) |
| F-4, F-7, F-15 | §9, §10 |
| D-004, D-005 | Appendix A uses hardware on hand plus one purchase; push per REC-W11-07 |

---

## Glossary

- **EUD (end-user device):** a phone or tablet a field user carries, running ATAK or iTAK.
- **ATAK-CIV / iTAK / WinTAK / CloudTAK:** the TAK clients for Android (civil build), iOS, Windows and the browser.
- **SA (situational awareness):** sharing positions and markers; "mesh SA" uses multicast on a local network without a server.
- **Multicast:** one packet sent to a group address that every listener on the network receives.
- **GrapheneOS:** a hardened Android distribution for Pixels.
- **hardened_malloc:** GrapheneOS's memory allocator that stops programs when it detects heap corruption.
- **MTE (memory tagging):** an ARM hardware feature that catches many memory bugs; on Pixel 8 and later.
- **Exploit protection compatibility mode:** a GrapheneOS per-app switch back to standard Android memory behaviour.
- **Sandboxed Google Play:** Google's apps installed as ordinary apps without special privileges.
- **Tombstone:** Android's crash report file with the stack trace.
- **GNSS:** satellite positioning (GPS, Galileo, etc.).
- **Mock location:** an Android developer feature letting an app supply positions (used for external GPS receivers).
- **Knox Warranty Bit:** Samsung's one-time hardware fuse that records a non-approved boot.
- **Bootloader unlock / relock:** allowing (then forbidding again) installation of a different OS; Pixels can relock with the new OS's key (AVB custom key).
- **DPC / device owner / MDM:** the app that manages a fully managed Android device; an MDM server controls many of them.
- **Lock task mode:** Android's kiosk mode for allowlisted apps.
- **Waydroid:** runs Android apps in a container on Linux.
- **AVF / pKVM:** Android Virtualization Framework and its hypervisor, used by the Terminal app's Debian VM.
- **DSoftBus:** OpenHarmony's distributed communication layer for nearby devices.

---

## Appendix A · GrapheneOS + ATAK founder test (for `22-HARDWARE-LAB-TEST-PLAN.md`)

**Owner:** Zeus · **Time:** about 3 hours for A.1–A.6 on one phone, plus 1 hour per extra device · **Hardware:** one Pixel 8 or later (9a/10a preferred), the Pixel Tablet if available, the S24 Ultra (control), a laptop with `adb` (Android platform-tools), optionally a Meshtastic radio and a Bluetooth GPS. **Decision consequence:** T-W14-01…05 pass on the Pixel phone → GrapheneOS becomes the OneMind-recommended EUD (REC-W14-01). Any fail without workaround → recommend stock Pixel/Samsung for ATAK and keep GrapheneOS only for non-TAK users. **Record results** in a table in `22-…` (device, OS build, ATAK version, plugin list, pass/fail, notes). Do not commit tombstones or bug reports to the public repo; they can contain personal data (GrapheneOS warns about this [C-W14-006]).

**Pass/fail criteria are written before running.**

### A.0 Inventory (answers Q290 phone rows)
```sh
adb shell getprop ro.product.model          # device model
adb shell getprop ro.build.version.release  # Android version
adb shell getprop ro.build.fingerprint      # exact build (GrapheneOS shows grapheneos/… or google/…:user/release-keys)
adb shell pm list packages | grep -i atak   # ATAK package(s) installed
adb shell dumpsys package com.atakmap.app.civ | grep -E "versionName|primaryCpuAbi"
```
Pass: every value recorded.

### A.1 Install
1. Confirm the Pixel is carrier-unlocked: Settings → System → Developer options → "OEM unlocking" is available [C-W14-004].
2. Install GrapheneOS with the official web installer; relock the bootloader; verify the boot key fingerprint shown matches the one on the GrapheneOS install page.
3. Install ATAK-CIV from the source you will use in the field (tak.gov download or Google Play in a profile with sandboxed Play). Record which.
- **Pass:** device boots with a locked bootloader, ATAK launches to the map.

### T-W14-01 · Baseline (no Google Play)
Owner profile, no sandboxed Play. Grant location "Allow all the time"; battery "Unrestricted". Outdoors, wait for a GNSS fix.
- **Pass:** self position appears within 2 minutes; ATAK runs 60 minutes in the background with screen off and keeps updating position (check the track or breadcrumb trail).

### T-W14-02 · Location matrix
Repeat position checks with: (a) GrapheneOS network location on, indoors; (b) location off at launch, then on; (c) Pixel Tablet only: no external GPS, then with a Bluetooth GPS via a mock-location app selected in Developer options.
- **Pass:** no crash in any case; (a) gives a position indoors; (c) shows the "no GPS" hint without crashing, then a position once mock GPS is on (C-W14-012, C-W14-015).

### T-W14-03 · Exploit-protection check (hypothesis H1)
Use ATAK normally for 30 minutes: zoom/pan imagery, load offline maps, open each installed tool, start and stop any video feed.
- If a crash notice says memory corruption was detected: save the notice; capture Settings → System → Developer options → **Take bug report**; then enable **Settings → Apps → ATAK → Exploit protection compatibility mode** and repeat [C-W14-005].
- **Pass:** no crash, **or** crash reproduces without compatibility mode and disappears with it (then: H1 confirmed; report upstream with the tombstone, privately).
- **Fail:** crash persists with compatibility mode on (go to T-W14-04/05).

### T-W14-04 · System-crash check (hypothesis H2/H5, Pixel Tablet)
Enable Settings → Security & privacy → More security & privacy → **Notify about system process crashes** [C-W14-006 source page]. Run ATAK in the Owner profile only, then in a secondary profile, switching profiles three times; start an ATAK voice or video feature.
```sh
adb logcat -b crash -d > atak-crash-buffer.txt   # keep locally, do not commit
```
- **Pass:** no system_server or audio HAL crash. **Fail:** crash names system_server/audio HAL or a kernel crash → H2/H5; note GrapheneOS #6727 [C-W14-013].

### T-W14-05 · Plugins (hypothesis H4)
Remove all plugins, run 15 minutes; add them back one at a time, 10 minutes each.
- **Pass:** no crash. **Fail:** the plugin added last before a crash is the cause; record its version and the ATAK version it targets.

### T-W14-06 · Team SA and mesh
Two devices: the GrapheneOS phone and the S24 Ultra (stock) on the same Wi-Fi.
1. Mesh SA (multicast), no VPN on either: each sees the other within 60 s.
2. Same with Tailscale (or the team VPN) active on the GrapheneOS phone: record whether the S24U still sees it (expected to fail, C-W14-010).
3. Both connected to TAK Server (founder's server or OpenTAKServer on a lab box) over TLS 8089: each sees the other within 60 s.
4. Optional: Meshtastic radio + Meshtastic app + ATAK plugin; send a PLI and a chat both ways; then change the hop limit and repeat [C-W8-015, C-W14-019].
- **Pass:** steps 1 and 3 both directions. Step 2 result documented (it decides REC-W14-04's wording). Step 4 documented.

### T-W14-07 · Sandboxed Google Play variant
Create a second profile with sandboxed Google Play, install ATAK there, repeat T-W14-01 and T-W14-06 step 3.
- **Pass:** same results as without Play. Record any plugin that only works with Play.

### A.2 S24 Ultra control (read-only)
```sh
adb shell getprop ro.boot.warranty_bit        # 0 expected on an untouched device (may be absent on some firmwares)
adb shell getprop ro.boot.flash.locked        # 1 = locked
adb shell getprop sys.oem_unlock_allowed      # 0 = OEM unlocking not allowed
```
- **Pass:** values recorded. **Never** attempt an unlock on this device [C-W14-021].

### A.3 What each result decides
| Result | Decision |
|---|---|
| T-W14-01…05 pass on Pixel phone | REC-W14-01 confirmed; publish the loadout (REC-W14-04) in OneMind docs |
| T-W14-03 shows H1 | Ship the loadout with "enable compatibility mode for ATAK" as a documented exception; file upstream |
| T-W14-06 step 2 fails | Keep the "prefer TAK Server when a VPN is on" rule |
| T-W14-04 fails on Pixel Tablet only | Pixel Tablet stays out of the EUD list (already REC-W14-02) |
| Any unexplained fail on Pixel phone | Downgrade REC-W14-01 to "stock Pixel/Samsung for ATAK" until fixed |
