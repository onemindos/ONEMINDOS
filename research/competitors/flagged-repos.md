# Founder-Flagged Repos (Part B)

Research date: 2026-11-10. Source: `gh api` / `gh repo view` plus the repo READMEs. I did not clone, install, or run anything from these repos (they ship installers, an `npx` setup that edits agent configs, and decoy/"poison" payloads - see cautions).

All three exist and are non-empty. They form one linked story: **REA** reverse-engineers software with AI agents, **Craft Anything** uses a similar engine to clone/rebuild software, and **BLA** is a defense tool built specifically to counter REA.

| | craft-anything | bla | rea |
|---|---|---|---|
| URL | https://github.com/storytold/craft-anything | https://github.com/qybaihe/bla | https://github.com/morluto/rea |
| Description | "Craft Anything: understand how any software works, and craft your own." | "BLA (Blind LLM Agents) - Adversarial defense shield ... against AI reverse-engineering agents like REA. Poison -> Exhaust -> Hallucinate." | "Reverse engineer anything with agents, from app behavior down to native binaries." |
| Primary language | Rust (10.7 MB of ~10.8 MB) | TypeScript (2.4 MB; plus 1.8 MB JS, Python 42 KB) | TypeScript (60 MB; plus Python, JS, Java, C, C++, Swift, etc.) |
| License (GitHub API) | Apache-2.0 (repo has `LICENSE-APACHE` and `LICENSE-MIT`; README badge says "MIT OR Apache-2.0" - API reports only Apache-2.0) | MIT | MIT |
| Stars / forks | 25,983 / 5,277 | 4,941 / 592 | 449,517 / 110,694 |
| Created | 2026-10-31 | 2026-10-25 | 2026-04-14 |
| Last push | 2026-11-10 | 2026-11-10 | 2026-11-10 |
| Latest release | v0.6.0 (2026-11-09) | v3.2.3 (2026-11-10) | rea-agents-6.8.0 (2026-10-25) |
| Open issues | 312 | 14 | 1,725 |
| Status per README | "early alpha" | "bla-agents v3.2.4" on npm (badge) | npm `rea-agents` |
| Website | getartcraft.com (ArtCraft brand) | https://bla.tools | https://rea.tools |

Caveat on popularity numbers: these are the live API values and are extraordinary (449k stars is in the range of the largest repos on GitHub; craft-anything reached ~26k stars in 10 days). I did not investigate whether star counts are organic - **UNVERIFIED**. Do not use them as a quality signal without checking.

---

## 1. storytold/craft-anything

**Purpose (README):** "See how any website, app or game works, then have AI build your own version; an open-source, clean-room engine in pure Rust." Point it at a target, say what you want; it studies the original with inspection tools, a coding agent builds a new project, then it checks the result against the original and refines it (Study -> Build -> Check -> Ready).

**Key facts**
- Desktop app (egui), CLI (`craft-anything-cli`) and **MCP server** all drive one engine. README claims 320 tools, each both a CLI command and an MCP tool; `craft-anything-cli mcp` serves them to any MCP client; `craft-anything-cli setup` connects it to coding-agent apps.
- Two modes: **Clean room** (default - does not read the original's code/page source; works from what's visible) and **Deep** (uses disassembler/decompiler, and Ghidra if installed).
- Targets: websites (checked at three screen widths), desktop/phone apps, games (rebuilds in Unity/Unreal/Godot), plus firmware, packet captures, databases, game files.
- Builder is a coding agent on the user's machine: Claude Code supported first (runs the user's own unmodified `claude` and sign-in); Codex adapter unverified; Copilot CLI and Grok Build via ACP; others via ACP; API providers (Anthropic, OpenAI, OpenRouter, xAI, local OpenAI-compatible) for questions/analysis.
- Platforms: macOS, Windows, Linux, FreeBSD, plus parts running in browser as WebAssembly. Requires Rust 1.97+ to build from source.
- Repo layout includes `crates/`, `apps/`, `vendor/`, `packaging/`, `docs/` (ROADMAP, STATUS, tool-status), `AGENTS.md`, `CLAUDE.md`, `SECURITY.md`.
- README "Status" says early alpha; "Next: the managed tier" (implies a future paid/hosted tier). Brand ties to ArtCraft (community of artists, Discord).
- Responsible-use text: only for software you own or may examine; says it never bypasses DRM, logins or anti-cheat; warns that installing dependencies runs code and asks before new command kinds.

**Relevance to OneMind OS**
1. **Agent-native tool surface as a model.** "Every tool is a CLI subcommand and an MCP tool" with evidence records (confidence, coverage, limitations) is a clean pattern for OneMind's own MCP layer: one capability registry rendered as UI, CLI and MCP.
2. **Competitive/IP awareness.** A tool that can rebuild a website from its public appearance lowers the cost of cloning OneMind's marketing site and UI; clean-room replication of app UIs is now cheap. (Inference.)
3. **Possible internal use:** study competitor UIs (Umbrel, Olares) for UX benchmarking under the clean-room mode, within legal limits - needs legal review (**UNVERIFIED** legality; README only says use on software you own or may examine).
4. **Packaging idea:** Rust workspace + Apache-2.0/MIT dual license + multi-OS installers is a reference for a cross-platform OneMind client.
5. Not a home-server product; low direct overlap.

**Cautions:** early alpha; the builder runs package installs on the user's machine; star/fork counts unexplained; GitHub license field says Apache-2.0 while README says dual - verify `LICENSE-*` files before reuse.

---

## 2. qybaihe/bla ("Blind LLM Agents")

**Purpose (README):** Open-source "Counter-REA Blue Defense MCP & CLI" that hardens your own release artifacts (Electron apps, `.asar`, JS bundles and SourceMaps, `.wasm`, SQLite, `.safetensors`, Python, native binaries - "19+ formats") against AI reverse-engineering agents. Strategy tagline: **Poison -> Exhaust -> Hallucinate.**

**Key facts**
- CLI: `npx bla-agents harden .` runs audit -> protect -> verify. `npx bla-agents setup` registers BLA's MCP server with coding agents (Claude Code, Cursor, Codex, Windsurf, Gemini CLI, Copilot CLI, VS Code, OpenCode, Antigravity). README lists "25 defense tools". Bundler plugins for Vite/Rollup/Webpack/esbuild.
- Techniques described: deterministic resource ceilings that analyzers hit, decoy/honey SourceMaps, number-theoretic opaque predicates, inert decoy metadata and canary credentials meant to mislead automated analysis.
- Claims: 14/14 bundled benchmark targets keep input/output equivalence; "300x-2,800x modeled token amplification" - the README labels benchmark figures as **internal estimates**, so treat as unverified marketing.
- Has a DISCLAIMER.md: defensive use only, protect your own software; says payloads are benign/inert at runtime and activate only when an analysis pipeline reads the artifact.
- Languages: TypeScript, JS, CSS, HTML, small Python. 22 translated READMEs. Site bla.tools has guides, benchmarks, a "CrackMe Arena" and an Enterprise page (hints at commercial offering - detail not read).
- Self-describes as GitHub Trending #15 (badge); not independently verified.

**Relevance to OneMind OS**
1. **Protecting a sold product.** If OneMind ships a desktop/Electron client, firmware images, a web UI bundle, or model files in its hardware, BLA targets exactly those artifacts. Candidate for the release pipeline of proprietary components - only if OneMind keeps parts closed. For an open-source OS (the likely strategy) it is mostly irrelevant, except for a closed premium tier.
2. **Threat model signal.** The existence of REA + BLA shows AI agents can clone closed binaries cheaply; OneMind's moat should not depend on code secrecy. (Inference.)
3. **MCP-in-the-release-pipeline pattern:** a security tool delivered as an MCP server the coding agent calls (`bla_audit`, `bla_harden`, `bla_verify`) is a template for OneMind "ops" MCP tools.
4. **Risk:** the payload design (decoys that influence LLM readers, canary credentials) behaves like prompt-injection-style content embedded in artifacts. Shipping it inside user-facing devices could confuse support/debug workflows and agent tooling, and could look malicious to AV scanners (**UNVERIFIED**; not tested).

**Cautions:** `npx ... setup` modifies agent config; do not run without review. Effectiveness claims are self-reported.

---

## 3. morluto/rea ("Reverse Engineer Anything")

**Purpose (README):** "One MCP for reverse engineering across binaries, applications, and runtime behavior." Your agent calls REA over MCP to inspect a local target, trace relevant code, and return findings with evidence and limitations; the agent can then explain or re-implement the behavior. Analysis runs locally.

**Key facts**
- Install: `npx rea-agents setup` registers the MCP server and workflow instructions with Claude Code, Codex, Cursor, Gemini CLI, Grok Build and others (backs up existing config; asks approval). Node 22.x/24.x/26.x required.
- Targets (table in README): desktop installs, native binaries (via Hopper, Ghidra, IDA or Kuna), ELF/PE/Mach-O static inspection, Go and Rust binary metadata, GPU code objects (CUDA/HIP/PTX), model artifacts (GGUF/safetensors headers), Unity IL2CPP metadata, Godot PCK, PE certificates/imports, shortcuts, JS/Electron/ASAR, .NET, websites, firmware, and more. Also "Build RL environments" section.
- MIT licensed; 23-language README; Discord; listed on skills.sh; npm `rea-agents` at 6.8.0.
- Repo includes a `website/` directory (the site at rea.tools publishes `/.well-known/ai-catalog.json`, `agent-skills/index.json` and an `index.md` alternate - visible in HTTP Link headers I fetched) - a concrete example of making a website agent-readable.
- Repo contains `.claude-plugin` and `.codex-plugin` directories, i.e. ships as plugins for Claude Code/Codex.
- Topics include `agent-skills`, `claude-code`, `mcp`, and (oddly) `touhou` - unexplained, **UNVERIFIED**.

**Relevance to OneMind OS**
1. **MCP product-distribution pattern:** `npx <pkg> setup` that auto-registers an MCP server in multiple agent hosts + plugin manifests (`.claude-plugin`, `.codex-plugin`) + a skills.sh listing is the lowest-friction way to get an agent-native product adopted. OneMind could copy this for an "agent connector" (`npx onemind setup`).
2. **Agent-readable website:** `.well-known/ai-catalog.json`, `agent-skills/index.json`, markdown alternate - directly applicable to OneMind's site (see platform/website-patterns.md).
3. **Security audit use:** REA can be pointed at OneMind's own releases/firmware (and competitors' apps) to see what an agent can learn - useful red-team step before shipping hardware.
4. **Firmware/embedded scope:** REA handles firmware and GPU code objects - relevant for OneMind's hardware roadmap (inspecting vendor blobs, SBC images).
5. **Dependency risk:** relies on Hopper/Ghidra/IDA for native analysis; heavy; not a runtime component of an OS.

**Cautions:** installer touches agent configs; "Build RL environments" suggests training-data use cases (not read in depth); star/fork numbers unexplained.

---

## Bottom line

| Repo | Use for OneMind |
|---|---|
| rea | **Study** (distribution pattern, agent-readable site, MCP tool design) and **use** as a pre-release red-team tool |
| craft-anything | **Study** (CLI=MCP tool registry, evidence-record schema); treat as competitive/IP signal; low direct overlap |
| bla | **Optional** protection for any closed-source client/firmware; weak fit if OneMind is fully open source |

## Sources
- https://github.com/storytold/craft-anything (README, LICENSE-APACHE/LICENSE-MIT presence, releases, repo metadata via `gh`)
- https://github.com/qybaihe/bla (README, DISCLAIMER.md, releases, repo metadata)
- https://github.com/morluto/rea (README, contents listing, releases, repo metadata)
- https://rea.tools (HTTP `Link` headers: ard.json, ai-catalog.json, agent-skills/index.json, index.md)
- https://bla.tools (reachable; content not read in depth)
