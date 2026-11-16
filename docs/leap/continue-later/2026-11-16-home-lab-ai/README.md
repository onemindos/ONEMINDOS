<!-- SPDX-License-Identifier: Apache-2.0 -->
# Continue later: home lab, AI and VM test bed (session of 2026-11-15/16)

**What this folder is.** Zeus asked to save the whole conversation and its plan so that another
agent (Claude, Codex, GPT) can pick up exactly where this one stopped. Nothing here is a founder
decision. It is advice and a proposed next build step, and it is waiting on hardware facts from Zeus.

| File | What is in it |
|---|---|
| [CONVERSATION.md](CONVERSATION.md) | The full conversation: every question Zeus asked and every answer, in order |
| [HOME-LAB-PLAN.md](HOME-LAB-PLAN.md) | The plan in one place: what each server is for, the VM layout, RAM budget, warnings, and the proposed `lab-kits/LT-LAB-01` kit |
| This README | Where things stand, what is blocked, and the prompt to paste into a new agent |

## Where things stand

- **Hardware Zeus has (new in this session):** servers with **DDR3** memory and servers with **DDR4**
  memory. Exact models, CPUs, RAM size, disks and free PCIe slots are **not known yet**.
- **Zeus's goal:** use them **today as a personal home lab with AI**, and also use the same server
  for **OneMind OS deployments and testing with VMs**.
- **Advice given (summary; full text in CONVERSATION.md):**
  1. DDR4 server = the AI box and the VM host (Proxmox VE). DDR3 server = light jobs (backups,
     storage, a throwaway test node) or switched off. Neither is a OneMind product target.
  2. AI today: Proxmox, then a Debian 13 VM/LXC, then Ollama and Open WebUI. A used 24 GB GPU is the
     biggest upgrade if the chassis can take it.
  3. One server can host all OneMind deployment shapes in separate groups: always-on home lab,
     throwaway test VMs on an isolated bridge/VLAN, and an optional self-hosted CI runner.
- **Nothing in the code was changed.** Only this folder and a `changes/` fragment were added.

## Blocked on Zeus (ask for these first)

Run on **each** server and paste the output:
```sh
lscpu
free -h
lsblk -o NAME,SIZE,TYPE,ROTA,MODEL
sudo dmidecode -t system | head -20
lspci | grep -iE 'vga|3d|nvidia|amd'
```
Also: does the DDR4 server have a free full-length PCIe x16 slot and spare 8-pin GPU power cables?
And: is it a rack server or a tower (noise and where it lives)?

## Open questions for Zeus

1. Build `lab-kits/LT-LAB-01` (Proxmox home-lab and VM test bed kit)? Proposed in HOME-LAB-PLAN.md §6.
2. Add the servers to `docs/HARDWARE.md` §1 with their roles (a founder-requested entry)?
3. Turn the AI home-lab steps into a lesson at `docs/learning/home-lab-ai.md`?
4. Add a self-hosted GitHub runner? Only with the safety rules in HOME-LAB-PLAN.md §5 (public repo).

## Prompt to paste into a new agent

```
You are continuing a OneMind OS session. Read CLAUDE.md, then read
docs/leap/continue-later/2026-11-16-home-lab-ai/README.md, CONVERSATION.md and HOME-LAB-PLAN.md
in full. Zeus has servers with DDR3 and DDR4 memory and wants (a) a personal home lab with local AI
today and (b) the same DDR4 server used for OneMind OS deployments and testing with VMs.
Ask Zeus for the hardware facts listed under "Blocked on Zeus" if they are not in this folder yet.
Then, with his OK, build lab-kits/LT-LAB-01 following the style of the existing lab-kits/LT-X86-01
kit, as described in HOME-LAB-PLAN.md §6. Follow the definition of done in docs/leap/AGENT-QUEUE.md
(tests, change fragment, signed-off commits). Explain the "why" in plain language: Zeus is learning
OS engineering. Do not reopen founder decisions (D-001…D-007).
```

## How to copy this folder to your Desktop (on your Mac)

From your local clone of ONEMINDOS:
```sh
git fetch origin ccr-65932748-pe4cl6
git archive FETCH_HEAD docs/leap/continue-later | tar -x -C ~/Desktop
```
That creates `~/Desktop/docs/leap/continue-later/2026-11-16-home-lab-ai/`. Or open the branch
`ccr-65932748-pe4cl6` on GitHub and download the files from this folder.

## Build-step links (CLAUDE.md prime directive)

- `docs/HARDWARE.md` §1 (D-004, hardware on hand) and `research-output/11-hardware-line.md`
  (W10-T5 power measurement, old-BYO behaviour, superpowers such as "Vault" and "Private AI").
- `test/qemu/` and `.github/workflows/image.yml`, `battery.yml` (its `runner` input), `net-2vm.yml`.
- `deploy/install.sh` (P6 developer install: `--role hub` / `--role node`) and `deploy/verify/`.
- `lab-kits/` (existing kits: LT-DO-01, LT-JET-01, LT-PI5-01, LT-X86-00, LT-X86-01, common).
