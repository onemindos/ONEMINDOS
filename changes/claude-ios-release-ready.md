---
pr: pending
branch: claude/ios-release-ready
status_rows:
  - CORE-MOBILE-7 | in-progress | iPhone release lane built, waits for Apple secrets
---
iPhone release lane that is ready for TestFlight without a device: a release-ios workflow that archives, exports and uploads the signed app only when the Apple secrets exist (otherwise it runs the free checks and stops with a notice), the iOS privacy manifest and export-compliance flag in the app config, an App Store pre-flight check with tests that also runs in the mobile CI, and mobile/docs/ios-release.md listing what to buy, which secrets to add and the first TestFlight steps.
