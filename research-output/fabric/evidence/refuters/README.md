<!-- SPDX-License-Identifier: Apache-2.0 -->
# Refuters for the fabric's decision-critical (P0) conclusions

> **Explain it like I'm the founder.** For each big conclusion, we tried hard to prove ourselves wrong, from several angles (technical, security, long-term risk, cost, robotics), and wrote the best case for the option we did not pick. Where an argument landed, the design changed; the README table shows which.

**Protocol** (RESEARCH-MISSION.md §2 rule 7): each refuter receives only the claim and its cited sources, argues the strongest counter-case, adds at least two **new** sources found by looking for failure or abandonment evidence, gives a verdict (`upheld` / `weakened` / `refuted`) and says what evidence would flip the decision. A `weakened` verdict gets a written response. Each decision also has a **steelman of the runner-up**.

**Disclosure (not blind).** This run had no way to start separate agents. All refuters and steelmen below were written **sequentially by the same agent** that wrote the conclusions, in a separate pass that used only the claim text, its cited claim IDs and new searches. They are therefore *not* independent in the sense of mission 01's blind refuters (`01` §5.1.2 made the same disclosure for FIX4). A blind re-run by separate agents is listed as an open item in `../../14-OPEN-QUESTIONS-FOR-ZEUS.md`.

| Decision | Claim (as given to the refuters) | Refuters | Verdicts | Steelman |
|---|---|---|---|---|
| **DC-F1** | NATS (JetStream on each site hub, a leaf on every node, site hubs leafed to a fleet hub) is the one bus for OneMind; MQTT, Sparkplug, OPC UA, Modbus, CAN, MAVLink and Zenoh/ROS 2 are bridges; per-node isolation uses top-level NATS users with permissions | technical, security, longevity, robotics | weakened, weakened, upheld, upheld | Zenoh as the one bus |
| **DC-F2** | OneMind is many clusters with a hub: one k3s cluster (or single box) per site, never a cluster stretched across sites (except always-online cloud workers), and sites pull desired state from a fleet hub with rings; Rancher Fleet is an optional engine, not core | technical, security, cost/longevity | weakened, weakened, upheld | one big cluster over the mesh |
| **DC-F3** | The owner-approved ticket + pairing code is the universal join; FDO is an optional zero-touch front end for OneMind-built and industrial hardware, gated by voucher import approval | security, longevity, usability/cost | weakened, weakened, upheld | FDO (or a vendor-provisioned key) for every machine |

New sources added by the refuters are ledgered as `C-FBREF-001…012` in `../claims/FBREF.csv`.
