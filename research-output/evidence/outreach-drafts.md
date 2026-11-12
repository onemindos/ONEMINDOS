# Outreach drafts for Zeus (not sent)

**Owner:** LIC · **Date:** 2026-11-11 · **Status:** drafts only. Under brief rule 5, the research agents never contact vendors. **Zeus sends these** from his own account, through each vendor's public contact route (listed per draft; no addresses are copied here).
**Why:** DC-03 ("10-year lifecycle cost to 2036 per base, per device, at 1k and 10k units") is `partial / blocked: paywalled` because none of the three paid support routes publishes a price [C-W2-006, C-W2-003, C-W2-041]. The critic (pass 1, S2 #12) asked for these drafts. Drafts O-1 to O-3 are the DC-03 quotes. O-4 is a licensing clarification raised by [`license-matrix.md`](license-matrix.md) H-3.
**Serves requirements:** R-3, H-1, H-4, M-8, F-2, N-8, F-11, F-12, P-5

> ### Explain it like I'm the founder
> Three companies sell "long-life" support for the operating systems we might ship: **Canonical** (Ubuntu), **Freexian** (Debian beyond its free support) and **Red Hat** (RHEL and its edge edition). None of them publishes prices, so our 10-year cost answer has holes. These are ready-to-send emails. Each asks for a price per device at 1,000 and 10,000 units to 2036, **and** for the right to ship their software inside OneMind boxes. That second part matters as much as price: Freexian's contract currently says its packages are for the customer's *own* use only [C-W2-004], and Ubuntu needs Canonical's approval for a modified image [C-LIC-011]. Send all three in the same week, so the answers come back together and can be compared.

## Glossary

| Term | Meaning |
|---|---|
| **ESM / Ubuntu Pro for Devices** | Canonical's paid security updates for Ubuntu on devices: up to 10 years, 15 with the Legacy add-on [C-W2-006, C-REF-DC-cost-001] |
| **ELTS** | Freexian's paid Extended LTS for Debian after free LTS ends; for Debian 13, to 2035-06-30 [C-W2-001] |
| **RHDE** | Red Hat Device Edge: RHEL image mode plus MicroShift for small devices, including Jetson Orin [C-W2-041] |
| **Per-device fee** | A price per box shipped (one-time or yearly), the model these vendors use for devices |

## Shared assumptions to state in every request

| Item | Value (state it plainly; Zeus may change it) |
|---|---|
| Company | OneMind OS: an Apache-2.0 open-core home, edge and robotics OS; early stage, founder-led |
| Product | A read-only, A/B-updated OS image, built and signed by OneMind, preinstalled on OneMind boxes and offered as a free download for bring-your-own hardware |
| Architectures and boards | x86_64 (mini PCs, 8–16 GB); arm64 Raspberry Pi 5 / CM5; arm64 NVIDIA Jetson Orin (Nano/NX/AGX), Jetson Thor later |
| Volumes | Scenario A: 1,000 devices over 3 years. Scenario B: 10,000 devices over 5 years |
| Support horizon | Ship 2027–2031; each device supported ≥ 5 years after the end of sale of its model (SEC-07), so to about **2036** |
| Package scope | Base OS (kernel, systemd, OpenSSL, container runtime dependencies), about 400–600 source packages; apps run in containers |
| EU | Will sell in the EU; needs a support period it can declare under the Cyber Resilience Act (SEC-06/07) |

---

## O-1 · Canonical: Ubuntu Pro for Devices + modified-image redistribution

**Route:** the "Contact us" form on https://ubuntu.com/pro/devices (that page publishes no price [C-REF-DC-cost-001]). **Decides:** DC-03 (Ubuntu cost cells), DC-09 (Jetson rootfs), license-matrix H-4, and S1 cells C1/C6 for candidate D.

**Subject:** Quote request: Ubuntu Pro for Devices + redistribution approval for a derived device image (x86, Pi 5, Jetson Orin)

> Hello,
>
> We are OneMind OS, an early-stage company building an open-source (Apache-2.0) operating system for home, edge and robotics devices. We are deciding our base OS for the next ten years and would like a quote and a licensing answer.
>
> **Our product:** a read-only, A/B-updated image that we build and sign ourselves from Ubuntu packages (classic debs, no snaps). We would preinstall it on boxes we sell, and offer it as a download for customers' own hardware. Devices: x86_64 mini PCs, Raspberry Pi 5 / CM5, and NVIDIA Jetson Orin running NVIDIA's L4T on Ubuntu 24.04.
>
> **Questions:**
> 1. **Price of Ubuntu Pro for Devices** per device, for (A) 1,000 devices over 3 years and (B) 10,000 devices over 5 years, one-time and annual options, with coverage to 2036. Is the Legacy add-on needed for that horizon, and at what price?
> 2. **Redistribution.** Your IPRights Policy says modified versions must be approved, certified or provided by Canonical, otherwise trademarks must be removed and binaries recompiled. What agreement would let us ship our derived image (our own branding, Ubuntu packages, our own kernel config where needed)? Is it included in Pro for Devices or separate, and what does it cost?
> 3. **Jetson.** NVIDIA's L4T root filesystem is derived from Ubuntu 24.04. Does an agreement with Canonical cover our redistribution of an L4T-based image on Jetson Orin, and is ESM available for those devices?
> 4. **Raspberry Pi 5:** is Pro for Devices available for a derived image on Pi 5 / CM5?
> 5. **EU CRA:** can Canonical commit, in the contract, to security updates for the covered period, so that we can declare our support period?
> 6. Are there startup or OEM programmes, and minimum volumes?
>
> Thank you,
> [Founder name], OneMind OS · [contact details]

**What we need back:** a per-device price table for A and B; the agreement name and terms for a derived image; a yes/no on Jetson and Pi 5.

---

## O-2 · Freexian: Debian ELTS for Debian 13 on arm64 + redistribution to customers

**Route:** the contact form linked from https://www.freexian.com/lts/extended/ (pricing is quoted per customer from a source-package list and rises every half-year [C-W2-003]). **Decides:** DC-03 (Debian years 2030–2035), S1 cells C1/C6 for candidate A (the ADR-001 choice), W2-R2.

**Subject:** ELTS quote for Debian 13 on amd64 + arm64, and permission to deliver ELTS updates to our customers' devices

> Hello,
>
> We are OneMind OS, an open-source (Apache-2.0) operating system for home, edge and robotics devices, built on Debian 13 "trixie". We are planning support to about 2036 and are considering ELTS for 2030-07-01 to 2035-06-30.
>
> **Scope:** about 400–600 source packages (we can send the exact list from our image build). Architectures: **amd64 and arm64** (Raspberry Pi 5 and generic arm64). Kernel: Debian's kernel on x86/arm64; Raspberry Pi's kernel on Pi 5.
>
> **Questions:**
> 1. **Price** for that package list on amd64 + arm64, for (A) 1,000 and (B) 10,000 deployed devices, and how the half-yearly increase is calculated. Is pricing per package list, per device, or both?
> 2. **arm64:** your page says at least amd64, other architectures on request. Can you commit to arm64 for trixie ELTS, and at what extra cost?
> 3. **Redistribution (critical for us):** the current service order says ELTS packages are for the client's own use and must not be shared with third parties. Our customers own the devices; we deliver updates to them as signed OS images. Is there an OEM/distributor agreement that allows this? If not, could ELTS updates reach customers' devices under any other model?
> 4. **Kernel:** ELTS supports the kernel by backporting a newer kernel version. How would that work with a vendor kernel (Raspberry Pi), or is the kernel ours to maintain?
> 5. **Commitment:** can the contract guarantee coverage to 2035-06-30 for an EU Cyber Resilience Act support-period declaration?
> 6. Could we sponsor Debian LTS (2028–2030) through Freexian at the same time, and what tier fits our size?
>
> Thank you,
> [Founder name], OneMind OS · [contact details]

**What we need back:** a price formula, an arm64 yes/no, and above all a **redistribution yes/no** [C-W2-004]. If redistribution is "no", ELTS cannot be the 2030–2035 plan for shipped boxes, and DC-03 has to price the in-place rebase to Debian 14/15 instead (W2-R6).

---

## O-3 · Red Hat: Red Hat Device Edge on Jetson Orin + RHEL image mode for an OEM appliance

**Route:** "Contact sales" on redhat.com, naming Red Hat Device Edge and the OEM/embedded programme (RHDE on Orin is announced as available [C-W2-041]; price not public). **Decides:** DC-03 (bootc Industrial profile cost), W2-R3, W8-R5, S1 cells for candidate C.

**Subject:** OEM pricing: Red Hat Device Edge (Jetson Orin and x86) and RHEL 10 image mode in a third-party appliance

> Hello,
>
> We are OneMind OS, an open-source (Apache-2.0) OS for home, edge, industrial IoT and robotics. Our Industrial/Enterprise profile is planned on RHEL image mode (bootc) with greenboot and our own Kubernetes apps. We would like OEM pricing and terms.
>
> **Questions:**
> 1. **Price** of Red Hat Device Edge per device on **NVIDIA Jetson Orin (Nano/NX/AGX)** and on **x86 edge boxes**, for (A) 1,000 and (B) 10,000 devices, annual and multi-year, to 2036.
> 2. **Embedding:** can we preinstall RHEL 10 image mode / RHDE on appliances we sell, with our own branding on our layers (we would follow your trademark guidelines)? Which agreement covers that (OEM, embedded, ISV)?
> 3. **Our own Kubernetes:** may we run k3s instead of MicroShift on RHDE and stay supported, or is MicroShift required?
> 4. **Lifecycle:** what is the support end for RHDE on Orin, and how do RHEL 10 minor-release EUS terms apply to fielded devices?
> 5. **Certificates:** which IEC 62443-4-2 certificates apply to RHEL 10 image mode / RHDE, and can an OEM reference them in its own 62443 assessment?
> 6. **Hardware:** Raspberry Pi 5 is not a RHEL platform today; is it on any roadmap?
>
> Thank you,
> [Founder name], OneMind OS · [contact details]

**What we need back:** a per-device price table; the agreement name for embedding; k3s supportability; the RHDE-on-Orin lifecycle.

---

## O-4 · NVIDIA: licensing clarification for an OS vendor (optional, raised by the licence matrix)

**Route:** the licensing contact named in s20 of the Jetson BSP licence (address in the archived text, masked in this repo) and/or NVIDIA Inception / Jetson partner channels. **Decides:** license-matrix H-3, LIC-R5, LIC-R11, W7-R2/R8.

**Subject:** Redistribution of Jetson Linux r39 and Isaac ROS inside a third-party OS image

> Hello,
>
> We build OneMind OS, an open-source OS that will run on Jetson Orin and Thor devices. Before we ship, we would like to confirm our reading of the licences:
>
> 1. **Jetson Linux BSP (NVIDIA Driver License Agreement, v. 2025-02-25):** we plan to redistribute the unmodified BSP binaries in our own A/B image, with the Agreement included, on NVIDIA hardware only. Is that within s1.1(d)? Does replacing the Ubuntu root filesystem with a Debian one change anything on NVIDIA's side?
> 2. **CUDA:** under the Attachment A Jetson clause, may we include the CUDA runtime and libraries in a general-purpose OS image for Jetson, not tied to one application?
> 3. **Isaac ROS:** the Isaac ROS Software License allows distribution inside an application or as unmodified binaries. May we offer NVIDIA's Isaac ROS containers in our app store, and must users accept the licence themselves?
> 4. **Critical Applications:** our users build robots and drones. Is there an NVIDIA programme or agreement that changes the Critical Application terms for such products?
> 5. Is there a partner programme for OS vendors (similar to the Jetson ecosystem partners) that we should join?
>
> Thank you,
> [Founder name], OneMind OS · [contact details]

---

## How the answers feed the research

| Answer | Updates | Where |
|---|---|---|
| O-1 price + agreement | S1 candidate D C1/C6 cells; DC-03 cost range; Jetson G1 rootfs condition | 01 §3.1, 03, 26, license-matrix H-4 |
| O-2 price + redistribution yes/no | S1 candidate A C1/C6; DC-03 2030–2035 years; W2-R2 (no ELTS plan without redistribution rights) | 01 §3.1, 03 |
| O-3 price + embedding terms | S1 candidate C; W2-R3 profile cost; W8-R5 62443 route | 03, 09 |
| O-4 clarifications | LIC-R5, LIC-R11; W7-R8 | license-matrix, 08 |

**Until answers arrive:** price cells stay at the lowest scorecard anchor ("unverified → lowest anchor", critic S2 #9 and #12). This file records no invented numbers. Status for DC-03: `partial; blocked: paywalled (outreach drafted, not sent)`.
