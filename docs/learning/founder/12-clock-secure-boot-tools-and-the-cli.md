<!-- SPDX-License-Identifier: Apache-2.0 -->
# Clock, Secure Boot, disk and admin tools, and the `onemind` CLI

**Asked by:** the founder, 2026-11-25, during the "stable and live" sprint (Step 2: the Debian bones).
**Serves:** Step 2 of the stable-and-live sprint (standard Debian parts on the image), D-007 (Debian 13 base), issue #148 (Secure Boot), issue #153 (update key ceremony).

Step 2 adds the everyday Debian layer the image was missing. Three of its pieces, plus the command-line tool, explained in plain words.

## 1. The clock (time sync)

A computer keeps time with a small clock chip, and that chip drifts. **Time sync** asks internet time servers for the exact time and corrects the box every few minutes. Debian's tool for it is `systemd-timesyncd` (NTP, the Network Time Protocol, is the language it speaks).

Why the box needs it:
- **Security.** Update signatures, web certificates and sign-in tokens all carry expiry dates. With a wrong clock the box can refuse a valid update or accept an expired one.
- **Snapshots and backups** are named and pruned by time. A wrong clock prunes the wrong ones.
- **Logs.** When something breaks, the times have to be right to work out what happened in what order.

Until Step 2 the image had no time sync at all: Debian's "recommended" packages are switched off in our build (`os/rootfs/sources/configure-apt.sh`), so it was never pulled in. Step 2 lists it explicitly (PR #1091).

## 2. Secure Boot

When a computer turns on, the firmware (the built-in startup software) loads a boot loader, which loads the kernel, which starts the OS. **Secure Boot** makes the firmware check a digital signature at each step. If anything was changed (malware hidden in the boot files, or someone swapping the disk), the box refuses to start it.

The OneMind plan:
- Each update slot (A and B) gets one signed file holding the kernel, its starting files and its settings. This file is called a **UKI** (unified kernel image).
- With RAUC's `efi` backend the firmware itself picks the slot from its boot entries, so there is no separate boot loader in the chain, and A/B updates and the health-gated rollback keep working. (GRUB, today's boot loader, would need Microsoft's `shim` to start a signed kernel under Secure Boot; see `os/secureboot/README.md`.)
- Only files signed with an enrolled key boot. Per decision D-019, OneMind's key is enrolled at the factory; it is made once, offline, in the **key ceremony** (#153). An owner may take over the box's keys ("sovereign mode": physical presence, a clear warning first), and OneMind's key stays enrolled so updates keep working.
- It ties into disk encryption: the security chip (**TPM**) seals the key that unlocks `/data` to measurements of the boot, including PCR 7, which records the Secure Boot state (and a signed PCR 11 policy when the image ships one; `internal/storage/luks.go`). If the boot chain or Secure Boot state changes, the TPM does not release the key and the printed recovery key is needed instead. A stolen disk on its own stays locked. Because turning Secure Boot on changes PCR 7, the boot route should be settled before a box holds real files.

It ships behind a switch that is off by default and uses test keys until the ceremony (work in PR #1032), so the normal boot path stays unchanged while the new one is proven in a VM.

## 3. Disk and admin tools

Standard Linux tools every server has, which the image lacked (PR #1088):
- **`smartmontools`** reads the health report a drive keeps about itself (worn sectors, temperature, failure warnings), so the dashboard can warn *before* a disk dies. The disk-health code already existed in OneMind; it could not run without this tool.
- **`btrfs-progs`** and **`gdisk`** manage the btrfs file system (the one that supports snapshots) and the disk's partitions.
- **Admin tools:** `bash-completion` (Tab to finish commands), `less` (page through long output), `htop` (what is using CPU and memory), `nano` (a simple text editor), `rsync` (reliable file copies), `jq` (reads JSON), `ping` (network check), plus hardware-info tools (`pciutils`, `usbutils`, `dmidecode`, `ethtool`). When something goes wrong and someone logs in over SSH, these are what they fix it with.

Each comes straight from Debian, so OneMind builds none of it. (The planning estimate for all Step 2 packages together was roughly 63 MiB; UNVERIFIED until measured on a built image.)

## 4. The `onemind` CLI, and is it built the best way?

There is a CLI: the `onemind` command (Go, in `cmd/onemind`), with about 97 commands in 28 groups: `status`, `doctor`, `logs`, `update`, `snapshots`, `storage`, `apps`, `machines`, `join`, `agents`, `actions` (the approval queue), `mcp`, `audit` and more.

It is built the same way as `kubectl` (Kubernetes), `gh` (GitHub) and `docker`, and that is the right way:

| Choice | Why it is right |
|---|---|
| Go, one file, no dependencies | Copy it to any machine (Linux, Mac, Pi) and it runs |
| Cobra, the standard Go CLI library | Gives Tab completion and help text for free; man pages need Cobra's small doc generator |
| Talks to the box through the gateway, with the generated Go SDK (`sdk/go`) | CLI, dashboard, phone and AI agents use the same door: one set of permissions and one audit log. An agent can only request an action; the owner approves it. (A few commands act on the machine they run on instead: `node info`, `storage` disk checks and `update apply`, which need local root.) |
| `--json` output | Scripts and agents can read the results |
| Contexts (`onemind context`, `use`) | One CLI can talk to several boxes |

What was missing is polish, queued as one PR after Step 2: the `onemind` Tab-completion file and man pages (read with Debian's `man-db`) built into the image (`bash-completion` itself arrives with PR #1088), and a `.deb` plus a Homebrew package built in CI so the CLI installs on a laptop with `apt install` or `brew install`. A later test will check that every command supports `--json` and returns errors in one format.
