<!-- SPDX-License-Identifier: Apache-2.0 -->
# Home lab plan: DDR3 and DDR4 servers, local AI, and OneMind VM testing

Status: **proposal, waiting on hardware facts** (see README.md, "Blocked on Zeus").
Numbers marked UNVERIFIED are estimates and must be measured on the real machines.

## 1. What each server is for

| | DDR3 servers (usually Xeon E5 v1/v2, 2012–2013) | DDR4 servers (usually Xeon E5 v3/v4 2014–2016, or Xeon Scalable 2017+) |
|---|---|---|
| Role | Light jobs only: restic backup target, file storage, throwaway test node; or **off** | **Main home-lab box:** AI, Proxmox VM host, OneMind test bed, optional CI runner |
| Why | Intel stopped microcode (CPU firmware security) updates for that generation (like the Beelink U55: servicing ended 2021-06-30, `docs/HARDWARE.md`). **No AVX2** on Sandy/Ivy Bridge. High idle power. Old BIOS often has no custom Secure Boot keys and no TPM 2.0 | AVX2, ECC memory, lots of RAM, KVM virtualization |
| Product target? | Never | Never: the product tier is the low-power Intel N150 class. These are dev and "bring your own old machine" hardware |

**Plain-language terms**
- **Memory bandwidth:** how fast data moves from RAM to the CPU. For AI on a CPU, every generated
  word reads roughly the whole model from RAM, so bandwidth sets the speed.
- **AVX2:** CPU instructions that do many math operations at once; AI runtimes rely on them.
- **ECC:** error-correcting memory; it catches bit flips before they corrupt data. Good for backups.
- **NUMA:** on a two-socket server each CPU has its own RAM; reaching the other socket's RAM is slower.
- **Hypervisor:** software that runs many virtual machines (VMs) on one physical machine.

## 2. Local AI: what to expect (UNVERIFIED estimates)

| | DDR3 (4 channels per socket) | DDR4-2400 (4 channels per socket) |
|---|---|---|
| Theoretical memory speed per socket | ~51 GB/s | ~77 GB/s |
| 8B model, about 5 GB (Q4) | Slow, single-digit words/sec | Roughly 5–10 words/sec: fine for chat |
| 70B model, about 40 GB (Q4) | Painful | About 1–2 words/sec: background jobs only |

**Biggest upgrade:** a used 24 GB GPU (an RTX 3090 is the usual pick; check current prices) if the DDR4
server has a free full-length PCIe x16 slot, two spare 8-pin power cables and the physical space.
Many rack servers lack the cables or the room: check before buying.

## 3. Steps you can do today (AI home lab)

1. Install **Proxmox VE** (a free hypervisor built on Debian) on the DDR4 server.
2. Create a **Debian 13** VM or LXC container for AI and give it most of the RAM. On a two-socket
   server, keep it on one socket's cores and memory (NUMA).
3. Install **Ollama**, then **Open WebUI**:
   ```sh
   curl -fsSL https://ollama.com/install.sh | sh
   ollama run llama3.1:8b
   ```
   Open WebUI runs in Docker and gives a ChatGPT-style page on the home network.
4. DDR3 server: a backup target (restic) or file storage, or switch it off.
5. Put each server on a smart plug with a power meter. If a DDR3 server idles at about 150 W or more
   (UNVERIFIED; dual-socket servers often idle around 80–200 W), switch it off when not in use.
   This matches test **W10-T5** in `research-output/11-hardware-line.md` (measure idle and load watts).
6. **Security:** never expose Ollama (port 11434) or Open WebUI to the internet. Use Tailscale for
   phone access.

**Why it also helps OneMind:** you run the same pieces OneMind ships (Debian 13, local AI, backups)
and learn where they hurt. The "Private AI" and "Vault" superpowers in `research-output/11-…` §4 are
exactly these roles.

## 4. One server for home lab, deployments and VM testing

| OneMind deployment shape (in the repo) | What runs it today | On the DDR4 server |
|---|---|---|
| **OneMind image** (read-only, RAUC A/B): `make image`, `make battery` | GitHub `ubuntu-24.04` runners with KVM (`image.yml`, `battery.yml`) | A UEFI (OVMF) VM boots the real image. Proxmox can add a virtual TPM, so A/B rollback and first-boot tests run locally |
| **Developer install** (`deploy/install.sh --role hub/node` on Debian 13) | By hand, or `net-2vm.yml` (a hub VM + a node VM) | One hub VM + 2–3 node VMs: real fabric join, owner approval, `deploy/verify/verify.sh` |
| **Compose bundle** (`deploy/compose/`) | Your Mac with Docker | One small Debian VM with Docker |
| **Cloud** (DigitalOcean droplet, `lab-kits/LT-DO-01`) | DigitalOcean | Keep it there: it tests the real internet path |

**Three groups on the server**
1. **Home lab, always on:** the AI VM and backups. Fixed share of RAM; never touched by tests.
2. **Test VMs, throwaway:** image VMs, hub and node VMs. Snapshot before each test, roll back after.
   Put them on their **own network bridge or VLAN**: OneMind nodes discover and join each other, so
   tests must not see home devices or each other's runs.
3. **CI runner, optional:** a VM with a GitHub self-hosted runner. `battery.yml` already takes a
   `runner` input, so a run can target your server instead of GitHub's.

**Rough RAM budget** (assumes 128 GB; replace with the real number): AI 48–64 GB, test VMs 4–8 GB each
(about 32 GB for a hub + 3 nodes), runner 16 GB, Proxmox about 8 GB.

## 5. Warnings

- **Public repo + self-hosted runner is a risk.** GitHub advises against self-hosted runners on public
  repositories: a pull request from a fork could run its code on your server. If added: trigger
  only by hand (`workflow_dispatch`), never on `pull_request`; runner in its own VM, with no network
  route to the home-lab group.
- **VMs do not replace real hardware.** Real power cuts, Secure Boot with OneMind's own keys on real
  firmware, the Pi 5 and the Jetson still need the physical kits (`lab-kits/LT-X86-01`,
  `LT-PI5-01`, `LT-JET-01`).
- **Heavy tests slow the AI.** Image builds and AI chat compete for CPU and memory bandwidth. Cap
  test-VM CPU, or run big tests when you are not chatting.

## 6. Proposed next build step: `lab-kits/LT-LAB-01`

A new lab kit for the DDR4 server, in the style of `lab-kits/LT-X86-01`:
- Proxmox install notes and post-install settings (no-subscription repo, updates, KVM check).
- Network: a home bridge (`vmbr0`) and an isolated test bridge/VLAN (`vmbr1`) for OneMind test VMs.
- VM templates: Debian 13 cloud-init template (hub/node), a UEFI + vTPM VM for the OneMind image.
- A script: bring up hub + 2 nodes, then `deploy/install.sh --role hub`, join the nodes with
  `onemind fabric ticket`, then run `deploy/verify/verify.sh`; snapshot and roll back.
- An AI VM recipe (Ollama + Open WebUI) and the power-measurement sheet for W10-T5.
- Optional, behind the warnings in §5: a self-hosted runner VM for `battery.yml`.
- Definition of done: `docs/leap/AGENT-QUEUE.md` §4 (real data, tests, `changes/` fragment, DCO sign-off).

**Needs from Zeus before building:** the hardware facts in README.md and his OK.
