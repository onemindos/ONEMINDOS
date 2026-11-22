#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Release-mode Android build for CI (dev-android.yml, ci-mobile.yml). Run from mobile/ after `npm ci`.
#   android-release-build.sh OUTDIR VERSION_CODE VERSION_LABEL
# With ANDROID_KEYSTORE_BASE64 (+ ANDROID_KEYSTORE_PASSWORD, ANDROID_KEY_ALIAS, ANDROID_KEY_PASSWORD) set:
#   signed APK  OUTDIR/onemind-android-<label>.apk  and AAB  OUTDIR/onemind-android-<label>.aab
# Without them (forks, today's repo): a debug-signed APK OUTDIR/onemind-android-<label>-dev-unsigned.apk
# (installable by sideloading, not for any store) and no AAB, with a notice. Secrets never touch the log.
set -euo pipefail
out=${1:?outdir}; code=${2:?version code}; label=${3:?version label}
[[ "$code" =~ ^[0-9]+$ ]] || { echo "::error::version code '$code' is not a number"; exit 2; }
[[ "$label" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "::error::version label '$label' has odd characters"; exit 2; }
mkdir -p "$out"; out=$(cd "$out" && pwd)
export ONEMIND_VERSION_CODE="$code"
export JAVA_HOME="${JAVA_HOME_17_X64:-${JAVA_HOME:-}}"

signed=0
if [ -n "${ANDROID_KEYSTORE_BASE64:-}" ] && [ -n "${ANDROID_KEYSTORE_PASSWORD:-}" ] \
   && [ -n "${ANDROID_KEY_ALIAS:-}" ] && [ -n "${ANDROID_KEY_PASSWORD:-}" ]; then
  ks=$(mktemp)
  trap 'rm -f "$ks"' EXIT
  printf '%s' "$ANDROID_KEYSTORE_BASE64" | base64 -d > "$ks"
  export ANDROID_KEYSTORE_PATH="$ks"
  signed=1
else
  echo "::notice::Android signing secrets are not set: building a debug-signed '-dev-unsigned' APK and no AAB"
fi

npx expo prebuild --platform android --no-install
( cd android
  if [ "$signed" = 1 ]; then
    ./gradlew assembleRelease bundleRelease --no-daemon --console=plain
  else
    ./gradlew assembleRelease --no-daemon --console=plain
  fi )

apk=android/app/build/outputs/apk/release/app-release.apk
if [ "$signed" = 1 ]; then
  cp "$apk" "$out/onemind-android-$label.apk"
  cp android/app/build/outputs/bundle/release/app-release.aab "$out/onemind-android-$label.aab"
else
  cp "$apk" "$out/onemind-android-$label-dev-unsigned.apk"
fi

# Permission check: the release APK must request none of the permissions app.json blocks
# (a release build has no developer-menu overlay, so SYSTEM_ALERT_WINDOW must be absent too).
bt=$(ls -d "$ANDROID_HOME"/build-tools/*/ | sort -V | tail -1)
perms=$("${bt}aapt2" dump permissions "$apk")
echo "$perms"
blocked=$(python3 -c 'import json; print("\n".join(json.load(open("app.json"))["expo"]["android"]["blockedPermissions"]))')
bad=0
for p in $blocked; do
  if grep -qF "'$p'" <<<"$perms"; then echo "::error::the release APK requests blocked permission $p"; bad=1; fi
done
[ "$bad" -eq 0 ] || exit 1
echo "no blocked permission requested; versionCode $code"
"${bt}aapt2" dump badging "$apk" | grep -E "^package:" | grep -q "versionCode='$code'" \
  || { echo "::error::the APK's versionCode is not $code"; exit 1; }
ls -l "$out"
