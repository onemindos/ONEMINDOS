# YunoHost: Tier C teardown

**Workstream:** W1 (Tier C) · **Tag:** TD-tier-c-selfhost · **Date:** 2026-11-11 · **Status:** draft
**Claims:** `evidence/claims/TD-tier-c-selfhost.csv` (C-TD-tier-c-selfhost-020 … 032), plus reused OneMind-target claims from `MATRIX.md` · **Sources:** `evidence/sources/TD-tier-c-selfhost.md`
**Requirements served:** P-1, P-7, A-1, A-6, U-1, U-4, R-1, R-3, UX-6, RS-2, D-001

> ### Explain it like I'm the founder
> YunoHost is the **oldest community self-hosting project in this set** (started in 2014). It is a set of Debian packages that turn a normal Debian install into a home server, with a web admin, one login for every app (LDAP + SSO), email and an app catalog [C-TD-tier-c-selfhost-023, C-TD-tier-c-selfhost-025, C-TD-tier-c-selfhost-031].
>
> **The big lesson for you is how it treats app updates.** Before every app upgrade it takes a "safety backup" of that app. If the upgrade fails, it removes the broken app and restores the backup automatically [C-TD-tier-c-selfhost-024]. That is a simple, proven rollback for apps that does not need A/B partitions.
>
> **The big warning is OS upgrades.** YunoHost has no A/B and no OS rollback: the OS is updated with `apt` in place [C-TD-tier-c-selfhost-023]. Moving to each new Debian release takes the volunteer team a long time. Debian 13 came out on 2025-08-09 [C-W2-001], and YunoHost 13 on Debian 13 is *still* marked "testing" in November 2026 [C-TD-tier-c-selfhost-021, C-TD-tier-c-selfhost-022]. Its own beta notice tells testers to be able to roll back the whole server first [C-TD-tier-c-selfhost-029]. OneMind's image-based updates exist to avoid exactly this.

---

## 1. What was analysed

| Item | Value |
|---|---|
| Release | **12.1.41.2** stable (2026-09-04) on Debian 12. **13.0.9** on Debian 13 is tagged "testing" (2026-10-26) [C-TD-tier-c-selfhost-021] |
| Code pins | `YunoHost/yunohost` @ `2734f233` (dev, = 12.1.41.2); tag `debian/13.0.9` @ `5b4d51cb`; example app `YunoHost-Apps/nextcloud_ynh` @ `ae8b20a7`. Citation form `YN@2734f233:path#L` |
| Code read | `src/app.py#L913-L950, #L1034-L1050` (safety backup and restore), `src/tools.py#L380-L431` (apt upgrade), `src/app_catalog.py#L40-L42`, `src/utils/resources.py#L323-L372`, `nextcloud_ynh/manifest.toml#L1-L45` |
| Licence posture | **AGPL-3.0** core [C-TD-tier-c-selfhost-020]; each app package has its own licence. Patterns only for OneMind (D-001). |

## 2. Field by field

| Field | YunoHost (evidence) |
|---|---|
| **Architecture** | A Python CLI and API (`yunohost …`) with a web admin and a user portal. It configures nginx, an LDAP directory with SSO, Postfix/Dovecot mail, a firewall and certificates on the host. Apps are installed **natively on the host** by bash scripts, not in containers [C-TD-tier-c-selfhost-025]. |
| **Base OS** | Plain **Debian**: 12 (bookworm) for stable, 13 (trixie) in testing [C-TD-tier-c-selfhost-021, C-TD-tier-c-selfhost-022]. |
| **Update / rollback** | OS and core: `apt-get` in place, with no A/B and no OS rollback [C-TD-tier-c-selfhost-023]. Apps: a safety backup before every upgrade, and an automatic restore on failure [C-TD-tier-c-selfhost-024]. |
| **App format** | Packaging v2: `manifest.toml` declares the minimum YunoHost version, architectures (amd64/arm64/armhf), LDAP/SSO integration, disk and RAM needs, install questions and "resources" (users, ports, databases, sources). Bash scripts handle install, upgrade, backup and restore [C-TD-tier-c-selfhost-025]. Upstream downloads are pinned by **sha256** and checked before the script runs [C-TD-tier-c-selfhost-026]. The catalog comes from `app.yunohost.org`, and no catalog signature check was found [C-TD-tier-c-selfhost-027]. |
| **AI features** | **None in core** [C-TD-tier-c-selfhost-032]. |
| **Hardware** | Ready-made images for Raspberry Pi 3/4/5 and other ARM boards; also x86, VPS, VM and install-on-Debian. An optional public key checks images [C-TD-tier-c-selfhost-028]. No hardware is sold. |
| **Licence** | AGPL-3.0 [C-TD-tier-c-selfhost-020]. |
| **Business model** | Volunteer project funded by donations; no paid tier was found [C-TD-tier-c-selfhost-030]. |
| **Team** | 100+ contributors since 2014; the top three made 61% of contributions, so it is the least concentrated project in this set [C-TD-tier-c-selfhost-031]. |

## 3. Strengths and weaknesses

| Strengths | Weaknesses |
|---|---|
| Automatic per-app safety backup and restore on a failed upgrade [C-TD-tier-c-selfhost-024] | In-place `apt` OS upgrades with no rollback; Debian majors land a year or more late [C-TD-tier-c-selfhost-021, C-TD-tier-c-selfhost-023] |
| One account for every app (LDAP + SSO) declared in the manifest [C-TD-tier-c-selfhost-025] | Apps run natively as root-run bash scripts, with weak isolation between apps [C-TD-tier-c-selfhost-025] |
| sha256-pinned upstream sources, checked before install [C-TD-tier-c-selfhost-026] | No catalog signing found [C-TD-tier-c-selfhost-027] |
| Twelve years of a broad contributor base [C-TD-tier-c-selfhost-031] | No AI, no Kubernetes, no robotics or IoT [C-TD-tier-c-selfhost-032] |
| Pi 3/4/5 images, the closest Tier C match to OneMind's Pi entry [C-TD-tier-c-selfhost-028] | |

## 4. What competitors do (on YunoHost's lesson: "safe app updates")

| Product | What happens when an app update fails | Constraint fit to OneMind |
|---|---|---|
| **YunoHost** | Mandatory pre-upgrade backup; on failure, remove and restore [C-TD-tier-c-selfhost-024] | **Candidate:** same Debian base and Pi targets; native apps differ from OneMind's containers |
| **Cloudron** | Mandatory backup before every app update; the update aborts if the backup fails [C-TD-tier-c-selfhost-064] | Candidate (x86 only) |
| **Runtipi** | Snapshot of files + env; automatic restore [C-TD-tier-c-selfhost-045] | Low (GPL, volunteer) |
| **StartOS** | Service data snapshot restored on a failed update [C-TD-startos-022] | Candidate (MATRIX) |
| **OneMind target** | Apps are excluded from the OS health gate (REC-DEC-07) [C-LAB-rauc-015]; app-level rollback is still to be designed | Yardstick |

## 5. Constraint fit to OneMind

**Overall: Low as a base, Candidate for the app-lifecycle pattern.** YunoHost matches OneMind on Debian and on Pi 3/4/5 [C-TD-tier-c-selfhost-021, C-TD-tier-c-selfhost-028]. It differs on everything that makes OneMind an appliance: no image, no A/B, apps installed natively instead of in containers, no Kubernetes, no AI and no robotics. Its slow Debian-major migration is evidence *for* OneMind's image-based approach [C-TD-tier-c-selfhost-021].

## 6. What OneMind copies (patterns only) and does better

| ID | Recommendation | Evidence | Req IDs |
|---|---|---|---|
| REC-TDC-YNH-01 | Make a **pre-update app snapshot mandatory** and restore it automatically when an app update fails, as YunoHost and Cloudron do. Put it in the app lifecycle (outside the OS health gate). | [C-TD-tier-c-selfhost-024][C-TD-tier-c-selfhost-064] | R-1, A-1 |
| REC-TDC-YNH-02 | Let app manifests **declare** SSO/LDAP integration, minimum platform version, architectures and RAM/disk needs, so the store can refuse an install that will not fit. | [C-TD-tier-c-selfhost-025] | A-1, A-8, U-4 |
| REC-TDC-YNH-03 | Pin every upstream download by digest in the manifest, and add what YunoHost lacks: a signed catalog index. | [C-TD-tier-c-selfhost-026][C-TD-tier-c-selfhost-027] | A-6, U-4 |
| REC-TDC-YNH-04 | Budget Debian-major moves as image rebuilds tested in CI, not in-place migrations. YunoHost's 13.0 is still in testing more than a year after Debian 13. | [C-TD-tier-c-selfhost-021][C-TD-tier-c-selfhost-029] | R-1, R-3 |

## Glossary

| Term | Meaning |
|---|---|
| **apt / in-place upgrade** | Debian's package tool, which updates files on the running system. If it breaks midway there is no automatic undo. |
| **Safety backup** | YunoHost's automatic backup of one app taken just before upgrading it. |
| **LDAP / SSO** | A shared user directory, and single sign-on: one login for every app. |
| **Packaging v2** | YunoHost's current app format: a TOML manifest plus bash scripts. |
| **sha256 pin** | Recording the exact fingerprint of a download, so a changed file is refused. |
| **AGPL-3.0** | A copyleft licence. Code derived from it must stay AGPL, even when it is only offered as a network service. |
