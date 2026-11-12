<!-- SPDX-License-Identifier: Apache-2.0 -->
# Machines (virtual machines): umbrelOS study and the OneMind design

**Status:** study and design proposal (2026-11-12). Nothing here changes [`docs/DECISIONS.md`](../DECISIONS.md) or the contract [`sdk/contracts/poc-v0.md`](../../sdk/contracts/poc-v0.md); the API, scopes and action types below go into a contract PR first (§5, MACH-0).
**Umbrel source read:** umbrelOS `2.1.0-beta.1`, commit `6f357e18d0a4`, licence PolyForm Noncommercial 1.0.0. Paths below are relative to that tree and written as `U:<path>`.
**Builds on:** [research-output/02-competitors/umbrelos.md](../../research-output/02-competitors/umbrelos.md), [research-output/24-QUESTION-BANK-ANSWERS.md](../../research-output/24-QUESTION-BANK-ANSWERS.md) Q296 and REC-QB-02, [docs/ARCHITECTURE.md](../ARCHITECTURE.md) (VM row), [docs/leap/WORKSTREAMS.md](../leap/WORKSTREAMS.md).

> **Explain it like I am the founder**
> **Does Umbrel have a desktop? Yes, twice over.** The umbrelOS web page *is* a desktop: wallpaper, app grid, dock, widgets. And its "Machines" feature runs a whole second computer (Windows 11, Ubuntu Desktop, Fedora, Debian, Android, even Windows 98) inside a browser tab, drawn on top of that desktop with the dock still showing. You can pin a machine to the home screen like an app, plug a USB stick into the box and hand it to the machine, copy and paste, hear its sound, and use it from a phone with a touch keyboard.
> Under the hood it is plain, proven Linux parts: **QEMU/KVM driven through libvirt**, a software TPM so Windows 11 installs, and **noVNC** in the browser. Umbrel's own code is the glue: about 18,000 lines of TypeScript.
> **OneMind's plan:** use **KubeVirt** (the Kubernetes way of running the same QEMU/KVM), because OneMind already runs k3s on every box. That gives us things Umbrel cannot do: run a machine on *any* box in your house, have an AI agent only *ask* to use a machine and wait for your tap, prove a machine backup actually boots, and give each person in the house their own machines. Desktop extras (sound, clipboard, 3D graphics) come later, because KubeVirt does not do them out of the box.
> **Raspberry Pi:** small Linux servers in a VM should work on a Pi 5 with 16 GB; Windows will not. Both are lab tests, not facts yet (§4.10).

**Legal rule for this page and everything built from it.** umbrelOS is PolyForm Noncommercial; OneMind is sold. This page describes Umbrel's architecture and cites file paths. No Umbrel code, strings, images, icons, wallpapers, OS-catalog data or UI text goes into this repo, and nothing is paraphrased line by line. Every OneMind piece below is our own code on components whose licences are listed in §4.2.

---

## 1. How umbrelOS does it

### 1.1 Shape

```
Browser (React)                      umbreld (Node, one process)                       Host (Debian, read-only A/B image)
──────────────                       ───────────────────────────                       ──────────────────────────────────
Machines overlay ──tRPC──────────►  modules/machines  ──virsh / qemu-img──────────►  libvirtd (socket-activated, qemu:///system)
  catalog, wizard, settings           machine-store (one YAML per machine)               └ QEMU/KVM per machine (transient domain)
  noVNC console ──WebSocket──────►  server/machine-console-socket ──unix socket──►     VNC display socket (no TCP port)
  audio worklet ──WebSocket──────►  server/machine-audio-socket  ──ALSA capture──►     snd-aloop loopback card (playback from QEMU)
                                     guest-api (HTTP on the private VM bridge) ◄──────  guest cloud-init "first boot done" call
AI agent ──MCP──────────────────►  modules/mcp/tools/machines ──RFB client──────────►  same VNC socket (screenshot + input)
                                     backups (Kopia) ── prepare/release ──────────────► virsh snapshot-create-as / blockcommit
```

Everything runs on the host. There is no container boundary around libvirt; umbreld runs as root and calls `virsh`, `qemu-img`, `nft`, `iptables`, `nmcli`, `mount`, `udevadm`, `wimlib-imagex`, `bsdtar`, `mtools` and a few others through `execa` (counted from `U:packages/umbreld/source/modules/machines/*.ts`).

### 1.2 Key files

| Concern | File (at `6f357e18d0a4`) | What it does |
|---|---|---|
| Service, catalog, lifecycle | `U:packages/umbreld/source/modules/machines/machines.ts` (3,481 lines) | The `Machines` class: built-in OS catalog (zod-validated, filtered to the host architecture), image download queue (one at a time), create queue, per-machine lock, install jobs, 1-second state poll, USB reconcile, agent-control bookkeeping, backup prepare/release |
| tRPC API | `U:.../machines/routes.ts` | `capabilities`, `list`, `create`, `retryInstall`, `start`, `stop`, `restart`, `forceStop`, `uninstall`, `updateSettings`, `usbDevices`, `setPinned`, `ejectInstallMedia`, `osImages`, `agentControls`, `clipboardSharing`, `screenshot`, `control`. All are `privateProcedure` (signed-in owner) |
| Machine definition | `U:.../machines/domain.ts` | Versioned definition type (arch, platform profile, firmware, disk bus, network mode, cores, memory, TPM, secure boot, port forwards, USB assignments); builds the libvirt domain XML |
| libvirt wrapper | `U:.../machines/libvirt.ts` (1,174 lines) | Probes `qemu-img`, `virsh` and `/dev/kvm`; firmware lookup (OVMF on x86, AAVMF on arm64, Microsoft-keyed variants for secure boot); swtpm state; network and firewall reconcile; start with GPU fallback; stop, restart, live USB attach/detach, eject media; backup overlay pivot |
| Persistence | `U:.../machines/machine-store.ts` | One definition file per machine under the umbreld data directory; the disk is `disk.qcow2` beside it unless the owner placed it in a Files folder |
| NAT network | `U:.../machines/machine-network.ts` | A libvirt network on its own Linux bridge and a private /24, static DHCP leases per machine, DNS taken from the host's resolver, nftables port-forward rules |
| LAN bridge | `U:.../machines/lan-bridge.ts` | Moves the host's wired interface under a bridge with NetworkManager so bridged machines get addresses from the home router; refuses Wi-Fi |
| USB | `U:.../machines/usb-devices.ts` (621 lines) | Lists host USB devices, works out whether the host or an app is using one, writes udev rules into `/run` to keep host services off assigned devices, follows devices that re-enumerate as another model |
| First-boot handshake | `U:.../machines/guest-api.ts` | Small HTTP server bound to the VM bridge address only; the guest posts a per-machine random token when setup finishes, then install media is detached and a bridged machine moves from NAT to the LAN |
| Windows media | `U:.../machines/windows-image.ts` (786 lines) | Rebuilds Windows install media with an unattended answer file and virtio drivers; special paths for Windows 98/XP/7 and Windows on Arm |
| Android | `U:.../machines/waydroid-dock.py`, `ANDROID_INSTALL` in `machines.ts` | Android is **not** an Android VM: it is an Ubuntu cloud image whose cloud-init installs Waydroid (Android in an LXC container) under a kiosk compositor, phone-shaped display |
| Agent control | `U:.../machines/rfb-client.ts`, `machine-control.ts`, `input-motion.ts` | Host-side RFB client on the VNC socket: screenshots scaled to at most 1568 px on the long edge, typed text, key combos, pointer moves with eased motion so the browser can animate the agent's pointer |
| Console transport | `U:packages/umbreld/source/modules/server/machine-console-socket.ts`, `machine-console-sessions.ts`, `machine-audio-socket.ts` | WebSocket ↔ unix-socket pump with back-pressure limits; one controlling console per machine (a new one supersedes the old); audio captured from a loopback card |
| MCP tools | `U:packages/umbreld/source/modules/mcp/tools/machines.ts`, grants in `modules/mcp/mcp.ts` | Tools to list, get, update, delete, screenshot, control, list images and create machines; access is a per-credential grant (`machines: 'all' \| id[]`, `createMachines: boolean`), checked before each call, no approval step |
| Backups | `U:packages/umbreld/source/modules/backups/backups.ts` (machine section), `libvirt.ts` snapshot code | Before a backup, each running machine's disk is pivoted to a temporary external overlay so the base disk is stable; after it, the overlay is committed back. Downloaded images, install media and operation journals are excluded |
| OS packaging | `U:packages/os/umbrelos.Dockerfile` (virtualization block), `U:packages/os/qemu-machines.conf` | Installs libvirt (monolithic daemon, socket-activated), QEMU for x86 and Arm with the OpenGL module, OVMF, AAVMF, swtpm, wimtools, mtools; switches libvirt networks to nftables; adds loopback sound devices to QEMU's device ACL |
| UI | `U:packages/ui/src/features/machines/**` (routes, catalog, create wizard, spec form, settings, network mode, USB devices, console, fullscreen console, agent presence and pointer overlay, touch console) | Mounted inside the desktop layout as an immersive overlay; **owner-only** (`EnsureOwner` in `routes.tsx`) |
| Desktop integration | `U:packages/ui/src/modules/desktop/desktop-content.tsx` | Pinned machines are merged into the home-screen grid with apps and shortcuts |
| Browser console | `U:packages/ui/package.json` | `@novnc/novnc` 1.5.0; audio played by an AudioWorklet (`U:packages/ui/public/machine-audio-worklet.js`) |

### 1.3 Hypervisor and guest hardware

- **QEMU/KVM through libvirt**, connection `qemu:///system`. Domains are **transient** (`virsh create` from an XML file written per start), so libvirt holds no persistent config; umbreld's YAML is the only source of truth. This makes a restored machine portable between boxes.
- **Acceleration:** KVM when guest architecture equals host architecture and `/dev/kvm` exists, otherwise TCG (software emulation) with a warning in the UI. So an arm64 guest on an x86 box runs, slowly.
- **Platform profiles** pick chipset, NIC model, video and disk bus per guest era: modern x86 (q35, virtio), Windows 7, legacy x86, Windows 98 (ISA NE2000, VGA, floppy boot), modern arm64 (virt, GIC).
- **CPU:** `host-passthrough` under KVM. Windows 11 / Server / 7 guests get a set of Hyper-V enlightenments and a Hyper-V clock.
- **Firmware:** UEFI (OVMF/AAVMF, secure-boot variants for Windows) or BIOS for legacy guests. **TPM 2.0:** swtpm emulator with persistent state kept in the machine directory and bind-mounted where libvirt's AppArmor profile allows it.
- **Disk:** qcow2, `cache=none`, `discard=unmap`; virtio or SATA per profile. Imports `qcow2`, `raw`, `vmdk`, `vdi`, `vhdx`, `vhd` and converts with `qemu-img convert`. A disk may live in a Files folder (for example an external drive).
- **Memory:** virtio balloon with free-page reporting.
- **Security label:** dynamic AppArmor per domain; QEMU runs as the unprivileged `libvirt-qemu` user.

### 1.4 Display, "Windows/Linux/Android in a browser tab"

1. Each domain gets a **VNC server on a unix socket** in its runtime directory (no TCP port, share policy "allow exclusive").
2. The browser asks umbreld for a short WebSocket ticket (owner only, target `machines`; `U:packages/umbreld/source/modules/user/routes.ts`), then opens the console WebSocket. umbreld pumps bytes between it and the unix socket with 1 MiB/512 KiB back-pressure marks and an 8 MiB cap before it drops a slow client.
3. **noVNC** renders the framebuffer. A second open console takes control and the first is closed with a "superseded" code.
4. **Clipboard:** a `qemu-vdagent` channel with clipboard and server-side mouse is added for guests that run `spice-vdagent` (the Ubuntu and Fedora desktop images); the console checks whether the guest agent is connected before offering clipboard sharing.
5. **Audio:** QEMU plays into one substream of an ALSA loopback card (8 cards × 8 substreams = 64 slots); umbreld captures the paired side and streams PCM to an AudioWorklet in the browser. Legacy profiles get no sound card.
6. **3D:** for Linux desktop, Android and Omarchy guests, if the host has a DRM render node, the domain uses `egl-headless` graphics with a virtio-gpu device and `accel3d` (virgl). If start fails with GPU acceleration, it retries in software rendering.
7. **Touch console** for phones and tablets: on-screen keyboard, camera/pan, a separate RFB guest wrapper (`U:packages/ui/src/features/machines/touch/**`).
8. **Agent presence:** when an MCP agent sends input, the console shows which agent is driving and an animated pointer; a person must confirm before taking over, and control returns to people 60 s after the agent's last input (`AGENT_CONTROL_TIMEOUT_MS` in `machines.ts`).

### 1.5 Install flow (user-visible)

1. Owner opens Machines from the dock, picks an OS family from the catalog (Ubuntu, Fedora, Debian, Alpine, Android, Omarchy, Windows 11, Windows Server 2025, Windows 7, XP, 98) or "custom image" from Files.
2. Wizard: name, cores, memory, disk size, user name and password (Linux and Android) or licence key (Windows), network mode (NAT or LAN), optional disk folder.
3. The box downloads the image from the **upstream URL with a pinned SHA-256** (`safe-download.ts`), one download at a time, with progress.
4. Linux cloud images are booted with a generated cloud-init seed (user, packages such as the desktop and `spice-vdagent`); Windows media is rebuilt with an unattended answer file and virtio drivers.
5. The install state (`preparing`, `starting`, `setting-up`, `setup-delayed`, `ready-for-setup`) and progress show in the UI. The install source is recorded in the definition, so an interrupted install stays visible and can be retried instead of looking like a broken stopped machine.
6. The guest calls home over the private VM network with its one-time token when first-boot setup finishes (time-out 1 h, 4 h for Windows on Arm). Install media is ejected; a bridged machine then switches its NIC to the LAN bridge and its link is bounced.
7. The machine appears in the list with live CPU and memory use; it can be pinned to the home screen, set to autostart, resized, given port forwards (host ports 40000–49999) and USB devices.

### 1.6 Storage and networking

- **Where data lives:** one directory per machine under the umbreld data directory (definition, `disk.qcow2`, NVRAM, TPM state, media), plus a shared `machine-images` cache. Because it is under the normal data directory it is covered by umbrelOS backups (with the exclusions in §1.2).
- **Backups are crash-consistent**, not application-consistent: the overlay pivot (`virsh snapshot-create-as --disk-only --atomic --no-metadata`, then `blockcommit --active --pivot`) gives a stable base image while the guest keeps running; there is no guest freeze. A journal lets an interrupted backup be recovered on the next run.
- **NAT mode:** private libvirt network with an isolated port per machine (`<port isolated='yes'/>`) and libvirt's `clean-traffic` filter, so NAT machines cannot reach each other or spoof addresses. Port forwards are nftables DNAT rules on the LAN interface; Docker's `DOCKER-USER` chain gets an allow rule so its default DROP does not eat bridge traffic.
- **LAN mode:** a host bridge over the **wired** interface (Wi-Fi refused, since access points drop frames from unknown MACs). A bridged machine is an ordinary LAN device with no filtering, so it can run things like a DHCP server or Home Assistant OS discovery. It stays on NAT until first-boot setup is done.
- **USB passthrough:** live attach/detach (`virsh attach-device --live`), identification by vendor/product/serial and port, udev rules so host services leave assigned devices alone, explicit "take it from the host" consent when a drive is mounted in Files or an app uses the device.

### 1.7 GPU passthrough

**There is none.** At this commit there is no VFIO, IOMMU or PCI `hostdev` in umbreld (the only PCI `hostdev` string is a negative test fixture in `usb-devices.unit.test.ts`). What Umbrel calls GPU acceleration is **virgl paravirtual 3D** through the host's render node (§1.4 item 6). NVIDIA driver packages in the OS image (`U:packages/os/nvidia-driver-packages.sha256`) serve apps, not machines. USB accelerators (Coral) can be passed through as USB devices.

### 1.8 What is good, and what is weak

| Strong (we must at least match) | Weak (where we can beat it) |
|---|---|
| One-click Windows 11 with TPM, secure boot and drivers; Linux desktops with clipboard and sound | Owner-only: members of the household cannot have machines (`EnsureOwner`) |
| Checksum-pinned upstream images, recoverable interrupted installs | AI agents act directly on a standing grant; no per-change approval, and control of a Windows desktop is a very large grant |
| NAT isolation per machine and anti-spoofing; LAN mode for HAOS-style guests | Single box only; no placement on another node, no cold move between boxes |
| Live USB passthrough with host-use consent | Backups are crash-consistent and never proven to boot |
| Touch console; agent presence shown on screen | No PCI/GPU passthrough; no quotas; umbreld runs everything as root on the host |
| Transient domains: the definition file is the truth, restores move between boxes | Network mode and port forwards are host-wide nftables edits made by the same root process as the UI API |

---

## 2. What OneMind has today

| Area | State | Where |
|---|---|---|
| Any VM runtime | **None.** No KubeVirt, libvirt or QEMU in the image or the gateway | – |
| Plan for VMs | One row: "VMs [competitive parity] — KubeVirt (cluster) / libvirt (box)" | [docs/ARCHITECTURE.md](../ARCHITECTURE.md) (VM row, layer diagram) |
| Research | Umbrel Machines summary, Q296 answer and **REC-QB-02** ("VMs on x86 Pro and above only, host libvirt + swtpm as a signed system extension; keep KVM in the kernel contract; KubeVirt later"). Not done: Pi 5 KVM, KubeVirt on arm64, benchmark | [research-output/24-QUESTION-BANK-ANSWERS.md](../../research-output/24-QUESTION-BANK-ANSWERS.md), [research-output/02-competitors/umbrelos.md](../../research-output/02-competitors/umbrelos.md), [research-output/09-iot-mesh-offgrid-tak.md](../../research-output/09-iot-mesh-offgrid-tak.md) (HAOS as a VM, LAB-W8-6) |
| UI parity audit | Deployment kind **D8 Machine**: "P2, not planned for the core" | `docs/strategy/umbrel-parity.md` on `feat/ui-leap` (in flight) |
| k3s on every box | Yes; system manifests are copied into k3s auto-deploy at boot | `os/rootfs/layers/base/usr/lib/systemd/system/k3s.service`, `/usr/lib/onemind/manifests/` in the image |
| Base OS | Debian 13 kernel (x86_64, arm64), Raspberry Pi kernel on Pi 5; RAUC A/B | [docs/DECISIONS.md](../DECISIONS.md), `os/boards/`, `os/rootfs/Containerfile`, `os/versions.lock.yaml` |
| Capability detection | `internal/detect` reports board, TPM, secure boot, k3s, RAUC, NVIDIA GPU. **No `kvm` capability yet** | `internal/detect/detect.go`, `services.go` |
| Governed changes | Actions with `awaiting_approval`, owner approval, executor, hash-chained audit; only `app.install` / `app.remove` exist | `core/onemind_core/{actions,auth,audit,executors}.py`; contract §3, §11 |
| Kubernetes executor | `kubectl apply -k` into `app-<id>` namespaces | `core/onemind_core/executors.py` (`KubernetesExecutor`) |
| Planned machinery we will reuse | Install sandbox and `plan_sha256` (CORE-SANDBOX), passkey step-up (CORE-SEC-2), capability labels and placement (CORE-FABRIC-4), restic backups and verified restore (CORE-BACKUP), standing approvals (CORE-AUTO-3), MCP request-only writes (DEV-MCP-3), mesh and app proxy (CORE-NET on `feat/core-net`), design system and Home/dock (`ui/`, `feat/ui-leap`) | [docs/leap/BACKLOG.md](../leap/BACKLOG.md) |
| Dashboard | Home, Nodes, Market, Approvals, SignIn pages; no console component | `dashboard/src/pages/` |

So Machines is a green field for OneMind. Every building block it needs (approvals, placement, backups, mesh, design system) is already specified elsewhere in the leap.

---

## 3. Match and beat

### 3.1 Where OneMind matches Umbrel (parity bar for v1)

| Umbrel capability | OneMind v1 | How |
|---|---|---|
| Linux server and desktop guests from a curated list, checksum-pinned upstream downloads | Yes | Own catalog (§4.4), CDI import with SHA-256 check |
| Windows 11 with TPM 2.0 and secure boot, unattended install | Yes (x86 only) | KubeVirt persistent TPM and EFI with secure boot; own answer-file generator (MACH-6) |
| Browser console | Yes | noVNC (MPL-2.0, unmodified) over a gateway WebSocket broker to KubeVirt's VNC subresource |
| Custom image from Files (ISO, qcow2, raw, vmdk, vhdx) | Yes | CDI upload/import (qemu-img inside CDI does the conversion) |
| NAT with port forwards | Yes | KubeVirt `masquerade` binding + a Kubernetes Service, or the CORE-NET app proxy for HTTP |
| Machines on the home LAN | Yes, wired only | Multus + bridge CNI on a host bridge (MACH-7) |
| USB passthrough | Yes, applied on restart | KubeVirt `permittedHostDevices.usb` (MACH-8). Umbrel attaches live; KubeVirt does not hot-plug USB, so we say "takes effect after restart" honestly |
| Interrupted install stays visible and retryable | Yes | The action and the `Machine` row carry the install state; the health gate decides success |
| Pin a machine to Home | Yes | Machine tiles on Home/dock (`feat/ui-leap`) |
| Android | Later (MACH-16) | Linux guest + Waydroid, our own provisioning script |
| Clipboard, sound, virgl 3D, touch console | **Later** (MACH-14) | KubeVirt has none of these out of the box (§4.3). Gap stated, not hidden |

### 3.2 Where OneMind beats Umbrel

| # | Beat | Why it matters to the founder | Mechanism |
|---|---|---|---|
| B1 | **Agents ask, you approve, for machines too** | Umbrel lets an MCP credential with the machine grant drive a Windows desktop directly. OneMind turns "use this machine" into a time-boxed **control lease** that the owner approves on the phone, ends with one tap, and records input by input | `machine.control` action (§5.3), lease enforced in the gateway, every input in the audit chain |
| B2 | **Accounts for the whole house** | Each adult can have their own machines and consoles, within a quota the owner sets; guests get none; a console can be shared view-only | Per-principal ownership and quotas (§4.5), console tickets bound to the person |
| B3 | **Runs on any box in the house** | Put the Windows VM on the big box and the Linux router VM on the small one; move a stopped machine between boxes | KubeVirt + fabric capability labels (`kvm`, `iommu`, arch) and placement (CORE-FABRIC-4); cold move via backup/restore |
| B4 | **Backups that are proven to boot** | Umbrel's machine backup is crash-consistent and never tested | Guest-agent filesystem freeze when the agent is present (application-consistent), restic of the disk, then a weekly **scratch restore that boots** the copy in a sealed namespace and checks the guest agent or a non-black screen (ties into CORE-BACKUP-7) |
| B5 | **Deployments that never fail silently** | Every create/start is a plan the owner sees: CPU, RAM, disk, node, network exposure, USB and GPU devices | `plan_sha256` over the rendered KubeVirt objects (CORE-SANDBOX-2), preflight checks (§4.7), health gate, automatic clean-up of partial objects |
| B6 | **Real GPU passthrough on the Pro box** | Gaming or CAD Windows VM, or a Linux ML VM, using a whole RTX card | VFIO PCI passthrough with IOMMU checks (MACH-9); honest warning that the GPU leaves the host's AI apps while the machine runs |
| B7 | **Least privilege** | Umbrel's root daemon edits nftables, NetworkManager and udev from the same process that serves the UI | The gateway only writes Kubernetes objects through a scoped service account; KubeVirt's `virt-handler` is the one privileged component; machine pods run non-root under default-deny NetworkPolicy |
| B8 | **Same API everywhere** | The founder and other developers script machines like everything else | REST + CLI + MCP + SDK from one OpenAPI document, same action/approval model as apps |

---

## 4. OneMind design

### 4.1 Runtime decision: KubeVirt, not a home-made QEMU + noVNC service

| Criterion | **A. KubeVirt + CDI on k3s** (recommended) | B. Own QEMU + noVNC service (a pod or systemd unit per VM) | C. Host libvirt as a system extension (REC-QB-02) |
|---|---|---|---|
| Fits OneMind's model (k3s, objects, `plan_sha256`, RBAC, NetworkPolicy) | Native: a machine is a `VirtualMachine` object the sandbox can render and hash | Partly: we invent our own object model | No: a second control plane beside k3s, like Umbrel |
| Multi-box placement and moves | Built in (scheduler, node labels) | We build it | We build it |
| Windows 11 (TPM, secure boot, EFI vars) | Persistent TPM and EFI supported (x86); needs a filesystem PVC for state | We build it (swtpm, OVMF wiring) | libvirt does it |
| Console | VNC WebSocket subresource on the Kubernetes API, ready for a broker | We expose QEMU's VNC socket ourselves | Same as Umbrel |
| Audio, clipboard, virgl 3D | Not provided; possible later through a hook sidecar that edits the domain XML (alpha feature) | Full control | Full control |
| USB passthrough | Yes, configured per node, restart to apply | Full control, live | Live |
| PCI/GPU passthrough | Yes (`permittedHostDevices.pciHostDevices`), VFIO | We build it | libvirt does it |
| Live migration | Possible with shared storage; not a v1 goal | No | No |
| Memory overhead on the box | Highest (operator, API, controller, per-node handler, CDI; **UNVERIFIED estimate 0.6–1 GiB**, MACH-1 measures) | Lowest | Low |
| Code OneMind must own | Smallest: API, broker, catalog, UI | Largest: we would be rewriting KubeVirt/libvirt glue (what Umbrel's 18k lines are) | Medium, and duplicates k3s concerns |
| Licence | Apache-2.0 (KubeVirt, CDI) | Our own + QEMU (GPL-2.0, separate binary) | LGPL-2.1+ libvirt (separate) |

**Decision proposed (founder call F-MACH-1):** A, KubeVirt, as an **optional signed extension** that is downloaded and enabled only when the owner turns Machines on, so boxes that never run a VM pay no RAM or image size. B stays the fallback if MACH-1 shows KubeVirt's overhead is unacceptable on the Lite box; the gateway API (§5) is written against a small `MachineRuntime` interface so the fallback would not change the contract. This updates REC-QB-02 ("libvirt on the box, KubeVirt later"): since the leap put k3s on every box and built approvals around Kubernetes objects, one runtime for both box and cluster is cheaper than two.

### 4.2 Components and licences

Versions are **candidates**; MACH-2 pins exact versions and digests in `os/versions.lock.yaml` and re-checks each licence at that pin. Nothing below is copied into our source tree; upstream images and packages are shipped unmodified.

| Component | Role | Candidate pin | Licence | Distribution note |
|---|---|---|---|---|
| KubeVirt (`virt-operator`, `virt-api`, `virt-controller`, `virt-handler`, `virt-launcher`) | VM runtime on k3s | newest v1.6.x or later patch release at pin time | Apache-2.0 | Upstream images by digest. `virt-launcher` contains QEMU (GPL-2.0), libvirt (LGPL-2.1+), swtpm (BSD-3-Clause), EDK2 firmware (BSD-2-Clause-Patent): if we mirror these images to our registry we also publish the corresponding source offer (GPL-2.0 §3) |
| Containerized Data Importer (CDI) | Import, upload and convert disk images into PVCs; SHA-256 check | v1.62.x or later | Apache-2.0 | Upstream images by digest; contains `qemu-img` (GPL-2.0) |
| `virtctl` | Not shipped to users; used in lab kits only | matches KubeVirt pin | Apache-2.0 | Lab only |
| Multus CNI (thin) | Second NIC for LAN-bridged machines | v4.2.x | Apache-2.0 | Enabled only when LAN mode is first used |
| CNI reference plugins (`bridge`) | Attach to the host bridge | v1.7.x | Apache-2.0 | k3s already ships some CNI plugins; pin the one we use |
| noVNC (`@novnc/novnc`) | Browser console | 1.5.0 or later | MPL-2.0 (bundled `pako` MIT) | npm dependency, **unmodified**; MPL is file-level copyleft, so any change to a noVNC file is published as source |
| QEMU guest agent, `spice-vdagent` | Inside guests (freeze, IP report, clipboard later) | guest distro packages | GPL-2.0+ | Installed by cloud-init from the guest's own repositories; not shipped by OneMind |
| virtio-win drivers | Windows guests | upstream release at pin | Mixed Red Hat terms (to verify at pin) | **Downloaded by the box from upstream on demand**, checksum-pinned; never rehosted until the licence is confirmed |
| Waydroid | Android inside a Linux guest | upstream repo | GPL-3.0 | Installed inside the guest from upstream; not shipped by OneMind |
| Guest OS images (Ubuntu, Debian, Fedora, Alpine cloud images; Windows ISOs) | Machine templates | per-image pin with SHA-256 | Each vendor's terms and trademarks | Downloaded by the box from the vendor; OneMind ships only the URL and checksum. Windows needs the person's own licence or an evaluation ISO under Microsoft's terms |
| OneMind gateway machines module, console broker, catalog, UI, CLI, MCP tools | Our code | – | Apache-2.0 (repo licence) | SPDX header on every new file |

### 4.3 Architecture

```
Dashboard (ui/, noVNC) ──REST──► gateway /v1/machines ──(action → approve → executor)──► k3s API
        │                              │   renders VirtualMachine + DataVolume + Service + NetworkPolicy
        │                              │   (sandbox allowlist, plan_sha256)
        └──WSS /v1/machines/{id}/console?ticket=…──► gateway console broker ──WSS──► KubeVirt vnc subresource ──► virt-launcher (QEMU VNC)
Phone app ── same REST; console via the same broker (touch layer later)
CLI / SDK / MCP ── same REST; MCP machine tools are read + request only; screen/input only inside an approved control lease

Namespaces: onemind-machines (KubeVirt, CDI system), machines-<owner_principal> (each person's machines, default-deny NetworkPolicy, ResourceQuota)
Storage:    DataVolume → PVC on `onemind-local` (Retain, CORE-BACKUP-1); TPM/EFI state → small filesystem PVC
Network:    pod network + masquerade (NAT) by default; LAN mode = Multus NetworkAttachmentDefinition on a host bridge over the wired NIC
Placement:  nodeSelector/affinity from fabric labels: onemind.io/kvm=true, onemind.io/arch, onemind.io/iommu, onemind.io/gpu-passthrough
```

- **The gateway never talks to QEMU.** It writes Kubernetes objects with a service account whose RBAC covers only KubeVirt/CDI kinds in `machines-*` namespaces plus the `vnc`, `freeze`, `unfreeze`, `start`, `stop`, `restart` subresources.
- **The console broker** lives in the gateway: it validates a 30-second single-use ticket bound to (person, machine, mode `control|view`), opens KubeVirt's VNC WebSocket with the gateway's service account, and pumps bytes with back-pressure limits. One controller per machine; any number of view-only viewers (the broker drops their input messages). An approved agent lease is a third mode (`agent`) that the broker can see, so the console shows "an agent is driving" and the person can take over or end the lease.
- **Desktop extras (MACH-14):** clipboard, sound and virgl need QEMU options KubeVirt does not expose. The path is a OneMind **hook sidecar** (our own small Go binary, KubeVirt's alpha `Sidecar` feature) that adds a `qemu-vdagent` channel, an audio device and, on hosts with a render node, `egl-headless` + virtio-gpu 3D. It ships only after a lab test on each KubeVirt pin, because it depends on an alpha interface. Audio to the browser then needs our own capture path; noVNC has no audio, so the broker would carry a second stream. Until then the UI says plainly that sound and clipboard are not available.

### 4.4 Data model

**Gateway record** (ledger table `machines`, one migration in MACH-3):

```json
{
  "id": "mch_01JD0Q7Z…",
  "name": "Dad's Windows",
  "owner_principal": "person:dad",
  "template_id": "windows-11-x64",
  "arch": "amd64",
  "state": "running",
  "install": {"state": "done", "progress": 100, "action_id": "act_…"},
  "resources": {"cores": 4, "memory_mib": 8192, "disk_gib": 80},
  "firmware": {"kind": "uefi", "secure_boot": true, "tpm": true},
  "network": {"mode": "nat", "forwards": [{"protocol": "tcp", "guest_port": 3389, "exposure": "lan"}]},
  "devices": {"usb": [{"vendor_id": "1a86", "product_id": "55d4", "serial": null}], "gpu": null},
  "placement": {"node_id": "node_…", "pinned_node": false},
  "autostart": false,
  "pinned_home": true,
  "acceleration": "kvm",
  "guest_agent": {"connected": true, "ip_addresses": ["…"]},
  "backup": {"policy": "daily", "last_snapshot_id": "snap_…", "verified_at": "2026-11-12T03:00:00Z"},
  "created_at": "…",
  "kube": {"namespace": "machines-person-dad", "vm": "mch-01jd0q7z"}
}
```

- The **Kubernetes objects are derived** from this record by a pure render function (like Umbrel's transient domains, the record is the truth; unlike Umbrel, the rendered objects are hashed and approved).
- **Template catalog** (`sdk/machines/catalog.yaml`, our own file, own schema `sdk/schema/onemind.machine-template.schema.json`): `id`, `family`, `display_name`, `version`, `arch`, `source: {url, sha256, format}`, `firmware`, `min: {cores, memory_mib, disk_gib}`, `provision: cloud-init | windows-unattend | none`, `licence_note`, `desktop: bool`, `pi_supported: bool`. Entries are written by us from the vendors' own release pages; nothing is taken from Umbrel's catalog. CI checks every URL and checksum weekly (same idea as the app pipeline's pin checks).
- **Secrets:** guest password and Windows product key are **write-only**: they go into a Kubernetes Secret used by the cloud-init or answer-file volume, are deleted after first boot (guest calls home with a one-time token, as the CORE-SEC token rules define), and are never returned by `GET`.

### 4.5 Accounts for the whole house

| Role | Machines |
|---|---|
| owner | Create, run and delete any machine; set household quotas; approve requests; enable LAN mode, USB and GPU passthrough |
| adult | Own machines inside their quota (default 4 cores, 8 GiB RAM, 100 GiB disk; owner-set); console to their own; LAN mode, USB and GPU still need the owner's approval |
| guest | None by default; the owner may share one machine view-only or with control |
| agent / plugin / automation | Read machines they are granted; **request** lifecycle actions; never approve; screen and input only inside an approved control lease |

Each person's machines live in their own namespace with a `ResourceQuota`, so a quota is enforced by Kubernetes, not only by the UI.

### 4.6 Security

- **Isolation:** each machine pod has default-deny ingress and egress NetworkPolicy, then explicit allows: DNS, the internet (on by default for NAT machines; owner can turn it off), the gateway's first-boot endpoint, and each port forward. Machines in NAT mode cannot reach each other or the box's own services unless a rule says so. LAN-bridged machines are ordinary LAN devices with no filtering (same as Umbrel); the approval card says so.
- **Privilege:** only `virt-handler` (DaemonSet) and CDI's importer run with extra privileges; `virt-launcher` runs non-root (KubeVirt default). The install sandbox allowlist (CORE-SANDBOX-1) gets a **machines profile**: KubeVirt and CDI kinds in `machines-*` namespaces only, no `hostDevices` unless the action type is `machine.devices.update` and the owner approved it.
- **Console:** WebSocket only through the gateway, TLS (CORE-SEC-1), tickets single-use and bound to person + machine + mode; idle consoles closed after 30 min; every console open/close audited.
- **Agent control lease (`machine.control`):** parameters `{machine_id, duration_s ≤ 3600, purpose}`; risk `sensitive`; needs the owner's passkey (CORE-SEC-2); never covered by standing approvals; the person can end it from the console or the phone at any time; each input (type, coordinates, key names; typed text is stored only as length + hash, because the gateway cannot tell whether the guest field is a password) and each screenshot hash go into the audit chain. The lease never grants clipboard, USB, network or settings changes.
- **Devices:** USB and PCI passthrough are separate actions; the plan shows the exact device (vendor, product, serial, PCI address, IOMMU group members). A device used by the host (mounted disk, NVIDIA GPU in use by apps) is refused until the person confirms taking it.
- **Images:** every template download is SHA-256 checked by CDI; custom uploads are marked "untrusted image" on the card; Windows activation keys never leave the Secret.
- **Kill switch:** the CORE-SEC kill switch also stops all agent leases and pauses machine actions in flight.

### 4.7 Deployments that never fail silently

Preflight (in the plan, before approval): KVM present on a matching-architecture node; free RAM ≥ requested + 512 MiB headroom; free disk ≥ disk size + image size; template checksum known; quota left; device available; LAN mode only on a wired node. Any failure is a `would_be_refused` reason in the preview, not a broken machine.

Health gate (after approval): the action succeeds only when the VMI is `Running` **and** either the guest agent connects or the first framebuffer is not blank within the template's time-out (Linux 15 min, Windows 60 min). On failure the action is `failed` with the step that failed; partially created objects are removed unless the owner chose "keep for debugging"; the disk is never deleted by a failed install of an existing machine.

### 4.8 API surface (proposal for the contract PR)

In the style of [dev/API.md](../leap/dev/API.md): kinds R (read), W (direct owner write, audited), Q (request: creates an action, `202`).

| Method and path | Kind | Scope | Who | Body / returns |
|---|---|---|---|---|
| `GET /v1/machines/capabilities` | R | `machines:read` | any | per node: `kvm`, `arch`, `iommu`, `gpu_passthrough`, `lan_bridge: {available, reason}`, `extension: enabled\|disabled` |
| `GET /v1/machines` | R | `machines:read` | owner: all; others: own and shared | list of machine records; `?owner&state&node_id` |
| `GET /v1/machines/{id}` | R | `machines:read` | as above | one record + live usage |
| `GET /v1/machines/templates` | R | `machines:read` | any | catalog entries for the box's architectures, with `download_state` |
| `POST /v1/machines` | Q | `machines:request` | owner, adult, agent | `{name, template_id \| upload_id, resources, network, credentials?}` → `202` `machine.create` (risk `write`) |
| `POST /v1/machines/{id}/start` · `/stop` · `/restart` | Q | `machines:request` | owner, machine owner, agent, automation | `{force?: bool}` → `202` `machine.start` / `.stop` / `.restart` (risk `write`; `force` stop is `sensitive`) |
| `PATCH /v1/machines/{id}` | Q | `machines:request` | owner, machine owner, agent | resources, name, autostart, forwards → `202` `machine.update` |
| `PUT /v1/machines/{id}/devices` | Q | `machines:request` | owner, machine owner, agent | `{usb: [...], gpu: {pci_address} \| null}` → `202` `machine.devices.update` (risk `sensitive`, owner approval) |
| `PUT /v1/machines/{id}/network` | Q | `machines:request` | owner, machine owner, agent | `{mode: nat\|lan}` → `202` `machine.network.update` (`lan` is `sensitive`) |
| `DELETE /v1/machines/{id}` | Q | `machines:request` | owner, machine owner, agent | `{keep_disk: bool}` → `202` `machine.delete` (risk `destructive`, step-up) |
| `POST /v1/machines/{id}/control` | Q | `machines:control` | agent | `{duration_s, purpose}` → `202` `machine.control` (risk `sensitive`, passkey) |
| `DELETE /v1/machines/{id}/control` | W | `machines:read` | owner, machine owner, the agent itself | ends a lease at once (always safe) |
| `POST /v1/machines/{id}/console-tickets` | W | `machines:console` | person with access | `{mode: control\|view}` → `{ticket, expires_at}` (30 s, single use) |
| `GET /v1/machines/{id}/console` | WebSocket | ticket | – | RFB bytes |
| `GET /v1/machines/{id}/screen` | R | `machines:control` | agent with an active lease; owner | PNG, long edge ≤ 1600 px, `{width, height, sequence}` headers |
| `POST /v1/machines/{id}/input` | W | `machines:control` | agent with an active lease | `{kind: key\|text\|pointer\|scroll\|wait, …}`; refused with `409 lease_required` without a lease |
| `POST /v1/machines/uploads` | W | `machines:request` | owner, adult | resumable upload of an image from Files → `{upload_id}` |
| `PUT /v1/machines/quotas/{principal}` | W | `machines:admin` | owner | `{cores, memory_mib, disk_gib}` |
| `POST /v1/machines/enable` | Q | `machines:admin` | owner | → `202` `machines.enable` (download and start the KubeVirt extension; risk `sensitive`) |

**New scopes** (§8.2 of API.md): `machines:read` (all), `machines:request` (person, agent, automation), `machines:console` (person only), `machines:control` (agent only, effective only inside an approved lease), `machines:admin` (owner). **Never grantable to an agent:** `machines:console`, `machines:admin`.
**Events** (`/v1/events`): `machine.state_changed`, `machine.install_progress`, `machine.control_started`, `machine.control_input` (metadata only), `machine.control_ended`, `machine.console_opened`.

### 4.9 CLI and MCP

**CLI** (`cmd/onemind/cli/machines.go`, the core branch writes it per WORKSTREAMS §3):

| Command | Calls |
|---|---|
| `onemind machines list [--owner P] [--json]` | `GET /v1/machines` |
| `onemind machines info <id>` | `GET /v1/machines/{id}` |
| `onemind machines templates` | `GET /v1/machines/templates` |
| `onemind machines create --template T --name N [--cores C --memory 8G --disk 80G] [--lan] [--wait] [--no-approve]` | `POST /v1/machines`, then the approval flow (owner shortcut `approve: true` unless `--no-approve`) |
| `onemind machines start\|stop\|restart <id> [--force]` | lifecycle requests |
| `onemind machines usb <id> --add VID:PID[:SERIAL] \| --remove …` | `PUT …/devices` |
| `onemind machines rm <id> [--keep-disk]` | `DELETE /v1/machines/{id}` (step-up prompt) |
| `onemind machines console <id> [--view]` | ticket, then opens the dashboard console URL (no local VNC client) |

**MCP** (one PR agreed with the MCP stream owner, as `mcp/catalog.py` is theirs):

| Tool | Scope | Same as |
|---|---|---|
| `list_machines` | `machines:read` | `GET /v1/machines` |
| `get_machine` | `machines:read` | `GET /v1/machines/{id}` |
| `list_machine_templates` | `machines:read` | `GET /v1/machines/templates` |
| `request_action` with `type` `machine.create`, `machine.start`, `machine.stop`, `machine.restart`, `machine.update`, `machine.delete` | `actions:request:machine.<verb>` | the matching `Q` route |
| `request_machine_control` | `actions:request:machine.control` | `POST /v1/machines/{id}/control` |
| `get_machine_screen` | `machines:control` (active lease) | `GET …/screen` |
| `send_machine_input` | `machines:control` (active lease) | `POST …/input` |
| `end_machine_control` | always, for its own lease | `DELETE …/control` |

`machine.devices.update`, `machine.network.update` and `machines.enable` are requestable only by persons, not agents (added to the never-requestable list in DEV-MCP-3).

### 4.10 UI screens (on `ui/` components, Home/dock from `feat/ui-leap`)

1. **Machines** list: cards with state pill, owner avatar, node, CPU/RAM meters, "agent driving" badge; empty state explains what a machine is and whether this box can run one (from capabilities).
2. **New machine:** template gallery (our own art and names) → size form with quota meter → network (NAT / home network, with the trust note) → **plan card** (CPU, RAM, disk, node, exposure, devices, licence note) → approve with passkey.
3. **Install progress** on the card and in the floating job indicator; failed step and "retry" or "remove".
4. **Console:** full-window noVNC with toolbar (keyboard combos, scale, view-only indicator, take control, fullscreen); agent banner with "end agent control"; touch layer later.
5. **Settings:** resources, autostart, port forwards with exposure tier (LAN / mesh / public via CORE-NET), USB and GPU devices with host-use warnings, backups (policy, last verified boot), sharing with household members, delete (keep disk).
6. **Home/dock:** pin a machine as a tile that opens its console.
7. **Settings → Machines:** enable the extension, quotas per person, LAN bridge status.

### 4.11 Raspberry Pi 5 feasibility

| Question | Expectation | Status |
|---|---|---|
| KVM on Pi 5 | The Raspberry Pi kernel builds KVM for BCM2712 (Cortex-A76); arm64 guests run with KVM | **To verify** (LT-MACH-3) on our image's Pi kernel |
| Page size | The Pi 5 default kernel uses 16 KiB pages; KubeVirt and QEMU are tested mainly on 4 KiB hosts. Fallback: boot the 4 KiB-page kernel variant on boxes that enable Machines | **Risk; to verify** (LT-MACH-3) |
| KubeVirt on arm64 | Supported upstream with limits: UEFI boot only, no secure boot/SMM, fewer device models | Documented upstream; **not tested by us** |
| RAM budget (16 GB Pi 5) | k3s + OneMind base (CORE-NET §14 targets) + KubeVirt/CDI **UNVERIFIED estimate 0.6–1 GiB** + one 2 GiB Linux server VM fits; a desktop VM with software rendering fits but is slow | **Estimate**, LT-MACH-2 measures |
| RAM budget (8 GB Pi 5) | One small headless Linux VM (≤ 1 GiB); no desktops | Estimate |
| Windows on Pi | **Not offered.** Windows 11 on Arm needs TPM + secure boot, which KubeVirt does not give arm64 guests, and the Pi has 4 cores | Decision |
| Android on Pi | Waydroid in an arm64 Linux guest with software rendering: possible, slow; **experimental** flag | To verify (MACH-16) |
| x86 guests on Pi | Software emulation only; hidden from the template list (Umbrel shows a performance warning instead) | Decision |
| Storage | NVMe HAT required; SD cards refused as a machine disk target | Decision |

Tier summary: **Edge (Pi 5)** headless Linux VMs only (HAOS, small routers, test boxes), if LT-MACH-3 passes; **Lite (N150/N300)** Linux and Windows 11, one desktop at a time; **Pro** everything, including GPU passthrough.

### 4.12 Lab tests

| Id | Test | Pass rule |
|---|---|---|
| LT-MACH-1 | KubeVirt + CDI install from the signed extension on the Dell 5540 and an N150 box | All components ready in ≤ 5 min; removing the extension leaves no pods, CRDs or webhooks |
| LT-MACH-2 | Idle overhead of KubeVirt + CDI (RSS, CPU) on x86 and Pi 5 | Recorded; **x86 ≤ 1 GiB, Pi 5 ≤ 800 MiB** or F-MACH-1 is reopened |
| LT-MACH-3 | Pi 5 with our Pi kernel: KVM present, Ubuntu arm64 cloud image boots under KubeVirt, 16 KiB vs 4 KiB page kernel | Boot to guest agent in ≤ 3 min on at least one kernel variant |
| LT-MACH-4 | Windows 11 x64 unattended install with TPM + secure boot on the Lite box | Reaches the desktop with no clicks; `tpm.msc` shows TPM 2.0 |
| LT-MACH-5 | HAOS VM in LAN mode with a USB Zigbee stick (with the research-09 LAB-W8-6) | Device commissions; HAOS is discovered on the LAN |
| LT-MACH-6 | Backup with guest freeze, restore on the other box, boot check | Restored machine boots and its guest agent reports within the gate |
| LT-MACH-7 | GPU passthrough on the Pro box (RTX) to a Windows guest | Driver loads in the guest; host apps see the GPU again after the machine stops |

---

## 5. Epics

Proposed new stream **Machines** (branches `feat/machines-<n>-<slug>`), to be added to [WORKSTREAMS.md](../leap/WORKSTREAMS.md) §2 in the leap-docs stream's next PR. It owns `core/onemind_core/machines/**`, `sdk/machines/**`, `sdk/schema/onemind.machine-template.schema.json`, `dashboard/src/pages/Machines*.tsx`, `dashboard/src/machines/**`, `test/machines/**`. Files owned by other streams change only through those streams, as listed per epic. Whether Machines enters the leap or waits until after it (the parity audit has D8 as P2) is founder call **F-MACH-2**.

| Id | Title | Size | Owner paths | Acceptance (tests) | Depends on |
|---|---|---|---|---|---|
| MACH-0 | Contract: machine routes, scopes, action types, events | S | `sdk/contracts/poc-v0.md` (hotspot, contract owner, `contract/12-machines`) | Contract PR merged; schema lint passes; API.md §8.2 scope table and §5.12 risk table list the new entries | C12-A |
| MACH-1 | Lab kit and feasibility (LT-MACH-1…3) | M | `lab-kits/machines/**` (image and hardware stream merges), results in `research-output/evidence/lab/machines/` | LT-MACH-1, -2, -3 results recorded; F-MACH-1 confirmed or reopened | none |
| MACH-2 | KubeVirt + CDI signed extension and `kvm`/`iommu` capabilities | M | `os/rootfs/layers/machines/**`, add-only pins in `os/versions.lock.yaml` (image stream); `internal/detect/**` capability fields after CORE-FABRIC-4 | Extension enable/disable is idempotent; pins by digest with licence recorded; heartbeat shows `kvm` on the Dell and not in a VM without nested virt | MACH-1, CORE-FABRIC-4, CORE-UPDATE (extension signing) |
| MACH-3 | Gateway machines module: records, render, executor hook, health gate | L | `core/onemind_core/machines/**`, one ledger migration, one line in `routes.py`, one executor hook through the sandbox owner | Render is pure and golden-tested; `plan_sha256` changes when any resource changes; failed install cleans up; agent `approve: true` → 403; kind `fake-kubevirt` integration test creates/starts/stops/deletes | MACH-0, CORE-SANDBOX-2, DEV-API-1 |
| MACH-4 | Console broker and dashboard console | M | `core/onemind_core/machines/console.py`, `dashboard/src/machines/console/**`, `dashboard/package.json` noVNC pin (one PR with the dashboard owner) | Ticket reuse refused; expired ticket refused; second controller supersedes first; view-only input dropped; slow client cut at the buffer cap; WCAG checks on the toolbar | MACH-3, CORE-SEC-1 |
| MACH-5 | Template catalog and image import/upload | M | `sdk/machines/catalog.yaml`, `sdk/schema/onemind.machine-template.schema.json`, `.github/workflows/machines-catalog.yml` (new) | Weekly job verifies every URL and SHA-256; wrong checksum → import fails and no PVC remains; upload from Files resumes after a dropped connection | MACH-3 |
| MACH-6 | Windows guests (TPM, secure boot, own answer-file generator, virtio drivers on demand) | M | `core/onemind_core/machines/windows/**` | LT-MACH-4 passes; product key never in any `GET` or log (gitleaks + response test) | MACH-5 |
| MACH-7 | Networking: NAT + forwards, NetworkPolicy, LAN bridge | M | `core/onemind_core/machines/network.py`; host bridge unit via image stream; exposure through CORE-NET app proxy | NAT machines cannot reach each other or box services (netpol test); forward reachable only at its exposure tier; LAN mode refused on Wi-Fi-only nodes; LT-MACH-5 | MACH-3, CORE-NET (mesh and app proxy) |
| MACH-8 | USB passthrough | S | `core/onemind_core/machines/devices.py`; `permittedHostDevices` config via MACH-2 layer | Device in use by the host is refused until confirmed; restart applies it; plan shows vendor/product/serial | MACH-3, MACH-2 |
| MACH-9 | GPU (PCI/VFIO) passthrough on Pro | M | `core/onemind_core/machines/devices.py`, IOMMU detection in `internal/detect/**` after CORE-DOGFOOD-5 | LT-MACH-7; IOMMU group with other devices → refused with the group listed; GPU returned to host after stop | MACH-8, CORE-DOGFOOD-5 |
| MACH-10 | Backups with guest freeze and verified boot restore | M | hook in `internal/backup/**` through the backups owner; `core/onemind_core/machines/backup.py` | Freeze/thaw around the snapshot when the agent is present; LT-MACH-6; badge turns green only after a boot check | MACH-3, CORE-BACKUP-5, CORE-BACKUP-7 |
| MACH-11 | MCP tools and agent control lease | M | tool projection PR in `core/onemind_core/mcp/**` agreed with the MCP stream; lease logic in `core/onemind_core/machines/control.py` | `get_machine_screen` without a lease → `lease_required`; lease ends on owner tap within 1 s; inputs audited without typed text; never-requestable list includes devices/network/enable | MACH-4, DEV-MCP-3, CORE-SEC-2 |
| MACH-12 | Household accounts, sharing and quotas | S | `core/onemind_core/machines/quotas.py` | Adult over quota → plan refused; guest cannot open a console unless shared; ResourceQuota objects match the record | MACH-3, CORE-SEC-10 (identity) |
| MACH-13 | Dashboard screens (list, wizard, plan card, settings, Home tile) | M | `dashboard/src/pages/Machines*.tsx`, `dashboard/src/machines/**`, one route line in `App.tsx` (hotspot) | Screens render from fixtures; plan card shows every field of §4.7; no Umbrel asset or string (review checklist item) | MACH-3, CORE-DASH-1 |
| MACH-14 | Desktop extras: clipboard, sound, virgl, touch console | L | `core/onemind_core/machines/sidecar/**` (Go hook binary), `dashboard/src/machines/console/**` | Per KubeVirt pin: hook test passes or the feature is off; clipboard only when the guest agent is connected; sound latency measured | MACH-4, LT on each KubeVirt pin |
| MACH-15 | CLI `onemind machines` | S | `cmd/onemind/cli/machines.go`, one line in `root.go` (hotspot) | Golden output tests; `--json` stable; exit codes per CLI.md | MACH-3, DEV-CLI-1 |
| MACH-16 | Android template (Linux guest + Waydroid, our own provisioning) | S | `sdk/machines/provision/android/**` | Boots to the Android launcher on x86; Pi flagged experimental with a recorded result | MACH-5, MACH-14 (for usable graphics) |

**Order:** MACH-1 first (it can kill or confirm the runtime choice), then MACH-0 → MACH-2 → MACH-3 → MACH-4/5 → MACH-13 (first usable release: Linux machines with a console), then MACH-6, -7, -8, -10, -11, -12, -15, and last MACH-9, -14, -16.

## 6. Decisions needed

| Id | Question | Proposal |
|---|---|---|
| F-MACH-1 | Runtime: KubeVirt extension, own QEMU service, or host libvirt | KubeVirt as an optional signed extension; reopen if LT-MACH-2 fails |
| F-MACH-2 | Does Machines enter the leap, or wait until after it | After the leap's S1 core (sandbox, passkeys, fabric labels); MACH-1 lab work can start now |
| F-MACH-3 | Pi tier: offer headless Linux machines on Pi 5 | Yes on 16 GB only, if LT-MACH-3 passes; never Windows |
| F-MACH-4 | Ship the 4 KiB-page Pi kernel on Machines-enabled Pi boxes if 16 KiB fails | Only if LT-MACH-3 needs it; it is an image change owned by the image stream |
