# Coolify and Dokploy: Tier C teardown

**Workstream:** W1 (Tier C) · **Tag:** TD-tier-c-selfhost · **Date:** 2026-11-11 · **Status:** draft
**Claims:** `evidence/claims/TD-tier-c-selfhost.csv` (Coolify C-TD-tier-c-selfhost-080 … 089; Dokploy 100 … 110), plus reused OneMind-target claims from `MATRIX.md` · **Sources:** `evidence/sources/TD-tier-c-selfhost.md`
**Requirements served:** A-1, A-2, A-5, AI-2, AI-4, AI-5, AI-8, U-4, UX-6, R-1, M-8, RS-2, D-001

> ### Explain it like I'm the founder
> Coolify and Dokploy are **"your own Heroku/Vercel"**: you point them at a server (or several), and they build and deploy your apps and databases from Git or Docker Compose, with HTTPS and backups. They are aimed at **developers deploying their own code**, not at households installing apps. Neither is an operating system [C-TD-tier-c-selfhost-086, C-TD-tier-c-selfhost-103].
>
> **Why they matter to OneMind anyway: AI control of a server.** Both already let an AI agent run the platform over MCP. They took opposite approaches:
> - **Coolify** built MCP **into the product**, off until switched on. Each token has abilities (read, deploy, write, delete), tools the token cannot use are hidden, destructive actions need `confirm=true`, and secrets are never returned [C-TD-tier-c-selfhost-082, C-TD-tier-c-selfhost-083].
> - **Dokploy** publishes a **separate MCP server** that turns its whole API into 508 tools. Only *hints* mark which are read-only or destructive, and the AI client decides what to do with them [C-TD-tier-c-selfhost-107].
>
> Coolify's design is the closest any competitor gets to OneMind's plan (per-agent scopes + approvals + audit, REC-MATRIX-05). It is the one to beat.

---

## 1. What was analysed

| Item | Coolify | Dokploy |
|---|---|---|
| Release | **4.7.5**, 2026-11-10 (five 4.7.x releases in two days) [C-TD-tier-c-selfhost-081] | **v0.31.0**, 2026-11-05 [C-TD-tier-c-selfhost-102] |
| Code pin | `coollabsio/coolify` @ `37aaf607` (`CF@37aaf607:`) | `Dokploy/dokploy` @ `1048bcb1` (`DK@1048bcb1:`); `Dokploy/mcp` @ `26799a77` |
| Code read | `routes/ai.php#L6-L7`, `app/Mcp/Servers/CoolifyServer.php#L97-L140`, `scripts/upgrade.sh#L90-L320`, `scripts/install.sh#L542`, `templates/compose/` | `LICENSE.MD`, `*/proprietary/`, `server-setup.ts#L455-L465`, `settings.ts#L31-L80, #L295-L303`, `rollbacks.ts#L34-L90`, `select-ai-provider.ts#L27-L129`, MCP `README.md`, `tools.ts` |
| Licence | **Apache-2.0** [C-TD-tier-c-selfhost-080] | **Apache-2.0 except `/proprietary`** (SSO, SCIM, audit logs, roles, white-label, licence keys), which is source-available [C-TD-tier-c-selfhost-100, C-TD-tier-c-selfhost-101] |

Coolify's code is Apache-2.0, so OneMind *may* adapt it with attribution and a NOTICE. The same holds for Dokploy's non-proprietary code and its MCP server. Patterns are still preferred, because both are PHP/TypeScript web apps and not OS code.

## 2. Field by field

| Field | Coolify | Dokploy |
|---|---|---|
| **Architecture** | Laravel (PHP) control plane in Docker; manages servers over SSH; Traefik or Caddy proxy [C-TD-tier-c-selfhost-089]; 388 Compose service templates [C-TD-tier-c-selfhost-085] | Next.js control plane with Traefik [C-TD-tier-c-selfhost-110], running on **Docker Swarm**, which also provides multi-node [C-TD-tier-c-selfhost-103] |
| **Base OS** | None; many distros incl. Debian, Ubuntu, 64-bit Raspberry Pi OS [C-TD-tier-c-selfhost-086] | None; Ubuntu 18.04–24.04, Debian 10–12; needs IPVS in the kernel, which ZimaOS-style Buildroot images lack [C-TD-tier-c-selfhost-103] |
| **Update / rollback** | Self-upgrade pulls new images (with retry), backs up `.env`, aborts if a pull fails; no signature check found [C-TD-tier-c-selfhost-084]. App rollback to a previous deployment exists (`rollback_application`) [C-TD-tier-c-selfhost-083] | `docker service update --image dokploy/dokploy:<tag>`, tags from Docker Hub, no signature check found [C-TD-tier-c-selfhost-104]. App rollback: each deploy is tagged `<app>:v<n>` and pushed to a registry [C-TD-tier-c-selfhost-105] |
| **App format** | Git repo (buildpacks/Dockerfile), Docker image or Compose; one-click templates are Compose [C-TD-tier-c-selfhost-085] | Git, Dockerfile or Compose; AI can draft Compose from a description [C-TD-tier-c-selfhost-106] |
| **AI features** | **Built-in MCP server**, opt-in, token abilities, hidden tools, `confirm=true`, secrets redacted; 84 tools [C-TD-tier-c-selfhost-082, C-TD-tier-c-selfhost-083] | **BYO-key AI assistant** (OpenAI, Anthropic, Ollama, Gemini, OpenRouter, …) for Compose generation and log investigation [C-TD-tier-c-selfhost-106]; **separate MCP server**: 508 tools, tag filter, advisory read-only/destructive hints [C-TD-tier-c-selfhost-107] |
| **Hardware** | 2 cores, 2 GB RAM, 10 GB disk; Pi supported [C-TD-tier-c-selfhost-086] | 2 GB RAM, 30 GB disk [C-TD-tier-c-selfhost-103] |
| **Business model** | Self-hosted free with every feature; Cloud USD 5/month for 2 servers + USD 3/server [C-TD-tier-c-selfhost-087] | Cloud Hobby USD 4.50/server/month; Startup from USD 15; Enterprise sells SSO, SCIM, audit and white-label (the `/proprietary` code) [C-TD-tier-c-selfhost-108] |
| **Team** | ~66k stars; top three = 92% of contributions [C-TD-tier-c-selfhost-088] | ~38k stars since 2024; top three = 80% [C-TD-tier-c-selfhost-109] |

## 3. Strengths and weaknesses

| | Strengths | Weaknesses |
|---|---|---|
| **Coolify** | The best-guarded MCP in any competitor read so far [C-TD-tier-c-selfhost-083]; truly free self-hosting [C-TD-tier-c-selfhost-087]; large template library [C-TD-tier-c-selfhost-085] | Very fast release churn (5 releases in 2 days) [C-TD-tier-c-selfhost-081]; unsigned self-upgrade [C-TD-tier-c-selfhost-084]; developer tool, not a household OS |
| **Dokploy** | Clear open-core line: enterprise identity and audit are the paid part [C-TD-tier-c-selfhost-101, C-TD-tier-c-selfhost-108]; registry-backed app rollback [C-TD-tier-c-selfhost-105]; BYO-model AI incl. local Ollama [C-TD-tier-c-selfhost-106] | MCP exposes every endpoint with only advisory hints [C-TD-tier-c-selfhost-107]; Swarm (a niche orchestrator) [C-TD-tier-c-selfhost-103]; unsigned self-update [C-TD-tier-c-selfhost-104] |

## 4. What competitors do (on the lesson: "letting AI agents operate the box")

| Product | MCP shape | Guard rails | Constraint fit to OneMind |
|---|---|---|---|
| **Coolify** | Built in, opt-in, 84 tools [C-TD-tier-c-selfhost-082, C-TD-tier-c-selfhost-083] | Token abilities, hidden tools, `confirm=true`, secret redaction [C-TD-tier-c-selfhost-083] | **Candidate**, the strongest pattern; but a developer audience on single servers |
| **Dokploy** | Separate package, 508 tools [C-TD-tier-c-selfhost-107] | Tag filter + advisory hints [C-TD-tier-c-selfhost-107] | Low (too broad by default) |
| **umbrelOS** | Built in; one shared grant set; agents act as the owner [C-TD-umbrelos-037] | Tools registered only when granted [C-TD-umbrelos-023] | **Candidate** (household box, per MATRIX §5) |
| **StartOS** | 208 tools, opt-out, full admin [C-TD-startos-030] | Few | Low |
| **TrueNAS** | Separate preview server [C-TD-truenas-scale-034] | Read-only mode, confirmations [C-TD-truenas-scale-034] | Candidate |
| **OneMind target** | MCP/CLI/API behind gateway-enforced approvals (REC-DEC-13) [C-W9-004] | Per-agent scopes + human approval + audit (REC-MATRIX-05) | Yardstick |

## 5. Constraint fit to OneMind

**Overall: Low as a base** (developer PaaS, not an OS: no image, no OS updates, no household UX, no robotics) **and Candidate for the AI-operations layer and the open-core split.** Coolify is the nearest match for OneMind's MCP guard rails. Dokploy is the nearest match for "what to keep in the paid tier" (enterprise identity and audit).

## 6. What OneMind copies (patterns) and does better

| ID | Recommendation | Evidence | Req IDs |
|---|---|---|---|
| REC-TDC-PAAS-01 | Adopt Coolify's MCP rules as the minimum: off by default, per-token abilities split read / read-sensitive / operate / write / delete, hide tools a token cannot use, require explicit confirmation for destructive acts, never return secrets. OneMind adds per-agent identity, physical-action approvals and an audit log (REC-MATRIX-05). | [C-TD-tier-c-selfhost-082][C-TD-tier-c-selfhost-083][C-W9-004] | AI-2, AI-4, AI-5, U-4 |
| REC-TDC-PAAS-02 | Do **not** auto-generate one MCP tool per API endpoint (Dokploy: 508). Curate task-level tools with server-side enforcement. Hints that only the client reads are not a control. | [C-TD-tier-c-selfhost-107] | AI-2, AI-5 |
| REC-TDC-PAAS-03 | Let the AI layer use any model, local (Ollama) or remote, with the user's own key, as Dokploy does. That fits AI-8's "local plus external models". | [C-TD-tier-c-selfhost-106] | AI-8 |
| REC-TDC-PAAS-04 | Keep each deployed app version addressable (an image digest per revision) so rollback means redeploying a known artefact. | [C-TD-tier-c-selfhost-105] | R-1, A-1 |
| REC-TDC-PAAS-05 | Paid-tier candidates: enterprise SSO/SCIM, audit export and white-label for OEMs. Keep the household security features (MFA, per-user spaces) free. | [C-TD-tier-c-selfhost-101][C-TD-tier-c-selfhost-108][C-MATRIX-012] | M-8, H-4, U-1, D-001 |
| REC-TDC-PAAS-06 | Offer a "developer deploy" Market app (Coolify, Apache-2.0, is a candidate) for users who want to ship their own code, instead of building a PaaS into the OS. | [C-TD-tier-c-selfhost-080][C-TD-tier-c-selfhost-086] | A-2, A-5 |

## Glossary

| Term | Meaning |
|---|---|
| **PaaS** | Platform as a Service: you push code and the platform builds, runs and exposes it (Heroku, Vercel). |
| **MCP** | Model Context Protocol: the standard way an AI agent calls tools on a system. |
| **Token ability / scope** | What a given API key is allowed to do (read, deploy, delete…). |
| **readOnlyHint / destructiveHint** | MCP labels that *describe* a tool. The client may honour them; the server does not enforce them. |
| **Docker Swarm** | Docker's built-in multi-machine scheduler, simpler than Kubernetes and less widely used. |
| **IPVS** | A Linux kernel load-balancing feature that Swarm needs. |
| **Open core** | A free, open-source base product, with some features sold separately. |
