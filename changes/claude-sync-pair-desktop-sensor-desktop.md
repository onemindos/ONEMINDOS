---
pr: pending
branch: claude/sync-pair-desktop-sensor-desktop
---
Desktop app joins by link or code, second slice of the desktop and small-device pairing (Refs #717): the Tauri app takes the box's `onemind-join:v2` link (or a typed code with the box address and its required CA fingerprint), downloads the box CA and keeps it only if its sha256 matches, then talks to that box only through a client that trusts that one CA. Sign-in (password or an owner's enrolment code) goes over the pinned connection, and the access and refresh tokens are kept in the OS keychain instead of a pasted token; the access token is renewed when the box refuses it. A link for another device, a join without a fingerprint and a box with another CA are refused, and the Rust join-link reader passes the shared vectors in `sdk/testdata/join-qr`.
