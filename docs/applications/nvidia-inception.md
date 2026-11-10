# NVIDIA Inception: Application Draft (D-006)

**Apply at:** https://www.nvidia.com/en-us/startups/ (the contact form showed a maintenance notice on 2026-11-10; try again or use the "Join" flow).
**Zeus submits this himself.** Fill every `[[ ]]`.

## Eligibility check (quoted from NVIDIA's FAQ, 2026-11-10)
- [ ] "maintain a working website": [[onemindos.dev? or the planned OneMind OS site]]. **Needs a public landing page first.**
- [ ] "be officially incorporated": [[company legal name, incorporation date]]. **Required; NVIDIA asks for the date.**
- [ ] "less than 10 years old"
- [ ] "clear use case for NVIDIA technology" (see below)
- [ ] "actively operated by at least one founder": Zeus Delacruz
- Revenue is **not** required. Excluded: consulting/outsourcing firms, crypto, cloud providers, resellers and distributors, public companies. Position OneMind as a **software platform + OEM hardware company**, not a reseller.

## Business description (draft)
OneMind OS is a local-first "operating system for sovereignty": a self-hosted cloud OS that runs on hardware people own, from Raspberry Pi and mini PCs to GPU servers and NVIDIA Jetson robots. Every device becomes a node in one mesh. Every installed app is automatically available to AI agents through a permissioned capability layer (MCP/REST/CLI). It also integrates robotics, drones, IoT, situational awareness (TAK) and XR. We are building the OS plus a family of OneMind boxes, from Edge to Pro, Robotics and Omni.

## Use of NVIDIA technology (draft)
- **Jetson Orin / Thor:** the OneMind Robotics and Edge-AI tiers. A JetPack 7.x (Ubuntu 24.04) based OneMind image, Isaac ROS in containers, the k8s device plugin + CDI.
- **RTX / DGX Spark:** the OneMind Pro tier. Local LLM inference (vLLM/SGLang/NIM), GPU sharing, Isaac Sim for robot simulation.
- **Kubernetes stack:** GPU Operator (with K3s support), DRA driver, KAI Scheduler and Dynamo for Cluster/Omni deployments.
- **Robotics models:** GR00T and Cosmos for physical AI workloads on customer boxes.
- **Goal:** NVIDIA-optimized OneMind boxes (Pro, Robotics, Omni) as certified hardware.

## Funding status
[[bootstrapped / pre-seed / amount]]

## Pitch deck (required)
Outline: problem (Apple/Google lock-in, cloud AI owns your data) → solution (OneMind OS + boxes) → why now (local AI, robotics, sovereignty trend) → product layers → competition (Umbrel, Olares, CasaOS, HAOS; none do robotics/TAK/mesh/k8s multi-node) → NVIDIA fit → roadmap → team → ask.
*I can build this deck when you're ready.*

> ⚠️ **Public repo:** don't fill this file in place. Copy it to a local `*.filled.md` (gitignored) before adding the company name, email, incorporation date or funding.
