---
pr: pending
branch: claude/clients-app-identifier
---
Every client now uses one app identifier domain, com.onemindos.* (the domain the founder owns): mobile is com.onemindos.mobile (Android package and iOS bundle id) and desktop is com.onemindos.desktop (Tauri identifier and keychain service). Store identifiers cannot change after the first upload, and nothing is published yet. A unit test fails if either leaves the domain. Desktop app data moves to a new folder with the new identifier (no released users yet).
