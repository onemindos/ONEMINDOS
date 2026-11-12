# Runtipi: Tier C teardown

**Workstream:** W1 (Tier C) · **Tag:** TD-tier-c-selfhost · **Date:** 2026-11-11 · **Status:** draft
**Claims:** `evidence/claims/TD-tier-c-selfhost.csv` (C-TD-tier-c-selfhost-040 … 049), plus C-W12-010 and reused OneMind-target claims from `MATRIX.md` · **Sources:** `evidence/sources/TD-tier-c-selfhost.md`
**Requirements served:** P-1, A-1, A-3, R-1, UX-6, RS-2, D-001

> ### Explain it like I'm the founder
> Runtipi is a **free, volunteer-built home-server app manager**. You run one script on a 64-bit Linux box or a Raspberry Pi with at least 4 GB of RAM. It installs Docker and a small stack (Traefik, Postgres, RabbitMQ and the Runtipi app), and gives you a web app store [C-TD-tier-c-selfhost-043, C-TD-tier-c-selfhost-044, C-TD-tier-c-selfhost-047].
>
> **What it teaches:** its app updates are **careful**. It saves the old app's files and settings first, and puts them back automatically if the update fails [C-TD-tier-c-selfhost-045]. Its install is **careless**. The script downloads the program from GitHub and runs it with no checksum and no signature [C-TD-tier-c-selfhost-043]. Its own README warns there is "no guarantee of support or security" [C-TD-tier-c-selfhost-042].
>
> **Licence:** both the code and the app store are **GPL-3.0** [C-TD-tier-c-selfhost-040, C-W12-010]. OneMind can study them, but anything copied would have to stay GPL. Keep it out of the Apache core.

---

## 1. What was analysed

| Item | Value |
|---|---|
| Release | **v4.12.0**, published 2026-10-31 [C-TD-tier-c-selfhost-041] |
| Code pins | `runtipi/runtipi` @ `a8f22ed8` (2026-11-03); `runtipi/runtipi-appstore` @ `1de3985b`. Citation form `RT@a8f22ed8:path#L`. The CLI is a separate repo (`runtipi/cli`, a git submodule), not read [C-TD-tier-c-selfhost-049] |
| Code read | `scripts/install.sh#L8-L13, #L204-L229`; `docker-compose.prod.yml`; `packages/backend/src/modules/app-lifecycle/commands/update-app-command.ts#L61-L257`; `…/apps/app-files-manager.ts#L83-L160`; `apps/nextcloud/config.json` |
| Licence posture | **GPL-3.0** for the platform and the app store [C-TD-tier-c-selfhost-040, C-W12-010]. Patterns only (D-001). |

## 2. Field by field

| Field | Runtipi (evidence) |
|---|---|
| **Architecture** | A TypeScript/NestJS backend and a React UI in one container, with Traefik v3.7.16 as reverse proxy, Postgres 14 and a RabbitMQ job queue, all as one Compose stack driven by a `runtipi-cli` binary [C-TD-tier-c-selfhost-044, C-TD-tier-c-selfhost-049]. |
| **Base OS** | None of its own. Any 64-bit Linux; Ubuntu 22.04+ recommended; Raspberry Pi supported. 32-bit is refused [C-TD-tier-c-selfhost-043, C-TD-tier-c-selfhost-047]. |
| **Update / rollback** | Platform: re-run the installer or the CLI, which downloads the new CLI from GitHub releases with **no checksum** [C-TD-tier-c-selfhost-043]. Apps: snapshot the previous files and env (optionally a full backup), and restore them on failure (`rollbackSucceeded`) [C-TD-tier-c-selfhost-045]. No OS updates or rollback. |
| **App format** | `config.json` (id, port, `tipi_version`, form fields that become environment variables, categories) plus a Compose file with an `x-runtipi` block [C-TD-tier-c-selfhost-046]. The store is a GPL git repo [C-W12-010]. |
| **AI features** | **None in the backend** [C-TD-tier-c-selfhost-049]. |
| **Hardware** | 64-bit x86 and ARM, including Pi; ≥ 4 GB RAM, 10 GB disk [C-TD-tier-c-selfhost-047]. No hardware is sold. |
| **Licence** | GPL-3.0 [C-TD-tier-c-selfhost-040]. |
| **Business model** | None: "built and maintained by volunteers" [C-TD-tier-c-selfhost-042]. |
| **Team** | 47 contributors; the top three made 97% of contributions; about 9.7k stars [C-TD-tier-c-selfhost-048]. |

## 3. Strengths and weaknesses

| Strengths | Weaknesses |
|---|---|
| App updates roll back automatically from a snapshot [C-TD-tier-c-selfhost-045] | Unverified binary download at install and update [C-TD-tier-c-selfhost-043] |
| A simple, readable app format (JSON form → env vars → Compose) [C-TD-tier-c-selfhost-046] | No business model, no support promise, very concentrated team [C-TD-tier-c-selfhost-042, C-TD-tier-c-selfhost-048] |
| Pi + x86 from one installer [C-TD-tier-c-selfhost-047] | GPL licence limits reuse by an Apache-2.0 project [C-TD-tier-c-selfhost-040] |
| | 4 GB minimum: a heavy stack (Postgres + RabbitMQ) for a home box [C-TD-tier-c-selfhost-044, C-TD-tier-c-selfhost-047] |

## 4. What competitors do (on Runtipi's lesson: "install-time trust")

| Product | How the platform binary or image is checked at install | Constraint fit to OneMind |
|---|---|---|
| **Runtipi** | Not checked [C-TD-tier-c-selfhost-043] | Low |
| **CasaOS** | Not checked [C-TD-casaos-zimaos-021] | Low |
| **Cosmos** | MD5 from the same release [C-TD-tier-c-selfhost-004] | Low |
| **Cloudron** | GPG-signed release list and tarball [C-TD-tier-c-selfhost-062] | Candidate (x86 only) |
| **OneMind target** | Signed RAUC bundles; unknown CA refused in the lab [C-LAB-rauc-014] | Yardstick |

## 5. Constraint fit to OneMind

**Overall: Low.** Runtipi is a Docker app manager on someone else's OS, with no image, no OS updates, no AI, no Kubernetes and no robotics. A GPL licence and a volunteer-only model sit far from OneMind's Apache-2.0 company product (M-8). Its pattern value is limited to its app-update rollback and its simple manifest.

## 6. What OneMind copies (patterns only) and does better

| ID | Recommendation | Evidence | Req IDs |
|---|---|---|---|
| REC-TDC-RTP-01 | Snapshot an app's files and settings before each update and restore them automatically on failure (same pattern as REC-TDC-YNH-01). | [C-TD-tier-c-selfhost-045] | R-1, A-1 |
| REC-TDC-RTP-02 | Generate the install form from the manifest (each field maps to a variable), as Runtipi does. OneMind maps it to Helm values instead of Compose env. | [C-TD-tier-c-selfhost-046][C-DEC-007] | A-1, A-2 |
| REC-TDC-RTP-03 | Do better on install trust: the bring-your-own-hardware installer verifies a signature before it runs anything, and the published `curl` one-liner pins a hash. | [C-TD-tier-c-selfhost-043][C-LAB-rauc-014] | P-7, U-4 |
| REC-TDC-RTP-04 | Keep the Runtipi store out of the Apache-2.0 repo (already W12-R3). | [C-W12-010] | A-3, D-001 |

## Glossary

| Term | Meaning |
|---|---|
| **Traefik** | A reverse proxy that routes web traffic to containers and gets HTTPS certificates. |
| **RabbitMQ** | A job queue; Runtipi uses it to run installs and updates in the background. |
| **Snapshot / rollback** | A copy taken before a change, put back if the change fails. |
| **GPL-3.0** | A copyleft licence: code derived from it must be released under the GPL. |
| **Checksum vs signature** | A checksum shows a file is not corrupted. A signature shows who published it. |
