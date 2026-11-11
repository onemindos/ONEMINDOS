# Risks {#sec-risks}

> **Explain it like I'm the founder.** The research raised about 120 risk statements across 30-odd files; many were the same risk seen from different angles, so `23-RISK-REGISTER.md` merges them into **62 risks**. Each has a likelihood, an impact, what we do now, an owner, and a **tripwire**: the specific event that says the risk is turning real. None of them says "change the foundation". Most say "keep the exit cheap and run the test before you depend on it".

![All 62 risks by likelihood and impact. Red cells are critical (score ≥ 16), orange high (12–15).](img/chart-risk-heatmap.png){width=84%}

## The five critical risks {#sec-risks-critical}

| ID | Risk | Mitigation now | Tripwire |
|---|---|---|---|
| **RR-01** | **Jetson software ends before the robot does.** JetPack 4 ended 26–32 months before Nano/TX2 NX stopped shipping [C-REF-W7-T-001]; JetPack 5 ended 2026-10-30 [C-REF-W7L-001]; fixes land only at branch head [C-REF-W7-T-005] | Per-module support periods; A/B from the factory; track every JetPack major and point release; meta-tegra LTS route as the exit | A JetPack branch ends with OneMind robots still on it |
| **RR-02** | **Kubernetes upgrade treadmill on offline boxes.** About 8–10 minors to 2036, none skippable [C-W4-012] | Snapshot-gated stepwise upgrades inside the A/B release; support window in the CRA declaration | A box returns after a year offline, 2–3 minors behind |
| **RR-03** | **Your own time.** Labour, not licences, dominates the 10-year cost on every base (about 1,680 base + 1,480 CRA hours on Debian, computed in `evidence/lifecycle-cost-2036.md`) | One image pipeline; three plugin contracts in beta; costed review plan; release engineer as first hire | A gate slips more than a week, or < 80% of a phase is done |
| **RR-04** | **Your cloud cluster still serves public traffic through ingress-nginx**, retired with no security fixes since March 2026 [C-W4-016] (reported state) | Phase-0 move to Gateway API + Traefik before any other conversion work | Any new ingress-nginx CVE, or public exposure found by the read-only check |
| **RR-05** | **CRA route or classification wrong** for the image or the box [C-REF-W6-technical-008] | Counsel opinion (Z-05); decide by 2027-Q2; notified-body pre-assessment in parallel from 2027-Q1 | Counsel disagrees with the FOSS route, or a harmonised OS standard is cited |

## The high risks, in one line each {#sec-risks-high}

| ID | Risk | Key mitigation |
|---|---|---|
| RR-06 | Prompt injection drives a physical or destructive action [C-W6-068] | Gateway-enforced human approval; tainted-data rules |
| RR-07 | Signing-key loss or theft, including the module key and the root's own lifetime | Offline root, HSM, 2-of-3, rotation drill, vendor-exit clause |
| RR-08 | k3s on small, capturable devices exposes every Secret [C-REF-W4-security-008] | Agent-only robots; hardened re-measure; 8 GB floor if needed |
| RR-09 | Canonical refuses or overprices modified-Ubuntu redistribution, now blocking Jetson too [C-REF-DC-cost-007] | Ask now (Z-01); meta-tegra lab; Debian core needs no permission |
| RR-10 | Secure Boot downgrade [C-LAB-secureboot-rauc-018] | Version-match gate rule; SBAT and key rotation |
| RR-11 | A third-party plugin persists through an unsigned extension [C-REF-W19-security-004] | Signed-only policy; T-W19-01 as the ADR condition |
| RR-12 | Secure Boot enforcement forces a OneMind-built kernel on a solo founder [C-DEC-008] | Plan K2; measure bump time; seek a console-free route |
| RR-13 | Debian 13 → 14 rebase costs more than budgeted; Pi paced by Raspberry Pi | Timed rebase drill with founder-hours; pinned Pi archive |
| RR-14 | Hardware price and supply volatility [C-W10-037, C-W10-034] | No own boxes in year 1; second-source SKUs |

The remaining 16 high, 30 medium and 6 low risks are in `23-RISK-REGISTER.md` §4, with a deduplication map in §6 showing where each original risk statement went. Also tracked: Pi 5 real time unreliable under load [C-REF-DC-technical-001] and k3s crashing in Go's FIPS-only mode [C-REF-DC-longevity-010].

## What competitors do about these risks (constraint fit) {#sec-risks-competitors}

| Risk | Competitor practice | Constraint fit |
|---|---|---|
| Bad update bricks a box | Home Assistant OS: RAUC A/B, 3 tries [C-TD-home-assistant-os-009], but commits while unhealthy [C-TD-home-assistant-os-018] | High; OneMind adds the fresh gate |
| Key compromise | umbrelOS beta: offline root, M-of-N signers, two-source revocation [C-TD-umbrelos-013] | High; copy the design for release 1 |
| Key person leaves | Every small competitor carries it [C-MATRIX-005] | High; document, automate, hire a release engineer first |
| Licence change backlash | HashiCorp, Elastic, Redis [C-W16-007, C-W16-008, C-W16-009] | High; stay Apache-2.0, protect the trademark |
