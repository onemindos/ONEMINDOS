<!-- SPDX-License-Identifier: Apache-2.0 -->
# First Android build: the OneMind app live on a real phone

**For:** Zeus · **Date:** 2026-11-26 · **Founder-requested learning entry** ("save this, it is our first time building on Android").
**Serves:** M-LIVE (OneMind running live on the phone, #234), D-021 (1.0 ships with Android), [`mobile/docs/install-android.md`](../../mobile/docs/install-android.md).

## What happened

1. The nightly APK `onemind-android-0.1.0-dev.954-dev-unsigned.apk` (release `dev-20261122-96333e9`) installed on a Samsung Galaxy S24 Ultra (Android 17) and **crashed the moment it opened**. The phone's crash log showed the same crash a day earlier, so every nightly APK was broken.
2. The cause, from the log: `NoSuchMethodException: androidx.work.impl.WorkDatabase_Impl.<init>`.
3. With the fix (below), a local build opened, connected to a OneMind box and showed live data.

Screenshots from that run (status and navigation bars cropped): [home](../../mobile/docs/screenshots/android/01-home.png), [OS updates](../../mobile/docs/screenshots/android/02-os-updates.png), [More](../../mobile/docs/screenshots/android/03-more.png).

## Words you need

- **APK:** the Android app file you install by hand ("sideload").
- **R8:** the tool that shrinks a release app by deleting code it thinks is unused and renaming the rest.
- **WorkManager:** Android's library for background jobs (the app's background tasks use it). It keeps its job list in a small database built with **Room**, which generates a class `WorkDatabase_Impl` that is only created by name at runtime.
- **adb:** Android Debug Bridge, the USB tool that installs apps, reads logs and forwards ports.

## Why it crashed, in plain words

R8 saw that nothing in the code calls `new WorkDatabase_Impl()`, because Room creates it by name when the app starts. So R8 deleted its constructor. At startup Android asked for that constructor, found none, and the app died before showing anything. Tests did not catch it because no test opens the release APK on a phone or emulator.

## The fix

Two "keep" rules for R8, set through `expo-build-properties` in [`mobile/app.json`](../../mobile/app.json):

```text
-keep class * extends androidx.room.RoomDatabase { <init>(); }
-keep class androidx.work.impl.WorkDatabase_Impl { *; }
```

"Keep" tells R8 not to delete or rename those classes. The first rule protects every Room database, so a later library with the same pattern does not break the same way.

## How to repeat it on the Mac

You need Android Studio (it brings Java and the Android SDK), a phone with **USB debugging** on (Settings → About phone → tap Build number 7 times → Developer options → USB debugging), and a USB cable. No emulator image is needed for a real phone.

```sh
# 1. Build the release APK (from mobile/, about 5-10 minutes the first time)
export ANDROID_HOME=$HOME/Library/Android/sdk
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
npm ci
bash scripts/android-release-build.sh ./out 955 0.1.0-dev.955-local

# 2. Install it on the phone
adb devices                      # the phone must say "device"
adb install -r out/onemind-android-0.1.0-dev.955-local-dev-unsigned.apk

# 3. A throwaway box on the Mac (repo root; port 8080 may be taken, so 8099)
ONEMIND_PORT=8099 make -C core run

# 4. Let the phone reach the Mac's box through the cable
adb reverse tcp:8099 tcp:8099
```

In the app: **Hub address** `http://127.0.0.1:8099`, then **Use an access token instead**, token `dev-owner-token-change-me`, then **Connect with the token**. That token is public in the repo (`core/examples/tokens.example.yaml`): use it only on a throwaway box.

Why `adb reverse`: it makes `127.0.0.1:8099` on the phone point to port 8099 on the Mac, through the USB cable. The box then never has to listen on your Wi-Fi.

If the app crashes, read why with `adb logcat -d -b crash | tail -40`.

## What this teaches us

- **A green build is not a working app.** Every nightly built and passed its checks, and every one crashed on open. The next step is a CI smoke test that starts the release APK on an Android emulator and fails if it crashes.
- **Release builds differ from debug builds.** R8 only runs in release, so a crash like this never shows up while developing. Test the release APK.
- **Libraries that create classes by name need keep rules** (Room, WorkManager, anything using reflection).

## Check yourself

1. Why did the app build fine but crash on open?
2. What does a "keep" rule tell R8?
3. Why does `adb reverse` mean the box does not need to be on your Wi-Fi?
4. Which test would have caught this before it shipped?
