# DC-17 refuter: one OS from Pi 5 to GPU cluster (cost and business lens)

**Target:** DC-17 / gate G5 (Q334, Q98). **Current answer (rev. 2):** G5 is CONDITIONAL for Debian, Ubuntu and bootc alike, so this row is a tie. The small end was measured in VMs: k3s idle uses about 0.9–1.1 GiB [C-W2-053, C-LAB-k3s-footprint-restore-007], which leaves about 2.7 GiB of a 4 GB node for apps. The large end is k3s/RKE2 plus a separate Jetson flavor [C-W2-026, C-W2-027, C-W4-012].
**Refuter:** independent, cost and business lens. Formed before reading other refuters or the author's reasoning. **Verdict: weakened.**

## 1. Re-checking the cited sources

- C-W2-053 and C-LAB-k3s-footprint-restore-007 come from one QEMU/Lima sample each, not from a Pi. They support the memory number but not the cost of the hardware that has to hold it.
- C-W2-026/027 show that the GPU end runs on a different NVIDIA path from the Jetson end. That is a second image family, and a solo developer pays for it in every release (M-6). The COND verdict counts it as a technical caveat. It does not cost it.
- C-W4-012: k3s minors reach EOL about 13–18 months after GA. The fleet therefore gets a Kubernetes upgrade at least yearly on every tier, including the smallest. That recurring labour applies to every tier.

## 2. Strongest counter-argument

G5 was written as a technical question: does the same stack fit on a Pi 5? The founder's promise is economic: the same stack, simple, from a cheap Pi 5 greenhouse box up to a cluster. The economics changed during 2026:

1. **Memory has become the expensive part of the small node.** Raspberry Pi raised Pi 5 and CM5 prices repeatedly in 2026, citing DRAM supply. The 16 GB Pi 5 went from $120 at launch to $385, and even the 2 GB Pi 5 rose to $77.50 in October 2026 [C-REF3-DC-cost-001]. A fixed k3s overhead of about 1 GiB therefore takes roughly a quarter of a 4 GB board's RAM, and RAM is now the component whose price is rising fastest.
2. **The usable floor is probably 8 GB, not 4 GB.** About 2.7 GiB is left on a 4 GB node before OneMind's own gateway, IdP, NATS and any model run (Q98, still unmeasured). If the minimum stack does not fit in 4 GB, the entry SKU becomes an 8 GB board at 2026 prices, and the "simple Pi 5 greenhouse" price point moves up. A non-Kubernetes competitor such as balena (C-W2-040), or a 2 GB or microcontroller edge node, undercuts it. Press coverage also reports makers moving to ESP32 and mini PCs for small jobs (Tom's Hardware headline, not ledgered).
3. **The GPU end got more expensive as well.** NVIDIA raised Jetson prices by up to 101% in July 2026 without notice. The Orin Nano Super kit went from $249 to $399 and AGX Thor from $3,499 to $5,499 [C-REF3-DC-cost-002]. The Robotics tier, which needs its own image flavor, now carries both a higher BOM and a second maintenance pipeline.
4. **The result is two families on two kinds of BOM, both under price pressure.** "One OS" holds for the app platform (k3s APIs). The image, update and driver work splits in two, and the founder's pitch prices the cheapest tier at a level the 2026 BOM may no longer support.

The counter-argument is not that another base passes G5. None does cleanly: Ubuntu has the same Jetson split. The argument is that **COND is too generous at the small end** until someone measures the minimum OneMind stack on a real 4 GB Pi 5 and prices the SKU at current memory costs. If the stack needs 8 GB, the small end of G5 is a business FAIL for the "cheap greenhouse" promise, even though it still passes technically.

## 3. New sources (searched for price shocks, lifecycle cuts, regressions)

| ID | What it shows | Effect |
|---|---|---|
| C-REF3-DC-cost-001 | Raspberry Pi's 2026 DRAM-driven price rises (16 GB Pi 5 at $385; 2 GB Pi 5 at $77.50) | Raises the cost of the small node; every GiB of platform overhead now costs more |
| C-REF3-DC-cost-002 | Jetson price rises of up to 101% in July 2026, unannounced | The Robotics tier's BOM rose while it still needs its own flavor |

Searched, with nothing usable found: a 2026 k3s memory regression on arm64. The closest report, k3s-io/k3s#12452, involves x86 and Fedora, was closed by the stale bot, and named no cause, so it is not ledgered. I could not verify the exact 4 GB and 8 GB Pi 5 prices from an article I opened. They need a direct check against the Raspberry Pi product pages.

## 4. What would flip it

- **Back to COND, or toward PASS:** a ledgered measurement on real 4 GB Pi 5 hardware of the minimum OneMind stack (k3s, gateway, IdP, NATS leaf, one app) with at least 1 GiB of headroom, and a priced 4 GB SKU within the H-1 margin at current Raspberry Pi list prices. A DRAM price rollback, as Upton expects, would also help.
- **To FAIL (business):** the minimum stack needs 8 GB, and the 8 GB Pi 5 or CM5 BOM breaks the entry-tier H-1 margin. A smaller edge tier would then have to drop k3s (agent-only or no Kubernetes), which ends "one OS" at the bottom.
- **Weakens Debian specifically:** none of this. The pressure applies to every base equally, so the DC-17 row stays a tie.
