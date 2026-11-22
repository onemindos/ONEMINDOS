---
pr: 923
branch: claude/d12-phone-apk-release
---
Every release now carries the phone app. A new android job in the release workflow (no trigger change, still behind the F-27 gate and the release environment) builds the Android APK from the commit the released image was built from, with the version stamped to the release and the upload key from the secrets store; it refuses to run without the signing secrets, so no debug-signed app is ever released. The new scripts/check-apk then refuses an APK whose package is not com.onemindos.*, whose version is not the tag, that is debuggable or debug-signed, or whose bundle still carries the demo-data module. The publish job attaches onemind-VERSION.apk, its SHA-256 file and a signature of that file made with the release key (scripts/release/apk-assets.py, verified before upload), tags the release at the same commit and links the Android install guide in the notes.
