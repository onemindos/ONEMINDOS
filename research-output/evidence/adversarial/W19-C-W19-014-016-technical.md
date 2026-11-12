# REF3 · W19 · C-W19-014…016 (HACS) · technical lens

**Refuter:** independent, technical lens, 2026-11-11. Existing adversarial files not read.

## Target
- C-W19-014: HACS default lists 5,165 integrations, 1,113 frontend plugins, 551 removals.
- C-W19-015: HACS fetches a "critical" list every 6 h; listed installed repos are uninstalled and HA restarted.
- C-W19-016: HACS publishing checks (manifest schema, brands, ≥1 release, `hacs.json`, no core clash).
- **Conclusion drawn in 29:** HACS is a "**High** fit for the kill-switch pattern"; OneMind's E9 revocation list copies it (fetch every 6 h, store reason + link).

## Strongest counter-argument
The code exists (C-W19-015 is accurate), but **the kill switch has never been used on a real repository**. The `critical` file contains one entry, `test/test`, and has exactly two commits, both on 2019-11-01 [C-REF3-W19-technical-004]. Of 551 removals, one is typed `critical` (the same test entry); 434 are plain `remove` and 70 `blacklist`, and `removal_type` is free text with five spellings of "removed" [C-REF3-W19-technical-005]. In seven years, with 6,000+ repos, HACS's operational revocation has been **delisting**, not uninstalling. So HACS is evidence that a remote-uninstall hook is cheap to write, not that it is a working, exercised process; the hard parts (deciding to fire, false positives, restart side effects on a running home, what "safe state" means) are untested there. Copying it as "high fit" overstates the evidence. Separately, the inclusion gate (C-W19-016) is a structural lint, not a security review, and even that has an 829-PR backlog [C-REF3-W19-technical-006].

## New sources (opened)
- `hacs/default` `critical` file and its commit history at `d1bec96` [C-REF3-W19-technical-004].
- `hacs/default` `removed` file, tallied by `removal_type` [C-REF3-W19-technical-005]; open-PR count [C-REF3-W19-technical-006].

## Verdict: **weakened**
Facts upheld; the "high fit / proven pattern" conclusion is weakened. OneMind should treat the kill list as an **unproven** mechanism: typed (enum, not free text) removal reasons, a scheduled live-fire drill against a canary plugin, and separate "delist" (common) from "disable/uninstall" (rare, audited).

## What would flip it
- **→ upheld:** a peer ecosystem where remote disable/uninstall has fired on real malicious items with a measured false-positive rate (VS Code's block list may qualify; HACS does not).
- **→ refuted:** evidence that HACS's critical path is broken (e.g., the 6-hour fetch silently fails in current releases).
