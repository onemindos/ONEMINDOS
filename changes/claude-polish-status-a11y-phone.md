---
pr: pending
branch: claude/polish-status-a11y-phone
---
Desktop polish 2 (status meaning, accessibility, phone), colour-independent: the dock and the jobs tray no longer push the phone layout wider than the screen (the dock was off screen on Home); the dock names every icon at 12 px on phones; menu bar, window and tab targets are 44 px and the avatar is tonal at 36 px; one pending approval shows one badge (the Approvals dock badge) instead of also counting in the bell; every freshness state and the jobs indicator has its own shape (unknown is a dashed ring with a question mark, stale a triangle, offline a dash, progress an open arc) and no status pill is ever without a word; placeholder text, control borders (new control-border token at 3:1), a selected row that differs from the focus ring, scroll padding above the dock, a minimum pane opacity, and prefers-contrast and forced-colors rules.

Fix round: one main-button colour. The primary button (Approve, Request install, the passkey button, the Settings preview) is neutral ink and never red; red stays on Deny and danger. The launchpad scrim has an opaque floor (97 percent), hides the dock while open, and its last row clears the safe area.
