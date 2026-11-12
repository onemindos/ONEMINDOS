# Cloudron: Tier C teardown

**Workstream:** W1 (Tier C) · **Tag:** TD-tier-c-selfhost · **Date:** 2026-11-11 · **Status:** draft
**Claims:** `evidence/claims/TD-tier-c-selfhost.csv` (C-TD-tier-c-selfhost-060 … 070), plus reused OneMind-target claims from `MATRIX.md` · **Sources:** `evidence/sources/TD-tier-c-selfhost.md`
**Requirements served:** P-1, A-1, A-2, U-1, U-4, R-1, R-2, R-3, M-8, H-1, RS-2, D-001

> ### Explain it like I'm the founder
> Cloudron is the **most "grown-up" commercial product in this group**: a small German company sells a self-hosted app platform on a subscription. You install it on a fresh Ubuntu x86 server. It then runs every app in a locked-down container with one login, email, backups and automatic updates [C-TD-tier-c-selfhost-061, C-TD-tier-c-selfhost-065, C-TD-tier-c-selfhost-066].
>
> **Three things it gets right that OneMind should match:**
> 1. **Every platform update is GPG-signed** and checked on the server before install [C-TD-tier-c-selfhost-062].
> 2. **No backup, no update.** Before any platform or app update it makes a backup. If the backup fails, the update does not run [C-TD-tier-c-selfhost-063, C-TD-tier-c-selfhost-064].
> 3. **Apps run with read-only system files** by default, and each declares a health URL and a memory limit [C-TD-tier-c-selfhost-065, C-TD-tier-c-selfhost-066].
>
> **Its business model is a lesson too:** free for two apps, then a monthly subscription. If you stop paying, your apps keep running but stop getting updates [C-TD-tier-c-selfhost-067, C-TD-tier-c-selfhost-068]. That is how it charges without holding data hostage. **But its code is not open source**: production use needs a subscription [C-TD-tier-c-selfhost-060]. It also runs on x86 only, with no ARM, no Pi and no Jetson [C-TD-tier-c-selfhost-061].

---

## 1. What was analysed

| Item | Value |
|---|---|
| Release | `box` master @ `3a75b363` (2026-11-10). Its `CHANGES` file ends at **10.2.0**; the release date of that version was not checked [C-TD-tier-c-selfhost-070]. The docs' manifest example asks for `minBoxVersion` 10.0.0 [C-TD-tier-c-selfhost-066] |
| Code pin | `platform/box` on git.cloudron.io @ `3a75b3638940559e8c803cdc46cacf38b016a6d4`. Citation form `CB@3a75b363:path#L` |
| Code read | `scripts/cloudron-setup#L40-L148`, `src/updater.js#L37-L232`, `src/apptask.js#L717-L735, #L890-L891`, `src/docker.js#L735`, `src/apphealthmonitor.js#L21-L75`, `LICENSE` |
| Licence posture | **"Cloudron Subscription license"**: the source is published, but production use needs a subscription, and patches belong to Cloudron [C-TD-tier-c-selfhost-060]. Not open source. Patterns only. |

## 2. Field by field

| Field | Cloudron (evidence) |
|---|---|
| **Architecture** | A Node.js "box" service on the host, with an nginx reverse proxy, a built-in mail server, an LDAP and OIDC directory, a backup engine and an app health monitor (modules `nginxconfig.ejs`, `mailserver.js`, `ldapserver.js`, `oidcserver.js`, `backuptask.js` and `apphealthmonitor.js` in `CB@3a75b363:src/`). Each app is a Docker container with a read-only root filesystem [C-TD-tier-c-selfhost-065, C-TD-tier-c-selfhost-066]. |
| **Base OS** | **Ubuntu LTS** only (22.04, 24.04 or 26.04), x86_64, installed fresh by `cloudron-setup`. It refuses ARM, LXC, Docker and OpenVZ [C-TD-tier-c-selfhost-061]. The host OS is not image-based. |
| **Update / rollback** | Platform: download → **GPG-verify** the release list and tarball → full backup (abort if impossible) → install [C-TD-tier-c-selfhost-062, C-TD-tier-c-selfhost-063]. Apps: backup before every update; abort if the backup fails; update backups kept 3 weeks [C-TD-tier-c-selfhost-064]. Rollback means **restore from backup**, for platform and apps. There is no A/B [C-TD-tier-c-selfhost-063]. Policies: off, apps only, or platform + apps, on a schedule [C-TD-tier-c-selfhost-063]. |
| **App format** | Docker image + `CloudronManifest.json`: ports, **addons** (Postgres, MySQL, Redis, mail, LDAP/OIDC and more provided by the platform), `healthCheckPath` (must return 2xx), `memoryLimit` (default 256 MB) and `minBoxVersion` [C-TD-tier-c-selfhost-066]. |
| **AI features** | **None in the platform code** [C-TD-tier-c-selfhost-069]. |
| **Hardware** | x86_64 only; ≥ 2 GB RAM, 20 GB disk. Sold through cloud marketplaces, no own hardware [C-TD-tier-c-selfhost-061]. |
| **Licence** | Source-available subscription licence [C-TD-tier-c-selfhost-060]. |
| **Business model** | Free (2 apps); Pro and Max subscriptions in euros per month, with unlimited apps. Max adds groups, a directory server, multiple backup sites and VPN-only app access [C-TD-tier-c-selfhost-067]. Cancelling stops updates, not apps [C-TD-tier-c-selfhost-068]. |

## 3. Strengths and weaknesses

| Strengths | Weaknesses |
|---|---|
| Signed platform updates [C-TD-tier-c-selfhost-062] | x86 Ubuntu only; no ARM, Pi or GPU focus [C-TD-tier-c-selfhost-061] |
| Mandatory backup before every update [C-TD-tier-c-selfhost-063, C-TD-tier-c-selfhost-064] | Rollback = restore (slow, manual); no A/B for the host OS [C-TD-tier-c-selfhost-063] |
| Read-only app containers, health URL and memory limit in every manifest [C-TD-tier-c-selfhost-065, C-TD-tier-c-selfhost-066] | Not open source; patches are owned by the vendor [C-TD-tier-c-selfhost-060] |
| Platform-provided "addons" (databases, mail, SSO), so apps do not each bundle their own [C-TD-tier-c-selfhost-066] | No AI or MCP [C-TD-tier-c-selfhost-069] |
| A fair failure mode when you stop paying [C-TD-tier-c-selfhost-068] | |

## 4. What competitors do (on Cloudron's lesson: "how a paid self-hosted platform charges")

| Product | What you pay for | What happens if you stop | Constraint fit to OneMind |
|---|---|---|---|
| **Cloudron** | Unlimited apps and admin features, per month [C-TD-tier-c-selfhost-067] | Apps run, updates stop [C-TD-tier-c-selfhost-068] | **Candidate** for the business model; Low technically (x86, closed licence) |
| **Cosmos** | Multi-server and file backups [C-TD-tier-c-selfhost-009] | Not documented in the sources read | Low |
| **Proxmox VE** | Stable repository + support [C-TD-proxmox-ve-036] | Free repo continues | **Default** for business model (MATRIX §5) |
| **ZimaOS** | USD 29 lifetime licence per device [C-TD-casaos-zimaos-032] | n/a | Candidate |
| **OneMind target** | Apache-2.0 open core: boxes, support, pro features [C-MATRIX-012] | Core stays free and open | Yardstick |

## 5. Constraint fit to OneMind

**Overall: Low as a base (x86 Ubuntu, closed licence, no AI, no robotics); Candidate for update discipline, app sandboxing and subscription behaviour.** Cloudron's company shape (a small vendor selling a long-lived product) is closer to OneMind's goal (M-8) than the volunteer projects are. Its safety rules cost little to copy.

## 6. What OneMind copies (patterns only) and does better

| ID | Recommendation | Evidence | Req IDs |
|---|---|---|---|
| REC-TDC-CLD-01 | **"No backup, no update"** for apps: refuse an app update when the pre-update backup fails, and keep the update backups for a fixed period. | [C-TD-tier-c-selfhost-064] | R-1, R-2 |
| REC-TDC-CLD-02 | Run app containers with a **read-only root filesystem by default**, and require a health endpoint and a memory limit in `onemind.app.yaml`. On k3s these map to `readOnlyRootFilesystem`, probes and resource limits. | [C-TD-tier-c-selfhost-065][C-TD-tier-c-selfhost-066] | U-4, A-1, UX-4 |
| REC-TDC-CLD-03 | Offer platform-provided **shared services** (database, SSO, mail relay) that apps declare instead of bundling their own. This saves RAM on Pi-class boxes. | [C-TD-tier-c-selfhost-066] | A-1, A-2, P-1 |
| REC-TDC-CLD-04 | If OneMind sells a paid tier, use Cloudron's fair rule: lapsed payment stops *paid extras*, never running apps or access to data. Security updates to the open core stay free. | [C-TD-tier-c-selfhost-068][C-MATRIX-012] | M-8, R-3, D-001 |
| REC-TDC-CLD-05 | Do better on rollback: A/B with a health gate for the OS (REC-DEC-07), so recovery is a reboot, not a restore. | [C-TD-tier-c-selfhost-063][C-LAB-rauc-015] | R-1 |

## Glossary

| Term | Meaning |
|---|---|
| **GPG signature** | A cryptographic stamp made with the vendor's private key. The server checks it with the matching public key before installing. |
| **Read-only root filesystem** | The app cannot change its own program files, only its data folders. This limits damage from a break-in. |
| **Addon (Cloudron)** | A shared service the platform provides to apps, such as a database or mail. |
| **Health check path** | A web address the platform polls to see whether an app is alive. |
| **Source-available** | You can read the code, but the licence restricts use. It is not open source. |
