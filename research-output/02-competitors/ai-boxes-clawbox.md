# ClawBox and other AI boxes: Tier C teardown

**Workstream:** W1 (Tier C), with W10 (hardware) · **Tag:** `TD-tier-c-alt` · **Date:** 2026-11-11 · **Status:** draft, brief (Tier C; no refuter pass required). **Mostly vendor marketing:** no ClawBox source code, image or update client is public, so nothing here is checked against code.
**Claims:** `evidence/claims/TD-tier-c-alt.csv` (rows 042–053), plus reused C-W10-024, C-W10-027, C-W10-031/032, C-TD-olares-045/046, C-TD-umbrelos-046/047, C-TD-casaos-zimaos-039 · **Sources:** `evidence/sources/TD-tier-c-alt.md`
**Scope:** ClawBox (ID Robots OOD) in depth; Beelink SER10 MAX, ACEMAGIC "OpenClaw Pre-installed" mini PCs, ClawBox Workstation (DGX Spark), Olares One and Umbrel Home as the comparison set.

> ### Explain it like I'm the founder
> In 2026 a new product category appeared: **the "AI agent box".** You buy a small computer with an AI assistant already installed (usually **OpenClaw**, sometimes **Hermes Agent**), plug it in, and it answers you on Telegram or WhatsApp, reads your inbox and automates your browser around the clock [C-TD-tier-c-alt-048][C-TD-tier-c-alt-045].
>
> **ClawBox** is the purest example: an NVIDIA **Jetson Orin Nano Super** (8 GB) in a case, EUR 749, with optional EUR 9 or 49 monthly plans [C-W10-024][C-TD-tier-c-alt-044]. Mini-PC makers (Beelink, ACEMAGIC) now ship OpenClaw pre-installed too [C-TD-tier-c-alt-051][C-TD-tier-c-alt-052].
>
> **What it tells OneMind:** people will pay for "AI that lives in my house and just works", and Jetson is already a consumer AI box. **The weak spots are exactly where OneMind is strong:** ClawBox runs **Ubuntu 22.04, whose free security updates end in May 2027** [C-TD-tier-c-alt-042][C-TD-tier-c-alt-043]; it uses dev-kit-class Jetson hardware that NVIDIA says is not for production [C-W10-027]; its update and rollback system is not published; and the agent's skill marketplace has already shipped malware [C-TD-tier-c-alt-053]. These boxes are **one agent app on a box**, not an OS with a Market, permissions, robots and IoT.

---

## 1. ClawBox in one table

| Topic | What ClawBox does | Evidence |
|---|---|---|
| **Architecture** | Appliance: Ubuntu + OpenClaw (or Hermes Agent) as a service, local models (Qwen2.5 3B, Whisper, Kokoro, LLaVA 7B, CodeLlama 7B), messaging bridges, web UI at `clawbox.local`; "no Docker, no terminal" for the user, **full SSH root** for those who want it | [C-TD-tier-c-alt-048][C-TD-tier-c-alt-045] |
| **Base OS** | "ClawBox OS (JetPack 6, Ubuntu 22.04)", i.e. NVIDIA's L4T Ubuntu | [C-TD-tier-c-alt-042] |
| **OS lifecycle** | Ubuntu 22.04 standard security ends **May 2027**; ESM (paid Ubuntu Pro) to May 2032 | [C-TD-tier-c-alt-043] |
| **Update / rollback** | "Over-the-air updates" from "a release we pinned and tested", security fixes fast-tracked. **Mechanism, signing and rollback are not published** (UNVERIFIED beyond the claim) | [C-TD-tier-c-alt-045] |
| **App format** | None of its own; the agent's skills (OpenClaw "Skills", ClawHub marketplace) are the extension point, plus a ClawBox Store page | [C-TD-tier-c-alt-053] |
| **AI features** | Local small models + optional cloud (Claude is the "main supported cloud provider"); Pro/Max plans add a Coding Agent, "Memory Shard", cloud voice and remote access | [C-W10-024][C-TD-tier-c-alt-044] |
| **Hardware** | Jetson Orin Nano Super, 67 TOPS, 8 GB, 512 GB NVMe, 7–25 W. **Workstation** model on DGX Spark | [C-W10-024][C-TD-tier-c-alt-047] |
| **Licence** | Agents are MIT (OpenClaw © 2026 OpenClaw Foundation; Hermes Agent © 2025 Nous Research); ClawBox OS itself has no published licence or source | [C-TD-tier-c-alt-049][C-TD-tier-c-alt-050] |
| **Business model** | EUR 749 hardware once; free plan with weekly allowances; Pro EUR 9/month, Max EUR 49/month; sold direct by ID Robots OOD (Bulgaria), 2-year warranty | [C-TD-tier-c-alt-044][C-TD-tier-c-alt-046] |

## 2. The wider AI-box field

| Box | Hardware | OS / agent | Price | Constraint fit to OneMind |
|---|---|---|---|---|
| **ClawBox** | Jetson Orin Nano Super 8 GB [C-W10-024] | L4T Ubuntu 22.04 + OpenClaw/Hermes [C-TD-tier-c-alt-042] | EUR 749 + optional plans [C-TD-tier-c-alt-044] | **Medium:** same Jetson + agent idea as OneMind Robotics/Lite, but a single-app appliance with no Market, no k3s |
| **ClawBox Workstation** | NVIDIA DGX Spark [C-TD-tier-c-alt-047] | DGX OS (Ubuntu-based) [C-W10-031] + OpenClaw | Sales quote; Spark itself USD 4,699 MSRP [C-W10-032] | **Low–medium:** office inference server; OneMind's Omni tier competes |
| **Beelink SER10 MAX** | x86 mini PC, up to 48 GB as video memory in the test | Ubuntu + OpenClaw + llama.cpp, Qwen-3.5 9B [C-TD-tier-c-alt-051] | (not ledgered) | **Low:** a PC with an app pre-loaded |
| **ACEMAGIC F2A / F5A / M1A** | Ryzen AI mini PCs | "OpenClaw Pre-installed" (F2A); others Windows 11 + WSL2 [C-TD-tier-c-alt-052] | (not ledgered) | **Low:** Windows-first |
| **Olares One** | RTX 5090 Mobile 24 GB, 96 GB RAM [C-TD-olares-045] | Olares (k3s) with agent apps | USD 4,999 [C-TD-olares-046] | **Default** for the GPU "AI home cloud" (k3s, Market) |
| **Umbrel Home** | Intel N150, 16 GB [C-TD-umbrelos-046] | umbrelOS + agent apps from the store | USD 499–949 [C-TD-umbrelos-047] | **Default** for the household box |
| **ZimaOS Blue** (software) | ZimaOS boxes | MIT agent runtime "inspired by OpenClaw" [C-TD-casaos-zimaos-039] | — | Shows OS vendors absorbing the agent category |

## 3. Strengths and weaknesses (ClawBox)

| Strengths | Weaknesses |
|---|---|
| Five-minute setup, near-silent, 7–25 W: an always-on agent at router-level power [C-W10-024][C-TD-tier-c-alt-048] | OS base loses free security support in May 2027 [C-TD-tier-c-alt-043] |
| Clear pricing: hardware once, optional plans [C-TD-tier-c-alt-044] | 8 GB shared memory caps local models at small sizes [C-W10-024] |
| Agent choice (OpenClaw or Hermes), both MIT [C-TD-tier-c-alt-049][C-TD-tier-c-alt-050] | Dev-kit-class Jetson; NVIDIA: "not intended for production use" [C-W10-027] |
| Hardened, pinned agent releases instead of tracking upstream [C-TD-tier-c-alt-045] | Update, signing and rollback mechanisms not public [C-TD-tier-c-alt-045] |
| — | Agent skill marketplace already carried malware [C-TD-tier-c-alt-053]; no OS-level permission layer is documented |

## 4. Constraint fit and what OneMind does with it

**Constraint fit: Medium.** The hardware (Jetson), the buyer (privacy-minded households and small offices) and the "agent always on" use case overlap with OneMind Lite/Robotics and Hermes. The product does not: it is one agent on a vendor Ubuntu, with no app platform, robotics, IoT or multi-node story. So it is a **market signal and a pricing anchor**, not a foundation default.

| ID | Recommendation | Evidence | Req IDs |
|---|---|---|---|
| REC-TDC-AIBOX-01 | Ship **OpenClaw and Hermes Agent as first-class Market apps** (both MIT), pinned and tested per OneMind release like ClawBox does, but behind OneMind's permission gateway rather than with root on the box. | [C-TD-tier-c-alt-049][C-TD-tier-c-alt-050][C-TD-tier-c-alt-045] | AI-2, AI-4, AI-5, A-1 |
| REC-TDC-AIBOX-02 | Treat **agent skills as plugins** under OneMind's plugin rules (signed publishers, review tiers, revocation list, sandbox; 29 / REC-DEC on E1–E10). The ClawHub malware shows unsigned skill stores get attacked within weeks. | [C-TD-tier-c-alt-053] | A-5, A-6, U-4, AI-5 |
| REC-TDC-AIBOX-03 | Publish a **support period per box SKU** and never ship a box whose base OS loses free security updates inside the warranty (ClawBox: 2-year warranty vs Ubuntu 22.04 standard support to May 2027). For Jetson boxes this means L4T on Ubuntu 24.04 now and the meta-tegra path (01, REC-DEC-01/12). | [C-TD-tier-c-alt-043][C-TD-tier-c-alt-046][C-TD-tier-c-alt-042] | R-2, R-3, H-1 |
| REC-TDC-AIBOX-04 | Build the OneMind **Lite/Robotics** box on **production Jetson modules**, not dev-kit-class boards, and say so in marketing as a differentiator against ClawBox. | [C-W10-027][C-W10-024] | H-1, R-3, M-7 |
| REC-TDC-AIBOX-05 | Use ClawBox as the **price anchor** for a Jetson AI box (EUR 749 + optional EUR 9/49 plans) in 11 and 17: hardware once, an optional plan for cloud extras, local use free. | [C-TD-tier-c-alt-044] | H-1, M-8, F-6 |

## Glossary

| Term | Meaning |
|---|---|
| **AI agent box** | A small computer sold with an AI agent pre-installed and running all day. |
| **OpenClaw / Hermes Agent** | Two popular open-source (MIT) AI agent programs that act on your behalf through chat apps, a browser and "skills". |
| **Skill** | An add-on that teaches an agent a new task; often a `SKILL.md` file plus scripts. |
| **JetPack / L4T** | NVIDIA's software for Jetson: Jetson Linux (L4T) is a modified Ubuntu plus drivers; JetPack adds CUDA and AI libraries. JetPack 6 is on Ubuntu 22.04. |
| **ESM** | Ubuntu's paid "Expanded Security Maintenance" after the free five years end. |
| **Dev kit vs production module** | A dev kit is for building and testing; NVIDIA sells separate production modules with longer warranty for products. |
| **TOPS** | Trillions of operations per second: a rough measure of AI chip speed. |
