<!-- SPDX-License-Identifier: Apache-2.0 -->
# DC-F1 refuter, technical lens

**Claim given:** NATS is the one bus; everything else bridges; per-node isolation uses top-level NATS users with permissions. **Cited:** C-FB3-001…004, C-LAB-fb3-mesh-nat-006/-012, C-W8-050.

**Strongest counter-argument.** The claim leans on a part of NATS that is less exercised than core pub/sub: permissions on *leaf* connections combined with cross-domain JetStream sourcing. Known defects sit exactly there. An embedded leaf crashed out of memory after 7.4 days because the leaf permission check cached subjects that alias the read buffer (nats-server #8787, open) [C-FBREF-001]. "Allow responses" permissions do not transit a leaf connection, which blocks service replies (#2949, open since 2022) [C-FBREF-003]. ACLs cannot target domain-mapped JetStream API subjects (#6902, open) [C-FBREF-002], which is the very thing the hub's outbox sourcing needs under per-node permissions (NETWORKING's NT-6 is still UNVERIFIED). The repo test that "proves" isolation [C-FB3-001] checks one plain publish in one direction for under a second; it says nothing about week-long leaves, JetStream sourcing or request/reply.

**New sources:** C-FBREF-001, C-FBREF-002, C-FBREF-003 (all GitHub issues in nats-server).

**Verdict: weakened.** NATS as the one bus stands; "per-node isolation with config users is solved" does not.

**What would flip it:** NT-6 failing (outbox sourcing cannot work under per-node permissions), or #8787 reproducing on 2.15.x in a 7-day soak with OneMind's permission set. Then isolation moves to one NATS account per node or operator/JWT mode; the bus choice still holds.

**Response (author).** Accepted. `04-…` §4 item 1 now says "still UNVERIFIED for JetStream sourcing"; the build path adds a 7-day leaf soak with the production permission set and a request/reply check to phase P1's gate (`13-…`); the version pin follows the advisory feed (`DC-F1-security.md`).
