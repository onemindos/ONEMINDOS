# REF3 · W19 · E9 trust root (29 §1, 01 §4.8) · technical lens

**Refuter:** independent, technical lens, 2026-11-11. Existing adversarial files not read.

## Target
E9 (Frozen v1): publisher signature, OneMind countersignature, exact-digest pinning, a revocation ("kill") list (fetched every 6 h, at boot, before updates; TUF-style expiry), plugin API levels. Rationale cites C-W19-012, -015, -023, -033 and the incident set C-W19-025…028.

## Strongest counter-argument
E9 binds trust to **who published which bytes**. Four recent failure modes pass every E9 check:
1. **Legitimate pipeline, malicious bytes.** Ultralytics' first malicious releases came out of the project's own trusted-publisher workflow after a cache-poisoning attack [C-REF3-W19-technical-011]. Publisher signature and provenance would be valid; OneMind's countersignature would be applied to the reviewed digest, which *is* the malicious digest unless review catches it.
2. **Benign at review, malicious at the next update, payload off-registry.** GlassWorm sleepers passed publication, turned malicious in an update, and fetched the payload from GitHub, outside the registry [C-REF3-W19-technical-012]. Digest pinning protects only the bytes in the package; a runtime download is not pinned, and the kill list cannot revoke it.
3. **Legitimate code, malicious configuration.** The Obsidian REF6598 campaign weaponised two legitimate, listed plugins via shared configuration [C-REF3-W19-technical-009]. E9 has no notion of signed configuration.
4. **The kill switch it copies has never fired.** HACS's `critical` list holds only a 2019 test entry [C-REF3-W19-technical-004]; Omarchy's digest-bound review already lags HEAD on ~20% of a sample [C-REF3-W19-technical-002]. E9 is being frozen as v1 on patterns that are unexercised (kill) or operationally costly (per-digest review).

Technically, these mean E9 as frozen is **necessary but not the "make every other socket safe" element** 29 claims. The missing parts are runtime: plugin egress default-deny (enforced by E2/network policy), signed configuration/profile inputs (E8) under the same root, staged rollout with a hold window, and OneMind rebuilds for host-touching types (4, 7).

## New sources (opened)
PyPI Ultralytics analysis [C-REF3-W19-technical-011]; Socket GlassWorm sleepers [C-REF3-W19-technical-012]; Elastic REF6598 [C-REF3-W19-technical-009]; HACS `critical` history [C-REF3-W19-technical-004]; Omarchy registry drift sample [C-REF3-W19-technical-002].

## Verdict: **weakened**
E9's mechanisms are right and should ship; its stated role is overstated, and freezing the contract at v1 without configuration signing and a rollout/hold field risks a later breaking change to the very contract 29 says must not change.

## What would flip it
- **→ upheld:** the E9 v1 schema includes signed config/profile objects, a rollout stage/hold field, and a revocation entry type for "disable capability" (not only "remove digest"), and a T-W19 lab drill shows a kill entry disabling a running plugin to a safe state within the expiry window.
- **→ refuted:** a plausible day-one plugin type whose safety depends on runtime-fetched code that E9 cannot pin and E2 cannot block (e.g. AI-skill plugins that must download models/tools at runtime), with no design answer.
