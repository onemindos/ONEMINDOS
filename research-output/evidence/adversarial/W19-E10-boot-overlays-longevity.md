# W19 · E10 boot-stage overlays: refuter, longevity and vendor-risk lens

**Target conclusion** (`01-FOUNDATION-DECISION.md` §4.8 E10 row, and the DC-16 row in the decision table): boot-stage hardware enablement (device-tree overlays, early-boot drivers) is frozen v1. HAT, CAN and camera overlays ship only through the OneMind release pipeline, inside the RAUC bundle or boot slot, selected by profile. "A vendor whose overlay cannot ship this way is the DC-16 flip case."

**Verdict: WEAKENED.** The mechanism is sound and avoids a fork. The cost of keeping it running over time is unaccounted for, and the flip test only asks "can it ship," not "can it keep shipping."

## Strongest counter-argument
E10 makes OneMind the permanent downstream maintainer of every supported add-on board's overlay and early driver, across every kernel bump, for the life of each box. Field history shows these break on kernel updates, and that the fix lags:
1. **Kernel bumps break vendor overlays and drivers.** Seeed's reTerminal LCD went blank when Raspberry Pi OS moved from kernel 5.15 to 6.1. The vendor's DKMS driver failed to build. The fix took about seven weeks (opened 2023-03-19, merged 2023-05-08) and left the buzzer and LEDs needing an overlay workaround [C-REF-W19-longevity-010].
2. **An appliance OS has hit this itself.** After balenaOS v6.3.38 (kernel 6.1) on a CM4 board, the mcp23017 GPIO-expander overlay stopped producing its gpiochip, and the RS485 port renamed from ttyAMA3 to ttyAMA5. The workaround was hand-copying a 6.6 `.dtbo` onto the boot partition. The real fix was a kernel-bump PR with "no ETA" [C-REF-W19-longevity-011]. Balena is the closest analogue to OneMind's model. The vendor owns the boot partition, so users wait on the vendor's release train.
3. **Device renaming breaks plugins above E10.** A remap like ttyAMA3→ttyAMA5 doesn't stop at the boot stage. It breaks the E2 device grant and the E4/type-4 adapter that named the old node. E10 overlays and E2 grants need stable naming (udev symlinks by path or by overlay) tested on every kernel bump. 01 §4.8 doesn't link them.
4. **Vendor risk sits in a repo OneMind doesn't control.** HAT vendors keep overlays and drivers in their own repos (e.g. `seeed-linux-dtoverlays`) on their own schedule. When a vendor abandons a board, OneMind inherits the source, if the license allows redistribution, or drops the board mid-life. On Jetson the overlay and its pinmux are tied to an L4T release (JetPack 5 EOL 2026-10-30, per W7). Every BSP major means re-porting every overlay.

## New sources
C-REF-W19-longevity-010, 011 in `evidence/claims/REF3-W19-longevity.csv`. Both were opened.

## What would flip it
- **To upheld:** a per-kernel CI cell that boots each certified overlay and asserts its device nodes and names (catching 1–3 before release), plus a "Works with OneMind" clause making the board vendor upstream the overlay to `raspberrypi/linux` or give OneMind a redistributable source with a support term.
- **To refuted:** a day-one board whose overlay or early driver is closed or non-redistributable. Or evidence that keeping overlays current across a Pi or Jetson kernel major needs a carried kernel patch set, which is the fork DC-16 forbids.

**Recommendation to the author (not applied):** extend E10's contract with (a) a stable device-naming rule shared with E2, (b) an overlay regression cell per kernel bump, (c) an end-of-support rule for boards whose vendor stops maintaining the overlay, and (d) count overlay re-porting in the K2/BSP-major cost lines.
