<!-- SPDX-License-Identifier: Apache-2.0 -->
# Sovereignty: what can stand between an owner and their OneMind

**For:** Zeus and every builder · **Date:** 2026-11-26 · **Status:** founder-requested audit and checklist.
> "we are a sovereign OS so we need to make ownership as free as possible so users can have it all … not just iOS but everywhere in the OS, when we build any apps or things" (founder, 2026-11-26)

**Sovereign** means the owner can **run, keep, change and move** everything: no hidden cloud, no closed part that can be taken away, no keys that only someone else holds, and no data locked inside an engine. This applies to the whole OS: image, updates, gateway, Market, AI, desktop, phone and every app.

## The checklist (every PR, every dependency, every Market app)

| # | Question | Pass when |
|---|---|---|
| 1 | Does it work offline on the box? | It does everything it can without the internet, and says plainly what needs the internet |
| 2 | Is the licence open? | D-035 rules: only MIT/BSD/Apache-2.0/MPL-2.0/public-domain in app binaries; GPL/AGPL only unmodified, in its own container, behind a standard protocol |
| 3 | Does it need an outside account or cloud service? | No, or it is optional and off by default |
| 4 | Is the data in open, exportable formats? | Yes, and restic backs it up |
| 5 | Does it call home? | Never. No telemetry, and no hidden network calls |
| 6 | Can the owner use their own keys and their own source (updates, catalog, registry)? | Yes, or there is an issue to make it so |
| 7 | Can it be swapped? | It sits behind a OneMind adapter or a standard protocol |
| 8 | Is there a Debian package or Linux feature for this already? | It was checked first, before writing code or adding a dependency |

A builder answers these in the PR (the Codex gate report has a "Sovereignty check" line). The Opus gate refuses a PR that fails one without a recorded reason.

## Audit of release/next, 2026-11-26 (read-only sweep, file:line evidence)

### Already sovereign
- **No telemetry or analytics** (`dashboard/src/pages/PrivacyCard.tsx`). The phone's Apple privacy manifest declares no tracking.
- **Own mesh:** the box runs its own Headscale and DERP server, with no Tailscale servers (`deploy/install.sh`, `internal/mesh/enroll.go`).
- **Android push without Google:** UnifiedPush through the box's own ntfy, with Google's push permission blocked (`mobile/app.json`).
- **Backups open without OneMind:** restic, with the owner key printed in the emergency kit. Destinations are USB, box, REST or S3.
- **Setup needs no account and no cloud:** a local first-boot wizard, plus an offline install bundle (`deploy/bundle.sh`).
- **Secure Boot without Microsoft keys or shim,** and a fully open image with `FIRMWARE=no`.
- **All third-party downloads pinned by sha256** (`deploy/pins.env`). The owner can sign their own Android build (`mobile/plugins/withReleaseSigning.js`).
- **Market:** all 78 apps carry OSI open-source licences, and open-core parts are excluded (Metabase enterprise, Frigate+, SSPL MongoDB).

### What limits the owner today (worst first)

| # | Finding | Evidence | Severity | Fix |
|---|---|---|---|---|
| S1 | **Only OneMind's keys can sign OS updates.** The trust root ships in the read-only image, and an owner cannot take over the keys without building their own image. If the root keys are lost or expire, every box stops updating. | `internal/update/tuf.go:59`, `os/update/CHANNEL.md` §7, `os/update/CEREMONY.md` | High | Founder decision: an **owner trust root** (the owner can add their own TUF root and RAUC keyring, like Secure Boot "sovereign mode"), plus a published key-continuity plan |
| S2 | **Updates, the catalog and desktop app updates are hosted only on GitHub Releases.** The desktop updater URL is compiled in. | `etc/onemind/update.conf:7`, `catalog.conf:6`, `os/update/channel.json`, `desktop/src-tauri/src/updates.rs:23` | High | A second host plus a mirrors list in the signed metadata; a configurable desktop updater endpoint; a mirror kit |
| S3 | **An owner can't add a catalog of their own,** and **iPhone push needs the founder's Apple account** (APNs). The desktop updater key is still a placeholder. | `catalog.conf:3-5`, `mobile/README.md:138`, `desktop/src-tauri/tauri.conf.json:31` | High | Owner catalogs (signed by the owner's own key). iPhone push stays Apple's rule (no way around APNs), with a documented self-built relay for households that want one. |
| S4 | **Secure Boot "sovereign mode"** (the owner enrols their own keys) is planned, not built | `os/secureboot/README.md` | Medium | Build it alongside S1 |
| S5 | **Market app images are pulled from Docker Hub and GHCR** (153 references), with no OneMind mirror and no offline app-image bundle; some images are unsigned | `apps/*/manifests`, `apps/ollama/README.md:88` | Medium | A registry mirror on the box, an offline app bundle, and cosign signatures |
| S6 | Building the image needs snapshot.debian.org, NVIDIA's and Raspberry Pi's archives (build time only; the Pi archive has no snapshots) | `os/rootfs/sources/mkbase.sh`, `os/versions.lock.yaml` | Medium | Vendor or mirror the build sources |
| S7 | The default image includes closed firmware (Debian non-free-firmware, microcode); `FIRMWARE=no` gives a fully open image | `os/rootfs/firmware/README.md` | Medium | Keep the choice visible at download and in Settings |
| S8 | **NVIDIA:** closed drivers (opt-in board); on Jetson the owner must fetch NVIDIA's BSP themselves | `os/boards/*nvidia*`, `os/boards/jetson-orin/README.md` | Medium | Document it as the one non-open path |
| S9 | Android: CI checks that `play-services-auth` is absent, but whether `firebase-messaging` gets in is UNVERIFIED | `.github/workflows/ci-mobile.yml:156` | Low–Med | Extend the check to every `com.google.android.gms` and `com.google.firebase` library (#1291) |
| S10 | Domain checks default to the public resolver 1.1.1.1 (Cloudflare); the feature is off by default | `core/onemind_core/domains.py:57` | Low | Default to the box's own resolver |
| S11 | Model and Market details: the Ollama example pulls a Llama model (restrictive licence); Hermes expects cloud AI keys; licence fields for chromium and esphome are unclear; tautulli and seerr lean toward Plex | as audited | Low | Fix the metadata and the examples; default to Apache or MIT models |
| S12 | "Report a problem" needs a GitHub account | `dashboard/src/pages/troubleshoot/ReportProblem.tsx` | Low | Add a save-a-report-file option |

**What is not in our control:** Apple requires its push service (APNs) and its developer account for iPhone apps. We keep Apple optional: Android, web and desktop never need it.
