# StartOS (Start9): Tier B condensed teardown

**Workstream:** W1 (Tier B teardown), feeding W3 (updates), W6 (security), W9 (AI layer) and W12 (app format) · **Tag:** TD-startos · **Date:** 2026-11-11
**Baseline:** StartOS **v0.4.2**, released 2026-11-09, tag `start-os/v0.4.2` = commit `175ce3beb370443d8db2cea30c3f99ebdcd1a8f5` [C-TD-startos-001]. In this file, `@175ce3b` means that full SHA, and every code path is in `github.com/Start9Labs/start-technologies` (renamed from `start-os`).
**Claims:** `evidence/claims/TD-startos.csv` (C-TD-startos-001 … 051) · **Sources:** `evidence/sources/TD-startos.md` (saved pages and SHA-256 hashes in `evidence/sources/TD-startos/`)
**Builds on:** [`research/competitors/landscape.md`](../../research/competitors/landscape.md) §1.6 and the earlier StartOS rows in `04-image-install-updates-rollback.md` (C-W3-048). This file answers the items 04 left open ("StartOS automatic rollback behaviour", "signing details not read"). It does not repeat Tier A work.
**Requirements served:** R-1, R-2, R-3, P-1, P-7, P-8, A-1, A-5, A-6, AI-2, AI-3, AI-4, AI-5, AI-8, U-1, U-4, M-2, M-6, N-2, N-3, N-8, N-9, H-1, H-2, RS-1, RS-2.

> ### Explain it like I'm the founder
> Start9 is a small US company that has sold a "personal server" box since about 2020. Its OS, **StartOS**, is the closest relative of umbrelOS: one box, one owner, a web dashboard, one-click apps. Its users are mostly privacy and Bitcoin people.
>
> **What they do well.** It is all MIT-licensed, so OneMind may reuse it, unlike umbrelOS. It is built on **Debian 13**, like OneMind's plan, and the same build makes x86, ARM, RISC-V, Raspberry Pi and NVIDIA GPU images, including one for NVIDIA's DGX Spark. Every app package and every OS update is **cryptographically signed**, and **you choose which signing keys you trust**. Since version 0.4.1, AI agents can drive the whole box through a built-in **MCP server**.
>
> **What they skip.** The OS has **no automatic rollback**. If a new version doesn't boot, Start9's own advice is to re-flash the box. Before each update it even deletes every old kernel except the one running now. The data disk is "encrypted", but **with a fixed key written in the source code**, and Start9's docs say plainly that anyone holding the drive can read it. The AI connection gives an agent **every admin power** (install, delete, run commands, update the OS, add SSH keys), with no per-action approval.
>
> **What this means for OneMind.** Nothing here overturns the Tier A plan. It strengthens three of its choices: real A/B with a health-gated commit, real disk keys (TPM or passphrase), and human approval on AI actions. Copy Start9's signed package format, its "registry is just a signed index" idea, its user-editable trust list and its pre-update app snapshot. One detail needs attention: on new hardware Start9 had to move to Debian's **backports** kernel, which Debian itself says is less tested. 01's kernel route should say which Debian kernel OneMind ships (§12).

---

## 1. At a glance

| Topic | StartOS 0.4.2 | Evidence |
|---|---|---|
| What it is | Single-box "personal server" OS with a web UI and a curated service marketplace; one monorepo also builds StartWRT (router OS), StartTunnel, the registry and the SDK | [C-TD-startos-002] |
| Architecture | Rust daemon (`startd`, one `start-core` crate) + JSON-RPC API + Angular UI + Patch-DB state; services in LXC | [C-TD-startos-004] |
| Base OS | Debian 13 "trixie" via live-build | [C-TD-startos-005] |
| Kernel | Debian **trixie-backports** kernel on x86/arm64 (7.x); Raspberry Pi vendor kernel 6.18.33+rpt on Pi | [C-TD-startos-007, -008] |
| Image build | live-build in a container → squashfs root → hybrid ISO (x86, arm64, riscv64) or GPT `.img` (Pi, Rockchip) | [C-TD-startos-006, -011] |
| Install paths | USB installer ISO; flash `.img` to microSD for Pi 4; Start9 box preinstalled. No script install, no VM appliance image found | [C-TD-startos-006, -007, -038] |
| Update | Signed squashfs downloaded and verified, `upgrade` script rewrites `/boot` and GRUB, then a symlink flip; reboot | [C-TD-startos-013, -014, -016] |
| Rollback | **OS: none automatic**, re-flash is the documented fallback. **Services: data snapshot restored on a failed update** | [C-TD-startos-017, -019, -022] |
| App format | **S9PK v2**: signed BLAKE3 Merkle archive with manifest, JS lifecycle code and per-arch squashfs images; built with a TypeScript SDK | [C-TD-startos-024, -025, -026] |
| Marketplace | Registries are signed indexes; binaries hosted anywhere; Start9 Registry (supported) + Community Registry (listed only) | [C-TD-startos-028] |
| Identity | One master password (also SSH); per-device signing keys; named bearer tokens; no multi-user | [C-TD-startos-031, -032] |
| AI features | MCP server at `/mcp` with 208 tools, opt-out exposure; AI support agent "Dux" (paid support) | [C-TD-startos-029, -030, -040] |
| Backups | Own encrypted, erasure-coded FUSE filesystem to a USB drive or LAN share; per-service stop during backup; cross-hardware and cross-arch restore | [C-TD-startos-034, -035] |
| Security | Signed updates and packages with user-managed trust; Secure Boot via shim + per-box MOK; **data-disk LUKS key is a source constant**; no dm-verity | [C-TD-startos-014, -033, -036, -037] |
| Hardware | Server One (Ryzen 5 6600H, 16/32 GB, 2/4 TB), USD 899–1,399; also runs on DIY x86/ARM/RISC-V, Pi 4, DGX Spark | [C-TD-startos-038, -039, -050] |
| License | MIT (a few third-party exceptions) | [C-TD-startos-002] |
| Business model | Hardware sales + Premium Support USD 200/yr; USD 1.2M seed (2021, secondary source) | [C-TD-startos-039, -040, -041] |
| Team | Small core: two human developers dominate commit history; an agent account is the third-largest contributor | [C-TD-startos-042] |
| Kubernetes / robotics | No / no | [C-TD-startos-027]; no robot, ROS or device-protocol code found |

## 2. Architecture

One Rust library (`start-core`) holds the whole backend: service lifecycle, networking (DNS, ACME, Wi-Fi, Tor, WireGuard), backups and the API. Thin binaries wrap it for each product (`startbox` runs the `startd` daemon and the CLI). The UI talks to the daemon only over JSON-RPC. State changes stream to the browser as Patch-DB diffs [C-TD-startos-004]. 0.4.0 replaced PostgreSQL with Patch-DB and is Start9's third full rewrite (0.2.0 in 2020, 0.3.0 in 2022, 0.4.0 in 2026). Each rewrite broke backup compatibility [C-TD-startos-003].

**Apps run in LXC, not Docker.** Every service gets its own LXC container. Inside it, a Node.js runtime loads the package's JavaScript and starts the app's processes as namespace "subcontainers" [C-TD-startos-027]. Start9 says Docker and Podman "did not offer the reliability and flexibility needed" [C-TD-startos-027]. **Constraint note:** this is a single-box design. Nothing schedules work across machines.

## 3. Base OS and kernel

- **Debian 13 trixie**, built with Debian's own `live-build` (`projects/start-os/build/image-recipe/Dockerfile#L1` `ARG SUITE=trixie`; `build.sh#L107-L122` `lb config … -d ${IB_SUITE}`) [C-TD-startos-005].
- **Kernel source:** on x86 and arm64, apt pinning makes `linux-image-*`, `linux-headers-*` and NVIDIA packages come from **trixie-backports** (`build.sh#L233-L239` @175ce3b) [C-TD-startos-008]. Issue reports show shipped kernels `7.0.4+deb13` and `7.2.11+deb13` [C-TD-startos-008]. Debian's own wording on backports: they "cannot be tested as extensively as Debian stable" and are "provided on an as-is basis" [C-TD-startos-009].
- **Raspberry Pi:** the image pins Raspberry Pi's vendor kernel `6.18.33+rpt`, including the `rpi-2712` (Pi 5) flavour. Even so, the docs say "Raspberry Pi 4 ONLY", and a Pi must be **re-flashed** for a major version upgrade (`build.sh#L85-L89`; `docs/src/installing-startos.md#L190-L195`) [C-TD-startos-007].
- **NVIDIA:** the `-nvidia` images add NVIDIA's container-toolkit repo and compile NVIDIA's `.run` driver with `--kernel-module-type=open` inside the build chroot (`build.sh#L204-L208`, `#L255-L363`) [C-TD-startos-010]. One arm64 variant targets the **DGX Spark** and carries a boot argument that works around a GB10 hang [C-TD-startos-050]. There is **no Jetson/L4T target** [C-TD-startos-006].

## 4. Image build and disk layout (code)

**Build** (`projects/start-os/build/image-recipe/build.sh` @175ce3b):
1. Read the version, git hash and platform out of the StartOS `.deb` (L18–L33).
2. Pick the bootloaders, `non-free` firmware areas and image type for each platform (L35–L72). Pi and Rockchip build `.img`; everything else builds a hybrid ISO [C-TD-startos-006].
3. Run `lb config` on trixie, add the Raspberry Pi, Armbian or NVIDIA apt sources, install the StartOS `.deb`, and pre-download the Tor service package (L107–L140, L190–L208).
4. `lb binary_rootfs` produces `filesystem.squashfs`, which also ships alone as the OTA update artifact (L429–L432).

**Disk layout of the Pi/Rockchip `.img`** (`build.sh#L463-L587`) [C-TD-startos-011]:

| # | Partition | Size | FS | Contents |
|---|---|---|---|---|
| 1 | `firmware` | 128 MiB | vfat | Pi firmware, U-Boot, DTBs |
| 2 | `efi` | 100 MB | vfat | GRUB (arm64-efi, removable) |
| 3 | `boot` | 2 GB | vfat | kernels + initrds (**one shared set, no A/B**) |
| 4 | `root` | squashfs + 256 MB, grows at first boot | btrfs | `images/<blake3>.rootfs` files, `config/current.rootfs` symlink, `config/overlay/` (persistent `/etc` changes) |

**Boot** (`projects/start-os/build/lib/scripts/startos-initramfs-module#L45-L121`) [C-TD-startos-012]: the initramfs mounts partition 4. It follows `current.rootfs`, or picks the newest `*.rootfs` when the pointer is missing. It mounts that squashfs read-only and builds `/` as an overlay: the persistent `config/overlay`, then the squashfs, with a **tmpfs** upper layer on top. Anything written outside the config overlay is lost at reboot. Issue #4647 shows this biting users (§10).

**Takeaway:** this is an "image store" design, not A/B slots. Many root images can sit on the data filesystem, limited only by free space, so there is no fixed slot size. The cost: the bootloader, `/boot` and the ESP are shared and rewritten on every update.

## 5. Install paths

| Path | Offered? | Notes |
|---|---|---|
| USB installer ISO (x86_64, aarch64, riscv64; standard / slim / NVIDIA) | Yes | Users check SHA-256 against the release page. Images are served from a DigitalOcean Spaces CDN [C-TD-startos-049] |
| Flash `.img` to microSD | Pi 4 only | Also the only major-upgrade path on a Pi [C-TD-startos-007] |
| Preinstalled box | Yes | Server One [C-TD-startos-038] |
| Script on an existing distro | Not found | No installer script in the repo or docs |
| VM appliance | Not found | `qemu-guest-agent` is in the package list, but no VM image is published (release table) [C-TD-startos-049] |

## 6. Update and rollback (code)

```mermaid
sequenceDiagram
    participant U as Owner (UI/CLI)
    participant D as startd (update/mod.rs)
    participant R as Registry
    participant S as upgrade script
    participant B as Boot (GRUB + initramfs)
    U->>D: server.update (explicit; no auto-update)
    D->>R: os.version.get(source, target range)
    R-->>D: squashfs asset + signatures
    D->>D: require signer trusted for OS updates (L320-326)
    D->>D: prune-images (oldest non-current) + prune-boot (all kernels except running) (L459-466)
    D->>D: download to images/next.squashfs, re-verify BLAKE3 (L469-484)
    D->>S: run new image's upgrade script (L486-503)
    S->>S: b3sum check, unpack new /boot over shared /boot
    S->>S: chroot new image: grub-install + update-grub
    S->>S: sign unsigned modules with box MOK
    S->>S: mv to images/<hash>.rootfs; ln -sf current.rootfs
    D-->>U: "restart required"
    U->>B: reboot
    B->>B: mount current.rootfs (no boot counter, no fallback)
    alt boots
        B->>D: startd runs DB migrations (down-migrations if DB is newer)
    else does not boot
        U->>U: re-flash (documented fallback)
    end
```

Code anchors (all @175ce3b):
- **Signature gate:** `shared-libs/crates/start-core/src/update/mod.rs#L320-L326` [C-TD-startos-014]. The CLI's `--trust` flag overrides signer trust only. Signature and integrity checks always run.
- **Download, verify, run:** `update/mod.rs#L448-L506` [C-TD-startos-013].
- **The upgrade itself:** `projects/start-os/build/lib/scripts/upgrade#L17-L94`. It checks the checksum (L17–L25), unpacks the new `/boot` (L33), runs `grub-install` and `update-grub` from a chroot of the new image (L65–L76), signs modules with the box's MOK (L78–L85) and flips the pointer (L93–L94) [C-TD-startos-016].
- **Pruning:** `prune-boot#L10-L21` deletes every kernel except the one running. `prune-images#L32-L58` deletes the oldest non-current images until the new image plus 1 GiB fits [C-TD-startos-018].
- **No automatic OS rollback.** At the tag there is no boot counter, `grubenv` flag or fallback-image logic. The initramfs always boots `current.rootfs` [C-TD-startos-017]. Previous images may still be on disk, but nothing selects them, and their kernels were already deleted by `prune-boot`. That last point is our inference from the scripts and was not tested. Start9's docs: "There are *no* automatic updates", and if a UI update goes wrong, "it may be necessary to update StartOS by re-flashing" [C-TD-startos-019]. An update can take up to an hour after the restart, with no progress shown [C-TD-startos-020].
- **Data side:** when the database is newer than the running OS, `startd` runs **down-migrations** (`version/mod.rs#L100-L112`) [C-TD-startos-021], so a manually restored older image can still start. **Service updates** snapshot the service's data and restore it if the update fails (`service/mod.rs#L586-L596`) [C-TD-startos-022]. Open issue #4454 says a failed service rollback can leave the service stuck [C-TD-startos-023].
- **Layout migration over the air:** x86 boxes moved from the 0.3.x three-root layout to the 0.4.0 image store in place. The initramfs runs the migration on first boot (`startos-initramfs-module#L60-L95`). Pi boxes had to re-flash [C-TD-startos-047].

- **Health checks exist, but only for services.** Package developers define them (Starting / Loading / Success / Error, with a grace period), and they gate a service's readiness. No health signal feeds the OS update [C-TD-startos-048].

**Compared with the Tier A finding.** umbrelOS commits at daemon start [C-W3-036] and HAOS commits even when unhealthy [C-W3-025]. StartOS has **nothing to commit or roll back**. It is the least protected of the three against a bad OS image.

## 7. App format, SDK and marketplace (code)

- **S9PK v2** (`shared-libs/crates/start-core/src/s9pk/v2/mod.rs#L25-L27`): magic `0x3b 0x3b 0x02`. It is a BLAKE3 Merkle archive with an embedded Ed25519 signature (context `s9pk`) that readers **always** verify. Extra endorsements go in an append-only trailer (`s9pk-structure.md#L1-L33`) [C-TD-startos-024]. Because it is a Merkle archive, partial downloads can be verified, and container images mount straight from the archive without unpacking [C-TD-startos-003].
- **Contents:** `manifest.json`, an icon, `LICENSE.md`, `instructions.md`, `javascript.squashfs` (the package's lifecycle code) and `images/<arch>/<id>.squashfs`. The packer rejects archives that lack the required files (`manifest.rs#L47-L74`) [C-TD-startos-025].
- **Manifest** (`manifest.rs#L30-L43`, `#L142-L154`): Exver version, `canMigrateTo/From`, volumes, dependencies and **`hardwareRequirements` (device filters, RAM, architectures)**, which the server checks against the hardware it detects [C-TD-startos-026]. Flags request `/dev/fuse`, `/dev/net/tun`, `/dev/kvm` or hardware acceleration, and packages can register **plugins**. Tor became a plugin in 0.4.0 [C-TD-startos-051].
- **SDK:** apps are written in TypeScript against `@start9labs/start-sdk`, then packed from Docker/Podman/OCI images into squashfs [C-TD-startos-025].
- **Registries:** a registry is a **signed index**. Binaries live on any CDN or GitHub release and are verified on install. Two registries are preloaded: Start9's (maintained and supported) and a Community registry (listed, not supported) [C-TD-startos-028].

## 8. Identity

There is one owner. A single **master password** logs in to the UI and also works for SSH. Browsers enrol per-device signing keys. API clients use named **bearer tokens** that are revoked by hand or after 30 days unused [C-TD-startos-031, -032]. There are no household accounts, roles or scopes. Issue #3881 (open) asks for named, revocable credentials and a read-only tier [C-TD-startos-032]. **Gap against OneMind U-1/U-3/U-4.**

## 9. AI features

- **MCP server** at `https://<server>/mcp` (streamable HTTP) since 0.4.1. It authenticates with a bearer token and adds `package.exec` (run a command inside a service) [C-TD-startos-029].
- **Exposure is opt-out** (`shared-libs/crates/start-core/src/mcp.rs#L21-L43`): every API method becomes a tool unless its handler sets `mcp=false`. At 0.4.2 that is **208 tools**, including `package.exec`, `package.install`/`uninstall`, `server.update`, `server.shutdown`, `backup.create`, `ssh.add` and `server.update-signers.add` [C-TD-startos-030]. The one guard in that file is a Host-header check that blocks requests to unknown names. We found no per-tool approval or audit. **An agent holding the token can add itself an SSH key and a new OS-update signer.**
- **Support AI:** paid support starts with an AI agent ("Dux"). It can hand off to an engineering agent ("Helix") that reads the source and files bug reports [C-TD-startos-040]. An agent account is the third-largest contributor to the repo [C-TD-startos-042].
- No local-LLM manager, GPU auto-detection UI or agent sandbox in the OS. GPU apps such as Ollama simply declare `hardwareAcceleration` [C-TD-startos-051].

## 10. Backups

Backups go to a **USB drive or a LAN network folder (CIFS)**. They are encrypted with the master password, and later backups update the copy already on the target. Each service is **stopped while it is backed up**, for consistency. Apps can exclude data; the Bitcoin package, for example, skips the blockchain. Restores work onto other hardware, and onto another CPU architecture through emulation [C-TD-startos-034]. The storage is Start9's own **`startos-backup-fs`**: append-only segments, ChaCha20 + HMAC-SHA256 and **Reed-Solomon erasure coding (10 + 2)** (`projects/start-os/backup-fs/DESIGN.md#L1-L40`) [C-TD-startos-035]. There is **no cloud or off-site target** and no restic-style deduplicated repository. 0.4.0 broke compatibility with older backups [C-TD-startos-003].

## 11. Security

| Control | StartOS 0.4.2 | Evidence |
|---|---|---|
| Update signing | Ed25519 keys; user-editable trust per channel (packages vs OS updates); three keys trusted by default; diagnostic mode has its own signer file | [C-TD-startos-014, -015] |
| Package signing | Mandatory embedded signature plus optional endorsements; unsigned or untrusted installs need explicit confirmation | [C-TD-startos-024] |
| Download integrity | BLAKE3 commitment checked after download and again in `upgrade` | [C-TD-startos-013, -016] |
| Verified boot / dm-verity | **None**: the squashfs is mounted with no runtime check | [C-TD-startos-037] |
| Secure Boot | Debian shim + **per-box MOK** that signs DKMS/NVIDIA modules; two MOK bugs broke installs | [C-TD-startos-036] |
| Disk encryption | LUKS, unlocked with a **compile-time constant key** (`disk/main.rs#L20-L21`, `setup.rs#L491-L499`). Docs: "anyone holding the server or its drive can read your services' data". Key-collection UX open since 2021 (#735) | [C-TD-startos-033] |
| Network | Tor plugin, WireGuard gateways, StartTunnel, per-interface public/private switches, a local root CA | [C-TD-startos-002, -051] |
| Auto security updates | None (owner action required) | [C-TD-startos-019] |

## 12. Real-world failure reports

| Issue | What happened | Lesson for OneMind |
|---|---|---|
| #4647 (closed 2026-11-09) | An OS update silently dropped user kernel parameters. Edits lived on the tmpfs layer, and `update-grub` ran inside the new image [C-TD-startos-043] | Supported, persistent drop-ins for boot arguments and `/etc` must survive updates (the same lesson as umbrelOS #2124; DC-16) |
| #3923 (closed 2026-09-17) | The installer wrote `/dev/sdX` names into fstab; a re-enumerated disk caused unrecoverable emergency mode [C-TD-startos-044] | Mount by UUID/PARTUUID only; test disk re-enumeration in CI |
| #4435 (open) | The FOSS-only image lost Wi-Fi after migration (no iwlwifi firmware) [C-TD-startos-045] | Firmware sets per SKU are part of the release contract; check hardware before an update |
| #4009 (closed) | The Pi root never grew; the resize ran through a read-only mount and ignored the error [C-TD-startos-046] | First-boot steps must fail loudly and be tested on real media |
| #3465 (closed 2026-07-13) | NVIDIA images shipped the proprietary module flavour, so Blackwell (GB10, RTX 50) could not initialise. The build chroot sees no GPU [C-TD-startos-010] | Pin NVIDIA's open modules explicitly; never let a build host's hardware decide |
| #4454 (open) | A failed service rollback has no exit [C-TD-startos-023] | Rollback paths need their own tests and a manual escape |

## 13. Claims vs code (condensed)

| Claim (docs / marketing) | Code @175ce3b | Verdict |
|---|---|---|
| "Squashfs images for OS updates, enabling better update verification" [C-TD-startos-003] | BLAKE3 commitment checked twice before the pointer flips [C-TD-startos-013, -016] | **Agree** |
| "OS updates from the UI require a signature from a key trusted for StartOS updates" | `validate_update_signatures` with the OS trust policy, before download [C-TD-startos-014] | **Agree** |
| "Rollback on failed updates" (0.4.0 notes) | Applies to **service data only** (`service/mod.rs`). The OS has no rollback [C-TD-startos-017, -022] | **Agree, but narrower than the headline suggests** |
| Pi 4 only (docs) | The image also builds the `rpi-2712` (Pi 5) kernel flavour [C-TD-startos-007] | **Docs narrower than the code** (support vs capability) |
| Data drive is not protected by your password (docs) | LUKS opened with a fixed constant [C-TD-startos-033] | **Agree** (honestly disclosed) |

## 14. Strengths and weaknesses

**Strengths:** MIT license; Debian 13 shared with OneMind's base; one build pipeline for x86, arm64, riscv64, Pi, Rockchip and NVIDIA (DGX Spark); signed packages and updates with **user-owned trust**; a registry that is a signed index (cheap to self-host or fork); per-service data snapshots on update; hardware requirements declared in the manifest; MCP built in; honest, very detailed docs; disciplined issue reports that cite file and line.

**Weaknesses:** no OS rollback, and old kernels are pruned before each update; one shared `/boot` and ESP rewritten every update; no dm-verity; the disk key is a constant; single user; MCP exposes full admin; no automatic security updates; frequent ground-up rewrites (three in six years) that broke backups; a backports kernel; the Pi is stuck on the Pi 4; no Kubernetes, multi-node, robotics or IoT; a very small team.

## 15. What competitors do (constraint-fit)

| Question | StartOS | umbrelOS | HAOS | Olares | Constraint fit with OneMind | OneMind choice (01) |
|---|---|---|---|---|---|---|
| OS update shape | Image store + symlink, shared `/boot` [C-TD-startos-016] | Rugix A/B [C-W3-036] | RAUC A/B [C-W3-025] | No OS image (script on a distro) | StartOS: **low** (single box, accepts re-flash). HAOS: **high** (appliance + boards) | RAUC A/B + health gate |
| Automatic rollback | None [C-TD-startos-017] | Commit at daemon start [C-W3-036] | Commits even when unhealthy [C-W3-025] | n/a | None of them fits fleets of robots | Fresh-signal gate [C-LAB-debian-rugix-023] |
| Base | Debian 13 [C-TD-startos-005] | Debian 13 [C-W3-039] | Buildroot | Ubuntu/Debian host | **High** (same distro, x86 + arm) | Debian 13 core |
| App unit | S9PK on LXC [C-TD-startos-024, -027] | Compose | Docker add-ons | Helm/OAC on k3s | **Medium**: S9PK signing and hardware fields fit; LXC runtime does not (OneMind is k3s) | Helm + `onemind.app.yaml` |
| AI control | MCP, 208 tools, opt-out, full admin [C-TD-startos-030] | MCP server (see umbrelos.md) | none in OS | Lares/Router | **Low** for physical devices: no approvals | Gateway-enforced approvals |
| Disk encryption | LUKS with a constant key [C-TD-startos-033] | see umbrelos.md | none | see olares.md | **Low** | LUKS2 data + real key material |

## 16. Challenges to OneMind's Tier A decisions (01)

| Tier A decision | What StartOS evidence says | Effect |
|---|---|---|
| **Debian 13 core** | A second shipping product on trixie, with x86, arm64, riscv64, Pi and NVIDIA (incl. arm64 DGX Spark) images from one live-build pipeline [C-TD-startos-005, -006, -050] | **Supports.** It also bears on DC-13: NVIDIA on Debian works in the field when the open module is pinned and the build compiles it ([C-TD-startos-010] shows what goes wrong otherwise). This slightly weakens the case that the GPU-server tier *needs* Ubuntu. |
| **K1: the board maintainer's kernel** (Debian kernel on x86) | To support its own newer box (Ryzen 6600H) and Blackwell/GB10, Start9 moved to **trixie-backports** kernels [C-TD-startos-008], which Debian calls less tested and "as-is" [C-TD-startos-009] | **Weakens a detail, does not flip.** 01 should say which Debian kernel OneMind ships: trixie stable (security-team supported) by default, with a written rule for when a SKU may use backports and who carries its CVE watch. Flagged for the owners of 01 §… (S5 kernel) and 26-…; not edited here. |
| **RAUC A/B + health-gated commit** | StartOS shows the cost of skipping it: re-flash as the recovery story, kernels pruned before update, a shared `/boot`. Its image-store design does avoid fixed slot sizes, which bears on Risk 3 (a Debian 14 rebase not fitting the slots) [C-TD-startos-011, -017, -018] | **Supports A/B.** The image-store idea is noted as a fallback layout if the T-W3-04 rebase spike shows slots are too small; it would still need boot counting added. |
| **k3s on ≥ 4 GB + SSD, NATS leaves below** | StartOS runs single boxes with LXC and no orchestrator [C-TD-startos-027] | **No challenge.** Its constraints (one box, no fleet, no GPU cluster) don't match F-14. It is consistent with OneMind's no-k3s leaf tier for small nodes. |
| **restic + online SQLite backup** | A custom erasure-coded FUSE store with no off-site target; the backup format broke at the 0.4.0 rewrite [C-TD-startos-003, -035] | **Supports restic** (a widely used, stable format). Copy the per-service quiesce and the cross-arch restore idea. |
| **Security day-1 layout (LUKS2 data)** | Encryption with a constant key gives no confidentiality against someone holding the disk [C-TD-startos-033] | **Supports and sharpens:** OneMind's LUKS2 must use TPM-sealed or user-held keys from day 1, or the docs must say "not encrypted". |
| **Signed from release 1** | Ed25519 signing for packages and OS updates, with a user-managed trust list, is shipping at small-team scale [C-TD-startos-014, -015, -024] | **Supports.** |
| **CRA: security updates on by default** | StartOS has no automatic updates [C-TD-startos-019] | **No relief.** StartOS doesn't show a CRA-compliant pattern; the conflict in [C-W6-008] stands. |
| **Jetson on L4T Ubuntu 24.04; bootc Industrial in year 2** | StartOS has no Jetson and no bootc | No evidence either way |

## 17. What OneMind copies and what it does better

| ID | Recommendation | Copy / better | Evidence | Requirements |
|---|---|---|---|---|
| REC-TD-startos-01 | **Signed app archive with a Merkle root**: one embedded publisher signature always verified, extra endorsements in a trailer, verifiable partial downloads. Model `onemind.app` bundles on it (MIT, so code reuse is allowed with attribution) | Copy | [C-TD-startos-024, -002] | A-1, A-5, A-6, R-1, U-4 |
| REC-TD-startos-02 | **Registry = signed index; binaries hosted anywhere.** It lets startups and communities run their own Market cheaply | Copy | [C-TD-startos-028] | A-5, A-6, F-5, W-8 |
| REC-TD-startos-03 | **User-owned trust list**, separate per channel (apps vs OS), with notifications when a registry adds or drops a key | Copy | [C-TD-startos-014, -015] | M-2, R-1, U-4 |
| REC-TD-startos-04 | **`hardwareRequirements` in the app manifest** (device filters, RAM, arch) checked against detected hardware, which drives "your box can or can't run this" | Copy, extend with NFD labels | [C-TD-startos-026] | N-3, A-8, P-6, AI-8 |
| REC-TD-startos-05 | **Snapshot app data before each app update and restore it on failure**, with a tested manual escape (their #4454) | Copy + better | [C-TD-startos-022, -023] | R-1, R-2 |
| REC-TD-startos-06 | **Never ship OS updates without a health-gated commit and automatic fallback**; never prune the last known-good kernel or slot before the new one is committed | Better | [C-TD-startos-017, -018] | R-1, R-3, M-6 |
| REC-TD-startos-07 | **MCP exposure opt-in per tool**, scoped tokens, and gateway approval for destructive or physical actions; never expose signer or SSH-key changes to agents | Better | [C-TD-startos-030, -031] | AI-2, AI-4, AI-5, U-4 |
| REC-TD-startos-08 | **Real disk keys** (TPM-sealed, with a recovery key) or state plainly "not encrypted" | Better | [C-TD-startos-033] | M-2, U-4, R-3 |
| REC-TD-startos-09 | **Persistent drop-ins for kernel arguments and `/etc`** that survive updates, as a base-OS extension point (DC-16) | Better | [C-TD-startos-043] | A-5, R-1, P-8 |
| REC-TD-startos-10 | **Pin NVIDIA's open kernel modules and test every GPU generation in CI**; never let the build host decide the flavour | Copy the build, do the test better | [C-TD-startos-010] | N-8, F-2, H-3 |
| REC-TD-startos-11 | **Honest, file-and-line issue culture and docs** (their issues name the file and line; their docs disclose weaknesses) | Copy | [C-TD-startos-033, -043, -044] | R-2, RS-1 |
| REC-TD-startos-12 | **Bundle paid support with hardware**, with AI first-line support that hands off to humans, as a model for R-2 and H-1 | Copy (business) | [C-TD-startos-040] | R-2, H-1, W-6 |

## 18. Glossary

| Term | Meaning |
|---|---|
| **squashfs** | A compressed, read-only filesystem packed into one file. StartOS ships its whole OS as one squashfs. |
| **overlayfs / tmpfs** | Overlayfs stacks a writable layer on a read-only one. Tmpfs is a RAM disk, so whatever it holds vanishes at reboot. |
| **initramfs** | A tiny early-boot system that finds and mounts the real root filesystem. |
| **A/B update** | Two OS copies: update the idle one, boot it, and switch back automatically if it fails. StartOS does **not** do this. |
| **Boot counter** | A counter the bootloader decrements on each try; when it hits zero, the box falls back to the old OS. |
| **dm-verity** | A kernel feature that checks every block of a read-only image against a signed hash while it runs. |
| **Secure Boot, shim, MOK** | UEFI firmware only runs signed bootloaders. Debian's *shim* is signed by Microsoft. A *Machine Owner Key* lets one box sign its own extra modules (e.g. NVIDIA). |
| **LUKS** | Linux disk encryption. Only as strong as the key that unlocks it. |
| **BLAKE3 / Merkle archive** | A fast hash. A Merkle archive hashes pieces into a tree, so any piece can be checked against one signed root. |
| **Ed25519** | A modern signature algorithm with small keys. |
| **S9PK** | StartOS's app package file. |
| **Exver** | Start9's version format: upstream version + wrapper version + optional "flavor". |
| **LXC** | Linux containers that behave like small whole systems; an alternative to Docker. |
| **live-build** | Debian's official tool for building live and installer images. |
| **Backports** | Newer Debian packages rebuilt for the current stable release; less tested, as-is. |
| **MCP** | Model Context Protocol: a standard way for AI agents to call tools. |
| **Registry** | A server that lists apps and their signatures for the marketplace. |
| **Erasure coding (Reed-Solomon)** | Extra parity data that lets a backup survive some corrupted pieces. |

## 19. Open items

- Behaviour after a real power cut during `upgrade` (GRUB rewrite plus pointer flip) is **not tested**. The single shared `/boot` suggests a vulnerable window, but this is inference. A VM spike, if wanted: run a forced kill during `grub-install` in a QEMU StartOS install (only inside a disposable VM, per rule 5).
- Contents of `signatures.tar.gz` and Start9's key ceremony or revocation process: **not read**.
- Whether Start9 will support the Pi 5 (the kernel flavour is already built): **unknown**. Re-check at the next minor release.
- Team size beyond the commit counts, and revenue: **not public**. The funding figure is SECONDARY [C-TD-startos-041].
