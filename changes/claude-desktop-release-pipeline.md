---
pr: pending
branch: claude/desktop-release-pipeline
---
CLIENT-12: new desktop-release workflow builds the Tauri desktop app as a macOS universal .dmg, Windows NSIS .exe and .msi, and Linux .AppImage and .deb, and attaches them with SHA256SUMS-desktop to a GitHub release. It runs on a v* tag, after the nightly dev-build and after release.yml, or by hand (an empty tag is a dry run that publishes nothing); never on a pull request. macOS signing and notarization and Windows signing run only when their secrets exist; otherwise the files are built unsigned and every name ends in -UNSIGNED. The Linux bundles are added to tauri.conf.json. Release steps are in desktop/docs/RELEASE.md.
