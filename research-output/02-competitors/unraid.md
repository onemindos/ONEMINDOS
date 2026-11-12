# Unraid: Tier C teardown

**Workstream:** W1 (Tier C) · **Tag:** TD-tier-c-nas · **Date:** 2026-11-11
**Claims:** `evidence/claims/TD-tier-c-nas.csv` (Unraid rows C-TD-tier-c-nas-001 … 017), plus reused C-W16-029 · **Sources:** `evidence/sources/TD-tier-c-nas.md`
**Pins:** `unraid/docs@297a271f` (2026-11-10), `unraid/webgui@b135287c` (2026-11-04), `unraid/api@8e587fe2` (2026-11-04). Release analysed: **Unraid OS 7.4.0** (2026-11-10) [C-TD-tier-c-nas-001].
**Requirements served:** R-1, R-2, R-3, A-1, A-2, A-5, A-6, AI-1, AI-5, M-2, M-8, H-1, P-7, F-14, D-001

> ### Explain it like I'm the founder
> Unraid is the paid home-server OS that hobbyists love. It boots from a **USB stick**, copies itself into **RAM** and runs from there. It lets you mix drives of different sizes under one or two "parity" drives [C-TD-tier-c-nas-002]. Apps are Docker containers picked from a community store, and VMs run on KVM.
>
> **What matters for OneMind:** Unraid shows that people will **pay** for a simple home server OS, about USD 49–249 per licence [C-W16-029]. Under the hood, though, its updates are basic. The updater checks an **MD5 checksum**, not a signature. It keeps **one** previous version in a folder, and rolling back is a **manual** menu click [C-TD-tier-c-nas-005, C-TD-tier-c-nas-006, C-TD-tier-c-nas-007]. Its plugin system gives third-party code **full access to the OS** [C-TD-tier-c-nas-009]. OneMind should copy Unraid's business clarity and its simplicity. It should not copy the update chain or the plugin trust model.

## 1. W1 fields

| Field | Unraid (evidence) |
|---|---|
| **Architecture** | A monolithic appliance. The PHP "dynamix" WebGUI (GPL-2.0) [C-TD-tier-c-nas-012] runs over a storage layer: the parity "array" plus XFS/Btrfs/ZFS pools [C-TD-tier-c-nas-001]. Docker runs the apps and KVM/libvirt runs the VMs [C-TD-tier-c-nas-017]. Since 7.2, a built-in **GraphQL API** (GPL-2.0-or-later) is gradually replacing the WebGUI backend [C-TD-tier-c-nas-011]. |
| **Base OS** | No public distro build. It appears to be Slackware-derived: its init scripts say "on Slackware" [C-TD-tier-c-nas-004, partial]. Its own kernel build is `6.18.60-Unraid` [C-TD-tier-c-nas-001]. |
| **Boot / image** | `bzimage` + `bzroot` files on a FAT USB stick, loaded into RAM [C-TD-tier-c-nas-002]. 7.3 added **internal boot** (NVMe/SATA, optionally a ZFS boot pool) [C-TD-tier-c-nas-003]. |
| **Update / rollback** | `unRAIDServer.plg` downloads a zip plus an MD5 file, checks the MD5, unzips, and checks `.sha256` sidecars that ship inside the same zip. **No signature check** was found [C-TD-tier-c-nas-005]. The old files move to `/boot/previous`, so **one** version is kept [C-TD-tier-c-nas-006]. Rollback is "Tools → Downgrade OS" or a manual file copy. There is **no automatic fallback** [C-TD-tier-c-nas-007]. A "Safe Mode (no plugins)" boot entry is the recovery tool [C-TD-tier-c-nas-008]. Some features are one-way: ZFS pool upgrades, internal boot and TPM licensing block downgrades [C-TD-tier-c-nas-003]. |
| **App format** | Docker **XML templates** in the Community Applications (CA) store. A moderation team does "basic vetting", and submissions are validated and scanned [C-TD-tier-c-nas-010, C-TD-tier-c-nas-017]. Separately, **plugins** (`.plg`) run as root with full filesystem access. The docs themselves warn about this [C-TD-tier-c-nas-009]. |
| **Identity** | One root account for the WebGUI. Optional SSO/OIDC login since 7.2. API keys with roles [C-TD-tier-c-nas-011]. An open bug reports a VIEWER key that can perform writes [C-TD-tier-c-nas-014]. No family accounts or parental controls were found. |
| **AI features** | **None in the OS.** A "native MCP" work-intent issue was opened and closed with no release. Only community MCP servers wrap the GraphQL API [C-TD-tier-c-nas-014]. The NVIDIA driver is a plugin, not part of the base image [C-TD-tier-c-nas-016]. |
| **Backups** | Boot-device backup, local or via the Unraid Connect cloud. 7.4 adds download/save-to-server options [C-TD-tier-c-nas-001]. Parity protects against disk failure. It is not a backup. |
| **Security** | Runs from RAM, so the system files reset on every boot [C-TD-tier-c-nas-002]. Frequent CVE package bumps [C-TD-tier-c-nas-001]. Weak points: MD5-checked updates, root plugins, and no Secure Boot story found. |
| **Hardware** | x86_64 only [C-TD-tier-c-nas-002]. No ARM, Pi or Jetson. The licence is tied to the USB GUID or, since 7.3, a TPM [C-TD-tier-c-nas-012, C-TD-tier-c-nas-003]. |
| **License** | Proprietary OS, perpetual licence. GUI and API source is GPL-2.0 [C-TD-tier-c-nas-012, C-TD-tier-c-nas-011]. |
| **Business model** | Perpetual licences at USD 49 / 109 / 249; every licence includes every feature; vendor claims "over half a million users" [C-W16-029]. Starter and Unleashed get 1 year of updates, then an optional USD 36/year. Only the **two newest minor versions** get patches, so a lapsed box stops getting security fixes quickly [C-TD-tier-c-nas-013]. |

## 2. Failure signals (what they teach)

| Signal | Lesson for OneMind |
|---|---|
| 7.2.5 changed container MAC addresses on recreate (a breaking change in a point release). 7.3 then shipped a VLAN DHCP known issue [C-TD-tier-c-nas-015] | Network identity is part of the app contract. Pin it in `onemind.app.yaml` and test it in CI. |
| Users must update the NVIDIA and Connect plugins *before* updating the OS [C-TD-tier-c-nas-016] | Drivers that live outside the image break on OS updates. OneMind ships GPU drivers as signed, version-locked extensions (01, REC-DEC-24). |
| Bug #2065: a read-only API key can perform writes [C-TD-tier-c-nas-014] | Role checks must be tested per method. Matches OneMind's gateway-enforced approvals (REC-DEC-13). |
| One-way features (internal boot, TPM licence, ZFS upgrade) block downgrades [C-TD-tier-c-nas-003] | A rollback promise needs a "point of no return" warning before any one-way migration. |

## 3. What competitors do (constraint-fit)

| Product | Update + rollback | App trust | Constraints | Constraint fit with OneMind |
|---|---|---|---|---|
| **Unraid 7.4** | MD5-checked file swap; 1 previous version; manual [C-TD-tier-c-nas-005, C-TD-tier-c-nas-007] | Docker templates + root plugins [C-TD-tier-c-nas-009] | Small company; x86 only; single box; no robotics | **Low** for image/updates/trust; **Candidate** for pricing and storage UX |
| Home Assistant OS | RAUC A/B, signed bundles (see `home-assistant-os.md`) | Add-on security rating | Funded; Pi + x86 | High for the image layer |
| TrueNAS CE | ZFS boot environments; manual rollback [C-TD-truenas-scale-009] | Git catalogue, Compose | Funded; x86 NAS | Candidate for a storage profile |
| **OneMind (01)** | Signed RAUC A/B + health gate | Signed `onemind.app.yaml` + extension allow-list | Solo; Pi → GPU cluster; robotics | — |

## 4. What OneMind copies and what it does better

| # | Pattern | Copy or improve | Requirement IDs |
|---|---|---|---|
| REQ-UR-1 | **"Every feature in every licence"** pricing, with tiers by device count and update years [C-W16-029] | Copy the clarity. But never let a lapsed licence lose **security** fixes, because the CRA requires a support period (01, REC-DEC-14) [C-TD-tier-c-nas-013] | H-1, M-8 |
| REQ-UR-2 | **Safe-mode boot entry** that skips all plugins/extensions [C-TD-tier-c-nas-008] | Copy: a "no extensions" boot target in each slot | R-1, A-6 |
| REQ-UR-3 | **Mixed-size drive pooling** as the headline storage UX | Candidate for the Pro storage profile only. Evaluate it with the TrueNAS REQ-TN-13 | UX-6, F-14 |
| REQ-UR-4 | **Signed updates** | **Do better:** signed RAUC verity bundles instead of MD5 plus in-zip sha256 [C-TD-tier-c-nas-005] | R-1, R-3, M-2 |
| REQ-UR-5 | **Automatic rollback** | **Do better:** boot counter + health gate instead of a manual downgrade [C-TD-tier-c-nas-007] | R-1, P-7 |
| REQ-UR-6 | **Plugins without root** | **Do better:** OS-level plugins only as signed, allow-listed extensions (sysext/confext). Never root shell scripts [C-TD-tier-c-nas-009] | A-5, A-6, M-2 |
| REQ-UR-7 | **Warn before one-way migrations** [C-TD-tier-c-nas-003] | Copy the release-note "Rolling back" section and turn it into an in-UI pre-update check | R-1, R-3 |
| REQ-UR-8 | **Built-in AI/MCP** | **Do better:** first-party MCP with per-tool grants (01), where Unraid has none [C-TD-tier-c-nas-014] | AI-1, AI-5 |

**Effect on Tier A decisions:** none flip. Unraid confirms the market for simple paid home servers. It is a contrast case for signed, health-gated A/B updates.

## Glossary

| Term | Meaning |
|---|---|
| **Parity array** | Unraid's storage scheme: data disks keep separate filesystems, and one or two parity disks can rebuild any one or two failed disks. |
| **RAM root filesystem** | The OS is unpacked into memory at boot, so changes to system files vanish on reboot. |
| **`.plg` plugin** | An Unraid XML file that downloads and runs scripts as root to extend the OS. |
| **MD5 / SHA-256 checksum** | Fingerprints that detect corruption. Without a signature they do not prove *who* made the file. |
| **TPM licensing** | Tying the licence to the motherboard's security chip instead of the USB stick. |
| **GraphQL** | An API style where the client asks for exactly the fields it needs. |
