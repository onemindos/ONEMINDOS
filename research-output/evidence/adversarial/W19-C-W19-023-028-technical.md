# REF3 · W19 · C-W19-023…028 (VS Code, Open VSX, npm, AUR, WordPress incident lessons) · technical lens

**Refuter:** independent, technical lens, 2026-11-11. Existing adversarial files not read.

## Target
- C-W19-023: VS Code extension host has the editor's permissions; Marketplace scans, signs, verifies publishers, blocks secrets, auto-uninstalls block-listed extensions.
- C-W19-024: `engines.vscode` semver range declares host compatibility.
- C-W19-025: Open VSX GlassWorm (Oct 2025) → token revocation, shorter lifetimes, prefixes, scanning at publication.
- C-W19-026: npm Shai-Hulud (Sep 2025) → 7-day tokens, trusted publishing, FIDO 2FA.
- C-W19-027 (*partial*, SECONDARY): AUR CHAOS RAT packages, live 2 days.
- C-W19-028: WordPress.org forked ACF into SCF and auto-switched sites (2024-10-12).
- **Conclusions drawn in 29 §5:** publish only from CI with OIDC trusted publishing; short-lived prefixed tokens + scanning; copy VS Code's controls; kill list never substitutes code.

## Strongest counter-argument
The registry responses are cited as if they closed the hole. The follow-ups show they did not:
1. **Trusted publishing signs whatever the CI builds.** The first malicious `ultralytics` releases "were published through the existing GitHub Actions workflow, not by an API token", after the attacker poisoned the Actions cache; those uploads carried valid provenance for the real repository [C-REF3-W19-technical-011]. OneMind's "CI-only OIDC publishing" (from C-W19-026) moves the attack surface to the publisher's CI; it does not remove it. A second wave used a leftover long-lived token, so "tokens off" must include revoking old ones.
2. **Scanning at publication misses sleeper updates and off-registry payloads.** After Eclipse's October 2025 remediation (C-W19-025), GlassWorm continued: in March 2026, extensions benign at publication were weaponised in an update about six days later, and for the first time the payload was hosted **outside** Open VSX (GitHub releases), out of reach of the registry takedown [C-REF3-W19-technical-012]. Per-version scanning and a kill list both act on the registry artefact; a runtime-fetched payload escapes both.
3. **C-W19-028 is incomplete.** A preliminary injunction on 2024-12-10 required restoring WP Engine's control of the ACF listing, and ACF was restored to the directory [C-REF3-W19-technical-013]. The lesson ("a kill switch is also a governance weapon") still holds, but the claim should record that the substitution was legally reversed within two months; otherwise it reads as an accepted, permanent precedent.
4. C-W19-023/024 hold. C-W19-027 stays SECONDARY.

## New sources (opened)
- PyPI blog, Ultralytics attack analysis (2024-12-11) [C-REF3-W19-technical-011].
- Socket, GlassWorm sleeper extensions on Open VSX (2026-03-18) [C-REF3-W19-technical-012].
- LWN, WP Engine preliminary injunction (Dec 2024) [C-REF3-W19-technical-013].

## Verdict: **weakened**
Facts upheld (028 needs the injunction addendum). The "lessons" conclusions are weakened: trusted publishing and publish-time scanning are necessary but demonstrably insufficient. OneMind needs (a) reproducible builds or OneMind-side rebuilds for host-touching types, (b) default-deny egress for plugins so runtime payload fetches fail, and (c) a delay/canary window between countersign and fleet rollout for updates (sleeper pattern).

## What would flip it
- **→ upheld:** 29/E9 adds OneMind rebuilds (or reproducibility checks) for types 4/7, plugin egress allowlists, and staged rollout of updates.
- **→ refuted:** evidence that publish-time scanning plus provenance caught sleeper and off-registry payload variants at scale in any major registry.
