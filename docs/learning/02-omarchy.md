# Lesson 02: Omarchy, and Where It Fits OneMind OS

**Date:** 2026-11-10 · **Sources:** omarchy.org (homepage, fetched 2026-11-10), GitHub `omacom/omarchy` (checked via the GitHub API: **MIT license, 46.7k stars, v4.5.0 released 2026-11-05**, mostly shell scripts). Homepage claims are self-reported marketing.

## What it is
"**The malleable OS for the age of agents.**" A Linux **desktop** built by David Heinemeier Hansson (creator of Ruby on Rails, co-founder of Basecamp), backed by the Omacom Foundation ($23.65M pledged per the site).
- **Stack:** Arch Linux, the Hyprland tiling window manager, and Quickshell for the bar/shell (the homepage doesn't name Arch; the repo and reviews do).
- **Installs on:** x86 and ARM64 ISOs ("answer five questions"), **Apple Silicon Macs next to macOS** (Omarchy M; M1–M3 now, M4+ coming), dual boot, unattended installs. The repo has package lists for **NVIDIA GB10 (DGX Spark)**, N1X, Qualcomm and Apple.
- **Ships with:** dev tools (Neovim, Docker, Mise, Lazygit), terminals, gaming (Steam etc.), a Windows 11 VM, and ~20 themes.

## The agent-native features (what to learn from)
| Omarchy feature | What it does | OneMind equivalent (requirement) |
|---|---|---|
| Choose your default AI agent at first boot | Claude Code, Codex, OpenCode, Copilot CLI and others are first-class | First-boot setup picks the household AI and model routes [AI-8, AI-9] |
| Crash notification → "send agent" | The agent reads the crash dump and diagnoses it | Native alerts with a "let AI investigate" button and approval [UX-4, AI-5] |
| Built-in agent **skills** for making apps, plugins and themes | Agents can extend the OS | Studio + Agent Skills generated from `onemind.app.yaml` [AI-4, A-5] |
| **plugins.omarchy.org** community directory | Users (often via their agents) publish plugins | OneMind Market + community publishing with quality tiers [A-5, A-6, W-8] |
| `AGENTS.md` / `CLAUDE.md` in the repo | The project is designed for AI contributors | Same in OneMind repos, so agents can build apps safely |
| Plugin validator (`omarchy-plugin-validate`) | Manifests checked before install | `onemind app validate` linter [A-1] |

## Where Omarchy fits, and where it doesn't

**✅ Good for: the OneMind *Desktop* edition [UX-10, P-4]**
- A workstation that talks to your OneMind box: panels for nodes, alerts, agents and TAK, as Omarchy plugins.
- Your Dell Latitude 5540 pilot from the earlier plans.
- An "Omarchy M"-style install next to macOS shows how a OneMind desktop client could live on Macs.

**❌ Not the base for the OneMind *box***
- **Arch is rolling** (Lesson 01): updates can need manual fixes, which is bad for a box nobody is watching.
- No LTS and no A/B image updates.
- It's a **desktop**. A box needs to be headless, stable and identical everywhere.

**The split:**

```
OneMind BOX (server)  = Ubuntu 24.04 LTS + read-only A/B image + k3s   ← runs everything
OneMind DESKTOP       = Omarchy (Arch + Hyprland) + OneMind plugins    ← one of many clients
Other clients         = phone app, web, Mac/Windows, XR glasses
```

## Big takeaway
Omarchy proves the **"agents customize your OS" model works and people love it** (46.7k stars). OneMind should make the *whole home and infrastructure* malleable by agents, not just the desktop, with permissions and approvals because it controls real devices.

## Check yourself
1. Why is Omarchy great for a desktop but wrong for the box? *(Rolling Arch, no LTS or A/B updates, desktop-first.)*
2. Which two Omarchy ideas should OneMind copy first? *(Agent skills for building plugins, and the crash → agent flow.)*
3. How does Omarchy relate to the OneMind box? *(It's a client, one desktop edition that connects to the box.)*
