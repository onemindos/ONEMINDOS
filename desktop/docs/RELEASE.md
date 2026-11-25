# Desktop release builds (CLIENT-12)

`.github/workflows/desktop-release.yml` builds the app for every desktop platform and attaches it to a GitHub release.

| Platform | Files | Signed when these secrets exist |
|---|---|---|
| macOS (Apple silicon and Intel, one universal build) | `OneMind_<version>_universal.dmg` | `APPLE_CERTIFICATE` (base64 of the Developer ID Application .p12), `APPLE_CERTIFICATE_PASSWORD`, `APPLE_ID`, `APPLE_TEAM_ID`, `APPLE_APP_SPECIFIC_PASSWORD` (signs and notarizes) |
| Windows | `OneMind_<version>_x64-setup.exe` (NSIS) and `OneMind_<version>_x64_en-US.msi` | `WINDOWS_CERTIFICATE` (base64 of the code-signing .pfx), `WINDOWS_CERTIFICATE_PASSWORD` |
| Linux | `OneMind_<version>_amd64.AppImage` and `OneMind_<version>_amd64.deb` | not signed (checksums only) |

Every run also uploads `SHA256SUMS-desktop`. (The name `SHA256SUMS` already belongs to the OS image release.)

## When it runs

- A pushed `v*` tag attaches to that release.
- After the nightly `dev-build`, it attaches to the newest `dev-*` pre-release.
- After `release.yml` publishes, it attaches to that release. (A release made with the default token does not fire a tag event, so the workflow listens for those two workflows ending.)
- By hand with an empty `tag`: a dry run that builds everything and keeps the files as workflow artifacts for 14 days. Publishes nothing.

It never runs on a pull request, so a PR cannot read the secrets. `ci-desktop.yml` stays the per-PR check.

## Unsigned builds

With no secrets (a fork, or today), a platform still builds, but every file name ends in `-UNSIGNED` and the run prints a warning. macOS: right-click, Open the first time. Windows: SmartScreen shows "unknown publisher".

## Founder steps

1. Apple Developer account: create a Developer ID Application certificate, export it as .p12, `base64 -i cert.p12 | pbcopy`, add the five Apple secrets.
2. Windows: buy a code-signing certificate (an EV certificate avoids SmartScreen warm-up), export .pfx, base64 it, add the two Windows secrets. Cloud-HSM certificates (Azure Trusted Signing, DigiCert KeyLocker) need a different step and are not wired yet.
3. Run the workflow by hand once with an empty tag to prove the three builds, then with a real tag.

Not built yet: the signed auto-updater ([UPDATER.md](UPDATER.md)), MSIX and Flatpak, Linux arm64.
