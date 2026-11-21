<!-- SPDX-License-Identifier: Apache-2.0 -->
# Clients wave: desktop, phone, release lanes

**Part:** clients, site, docs and CI. **State:** 9 draft PRs, reviewed, fixes done.

| PR | What it does | Review |
|---|---|---|
| #488 | Desktop release workflow: macOS universal, Windows, Linux builds with checksums | CHANGES, 2 fix rounds (a test expected the old publish step) |
| #483 | Signed click-to-install desktop auto-update (Tauri updater) | APPROVE, 1 fix |
| #485 | Desktop companion: Needs you, box health, quick requests, login launch, Linux builds | APPROVE |
| #478 | Android dev APK on every dev release | APPROVE |
| #486 | iPhone release lane, ready for TestFlight (needs six Apple secrets) | APPROVE, 1 fix |
| #492 | Phone System section: updates, device info, usage, network, controls | APPROVE |
| #482 | Phone People, Ask a parent, Agents screens | CHANGES, 2 fix rounds (Add person dropped the hub's one-time result) |
| #487 | Phone Files: download, share, upload | APPROVE |
| #481 | One version stamped into desktop and mobile builds | APPROVE, 1 fix |

## What is left

- Founder supplies signing secrets (Apple, Android, desktop updater key). Nothing is signed until then.
- No client has been run on a real device in this wave.
- Re-review of #488 and #482 after the fix rounds.
