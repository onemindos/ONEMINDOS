---
pr: pending
branch: claude/desktop-auto-update
---
Desktop app updates with the Tauri updater plugin, driven from Rust and switched on only once the founder generates the updater key (the committed public key is a placeholder, so today the app shows nothing and checks nothing). The channel follows the version (a dev build follows dev, everything else stable) and the HTTPS endpoints are compiled in. The popover shows an update strip with the notes and installs only when the person clicks Install and restart, never silently. The update signature and the newer-only rule are enforced by the plugin. A manifest builder (tools/make-latest-json.mjs) turns signed artifacts into latest.json and refuses missing signatures or non-HTTPS URLs, ready for the desktop release workflow.
