<!-- SPDX-License-Identifier: Apache-2.0 -->
# Founder note 03: Olares, Project NOMAD, k3s vs Docker, and where OneMind goes next

**For:** Zeus · **Date:** 2026-11-14
**Status:** founder-requested study. It adds no decision and reopens none. Where evidence touches a locked decision (k3s in the stack, D-007 Debian), it is laid out for Zeus to judge.
**Builds on:** the Foundation Report (`research-output/ONEMIND-OS-FOUNDATION-REPORT.pdf`, chapters 1, 6 and 10), the teardowns in [`research-output/02-competitors/`](../../../research-output/02-competitors/) (Olares, Project NOMAD and 20 more), and [note 02](02-umbrelos-image-teardown.md) (umbrelOS images).
**Feeds:** Wave G #5 parity re-score and #7 Market ([`docs/leap/NEXT-WAVE.md`](../../leap/NEXT-WAVE.md)), REC-NOMAD-01 and REC-NOMAD-08 in the NOMAD teardown, CORE-NET-5 (per-app login), the dashboard wiring pass, and the robotics layer L2b in the report §6.1.

---

## 1. Inside the Olares 1.12.7 ISO
Read-only: nothing was booted. The ISO was listed, and its root filesystem was listed and sampled with `unsquashfs` inside a throwaway container. Olares is AGPL-3.0, so this is study only; no Olares code may be copied into OneMind (D-001, Apache-2.0).

| What | Finding |
|---|---|
| Base | **Ubuntu 24.04.3 LTS**, kernel 6.14 (Ubuntu's hardware-enablement kernel). The ISO is an Ubuntu "casper" live system with two boot entries: "Start Olares Live System" and "Install Olares to Hard Disk". |
| Size | 8.5 GB, because the whole platform is pre-loaded: about 900 container image layers sit in containerd's store, so install works without downloading the platform. |
| OS updates | No A/B slots and no read-only root: it installs a normal Ubuntu. This matches the report: "no A/B; retries forward, never back" (§10.2). |
| Cluster | **k3s v1.33.3** with etcd 3.5.18 and containerd 2.1.3; kubeadm and kubelet 1.33.3 are also bundled; Helm 3.9; CNI plugins and Multus. |
| Platform services | NATS, **Headscale + Tailscale** (mesh), Infisical (secrets), lldap (accounts), OPA (policy), Envoy (proxy), Prometheus and node-exporter (monitoring), Velero (backups), JuiceFS + MinIO (storage), Seafile + Samba (files), KubeBlocks with Citus, MongoDB, Redis and KVrocks (databases for apps), Argo Workflows. |
| GPUs | NVIDIA container toolkit, **HAMi** (shares one GPU between several apps), and AMD and Intel device plugins, plus node-feature-discovery. |
| Daemon | `olaresd`, a systemd service: the same "name + d" pattern as `onemindd` ([note 01](01-daemons-and-the-github-plan.md)). |
| Setup | The LarePass phone app is required to activate the box (their install guide). x86-64 only for this ISO. |

**What it validates for OneMind:** a consumer box can run k3s; Headscale + Tailscale and NATS are the same choices OneMind made (F-32 default, the NATS bus). **Where OneMind is ahead:** Olares has no OS rollback, no image of its own and a higher RAM floor (8 GB, report §6.2), while OneMind targets 4 GB boxes with a read-only A/B image and a health gate.

## 2. Project NOMAD: more than four apps
The website shows four modules (Kiwix library, Ollama AI, OpenStreetMap maps, Kolibri education). The code does more. From the repo's teardown of v1.35.1, still the latest release on 2026-11-14:

- **17 seed apps** in its "Supply Depot": Kiwix, Qdrant, Ollama, CyberChef, FlatNotes, Kolibri, Stirling-PDF, FileBrowser, Calibre-Web, IT-Tools, Excalidraw, Meshtastic Web, MeshCore Web, Homebox, Vaultwarden, Jellyfin and its own translator.
- **RAG chat:** the AI answers from your uploaded files and the offline library.
- **A hardware benchmark with a public leaderboard** that drives hardware advice.
- **Per-app update with rollback** (rename the old container aside, health-check the new one, restore on failure), an update window and a cool-off period.
- **Content manager** for Wikipedia sizes, medical, survival and education collections.

**What it lacks** (teardown §5-§10): no OS of its own and no OS updates, **no logins** (anyone on the Wi-Fi can install or delete apps), no backups, x86 only, about two maintainers.

**Why it matters anyway:** about 43,400 GitHub stars on 2026-11-14 (`gh repo view`), in about 16 months. People want **offline content + local AI that just works**.

**What its users ask for next** (its public roadmap, read 2026-11-14): Meshtastic and MeshCore messaging, SDR and ham radio, Home Assistant, an offline office suite, GPU access for every app (not only Ollama), scheduled AI on/off to save battery, folder ingest for the AI, OS update status in the admin panel, non-English content, and an installer you can share offline. Several of these are already OneMind plans: mesh (report §3.7), automation schedules (#75), files (#77), app lifecycle (#72), GPU scheduling on k3s.

NOMAD is Apache-2.0, the same licence as OneMind, so its patterns and even code can be reused with attribution. Its Creator Pack video content has a separate non-commercial licence and must never be bundled.

## 3. k3s or Docker?
k3s is in the locked stack (CLAUDE.md, report chapter 6). This section lays out the evidence; the call stays with Zeus.

| | Docker / Compose | k3s |
|---|---|---|
| Who uses it | Home Assistant OS, umbrelOS, NOMAD, CasaOS, ZimaOS; TrueNAS moved from k3s to Docker in 24.10 | Olares; your existing DigitalOcean cluster |
| Memory | Lowest | Adds about 936 MiB idle, 1.5 GiB under load on a 4 GB arm64 box (report §6.2, measured) |
| Several machines as one | Not built in | Built in: placement, failover, the same app on any node |
| GPU sharing and scheduling | Manual | Device plugins, HAMi, NVIDIA GPU Operator |
| Robots and field kits | No safe "worker only" mode | A robot runs the k3s **agent only**, so a stolen robot holds no cluster secrets |
| Simplicity for one box | Simpler | More moving parts |

**What the evidence says:** Docker wins for one simple box; k3s wins for the product OneMind says it is: many machines as one mind, GPUs, robots, and the same app from a Pi to a cluster. The competitors that chose Docker are single-box products. The one closest to OneMind's goal (Olares) chose k3s.

**What already softens the cost**, so there is no need to switch:
- Devices under 4 GB or SD-only run as **NATS leaf nodes**, not k3s (report §6.2).
- App store depth (#57) adds a **Compose importer**, so Docker apps come in without a rewrite.
- The report's rule that apps never depend on k3s-only features keeps the door open if this is ever revisited (the TrueNAS lesson).

If Zeus wants to revisit, the testable question is: *on a 4 GB Pi 5, does the measured k3s overhead leave enough room for the greenhouse profile?* That is a hardware test that waits on F-25.

## 4. Where OneMind stands today
From `origin/main` on 2026-11-14.

**Already ahead of all three competitors:**
- Approvals: AI and agents can only ask, the owner approves, everything is audited. None of the three has this.
- A read-only image with A/B updates and a fresh-signal health gate (umbrelOS has A/B but no health gate; Olares and NOMAD have no OS rollback).
- Signed updates through TUF (publishing waits on F-27).
- Accounts and passkeys, backups with verified restores, app updates with automatic revert, automation, files, photos, notifications, multi-node join.

**Behind, and these are what a first-time user sees:**

| Gap | Evidence | Competitor that has it |
|---|---|---|
| Many apps are blocked | 40 of 61 apps are tier `blocked` by the scan gate | umbrelOS has hundreds of apps; NOMAD has 17 that just work |
| No offline-knowledge apps | No Kiwix, Kolibri or offline-maps app in `apps/`; Ollama is community tier | NOMAD's whole product |
| Dashboard pages not wired for every API | Dashboard wiring pass not started | umbrelOS: "every button does something" |
| Per-app login gate missing | CORE-NET-5; it keeps PrivateBin blocked (D25) | umbrelOS has a per-app login gateway |
| Robotics: none on `main` | No ROS 2, MAVLink or Meshtastic code in `core/`, `internal/`, `cmd/` | Nobody has it either (report §10.1): open ground |

## 5. Where OneMind can go: the next build streams
Ranked by what moves OneMind past all three, smallest step first. Each names the build step it feeds.

1. **"Offline Knowledge" bundle** (REC-NOMAD-01, Wave G #7): Kiwix with a library manager, Kolibri, offline maps (PMTiles), and Ollama chat with RAG over the library, as Market apps with one-click install. Licence checks per content source first. This takes NOMAD's whole product and puts it behind approvals, backups and A/B updates, on a Pi as well as x86.
2. **Unblock the Market** (A11, Wave G #7): work down the blocked list with newer upstream images, so the store looks full.
3. **Dashboard wiring pass** (HANDOFF B5): a page for every API already on `main`.
4. **Per-app login gate** (CORE-NET-5): unblocks PrivateBin and makes every app safe on the home network, the exact hole in NOMAD.
5. **GPU for any app** (NOMAD roadmap's top hardware ask): GPU sharing on k3s, following Olares's HAMi pattern. Check HAMi's licence before adopting.
6. **Benchmark and "can my box run this?"** (REC-NOMAD-08, report §8.2): a hardware score feeding the Market's placement advice.
7. **Mesh radio** (report §3.7, L2b): a Meshtastic adapter on the NATS bus. NOMAD users are asking for it; OneMind's bus fits it better than a web app.
8. **First robotics slice** (report §9.4 "Connect a robot → use OneMind", F-3): a ROS 2 bridge that starts **observe-only**, with any motion gated by owner approval. Nobody ships this; it is OneMind's clearest category of its own.

Items 1 to 4 are software-only and can start now. Items 6 to 8 get their real proof on hardware (F-25).

## 6. Words used
- **Live ISO:** a USB image that boots a full system without installing; Olares's also has an "install to disk" entry.
- **casper:** Ubuntu's live-boot system.
- **squashfs:** a compressed, read-only filesystem.
- **RAG:** retrieval-augmented generation: the AI looks things up in your documents first, then answers.
- **HAMi:** a Kubernetes add-on that lets several apps share one GPU.
- **NATS leaf node:** a small device that joins the message bus without running Kubernetes.
- **ROS 2 / MAVLink:** the standard software link for robots, and for drones.

## 7. Check yourself
1. Why does the Olares ISO weigh 8.5 GB when Ubuntu alone is much smaller?
2. Name two things NOMAD's users are asking for that OneMind already plans.
3. What would have to be true on a 4 GB Pi 5 for k3s to be the wrong choice?
