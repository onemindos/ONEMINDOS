<!-- SPDX-License-Identifier: Apache-2.0 -->
# DC-F2 refuter, cost and longevity lens

**Claim given:** as DC-F2. **Cited:** C-FB3-006, C-FB4-007, C-FB4-011.

**Strongest counter-argument.** A solo founder (M-6) cannot afford to build and maintain a fleet engine, a per-site mesh, a fleet hub, summaries and federation. One big cluster over one mesh would be less code. Conversely, the per-site mesh rests on Headscale, whose maintainers state a single-tailnet, small-organisation scope [C-FB3-006] and whose O(N²) reachability computation could not serve thousands of clients in a 2026 report [C-FBREF-006].

**New sources:** C-FBREF-006 (Headscale PR #3156), C-FB4-011 (argocd-agent is pre-1.0: the open pull-model alternatives are young).

**Verdict: upheld.** The Headscale evidence *supports* per-site meshes (one big mesh is the option that would hit the O(N²) wall). The fleet engine reuses pieces already planned (signed jobs over NATS, CORE-UPDATE-9 fleet staging), so the marginal build is ring sequencing plus site summaries, not a new platform. Fleet stays available for Kubernetes-heavy buyers.

**What would flip it:** CORE-UPDATE-9 estimates growing past an L-size epic, or a customer needing hundreds of sites in year 1 → adopt Fleet (or OCM) as the engine and keep OneMind's own logic to approval and summaries.
