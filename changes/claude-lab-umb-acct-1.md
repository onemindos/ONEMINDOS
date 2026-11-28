---
pr: 1141
branch: claude/lab-umb-acct-1
status_rows:
  - UMB-ACCT-1 | in-review | run 2 is lab evidence for F-33 option (a), F-33 stays open; TOTP replay still fails
---
Lab run 2 (virtual authenticator, simulated paths, self-attested test plan, F-33 stays open for Zeus pending the pre-registered UMB-ACCT-13 result) for the Kanidm identity test UMB-ACCT-1, done in a real browser with a virtual passkey on fresh Debian 13 machines running Kanidm v1.12.0. One canonical sign-in name (the passkey's relying-party ID) works from a simulated LAN path and a simulated mesh path with one passkey: enrolled offline with the network cut, signed in on both paths, and accepted again on a fresh machine restored from a backup. Names under the canonical domain worked. At the unrelated test name, Chromium refused sign-in with an RP ID error and enrolment returned HTTP 403 in the tested single-domain configuration. WebAuthn Related Origin Requests share one RP ID across origins. Kanidm's support for related origins or a separate RP ID per domain remains untested. Groups, OIDC, reset links, expiry and revocation pass again. A reused TOTP code is still accepted, and the passkey-minimum policy only blocks new weak credentials. Evidence and scripts are under research-output/evidence/lab/acct-kanidm.
