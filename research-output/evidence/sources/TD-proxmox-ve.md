# Sources: TD-proxmox-ve (Proxmox VE, Tier B condensed teardown)

Used in `research-output/02-competitors/proxmox-ve.md`. Claim rows are in `evidence/claims/TD-proxmox-ve.csv`.

**Code was read from shallow clones** (`--depth 1`) in `<lab-dir>/src/proxmox/`, outside the repo. Nothing was built or run. The GitHub `proxmox/*` repositories are Proxmox's official read-only mirrors of git.proxmox.com, so their commit SHAs match upstream. `proxmox-kernel-helper` has no GitHub mirror and is cited on git.proxmox.com with `hb=<sha>`. SHA permalinks serve as their own archive.

**Saved web pages** are in `evidence/sources/TD-proxmox-ve/`, with hashes in `TD-proxmox-ve/SHA256SUMS`. They were fetched with curl on 2026-11-11 and stripped to plain text. Emails are redacted, and one private IP address in a Proxmox example log is masked. Forum threads are saved as **short excerpts only**: user handles, host names and partition UUIDs are removed. Wayback save requests are denied in this environment, and no existing captures were checked.

## Pinned code

| Repository | Commit | Commit date | Version in debian/changelog | Licence | Type |
|---|---|---|---|---|---|
| github.com/proxmox/pve-installer | `ce4ea55a471f778ac2b052b48765a51dc87097da` | 2026-11-07 | proxmox-installer 9.2.9 | AGPL-3 | PRIMARY (code) |
| github.com/proxmox/pve-manager | `e1e1c4afbe2dbf3ab8c32dea80aded60bd26b979` | 2026-11-11 | pve-manager 9.2.27 | AGPL-3+ | PRIMARY (code) |
| github.com/proxmox/pve-container | `15eb5c70bb55bade872f4e794ab3c68ed86b404a` | 2026-11-11 | pve-container 6.1.20 | AGPL-3+ | PRIMARY (code) |
| github.com/proxmox/pve-access-control | `bbc4ed63427249f98c86efd64054dabcca77bd9d` | 2026-11-03 | n/a | AGPL-3+ | PRIMARY (code) |
| github.com/proxmox/pve-docs | `7742f85bfb53c0eb71bd8d7e46b65cbfa640bcc1` | 2026-11-10 | n/a | GFDL-1.3 | PRIMARY (official docs source) |
| git.proxmox.com/proxmox-kernel-helper | `3b801dcd7bcc2b61f86f19b3b94679e26a07df7b` | 2026-10-28 | proxmox-kernel-helper 9.2.1 | GPL-2.0-only | PRIMARY (code) |
| github.com/community-scripts/ProxmoxVE | `c1e45c1c51928372c130c26e41e3773c41fcc90e` | 2026-11-11 | n/a | MIT | PRIMARY-METADATA (gh api: stars, licence, count of `ct/` entries) |

### Files read
- pve-installer: `Proxmox/Install.pm` (L450–560 LVM layout, L630–690 ESP and bootloader, L950–1060 extract_data, L1225–1245 unsquashfs, L1451–1491 .deb unpack), `Proxmox/Sys/Block.pm` L219–300 (partitioning), `debian/changelog` (arm64 entries L115–125 and L272–276).
- pve-manager: `bin/pveupgrade`, `bin/pveupdate`, `PVE/CLI/pve8to9.pm` (check list; L1592–1684 bootloader check), `PVE/APLInfo.pm` L148–196, `PVE/API2/Nodes.pm` L1803–1870, `debian/copyright`.
- pve-container: `src/PVE/LXC/Create.pm` L640–790 (OCI).
- pve-access-control: `src/PVE/Auth/` (listing), `src/PVE/AccessControl.pm` (TFA types).
- proxmox-kernel-helper: `src/bin/proxmox-boot-tool` L552–620, `src/proxmox-boot/functions` L18–72, `src/proxmox-boot/proxmox-auto-removal`, `debian/copyright`.
- pve-docs: `pve-system-requirements.adoc`, `system-booting.adoc` L389–416, `pmxcfs.adoc`, `pvecm.adoc`, `ha-manager.adoc`, `vzdump.adoc`, `pve-storage-pbs.adoc`, `pveum.adoc`, `pve-installation.adoc`, `pve-firewall.adoc`.

## Saved web pages (`TD-proxmox-ve/`)

| File | URL | Type | Used for |
|---|---|---|---|
| `roadmap.txt` | https://pve.proxmox.com/wiki/Roadmap | PRIMARY | release dates, bases, kernels, 9.1 OCI, 9.2 arm64, planned items, no AI items |
| `faq.txt` | https://pve.proxmox.com/wiki/FAQ | PRIMARY | licence, architectures, support lifecycle table, upgrade method |
| `upgrade-8-to-9.txt` | https://pve.proxmox.com/wiki/Upgrade_from_8_to_9 | PRIMARY | in-place vs reinstall paths, known boot issues |
| `package-repos.txt` | https://pve.proxmox.com/wiki/Package_Repositories | PRIMARY | enterprise / no-subscription / test repos, key per architecture |
| `secure-boot.txt` | https://pve.proxmox.com/wiki/Secure_Boot_Setup | PRIMARY | Secure Boot chain background |
| `pricing.txt` | https://www.proxmox.com/en/products/proxmox-virtual-environment/pricing | PRIMARY | subscription tiers and prices |
| `pdm-roadmap.txt` | https://pdm.proxmox.com/docs/roadmap.html | PRIMARY | Datacenter Manager 1.0 / 1.1 dates |
| `pbs-roadmap.txt` | https://pbs.proxmox.com/wiki/Roadmap | PRIMARY | Backup Server 4.0 / 4.2 dates |
| `git-index.txt` | https://git.proxmox.com/?a=project_index | PRIMARY | absence of a public ISO-build repository |
| `press.txt` | https://www.proxmox.com/en/about/company-details/press-releases | SECONDARY | press release index. The dates in the stripped listing are misaligned with the titles, so they are not used |
| `pr-arm64.txt` | …/press-releases/proxmox-virtual-environment-launches-official-arm64-support | SECONDARY (vendor) | arm64 launch, NVIDIA/Supermicro validation |
| `pr-nvidia-mission-control.txt` | …/press-releases/proxmox-ve-for-nvidia-mission-control-ai-factories | SECONDARY (vendor) | NVIDIA Mission Control collaboration, 2026-07-28 |
| `pr-20-years.txt` | …/press-releases/proxmox-celebrates-20-years | SECONDARY (vendor self-report) | founded 2005, subscriptions since 2013, 1.5 M hosts |
| `forum-grub-8to9.txt` | https://forum.proxmox.com/threads/issue-booting-into-grub-after-upgrade-from-proxmox-8-to-9.178482/ | SECONDARY (excerpt) | failure report 1 |
| `forum-broken-boot.txt` | https://forum.proxmox.com/threads/broken-boot-after-upgrade-from-8-9.176455/ | SECONDARY (excerpt) | failure report 2 |
| `forum-nested-beta.txt` | https://forum.proxmox.com/threads/pve-9-beta-pve-nested-upgrade-from-8-to-9-breaks-boot.168662/ | SECONDARY (excerpt) | failure report 3 |

Fetches that failed (HTTP 404, not used): proxmox.com "about" and "open-source" company pages. An OVH forum thread found by search returned a login wall and is marked `UNVERIFIED (blocked)`. It is not cited.

Also reused, not re-fetched: `evidence/sources/W16/proxmox-pricing.txt` (accessed 2026-11-10). It matches today's copy on the Community, Basic, Standard and Premium prices.
