# Cosmos Cloud (Cosmos-Server): Tier C teardown

**Workstream:** W1 (Tier C) · **Tag:** TD-tier-c-selfhost · **Date:** 2026-11-11 · **Status:** draft
**Claims:** `evidence/claims/TD-tier-c-selfhost.csv` (C-TD-tier-c-selfhost-001 … 013), plus reused OneMind-target claims from `MATRIX.md` · **Sources:** `evidence/sources/TD-tier-c-selfhost.md`
**Requirements served:** P-1, A-1, U-1, U-4, U-5, UX-6, R-1, AI-2, N-1, RS-2, D-001

> ### Explain it like I'm the founder
> Cosmos is a **control panel you install on top of an ordinary Linux box with Docker**. It is not an operating system. In one program it bundles an app store, a reverse proxy that gives each app an HTTPS address, a login server for all your apps, a VPN, backups and disk management [C-TD-tier-c-selfhost-003, C-TD-tier-c-selfhost-008].
>
> **Why it matters to you:** its paid multi-server feature, "Constellation", joins several boxes together with a **Nebula VPN and a NATS cluster**. That is the same bus OneMind already runs [C-TD-tier-c-selfhost-007]. So a one-person project has already shipped "many machines, one NATS bus, one dashboard" to home users.
>
> **Two warnings.** (1) Its licence is *not* open source. Commons Clause forbids selling it, and an "anti-tampering" clause ends your rights if you get around its paywall [C-TD-tier-c-selfhost-001]. Study the ideas only. (2) It updates itself by replacing its own files after an **MD5 check**, with no signature and no way back [C-TD-tier-c-selfhost-004, C-TD-tier-c-selfhost-005]. OneMind's signed A/B updates are much safer.

---

## 1. What was analysed

| Item | Value |
|---|---|
| Release | **v0.23.4**, published 2026-08-30. The 0.24.0 series is still "unstable" pre-releases (unstable031 on 2026-11-08) [C-TD-tier-c-selfhost-002] |
| Code pin | `azukaar/Cosmos-Server` @ `69c53038` (master = v0.23.4). Citation form `CO@69c53038:path#L` |
| Code read | `LICENCE`, `dockerfile`, `src/update.go#L66-L150`, `src/launcher/launcher.go#L121-L199`, `src/market/init.go#L40-L48`, `src/pro/index.go`, `src/backups/restic.go`, `src/constellation/` (NATS + Nebula files), `changelog.md` |
| Licence posture | Apache-2.0 **plus Commons Clause plus an Anti-Tampering Clause** [C-TD-tier-c-selfhost-001]. OneMind (Apache-2.0, D-001) **may study it but must not copy code**. |

## 2. Field by field

| Field | Cosmos (evidence) |
|---|---|
| **Architecture** | One Go server, shipped as a Docker container or a binary. It owns the Docker socket and acts as the gateway: reverse proxy with automatic HTTPS, an OpenID Connect authorization server with 2FA, a container manager, a VPN, monitoring, cron, restic backups and MergerFS/SnapRAID storage [C-TD-tier-c-selfhost-008]. Multi-server "Constellation" adds a Nebula overlay network and a NATS JetStream cluster to sync config. 0.23.00 swapped MongoDB for SQLite/Postgres and oplog sync [C-TD-tier-c-selfhost-007]. |
| **Base OS** | None of its own. The container is built `FROM debian:12` [C-TD-tier-c-selfhost-003]. The host is whatever Linux with Docker the user has. |
| **Update / rollback** | Fetches the release list from the GitHub API (the Pro build uses a vendor endpoint). It checks the zip against an **MD5 file from the same release** and unzips it over the install folder [C-TD-tier-c-selfhost-004, C-TD-tier-c-selfhost-005]. There is **no signature, no A/B and no rollback** of Cosmos itself. Containers get "automatic updates" from the UI. Host OS updates are the user's job. |
| **App format** | "cosmos-compose" blueprints: Compose-like JSON plus proxy routes. The default store is a JSON index on GitHub Pages [C-TD-tier-c-selfhost-006]. Any `docker-compose` file can be imported [C-TD-tier-c-selfhost-008]. |
| **AI features** | **None in the code.** A search for MCP, OpenAI, Ollama and LLM returned no files [C-TD-tier-c-selfhost-011]. |
| **Hardware** | amd64 and arm64 binaries [C-TD-tier-c-selfhost-003]. Marketed for a home server, NAS or Raspberry Pi with one Docker command [C-TD-tier-c-selfhost-013]. No hardware is sold. |
| **Licence** | Source-available, with no right to sell. Rights end on tampering [C-TD-tier-c-selfhost-001]. The paid code is not in the public tree: `IsPro()` is a stub that returns `false` [C-TD-tier-c-selfhost-010]. |
| **Business model** | Free Community tier (5 users); Home Premium USD 99/year; Lifetime USD 249; Pro from USD 16/month, priced per GB of RAM and per user [C-TD-tier-c-selfhost-009]. |
| **Team** | 19 contributors; the top three made 98% of contributions; one named individual is the licensor [C-TD-tier-c-selfhost-012]. |

## 3. Strengths and weaknesses

| Strengths | Weaknesses |
|---|---|
| A whole "secure gateway" in one binary: proxy, SSO, 2FA, VPN and backups. Strong P-1 UX for little code [C-TD-tier-c-selfhost-008] | Self-update is MD5 from the same source, with no signature and no rollback [C-TD-tier-c-selfhost-004, C-TD-tier-c-selfhost-005] |
| Multi-server over NATS + Nebula, already shipped to home users [C-TD-tier-c-selfhost-007] | Not open source; a one-person bus factor [C-TD-tier-c-selfhost-001, C-TD-tier-c-selfhost-012] |
| Honest freemium: config and container backups are free, file backups are paid [C-TD-tier-c-selfhost-009] | Not an OS: it never manages the host kernel, drivers or OS updates [C-TD-tier-c-selfhost-003] |
| | Store index is plain JSON on GitHub Pages with no signing seen [C-TD-tier-c-selfhost-006] |

## 4. What competitors do (on the lesson Cosmos teaches: "multi-box over a bus")

| Product | How several boxes are joined | Constraint fit to OneMind |
|---|---|---|
| **Cosmos** | Nebula VPN + NATS JetStream config sync, paid tier [C-TD-tier-c-selfhost-007, C-TD-tier-c-selfhost-009] | **Candidate:** same bus as OneMind; but Docker-only, single developer, not an OS |
| **Olares** | One k3s cluster [C-TD-olares-021] | **Default** for the app platform (k3s), per MATRIX §5 |
| **Kairos** | p2p k3s [C-TD-kairos-043] | Candidate |
| **umbrelOS** | Single box only [C-TD-umbrelos-027] | Low for multi-box |
| **OneMind target** | k3s on nodes with ≥ 4 GB RAM and an SSD; NATS leaf on small nodes (REC-DEC-09) [C-LAB-k3s-footprint-restore-007] | Yardstick |

## 5. Constraint fit to OneMind

**Overall: Low as a base; Candidate as a pattern source for the gateway and the multi-box layer.** Cosmos targets home servers and Pis like OneMind does, and it also runs a NATS cluster. But it is not an OS, it has no robotics or IoT work, it uses Docker rather than Kubernetes, and its licence rules out reuse [C-TD-tier-c-selfhost-001, C-TD-tier-c-selfhost-003, C-TD-tier-c-selfhost-011]. Its team scale (essentially one person) matches OneMind's start [C-MATRIX-009], which proves the scope is reachable. It also shows the bus-factor risk.

## 6. What OneMind copies (patterns only) and does better

| ID | Recommendation | Evidence | Req IDs |
|---|---|---|---|
| REC-TDC-COS-01 | Ship the "secure gateway" bundle as one built-in service: reverse proxy with automatic HTTPS, SSO with MFA, and per-app access rules, on by default. | [C-TD-tier-c-selfhost-008] | P-1, U-4, U-5 |
| REC-TDC-COS-02 | Use NATS to join boxes (config and events) as Cosmos does, but over OneMind's own subject grammar and with signed node identity. Keep it in the free tier, because multi-box is core to UX-6 and N-1. | [C-TD-tier-c-selfhost-007][C-LAB-k3s-footprint-restore-007] | UX-6, N-1 |
| REC-TDC-COS-03 | Do better on updates: signed RAUC bundles with A/B and a health gate instead of an MD5 check and an in-place unzip. | [C-TD-tier-c-selfhost-004][C-TD-tier-c-selfhost-005][C-LAB-rauc-014] | R-1 |
| REC-TDC-COS-04 | Keep the licence honest: Apache-2.0 core, with paid features as separate add-ons, not anti-tampering clauses. Cosmos shows how a paywall clause makes a project non-open-source. | [C-TD-tier-c-selfhost-001][C-MATRIX-012] | D-001, M-8 |

## Glossary

| Term | Meaning |
|---|---|
| **Reverse proxy** | A front door that receives every web request and forwards it to the right app, adding HTTPS. |
| **Commons Clause** | A rider added to a licence that removes the right to sell the software. The result is not open source. |
| **MD5 check** | A fingerprint of a file. It catches corrupt downloads, but anyone who can change the file can change the fingerprint too, so it does not prove the update is genuine. |
| **Nebula** | An open-source mesh VPN that links machines directly to each other. |
| **NATS JetStream** | A messaging system with stored streams. OneMind's bus is NATS. |
| **Bus factor** | How many people would have to leave before the project stalls. |
