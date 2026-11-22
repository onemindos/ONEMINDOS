<!-- SPDX-License-Identifier: Apache-2.0 -->
# Share photos and documents into Files

## Native build

The pinned `expo-sharing@58.0.23` package (MIT) generates the Android intents, the iOS ShareExtension target and both App Group entitlements. It stages each incoming iPhone attachment in the group's cache. OneMind copies the confirmed batch into private storage and uses the pinned `expo-file-system` background URLSession for tus PATCH requests. A scheduled worker can continue from the gateway's saved offset after a process restart. The OS determines its schedule.

The actual published `@bacons/apple-targets@5.0.0` tarball contains an MIT `package/LICENSE`. Its SHA-256 is `88b4960b25273ceb263a78320bdba5951a82a810fa836f3979967b051aae5a14`. Check with `npm pack @bacons/apple-targets@5.0.0 --ignore-scripts` and `tar -xOf bacons-apple-targets-5.0.0.tgz package/LICENSE`. Expo Sharing is the sole generator for this target.

## Founder device run for #713

Android 14, iPhone and Apple Developer account results are pending. On iOS, register `group.com.onemindos.mobile` for the app and extension identifiers and sign both targets (F-4). Install native builds made from this branch. Connect each phone to a real hub with a writable Files root, a nested folder and a second root whose quota can be exhausted.

1. From the system Photos app share a photo to OneMind. Check the name, open the nested folder and cancel. Verify that the hub has received no upload.
2. Share the photo again. Select the nested folder and press **Send to this folder**. From the Files app share a PDF to the same folder. On Android also share an office document, then send several photos with the system share sheet. Check that read-only roots are unavailable.
3. With a transfer in progress, leave the app and lock the phone. On another client verify the destination names and SHA-256 checksums against the originals. Repeat with a PDF larger than 4 MiB, interrupt connectivity, restore it, and confirm that each file arrives once. Record whether delivery completed while suspended, after the OS restarted the process, or after reopening. A user force-stop can suppress OS background scheduling until the next launch.
4. Send a file exceeding the target root's remaining quota. Verify the phone explains the space limit, the file is absent on the hub, and the pending batch can be discarded.

Record device and OS, app commit, hub version, per-step pass or fail and sanitized evidence. Keep private addresses, names and user files off the public issue.
