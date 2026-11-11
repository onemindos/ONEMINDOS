# 00 · Executive summary (final for this run)

**Date:** 2026-11-11 (revision 3, final; revision 2 earlier the same day) · **Owner:** FINAL · **Status:** every deliverable in brief §6 exists. The foundation decision is final at `01` revision 3. **Not done:** "loop until dry" (a third completeness-critic pass has not run), the master ledger re-merge, every hardware test, and marking the PR ready (§7)
**Read next:** [`REVIEW-CHECKLIST.md`](REVIEW-CHECKLIST.md) (reading order and approval boxes), then the PDF [`ONEMIND-OS-FOUNDATION-REPORT.pdf`](ONEMIND-OS-FOUNDATION-REPORT.pdf), then [`01-FOUNDATION-DECISION.md`](01-FOUNDATION-DECISION.md) and [`26-OPEN-QUESTIONS-FOR-ZEUS.md`](26-OPEN-QUESTIONS-FOR-ZEUS.md)
**Claim IDs** below resolve in `evidence/claims/*.csv`. This page adds no new facts; it summarises `01` rev. 3, `23`, `24`, `25` and `26`. `evidence/claims/FINAL.csv` is therefore header-only.
**Serves requirements:** RS-1, RS-4, RS-6, RS-7, R-1, R-3, M-6, M-7, N-9, F-9, F-10, F-11, F-12, F-14, A-5, A-6, D-001

> ### Explain it like I'm the founder
> **The answer:** OneMind OS stands on **your own read-only image built from Debian 13**. It keeps **two copies of the OS**, updated by **RAUC**, and switches to a new copy only after Kubernetes proves it is healthy *right now*. It runs **k3s** on every box with 4 GB or more and an SSD, connects small gadgets over **NATS**, and backs up with **restic**. That is ADR-001's core, **confirmed**. Many details changed, and one tool changed: the updater moved from Rugix to RAUC.
> **How sure are we?** Not very, on two choices, and we say so. Debian vs Ubuntu vs Red Hat's bootc, and RAUC vs Mender, are **ties on the scorecard**. Debian and RAUC win on the evidence that is hardest to undo: we may ship Debian without anyone's permission, the Pi 5 path works today, RAUC allows three trial boots and Secure Boot. In the last round we gave Ubuntu and Mender the **same lab exam**. Both passed, and the leads held, narrower. Every choice has a written, testable way back to the runner-up.
> **What only you can do:** ask Canonical and a lawyer the Ubuntu question (Z-01); decide whether security updates install automatically (Z-02); choose who holds the signing keys (Z-04); and let us remove some personal data an early commit pushed to the public branch (Z-28). Then **buy a Pi 5 and a Jetson Orin Nano**, because every test so far ran in emulation.

---

## 1. The answer (from `01` revision 3)

| Layer | Decision | vs ADR-001 | Confidence |
|---|---|---|---|
| Base OS | **Debian 13** core (x86, arm64, Pi 5 on Raspberry Pi's kernel); a `FROM ubuntu:26.04` CI leg as the hedge (lab-proven [C-LAB-ubuntu-2604-leg-011]). **Jetson on NVIDIA L4T Ubuntu 24.04** for the beta, gated on Canonical (Z-01); Yocto meta-tegra + 6.18 LTS tested within 180 days. Ubuntu LTS + RKE2 permitted for GPU servers and robotics simulation after Z-01. **bootc Industrial profile** in year 2, with Fedora IoT as a CI canary | Confirmed, with changes | **Low-medium**: on the fully cited card bootc 64 · Ubuntu 62 · Debian 60, a tie; Debian wins head-to-head (7–4 vs Ubuntu, 5–5 vs bootc, taken on the Pi 5 tier) [C-SCORE-025] |
| Image | OneMind owns the image: a container-defined rootfs turned into A/B disk images. A from-source (Buildroot) build is 4–6× smaller but has only 7–18% fewer CVEs, so the distro base stays [C-LAB-minimal-image-dc20-011] | Confirmed (measured) | High |
| Updates | **RAUC** A/B on x86 and Pi 5, **OneMind-built from a pinned tag (v1.15.2)**, verity bundles only; NVIDIA A/B + OTA on Jetson with a OneMind payload verifier; one release contract. Mender is the lab-passed runner-up | Changed (engine) | **Medium-low**: Mender 62 vs RAUC 61 raw; RAUC wins the tie-break 5–3 |
| Health gate | Commit only on fresh, post-boot signals; apps excluded; 3 tries; watchdog; no auto-retry | Confirmed, made concrete | **High**: six labs, three engines, two bases |
| Secure Boot (x86) | RAUC `efi` backend + one signed UKI per slot; data key on PCR 7 + signed PCR 11; PCR 15 volume check; anti-downgrade; db key on every x86 box from the first shipment; a OneMind-built kernel for the release that enforces Secure Boot with out-of-tree drivers | Changed (layout on day 1) | Medium (emulation only) |
| Install | Flash image, USB installer/rescue ISO, VM images, preinstalled boxes, NVIDIA flash; host-modifying scripts unsupported after image GA; a container/VM developer preview stays | Confirmed | High |
| Kubernetes | **k3s** on platform nodes (≥ 4 GB + SSD; 8 GB recommended), hardened; agent-only on robots and field kits; NATS leaf below; RKE2 only for a FIPS/STIG buyer | Changed | Medium |
| Storage + backups | local-path with a Retain class; restic with three keys; online SQLite backup bound to the k3s version; embedded etcd on hub/Pro/Omni if the 72 h write test passes | Changed (method) | High |
| Plugins (DC-16) | Ten extension points E1–E10; signed-only system extensions; per-vendor driver packs; expiring revocation list | New | Medium |
| CRA | Image = Class I; box classified by its own function; FOSS self-assessment route primary; a notified-body pre-assessment as a parallel track from 2027-Q1 | Changed | Medium |

**ADR-001 verdict (final, `01` §7):** confirmed: D1 own image, D2 Debian core, D3 A/B + signed + gate, D4 k3s on platform nodes, D5 restic. Changed: engine (Rugix → RAUC), datastore method, RKE2/FIPS text, CRA timing, Secure Boot timing. Overturned: Kairos for Jetson, system-upgrade-controller on image nodes, "DOKS in three changes", and "no Fedora/RHEL role".

## 2. Top 10 findings

1. **The base OS is a three-way tie, and Debian wins it head-to-head.** Once every scorecard cell had to carry a source, RHEL-family bootc led on paper (64 vs 62 vs 60). Its lead rests on one documentation-only Pi 5 cell [C-SCORE-025]. Debian beats Ubuntu and draws bootc on the decisive rows: shipping rights, a production Pi 5 path, and precedent. One Pi 5 test (W2-HW-3) settles it.
2. **The fair fight happened, and both leads survived.** Ubuntu 26.04 and Mender ran the same pre-registered battery and passed [C-LAB-ubuntu-2604-leg-011, C-LAB-mender-008…014]. The "only the winner was tested" rows were dropped, and the tie-breaks were recounted.
3. **Stock Mender gives a new version one boot; RAUC gives three.** A power cut during Mender's single trial boot threw away a good update [C-LAB-mender-013].
4. **Distribution RAUC is a trap.** Debian's RAUC 1.13 carries the 2026 CVE fix [C-LAB-rauc-1152-005] but cannot install any update on kernels 6.19 or newer [C-LAB-ubuntu-2604-leg-010]. RAUC 1.15.2 built from upstream passed everything [C-LAB-rauc-1152-011]. OneMind ships its own RAUC.
5. **Nobody ships our exact combination.** No product runs Debian or Ubuntu with RAUC, let alone with k3s [C-DEC-013]. Each layer is proven somewhere else, so the hardware tests are release gates.
6. **"Healthy" must mean healthy now.** A naive gate committed a broken kubelet under every engine; the fresh-signal gate caught it every time [C-LAB-rauc-k3s-gate-008, C-LAB-debian-rugix-023].
7. **Jetson is modified Ubuntu, and its software dies before its hardware.** Canonical's permission covers the robots too [C-REF-DC-cost-007, C-LIC-011]. JetPack 4 ended 26–32 months before its modules stopped shipping [C-REF-W7-T-001], and JetPack 5 ended on 2026-10-30 [C-REF-W7L-001].
8. **Secure Boot works with the layout, with two catches.** It worked in emulation with our own keys and TPM unlock [C-LAB-secureboot-rauc-012…016]. But it booted an old signed kernel [C-LAB-secureboot-rauc-018], and a UEFI db key cannot sign modules for a stock kernel [C-DEC-008…010]. So we add an anti-downgrade rule, and a OneMind-built kernel is needed for the enforcing release.
9. **Plugin sockets must be locked.** systemd extensions accept unsigned images by default [C-REF-W19-security-004]. DC-16 is safe only with OneMind's signed-only enforcement.
10. **Building from source is not a security shortcut.** About 73–80% of known CVEs sit in the kernel either way, and Buildroot has only 7–18% fewer [C-LAB-minimal-image-dc20-011]. Labour, not licences, dominates the 10-year cost (`evidence/lifecycle-cost-2036.md` COST-1).

## 3. Top 10 risks (from `23-RISK-REGISTER.md`; 62 risks in all, 5 Critical)

| # | Risk | L × I | Mitigation | Trigger |
|---|---|---|---|---|
| RR-01 | Jetson software ends before the robot does | 4×4 = 16 | Per-module support periods; meta-tegra LTS exit (LAB-W7-6) | Kernel CVE unfixed in L4T for 30+ days; any JetPack EOL notice |
| RR-02 | k3s upgrade treadmill on offline boxes (8–10 minors to 2036) | 16 | Snapshot-gated stepwise upgrades inside the A/B release | Any box > 2 minors behind |
| RR-03 | Solo-founder load: labour dominates cost | 16 | One pipeline; every "second X" only on a named buyer trigger | Founder hours over budget two months running |
| RR-04 | The live cloud cluster serves public traffic via retired ingress-nginx | 16 | Phase-0 move to Gateway API + Traefik | Any new ingress-nginx CVE |
| RR-05 | CRA route or classification wrong for the image or the box | 16 | Counsel by 2027-Q2 (Z-05); notified-body parallel track | EN 304 626 not cited by ~2027-09 |
| RR-06 | Prompt injection drives a physical action | 3×5 = 15 | Gateway-enforced human approval; capability tokens | First robot adapter ships |
| RR-07 | Signing-key loss or theft (impact-5 rule) | 2×5 = 10 ⇧ | Offline root, HSM, 2-of-3, rotation drill (Z-04) | Any CI credential leak |
| RR-08 | k3s on small and capturable devices | 12 | Agent-only field nodes; hardened re-measure; 8 GB floor if needed | Hardened k3s on Pi 5 leaves < 2 GiB |
| RR-09 | Canonical refuses or overprices modified-Ubuntu redistribution | 12 | Ask now (Z-01); Debian core needs no permission | Canonical's reply |
| RR-10 | Secure Boot downgrade to an old signed kernel | 12 | Version-match gate, recovery UKI, SBAT/key rotation | A CVE'd signed kernel still accepted |

## 4. Decisions Zeus must make (all in `26-…`, with recommendations; dated in `20-…` §2.3)

| When | Decisions |
|---|---|
| **Now / week 1** | **Z-28** purge personal data from branch history (before the PR is marked ready) · **Z-01** Canonical + counsel, now covering Jetson · **Z-37** approve vendor outreach · **Z-30** incorporate (Inception needs it) · **Z-14/Z-24** confirm platform-first inside an image-first plan |
| Weeks 2–8 | **Z-29** trademark clearance · **Z-03** RAUC / Mender / Rugix and **Z-22** third-party host plugins (gate G1, week 4) · **Z-18** x86 boot route (G2, week 6) · **Z-04** key custody, **Z-07** k3s floor, **Z-23** field-node roles (G3, week 8) |
| Weeks 9–21 | **Z-17** robotics GPU flavor, **Z-19** Secure Boot key model, **Z-21** plugin contracts (G4) · **Z-02** auto security updates, **Z-10/Z-27** bootc profile and industrial tests, **Z-12** TAK server, **Z-20** fleet server (G5) · **Z-16** Jetson base, **Z-13** "mirror", **Z-06** support periods (G6) |
| Week 26 and later | **Z-05** CRA route (+ **Z-36** extra counsel questions) · **Z-09** GPU-server flavor · **Z-15** fusing (never in the 180 days) · Z-08, Z-25, Z-11, Z-26 only on a buyer trigger |
| Product calls | **Z-31** first segment · **Z-32** desktop edition · **Z-33** APNs relay · **Z-34** remote-access default · **Z-35** kids' tablet bundle |

Also in `26`: the REQUIREMENTS open questions 2–5 (§B), the recurring Blueprint questions (§C: Pixel yes for field EUDs; the Dell's state via LT-X86-00; the seven-step first slice; a thin Tasks module), all 21 `blocked: founder-decision` items from `24` mapped to Z-IDs (§G), and the access we needed but couldn't get (§D, §F).

## 5. Status and confidence per workstream and deliverable

| WS / file | Topic | Tier | Status (final, 2026-11-11) | Confidence | File |
|---|---|---|---|---|---|
| W1 | Competitor teardowns | A / B / C | **Done.** Tier A: HAOS, umbrelOS, Olares, VillageOS, flagged repos. Tier B: 8 teardowns. Tier C: 16 (Unraid, HexOS, Synology, Cosmos, YunoHost, Runtipi, Cloudron, Puter, Sandstorm, FreedomBox, Coolify/Dokploy, AI boxes, Formant, Foxglove, Viam, balena-for-robots). `MATRIX.md`. Olares update-path citations not re-checked at its pinned tag (critic #19) | High (A), medium (B), low-medium (C) | `02-competitors/` |
| W2 | Base OS | A | Done; 3 refuters per P0; bootc and Ubuntu steelmen; Ubuntu 26.04 lab leg | Low-medium | `03-…`, `01` §3.1 |
| W3 | Image, install, updates | A | Done; Mender, Rugix and Buildroot steelmen; RAUC 1.15.2, Mender and Secure Boot labs. The file's own header still reads "draft"; `01` supersedes it | Medium-low (engine), high (gate) | `04-…` |
| W4 | Kubernetes, DOKS, NVIDIA | A | Done; 3 refuters per P0; Compose steelman. KubeCon NA 2026 days 3–4 not re-checked | Medium | `05-…` |
| W5 | Backups | A | Done; Kopia and embedded-etcd steelmen; restore lab | High | `06-…` |
| W6 | Security, CRA | A | Done; notified-body steelman; Secure Boot lab in emulation | Medium | `07-…` |
| W7 | Robotics foundation fit | A (plan P1) | Done; meta-tegra steelman; no Jetson or RT hardware test | Medium | `08-…` |
| W8 | IoT/IIoT, TAK, mesh | A (rest B) | Done; EL10 bootc steelman; NATS leaf lab | Medium | `09-…` |
| W9 | AI capability layer | B | Drafted (no refuters needed) | Medium | `10-…` |
| W10 | Hardware line | B | Drafted | Medium | `11-…` |
| W11 | Dashboard, clients, XR | B | Drafted; no UI or device tests | Medium | `12-…` |
| W12 | Apps, Market, plugins | B | Drafted | Medium | `13-…` |
| W13 | Family, education, website | C | Drafted | Medium-low | `14-…` |
| W14 | Phones, field devices | C | Drafted; Pixel Tablet crash not found publicly | Medium | `15-…` |
| W15 | World context, scenarios | C | Drafted (cites `01` rev. 2; no conflict with rev. 3) | Medium-low | `16-…` |
| W16 | Business, licensing, GTM | B | Drafted; prices unquoted; trademark search blocked | Medium | `17-…` |
| W17 | Learning path | C | Draft 1 (cites `01` rev. 2) | Medium | `27-…` |
| W18 | Kernel, image ownership, Mac toolchain | A | Done; K2 steelman; Mac lab | Medium-high | `28-…` |
| W19 | Platform and plugin ecosystem | B (DC-16 A) | Drafted; DC-16 decided after 25 refuters; T-W19-01 security variant not run | Medium | `29-…`, `01` §4.8 |
| 20 | 180-day plan | — | Complete: 6 phases, gates G1–G7, every lab test scheduled, capacity, cut list, days 1–10 | Medium | `20-…` |
| 21 | 5–10-year roadmap | — | Drafted with exit criteria and scenario triggers | Medium-low | `21-…` |
| 22 | Hardware and live-cluster tests | — | Complete; **none run** | — | `22-…` |
| 23 | Risk register | — | 62 risks, deduplicated | Medium | `23-…` |
| 24 | Question bank | — | All 335 have a status: 76 answered, 236 partial, 23 blocked (14 hardware, 6 founder-decision, 1 paywalled, 2 live-cluster), plus 34 added questions | — | `24-…` |
| 25 | Traceability | — | All 97 IDs traced (its "F-10 not started" line predates the PDF) | High | `25-…` |
| 26 | Open questions | — | Complete per brief §6 (Z-01…Z-37) | — | `26-…` |
| 30 | Build brief | — | Complete | Medium | `30-…` |
| PDF | Founder report | — | **Built**: 101 pages; `verify_pdf.py` passes (75/75 conversation topics, 36 images embedded, 453 claim IDs in the text, no hygiene hits) | — | `ONEMIND-OS-FOUNDATION-REPORT.pdf`, `report/` |
| Ledgers | Claims, licences, sources | — | 2,704 per-tag claim rows; licence matrix 231 rows; `SOURCES.md` compiled; hygiene log | High (per-tag); see §7 | `evidence/` |

## 6. The VM lab (disposable Lima/QEMU VMs; criteria written before each run; `evidence/lab/PREREGISTRATION.md`)

| Spike | Result |
|---|---|
| Debian 13 + Rugix (x86_64, aarch64) | **PASS** (run 4); found the stale-status trap [C-LAB-debian-rugix-022, C-LAB-debian-rugix-023] |
| Debian 13 + RAUC 1.13, stand-in gate | **PASS** twice [C-LAB-rauc-014…018] |
| RAUC + real k3s gate | **PASS** twice; the naive gate committed a broken kubelet [C-LAB-rauc-k3s-gate-006…010] |
| RAUC under enforced Secure Boot (OVMF + swtpm) | **PASS** twice; downgrade gap found [C-LAB-secureboot-rauc-012…018] |
| RAUC 1.15.2 + real k3s gate | **PASS**; Pi 5 tryboot kit desk-checked only [C-LAB-rauc-1152-011, C-LAB-rauc-1152-017] |
| Ubuntu 26.04 leg | **PASS** on RAUC 1.15.1; **FAIL** for RAUC 1.13 on Linux 7.0 [C-LAB-ubuntu-2604-leg-010, C-LAB-ubuntu-2604-leg-011] |
| Mender 5.2.0 + same gate | **PASS** with the predicted one-try limit [C-LAB-mender-013] |
| DC-20 minimal image, mkosi Debian vs Buildroot | Measured: 4–6× smaller, 7–18% fewer CVEs [C-LAB-minimal-image-dc20-011] |
| Fedora bootc + greenboot (aarch64) | **Mostly PASS**; a power cut in finalize silently downgraded a healthy box [C-LAB-fedora-bootc-011] |
| Fedora IoT bootc + k3s gate | **PASS** on automation; **FAIL** on the 15-minute target (32 min) [C-W2-054] |
| k3s footprint + restore (aarch64) | **PASS**: +936 MiB idle; SQLite and etcd restores [C-LAB-k3s-footprint-restore-007, C-LAB-k3s-footprint-restore-011] |
| W4 k3s vs Podman | **PASS**: 2.50 GiB free of 4 GiB, default unhardened k3s [C-W4-078] |
| W5 restore drill | **PASS**: `etcd-snapshot` fails on SQLite; online `.backup` + token restores [C-W5-001, C-W5-009] |
| W8 NATS leaf buffering | **PASS**: 600/600 delivered [C-W8-050] |
| W18 Mac kernel build | **PASS**: arm64 kernel in 333 s [C-W18-066] |
| W19 sysext/confext | **PASS** functionally; signing and slot switches not tested [C-W19-006…009] |

**What the lab can't show:** real power loss, real PC firmware, Pi 5, Jetson, GPU drivers, RT latency, or a Debian 13 → 14 rebase. These are founder tests in `22-…`, scheduled as gates in `20-…`. The Secure Boot spike was not re-run on RAUC 1.15.2, and RAUC + k3s ran on x86 only.

## 7. What remains, by workstream (brief §9 fallback)

**Against §9's definition of done:**

| §9 item | State |
|---|---|
| Tier A to the teardown, scorecard and adversarial protocols, plus the lab | **Met in emulation.** Every P0 has ≥ 3 refuters, and every runner-up has a steelman. DC-12 and DC-20 have labs but no dedicated refuter. "Loop until dry" is **not met**: pass 2 added 15 gaps, and no pass 3 has run |
| W1–W17 files at tier depth | **Met** |
| Every bank question has a status; DCs fully evidenced | **Met for status**; many DC answers remain `partial` pending hardware |
| All 97 requirement IDs traced | **Met** (`25`) |
| ADR-001 confirmed/changed/overturned | **Met** (`01` §7) |
| 20 and 21 complete | **Met** |
| Every claim in `01` resolves to a primary-source row in `evidence/claims.csv` | **Not met for the master file.** All of 01's IDs resolve in the per-tag ledgers (`evidence/claims/*.csv`), but the master `claims.csv` holds 2,039 of 2,704 rows, and 136 of 01's IDs are missing from it. It needs a re-merge |
| Licence matrix covers every recommended component | **Mostly met** (231 rows, up from 153); not re-audited against critic N5 |
| 28, 29, 30 complete | **Met** (29's header predates `01` rev. 2–3, and `01` §4.8 wins) |
| PDF built | **Met** |
| PR marked ready | **Not done.** Blocked on Z-28 and on committing the working tree; this agent does not commit |

**By workstream:**
- **W1:** re-check Olares §3.3–3.5 at tag 1.12.7 (`e4a353df`). Tier C teardowns are secondary-heavy by design.
- **W2:** W2-HW-3 (bootc on a real Pi 5) decides bootc's paper lead. Canonical's answer (Z-01) can re-open Ubuntu.
- **W3:** hardware tests F1/F2 (power pulls), F-PI5 (RAUC tryboot on a Pi 5), T-W3-04 (Debian rebase with founder hours), T-W3-06 (Jetson A/B gate), Mender F3/F4; an aarch64 RAUC + k3s run; the Secure Boot spike on 1.15.2. Sync 04's header and S2 totals to `01` rev. 3.
- **W4:** re-check the KubeCon NA 2026 day 3–4 NVIDIA announcements after 2026-11-12 (critic N12); a hardened k3s footprint on a Pi 5; read-only checks of the live cluster (LT-CLU).
- **W5:** corrected 72 h etcd-vs-SQLite write test T-W5-03; whole-box restore on hardware (LT-X86-14).
- **W6:** Secure Boot on real firmware (F-SB-1…3), the PCR 15 check (SB-5b), counsel on the CRA (Z-05, Z-36); EN 304 626 correction into `07`.
- **W7:** meta-tegra LAB-W7-6, RT latency on Pi 5 and two Orins, Isaac Sim on Debian; repoint the superseded C-W7-005 in `08`.
- **W8:** LAB-W8-4 (FDO on Debian and EL10 bootc), a Sparkplug TCK run, Flight Control simulation, the 10k fleet test.
- **W9–W12, W16, W19:** Tier B drafts with no refuters (not required). Open: prices (Z-37), trademark (Z-29), T-W19-01…03, UI and device tests.
- **W13–W15, W17:** Tier C drafts. 16 and 27 cite `01` rev. 2; nothing in rev. 3 contradicts them, but their headers should be synced.
- **W18:** T-W18-4 (< 1 h per kernel bump) and the LT-BIZ-05 kernel-lag log decide K1 vs K2.
- **Cross-cutting:** run completeness-critic pass 3; re-merge the master ledger; sync stale headers (03–09, 28 and 29 say "draft"; 25 says the PDF has not started); add `SHA256SUMS`/`versions.md` where critic N11 found them missing; Wayback captures were blocked throughout (pages are saved with sha256 instead); none of this is legal advice.

## Glossary

| Term | Meaning |
|---|---|
| **A/B update** | Two OS copies; the update goes to the idle one, and the box falls back if it fails. |
| **Health gate** | The check that decides whether a new OS copy becomes permanent. |
| **Tie / tie-break** | Two candidates within 3 points on the scorecard; the winner is then chosen on the pre-named decision-critical evidence, never by changing scores. |
| **Refuter / steelman** | An agent told to disprove a conclusion / an agent told to argue for the runner-up. |
| **Loop until dry** | Keep running completeness critics until two passes in a row find nothing new. |
| **Master ledger** | `evidence/claims.csv`: the single file of every claim; the per-tag files are its parts. |
| **CRA** | EU Cyber Resilience Act; main duties from 2027-12-11. |
| **Gate (G1–G7)** | A dated go/no-go point in the 180-day plan. |

## What competitors do (the foundation in one table; detail in `01` §9 and `02-competitors/MATRIX.md`)

| Layer | Home Assistant OS | umbrelOS 2.0 | Olares | OneMind (this decision) | Constraint fit |
|---|---|---|---|---|---|
| Base | Buildroot, one image per board [C-TD-home-assistant-os-003] | Debian 13, snapshot-pinned [C-TD-umbrelos-003] | None of its own; installs on Ubuntu or Debian [C-TD-olares-007] | Debian 13 | umbrelOS is the closest match (small team, consumer box); none of the three runs robots |
| Updates | RAUC A/B, GRUB 3 tries; marks good when the Supervisor starts [C-TD-home-assistant-os-009, C-TD-home-assistant-os-018] | Rugix A/B; commits at daemon start [C-TD-umbrelos-010, C-TD-umbrelos-019] | No A/B; retries forward [C-TD-olares-010] | RAUC (OneMind's own build) with a fresh-signal gate | HAOS's engine on umbrelOS's base; nobody ships the combination [C-DEC-013] |
| Apps | Docker add-ons, privileged Supervisor [C-TD-home-assistant-os-028] | Docker Compose, single node [C-TD-umbrelos-027] | k3s + Helm [C-TD-olares-021] | k3s on platform nodes | Olares matches the k3s choice; single-box products rarely run Kubernetes (`MATRIX.md` §4) |
| Backups | SecureTar v3 encrypted archives [C-TD-home-assistant-os-033] | Kopia, hourly, encrypted [C-TD-umbrelos-030] | restic + etcd snapshots on the same disk [C-TD-olares-026, C-TD-olares-025] | restic, three keys, SQLite online backup | Olares shares the engine; OneMind keeps the datastore copy off the box |
