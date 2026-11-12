# DC-05 · Rebasing without a reflash — longevity refuter (round 4)

> **Refuter round 4 · lens: longevity and vendor risk · 2026-11-11.** Independent refuter (RESEARCH-MISSION.md §2 rule 7). Formed from the DC-05 Result in `decision-critical.md`, `01-FOUNDATION-DECISION.md`, the owning workstream file and the cited claim rows only; no earlier adversarial file was read first. New claims are in `evidence/claims/REF4-DC-longevity.csv`.

## Conclusion under test (rev. 3)
A major rebase without reflash has a **constraint-matched production precedent**: umbrelOS Debian 12 → 13 by OTA bundle [C-W3-039]; bootc rebases by design [C-LAB-fedora-bootc-015]. Flip not met; status partial (OneMind has not run it, test T-W3-04).

## Strongest counter-argument
The precedent proves the *bundle shipped*, not that the fleet stayed updatable afterwards. The public record after the umbrelOS trixie rebase shows the update path degrading:

1. On umbrelOS 1.5.0 amd64 (the first trixie release), a user reports the updater offers nothing beyond 1.5.0 because the **Debian-packaged Mender client 3.4.0 cannot read the format-v3 artifacts** the vendor ships next; manual install fails with "invalid tar header"; no staff response [C-REF4-DC-longevity-006]. A rebase that swaps in the distribution's own update client can strand the box one release later.
2. The next jump, 1.5 → 1.7.1 (April–May 2026), failed on several Intel NUCs and left Pi and mini-PC users with unmounted data disks and broken apps; the community workarounds were **clean install or reflash**, again with no staff reply [C-REF4-DC-longevity-007].

So the only production Debian-major rebase precedent is a mixed result: the rebase step worked, but the device's update chain and data mounts were fragile for at least two releases after it. "Constraint-matched precedent" overstates it. A 10-year box needs two such rebases (13 → 14 → 15) [04 §5.1], so the risk compounds.

## Why it does not flip
The flip condition is "RAUC needs a reflash for a major rebase and a gate-passing alternative does not". Nothing here shows RAUC needs a reflash; the failure mode (distro-packaged update client lagging the artifact format) is already designed out by rev. 3's rule that OneMind builds RAUC from a pinned upstream tag, never the distribution package. The data-mount failures are integration bugs a health gate should catch.

## Verdict: **weakened**
- Required change: describe C-W3-039 as "rebase shipped; post-rebase updates were unreliable in the field" and cite these two threads.
- Required change: T-W3-04 must test **N → N+1 → N+2 OTA after the rebase** (not just the rebase bundle), with an external data disk attached, and must check that the update client and bundle format are carried inside the slot.

## What would flip this verdict
- **To upheld:** T-W3-04 passing a 13 → 14 rebase followed by two further OTAs on x86 and Pi 5 with a data disk, or an official umbrelOS post-mortem showing the 1.5.x issues were unrelated to the rebase.
- **To refuted:** T-W3-04 needing a layout or bootloader change that RAUC cannot apply in place.

## Sources opened (new)
- https://community.umbrel.com/t/umbreld-crashes-every-36h-with-gpf-in-libc-so-6-node-process-on-amd64-umbrelos-1-5-0-update-system-also-broken/24970 [C-REF4-DC-longevity-006]
- https://community.umbrel.com/t/fail-to-update-umbrelos1-5-1-7-1/25043 [C-REF4-DC-longevity-007]

Limits: both are community reports (medium confidence), not vendor statements; the forum's claim that Mender 4.x/5.x needs paid dependencies was **not** confirmed — Mender's docs attribute 403s to a removed repository [C-REF4-DC-longevity-010].
