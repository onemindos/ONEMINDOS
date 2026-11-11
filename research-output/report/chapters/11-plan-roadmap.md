# The first 180 days and the ten-year roadmap {#sec-plan}

> **Explain it like I'm the founder.** The research decided *what* to build on. Two of those choices won only on a tie-break (the base OS, now Ubuntu 26.04 if Canonical allows it, and the update engine), and almost everything was proven in virtual machines, never on a real Pi, Jetson or PC. So the first 180 days do two jobs at once: **build the product in thin slices**, in the Blueprint's order, and **prove the foundation on real metal early**, so a wrong choice shows up in week 4–8, when switching costs days. There are six phases and eight **gates**: dates where you look at test results and follow a rule written *in advance*. After that, the ten-year roadmap has four phases, each with a different job: prove it, become a product, become a platform, become the default.

## The 180 days on one page {#sec-180}

Day 1 is Monday **2026-11-16**; Day 180 is Friday **2027-05-14**. The plan assumes about 45 hours a week from you, with AI coding agents (the second build session) writing most of the code under your review; these hours are planning assumptions, not evidence (`20-PLAN-180-DAYS.md` §2).

| Phase | Weeks · dates | Goal | Blueprint milestone | Gate |
|---|---|---|---|---|
| **P1** Workbench + update engine on metal | 1–4 · 11-16 → 12-13 | Mac workbench, CI, core by script on a Debian VM, first RAUC image in both base legs (Ubuntu 26.04 and Debian 13), x86 update tests on real hardware, **bootc on a real Pi 5 (W2-HW-3)** | M0 Reconcile | G0 (wk 1), G1 x86 update engine + base-OS reading (wk 4) |
| **P2** Secure vertical slice | 5–8 · 12-14 → 01-10 | Identity, agent identity, gateway, action ledger, one read and one bounded action, clean restore; Pi 5, Secure Boot, Jetson proofs | M1 | G2 (wk 6), G3 (wk 8) |
| **P3** Extensions and the Market | 9–13 · 01-11 → 02-14 | Signed packages, the ten sockets (v1-beta), four reference adapters, GPU and kernel-route decisions, robot runtime | M2 | G4 (wk 13) |
| **P4** Disconnected field node + profiles | 14–17 · 02-15 → 03-14 | Offline capture and sync, NATS leaf buffering, `tak-node` and `greenhouse` on Pi 5, one cluster across Pi/x86/Orin | M3 | G5 (wk 17) |
| **P5** Independent owner alpha | 18–21 · 03-15 → 04-11 | Installer, onboarding, QR join, whole-box restore on metal, capability detection, first Market seed set; Jetson base lab; **base lock** | M4 | G6 (wk 21) |
| **P6** Managed appliance beta | 22–26 · 04-12 → 05-14 | Signed release pipeline with offline root, air-gapped rebuild, every release-gate test re-run, a second operator succeeds unaided, "connect a robot" demo | M5 | **G7 beta go/no-go** |

![The 180-day Gantt: phases, gates, and every lab test scheduled against them (from 20 §1).](img/plan-180.png){width=100%}

## The gates: what passes, what fails, and what happens then {#sec-gates}

| Gate | When | GO → | NO-GO → (an alternative already evaluated) |
|---|---|---|---|
| **G0** Workbench ready | 2026-11-22 | Plan as written | No KVM on the Mac → VM labs run in CI; Dell lacks custom Secure Boot keys → Secure Boot tests move to the first ODM candidate |
| **G1** x86 update engine, base-OS reading | 2026-12-13 | RAUC confirmed for x86 (Z-03); bootc passes on a real Pi 5 but its known bugs are still open → no change: the base stays **Ubuntu 26.04**, both legs keep building | RAUC fails on metal → Mender test in week 5; if Mender passes, **the engine flips to Mender** on the engine-neutral layout. **bootc fails on a real Pi 5 (W2-HW-3)** → the base becomes **Debian 13** (6–5), and the Debian leg becomes the default |
| **G2** Pi 5, Secure Boot | 2026-12-27 | Pi 5 tier proven; x86 route = `efi` + signed UKIs | Pi tryboot fails → Rugix's proven Pi integration [C-W3-029]; Secure Boot fails → ship on the GRUB route with the same layout |
| **G3** Platform floor, Jetson, rebase cost | 2027-01-10 | 4 GB Pi 5 is a platform node; hub servers start on embedded etcd | Soak fails → floor rises to **8 GB** and 4 GB boards become NATS leaves; etcd writes too much → SQLite everywhere |
| **G4** GPU, kernel route, AI actuation | 2027-02-14 | Pro GPU runs on the core leg the base decision selects; kernel stays K1 | Stock kernel refuses OneMind-signed modules (expected [C-DEC-008]) → try the OneMind shim route first, K2-hybrid only if it fails. If the base is Debian: GPU fails on Debian, passes on Ubuntu → GPU tier gets the Ubuntu flavor (after Z-01); Isaac Sim fails on Debian (expected [C-REF-DC-robotics-013]) → simulation boxes use Ubuntu |
| **G5** Field profiles + IIoT | 2027-03-14 | `tak-node` and `greenhouse` enter the alpha | FDO blocked on the core legs but works on EL10 bootc → the bootc Industrial profile (AlmaLinux 10 / RHEL 10 image mode) moves into year 1 |
| **G6** Alpha, Jetson base, backup engine, **base lock** | 2027-04-11 | restic stays; Jetson decision recorded (Z-16); **the shipping base is locked** by the decision map: Canonical agrees → Ubuntu; W2-HW-3 failed → Debian; or your logged choice (Z-38) | Canonical refuses and you reject the debranded rebuild → **bootc**, a different build, so the alpha slips by weeks; refused **and** W2-HW-3 failed → **you decide**; no Canonical answer by G6 → you decide (the alpha runs the Debian leg, labelled "base not locked"). Restore fails or takes > 4 h → no beta until fixed; restic runs out of memory where Kopia doesn't → backups flip to Kopia |
| **G7** Beta go/no-go | 2027-05-14 | Public beta: x86 Lite image + Pi 5 Edge profile on a certified-hardware list; Robotics beta on Orin only if G3 and G6 passed | Any release-gate test fails, or no base is locked → **no beta**. "Do not weaken safety to hit a date" (Blueprint) |

**Weeks 1–2, day by day** (`20-…` §7): D1 order the hardware and apply to NVIDIA Inception; D2 inventory the Dell and Beelink (TPM, Secure Boot custom keys, CPU level) and run read-only cluster checks; D3 reconcile every Blueprint contract onto the layer map; D4 the monorepo and a two-legged root-filesystem build (`ubuntu:26.04` and `debian:trixie`); D3 also sends the Canonical and counsel questions (Z-01), asking for a written price; D5 OneMind's own RAUC from the v1.15.2 tag [C-PLAN180-001]. Week 2 brings the first real-hardware update test and ten power pulls on x86, the sysext security test, and the first CI-built image passing the gate in QEMU.

**The cut list, if you fall behind:** first the non-gate validation tests, then the desktop client and XR, then fleet scale at 1k, runner-up tests already settled, the industrial pull-forward, real time, and only then the "connect a robot" demo. **Never cut** the update, power-cut, Secure Boot, restore, sysext-security and AI-actuation tests: each protects users from a bricked or unsafe device.

## The ten-year roadmap {#sec-roadmap}

![The roadmap from 21 §1.1.](img/roadmap-timeline.png){width=100%}

| Phase | Job | Product | Hardware | Team | Revenue | One hard exit criterion |
|---|---|---|---|---|---|---|
| **Year 1** (2026-11 → 2027-11) | Prove the foundation | OS beta → 1.0 on bring-your-own hardware; Market; dashboard; greenhouse and TAK profiles | No own boxes; certified list [C-W10-037] | Solo + contracted counsel | Support, pre-orders, education, grants | First image passing every release gate, run by ≥ 25 outside users before 2027-12-11 |
| **Years 2–3** | Become a product | Lite, Edge, Pro, Robotics profiles; Industrial bootc profile; mirror; WebXR | ODM Lite and Edge boxes, direct | 1–3 hires, release engineer first | Boxes, support plans, certification fees | First major rebase of the locked base (or, on Ubuntu, a priced Pro window) done in the field on ≥ 95% of boxes, no reflash |
| **Years 3–5** | Become a platform | OEM programme; Cluster; public-safety tier on demand | Partners and distributors | 5–12 people (proposal) | OEM fees, fleet console, partner share | ≥ 10 third-party products shipping on OneMind; every SKU inside its declared support period |
| **Years 5–10** | Become the default | One OS from Pi to GPU cluster across two more base majors and the post-Orin Jetson | Second-source silicon (RK3588-class; riscv64 if credible) | Company or foundation that outlives the founder's attention | Platform economics | No robot or box stranded on an unsupported branch; a third party can rebuild and sign a release |

**Year-1 exit criteria** (`21-…` §3.6) include: release gates 100% on Dell, Pi 5 and Orin; **zero** bad commits across at least 200 forced-bad updates (the lab already showed the naive gate fails [C-LAB-rauc-k3s-gate-008]); whole-box restore onto new hardware in under 60 minutes, green monthly for six months [C-LAB-k3s-footprint-restore-011]; a box offline 90 days accepts its next signed update from USB; CRA-ready before 2027-12-11 [C-W6-001]; three third-party robots onboarded by QR by a non-developer in under 10 minutes each.

## The calendar OneMind does not control {#sec-calendar}

![Lifecycles and legal dates the roadmap must fit (21 §1.2; bar starts approximate).](img/external-calendar.png){width=100%}

| Date | Event | What must be done by then |
|---|---|---|
| 2026-10-30 | JetPack 5 ended [C-REF-W7L-001] | Jetson flavor on JetPack 7.2+ |
| 2027-01-14 | EU Machinery Regulation applies [C-W7-045] | Robot decision log in the audit layer |
| 2027-12-11 | **EU CRA applies** [C-W6-001] | First sold image CRA-ready |
| 2028-08-09 | Debian 13 regular security ends [C-W2-001] | If the base is Debian: most boxes on Debian 14 |
| Dec 2028 | Linux 6.12 and 6.18 LTS projected end [C-W18-001] | Kernel hop shipped as an image update |
| May 2029 | ROS 2 Jazzy ends [C-W7-029] | Robot containers on Lyrical or newer |
| **2030-06-30** | **Debian 13 LTS ends** [C-W2-001] | If the base is Debian: zero supported boxes on Debian 13 |
| Jan 2032 | Jetson Orin end of supply [C-W7-001] | Post-Orin robot SKU available |
| Jan 2036 | Pi 5 / CM5 production commitment ends [C-W2-029] | Edge successor board chosen |
| May 2036 | Ubuntu 26.04 support with Ubuntu Pro ends [C-W2-005] | If the base is Ubuntu: boxes rebased to a later LTS, or retired |

## The second build session (F-9) {#sec-build-brief}

`30-NEXT-ULTRACODE-BUILD-BRIEF.md` is the one-shot brief for the AI session that builds release v0. It builds **your own read-only image** from one recipe in two legs, **Ubuntu 26.04** (the decision of record) and **Debian 13**, kept at parity until you lock the base, with nothing Ubuntu-based published before Canonical answers; A/B slots under **RAUC**, **k3s** on top, and the **OneMind Core**: sign-in, the capability gateway, the action ledger, backups, the Market and the dashboard. It works in VMs on the Mac and in CI; for your Pi, Jetson, Dell and Beelink, your cluster, your signing keys and any vendor, it writes a **kit** of exact commands and pass/fail rules for you to run. Success looks like: a signed image boots in QEMU for x86 and arm64 (Pi 5 as a kit); a broken update rolls back by itself; an AI agent asks to switch on a test light and **cannot until you approve on your phone**; a simulated robot arm is discovered, starts observe-only and stops safely when its plugin is revoked; a backup restores onto a fresh VM.

## What competitors did at the same stage (constraint fit) {#sec-plan-competitors}

| Product | Early path | Constraint fit | Lesson |
|---|---|---|---|
| Home Assistant | Software first, boxes years later, foundation-funded [C-W16-012] | High | Revenue from support and partners before hardware |
| umbrelOS | Script installs, then an image, dropped scripts at 1.0 [C-REF-DC-longevity-005] | High | Image is the product |
| Olares | Crowdfunded its box (Kickstarter) [C-W16-018] | Medium | Pre-orders test price before inventory |
| Sandstorm | Enterprise sales too early [C-W16-050] | Medium | Don't lead with enterprise |

**Requirements served:** RS-3, RS-7, M-6, M-7, F-9, F-10, D-002, D-004, R-1, R-3, H-1.
