# Puter: Tier C teardown

**Workstream:** W1 (Tier C) · **Tag:** `TD-tier-c-alt` · **Date:** 2026-11-11 · **Status:** draft, brief (Tier C; no refuter pass required)
**Claims:** `evidence/claims/TD-tier-c-alt.csv` (Puter rows 001–014) · **Sources:** `evidence/sources/TD-tier-c-alt.md`
**Pinned:** `HeyPuter/puter@44bf99f80840a145ecb515668d5bcef393bdd524` (release line 26.11, 2026-11-02) [C-TD-tier-c-alt-012]
**License note:** AGPL-3.0-only [C-TD-tier-c-alt-001]. OneMind may study the patterns but must **not copy code** (D-001, mission §2 rule 4). The name is trademarked separately [C-TD-tier-c-alt-013].

> ### Explain it like I'm the founder
> Puter calls itself an "internet computer". It is a **desktop that runs in a web browser**: windows, a file manager, an app store and a built-in AI helper, all in one browser tab. Most people use the hosted version at puter.com, which has paid plans from USD 10 to 100 a month [C-TD-tier-c-alt-011]. You can also self-host it with Docker [C-TD-tier-c-alt-002].
>
> **It is not an operating system in OneMind's sense.** It has no kernel, no image, no A/B slots and no device drivers. It runs on someone else's Linux or Docker host and only touches files and web apps.
>
> **Why it matters anyway:** it has about 44,000 GitHub stars in under three years [C-TD-tier-c-alt-012], which shows how much people like **"a whole desktop in the browser"**. Its **"user pays" model** is also a new idea: each user's own account pays for the AI and storage they use, so an app developer pays nothing [C-TD-tier-c-alt-008].
>
> **For OneMind:** copy the browser-desktop feel for the dashboard (P-2, UX-1) and think about "user pays" for paid AI in the Market. Do better on what Puter skips: a real OS, pinned and signed versions, rollback, devices and robots, and AI that runs locally by default.

---

## 1. What it is, in one table

| Topic | What Puter does | Evidence |
|---|---|---|
| **Architecture** | Node.js/TypeScript backend in layers (controllers → drivers → services → stores → clients) with plug-in "extensions"; a browser GUI; the Puter.js SDK for third-party web apps | [C-TD-tier-c-alt-010] |
| **Base OS** | None. Self-hosting needs any host with Docker + compose and a domain with **wildcard DNS**, because it routes by subdomain | [C-TD-tier-c-alt-002] |
| **Self-host stack** | Seven containers: Caddy, Valkey, MariaDB, DynamoDB-local, RustFS (S3), a bucket-init job and Puter. Ollama is optional | [C-TD-tier-c-alt-003] |
| **Update / rollback** | `docker compose pull && up -d`; migrations re-apply. **No rollback, no pre-update backup, no pinned version:** the app image is `:main` with `pull_policy: always` | [C-TD-tier-c-alt-004][C-TD-tier-c-alt-005] |
| **App format** | A Puter app is a **web app registered by URL** through the Apps API and opened inside the browser desktop | [C-TD-tier-c-alt-014] |
| **AI features** | Chat driver with ~20 provider adapters (Claude, OpenAI, Gemini, Ollama, OpenRouter…); optional local Ollama, CPU-only by default with the 1.1B `tinyllama` | [C-TD-tier-c-alt-006][C-TD-tier-c-alt-007] |
| **MCP** | A connector on **Cloudflare Workers** lets an MCP client drive the user's Puter files and web hosting with the user's token, including recursive delete | [C-TD-tier-c-alt-009] |
| **Hardware** | None sold. Any Docker host; ARM is not documented | [C-TD-tier-c-alt-002] |
| **Licence** | AGPL-3.0-only + trademark policy | [C-TD-tier-c-alt-001][C-TD-tier-c-alt-013] |
| **Business model** | Hosted subscription (Free 25 MB; Basic $10, Plus $25, Pro $100 a month) and metered "user pays" usage for Puter.js apps | [C-TD-tier-c-alt-011][C-TD-tier-c-alt-008] |
| **Team / activity** | Company-backed (Puter Technologies Inc.); three releases in five weeks; two people hold most commits (bus factor about 2) | [C-TD-tier-c-alt-012] |

## 2. Strengths and weaknesses

| Strengths | Weaknesses |
|---|---|
| A polished browser desktop that needs nothing installed on the client | Not an OS: no image, boot, update safety, drivers or devices |
| "User pays" removes the developer's AI and hosting bill [C-TD-tier-c-alt-008] | Self-host tracks a moving `:main` image with no rollback [C-TD-tier-c-alt-004][C-TD-tier-c-alt-005] |
| Many AI providers behind one driver [C-TD-tier-c-alt-007] | Local AI is an afterthought (CPU, 1.1B model) [C-TD-tier-c-alt-006] |
| MCP access to files and hosting [C-TD-tier-c-alt-009] | The MCP connector runs on Cloudflare, not on the user's box, and can delete recursively by default [C-TD-tier-c-alt-009] |
| Strong community growth [C-TD-tier-c-alt-012] | Wildcard DNS and TLS make self-hosting hard for non-experts [C-TD-tier-c-alt-002] |

## 3. What competitors do (browser-desktop / web-OS pattern)

| Product | Desktop in the browser? | Local AI by default? | Real OS underneath? | Constraint fit to OneMind |
|---|---|---|---|---|
| **Puter** | Yes, the whole product | No (cloud providers; Ollama optional) [C-TD-tier-c-alt-006] | No [C-TD-tier-c-alt-002] | **Low** for the foundation; **candidate** for the dashboard UX only |
| **Olares** | Yes: a "desktop" web domain behind single sign-on [C-TD-olares-036] | AI gateway and agent built in (see `olares.md`) | No own image; installs on Ubuntu/Debian [C-TD-olares-007][C-TD-olares-041] | **Default** for "web desktop on k3s" (same Kubernetes constraint) |
| **umbrelOS** | Web dashboard + app store; apps are `umbrel-app.yml` + Compose [C-TD-umbrelos-026] | Apps (Ollama etc.); built-in MCP [C-TD-umbrelos-039] | Yes, Debian 13 image [C-TD-umbrelos-003] | **Default** for home-box UX |

## 4. Constraint fit and what OneMind does with it

**Constraint fit: Low** for anything below the dashboard. Puter is a hosted web product with no hardware, no Kubernetes, no robotics and no IoT. Its constraints (a company running a cloud SaaS) do not match OneMind's (a self-hosted OS on Pi-to-GPU hardware), so it is **one candidate among others** for UX ideas only (mission §2 rule 2).

| ID | Recommendation | Evidence | Req IDs |
|---|---|---|---|
| REC-TDC-PUTER-01 | Offer a **windowed "Pro" desktop view** in the OneMind dashboard (multi-window file manager, terminal, app windows) next to the simple app grid. Build it ourselves; do not reuse AGPL code. | [C-TD-tier-c-alt-001][C-TD-tier-c-alt-014] | P-2, UX-1, UX-2 |
| REC-TDC-PUTER-02 | Study **"user pays"** for paid cloud AI inside Market apps: the household's own OneMind account pays for metered cloud calls, so third-party app makers carry no AI bill. Keep local inference free. Decision belongs in 13/29 (Market business model). | [C-TD-tier-c-alt-008] | A-1, A-6, F-6, M-8 |
| REC-TDC-PUTER-03 | Do better: the OneMind MCP server runs **on the box**, with per-agent scopes and approval for destructive actions (REC-MATRIX-05), never a third-party relay holding user tokens. | [C-TD-tier-c-alt-009] | AI-2, AI-4, AI-5, U-4 |
| REC-TDC-PUTER-04 | Do better: every component is **version-pinned and signed**, and updates roll back (REC-DEC-05/07). Puter's moving `:main` tag is the anti-pattern. | [C-TD-tier-c-alt-004][C-TD-tier-c-alt-005] | R-1, R-3 |

## Glossary

| Term | Meaning |
|---|---|
| **Web OS / internet computer** | A desktop (windows, files, apps) drawn by a web page, not by an operating system on the machine. |
| **Wildcard DNS** | One DNS record (`*.example.com`) that sends every subdomain to the same server. |
| **`:main` / `:latest` tag** | A container tag that moves with every build, so two installs on different days run different code. |
| **User-pays model** | Each end user's account pays for the AI, storage or bandwidth they use, instead of the app developer. |
| **MCP** | Model Context Protocol: the standard way AI agents call tools. |
| **AGPL** | A copyleft licence: if you run modified code as a network service, you must publish your changes. Incompatible with copying into OneMind's Apache-2.0 core. |
