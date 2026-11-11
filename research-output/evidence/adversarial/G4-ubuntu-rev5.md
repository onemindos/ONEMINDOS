# G4 for the decision of record: Ubuntu 26.04 + RAUC + k3s (critic gap P7-2)

- **Gate under test:** G4, "IoT/IIoT, no blocking limitation" (`evidence/scorecard-weights.md` §2, F-11). It has five sub-checks: (a) industrial protocols as apps; (b) real time; (c) a path to IEC 62443-4-1/4-2; (d) zero-touch onboarding; (e) fleet scale to about 10k devices. **One FAIL fails the gate**, and a gate FAIL removes the candidate from the ranking.
- **Candidate:** D, Ubuntu 26.04 LTS + RAUC A/B + k3s, with JetPack's Ubuntu 24.04 on Jetson (`01-FOUNDATION-DECISION.md` rev. 4, §3.1.1).
- **Prior state:**
  - Before FIX7, 01 cited D·G4 = COND to one ROS 2 platform-tier row [C-W2-028], which covers none of the five sub-checks (critic pass 7, P7-2).
  - FIX7 then added an Ubuntu column to 09 §1, restated DC-02's flip condition, and synced DC-04 (C-FIX7-001…006).
  - This file is a **second, independent primary-source pass** over that column. It follows the method of DC-02's round-4 refuters for Debian: test each sub-check in absolute terms, look for failure evidence, re-run the flip condition and state what would flip it.
- **Lens:** technical / IIoT. **Not blind:** I read FIX7's column before checking it, so this is a verification pass, not a refuter in the §2 rule-7 sense.
- **Date:** 2026-11-11 · **Ledger:** `evidence/claims/G4U.csv` (C-G4U-001…012).
- **Environment limit:** the Ubuntu, Canonical and Launchpad names do not resolve from this session [C-G4U-012]. I did not work around that. Canonical facts below come from Canonical's own GitHub repositories, pinned to commit SHAs. Anything that needs the 26.04 archive itself is a founder step (§6).

> **Explain it like I'm the founder.** Gate G4 asks one question: does anything in the chosen stack *stop* OneMind from serving factories, farms and other industrial sites? We checked the five things industry needs on Ubuntu 26.04 specifically:
> - **Speaking the machines' languages.** Yes. The protocol software is in Ubuntu.
> - **Reacting in time.** Mostly. Canonical's free real-time kernel covers PCs and, by Canonical's own docs, Raspberry Pi. The Pi 5's actual latency still has to be measured.
> - **A route to the industrial security standard (IEC 62443).** Yes. Another vendor already certified a box running ordinary Ubuntu.
> - **Plug-in-and-it-sets-itself-up onboarding (FDO).** Not yet. The open-source client works and has a 1.0 release, but nobody has packaged it for Ubuntu, and the library under it has not passed the official interop test.
> - **Running 10,000 boxes.** Not shown. The pieces exist, but nobody has run that many.
>
> Nothing is a hard "no", so the gate result is **CONDITIONAL** (pass, with listed work items), the same as before. Two corrections came out of this pass. The Pi real-time picture is *better* than FIX7 wrote. The fleet picture is slightly *worse*, because Canonical's fleet tool (Landscape) does not handle A/B image updates.

## 1. Verdict

**D·G4 = CONDITIONAL. No sub-check FAILs. FIX7's result is upheld, with one correction in D's favour, (b), and one new limit, (e).** DC-02's flip condition for the decision of record is **not met**, so the S1 decision of record does not move.

| Sub-check | FIX7 (09 §1) | This pass | Result | What changed |
|---|---|---|---|---|
| (a) Industrial protocols | PASS | PASS | **PASS** | Confirmed with a primary source that the 26.04 broker version speaks MQTT 5: Mosquitto added broker MQTT v5 in 1.6 (2019-04-17), and 2.0.22 dates from 2025-07-11 [C-G4U-003]. Package presence in 26.04 universe is still SECONDARY [C-FIX7-004] |
| (b) Real time | COND ("Pi 4/5 RT variant only for 24.04") | COND, **narrower** | **COND** | **Correction.** Canonical's RT docs list 26.04 with variants **"generic, raspi"** [C-G4U-001]. The 26.04 how-to says to install `linux-raspi-realtime` on Raspberry Pi [C-G4U-002]. FIX7's inference came from a marketing page that does not mention 26.04 for Pi [C-FIX7-002], plus a Repology gap [C-FIX7-003, SECONDARY]. Still open: the docs name no Pi model, the archive entry is unchecked, and Pi 5 latency is unmeasured |
| (c) IEC 62443 path | PASS (path) | PASS (path) | **PASS** | No new evidence. The precedent is classic Ubuntu **22.04** in a certified SL-C 2 host device [C-FIX7-001], plus Canonical's 4-1-audited process [C-STEEL-ubu-010]. The certificate attaches to that product, not to Ubuntu, and no 26.04 certificate exists |
| (d) Zero-touch onboarding | COND ("go-fdo has no release") | COND, **reworded** | **COND** | The **client and server do have releases**: go-fdo-client v1.0.0 (2026-02-19, TPM option) [C-G4U-004] and go-fdo-server v1.0.2 (2026-10-08) [C-G4U-005]. Both are packaged **only as RPMs** for Fedora and CentOS (Packit). The library under them is untagged and still not FIDO interop-tested [C-G4U-006]. On Ubuntu, OneMind builds the `.deb`. On EL10 the distribution does it. The Pi 5 has no TPM [C-W8-041] |
| (e) Fleet scale ~10k | COND | COND, **one new limit** | **COND** | **New:** Landscape, the fleet tool bundled with Ubuntu Pro [C-G4U-009], manages debs and snaps. It acts on at most 100 instances per package action [C-G4U-008], and its docs never mention RAUC or A/B images [C-G4U-008]. Its compliance report covers up to 10,000 instances [C-G4U-007]. So Landscape can be the **inventory and compliance** plane, but not the **OTA** plane. RAUC ships no server and points to hawkBit [C-G4U-010]. hawkBit 1.2.0 shipped today [C-G4U-011]. The hawkBit client is still not packaged for 26.04 [C-FIX7-005, SECONDARY]. No 10k run exists |
| **G4** | **COND** | **COND** | **CONDITIONAL** | Gate result unchanged |

## 2. The absolute test (the DC-02 technical refuter's point, applied to Ubuntu)

DC-02's round-4 technical refuter found that the Debian answer met only a *relative* test: "no sub-check fails *relative to the alternatives*". Shared gaps such as go-fdo and NATS could never trigger the flip. Applied to D in absolute terms:

| Sub-check | Proven today on 26.04? | What is still OneMind-built |
|---|---|---|
| (a) | Yes for the software (MQTT 5 broker [C-G4U-003]; OPC UA, Modbus and CAN stacks [C-FIX7-004, SECONDARY]) | A CVE path for universe packages. Either attach Pro ("Universe and Main" [C-FIX4-001]), or ship the stacks as upstream-pinned app images with OneMind's own CVE SLA (DC-02 rev-4 mitigation 3). The NATS ↔ MQTT 5 bridge is permanent [C-REF4-DC-technical-003] |
| (b) | x86 and generic arm64: yes, free from 26.04 [C-G4U-002, C-STEEL-ubu-008]. Pi: documented [C-G4U-001], not measured | A Pi 5 `cyclictest` measurement only, with no custom kernel, provided the package boots a Pi 5 (§6, F-1). Hard real time stays on a PLC, RTOS or MCU |
| (c) | A path only: an Ubuntu 22.04 product precedent [C-FIX7-001] | OneMind's own 62443-4-1 process and a certified reference box (09 §4). This is the same on every finalist |
| (d) | No | A `.deb` of go-fdo-client, an owner/rendezvous service, and interop testing upstream has not done [C-G4U-004, C-G4U-006]. IDevID needs a TPM, so a Pi 5 industrial SKU needs a TPM HAT or secure element [C-W8-041] |
| (e) | No | The hawkBit updater backport (G4-M5), a hawkBit deployment, and the fleet test (G4-M4) |

**Reading.** Two of five sub-checks are proven in absolute terms ((a) and, apart from the Pi 5, (b)), and (c) is proven as a path. **(d) and (e) are unproven on every finalist.** Compared with the Debian column, D is **stronger** on (b), where Canonical documents a Pi RT kernel and Debian has no Pi 5 RT kernel [C-W7-024, C-W8-040], and on (c), with a direct Ubuntu precedent. D is **weaker** than EL10 on (d), where EL10 gets the FDO packages from upstream [C-G4U-004, C-G4U-005]. On (e) D is equal or slightly weaker, because Canonical's own fleet tool does not cover A/B images. None of these is a FAIL.

## 3. DC-02 flip condition, re-run for the decision of record

- **Condition** (decision-critical.md DC-02, as restated by FIX7): any G4 sub-check FAILs for Ubuntu 26.04 + RAUC + k3s.
- **Result:** **not met.** There are 0 FAILs (§1).
- **If it had been met:** the (h) map in 01 §3.1.6 has no G4 row. A gate FAIL un-ranks D exactly as V8 does (D·G1 → FAIL), giving C 64 · A 63 → **C, RHEL-family bootc** (C–A tie, 6–5; 14 of 14 runs). I re-checked this against 01 §3.1.6 (f) and (g), V8. FIX7's statement matches.
- **Tie-break rows:** the (b) correction touches no row of the (f) table, which has no real-time row. The "IIoT vendor process" row already reads D ≈ C > A. **No count changes.**

## 4. DC-04 "D2 confirmed" wording

The task asked me to update this wording if it no longer holds. **It no longer holds, and FIX7 has already fixed it.**
- DC-04's result block now opens with a "Rev. 4 sync (FIX7, critic P7-2)" bullet. It says "D2 is no longer 'confirmed'", and restates the support-period logic for Ubuntu Pro to May 2036 [C-W2-005, C-W2-006, C-W6-002].
- The remaining "D2 confirmed for amd64" sentence is now labelled "Answer (rev. 3 wording, Debian leg)", which is accurate as history.
- **No further edit is needed.** I would not change DC-04 anyway: it is outside the files assigned to me.
- **One addition for the next DC-04 sync:** the support-period dependency covers more than Pro itself. Without Pro, the protocol stacks (universe [C-FIX7-004]) and the archive RAUC package (universe [C-STEEL-ubu-008]) get no Canonical security commitment. RAUC does not matter here, because OneMind ships its own RAUC build (01 R4 list, REC-DEC-31). The protocol stacks do, unless they ship as app images.

## 5. Mitigations and cost (D leg)

The costs are 09's estimates, adjusted where this pass changes the scope. They are **estimates (labour, solo founder)**, not measured.

| ID | Mitigation on D | Change from 09 | Cost | Gate check |
|---|---|---|---|---|
| G4-M1 | Pi 5 soft real time: install `linux-raspi-realtime` on 26.04, run `cyclictest` under load. Build a bcm2712 RT variant only if the package is missing or fails | **Scope shrinks.** The Canonical package is documented for 26.04 [C-G4U-001, C-G4U-002], so the default is measure-only | about 0.5–1 day if the package works (09's 2–4 days only on the fallback); days 60–120; LAB-W7-1 | (b) |
| G4-M2 | Build go-fdo-client v1.0.0 as a `.deb` in the image pipeline; owner/rendezvous service as an app; fund or run interop | **Reworded.** The client is released [C-G4U-004]; the Ubuntu packaging is OneMind's, unlike EL10 | about 1 week, year 1 (unchanged); interop of unknown size [C-G4U-006]; LAB-W8-4 | (d) |
| G4-M3 | MQTT 5 broker app (Mosquitto [C-G4U-003]) bridged to NATS; Sparkplug TCK | none | about 1 week; days 90–180; LAB-W8-3 | (a) |
| G4-M4 | Fleet test: 100 simulated sites (k3s + NATS leaf + RAUC + hawkBit updater) against one **hawkBit** server, extrapolated to 10k | **hawkBit named as the OTA plane.** Landscape is only for inventory and compliance [C-G4U-007, C-G4U-008, C-G4U-010] | about 2 weeks, year 1; LAB-W8-5 | (e) |
| G4-M5 | Backport `rauc-hawkbit-updater` 1.4 to 26.04 | none (FIX7) | about 1 day, year 1 | (e) |
| G4-M6 *(new)* | Universe CVE coverage for the protocol stacks: either attach Pro for Devices on industrial SKUs [C-FIX4-001], or ship the stacks as pinned app images with OneMind's own CVE SLA | **New on D**, because on Debian the same packages sit in main | **Pro:** unpublished price (Z-01; bracket in `lifecycle-cost-2036.md`). **App images:** CVE triage labour, already counted under DC-02 rev-4 mitigation 3 | (a) |

**Net cost versus the Debian column:** about 1.5–3.5 days *less* on M1 (if the package works), about 1 day *more* on M5, and M6, whose cost sits inside the Pro decision (Z-01) that G1 and G3 already depend on. **No new founder decision.**

## 6. Founder-runnable checks (they need the Ubuntu archive, which is blocked here)

Run these on a networked 26.04 machine (they fit 20 D1, alongside LT-VM-20):

| # | Command (Ubuntu 26.04) | Pass | Fail → consequence |
|---|---|---|---|
| F-1 | On a Pi 5: `apt-cache policy linux-raspi-realtime`, install it, reboot, `uname -v` shows `PREEMPT_RT`, then `cyclictest -m -S -p90 -i200 -D 1h` under `stress-ng` load | The package exists in `resolute` and boots the Pi 5. Max latency is recorded for 09 | Missing or no boot → G4-M1's build fallback (2–4 days); (b) stays COND |
| F-2 | `apt-cache policy open62541 libopen62541-1-dev mosquitto libmodbus5 can-utils rauc-hawkbit-updater` and note the component | The first five are in universe (confirms C-FIX7-004). `rauc-hawkbit-updater` is absent (confirms C-FIX7-005) | Any protocol package absent → it ships as an app image only; (a) still PASS |
| F-3 | `grep -E 'CONFIG_CAN=|CONFIG_NET_SCH_TAPRIO|CONFIG_PTP_1588_CLOCK=' /boot/config-$(uname -r)` | All present (`y` or `m`) | Missing → kernel config item in W18 |
| F-4 | `wpa_cli -v` and `strings $(command -v wpa_supplicant) \| grep -ci dpp` | DPP symbols present (Wi-Fi Easy Connect as a (d) alternative) | Absent → FDO or IDevID only |

## 7. New sources found by looking for failure

- **N1.** Landscape's 100-instance limit per package action and its deb/snap-only scope [C-G4U-008]. This **counts against** D on (e): Canonical's own fleet tool is not an A/B OTA plane.
- **N2.** go-fdo-client and go-fdo-server packaging is RPM-only [C-G4U-004, C-G4U-005]. This **counts against** D relative to EL10 on (d).
- **N3.** The go-fdo README still has the interop warning at the current SHA [C-G4U-006]. This is **against** every finalist.
- **N4.** Canonical's RT docs list a raspi variant for 26.04 [C-G4U-001, C-G4U-002]. Searching for the "24.04 only" gap found the opposite, which **supports** D.
- **N5.** hawkBit 1.2.0 shipped 2026-11-11 [C-G4U-011]. This **supports** the RAUC fleet path.

## 8. What would flip it

- **To FAIL (un-ranks D → C):**
  - `linux-raspi-realtime` is absent from 26.04 **and** no PREEMPT_RT kernel of any kind can be built for the Pi 5. Today this is unlikely, given C-G4U-001 and Debian's v8-rt route.
  - Or go-fdo-client cannot complete DI → TO2 on Ubuntu x86 + TPM while the same release can on EL10 (LAB-W8-4).
  - Or a 1k+ simulated RAUC/hawkBit fleet cannot be driven while Flight Control on bootc can (LAB-W8-5).
- **To PASS:**
  - F-1 passes with a published latency figure.
  - A go-fdo release completes FIDO interop and LAB-W8-4 passes on Ubuntu.
  - LAB-W8-5 shows linear hub cost to 100 sites with health-gated rollback.
  - A 62443-4-2 certificate names a 24.04 or 26.04 classic Ubuntu product.

## 9. Follow-up edits for the orchestrator (not made: outside this file's scope)

1. **(b) wording:**
   - 01 l. 161 and l. 172, 09 l. 46 and l. 57, `decision-critical.md` DC-02 (b) (l. 74), and 24 l. 95 say Canonical's Pi RT variant is "only for 24.04". Replace that with: "Canonical documents a raspi RT variant for 26.04 [C-G4U-001, C-G4U-002]; Pi 5 boot and latency are unmeasured (F-1)".
   - C-FIX7-002 is accurate as a quote of the marketing page. Only the inference built on it changes. Leave the row as it is and cite C-G4U-001/002 beside it.
2. **(d) wording:** where 09, 01 or DC-02 say "go-fdo has no release", write "the go-fdo library is untagged and not interop-tested [C-G4U-006]; go-fdo-client v1.0.0 and go-fdo-server v1.0.2 are released, packaged as RPMs only [C-G4U-004, C-G4U-005]".
3. **(e) in 09 and 20:** name hawkBit as D's OTA plane and Landscape as inventory/compliance only. Add G4-M6 to 09's mitigation table and to 23.
4. **22:** add F-1…F-4 (§6) next to LT-VM-20, or fold them into it.
5. **Ledger merge:** add `claims/G4U.csv` to the master `claims.csv` at the next merge.
