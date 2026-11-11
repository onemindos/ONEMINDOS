# REF3 · W19 · C-W19-017…020 (Home Assistant blocklist, quality scale, manifest, Works with HA) · technical lens

**Refuter:** independent, technical lens, 2026-11-11. Existing adversarial files not read.

## Target
- C-W19-017: core hard-codes `BLOCKED_CUSTOM_INTEGRATIONS` with minimum versions and warns on every custom integration.
- C-W19-018: the quality scale has 20 Bronze, 10 Silver, 21 Gold, 3 Platinum rules.
- C-W19-019: hassfest makes `version` mandatory for custom integrations and validates type/iot_class/quality_scale.
- C-W19-020: Works with Home Assistant: CHF 500/yr, lab testing, local control, Gold integration, FCC/CE.
- **Conclusions drawn in 29:** copy the Bronze–Platinum ladder (Bronze = minimum for Verified, Gold for Certified); "blocklist by version (HA core pattern)"; "Works with OneMind" modelled on WWHA.

## Strongest counter-argument
1. **The ladder is mostly unused even by its owner.** At core `d9115f3`, of 1,418 non-virtual integrations, 565 have no `quality_scale` and 282 are `legacy`, i.e. 60% are unrated two years after the rules-based scale; only 152 (≈11%) are Gold or Platinum [C-REF3-W19-technical-007]. A Gold floor (WWHA, and OneMind's Certified tier) excludes ~89% of HA's own first-party integrations. For a solo-developer platform with no third parties yet, a 54-rule ladder risks being specification without enforcement; 29 should state which rules are machine-checked (hassfest-style) versus self-declared.
2. **The version blocklist is reactive and rides the host release train.** The `dreame_vacuum` entry followed a field incident: v1.0.2/1.0.3 put HA 2024.5.0 into a reboot loop and users were told by forum PSA to update first [C-REF3-W19-technical-008]; the minimum-version block landed in core afterwards (C-W19-017). Because the list is compiled into core, it protects only boxes that already installed the fixed core, and boot-loop boxes may never get there. OneMind's equivalent must be **data, fetched and applied before plugins load** (E9's list), not a constant in `onemindd`.
3. C-W19-019/020 hold as stated; the WWHA fee and lab model is a business template, not technical evidence that the bar is achievable by small vendors.

## New sources (opened)
- Home Assistant core manifests at `d9115f3`, tallied by `quality_scale` (sparse checkout) [C-REF3-W19-technical-007].
- HA community PSA on 2024.5 upgrade failure and `dreame_vacuum` (2024-05-02) [C-REF3-W19-technical-008].

## Verdict: **weakened**
Facts upheld. The adoption conclusions are weakened: the quality ladder needs a machine-checked core (and an explicit "unrated" state that is allowed), and the version blocklist must be out-of-band data evaluated before plugin load, or it repeats HA's crash-first pattern.

## What would flip it
- **→ upheld:** OneMind's spec makes Bronze fully machine-checkable in CI, and the version blocklist is part of the signed revocation feed applied pre-load at boot.
- **→ refuted:** evidence that HA's Gold+ share is rising fast enough that a Gold floor is normal for comparable device vendors (e.g. most WWHA-certified devices' integrations are already Gold+ without vendor work).
