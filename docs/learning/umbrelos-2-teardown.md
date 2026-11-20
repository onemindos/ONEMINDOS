<!-- SPDX-License-Identifier: Apache-2.0 -->
# umbrelOS 2.0.1 teardown: how it is built, and why it feels like an OS

**Serves:** the umbrelOS parity stream ([`docs/strategy/umbrel-parity.md`](../strategy/umbrel-parity.md), issues UMB-P01 to P10), Home launcher PU-04, IA §1 ([`docs/design/IA.md`](../design/IA.md)), D-007 (Debian 13 base).
**Method (2026-11-20, founder request):** the official `umbrelos-amd64-usb-installer.iso` for 2.0.1 (released 2026-11-01; SHA-256 checked against Umbrel's `SHA256SUMS`) was installed in a lab VM (UEFI, Secure Boot off, 64 GB disk). The image inside the ISO was opened **read-only** to read its layout and config. The UI was used as a new owner would.
**Licence:** umbrelOS is PolyForm Noncommercial 1.0.0. We **study patterns only**: no code, assets, icons, wallpapers, strings or screenshots go into this repo (same rule as `umbrel-parity.md` §6). Lab screenshots stay off the repo.

## 1. Plain-English summary
- umbrelOS 2.0.1 is **Debian 13 (trixie) with A/B updates**, the same shape as OneMind (D-007 plus RAUC). The base OS is **not** what makes it feel like an OS.
- The feeling comes from the **web UI's shell**: a full-screen wallpaper "desktop", a greeting, a few widgets, and a **dock**. Every app (App Store, Files, Settings, Live usage) opens **on top of** that desktop as a window or sheet, and closing it brings you back. There is **no permanent sidebar**.
- OneMind's dashboard is built the other way: a **permanent left sidebar** with about 15 entries (Home, Market, Approvals, Activity, Installed, Nodes, Machines, Alerts, Storage, Backups, Settings, …) and a page area. That is the layout of an admin console, so it reads as a "dashboard" even though our Home already has a wallpaper, greeting, widgets and a dock (`ui/src/home/`).

## 2. How the umbrelOS image is put together (read from the image)
| Layer | What umbrelOS 2.0.1 does | OneMind today |
|---|---|---|
| Base | Debian 13.7 trixie, Debian kernel 6.12 (`6.12.*+deb13-amd64`), about 900 packages | Debian 13 (D-007), own read-only image |
| Installer | Live ISO (a small Nix-built environment in `nix-store.squashfs`) that writes a prebuilt 8.5 GB disk image with `dd`. It lists disks, you type a number, and it **writes immediately, with no confirmation**. Then "press any key to shut down, remove the USB" | Installer stick; the owner types `ERASE` before anything is written |
| Disk layout | GPT: `EFI` 256 MB, `boot-a` / `boot-b` 512 MB, `system-a` / `system-b` 10 GiB, `data` = rest of disk (ext4, only 0.5 % reserved blocks so huge disks don't waste space). The shipped image holds EFI, boot-a, system-a; the rest is created on first boot from `/etc/rugix/bootstrapping.toml` | GRUB + RAUC, `onemind-system-a` / `-b` ext4 slots, `/data` (`os/rauc/system.conf.in`, `os/boards/x86_64-efi/layout.yaml`) |
| A/B updates | **Rugix Ctrl** (Rust, Apache-2.0/MIT). GRUB reads two checksummed environment files (`rugpi/primary.grubenv`, `secondary.grubenv`) and a "boot spare once" flag: it tries the other slot one time, and falls back if the new slot isn't committed | RAUC with verity bundles and a health gate (k3s) before commit |
| Data partition | A mount script reads `umbrel.yaml` from Rugix's config partition and can mount an external RAID instead of the local `data` partition. If mounting fails, the box **still boots** on a temporary in-memory data area and the daemon starts in **recovery mode** (`fail-on-mount-error = false`) | Rescue console when k3s is down (REC-W11-04); no "boot without data" mode yet |
| Factory reset | A Rugix **state-reset** hook (`/etc/rugix/hooks/state-reset/prepare/10-umbrel.sh`) | UMB-P09 (#146, PR #355) |
| System daemon | **One** Node.js daemon, `umbreld` (`umbrel.service`, restarts forever, data in `/home/umbrel/umbrel`). It serves the web UI, the API and per-app login, and drives everything else | Gateway (FastAPI) + `onemindd` (Go) + k3s + NATS |
| Apps | Docker (each app is a Compose project) | k3s |
| VMs ("Machines") | libvirt / QEMU, with a `machines.target` | Not in v0 (dashboard has a Machines page) |
| Local name | Avahi mDNS → `umbrel.local` works on the LAN with no setup | Check: does the hub announce itself over mDNS? |
| Console | `umbrel-tty-message` prints the box's IP and `.local` name on the physical screen | Owner token on the serial console |
| Also on board | NetworkManager + wpa_supplicant (Wi-Fi from the UI), Samba (file sharing to Mac/Windows), smartmontools, a ZFS target, a preloaded Tor image, linuxbrew, SSH host-key hydration from the data partition | |

**What it means for us:** the low layers match ours almost one-to-one, so we are not behind on the OS itself. Three ideas worth taking as **patterns** (no code): "boot anyway into recovery mode when the data disk fails"; checksummed, duplicated boot environment files; and mDNS plus a console message so a new owner can always find the box.

## 3. Why OneMind feels like a dashboard (and what already exists)
- **The decision behind it.** IA §1 puts a left sidebar on desktop and bottom tabs on phones. `umbrel-parity.md` PU-04 says **"A dock is not proposed (a sidebar and bottom tabs already exist)"**. So the dashboard look was a deliberate choice, not a bug.
- **What is already built.** `ui/src/home/` has HomeScreen, wallpapers, greeting, WidgetGrid, AppGrid and a **Dock** (up to 8 pinned apps). `dashboard/src/pages/Home.tsx` uses it, but **inside** `dashboard/src/shell/Shell.tsx`, so the sidebar frames it and every other screen is a normal page.
- **Open work does not change the shell.** UMB-P04 (#141), P05 (#142, PR #357), P06 (#143, PR #353), P08 (#145), P09 (#146, PR #355) and P10 (#147) add **screens and wiring**. They will land inside the sidebar layout as more pages. No open issue or PR changes the shell itself.

## 4. The OS shell: decided as D-016 (2026-11-20), first version built in `feat/desktop-shell`
1. **Desktop is the root.** `/` is the full-screen wallpaper with greeting, "Needs you", widgets, an app grid and the dock. No sidebar on it.
2. **Everything opens on top of the desktop.** Market, Files, Settings, Approvals, Activity, Nodes and Backups open as a large window (desktop) or a full sheet (phone) over the blurred wallpaper. Each keeps its own URL (deep links still work), and Esc or ✕ returns to the desktop.
3. **Dock as main navigation.** Home, Market, Files, Approvals (with badge), Settings, plus pinned apps. A dock icon for "System" opens Nodes, Storage, Backups, Alerts and Activity in one window.
4. **Keep the console view** for operators: the current sidebar layout stays as a "Console" mode (Settings → Appearance, or a role default for admins). That keeps OneMind's strengths: approvals, audit timeline, multi-node.
5. **First run sets the tone.** The onboarding PU-05 picks a wallpaper and lands on the desktop, not on a page.

**Decided:** Zeus chose this on 2026-11-20 ([D-016](../DECISIONS.md)). It replaces PU-04's "no dock" and IA §1's "sidebar on desktop". The first version keeps every screen as it is and changes only the frame (`dashboard/src/shell/DesktopShell.tsx`); the UMB-P screens render into it unchanged. Not in the first version: the System folder in the dock (all items are shown), a magnifying dock, a wallpaper choice in first run (PU-05).
