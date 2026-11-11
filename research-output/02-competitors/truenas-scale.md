# TrueNAS SCALE (Community Edition): Tier B condensed teardown

**Workstream:** W1 (Tier B) · **Tag:** TD-truenas-scale · **Date:** 2026-11-11
**Claims:** `evidence/claims/TD-truenas-scale.csv` (C-TD-truenas-scale-001 … 040; cited inline as `[C-TD-truenas-scale-###]`) plus reused C-DEC-007, C-W18-033 and C-W5-052 · **Sources:** `evidence/sources/TD-truenas-scale.md`
**Requirements served:** P-7, R-1, R-2, R-3, N-2, N-3, N-8, N-9, A-1, A-2, A-3, A-5, M-2, M-6, M-8, AI-1, AI-3, AI-5, H-1, H-2, H-4, UX-6, F-7, F-8, F-14, RS-1, RS-2, D-001

> **Naming.** iXsystems now calls the Linux product "TrueNAS Community Edition", and from the next major release it has no "SCALE" suffix in its version names. This file uses "TrueNAS" for the Linux edition and "CORE" for the old FreeBSD one.

> ### Explain it like I'm the founder
> TrueNAS is the best-known free NAS (network storage) operating system. It is the closest proof that **"Debian underneath, our own image on top" works for a funded company for years**. It is built from Debian packages that iX mirrors and freezes for each release, plus its own kernel and ZFS. It ships as one big image file. Users can't run `apt` on it [C-TD-truenas-scale-003, C-TD-truenas-scale-005, C-TD-truenas-scale-012].
>
> **Three lessons matter to you.**
> 1. **It ran its app store on k3s on single boxes, then left.** In 2024 it moved to Docker Compose. The reasons it gave: people prefer Compose, and Helm is "more complex and less portable". Its migration only moved apps from its own catalog. Apps from third-party catalogs were left behind [C-TD-truenas-scale-017, C-TD-truenas-scale-018, C-DEC-007]. This is why OneMind's app format must not depend on k3s-only features.
> 2. **Its updates are safe against broken installs, but they are not signed and not automatic.** Each update goes into a fresh ZFS "boot environment" next to the old one, and you can boot back into any older one. But the update client only checks checksums downloaded over HTTPS. It does not check a signature. Rollback is a manual choice, not a health check [C-TD-truenas-scale-008, C-TD-truenas-scale-009, C-TD-truenas-scale-011]. OneMind's plan (signed RAUC bundles plus an automatic health gate) is stronger on both counts.
> 3. **It is x86-only and NAS-first.** It has no Raspberry Pi, no Jetson, no robots, and no host Secure Boot [C-TD-truenas-scale-015, C-TD-truenas-scale-033]. It is a model for a **OneMind storage/Pro box profile**, not for the whole OS.

---

## 1. What was analysed

| Item | Value |
|---|---|
| Release analysed | **TrueNAS 25.10.8 "Goldeye"**, the General-profile release on 2026-11-11 [C-TD-truenas-scale-001] |
| Code pins | `truenas/middleware` @ `29ed02b8` (tag TS-25.10.8, 2026-10-26); `truenas/scale-build` @ `453acc8f` (tag TS-25.10.8, 2026-10-23); `truenas/apps` @ `c85431d5` (2026-11-10); 24.10.0 migration code @ `46406b62` |
| Next release | **TrueNAS 27** (it was "26" during beta). 27-RC.1 came out on 2026-10-06. It brings an annual cadence, Debian 13 trixie, Linux 6.18 and OpenZFS 2.4 [C-TD-truenas-scale-002, C-TD-truenas-scale-004, C-TD-truenas-scale-006] |
| Citation form | `SB@453acc8f:path#L` = `https://github.com/truenas/scale-build/blob/453acc8fddacf20c82a509a0177730e9479d49af/path#L…`; `MW@29ed02b8:` = `truenas/middleware` at `29ed02b8082f38494b0d2896bada8151f0d59716`; `AP@c85431d5:` = `truenas/apps` at `c85431d5f6ad13eb234bb67a1fc5dc908e05d112`. Full URLs are in the claims CSV. |
| Licence posture | Middleware and app catalog: **LGPL-3.0**. Build system: **GPL-3.0**. MCP server: **GPL-3.0** [C-TD-truenas-scale-025]. The LGPL and GPL are compatible with *using* TrueNAS, but OneMind (Apache-2.0, D-001) **copies patterns only, never code**. |

**Code citations used below (13):** image build `SB@453acc8f:scale_build/image/update.py#L56-L89`, `conf/build.manifest#L1-L30`, `#L355-L372`, `scale_build/extensions.py#L119-L166`, `scale_build/image/iso.py#L129-L132`; install/update `truenas_install/__main__.py#L293-L348, #L566-L580, #L679-L702`, `truenas_install/fhs.py#L95-L172`, `MW@29ed02b8:…/plugins/update_/install.py#L24-L62`, `…/update_/download.py#L72-L84`; rollback `…/plugins/boot_/environments.py#L132-L145`; app format `AP@c85431d5:ix-dev/community/actual-budget/app.yaml#L1-L40`, `…/templates/docker-compose.yaml#L1-L10`, `MW@29ed02b8:…/plugins/apps/compose_utils.py#L16-L56`, `…/apps/upgrade.py#L81-L160`, `…/apps/rollback.py#L27-L95`; migration `MW@46406b62:…/kubernetes_to_docker/list_utils.py#L42-L61`; backup `…/plugins/cloud_backup/sync.py#L18-L97`.

## 2. W1 field by field

| W1 field | TrueNAS (evidence) |
|---|---|
| **Architecture** | A Python **middleware** daemon owns all state and exposes a JSON-RPC 2.0 WebSocket API (the REST API is removed in 26/27). The Angular web UI and the CLI are clients of that API [C-TD-truenas-scale-030]. Storage is OpenZFS. Apps run on Docker Compose, and VMs and LXC containers run beside them [C-TD-truenas-scale-021, C-TD-truenas-scale-039]. |
| **Base OS** | **Debian 12 bookworm** for 25.10. Packages come from iX's own frozen mirror (`apt.sys.truenas.net/goldeye/25.10.2/…`) [C-TD-truenas-scale-003]. The next major moves to **Debian 13 trixie** [C-TD-truenas-scale-004]. iX builds **its own kernel** from a `truenas/linux` fork, tracking an upstream LTS line (6.12 for 25.10; 6.18 for 27), with its own config fragments [C-TD-truenas-scale-005, C-TD-truenas-scale-006]. |
| **Image build** | `scale-build` uses debootstrap to build a chroot, installs the manifest's packages, then makes a **nested squashfs**. The inner part is `rootfs.squashfs`. The outer part holds that image plus a `MANIFEST`, which is GPG-signed only "if enabled" (`SB@453acc8f:scale_build/image/update.py#L56-L89`) [C-TD-truenas-scale-007]. NVIDIA drivers are built as a separate **systemd-sysext** (`nvidia.raw`) [C-TD-truenas-scale-013]. **The public build repo is now frozen:** since March 2026 "the TrueNAS build system … has been moved to an internal infrastructure". 25.10.x release branches are still pushed, but no 26/27 build branch is public [C-TD-truenas-scale-026]. |
| **Install paths** | An x86 **ISO installer**, and since 2026 a **web-based install** through TrueNAS Connect [C-TD-truenas-scale-037]. Minimum hardware: 2-core x86_64, 8 GB RAM, 16 GB SSD boot device. "Almost any x86 computer" works [C-TD-truenas-scale-015]. There is no ARM image, no preinstalled image for third-party boards, and no VM appliance image in the docs read. iX sells its own appliances (§2, Hardware). |
| **Update / rollback** | The UI fetches an update manifest over HTTPS from `update.truenas.com`, downloads the `.update` file, checks its **sha256**, mounts the outer squashfs and checks per-file **sha1/sha256** values [C-TD-truenas-scale-008]. `truenas_install` then creates a **new boot environment** `boot-pool/ROOT/<version>`, clones the writable datasets from snapshots, unpacks the rootfs, sets `bootfs` and runs `update-grub`. If the install fails, it restores the old `bootfs` and deletes the half-built environment (`SB@453acc8f:truenas_install/__main__.py#L293-L348, #L566-L580, #L697-L702`) [C-TD-truenas-scale-009]. **Rollback is manual**: you activate an older environment in the UI or pick it in GRUB (`zectl activate`). No automatic fallback after a bad boot was found [C-TD-truenas-scale-011]. Update **profiles** (Developer / Early Adopter / General / Mission Critical) control which releases you are *told about*. Installing is still a click [C-TD-truenas-scale-038]. Major versions can't be skipped except by reinstalling and restoring the config file [C-TD-truenas-scale-016]. |
| **App format** | Git catalog `truenas/apps`, with trains community (487), stable (17), enterprise (4), test and dev. Each app has `app.yaml` (metadata, `min_scale_version`, run-as UID/GID, capabilities, a pinned render-library version and hash), `questions.yaml` (the install form), `ix_values.yaml` and a **Jinja-templated `docker-compose.yaml`** [C-TD-truenas-scale-020]. Images are pinned by digest [C-TD-truenas-scale-024]. The middleware renders the template and runs `docker compose up` [C-TD-truenas-scale-021]. Users can also paste **any Compose YAML** as a "custom app" [C-TD-truenas-scale-023]. |
| **Identity** | Local users and groups, AD/LDAP/IPA directory services, API keys, and 2FA (TOTP). About 141 fine-grained RBAC roles (e.g. `APPS_READ`, `BOOT_ENV_WRITE`, `FULL_ADMIN`) gate every API method [C-TD-truenas-scale-030]. Upgrading to 26/27 clears 2FA secrets that use non-standard intervals [C-TD-truenas-scale-030]. Web-UI login for directory accounts and STIG/FIPS are Enterprise-only [C-TD-truenas-scale-032]. |
| **AI features** | **There is no AI in the OS itself.** An official **MCP server** (`truenas/truenas-mcp`, Go, GPL-3.0) was released in Feb 2026 as a "Research Preview … NOT for production use". It has a read-only mode, confirmations before destructive actions, secret redaction, and uses an API key bound to an RBAC role [C-TD-truenas-scale-034]. Local-AI **apps** (Ollama, Open WebUI, LocalAI, vLLM) come from the community train, with a GPU picker [C-TD-truenas-scale-035]. NVIDIA GPUs from Turing onward only [C-TD-truenas-scale-014]. |
| **Backups** | ZFS snapshots and replication (core NAS feature). **TrueCloud Backup is restic** (a `truenas/restic` fork; zvols get snapshot-and-clone first), tied to an iX-referred Storj account [C-TD-truenas-scale-028]. App upgrades snapshot the app's data dataset [C-TD-truenas-scale-022]. The **config backup** is a tar of the config database plus an optional "secret seed". Without the seed, encrypted secrets are lost on restore [C-TD-truenas-scale-029]. |
| **Security** | Read-only `/usr`, `/opt` and `/conf`, read-only boot-environment roots, `@pristine` snapshots [C-TD-truenas-scale-010]. Package managers are disabled [C-TD-truenas-scale-012]. An audit subsystem is built into the image (`update.py#L37-L50`). **STIG and FIPS 140 are Enterprise-only** [C-TD-truenas-scale-032]. **No host Secure Boot:** the build has no shim or kernel-signing step, and the docs cover Secure Boot only for VMs [C-TD-truenas-scale-033]. Update integrity relies on HTTPS plus checksums. No signature check was found in the 25.10.8 client [C-TD-truenas-scale-008]. |
| **Hardware** | x86_64 only [C-TD-truenas-scale-015]. iX sells appliances: Mini (edge / branch office), R, M, H, F (all-NVMe) and V series [C-TD-truenas-scale-040]. HA dual-controller features are Enterprise appliance-only [C-TD-truenas-scale-036]. |
| **License** | Source under LGPL-3.0 / GPL-3.0 [C-TD-truenas-scale-025]. Community Edition has no licence fee. Enterprise features are unlocked by licence on iX hardware or, from 2026, through TrueNAS Connect [C-TD-truenas-scale-036]. |
| **Business model** | **Open core plus appliances plus SaaS.** Community Edition is free. Enterprise appliances come with 24×7 support. **TrueNAS Connect** has a free Foundation tier (2 systems, web install, TLS certificate, monitoring) and a Plus tier at $60/year (3 systems, history, replication management), with a Business tier planned. Connect becomes the "bridge" that licenses Enterprise features such as LTS onto your own hardware [C-TD-truenas-scale-036, C-TD-truenas-scale-037]. |

## 3. Boot → update → rollback (from code)

```mermaid
sequenceDiagram
  participant UI as Web UI / API
  participant MW as middlewared (update_ plugin)
  participant SRV as update.truenas.com (HTTPS)
  participant TI as truenas_install
  participant ZFS as boot-pool (ZFS)
  participant GRUB as GRUB
  UI->>MW: update.download (profile decides what is offered)
  MW->>SRV: GET train manifest (JSON)
  SRV-->>MW: version, filesize, sha256
  MW->>SRV: GET .update file
  MW->>MW: sha256(file) == manifest.checksum ? (download.py L72-84)
  MW->>MW: mount outer squashfs; per-file sha1/sha256 vs manifest.json (install.py L24-62)
  Note over MW: no MANIFEST.sig check found [C-TD-truenas-scale-008]
  MW->>TI: precheck, then install {old_root:/, pool}
  TI->>ZFS: create ROOT/<version>; clone data/home/var-log from snapshots
  TI->>ZFS: unsquashfs rootfs; set RO datasets; @pristine
  TI->>ZFS: zpool set bootfs=ROOT/<version>; update-grub
  alt install error
    TI->>ZFS: restore old bootfs; zfs destroy -r new BE
  end
  MW-->>UI: reboot
  GRUB->>ZFS: boot bootfs
  Note over GRUB,ZFS: no boot counter / health gate; a failed boot needs a human
  UI->>MW: boot.environment.activate <older BE> (manual rollback)
  MW->>ZFS: zectl activate; reboot
```

## 4. Claims vs code (condensed)

| Vendor / docs claim | Code at the pin | Verdict |
|---|---|---|
| Rollback lets "the system … revert to a previously used version with a single reboot" (25.10 update blog) | `boot.environment.activate` → `zectl activate` (`environments.py#L132-L145`) | **Agrees**, but a person has to choose it. There is no automatic revert [C-TD-truenas-scale-011] |
| The update image is signed (scale-build signs a `MANIFEST`) | Signing is optional at build time (`update.py#L70-L71`). The 25.10.8 update client checks only checksums (`install.py#L34-L41`; `download.py#L72-L84`) [C-TD-truenas-scale-007, C-TD-truenas-scale-008] | **Partly contradicts.** Signatures are produced, but the client was not found checking them |
| "The TrueNAS Apps catalog will migrate to Docker Compose without requiring users to take any manual actions" (2024 announcement) | The migration rejects any release "not from TrueNAS catalog" (`list_utils.py#L52-L53`) [C-TD-truenas-scale-018] | **Partly contradicts** for third-party catalog users |
| "TrueNAS CE … the source code remains open" (2026 blog) | The source repos are open, but the build system "has been moved to an internal infrastructure" (`README.md#L1-L9`) [C-TD-truenas-scale-026, C-TD-truenas-scale-036] | **Agrees for source, weaker for reproducible builds** |
| Apps are portable Compose | Catalog apps are Jinja templates over a TrueNAS-only render library. Custom apps are plain Compose [C-TD-truenas-scale-020, C-TD-truenas-scale-023] | **Mixed.** Plain Compose goes *in*. Catalog apps don't come *out* unchanged |

## 5. Real-world failure signals

| Report | What happened | Lesson for OneMind |
|---|---|---|
| k3s idle CPU on 24.04, 2024 [C-TD-truenas-scale-019] | k3s-server used about 10% of a core at idle. Staff said upgrading k3s in a point release was "very risky", so the fix waited for a major release. | Kubernetes minors must be upgradeable **inside** a OneMind point release, with automated, snapshot-gated steps (risk 8 in 00). |
| k3s SQLite corruption, 2024 [C-W5-052] | "database disk image is malformed" on a single box. | Integrity-check datastore copies (already in 06). |
| 24.10 app migration [C-TD-truenas-scale-018] | Third-party catalog apps were not migrated. | Keep one app manifest that compiles to more than one runtime (01's portability guard). |
| 26 legacy-VM removal [C-TD-truenas-scale-031] | VMs made on 25.04's "Instances" screen are dropped with **no migration tool**. | Never ship a feature as "experimental" without an exit path, and give every deprecation an automated migration. |
| 26 2FA reset [C-TD-truenas-scale-030] | 2FA secrets with non-standard intervals are cleared on upgrade. | Upgrade migrations for identity data need tests and a pre-update warning. |

## 6. What competitors do (constraint-fit)

| Product | Base / image | Update + rollback | App runtime | Constraints | Constraint fit with OneMind |
|---|---|---|---|---|---|
| **TrueNAS 25.10** | Debian 12, own kernel, nested squashfs [C-TD-truenas-scale-003, C-TD-truenas-scale-007] | ZFS boot environments, N copies; manual rollback; checksum-only [C-TD-truenas-scale-009, C-TD-truenas-scale-011, C-TD-truenas-scale-008] | Docker Compose (left k3s in 24.10) [C-DEC-007] | Funded company; x86 NAS appliance; single node (HA on Enterprise hardware); no robotics | **Medium for a storage/Pro x86 profile; low for Pi/Jetson/robots** |
| Home Assistant OS | Buildroot (see `home-assistant-os.md`) | RAUC A/B; commits too early [C-W3-025] | Docker via Supervisor | Funded; Pi + x86; single node | High for small boxes |
| umbrelOS 2.x | Debian trixie + Rugix (see `umbrelos.md`) | A/B; commit at daemon start [C-W3-036] | Docker Compose | Small team; x86 + Pi; single node | High for the home tier |
| Olares | Ubuntu/Debian host + k3s (see `olares.md`) | Script-based upgrade | k3s + Helm (OAC) | Funded; x86 + GPU; multi-node | High for the GPU/cluster tier |
| **OneMind (01)** | Debian 13 image; Jetson on L4T | Signed RAUC A/B + fresh-signal health gate | k3s on ≥ 4 GB + SSD; NATS leaves below | Solo founder; Pi → GPU cluster; robotics | — |

## 7. Strengths and weaknesses

**Strengths:**
- It has a decade of production use.
- **ZFS boot environments** keep many versions (not just two slots) and roll back atomically [C-TD-truenas-scale-009].
- `/usr` is read-only and apt is disabled, so the image stays the single source of truth [C-TD-truenas-scale-010, C-TD-truenas-scale-012].
- The Debian mirror is frozen per release, so builds are reproducible [C-TD-truenas-scale-003].
- The NVIDIA driver is a sysext, so the GPU stack is decoupled from the base [C-TD-truenas-scale-013].
- Data is snapshotted before every app upgrade [C-TD-truenas-scale-022].
- RBAC sits under every API method [C-TD-truenas-scale-030].
- Update profiles are tied to an automated status page [C-TD-truenas-scale-038].
- The app catalog is large, with digest-pinned images [C-TD-truenas-scale-020, C-TD-truenas-scale-024].
- The open-core-plus-SaaS bridge (Connect) has a clear free tier [C-TD-truenas-scale-037].

**Weaknesses:**
- No signature verification was found in the update client [C-TD-truenas-scale-008].
- There is no automatic health-gated rollback [C-TD-truenas-scale-011].
- It is x86-only [C-TD-truenas-scale-015], with no host Secure Boot [C-TD-truenas-scale-033].
- Security hardening (STIG/FIPS) is paywalled [C-TD-truenas-scale-032].
- The build system is now internal [C-TD-truenas-scale-026].
- It has broken things across majors (the k3s exit, legacy VMs, 2FA) [C-TD-truenas-scale-018, C-TD-truenas-scale-030, C-TD-truenas-scale-031].
- Upgrades must go major by major [C-TD-truenas-scale-016].
- Development is concentrated: about 12 accounts made about 1,445 middleware commits in a year [C-TD-truenas-scale-027].

## 8. What OneMind copies and what it does better

| # | Pattern | Copy or improve | Requirement IDs |
|---|---|---|---|
| REQ-TN-1 | **Freeze a per-release Debian mirror snapshot** and build every image from it (iX's `apt.sys.truenas.net/<release>/…`) [C-TD-truenas-scale-003] | Copy (pattern; use debian snapshot / aptly) | R-3, M-6, RS-2 |
| REQ-TN-2 | **Read-only `/usr`, disabled apt, sysext for optional stacks** (NVIDIA, dev tools) [C-TD-truenas-scale-010, C-TD-truenas-scale-012, C-TD-truenas-scale-013] | Copy. The GPU driver ships as a signed sysext so the core image stays vendor-neutral | N-8, R-1, F-8 |
| REQ-TN-3 | **Snapshot app data before every app upgrade; one-click app rollback** [C-TD-truenas-scale-022] | Copy, and improve: auto-roll back when the app's health check fails after upgrade | R-1, A-1, A-2 |
| REQ-TN-4 | **Accept plain Compose as a "custom app"**, and keep the catalog format as a thin layer over a portable runtime [C-TD-truenas-scale-023, C-TD-truenas-scale-018] | Copy and improve: `onemind.app.yaml` compiles to Helm *and* Compose, so a runtime change never strands apps | A-1, A-2, A-3, N-9 |
| REQ-TN-5 | **Update profiles tied to a status page** [C-TD-truenas-scale-038] | Copy as release channels, but CRA-compliant: the security channel auto-installs by default (01 §8) | R-1, R-2 |
| REQ-TN-6 | **RBAC on every API method; MCP server with read-only mode, confirmations and redaction** [C-TD-truenas-scale-030, C-TD-truenas-scale-034] | Copy the shape, and improve: enforce approvals at the gateway (01 Security), with MCP built in, not a side preview | AI-1, AI-3, AI-5, M-2 |
| REQ-TN-7 | **Config backup that includes the secret seed** [C-TD-truenas-scale-029] | Improve: OneMind's restic recovery keys (06) wrap the seed, so a restore never silently drops secrets | R-1, UX-6, M-2 |
| REQ-TN-8 | **Signed updates verified on the device** | **Do better:** verity-signed RAUC bundles checked on the device from release 1 (01), instead of relying on HTTPS checksums [C-TD-truenas-scale-008] | R-1, R-3 |
| REQ-TN-9 | **Automatic health-gated rollback** | **Do better:** a boot counter plus a fresh-signal gate (01), instead of manual BE activation [C-TD-truenas-scale-011] | R-1, P-7 |
| REQ-TN-10 | **Keep the image build public** and reproducible | **Do better:** OneMind's pipeline stays in the open repo (D-001), unlike iX's move to internal builds [C-TD-truenas-scale-026] | D-001, A-6, RS-2 |
| REQ-TN-11 | **Security baseline in the free edition** | **Do better:** Secure Boot path, LUKS and hardening are not paywalled; only certification support is paid [C-TD-truenas-scale-032, C-TD-truenas-scale-033] | M-2, M-8 |
| REQ-TN-12 | **Every deprecation ships with an automated migration and a pre-update warning** | Lesson from [C-TD-truenas-scale-031, C-TD-truenas-scale-030, C-TD-truenas-scale-018] | R-1, R-3, M-8 |
| REQ-TN-13 | **Optional x86 "Storage/Pro" profile on ZFS** (multi-version boot environments for the data box) | Candidate only. Evaluate in year 2 (see §9) | H-2, H-3, UX-6, F-14 |

## 9. Does TrueNAS challenge OneMind's Tier A decisions (01)?

| Tier A decision | What TrueNAS shows | Effect |
|---|---|---|
| **Debian 13 core** | A funded appliance vendor ran Debian 12 through 25.10 and moves to **trixie** for its next major [C-TD-truenas-scale-003, C-TD-truenas-scale-004]. A whole-image update carries the Debian major jump, and users don't reinstall (the 25.10 → 27 update path is "anticipated") [C-TD-truenas-scale-016]. | **Supports.** It also partly answers ADR risk 3 (rebase without reflash). But TrueNAS writes each version into a new ZFS dataset, which has **no fixed slot size**. RAUC's fixed A/B slots still need the slot-size headroom 01 sets. |
| **RAUC A/B** | ZFS boot environments are a proven alternative: N versions, atomic, and no slot-size limit [C-TD-truenas-scale-009]. | **Mild challenge, not a flip.** BEs need ZFS root, which is out-of-tree and kernel-coupled. TrueNAS builds its own kernel to keep ZFS in step [C-TD-truenas-scale-005], which 01 rejected for the core (K1). And ZFS root is not the norm on Pi 5 or Jetson. Keep RAUC. Record ZFS boot environments as the candidate for a year-2 x86 storage profile (REQ-TN-13). TrueNAS also has **no automatic rollback**, so it does not weaken the case for RAUC's boot-count gate. |
| **k3s on ≥ 4 GB + SSD nodes, NATS leaves below** | iX ran k3s on single NAS boxes and left. It cited complexity, portability and user preference [C-TD-truenas-scale-017, C-DEC-007]. Staff could not ship a k3s fix in a point release [C-TD-truenas-scale-019]. | **Already counted in 01 (refuter W4-P0-1, C-DEC-007).** This teardown adds two points. (a) The migration stranded third-party catalog apps [C-TD-truenas-scale-018], which strengthens 01's portability guard (REQ-TN-4). (b) The fix-in-point-release problem confirms that OneMind must be able to ship k3s minors inside point releases. **No flip:** OneMind's multi-node, GPU and robotics needs (N-7, N-8, F-14) are unlike a single-box NAS. Docker/Compose stays as the leaf-node / runtime fallback that the guard keeps possible. |
| **restic + online SQLite backup** | TrueNAS's own cloud backup product is built on restic [C-TD-truenas-scale-028]. | **Supports.** |
| **Own kernel route (01 keeps K1: board maintainer's kernel)** | TrueNAS owns its kernel (an LTS fork with its own config) and **still has no host Secure Boot** [C-TD-truenas-scale-005, C-TD-truenas-scale-033]. | **Supports K1.** Owning a kernel means owning shim/MOK signing too, which is extra work for a solo developer. |
| **Security baseline, CRA auto-updates** | TrueNAS only *notifies*. Installing an update is manual. Hardening is paywalled [C-TD-truenas-scale-038, C-TD-truenas-scale-032]. | **No challenge.** It is a contrast case for OneMind's CRA "auto by default" decision, which is still a founder decision in 26. |
| **bootc Industrial profile, Jetson on L4T** | Not addressed by TrueNAS (x86 only) [C-TD-truenas-scale-015]. | No effect. |

**Net:** no Tier A decision flips. One addition is proposed for 01 §12 or the backlog: **REQ-TN-13**, a year-2 candidate. It covers ZFS boot environments for an x86 storage/Pro box, to be judged against the slot-sizing risk on that SKU only.

## 10. Re-check triggers

- iX publishes a signed-update verification step in the middleware (a search for `MANIFEST.sig` or `gpg` in `plugins/update_`). If so, change REQ-TN-8 from "do better" to "parity".
- The TrueNAS 27 GA build system becomes public again, or an ARM or Secure Boot image ships.
- The TrueNAS MCP server leaves research preview, or AI features move into the OS.
- TrueNAS Connect Business tier pricing or the LTS terms are published.
- Recheck the kernel and NVIDIA facts by 2027-05-11, and the lifecycle and pricing facts by 2027-11-11.

## Glossary

| Term | Meaning |
|---|---|
| **Boot environment (BE)** | A complete, bootable copy of the OS stored as a ZFS dataset. You can keep many copies and boot any of them. |
| **ZFS / OpenZFS** | A filesystem and volume manager with snapshots, checksums and replication. Its licence keeps it outside the Linux kernel tree. |
| **squashfs** | A compressed, read-only filesystem image, used here as the update file. |
| **systemd-sysext** | A way to overlay extra files onto a read-only `/usr` at runtime, used for optional stacks like GPU drivers. |
| **zectl** | A tool that manages ZFS boot environments (create, activate, destroy). |
| **Update profile / train** | A release channel. It decides which versions the UI offers you. |
| **Open core** | The base product is free and open source. Some features are sold. |
| **STIG / FIPS 140** | US government hardening checklists and validated cryptography, needed by many public-sector buyers. |
| **MCP** | Model Context Protocol, a standard way for AI assistants to call tools on a system. |
| **Secure Boot / shim** | Firmware checks that only signed bootloaders and kernels run. "shim" is the small Microsoft-signed loader Linux distributions use to chain to their own keys. |
