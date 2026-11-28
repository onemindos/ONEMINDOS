<!-- SPDX-License-Identifier: Apache-2.0 -->
# Founder note 09: why our own OS, distro vs image, update engines, k3s, phones and the gateway

**For:** Zeus · **Date:** 2026-11-24
**Status:** founder-requested learning entry. It adds no decision and reopens none. Where it states an opinion, it says so; where it states a fact, it points to the research file that holds the evidence.
**Feeds:** D-007 (base OS), D-012/D-013 (bootc Pi 5 test before G1, 2026-12-13), ADR-001 D1/D3/D6, M-LIVE, brief 30 workstream B9 (gateway).

---

## 1. Are we crazy for building our own OS?

**No, because we are not building an OS from scratch.** OneMind OS is an *appliance image*: Debian 13 plus a fixed set of proven parts (RAUC, k3s, NATS, restic), sealed into one read-only image that updates itself safely. Home Assistant OS, umbrelOS and TrueNAS made the same bet.

**Why it is a good idea**
1. The promise ("plug it in, updates never brick it, AI never acts without your OK") cannot be kept from inside someone else's OS.
2. A/B updates with rollback only work if we own the image.
3. A read-only base means every box matches what we tested, so support stays small.
4. The gateway's guarantee only holds if an AI cannot reach around it, which needs control of the OS.
5. The hard parts (kernel, drivers, packages) come from Debian; we own the glue and the product.

**Where it risks being overkill (opinion)**
- Too many targets at once: Debian, the Ubuntu CI hedge, Jetson L4T, RHEL bootc for industrial, mobile, desktop, the fabric.
- Ten plugin sockets (E1–E10) before real apps push on them.
- Process (PR trains, CI fleets) ahead of the product. M-LIVE is the cure: one board, one update path, a few apps used daily.

---

## 2. Distro vs image

- **A distro is a pantry plus a cookbook.** Debian keeps about 60,000 packages patched, with about 1,000 volunteers and a security team. You install it and assemble your own system with `apt`; no two machines stay alike.
- **An image is a frozen meal made from that pantry.** You pick the packages, add your own, seal it read-only and ship the same bytes to every box. Updates replace the whole thing, with rollback.

**One-line test:** if users change the system with `apt install`, it is a distro. If everyone gets the same sealed system and updates replace it whole, it is an image.

**How OneMind does it** ([`os/rootfs/Containerfile`](../../../os/rootfs/Containerfile)):
1. `FROM debian:trixie@sha256:…` plus a Debian package snapshot pinned by date ([`os/rootfs/debian.args`](../../../os/rootfs/debian.args)), so every build pulls the same packages.
2. Package lists in [`os/rootfs/packages/`](../../../os/rootfs/packages/) choose what goes in.
3. OneMind adds its own RAUC build, k3s, the gateway, `onemindd` and the dashboard.
4. [`os/assemble/`](../../../os/assemble/) turns the tree into a sealed A/B disk image.

**Why not our own distro, even with AI?** AI makes writing packages cheap, but a distro is a daily duty: watch every package for security holes, rebuild, test on every chip, ship fixes within hours, and earn a place on the private early-warning lists for embargoed bugs (that takes years of trust, not code). Small teams fall behind (PureOS stayed on Debian 11 while Debian moved on). Users would never see the work. The snapshot pin, the package lists and building our own copies of key parts (as we already do for RAUC) give us most of a distro's control without the cost. Complexity of our own distro, ongoing: about 8/10 (opinion).

### All the paths to an OS product

| # | Path | Example | Fit for OneMind |
|---|---|---|---|
| 1 | From scratch | Fuchsia, SerenityOS | No |
| 2 | Build every program from source (Buildroot, Yocto) | Home Assistant OS, balenaOS | Possible, needs a bigger team (§4) |
| 3 | Own distro (fork) | Ubuntu, Pop!_OS, PureOS | No: a team of its own |
| 4 | **Image on a distro (us)** | SteamOS 3 (Arch), ChromeOS (Gentoo), umbrelOS (Debian) | Yes |
| 5 | Container-image OS (bootc, OSTree) | Fedora Atomic, Bazzite, RHEL image mode | Close cousin; our build already starts from a Containerfile |
| 6 | Declarative OS | NixOS | Powerful, steep |
| 7 | Minimal Kubernetes OS | Talos, Flatcar, Bottlerocket | Maybe for extra worker nodes later |
| 8 | Software on someone's OS | CasaOS, YunoHost | A possible extra "try it" door, never the product |
| 9 | Virtual appliance | VM files | An extra format of path 4 (we build an OVA) |

### Where other names fit

| Name | Distro or image | Built on |
|---|---|---|
| Fedora | Distro (Atomic editions are images) | Itself; upstream of RHEL |
| CentOS Stream | Distro | Fedora; preview of the next RHEL |
| AlmaLinux, Rocky Linux | Distro | RHEL sources (free rebuilds) |
| NixOS | Declarative distro | Itself |
| Bazzite | Image | Fedora Atomic (Universal Blue) |
| **OneMind OS** | **Image** | **Debian 13** |

---

## 3. Path 4 (Debian + RAUC) vs path 5 (RHEL-family bootc)

bootc is mostly a Red Hat-family tool, so path 5 meant changing the whole base, not only the updater. Evidence: [`research-output/01-FOUNDATION-DECISION.md`](../../../research-output/01-FOUNDATION-DECISION.md), [`04-image-install-updates-rollback.md`](../../../research-output/04-image-install-updates-rollback.md), [`03-base-os.md`](../../../research-output/03-base-os.md).

| Question | Debian + RAUC | RHEL-family bootc |
|---|---|---|
| Raspberry Pi 5 | Works | Only AlmaLinux's experimental images; no RHEL path |
| Update engine score | RAUC 61 (Mender 62, a tie) | 58 |
| Labs | Passed with real k3s and Secure Boot | Passed rollback with k3s; a power-cut issue was scored |
| Permission to ship | None needed | RHEL in sold boxes needs a Red Hat agreement (AlmaLinux is free) |
| Base-OS score (rev. 4) | Debian 63 | bootc 64: a statistical tie |

bootc's real strengths: it can convert an existing Linux in place with rollback, and Red Hat holds the industrial certificates (hence the year-2 Industrial profile).

**Flag, not a reopening:** the Pi 5 was a large part of the case against bootc, and the daily hub is now the x86 Dell AIO, where bootc is stronger. The pre-registered check stands: the bootc Pi 5 test (D-013, LT-PI5-02) runs before G1 on 2026-12-13, read with the rules fixed in D-012. A box shipped on Debian + RAUC cannot move to bootc without a reflash, so that test is the last fair moment to switch.

---

## 4. Buildroot (how Home Assistant OS does it) vs our Debian image

| | Buildroot (HAOS) | Debian image (OneMind) |
|---|---|---|
| Image size | 4–6× smaller (our lab, DC-20) | Bigger |
| Known security holes | Only 7–18% fewer: most live in the kernel, which both have | About the same |
| Who patches packages | Us, for every package and every board | Debian's security team |
| NVIDIA / CUDA / Jetson | Hard | NVIDIA ships Debian packages |
| Adding software | A build recipe per program | A line in a package list |
| Team it needs | Bigger (HAOS keeps 14 board configs, about 26 OS committers) | Small (umbrelOS: about 5 committers) |

Pattern from the competitor matrix: small teams pick Debian; board-by-board images take bigger teams. Buildroot or Yocto would fit a tiny sensor device later, not the hub.

---

## 5. Update engine: Rugix vs RAUC

| | Rugix | RAUC |
|---|---|---|
| Used by | umbrelOS (our closest twin) | Home Assistant OS, ZimaOS |
| Maintainers | One engineer wrote 303 of 304 commits in a year; 1.0 in Feb 2026 | 16 authors; two at one company write about 91% |
| Docs | Best of the group | Fine |
| License | MIT/Apache | LGPL-2.1 |
| Boot tries before fallback | Default flows have none | 3 |
| Key revocation, multiple signers | Not native | Yes |
| Secure Boot | Not tested by us | Passed our lab |
| Delta updates | n/a | Free |
| Score | 52 | 61 |

RAUC wins on the bus factor and the safety features. The choice is reversible by update: Rugix ships RAUC-compatible boot flows, and our disk layout stays engine-neutral.

---

## 6. Is k3s the right move? (we plan many nodes)

Measured in the W4-1 lab ([`research-output/05-kubernetes-cluster-conversion-nvidia.md`](../../../research-output/05-kubernetes-cluster-conversion-nvidia.md), Debian 13, 4 GiB VM, same two apps): k3s costs **about 0.95 GiB more RAM and about 2.7 GB/day more disk writes** than Podman. On the 16 GB Dell AIO that is about 6% of memory.

| Option | Score | Many machines? |
|---|---|---|
| Docker Compose | 64 (only with the multi-node gate removed) | No |
| **k3s** | **63** | Yes |
| RKE2 | 62 | Yes, heavier (4 GB minimum) |
| Talos | 61 | Yes, but replaces Debian |
| k0s | 60 | Yes |
| Compose small + k3s big | 52 (gate removed) | Two systems to keep |
| Podman Quadlet | about 49 (gate removed) | No |

**Counter-evidence:** TrueNAS moved off k3s to Compose and stranded third-party apps. Lesson (REC-DEC-10): the app format must never depend on k3s-only features. The gateway's Compose import already points that way.

**What would change it:** a real Pi 5 4 GB with under 2 GiB free under k3s, or more than 5 GB/day of writes; then the smallest tier alone moves to Podman. Nomad is excluded by its BSL licence.

**Hide k3s from people:** app authors write one simple app file; users see Install, Running, Move; nobody sees pods or YAML.

---

## 7. How the competitors build on Debian, and what we learn

From [`research-output/02-competitors/MATRIX.md`](../../../research-output/02-competitors/MATRIX.md).

| Product | How it is built | Updates | Compared with us |
|---|---|---|---|
| umbrelOS 2.0 | Docker multi-stage build `FROM debian` (snapshot- and digest-pinned) → Rugix Bakery disk image | Rugix A/B; stable releases unsigned; commits at daemon start | Our twin: same pattern as our Containerfile |
| StartOS 0.4 | **live-build** (Debian's tool for live/install discs) → squashfs (one compressed read-only file) → ISO or `.img` | Swaps image files; no automatic OS rollback; one shared `/boot` | Signs both OS and apps |
| TrueNAS CE | **debootstrap** (installs a bare Debian into a folder) from a frozen mirror → nested squashfs | New ZFS boot environment per update; manual rollback; checksums, not signatures | Frozen mirror = our snapshot pin |
| Proxmox VE | Prebuilt squashfs + `.deb`s unpacked by the installer; then a normal `apt` system | No second copy | Not an appliance; useful business model |
| Home Assistant OS | Buildroot, no Debian | RAUC A/B; commits at Supervisor start | Same update engine |

**Correction to an earlier chat answer:** all four of umbrelOS, StartOS, TrueNAS and Proxmox are built on Debian, but only umbrelOS and TrueNAS ship a sealed image with rollback, and **no product ships Debian + RAUC + k3s in production** (negative search, UNVERIFIED). Each piece is proven somewhere; the combination is ours, so our labs and hardware tests are the proof.

**Lessons to apply**
1. **Commit updates only on fresh health.** Every A/B competitor commits too early; our health gate fixes that.
2. **A/B protects only what is duplicated.** Shared boot partitions broke Kairos, StartOS, ZimaOS and Proxmox boxes. Keep kernel and boot files inside each slot; guard the shared boot area; never run data migrations before commit.
3. **Size slots for 2036 now and rehearse the Debian 13 → 14 rebase.** Umbrel's early layout choice became a permanent second build, and its 12 → 13 rebase left some boxes needing a reinstall.
4. **Sign OS and apps and check on the device** (StartOS is the only one that does both).
5. **Keep the app format runtime-neutral** (the TrueNAS lesson).
6. **AI permissions are our opening:** no competitor combines per-agent scopes, approvals and an audit log.
7. **Business model:** hardware + free OS, or free OS + paid stable channel and support.

---

## 8. Phones

**Own Android fork (the GrapheneOS route):** possible, but monthly security patches forever, a build per phone model and about 300 GB of source. GrapheneOS supports only Pixels because they let you re-lock the bootloader with your own keys. Complexity 9–10. Skip it.

**Debian-based phone OS: possible and proven at small scale.** Purism's Librem 5 has shipped with Debian-derived PureOS since 2019; Furi Labs sells the FLX1/FLX1s with Droidian-derived FuriOS; Mobian released a stable Debian 13 build in late 2025.

| Phone | Good for |
|---|---|
| Google Pixel 3a / 3a XL | Best dev phone: cheap used, supported by Mobian and Droidian |
| OnePlus 6 / 6T, Pocophone F1 | Second test phones (mainline kernel) |
| PinePhone / PinePhone Pro | Built for Linux, slow |
| Librem 5, Furi FLX1s | Closest to finished products |
| Fairphone 4/5, SHIFT6mq | Experimental, demo only |

Rule: an unlockable bootloader plus mainline kernel support (Mobian) or borrowable Android drivers (Droidian). Limits today: weak camera, worse battery, no Google Play. Fine for a OneMind control phone, hard as someone's only phone.

| Step | Complexity |
|---|---|
| OneMind app on a Mobian phone | 3 |
| "OneMind Phone" image (Mobian base + our layer + A/B) on 1–2 phones | 6 |
| Daily-driver phone sold to customers | 9 |

Opinion: ship the Expo app now; a Debian phone image after M-LIVE. This is new scope, not a decision.

Sources: [Mobian devices](https://wiki.debian.org/Mobian/Devices) · [Mobian Trixie release](https://linuxiac.com/mobian-trixie-officially-released-with-broader-device-support/) · [Droidian releases](https://github.com/droidian-images/droidian/releases) · [Furi FLX1 (The Register)](https://www.theregister.com/2024/06/26/furi_phone_flx1_debian_smartphone/) · [Librem 5](https://www.wikipedia.com/wiki/Librem_5) · [PureOS on Librem 5](https://puri.sm/posts/pureos-on-liberty-phone-and-librem-5)

---

## 9. Desktop: Hyprland, Arch, or something else?

- **Arch** is a rolling distro (constant updates), which clashes with a sealed, tested image.
- **Hyprland** is a tiling window manager (Wayland compositor); it runs on any distro. **Omarchy** is an opinionated Arch + Hyprland setup.

Suggested layers on Debian (opinion): (1) **hub kiosk now**: the AIO boots straight into the dashboard full-screen with a kiosk compositor such as `cage`; (2) **a desktop image variant later** (`onemind-desktop`, as Bazzite ships variants) with a tiling session for power users and GNOME or KDE for everyone else; (3) what beats Omarchy is the wiring: CLI, MCP and API everywhere, Market apps, AI actions with approvals, one identity across hub, desktop and phone.

---

## 10. The gateway

**What it is:** the front door and security guard of a hub ([`core/`](../../../core/), detail in lesson [09](../09-gateway-approvals-agents-mcp.md)). Every dashboard screen, phone call, machine and AI agent goes through it, and **"AI never actuates without human approval" is enforced in its code, not in a prompt.**

| Layer | Job | Code |
|---|---|---|
| Guard | Size limits, rate limits, bad-token lockout, security headers | [`guard.py`](../../../core/onemind_core/guard.py) |
| Identity | Token or passkey → principal + role; agents can never be owners | [`auth.py`](../../../core/onemind_core/auth.py), [`identity/`](../../../core/onemind_core/identity/) |
| Routers | One file per feature, found automatically | [`routers/`](../../../core/onemind_core/routers/) |
| Actions | Every change is a request that waits for an owner; idempotency keys; compare-and-swap; no automatic retry | [`actions.py`](../../../core/onemind_core/actions.py), [`ledger.py`](../../../core/onemind_core/ledger.py) |
| Checks | Fresh scan, install sandbox, preconditions checked twice, owner override off by default | [`scan.py`](../../../core/onemind_core/scan.py), [`policy.py`](../../../core/onemind_core/policy.py), [`override.py`](../../../core/onemind_core/override.py) |
| Executor | The only code that touches the world (`kubectl`), applying exactly the checked bytes | [`executors.py`](../../../core/onemind_core/executors.py) |
| Audit | Hash-chained log; any edit breaks the chain | [`audit.py`](../../../core/onemind_core/audit.py) |

AI agents use `POST /mcp`: read tools, one write tool (`request_action`), **no approve tool**, untrusted text labelled, per-agent limits. Machines join through the same approval path ([`fabric.py`](../../../core/onemind_core/fabric.py)).

**Where the idea came from:** Zeus's own Architecture and Implementation Blueprint v1.0 (2026-11-04), summarized in [`context/02-prior-planning.md`](../../../context/02-prior-planning.md) §5, already had the exact action lifecycle, approvals bound to exact parameters, and short expiry for physical commands. Then ADR-001 D6 named a capability gateway, D-001 made it Apache-2.0, research question Q88 asked where agent permissions should be enforced (answer: one point agents cannot bypass), and brief 30 workstream B9 built it. The building blocks (API gateway, idempotency keys, hash-chained logs) are standard; putting AI requests through human approval and audit at the OS level is the OneMind part.

---

## Check yourself
1. In one sentence, what makes OneMind OS an image and not a distro?
2. Why does the bootc Pi 5 test have to happen before the first boxes ship?
3. What does k3s cost on the hub, in RAM, and why do Compose and Podman fail our multi-node rule?
4. Which competitor lesson stops a rollback from being undone by a data migration?
5. Name the one thing an AI agent can never do through the gateway.
