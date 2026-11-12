<!-- SPDX-License-Identifier: Apache-2.0 -->
# DC-F3 refuter, security lens

**Claim given:** owner-approved ticket + 6-digit pairing code is the universal join; FDO is an optional front end. **Cited:** FABRIC §4, C-FB11-004, C-LAB-fb2-fdo-enroll-003…007.

**Strongest counter-argument.** Human comparison of short codes is weak in practice. In the Bluetooth "Method Confusion" study, none of 40 participants noticed a man-in-the-middle and 37 completed pairing [C-FBREF-009]; owners will approve whatever card shows up with roughly the right name. And FDO hands the owner root code execution on the device during TO2 (lab E4) — a stolen voucher plus an owner service is a remote root.

**New sources:** C-FBREF-009 (IEEE S&P 2021 user study), C-LAB-fb2-fdo-enroll-004 (root via `fdo.command`, this run).

**Verdict: weakened.**

**What would flip it:** a usability test in which owners approve a mismatched code more than rarely (then the join needs a scan-to-confirm flow instead of reading digits), or a voucher-theft path in OneMind's sales process.

**Response (author).** Accepted. OneMind's code is not Bluetooth's: it is derived from the ticket *and* the node's public key (FABRIC §4.1), a ticket alone only lets a machine ask, and the card shows the board, OS and hostname. Still: (1) prefer **scan-to-confirm** (the phone scans a QR on the new machine's console that encodes the pairing hash) over reading digits where a camera exists; (2) the approval card warns when two requests arrive for one ticket; (3) FDO vouchers are imported only by the owner's approval and stored by OneMind (no `fdo.command` from anything but the gateway's fixed join step). Added to `03-…` and ZF-04.
