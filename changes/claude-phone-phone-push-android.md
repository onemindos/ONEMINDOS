---
pr: pending
branch: claude/phone-phone-push-android
---
Android push without Google (issue 828): Settings, Push on Android now guides three steps. It asks the box to install ntfy through one app.install request that waits in Approvals, shows the box's ntfy address to copy with a link to ntfy on F-Droid, then turns on UnifiedPush with the box's VAPID key and Web Push keys and shows the box's registration and the time of the last ping (also when the app was closed). The demo branch is gone, the Kotlin module records ping times, and mobile/docs/push.md and install-android.md describe the real state and the open sign-in gap in front of ntfy on the box.
