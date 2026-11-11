# REF3 · W19 · C-W19-021…022 (Obsidian community plugins) · technical lens

**Refuter:** independent, technical lens, 2026-11-11. Existing adversarial files not read.

## Target
- C-W19-021: `community-plugins.json` lists 10,232 plugins (id/name/author/description/repo, no commit pin) and 175 removed.
- C-W19-022 (*partial*, ARCHIVE-GAP): Obsidian "cannot reliably restrict plugins"; Restricted Mode on by default; every plugin version auto-scanned.
- **Conclusion drawn in 29:** desktop/shell plugins (type 3) follow Obsidian's "Restricted Mode" pattern: Verified publishers only, off by default (REC-W19-13); install digests, not repos.

## Strongest counter-argument
"Off by default + reviewed publisher + scanned version" was defeated in the field **without any malicious plugin**. In REF6598 (April 2026), attackers shared a cloud vault whose configuration enabled two legitimate, listed community plugins (Shell Commands, Hider); once the victim turned on community plugin sync, "the Shell Commands plugin immediately triggers execution of attacker-defined commands on vault open" [C-REF3-W19-technical-009]. The malicious element was the configuration, not the code; sync is off by default and cannot be enabled remotely, so social engineering supplied the one click [C-REF3-W19-technical-010]. Signing, countersigning, digest pinning and per-version scanning all pass in this attack. For OneMind, profiles (E8) and confext images carry configuration, and AI tools (E6) can be driven by data: a Verified plugin with a generic "run command"/"call endpoint" capability plus attacker-supplied config is the same shape. The 29 design binds trust to code digests only.

C-W19-022 also remains partial (no archived primary text), so the "every version is scanned" sub-claim should not carry weight.

## New sources (opened)
- Elastic Security Labs, "Phantom in the vault" (2026-04-14) [C-REF3-W19-technical-009].
- The Hacker News coverage (2026-04-16) [C-REF3-W19-technical-010].

## Verdict: **weakened**
C-W19-021 upheld. The "Restricted Mode / off by default" conclusion is weakened: it must be extended to **configuration**: configs and profiles that enable or parameterise execution-capable plugins need the same signature/approval path, and plugins exposing generic command execution should be a separate, owner-approved capability (E2/E6), not a Verified-tier default.

## What would flip it
- **→ upheld:** OneMind's manifest makes "arbitrary command execution" a declared capability requiring per-box owner approval, and unsigned configuration cannot enable it.
- **→ refuted:** a OneMind threat model showing no plugin type can be steered into code execution by data (unlikely for shell/AI types).
