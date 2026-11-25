<!-- SPDX-License-Identifier: Apache-2.0 -->
# Beyond-umbrelOS benchmark

**Part:** clients, core. **State:** benchmark done, issues to file. This is our own comparison from public product behaviour. No umbrelOS text or screenshots are copied here.

**Result:** of 44 screens compared, OneMind is better on 12, level on 11, weaker on 14 and missing 7. OneMind already wins on trust, more than one person, approvals and seeing every machine. Almost every weak or missing screen has its backend on main and no screen to reach it, so closing the gap is mostly wiring.

## Close the gap (P0)

- Files window in the dashboard (rail, breadcrumb, upload, grid and list), tied to #141.
- Wire Rewind and restore against the backup routes (#241, #145, PR #444).
- Backups: add a destination and show state.
- Live usage (PR #441), restart and shutdown (PR #355, #493), Machines.
- AI-connections onboarding.

## Beyond: features only OneMind can offer

- One "Needs you" queue for every approval, health fix and critical alert.
- A trust pill and trust view.
- A first ten minutes that pairs the phone by QR, creates a passkey owner and checks that the recovery kit was saved.

## What is left

Turn the P0 list into issues and attach them to the UI sprint.
