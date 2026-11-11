# W19 refuter (cost and business): DC-16 trust root (E9 / REC-W19-06)

The conclusion has no claim ID of its own. Its evidence is C-W19-011, 012, 015, 021 to 023, 025, 026, 028 and 033, so this file is named after E9.

| Field | Value |
|---|---|
| Claim | OneMind installs only digest-pinned, publisher-signed and OneMind-countersigned plugins, publishes from CI only, and keeps a signed revocation list that disables to a safe state and never substitutes code. |
| Lens | Cost and business |
| Protocol | RESEARCH-MISSION.md §2 rule 7; conclusion and cited claims only. |
| Date | 2026-11-10 (re-check by 2027-05-10) |
| Verdict | **weakened** (the design direction stands; its cost and the limits of signing are not addressed) |

## 1. Re-check of the cited sources
- The cited sources support the negative case: unpinned HEAD clones in Omarchy, umbreld and Obsidian (C-W19-011, 012, 033, 021, 022). They also support the positive case: VS Code signing and block-list uninstall (C-W19-023) and HACS's 6-hour critical list (C-W19-015). The incident sources (C-W19-025, 026, 028) support CI-only publishing and "never substitute code".
- Every positive example is run by a funded organisation (Microsoft for VS Code) or a large community (HACS, with 5,165 integrations per C-W19-014). None of the cited sources gives the cost of operating review, countersigning and revocation.

## 2. Strongest counter-argument
1. **A countersignature is a promise that someone reviewed the plugin, and review costs staff.** The Eclipse Foundation says Open VSX "requires significant investment in security, staffing, maintenance, and operations", is kept running by "fewer than 50 people", and "the current model of unlimited, no-cost use cannot continue indefinitely" [C-REF-W19-cost-004]. Open VSX is also the registry where GlassWorm got through (C-W19-025). For OneMind, every plugin waits in a review queue held by a very small team. That slows the ecosystem, and when a countersigned plugin turns out to be malicious, the countersignature puts liability on OneMind.
2. **Signing and sandboxing do not stop the most costly attack.** In the Snap Store, the scam apps were signed, strictly confined snaps labelled "safe". One fake wallet cost a user about 9 BTC (around $490k), and replacements came from new accounts, so Canonical fell back to *manual review of every new name* [C-REF-W19-cost-007]. Countersigning does not fix publisher-identity abuse. Name and identity policy (verified publishers, reserved names) is the control that worked, and it is a staffed process.
3. **Signing infrastructure gets retired.** Docker Content Trust and Notary v1 shut down on 2026-12-08 [C-REF-W19-cost-002]. A bespoke dual-signature format would leave OneMind maintaining the tooling alone. The trust root should use an OCI-native standard (Sigstore/cosign or Notation) for both signatures.

## 3. New sources (searched for failures, abandonment and lifecycle cuts; all opened 2026-11-10)
| ID | Source |
|---|---|
| C-REF-W19-cost-004 | https://eclipse-foundation.blog/2025/09/23/businesses-built-on-open-infrastructure-have-a-responsibility-to-sustain-it/ |
| C-REF-W19-cost-007 | https://www.theregister.com/2024/03/28/canonical_snap_store_scams/ (secondary; the Snapcraft forum policy post is the primary) |
| C-REF-W19-cost-002 | https://docs.docker.com/retired/ |

## 4. Verdict
**Weakened.** Keep digest pinning, CI-only publishing and a signed revocation list: they are cheap and automatable. Make the **OneMind countersignature tiered**:
- automatic (scan plus provenance) for a community tier;
- human-reviewed only for a Verified tier;
- name and identity policy for sensitive categories.

Build both signatures on Sigstore/cosign or Notation, not a custom format. Put a staffing line in the business plan for review and revocation.

## 5. What would flip it
- **To upheld:** a costed estimate (reviews per week × minutes per review) showing that the release-1 plugin volume fits within the owner's time, or a partner who funds review.
- **To refuted:** evidence that publisher signing plus countersigning measurably did *not* reduce malicious installs relative to automated scanning alone in a comparable registry (VS Code Marketplace, Open VSX or the Snap Store). The cost would then buy no security.
