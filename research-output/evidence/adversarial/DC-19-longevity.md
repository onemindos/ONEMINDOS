# DC-19 · Pi 5 / CM5 pipeline on Debian: refuter, longevity and vendor-risk lens

**Target conclusion** (`01-FOUNDATION-DECISION.md` DC table; `03-base-os.md` G2 row A): the Pi 5 path on Debian is Raspberry Pi's own kernel and firmware from `archive.raspberrypi.com`, shipped in production by umbrelOS [C-W2-044, C-W2-043]; Pi 5 is produced to at least January 2036 [C-W2-029]; this favours A over Ubuntu (certified [C-W2-057] but with an open linux-raspi boot regression [C-DEC-006]) and Fedora (experimental [C-W2-018]).

**Verdict: UPHELD, with a sharper caveat.** The cited claims check out. Nothing found shows that the Pi 5 path needs a OneMind kernel fork. What the conclusion understates is how much OneMind depends on one vendor's apt archive and that vendor's release cadence.

## Strongest counter-argument
"Shipped by umbrelOS" shows the path works today. It does not show the path lasts ten years. In this route the kernel, firmware, bootloader EEPROM and signing key all come from one company's archive. That archive sits outside Debian's security pipeline. Raspberry Pi follows its own OS cadence, and it explicitly does not support moving an installed system across Debian releases. Hardware production to 2036 [C-W2-029] is a promise about boards, not about kernels for an older Debian suite. So for the 2030–2036 window, the Debian base still depends on Raspberry Pi continuing to publish a kernel for whichever suite OneMind runs.

## New sources (searched for failure, regressions, lifecycle cuts)
1. **No supported in-place suite upgrade.** A Raspberry Pi engineer wrote: "we do not recommend updating an existing bookworm image, and offer no support for problems encountered when attempting this" [C-REF-DC-longevity-001]. This matters little for an A/B image that is rebuilt and replaced; umbrelOS moved 12 to 13 that way. It does mean OneMind must test each Debian rebase of the Pi layers itself, with no vendor support.
2. **Archive signing-key breakage.** From 2026-02-01, apt rejected `archive.raspberrypi.com` for trixie and bookworm because of a SHA1 binding signature. Some users were still reporting it in 2026-08 [C-REF-DC-longevity-002]. An appliance whose image build pulls from this archive breaks when the vendor's keys change, so the image build must pin a snapshot and a keyring.
3. **The vendor kernel has its own ABI choices.** The default Pi 5 `kernel_2712` uses 16K pages. Falco 0.40.0 would not start because of a jemalloc page-size abort, and other projects hit the same issue [C-REF-DC-longevity-003]. Any OneMind app or third-party container with jemalloc built for 4K pages fails only on Pi 5. That is a test-matrix cost x86 does not have.

## What would flip it
- Raspberry Pi stops publishing `linux-image-rpi-2712` for a Debian suite while OneMind still ships that suite. Watch the archive's dists list and the Pi kernel branch policy at each Debian release.
- An archive outage or key rotation that a pinned snapshot can't absorb, forcing a carried kernel package. That would meet the DC-19 flip condition: "can't be maintained without carrying a fork".
- On the other side, Ubuntu's Pi 5 position improves if Launchpad #2170238 is fixed and stays fixed [C-DEC-006]. That would narrow A's lead on this row to a tie.

**Recommendation to the author (not applied):** add "pin `archive.raspberrypi.com` snapshot plus keyring in the Bakery recipe" and "Pi 5 16K-page CI cell" to the risk register for the Lite tier.
