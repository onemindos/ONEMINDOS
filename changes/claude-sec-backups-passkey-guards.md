---
pr: pending
branch: claude/sec-backups-passkey-guards
---
Security fix: the backups owner shortcuts (`"approve": true` on backup destinations, runs, verify and restores, and `POST /v1/backups/kit`) now run the same approval guards as `POST /v1/actions/{id}/approve`. Before, they approved directly, so with a passkey registered a stolen owner token or a password-only session could still add an off-box destination, restore an app in place, or mint the backup owner key without a passkey. Now they answer 401 `step_up_required` and the action stays awaiting approval, to be approved the normal way with a passkey assertion. Test added for every shortcut route and the kit. Left: the kit's one-time key is only returned by the shortcut, so with a passkey on, issuing a kit needs its own passkey-bound response.
