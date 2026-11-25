---
pr: pending
branch: claude/ui-notification-centre
---
One notification centre in the dashboard shell. The bell now reads the hub's own notifications (GET /v1/notifications) and lists every open alert that has no notification yet, so a critical disk alert reaches it; marking one read, or all read, is sent to the hub. It refreshes when the hub's event stream (GET /v1/events through the SDK) reports a change and falls back to polling every 30 seconds when the stream is not available. Facts the browser derives from actions and machines stay, minus any the hub already reported. Home gets a small health card with the last backup, open critical alerts and any update on offer, saying "Not reported" where the hub gives no answer. Preferences, quiet hours and web push are not in this slice.
