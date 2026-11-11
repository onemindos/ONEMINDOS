# Founder-flagged repos: REA, Craft Anything and BLA (RS-5)

**Workstream:** W1, "Flagged repos (RS-5)" · **Question:** Q297 · **Date:** 2026-11-10 · **Tier:** support work for Tier A teardowns
**Builds on:** `research/competitors/flagged-repos.md` (phase 1, metadata and READMEs only) and `context/03-repo-findings-index.md` (REPOS rows, contradiction C-38). This pass adds what phase 1 did not do: reading the code at pinned commits, checking the install paths for supply-chain risk, independent adoption signals, the legal limits, and a decision.
**Claims:** `evidence/claims/TD-flagged.csv` (C-TD-flagged-001 to 034) · **Sources:** `evidence/sources/TD-flagged.md`

> **Safety statement.** Nothing from these repos was installed, built or run. They were cloned shallow (no checkout, git hooks disabled) outside the OneMind repo, and only text and source files were read. So no VM was needed. Mission §3 allows running these tools only inside a disposable VM, only on software OneMind is licensed to analyze, and only when reading source cannot answer a Tier A question. This review found no such question (§5).

---

> ### Explain it like I'm the founder
>
> You flagged three linked projects:
>
> - **REA** is a toolbox that lets an AI coding agent (Claude Code, Codex and others) take apart a program: read its binary, unpack its firmware, watch its network traffic, and explain how a feature works.
> - **Craft Anything** uses the same idea to **rebuild** an app or website: it studies the original, then a coding agent writes your own version and compares the two.
> - **BLA** is the counter-move. It changes **your own** release files so that an agent like REA wastes its budget, follows fake leads, or skips over decoys.
>
> **The decision, in four lines:**
> 1. **For competitor teardowns: don't use them.** Home Assistant OS, Olares and umbrelOS all publish their full source code, so reading that code is faster, cheaper and legally cleaner than decompiling their images. If we ever need to unpack a firmware image, REA itself uses two plain open-source tools (Binwalk and Unblob), and we can use those directly.
> 2. **Use REA for one thing: attacking our own releases**, inside a throwaway VM, before we ship hardware. It shows what an outsider's agent could learn from a OneMind image.
> 3. **Do not put BLA's poison and decoys in OneMind images.** OneMind's promise is that everything on the box is readable by AI (AI-1). BLA's job is the opposite: to confuse AI that reads your files. It would also confuse our own agents and support tools, and one optional mode writes fake legal and medical-safety notices into files. Most of OneMind is open source anyway, so there is nothing to hide.
> 4. **Copy the honest part of BLA's idea** as release checks: no source maps, no debug ports, no secrets left in the files we ship, and everything signed. These checks use standard tools.
>
> **Craft Anything** is worth studying for one non-obvious reason: its licence-checking setup (an automatic allowlist that blocks copyleft code) is exactly the guard rail OneMind needs to protect its Apache-2.0 code (D-001).

---

## 1. Verdict

| Repo | What it is | Licence | Use for teardowns? | Other use for OneMind | Decision |
|---|---|---|---|---|---|
| **morluto/rea** | MCP server and CLI that lets an agent reverse-engineer binaries, apps, websites and firmware | MIT [C-TD-flagged-001] | **No.** Tier A competitors publish source [C-TD-flagged-034] | Red-team OneMind's own images, in a VM (REC-FL-2) | **Use narrowly** |
| **storytold/craft-anything** | Desktop app, CLI and MCP server that studies a target and has an agent rebuild it | MIT OR Apache-2.0 [C-TD-flagged-002] | **No.** Rebuilding a competitor UI risks copying protected expression into Apache code (§6) | Study its licence gate and its "one tool = one CLI command = one MCP tool" registry (REC-FL-5, REC-FL-6) | **Study only** |
| **qybaihe/bla** | Tool that adds decoys, resource traps and misleading metadata to your own release files to defeat AI reverse-engineering agents | MIT [C-TD-flagged-003] | Not applicable (it is a defense) | Adopt only its non-deceptive audits, as standard release gates (REC-FL-3) | **Don't adopt the deception layers** |

---

## 2. What changed since phase 1

| Phase-1 item (context/03) | Finding now | Evidence |
|---|---|---|
| C-38: craft-anything licence, API says Apache-2.0, README says dual | **Resolved: dual MIT OR Apache-2.0.** `Cargo.toml`, `NOTICE` and both licence files agree. GitHub's API shows only one of them. The ArtCraft brand is excluded from the licence. | [C-TD-flagged-002] |
| "Star counts unexplained" | **Still UNVERIFIED.** GitHub's stargazer listings returned "not found" from this environment, even for an unrelated control repo, so account sampling was impossible. Independent signals now gathered: npm downloads and commit activity (below). | [C-TD-flagged-006], [C-TD-flagged-007], [C-TD-flagged-005] |
| "`npx ... setup` modifies agent config; do not run without review" | **Reviewed in code.** BLA's setup only plans unless given `--yes`, backs up configs and pins its own version. REA's `install.sh` resolves the *latest* release unless you pin one, installs globally, then starts setup. Neither npm package runs install scripts, and both carry SLSA provenance. | [C-TD-flagged-025], [C-TD-flagged-011], [C-TD-flagged-008] |
| "BLA effectiveness claims self-reported" | **Confirmed self-reported.** The README labels its token-amplification numbers "internal estimates" limited to 14 bundled fixtures. | [C-TD-flagged-021] |
| "BLA AV/false-positive risk" | **Partly answered.** Gitleaks' default AWS rule should not match BLA's AWS-shaped canary (an inference from the regex, not tested). Antivirus, app-store and enterprise data-loss scanners remain **UNVERIFIED**. | [C-TD-flagged-033] |
| "rea Build RL environments" | Read: REA can package an app into a practice environment for training or testing agents. Not relevant to OneMind's OS. | README §"Build RL environments" at the pinned SHA |
| New | BLA's defenses are tuned to REA's internal limits and cite REA source lines. REA already has an open issue to bypass or detect BLA. This is an arms race, and BLA breaks whenever REA changes. | [C-TD-flagged-016], [C-TD-flagged-017], [C-TD-flagged-015] |
| New | One optional BLA mode writes fabricated regulatory notices (children's privacy law, pediatric medical-device safety, US computer-crime law) into protected files. | [C-TD-flagged-019], [C-TD-flagged-020] |

---

## 3. The three repos, read from code

### 3.1 morluto/rea ("Reverse Engineer Anything")

**What it does.** REA gives an agent tools to inspect native binaries (using Hopper, Ghidra, IDA or Kuna if installed), JavaScript and Electron apps, .NET, Android, websites, network captures, SQLite, model files and firmware. Firmware unpacking is done by **Binwalk and Unblob**, both MIT and both pinned as git submodules [C-TD-flagged-012]. Setup registers REA as an MCP server in the user's agent apps.

**Licence and activity.** MIT; npm `rea-agents` 6.8.0, released 2026-10-25 [C-TD-flagged-001]. The repo was created on 2026-04-14 and reports 450,015 stars and 110,751 forks [C-TD-flagged-004]. In the 30 days to 2026-11-10 it took 4,760 commits from 337 authors [C-TD-flagged-005], about 160 commits a day, which suggests heavy agent-written changes (inference). npm counted about 2.0 million downloads in 30 days [C-TD-flagged-007]. Downloads include CI and repeat installs, so they show heavy use, not a user count. The star count would put REA among the most-starred repos on GitHub after seven months. Whether that is organic is **UNVERIFIED** [C-TD-flagged-006].

**Safety, from its own policy and code:**
- REA "run[s] with the host process's permissions" and "is not a general-purpose sandbox" [C-TD-flagged-009]. If you point it at a hostile file, nothing stands between that file and your laptop except the parsers.
- Its optional HTTP MCP transport is plain HTTP with no TLS and no client authentication [C-TD-flagged-010]. Never expose it on a network.
- "Analysis runs locally", but whatever the tools find is sent to your agent's model provider [C-TD-flagged-014]. Pointing it at a vendor's licensed binary therefore sends pieces of that binary to a cloud model.
- `install.sh` fetches the latest release tag from GitHub unless `--version` is given, runs `npm install --global`, then starts interactive setup. It does offer a dry run [C-TD-flagged-011].
- The npm package has no install scripts and has SLSA provenance [C-TD-flagged-008]. That is good supply-chain hygiene, but it says nothing about the 30-plus runtime dependencies (`package.json` at the pinned SHA lists, among others, `playwright-core`, `@lydell/node-pty` and `isomorphic-git`).
- Its disclaimer refuses help with DRM bypass and with copying proprietary code, and says analysis output grants no rights to the original [C-TD-flagged-013].

### 3.2 storytold/craft-anything

**What it does.** You point it at a website, app or game and describe what you want. It studies the original, a coding agent (Claude Code first) builds your version, and it checks the result against the original. It has two modes. **Clean room** reads nothing inside the target, only what a visitor sees. **Deep** reads code and files, using Ghidra if installed. The README is explicit that clean room is a policy, "not an operating-system sandbox" [C-TD-flagged-026].

**Licence and activity.** MIT OR Apache-2.0 [C-TD-flagged-002]; v0.6.0 released 2026-11-09; "early alpha", with API-key and non-Claude builders "built, not yet run live" and "the managed tier" listed as next [C-TD-flagged-027]. Created 2026-10-31; 26,320 stars [C-TD-flagged-004]; 823 commits from 88 authors in 30 days [C-TD-flagged-005]. The README claims 320 tools, each a CLI command and an MCP tool. This is self-reported and was not counted [C-TD-flagged-028].

**The part worth copying.** Its licence policy is enforced by `cargo-deny`. Only permissive licences are allowed, MPL-2.0 is allowed only per named crate, copyleft code is never linked, and programs that are only *run* as separate processes may have any licence [C-TD-flagged-029]. That is the same line D-001 draws, turned into a CI check.

### 3.3 qybaihe/bla ("Blind LLM Agents")

**What it does.** BLA rewrites your own release files (JS bundles, Electron `.asar`, WASM, Python, ELF, SQLite, safetensors/GGUF, APK pieces, UF2 firmware and others) in three ways:
- **Poison:** decoy functions, fake credentials and fake architecture metadata. For example, it inserts decoy functions whose names sort to the top of REA's procedure lists [C-TD-flagged-017], and fake credential URLs, an AWS-documentation-shaped key and decoy `Authorization` headers [C-TD-flagged-018].
- **Exhaust:** structures sized to hit REA's internal limits so the analysis stops or burns tokens.
- **Hallucinate:** misleading content aimed at the model reading the output.

**Licence and activity.** MIT; four runtime dependencies, all Babel [C-TD-flagged-003]. Created 2026-10-25; 5,012 stars [C-TD-flagged-004]; 485 commits in 30 days, but only 8 authors [C-TD-flagged-005]. About 13,000 npm downloads in 30 days [C-TD-flagged-007]. It is small, new and essentially a one-person project.

**What the code shows:**
1. **It is tuned to one tool.** BLA ships a script that checks for drift in the REA constants it targets [C-TD-flagged-016], and its shields cite REA file paths and line numbers [C-TD-flagged-017]. A REA issue opened on 2026-11-08 proposes a bypass or detector for BLA [C-TD-flagged-015]. So BLA's protection lasts only until REA's next release.
2. **It plants misleading legal text when asked to.** With the opt-in `--llm-directives` flag, it writes notices claiming the code is protected by COPPA and GDPR child-privacy rules, IEC 62304 pediatric life-support safety rules, and 18 U.S.C. §1030 / 17 U.S.C. §1201 [C-TD-flagged-019]. This is off by default [C-TD-flagged-020]. For a product sold to families with children (U-2, U-3) and to public safety (M-4), shipping false compliance claims would be a trust and legal problem (inference; not legal advice).
3. **Its own authors say it is not real secrecy.** The disclaimer says no client-side scheme stops a determined human analyst and that high-value secrets belong on trusted servers [C-TD-flagged-022]. Its debug-posture report states it does not block Frida or gdb with local privileges [C-TD-flagged-023].
4. **Its numbers are estimates.** The 300x to 2,800x "token amplification" figures are internal estimates on 14 bundled fixtures [C-TD-flagged-021].
5. **It has an honest, useful half.** Separate from the deception, it has read-only audits that find source maps that leak original source, exposed debug settings and plaintext secrets, with `networkAccessed: false` [C-TD-flagged-024].
6. **Its installer is careful.** It only plans unless given `--yes`, backs up agent configs without overwriting earlier backups, and pins the registered MCP server to the exact version that ran setup [C-TD-flagged-025].

---

## 4. What competitors do (protecting their images, and studying others)

None of the proven competitors uses BLA-style deception. They protect **integrity** (the image is genuine) through signing, and protect **business** through licences, not through obfuscation.

| Competitor | Code openness | How it protects its images | Uses obfuscation or anti-AI decoys? | Constraint-fit to OneMind |
|---|---|---|---|---|
| **Home Assistant OS** | Apache-2.0, full OS source public [C-TD-flagged-034] | RAUC bundles signed with a release CA; cosign signs release checksums [C-TD-home-assistant-os-012], [C-TD-home-assistant-os-015] | None found | **High.** Same licence as OneMind's core (D-001), appliance OS, small core team. **Default pattern.** |
| **umbrelOS** | Source available under PolyForm Noncommercial; commercial forks barred [C-TD-flagged-032], [C-TD-umbrelos-045] | 2.1 beta adds an offline root key and a signed signer list; stable 2.0.1 ran an unsigned update script [C-TD-umbrelos-013], [C-TD-umbrelos-010] | None found | **Medium.** Protects the business with a licence, which OneMind rejected in D-001. Its signing design is the model ADR-001 D3 copies. |
| **Olares** | AGPL-3.0, source public [C-TD-flagged-034] | MD5 checksum only, no signature found [C-TD-olares-004], [C-TD-olares-006] | None found | **Low** for this question. A weak point OneMind should beat. |
| **BLA's model** (for comparison) | Assumes closed artifacts | Decoys, traps and misleading metadata | Yes, by design | **Low.** Conflicts with AI-1/AI-4 and with an Apache-2.0 core (§5.2). |

---

## 5. Answers to Q297

### 5.1 Should OneMind use REA or Craft Anything for competitor teardowns?

**No, not for the Tier A teardowns.** Reasons:
1. **Source beats decompilation.** HAOS (Apache-2.0) and Olares (AGPL-3.0) publish full OS source [C-TD-flagged-034], and umbrelOS publishes its source too [C-TD-umbrelos-056 in the umbrelOS ledger]. The mission requires citations to source at pinned commits (§2 rule 3). A decompiler's guess is weaker evidence than the code itself.
2. **The licence of the target matters.** umbrelOS's PolyForm Noncommercial licence allows research "without any anticipated commercial application", and "use" means anything that needs a licence [C-TD-flagged-032]. Reading the public source on GitHub needs no licence. Running, copying or decompiling umbrelOS binaries to design a competing commercial product is a question for counsel. This review does not decide it, and OneMind should not do it without advice (see §8).
3. **Decompiling is narrowly allowed by law.** In the US, 17 U.S.C. §1201(f) allows getting around a protection measure only to find what is needed for **interoperability** of an independently created program [C-TD-flagged-030]. In the EU, Directive 2009/24/EC Art. 6 allows decompiling only for interoperability and only the parts needed, and Art. 6(2) forbids using the results to build a program "substantially similar in its expression". Art. 5(3) separately lets a lawful user observe and test a program while running it [C-TD-flagged-031]. "Learn how a competitor's whole OS works so we can build a better one" is not interoperability. Not legal advice.
4. **Craft Anything's purpose is the risk.** Its job is to produce "your own version" of the target. Rebuilding the UI of umbrelOS (PolyForm-NC) or Olares (AGPL) with a coding agent risks moving protected expression into OneMind's Apache-2.0 code, which D-001's guard rail forbids.
5. **Plain tools are enough.** For the one case that needs binary inspection, unpacking a vendor's released image to see its partition layout, REA itself calls Binwalk and Unblob [C-TD-flagged-012]. Use those directly, inside a VM, without an agent layer that sends results to a cloud model [C-TD-flagged-014].

**The narrow exception (REC-FL-2).** Use REA against **OneMind's own** release images, app bundles and the OneMind client, inside a disposable VM with no host credentials and no private network, as a pre-release red team. The question it answers is "what could someone else's agent learn from our box?" That is fully authorized, because we own the target.

### 5.2 Should OneMind adopt BLA-style defenses for its own images?

**Not the deception layers. Yes to the honest audits, using standard tools.**

| Factor | Effect | Requirement |
|---|---|---|
| OneMind's core is Apache-2.0 open source (D-001). Hiding how open code works makes no sense; anyone can read the repo. | Deception adds nothing for open parts | D-001 |
| OneMind promises "everything hosted on the OS is context for AI" and an OS agent that manages the OS. BLA is built to make AI misread files. Decoy functions and fake credentials would also mislead OneMind's own agents (Hermes, the MCP layer) and support tooling. | Direct conflict | AI-1, AI-3, AI-4, R-2 |
| BLA is tuned to REA's internals and REA is already working on a bypass [C-TD-flagged-016], [C-TD-flagged-015]. A 5 to 10 year OS cannot depend on a weeks-old, mostly one-person tool in an arms race. | Brittle | R-3, M-6 |
| Optional fake legal and medical-safety notices [C-TD-flagged-019] in a family and public-safety product. | Trust and legal risk | U-2, M-2, M-4 |
| Fake credentials and decoy code in shipped files can trip security scanners in enterprise and public-safety buyers (gitleaks likely silent [C-TD-flagged-033]; antivirus and DLP **UNVERIFIED**). It also makes SBOMs and CVE triage harder, which the EU Cyber Resilience Act will require (ADR-001 §security). | Compliance friction | R-3, H-1 |
| BLA's own authors say the real protection for secrets is keeping them on trusted servers [C-TD-flagged-022]. | Use the right control instead | U-4 |

**What to protect, and how, if OneMind ships closed "pro" features later** (D-001 says this ADR is still to be written):
- Keep licence checks and paid entitlements **server-side or in hardware** (TPM / secure element on OneMind boxes, ADR-001 Phase 2), not hidden inside client code.
- Never ship signing keys, API keys or customer secrets in an image. Find them with gitleaks or trufflehog in CI (mission §2 rule 5).
- Rely on **signed images and signed app bundles** (ADR-001 D3, the HAOS and Umbrel pattern in §4) for integrity, plus the Apache-2.0 trademark carve-out (brand, Market, certified hardware stay OneMind's, D-001) for business protection.

---

## 6. Recommendations

| ID | Recommendation | Requirements served |
|---|---|---|
| **REC-FL-1** | Do Tier A teardowns from source at pinned commits. Do not use REA or Craft Anything on competitor binaries or UIs. If an image must be unpacked, use Binwalk or Unblob directly in a disposable VM. | RS-1, RS-2, RS-5, A-3, D-001 |
| **REC-FL-2** | Before each hardware release, run REA (pinned version, never `latest`) against OneMind's own images and bundles in a disposable VM with no host credentials or private-network access. Treat findings (leaked secrets, debug endpoints, internal URLs) as release blockers. Use a local or approved model provider, because REA's output goes to the model [C-TD-flagged-014]. | R-2, R-3, H-1, U-4, M-2 |
| **REC-FL-3** | Do not adopt BLA's poison, exhaustion or LLM-directive layers in any OneMind image, app bundle or client. Instead add release gates with standard tools: (a) no source maps with embedded source in shipped web bundles, (b) no debug ports or debuggable flags in release builds, (c) secret scanning of built artifacts as well as git history, (d) signed images and bundles, (e) SBOM per release. BLA's read-only `audit` checks can be used for (a) to (c) as a second opinion, in CI, with `--llm-directives` never enabled. | AI-1, AI-4, R-1, R-3, U-4, M-2, D-001 |
| **REC-FL-4** | When the "pro vs open" ADR is written (D-001 open item), put commercial enforcement server-side or in the secure element, and state in that ADR that OneMind does not ship anti-analysis deception. | D-001, P-5, H-1, M-2 |
| **REC-FL-5** | Copy Craft Anything's licence-gate pattern: a CI allowlist of permissive licences, named per-package exceptions, a ban on linking copyleft code, and a generated third-party licence bundle per release. Feed it into `evidence/license-matrix.csv`. | D-001, A-5, A-6, F-5, R-3 |
| **REC-FL-6** | Study (do not copy code from) the "one capability registry rendered as CLI command and MCP tool" pattern in Craft Anything and REA, and REA's evidence-with-limitations result shape, for OneMind's capability gateway. Both are MIT/Apache-licensed, so even code reuse would be allowed with attribution, but the registry design is the valuable part. | AI-2, AI-3, AI-4, A-5 |
| **REC-FL-7** | Follow BLA's installer hygiene in any future `onemind setup` agent connector: plan by default, write only with explicit consent, back up agent configs without overwriting, pin the registered version, publish with npm provenance, and run no install scripts. | AI-2, UX-8, U-4 |

---

## 7. Strongest case against these conclusions, and what would flip them

| Conclusion | Strongest counter-argument | Response | What would flip it |
|---|---|---|---|
| Don't use REA for teardowns | Some competitor behaviour lives only in binaries (vendor blobs, closed apps in the Umbrel or Olares markets, Olares' cloud services). | True, but those are interoperability questions at most. Handle them one at a time with counsel's sign-off, using Binwalk or Unblob in a VM. | A Tier A question that source cannot answer and that counsel confirms is an interoperability use. |
| Don't ship BLA deception | If OneMind sells a closed robotics or enterprise module, clones are cheap now. REA plus Craft Anything make rebuilding a closed client fast. | Correct threat; wrong control. BLA's own disclaimer says a determined analyst wins [C-TD-flagged-022]. Server-side entitlements, hardware keys, signing and trademark protect revenue without breaking AI-1. | A closed module whose value lives entirely in client code, and evidence (a tested, independent benchmark, not internal estimates) that BLA-style measures hold for months against current REA. |
| REA is safe enough for in-VM red teaming | The 450k-star and 2M-download figures may be inflated, and 160 commits a day means a large, fast-changing, agent-written codebase. | That is why the recommendation is VM-only, pinned version, no host credentials, local model. | A published compromise of `rea-agents` or its dependencies, or provenance attestations that stop matching the repo. |

---

## 8. Open items

- **Counsel question (for `26-OPEN-QUESTIONS-FOR-ZEUS.md`):** Does running or decompiling umbrelOS binaries (PolyForm Noncommercial) inside a VM, to inform a competing commercial OS, count as permitted "research ... without any anticipated commercial application"? This also affects the mission's VM lab for umbrelOS (§7). Reading the public source is not in question. `blocked: founder-decision` (needs counsel).
- **Star authenticity** for REA and Craft Anything: UNVERIFIED, because stargazer listings were blocked here. Re-try from another network, or use a third-party star-history service, before quoting popularity anywhere public.
- **BLA and antivirus / app-store scanners:** UNVERIFIED. Only matters if REC-FL-3 is ever reversed.
- **REA "touhou" topic:** still unexplained and irrelevant to the decision.

---

## Glossary

| Term | Meaning |
|---|---|
| **Reverse engineering** | Working out how software works from the finished program (binary, image, website) rather than from its source code. |
| **Decompiler / disassembler** | Tools that turn machine code back into readable approximations of code. Ghidra (NSA, open source), IDA and Hopper are common ones. |
| **MCP (Model Context Protocol)** | A standard way for an AI agent to call outside tools. REA, Craft Anything and BLA are all MCP servers. |
| **Firmware unpacking** | Splitting a device image into its parts (bootloader, kernel, file systems). Binwalk and Unblob do this. |
| **Clean room** | Rebuilding something only from its public behaviour, without reading its code, to avoid copying protected expression. |
| **Obfuscation** | Making code hard to read while keeping it working. |
| **Decoy / honeypot / canary** | Fake data planted to mislead an attacker or to reveal that someone used it. |
| **Opaque predicate** | A condition that always gives the same answer at runtime but looks uncertain to an analyzer, used to hide dead decoy code. |
| **Prompt injection** | Text written to steer an AI model that reads it. BLA's "hallucinate" layer works in this spirit. |
| **Interoperability exception** | Laws (17 U.S.C. §1201(f), EU Directive 2009/24/EC Art. 6) that allow limited reverse engineering only to make an independent program work with another one. |
| **PolyForm Noncommercial** | umbrelOS's licence: you can read and use it for noncommercial purposes; commercial use needs permission. |
| **SLSA provenance** | A signed record from the build system saying which source and workflow produced a package. |
| **SBOM** | Software bill of materials: the list of every component in a release. Needed for CVE handling and the EU Cyber Resilience Act. |
| **cargo-deny** | A Rust CI tool that fails the build when a dependency has a licence or advisory you have not allowed. |
| **Red team** | Attacking your own product to find weaknesses before others do. |
