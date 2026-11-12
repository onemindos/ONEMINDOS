<!-- SPDX-License-Identifier: Apache-2.0 -->
# DC-F3 refuter, usability and cost lens

**Claim given:** as DC-F3. **Cited:** FABRIC §4, C-FB11-004, C-TD-balenaos-035, C-TD-tier-c-robotics-050.

**Strongest counter-argument.** Every competitor that ships at scale skips the human approval: balena bakes a fleet provisioning key into the image (C-TD-balenaos-035), Viam embeds the machine key in the install command (C-TD-tier-c-robotics-050). For a family with ten sensors-and-Pis, an approval per machine is friction; for 1,000 sites it does not scale.

**New sources:** C-FB11-004 (Flight Control also requires an operator to approve enrollment requests, and lets approval add labels), C-FB4-006 (Fleet's one-time token forgotten after registration; reuse with a different token is held pending).

**Verdict: upheld.** The industrial open-source tool with matching constraints (Flight Control) keeps human approval and adds labels at approval time [C-FB11-004]; Fleet keeps a token-holder model but hardened it after advisories [C-FBREF-011]. For bulk joins OneMind can offer a pre-approved batch ticket bound to a count and an expiry (proposal in `14-…` ZF-04), which keeps an owner decision while removing per-machine taps.

**What would flip it:** user testing showing households abandon setup at the approval step.
