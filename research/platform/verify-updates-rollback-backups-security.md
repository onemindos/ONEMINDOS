# Verification: Updates, Rollback, Backups, Security (appliance OS research)

Date: 2026-11-10. Method: every claim below comes from a primary source opened in this session, either a GitHub file read with `gh api repos/OWNER/REPO/contents/PATH` (file paths quoted) or an official docs page fetched with WebFetch. Anything not opened is marked **UNVERIFIED**.

Evidence-quality notes:
- "GH file" means the raw file was read via `gh api` (strongest). "Page (summarised)" means the official page was fetched through WebFetch, which returns a model summary of the page, so quotes are paraphrase-grade. Re-open the page before quoting it externally.
- Versions and dates were taken from the GitHub API (`releases/latest`, `pushed_at`) on 2026-11-10.

---

## 1. Home Assistant OS (HAOS)

Latest release: 18.5 (published 2026-11-06). Repo `home-assistant/operating-system`, license Apache-2.0 (GitHub API `license.spdx_id`).

**Base and contents.** Built with Buildroot, one image per board, not a Debian/Ubuntu derivative. Bootloader: GRUB on UEFI (x86-64, generic Arm, VMs), U-Boot on most SBCs, the firmware's own tryboot on Raspberry Pi 5. Root FS is EROFS, read-only and compressed. systemd, NetworkManager, Docker engine runs the Supervisor. AppArmor kernel security module with profiles for the Supervisor and apps. ZRAM for `/var` and `/tmp`. Source: GH file `src/content/docs/os/operating-system/index.md` in `home-assistant/contributors.home-assistant.io` (the old developers.home-assistant.io/docs/operating-system/ URL 301-redirects to contributors.home-assistant.io/os/operating-system/).

**Repo layout.** `buildroot-external/` (configs, board, kernel, package, rootfs-overlay, genimage, ota, meta), `buildroot/` (submodule to the home-assistant/buildroot fork), `scripts/`, `tests/` (boot the image in QEMU). OTA files verified present: `buildroot-external/ota/system.conf.gtpl`, `manifest.raucm.gtpl`, `rauc-hook`, `rel-ca.pem`, `dev-ca.pem`, `provisioning-ca.pem`, `rel-ca-xsign-oldroot.cert.pem`.

**Partition layout** (GH file `.../os/operating-system/partitions.md`), GPT where possible, hybrid/MBR on boards that need it:

| Label | Size | Content |
|---|---|---|
| `hassos-boot` | 16 to 64 MB | FAT, bootloader files, `cmdline.txt`; not A/B, updated in place |
| `hassos-kernel0` / `hassos-kernel1` | 24 MB each | kernel of slot A / B |
| `hassos-system0` / `hassos-system1` | 256 MB each | EROFS rootfs of slot A / B |
| `hassos-bootstate` | 8 MB | U-Boot env (U-Boot boards) |
| `hassos-overlay` | 96 MB | ext4, persistent host settings (network, hostname, SSH keys) |
| `hassos-data` | rest of disk | ext4: Docker storage, Supervisor data, journal, swap; grown at first boot by `haos-expand` |

Sizes set in `buildroot-external/scripts/hdd-image.sh` plus board metadata; layouts in `buildroot-external/genimage/`. Data disk can be moved to another disk (copy via `e2image`, old partition relabelled `hassos-data-old`; failed copy keeps the old one).

**RAUC A/B flow** (GH file `.../os/operating-system/update-system.md`; `buildroot-external/ota/system.conf.gtpl`):
1. Supervisor downloads the `.raucb` bundle, asks RAUC over D-Bus to install it.
2. RAUC writes the inactive slot and tells the bootloader to try it next.
3. Supervisor reports `version_pending` and raises a repair issue "reboot needed". It does not reboot by itself.
4. User reboots; the new slot boots.
5. Once the Supervisor has started, it marks the booted slot good.
- Bundle format `verity` (`manifest.raucm.gtpl`: `[bundle] format=verity`), `compatible=haos-<board id>` so a bundle only installs on its own board. `install-check` hook in `ota/rauc-hook` rejects mismatched compatible (exit 10).
- RAUC `system.conf.gtpl`: `statusfile=/mnt/boot/rauc.db`, slots by partlabel, `kernel.0`/`rootfs.0` bootname A, `kernel.1`/`rootfs.1` bootname B; custom backend `/usr/lib/rauc/rpi-tryboot.sh` for Pi 5.
- Pi 5 caveat: must reboot with `systemctl reboot` (tryboot needs the reboot parameter); plain `reboot` starts the old slot.

**Rollback trigger.** After an update the bootloader tries the new slot a limited number of times (three on GRUB). If never marked good, it falls back to the other slot. GRUB state in `EFI/BOOT/grubenv`; U-Boot state on `hassos-bootstate`; Pi 5 via tryboot. Manual switch: `ha os boot-slot A|B` (persists until changed or next update); GRUB menu also lets you pick a slot, and has a rescue shell entry per slot. Key point for design: "good" = Supervisor started, not "all apps healthy" (per update-system.md and index.md boot sequence).

**Signing and verification.** RAUC checks bundle signature against `/etc/rauc/keyring.pem` before installing. HA runs its own PKI (development CA and release CA). Production/staging images trust the release CA; development images trust dev+release; self-built images additionally trust the builder's `cert.pem`. Public builds are signed by the release chain. Not locked down: root on the host can add a cert to the keyring for the current boot (documented in update-system.md).

**Channels.** GH file `.../os/operating-system/releases.md`: deployment `staging` = beta channel (release candidates), `production` = stable; build pipeline refuses to publish if deployment, version format and channel disagree. Supervisor checks `version.home-assistant.io/stable.json` for the latest OS version of the user's channel.

**Update UX** (GH file `home-assistant.io` `source/common-tasks/os.markdown`): user selects the OS update in Settings, or runs `ha os update [--version X]`; option "Automatic backup before update" / "Create manual backup before update"; Check for updates; "Join beta" in System > Updates. OS update needs a user reboot (step 4 above). I did not find a documented auto-install of OS updates (not exhaustive search, treat as UNVERIFIED that none exists).

**Backups** (GH file `home-assistant.io` `source/common-tasks/general/backups.markdown`, `source/_integrations/backup.markdown`):
- "Backups are encrypted by default and stored in a compressed archive file (.tar)". On HAOS stored in `/backup`; Container install: `backups` folder under config dir.
- Contents selectable on HAOS: HA settings (config + ssl; always included in automatic backups), history, media, share, local apps folder, apps (all/none/selected). "Full" = everything (optionally minus history); "partial" = chosen parts (actions `hassio.backup_full`, `hassio.backup_partial`).
- Excluded: logs, caches, tmp, nested backups; external databases (MariaDB/Postgres on another host) are not included; DB run as an app is included with the app.
- Automatic schedule: "Recommended" = daily, everything except media/share/local apps, keep last 3, stored locally and on HA Cloud if logged in. Custom schedule and retention available. Event entity `event.backup_automatic_backup` reports completed/in_progress/failed with failure reasons.
- Locations ("backup agents"): local, network storage (NAS), Google Drive, OneDrive, Synology DSM, HA Cloud (max 5 GB, stores only the latest backup, always encrypted). Docs: "recommended to keep a copy on another system ... and ideally also one off-site".
- Pre-update app backups: kept per app, default 1; not pruned by automatic retention.
- Encryption: SecureTar v3 from release 2026.4 (announcement 2026-03-26, GH file `source/_posts/2026-03-26-modernizing-encryption-of-home-assistant-backups.markdown`): Argon2id KDF, libsodium secretstream (XChaCha20-Poly1305), audited by Trail of Bits, old backups remain readable. Older v1/v2 used AES-128 with simple KDF. User must store the "emergency kit" with the encryption key.
- 3-2-1: HA blog `source/_posts/2025-01-03-3-2-1-backup.markdown` endorses the 3-2-1 rule, one off-site, encrypted backups.

**Security posture facts** (opened): read-only EROFS root; AppArmor profiles; no SSH by default. Dropbear SSH on port 22222 only runs when root has at least one authorized key, no password login, keys imported from a `CONFIG` USB drive (`debugging.md`). Local console gives HA CLI; `login` gives host root; serial console root login without a password exists on boards with serial consoles (documented in `debugging.md`). Journal persists on the data partition.
- **UNVERIFIED / not found:** UEFI Secure Boot, TPM unlock, or disk encryption in HAOS. A code search for "secure boot" in `home-assistant/operating-system` returned only unrelated board-package files; I did not find evidence of it, and I did not read a page that says it is absent.

---

## 2. umbrelOS (Umbrel)

Latest release: 2.0.1 (published 2026-11-01). Repo `getumbrel/umbrel`, license: **PolyForm Noncommercial License 1.0.0** (GH file `LICENSE.md`; API reports NOASSERTION). Not usable as-is in a commercial product; read the License FAQ before borrowing code. **UNVERIFIED:** whether OneMind's use would qualify; ask Umbrel / counsel.

**OS build.** `packages/os/` holds `rugix/` (Rugix Bakery project: `rugix-bakery.toml`, `recipes/`, `layers/`, `run-bakery`), `rugpi-image`, `mender.cfg` (legacy), `overlay/`, `overlay-pi/`, `umbrelos.Dockerfile`, `usb-installer/`. Debian trixie base with backports kernel on amd64/generic arm64 (README in `packages/os/README.md`). Targets: `umbrelos-amd64`, `umbrelos-arm64`, `umbrelos-pi` (Pi 4 and 5; Pi 4 image includes a firmware update to enable tryboot, README says "the image for Raspberry Pi 4 includes a firmware update to enable the `tryboot` mechanism ... Otherwise, the image is identical to the image for Raspberry Pi 5"). Legacy Mender-provisioned amd64 devices use `umbrelos-mender-amd64` with Rugix in Mender-compatible GRUB mode and a state migration hook.
- Layout (`rugix-bakery.toml`): GPT with config (FAT32 256M, ESP type), boot (ext4 512 MiB), system partition (ext4, 8 GiB; slot sizes referenced up to 10 GiB in `recipes/setup-rugix/files/bootstrapping.toml`, 5 GiB on Pi) and a data partition (Mender-era notes: 512 MB initial, expanded at first boot). Only the system slots are A/B; data is Rugix-managed state.
- **No Secure Boot:** README states DKMS modules are left unsigned, "umbrelOS doesn't use Secure Boot".

**Update signing and verification** (GH files `packages/umbreld/source/modules/update/update.ts`, `release-signing.ts`, `signing-keys.ts`, `install-release.ts`, `rugix.ts`):
- Update server `https://api.umbrel.com/latest-release` (query: version, device, platform, channel, bootFlow, arch) only says where the release is. What is shown and installed comes from the release's signed manifest.
- Release = `manifest.txt`, `manifest.txt.sig`, `release-notes.md`, `release-notes.md.sig` in a download directory (e.g. `download.umbrel.com/release/2.1.0/`). Manifest pins a hash of every file, including the Rugix bundle hash.
- Trust chain: an **offline root key on a hardware wallet** signs an "approved signing keys" list; each release signer holds a P-256 key created in a Mac Secure Enclave (Touch ID to sign). The list sets how many approved signers a release needs (`requiredSignatures`), can revoke signed releases by manifest hash, and revocation works by publishing a newer root-signed list. Devices fetch the list daily and before every update from api.umbrel.com and `raw.githubusercontent.com/getumbrel/umbrel/master/releases/umbrelos-signing-keys.txt`, take the newest valid one, never accept an older one. A device with no reachable source keeps trusting the newest list it has seen (lists do not expire). Manifest is timestamped with OpenTimestamps.
- Install: `rugix-ctrl update install --reboot set --bundle-hash <hash from signed manifest> <url>`; Rugix checks the hash while streaming, before writing to system partitions. Comment in `rugix.ts` warns never to sign a bundle with a script payload (Rugix pipes it to bash before checking its hash) or an incremental bundle.
- Anti-rollback: `install()` throws unless the server's release is newer (`semver.gt`) than the installed one, unless a releaseUrl is given explicitly (test builds). The UI-supplied `manifestHash` must match, so the server can't swap releases between "check" and "install".
- Optional signed per-release update script, pinned by manifest hash, run as root before the bundle installs.

**Rollback.** Support page (https://umbrel.com/support/basics/updating-umbrelos, updated 2026-10-02, page summarised): "If an update fails, your Umbrel automatically rolls back to the previous version," no data or settings lost. Mechanism is Rugix A/B boot-flow. Rugix does not auto-mark good (see section 4); how umbreld commits is **UNVERIFIED** (not read). ZFS pool compatibility is explicitly managed so rollback still imports pools: README says pools are created with `compatibility=openzfs-2.3` so a newer ZFS "doesn't enable features that would stop a pool importing after an OTA rollback"; existing pools are not upgraded automatically.

**Update UX.** Support page: updates over the air, "never installed automatically"; notification on the home screen plus Settings badge; user reviews notes and clicks Install now; manual check in Settings. Channels: `ReleaseChannel = 'stable' | 'beta'` stored in `settings.releaseChannel` (`update.ts`); beta via Settings > Advanced > umbrelOS beta program (search result for https://umbrel.com/support/basics/joining-the-beta-program; page itself not opened, **UNVERIFIED**). tRPC routes: `updateStatus`, `checkUpdate`, `update`, `getReleaseChannel`, `setReleaseChannel` (`routes.ts`). No user-defined schedule found.

**Backups (2.0)** (https://umbrel.com/support/backups-and-recovery/backing-up-your-data, updated 2026-10-02, summarised): backs up entire Umbrel (account, settings, files, apps, data) to another Umbrel, a NAS or an external USB drive; "Umbrel Private Cloud" listed as coming soon. Encrypted with a password set at setup, cannot be recovered. Hourly automatic backups; retention hourly 24 h, daily 1 week, weekly 1 month, monthly 1 year; older removed. Multiple locations allowed, each with own schedule; exclusions of files/folders/apps apply to all; destination needs at least 2x free space; Tailscale recommended between Umbrels. Rewind recovers individual files. Offsite: only if you point it at a remote Umbrel/NAS; no managed cloud yet. A community thread reports a 100 GB SMB restore hanging during onboarding (single user report, **UNVERIFIED**; https://community.umbrel.com/t/smb-network-backup-restore-fails-infinite-loading-in-onboarding/25506, not opened).

**FailSafe** (https://umbrel.com/support/storage/managing-your-storage, updated 2026-11-10, summarised): FailSafe = ZFS RAIDZ1 on SSDs, mirrored pairs on HDDs; survives a single drive failure; page says it is **not a backup**. Needs 2+ internal NVMe/SATA slots; Storage Manager not available on Raspberry Pi; SAS/USB/hardware-RAID drives not in main storage.

**Security model facts opened:** signed releases with offline root + hardware-key signers, revocation, anti-downgrade, hash-pinned bundles; no Secure Boot; no TPM use found (not searched exhaustively, **UNVERIFIED**). App sandboxing model: **UNVERIFIED** (not read).

---

## 3. Kairos

Latest release v4.4.0 (published 2026-10-26). Repos `kairos-io/kairos`, `kairos-agent`, `AuroraBoot`: Apache-2.0 (GitHub API). Docs source: `kairos-io/kairos-docs`, `docs/`.

**Architecture** (`docs/architecture/immutable.md`): root `/` immutable, `/etc` `/var` `/srv` ephemeral, `/usr/local` persistent (label `COS_PERSISTENT`), `/oem` persistent (`COS_OEM`), many paths bind-mounted onto the persistent partition (e.g. `/var/lib/rancher`, `/var/lib/longhorn`, `/var/lib/kubelet`, `/etc/rancher`, `/var/log`, `/home`, `/etc/ssh`). Partitions after install: **state** (stores active and passive images as `.img`, loopback-mounted), **recovery** (images in `.squashfs`), optional OEM, persistent. Fallback order "A -> B -> Recovery". Upgrade is built in a transition image and only swapped in after all steps complete; new image becomes active, old becomes passive.

**Upgrade methods** (`docs/upgrade/manual.md`): `kairos-agent upgrade --source oci:<repo/image:tag>` (also `ocifile:`, `dir:`, `file:`); `kairos-agent upgrade list-releases` (default registry quay.io/kairos); recovery upgraded separately with `--recovery` and "only upgrade the recovery system when you are sure the active system is running correctly". Kubernetes: **system-upgrade-controller is deprecated** (`docs/upgrade/system-upgrade-controller.md`), replaced by the Kairos operator: `NodeOpUpgrade` CR (`operator-docs/nodeop-upgrade.md`) with `image`, `concurrency`, `stopOnFailure`, canary deployments, `rebootOnSuccess` (`operator-docs/nodeop.md`). Each `NodeOpUpgrade` is a single one-shot run; GitOps users bump the CR name per version. AuroraBoot builds installable ISOs/raw images and, for Trusted Boot, generates keys and signed UKIs (`docs/architecture/trustedboot.md`).

**Rollback** (`docs/upgrade/boot_assessment.md`):
- Standard (GRUB) installs: kernel `panic=5` reboot, `systemd.crash_reboot=yes`, GRUB env vars + sentinel files detect a failed boot after upgrade and set the fallback entry as default, so a failed boot returns to the previous version automatically. A boot counts as successful once Kairos has mounted the active image and cloud-init reaches the `boot.before` stage. It does **not** wait for your workload or Kubernetes; a booted-but-broken app will not roll back. "Automatic rollback is a GRUB-only feature."
- Manual: `kairos-agent bootentry --select fallback` then reboot; selection lasts one boot only. Documented bug: with encrypted OEM on GRUB the selection may silently fail (issue kairos-io/kairos#5273).
- Trusted Boot installs: `boot_assessment.md` says systemd boot assessment "not yet implemented" (tracking issue kairos-io/kairos#2864), but `docs/examples/boot_assessment_trusted_boot.md` says boot entries are marked good at `multi-user.target`, with 3 retries then passive then recovery then autorecovery. **The two pages disagree; verify in code or a test VM before relying on either.**

**Trusted Boot** (`docs/architecture/trustedboot.md`): FDE + Secure Boot + Measured Boot. UKI/USI generated from container images, signed with your Secure Boot keys, user data encrypted under PCR policy. systemd-boot loads the UKI directly. In trusted-boot mode `/oem` and `/usr/local` are encrypted, `/usr` read-only. Kernel command line is part of the signed artifact, so it cannot be changed after install. On upgrade the new image must be signed with the same keys, and the certificate must be enrolled in the firmware DB (`boot_assessment.md`, last section). Revocation doc: `docs/advanced/revoking-secureboot-access.md` (exists, not read).

**Disk encryption** (`docs/advanced/partition_encryption.md`): LUKS on partitions listed in `install.encrypted_partitions` (usually `COS_PERSISTENT`); offline mode (key in TPM NV) or online mode with an external KMS (kcrypt challenger). Requires TPM 2.0. Outside Trusted Boot, `COS_OEM` (cloud-config, possibly join tokens) stays in plain text; docs warn about secrets there.

**Hardware.** `docs/installation/edge-devices/raspberry.md`: supports Raspberry Pi 3 and 4 (64-bit); **"Model 5 is currently not supported because of how we use U-boot"**. Jetson: `docs/installation/edge-devices/nvidia-jetson-images.md` (dated 2026-07-17) supports AGX Orin, Orin NX, AGX Thor via `kairos-init --model`; separate DGX Spark page exists. Generic x86/arm64 via `kairos-init --model generic`.

**User-controlled timing.** No built-in time-window/cron scheduler found in the operator docs I grepped (`nodeop.md`, `index.md`, `kairos-operator.md`); the operator model is "you create the upgrade CR when you want it", with concurrency and stop-on-failure. **UNVERIFIED** whether any scheduling feature exists elsewhere.

---

## 4. Rugix

Repo `silitics/rugix` (now also referenced as `rugix/rugix`), latest v1.4.0 (published 2026-11-02). License: dual **MIT or Apache-2.0** (files `LICENSE-MIT`, `LICENSE-APACHE`; rugix-bakery README says "licensed under either MIT or Apache 2.0 at your option"). The README says it is "fully open-source and permissively licensed, including features such as delta updates".

Features (GH file `README.md`): Rugix Ctrl = on-device updates and state management; Bakery = image builder (Debian, Alpine, Raspberry Pi OS); Admin = browser UI. Atomic A/B updates with automatic rollback on failure; static and dynamic (HTTP range) delta updates; "cryptographic verification before installing anything anywhere"; compatibility checks; application workload updates with rollback; supported strategies: symmetric A/B, asymmetric with recovery, incremental. CHANGELOG: "Make signatures mandatory unless opted out", CMS signatures, multiple configured certificate roots, HTTPS roots now taken from the OS trust store.
Boot flows (https://rugix.org/docs/ctrl/updates/system-updates/boot-flows/, summarised): `grub`, `uboot`, `systemd-boot`, `custom`, compat flows (`rauc-uboot`, `rauc-grub`, `mender-uboot`, `mender-grub`), Raspberry Pi `rpi-tryboot` ("Raspberry Pi 4 and newer") and `rpi-uboot`. **Important:** "Rugix Ctrl does not mark boot groups good or bad automatically. An external mechanism must trigger this through `rugix-ctrl boot`" and default flows have no dead-man switch. So the health-gated commit is the integrator's job.
Boards: Pi 5 is covered in practice by Umbrel shipping `umbrelos-pi` on Pi 4/5 with tryboot (above). **Jetson: UNVERIFIED** (no Rugix page or repo file mentioning Jetson/Tegra was found; a repo tree grep for jetson/tegra returned nothing). The site page https://rugix.org/docs/ctrl/advanced/signed-updates returned 404, so details of the Rugix-native signing config were taken from the CHANGELOG and the `crates/libs/rugix-pki/src/{sign,verify}.rs` file names only.

---

## 5. Mender and RAUC

**RAUC** (`rauc/rauc`): license **LGPL-2.1**; latest v1.15.2 (2026-03-27). README: fail-safe and atomic (update may be interrupted at any point), compatibility check, atomic bootloader updates, **cryptographic signing/verification via OpenSSL x.509**, PKCS#11/HSM keys supported. Docs page lists symmetric (A/B) and asymmetric (recovery+normal) setups and bootloaders grub, barebox, u-boot, EFI (https://rauc.readthedocs.io/en/latest/, summarised). Verity bundles are used by HAOS (`format=verity` in `manifest.raucm.gtpl`). Used in production by HAOS.

**Mender** (`mendersoftware/mender`): client latest 5.2.0 (2026-10-23), README: "licensed under the Apache License, Version 2.0" (`LICENSE`: Copyright 2026 Northern.tech AS; GitHub API says NOASSERTION because of the text). A/B rootfs with automatic rollback on update failure; rollback "requires an integration with the boot loader and a partition layout" (meta-mender for Yocto). Delta updates, RBAC, mTLS are listed under the **commercial** hosted product. `mendersoftware/mender-server` license NOASSERTION, **UNVERIFIED** terms. Umbrel migrated from Mender to Rugix (README "Mender to Rugix Migration").

---

## 6. Olares

Latest 1.12.7 (2026-09-24). Repo `beclab/Olares`. **License is ambiguous:** GitHub API/README badge say AGPL-3.0 (`LICENSE`), but there is also `LICENSE.md` titled "Olares License" with a limitation clause: use or modify "only for your own internal business purposes or for non-commercial or personal use" (read from `LICENSE.md`). **Treat as not freely reusable commercially until clarified.** Built on Kubernetes (K3s, KubeSphere, JuiceFS, MinIO, Restic, Velero listed in README third-party list).

**Backup** (GH file `docs/manual/olares/settings/backup.md`): full + incremental backups of chosen directories ("Backup files") and the Wise app ("Backup applications", only Wise supported). Destinations: local path (USB/SMB/external disk recommended), Olares Space, AWS S3, Tencent COS. Schedule daily/weekly/monthly, snapshot time, **backup password**; first run full, then incremental; "Snapshot now" manual; restore from local path, Olares Space or cloud with the password. Engine: source of `framework/backup-server` imports a restic package (`olares.com/backups-sdk/pkg/restic`), plus `infrastructure/restic/`. Olares Space charges for storage/bandwidth beyond quota. Whole-cluster/app-data backup of arbitrary apps is not offered per the doc (Wise only).

**Update/rollback.** System upgrades are done in the LarePass phone app by an admin, options "Download only" or "Download and upgrade" with a restart (`docs/manual/olares/settings/update.md`). Release types: Stable (monthly), RC, Daily build (`docs/developer/install/versioning.md`). Per that doc, within-minor upgrades are supported; "Upgrades across minor versions ... automatic upgrades are not supported" (must uninstall then install; doc says a future major release plans seamless upgrades; the doc may be dated, **check against 1.12.x release notes**). `olares-cli upgrade precheck|viable|spec` exist (`docs/developer/install/cli/upgrade.md`). I found **no A/B OS image or OS rollback** in the docs I opened (`search` for rollback under `docs/manual` only matched `update-app-image.md`); treat as absent unless proven otherwise. `SECURITY.md`: only the latest version gets security updates; report to hi@olares.com.

---

## 7. Kubernetes app-data backup building blocks

| Tool | License | Notes (source) |
|---|---|---|
| Velero v1.18.4 (2026-09-28) | Apache-2.0 | File System Backup uses **Kopia**; object storage only; one repo per namespace; opt-in by pod annotation `backup.velero.io/backup-volumes` or opt-out; **hostPath not supported** (local volumes are); node agent runs as root; backs up live FS, less consistent than snapshots; **"Velero uses a static, common encryption key for all backup repositories it creates"**; FSB and CSI snapshots are mutually exclusive per volume; FSB support described as beta quality (https://velero.io/docs/main/file-system-backup/, summarised). Repo docs: `site/content/docs/main/{file-system-backup,csi,csi-snapshot-data-movement,backup-repository-configuration}.md` exist (not read). |
| k3s v1.37.2+k3s1 (2026-11-03) | Apache-2.0 | `k3s etcd-snapshot`: scheduled snapshots on by default, `0 */12 * * *`, 5 kept locally; S3-compatible replication/restore (`--etcd-s3*`); restore by `k3s server --cluster-reset --cluster-reset-restore-path`. Page is etcd-only; **UNVERIFIED** that it covers the single-node default SQLite datastore. Source: https://docs.k3s.io/cli/etcd-snapshot (summarised). |
| Longhorn v1.13.0 (2026-09-29) | Apache-2.0 | Backup targets: NFS, SMB/CIFS, Azure Blob, S3-compatible; S3 recommended; default backup target auto-created on install; multiple backupstores since v1.8.0. Encryption of backups not covered on the opened page (**UNVERIFIED**). Source: https://longhorn.io/docs/latest/snapshots-and-backups/backup-and-restore/set-backup-target/ (summarised). |
| restic v0.19.1 (2026-07-05) | BSD-2-Clause | AES-256-CTR + Poly1305-AES, scrypt KDF, content-addressed immutable repository files, content-defined chunking dedup (https://restic.readthedocs.io/en/stable/100_references.html, summarised). |
| Kopia | Apache-2.0 | (license from GitHub API only; features not read here) |
| borg | BSD-style (`LICENSE` header "Copyright (C) 2015-2026 The Borg Collective"; GitHub API NOASSERTION; clause count **UNVERIFIED**) | Features **UNVERIFIED** (not opened). |

**How the reference products handle app data and offsite:**
- HAOS: one built-in encrypted archive of config + apps + data; local, NAS, cloud-drive agents, HA Cloud (latest only, 5 GB); backup before update; 3-2-1 recommended in docs.
- Umbrel: whole-device encrypted backup to another Umbrel/NAS/USB, hourly with GFS-style retention; no managed offsite yet; FailSafe is explicitly not a backup.
- Olares: restic-based snapshots of selected directories and Wise to local/Olares Space/S3/COS; app-data restore for Wise only.

---

## 8. Security baseline sources

- **Secure Boot + measured boot + TPM unlock**: Kairos Trusted Boot (FDE + Secure Boot + Measured Boot, TPM 2.0 required for encryption) is the one fully documented stack among the compared products. Umbrel: no Secure Boot (README). HAOS: not found.
- **Raspberry Pi** (`raspberrypi/documentation`, `documentation/asciidoc/security/security-architecture.adoc`, branch `master`): secure boot chain starts in boot ROM, customer-generated RSA 2048 key pair, hash of public key stored in OTP; on BCM2712 (Pi 5 SoC) the customer key also signs the EEPROM bootloader; optional LUKS root FS encryption with a device-unique secret stored in OTP via the Secure Boot Provisioner; if verification fails the bootloader proceeds to the next boot method. This is OTP-bound, not TPM-bound; **no TPM on Pi is UNVERIFIED** (not stated in what I read).
- **Jetson** (https://docs.nvidia.com/jetson/archives/r36.4/DeveloperGuide/SD/Security/SecureBoot.html, summarised): BootROM root of trust, PKC key hash in write-once fuses (RSA 3K, ECDSA P-256/P-521 on Orin; key revocation for two of three keys; fusing irreversible), UEFI Secure Boot (PK/KEK/db), once enabled at flash time cannot be disabled without reflash. fTPM and disk-encryption pages not read: **UNVERIFIED**.
- **Read-only root, signed updates**: HAOS (EROFS + RAUC verity bundles + release PKI), Umbrel (Rugix hash-pinned bundle + root-signed signer list), Kairos (immutable + UKI signing).
- **k3s hardening** (https://docs.k3s.io/security/hardening-guide, summarised): `protect-kernel-defaults: true` with sysctl `vm.overcommit_memory=1`, `kernel.panic_on_oops=1` (`/etc/sysctl.d/90-kubelet.conf`); Pod Security Admission via `admission-control-config-file=/var/lib/rancher/k3s/server/psa.yaml` (restricted); network policies (controller ships, policies are the operator's job); `secrets-encryption: true`; audit policy `/var/lib/rancher/k3s/server/audit.yaml`. Secrets encryption (https://docs.k3s.io/security/secrets-encryption): default provider `aescbc`, `secretbox` selectable (needs April 2025+ releases), config at `/var/lib/rancher/k3s/server/cred/encryption-config.json`, rotation via `k3s secrets-encrypt`; cannot be enabled on a running server without restart.
- **CIS**: SUSE/Rancher K3s CIS self-assessment page is for CIS Kubernetes Benchmark v1.9 and K3s v1.27 to v1.29 (https://documentation.suse.com/cloudnative/k3s/latest/en/security/self-assessment-1.9.html, first 100k chars read). It is behind the current k3s (v1.37), so rerun any scanner yourself; the hardening guide itself references CIS 1.8 section 5 and a 2.0 self-assessment.
- **SBOM**: CISA describes an SBOM as "a nested inventory, a list of ingredients that make up software components" and links to VEX (https://www.cisa.gov/sbom, summarised). The page does not name SPDX or CycloneDX, so format choice is **UNVERIFIED** from CISA.
- **CVE tracking tooling** (Trivy, Grype, OSV): **UNVERIFIED**, not opened.
- **Regulation**: EU Cyber Resilience Act (https://digital-strategy.ec.europa.eu/en/policies/cyber-resilience-act, summarised): entered into force 2024-12-10; reporting of actively exploited vulnerabilities applies from 2026-09-11 (already in force today); main obligations apply from 2027-12-11. Page does not detail update/SBOM duties. If OneMind sells boxes into the EU it applies; legal read **UNVERIFIED**.
- **Automatic security-update cadence**: Observed practices only: Olares stable monthly; Umbrel and HA ship OS updates only on user action; Kairos upgrades are operator-initiated. No cited industry cadence standard; none claimed.

---

## 9. Comparison table

| | HAOS | umbrelOS | Kairos | Olares |
|---|---|---|---|---|
| Latest (2026-11-10) | 18.5 | 2.0.1 | v4.4.0 | 1.12.7 |
| License | Apache-2.0 | PolyForm Noncommercial 1.0.0 | Apache-2.0 | AGPL-3.0 badge plus restrictive "Olares License" (`LICENSE.md`) |
| Base / build | Buildroot | Debian (trixie) via Rugix Bakery | Any distro as OCI image (kairos-init) | Debian-based K8s distro on K3s (OS image details not read) |
| Updater | RAUC (verity bundle) | Rugix Ctrl | kairos-agent, OCI images | In-place via LarePass; olares-cli |
| A/B | yes, kernel+rootfs A/B, boot partition in place | yes (Rugix A/B) | active/passive + recovery | not documented |
| Boot loaders | GRUB, U-Boot, Pi 5 tryboot | GRUB, Pi tryboot | GRUB; systemd-boot for Trusted Boot | n/a |
| Rollback trigger | bootloader tries 3x (GRUB); good = Supervisor started | automatic on failed update (support page); commit mechanism UNVERIFIED | GRUB sentinels; good = cloud-init `boot.before`; trusted boot assessment docs conflict | none found |
| Manual rollback | `ha os boot-slot`, GRUB menu | UNVERIFIED | `kairos-agent bootentry --select fallback` (one boot) | none found |
| Update signing | RAUC x.509, release+dev CA, keyring `/etc/rauc/keyring.pem` | Offline root (hardware wallet) + Secure Enclave signers, hash-pinned bundle, revocation list | UKI signed with Secure Boot keys (trusted boot); OCI image signing UNVERIFIED | UNVERIFIED |
| Secure Boot / TPM | not found | no Secure Boot | yes (Trusted Boot, TPM 2.0) | UNVERIFIED |
| Root FS | EROFS read-only | ext4 slot (read-only status UNVERIFIED) | immutable, ephemeral /etc | UNVERIFIED |
| Pi 5 | yes (tryboot) | yes (tryboot) | **no** (docs) | UNVERIFIED |
| Jetson | UNVERIFIED | UNVERIFIED | yes (AGX Orin, Orin NX, Thor) | UNVERIFIED |
| Channels | stable / beta (staging) / dev | stable / beta | n/a (tags on quay.io) | Stable monthly / RC / daily |
| Update timing | user-triggered, reboot required | user-triggered, never automatic | operator-created CR, no scheduler found | admin in LarePass, download-only option |
| Backups | built-in encrypted tar, partial/full, multiple agents, HA Cloud (latest only), pre-update | whole-device encrypted, hourly GFS retention, to Umbrel/NAS/USB | none built in (bring Velero/Longhorn) | restic snapshots, local/S3/COS/Olares Space, app restore Wise only |
| Offsite | HA Cloud, cloud drives, NAS | another Umbrel via Tailscale, NAS | n/a | S3, COS, Olares Space |

Mender/RAUC/Rugix side-by-side:

| | RAUC | Mender client | Rugix Ctrl |
|---|---|---|---|
| License | LGPL-2.1 | Apache-2.0 (client); commercial add-ons hosted | MIT or Apache-2.0 |
| A/B | symmetric + asymmetric | A/B rootfs, needs bootloader integration | symmetric, asymmetric, incremental |
| Signing | x.509 via OpenSSL, PKCS#11/HSM | UNVERIFIED (not opened) | mandatory by default, CMS (CHANGELOG) |
| Delta | not stated on page | commercial | yes, open source |
| Auto-commit | integrator/bootloader | UNVERIFIED | no, external mechanism required |

---

## 10. Recommended OneMind update / backup / security design

Constraints: x86, Pi 5, Jetson, GPU boxes; k3s workload; founder priorities are backups, rollback, security, updates. Everything below is a recommendation, not a verified fact. Items depending on UNVERIFIED facts are flagged "validate".

### 10.1 OS image and update engine
1. **Immutable image with two system slots, persistent data separate** (HAOS partition pattern: boot, kernel/system A/B, overlay, data). Keep k3s data, containerd, PVs on the data partition. Source pattern: HAOS `partitions.md`.
2. **Updater: RAUC or Rugix Ctrl, not Mender hosted.** RAUC: proven by HAOS with verity bundles and Pi 5 tryboot custom backend (`ota/system.conf.gtpl`), LGPL-2.1 is fine for a separate system daemon. Rugix: MIT/Apache, delta updates, mandatory signatures, Pi 5 proven in Umbrel; but no auto-commit (you write it) and Jetson support is UNVERIFIED. Pick one after a Jetson spike (validate: bootloader flow for L4T UEFI A/B on Orin; Kairos shows Jetson images are buildable, but Kairos itself lacks Pi 5).
3. **Do not adopt Kairos as the base unless Pi 5 is dropped**: its docs say model 5 is unsupported. It is still the best reference for Trusted Boot (UKI + TPM PCR-bound LUKS) on x86 and for operator-driven upgrades.
4. **Health-gated commit, stricter than HAOS/Kairos:** mark the slot good only after k3s API is up, core OneMind pods are Ready, and a local health probe passes; otherwise let the bootloader's try counter (3 attempts, like HAOS GRUB) fall back. Both HAOS (good = Supervisor started) and Kairos (good = cloud-init stage, explicitly not workload) mark good early; this is the gap to improve. Also add a watchdog (`panic=5`, `systemd.crash_reboot=yes`, as Kairos does).
5. **Manual rollback in UI and recovery console:** `boot-slot`-style command plus bootloader menu entry (HAOS GRUB menu, rescue shell).
6. **Recovery path:** a recovery partition or USB installer that can reinstall the OS while keeping the data partition (Kairos recovery; HAOS emergency shell).

### 10.2 Signing and update trust (copy Umbrel's design, change the key custody)
- Two-level trust: offline root key signs a list of release-signer keys, signer count (`requiredSignatures`), and revoked manifest hashes; devices refresh the list daily and before each update from two independent sources (API plus a static git raw URL); newest-valid-list wins, older ignored (Umbrel `release-signing.ts`).
- Signed manifest pins every file hash including the bundle; anti-downgrade (new version must be greater than installed unless an explicit test URL); update "check" returns the manifest hash and "install" must match it.
- Plus bundle-level signature verified by the updater before writing (RAUC keyring or Rugix CMS roots). Keep the dev and release CAs separate as HAOS does (`dev-ca.pem`, `rel-ca.pem`).
- Never allow script payloads in bundles that run before hash verification (Umbrel warning in `rugix.ts`).
- Provide a CRA-ready vulnerability intake and a published support period (CRA reporting duties already apply since 2026-09-11; main duties 2027-12-11).

### 10.3 Update UX
- Channels `stable` and `beta` (Umbrel `ReleaseChannel`, HAOS beta/stable). Add `lts` only if you can fund backports (not evidenced by any compared product).
- **Never auto-reboot by default** (Umbrel "never installed automatically", HAOS "does not reboot by itself"). Offer: notify, download in background, install in a user-chosen maintenance window (Olares "Download only" then upgrade, Kairos operator `concurrency`/`stopOnFailure` for multi-node). Optional opt-in auto-install for security-only releases is OneMind's own choice; no compared product ships it, so it is a differentiator with risk.
- Always show release notes from the signed manifest, not the server response (Umbrel pattern).
- After failure: banner "rolled back to X, update again" (Umbrel).

### 10.4 Backup design (3-2-1, encrypted by default, restore-tested)
- **Tier 1 pre-update snapshot (automatic):** before every OS or app update, snapshot app PV data (ZFS/btrfs snapshots or Longhorn snapshots) plus k3s state; keep one per app like HAOS app update backups. This makes OS rollback not leave newer-schema data behind. Umbrel explicitly sets ZFS pool `compatibility=openzfs-2.3` so a rolled-back OS can still import pools; copy this rule for any filesystem feature flags.
- **Tier 2 scheduled encrypted backup of the whole box state** (HAOS/Umbrel model): k3s datastore (etcd snapshot if you run embedded etcd, as `k3s etcd-snapshot` documents; validate how to back up the single-node SQLite default), Kubernetes object manifests, and app PV data.
- **Engine choice for PV data:** restic or Kopia with a repository password you control (restic: AES-256-CTR + Poly1305-AES + scrypt, documented). Velero is good for object+volume orchestration but its FSB uses one **static common encryption key per repo set**, so if you use Velero, put the repository on storage you encrypt separately or front it with your own encryption; Velero FSB does not support hostPath. Longhorn backups to S3/NFS/SMB are an option for block volumes (validate encryption). Olares already combines restic and Velero in one product, a useful precedent.
- **Targets:** local disk or USB, NAS (SMB/NFS), another OneMind box, S3-compatible offsite. Offer an optional managed offsite later (HA Cloud stores only the latest backup and caps at 5 GB; Umbrel lists a private cloud as "coming soon"; so offsite is the market gap).
- **Retention default:** hourly 24 h, daily 7, weekly 4, monthly 12 (Umbrel) for small data; daily with last 3 (HAOS) if backup is large. Warn if destination free space is under 2x backup size (Umbrel rule).
- **Encryption key custody:** generate key, show an "emergency kit" download at setup (HAOS), never display again, document that loss means no restore (Umbrel). Backup status entity and failure notification (HAOS event entity pattern).
- **Restore UX:** restore at onboarding of a fresh box (the Umbrel 2.0 SMB report suggests a restore-at-onboarding path is fragile; test it). Include periodic **automated restore tests** (verify last backup can be opened/listed; not done by any compared product per what I read, so validate feasibility).
- FailSafe/RAID is availability, not backup (Umbrel states this). Surface it that way.

### 10.4b Per-hardware notes
- x86: UEFI Secure Boot + TPM 2.0 measured boot + TPM-bound LUKS as an opt-in "Hardened" profile (Kairos Trusted Boot is the working reference; kernel cmdline is signed and fixed, so keep your own cmdline stable).
- Pi 5: Raspberry Pi secure boot with customer RSA key in OTP and LUKS with OTP-bound secret via the Secure Boot Provisioner; OTP programming is permanent, so make it opt-in. No TPM claim is made (UNVERIFIED).
- Jetson: fused PKC + UEFI Secure Boot; fuse writes are irreversible and UEFI Secure Boot cannot be disabled without reflash (NVIDIA docs). Provide only at factory/provisioning time. fTPM and disk-encryption options are UNVERIFIED.

### 10.5 Security baseline checklist
- Read-only rootfs (EROFS/squashfs/verity), `/etc` and `/var` via overlay or ephemeral, persistent paths whitelisted (HAOS and Kairos both do this).
- No SSH by default; key-only SSH enabled explicitly (HAOS Dropbear on 22222, off unless a key is imported); no password serial root login on production images (HAOS has passwordless serial root on some boards, do not copy).
- k3s: `secrets-encryption: true` (consider `secretbox` provider), `protect-kernel-defaults: true` with the documented sysctls, Pod Security Admission `restricted` with exemptions for system namespaces, default-deny NetworkPolicies per app namespace, audit log. Then run the CIS check yourself; the published K3s self-assessment lags (v1.9 benchmark, k3s 1.27-1.29 vs current k3s v1.37).
- AppArmor profiles for core services (HAOS) and per-app sandboxing via K8s securityContext.
- SBOM per release (SPDX or CycloneDX; format choice not verified from CISA), VEX for known-not-affected CVEs, CVE scan in CI and a published advisory channel; CRA alignment.
- Remote access via Tailscale/WireGuard only; no inbound ports by default (Umbrel recommends Tailscale for backup link; fact limited to that page).

### 10.6 Spikes needed before committing (all UNVERIFIED items)
1. RAUC or Rugix on Jetson Orin: boot flow with L4T UEFI, rollback test by corrupting the new slot.
2. Pi 5 tryboot A/B with k3s: confirm commit gate end to end.
3. k3s single-node datastore backup path (SQLite vs embedded etcd) and `etcd-snapshot` restore test.
4. Velero versus restic/Kopia direct, with a restore drill; confirm Longhorn backup encryption.
5. Kairos Trusted Boot assessment behaviour (docs conflict) if used as a reference.
6. Umbrel license scope; Olares license scope (AGPL-3.0 vs `LICENSE.md`).

---

## 11. Sources (all opened this session)

GitHub files via `gh api repos/OWNER/REPO/contents/PATH`:
- home-assistant/operating-system: `buildroot-external/ota/system.conf.gtpl`, `buildroot-external/ota/manifest.raucm.gtpl`, `buildroot-external/ota/rauc-hook`, directory listings of `/`, `buildroot-external/`, `buildroot-external/ota/`, `buildroot-external/bootloader/`, `buildroot-external/genimage/`, `buildroot-external/rootfs-overlay/etc/`, `Documentation/README.md`; release API (18.5), license API.
- home-assistant/contributors.home-assistant.io: `src/content/docs/os/operating-system/{index,partitions,update-system,debugging,releases}.md`.
- home-assistant/home-assistant.io (branch `current`): `source/common-tasks/general/backups.markdown`, `source/common-tasks/os.markdown`, `source/_integrations/backup.markdown`, `source/_includes/common-tasks/beta_version.md`, `source/_posts/2026-03-26-modernizing-encryption-of-home-assistant-backups.markdown`, `source/_posts/2025-01-03-3-2-1-backup.markdown`.
- getumbrel/umbrel: `LICENSE.md`, `packages/umbreld/source/modules/update/{update,release-signing,signing-keys,install-release,rugix,routes}.ts`, `packages/os/README.md`, `packages/os/mender.cfg`, `packages/os/rugix/rugix-bakery.toml`, `packages/os/release-notes/2.1.0-beta.1.md`, directory listings of `packages/os`, `packages/os/rugix`, `packages/umbreld/source/modules/update`; release API (2.0.1).
- silitics/rugix and rugix/rugix-bakery: `README.md`, `CHANGELOG.md`, `LICENSE-*` listing, repo tree grep.
- kairos-io/kairos-docs: `docs/architecture/{immutable,trustedboot}.md`, `docs/upgrade/{boot_assessment,manual,system-upgrade-controller,kairos-operator}.md`, `docs/advanced/partition_encryption.md`, `docs/examples/boot_assessment_trusted_boot.md`, `docs/installation/edge-devices/{raspberry,nvidia-jetson-images}.md`, `operator-docs/{index,nodeop,nodeop-upgrade}.md`; kairos-io/kairos release API (v4.4.0), license APIs for kairos, kairos-agent, AuroraBoot.
- rauc/rauc `README.rst`; mendersoftware/mender `LICENSE`, `README.md`.
- beclab/Olares: `LICENSE.md`, `README.md`, `SECURITY.md`, `docs/manual/olares/settings/{backup,update}.md`, `docs/developer/install/versioning.md`, `docs/developer/install/cli/upgrade.md`, `framework/backup-server/pkg/handlers/handler_snapshot.go` (restic import grep), repo tree grep.
- raspberrypi/documentation (branch master): `documentation/asciidoc/security/security-architecture.adoc`, `secure-boot-provisioner.adoc`.
- Release/license metadata via GitHub API: velero, restic, borg, longhorn, k3s, kopia.

Web pages fetched (summarised by WebFetch):
- https://developers.home-assistant.io/docs/operating-system/ (301 to https://contributors.home-assistant.io/os/operating-system/)
- https://umbrel.com/support/backups-and-recovery/backing-up-your-data
- https://umbrel.com/support/storage/managing-your-storage
- https://umbrel.com/support/basics/updating-umbrelos
- https://community.umbrel.com/t/introducing-umbrelos-2-0/25444
- https://rugix.org/ and https://rugix.org/docs/ctrl/updates/system-updates/boot-flows/ (the `.../advanced/signed-updates` URL returned 404)
- https://rauc.readthedocs.io/en/latest/
- https://velero.io/docs/main/file-system-backup/
- https://docs.k3s.io/cli/etcd-snapshot, https://docs.k3s.io/security/hardening-guide, https://docs.k3s.io/security/secrets-encryption
- https://longhorn.io/docs/latest/snapshots-and-backups/backup-and-restore/set-backup-target/
- https://restic.readthedocs.io/en/stable/100_references.html
- https://documentation.suse.com/cloudnative/k3s/latest/en/security/self-assessment-1.9.html (first 100k chars)
- https://www.cisa.gov/sbom
- https://digital-strategy.ec.europa.eu/en/policies/cyber-resilience-act
- https://docs.nvidia.com/jetson/archives/r36.4/DeveloperGuide/SD/Security/SecureBoot.html (first 100k chars)
- https://www.raspberrypi.com/documentation/computers/raspberry-pi.html (no secure boot content in truncated text; Pi security claims instead come from the GitHub adoc above)

Seen only as web-search result snippets, NOT opened (treat as UNVERIFIED): https://umbrel.com/support/basics/joining-the-beta-program, https://community.umbrel.com/t/smb-network-backup-restore-fails-infinite-loading-in-onboarding/25506, https://community.umbrel.com/t/failsafe-not-available-on-a-raspberry-pi-5/25561.

Not researched (UNVERIFIED): Mender signing details, Kopia and borg features, Longhorn backup encryption, CVE tooling, Kairos revocation doc contents, HAOS Secure Boot, Umbrel app sandboxing, Rugix on Jetson, Olares OS-level signing and rollback.
