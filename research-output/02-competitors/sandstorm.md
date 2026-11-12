# Sandstorm: Tier C teardown

**Workstream:** W1 (Tier C) · **Tag:** `TD-tier-c-alt` · **Date:** 2026-11-11 · **Status:** draft, brief (Tier C; no refuter pass required)
**Claims:** `evidence/claims/TD-tier-c-alt.csv` (Sandstorm rows 015–028) · **Sources:** `evidence/sources/TD-tier-c-alt.md`
**Pinned:** `sandstorm-io/sandstorm@5c7c29c16f45b64bc059ace80e896f313c590bd2` (tag v0.310, 2026-10-12) [C-TD-tier-c-alt-020]
**License note:** Apache-2.0, the same licence as OneMind [C-TD-tier-c-alt-015]. Patterns and code could legally be reused with attribution; the name and logo are trademarks.

> ### Explain it like I'm the founder
> Sandstorm is a self-hosted **web-app platform with the strongest app security model anyone has shipped for home servers.** Every document, chat room or board you create is its own sealed box, called a **grain**. A grain cannot reach the internet or another app unless you click "allow" in a picker called the **Powerbox** [C-TD-tier-c-alt-023][C-TD-tier-c-alt-024]. Apps are signed, and an app's identity *is* its signing key [C-TD-tier-c-alt-022].
>
> **The technology worked, but the business did not.** Its founders said in 2017 that "our business has not succeeded", because almost nobody bought the enterprise edition [C-W16-050]. The paid hosting service closed at the end of 2019 [C-TD-tier-c-alt-025]. Then there were **no releases for about 26 months**, until volunteers shipped the "first community release" in October 2026 [C-TD-tier-c-alt-020][C-TD-tier-c-alt-021].
>
> **For OneMind:** copy the security ideas (per-object sandboxes, a permission picker, signed apps whose ID is a key, multi-person release keys). Avoid the business mistakes (closed enterprise features as the main revenue), and avoid asking app makers to rewrite their apps for a special format, which kept Sandstorm's catalogue small.

---

## 1. What it is, in one table

| Topic | What Sandstorm does | Evidence |
|---|---|---|
| **Architecture** | One server bundle (C++ supervisor, Meteor/MongoDB web shell, Cap'n Proto RPC). Each grain runs in its own sandbox with a **seccomp-BPF** syscall filter; apps reach anything outside only through capabilities granted in the Powerbox | [C-TD-tier-c-alt-023][C-TD-tier-c-alt-024] |
| **Base OS** | None. Installs a self-contained bundle on any **x86-64** Linux; refuses other CPUs. Needs unprivileged user namespaces; since v0.309 adds an AppArmor profile on Ubuntu 24.04-style hosts | [C-TD-tier-c-alt-016][C-TD-tier-c-alt-017] |
| **Update / rollback** | Self-updater polls a channel, downloads the bundle, **verifies a GPG signature** against a bundled keyring and aborts on failure; unpacks to a new directory and flips a `latest` symlink atomically. **Older builds are deleted**, so there is no rollback copy | [C-TD-tier-c-alt-018][C-TD-tier-c-alt-019] |
| **Release signing** | Since v0.309 the release key is held by **three maintainers** (it used to be the founder's) | [C-TD-tier-c-alt-020] |
| **App format** | Signed `.spk` package with a Cap'n Proto manifest; `spk verify` prints the app ID, which is derived from the public key. Apps must be packaged specially for Sandstorm | [C-TD-tier-c-alt-022] |
| **Backups** | Per-grain backup and restore to a zip | [C-TD-tier-c-alt-028] |
| **AI features** | None | (no AI module in the pinned tree) |
| **Hardware** | None sold; x86-64 servers or VMs only | [C-TD-tier-c-alt-016] |
| **Business model** | Was: enterprise edition + paid hosting (Oasis). Both failed or closed. Now: volunteer project with donations | [C-W16-050][C-TD-tier-c-alt-025][C-TD-tier-c-alt-026] |
| **Team / activity** | Volunteers; 7,082 stars; last push 2026-11-01; v0.308 (2023-08) → v0.309 (2026-10) gap; v0.309 needs a **manual** database migration | [C-TD-tier-c-alt-027][C-TD-tier-c-alt-020][C-TD-tier-c-alt-021] |

## 2. Strengths and weaknesses

| Strengths | Weaknesses |
|---|---|
| Least-privilege by default: every grain is sealed [C-TD-tier-c-alt-023] | Apps must be repackaged for Sandstorm, so the catalogue stayed small (e.g. Etherpad, Wekan, Davros) [C-TD-tier-c-alt-022][C-TD-tier-c-alt-026] |
| Capability grants through one UI, the Powerbox [C-TD-tier-c-alt-024] | x86-64 only; no Pi, no ARM [C-TD-tier-c-alt-016] |
| App identity = signing key, so an update from a stranger cannot pose as the app [C-TD-tier-c-alt-022] | No rollback: old builds are deleted after an update [C-TD-tier-c-alt-019] |
| Signed self-updates, now with a multi-person key [C-TD-tier-c-alt-018][C-TD-tier-c-alt-020] | Bus factor: one founder until 2026; a 26-month release gap [C-TD-tier-c-alt-021] |
| Apache-2.0 [C-TD-tier-c-alt-015] | The business failed [C-W16-050] |

## 3. What competitors do (app isolation and signing)

| Product | App isolation | App signing | Constraint fit to OneMind |
|---|---|---|---|
| **Sandstorm** | Per-grain sandbox + seccomp + Powerbox grants [C-TD-tier-c-alt-023][C-TD-tier-c-alt-024] | Signed `.spk`; app ID = key [C-TD-tier-c-alt-022] | **Candidate (pattern only):** no Kubernetes, x86 only, web apps only |
| **StartOS** | One LXC container per service [C-TD-startos-027] | Signed S9PK archive + signed registry index [C-TD-startos-024][C-TD-startos-028] | **Candidate** (appliance, small team) |
| **Olares** | SSO with default-deny policy in front of apps [C-TD-olares-036] | No package signing (MD5 check; see `MATRIX.md`) | **Default** for k3s app platform |
| **OneMind target** | Kubernetes namespace + network policy + gateway-enforced AI approvals (01) | Signed apps and OS bundles, offline root (REC-MATRIX-04) | — |

## 4. Constraint fit and what OneMind does with it

**Constraint fit: Low as a product reference, High as a security and business lesson.** Sandstorm has no Kubernetes, no ARM, no devices and no AI, and it is a volunteer project. Its *ideas* map directly onto OneMind's AI and plugin layer, where "what may this app or agent touch?" is the central question.

| ID | Recommendation | Evidence | Req IDs |
|---|---|---|---|
| REC-TDC-SAND-01 | Give OneMind a **Powerbox-style permission picker**: an app, plugin or AI agent gets access to another app's data, a device or the network only through a grant the user clicks, which is logged and revocable. Use the same grant model for MCP tool scopes. | [C-TD-tier-c-alt-024][C-TD-tier-c-alt-023] | U-4, AI-4, AI-5, A-6 |
| REC-TDC-SAND-02 | Make a Market app's **ID derive from its publisher signing key**, so only the holder of that key can ship updates under that ID; plan a documented key-transfer process (Sandstorm had to re-key abandoned apps). | [C-TD-tier-c-alt-022][C-TD-tier-c-alt-020] | A-1, A-6, U-4 |
| REC-TDC-SAND-03 | Hold the OneMind **release key with M-of-N maintainers** from day one, not one person, so the project survives a founder leaving. | [C-TD-tier-c-alt-020][C-TD-tier-c-alt-021] | R-2, R-3, M-8 |
| REC-TDC-SAND-04 | **Do not require apps to be rewritten** for OneMind: accept Helm + `onemind.app.yaml` and import Compose (REC-DEC-10), and add isolation from outside the app. Sandstorm's repackaging cost kept its catalogue small. | [C-TD-tier-c-alt-022] | A-1, A-2 |
| REC-TDC-SAND-05 | Business: no closed enterprise edition as the main revenue in year 1 (already in 17); keep **hosted services optional**, so the product outlives them as Sandstorm did after Oasis. | [C-W16-050][C-TD-tier-c-alt-025] | M-8, H-1, F-6 |

## Glossary

| Term | Meaning |
|---|---|
| **Grain** | Sandstorm's unit of isolation: one document, chat room or board, each in its own sandbox. |
| **Capability / Powerbox** | A capability is an unforgeable "permission token" for one thing. The Powerbox is the picker where the user hands one out. |
| **seccomp-BPF** | A Linux kernel filter that limits which system calls a process may make. |
| **Bus factor** | How many people would have to leave before a project stalls. |
| **M-of-N signing** | A release needs signatures from M of N key holders, so no single person can sign or block alone. |
