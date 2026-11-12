# CasaOS / ZimaOS: Tier B teardown (condensed)

**Workstream:** W1 (competitor teardowns), Tier B · **Tag:** TD-casaos-zimaos · **Date:** 2026-11-11
**Builds on:** `research/competitors/landscape.md` §1.3 (phase 1), C-W3-046/047 (W3 install survey), C-REF-DC-longevity-006 and C-W18-064. Those facts are reused, not re-derived.
**Claims:** [`evidence/claims/TD-casaos-zimaos.csv`](../evidence/claims/TD-casaos-zimaos.csv) (C-TD-casaos-zimaos-001 … 051) · **Sources:** [`evidence/sources/TD-casaos-zimaos.md`](../evidence/sources/TD-casaos-zimaos.md) (saved copies plus sha256 in `evidence/sources/TD-casaos-zimaos/`).
**License note:** the CasaOS repositories are Apache-2.0 [C-TD-casaos-zimaos-001], so their code is compatible with OneMind (D-001). **ZimaOS has no license file** [C-TD-casaos-zimaos-002], so it is studied **for patterns only**. Nothing here copies ZimaOS code or files.

---

> ### Explain it like I'm the founder
> IceWhale, the company behind the ZimaBoard and ZimaCube boxes, has made two products in a row.
>
> **CasaOS (2021)** is a set of Go services plus a web dashboard that you put on top of an existing Linux with one `curl | bash` command. It is open source and very popular (37.6k GitHub stars), but it has had no stable release since December 2024 [C-TD-casaos-zimaos-001]. Its "update" button downloads a script from IceWhale's server and runs it as root [C-TD-casaos-zimaos-023]. When we checked, that update address returned an error page [C-TD-casaos-zimaos-022].
>
> **ZimaOS (2023)** is the same dashboard and apps turned into a real appliance image. It is built with **Buildroot** and updated with **RAUC A/B slots** (two copies of the OS; if the new one fails to boot three times, it falls back to the old one) [C-TD-casaos-zimaos-004][C-TD-casaos-zimaos-010][C-TD-casaos-zimaos-012]. That is the same recipe as Home Assistant OS, and the same engine OneMind has chosen. It runs only on x86 PCs. Apps are plain **Docker Compose** files with an extra `x-casaos` block. There is no Kubernetes, no robotics and no real MCP integration [C-TD-casaos-zimaos-018][C-TD-casaos-zimaos-024][C-TD-casaos-zimaos-038]. It is free for up to 3 users and 4 disks, then $29 once per device [C-TD-casaos-zimaos-032].
>
> **Why it matters to you:** ZimaOS is a second consumer appliance, after HAOS, that independently chose **Buildroot + RAUC + GRUB, 3 boot tries**. That supports OneMind's RAUC decision. ZimaOS also shows the traps OneMind must avoid. It marks an update "good" as soon as its own services have *started*, not when they *work*. Its data migrations run before the reboot, so a rollback lands on already-changed data. And its bootloader partition is overwritten in place [C-TD-casaos-zimaos-011][C-TD-casaos-zimaos-013][C-TD-casaos-zimaos-014]. CasaOS users who wanted the image had to **wipe and reinstall** [C-TD-casaos-zimaos-047]. That is the lesson for OneMind's "script first, image later" plan.

---

## 0. What was analysed (pinned)

| Item | Pin | Date | Claim |
|---|---|---|---|
| CasaOS core | `IceWhaleTech/CasaOS@e099dd6b` (last stable v0.4.15) | 2026-11-09 (release 2024-12-19) | [C-TD-casaos-zimaos-001] |
| CasaOS installer scripts | `IceWhaleTech/get@15d5563a` + the live `get.casaos.io` script (sha256 `4a9e7c4b…`) | 2025-04-16 / 2026-11-11 | [C-TD-casaos-zimaos-021][C-TD-casaos-zimaos-022] |
| App management / store / users | `CasaOS-AppManagement@debfa317`, `CasaOS-AppStore@820f9900`, `CasaOS-UserService@800c630c`, `CasaOS-Common@bd9a9049` | 2025-04 … 2026-11 | [C-TD-casaos-zimaos-024..031] |
| ZimaOS public repo (README, OTA feed, SECURITY) | `IceWhaleTech/ZimaOS@8bc15999` | 2026-10-15 | [C-TD-casaos-zimaos-002] |
| **ZimaOS 1.8.0 release image** (the OS itself; its source is closed) | `zimaos-x86_64-1.8.0.raucb`, sha256 `c24bccfd…` | 2026-10-15 | [C-TD-casaos-zimaos-003] |
| Image build fork | `IceWhaleTech/buildroot@4d129097` (branch `2026.02.x-zima`) | 2026-11-04 | [C-TD-casaos-zimaos-005] |
| Docs | `IceWhaleTech/ZimaDocs@43d34b94` | 2026-11-11 | various |

**Method.** ZimaOS's build tree, installer and daemons are not public. To read the update chain from the real thing rather than from marketing, the 1.8.0 bundle's signature and signed manifest were range-read on the host. The full bundle was then unpacked and its root and boot filesystems mounted **read-only inside a disposable Lima VM** (no host mounts, deleted afterwards). Nothing from the image was executed. Excerpts and hashes are in [`zimaos-1.8.0-bundle-inspection.txt`](../evidence/sources/TD-casaos-zimaos/zimaos-1.8.0-bundle-inspection.txt). Artifact citations use `zimaos-1.8.0.raucb:<path>#Lx-Ly`.

---

## 1. W1 field summary

| W1 field | CasaOS | ZimaOS |
|---|---|---|
| **Architecture** | Separate Go services (gateway, message bus, user, local storage, app management, core, CLI) plus a Vue UI, each downloaded as its own tarball and run as a systemd unit [C-TD-casaos-zimaos-021][C-TD-casaos-zimaos-022] | Same service family renamed `zimaos-*` under `zimaos.target`, plus Files, Photos (AI worker), Search, virtualisation (QEMU/libvirt) and a hardware watchdog [C-TD-casaos-zimaos-013][C-TD-casaos-zimaos-037] |
| **Base OS** | Not owned: Debian 12, Ubuntu 20.04, Raspberry Pi OS (official) [C-TD-casaos-zimaos-020] | Own **Buildroot** image, glibc, systemd, kernel 6.18.9, read-only root [C-TD-casaos-zimaos-004][C-TD-casaos-zimaos-018][C-TD-casaos-zimaos-019] |
| **Image build** | None | Buildroot fork with a `-zima` branch per Buildroot release; patches pin Docker and adjust systemd [C-TD-casaos-zimaos-005]. Build tree closed. |
| **Install paths** | `curl … \| sudo bash` on a distro; amd64/arm64/armv7 [C-TD-casaos-zimaos-020] | USB installer `.img`/`.iso` that erases the target disk; Proxmox guide; x86-64 UEFI with **Secure Boot disabled** [C-TD-casaos-zimaos-006][C-TD-casaos-zimaos-007] |
| **Update / rollback** | UI runs a downloaded script as root; no OS rollback [C-TD-casaos-zimaos-023] | Signed **RAUC verity bundle**, GRUB A/B, 3 tries, rescue entry; offline `.raucb` drop folder; mark-good after services start [C-TD-casaos-zimaos-008..017] |
| **App format** | Compose + `x-casaos` (store metadata, port, UI path, arch, i18n texts) [C-TD-casaos-zimaos-024] | Same format and the same store repo (`store_id: zimaos-appstore`) [C-TD-casaos-zimaos-024] |
| **Identity** | ES256 JWT + JWKS from the user service; a `role` field [C-TD-casaos-zimaos-031] | Members with folder-level access; 3 members free, unlimited with Plus [C-TD-casaos-zimaos-032] |
| **AI features** | None in core | Photo AI (natural-language search, NCNN worker) [C-TD-casaos-zimaos-037]; docs for llama.cpp on NVIDIA [C-TD-casaos-zimaos-040]; an external file-only MCP server [C-TD-casaos-zimaos-038]; a separate agent runtime, ZimaOS Blue (MIT) [C-TD-casaos-zimaos-039] |
| **Backups** | None built in | Backup app: from-to tasks (Cloud/LAN/USB/Zima) with versions; rsync + rclone in the image, no restic/borg/kopia [C-TD-casaos-zimaos-042]. No OS-config/whole-box backup found. |
| **Security** | Unverified downloads; root script updates [C-TD-casaos-zimaos-021][C-TD-casaos-zimaos-023] | Signed bundles, read-only root; no Secure Boot; 11 CVEs disclosed 2024-2026, including two rated 9.1 and 9.4 [C-TD-casaos-zimaos-009][C-TD-casaos-zimaos-043] |
| **Hardware** | Any supported distro box, incl. Pi | x86 only: ZimaBoard 2 ($339/$399), ZimaCube 2 ($799–$2,499), generic PCs, 4 GB RAM minimum [C-TD-casaos-zimaos-035][C-TD-casaos-zimaos-036] |
| **License** | Apache-2.0 [C-TD-casaos-zimaos-001] | No license file; proprietary in practice [C-TD-casaos-zimaos-002] |
| **Business model** | Funnel to hardware | Hardware + **$29 lifetime per-device Plus license**; Plus is automatic on Zima hardware [C-TD-casaos-zimaos-032][C-TD-casaos-zimaos-048] |
| **Activity** | Stalled releases (v0.4.15, 2024-12-19) though the repo is still pushed [C-TD-casaos-zimaos-001] | Roughly monthly releases with 1–3 betas each; 1.8.0 bundle downloaded ~900k times [C-TD-casaos-zimaos-003] |

---

## 2. Architecture and boot → update → rollback

```mermaid
sequenceDiagram
  participant UI as ZimaOS UI / offline folder
  participant R as rauc (D-Bus)
  participant H as bundle hook
  participant G as GRUB (single ESP, grubenv)
  participant S as systemd (new slot)
  UI->>R: install zimaos-x86_64-1.8.0.raucb
  R->>R: verify CMS signature vs /etc/rauc/keyring.pem (CA valid to 9999)
  R->>H: install-check (compatible == zimaos-zimacube, grubenv sane)
  R->>H: boot slot: cp -rf new files over the live ESP (not A/B)
  R->>R: write kernel.N + rootfs.N (inactive pair)
  R->>H: post-install: migrate apps / restart policy / repo metadata on live /DATA
  R->>G: ORDER = new slot first, OK=1, TRY=0
  Note over G: reboot
  G->>G: pick first slot with OK=1 and TRY<3, TRY++
  G->>S: boot kernel + rootfs (rauc.slot=B)
  S->>S: zimaos.target: 9 daemons started (Requires/After)
  S->>R: zimaos-last.service: hd-migrate --check, then rauc status mark-good
  alt slot never reaches mark-good (panic, hang)
    G->>G: after 3 tries the slot is skipped, old slot boots; if none qualify, rescue shell
  end
```

The diagram is derived from: system.conf `zimaos-1.8.0.raucb:/etc/rauc/system.conf#L1-L35` [C-TD-casaos-zimaos-010]; GRUB `zimaos-1.8.0.raucb:boot.vfat/EFI/BOOT/grub.cfg#L4-L61` [C-TD-casaos-zimaos-012]; hook `zimaos-1.8.0.raucb:hook#L132-L211, #L547-L590` [C-TD-casaos-zimaos-011][C-TD-casaos-zimaos-014]; mark-good `zimaos-1.8.0.raucb:/usr/lib/systemd/system/zimaos-last.service#L1-L13` [C-TD-casaos-zimaos-013].

**Disk layout (target, as far as can be seen without running the installer).** There is a single `casaos-boot` ESP holding GRUB and grubenv. Kernel/rootfs pairs `casaos-kernel0/1` and `casaos-system0/1` sit at GPT 2/4 for the kernels [C-TD-casaos-zimaos-010][C-TD-casaos-zimaos-012]. The docs say each slot is about 6 GB [C-TD-casaos-zimaos-016]. A `casaos-overlay` ext4 partition carries `/etc` changes, and a data partition is bind-mounted to `/DATA` and `/var/lib/docker` [C-TD-casaos-zimaos-018]. A recovery script in the public repo refers to the data partition as "partition 8" (`ZimaOS@8bc15999:zimaos-fix.sh#L25-L32`). Exact partition sizes are **UNVERIFIED** because the installer was not run.

---

## 3. Code citations (≥3 required; 14 given)

| Area | Citation | What it shows |
|---|---|---|
| Image build | `IceWhaleTech/buildroot@4d129097:package/docker-engine/docker-engine.mk#L7` and commit `bca5fabb` | The Buildroot fork pins Docker 27.5.1 (down from 28.3.2) after a field failure [C-TD-casaos-zimaos-005][C-TD-casaos-zimaos-045] |
| Image build | `IceWhaleTech/ZimaOS@8bc15999:README.md#L23-L52` | "built using Buildroot", OTA + offline updates, hardware list [C-TD-casaos-zimaos-004] |
| Update / rollback | `zimaos-1.8.0.raucb:/etc/rauc/system.conf#L1-L35` | GRUB backend; A/B kernel+rootfs; one shared boot slot [C-TD-casaos-zimaos-010] |
| Update / rollback | `zimaos-1.8.0.raucb:boot.vfat/EFI/BOOT/grub.cfg#L4-L61` | OK/TRY counters, 3 tries, rescue fallback [C-TD-casaos-zimaos-012] |
| Update / rollback | `zimaos-1.8.0.raucb:/usr/lib/systemd/system/zimaos-last.service#L1-L13` | Mark-good after services start [C-TD-casaos-zimaos-013] |
| Update / rollback | `zimaos-1.8.0.raucb:hook#L132-L211`, `#L547-L590` | ESP overwritten in place; pre-reboot data migrations [C-TD-casaos-zimaos-011][C-TD-casaos-zimaos-014] |
| Update feed | `IceWhaleTech/ZimaOS@8bc15999:rauc.txt#L1-L12`, `.github/workflows/rauc.yaml#L1-L27` | OTA manifest with two mirrors; synced to OSS by an action pinned to `@master` [C-TD-casaos-zimaos-015] |
| CasaOS update | `IceWhaleTech/CasaOS@e099dd6b:service/system.go#L373-L389`; `route/v1/system.go#L65-L71` | `curl … \| bash` from an API call [C-TD-casaos-zimaos-023] |
| CasaOS install | `IceWhaleTech/get@15d5563a:install.sh#L509-L533`, `#L186-L193` | No checksum or signature; geo-IP lookup [C-TD-casaos-zimaos-021][C-TD-casaos-zimaos-034] |
| App format | `IceWhaleTech/CasaOS-AppStore@820f9900:Apps/Jellyfin/docker-compose.yml#L45-L133`; `CasaOS-AppManagement@debfa317:common/constants.go#L11` | `x-casaos` schema in use [C-TD-casaos-zimaos-024] |
| App format | `CasaOS-AppManagement@debfa317:cmd/validator/pkg/validate.go#L10-L31`; `route/v2/appstore.go#L158-L162` | Validator checks only that the block exists; a missing arch list means "all" [C-TD-casaos-zimaos-025][C-TD-casaos-zimaos-026] |
| App update | `CasaOS-AppManagement@debfa317:service/compose_app.go#L171-L258`, `#L428-L484` | Async update; compose-file rollback does not cover a failed start [C-TD-casaos-zimaos-027][C-TD-casaos-zimaos-028] |
| Catalog | `CasaOS-AppManagement@debfa317:service/appstore.go#L71-L117` | Catalog refresh keyed on Content-Length; unsigned zip [C-TD-casaos-zimaos-029] |
| Auth | `CasaOS-UserService@800c630c:main.go#L107-L130`; `CasaOS-Common@bd9a9049:utils/jwt/jwt.go#L18` | ES256 JWT + JWKS [C-TD-casaos-zimaos-031] |

---

## 4. Claims vs code

| Marketing or docs claim | What the code or artifact shows | Verdict |
|---|---|---|
| "Stable OTA update functionality" (README) [C-TD-casaos-zimaos-004] | Real RAUC A/B with signed verity bundles and 3-try fallback [C-TD-casaos-zimaos-008][C-TD-casaos-zimaos-012]. But the bootloader partition is not A/B [C-TD-casaos-zimaos-011], and mark-good does not test health [C-TD-casaos-zimaos-013]. | **Mostly agrees** |
| "When one partition fails, you can easily switch to the backup partition" (docs) [C-TD-casaos-zimaos-016] | True for the kernel/rootfs pair. The data partition and the pre-reboot migrations are not rolled back [C-TD-casaos-zimaos-014]. | **Partly agrees** |
| CasaOS "can be updated from the UI" | The UI triggers `curl get.casaos.io/update \| bash` as root [C-TD-casaos-zimaos-023]. That URL returned HTTP 500 on 2026-11-11 [C-TD-casaos-zimaos-022]. | **Contradicts** (in practice today) |
| ZimaOS "zero telemetry and zero user data collection" [C-TD-casaos-zimaos-033] | No telemetry was found in the units read. Plus licenses are device-bound and transferable via "Order Management", which implies an online activation path [C-TD-casaos-zimaos-032]. CasaOS's installer geo-locates the user [C-TD-casaos-zimaos-034]. | **Not contradicted; activation path unverified** |
| "Supports all X86-64 hardware" [C-TD-casaos-zimaos-035] | The only release assets are x86_64 [C-TD-casaos-zimaos-003]. Secure Boot must be off [C-TD-casaos-zimaos-006]. | **Agrees** (x86-only by design) |
| App updates are safe (implied by one-click update) | A failed container start leaves the new compose file in place, and no data is snapshotted [C-TD-casaos-zimaos-028] | **Contradicts** |

---

## 5. Real-world failure reports and lessons

| Report | What happened | Lesson for OneMind |
|---|---|---|
| ZimaOS#557 (2026-07) [C-TD-casaos-zimaos-044] | The update "succeeded" in the UI, but slot B kernel-panicked because a second NVMe enumerated slowly. RAUC fell back to A on every try, and the user saw nothing. | The fallback worked. The **reporting** failed. OneMind must surface "update rolled back, here's why" (boot-count and last-panic capture) in the UI and alert center (UX-4, R-2). |
| ZimaOS#549 (2026-07) [C-TD-casaos-zimaos-045] | Docker 28 mount churn knocked NetworkManager, logind and **rauc itself** off D-Bus on every boot. The box stayed "good". It was fixed by pinning Docker back to 27.5.1 in the Buildroot fork. | A started-services gate cannot see this class of failure. OneMind's fresh-signal gate should also probe **the control plane needed for remote recovery** (network config API, update daemon reachable). Pin and canary the container runtime. |
| ZimaOS#478 (2026-04, beta, open) [C-TD-casaos-zimaos-046] | "Corrupt Services and boot" (title only read) | Beta channel is where these surface; keep a beta channel (R-1). |
| CVE series 2024–2026 [C-TD-casaos-zimaos-043] | Unauthenticated user enumeration, file read and write through the API, an auth bypass via a system username (9.4), and internal service access via a proxy endpoint (9.1). | The web API is the attack surface on these boxes. OneMind needs an authz layer in the gateway and API fuzzing in CI (U-4). |

---

## 6. Strengths and weaknesses

**Strengths**
- A real appliance update chain on cheap x86 hardware: signed verity RAUC, 3-try A/B, a rescue entry and an offline update path [C-TD-casaos-zimaos-008][C-TD-casaos-zimaos-012][C-TD-casaos-zimaos-017].
- A very simple app format that any Compose user understands; a large install base (~900k downloads of the 1.8.0 bundle) [C-TD-casaos-zimaos-003][C-TD-casaos-zimaos-024].
- NAS depth: RAID, Btrfs, optional ZFS, SMB, Time Machine and a phone/desktop client with P2P remote access [C-TD-casaos-zimaos-041].
- An honest, low price: free with caps, $29 per device for life [C-TD-casaos-zimaos-032].

**Weaknesses**
- Closed OS, x86 only, Secure Boot off; signing CA never expires and is named "Development" [C-TD-casaos-zimaos-002][C-TD-casaos-zimaos-006][C-TD-casaos-zimaos-009][C-TD-casaos-zimaos-049].
- Mark-good after "services started"; pre-reboot data migrations; non-A/B ESP [C-TD-casaos-zimaos-011][C-TD-casaos-zimaos-013][C-TD-casaos-zimaos-014].
- App layer: no permission model in the validator, privileged and host-network apps in the official store, unsigned catalog, no data snapshot on app update [C-TD-casaos-zimaos-025][C-TD-casaos-zimaos-028][C-TD-casaos-zimaos-029][C-TD-casaos-zimaos-030].
- No Kubernetes, no multi-node, no robotics, IoT radios or TAK; AI is photo search plus an external file-only MCP server [C-TD-casaos-zimaos-018][C-TD-casaos-zimaos-038].
- CasaOS users were stranded: no stable release since 2024, and the only route to ZimaOS is a reinstall [C-TD-casaos-zimaos-001][C-TD-casaos-zimaos-047].

---

## 7. What competitors do (constraint-fit)

OneMind's constraints are: solo developer at first; x86 + Pi 5 + Jetson; k3s on platform nodes; robotics/IoT; Apache-2.0 open core; family accounts; AI-operated.

| Question | ZimaOS / CasaOS | HAOS | umbrelOS | Olares | Constraint fit with OneMind |
|---|---|---|---|---|---|
| Base / image build | Buildroot fork, closed build [C-TD-casaos-zimaos-005] | Buildroot, open BR2_EXTERNAL tree [C-TD-home-assistant-os-003] | Debian trixie via container build [C-W2-043] | None (installs on Ubuntu/Debian) [C-TD-olares-042] | **Medium.** It matches the appliance goal, but on x86 only. Buildroot made ZimaOS carry NVIDIA drivers as kernel-pinned sysext images [C-TD-casaos-zimaos-050], a cost Debian avoids. |
| Update engine | RAUC verity, GRUB, 3 tries; single shared boot partition [C-TD-casaos-zimaos-008][C-TD-casaos-zimaos-012] | RAUC verity, 3 tries; boot partition also single [C-LAB-rauc-010][C-TD-home-assistant-os-008] | Rugix [C-TD-umbrelos-009] | none; retry-forward [C-TD-olares-014] | **High.** It is the same engine and backend OneMind chose (REC-DEC-05). ZimaOS's `install-check` (compatible check, grubenv repair, exit 10) mirrors HAOS's hook [C-TD-home-assistant-os-010]. |
| Commit trigger | services started [C-TD-casaos-zimaos-013] | commits even when unhealthy [C-W3-025] | at daemon start [C-W3-036] | n/a | **Low.** None of the three is good enough; OneMind's fresh-signal gate is better. |
| Signing | RSA CA, no expiry, "Development" naming [C-TD-casaos-zimaos-009] | CA with expiry, rotated by cross-signing [C-W3-024] | stable unsigned [C-W3-034]; 2.1 beta signed with an offline root [C-TD-umbrelos-013] | MD5 only [C-TD-olares-004] | **Low.** It works as an anti-pattern list. |
| Install paths | USB installer, erases disk; Secure Boot off [C-TD-casaos-zimaos-007] | image / installer; script modes dropped [C-W3-028] | image (Rugix Bakery) [C-TD-umbrelos-006] | script / ISO [C-TD-olares-042] | **Medium.** It matches OneMind's P3 USB installer. |
| App format | Compose + `x-casaos`, no permission fields [C-TD-casaos-zimaos-024][C-TD-casaos-zimaos-025] | app `config.yaml` with declared host_network/privileged [C-TD-home-assistant-os-026] | Compose + `umbrel-app.yml` with permissions [C-TD-umbrelos-026] | Helm + OlaresManifest, linter bans hostNetwork [C-TD-olares-028] | **Medium.** It is a good import source for REC-DEC-10 (the Compose importer). |
| Script → image migration | reinstall + SMB + CTOZ [C-TD-casaos-zimaos-047] | dropped script modes | n/a | n/a | **High relevance.** It is a direct warning for OneMind's P6. |

---

## 8. What OneMind copies, and what it does better

| ID | Recommendation | Evidence | Requirement IDs |
|---|---|---|---|
| REC-TD-CZ-01 | **Copy:** RAUC verity bundles with GRUB OK/TRY counters, 3 tries and a **rescue-shell boot entry** per slot; an offline drop-folder update path for air-gapped boxes. | [C-TD-casaos-zimaos-008][C-TD-casaos-zimaos-012][C-TD-casaos-zimaos-017] | R-1, R-3, N-6 |
| REC-TD-CZ-02 | **Do better:** commit only on fresh health signals (REC-DEC-07). Add two probes ZimaOS#549 shows are needed: the update daemon answers on D-Bus, and the network-config API answers. Show every rollback with its cause in the UI and alert center. | [C-TD-casaos-zimaos-013][C-TD-casaos-zimaos-044][C-TD-casaos-zimaos-045] | R-1, R-2, UX-4 |
| REC-TD-CZ-03 | **Do better:** no data migrations before reboot. Migrations run in the new slot, after commit or against a copy, and stay reversible until commit. This extends 01 §4.2 item 6 (k3s datastore copy) to every data migration. | [C-TD-casaos-zimaos-014] | R-1, R-3, M-6 |
| REC-TD-CZ-04 | **Do better:** never overwrite the live ESP file by file. Treat first-stage GRUB updates as rare, separately gated, atomic writes (temp + rename, two grubenv copies as 01 §4.3 plans). | [C-TD-casaos-zimaos-011] | R-1, R-3 |
| REC-TD-CZ-05 | **Do better:** signing certificates with real expiry, production naming, and an offline root (01 §4.2 item 7). Pin CI actions by SHA. | [C-TD-casaos-zimaos-009][C-TD-casaos-zimaos-015][C-TD-casaos-zimaos-049] | U-4, R-3, M-2 |
| REC-TD-CZ-06 | **Copy:** the Compose + metadata-block idea as an **import format** (`x-casaos` → `onemind.app.yaml`). **Do better:** a validator that rejects privileged/host-network apps without a declared permission, a required arch list, a signed catalog, and a pre-update data snapshot with real rollback on a failed start. | [C-TD-casaos-zimaos-024..030] | A-1, A-3, A-5, U-4, AI-3 |
| REC-TD-CZ-07 | **Do better:** if OneMind ships the P6 script install, either ship an in-place "adopt this Debian into the image" path or label P6 clearly as "reinstall to upgrade". CasaOS left its users with a wipe. | [C-TD-casaos-zimaos-047][C-TD-casaos-zimaos-001] | P-7, R-3, REC-DEC-16 |
| REC-TD-CZ-08 | **Copy:** the plain business model of free with caps plus a cheap lifetime license that is automatic on own hardware. **Do better:** do not cap family members in the free tier (U-1 is core to OneMind). | [C-TD-casaos-zimaos-032][C-TD-casaos-zimaos-048] | H-1, U-1, M-4 |
| REC-TD-CZ-09 | **Do better:** OS-level, permissioned MCP over the local API with per-agent tokens, not an external file-only server that holds the admin password. | [C-TD-casaos-zimaos-038] | AI-2, AI-3, AI-5 |

---

## 9. Does anything here challenge the Tier A decisions in 01?

| 01 decision | What CasaOS/ZimaOS shows | Effect |
|---|---|---|
| **RAUC engine** (REC-DEC-05) | A second constraint-matched consumer appliance ships Buildroot + RAUC + GRUB with 3 tries [C-TD-casaos-zimaos-008][C-TD-casaos-zimaos-012] | **Strengthens.** It adds a code-level adopter to the S2 C4 "proven" cell. W3-steelman already lists ZimaOS from the release asset [C-W3-047]; this pass confirms it from the image itself. |
| **Debian 13 base** (REC-DEC-01) vs a Buildroot base | ZimaOS and HAOS chose Buildroot. But ZimaOS had to fork Buildroot to pin Docker after a field failure, and shipped NVIDIA drivers as kernel-version-pinned sysext images [C-TD-casaos-zimaos-005][C-TD-casaos-zimaos-045][C-TD-casaos-zimaos-050]. It never shipped ARM. | **Neutral to supportive.** Buildroot works for an x86 NAS. It shows the GPU-driver and runtime-pinning burden that Debian's packages avoid for N-8/F-2. No flip. |
| **k3s on ≥ 4 GB + SSD nodes** (REC-DEC-09) | A Docker-only appliance with a 4 GB minimum reached large adoption (~900k downloads of one bundle) without Kubernetes [C-TD-casaos-zimaos-003][C-TD-casaos-zimaos-035] | **Adds weight to the Docker/Compose steelman (01 §6.3)**, but only for a single-box NAS. ZimaOS has no multi-node, robotics or GPU-scheduling story, so its constraints do not match F-14/N-7. No flip, but it supports keeping the Compose importer and the NATS-leaf tier. |
| **Health gate** (REC-DEC-07) | Started-services gates miss control-plane failures (#549) | **Strengthens**, and adds two probes (REC-TD-CZ-02). |
| **Disk layout** (01 §4.3) | ZimaOS's single ESP is overwritten in place | **Refines.** Specify an ESP-update policy in 01 §4.3 (REC-TD-CZ-04). |
| **Data migrations / rollback** (01 §4.2 item 6) | Pre-reboot migrations defeat rollback | **Refines.** Generalise "trial boot runs against a copy" to all migrations (REC-TD-CZ-03). |
| **Script first, image later** (DC-22, W18 P0-8) | CasaOS → ZimaOS needed a wipe and reinstall [C-TD-casaos-zimaos-047] | **Weakens the P6 plan slightly.** It is a third data point after DC-22's refuter (C-REF-DC-longevity-006). An adopt-in-place path or explicit labelling is needed (REC-TD-CZ-07). |
| **Secure Boot later, layout now** (REC-DEC-08) | ZimaOS requires Secure Boot off [C-TD-casaos-zimaos-006] | **Supports.** It shows what happens when the layout is not planned for it. |

**Net:** nothing here overturns a Tier A decision. Four items refine 01 (gate probes, migrations, ESP policy, P6 migration path) and should be picked up when 01 §4.2–4.4 is next revised.

---

## 10. Glossary

| Term | Meaning |
|---|---|
| **Buildroot** | A tool that builds a small, custom Linux system from source; used by HAOS and ZimaOS instead of a full distribution. |
| **RAUC** | An open-source update engine that writes a new OS copy into the inactive "slot" and tells the bootloader to try it. |
| **Slot (A/B)** | One of two copies of the OS. Updates go to the copy you are *not* running, so a failure leaves the other intact. |
| **Verity bundle** | A RAUC update file whose contents are checked block by block against a signed hash tree while being installed. |
| **Mark-good / commit** | The moment the system declares the new slot healthy, so the bootloader stops counting failed tries. |
| **OK / TRY counters** | GRUB variables: OK=1 means the slot is allowed; TRY counts boots without mark-good; at 3 the slot is skipped. |
| **ESP** | EFI System Partition, the small FAT partition that holds the bootloader on UEFI PCs. |
| **Rescue shell** | A minimal boot mode for repair when no slot is healthy. |
| **systemd-sysext** | A systemd feature that overlays extra files (e.g. drivers) onto a read-only OS from an image file. |
| **Docker Compose / `x-casaos`** | A YAML file describing containers; `x-casaos` is IceWhale's extra block with app-store metadata. |
| **JWT / JWKS** | Signed login tokens, and the published public keys other services use to check them. |
| **OTA** | Over-the-air update, downloaded and installed by the device itself. |
| **CVE** | A public identifier for a disclosed security vulnerability. |

---

## 11. Gaps (not verified in this pass)

- The exact target partition table and sizes (the installer was not run) and how the installer chooses disks.
- Whether AppArmor profiles are enforced at runtime [C-TD-casaos-zimaos-051]; whether the license activation phones home.
- ZimaOS's own AppManagement build (closed): the CasaOS code at `debfa317` may differ from what ZimaOS 1.8.0 runs, whose release notes list "Optimized Docker application lifecycle management" (https://github.com/IceWhaleTech/ZimaOS/releases/tag/1.8.0).
- ARM: the hook handles a `spl` slot class and an eMMC `boot0` for `icewhale-zimaboard` (`zimaos-1.8.0.raucb:hook#L213-L281`), which hints at non-x86 boot code. No ARM release exists [C-TD-casaos-zimaos-003]. **UNVERIFIED** intent.
