# REF3 · W19 · C-W19-011…013 (Omarchy plugins and marketplace) · technical lens

**Refuter:** independent, technical lens, 2026-11-11. Read only the claims, their cited sources and 29 §1/§7–8 text that uses them. Existing adversarial files were not read.

## Target
- C-W19-011: Omarchy plugins are git-cloned into `~/.config/omarchy/plugins` and run as "arbitrary, unsandboxed code".
- C-W19-012: marketplace install/update clone mutable upstream `HEAD`, not verification-bound; listings need an exact-commit scan and maintainer approval.
- C-W19-013: the security baseline binds validation/scan/approval to one exact SHA, fails closed, flags `curl | sh`, NOPASSWD sudoers, bundled binaries; AI never decides outcomes.
- **Conclusion drawn in 29:** copy the exact-SHA review binding and *enforce it on the box* ("the box installs digests, never branches"), plus the baseline as review rules (§7 items 9–10, §8, REC-W19-06/13).

## Strongest counter-argument
The facts stand; the inference that exact-digest review is a cheap, solved pattern does not. Omarchy's own data shows what the binding costs once a store is popular:
1. **Drift is the normal state.** In a 25-listing random sample, 5 listings' validated branch `HEAD` had already moved past `listingValidatedCommit` [C-REF3-W19-technical-002]. Because install clones `HEAD` [C-W19-012], one in five sampled installs today would run code nobody validated. Enforcing digests on the box (OneMind's fix) turns this from a security gap into a **freshness gap**: users stay on stale versions until review catches up.
2. **Review volume scales with commits, not plugins.** The repository is 3.5 months old (created 2026-07-28) and its issue counter is at #14677, with many items of the form "[Verify]: X, newer upstream commit" [C-REF3-W19-technical-003]; 6,447 sources were validated in that window, 138 IDs retired and 109 repositories migrated [C-REF3-W19-technical-001]. That is roughly 140 tracker items a day for a desktop-theme ecosystem. A solo-developer OneMind (C5 anchors) cannot run human approval per digest at that rate; it needs automated re-validation with human review only for grant/capability diffs, which 29 does not specify.
3. **The baseline is static.** Every rule in C-W19-013 is a static pattern check on the repo at one SHA. It does not cover code fetched at runtime or configuration that weaponises a legitimate plugin (see the Obsidian and GlassWorm files), so "exact SHA reviewed" ≠ "behaviour reviewed".

## New sources (opened)
- Omarchy marketplace `registry.json` at `d2bf9a7` and a 25-repo HEAD-vs-validated-commit comparison via the GitHub API [C-REF3-W19-technical-001, -002].
- Omarchy marketplace repository metadata and issue tracker (created date, issue numbering, "[Verify]" re-verification items) [C-REF3-W19-technical-003].

## Verdict: **weakened**
The three claims are factually upheld. The design conclusion is weakened: exact-digest pinning on the box is right, but the evidence shows it needs an automated re-validation pipeline keyed on diffs (capability/grant changes → human; code-only → automated), and an explicit staleness policy, or the store either lags or the review queue becomes the product.

## What would flip it
- **→ upheld:** a costed OneMind review plan showing automated re-validation per digest, with human review only on manifest/grant diffs, sized to an Omarchy-like update rate (≈100+ updates/day).
- **→ refuted:** evidence that Omarchy's queue is mostly spam/duplicates (real re-verification ≪ 10/day), or that a larger sample shows drift ≪ 5%.
