---
pr: 1238
branch: fix/android-workmanager-r8
---
The Android app no longer crashes the moment it opens. The release build's code shrinker (R8) removed the constructor of WorkManager's generated Room database (`WorkDatabase_Impl`), which Android creates by name at startup, so every nightly APK died before showing a screen. `mobile/app.json` now keeps Room database classes and that class. The fixed build was installed on a Samsung Galaxy S24 Ultra, connected to a box and showed live data: the first run of the OneMind app on a real Android phone. A founder learning entry, `docs/learning/android-first-build.md`, explains the crash and how to build, install and connect the app from a Mac, with screenshots in `mobile/docs/screenshots/android/`. The entry also checks the phone's look against DESIGN.md: colours, logo and teal selection match, but primary buttons are teal on the phone and red on the dashboard, a drift left for a separate fix.
