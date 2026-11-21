# Install the OneMind app on an Android phone

Every nightly dev release (`dev-<date>-<sha7>` on the repository's Releases page) carries the Android app built from the same commit as the OS images (workflow `dev-android.yml`). It is a development build: it talks to a OneMind hub you run yourself and nothing else.

## Which file

| File in the release | What it is |
|---|---|
| `onemind-android-0.1.0-dev.N.apk` | Release-mode app signed with the OneMind upload key. Present once the founder has added the signing secrets. |
| `onemind-android-0.1.0-dev.N-dev-unsigned.apk` | The same app signed with a throwaway debug key. Installs by sideloading; not for any store. Used until the secrets exist. |
| `onemind-android-0.1.0-dev.N.aab` | Android App Bundle for a later Play Store upload. Not installable by hand; only built when signed. |
| `SHA256SUMS-android` | Checksums: `shasum -a 256 -c SHA256SUMS-android --ignore-missing`. |

`N` is the OS build number (the `-dev.N` of the images in the same release). It is also the Android `versionCode`, so each newer build installs over the older one and keeps your sign-in. **Switching between the signed and the `-dev-unsigned` file needs an uninstall first**, because Android refuses an update signed with a different key.

## Sideload steps (Samsung or any Android 14+ phone)

Passkey sign-in needs Android 14 or newer (the app leaves out Google Play Services; see `mobile/README.md`, Security notes).

1. On the phone, open the release page in the browser and download the `.apk`.
2. Open the download. Android asks to allow installs from that app (Chrome, Files): turn on **Allow from this source**, go back, tap **Install**.
3. If Play Protect warns about an unrecognised app, choose **More details**, then **Install anyway**. A debug-signed or newly signed app is unknown to Play Protect; that is expected.
4. Open OneMind, enter the hub address (for example `http://<hub-address>:8080` on your home network, or its HTTPS name), and sign in. Every change you start is an approval on the hub that you confirm; the phone decides nothing.

Plain `http://` works on a home network and the Connect screen warns about it.

## Updates with Obtainium

[Obtainium](https://obtainium.imranr.dev/) can follow the releases without an app store:

- Add the app with the repository's GitHub URL.
- Turn on **Include prereleases** (every dev build is a pre-release).
- Set the APK filter regex to `^onemind-android-.*\.apk$`; add `-dev-unsigned` handling as you like, for example `^onemind-android-[0-9.]+-dev\.[0-9]+\.apk$` once signed builds exist, or `-dev-unsigned\.apk$` before.
- Because the file name carries `0.1.0-dev.N`, Obtainium sees each build as newer than the last.

Releases older than the newest seven are deleted by `dev-build.yml`, so keep the app updated rather than relying on an old link.

## Building it yourself

`mobile/README.md` has the debug build. The release build CI runs is `mobile/scripts/android-release-build.sh OUTDIR VERSION_CODE LABEL`. Signing is read from the environment, never from the repository: `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`. With none of them set the script still builds, debug-signed, and says so.

UNVERIFIED: the signed path has not run yet (no keystore exists), and no release APK has been installed on a phone as of this writing. The first `dev-android` run and Zeus's Samsung are the proof.
