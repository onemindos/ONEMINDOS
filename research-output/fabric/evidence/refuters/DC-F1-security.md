<!-- SPDX-License-Identifier: Apache-2.0 -->
# DC-F1 refuter, security lens

**Claim given:** as DC-F1. **Cited:** C-FB3-001, C-FB3-004, C-LAB-fb3-mesh-nat-008, -012.

**Strongest counter-argument.** "One bus" is one blast radius. In a single release batch (2026-06-29) nats-server published advisories for MQTT SUBSCRIBE protocol injection through leaf-node/route forwarding that allows arbitrary NATS command injection, a pre-auth crash in the leafnode handshake (an incomplete fix of an earlier CVE), MQTT retained/QoS replay that bypasses subscribe deny filters, and leaf connections bypassing a permission check [C-FBREF-012]. OneMind's design puts MQTT devices straight onto NATS's MQTT listener (W8-R1) and every node on a leaf link, which is the combination several of those advisories hit. A memory-exhaustion defect in leaf permission checks is still open [C-FBREF-001]. A compromised or crashed hub NATS takes down every site's control and event path at once.

**New sources:** C-FBREF-012 (four GHSAs), C-FBREF-001.

**Verdict: weakened.**

**What would flip it:** an unpatched pre-auth remote-execution advisory in nats-server, or a pattern of advisories in the leaf/MQTT paths faster than a solo maintainer can ship image updates. Then MQTT devices move behind a separate broker app (Mosquitto) on their own account and leaf links get a second gate.

**Response (author).** Accepted, with mitigations already in the design and two additions: (1) commands are signed and expiring, so a bus compromise alone cannot make a node act (FABRIC §5.4; `07-…` A7); (2) the mesh ACL limits who can reach 7422 (fb3 T4); (3) **new**: MQTT device traffic lands in a separate NATS account with an import into the site account (a proposal for the adapter epic), and (4) **new**: the image's NATS pin must track the advisory feed and the OS security pipeline must treat a nats-server GHSA as a security update (contract §12.13). nats-server v2.15.3 is past all four advisories' patched versions.
