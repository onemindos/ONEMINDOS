---
pr: 909
branch: claude/phone-lockscreen-review-deny
---
Phone app: approval notifications get two lock-screen buttons, Review and Deny, and both need the phone unlocked (iOS authenticationRequired, Android setAuthenticationRequired, also on the closed-app UnifiedPush notification). Approve is never a notification button and a tap only opens the approval card. Deny asks for an in-app unlock (expo-local-authentication) before it records the deny on the box. Settings has a new Lock OneMind switch that locks the app on start and again after 30 seconds in the background; it covers the screen only, so background photo backup and push keep their access (issue 704). app.json no longer blocks USE_BIOMETRIC and USE_FINGERPRINT, which the unlock needs on Android; a test keeps them unblocked.
